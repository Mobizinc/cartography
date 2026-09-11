import logging
from dataclasses import dataclass

from cartography.models.core.common import PropertyRef
from cartography.models.core.relationships import CartographyRelProperties
from cartography.models.core.relationships import CartographyRelSchema
from cartography.models.core.relationships import LinkDirection
from cartography.models.core.relationships import make_source_node_matcher
from cartography.models.core.relationships import make_target_node_matcher
from cartography.models.core.relationships import SourceNodeMatcher
from cartography.models.core.relationships import TargetNodeMatcher

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AzureVirtualNetworkPeeringRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    _sub_resource_id: PropertyRef = PropertyRef("_sub_resource_id", set_in_kwargs=True)
    _sub_resource_label: PropertyRef = PropertyRef(
        "_sub_resource_label", set_in_kwargs=True
    )
    peering_name: PropertyRef = PropertyRef(
        "peering_name", description="Name of the peering resource on the local VNet."
    )
    peering_state: PropertyRef = PropertyRef(
        "peering_state",
        description="Peering state ARM reports for this direction: Initiated, "
        "Connected or Disconnected.",
    )
    allow_forwarded_traffic: PropertyRef = PropertyRef(
        "allow_forwarded_traffic",
        description="Whether traffic forwarded from the remote VNet is permitted.",
    )
    allow_gateway_transit: PropertyRef = PropertyRef(
        "allow_gateway_transit",
        description="Whether the remote VNet may use this VNet's gateway.",
    )


@dataclass(frozen=True)
class AzureVirtualNetworkPeeringRel(CartographyRelSchema):
    """One direction of an Azure VNet peering, as the local VNet declares it.

    Directional, not symmetric: Azure configures a peering per direction and reports each
    side's state separately, so the reverse edge is written only when the remote VNet is
    itself read and declares it. Entailing the reverse would assert a declaration that may
    not exist.
    """

    source_node_label: str = "AzureVirtualNetwork"
    source_node_matcher: SourceNodeMatcher = make_source_node_matcher(
        {"id": PropertyRef("NODE_ID")},
    )
    target_node_label: str = "AzureVirtualNetwork"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("REMOTE_VNET_ID")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "PEERED_WITH"
    properties: AzureVirtualNetworkPeeringRelProperties = (
        AzureVirtualNetworkPeeringRelProperties()
    )
