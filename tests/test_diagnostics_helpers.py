"""Unit tests for diagnostics redaction."""

import asyncio
from enum import Enum
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
import types

from tests.storage_fixtures import multi_pool_storage


def _redact_data(value, keys):
    if isinstance(value, dict):
        return {
            key: "REDACTED" if key in keys else _redact_data(child, keys)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [_redact_data(item, keys) for item in value]
    return value


def _load_diagnostics_module():
    root = Path(__file__).resolve().parents[1]
    package_root = root / "custom_components" / "unifi_unas"

    custom_components_pkg = types.ModuleType("custom_components")
    custom_components_pkg.__path__ = [str(root / "custom_components")]
    sys.modules.setdefault("custom_components", custom_components_pkg)

    drive_pkg = types.ModuleType("custom_components.unifi_unas")
    drive_pkg.__path__ = [str(package_root)]
    sys.modules["custom_components.unifi_unas"] = drive_pkg

    ha_pkg = types.ModuleType("homeassistant")
    sys.modules["homeassistant"] = ha_pkg

    components_pkg = types.ModuleType("homeassistant.components")
    sys.modules["homeassistant.components"] = components_pkg

    diagnostics_pkg = types.ModuleType("homeassistant.components.diagnostics")
    diagnostics_pkg.async_redact_data = _redact_data
    sys.modules["homeassistant.components.diagnostics"] = diagnostics_pkg

    config_entries_pkg = types.ModuleType("homeassistant.config_entries")
    config_entries_pkg.ConfigEntry = object
    sys.modules["homeassistant.config_entries"] = config_entries_pkg

    const_pkg = types.ModuleType("homeassistant.const")
    const_pkg.CONF_API_KEY = "api_key"
    const_pkg.CONF_HOST = "host"
    const_pkg.CONF_PASSWORD = "password"
    const_pkg.CONF_USERNAME = "username"

    class Platform(str, Enum):
        BINARY_SENSOR = "binary_sensor"
        BUTTON = "button"
        NUMBER = "number"
        SELECT = "select"
        SENSOR = "sensor"
        SWITCH = "switch"
        TIME = "time"
        UPDATE = "update"

    const_pkg.Platform = Platform
    sys.modules["homeassistant.const"] = const_pkg

    core_pkg = types.ModuleType("homeassistant.core")
    core_pkg.HomeAssistant = object
    sys.modules["homeassistant.core"] = core_pkg

    coordinator_pkg = types.ModuleType("custom_components.unifi_unas.coordinator")
    coordinator_pkg.UnifiUnasCoordinator = object
    sys.modules["custom_components.unifi_unas.coordinator"] = coordinator_pkg

    const_spec = spec_from_file_location(
        "custom_components.unifi_unas.const",
        package_root / "const.py",
    )
    if const_spec is None or const_spec.loader is None:
        raise RuntimeError("Could not load const module spec")
    const_module = module_from_spec(const_spec)
    sys.modules["custom_components.unifi_unas.const"] = const_module
    const_spec.loader.exec_module(const_module)

    diagnostics_spec = spec_from_file_location(
        "custom_components.unifi_unas.diagnostics",
        package_root / "diagnostics.py",
    )
    if diagnostics_spec is None or diagnostics_spec.loader is None:
        raise RuntimeError("Could not load diagnostics module spec")
    diagnostics_module = module_from_spec(diagnostics_spec)
    sys.modules["custom_components.unifi_unas.diagnostics"] = diagnostics_module
    diagnostics_spec.loader.exec_module(diagnostics_module)
    return diagnostics_module


diagnostics_module = _load_diagnostics_module()


def _manifest_version() -> str:
    """Return the integration version from the local manifest."""
    manifest_path = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "unifi_unas"
        / "manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return str(manifest["version"])


class _FakeClient:
    poweroff_permission_hint = "ok"
    native_fan_mode = "Cooling"
    fan_mode_read_supported = True
    fan_mode_write_supported = False
    fan_mode_write_payload_hint = "profile_apply"
    backup_tasks_read_supported = True
    snapshot_settings_read_supported = True
    snapshot_settings_write_supported = None
    snapshot_settings_write_supported_by_type = {"shared": False, "mydrive": True}
    snapshot_create_supported = None
    snapshot_create_supported_by_type = {"shared": True}
    snapshot_inventory_supported = True
    snapshot_inventory_supported_by_type = {"shared": True, "mydrive": False}


class _FakeCoordinator:
    client = _FakeClient()
    fan_mode = "Cooling"
    fan_control_enabled = True
    snapshot_buttons_enabled = True
    is_device_online = False
    last_update_success = True
    backup_tasks = [{"id": "task-1", "name": "Nightly Backup"}]
    snapshot_settings = [
        {"id": "mydrive", "name": "My Drive", "type": "mydrive"},
        {"id": "shared-1", "name": "Team", "type": "shared"},
    ]
    snapshot_inventory = {
        "shared_shared-1": {
            "snapshot_count": 2,
            "locked_count": 1,
        }
    }
    snapshot_inventory_errors = {"mydrive_mydrive": "unsupported"}
    snapshot_inventory_skip_reasons = {"mydrive_mydrive": "unsupported"}
    snapshot_target_missing_counts = {
        "shared_missing": {
            "missing_count": 3,
            "target_name": "Missing Share",
            "target_type": "shared",
        }
    }
    data = {
        "pools": [
            {
                "name": "Pool 1",
                "status": "healthy",
                "serial": "pool-secret",
                "capacity": 10_000,
                "used": 4_000,
                "drives": [{"serial": "disk-secret", "temperature": 33, "healthScore": 5}],
            }
        ],
        "disks": [{"serial": "disk-secret", "temperature": 33}],
        "shares": {
            "Private Share": {
                "status": "healthy",
                "readThroughput": "private-share-throughput",
            },
            "CustomerBackup": {
                "status": "healthy",
            },
        },
        "snapshotTargets": {
            "8ab16324-5061-469f-a37f-c50a24227ceb": {
                "backupStatus": "ok",
            },
        },
        "Private Top Level": {"status": "hidden"},
        "CustomerStatus": {"status": "hidden"},
        "authorization": "Bearer secret",
        "readThroughput": "42 MB/s",
    }


class _FakeEntry:
    entry_id = "entry-1"
    unique_id = "aa:bb:cc:dd:ee:ff"
    version = 1
    minor_version = 2
    source = "user"
    disabled_by = None
    pref_disable_new_entities = False
    data = {
        "host": "unas.local",
        "username": "admin",
        "password": "secret-password",
        "api_key": "secret-api-key",
        "discovery_mac_address": "aa:bb:cc:dd:ee:01",
        "discovery_host_aliases": ["unas.local", "nas-vlan.local"],
        "discovery_last_seen": "2026-05-19T12:00:00Z",
        "discovery_identity_source": "zeroconf_property_mac",
        "discovery_confidence": 65,
        "discovery_identity_conflicts": ["zeroconf_mac_eui64_mismatch"],
        "wol_mac_address": "aa:bb:cc:dd:ee:ff",
        "wol_broadcast_address": "192.0.2.255",
        "authorization": "Bearer secret",
        "access_token": "token-secret",
        "cookie": "cookie-secret",
        "session": "session-secret",
        "nested": {"serialNumber": "serial-secret"},
    }
    options = {
        "discovery_debug": True,
        "wol_mac_address": "11:22:33:44:55:66",
        "wol_broadcast_address": "192.0.2.255",
        "scan_interval": 120,
    }


class _FakeHass:
    data = {"unifi_unas": {"entry-1": _FakeCoordinator()}}

    async def async_add_executor_job(self, job, *args):
        return job(*args)


def test_diagnostics_redacts_credentials_and_sensitive_entry_fields() -> None:
    """Diagnostics should not expose stored auth, MAC or serial-like fields."""
    result = asyncio.run(
        diagnostics_module.async_get_config_entry_diagnostics(
            _FakeHass(),
            _FakeEntry(),
        )
    )

    entry_data = result["config_entry"]["data"]
    assert entry_data["host"] == "REDACTED"
    assert entry_data["username"] == "REDACTED"
    assert entry_data["password"] == "REDACTED"
    assert entry_data["api_key"] == "REDACTED"
    assert entry_data["discovery_mac_address"] == "REDACTED"
    assert entry_data["discovery_host_aliases"] == "REDACTED"
    assert entry_data["wol_mac_address"] == "REDACTED"
    assert entry_data["wol_broadcast_address"] == "REDACTED"
    assert entry_data["authorization"] == "REDACTED"
    assert entry_data["access_token"] == "REDACTED"
    assert entry_data["cookie"] == "REDACTED"
    assert entry_data["session"] == "REDACTED"
    assert entry_data["nested"]["serialNumber"] == "REDACTED"
    entry_options = result["config_entry"]["options"]
    assert entry_options["discovery_debug"] is True
    assert entry_options["wol_mac_address"] == "REDACTED"
    assert entry_options["wol_broadcast_address"] == "REDACTED"
    assert entry_options["scan_interval"] == 120


def test_diagnostics_export_does_not_contain_raw_identifiers() -> None:
    """Diagnostics should anonymize the full exported JSON document."""
    result = asyncio.run(
        diagnostics_module.async_get_config_entry_diagnostics(
            _FakeHass(),
            _FakeEntry(),
        )
    )

    exported = json.dumps(result, sort_keys=True)
    raw_identifiers = (
        "entry-1",
        "unas.local",
        "nas-vlan.local",
        "admin",
        "secret-password",
        "secret-api-key",
        "aa:bb:cc:dd:ee:ff",
        "11:22:33:44:55:66",
        "192.0.2.255",
        "Bearer secret",
        "token-secret",
        "cookie-secret",
        "session-secret",
        "serial-secret",
        "task-1",
        "Nightly Backup",
        "Pool 1",
        "pool-secret",
        "disk-secret",
        "Private Share",
        "CustomerBackup",
        "private-share-throughput",
        "8ab16324-5061-469f-a37f-c50a24227ceb",
        "Private Top Level",
        "CustomerStatus",
        "shared-1",
        "Missing Share",
    )

    for raw_identifier in raw_identifiers:
        assert raw_identifier not in exported


def test_drive_device_info_export_keeps_values_and_dynamic_keys_private(monkeypatch):
    metadata = {
        "firmwareVersion": "5.1.10", "version": "4.3.6",
        "hostname": "private-device.example", "token": "private-metadata-token",
        "serial": "private-device-serial", "startupTime": "2026-01-01T00:00:00Z",
        "networkInterfaces": {"private-interface": {"ipAddress": "192.0.2.123",
                                                    "macAddress": "02:00:00:00:00:99"}},
        "cpu": {"temperature": 42},
    }
    monkeypatch.setattr(_FakeCoordinator, "data", {
        **_FakeCoordinator.data, "_device_info": metadata,
        "cacheSlots": [{"id": "private-cache-id", "serial": "private-cache-serial",
                        "name": "private-cache-name", "lifeSpan": 99}],
    })
    result = asyncio.run(diagnostics_module.async_get_config_entry_diagnostics(_FakeHass(), _FakeEntry()))
    exported = json.dumps(result, sort_keys=True)
    for secret in ("private-device.example", "private-metadata-token", "private-device-serial",
                   "private-interface", "192.0.2.123", "02:00:00:00:00:99",
                   "2026-01-01T00:00:00Z", "5.1.10", "4.3.6"):
        assert secret not in exported
    for secret in ("private-cache-id", "private-cache-serial", "private-cache-name"):
        assert secret not in exported
    assert result["schema_version"] == 1
    assert "_device_info" in exported


def test_multi_pool_diagnostics_export_counts_without_disk_or_pool_identifiers(monkeypatch):
    """Combined data/cache layouts keep support counts without revealing topology IDs."""
    payload = multi_pool_storage()
    monkeypatch.setattr(_FakeCoordinator, "data", payload)
    result = asyncio.run(diagnostics_module.async_get_config_entry_diagnostics(_FakeHass(), _FakeEntry()))
    exported = json.dumps(result, sort_keys=True)
    for item in (*payload["pools"], *payload["disks"], *payload["cacheSlots"]):
        for key in ("id", "serial", "name", "label", "poolId"):
            if key in item:
                assert item[key] not in exported
    assert result["schema_version"] == 1
    assert result["runtime"]["monitoring_health"]["pool_count"] == 2
    assert result["runtime"]["monitoring_health"]["drive_count"] == 8
    assert result["privacy"]["raw_storage_payload_values_included"] is False


def test_diagnostics_uses_versioned_standard_shape() -> None:
    """Diagnostics should expose a compact schema for support tooling."""
    result = asyncio.run(
        diagnostics_module.async_get_config_entry_diagnostics(
            _FakeHass(),
            _FakeEntry(),
        )
    )

    assert result["schema_version"] == 1
    assert set(result) == {
        "schema_version",
        "integration",
        "config_entry",
        "runtime",
        "capabilities",
        "data_shape",
        "privacy",
    }
    assert result["integration"] == {
        "domain": "unifi_unas",
        "name": "UniFi Drive / UNAS",
        "version": _manifest_version(),
        "iot_class": "local_polling",
        "integration_type": "device",
        "config_flow": True,
        "platforms": [
            "binary_sensor",
            "button",
            "number",
            "select",
            "sensor",
            "switch",
            "time",
            "update",
        ],
    }
    assert result["config_entry"]["entry_id_present"] is True
    assert result["config_entry"]["has_unique_id"] is True
    assert result["config_entry"]["version"] == 1
    assert result["config_entry"]["minor_version"] == 2
    assert result["config_entry"]["source"] == "user"
    assert result["config_entry"]["pref_disable_new_entities"] is False
    assert result["runtime"]["coordinator_available"] is True
    assert result["runtime"]["fan"] == {
        "native_mode_present": True,
        "coordinator_mode_present": True,
        "read_supported": True,
        "write_supported": False,
        "write_payload_hint": "profile_apply",
    }
    assert result["runtime"]["power"] == {"poweroff_permission_hint": "ok"}
    assert result["data_shape"]["storage"]["pool_count"] == 1
    assert result["privacy"]["raw_storage_payload_values_included"] is False
    assert result["privacy"]["snapshot_target_identifiers_aliased"] is True
    assert "entry_data" not in result
    assert "entry_options" not in result
    assert "storage_summary" not in result
    assert "native_fan_mode" not in result


def test_diagnostics_includes_safe_capability_flags() -> None:
    """Diagnostics should expose feature capability state without secrets."""
    result = asyncio.run(
        diagnostics_module.async_get_config_entry_diagnostics(
            _FakeHass(),
            _FakeEntry(),
        )
    )

    capabilities = result["capabilities"]
    assert capabilities == {
        "device_online": False,
        "last_update_success": True,
        "fan_control_enabled": True,
        "fan_mode_read_supported": True,
        "fan_mode_write_supported": False,
        "fan_mode_write_payload_hint": "profile_apply",
        "backup_tasks_read_supported": True,
        "backup_task_count": 1,
        "has_backup_tasks": True,
        "snapshot_buttons_enabled": True,
        "snapshot_settings_read_supported": True,
        "snapshot_settings_write_supported": None,
        "snapshot_settings_write_supported_by_type": {
            "mydrive": True,
            "shared": False,
        },
        "snapshot_create_supported": None,
        "snapshot_create_supported_by_type": {"shared": True},
        "snapshot_inventory_supported": True,
        "snapshot_inventory_supported_by_type": {
            "mydrive": False,
            "shared": True,
        },
        "snapshot_inventory_supported_by_target": {
            "mydrive_target_1": False,
            "shared_target_1": True,
        },
        "snapshot_target_count": 2,
        "snapshot_target_valid_count": 2,
        "snapshot_target_invalid_count": 0,
        "has_snapshot_targets": True,
        "snapshot_inventory_target_count": 1,
        "snapshot_inventory_error_count": 1,
        "snapshot_inventory_errors": {"mydrive_target_1": "unsupported"},
        "snapshot_inventory_skipped_target_count": 1,
        "snapshot_inventory_skip_reasons": {"mydrive_target_1": "unsupported"},
        "snapshot_missing_target_count": 1,
        "snapshot_missing_targets": {
            "shared_target_2": {
                "missing_count": 3,
                "target_type": "shared",
            }
        },
        "snapshot_target_types": ["mydrive", "shared"],
    }


def test_diagnostics_prefers_runtime_data_grouping() -> None:
    """Diagnostics should read coordinator runtime data from the config entry."""

    class _FakeRuntimeEntry(_FakeEntry):
        runtime_data = _FakeCoordinator()

    class _FakeHassWithoutDomainData(_FakeHass):
        data = {"unifi_unas": {}}

    result = asyncio.run(
        diagnostics_module.async_get_config_entry_diagnostics(
            _FakeHassWithoutDomainData(),
            _FakeRuntimeEntry(),
        )
    )

    assert result["runtime"]["coordinator_available"] is True
    assert result["capabilities"]["snapshot_target_valid_count"] == 2


def test_diagnostics_includes_monitoring_health_summary() -> None:
    """Diagnostics should expose compact monitoring health without identifiers."""
    result = asyncio.run(
        diagnostics_module.async_get_config_entry_diagnostics(
            _FakeHass(),
            _FakeEntry(),
        )
    )

    assert result["runtime"]["monitoring_health"] == {
        "payload_present": True,
        "device_online": False,
        "last_update_success": True,
        "offline_cached_payload": True,
        "system_status": None,
        "storage_status": "healthy",
        "pool_count": 1,
        "drive_count": 1,
        "degraded_pool_count": 0,
        "maintenance_pool_count": 0,
        "at_risk_disk_count": 0,
        "storage_problem": False,
        "maintenance_active": False,
        "capacity_metrics_available": True,
        "throughput_metrics_available": True,
        "throughput": {
            "read": {
                "selected_source": "storage",
                "selected_status": "non_zero",
                "storage_status": "non_zero",
                "network_io_present": False,
                "network_io_status": "missing",
            },
            "write": {
                "selected_source": "none",
                "selected_status": "missing",
                "storage_status": "missing",
                "network_io_present": False,
                "network_io_status": "missing",
            },
        },
        "monitoring_ready": True,
    }


def test_diagnostics_reports_network_io_throughput_source_without_values() -> None:
    """Diagnostics should expose throughput source status, not raw values."""
    storage = {
        "readThroughput": 0,
        "writeThroughput": 0,
        "_network_io": {
            "receiveKBPS": 2500,
            "transmitKBPS": 1500,
        },
    }

    assert diagnostics_module._throughput_diagnostics(storage) == {
        "read": {
            "selected_source": "network_io",
            "selected_status": "non_zero",
            "storage_status": "zero",
            "network_io_present": True,
            "network_io_status": "non_zero",
        },
        "write": {
            "selected_source": "network_io",
            "selected_status": "non_zero",
            "storage_status": "zero",
            "network_io_present": True,
            "network_io_status": "non_zero",
        },
    }


def test_diagnostics_includes_discovery_health_summary() -> None:
    """Diagnostics should expose discovery health without raw identity values."""
    result = asyncio.run(
        diagnostics_module.async_get_config_entry_diagnostics(
            _FakeHass(),
            _FakeEntry(),
        )
    )

    assert result["runtime"]["discovery"] == {
        "debug_enabled": True,
        "last_seen": "2026-05-19T12:00:00Z",
        "preferred_identity_source": "zeroconf_property_mac",
        "confidence": 65,
        "host_alias_count": 2,
        "mac_identity_present": True,
        "prompt_dedupe_ready": True,
        "restart_persistence_ready": True,
        "multi_interface_ready": True,
        "conflicting_identity_hint_count": 3,
        "conflicting_identity_hints": [
            "discovery_mac_wol_mac_mismatch",
            "unique_id_discovery_mac_mismatch",
            "zeroconf_mac_eui64_mismatch",
        ],
    }


def test_diagnostics_skips_invalid_snapshot_targets() -> None:
    """Diagnostics must tolerate malformed snapshot targets without failing."""
    coordinator = _FakeCoordinator()
    coordinator.snapshot_settings = [
        {"id": "shared-1", "name": "Shared", "type": "shared"},
        "invalid-target",
        None,
        123,
        {"id": "mydrive", "name": "My", "type": "mydrive"},
    ]

    class _FakeHassWithInvalidTargets(_FakeHass):
        data = {"unifi_unas": {"entry-1": coordinator}}

    result = asyncio.run(
        diagnostics_module.async_get_config_entry_diagnostics(
            _FakeHassWithInvalidTargets(),
            _FakeEntry(),
        )
    )

    capabilities = result["capabilities"]
    assert capabilities["snapshot_target_types"] == ["mydrive", "shared"]
    assert capabilities["snapshot_target_count"] == 5
    assert capabilities["snapshot_target_valid_count"] == 2
    assert capabilities["snapshot_target_invalid_count"] == 3
    assert capabilities["has_snapshot_targets"] is True
    assert capabilities["snapshot_inventory_supported_by_target"] == {
        "mydrive_target_1": False,
        "shared_target_1": True,
    }


def test_diagnostics_invalid_targets_mark_snapshot_targets_as_absent() -> None:
    """Has-targets reflects valid entries only when snapshot settings are malformed."""
    coordinator = _FakeCoordinator()
    coordinator.snapshot_settings = ["invalid-target", None, 123]

    class _FakeHassWithInvalidTargetsOnly(_FakeHass):
        data = {"unifi_unas": {"entry-1": coordinator}}

    result = asyncio.run(
        diagnostics_module.async_get_config_entry_diagnostics(
            _FakeHassWithInvalidTargetsOnly(),
            _FakeEntry(),
        )
    )

    capabilities = result["capabilities"]
    assert capabilities["snapshot_target_count"] == 3
    assert capabilities["snapshot_target_valid_count"] == 0
    assert capabilities["snapshot_target_invalid_count"] == 3
    assert capabilities["has_snapshot_targets"] is False
    assert capabilities["snapshot_target_types"] == []
    assert capabilities["snapshot_inventory_supported_by_target"] == {}


def test_diagnostics_storage_summary_redacts_payload_values() -> None:
    """Storage diagnostics should expose paths and shapes, not raw values."""
    summary = diagnostics_module._storage_summary(_FakeCoordinator.data)

    assert summary["pool_count"] == 1
    assert summary["disk_count"] == 1
    assert "serial" in summary["disk_sample_keys"]
    exported = json.dumps(summary, sort_keys=True)
    assert "Private Share" not in exported
    assert "private-share-throughput" not in exported
    assert "8ab16324-5061-469f-a37f-c50a24227ceb" not in exported
    assert "Private Top Level" not in exported
    assert "CustomerBackup" not in exported
    assert "CustomerStatus" not in exported
    assert all("secret" not in path for path in summary["candidate_field_paths"])
    assert "readThroughput=[redacted]" in summary["candidate_field_paths"]
    assert "shares.<key>=[complex]" in summary["candidate_field_paths"]
    assert "shares.<key>.status=[redacted]" in summary["candidate_field_paths"]
    assert summary["candidate_field_paths"].count(
        "shares.<key>.status=[redacted]"
    ) == 1
    assert "shares.<key>.readThroughput=[redacted]" in summary["candidate_field_paths"]
    assert "snapshotTargets.<key>.backupStatus=[redacted]" in summary[
        "candidate_field_paths"
    ]
    assert "<key>.status=[redacted]" in summary["candidate_field_paths"]
