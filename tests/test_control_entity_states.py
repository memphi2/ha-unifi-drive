"""Integration-level state tests for non-snapshot control entities."""

from __future__ import annotations

from types import SimpleNamespace
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


def _entry_data(**overrides: Any) -> dict[str, Any]:
    """Build minimal config entry data with the non-snapshot controls enabled."""
    _ensure_repo_custom_components_path()
    from custom_components.unifi_unas.const import (
        CONF_FAN_CONTROL_ENABLED,
        CONF_SNAPSHOT_BUTTONS_ENABLED,
        DEFAULT_PORT,
        DEFAULT_SCAN_INTERVAL,
        DEFAULT_SSL,
        DEFAULT_VERIFY_SSL,
    )

    data = {
        CONF_HOST: "unas.local",
        CONF_PORT: DEFAULT_PORT,
        CONF_SSL: DEFAULT_SSL,
        CONF_VERIFY_SSL: DEFAULT_VERIFY_SSL,
        CONF_USERNAME: "test-user",
        CONF_PASSWORD: "test-pass",
        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
        CONF_FAN_CONTROL_ENABLED: True,
        CONF_SNAPSHOT_BUTTONS_ENABLED: False,
    }
    data.update(overrides)
    return data


def _storage_payload() -> dict[str, Any]:
    """Return storage data with enough metadata for update entities."""
    return {
        "_system": {
            "status": "online",
            "hardware": {
                "firmwareVersion": "v4.1.9",
                "shortname": "UNAS-Pro",
            },
            "latestUpdate": {
                "version": "4.2.1",
                "platform": "UNAS-Pro",
            },
            "apps": {
                "controllers": [
                    {
                        "name": "drive",
                        "displayName": "UniFi Drive",
                        "version": "1.2.3",
                        "updateAvailable": "1.3.0",
                    }
                ]
            },
            "firmware": {"update": {"state": "notStarted"}},
        }
    }


class _ControlIntegrationClient:
    """Fake API client for HA-state tests of remaining control platforms."""

    base_url = "https://unas.local"
    native_fan_mode = "Balance"
    poweroff_permission_hint = None
    snapshot_settings_read_supported = False

    def __init__(self) -> None:
        self.fan_modes: list[str] = []
        self.backup_runs: list[str] = []
        self.reboot_count = 0
        self.poweroff_count = 0
        self.fail_next: Exception | None = None
        self.backup_tasks = [{"id": "task-1", "name": "Nightly Backup"}]

    async def _maybe_fail(self) -> None:
        if self.fail_next is not None:
            err = self.fail_next
            self.fail_next = None
            raise err

    async def async_get_storage(self) -> dict[str, Any]:
        return _storage_payload()

    async def async_get_fan_mode(self) -> str:
        return self.native_fan_mode

    async def async_set_fan_mode(self, mode: str) -> str:
        await self._maybe_fail()
        self.fan_modes.append(mode)
        self.native_fan_mode = mode
        return mode

    async def async_get_backup_tasks(self) -> list[dict[str, Any]]:
        return list(self.backup_tasks)

    async def async_run_backup_task(self, task_id: str) -> None:
        await self._maybe_fail()
        self.backup_runs.append(task_id)

    async def async_reboot(self) -> None:
        await self._maybe_fail()
        self.reboot_count += 1

    async def async_poweroff(self) -> None:
        await self._maybe_fail()
        self.poweroff_count += 1

    async def async_install_unifi_os_update(self) -> None:
        return None

    async def async_install_drive_update(self) -> None:
        return None


@pytest.mark.asyncio
@pytest.mark.parametrize("language,suffix", [("en", "Run backup"), ("de", "Backup starten")])
async def test_backup_task_name_is_translated(hass, language, suffix):
    """Backup labels use the platform translation without changing unique IDs."""
    hass.config.language = language
    entry = await _async_setup_control_entry(hass, _ControlIntegrationClient())
    entity_id = _entity_id_for_unique_id(hass, entry, "device-1_backup_task-1")
    assert hass.states.get(entity_id).attributes["friendly_name"] == f"UNAS Nightly Backup {suffix}"


async def _async_setup_control_entry(hass, client, **data_overrides: Any):
    """Patch network calls and initialize the integration."""
    from homeassistant.setup import async_setup_component
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.unifi_unas.const import DOMAIN

    _ensure_repo_custom_components_path()
    assert await async_setup_component(hass, DOMAIN, {})
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="UNAS",
        unique_id="device-1",
        data=_entry_data(**data_overrides),
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
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


def _entity_id_for_unique_id(hass, entry, unique_id: str) -> str:
    """Resolve one entity ID by config-entry unique ID."""
    from homeassistant.helpers import entity_registry as er

    entries = er.async_entries_for_config_entry(
        er.async_get(hass),
        entry.entry_id,
    )
    for entity_entry in entries:
        if entity_entry.unique_id == unique_id:
            return entity_entry.entity_id
    raise AssertionError(f"Missing entity with unique ID {unique_id}")


