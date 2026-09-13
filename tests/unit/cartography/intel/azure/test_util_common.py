import pytest

from cartography.intel.azure.util.common import copy_properties
from cartography.intel.azure.util.common import get_value
from cartography.intel.azure.util.common import reference_id


@pytest.mark.parametrize(
    "data,expected",
    [
        # Flat and snake_case, as older SDKs returned it.
        ({"private_ip_address": "10.0.0.4"}, "10.0.0.4"),
        # Nested and camelCase, as as_dict() returns it on the current hybrid models.
        ({"properties": {"privateIPAddress": "10.0.0.4"}}, "10.0.0.4"),
        # A top-level spelling wins over a nested one.
        (
            {
                "private_ip_address": "10.0.0.4",
                "properties": {"privateIPAddress": "10.0.0.5"},
            },
            "10.0.0.4",
        ),
        ({"properties": None}, None),
        ({}, None),
        (None, None),
        ("not-a-dict", None),
    ],
)
def test_get_value_reads_either_shape(data, expected):
    assert get_value(data, "private_ip_address", "privateIPAddress") == expected


def test_get_value_returns_a_present_falsy_value_rather_than_the_next_key():
    assert get_value({"properties": {"primary": False}}, "primary") is False


def test_reference_id_reads_a_reference_in_either_shape():
    assert reference_id({"subnet": {"id": "subnet-id"}}, "subnet") == "subnet-id"
    assert (
        reference_id(
            {"properties": {"publicIPAddress": {"id": "pip-id"}}}, "publicIPAddress"
        )
        == "pip-id"
    )


@pytest.mark.parametrize(
    "data", [{}, {"subnet": None}, {"subnet": "subnet-id"}, {"subnet": {}}]
)
def test_reference_id_of_anything_that_is_not_a_reference_is_none(data):
    assert reference_id(data, "subnet") is None


def test_copy_properties_lifts_the_wire_spelling_to_the_key_the_models_read():
    assert (
        copy_properties(
            {"properties": {"diskSizeGB": 128}},
            {"disk_size_gb": ("disk_size_gb", "diskSizeGB")},
        )["disk_size_gb"]
        == 128
    )


def test_copy_properties_never_overwrites_a_key_that_is_already_there():
    assert (
        copy_properties(
            {"disk_size_gb": 64, "properties": {"diskSizeGB": 128}},
            {"disk_size_gb": ("disk_size_gb", "diskSizeGB")},
        )["disk_size_gb"]
        == 64
    )


def test_copy_properties_lifts_a_nested_key_with_no_properties_block():
    """`transform_vm` calls this on blocks it has already lifted, whose own fields are flat
    and camelCase."""
    assert copy_properties({"vmSize": "Standard_D2s_v3"}, {"vm_size": ("vmSize",)}) == {
        "vmSize": "Standard_D2s_v3",
        "vm_size": "Standard_D2s_v3",
    }


def test_copy_properties_leaves_an_absent_field_absent():
    assert copy_properties({"properties": {}}, {"os_type": ("osType",)}) == {
        "properties": {}
    }
