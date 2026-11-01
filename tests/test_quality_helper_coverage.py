"""Additional helper tests to keep the CI coverage floor stable."""

from __future__ import annotations

from types import SimpleNamespace
import sys
import types

import pytest

from tests import module_stubs

module_stubs.install_package_stubs()
module_stubs.install_homeassistant_const_stub(
    CONF_HOST="host",
    CONF_PORT="port",
    DEFAULT_PORT=443,
)
module_stubs.load_const_module()
module_stubs.load_wake_on_lan_module()

homeassistant_pkg = sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
core_pkg = types.ModuleType("homeassistant.core")
core_pkg.HomeAssistant = object
sys.modules["homeassistant.core"] = core_pkg
homeassistant_pkg.core = core_pkg

config_entries_pkg = types.ModuleType("homeassistant.config_entries")
config_entries_pkg.ConfigEntry = object
sys.modules["homeassistant.config_entries"] = config_entries_pkg
homeassistant_pkg.config_entries = config_entries_pkg

config_flow_identity = module_stubs.load_integration_module("config_flow_identity")
discovery_common = module_stubs.load_integration_module("discovery_common")
runtime_module = module_stubs.load_integration_module("runtime")
snapshot_paths = module_stubs.load_integration_module("snapshot_paths")
snapshot_values = module_stubs.load_integration_module("snapshot_values")


class _EntryList:
    """Minimal config_entries manager double."""

    def __init__(self, entries: list[object]) -> None:
        self._entries = entries

    def async_entries(self, _domain: str) -> list[object]:
        return self._entries


def _entry(
    *,
    unique_id: str | None = "device-1",
    host: str = "unas.local",
    port: object = 443,
    state: object = "loaded",
    runtime_data: object | None = None,
) -> SimpleNamespace:
    """Build a lightweight config-entry-like object."""
    return SimpleNamespace(
        unique_id=unique_id,
        data={"host": host, "port": port},
        entry_id="entry-1",
        state=state,
        runtime_data=runtime_data,
    )


def test_entry_info_and_unique_id_matching_cover_dedupe_and_empty_values() -> None:
    """Entry identity helpers should normalize and deduplicate IDs."""
    info = config_flow_identity._entry_info(
        {"host": "UNAS.LOCAL", "port": "443"},
        unique_id="device-1",
        unique_ids=("device-1", "legacy-1", "", None),
        device_scoped_unique_ids=("device-1", "", None),
    )
    assert info["title"] == "UniFi Drive (UNAS.LOCAL)"
    assert info["unique_ids"] == ("device-1", "legacy-1")
    assert info["device_scoped_unique_ids"] == ("device-1",)
    assert info["host"] == "unas.local"
    assert info["port"] == 443

    assert config_flow_identity._entry_unique_id_matches(None, info) is False
    assert config_flow_identity._entry_unique_id_matches("", info) is False
    assert config_flow_identity._entry_unique_id_matches("device-1", info) is True
    assert config_flow_identity._entry_unique_id_matches("legacy-1", info) is False


def test_entry_device_match_helper_uses_current_and_connection_fallback_ids() -> None:
    """Identity matching should accept device IDs and host:port fallbacks."""
    info = config_flow_identity._entry_info(
        {"host": "unas.local", "port": 443},
        unique_id="device-1",
        unique_ids=("device-1", "legacy-1"),
        device_scoped_unique_ids=("device-1",),
    )

    assert (
        config_flow_identity._entry_matches_validated_device(
            _entry(unique_id="device-1"),
            info,
        )
        is True
    )
    assert (
        config_flow_identity._entry_matches_validated_device(
            _entry(unique_id="legacy-1"),
            info,
        )
        is False
    )
    assert (
        config_flow_identity._entry_matches_validated_device(
            _entry(unique_id="UNAS.LOCAL:443"),
            info,
        )
        is True
    )
    assert (
        config_flow_identity._entry_matches_validated_device(
            _entry(unique_id="other", host="unas.local", port=443),
            info,
        )
        is False
    )
    assert (
        config_flow_identity._entry_matches_validated_device(
            _entry(unique_id="UNAS.LOCAL:443", host=""),
            info,
        )
        is False
    )


