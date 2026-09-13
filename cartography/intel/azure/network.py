import logging
from typing import Any

import neo4j
from azure.mgmt.network import NetworkManagementClient

from cartography.client.core.tx import load
from cartography.client.core.tx import load_matchlinks
from cartography.graph.job import GraphJob
from cartography.intel.azure.util.tag import transform_tags
from cartography.models.azure.network_interface import AzureNetworkInterfaceSchema
from cartography.models.azure.network_security_group import (
    AzureNetworkSecurityGroupSchema,
)
from cartography.models.azure.network_security_rule import (
    AzureInboundNetworkSecurityRuleSchema,
)
from cartography.models.azure.network_security_rule import (
    AzureOutboundNetworkSecurityRuleSchema,
)
from cartography.models.azure.public_ip_address import AzurePublicIPAddressSchema
from cartography.models.azure.subnet import AzureSubnetSchema
from cartography.models.azure.subnet import AzureSubnetToNSGRel
from cartography.models.azure.tags.network_security_group_tag import (
    AzureNetworkSecurityGroupTagsSchema,
)
from cartography.models.azure.tags.virtual_network_tag import (
    AzureVirtualNetworkTagsSchema,
)
from cartography.models.azure.virtual_network import AzureVirtualNetworkSchema
from cartography.util import timeit

from . import route_table
from . import vnet_peering
from .util import arm_id
from .util.common import get_value
from .util.common import reference_id
from .util.credentials import Credentials

logger = logging.getLogger(__name__)


def _get_resource_group_from_id(resource_id: str) -> str:
    """
    Helper function to parse the resource group name from a full resource ID string.
    """
    parts = resource_id.lower().split("/")
    rg_index = parts.index("resourcegroups")
    return parts[rg_index + 1]


@timeit
def get_virtual_networks(client: NetworkManagementClient) -> list[dict]:
    """
    Get a list of all Virtual Networks in a subscription.
    """
    return [vnet.as_dict() for vnet in client.virtual_networks.list_all()]


@timeit
def get_subnets(
    client: NetworkManagementClient, rg_name: str, vnet_name: str
) -> list[dict]:
    """
    Get subnets for a single Virtual Network. This is a transient, per-resource call.
    """
    return [subnet.as_dict() for subnet in client.subnets.list(rg_name, vnet_name)]


@timeit
def get_network_security_groups(client: NetworkManagementClient) -> list[dict]:
    """
    Get a list of all Network Security Groups in a subscription.
    """
    return [nsg.as_dict() for nsg in client.network_security_groups.list_all()]


@timeit
def get_public_ip_addresses(client: NetworkManagementClient) -> list[dict]:
    """
    Get a list of all Public IP Addresses in a subscription.
    """
    return [pip.as_dict() for pip in client.public_ip_addresses.list_all()]


@timeit
def get_network_interfaces(client: NetworkManagementClient) -> list[dict]:
    """
    Get a list of all Network Interfaces in a subscription.
    """
    return [interface.as_dict() for interface in client.network_interfaces.list_all()]


def transform_virtual_networks(vnets: list[dict]) -> list[dict]:
    transformed: list[dict[str, Any]] = []
    for vnet in vnets:
        transformed.append(
            {
                "id": vnet.get("id"),
                "name": vnet.get("name"),
                "location": vnet.get("location"),
                "tags": vnet.get("tags"),
                "provisioning_state": get_value(
                    vnet,
                    "provisioning_state",
                    "provisioningState",
                ),
                "address_prefixes": _address_prefixes(
                    get_value(vnet, "address_space", "addressSpace")
                ),
            }
        )
    return transformed


def _address_prefixes(address_space: Any) -> list[str] | None:
    if not isinstance(address_space, dict):
        return None
    return address_space.get("address_prefixes") or address_space.get("addressPrefixes")


def transform_subnets(subnets: list[dict]) -> list[dict]:
    transformed: list[dict[str, Any]] = []
    for subnet in subnets:
        transformed.append(
            {
                "id": subnet.get("id"),
                "name": subnet.get("name"),
                "address_prefix": get_value(
                    subnet,
                    "address_prefix",
                    "addressPrefix",
                ),
                "address_prefixes": get_value(
                    subnet,
                    "address_prefixes",
                    "addressPrefixes",
                ),
                "nsg_id": reference_id(
                    subnet, "network_security_group", "networkSecurityGroup"
                ),
                "route_table_id": reference_id(subnet, "route_table", "routeTable"),
            }
        )
    return transformed


