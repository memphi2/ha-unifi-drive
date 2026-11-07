"""Integration-level state tests for core monitoring entities."""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from unittest.mock import patch

import pytest

from tests.ha_test_helpers import (
    ensure_repo_custom_components_path as _ensure_repo_custom_components_path,
)
from tests.storage_fixtures import multi_pool_storage

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

    def invalidate_system_metadata(self) -> None:
        """The synthetic monitoring client has no metadata cache."""

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
    from tests.ha_test_compat import MockConfigEntry

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
async def test_device_metadata_fallback_updates_device_and_freezes_offline(hass, freezer):
    """API-key metadata uses existing entities and keeps sampled uptime offline."""
    from homeassistant.helpers import device_registry as dr
    from custom_components.unifi_unas.const import DOMAIN

    client = _MonitoringClient()
    client.storage["_system"] = {"status": "online"}
    client.storage["_device_info"] = {
        "firmwareVersion": "5.1.10", "version": "4.3.6", "uptime": 7200,
        "startupTime": "2026-01-01T00:00:00Z", "cpu": {"temperature": 42},
        "networkInterfaces": [{"ipAddress": "192.0.2.10"}],
    }
    entry = await _async_setup_monitoring_entry(hass, client)
    coordinator = entry.runtime_data
    values = {"system_uptime": "2.0", "unifi_os_version": "5.1.10",
              "drive_version": "4.3.6", "cpu_temperature": "42.0", "system_ip": "192.0.2.10"}
    ids = {key: _entity_id_for_unique_id(hass, entry, f"device-1_{key}") for key in values}
    for key, expected in values.items():
        assert _state(hass, ids[key]) == expected
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    device = next(item for item in devices if (DOMAIN, "device-1") in item.identifiers)
    assert device.sw_version == "5.1.10"
    client.offline = True
    freezer.tick(3600)
    for _ in range(2):
        await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.is_device_online is False
    assert _state(hass, ids["system_uptime"]) == "2.0"
    client.offline = False
    client.storage["_device_info"]["uptime"] = 10800
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, ids["system_uptime"]) == "3.0"


@pytest.mark.asyncio
async def test_scrubbing_and_raid_groups_drive_existing_maintenance_states(hass):
    """Idle/completed operations clear existing maintenance entities."""
    client = _MonitoringClient()
    entry = await _async_setup_monitoring_entry(hass, client)
    coordinator = entry.runtime_data
    active_id = _entity_id_for_unique_id(hass, entry, "device-1_maintenance_active")
    count_id = _entity_id_for_unique_id(hass, entry, "device-1_maintenance_pool_count")
    for operation, active in (
        ({"dataScrubbing": {"status": "running", "progress": 0}}, True),
        ({"dataScrubbing": {"status": "idle", "progress": 50}}, False),
        ({"raidGroups": [{"progress": 1}]}, True),
        ({"raidGroups": [{"progress": 100}]}, False),
        ({"raidGroups": [{"progress": 50, "isSSDCache": True}]}, False),
    ):
        client.storage = _storage_payload()
        client.storage["pools"][0].update(operation)
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert _state(hass, active_id) == ("on" if active else "off")
        assert _state(hass, count_id) == ("1" if active else "0")


@pytest.mark.asyncio
async def test_drive_diagnostics_are_opt_in_and_late_fields_do_not_duplicate_entities(hass):
    from homeassistant.helpers import entity_registry as er

    client = _MonitoringClient()
    client.storage["cacheSlots"] = [{"id": "cache-a", "lifeSpan": 99, "temperature": 30}]
    entry = await _async_setup_monitoring_entry(hass, client)
    registry = er.async_get(hass)
    def entries():
        return er.async_entries_for_config_entry(registry, entry.entry_id)
    cache = [item for item in entries() if ":cache:" in item.unique_id]
    assert len(cache) == 2
    assert all(item.disabled_by is er.RegistryEntryDisabler.INTEGRATION for item in cache)
    assert all(hass.states.get(item.entity_id) is None for item in cache)
    client.storage["pools"][0]["drives"][0]["badSectorCount"] = 0
    for _ in range(3):
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
    added = [item for item in entries() if item.translation_key == "drive_bad_sectors"]
    assert len(added) == 1
    assert added[0].disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert hass.states.get(added[0].entity_id) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("drive_count", [4, 7, 8])