def test_offline_reconfigure_guard_and_unique_id_lookup_helpers() -> None:
    """Feature-only reconfigure should guard offline reloads without WOL."""
    entry = _entry(state=SimpleNamespace(value="setup_error"))

    # WOL enabled with MAC always bypasses the offline guard.
    assert (
        config_flow_identity._feature_reconfigure_would_reload_offline_without_wol(
            SimpleNamespace(data={}),
            entry,
            {"wol_enabled": True, "wol_mac_address": "aa:bb:cc:dd:ee:ff"},
        )
        is False
    )

    # Invalid hass.data/domain data shape should fail safe and avoid false warnings.
    assert (
        config_flow_identity._feature_reconfigure_would_reload_offline_without_wol(
            SimpleNamespace(data=[]),
            entry,
            {},
        )
        is False
    )
    assert (
        config_flow_identity._feature_reconfigure_would_reload_offline_without_wol(
            SimpleNamespace(data={config_flow_identity.DOMAIN: "bad"}),
            entry,
            {},
        )
        is False
    )

    # Without runtime coordinator, setup error/retry state should be treated as offline.
    assert (
        config_flow_identity._feature_reconfigure_would_reload_offline_without_wol(
            SimpleNamespace(data={}),
            entry,
            {},
        )
        is True
    )

    coordinator = SimpleNamespace(is_device_online=False)
    entry.runtime_data = coordinator
    assert (
        config_flow_identity._feature_reconfigure_would_reload_offline_without_wol(
            SimpleNamespace(data={config_flow_identity.DOMAIN: {entry.entry_id: coordinator}}),
            entry,
            {},
        )
        is True
    )

    matching_entry = _entry(unique_id="device-1", host="unas.local", port=443)
    hass = SimpleNamespace(config_entries=_EntryList([matching_entry]))
    info = config_flow_identity._entry_info(
        {"host": "unas.local", "port": 443},
        unique_id="device-1",
        unique_ids=("device-1", "legacy-1"),
        device_scoped_unique_ids=("device-1",),
    )
    assert config_flow_identity._any_unique_id_configured(hass, info) is True

    legacy_entry = _entry(unique_id="UNAS.LOCAL:443", host="unas.local", port=443)
    legacy_hass = SimpleNamespace(config_entries=_EntryList([legacy_entry]))
    assert config_flow_identity._any_unique_id_configured(legacy_hass, info) is True


def test_runtime_discovery_and_snapshot_value_helpers_cover_edge_shapes() -> None:
    """Low-level helper functions should gracefully handle malformed input."""
    assert runtime_module.coordinator_from_entry_or_none(None) is None
    assert runtime_module.coordinator_from_entry_or_none(
        SimpleNamespace(runtime_data="invalid")
    ) is None
    looks_like = SimpleNamespace(
        client=object(),
        data={},
        is_device_online=True,
        last_update_success=True,
    )
    assert runtime_module.coordinator_from_entry_or_none(
        SimpleNamespace(runtime_data=looks_like)
    ) is looks_like

    assert discovery_common.parse_bool("Enabled") is True
    assert discovery_common.parse_bool("disabled") is False
    assert discovery_common.parse_bool("maybe") is None
    assert (
        discovery_common.mac_from_eui64_ipv6("[fe80::0211:22ff:fe33:4455%eth0]")
        == "00:11:22:33:44:55"
    )
    assert discovery_common.mac_from_eui64_ipv6("not-an-ip") is None
    assert discovery_common.mac_from_eui64_ipv6("2001:db8::1") is None

    assert snapshot_values._value_from_dict("not-a-dict", ("id",)) is None
    assert snapshot_values._int_value(True) is None
    assert snapshot_values._int_value("42") == 42
    assert snapshot_values._int_value("bad") is None
    assert snapshot_values._bool_value(0) is False
    assert snapshot_values._bool_value("enabled") is True
    assert snapshot_values._bool_value("disabled") is False
    assert snapshot_values._bool_value("unknown") is None
    assert snapshot_values._payload_debug_shape(["bad"]) == "list"
    assert snapshot_values._payload_debug_shape({"data": [1, 2]}) == {
        "top_level_count": 1,
        "data_type": "list",
        "data_count": 2,
    }
    assert snapshot_values._payload_debug_shape({"data": {"Example Private Share": []}}) == {
        "top_level_count": 1, "data_type": "dict", "data_count": 1,
    }


def test_snapshot_path_helpers_reject_unsupported_or_missing_targets() -> None:
    """Snapshot path helpers should reject missing IDs and unknown target types."""
    with pytest.raises(snapshot_paths.UnexpectedResponse, match="type is missing"):
        snapshot_paths._snapshot_settings_write_paths({"id": "x"})

    with pytest.raises(snapshot_paths.UnexpectedResponse, match="id is missing"):
        snapshot_paths._snapshot_settings_write_paths({"type": "shared"})

    assert snapshot_paths._snapshot_settings_write_paths(
        {"type": "shared", "id": "share-1", "shared_drive_name": "family"}
    ) == (
        "/proxy/drive/api/v1/snapshot-settings/shared/family",
        "/proxy/drive/api/v1/snapshot-settings/shared/share-1",
    )

    with pytest.raises(snapshot_paths.UnexpectedResponse, match="id is missing"):
        snapshot_paths._snapshot_create_paths({"type": "shared"})

    with pytest.raises(snapshot_paths.UnexpectedResponse, match="id is missing"):
        snapshot_paths._snapshot_create_paths({"type": "mydrive"})

    with pytest.raises(snapshot_paths.UnexpectedResponse, match="Unsupported snapshot"):
        snapshot_paths._snapshot_create_paths({"type": "unknown", "id": "x"})
