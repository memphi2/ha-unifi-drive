"""Integration-level state tests for core monitoring entities."""

from __future__ import annotations

from copy import deepcopy
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


GIB = 1024**3


@pytest.fixture
def hass_config_dir() -> str:
    """Point Home Assistant at this repository's test config directory."""
    return str(ROOT)


def _entry_data() -> dict[str, Any]:
    """Build minimal config entry data for storage monitoring tests."""
    _ensure_repo_custom_components_path()
    from custom_components.unifi_unas.const import (
        CONF_FAN_CONTROL_ENABLED,
        CONF_SNAPSHOT_BUTTONS_ENABLED,
        DEFAULT_PORT,
        DEFAULT_SCAN_INTERVAL,
        DEFAULT_SSL,
        DEFAULT_VERIFY_SSL,
    )

    return {
        CONF_HOST: "unas.local",
        CONF_PORT: DEFAULT_PORT,
        CONF_SSL: DEFAULT_SSL,
        CONF_VERIFY_SSL: DEFAULT_VERIFY_SSL,
        CONF_USERNAME: "test-user",
        CONF_PASSWORD: "test-pass",
        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
        CONF_FAN_CONTROL_ENABLED: False,
        CONF_SNAPSHOT_BUTTONS_ENABLED: False,
    }


def _storage_payload(
    *,
    pool_status: str = "healthy",
    drive_health_score: int = 5,
    rebuild_progress: int | None = None,
) -> dict[str, Any]:
    """Return a storage payload with stable aggregate, pool and drive metrics."""
    pool: dict[str, Any] = {
        "id": "pool-a",
        "label": "Main",
        "status": pool_status,
        "capacity": 10 * GIB,
        "used": 4 * GIB,
        "drives": [
            {
                "slotId": "1",
                "healthScore": drive_health_score,
                "temperature": 31,
                "powerOnHours": 1200,
            }
        ],
    }
    if rebuild_progress is not None:
        pool["rebuildProgress"] = rebuild_progress

    return {
        "_system": {
            "status": "online",
            "hardware": {
                "firmwareVersion": "v5.0.17",
                "shortname": "UNAS-Test",
            },
        },
        "pools": [pool],
        "readThroughput": "12 MB/s",
        "writeThroughput": "3 MB/s",
    }


class _MonitoringClient:
    """Fake API client for HA-state tests of core monitoring entities."""

    base_url = "https://unas.local"
    native_fan_mode = None
    poweroff_permission_hint = None
    snapshot_settings_read_supported = False

    def __init__(self) -> None:
        self.storage = _storage_payload()
        self.offline = False

    async def async_get_storage(self) -> dict[str, Any]:
        """Return storage or simulate an offline device."""
        if self.offline:
            from custom_components.unifi_unas.coordinator import CannotConnect

            raise CannotConnect("offline")
        return deepcopy(self.storage)

    async def async_get_backup_tasks(self) -> list[dict[str, Any]]:
        """Return no backup tasks for this monitoring-only setup."""
        return []

    async def async_reboot(self) -> None:
        """System action stub."""
        return None

    async def async_poweroff(self) -> None:
        """System action stub."""
        return None

    async def async_install_unifi_os_update(self) -> None:
        """Update action stub."""
        return None

    async def async_install_drive_update(self) -> None:
        """Update action stub."""
        return None


async def _async_setup_monitoring_entry(hass, client):
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
        data=_entry_data(),
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


def _state(hass, entity_id: str) -> str:
    """Return an entity state, failing with a useful message if absent."""
    state = hass.states.get(entity_id)
    assert state is not None, entity_id
    return state.state


@pytest.mark.asyncio
@pytest.mark.parametrize("language,capacity,temperature,maintenance", [
    ("en", "Capacity", "Temperature", "Maintenance active"),
    ("de", "Kapazitaet", "Temperatur", "Wartung aktiv"),
])
async def test_pool_and_drive_names_are_translated(hass, language, capacity, temperature, maintenance):
    """Dynamic pool and drive names work even for disabled diagnostic entities."""
    from homeassistant.helpers import entity_registry as er

    hass.config.language = language
    entry = await _async_setup_monitoring_entry(hass, _MonitoringClient())
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    for key, suffix in (("pool_capacity", capacity), ("drive_temperature", temperature), ("pool_maintenance_active", maintenance)):
        entity = next(item for item in entities if item.translation_key == key)
        assert entity.original_name.startswith("Main ")
        assert entity.original_name.endswith(suffix)
        assert "{" not in entity.original_name


