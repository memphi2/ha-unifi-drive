"""Unit tests for snapshot entity helpers."""

from __future__ import annotations

import asyncio
from enum import Enum
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
import types


def _load_snapshot_entities_module():
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

    core_pkg = types.ModuleType("homeassistant.core")
    core_pkg.HomeAssistant = object
    sys.modules["homeassistant.core"] = core_pkg

    config_entries_pkg = types.ModuleType("homeassistant.config_entries")
    config_entries_pkg.ConfigEntry = object
    sys.modules["homeassistant.config_entries"] = config_entries_pkg

    const_pkg = types.ModuleType("homeassistant.const")

    class EntityCategory(str, Enum):
        CONFIG = "config"

    class Platform(str, Enum):
        BINARY_SENSOR = "binary_sensor"
        BUTTON = "button"
        NUMBER = "number"
        SELECT = "select"
        SENSOR = "sensor"
        SWITCH = "switch"
        TIME = "time"
        UPDATE = "update"

    const_pkg.EntityCategory = EntityCategory
    const_pkg.Platform = Platform
    sys.modules["homeassistant.const"] = const_pkg

    exceptions_pkg = types.ModuleType("homeassistant.exceptions")

    class HomeAssistantError(Exception):
        """Base Home Assistant error stub."""

    class ServiceValidationError(HomeAssistantError):
        """Service validation error stub."""

    exceptions_pkg.HomeAssistantError = HomeAssistantError
    exceptions_pkg.ServiceValidationError = ServiceValidationError
    sys.modules["homeassistant.exceptions"] = exceptions_pkg

    helpers_pkg = types.ModuleType("homeassistant.helpers")
    sys.modules["homeassistant.helpers"] = helpers_pkg

    issue_registry_pkg = types.ModuleType("homeassistant.helpers.issue_registry")
    issue_registry_pkg.IssueSeverity = types.SimpleNamespace(WARNING="warning")
    issue_registry_pkg.async_create_issue = lambda *args, **kwargs: None
    issue_registry_pkg.async_delete_issue = lambda *args, **kwargs: None
    sys.modules["homeassistant.helpers.issue_registry"] = issue_registry_pkg

    entity_platform_pkg = types.ModuleType("homeassistant.helpers.entity_platform")
    entity_platform_pkg.AddEntitiesCallback = object
    sys.modules["homeassistant.helpers.entity_platform"] = entity_platform_pkg

    update_coordinator_pkg = types.ModuleType("homeassistant.helpers.update_coordinator")

    class CoordinatorEntity:
        @classmethod
        def __class_getitem__(cls, item):
            return cls

        def __init__(self, coordinator) -> None:
            self.coordinator = coordinator

        @property
        def available(self) -> bool:
            return True

    update_coordinator_pkg.CoordinatorEntity = CoordinatorEntity
    sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator_pkg

    api_pkg = types.ModuleType("custom_components.unifi_unas.api")
    api_pkg.CannotConnect = Exception
    api_pkg.InvalidAuth = Exception
    api_pkg.UnexpectedResponse = Exception
    api_pkg.UnsupportedFeature = Exception
    sys.modules["custom_components.unifi_unas.api"] = api_pkg

    coordinator_pkg = types.ModuleType("custom_components.unifi_unas.coordinator")
    coordinator_pkg.UnifiUnasCoordinator = object
    sys.modules["custom_components.unifi_unas.coordinator"] = coordinator_pkg

    device_pkg = types.ModuleType("custom_components.unifi_unas.device")
    device_pkg.build_device_info = lambda *args, **kwargs: {}
    sys.modules["custom_components.unifi_unas.device"] = device_pkg

    snapshot_spec = spec_from_file_location(
        "custom_components.unifi_unas.snapshot_entities",
        package_root / "snapshot_entities.py",
    )
    if snapshot_spec is None or snapshot_spec.loader is None:
        raise RuntimeError("Could not load snapshot_entities module spec")
    snapshot_module = module_from_spec(snapshot_spec)
    sys.modules["custom_components.unifi_unas.snapshot_entities"] = snapshot_module
    snapshot_spec.loader.exec_module(snapshot_module)
    return snapshot_module


