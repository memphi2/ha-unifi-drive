"""Integration-level state tests for snapshot control entities."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from tests.ha_test_helpers import (
    ROOT,
    ensure_repo_custom_components_path as _ensure_repo_custom_components_path,
)

try:
    from homeassistant.const import (
        CONF_HOST,
        CONF_PASSWORD,
        CONF_PORT,
        CONF_SCAN_INTERVAL,
        CONF_SSL,
        CONF_USERNAME,
        CONF_VERIFY_SSL,
    )
except (ImportError, AttributeError):
    # Some environments expose a stubbed/partial homeassistant.const module.
    CONF_HOST = "host"
    CONF_PASSWORD = "password"
    CONF_PORT = "port"
    CONF_SCAN_INTERVAL = "scan_interval"
    CONF_SSL = "ssl"
    CONF_USERNAME = "username"
    CONF_VERIFY_SSL = "verify_ssl"


@pytest.fixture
def hass_config_dir() -> str:
    """Point Home Assistant at this repository's test config directory."""
    return str(ROOT)


def _entry_data(
    *,
    snapshot_buttons: bool = True,
    fan_control: bool = False,
) -> dict[str, Any]:
    """Build minimal config entry data with optional snapshot controls."""
    _ensure_repo_custom_components_path()
    from custom_components.unifi_unas.const import (
        CONF_FAN_CONTROL_ENABLED,
        DEFAULT_PORT,
        DEFAULT_SCAN_INTERVAL,
        DEFAULT_SSL,
        DEFAULT_VERIFY_SSL,
        CONF_SNAPSHOT_BUTTONS_ENABLED,
    )

    return {
        CONF_HOST: "unas.local",
        CONF_PORT: DEFAULT_PORT,
        CONF_SSL: DEFAULT_SSL,
        CONF_VERIFY_SSL: DEFAULT_VERIFY_SSL,
        CONF_USERNAME: "test-user",
        CONF_PASSWORD: "test-pass",
        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
        CONF_FAN_CONTROL_ENABLED: fan_control,
        CONF_SNAPSHOT_BUTTONS_ENABLED: snapshot_buttons,
    }


def _snapshot_target_with_controls() -> dict[str, Any]:
    """Return a realistic shared snapshot target with all control options."""
    return {
        "type": "shared",
        "id": "shared-1",
        "name": "Team Drive",
        "enabled": True,
        "max_count": 12,
        "total_count": 4,
        "locked_count": 0,
        "schedule_enabled": True,
        "schedule_frequency": "Daily",
        "schedule_time": "08:15",
        "schedule_weekdays": "1,2",
        "schedule_monthdays": "15",
        "paused": False,
        "restoring_drive": False,
    }


async def _async_setup_entry_with_snapshot_controls(hass, client):
    """Patch network calls and initialize the integration for snapshot controls."""
    from homeassistant.setup import async_setup_component
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.unifi_unas.const import DOMAIN
    _ensure_repo_custom_components_path()

    assert await async_setup_component(hass, DOMAIN, {})
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="UNAS",
        unique_id="device-1",
        data=_entry_data(snapshot_buttons=True),
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.unifi_unas.async_create_clientsession",
            return_value=object(),
        ),
        patch(
            "custom_components.unifi_unas.UnifiUnasApiClient",
            return_value=client,
        ),
    ):
        # Keep test wiring deterministic while keeping integration setup paths.
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


def _snapshot_entity_ids_by_unique_id(hass, config_entry):
    """Index snapshot entity IDs by their unique IDs."""
    from homeassistant.helpers import entity_registry as er

    entries = er.async_entries_for_config_entry(
        er.async_get(hass),
        config_entry.entry_id,
    )

    return {
        entry.unique_id: entry.entity_id
        for entry in entries
        if entry.unique_id is not None and entry.unique_id.startswith(
            f"{config_entry.unique_id}_snapshot_"
        )
    }


