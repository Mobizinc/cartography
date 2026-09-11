"""Instance view statuses in the shape `virtual_machines.instance_view()` returns."""

from unittest.mock import MagicMock

SUBSCRIPTION_ID = "00-00-00-00"
RG = f"/subscriptions/{SUBSCRIPTION_ID}/resourcegroups/test-rg"

RUNNING_VM_ID = f"{RG}/providers/microsoft.compute/virtualmachines/vm-running"
NO_STATUS_VM_ID = f"{RG}/providers/microsoft.compute/virtualmachines/vm-no-status"
FORBIDDEN_VM_ID = f"{RG}/providers/microsoft.compute/virtualmachines/vm-forbidden"

MOCK_VM_LIST = [
    {"id": RUNNING_VM_ID, "name": "vm-running"},
    {"id": NO_STATUS_VM_ID, "name": "vm-no-status"},
    {"id": FORBIDDEN_VM_ID, "name": "vm-forbidden"},
]


def _status(code: str) -> MagicMock:
    status = MagicMock()
    status.code = code
    return status


#: A real instance view carries provisioning state alongside power state.
RUNNING_STATUSES = [
    _status("ProvisioningState/succeeded"),
    _status("PowerState/running"),
]

#: Answered, but with no PowerState row at all.
NO_POWER_STATE_STATUSES = [_status("ProvisioningState/succeeded")]