snapshot_entities_module = _load_snapshot_entities_module()
snapshot_types_module = sys.modules["custom_components.unifi_unas.snapshot_types"]


def _load_switch_module():
    root = Path(__file__).resolve().parents[1]
    package_root = root / "custom_components" / "unifi_unas"

    components_pkg = types.ModuleType("homeassistant.components")
    sys.modules["homeassistant.components"] = components_pkg

    switch_pkg = types.ModuleType("homeassistant.components.switch")

    class SwitchEntity:
        """Switch entity stub."""

    switch_pkg.SwitchEntity = SwitchEntity
    sys.modules["homeassistant.components.switch"] = switch_pkg

    core_pkg = types.ModuleType("homeassistant.core")
    core_pkg.HomeAssistant = object
    sys.modules["homeassistant.core"] = core_pkg

    const_pkg = types.ModuleType("custom_components.unifi_unas.const")
    const_pkg.CONF_SNAPSHOT_BUTTONS_ENABLED = "snapshot_buttons_enabled"
    const_pkg.DEFAULT_SNAPSHOT_BUTTONS_ENABLED = True
    const_pkg.DOMAIN = "unifi_unas"
    sys.modules["custom_components.unifi_unas.const"] = const_pkg

    switch_spec = spec_from_file_location(
        "custom_components.unifi_unas.switch",
        package_root / "switch.py",
    )
    if switch_spec is None or switch_spec.loader is None:
        raise RuntimeError("Could not load switch module spec")
    switch_module = module_from_spec(switch_spec)
    sys.modules["custom_components.unifi_unas.switch"] = switch_module
    switch_spec.loader.exec_module(switch_module)
    return switch_module


switch_module = _load_switch_module()


class _FakeEntry:
    data = {"snapshot_buttons_enabled": True}
    entry_id = "entry-1"
    unique_id = "device-1"

    def async_on_unload(self, _unsub) -> None:
        """Accept listener cleanup registration like Home Assistant entries do."""


def test_async_track_snapshot_target_entities_adds_new_targets_once() -> None:
    """Dynamic snapshot entity factories should run once per stable target."""
    added: list[str] = []
    listeners = []
    coordinator = types.SimpleNamespace(
        snapshot_settings=[{"type": "shared", "id": "shared-1"}],
        async_add_listener=lambda listener: listeners.append(listener),
    )

    snapshot_entities_module.async_track_snapshot_target_entities(
        _FakeEntry(),
        coordinator,
        lambda entities: added.extend(entities),
        lambda target: (target["id"],),
    )

    assert added == ["shared-1"]
    assert len(listeners) == 1

    listeners[0]()
    assert added == ["shared-1"]

    coordinator.snapshot_settings.append({"type": "mydrive", "id": "user-1"})
    listeners[0]()
    assert added == ["shared-1", "user-1"]


def test_snapshot_target_entity_registry_is_cleared_on_unload() -> None:
    """Unloading snapshot targets should clear cached entity buckets immediately."""
    coordinator = types.SimpleNamespace(
        snapshot_settings=[{"type": "shared", "id": "shared-1"}],
        async_add_listener=lambda listener: None,
    )
    target = {
        "type": "shared",
        "id": "shared-1",
        "name": "Shared",
    }
    snapshot_entities_module.UnifiUnasSnapshotTargetEntity(
        coordinator,
        _FakeEntry(),
        target,
        entity_key="enabled",
        icon="mdi:camera-switch",
    )

    coordinator_key = id(coordinator)
    assert coordinator_key in snapshot_entities_module._SNAPSHOT_TARGET_ENTITIES_BY_ID

    snapshot_entities_module._clear_snapshot_target_entities_for_coordinator(coordinator)
    assert coordinator_key not in snapshot_entities_module._SNAPSHOT_TARGET_ENTITIES_BY_ID