def transform_network_security_groups(nsgs: list[dict]) -> list[dict]:
    transformed: list[dict[str, Any]] = []
    for nsg in nsgs:
        transformed.append(
            {
                "id": nsg.get("id"),
                "name": nsg.get("name"),
                "location": nsg.get("location"),
                "tags": nsg.get("tags"),
            }
        )
    return transformed


def transform_network_security_rules(nsgs: list[dict]) -> list[dict]:
    """
    Flatten the inbound/outbound and default security rules from each NSG into a
    single list, tagging each rule with its parent NSG id.
    """
    transformed: list[dict[str, Any]] = []
    for nsg in nsgs:
        nsg_id = nsg.get("id")

        rule_collections = (
            (get_value(nsg, "security_rules", "securityRules") or []),
            (get_value(nsg, "default_security_rules", "defaultSecurityRules") or []),
        )
        is_default_flags = (False, True)

        for rules, is_default in zip(rule_collections, is_default_flags):
            for rule in rules:
                rule_props = rule.get("properties", {})
                merged = {**rule_props, **{k: v for k, v in rule.items() if v}}
                transformed.append(
                    {
                        "id": rule.get("id"),
                        "name": rule.get("name"),
                        "nsg_id": nsg_id,
                        "description": merged.get("description"),
                        "protocol": merged.get("protocol"),
                        "direction": merged.get("direction"),
                        "access": merged.get("access"),
                        "priority": merged.get("priority"),
                        "source_port_range": merged.get("source_port_range")
                        or merged.get("sourcePortRange"),
                        "source_port_ranges": merged.get("source_port_ranges")
                        or merged.get("sourcePortRanges"),
                        "destination_port_range": merged.get("destination_port_range")
                        or merged.get("destinationPortRange"),
                        "destination_port_ranges": merged.get("destination_port_ranges")
                        or merged.get("destinationPortRanges"),
                        "source_address_prefix": merged.get("source_address_prefix")
                        or merged.get("sourceAddressPrefix"),
                        "source_address_prefixes": merged.get("source_address_prefixes")
                        or merged.get("sourceAddressPrefixes"),
                        "destination_address_prefix": merged.get(
                            "destination_address_prefix"
                        )
                        or merged.get("destinationAddressPrefix"),
                        "destination_address_prefixes": merged.get(
                            "destination_address_prefixes"
                        )
                        or merged.get("destinationAddressPrefixes"),
                        "is_default": is_default,
                    }
                )
    return transformed


def transform_public_ip_addresses(public_ips: list[dict]) -> list[dict]:
    transformed: list[dict[str, Any]] = []
    for public_ip in public_ips:
        transformed.append(
            {
                "id": public_ip.get("id"),
                "name": public_ip.get("name"),
                "location": public_ip.get("location"),
                "ip_address": get_value(public_ip, "ip_address", "ipAddress"),
                "public_ip_allocation_method": get_value(
                    public_ip,
                    "public_ip_allocation_method",
                    "publicIPAllocationMethod",
                ),
            }
        )
    return transformed


def transform_ip_configuration(ip_config: dict) -> dict[str, Any]:
    """One IP configuration of a network interface.

    The private address, the subnet and the public IP stay in the configuration that binds
    them: which subnet a given public IP is reachable on is a fact of the configuration,
    and separate lists cannot state it.
    """
    return {
        "name": ip_config.get("name"),
        "private_ip_address": get_value(
            ip_config, "private_ip_address", "privateIPAddress"
        ),
        "private_ip_allocation_method": get_value(
            ip_config, "private_ip_allocation_method", "privateIPAllocationMethod"
        ),
        "primary": get_value(ip_config, "primary"),
        "subnet_id": reference_id(ip_config, "subnet"),
        "public_ip_id": reference_id(ip_config, "public_ip_address", "publicIPAddress"),
    }


def _stated(ip_configurations: list[dict], field: str) -> list[str]:
    """The values the configurations state for one field, in order, without repeats."""
    return list(dict.fromkeys(c[field] for c in ip_configurations if c[field]))


