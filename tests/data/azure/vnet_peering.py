"""VNet peering payloads in the shape `VirtualNetworkPeering.as_dict()` returns."""

SUBSCRIPTION_ID = "00-00-00-00"
RG = f"/subscriptions/{SUBSCRIPTION_ID}/resourceGroups/test-rg"

LOCAL_VNET_ID = f"{RG}/providers/Microsoft.Network/virtualNetworks/vnet-local"
REMOTE_VNET_ID = f"{RG}/providers/Microsoft.Network/virtualNetworks/vnet-remote"

MOCK_PEERINGS = [
    {
        "id": f"{LOCAL_VNET_ID}/virtualNetworkPeerings/local-to-remote",
        "name": "local-to-remote",
        "peering_state": "Connected",
        "allow_forwarded_traffic": True,
        "allow_gateway_transit": False,
        "remote_virtual_network": {"id": REMOTE_VNET_ID},
    },
    # Dropped on purpose: a peering that names no remote id is not an identity.
    {
        "id": f"{LOCAL_VNET_ID}/virtualNetworkPeerings/orphan",
        "name": "orphan",
        "peering_state": "Initiated",
        "remote_virtual_network": {},
    },
]

MOCK_PEERINGS_NESTED = [
    {
        "id": f"{LOCAL_VNET_ID}/virtualNetworkPeerings/local-to-remote",
        "name": "local-to-remote",
        "properties": {
            "peeringState": "Connected",
            "allowForwardedTraffic": True,
            "allowGatewayTransit": False,
            "remoteVirtualNetwork": {"id": REMOTE_VNET_ID},
        },
    },
]
