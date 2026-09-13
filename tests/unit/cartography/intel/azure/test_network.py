from cartography.intel.azure.network import transform_network_interfaces
from cartography.intel.azure.network import transform_network_security_rules
from cartography.intel.azure.network import transform_public_ip_addresses
from cartography.intel.azure.network import transform_subnets
from cartography.intel.azure.network import transform_virtual_networks


def test_transform_public_ip_addresses_handles_flattened_fields():
    data = transform_public_ip_addresses(
        [
            {
                "id": "public-ip-1",
                "name": "my-public-ip-1",
                "location": "eastus",
                "ip_address": "20.10.30.40",
                "public_ip_allocation_method": "Static",
            },
        ],
    )

    assert data == [
        {
            "id": "public-ip-1",
            "name": "my-public-ip-1",
            "location": "eastus",
            "ip_address": "20.10.30.40",
            "public_ip_allocation_method": "Static",
        },
    ]


def test_transform_public_ip_addresses_handles_nested_properties_fields():
    data = transform_public_ip_addresses(
        [
            {
                "id": "public-ip-1",
                "name": "my-public-ip-1",
                "location": "eastus",
                "properties": {
                    "ip_address": "20.10.30.40",
                    "public_ip_allocation_method": "Static",
                },
            },
        ],
    )

    assert data == [
        {
            "id": "public-ip-1",
            "name": "my-public-ip-1",
            "location": "eastus",
            "ip_address": "20.10.30.40",
            "public_ip_allocation_method": "Static",
        },
    ]


def test_transform_network_resources_handles_sdk_31_camel_properties():
    vnets = transform_virtual_networks(
        [
            {
                "id": "vnet-id",
                "name": "vnet",
                "location": "eastus",
                "properties": {"provisioningState": "Succeeded"},
            }
        ]
    )
    subnets = transform_subnets(
        [
            {
                "id": "subnet-id",
                "name": "subnet",
                "properties": {
                    "addressPrefix": "10.0.0.0/24",
                    "networkSecurityGroup": {"id": "nsg-id"},
                },
            }
        ]
    )
    public_ips = transform_public_ip_addresses(
        [
            {
                "id": "public-ip-1",
                "name": "my-public-ip-1",
                "location": "eastus",
                "properties": {
                    "ipAddress": "20.10.30.40",
                    "publicIPAllocationMethod": "Static",
                },
            },
        ],
    )

    assert vnets[0]["provisioning_state"] == "Succeeded"
    assert subnets[0]["address_prefix"] == "10.0.0.0/24"
    assert subnets[0]["nsg_id"] == "nsg-id"
    assert public_ips[0]["ip_address"] == "20.10.30.40"
    assert public_ips[0]["public_ip_allocation_method"] == "Static"


def test_transform_network_security_rules_handles_sdk_31_camel_properties():
    rules = transform_network_security_rules(
        [
            {
                "id": "nsg-id",
                "properties": {
                    "securityRules": [
                        {
                            "id": "rule-id",
                            "name": "allow-https",
                            "properties": {
                                "protocol": "Tcp",
                                "direction": "Inbound",
                                "access": "Allow",
                                "priority": 100,
                                "sourcePortRange": "*",
                                "destinationPortRange": "443",
                                "sourceAddressPrefix": "*",
                                "destinationAddressPrefix": "*",
                            },
                        }
                    ],
                    "defaultSecurityRules": [],
                },
            }
        ]
    )

    assert rules == [
        {
            "id": "rule-id",
            "name": "allow-https",
            "nsg_id": "nsg-id",
            "description": None,
            "protocol": "Tcp",
            "direction": "Inbound",
            "access": "Allow",
            "priority": 100,
            "source_port_range": "*",
            "source_port_ranges": None,
            "destination_port_range": "443",
            "destination_port_ranges": None,
            "source_address_prefix": "*",
            "source_address_prefixes": None,
            "destination_address_prefix": "*",
            "destination_address_prefixes": None,
            "is_default": False,
        }
    ]


def test_transform_network_interfaces_handles_sdk_31_camel_properties():
    interfaces = transform_network_interfaces(
        [
            {
                "id": "nic-id",
                "name": "nic",
                "location": "eastus",
                "properties": {
                    "ipConfigurations": [
                        {
                            "properties": {
                                "subnet": {"id": "subnet-id"},
                                "publicIPAddress": {"id": "public-ip-id"},
                                "privateIPAddress": "10.0.0.4",
                            },
                        }
                    ],
                    "networkSecurityGroup": {"id": "nsg-id"},
                    "virtualMachine": {"id": "VM-ID"},
                },
            }
        ]
    )

    assert interfaces[0]["SUBNET_IDS"] == ["subnet-id"]
    assert interfaces[0]["PUBLIC_IP_IDS"] == ["public-ip-id"]
    assert interfaces[0]["private_ip_addresses"] == ["10.0.0.4"]
    assert interfaces[0]["NSG_ID"] == "nsg-id"
    assert interfaces[0]["VIRTUAL_MACHINE_ID"] == "vm-id"


