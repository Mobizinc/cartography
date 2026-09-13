import logging
from typing import Any

import neo4j
from azure.mgmt.network import NetworkManagementClient

from cartography.client.core.tx import load_matchlinks
from cartography.graph.job import GraphJob
from cartography.intel.azure.util import arm_id
from cartography.intel.azure.util.common import get_value
from cartography.intel.azure.util.common import reference_id
from cartography.models.azure.vnet_peering import AzureVirtualNetworkPeeringRel
from cartography.util import timeit

logger = logging.getLogger(__name__)


def _get_resource_group_from_id(resource_id: str) -> str:
    parts = resource_id.lower().split("/")
    return parts[parts.index("resourcegroups") + 1]


@timeit
def get_vnet_peerings(
    client: NetworkManagementClient, rg_name: str, vnet_name: str
) -> list[dict]:
    """Get peerings declared by a single VNet. Per-resource, like get_subnets."""
    return [
        peering.as_dict()
        for peering in client.virtual_network_peerings.list(rg_name, vnet_name)
    ]


def transform_vnet_peerings(vnet_id: str, peerings: list[dict]) -> list[dict]:
    """One link row per peering the local VNet declares.

    A peering whose remote VNet carries no resource id is dropped: the embedded name is
    not an identity, and matching on it would join two unrelated networks.
    """
    transformed: list[dict[str, Any]] = []
    for peering in peerings:
        remote_id = reference_id(
            peering, "remote_virtual_network", "remoteVirtualNetwork"
        )
        if not remote_id:
            logger.warning(
                "Skipping peering %s on %s: it names no remote virtual network id.",
                peering.get("name"),
                vnet_id,
            )
            continue
        transformed.append(
            {
                "NODE_ID": vnet_id,
                "REMOTE_VNET_ID": remote_id,
                "peering_name": peering.get("name"),
                "peering_state": get_value(peering, "peering_state", "peeringState"),
                "allow_forwarded_traffic": get_value(
                    peering, "allow_forwarded_traffic", "allowForwardedTraffic"
                ),
                "allow_gateway_transit": get_value(
                    peering, "allow_gateway_transit", "allowGatewayTransit"
                ),
                "allow_virtual_network_access": get_value(
                    peering,
                    "allow_virtual_network_access",
                    "allowVirtualNetworkAccess",
                ),
                "use_remote_gateways": get_value(
                    peering, "use_remote_gateways", "useRemoteGateways"
                ),
            }
        )
    return transformed


@timeit
def load_vnet_peerings(
    neo4j_session: neo4j.Session,
    data: list[dict[str, Any]],
    subscription_id: str,
    update_tag: int,
) -> None:
    load_matchlinks(
        neo4j_session,
        AzureVirtualNetworkPeeringRel(),
        data,
        lastupdated=update_tag,
        _sub_resource_id=subscription_id,
        _sub_resource_label="AzureSubscription",
    )


@timeit
def cleanup(neo4j_session: neo4j.Session, common_job_parameters: dict) -> None:
    GraphJob.from_matchlink(
        AzureVirtualNetworkPeeringRel(),
        "AzureSubscription",
        common_job_parameters["AZURE_SUBSCRIPTION_ID"],
        common_job_parameters["UPDATE_TAG"],
    ).run(neo4j_session)


@timeit
def collect(client: NetworkManagementClient, vnets: list[dict]) -> list[dict[str, Any]]:
    """Peering rows for one subscription's VNets, collected but not loaded.

    Collection and loading are separate because a peering may name a VNet in another
    subscription. ``load_matchlinks`` only joins endpoints that already exist and does not
    retry, so loading here would silently drop every peering whose remote VNet belongs to
    a subscription this sync has not reached yet.
    """
    rows: list[dict[str, Any]] = []
    for vnet in vnets:
        vnet_id = vnet["id"]
        peerings = get_vnet_peerings(
            client, _get_resource_group_from_id(vnet_id), vnet["name"]
        )
        rows.extend(transform_vnet_peerings(vnet_id, peerings))
    return rows


@timeit
def sync(
    neo4j_session: neo4j.Session,
    rows_by_subscription: dict[str, list[dict[str, Any]]],
    update_tag: int,
    common_job_parameters: dict,
) -> None:
    """Load every subscription's collected peerings, once all VNet nodes exist."""
    vnet_ids = arm_id.stored_ids(neo4j_session, "AzureVirtualNetwork")
    for subscription_id, rows in rows_by_subscription.items():
        load_vnet_peerings(
            neo4j_session,
            arm_id.resolve(rows, ("NODE_ID", "REMOTE_VNET_ID"), vnet_ids),
            subscription_id,
            update_tag,
        )
        cleanup(
            neo4j_session,
            {**common_job_parameters, "AZURE_SUBSCRIPTION_ID": subscription_id},
        )
