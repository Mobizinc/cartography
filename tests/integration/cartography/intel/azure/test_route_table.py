from unittest.mock import MagicMock
from unittest.mock import patch

import cartography.intel.azure.network as network
import cartography.intel.azure.route_table as route_table
from tests.data.azure.route_table import APPLIANCE_ROUTE_ID
from tests.data.azure.route_table import EMPTY_ROUTE_TABLE_ID
from tests.data.azure.route_table import INTERNET_ROUTE_ID
from tests.data.azure.route_table import MOCK_ROUTE_TABLES
from tests.data.azure.route_table import MOCK_TRANSFORMED_SUBNETS
from tests.data.azure.route_table import ROUTE_TABLE_ID
from tests.integration.util import check_nodes
from tests.integration.util import check_rels

TEST_SUBSCRIPTION_ID = "00-00-00-00"
TEST_UPDATE_TAG = 123456789


def _common_job_parameters(update_tag=TEST_UPDATE_TAG):
    return {
        "UPDATE_TAG": update_tag,
        "AZURE_SUBSCRIPTION_ID": TEST_SUBSCRIPTION_ID,
    }


EXPECTED_TABLES = {(ROUTE_TABLE_ID,), (EMPTY_ROUTE_TABLE_ID,)}
EXPECTED_ROUTES = {(APPLIANCE_ROUTE_ID,), (INTERNET_ROUTE_ID,)}
EXPECTED_CONTAINS = {
    (ROUTE_TABLE_ID, APPLIANCE_ROUTE_ID),
    (ROUTE_TABLE_ID, INTERNET_ROUTE_ID),
}


def _estate(neo4j_session) -> tuple:
    """Route tables, routes, and the CONTAINS edges between them."""
    return (
        check_nodes(neo4j_session, "AzureRouteTable", ["id"]),
        check_nodes(neo4j_session, "AzureRoute", ["id"]),
        check_rels(
            neo4j_session, "AzureRouteTable", "id", "AzureRoute", "id", "CONTAINS"
        ),
    )


def _seed_subscription(neo4j_session, update_tag=TEST_UPDATE_TAG):
    neo4j_session.run(
        "MERGE (s:AzureSubscription{id: $sub_id}) SET s.lastupdated = $tag",
        sub_id=TEST_SUBSCRIPTION_ID,
        tag=update_tag,
    )


@patch("cartography.intel.azure.route_table.get_route_tables")
def test_sync_route_tables(mock_get_route_tables, neo4j_session):
    # Arrange
    mock_get_route_tables.return_value = MOCK_ROUTE_TABLES
    _seed_subscription(neo4j_session)

    # Act
    route_table.sync(
        neo4j_session,
        MagicMock(),
        TEST_SUBSCRIPTION_ID,
        TEST_UPDATE_TAG,
        _common_job_parameters(),
    )

    # Assert
    assert check_nodes(neo4j_session, "AzureRouteTable", ["id"]) == {
        (ROUTE_TABLE_ID,),
        (EMPTY_ROUTE_TABLE_ID,),
    }
    assert check_nodes(
        neo4j_session, "AzureRoute", ["id", "address_prefix", "next_hop_ip_address"]
    ) == {
        (APPLIANCE_ROUTE_ID, "0.0.0.0/0", "10.52.0.20"),
        (INTERNET_ROUTE_ID, "20.0.0.0/8", None),
    }
    assert check_rels(
        neo4j_session, "AzureRouteTable", "id", "AzureRoute", "id", "CONTAINS"
    ) == {
        (ROUTE_TABLE_ID, APPLIANCE_ROUTE_ID),
        (ROUTE_TABLE_ID, INTERNET_ROUTE_ID),
    }
    assert check_rels(
        neo4j_session, "AzureSubscription", "id", "AzureRouteTable", "id", "RESOURCE"
    ) == {
        (TEST_SUBSCRIPTION_ID, ROUTE_TABLE_ID),
        (TEST_SUBSCRIPTION_ID, EMPTY_ROUTE_TABLE_ID),
    }


