import logging
from collections.abc import Mapping
from typing import Any

logger = logging.getLogger(__name__)


def extract_identity_principal_ids(identity: Any) -> list[str]:
    """
    Collect the object (principal) ids of a resource's managed identities from
    the ARM `identity` block: the system-assigned principal plus every
    user-assigned identity. These ids match an EntraServicePrincipal.id and an
    AzureRoleAssignment.principal_id, so they anchor the workload-identity
    (RUNS_AS / ASSUMES) edges. Handles both camelCase (ARM wire) and snake_case
    key spellings defensively.
    """
    if not isinstance(identity, dict):
        return []
    ids: list[str] = []
    system_pid = identity.get("principalId") or identity.get("principal_id")
    if system_pid:
        ids.append(system_pid)
    user_assigned = (
        identity.get("userAssignedIdentities")
        or identity.get("user_assigned_identities")
        or {}
    )
    if isinstance(user_assigned, dict):
        for entry in user_assigned.values():
            if isinstance(entry, dict):
                pid = entry.get("principalId") or entry.get("principal_id")
                if pid:
                    ids.append(pid)
    # Preserve order, drop duplicates.
    return list(dict.fromkeys(ids))


def get_value(data: Any, *keys: str) -> Any:
    """
    The first of `keys` present on `data` or inside its ARM `properties` block.

    The current Azure SDK hybrid models serialize `as_dict()` in wire format, so
    resource-specific fields live under `properties` with camelCase names, while older
    SDKs returned them flat and snake_case. Callers name every spelling a field is known
    by, in order of preference, and read either shape.
    """
    if not isinstance(data, dict):
        return None
    properties = data.get("properties") or {}
    for key in keys:
        if key in data:
            return data[key]
        if key in properties:
            return properties[key]
    return None


def reference_id(data: Any, *keys: str) -> str | None:
    """
    The resource id of a reference ARM returns as `{"id": ...}`, or None when the field is
    absent or carries something else.
    """
    reference = get_value(data, *keys)
    return reference.get("id") if isinstance(reference, dict) else None


def copy_properties(data: dict, mapping: Mapping[str, tuple[str, ...]]) -> dict:
    """
    Lift fields out of an ARM `properties` block onto the top level of `data`.

    The graph models read flat snake_case keys, so each mapping entry names the target key
    and the wire spellings to look for, in order of preference. Existing top-level keys are
    never overwritten.
    """
    for target, sources in mapping.items():
        if target in data:
            continue
        value = get_value(data, *sources)
        if value is not None:
            data[target] = value
    return data


def rename_keys(data: Any, mapping: Mapping[str, str]) -> Any:
    """
    Alias camelCase wire keys of a nested ARM object to the snake_case names the graph
    models read. Returns `data` untouched when it is not a dict, so callers can pipe
    optional nested blocks straight through.
    """
    if not isinstance(data, dict):
        return data
    for target, source in mapping.items():
        if target not in data and source in data:
            data[target] = data[source]
    return data


def get_resource_group_from_id(resource_id: str) -> str:
    """
    Helper function to parse the resource group name from a full resource ID string.
    e.g. /subscriptions/sub_id/resourceGroups/rg_name/providers/...
    """
    parts = resource_id.lower().split("/")
    rg_index = parts.index("resourcegroups")
    return parts[rg_index + 1]