@pytest.mark.asyncio
async def test_fan_select_reports_and_updates_home_assistant_state(hass) -> None:
    """Fan select should expose and refresh real Home Assistant state."""
    client = _ControlIntegrationClient()
    entry = await _async_setup_control_entry(hass, client)
    entity_id = _entity_id_for_unique_id(hass, entry, "device-1_fan_mode")

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "Balance"
    assert state.attributes["options"] == ["Quiet", "Balance", "Cooling"]
    assert state.attributes["mode_type"] == "native_unifi_unas_fan_mode"

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": entity_id, "option": "Cooling"},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert client.fan_modes == ["Cooling"]
    assert hass.states.get(entity_id).state == "Cooling"


@pytest.mark.asyncio
async def test_fan_select_reports_action_failures(hass) -> None:
    """Fan select should surface validation, permission and endpoint failures."""
    from custom_components.unifi_unas.api import InvalidAuth, UnsupportedFeature

    client = _ControlIntegrationClient()
    entry = await _async_setup_control_entry(hass, client)
    entity_id = _entity_id_for_unique_id(hass, entry, "device-1_fan_mode")

    with pytest.raises(Exception) as err:
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": entity_id, "option": "Turbo"},
            blocking=True,
        )
    assert getattr(err.value, "translation_key", None) == "not_valid_option"

    client.fail_next = InvalidAuth("forbidden")
    with pytest.raises(Exception) as err:
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": entity_id, "option": "Quiet"},
            blocking=True,
        )
    assert getattr(err.value, "translation_key", None) == "fan_mode_permission"

    client.fail_next = UnsupportedFeature("missing")
    with pytest.raises(Exception) as err:
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": entity_id, "option": "Quiet"},
            blocking=True,
        )
    assert getattr(err.value, "translation_key", None) == "fan_mode_unsupported"


@pytest.mark.asyncio
async def test_update_entities_report_home_assistant_state(hass) -> None:
    """Update entities should expose installed and latest versions in HA state."""
    client = _ControlIntegrationClient()
    entry = await _async_setup_control_entry(hass, client)
    unifi_os_entity_id = _entity_id_for_unique_id(
        hass,
        entry,
        "device-1_unifi_os_update",
    )
    drive_entity_id = _entity_id_for_unique_id(
        hass,
        entry,
        "device-1_drive_update",
    )

    unifi_os_state = hass.states.get(unifi_os_entity_id)
    drive_state = hass.states.get(drive_entity_id)

    assert unifi_os_state is not None
    assert unifi_os_state.state == "on"
    assert unifi_os_state.attributes["installed_version"] == "4.1.9"
    assert unifi_os_state.attributes["latest_version"] == "4.2.1"
    assert unifi_os_state.attributes["title"] == "UniFi OS / UNAS-Pro"

    assert drive_state is not None
    assert drive_state.state == "on"
    assert drive_state.attributes["installed_version"] == "1.2.3"
    assert drive_state.attributes["latest_version"] == "1.3.0"
    assert drive_state.attributes["title"] == "Application / Unifi Drive"


@pytest.mark.asyncio
async def test_system_buttons_run_and_report_failures(hass) -> None:
    """System buttons should call clients and translate offline/API failures."""
    from custom_components.unifi_unas.api import CannotConnect, InvalidAuth
    from custom_components.unifi_unas.const import DOMAIN

    client = _ControlIntegrationClient()
    entry = await _async_setup_control_entry(hass, client)
    coordinator = hass.data[DOMAIN][entry.entry_id]
    reboot_id = _entity_id_for_unique_id(hass, entry, "device-1_reboot")
    shutdown_id = _entity_id_for_unique_id(hass, entry, "device-1_shutdown")

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": reboot_id},
        blocking=True,
    )
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": shutdown_id},
        blocking=True,
    )

    assert client.reboot_count == 1
    assert client.poweroff_count == 1

    coordinator.is_device_online = False
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": reboot_id},
        blocking=True,
    )
    assert client.reboot_count == 1

    coordinator.is_device_online = True
    client.fail_next = InvalidAuth("forbidden")
    with pytest.raises(Exception) as err:
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": reboot_id},
            blocking=True,
        )
    assert getattr(err.value, "translation_key", None) == "system_action_permission"

    client.fail_next = CannotConnect("offline")
    with pytest.raises(Exception) as err:
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": reboot_id},
            blocking=True,
        )
    assert getattr(err.value, "translation_key", None) == "system_action_failed"


