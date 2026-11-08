"""Source separation and offline-safe sampling for Drive device metadata."""

from copy import deepcopy
from datetime import UTC, datetime
from importlib import import_module

import pytest
from tests.module_stubs import load_api_module

load_api_module()

metadata = import_module("custom_components.unifi_unas.system_metadata")
drive_version = metadata.drive_version
sampled_device_info = metadata.sampled_device_info
system_payload = metadata.system_payload
unifi_os_version = metadata.unifi_os_version


def test_metadata_keeps_versions_identity_and_status_in_their_source():
    data = {
        "_system": {"status": "offline", "systemId": "core-device", "cpu": {"temperature": None}},
        "_device_info": {
            "version": "4.3.6", "firmwareVersion": "5.1.10", "systemId": "app-device",
            "status": "online", "cpu": {"temperature": 42}, "uptime": 7200,
            "networkInterfaces": [{"ipAddress": "192.0.2.10"}],
        },
    }
    original = deepcopy(data)
    merged = system_payload(data)
    assert merged["status"] == "offline"
    assert merged["systemId"] == "core-device"
    assert merged["cpu"]["temperature"] == 42
    assert merged["uptime"] == 7200
    assert merged["networkInterfaces"] == data["_device_info"]["networkInterfaces"]
    assert "version" not in merged
    assert unifi_os_version(data) == "5.1.10"
    assert drive_version(data) == "4.3.6"
    assert data == original


def test_metadata_never_mistakes_app_version_for_os_version_or_reverse():
    assert unifi_os_version({"_device_info": {"version": "4.3.6"}}) is None
    assert drive_version({"_system": {"version": "5.1.10"}}) is None
    assert unifi_os_version({"_device_info": {"firmwareVersion": {"secret": "value"}}}) is None
    assert drive_version({"_device_info": {"version": ["private"]}}) is None


@pytest.mark.parametrize("uptime", [{"uptime": 0}, {"uptimeSeconds": 0}, {"uptimeMs": 1000}])
def test_core_metadata_precedes_drive_fallbacks(uptime):
    core = {**uptime, "cpu": {"temperature": 50}, "hardware": {"firmwareVersion": "5.1.19"},
            "apps": [{"name": "drive", "version": "4.4.0"}]}
    data = {"_system": core, "_device_info": {"uptime": 7200, "cpu": {"temperature": 42},
            "firmwareVersion": "5.1.10", "version": "4.3.6"}}
    merged = system_payload(data)
    assert merged == core
    assert unifi_os_version(data) == "5.1.19"
    assert drive_version(data) == "4.4.0"


@pytest.mark.parametrize("started,seconds", [
    ("2026-01-01T00:00:00Z", 7200),
    ("2026-01-01T01:00:00+01:00", 7200),
    ("2026-01-01T03:00:00Z", None),
    ("2026-01-01T00:00:00", None),
    ("not-a-time", None), (None, None), ({"timestamp": "private"}, None),
])
def test_startup_time_is_sampled_with_explicit_timezone(started, seconds):
    payload = {"startupTime": started, "version": "4.3.6", "uptime": 999}
    sampled = sampled_device_info(payload, datetime(2026, 1, 1, 2, tzinfo=UTC))
    assert sampled.get("uptime") == seconds
    assert payload["uptime"] == 999
    assert sampled["version"] == "4.3.6"