@pytest.mark.asyncio
async def test_core_monitoring_states_survive_degraded_offline_online_cycle(hass) -> None:
    """Core monitoring entities should change state without becoming unavailable."""
    from custom_components.unifi_unas.const import DOMAIN

    client = _MonitoringClient()
    entry = await _async_setup_monitoring_entry(hass, client)
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entity_ids = {
        "device_online": _entity_id_for_unique_id(
            hass,
            entry,
            "device-1_device_online",
        ),
        "system_status": _entity_id_for_unique_id(
            hass,
            entry,
            "device-1_system_status",
        ),
        "overall_status": _entity_id_for_unique_id(
            hass,
            entry,
            "device-1_overall_status",
        ),
        "total_storage": _entity_id_for_unique_id(
            hass,
            entry,
            "device-1_total_storage",
        ),
        "at_risk_disk_count": _entity_id_for_unique_id(
            hass,
            entry,
            "device-1_at_risk_disk_count",
        ),
        "maintenance_pool_count": _entity_id_for_unique_id(
            hass,
            entry,
            "device-1_maintenance_pool_count",
        ),
        "storage_problem": _entity_id_for_unique_id(
            hass,
            entry,
            "device-1_storage_problem",
        ),
        "maintenance_active": _entity_id_for_unique_id(
            hass,
            entry,
            "device-1_maintenance_active",
        ),
    }

    assert _state(hass, entity_ids["device_online"]) == "on"
    assert _state(hass, entity_ids["system_status"]) == "online"
    assert _state(hass, entity_ids["overall_status"]) == "healthy"
    assert _state(hass, entity_ids["total_storage"]) == "10.0"
    assert _state(hass, entity_ids["at_risk_disk_count"]) == "0"
    assert _state(hass, entity_ids["maintenance_pool_count"]) == "0"
    assert _state(hass, entity_ids["storage_problem"]) == "off"
    assert _state(hass, entity_ids["maintenance_active"]) == "off"

    client.storage = _storage_payload(
        pool_status="degraded",
        drive_health_score=2,
        rebuild_progress=42,
    )
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert _state(hass, entity_ids["system_status"]) == "online"
    assert _state(hass, entity_ids["overall_status"]) == "degraded"
    assert _state(hass, entity_ids["at_risk_disk_count"]) == "1"
    assert _state(hass, entity_ids["maintenance_pool_count"]) == "1"
    assert _state(hass, entity_ids["storage_problem"]) == "on"
    assert _state(hass, entity_ids["maintenance_active"]) == "on"

    client.offline = True
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.is_device_online is True
    assert _state(hass, entity_ids["device_online"]) == "on"
    assert _state(hass, entity_ids["system_status"]) == "online"
    assert all(_state(hass, entity_id) != "unavailable" for entity_id in entity_ids.values())

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.is_device_online is False
    assert _state(hass, entity_ids["device_online"]) == "off"
    assert _state(hass, entity_ids["system_status"]) == "offline"
    assert _state(hass, entity_ids["total_storage"]) == "10.0"
    assert _state(hass, entity_ids["storage_problem"]) == "on"
    assert all(_state(hass, entity_id) != "unavailable" for entity_id in entity_ids.values())

    client.offline = False
    client.storage = _storage_payload()
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.is_device_online is True
    assert _state(hass, entity_ids["device_online"]) == "on"
    assert _state(hass, entity_ids["system_status"]) == "online"
    assert _state(hass, entity_ids["overall_status"]) == "healthy"
    assert _state(hass, entity_ids["at_risk_disk_count"]) == "0"
    assert _state(hass, entity_ids["maintenance_pool_count"]) == "0"
    assert _state(hass, entity_ids["storage_problem"]) == "off"
    assert _state(hass, entity_ids["maintenance_active"]) == "off"
    assert set(entity_ids.values()) == {
        _entity_id_for_unique_id(hass, entry, unique_id)
        for unique_id in (
            "device-1_device_online",
            "device-1_system_status",
            "device-1_overall_status",
            "device-1_total_storage",
            "device-1_at_risk_disk_count",
            "device-1_maintenance_pool_count",
            "device-1_storage_problem",
            "device-1_maintenance_active",
        )
    }