def test_snapshot_target_entity_tracks_missing_target_lifecycle() -> None:
    """Missing snapshot targets should be counted and repaired without deletion."""
    repair_calls: list[dict] = []
    clear_calls: list[dict] = []
    original_repair = snapshot_entities_module.async_update_snapshot_target_missing_issue
    original_clear = snapshot_entities_module.async_clear_snapshot_target_missing_issue
    snapshot_entities_module.async_update_snapshot_target_missing_issue = (
        lambda *args, **kwargs: repair_calls.append(kwargs)
    )
    snapshot_entities_module.async_clear_snapshot_target_missing_issue = (
        lambda *args, **kwargs: clear_calls.append(kwargs)
    )
    target = {"type": "shared", "id": "shared-1", "name": "Shared"}
    coordinator = types.SimpleNamespace(
        hass=object(),
        snapshot_settings=[target],
        async_add_listener=lambda listener: None,
    )

    try:
        entity = snapshot_entities_module.UnifiUnasSnapshotTargetEntity(
            coordinator,
            _FakeEntry(),
            target,
            entity_key="enabled",
            icon="mdi:camera-switch",
        )

        missing_snapshots = []
        coordinator.snapshot_settings_available = False
        for _ in range(3):
            coordinator.snapshot_settings = []
            snapshot_entities_module._update_snapshot_target_missing_state(coordinator, _FakeEntry())
        assert entity._snapshot_target_missing_count == 0
        assert repair_calls == []
        coordinator.snapshot_settings_available = True
        for expected_count in (1, 2, 3):
            snapshot_settings = []
            missing_snapshots.append(snapshot_settings)
            coordinator.snapshot_settings = snapshot_settings
            snapshot_entities_module._update_snapshot_target_missing_state(
                coordinator,
                _FakeEntry(),
            )
            attrs = entity.extra_state_attributes
            assert attrs["snapshot_target_present"] is False
            assert attrs["snapshot_target_missing_count"] == expected_count
            assert repair_calls[-1]["missing_count"] == expected_count

        assert coordinator.snapshot_target_missing_counts == {
            "shared_shared-1": {
                "missing_count": 3,
                "target_name": "Shared",
                "target_type": "shared",
            }
        }

        coordinator.snapshot_settings = [target]
        snapshot_entities_module._update_snapshot_target_missing_state(
            coordinator,
            _FakeEntry(),
        )

        assert clear_calls[-1]["target_key"] == "shared_shared-1"
        assert entity.extra_state_attributes["snapshot_target_missing_count"] == 0
        assert coordinator.snapshot_target_missing_counts == {}
    finally:
        snapshot_entities_module.async_update_snapshot_target_missing_issue = (
            original_repair
        )
        snapshot_entities_module.async_clear_snapshot_target_missing_issue = (
            original_clear
        )


def test_snapshot_target_key_normalizes_type_aliases() -> None:
    """Entity keys should not drift when UniFi exposes equivalent target aliases."""
    assert (
        snapshot_types_module.snapshot_target_key(
            {"type": "personal", "id": "user-1"}
        )
        == "mydrive_user-1"
    )
    assert (
        snapshot_types_module.snapshot_target_key(
            {"type": "shared_drive", "id": "shared-1"}
        )
        == "shared_shared-1"
    )


def test_snapshot_target_name_prefers_alias_fields() -> None:
    """Fallback name resolution should prefer stable alias fields."""
    assert snapshot_types_module.snapshot_target_name(
        {"type": "shared", "id": "shared-1", "name": "Main", "display_name": "ignored"}
    ) == "Main"
    assert snapshot_types_module.snapshot_target_name(
        {"type": "shared", "id": "shared-1", "display_name": "Display"}
    ) == "Display"
    assert snapshot_types_module.snapshot_target_name(
        {"type": "mydrive", "id": "user-1", "shared_drive_name": "Drive"}
    ) == "Drive"
    assert snapshot_types_module.snapshot_target_name(
        {"type": "mydrive", "id": "user-1", "user_name": "Alice"}
    ) == "Alice"
    assert snapshot_types_module.snapshot_target_name(
        {"type": "shared", "id": "shared-1"}
    ) == "shared-1"


