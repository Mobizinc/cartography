"""Route table payloads in the shape `RouteTable.as_dict()` returns.

Shapes exercised: a table whose routes use an appliance next hop (address present) and
one whose route names a next hop type only (no address), plus a table with no routes.
"""

SUBSCRIPTION_ID = "00-00-00-00"
RG = f"/subscriptions/{SUBSCRIPTION_ID}/resourceGroups/test-rg"

ROUTE_TABLE_ID = f"{RG}/providers/Microsoft.Network/routeTables/rt-with-routes"
EMPTY_ROUTE_TABLE_ID = f"{RG}/providers/Microsoft.Network/routeTables/rt-no-routes"

APPLIANCE_ROUTE_ID = f"{ROUTE_TABLE_ID}/routes/default-to-nva"
INTERNET_ROUTE_ID = f"{ROUTE_TABLE_ID}/routes/to-internet"

MOCK_ROUTE_TABLES = [
    {
        "id": ROUTE_TABLE_ID,
        "name": "rt-with-routes",
        "location": "eastus",
        "provisioning_state": "Succeeded",
        "disable_bgp_route_propagation": True,
        "routes": [
            {
                "id": APPLIANCE_ROUTE_ID,
                "name": "default-to-nva",
                "address_prefix": "0.0.0.0/0",
                "next_hop_type": "VirtualAppliance",
                "next_hop_ip_address": "10.52.0.20",
            },
            {
                "id": INTERNET_ROUTE_ID,
                "name": "to-internet",
                "address_prefix": "20.0.0.0/8",
                "next_hop_type": "Internet",
            },
        ],
    },
    {
        "id": EMPTY_ROUTE_TABLE_ID,
        "name": "rt-no-routes",
        "location": "eastus",
        "provisioning_state": "Succeeded",
        "disable_bgp_route_propagation": False,
        "routes": [],
    },
]

#: The camelCase nesting the SDK returns when it does not flatten `properties`.
MOCK_ROUTE_TABLES_NESTED = [
    {
        "id": ROUTE_TABLE_ID,
        "name": "rt-with-routes",
        "location": "eastus",
        "properties": {
            "provisioningState": "Succeeded",
            "disableBgpRoutePropagation": True,
            "routes": [
                {
                    "id": APPLIANCE_ROUTE_ID,
                    "name": "default-to-nva",
                    "properties": {
                        "addressPrefix": "0.0.0.0/0",
                        "nextHopType": "VirtualAppliance",
                        "nextHopIpAddress": "10.52.0.20",
                    },
                },
            ],
        },
    },
]

#: Transformed subnets as `network.transform_subnets` emits them.
MOCK_TRANSFORMED_SUBNETS = [
    {
        "id": f"{RG}/providers/Microsoft.Network/virtualNetworks/vnet/subnets/routed",
        "route_table_id": ROUTE_TABLE_ID,
    },
    {
        "id": f"{RG}/providers/Microsoft.Network/virtualNetworks/vnet/subnets/unrouted",
        "route_table_id": None,
    },
]