def transform_network_interfaces(network_interfaces: list[dict]) -> list[dict]:
    transformed: list[dict[str, Any]] = []
    for interface in network_interfaces:
        ip_configurations = [
            transform_ip_configuration(ip_config)
            for ip_config in get_value(
                interface, "ip_configurations", "ipConfigurations"
            )
            or []
        ]

        # Handle case where virtual_machine can be None (unattached NIC)
        # Lowercase the VM ID to match the normalized VM node id (Azure APIs
        # return inconsistent casing for resource group names across services)
        vm_id = reference_id(interface, "virtual_machine", "virtualMachine")

        transformed.append(
            {
                "id": interface.get("id"),
                "name": interface.get("name"),
                "location": interface.get("location"),
                "mac_address": get_value(interface, "mac_address", "macAddress"),
                "ip_configurations": ip_configurations,
                "private_ip_addresses": _stated(
                    ip_configurations, "private_ip_address"
                ),
                "VIRTUAL_MACHINE_ID": vm_id.lower() if vm_id else None,
                "SUBNET_IDS": _stated(ip_configurations, "subnet_id"),
                "PUBLIC_IP_IDS": _stated(ip_configurations, "public_ip_id"),
                "NSG_ID": reference_id(
                    interface, "network_security_group", "networkSecurityGroup"
                ),
            }
        )
    return transformed


@timeit
def load_virtual_networks(
    neo4j_session: neo4j.Session,
    data: list[dict[str, Any]],
    subscription_id: str,
    update_tag: int,
) -> None:
    load(
        neo4j_session,
        AzureVirtualNetworkSchema(),
        data,
        lastupdated=update_tag,
        AZURE_SUBSCRIPTION_ID=subscription_id,
    )


@timeit
def load_subnets(
    neo4j_session: neo4j.Session,
    data: list[dict[str, Any]],
    vnet_id: str,
    subscription_id: str,
    update_tag: int,
) -> None:
    load(
        neo4j_session,
        AzureSubnetSchema(),
        data,
        lastupdated=update_tag,
        VNET_ID=vnet_id,
        AZURE_SUBSCRIPTION_ID=subscription_id,
    )


@timeit
def load_network_security_groups(
    neo4j_session: neo4j.Session,
    data: list[dict[str, Any]],
    subscription_id: str,
    update_tag: int,
) -> None:
    load(
        neo4j_session,
        AzureNetworkSecurityGroupSchema(),
        data,
        lastupdated=update_tag,
        AZURE_SUBSCRIPTION_ID=subscription_id,
    )


@timeit
def load_network_security_rules(
    neo4j_session: neo4j.Session,
    data: list[dict[str, Any]],
    subscription_id: str,
    update_tag: int,
) -> None:
    """
    Load NSG rules into Neo4j, splitting Inbound and Outbound rules so each
    batch picks up the appropriate ontology label (`IpPermissionInbound` vs
    `IpPermissionEgress`).
    """
    inbound = [r for r in data if (r.get("direction") or "").lower() == "inbound"]
    outbound = [r for r in data if (r.get("direction") or "").lower() == "outbound"]
    if inbound:
        load(
            neo4j_session,
            AzureInboundNetworkSecurityRuleSchema(),
            inbound,
            lastupdated=update_tag,
            AZURE_SUBSCRIPTION_ID=subscription_id,
        )
    if outbound:
        load(
            neo4j_session,
            AzureOutboundNetworkSecurityRuleSchema(),
            outbound,
            lastupdated=update_tag,
            AZURE_SUBSCRIPTION_ID=subscription_id,
        )


@timeit
def load_public_ip_addresses(
    neo4j_session: neo4j.Session,
    data: list[dict[str, Any]],
    subscription_id: str,
    update_tag: int,
) -> None:
    load(
        neo4j_session,
        AzurePublicIPAddressSchema(),
        data,
        lastupdated=update_tag,
        AZURE_SUBSCRIPTION_ID=subscription_id,
    )


@timeit
def load_network_interfaces(
    neo4j_session: neo4j.Session,
    data: list[dict[str, Any]],
    subscription_id: str,
    update_tag: int,
) -> None:
    load(
        neo4j_session,
        AzureNetworkInterfaceSchema(),
        data,
        lastupdated=update_tag,
        AZURE_SUBSCRIPTION_ID=subscription_id,
    )