def _snapshot_unique_ids(target: dict[str, Any], device_id: str) -> dict[str, str]:
    """Return expected unique IDs for one snapshot target."""
    _ensure_repo_custom_components_path()
    from custom_components.unifi_unas.snapshot_types import (
        snapshot_target_key,
        snapshot_target_slug,
    )

    base = f"{device_id}_snapshot_{snapshot_target_slug(snapshot_target_key(target))}"
    return {
        "button": base,
        "switch": f"{base}_enabled",
        "limit": f"{base}_limit",
        "schedule": f"{base}_schedule",
        "weekday": f"{base}_weekday",
        "month_day": f"{base}_month_day",
        "schedule_time": f"{base}_schedule_time",
    }


def _snapshot_entity_ids_for_target(
    hass,
    entry,
) -> dict[str, str]:
    """Resolve stable snapshot entity IDs for one config entry."""
    registry_ids = _snapshot_entity_ids_by_unique_id(hass, entry)
    target = _snapshot_target_with_controls()
    expected_ids = _snapshot_unique_ids(target, entry.unique_id)
    return {name: registry_ids[uid] for name, uid in expected_ids.items()}


async def _setup_snapshot_controls(
    hass,
    client,
) -> tuple[Any, dict[str, str]]:
    """Set up snapshot controls and return entry plus entity IDs."""
    entry = await _async_setup_entry_with_snapshot_controls(hass, client)
    return entry, _snapshot_entity_ids_for_target(hass, entry)