def test_snapshot_target_key_and_name_are_safe_on_invalid_input() -> None:
    """Non-mapping snapshot targets must not crash the normalizers."""
    assert snapshot_types_module.snapshot_target_type(None) == ""
    assert snapshot_types_module.snapshot_target_key(None) == ""
    assert snapshot_types_module.snapshot_target_name(None) == "Snapshot Target"


def test_snapshot_switch_setup_adds_only_enable_switch_per_target() -> None:
    """Snapshot switches should not create per-day registry entries."""
    target = {
        "type": "shared",
        "id": "shared-1",
        "name": "Shared",
        "enabled": True,
    }
    listeners = []
    coordinator = types.SimpleNamespace(
        is_device_online=True,
        snapshot_settings=[target],
        async_add_listener=lambda listener: listeners.append(listener),
    )
    hass = types.SimpleNamespace(
        data={"unifi_unas": {_FakeEntry.entry_id: coordinator}},
    )
    entry = _FakeEntry()
    entry.runtime_data = coordinator
    added: list[object] = []

    asyncio.run(
        switch_module.async_setup_entry(
            hass,
            entry,
            lambda entities: added.extend(entities),
        )
    )

    assert [entity.__class__.__name__ for entity in added] == [
        "UnifiUnasSnapshotEnabledSwitch"
    ]
    assert added[0]._attr_unique_id == "device-1_snapshot_shared_shared_1_enabled"
    assert len(listeners) == 1


def test_async_track_snapshot_target_entities_with_missing_snapshot_settings() -> None:
    """Missing snapshot_settings should not break entity tracking."""
    added: list[str] = []
    listeners = []
    coordinator = types.SimpleNamespace(
        async_add_listener=lambda listener: listeners.append(listener),
    )

    snapshot_entities_module.async_track_snapshot_target_entities(
        _FakeEntry(),
        coordinator,
        lambda entities: added.extend(entities),
        lambda target: (target["id"],),
    )

    assert added == []
    assert len(listeners) == 1

    listeners[0]()
    assert added == []


def test_async_track_snapshot_target_entities_skips_invalid_targets_for_filter() -> None:
    """Invalid snapshot targets should be skipped before applying filters."""
    added: list[str] = []
    listeners: list = []
    calls: list[dict[str, str]] = []

    coordinator = types.SimpleNamespace(
        snapshot_settings=[
            None,
            123,
            "bad",
            ["not", "a", "mapping"],
            {"type": "shared", "id": "shared-1"},
        ],
        async_add_listener=lambda listener: listeners.append(listener),
    )

    def _factory(target: dict[str, str]) -> tuple[str]:
        calls.append(target)
        return (target["id"],)

    snapshot_entities_module.async_track_snapshot_target_entities(
        _FakeEntry(),
        coordinator,
        lambda entities: added.extend(entities),
        _factory,
        target_filter=lambda target: target.get("type") == "shared",
    )

    assert added == ["shared-1"]
    assert calls == [{"type": "shared", "id": "shared-1"}]

    listeners[0]()
    assert added == ["shared-1"]


