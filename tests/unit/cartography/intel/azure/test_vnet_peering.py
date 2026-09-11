from unittest.mock import MagicMock

import cartography.intel.azure.vnet_peering as vnet_peering
from tests.data.azure.vnet_peering import LOCAL_VNET_ID
from tests.data.azure.vnet_peering import MOCK_PEERING_ACCESS_DISABLED
from tests.data.azure.vnet_peering import MOCK_PEERINGS
from tests.data.azure.vnet_peering import MOCK_PEERINGS_NESTED
from tests.data.azure.vnet_peering import REMOTE_VNET_ID


def test_transform_vnet_peerings_carries_direction_and_state():
    # Act
    result = vnet_peering.transform_vnet_peerings(LOCAL_VNET_ID, MOCK_PEERINGS)

    # Assert
    assert len(result) == 1
    assert result[0]["NODE_ID"] == LOCAL_VNET_ID
    assert result[0]["REMOTE_VNET_ID"] == REMOTE_VNET_ID
    assert result[0]["peering_state"] == "Connected"
    assert result[0]["allow_forwarded_traffic"] is True
    assert result[0]["allow_gateway_transit"] is False


def test_transform_vnet_peerings_drops_peering_with_no_remote_id():
    """A peering naming no remote resource id must not become an edge: the embedded
    name is not an identity and matching on it would join unrelated networks."""
    # Act
    result = vnet_peering.transform_vnet_peerings(LOCAL_VNET_ID, MOCK_PEERINGS)

    # Assert
    assert "orphan" not in {row["peering_name"] for row in result}


def test_transform_vnet_peerings_reads_nested_camel_case():
    # Act
    result = vnet_peering.transform_vnet_peerings(LOCAL_VNET_ID, MOCK_PEERINGS_NESTED)

    # Assert
    assert result[0]["REMOTE_VNET_ID"] == REMOTE_VNET_ID
    assert result[0]["peering_state"] == "Connected"


def test_resource_group_parsed_case_insensitively():
    # Act
    lowered = LOCAL_VNET_ID.replace("resourceGroups", "resourcegroups")

    # Assert
    assert vnet_peering._get_resource_group_from_id(LOCAL_VNET_ID) == "test-rg"
    assert vnet_peering._get_resource_group_from_id(lowered) == "test-rg"


def test_collect_gathers_rows_without_loading_them():
    """Collection is separate from loading so a peering naming a VNet in another
    subscription is not dropped by load_matchlinks before that VNet exists."""
    # Arrange
    client = MagicMock()
    client.virtual_network_peerings.list.return_value = [
        MagicMock(as_dict=lambda p=p: p) for p in MOCK_PEERINGS
    ]

    # Act
    rows = vnet_peering.collect(client, [{"id": LOCAL_VNET_ID, "name": "vnet-local"}])

    # Assert
    assert [row["REMOTE_VNET_ID"] for row in rows] == [REMOTE_VNET_ID]


def test_transform_carries_the_connectivity_controls():
    """peering_state alone does not say whether traffic flows: ARM reports Connected
    while allow_virtual_network_access is false."""
    # Act
    result = vnet_peering.transform_vnet_peerings(
        LOCAL_VNET_ID, MOCK_PEERING_ACCESS_DISABLED
    )

    # Assert
    assert result[0]["peering_state"] == "Connected"
    assert result[0]["allow_virtual_network_access"] is False
    assert result[0]["use_remote_gateways"] is True


def test_transform_reads_the_connectivity_controls_from_nested_camel_case():
    # Act
    result = vnet_peering.transform_vnet_peerings(LOCAL_VNET_ID, MOCK_PEERINGS_NESTED)

    # Assert
    assert result[0]["allow_virtual_network_access"] is True
    assert result[0]["use_remote_gateways"] is False