class _SnapshotIntegrationClient:
    """Fake API client that tracks calls and updates snapshot settings in-memory."""

    snapshot_settings_read_supported = True
    native_fan_mode = "Balance"
    poweroff_permission_hint = None

    def __init__(self, targets: list[dict[str, Any]]) -> None:
        self.snapshot_settings = list(targets)
        self.updated: list[tuple[str, dict[str, Any]]] = []
        self.created: list[dict[str, Any]] = []
        self.inventory_requests: list[str] = []
        self.fail_next: Exception | None = None

    async def _maybe_fail(self) -> None:
        if self.fail_next is not None:
            err = self.fail_next
            self.fail_next = None
            raise err

    async def async_get_storage(self) -> dict[str, Any]:
        return {"_system": {"status": "online"}}

    async def async_get_backup_tasks(self) -> list[dict[str, Any]]:
        return []

    async def async_get_snapshot_settings(self) -> list[dict[str, Any]]:
        return self.snapshot_settings

    async def async_get_snapshot_inventory_target(
        self,
        target: dict[str, Any],
    ) -> dict[str, Any]:
        """Return static inventory metadata for shared targets."""
        from custom_components.unifi_unas.snapshot_types import snapshot_target_key

        self.inventory_requests.append(snapshot_target_key(target))
        return {"recent_snapshot_count": 0}

    async def async_update_snapshot_target_settings(
        self,
        target: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        """Mutate the tracked snapshot target and record the settings payload."""
        from custom_components.unifi_unas.snapshot_types import snapshot_target_key

        await self._maybe_fail()
        target_key = snapshot_target_key(target)
        for candidate in self.snapshot_settings:
            if snapshot_target_key(candidate) == target_key:
                for key, value in kwargs.items():
                    if value is not None:
                        candidate[key] = value
                break
        self.updated.append((target_key, {k: v for k, v in kwargs.items() if v is not None}))

    async def async_create_snapshot_target(
        self,
        target: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        """Record create-snapshot actions."""
        from custom_components.unifi_unas.snapshot_types import snapshot_target_key

        await self._maybe_fail()
        payload = {"target_key": snapshot_target_key(target), **kwargs}
        self.created.append(payload)


@pytest.mark.asyncio
@pytest.mark.parametrize("language,suffix", [("en", "Snapshot limit"), ("de", "Snapshot-Limit")])
async def test_snapshot_names_use_translations_and_preserve_registry_identity(hass, language, suffix):
    """Target names are placeholders, while the control label is translated."""
    from homeassistant.helpers import entity_registry as er

    hass.config.language = language
    client = _SnapshotIntegrationClient([_snapshot_target_with_controls()])
    entry, controls = await _setup_snapshot_controls(hass, client)
    entity_id = controls["limit"]
    assert hass.states.get(entity_id).attributes["friendly_name"] == f"UNAS Team Drive {suffix}"
    registry_entry = er.async_get(hass).async_get(entity_id)
    assert registry_entry.unique_id == _snapshot_unique_ids(client.snapshot_settings[0], entry.unique_id)["limit"]
    er.async_get(hass).async_update_entity(entity_id, name="Custom retention")
    entry.runtime_data.async_set_updated_data(entry.runtime_data.data)
    await hass.async_block_till_done()
    assert er.async_get(hass).async_get(entity_id).name == "Custom retention"


@pytest.mark.asyncio
async def test_control_recorder_attributes_stay_stable_during_snapshot_count_changes(hass) -> None:
    """Counter churn stays visible live without new control attribute blobs."""
    from homeassistant.components.recorder.db_schema import StateAttributes
    from homeassistant.const import EVENT_STATE_CHANGED
    from homeassistant.core import Event

    target = _snapshot_target_with_controls()
    client = _SnapshotIntegrationClient([target])
    entry, controls = await _setup_snapshot_controls(hass, client)

    def recorded(entity_id):
        return StateAttributes.shared_attrs_bytes_from_event(
            Event(EVENT_STATE_CHANGED, {
                "entity_id": entity_id, "old_state": None,
                "new_state": hass.states.get(entity_id),
            }), None,
        )

    before = {entity_id: recorded(entity_id) for entity_id in controls.values()}
    for count in range(5, 25):
        target.update(total_count=count, locked_count=count - 5)
        entry.runtime_data.async_set_updated_data(entry.runtime_data.data)
        await hass.async_block_till_done()
        for entity_id in controls.values():
            assert hass.states.get(entity_id).attributes["total_count"] == count
            assert recorded(entity_id) == before[entity_id]
    await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.asyncio
async def test_snapshot_recorder_omits_preview_but_keeps_live_attributes(hass) -> None:
    """Real HA states retain previews while recorder serializes only useful history."""
    import json

    from homeassistant.components.recorder.db_schema import StateAttributes
    from homeassistant.const import EVENT_STATE_CHANGED
    from homeassistant.core import Event

    from custom_components.unifi_unas.snapshot_types import snapshot_target_key

    target = _snapshot_target_with_controls()
    client = _SnapshotIntegrationClient([target])
    entry, _ = await _setup_snapshot_controls(hass, client)
    entity_id = next(
        entity_id for uid, entity_id in _snapshot_entity_ids_by_unique_id(hass, entry).items()
        if uid.endswith("_inventory")
    )
    coordinator = entry.runtime_data
    key = snapshot_target_key(target)

    def recorded(state):
        return StateAttributes.shared_attrs_bytes_from_event(
            Event(EVENT_STATE_CHANGED, {"entity_id": entity_id, "old_state": None, "new_state": state}),
            None,
        )

    coordinator.snapshot_inventory[key] = {
        "snapshot_count": 12, "snapshot_count_source": "inventory_total",
        "snapshot_names": ["snapshot-a"], "recent_snapshots": [{"name": "snapshot-a"}],
    }
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state is not None and state.state == "12"
    assert state.attributes["snapshot_names"] == ["snapshot-a"]
    before = recorded(state)
    assert "snapshot_names" not in json.loads(before)
    assert "recent_snapshots" not in json.loads(before)
    assert json.loads(before)["snapshot_count_source"] == "inventory_total"

    coordinator.snapshot_inventory[key]["snapshot_names"] = ["snapshot-b"]
    coordinator.snapshot_inventory[key]["recent_snapshots"] = [{"name": "snapshot-b"}]
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()
    updated = hass.states.get(entity_id)
    assert updated.attributes["snapshot_names"] == ["snapshot-b"]
    assert recorded(updated) == before

    changes = []
    unsub = hass.bus.async_listen(EVENT_STATE_CHANGED, lambda event: changes.append(event))
    try:
        coordinator.async_set_updated_data(coordinator.data)
        await hass.async_block_till_done()
        assert not [event for event in changes if event.data["entity_id"] == entity_id]
    finally:
        unsub()


@pytest.mark.asyncio
async def test_snapshot_control_entities_report_state_in_home_assistant(hass) -> None:
    """Create snapshot entities should expose expected HA state and attributes."""
    from custom_components.unifi_unas.snapshot_types import snapshot_target_key

    target = _snapshot_target_with_controls()
    client = _SnapshotIntegrationClient([target])

    _, entity_ids = await _setup_snapshot_controls(hass, client)

    switch_state = hass.states.get(entity_ids["switch"])
    limit_state = hass.states.get(entity_ids["limit"])
    schedule_state = hass.states.get(entity_ids["schedule"])
    weekday_state = hass.states.get(entity_ids["weekday"])
    month_day_state = hass.states.get(entity_ids["month_day"])
    time_state = hass.states.get(entity_ids["schedule_time"])
    button_state = hass.states.get(entity_ids["button"])

    assert switch_state is not None
    assert switch_state.state == "on"
    assert limit_state is not None
    assert limit_state.state == "12"
    assert schedule_state is not None
    assert schedule_state.state == "Daily"
    assert weekday_state is not None
    assert weekday_state.state == "Monday"
    assert month_day_state is not None
    assert month_day_state.state == "15"
    assert time_state is not None
    assert time_state.state.startswith("08:15")
    assert button_state is not None
    assert button_state.attributes["target_type"] == "shared"
    assert button_state.attributes["target_key"] == snapshot_target_key(target)


@pytest.mark.asyncio
async def test_snapshot_control_services_update_client_and_refresh_states(hass) -> None:
    """Snapshot control services should call API updates and refresh HA states."""
    target = _snapshot_target_with_controls()
    from custom_components.unifi_unas.snapshot_types import snapshot_target_key

    client = _SnapshotIntegrationClient([target])
    entry, entity_ids = await _setup_snapshot_controls(hass, client)
    target_key = snapshot_target_key(target)

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": entity_ids["button"]},
        blocking=True,
    )
    assert client.created
    assert client.created[-1]["target_key"] == target_key

    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": entity_ids["switch"]},
        blocking=True,
    )
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": entity_ids["limit"], "value": 24},
        blocking=True,
    )
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": entity_ids["schedule"], "option": "Monthly"},
        blocking=True,
    )
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": entity_ids["weekday"], "option": "Wednesday"},
        blocking=True,
    )

    await hass.services.async_call(
        "time",
        "set_value",
        {"entity_id": entity_ids["schedule_time"], "time": "14:30:00"},
        blocking=True,
    )

    await hass.async_block_till_done()
    from custom_components.unifi_unas.const import DOMAIN

    coordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_request_refresh()
    await hass.async_block_till_done()

    assert client.updated == [
        (target_key, {"enabled": False}),
        (target_key, {"max_count": 24}),
        (target_key, {"schedule_frequency": "Monthly"}),
        (target_key, {"schedule_frequency": "Weekly", "schedule_weekdays": "3"}),
        (target_key, {"schedule_time": "14:30"}),
    ]

    current_target = next(
        target
        for target in coordinator.snapshot_settings
        if snapshot_target_key(target) == target_key
    )
    assert not current_target["enabled"]
    assert hass.states.get(entity_ids["switch"]).state == "off"
    assert hass.states.get(entity_ids["limit"]).state == "24"
    assert hass.states.get(entity_ids["schedule"]).state == "Weekly"
    assert hass.states.get(entity_ids["weekday"]).state == "Wednesday"
    assert hass.states.get(entity_ids["schedule_time"]).state == "14:30:00"