@patch("cartography.intel.azure.route_table.get_route_tables")
def test_subnet_routed_by_route_table(mock_get_route_tables, neo4j_session):
    # Arrange
    mock_get_route_tables.return_value = MOCK_ROUTE_TABLES
    _seed_subscription(neo4j_session)
    for subnet in MOCK_TRANSFORMED_SUBNETS:
        neo4j_session.run(
            "MERGE (s:AzureSubnet{id: $id}) SET s.lastupdated = $tag",
            id=subnet["id"],
            tag=TEST_UPDATE_TAG,
        )

    # Act
    route_table.sync(
        neo4j_session,
        MagicMock(),
        TEST_SUBSCRIPTION_ID,
        TEST_UPDATE_TAG,
        _common_job_parameters(),
    )

    # Act
    route_table.load_subnet_route_table_relationships(
        neo4j_session,
        route_table.transform_subnet_route_table_links(MOCK_TRANSFORMED_SUBNETS),
        TEST_SUBSCRIPTION_ID,
        TEST_UPDATE_TAG,
    )

    # Only the routed subnet gets an edge; the unrouted one states no association.

    # Assert
    assert check_rels(
        neo4j_session, "AzureSubnet", "id", "AzureRouteTable", "id", "ROUTED_BY"
    ) == {(MOCK_TRANSFORMED_SUBNETS[0]["id"], ROUTE_TABLE_ID)}


@patch("cartography.intel.azure.route_table.get_route_tables")
def test_cleanup_removes_route_table_deleted_from_azure(
    mock_get_route_tables, neo4j_session
):
    # Arrange
    mock_get_route_tables.return_value = MOCK_ROUTE_TABLES
    _seed_subscription(neo4j_session)

    # Act
    route_table.sync(
        neo4j_session,
        MagicMock(),
        TEST_SUBSCRIPTION_ID,
        TEST_UPDATE_TAG,
        _common_job_parameters(),
    )

    # Arrange - Azure no longer returns the empty table; the routed one is unchanged.
    next_tag = TEST_UPDATE_TAG + 1
    mock_get_route_tables.return_value = MOCK_ROUTE_TABLES[:1]
    _seed_subscription(neo4j_session, next_tag)

    # Act
    route_table.sync(
        neo4j_session,
        MagicMock(),
        TEST_SUBSCRIPTION_ID,
        next_tag,
        _common_job_parameters(next_tag),
    )

    # Assert
    assert check_nodes(neo4j_session, "AzureRouteTable", ["id"]) == {(ROUTE_TABLE_ID,)}
    assert check_nodes(neo4j_session, "AzureRoute", ["id"]) == {
        (APPLIANCE_ROUTE_ID,),
        (INTERNET_ROUTE_ID,),
    }


@patch("cartography.intel.azure.route_table.get_route_tables")
def test_repeat_sync_is_idempotent(mock_get_route_tables, neo4j_session):
    # Arrange
    mock_get_route_tables.return_value = MOCK_ROUTE_TABLES
    _seed_subscription(neo4j_session)

    # Act
    route_table.sync(
        neo4j_session,
        MagicMock(),
        TEST_SUBSCRIPTION_ID,
        TEST_UPDATE_TAG,
        _common_job_parameters(),
    )

    # Assert
    assert _estate(neo4j_session) == (
        EXPECTED_TABLES,
        EXPECTED_ROUTES,
        EXPECTED_CONTAINS,
    )

    # Arrange - Azure returns the same estate under a new update tag.
    next_tag = TEST_UPDATE_TAG + 1
    _seed_subscription(neo4j_session, next_tag)

    # Act
    route_table.sync(
        neo4j_session,
        MagicMock(),
        TEST_SUBSCRIPTION_ID,
        next_tag,
        _common_job_parameters(next_tag),
    )

    # Assert - a repeat sync neither duplicates nor removes.
    assert _estate(neo4j_session) == (
        EXPECTED_TABLES,
        EXPECTED_ROUTES,
        EXPECTED_CONTAINS,
    )


