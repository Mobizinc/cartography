from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from azure.core.exceptions import HttpResponseError

import cartography.intel.azure.compute as compute
from tests.data.azure.vm_power_state import FORBIDDEN_VM_ID
from tests.data.azure.vm_power_state import MOCK_VM_LIST
from tests.data.azure.vm_power_state import NO_POWER_STATE_STATUSES
from tests.data.azure.vm_power_state import NO_STATUS_VM_ID
from tests.data.azure.vm_power_state import RUNNING_STATUSES
from tests.data.azure.vm_power_state import RUNNING_VM_ID
from tests.integration.util import check_nodes

TEST_SUBSCRIPTION_ID = "00-00-00-00"
TEST_UPDATE_TAG = 123456789


def _compute_client():
    """A compute client whose VM list and instance views behave like ARM's.

    vm-running answers with a PowerState status, vm-no-status answers without one, and
    vm-forbidden refuses - the three cases the graph must distinguish.
    """

    def instance_view(resource_group, name):
        view = MagicMock()
        if name == "vm-running":
            view.statuses = RUNNING_STATUSES
            return view
        if name == "vm-no-status":
            view.statuses = NO_POWER_STATE_STATUSES
            return view
        raise HttpResponseError("(AuthorizationFailed) no access to Microsoft.Compute")

    client = MagicMock()
    client.virtual_machines.list_all.return_value = [
        MagicMock(as_dict=lambda vm=vm: dict(vm)) for vm in MOCK_VM_LIST
    ]
    client.virtual_machines.instance_view.side_effect = instance_view
    return client


@patch.object(compute, "get_client")
def test_sync_virtual_machine_loads_power_state(mock_get_client, neo4j_session):
    # Arrange
    mock_get_client.return_value = _compute_client()
    neo4j_session.run(
        "MERGE (s:AzureSubscription{id: $sub_id}) SET s.lastupdated = $tag",
        sub_id=TEST_SUBSCRIPTION_ID,
        tag=TEST_UPDATE_TAG,
    )

    # Act
    compute.sync_virtual_machine(
        neo4j_session,
        MagicMock(),
        TEST_SUBSCRIPTION_ID,
        TEST_UPDATE_TAG,
        {"UPDATE_TAG": TEST_UPDATE_TAG, "AZURE_SUBSCRIPTION_ID": TEST_SUBSCRIPTION_ID},
    )

    # A VM whose instance view did not answer keeps power_state unset. It must never be
    # written as stopped, and its other properties must survive the enrichment.

    # Assert
    assert check_nodes(
        neo4j_session, "AzureVirtualMachine", ["id", "name", "power_state"]
    ) == {
        (RUNNING_VM_ID, "vm-running", "running"),
        (NO_STATUS_VM_ID, "vm-no-status", None),
        (FORBIDDEN_VM_ID, "vm-forbidden", None),
    }


@patch.object(compute, "get_client")
def test_power_state_read_at_is_set_only_where_a_state_was_read(
    mock_get_client, neo4j_session
):
    # Arrange
    mock_get_client.return_value = _compute_client()
    neo4j_session.run(
        "MERGE (s:AzureSubscription{id: $sub_id}) SET s.lastupdated = $tag",
        sub_id=TEST_SUBSCRIPTION_ID,
        tag=TEST_UPDATE_TAG,
    )

    # Act
    compute.sync_virtual_machine(
        neo4j_session,
        MagicMock(),
        TEST_SUBSCRIPTION_ID,
        TEST_UPDATE_TAG,
        {"UPDATE_TAG": TEST_UPDATE_TAG, "AZURE_SUBSCRIPTION_ID": TEST_SUBSCRIPTION_ID},
    )

    read_at = {
        row["id"]: row["read_at"]
        for row in neo4j_session.run(
            "MATCH (vm:AzureVirtualMachine) "
            "RETURN vm.id AS id, vm.power_state_read_at AS read_at"
        )
    }

    # Assert
    assert read_at[RUNNING_VM_ID] is not None
    assert read_at[NO_STATUS_VM_ID] is None
    assert read_at[FORBIDDEN_VM_ID] is None