# The field set and nesting of `NetworkInterface.as_dict()` on azure-mgmt-network 31.0.1:
# two IP configurations, only the second of which has a public IP.
NIC_WITH_TWO_IP_CONFIGURATIONS = {
    "id": "/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.Network/networkInterfaces/nic-1",
    "name": "nic-1",
    "location": "eastus",
    "properties": {
        "macAddress": "00-0D-3A-1B-2C-3D",
        "ipConfigurations": [
            {
                "id": "/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.Network/networkInterfaces/nic-1/ipConfigurations/ipconfig1",
                "name": "ipconfig1",
                "properties": {
                    "primary": True,
                    "privateIPAddress": "10.0.0.4",
                    "privateIPAllocationMethod": "Dynamic",
                    "subnet": {
                        "id": "/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.Network/virtualNetworks/vnet-1/subnets/app",
                    },
                },
            },
            {
                "id": "/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.Network/networkInterfaces/nic-1/ipConfigurations/ipconfig2",
                "name": "ipconfig2",
                "properties": {
                    "primary": False,
                    "privateIPAddress": "10.0.1.5",
                    "privateIPAllocationMethod": "Static",
                    "subnet": {
                        "id": "/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.Network/virtualNetworks/vnet-1/subnets/edge",
                    },
                    "publicIPAddress": {
                        "id": "/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.Network/publicIPAddresses/pip-1",
                    },
                },
            },
        ],
    },
}

APP_SUBNET = "/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.Network/virtualNetworks/vnet-1/subnets/app"
EDGE_SUBNET = "/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.Network/virtualNetworks/vnet-1/subnets/edge"
PUBLIC_IP = "/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.Network/publicIPAddresses/pip-1"


def test_transform_network_interfaces_keeps_each_ip_configuration_together():
    """Which subnet a public IP is reachable on is a fact of the configuration that binds
    them. Three parallel lists cannot state it: the configuration without a public IP
    shortens one list, so the same index names a different configuration in each."""
    # Act
    interface = transform_network_interfaces([NIC_WITH_TWO_IP_CONFIGURATIONS])[0]

    # Assert
    assert interface["ip_configurations"] == [
        {
            "name": "ipconfig1",
            "private_ip_address": "10.0.0.4",
            "private_ip_allocation_method": "Dynamic",
            "primary": True,
            "subnet_id": APP_SUBNET,
            "public_ip_id": None,
        },
        {
            "name": "ipconfig2",
            "private_ip_address": "10.0.1.5",
            "private_ip_allocation_method": "Static",
            "primary": False,
            "subnet_id": EDGE_SUBNET,
            "public_ip_id": PUBLIC_IP,
        },
    ]


def test_transform_network_interfaces_derives_its_id_lists_from_the_configurations():
    """The relationship matchers read these three, so they carry what the configurations
    state, in order, and nothing else."""
    # Act
    interface = transform_network_interfaces([NIC_WITH_TWO_IP_CONFIGURATIONS])[0]

    # Assert
    assert interface["SUBNET_IDS"] == [APP_SUBNET, EDGE_SUBNET]
    assert interface["PUBLIC_IP_IDS"] == [PUBLIC_IP]
    assert interface["private_ip_addresses"] == ["10.0.0.4", "10.0.1.5"]


def test_transform_network_interfaces_names_a_shared_subnet_once():
    """Two configurations on one subnet are one attachment, not two."""
    # Arrange
    nic = {
        "properties": {
            "ipConfigurations": [
                {"name": "ipconfig1", "properties": {"subnet": {"id": APP_SUBNET}}},
                {"name": "ipconfig2", "properties": {"subnet": {"id": APP_SUBNET}}},
            ]
        }
    }

    # Act
    interface = transform_network_interfaces([nic])[0]

    # Assert
    assert [c["subnet_id"] for c in interface["ip_configurations"]] == [
        APP_SUBNET,
        APP_SUBNET,
    ]
    assert interface["SUBNET_IDS"] == [APP_SUBNET]


def test_transform_network_interfaces_reads_a_nested_mac_address():
    """`as_dict()` returns it as `properties.macAddress`, so a top-level-only read stored
    every NIC in the subscription with no MAC address at all."""
    # Act
    interface = transform_network_interfaces([NIC_WITH_TWO_IP_CONFIGURATIONS])[0]

    # Assert
    assert interface["mac_address"] == "00-0D-3A-1B-2C-3D"


def test_transform_network_interfaces_handles_a_nic_with_no_ip_configurations():
    # Act
    interface = transform_network_interfaces(
        [{"id": "nic-id", "name": "nic", "location": "eastus", "properties": {}}]
    )[0]

    # Assert
    assert interface["ip_configurations"] == []
    assert interface["SUBNET_IDS"] == []
    assert interface["PUBLIC_IP_IDS"] == []
    assert interface["private_ip_addresses"] == []
    assert interface["mac_address"] is None
    assert interface["VIRTUAL_MACHINE_ID"] is None
    assert interface["NSG_ID"] is None