@timeit
def load_subnet_nsg_relationships(
    neo4j_session: neo4j.Session,
    data: list[dict[str, Any]],
    vnet_id: str,
    update_tag: int,
) -> None:
    """
    Loads the relationships from Subnets to the Network Security Groups they are associated with.
    """
    load_matchlinks(
        neo4j_session,
        AzureSubnetToNSGRel(),
        data,
        lastupdated=update_tag,
        _sub_resource_id=vnet_id,
        _sub_resource_label="AzureVirtualNetwork",
    )


@timeit
def load_virtual_network_tags(
    neo4j_session: neo4j.Session,
    subscription_id: str,
    vnets: list[dict],
    update_tag: int,
) -> None:
    tags = transform_tags(vnets, subscription_id)
    load(
        neo4j_session,
        AzureVirtualNetworkTagsSchema(),
        tags,
        lastupdated=update_tag,
        AZURE_SUBSCRIPTION_ID=subscription_id,
    )


@timeit
def cleanup_virtual_network_tags(
    neo4j_session: neo4j.Session, common_job_parameters: dict
) -> None:
    GraphJob.from_node_schema(
        AzureVirtualNetworkTagsSchema(), common_job_parameters
    ).run(neo4j_session)


@timeit
def load_nsg_tags(
    neo4j_session: neo4j.Session,
    subscription_id: str,
    nsgs: list[dict],
    update_tag: int,
) -> None:
    tags = transform_tags(nsgs, subscription_id)
    load(
        neo4j_session,
        AzureNetworkSecurityGroupTagsSchema(),
        tags,
        lastupdated=update_tag,
        AZURE_SUBSCRIPTION_ID=subscription_id,
    )


@timeit
def cleanup_nsg_tags(neo4j_session: neo4j.Session, common_job_parameters: dict) -> None:
    GraphJob.from_node_schema(
        AzureNetworkSecurityGroupTagsSchema(), common_job_parameters
    ).run(neo4j_session)


@timeit
def _sync_virtual_networks(
    neo4j_session: neo4j.Session,
    client: NetworkManagementClient,
    subscription_id: str,
    update_tag: int,
    common_job_parameters: dict,
) -> list[dict]:
    """
    Syncs Virtual Networks and returns the raw vnet list for further processing.
    """
    vnets = get_virtual_networks(client)
    transformed_vnets = transform_virtual_networks(vnets)
    load_virtual_networks(neo4j_session, transformed_vnets, subscription_id, update_tag)
    load_virtual_network_tags(neo4j_session, subscription_id, vnets, update_tag)
    GraphJob.from_node_schema(AzureVirtualNetworkSchema(), common_job_parameters).run(
        neo4j_session
    )
    cleanup_virtual_network_tags(neo4j_session, common_job_parameters)
    return vnets


@timeit
def _sync_network_security_groups(
    neo4j_session: neo4j.Session,
    client: NetworkManagementClient,
    subscription_id: str,
    update_tag: int,
    common_job_parameters: dict,
) -> None:
    """
    Syncs Network Security Groups and the inbound/outbound security rules they
    contain.
    """
    nsgs = get_network_security_groups(client)
    transformed_nsgs = transform_network_security_groups(nsgs)
    load_network_security_groups(
        neo4j_session, transformed_nsgs, subscription_id, update_tag
    )
    transformed_rules = transform_network_security_rules(nsgs)
    load_network_security_rules(
        neo4j_session, transformed_rules, subscription_id, update_tag
    )
    load_nsg_tags(neo4j_session, subscription_id, nsgs, update_tag)
    # Both rule schemas share the AzureNetworkSecurityRule node label, so a
    # single cleanup pass covers nodes loaded under either schema.
    GraphJob.from_node_schema(
        AzureInboundNetworkSecurityRuleSchema(), common_job_parameters
    ).run(neo4j_session)
    GraphJob.from_node_schema(
        AzureNetworkSecurityGroupSchema(), common_job_parameters
    ).run(neo4j_session)
    cleanup_nsg_tags(neo4j_session, common_job_parameters)


@timeit
def _sync_public_ip_addresses(
    neo4j_session: neo4j.Session,
    client: NetworkManagementClient,
    subscription_id: str,
    update_tag: int,
    common_job_parameters: dict,
) -> None:
    """
    Syncs Public IP Addresses.
    """
    public_ip_addresses = get_public_ip_addresses(client)
    transformed_public_ips = transform_public_ip_addresses(public_ip_addresses)
    load_public_ip_addresses(
        neo4j_session, transformed_public_ips, subscription_id, update_tag
    )
    GraphJob.from_node_schema(AzurePublicIPAddressSchema(), common_job_parameters).run(
        neo4j_session
    )