def test_snapshot_create_button_filter_hides_foreign_personal_targets() -> None:
    """Foreign personal snapshot targets should not get create buttons."""
    assert snapshot_types_module.snapshot_create_button_supported(
        {"type": "shared", "id": "shared-1"}
    )
    assert snapshot_types_module.snapshot_create_button_supported(
        {"type": "shared_drive", "id": "shared-1"}
    )
    assert snapshot_types_module.snapshot_create_button_supported(
        {"type": "mydrive", "id": "current-user", "is_current_user": True}
    )
    assert not snapshot_types_module.snapshot_create_button_supported(
        {"type": "personal", "id": "backup-user", "is_current_user": False}
    )
    assert not snapshot_types_module.snapshot_create_button_supported(
        {"type": "mydrive", "id": "backup-user"}
    )
    assert snapshot_types_module.snapshot_create_button_supported(
        {"type": "mydrive", "id": "api-key-user", "is_current_user": False},
        preserve_inventory_unknown=True,
    )
    assert snapshot_types_module.snapshot_create_button_supported(
        {"type": "mydrive", "id": "api-key-user", "is_current_user": False},
        inventory_available=True,
    )
    assert not snapshot_types_module.snapshot_create_button_supported(
        {"type": "mydrive", "id": "backup-user", "is_current_user": False},
        inventory_error_reason="unsupported",
        preserve_inventory_unknown=True,
    )


def test_snapshot_create_button_filter_uses_inventory_context() -> None:
    """Inventory context should keep button decisions consistent across callers."""
    target = {"type": "mydrive", "id": "api-key-user", "is_current_user": False}

    assert snapshot_types_module.snapshot_create_button_supported_for_inventory(target)
    assert snapshot_types_module.snapshot_create_button_supported_for_inventory(
        target,
        snapshot_inventory={"mydrive_api-key-user": {"snapshot_count": 1}},
    )
    assert not snapshot_types_module.snapshot_create_button_supported_for_inventory(
        target,
        snapshot_inventory_errors={"mydrive_api-key-user": "permission"},
    )
    assert not snapshot_types_module.snapshot_create_button_supported_for_inventory(
        {"type": "mydrive"},
    )


def test_snapshot_entity_blocks_writes_while_offline() -> None:
    """Snapshot entities should reject writes while keeping metadata inspectable."""
    target = {
        "type": "shared",
        "id": "shared-1",
        "name": "Shared",
        "enabled": True,
    }
    coordinator = types.SimpleNamespace(
        is_device_online=False,
        snapshot_settings=[target],
    )
    entity = snapshot_entities_module.UnifiUnasSnapshotTargetEntity(
        coordinator,
        _FakeEntry(),
        target,
        entity_key="enabled",
        icon="mdi:camera-switch",
    )

    assert entity.available is False
    assert entity.extra_state_attributes["snapshot_target_present"] is True

    try:
        entity._validated_target("change snapshot settings")
    except Exception as err:  # noqa: BLE001 - lightweight HA exception stub
        assert "offline" in str(err)
        assert err.translation_key == "device_offline"
    else:
        raise AssertionError("offline snapshot writes should fail")


def test_snapshot_entity_with_invalid_target_key_has_absent_state() -> None:
    """Entity created from malformed target keeps a safe unavailable state."""
    coordinator = types.SimpleNamespace(
        is_device_online=True,
        snapshot_settings=[],
    )
    entity = snapshot_entities_module.UnifiUnasSnapshotTargetEntity(
        coordinator,
        _FakeEntry(),
        {},
        entity_key="enabled",
        icon="mdi:camera-switch",
    )

    assert entity.extra_state_attributes["snapshot_target_present"] is False
    assert entity._current_target() is None


def test_snapshot_entity_current_target_skips_invalid_snapshot_settings_entries() -> None:
    """Current-target lookup should ignore malformed entries and still find valid ones."""
    coordinator = types.SimpleNamespace(
        is_device_online=True,
        snapshot_settings=[
            None,
            "bad",
            ["list", "entry"],
            {"type": "shared", "id": "shared-1", "enabled": False},
        ],
    )
    entity = snapshot_entities_module.UnifiUnasSnapshotTargetEntity(
        coordinator,
        _FakeEntry(),
        {"type": "shared", "id": "shared-1", "name": "Shared"},
        entity_key="enabled",
        icon="mdi:camera-switch",
    )

    assert entity._current_target() == {
        "type": "shared",
        "id": "shared-1",
        "enabled": False,
    }
    assert entity.extra_state_attributes["snapshot_target_present"] is True
