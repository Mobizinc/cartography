"""Virtual machine power state, read from the ARM instance view.

One call per VM, because ARM rejects ``expand=instanceView`` on its virtual machine list
operations. This enriches the rows ``compute.get_vm_list`` returned rather than loading
separately: ``load()`` writes every property its schema declares, so a partial row would
null the properties it omits on a node that already exists.

For the same reason a VM whose instance view did not answer is backfilled from the graph
rather than left absent. ``load()`` would otherwise write null over a power state an
earlier sync had read, turning a transient authorization or API failure into data loss.
"""

import logging
from datetime import datetime
from datetime import timezone
from typing import Any

import neo4j
from azure.core.exceptions import AzureError
from azure.mgmt.compute import ComputeManagementClient

logger = logging.getLogger(__name__)

POWER_STATE_PREFIX = "PowerState/"


def _resource_group_and_name(resource_id: str) -> tuple[str, str]:
    parts = resource_id.split("/")
    lowered = [part.lower() for part in parts]
    return parts[lowered.index("resourcegroups") + 1], parts[-1]


def get_power_state(
    client: ComputeManagementClient, resource_group: str, name: str
) -> str | None:
    """The PowerState code from the instance view, without its ``PowerState/`` prefix."""
    view = client.virtual_machines.instance_view(resource_group, name)
    for status in view.statuses or []:
        code = getattr(status, "code", None) or ""
        if code.startswith(POWER_STATE_PREFIX):
            return code[len(POWER_STATE_PREFIX) :]
    return None


def get_power_states(
    client: ComputeManagementClient, vm_list: list[dict]
) -> dict[str, str]:
    """Power state per VM resource id, omitting any VM whose instance view did not answer.

    Omission means unknown, never stopped. A VM missing from this mapping keeps whatever
    power state the graph already holds.
    """
    states: dict[str, str] = {}
    for vm in vm_list:
        resource_id = vm.get("id")
        if not resource_id:
            continue
        resource_group, name = _resource_group_and_name(resource_id)
        try:
            power_state = get_power_state(client, resource_group, name)
        # AzureError, not HttpResponseError: ServiceRequestError and ServiceResponseError
        # are its siblings, not its subclasses, so a connection timeout would otherwise
        # escape this per-VM boundary and abort the whole subscription sync.
        except AzureError as error:
            logger.warning(
                "Skipping power state for %s: instance view unreadable - %s",
                resource_id,
                error,
            )
            continue
        if power_state is None:
            logger.warning(
                "Skipping power state for %s: the instance view carried no PowerState "
                "status.",
                resource_id,
            )
            continue
        states[resource_id] = power_state
    return states


def get_known_power_states(
    neo4j_session: neo4j.Session, subscription_id: str
) -> dict[str, dict[str, Any]]:
    """The power state each VM in the subscription already carries in the graph."""
    query = """
    MATCH (:AzureSubscription{id: $AZURE_SUBSCRIPTION_ID})-[:RESOURCE]->(vm:AzureVirtualMachine)
    WHERE vm.power_state IS NOT NULL
    RETURN vm.id AS id, vm.power_state AS power_state,
           vm.power_state_read_at AS power_state_read_at
    """
    rows = neo4j_session.run(query, AZURE_SUBSCRIPTION_ID=subscription_id)
    return {row["id"]: dict(row) for row in rows if row.get("id")}


def transform_power_states(
    vm_list: list[dict], power_states: dict[str, str], read_at: str
) -> list[dict[str, Any]]:
    """Merge the states that were read into the VM rows, returning the same list."""
    for vm in vm_list:
        power_state = power_states.get(vm.get("id", ""))
        if power_state is None:
            continue
        vm["power_state"] = power_state
        vm["power_state_read_at"] = read_at
    return vm_list


def enrich(
    client: ComputeManagementClient, vm_list: list[dict]
) -> list[dict[str, Any]]:
    """Add power_state and power_state_read_at to the VM rows ARM answered for.

    ``power_state_read_at`` is the clock of the sync that read the state, not a source
    observation time: ARM does not stamp the PowerState status.
    """
    read_at = datetime.now(timezone.utc).isoformat()
    return transform_power_states(vm_list, get_power_states(client, vm_list), read_at)


def backfill(
    neo4j_session: neo4j.Session, subscription_id: str, vm_list: list[dict]
) -> list[dict[str, Any]]:
    """Restore the last known power state onto rows whose instance view did not answer.

    Without this, ``load()`` writes null over a state an earlier sync read, turning a
    transient authorization or API failure into data loss. A VM the graph knows nothing
    about is left untouched rather than given a null.
    """
    missing = [vm for vm in vm_list if vm.get("power_state") is None]
    if not missing:
        return vm_list
    known = get_known_power_states(neo4j_session, subscription_id)
    for vm in missing:
        previous = known.get(vm.get("id", ""))
        if previous:
            vm["power_state"] = previous.get("power_state")
            vm["power_state_read_at"] = previous.get("power_state_read_at")
    return vm_list
