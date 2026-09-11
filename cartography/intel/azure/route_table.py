import logging
from typing import Any

import neo4j
from azure.mgmt.network import NetworkManagementClient

from cartography.client.core.tx import load
from cartography.client.core.tx import load_matchlinks
from cartography.graph.job import GraphJob
from cartography.intel.azure.util import arm_id
from cartography.models.azure.route_table import AzureRouteSchema
from cartography.models.azure.route_table import AzureRouteTableSchema
from cartography.models.azure.route_table import AzureSubnetToRouteTableRel
from cartography.util import timeit

logger = logging.getLogger(__name__)


def _get_value(data: dict[str, Any], *keys: str) -> Any:
    properties = data.get("properties") or {}
    for key in keys:
        if key in data:
            return data[key]
        if key in properties:
            return properties[key]
    return None


@timeit
def get_route_tables(client: NetworkManagementClient) -> list[dict]:
    """Get a list of all Route Tables in a subscription."""
    return [table.as_dict() for table in client.route_tables.list_all()]


def transform_route_tables(route_tables: list[dict]) -> list[dict]:
    transformed: list[dict[str, Any]] = []
    for table in route_tables:
        transformed.append(
            {
                "id": table.get("id"),
                "name": table.get("name"),
                "location": table.get("location"),
                "provisioning_state": _get_value(
                    table, "provisioning_state", "provisioningState"
                ),
                "disable_bgp_route_propagation": _get_value(
                    table,
                    "disable_bgp_route_propagation",
                    "disableBgpRoutePropagation",
                ),
            }
        )
    return transformed


def transform_routes(route_tables: list[dict]) -> list[dict]:
    """Flatten the routes each table declares, tagging each with its parent table id."""
    transformed: list[dict[str, Any]] = []
    for table in route_tables:
        table_id = table.get("id")
        for route in _get_value(table, "routes") or []:
            transformed.append(
                {
                    "id": route.get("id"),
                    "name": route.get("name"),
                    "ROUTE_TABLE_ID": table_id,
                    "address_prefix": _get_value(
                        route, "address_prefix", "addressPrefix"
                    ),
                    "next_hop_type": _get_value(route, "next_hop_type", "nextHopType"),
                    "next_hop_ip_address": _get_value(
                        route, "next_hop_ip_address", "nextHopIpAddress"
                    ),
                }
            )
    return transformed


def transform_subnet_route_table_links(subnets: list[dict]) -> list[dict]:
    """Subnet to route table links, from transformed subnets carrying route_table_id."""
    return [
        {"NODE_ID": subnet["id"], "ROUTE_TABLE_ID": subnet["route_table_id"]}
        for subnet in subnets
        if subnet.get("route_table_id")
    ]


@timeit
def load_route_tables(
    neo4j_session: neo4j.Session,
    data: list[dict[str, Any]],
    subscription_id: str,
    update_tag: int,
) -> None:
    load(
        neo4j_session,
        AzureRouteTableSchema(),
        data,
        lastupdated=update_tag,
        AZURE_SUBSCRIPTION_ID=subscription_id,
    )


@timeit
def load_routes(
    neo4j_session: neo4j.Session,
    data: list[dict[str, Any]],
    subscription_id: str,
    update_tag: int,
) -> None:
    load(
        neo4j_session,
        AzureRouteSchema(),
        data,
        lastupdated=update_tag,
        AZURE_SUBSCRIPTION_ID=subscription_id,
    )


@timeit
def load_subnet_route_table_relationships(
    neo4j_session: neo4j.Session,
    data: list[dict[str, Any]],
    subscription_id: str,
    update_tag: int,
    route_table_ids: dict[str, str] | None = None,
) -> None:
    """``route_table_ids`` is the id map from ``arm_id.stored_ids``.

    Passed in because this runs once per VNet: rebuilding it here would scan every stored
    route table for every VNet in the subscription.
    """
    if route_table_ids is None:
        route_table_ids = arm_id.stored_ids(neo4j_session, "AzureRouteTable")
    load_matchlinks(
        neo4j_session,
        AzureSubnetToRouteTableRel(),
        arm_id.resolve(data, ("ROUTE_TABLE_ID",), route_table_ids),
        lastupdated=update_tag,
        _sub_resource_id=subscription_id,
        _sub_resource_label="AzureSubscription",
    )


@timeit
def cleanup(neo4j_session: neo4j.Session, common_job_parameters: dict) -> None:
    """Routes first: a route is only reachable through the table that contains it."""
    GraphJob.from_node_schema(AzureRouteSchema(), common_job_parameters).run(
        neo4j_session
    )
    GraphJob.from_node_schema(AzureRouteTableSchema(), common_job_parameters).run(
        neo4j_session
    )


@timeit
def cleanup_subnet_route_table_relationships(
    neo4j_session: neo4j.Session, common_job_parameters: dict
) -> None:
    """Separate from ``cleanup`` so it can run after every subnet link has loaded.

    Route tables sync before subnets, because ``ROUTED_BY`` needs its target to exist.
    Running this cleanup there too would delete the previous links before the current
    ones are written, and a later ``get_subnets`` failure would leave associations that
    still exist in Azure missing from the graph.
    """
    GraphJob.from_matchlink(
        AzureSubnetToRouteTableRel(),
        "AzureSubscription",
        common_job_parameters["AZURE_SUBSCRIPTION_ID"],
        common_job_parameters["UPDATE_TAG"],
    ).run(neo4j_session)


@timeit
def sync(
    neo4j_session: neo4j.Session,
    client: NetworkManagementClient,
    subscription_id: str,
    update_tag: int,
    common_job_parameters: dict,
) -> None:
    route_tables = get_route_tables(client)
    load_route_tables(
        neo4j_session, transform_route_tables(route_tables), subscription_id, update_tag
    )
    load_routes(
        neo4j_session, transform_routes(route_tables), subscription_id, update_tag
    )
    cleanup(neo4j_session, common_job_parameters)