@pytest.mark.asyncio
async def test_wake_on_lan_button_stays_available_offline(hass) -> None:
    """WOL button should remain usable when the device is offline."""
    from custom_components.unifi_unas.const import (
        CONF_WOL_ENABLED,
        CONF_WOL_MAC_ADDRESS,
        DOMAIN,
    )

    packets: list[tuple[str, str, int]] = []

    async def _send_packet(mac_address: str, *, broadcast_address: str, port: int):
        packets.append((mac_address, broadcast_address, port))

    client = _ControlIntegrationClient()
    with patch(
        "custom_components.unifi_unas.button.async_send_magic_packet",
        _send_packet,
    ):
        entry = await _async_setup_control_entry(
            hass,
            client,
            **{
                CONF_WOL_ENABLED: True,
                CONF_WOL_MAC_ADDRESS: "aa:bb:cc:dd:ee:ff",
            },
        )
        coordinator = hass.data[DOMAIN][entry.entry_id]
        coordinator.is_device_online = False
        entity_id = _entity_id_for_unique_id(hass, entry, "device-1_wake_on_lan")

        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state != "unavailable"
        assert state.attributes["mac_address"] == "**:**:**:**:ee:ff"

        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": entity_id},
            blocking=True,
        )

    assert packets == [("aa:bb:cc:dd:ee:ff", "255.255.255.255", 9)]


@pytest.mark.asyncio
async def test_wake_on_lan_button_reports_missing_config_and_send_failures() -> None:
    """WOL button errors should be translatable and independent of online state."""
    from custom_components.unifi_unas.button import UnifiUnasWakeOnLanButton
    from custom_components.unifi_unas.const import (
        CONF_WOL_ENABLED,
        CONF_WOL_MAC_ADDRESS,
    )

    missing_entry = SimpleNamespace(
        entry_id="entry-1",
        unique_id="device-1",
        title="UNAS",
        data=_entry_data(
            **{
                CONF_WOL_ENABLED: False,
                CONF_WOL_MAC_ADDRESS: "",
            }
        ),
        options={},
    )
    coordinator = SimpleNamespace(client=SimpleNamespace(base_url=None), data={})
    button = UnifiUnasWakeOnLanButton(coordinator, missing_entry)

    assert button.available is False
    assert button.device_info["configuration_url"] == "https://unas.local"
    with pytest.raises(Exception) as err:
        await button.async_press()
    assert getattr(err.value, "translation_key", None) == "wake_on_lan_mac_missing"

    failing_entry = SimpleNamespace(
        entry_id="entry-1",
        unique_id="device-1",
        title="UNAS",
        data=_entry_data(
            **{
                CONF_WOL_ENABLED: True,
                CONF_WOL_MAC_ADDRESS: "aa:bb:cc:dd:ee:ff",
            }
        ),
        options={},
    )
    button = UnifiUnasWakeOnLanButton(coordinator, failing_entry)

    async def _fail_send(*args, **kwargs):
        raise ValueError("bad broadcast")

    with patch("custom_components.unifi_unas.button.async_send_magic_packet", _fail_send):
        with pytest.raises(Exception) as err:
            await button.async_press()
    assert getattr(err.value, "translation_key", None) == "wake_on_lan_send_failed"


@pytest.mark.asyncio
async def test_backup_button_reports_and_runs_from_home_assistant_state(hass) -> None:
    """Backup task buttons should expose task metadata and call the API service."""
    client = _ControlIntegrationClient()
    entry = await _async_setup_control_entry(hass, client)
    entity_id = _entity_id_for_unique_id(hass, entry, "device-1_backup_task-1")

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state != "unavailable"
    assert state.attributes["task_id"] == "task-1"
    assert state.attributes["task_name"] == "Nightly Backup"

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": entity_id},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert client.backup_runs == ["task-1"]
    assert hass.states.get(entity_id).state != "unavailable"


@pytest.mark.asyncio
async def test_backup_button_reports_offline_and_api_failures(hass) -> None:
    """Backup task button should not turn offline into repairs or silent success."""
    from custom_components.unifi_unas.api import InvalidAuth, UnsupportedFeature
    from custom_components.unifi_unas.const import DOMAIN

    client = _ControlIntegrationClient()
    entry = await _async_setup_control_entry(hass, client)
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entity_id = _entity_id_for_unique_id(hass, entry, "device-1_backup_task-1")

    coordinator.is_device_online = False
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": entity_id},
        blocking=True,
    )
    assert client.backup_runs == []

    coordinator.is_device_online = True
    client.fail_next = InvalidAuth("forbidden")
    with pytest.raises(Exception) as err:
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": entity_id},
            blocking=True,
        )
    assert getattr(err.value, "translation_key", None) == "backup_task_permission"

    client.fail_next = UnsupportedFeature("missing")
    with pytest.raises(Exception) as err:
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": entity_id},
            blocking=True,
        )
    assert getattr(err.value, "translation_key", None) == "backup_task_failed"