@timeit
def _sync_network_interfaces(
    neo4j_session: neo4j.Session,
    client: NetworkManagementClient,
    subscription_id: str,
    update_tag: int,
    common_job_parameters: dict,
) -> None:
    """
    Syncs Network Interfaces.
    """
    network_interfaces = get_network_interfaces(client)
    transformed_network_interfaces = transform_network_interfaces(network_interfaces)
    load_network_interfaces(
        neo4j_session, transformed_network_interfaces, subscription_id, update_tag
    )
    GraphJob.from_node_schema(AzureNetworkInterfaceSchema(), common_job_parameters).run(
        neo4j_session
    )


@timeit
def _sync_subnets(
    neo4j_session: neo4j.Session,
    client: NetworkManagementClient,
    vnets: list[dict],
    subscription_id: str,
    update_tag: int,
    common_job_parameters: dict,
) -> None:
    """
    Syncs Subnets and their relationships for a given list of VNets.
    """
    route_table_ids = arm_id.stored_ids(neo4j_session, "AzureRouteTable")

    for vnet in vnets:
        vnet_id = vnet["id"]
        rg_name = _get_resource_group_from_id(vnet_id)
        subnets = get_subnets(client, rg_name, vnet["name"])
        transformed_subnets = transform_subnets(subnets)
        load_subnets(
            neo4j_session, transformed_subnets, vnet_id, subscription_id, update_tag
        )

        subnet_nsg_rels = []
        for subnet in transformed_subnets:
            if subnet.get("nsg_id"):
                subnet_nsg_rels.append(
                    {"NODE_ID": subnet["id"], "NSG_ID": subnet["nsg_id"]}
                )

        if subnet_nsg_rels:
            load_subnet_nsg_relationships(
                neo4j_session, subnet_nsg_rels, vnet_id, update_tag
            )

        route_table_rels = route_table.transform_subnet_route_table_links(
            transformed_subnets
        )
        if route_table_rels:
            route_table.load_subnet_route_table_relationships(
                neo4j_session,
                route_table_rels,
                subscription_id,
                update_tag,
                route_table_ids,
            )

        subnet_cleanup_params = common_job_parameters.copy()
        subnet_cleanup_params["VNET_ID"] = vnet_id
        GraphJob.from_node_schema(AzureSubnetSchema(), subnet_cleanup_params).run(
            neo4j_session
        )


@timeit
def sync(
    neo4j_session: neo4j.Session,
    credentials: Credentials,
    subscription_id: str,
    update_tag: int,
    common_job_parameters: dict,
) -> list[dict[str, Any]]:
    """Returns the VNet peering rows collected for this subscription, unloaded."""
    logger.info(f"Syncing Azure Networking for subscription {subscription_id}.")
    client = NetworkManagementClient(credentials.credential, subscription_id)

    vnets = _sync_virtual_networks(
        neo4j_session, client, subscription_id, update_tag, common_job_parameters
    )

    # Route tables must be synced before Subnets so that Subnet->RouteTable links resolve
    route_table.sync(
        neo4j_session, client, subscription_id, update_tag, common_job_parameters
    )

    _sync_network_security_groups(
        neo4j_session, client, subscription_id, update_tag, common_job_parameters
    )

    # Subnets must be synced before Network Interfaces so that NIC→Subnet relationships work
    if vnets:
        _sync_subnets(
            neo4j_session,
            client,
            vnets,
            subscription_id,
            update_tag,
            common_job_parameters,
        )

    # Outside the guard: subnet cleanup is scoped per VNet, so an authoritative empty VNet
    # list cleans no subnets and would otherwise strand their route-table links forever.
    # Every current link has loaded by now, whether that was none or many.
    route_table.cleanup_subnet_route_table_relationships(
        neo4j_session, common_job_parameters
    )

    # Public IPs must be synced before Network Interfaces so that NIC→PublicIP relationships work
    _sync_public_ip_addresses(
        neo4j_session, client, subscription_id, update_tag, common_job_parameters
    )

    _sync_network_interfaces(
        neo4j_session, client, subscription_id, update_tag, common_job_parameters
    )

    # Collected, not loaded: a peering can name a VNet in a subscription this run has not
    # synced yet. The caller loads them once every subscription's VNets exist.
    return vnet_peering.collect(client, vnets)
