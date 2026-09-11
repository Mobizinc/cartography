from cartography.intel.azure.util import arm_id

RG = "/subscriptions/00-00-00-00/resourceGroups/test-rg"
VNET = f"{RG}/providers/Microsoft.Network/virtualNetworks/vnet-remote"
TABLE = f"{RG}/providers/Microsoft.Network/routeTables/rt-with-routes"


def test_resolve_rewrites_a_reference_that_differs_only_in_case():
    """load_matchlinks compares with exact equality, so a reference whose casing differs
    from the stored node id would silently never produce an edge."""
    # Arrange
    rows = [{"NODE_ID": VNET.replace("resourceGroups", "RESOURCEGROUPS")}]

    # Act
    resolved = arm_id.resolve(rows, ("NODE_ID",), {VNET.lower(): VNET})

    # Assert
    assert resolved[0]["NODE_ID"] == VNET


def test_resolve_rewrites_every_named_key():
    # Arrange
    rows = [{"NODE_ID": VNET.upper(), "ROUTE_TABLE_ID": TABLE.upper()}]

    # Act
    resolved = arm_id.resolve(
        rows,
        ("NODE_ID", "ROUTE_TABLE_ID"),
        {VNET.lower(): VNET, TABLE.lower(): TABLE},
    )

    # Assert
    assert resolved[0] == {"NODE_ID": VNET, "ROUTE_TABLE_ID": TABLE}


def test_resolve_leaves_an_unknown_reference_alone():
    """A resource outside this ingestion has no stored id to match; recasing it would not
    make it resolve."""
    # Arrange
    outside = "/subscriptions/other/resourceGroups/rg/providers/Microsoft.Network/virtualNetworks/Elsewhere"
    rows = [{"NODE_ID": outside}]

    # Act
    resolved = arm_id.resolve(rows, ("NODE_ID",), {VNET.lower(): VNET})

    # Assert
    assert resolved[0]["NODE_ID"] == outside


def test_resolve_tolerates_a_missing_key():
    # Arrange
    rows = [{"NODE_ID": VNET}]

    # Act
    resolved = arm_id.resolve(rows, ("NODE_ID", "ROUTE_TABLE_ID"), {VNET.lower(): VNET})

    # Assert
    assert resolved[0] == {"NODE_ID": VNET}
