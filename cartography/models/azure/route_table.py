import logging
from dataclasses import dataclass

from cartography.models.core.common import PropertyRef
from cartography.models.core.nodes import CartographyNodeProperties
from cartography.models.core.nodes import CartographyNodeSchema
from cartography.models.core.relationships import CartographyRelProperties
from cartography.models.core.relationships import CartographyRelSchema
from cartography.models.core.relationships import LinkDirection
from cartography.models.core.relationships import make_source_node_matcher
from cartography.models.core.relationships import make_target_node_matcher
from cartography.models.core.relationships import OtherRelationships
from cartography.models.core.relationships import SourceNodeMatcher
from cartography.models.core.relationships import TargetNodeMatcher

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AzureRouteTableProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id", description="Full Azure resource ID of the route table."
    )
    name: PropertyRef = PropertyRef("name", description="Name of the route table.")
    location: PropertyRef = PropertyRef(
        "location", description="Azure region where the route table is deployed."
    )
    provisioning_state: PropertyRef = PropertyRef(
        "provisioning_state",
        description="Current provisioning state of the route table.",
    )
    disable_bgp_route_propagation: PropertyRef = PropertyRef(
        "disable_bgp_route_propagation",
        description="Whether routes learned by BGP on this table are disabled.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class AzureRouteTableToSubscriptionRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class AzureRouteTableToSubscriptionRel(CartographyRelSchema):
    """An Azure subscription contains the route table as a resource."""

    target_node_label: str = "AzureSubscription"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("AZURE_SUBSCRIPTION_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: AzureRouteTableToSubscriptionRelProperties = (
        AzureRouteTableToSubscriptionRelProperties()
    )


@dataclass(frozen=True)
class AzureRouteTableSchema(CartographyNodeSchema):
    """A route table that Azure subnets can be associated with."""

    label: str = "AzureRouteTable"
    properties: AzureRouteTableProperties = AzureRouteTableProperties()
    sub_resource_relationship: AzureRouteTableToSubscriptionRel = (
        AzureRouteTableToSubscriptionRel()
    )


@dataclass(frozen=True)
class AzureRouteProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id", description="Full Azure resource ID of the route."
    )
    name: PropertyRef = PropertyRef("name", description="Name of the route.")
    address_prefix: PropertyRef = PropertyRef(
        "address_prefix", description="Destination CIDR this route applies to."
    )
    next_hop_type: PropertyRef = PropertyRef(
        "next_hop_type",
        description="Azure next hop type: VirtualAppliance, VnetLocal, Internet, "
        "VirtualNetworkGateway or None.",
    )
    next_hop_ip_address: PropertyRef = PropertyRef(
        "next_hop_ip_address",
        description="Next hop IP address. Azure sets this only when next_hop_type is "
        "VirtualAppliance; the other types name a destination without an address.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class AzureRouteToSubscriptionRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class AzureRouteToSubscriptionRel(CartographyRelSchema):
    """An Azure subscription contains the route as a resource."""

    target_node_label: str = "AzureSubscription"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("AZURE_SUBSCRIPTION_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: AzureRouteToSubscriptionRelProperties = (
        AzureRouteToSubscriptionRelProperties()
    )


@dataclass(frozen=True)
class AzureRouteToRouteTableRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class AzureRouteToRouteTableRel(CartographyRelSchema):
    """An Azure route table contains the route."""

    target_node_label: str = "AzureRouteTable"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("ROUTE_TABLE_ID")},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "CONTAINS"
    properties: AzureRouteToRouteTableRelProperties = (
        AzureRouteToRouteTableRelProperties()
    )


@dataclass(frozen=True)
class AzureRouteSchema(CartographyNodeSchema):
    """A single route within an Azure route table."""

    label: str = "AzureRoute"
    properties: AzureRouteProperties = AzureRouteProperties()
    sub_resource_relationship: AzureRouteToSubscriptionRel = (
        AzureRouteToSubscriptionRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [
            AzureRouteToRouteTableRel(),
        ],
    )


@dataclass(frozen=True)
class AzureSubnetToRouteTableRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    _sub_resource_id: PropertyRef = PropertyRef("_sub_resource_id", set_in_kwargs=True)
    _sub_resource_label: PropertyRef = PropertyRef(
        "_sub_resource_label", set_in_kwargs=True
    )


@dataclass(frozen=True)
class AzureSubnetToRouteTableRel(CartographyRelSchema):
    """An Azure subnet sends traffic according to the route table bound to it."""

    source_node_label: str = "AzureSubnet"
    source_node_matcher: SourceNodeMatcher = make_source_node_matcher(
        {"id": PropertyRef("NODE_ID")},
    )
    target_node_label: str = "AzureRouteTable"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("ROUTE_TABLE_ID")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "ROUTED_BY"
    properties: AzureSubnetToRouteTableRelProperties = (
        AzureSubnetToRouteTableRelProperties()
    )
