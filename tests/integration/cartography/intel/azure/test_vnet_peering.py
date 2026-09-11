from unittest.mock import MagicMock
from unittest.mock import patch

import cartography.intel.azure.vnet_peering as vnet_peering
from tests.data.azure.vnet_peering import LOCAL_VNET_ID
from tests.data.azure.vnet_peering import MOCK_PEERINGS
from tests.data.azure.vnet_peering import REMOTE_VNET_ID
from tests.integration.util import check_rels

TEST_SUBSCRIPTION_ID = "00-00-00-00"
TEST_UPDATE_TAG = 123456789

MOCK_VNETS = [
    {"id": LOCAL_VNET_ID, "name": "vnet-local"},
    {"id": REMOTE_VNET_ID, "name": "vnet-remote"},
]


def _common_job_parameters(update_tag=TEST_UPDATE_TAG):
    return {"UPDATE_TAG": update_tag, "AZURE_SUBSCRIPTION_ID": TEST_SUBSCRIPTION_ID}


def _seed(neo4j_session, update_tag=TEST_UPDATE_TAG):
    neo4j_session.run(
        "MERGE (s:AzureSubscription{id: $sub_id}) SET s.lastupdated = $tag",
        sub_id=TEST_SUBSCRIPTION_ID,
        tag=update_tag,
    )
    for vnet in MOCK_VNETS:
        neo4j_session.run(
            "MERGE (v:AzureVirtualNetwork{id: $id}) SET v.lastupdated = $tag",
            id=vnet["id"],
            tag=update_tag,
        )


@patch("cartography.intel.azure.vnet_peering.get_vnet_peerings")
def test_peering_is_written_only_in_the_declared_direction(
    mock_get_peerings, neo4j_session
):
    """Azure configures a peering per direction. Only the local VNet declares this one,
    so the reverse edge must not exist."""

    # Arrange
    mock_get_peerings.side_effect = lambda client, rg, name: (
        MOCK_PEERINGS if name == "vnet-local" else []
    )
    _seed(neo4j_session)

    # Act
    vnet_peering.sync(
        neo4j_session,
        {TEST_SUBSCRIPTION_ID: vnet_peering.collect(MagicMock(), MOCK_VNETS)},
        TEST_UPDATE_TAG,
        _common_job_parameters(),
    )

    # Assert
    assert check_rels(
        neo4j_session,
        "AzureVirtualNetwork",
        "id",
        "AzureVirtualNetwork",
        "id",
        "PEERED_WITH",
    ) == {(LOCAL_VNET_ID, REMOTE_VNET_ID)}


@patch("cartography.intel.azure.vnet_peering.get_vnet_peerings")
def test_peering_state_is_carried_on_the_edge(mock_get_peerings, neo4j_session):
    # Arrange
    mock_get_peerings.side_effect = lambda client, rg, name: (
        MOCK_PEERINGS if name == "vnet-local" else []
    )
    _seed(neo4j_session)

    # Act
    vnet_peering.sync(
        neo4j_session,
        {TEST_SUBSCRIPTION_ID: vnet_peering.collect(MagicMock(), MOCK_VNETS)},
        TEST_UPDATE_TAG,
        _common_job_parameters(),
    )

    result = neo4j_session.run(
        "MATCH (:AzureVirtualNetwork)-[r:PEERED_WITH]->(:AzureVirtualNetwork) "
        "RETURN r.peering_state AS state, r.peering_name AS name, "
        "r.allow_forwarded_traffic AS forwarded"
    ).single()

    # Assert
    assert result["state"] == "Connected"
    assert result["name"] == "local-to-remote"
    assert result["forwarded"] is True


@patch("cartography.intel.azure.vnet_peering.get_vnet_peerings")
def test_cleanup_removes_peering_torn_down_in_azure(mock_get_peerings, neo4j_session):
    # Arrange
    mock_get_peerings.side_effect = lambda client, rg, name: (
        MOCK_PEERINGS if name == "vnet-local" else []
    )
    _seed(neo4j_session)

    # Act
    vnet_peering.sync(
        neo4j_session,
        {TEST_SUBSCRIPTION_ID: vnet_peering.collect(MagicMock(), MOCK_VNETS)},
        TEST_UPDATE_TAG,
        _common_job_parameters(),
    )

    # Arrange - the peering has been torn down in Azure.
    next_tag = TEST_UPDATE_TAG + 1
    mock_get_peerings.side_effect = lambda client, rg, name: []
    _seed(neo4j_session, next_tag)

    # Act
    vnet_peering.sync(
        neo4j_session,
        {TEST_SUBSCRIPTION_ID: vnet_peering.collect(MagicMock(), MOCK_VNETS)},
        next_tag,
        _common_job_parameters(next_tag),
    )

    # Assert
    assert (
        check_rels(
            neo4j_session,
            "AzureVirtualNetwork",
            "id",
            "AzureVirtualNetwork",
            "id",
            "PEERED_WITH",
        )
        == set()
    )


@patch("cartography.intel.azure.vnet_peering.get_vnet_peerings")
def test_peering_resolves_a_remote_id_whose_casing_differs(
    mock_get_peerings, neo4j_session
):
    """Azure returns resource ids with inconsistent casing. load_matchlinks compares with
    exact equality, so without resolution this edge is silently never created."""

    # Arrange
    miscased = [
        {
            **MOCK_PEERINGS[0],
            "remote_virtual_network": {
                "id": REMOTE_VNET_ID.replace("resourceGroups", "RESOURCEGROUPS")
            },
        }
    ]
    mock_get_peerings.side_effect = lambda client, rg, name: (
        miscased if name == "vnet-local" else []
    )
    _seed(neo4j_session)

    # Act
    vnet_peering.sync(
        neo4j_session,
        {TEST_SUBSCRIPTION_ID: vnet_peering.collect(MagicMock(), MOCK_VNETS)},
        TEST_UPDATE_TAG,
        _common_job_parameters(),
    )

    # Assert
    assert check_rels(
        neo4j_session,
        "AzureVirtualNetwork",
        "id",
        "AzureVirtualNetwork",
        "id",
        "PEERED_WITH",
    ) == {(LOCAL_VNET_ID, REMOTE_VNET_ID)}