@patch.object(compute, "get_client")
def test_unreadable_instance_view_keeps_the_previously_known_state(
    mock_get_client, neo4j_session
):
    """A 403 on Microsoft.Compute must not wipe a state an earlier sync recorded."""

    # Arrange
    mock_get_client.return_value = _compute_client()
    neo4j_session.run(
        "MERGE (s:AzureSubscription{id: $sub_id}) SET s.lastupdated = $tag",
        sub_id=TEST_SUBSCRIPTION_ID,
        tag=TEST_UPDATE_TAG,
    )
    # An earlier sync read this VM as deallocated; this one cannot read it at all.
    neo4j_session.run(
        """
        MATCH (s:AzureSubscription{id: $sub_id})
        MERGE (vm:AzureVirtualMachine{id: $vm_id})
        SET vm.lastupdated = $tag, vm.power_state = 'deallocated',
            vm.power_state_read_at = '2026-09-01T00:00:00+00:00'
        MERGE (s)-[r:RESOURCE]->(vm) SET r.lastupdated = $tag
        """,
        sub_id=TEST_SUBSCRIPTION_ID,
        vm_id=FORBIDDEN_VM_ID,
        tag=TEST_UPDATE_TAG,
    )

    # Act
    compute.sync_virtual_machine(
        neo4j_session,
        MagicMock(),
        TEST_SUBSCRIPTION_ID,
        TEST_UPDATE_TAG,
        {"UPDATE_TAG": TEST_UPDATE_TAG, "AZURE_SUBSCRIPTION_ID": TEST_SUBSCRIPTION_ID},
    )

    # Assert
    assert check_nodes(
        neo4j_session,
        "AzureVirtualMachine",
        ["id", "power_state", "power_state_read_at"],
    ) == {
        (RUNNING_VM_ID, "running", _read_at(neo4j_session, RUNNING_VM_ID)),
        (NO_STATUS_VM_ID, None, None),
        (FORBIDDEN_VM_ID, "deallocated", "2026-09-01T00:00:00+00:00"),
    }


def _read_at(neo4j_session, vm_id):
    return neo4j_session.run(
        "MATCH (vm:AzureVirtualMachine{id: $id}) RETURN vm.power_state_read_at AS r",
        id=vm_id,
    ).single()["r"]


@patch.object(compute, "get_client")
def test_unreadable_inventory_does_not_delete_the_existing_vms(
    mock_get_client, neo4j_session
):
    """The failure proved in evaluation: a 403 on the VM list used to empty the whole
    subscription's inventory. The read must now fail loudly and delete nothing."""
    # Arrange
    mock_get_client.return_value = _compute_client()
    neo4j_session.run(
        "MERGE (s:AzureSubscription{id: $sub_id}) SET s.lastupdated = $tag",
        sub_id=TEST_SUBSCRIPTION_ID,
        tag=TEST_UPDATE_TAG,
    )
    # Act
    compute.sync_virtual_machine(
        neo4j_session,
        MagicMock(),
        TEST_SUBSCRIPTION_ID,
        TEST_UPDATE_TAG,
        {"UPDATE_TAG": TEST_UPDATE_TAG, "AZURE_SUBSCRIPTION_ID": TEST_SUBSCRIPTION_ID},
    )

    # Assert
    before = check_nodes(neo4j_session, "AzureVirtualMachine", ["id"])
    assert before == {(RUNNING_VM_ID,), (NO_STATUS_VM_ID,), (FORBIDDEN_VM_ID,)}

    # Arrange - the next sync cannot read the inventory at all.
    failing = MagicMock()
    failing.virtual_machines.list_all.side_effect = HttpResponseError(
        "(AuthorizationFailed) no access to Microsoft.Compute"
    )
    mock_get_client.return_value = failing
    next_tag = TEST_UPDATE_TAG + 1

    # Act and assert
    with pytest.raises(compute.AzureVirtualMachineInventoryError):
        compute.sync_virtual_machine(
            neo4j_session,
            MagicMock(),
            TEST_SUBSCRIPTION_ID,
            next_tag,
            {"UPDATE_TAG": next_tag, "AZURE_SUBSCRIPTION_ID": TEST_SUBSCRIPTION_ID},
        )

    # Assert - nothing was deleted.
    assert check_nodes(neo4j_session, "AzureVirtualMachine", ["id"]) == before