@patch("cartography.intel.azure.network.get_network_interfaces")
@patch("cartography.intel.azure.network.get_public_ip_addresses")
@patch("cartography.intel.azure.network.get_network_security_groups")
@patch("cartography.intel.azure.network.get_subnets")
@patch("cartography.intel.azure.network.get_virtual_networks")
@patch("cartography.intel.azure.route_table.get_route_tables")
def test_empty_vnet_result_still_cleans_stale_subnet_route_links(
    mock_get_route_tables,
    mock_get_vnets,
    mock_get_subnets,
    mock_get_nsgs,
    mock_get_public_ips,
    mock_get_nics,
    neo4j_session,
):
    """Subnet cleanup is scoped per VNet, so an authoritative empty VNet list cleans no
    subnets. The route-link cleanup must still run or the links are stranded forever."""

    # Arrange
    mock_get_route_tables.return_value = MOCK_ROUTE_TABLES
    mock_get_subnets.return_value = []
    mock_get_nsgs.return_value = []
    mock_get_public_ips.return_value = []
    mock_get_nics.return_value = []
    _seed_subscription(neo4j_session)
    # Both endpoints must exist before load_matchlinks can join them.

    # Act
    route_table.sync(
        neo4j_session,
        MagicMock(),
        TEST_SUBSCRIPTION_ID,
        TEST_UPDATE_TAG,
        _common_job_parameters(),
    )
    neo4j_session.run(
        "MERGE (s:AzureSubnet{id: $id}) SET s.lastupdated = $tag",
        id=MOCK_TRANSFORMED_SUBNETS[0]["id"],
        tag=TEST_UPDATE_TAG,
    )

    # Act
    route_table.load_subnet_route_table_relationships(
        neo4j_session,
        route_table.transform_subnet_route_table_links(MOCK_TRANSFORMED_SUBNETS),
        TEST_SUBSCRIPTION_ID,
        TEST_UPDATE_TAG,
    )

    # Assert
    assert check_rels(
        neo4j_session,
        "AzureSubnet",
        "id",
        "AzureRouteTable",
        "id",
        "ROUTED_BY",
        # Arrange
    ) == {(MOCK_TRANSFORMED_SUBNETS[0]["id"], ROUTE_TABLE_ID)}

    # Arrange - Azure now authoritatively reports no VNets at all.
    next_tag = TEST_UPDATE_TAG + 1
    mock_get_vnets.return_value = []
    _seed_subscription(neo4j_session, next_tag)

    # Act
    network.sync(
        neo4j_session,
        MagicMock(),
        TEST_SUBSCRIPTION_ID,
        next_tag,
        _common_job_parameters(next_tag),
    )

    # Assert
    assert (
        check_rels(
            neo4j_session, "AzureSubnet", "id", "AzureRouteTable", "id", "ROUTED_BY"
        )
        == set()
    )


@patch("cartography.intel.azure.route_table.get_route_tables")
def test_subnet_route_table_reference_resolves_when_casing_differs(
    mock_get_route_tables, neo4j_session
):
    """subnets.list() and route_tables.list_all() can spell the same id differently.
    load_matchlinks compares exactly, so without resolution the edge is never created.
    """

    # Arrange
    mock_get_route_tables.return_value = MOCK_ROUTE_TABLES
    _seed_subscription(neo4j_session)

    # Act
    route_table.sync(
        neo4j_session,
        MagicMock(),
        TEST_SUBSCRIPTION_ID,
        TEST_UPDATE_TAG,
        _common_job_parameters(),
    )
    subnet_id = MOCK_TRANSFORMED_SUBNETS[0]["id"]
    neo4j_session.run(
        "MERGE (s:AzureSubnet{id: $id}) SET s.lastupdated = $tag",
        id=subnet_id,
        tag=TEST_UPDATE_TAG,
    )

    miscased = [
        {
            "id": subnet_id,
            "route_table_id": ROUTE_TABLE_ID.replace(
                "resourceGroups", "RESOURCEGROUPS"
            ),
        }
    ]

    # Act
    route_table.load_subnet_route_table_relationships(
        neo4j_session,
        route_table.transform_subnet_route_table_links(miscased),
        TEST_SUBSCRIPTION_ID,
        TEST_UPDATE_TAG,
    )

    # Assert
    assert check_rels(
        neo4j_session, "AzureSubnet", "id", "AzureRouteTable", "id", "ROUTED_BY"
    ) == {(subnet_id, ROUTE_TABLE_ID)}
