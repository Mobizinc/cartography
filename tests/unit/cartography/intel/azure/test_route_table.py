from unittest.mock import MagicMock
from unittest.mock import patch

import cartography.intel.azure.route_table as route_table
from tests.data.azure.route_table import APPLIANCE_ROUTE_ID
from tests.data.azure.route_table import EMPTY_ROUTE_TABLE_ID
from tests.data.azure.route_table import INTERNET_ROUTE_ID
from tests.data.azure.route_table import MOCK_ROUTE_TABLES
from tests.data.azure.route_table import MOCK_ROUTE_TABLES_NESTED
from tests.data.azure.route_table import MOCK_TRANSFORMED_SUBNETS
from tests.data.azure.route_table import ROUTE_TABLE_ID


def test_transform_route_tables_flattens_properties():
    # Act
    result = route_table.transform_route_tables(MOCK_ROUTE_TABLES)

    # Assert
    assert [table["id"] for table in result] == [ROUTE_TABLE_ID, EMPTY_ROUTE_TABLE_ID]
    assert result[0]["provisioning_state"] == "Succeeded"
    assert result[0]["disable_bgp_route_propagation"] is True
    assert result[1]["disable_bgp_route_propagation"] is False


def test_transform_route_tables_reads_nested_camel_case():
    # Act
    result = route_table.transform_route_tables(MOCK_ROUTE_TABLES_NESTED)

    # Assert
    assert result[0]["provisioning_state"] == "Succeeded"
    assert result[0]["disable_bgp_route_propagation"] is True


def test_transform_routes_tags_each_route_with_its_table():
    # Act
    result = route_table.transform_routes(MOCK_ROUTE_TABLES)

    # Assert
    assert {route["id"] for route in result} == {
        APPLIANCE_ROUTE_ID,
        INTERNET_ROUTE_ID,
    }
    assert all(route["ROUTE_TABLE_ID"] == ROUTE_TABLE_ID for route in result)


def test_transform_routes_keeps_next_hop_type_when_there_is_no_address():
    # Act
    by_id = {r["id"]: r for r in route_table.transform_routes(MOCK_ROUTE_TABLES)}

    # Assert
    appliance = by_id[APPLIANCE_ROUTE_ID]
    assert appliance["next_hop_type"] == "VirtualAppliance"
    assert appliance["next_hop_ip_address"] == "10.52.0.20"

    # Internet, VnetLocal and gateway hops name a destination without an address.
    internet = by_id[INTERNET_ROUTE_ID]
    assert internet["next_hop_type"] == "Internet"
    assert internet["next_hop_ip_address"] is None


def test_transform_routes_reads_nested_camel_case():
    # Act
    result = route_table.transform_routes(MOCK_ROUTE_TABLES_NESTED)

    # Assert
    assert result[0]["address_prefix"] == "0.0.0.0/0"
    assert result[0]["next_hop_ip_address"] == "10.52.0.20"


def test_transform_subnet_route_table_links_skips_unrouted_subnets():
    # Act
    result = route_table.transform_subnet_route_table_links(MOCK_TRANSFORMED_SUBNETS)

    # Assert
    assert result == [
        {"NODE_ID": MOCK_TRANSFORMED_SUBNETS[0]["id"], "ROUTE_TABLE_ID": ROUTE_TABLE_ID}
    ]


def test_load_subnet_route_table_relationships_uses_the_supplied_id_map():
    """The id map is fetched once per subscription and passed in. Rebuilding it here
    would scan every stored route table once per VNet in the subscription."""
    # Arrange
    session = MagicMock()
    rows = [{"NODE_ID": "subnet", "ROUTE_TABLE_ID": ROUTE_TABLE_ID.upper()}]

    # Act
    with patch.object(route_table.arm_id, "stored_ids") as mock_stored_ids:
        with patch.object(route_table, "load_matchlinks") as mock_load:
            route_table.load_subnet_route_table_relationships(
                session, rows, "sub", 1, {ROUTE_TABLE_ID.lower(): ROUTE_TABLE_ID}
            )

    # Assert
    mock_stored_ids.assert_not_called()
    assert mock_load.call_args[0][2][0]["ROUTE_TABLE_ID"] == ROUTE_TABLE_ID
