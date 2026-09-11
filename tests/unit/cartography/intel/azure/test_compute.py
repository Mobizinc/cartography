from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from azure.core.exceptions import HttpResponseError
from azure.core.exceptions import ServiceRequestTimeoutError

import cartography.intel.azure.compute as compute
from cartography.intel.azure.compute import transform_disk
from cartography.intel.azure.compute import transform_snapshot
from cartography.intel.azure.compute import transform_vm
from cartography.intel.azure.compute import transform_vm_list


def test_transform_vm_flattens_sdk_38_properties():
    vm = transform_vm(
        {
            "id": "vm-id",
            "properties": {
                "storageProfile": {
                    "dataDisks": [
                        {
                            "name": "data-disk",
                            "lun": 0,
                            "diskSizeGB": 128,
                        }
                    ]
                },
                "hardwareProfile": {"vmSize": "Standard_D2s_v3"},
                "osProfile": {"computerName": "vm"},
                "additionalCapabilities": {"ultraSSDEnabled": True},
                "licenseType": "Windows_Server",
                "evictionPolicy": "Deallocate",
            },
        }
    )

    assert vm["storage_profile"]["data_disks"][0]["disk_size_gb"] == 128
    assert vm["hardware_profile"]["vm_size"] == "Standard_D2s_v3"
    assert vm["os_profile"]["computer_name"] == "vm"
    assert vm["additional_capabilities"]["ultra_ssd_enabled"] is True
    assert vm["license_type"] == "Windows_Server"
    assert vm["eviction_policy"] == "Deallocate"


def test_transform_vm_list_finds_sdk_38_data_disks():
    vms, data_disks = transform_vm_list(
        [
            transform_vm(
                {
                    "id": "vm-id",
                    "properties": {
                        "storageProfile": {
                            "dataDisks": [
                                {
                                    "name": "data-disk",
                                    "lun": 0,
                                    "diskSizeGB": 128,
                                }
                            ]
                        }
                    },
                }
            )
        ]
    )

    assert vms[0]["id"] == "vm-id"
    assert data_disks == [
        {
            "name": "data-disk",
            "lun": 0,
            "diskSizeGB": 128,
            "disk_size_gb": 128,
            "vm_id": "vm-id",
        }
    ]


def test_transform_disk_and_snapshot_flatten_sdk_38_properties():
    disk = transform_disk(
        {
            "id": "disk-id",
            "properties": {
                "diskSizeGB": 128,
                "networkAccessPolicy": "AllowAll",
                "osType": "Linux",
                "diskState": "Attached",
            },
        }
    )
    snapshot = transform_snapshot(
        {
            "id": "snapshot-id",
            "properties": {
                "diskSizeGB": 128,
                "networkAccessPolicy": "AllowAll",
                "osType": "Linux",
                "incremental": True,
            },
        }
    )

    assert disk["disk_size_gb"] == 128
    assert disk["network_access_policy"] == "AllowAll"
    assert disk["os_type"] == "Linux"
    assert disk["disk_state"] == "Attached"
    assert snapshot["disk_size_gb"] == 128
    assert snapshot["network_access_policy"] == "AllowAll"
    assert snapshot["os_type"] == "Linux"
    assert snapshot["incremental"] is True


def test_get_vm_list_raises_instead_of_reporting_an_empty_inventory():
    """A failed inventory read must not become []: sync_virtual_machine would load
    nothing and cleanup_virtual_machine would delete the subscription's whole VM
    inventory, treating unknown coverage as authoritative absence."""
    # Arrange
    client = MagicMock()
    client.virtual_machines.list_all.side_effect = HttpResponseError(
        "(AuthorizationFailed) no access to Microsoft.Compute"
    )

    # Act
    with patch.object(compute, "get_client", return_value=client):
        with pytest.raises(compute.AzureVirtualMachineInventoryError) as raised:
            compute.get_vm_list(MagicMock(), "sub-1")

    # Assert
    assert isinstance(raised.value, compute.AzureVirtualMachineInventoryError)
    assert raised.value.subscription_id == "sub-1"


def test_get_vm_list_raises_on_a_transport_failure_too():
    # Arrange
    client = MagicMock()
    client.virtual_machines.list_all.side_effect = ServiceRequestTimeoutError(
        "connection timed out"
    )

    # Act and assert
    with patch.object(compute, "get_client", return_value=client):
        with pytest.raises(compute.AzureVirtualMachineInventoryError):
            compute.get_vm_list(MagicMock(), "sub-1")


def test_get_vm_list_returns_empty_when_azure_answers_with_no_vms():
    """An answered read of zero VMs is authoritative absence and must stay []."""
    # Arrange
    client = MagicMock()
    client.virtual_machines.list_all.return_value = []

    # Act
    with patch.object(compute, "get_client", return_value=client):
        result = compute.get_vm_list(MagicMock(), "sub-1")

    # Assert
    assert result == []