@pytest.mark.asyncio
async def test_snapshot_create_button_reports_api_failures(hass) -> None:
    """Snapshot create failures should surface translatable HA errors."""
    from custom_components.unifi_unas.api import (
        CannotConnect,
        InvalidAuth,
        UnsupportedFeature,
    )

    client = _SnapshotIntegrationClient([_snapshot_target_with_controls()])
    _, entity_ids = await _setup_snapshot_controls(hass, client)

    client.fail_next = InvalidAuth("denied")
    with pytest.raises(Exception) as err:
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": entity_ids["button"]},
            blocking=True,
        )
    assert getattr(err.value, "translation_key", None) == "snapshot_action_permission"

    client.fail_next = UnsupportedFeature("not supported")
    with pytest.raises(Exception) as err:
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": entity_ids["button"]},
            blocking=True,
        )
    assert getattr(err.value, "translation_key", None) == "snapshot_action_unsupported"

    client.fail_next = CannotConnect("offline")
    with pytest.raises(Exception) as err:
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": entity_ids["button"]},
            blocking=True,
        )
    assert getattr(err.value, "translation_key", None) == "snapshot_action_failed"


@pytest.mark.asyncio
async def test_snapshot_setting_controls_report_api_failures(hass) -> None:
    """Snapshot setting writes should surface actionable translated failures."""
    from custom_components.unifi_unas.api import (
        CannotConnect,
        InvalidAuth,
        UnsupportedFeature,
    )

    client = _SnapshotIntegrationClient([_snapshot_target_with_controls()])
    _, entity_ids = await _setup_snapshot_controls(hass, client)

    client.fail_next = InvalidAuth("denied")
    with pytest.raises(Exception) as err:
        await hass.services.async_call(
            "switch",
            "turn_off",
            {"entity_id": entity_ids["switch"]},
            blocking=True,
        )
    assert getattr(err.value, "translation_key", None) == "snapshot_action_permission"

    client.fail_next = UnsupportedFeature("not supported")
    with pytest.raises(Exception) as err:
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": entity_ids["limit"], "value": 16},
            blocking=True,
        )
    assert getattr(err.value, "translation_key", None) == "snapshot_settings_unsupported"

    client.fail_next = CannotConnect("offline")
    with pytest.raises(Exception) as err:
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": entity_ids["schedule"], "option": "Weekly"},
            blocking=True,
        )
    assert getattr(err.value, "translation_key", None) == "snapshot_settings_failed"


