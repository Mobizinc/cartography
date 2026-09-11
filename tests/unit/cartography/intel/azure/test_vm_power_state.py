from unittest.mock import MagicMock

from azure.core.exceptions import HttpResponseError
from azure.core.exceptions import ServiceRequestTimeoutError

import cartography.intel.azure.vm_power_state as vm_power_state
from tests.data.azure.vm_power_state import FORBIDDEN_VM_ID
from tests.data.azure.vm_power_state import MOCK_VM_LIST
from tests.data.azure.vm_power_state import NO_POWER_STATE_STATUSES
from tests.data.azure.vm_power_state import NO_STATUS_VM_ID
from tests.data.azure.vm_power_state import RUNNING_STATUSES
from tests.data.azure.vm_power_state import RUNNING_VM_ID


def _client():
    """A compute client whose instance view answers differently per VM name."""

    def instance_view(resource_group, name):
        if name == "vm-running":
            view = MagicMock()
            view.statuses = RUNNING_STATUSES
            return view
        if name == "vm-no-status":
            view = MagicMock()
            view.statuses = NO_POWER_STATE_STATUSES
            return view
        raise HttpResponseError("(AuthorizationFailed) no access to Microsoft.Compute")

    client = MagicMock()
    client.virtual_machines.instance_view.side_effect = instance_view
    return client


def test_get_power_states_strips_the_power_state_prefix():
    # Act

    # Assert
    assert (
        vm_power_state.get_power_states(_client(), MOCK_VM_LIST)[RUNNING_VM_ID]
        == "running"
    )


def test_get_power_states_survives_a_transport_failure():
    """ServiceRequestError is a sibling of HttpResponseError, not a subclass. Catching
    only the latter would let a connection timeout abort the whole subscription sync."""

    # Arrange
    def instance_view(resource_group, name):
        if name == "vm-running":
            view = MagicMock()
            view.statuses = RUNNING_STATUSES
            return view
        raise ServiceRequestTimeoutError("connection timed out")

    client = MagicMock()
    client.virtual_machines.instance_view.side_effect = instance_view

    # Act
    states = vm_power_state.get_power_states(client, MOCK_VM_LIST)

    # Assert
    assert states == {RUNNING_VM_ID: "running"}


def test_get_power_states_omits_vm_whose_instance_view_is_unreadable():
    """Unreadable is unknown, never stopped, so the VM must be absent from the mapping
    and keep whatever power state the graph already holds."""
    # Act
    states = vm_power_state.get_power_states(_client(), MOCK_VM_LIST)

    # Assert
    assert FORBIDDEN_VM_ID not in states


def test_get_power_states_omits_vm_whose_view_carried_no_power_state():
    # Act
    states = vm_power_state.get_power_states(_client(), MOCK_VM_LIST)

    # Assert
    assert NO_STATUS_VM_ID not in states


def test_transform_power_states_only_touches_vms_with_a_state():
    # Arrange
    vm_list = [dict(vm) for vm in MOCK_VM_LIST]

    result = vm_power_state.transform_power_states(
        vm_list, {RUNNING_VM_ID: "running"}, "2026-09-11T00:00:00+00:00"
    )

    # Act
    by_id = {vm["id"]: vm for vm in result}
    # Assert
    assert by_id[RUNNING_VM_ID]["power_state"] == "running"
    assert by_id[RUNNING_VM_ID]["power_state_read_at"] == "2026-09-11T00:00:00+00:00"
    assert "power_state" not in by_id[FORBIDDEN_VM_ID]
    assert "power_state_read_at" not in by_id[FORBIDDEN_VM_ID]


def test_backfill_keeps_a_known_state_when_the_read_failed(monkeypatch):
    """A transient authorization or API failure must not overwrite a state an earlier
    sync read: load() writes every declared property, so an absent field becomes null.
    """
    # Arrange
    vm_list = [dict(vm) for vm in MOCK_VM_LIST]
    monkeypatch.setattr(
        vm_power_state,
        "get_known_power_states",
        lambda session, subscription_id: {
            FORBIDDEN_VM_ID: {
                "power_state": "deallocated",
                "power_state_read_at": "2026-09-01T00:00:00+00:00",
            }
        },
    )

    result = vm_power_state.backfill(MagicMock(), "sub", vm_list)

    # Act
    by_id = {vm["id"]: vm for vm in result}
    # Assert
    assert by_id[FORBIDDEN_VM_ID]["power_state"] == "deallocated"
    assert by_id[FORBIDDEN_VM_ID]["power_state_read_at"] == "2026-09-01T00:00:00+00:00"
    # A VM the graph knows nothing about stays absent rather than gaining a null.
    assert "power_state" not in by_id[NO_STATUS_VM_ID]


def test_backfill_does_not_overwrite_a_state_read_this_sync(monkeypatch):
    # Arrange
    vm_list = [dict(vm) for vm in MOCK_VM_LIST]
    vm_list[0]["power_state"] = "running"
    vm_list[0]["power_state_read_at"] = "2026-09-11T00:00:00+00:00"
    monkeypatch.setattr(
        vm_power_state,
        "get_known_power_states",
        lambda session, subscription_id: {
            RUNNING_VM_ID: {"power_state": "deallocated", "power_state_read_at": "old"}
        },
    )

    result = vm_power_state.backfill(MagicMock(), "sub", vm_list)

    # Act
    by_id = {vm["id"]: vm for vm in result}
    # Assert
    assert by_id[RUNNING_VM_ID]["power_state"] == "running"
    assert by_id[RUNNING_VM_ID]["power_state_read_at"] == "2026-09-11T00:00:00+00:00"


def test_backfill_reads_the_graph_only_when_something_is_missing(monkeypatch):
    # Arrange
    calls = []
    monkeypatch.setattr(
        vm_power_state,
        "get_known_power_states",
        lambda session, subscription_id: calls.append(1) or {},
    )

    # Act
    vm_power_state.backfill(
        MagicMock(), "sub", [{"id": RUNNING_VM_ID, "power_state": "running"}]
    )

    # Assert
    assert calls == []


def test_resource_group_and_name_parsed_case_insensitively():
    # Act
    upper = RUNNING_VM_ID.replace("resourcegroups", "resourceGroups")

    # Assert
    assert vm_power_state._resource_group_and_name(upper) == ("test-rg", "vm-running")