async def test_multi_pool_diagnostics_stay_disabled_and_registry_stays_bounded(hass, drive_count):
    """Larger synthetic layouts do not enable extra history or duplicate entities."""
    from homeassistant.helpers import entity_registry as er
    from custom_components.unifi_unas.sensor_descriptions import DRIVE_SENSOR_TYPES

    client = _MonitoringClient()
    client.storage = multi_pool_storage(drive_count)
    entry = await _async_setup_monitoring_entry(hass, client)
    registry = er.async_get(hass)
    initial = er.async_entries_for_config_entry(registry, entry.entry_id)
    initial_ids = {item.unique_id: item.entity_id for item in initial}
    drive_keys = {description.translation_key for description in DRIVE_SENSOR_TYPES}
    diagnostics = [item for item in initial if item.translation_key in drive_keys]
    assert len(diagnostics) == drive_count * 5 + 2 * 5
    assert all(item.disabled_by is er.RegistryEntryDisabler.INTEGRATION for item in diagnostics)
    assert all(hass.states.get(item.entity_id) is None for item in diagnostics)

    for _ in range(3):
        client.storage["pools"].reverse()
        client.storage["disks"].reverse()
        client.storage["cacheSlots"].reverse()
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        assert {
            item.unique_id: item.entity_id
            for item in er.async_entries_for_config_entry(registry, entry.entry_id)
        } == initial_ids
        assert all(hass.states.get(item.entity_id) is None for item in diagnostics)


@pytest.mark.asyncio
async def test_multi_pool_enabled_readings_keep_identity_through_topology_changes(hass, monkeypatch):
    """Enabled data/cache readings remain isolated across reorder, loss and recovery."""
    from dataclasses import replace
    from homeassistant.helpers import entity_registry as er
    from custom_components.unifi_unas import entities

    monkeypatch.setattr(entities, "DRIVE_SENSOR_TYPES", tuple(
        replace(description, entity_registry_enabled_default=True)
        for description in entities.DRIVE_SENSOR_TYPES
    ))
    client = _MonitoringClient()
    client.storage = multi_pool_storage()
    entry = await _async_setup_monitoring_entry(hass, client)
    coordinator = entry.runtime_data
    registry = er.async_get(hass)
    initial_ids = {
        item.unique_id: item.entity_id
        for item in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    data_ids = [
        initial_ids[f"device-1_pool_{'a' if index % 2 == 0 else 'b'}_disk_{index}_drive_temperature"]
        for index in range(8)
    ]
    cache_ids = [initial_ids[f"device-1:cache:id_disk_{index}:drive_temperature"] for index in range(2)]

    client.storage["pools"].reverse()
    client.storage["disks"].reverse()
    client.storage["cacheSlots"].reverse()
    for pool in client.storage["pools"]:
        pool["label"] = "Renamed " + pool["id"]
    for disk in client.storage["disks"]:
        disk["temperature"] += 1
    for disk in client.storage["cacheSlots"]:
        disk["name"] = "Renamed " + disk["id"]
        disk["temperature"] += 1
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert [_state(hass, entity_id) for entity_id in data_ids] == [f"{31 + i}.0" for i in range(8)]
    assert [_state(hass, entity_id) for entity_id in cache_ids] == ["41.0", "42.0"]

    missing_pool = client.storage["pools"].pop()
    missing_cache = client.storage["cacheSlots"].pop()
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    for index, entity_id in enumerate(data_ids):
        assert _state(hass, entity_id) == ("unavailable" if index % 2 == 0 else f"{31 + index}.0")
    assert _state(hass, cache_ids[0]) == "unavailable"
    assert _state(hass, cache_ids[1]) == "42.0"

    client.storage["pools"].append(missing_pool)
    client.storage["cacheSlots"].append(missing_cache)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    client.offline = True
    for _ in range(2):
        await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.is_device_online is False
    assert [_state(hass, entity_id) for entity_id in data_ids] == [f"{31 + i}.0" for i in range(8)]
    assert [_state(hass, entity_id) for entity_id in cache_ids] == ["41.0", "42.0"]
    client.offline = False
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.is_device_online is True
    assert {
        item.unique_id: item.entity_id
        for item in er.async_entries_for_config_entry(registry, entry.entry_id)
    } == initial_ids


@pytest.mark.asyncio
async def test_enabled_cache_sensor_survives_removal_reappearance_and_reordering(hass, monkeypatch):
    from dataclasses import replace
    from custom_components.unifi_unas import entities

    # Simulate an enabled diagnostic without changing production defaults.
    monkeypatch.setattr(entities, "DRIVE_SENSOR_TYPES", tuple(
        replace(description, entity_registry_enabled_default=True)
        for description in entities.DRIVE_SENSOR_TYPES
    ))
    client = _MonitoringClient()
    disk = {"id": "cache-a", "lifeSpan": 99}
    client.storage["cacheSlots"] = [disk]
    entry = await _async_setup_monitoring_entry(hass, client)
    entity_id = _entity_id_for_unique_id(hass, entry, "device-1:cache:id_cache_a:drive_remaining_life")
    assert _state(hass, entity_id) == "99.0"
    client.storage["cacheSlots"] = []
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, entity_id) == "unavailable"
    client.storage["cacheSlots"] = [{"id": "cache-b", "lifeSpan": 80}, {**disk, "name": "Renamed"}]
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, entity_id) == "99.0"
    assert _entity_id_for_unique_id(hass, entry, "device-1:cache:id_cache_a:drive_remaining_life") == entity_id


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