@pytest.mark.asyncio
async def test_snapshot_control_states_refresh_immediately_after_service_update(hass) -> None:
    """Service updates should rewrite snapshot entity states without manual refresh."""
    target = _snapshot_target_with_controls()
    from custom_components.unifi_unas.snapshot_types import snapshot_target_key

    client = _SnapshotIntegrationClient([target])
    entry, entity_ids = await _setup_snapshot_controls(hass, client)
    target_key = snapshot_target_key(target)

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": entity_ids["limit"], "value": 36},
        blocking=True,
    )

    current_target = next(
        candidate
        for candidate in hass.data["unifi_unas"][entry.entry_id].snapshot_settings
        if snapshot_target_key(candidate) == target_key
    )
    assert current_target["max_count"] == 36
    assert hass.states.get(entity_ids["limit"]).state == "36"
    assert client.updated == [(target_key, {"max_count": 36})]


@pytest.mark.asyncio
async def test_snapshot_control_entities_ignore_invalid_snapshot_targets(hass) -> None:
    """Entity state creation should ignore malformed snapshot settings entries."""
    valid_target = _snapshot_target_with_controls()
    client = _SnapshotIntegrationClient(
        [
            None,
            123,
            "bad-entry",
            valid_target,
            {"type": "mydrive", "id": "other-user"},
        ]
    )
    entry, entity_ids = await _setup_snapshot_controls(hass, client)
    coordinator = hass.data["unifi_unas"][entry.entry_id]
    assert any(
        isinstance(target, dict) and target.get("id") == "shared-1"
        for target in coordinator.snapshot_settings
    )
    assert hass.states.get(entity_ids["switch"]) is not None
    assert hass.states.get(entity_ids["switch"]).state == "on"
    assert hass.states.get(entity_ids["limit"]) is not None
    assert hass.states.get(entity_ids["limit"]).state == "12"


@pytest.mark.asyncio
async def test_snapshot_control_services_target_valid_entry_with_invalid_settings(
    hass,
) -> None:
    """Service calls should still update the valid shared target when other entries are invalid."""
    valid_target = _snapshot_target_with_controls()
    from custom_components.unifi_unas.snapshot_types import snapshot_target_key

    client = _SnapshotIntegrationClient(
        [
            None,
            123,
            valid_target,
            {"type": "mydrive", "id": "other-user"},
        ]
    )
    entry, entity_ids = await _setup_snapshot_controls(hass, client)
    target_key = snapshot_target_key(valid_target)

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": entity_ids["limit"], "value": 33},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert (target_key, {"max_count": 33}) in client.updated
