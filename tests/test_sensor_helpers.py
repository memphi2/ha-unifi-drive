"""Unit tests for sensor helper mapping logic."""

import asyncio
from dataclasses import dataclass
from enum import Enum
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
import types


def _load_sensor_module():
    root = Path(__file__).resolve().parents[1]
    package_root = root / "custom_components" / "unifi_unas"
    sensor_path = package_root / "sensor.py"

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

    sensor_pkg = types.ModuleType("homeassistant.components.sensor")

    @dataclass(frozen=True, kw_only=True)
    class SensorEntityDescription:
        key: str
        name: str | None = None
        translation_key: str | None = None
        icon: str | None = None
        device_class: str | None = None
        native_unit_of_measurement: str | None = None
        state_class: str | None = None
        suggested_display_precision: int | None = None
        entity_category: str | None = None
        entity_registry_enabled_default: bool = True

    class SensorEntity:
        pass

    class SensorDeviceClass:
        DATA_SIZE = "data_size"
        TEMPERATURE = "temperature"

    class SensorStateClass:
        MEASUREMENT = "measurement"

    sensor_pkg.SensorDeviceClass = SensorDeviceClass
    sensor_pkg.SensorEntity = SensorEntity
    sensor_pkg.SensorEntityDescription = SensorEntityDescription
    sensor_pkg.SensorStateClass = SensorStateClass
    sys.modules["homeassistant.components.sensor"] = sensor_pkg

    config_entries_pkg = types.ModuleType("homeassistant.config_entries")
    config_entries_pkg.ConfigEntry = type("ConfigEntry", (), {})
    sys.modules["homeassistant.config_entries"] = config_entries_pkg

    const_pkg = types.ModuleType("homeassistant.const")
    const_pkg.PERCENTAGE = "%"

    class Platform(str, Enum):
        BINARY_SENSOR = "binary_sensor"
        BUTTON = "button"
        NUMBER = "number"
        SELECT = "select"
        SENSOR = "sensor"
        SWITCH = "switch"
        TIME = "time"
        UPDATE = "update"

    class EntityCategory:
        DIAGNOSTIC = "diagnostic"
        CONFIG = "config"

    const_pkg.EntityCategory = EntityCategory
    class UnitOfInformation:
        GIBIBYTES = "GiB"

    class UnitOfTemperature:
        CELSIUS = "C"

    const_pkg.Platform = Platform
    const_pkg.UnitOfInformation = UnitOfInformation
    const_pkg.UnitOfTemperature = UnitOfTemperature
    sys.modules["homeassistant.const"] = const_pkg

    core_pkg = types.ModuleType("homeassistant.core")
    core_pkg.HomeAssistant = type("HomeAssistant", (), {})
    sys.modules["homeassistant.core"] = core_pkg

    helpers_pkg = types.ModuleType("homeassistant.helpers")
    sys.modules["homeassistant.helpers"] = helpers_pkg

    exceptions_pkg = types.ModuleType("homeassistant.exceptions")
    exceptions_pkg.HomeAssistantError = Exception
    exceptions_pkg.ServiceValidationError = Exception
    sys.modules["homeassistant.exceptions"] = exceptions_pkg

    device_registry_pkg = types.ModuleType("homeassistant.helpers.device_registry")
    device_registry_pkg.DeviceInfo = dict
    sys.modules["homeassistant.helpers.device_registry"] = device_registry_pkg

    issue_registry_pkg = types.ModuleType("homeassistant.helpers.issue_registry")
    issue_registry_pkg.IssueSeverity = types.SimpleNamespace(WARNING="warning")
    issue_registry_pkg.async_create_issue = lambda *args, **kwargs: None
    issue_registry_pkg.async_delete_issue = lambda *args, **kwargs: None
    sys.modules["homeassistant.helpers.issue_registry"] = issue_registry_pkg

    entity_platform_pkg = types.ModuleType("homeassistant.helpers.entity_platform")
    entity_platform_pkg.AddEntitiesCallback = object
    sys.modules["homeassistant.helpers.entity_platform"] = entity_platform_pkg

    typing_pkg = types.ModuleType("homeassistant.helpers.typing")
    typing_pkg.StateType = object
    sys.modules["homeassistant.helpers.typing"] = typing_pkg

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

    coordinator_pkg = types.ModuleType("custom_components.unifi_unas.coordinator")
    coordinator_pkg.UnifiUnasCoordinator = type("UnifiUnasCoordinator", (), {})
    sys.modules["custom_components.unifi_unas.coordinator"] = coordinator_pkg

    api_pkg = types.ModuleType("custom_components.unifi_unas.api")
    api_pkg.CannotConnect = Exception
    api_pkg.InvalidAuth = Exception
    api_pkg.UnexpectedResponse = Exception
    api_pkg.UnsupportedFeature = Exception
    sys.modules["custom_components.unifi_unas.api"] = api_pkg

    const_path = package_root / "const.py"
    const_spec = spec_from_file_location("custom_components.unifi_unas.const", const_path)
    if const_spec is None or const_spec.loader is None:
        raise RuntimeError("Could not load const module spec")
    const_module = module_from_spec(const_spec)
    sys.modules["custom_components.unifi_unas.const"] = const_module
    const_spec.loader.exec_module(const_module)

    sensor_spec = spec_from_file_location(
        "custom_components.unifi_unas.sensor",
        sensor_path,
    )
    if sensor_spec is None or sensor_spec.loader is None:
        raise RuntimeError("Could not load sensor module spec")
    sensor_module = module_from_spec(sensor_spec)
    sys.modules["custom_components.unifi_unas.sensor"] = sensor_module
    sensor_spec.loader.exec_module(sensor_module)
    return sensor_module


sensor_module = _load_sensor_module()


def _load_binary_sensor_module():
    root = Path(__file__).resolve().parents[1]
    package_root = root / "custom_components" / "unifi_unas"
    binary_sensor_path = package_root / "binary_sensor.py"

    binary_sensor_pkg = types.ModuleType("homeassistant.components.binary_sensor")

    @dataclass(frozen=True, kw_only=True)
    class BinarySensorEntityDescription:
        key: str
        name: str | None = None
        translation_key: str | None = None
        device_class: str | None = None
        entity_category: str | None = None
        entity_registry_enabled_default: bool = True

    class BinarySensorEntity:
        pass

    class BinarySensorDeviceClass:
        CONNECTIVITY = "connectivity"
        PROBLEM = "problem"

    binary_sensor_pkg.BinarySensorDeviceClass = BinarySensorDeviceClass
    binary_sensor_pkg.BinarySensorEntity = BinarySensorEntity
    binary_sensor_pkg.BinarySensorEntityDescription = BinarySensorEntityDescription
    sys.modules["homeassistant.components.binary_sensor"] = binary_sensor_pkg

    binary_sensor_spec = spec_from_file_location(
        "custom_components.unifi_unas.binary_sensor",
        binary_sensor_path,
    )
    if binary_sensor_spec is None or binary_sensor_spec.loader is None:
        raise RuntimeError("Could not load binary_sensor module spec")
    binary_sensor_module = module_from_spec(binary_sensor_spec)
    sys.modules["custom_components.unifi_unas.binary_sensor"] = binary_sensor_module
    binary_sensor_spec.loader.exec_module(binary_sensor_module)
    return binary_sensor_module


binary_sensor_module = _load_binary_sensor_module()


def _load_update_module():
    root = Path(__file__).resolve().parents[1]
    package_root = root / "custom_components" / "unifi_unas"
    update_path = package_root / "update.py"

    update_pkg = types.ModuleType("homeassistant.components.update")

    @dataclass(frozen=True, kw_only=True)
    class UpdateEntityDescription:
        key: str
        name: str | None = None
        translation_key: str | None = None
        icon: str | None = None
        device_class: str | None = None
        entity_category: str | None = None

    class UpdateEntity:
        pass

    class UpdateDeviceClass:
        FIRMWARE = "firmware"

    class UpdateEntityFeature:
        INSTALL = 1

    update_pkg.UpdateDeviceClass = UpdateDeviceClass
    update_pkg.UpdateEntity = UpdateEntity
    update_pkg.UpdateEntityDescription = UpdateEntityDescription
    update_pkg.UpdateEntityFeature = UpdateEntityFeature
    sys.modules["homeassistant.components.update"] = update_pkg

    exceptions_pkg = types.ModuleType("homeassistant.exceptions")
    exceptions_pkg.HomeAssistantError = Exception
    sys.modules["homeassistant.exceptions"] = exceptions_pkg

    api_pkg = types.ModuleType("custom_components.unifi_unas.api")
    api_pkg.CannotConnect = Exception
    api_pkg.InvalidAuth = Exception
    api_pkg.UnexpectedResponse = Exception
    api_pkg.UnsupportedFeature = Exception
    api_pkg.UnifiUnasApiClient = type("UnifiUnasApiClient", (), {})
    sys.modules["custom_components.unifi_unas.api"] = api_pkg

    update_spec = spec_from_file_location(
        "custom_components.unifi_unas.update",
        update_path,
    )
    if update_spec is None or update_spec.loader is None:
        raise RuntimeError("Could not load update module spec")
    update_module = module_from_spec(update_spec)
    sys.modules["custom_components.unifi_unas.update"] = update_module
    update_spec.loader.exec_module(update_module)
    return update_module


update_module = _load_update_module()


class _FakeEntry:
    entry_id = "entry-1"
    unique_id = "device-1"
    title = "UNAS"
    data = {"snapshot_buttons_enabled": True}


class _FakeUpdateClient:
    def __init__(self) -> None:
        self.unifi_installs = 0
        self.drive_installs = 0
        self.fail_next: Exception | None = None

    async def _maybe_fail(self) -> None:
        if self.fail_next is not None:
            err = self.fail_next
            self.fail_next = None
            raise err

    async def async_install_unifi_os_update(self) -> None:
        await self._maybe_fail()
        self.unifi_installs += 1

    async def async_install_drive_update(self) -> None:
        await self._maybe_fail()
        self.drive_installs += 1


class _FakeUpdateCoordinator:
    def __init__(self, data: dict | None, *, online: bool = True) -> None:
        self.data = data
        self.is_device_online = online
        self.last_update_success = online
        self.client = _FakeUpdateClient()
        self.refresh_count = 0

    async def async_request_refresh(self) -> None:
        self.refresh_count += 1


def test_throughput_aggregates_global_disk_kbps_values() -> None:
    """Per-disk KBPS values should be summed, not taken from the first disk."""
    payload = {
        "pools": [],
        "disks": [
            {"readKBPS": 1200, "writeKBPS": "1500"},
            {"readKBPS": 800, "writeKBPS": "2500"},
        ],
    }

    assert sensor_module._read_throughput_mb_s(payload) == 2.0
    assert sensor_module._write_throughput_mb_s(payload) == 4.0


def test_throughput_aggregates_nested_global_disk_kbps_values() -> None:
    """Per-disk KBPS fallback should use nested storage disk lists too."""
    payload = {
        "storage": {
            "disks": [
                {"readKBPS": 1500, "writeKBPS": 3000},
                {"readKBPS": "2500", "writeKBPS": "1000"},
            ],
        },
    }

    assert sensor_module._read_throughput_mb_s(payload) == 4.0
    assert sensor_module._write_throughput_mb_s(payload) == 4.0


def test_throughput_prefers_top_level_disk_kbps_over_nested_duplicates() -> None:
    """Duplicate nested disk lists should not double-count disk throughput."""
    payload = {
        "disks": [
            {"poolId": "pool-a", "slotId": "1", "readKBPS": 1200, "writeKBPS": 1500},
            {"poolId": "pool-a", "slotId": "2", "readKBPS": 800, "writeKBPS": 2500},
        ],
        "storage": {
            "disks": [
                {"poolId": "pool-a", "slotId": "1", "readKBPS": 1200, "writeKBPS": 1500},
                {"poolId": "pool-a", "slotId": "2", "readKBPS": 800, "writeKBPS": 2500},
            ],
        },
    }

    assert sensor_module._read_throughput_mb_s(payload) == 2.0
    assert sensor_module._write_throughput_mb_s(payload) == 4.0


def test_throughput_uses_network_io_when_storage_reports_zero() -> None:
    """Network I/O should recover live throughput when storage fields stay zero."""
    payload = {
        "readThroughput": 0,
        "writeThroughput": 0,
        "_network_io": {
            "receiveKBPS": 2500,
            "transmitKBPS": 1500,
            "timestamp": "2026-06-20T17:57:44Z",
        },
    }

    assert sensor_module._read_throughput_mb_s(payload) == 1.5
    assert sensor_module._write_throughput_mb_s(payload) == 2.5


def test_throughput_keeps_zero_when_no_non_zero_fallback_exists() -> None:
    """Idle zero remains a valid measurement when no fallback has traffic."""
    payload = {
        "readThroughput": 0,
        "writeThroughput": 0,
        "_network_io": {
            "receiveKBPS": 0,
            "transmitKBPS": 0,
        },
    }

    assert sensor_module._read_throughput_mb_s(payload) == 0
    assert sensor_module._write_throughput_mb_s(payload) == 0


def test_aggregate_sensor_properties_cover_offline_and_attributes() -> None:
    """Aggregate sensor properties should stay cheap and offline-aware."""
    payload = {
        "pools": [
            {"name": "Primary", "status": "healthy"},
            {"name": "Backup", "status": "degraded"},
        ],
        "_system": {"status": "online"},
    }
    coordinator = _FakeUpdateCoordinator(payload)

    overall = sensor_module.UnifiUnasAggregateSensor(
        coordinator,
        _FakeEntry(),
        next(
            description
            for description in sensor_module.AGGREGATE_SENSOR_TYPES
            if description.key == "overall_status"
        ),
    )
    assert overall.native_value == "degraded"
    assert overall.extra_state_attributes == {
        "pool_count": 2,
        "pool_names": ["Primary", "Backup"],
        "raw_statuses": ["healthy", "degraded"],
    }

    missing_data = sensor_module.UnifiUnasAggregateSensor(
        _FakeUpdateCoordinator(None),
        _FakeEntry(),
        next(
            description
            for description in sensor_module.AGGREGATE_SENSOR_TYPES
            if description.key == "total_storage"
        ),
    )
    assert missing_data.native_value is None
    assert missing_data.extra_state_attributes is None

    offline = sensor_module.UnifiUnasAggregateSensor(
        _FakeUpdateCoordinator({"_system": {"status": "online"}}, online=False),
        _FakeEntry(),
        next(
            description
            for description in sensor_module.AGGREGATE_SENSOR_TYPES
            if description.key == "system_status"
        ),
    )
    assert offline.available is True
    assert offline.native_value == "offline"


def test_pool_and_drive_sensor_properties_follow_current_payload() -> None:
    """Pool and drive entities should survive disappearing dynamic data."""
    pool = {
        "id": "pool-a",
        "name": "Primary",
        "status": "healthy",
        "drives": [
            {"serial": "disk-a", "status": "healthy", "temperature": 31},
            {"serial": "disk-b", "status": "failed", "temperature": 42},
        ],
    }
    coordinator = _FakeUpdateCoordinator({"pools": [pool]})
    pool_key = sensor_module._pool_key(pool, 0)
    drive_key = f"{pool_key}_{sensor_module._drive_key(pool['drives'][0], 0)}"

    pool_sensor = sensor_module.UnifiUnasPoolSensor(
        coordinator,
        _FakeEntry(),
        next(
            description
            for description in sensor_module.POOL_SENSOR_TYPES
            if description.key == "pool_status"
        ),
        pool_key,
        "Primary",
    )
    drive_sensor = sensor_module.UnifiUnasDriveSensor(
        coordinator,
        _FakeEntry(),
        next(
            description
            for description in sensor_module.DRIVE_SENSOR_TYPES
            if description.key == "drive_status"
        ),
        pool_key,
        drive_key,
        "Primary",
        "Disk A",
    )
    legacy_drive_sensor = sensor_module.UnifiUnasDriveSensor(
        coordinator,
        _FakeEntry(),
        next(
            description
            for description in sensor_module.DRIVE_SENSOR_TYPES
            if description.key == "drive_temperature"
        ),
        pool_key,
        "pool_drive_2",
        "Primary",
        "Legacy Disk",
    )

    assert pool_sensor.available is True
    assert pool_sensor.native_value == "healthy"
    assert pool_sensor.extra_state_attributes == {
        "pool_key": "pool_a",
        "pool_name": "Primary",
        "raw_status": "healthy",
    }
    assert drive_sensor.available is True
    assert drive_sensor.native_value == "optimal"
    assert drive_sensor.extra_state_attributes == {
        "pool_key": "pool_a",
        "pool_name": "Primary",
        "drive_key": "pool_a_disk_a",
        "drive_name": "Disk A",
        "raw_health": "healthy",
    }
    assert legacy_drive_sensor.native_value == 42

    coordinator.data = {"pools": []}
    assert pool_sensor.available is False
    assert pool_sensor.native_value is None
    assert pool_sensor.extra_state_attributes is None
    assert drive_sensor.available is False
    assert drive_sensor.native_value is None
    assert drive_sensor.extra_state_attributes is None


def test_binary_sensor_properties_cover_aggregate_and_dynamic_pools() -> None:
    """Binary sensors should expose problem metadata and clear stale pools."""
    pool = {
        "id": "pool-a",
        "name": "Primary",
        "status": "degraded",
        "progress": {"rebuildProgress": 42},
        "drives": [{"status": "failed"}],
    }
    coordinator = _FakeUpdateCoordinator({"pools": [pool]})

    aggregate_problem = binary_sensor_module.UnifiUnasAggregateBinarySensor(
        coordinator,
        _FakeEntry(),
        next(
            description
            for description in binary_sensor_module.AGGREGATE_BINARY_SENSOR_TYPES
            if description.key == "storage_problem"
        ),
    )
    aggregate_maintenance = binary_sensor_module.UnifiUnasAggregateBinarySensor(
        coordinator,
        _FakeEntry(),
        next(
            description
            for description in binary_sensor_module.AGGREGATE_BINARY_SENSOR_TYPES
            if description.key == "maintenance_active"
        ),
    )
    pool_key = binary_sensor_module._pool_key(pool, 0)
    pool_problem = binary_sensor_module.UnifiUnasPoolBinarySensor(
        coordinator,
        _FakeEntry(),
        next(
            description
            for description in binary_sensor_module.POOL_BINARY_SENSOR_TYPES
            if description.key == "pool_problem"
        ),
        pool_key,
        "Primary",
    )

    assert aggregate_problem.is_on is True
    assert aggregate_problem.extra_state_attributes == {
        "overall_status": "degraded",
        "at_risk_disk_count": 1,
    }
    assert aggregate_maintenance.is_on is True
    assert aggregate_maintenance.extra_state_attributes == {
        "pool_count": 1,
        "maintenance_pool_count": 1,
    }
    assert pool_problem.available is True
    assert pool_problem.is_on is True
    assert pool_problem.extra_state_attributes == {
        "pool_key": "pool_a",
        "pool_name": "Primary",
        "raw_status": "degraded",
        "rebuild_progress": 42.0,
        "sync_progress": None,
    }

    coordinator.data = None
    assert aggregate_problem.is_on is None
    assert aggregate_problem.extra_state_attributes is None

    coordinator.data = {"pools": []}
    assert pool_problem.available is False
    assert pool_problem.is_on is None
    assert pool_problem.extra_state_attributes is None


def test_update_entity_properties_and_install_paths() -> None:
    """Update entities should expose metadata and translate install failures."""
    payload = {
        "_system": {
            "hardware": {"firmwareVersion": "v4.1.9+build", "model": "UNAS"},
            "firmware": {"update": {"state": "running", "progress": 42}},
            "apps": {
                "apps": [
                    {
                        "name": "drive",
                        "display_name": "unifi drive",
                        "version": "1.2.3",
                        "latestUpdate": {"latestVersion": "1.4.0"},
                    }
                ]
            },
        }
    }
    coordinator = _FakeUpdateCoordinator(payload)
    unifi_entity = update_module.UnifiDriveUpdateEntity(
        coordinator,
        _FakeEntry(),
        update_module.UPDATE_TYPES[0],
    )
    drive_entity = update_module.UnifiDriveUpdateEntity(
        coordinator,
        _FakeEntry(),
        update_module.UPDATE_TYPES[1],
    )

    assert unifi_entity.available is True
    assert unifi_entity.installed_version == "4.1.9"
    assert unifi_entity.latest_version == "4.1.9"
    assert unifi_entity.title == "UniFi OS / UNAS"
    assert unifi_entity.in_progress is True
    assert unifi_entity.update_percentage == 42
    assert "Experimental" in unifi_entity.release_summary
    assert unifi_entity.extra_state_attributes["firmware_dependent"] is True

    assert drive_entity.latest_version == "1.4.0"
    assert drive_entity.title == "Application / Unifi Drive"

    try:
        asyncio.run(unifi_entity.async_install("9.9.9", False))
    except Exception as err:
        assert getattr(err, "translation_key", None) == "update_version_not_supported"
    else:
        raise AssertionError("version-specific install should fail")

    offline_entity = update_module.UnifiDriveUpdateEntity(
        _FakeUpdateCoordinator(payload, online=False),
        _FakeEntry(),
        update_module.UPDATE_TYPES[0],
    )
    try:
        asyncio.run(offline_entity.async_install(None, False))
    except Exception as err:
        assert getattr(err, "translation_key", None) == "device_offline"
    else:
        raise AssertionError("offline install should fail")

    coordinator.client.fail_next = update_module.CannotConnect("offline")
    try:
        asyncio.run(unifi_entity.async_install(None, False))
    except Exception as err:
        assert getattr(err, "translation_key", None) == "update_install_failed"
    else:
        raise AssertionError("failed install should translate API error")

    asyncio.run(unifi_entity.async_install(None, False))
    asyncio.run(drive_entity.async_install(None, False))
    assert coordinator.client.unifi_installs == 1
    assert coordinator.client.drive_installs == 1
    assert coordinator.refresh_count == 2


def test_update_helpers_cover_metadata_fallbacks() -> None:
    """Update helper functions should handle optional UniFi metadata shapes."""
    assert update_module._clean_version(True) is None
    assert update_module._clean_version("v1.2.3+meta") == "1.2.3"
    assert update_module._clean_text(False) is None
    assert update_module._clean_text("  Drive  ") == "Drive"

    system_device_payload = {
        "_system": {
            "latestUpdate": {"platform": "Fallback Model"},
            "devices": {"unifiOS": [{"updateAvailable": "v5.0.0"}]},
            "apps": {"controllers": [{"name": "drive", "update": {"versionRaw": "2.0.0"}}]},
        }
    }
    assert update_module._unifi_os_latest_version(system_device_payload) == "5.0.0"
    assert update_module._system_model_name(system_device_payload) == "Fallback Model"
    assert update_module._drive_latest_version(system_device_payload) == "2.0.0"
    assert update_module._drive_application_name({"_system": {"apps": {}}}) == "Drive"
    assert update_module._drive_controller({"_system": {"apps": []}}) is None
    assert update_module._nested_version({"availableVersion": "3.0.0"}) == "3.0.0"
    assert update_module._nested_version({}) is None
    assert update_module._unifi_os_update_in_progress({"_system": {}}) is None
    assert (
        update_module._unifi_os_update_in_progress(
            {"_system": {"firmware": {"update": {"state": "done"}}}}
        )
        is False
    )
    assert update_module._unifi_os_update_percentage({"_system": {}}) is None
    assert (
        update_module._unifi_os_update_percentage(
            {"_system": {"firmware": {"update": {"progress": 101}}}}
        )
        is None
    )


def test_update_entity_handles_missing_data_as_unavailable() -> None:
    """Update properties should be cheap and safe while data is missing."""
    entity = update_module.UnifiDriveUpdateEntity(
        _FakeUpdateCoordinator(None),
        _FakeEntry(),
        update_module.UPDATE_TYPES[0],
    )

    assert entity.available is False
    assert entity.installed_version is None
    assert entity.latest_version is None
    assert entity.title == "UniFi OS / UNAS"
    assert entity.in_progress is False
    assert entity.update_percentage is None


def test_storage_drive_helpers_cover_nested_and_fallback_payloads() -> None:
    """Drive helper fallbacks should normalize varied UniFi storage shapes."""
    drive = {
        "details": {
            "temperatureC": "38.4",
            "powerOnHours": "1234.6",
            "health": {"status": "FAILED"},
        }
    }

    assert sensor_module._drive_key({}, 2) == "drive_3"
    assert sensor_module._legacy_drive_index("pool_drive_2") == 1
    assert sensor_module._legacy_drive_index("drive_0") is None
    assert sensor_module._drive_name({"slotId": "4"}, 0) == "Drive 4"
    assert sensor_module._drive_temperature(drive) == 38.4
    assert sensor_module._drive_power_on_hours(drive) == 1235
    assert sensor_module._raw_drive_health(drive) == "FAILED"
    assert sensor_module._drive_health(drive) == "at_risk"
    assert sensor_module._drive_health({"healthScore": 5}) == "optimal"
    assert sensor_module._drive_health({"healthScore": 2}) == "at_risk"
    assert sensor_module._drive_health({"smart": ["not", "scalar"]}) is None
    assert sensor_module._drive_is_at_risk({"status": "SMART failure"}) is True
    assert sensor_module._drive_is_at_risk({"status": "good"}) is False


def test_drive_life_span_gates_to_ssd_wear_reporting() -> None:
    """SSD lifeSpan should map to remaining-life percent; HDDs report nothing."""
    # SSD payload (UNAS reports lifeSpan 0-100, higher is healthier).
    assert sensor_module._drive_life_span({"type": "SSD", "lifeSpan": 91}) == 91
    # HDDs omit the field entirely -> sensor stays unavailable.
    assert sensor_module._drive_life_span({"type": "HDD", "temperature": 41}) is None
    # Values are clamped into the 0-100 range and rounded to an integer.
    assert sensor_module._drive_life_span({"lifeSpan": 88.6}) == 89
    assert sensor_module._drive_life_span({"lifeSpan": 140}) == 100
    assert sensor_module._drive_life_span({"details": {"remainingLife": 73}}) == 73


def test_drive_identity_capacity_and_smart_helpers() -> None:
    """Model/capacity/SMART helpers should read the UNAS disk payload."""
    ssd = {
        "type": "SSD",
        "model": "Seagate BarraCuda Q5 ZP2000CV30001",
        "size": 2000398934016,
        "badSectorCount": 0,
        "uncorrectableSectorCount": 3,
    }
    assert sensor_module._drive_model(ssd) == "Seagate BarraCuda Q5 ZP2000CV30001"
    assert sensor_module._drive_capacity(ssd) == 2000398934016
    assert sensor_module._drive_bad_sectors(ssd) == 0
    assert sensor_module._drive_uncorrectable_sectors(ssd) == 3
    assert sensor_module._drive_media_type(ssd) == "SSD"
    # Absent fields degrade to None rather than raising.
    assert sensor_module._drive_capacity({"type": "HDD"}) is None
    assert sensor_module._drive_model({}) is None


def test_drive_name_is_media_type_aware() -> None:
    """Drive names should be suggestive so HDD/SSD slot reuse does not collide."""
    assert sensor_module._drive_name({"type": "SSD", "slotId": "1"}, 0) == "SSD 1"
    assert sensor_module._drive_name({"type": "HDD", "slotId": "1"}, 0) == "HDD 1"
    # Falls back to the generic label when the media type is unknown.
    assert sensor_module._drive_name({"slotId": "2"}, 0) == "Drive 2"
    # An explicit name always wins.
    assert sensor_module._drive_name({"type": "SSD", "name": "Cache"}, 0) == "Cache"


def test_drive_attributes_expose_smart_and_identity_metadata() -> None:
    """Per-drive attributes should carry the non-promoted SMART/identity fields."""
    drive = {
        "type": "SSD",
        "firmware": "STGSC014",
        "nvmeVersion": "1.3",
        "state": "healthy",
        "rpm": 0,
        "readErrorRate": 0,
        "smartReadErrorCount": 0,
        "smartTestSupported": False,
        "isGlobalHotSpare": False,
        "isLocalHotSpare": True,
    }
    attrs = sensor_module._drive_attributes(drive)
    assert attrs["media_type"] == "SSD"
    assert attrs["firmware"] == "STGSC014"
    assert attrs["nvme_version"] == "1.3"
    assert attrs["rpm"] == 0
    assert attrs["smart_test_supported"] is False
    assert attrs["is_local_hot_spare"] is True
    # Missing fields are simply omitted.
    assert "read_error_rate" in attrs
    assert sensor_module._drive_attributes({}) == {}


def test_cache_drives_read_top_level_cache_slots() -> None:
    """SSD cache slots live outside pools and must be enumerated separately."""
    data = {
        "pools": [{"id": "p1", "disks": [{"serial": "hdd-1"}]}],
        "disks": [{"serial": "hdd-1", "type": "HDD"}],
        "cacheSlots": [
            {"serial": "ssd-1", "type": "SSD", "lifeSpan": 91, "slotId": "1"},
            {"serial": "ssd-2", "type": "SSD", "lifeSpan": 89, "slotId": "2"},
            "not-a-dict",
        ],
    }
    cache = sensor_module._cache_drives(data)
    assert [drive["serial"] for drive in cache] == ["ssd-1", "ssd-2"]
    # Cache drives carry the SSD wear metric that data-pool HDDs lack.
    assert sensor_module._drive_life_span(cache[0]) == 91
    # No cache slots -> empty, and non-dict payloads are tolerated.
    assert sensor_module._cache_drives({"pools": []}) == []
    assert sensor_module._cache_drives(None) == []


def test_cache_status_reads_pool_cache_block() -> None:
    """Cache status should normalize the pool's SSD-cache health field."""
    healthy = {"pools": [{"id": "p1", "cache": {"status": "fullyOperational"}}]}
    degraded = {"pools": [{"id": "p1", "cache": {"status": "degraded"}}]}
    assert sensor_module._cache_status(healthy) == "healthy"
    assert sensor_module._cache_status(degraded) == "degraded"
    # A pool without an SSD cache reports nothing (sensor stays unavailable).
    assert sensor_module._cache_status({"pools": [{"id": "p1"}]}) is None
    assert sensor_module._cache_status({"pools": []}) is None


def test_ssd_wear_averages_complement_of_lifespan() -> None:
    """SSD wear should be the average of (100 - lifeSpan) across all SSDs."""
    data = {
        "pools": [{"id": "p1", "disks": [{"serial": "hdd-1", "type": "HDD"}]}],
        "cacheSlots": [
            {"serial": "ssd-1", "type": "SSD", "lifeSpan": 91},
            {"serial": "ssd-2", "type": "SSD", "lifeSpan": 89},
        ],
    }
    # (100-91 + 100-89) / 2 = (9 + 11) / 2 = 10.0
    assert sensor_module._ssd_wear(data) == 10.0
    # Data-pool SSDs are included too, HDDs (no lifeSpan) are ignored.
    mixed = {"pools": [{"id": "p1", "disks": [{"serial": "s", "lifeSpan": 80}]}]}
    assert sensor_module._ssd_wear(mixed) == 20.0
    # No SSDs -> unavailable.
    assert sensor_module._ssd_wear({"pools": [{"disks": [{"type": "HDD"}]}]}) is None


def test_storage_pool_drive_collection_paths() -> None:
    """Pool drive extraction should cover direct, nested and referenced disks."""
    direct_pool = {"drives": [{"serial": "a"}, "bad"]}
    nested_pool = {"raid": {"disks": [{"serial": "b"}]}}
    raid_tree_pool = {
        "raidGroups": {
            "group": {
                "members": [
                    {
                        "serial": "c",
                        "slotId": "1",
                        "poolId": "pool-c",
                        "healthScore": 5,
                    }
                ]
            }
        }
    }
    global_pool = {
        "id": "pool-d",
        "__global_disks": [
            {"serial": "d", "pool": {"id": "pool-d"}},
            {"serial": "ignored", "poolId": "other"},
        ],
    }
    raid_ref_pool = {
        "activeRaidGroupId": "rg-1",
        "__global_disks": [
            {"serial": "e", "raidGroupId": "rg-1"},
            {"serial": "ignored", "raidGroupId": "rg-2"},
        ],
    }

    assert sensor_module._pool_drives(direct_pool) == [{"serial": "a"}]
    assert sensor_module._pool_drives(nested_pool) == [{"serial": "b"}]
    assert sensor_module._pool_drives(raid_tree_pool)[0]["serial"] == "c"
    assert sensor_module._pool_drives(global_pool)[0]["serial"] == "d"
    assert sensor_module._pool_drives(raid_ref_pool)[0]["serial"] == "e"
    assert sensor_module._pool_drive_count({"diskCount": "4"}) == 4
    assert sensor_module._pool_at_risk_drive_count({}) == 0
    assert sensor_module._pool_average_drive_temperature({}) is None
    assert sensor_module._pool_average_drive_temperature(
        {"disks": [{"temperature": 30}, {"temperature": 32}]}
    ) == 31.0


def test_storage_pool_list_and_identity_fallbacks() -> None:
    """Pool discovery should accept nested and alternate payload shapes."""
    payload = {
        "storage": {
            "volumeList": [
                {"name": "Main", "status": "ok", "capacity": 100},
                {"serial": "disk-only", "status": "ok", "capacity": 100},
                {"data": {"ignored": True}, "name": "wrapper", "status": "ok"},
            ],
            "disks": [
                {"serial": "disk-1", "poolId": "Main", "healthScore": 4},
                {"serial": "disk-1", "temperature": 35},
            ],
        }
    }

    pools = sensor_module._pools(payload)

    assert len(pools) == 1
    assert pools[0]["name"] == "Main"
    assert pools[0]["__global_disks"][0]["temperature"] == 35
    assert sensor_module._pool_key({}, 1) == "pool_2"
    assert sensor_module._pool_from_key(payload, "pool_1")[1] == 0
    assert sensor_module._pool_from_key(payload, "main")[1] == 0
    assert sensor_module._pool_from_key(payload, "missing") == (None, None)
    assert sensor_module._pool_name({"id": "550e8400-e29b-41d4-a716-446655440000"}, 0) == "Pool 1"
    assert sensor_module._pool_name({"poolId": "tank"}, 0) == "tank"


def test_storage_pool_status_progress_and_aggregates() -> None:
    """Pool status and progress helpers should cover nested variants."""
    healthy = {"status": {"state": "OK"}, "capacity": 10, "used": 1}
    degraded = {
        "condition": "Disk failure",
        "drives": [{"health": "ok"}, {"health": "failed"}],
        "progress": {"rebuildProgress": "42"},
    }
    syncing = {
        "state": "Synchronizing",
        "raid": "RAID5",
        "sync": {"percentComplete": "55"},
    }
    payload = {"pools": [healthy, degraded, syncing]}

    assert sensor_module._pool_status(healthy) == "healthy"
    assert sensor_module._pool_status(degraded) == "degraded"
    assert sensor_module._pool_status({"status": ["bad"]}) is None
    assert sensor_module._aggregate_status(payload) == "degraded"
    assert sensor_module._aggregate_status({"pools": [{"name": "Unknown"}]}) is None
    assert sensor_module._degraded_pool_count(payload) == 1
    assert sensor_module._at_risk_disk_count(payload) == 1
    assert sensor_module._pool_has_problem(degraded) is True
    assert sensor_module._pool_in_maintenance(degraded) is True
    assert sensor_module._pool_in_maintenance(syncing) is True
    assert sensor_module._pool_raid_level(syncing) == "RAID5"
    assert sensor_module._pool_raid_level({"raid": {"level": "RAID1"}}) == "RAID1"
    assert sensor_module._pool_rebuild_progress(degraded) == 42.0
    assert sensor_module._pool_sync_progress(syncing) == 55.0
    assert sensor_module._pool_progress(
        {"tree": {"rebuild": {"pct": "bad"}}},
        primary_keys=("missing",),
        context_hints=("rebuild",),
    ) is None


def test_throughput_parses_nested_units_and_invalid_values() -> None:
    """Throughput helpers should parse dict/list/unit variants defensively."""
    throughput_module = __import__(
        "custom_components.unifi_unas.storage_throughput",
        fromlist=["_throughput_unit_hints"],
    )
    unit_hints = throughput_module._throughput_unit_hints()

    assert sensor_module._parse_throughput_value(1200, unit_hints, key_norm="readkbps") == 1.2
    assert sensor_module._parse_throughput_value("1.5 GiB/s", unit_hints) == 1610.612736
    assert sensor_module._parse_throughput_value("9 XB/s", unit_hints) == 9
    assert sensor_module._parse_throughput_value({"rate": 2, "unit": "KiB/s"}, unit_hints) == 0.002048
    assert sensor_module._parse_throughput_value({"unit": "MB/s"}, unit_hints) is None
    assert sensor_module._parse_throughput_value(["bad"], unit_hints) is None

    nested = {
        "data": [
            {"ignored": "bad"},
            {"metrics": {"networkRead": {"value": 3, "unit": "MB/s"}}},
        ]
    }
    assert sensor_module._read_throughput_mb_s(nested) == 3
    assert sensor_module._throughput_from_disks_mb_s(
        {"disks": [{"readKBPS": "bad"}]},
        direction="read",
    ) is None


def test_snapshot_inventory_sensor_exposes_compact_inventory_metadata() -> None:
    """Snapshot inventory sensors should expose count plus compact metadata."""
    target = {
        "id": "shared-1",
        "type": "shared",
        "name": "Shared",
        "enabled": True,
        "total_count": 1,
    }
    coordinator = types.SimpleNamespace(
        is_device_online=True,
        snapshot_settings=[target],
        snapshot_inventory={
            "shared_shared-1": {
                "snapshot_count": 2,
                "snapshot_count_source": "inventory_total",
                "returned_snapshot_count": 2,
                "locked_count": 1,
                "inventory_total": 2,
                "inventory_offset": 0,
                "inventory_limit": 256,
                "inventory_truncated": False,
                "latest_snapshot_time": "2026-05-16T12:00:00Z",
                "oldest_snapshot_time": "2026-05-15T12:00:00Z",
                "latest_snapshot_id": "new",
                "oldest_snapshot_id": "old",
                "latest_snapshot_name": "New",
                "oldest_snapshot_name": "Old",
                "latest_snapshot_description": "Before maintenance",
                "oldest_snapshot_description": None,
                "snapshot_ids": ["new", "old"],
                "snapshot_names": ["New", "Old"],
                "snapshot_descriptions": ["Before maintenance"],
                "snapshot_metadata_truncated": False,
                "snapshot_metadata_limit": 10,
                "recent_snapshots": [
                    {
                        "id": "new",
                        "name": "New",
                        "description": "Before maintenance",
                        "locked": True,
                        "created_at": "2026-05-16T12:00:00Z",
                    }
                ],
                "recent_snapshot_count": 1,
                "recent_snapshot_limit": 10,
            }
        },
        snapshot_inventory_errors={},
    )

    entity = sensor_module.UnifiUnasSnapshotInventorySensor(
        coordinator,
        _FakeEntry(),
        target,
    )

    assert entity.native_value == 2
    assert entity._attr_unique_id == "device-1_snapshot_shared_shared_1_inventory"
    attributes = entity.extra_state_attributes
    assert attributes["snapshot_inventory_available"] is True
    assert attributes["snapshot_inventory_status"] == "ok"
    assert attributes["snapshot_count_source"] == "inventory_total"
    assert attributes["returned_snapshot_count"] == 2
    assert attributes["inventory_locked_count"] == 1
    assert attributes["inventory_total"] == 2
    assert attributes["latest_snapshot_id"] == "new"
    assert attributes["latest_snapshot_description"] == "Before maintenance"
    assert attributes["snapshot_ids"] == ["new", "old"]
    assert attributes["snapshot_metadata_truncated"] is False
    assert attributes["snapshot_metadata_limit"] == 10
    assert attributes["recent_snapshots"][0]["id"] == "new"


def test_snapshot_inventory_sensor_falls_back_to_settings_count() -> None:
    """Inventory sensors should still show settings count when list reads fail."""
    target = {
        "id": "mydrive-1",
        "type": "mydrive",
        "name": "Backup User",
        "enabled": True,
        "total_count": 3,
    }
    coordinator = types.SimpleNamespace(
        is_device_online=True,
        snapshot_settings=[target],
        snapshot_inventory={},
        snapshot_inventory_errors={"mydrive_mydrive-1": "unsupported"},
    )
    entity = sensor_module.UnifiUnasSnapshotInventorySensor(
        coordinator,
        _FakeEntry(),
        target,
    )

    assert entity.native_value == 3
    assert entity.extra_state_attributes["snapshot_inventory_available"] is False
    assert entity.extra_state_attributes["snapshot_inventory_status"] == "unsupported"
    assert (
        entity.extra_state_attributes["snapshot_count_source"]
        == "snapshot_settings_total_count"
    )


def test_snapshot_inventory_sensor_tolerates_malformed_inventory_state() -> None:
    """Malformed inventory runtime data should fall back to settings metadata."""
    target = {
        "id": "shared-2",
        "type": "shared",
        "name": "Shared",
        "enabled": True,
        "total_count": 4,
    }
    coordinator = types.SimpleNamespace(
        is_device_online=True,
        snapshot_settings=[target],
        snapshot_inventory=["bad"],
        snapshot_inventory_errors=["also bad"],
    )
    entity = sensor_module.UnifiUnasSnapshotInventorySensor(
        coordinator,
        _FakeEntry(),
        target,
    )

    assert entity.native_value == 4
    attributes = entity.extra_state_attributes
    assert attributes["snapshot_inventory_available"] is False
    assert attributes["snapshot_inventory_status"] == "fallback"
    assert attributes["recent_snapshots"] == []
    assert attributes["snapshot_metadata_truncated"] is False
    assert attributes["snapshot_metadata_limit"] == 10


def test_throughput_keeps_explicit_aggregate_values() -> None:
    """Explicit aggregate throughput should still take precedence over disk sums."""
    payload = {
        "readThroughput": "31.5 MB/s",
        "writeThroughput": "67.25 MB/s",
        "disks": [
            {"readKBPS": 1200, "writeKBPS": 1500},
            {"readKBPS": 800, "writeKBPS": 2500},
        ],
    }

    assert sensor_module._read_throughput_mb_s(payload) == 31.5
    assert sensor_module._write_throughput_mb_s(payload) == 67.25


def test_storage_parser_matches_global_disks_to_multiple_pools() -> None:
    """Pool helpers should map global disks to their owning pool."""
    payload = {
        "pools": [
            {
                "id": "pool-a",
                "name": "Pool A",
                "capacity": 10_000,
                "used": 4_000,
                "state": "healthy",
            },
            {
                "id": "pool-b",
                "name": "Pool B",
                "size": 20_000,
                "used": 5_000,
                "status": "degraded",
            },
        ],
        "disks": [
            {"poolId": "pool-a", "temperature": 31, "healthScore": 5},
            {"poolId": "pool-a", "temperature": 35, "healthScore": 5},
            {"poolId": "pool-b", "temperature": 40, "healthScore": 2},
        ],
    }

    pools = sensor_module._pools(payload)

    assert len(pools) == 2
    assert sensor_module._pool_drive_count(pools[0]) == 2
    assert sensor_module._pool_drive_count(pools[1]) == 1
    assert sensor_module._pool_average_drive_temperature(pools[0]) == 33.0
    assert sensor_module._pool_at_risk_drive_count(pools[1]) == 1
    assert sensor_module._aggregate_status(payload) == "degraded"


def test_storage_capacity_uses_nested_storage_summaries() -> None:
    """Capacity helpers should handle nested summary payload variants."""
    payload = {
        "storage": {
            "totalStorageBytes": 20_000,
            "usedStorageBytes": 8_000,
            "availableStorageBytes": 12_000,
        },
        "pools": [
            {
                "name": "Pool A",
                "summary": {
                    "totalSize": 10_000,
                    "freeSize": 6_000,
                },
            }
        ],
    }
    pool = sensor_module._pools(payload)[0]

    assert sensor_module._aggregate_capacity(payload) == 20_000
    assert sensor_module._aggregate_usage(payload) == 8_000
    assert sensor_module._aggregate_available(payload) == 12_000
    assert sensor_module._pool_capacity(pool) == 10_000
    assert sensor_module._pool_usage(pool) == 4_000
    assert sensor_module._pool_available(pool) == 6_000


def test_aggregate_capacity_ignores_generic_response_metadata() -> None:
    """Generic root total/used/free counters must not override pool bytes."""
    payload = {
        "total": 2,
        "used": 1,
        "free": 1,
        "pools": [
            {
                "name": "Pool A",
                "totalBytes": 10_000,
                "usedBytes": 4_000,
            },
            {
                "name": "Pool B",
                "totalBytes": 20_000,
                "usedBytes": 6_000,
            },
        ],
    }

    assert sensor_module._aggregate_capacity(payload) == 30_000
    assert sensor_module._aggregate_usage(payload) == 10_000
    assert sensor_module._aggregate_available(payload) == 20_000


def test_aggregate_capacity_ignores_nested_generic_response_metadata() -> None:
    """Generic nested counters should not override pool-derived byte values."""
    payload = {
        "storage": {
            "total": 2,
            "used": 1,
            "free": 1,
        },
        "pools": [
            {
                "name": "Pool A",
                "totalBytes": 10_000,
                "usedBytes": 4_000,
            }
        ],
    }

    assert sensor_module._aggregate_capacity(payload) == 10_000
    assert sensor_module._aggregate_usage(payload) == 4_000
    assert sensor_module._aggregate_available(payload) == 6_000


def test_storage_parser_reads_nested_volume_payloads() -> None:
    """Pool discovery should support nested volume-style payloads."""
    payload = {
        "storage": {
            "volumes": [
                {
                    "id": "pool-a",
                    "label": "Main",
                    "state": "healthy",
                    "usage": {
                        "total": 50_000,
                        "used": 25_000,
                    },
                }
            ],
            "disks": [
                {
                    "serial": "SLOT1",
                    "pool": {"id": "pool-a"},
                    "slotId": "1",
                    "smart": {"temperature": "41.2", "powerOnHours": 1234},
                }
            ],
        },
    }

    pools = sensor_module._pools(payload)
    drives = sensor_module._pool_drives(pools[0])

    assert len(pools) == 1
    assert sensor_module._pool_name(pools[0], 0) == "Main"
    assert sensor_module._pool_status(pools[0]) == "healthy"
    assert sensor_module._pool_usage(pools[0]) == 25_000
    assert len(drives) == 1
    assert sensor_module._drive_key(drives[0], 0) == "slot1"
    assert sensor_module._drive_temperature(drives[0]) == 41.2
    assert sensor_module._drive_power_on_hours(drives[0]) == 1234


def test_storage_parser_recurses_into_data_list_wrappers() -> None:
    """Data/result list wrappers should not become synthetic pool entries."""
    payload = {
        "data": [
            {
                "volumes": [
                    {
                        "id": "pool-a",
                        "label": "Main",
                        "state": "healthy",
                        "usage": {
                            "total": 50_000,
                            "used": 25_000,
                        },
                    }
                ],
                "disks": [
                    {
                        "serial": "SLOT1",
                        "pool": {"id": "pool-a"},
                        "slotId": "1",
                        "smart": {"temperature": "41.2"},
                    }
                ],
            }
        ]
    }

    pools = sensor_module._pools(payload)
    drives = sensor_module._pool_drives(pools[0])

    assert len(pools) == 1
    assert sensor_module._pool_name(pools[0], 0) == "Main"
    assert sensor_module._pool_capacity(pools[0]) == 50_000
    assert len(drives) == 1
    assert sensor_module._drive_key(drives[0], 0) == "slot1"


def test_storage_parser_keeps_direct_and_nested_pool_list_items() -> None:
    """Mixed explicit pool lists should keep direct pools and nested wrappers."""
    payload = {
        "storagePools": [
            {"id": "pool-a", "label": "A", "state": "healthy"},
            {
                "volumes": [
                    {"id": "pool-b", "label": "B", "state": "degraded"}
                ]
            },
        ]
    }

    pools = sensor_module._pools(payload)

    assert len(pools) == 2
    assert sensor_module._pool_name(pools[0], 0) == "A"
    assert sensor_module._pool_name(pools[1], 1) == "B"


def test_storage_parser_preserves_outer_explicit_pool_entries() -> None:
    """Explicit pool entries should not be replaced by nested child lists."""
    payload = {
        "storagePools": [
            {
                "id": "pool-a",
                "label": "A",
                "state": "healthy",
                "volumes": [
                    {"id": "child-volume", "label": "Child", "state": "degraded"}
                ],
            }
        ]
    }

    pools = sensor_module._pools(payload)

    assert len(pools) == 1
    assert sensor_module._pool_name(pools[0], 0) == "A"


def test_storage_parser_filters_metadata_from_explicit_pool_lists() -> None:
    """Explicit pool lists should ignore metadata wrappers without pool shape."""
    payload = {
        "storagePools": [
            {"metadata": {"total": 1}},
            {
                "volumes": [
                    {"id": "pool-a", "label": "A", "state": "healthy"}
                ]
            },
        ]
    }

    pools = sensor_module._pools(payload)

    assert len(pools) == 1
    assert sensor_module._pool_name(pools[0], 0) == "A"


def test_storage_parser_collects_disks_from_all_data_wrappers() -> None:
    """Every wrapper's disk list should be available to parsed pools."""
    payload = {
        "data": [
            {
                "volumes": [
                    {"id": "pool-a", "label": "A", "state": "healthy"},
                ],
                "disks": [
                    {
                        "serial": "SLOT1",
                        "pool": {"id": "pool-a"},
                        "slotId": "1",
                        "smart": {"temperature": 31},
                    }
                ],
            },
            {
                "volumes": [
                    {"id": "pool-b", "label": "B", "state": "healthy"},
                ],
                "disks": [
                    {
                        "serial": "SLOT2",
                        "pool": {"id": "pool-b"},
                        "slotId": "2",
                        "smart": {"temperature": 42},
                    }
                ],
            },
        ]
    }

    pools = sensor_module._pools(payload)

    assert len(pools) == 2
    assert sensor_module._pool_drive_count(pools[0]) == 1
    assert sensor_module._pool_drive_count(pools[1]) == 1
    assert sensor_module._pool_average_drive_temperature(pools[0]) == 31.0
    assert sensor_module._pool_average_drive_temperature(pools[1]) == 42.0


def test_storage_parser_merges_duplicate_global_disk_records() -> None:
    """Deduped disk records should keep richer pool and SMART fields."""
    payload = {
        "pools": [{"id": "pool-a", "label": "A", "state": "healthy"}],
        "disks": [
            {
                "serial": "SLOT1",
                "poolId": "pool-a",
                "temperature": 31,
                "healthScore": 5,
            }
        ],
        "storage": {
            "disks": [
                {
                    "serial": "SLOT1",
                    "slotId": "1",
                }
            ]
        },
    }

    pools = sensor_module._pools(payload)

    assert sensor_module._pool_drive_count(pools[0]) == 1
    assert sensor_module._pool_average_drive_temperature(pools[0]) == 31.0


def test_storage_parser_matches_global_disks_by_pool_uuid() -> None:
    """Global disk matching should use pool UUID/name references, not only id."""
    payload = {
        "pools": [{"uuid": "pool-uuid", "label": "A", "state": "healthy"}],
        "disks": [
            {
                "serial": "SLOT1",
                "poolUuid": "pool-uuid",
                "temperature": 31,
            }
        ],
    }

    pools = sensor_module._pools(payload)

    assert sensor_module._pool_drive_count(pools[0]) == 1
    assert sensor_module._pool_average_drive_temperature(pools[0]) == 31.0


def test_storage_parser_matches_disks_by_alternate_pool_identifiers() -> None:
    """Alternative firmware pool and disk identifiers should be matched."""
    payload = {
        "storagePools": [
            {
                "poolId": "pool-a",
                "state": "healthy",
                "capacity": 10_000,
            }
        ],
        "disks": [
            {
                "storagePoolId": "pool-a",
                "slotId": "1",
                "temperature": 31,
            }
        ],
    }

    pools = sensor_module._pools(payload)

    assert len(pools) == 1
    assert sensor_module._pool_key(pools[0], 0) == "pool_a"
    assert sensor_module._pool_drive_count(pools[0]) == 1
    assert sensor_module._pool_average_drive_temperature(pools[0]) == 31.0


def test_pool_key_keeps_legacy_name_precedence_over_new_pool_ids() -> None:
    """New firmware pool ids should not rewrite existing name-based entity ids."""
    pool = {
        "name": "Primary Pool",
        "label": "Primary Label",
        "poolId": "firmware-pool-id",
        "storagePoolId": "firmware-storage-pool-id",
        "volumeId": "firmware-volume-id",
        "state": "healthy",
        "capacity": 10_000,
    }

    assert sensor_module._pool_key(pool, 0) == "primary_pool"


def test_storage_parser_rejects_disk_shaped_pool_reference_records() -> None:
    """Pool-reference disk records in wrappers must not become pool entries."""
    payload = {
        "data": [
            {
                "slotId": "1",
                "poolId": "pool-a",
                "status": "healthy",
                "capacity": 10_000,
            }
        ]
    }

    assert sensor_module._pools(payload) == []


def test_explicit_pool_list_rejects_sparse_disk_reference_records() -> None:
    """Explicit pool lists should not promote sparse disk reference records."""
    payload = {
        "storagePools": [
            {
                "slotId": "1",
                "storagePoolId": "pool-a",
                "status": "healthy",
            }
        ]
    }

    assert sensor_module._pools(payload) == []


def test_storage_parser_preserves_nested_smart_when_deduping_disks() -> None:
    """Scalar SMART state should not replace richer nested SMART metrics."""
    payload = {
        "pools": [{"id": "pool-a", "label": "A", "state": "healthy"}],
        "disks": [
            {
                "serial": "SLOT1",
                "poolId": "pool-a",
                "smart": "passed",
            }
        ],
        "storage": {
            "disks": [
                {
                    "serial": "SLOT1",
                    "smart": {"temperature": 41, "powerOnHours": 1234},
                }
            ]
        },
    }

    pools = sensor_module._pools(payload)
    drives = sensor_module._pool_drives(pools[0])

    assert sensor_module._drive_temperature(drives[0]) == 41.0
    assert sensor_module._drive_power_on_hours(drives[0]) == 1234
    assert sensor_module._drive_health(drives[0]) == "optimal"


def test_storage_parser_uses_later_duplicate_disk_scalar_values() -> None:
    """Conflicting duplicate disk scalars should use the later payload value."""
    payload = {
        "pools": [{"id": "pool-a", "label": "A", "state": "healthy"}],
        "disks": [
            {
                "serial": "SLOT1",
                "poolId": "pool-a",
                "health": "healthy",
            }
        ],
        "storage": {
            "disks": [
                {
                    "serial": "SLOT1",
                    "health": "failed",
                }
            ]
        },
    }

    pools = sensor_module._pools(payload)
    drives = sensor_module._pool_drives(pools[0])

    assert sensor_module._drive_health(drives[0]) == "at_risk"
    assert sensor_module._pool_at_risk_drive_count(pools[0]) == 1


def test_storage_parser_falls_back_when_top_level_pools_is_empty() -> None:
    """Empty top-level pools should not block nested pool discovery."""
    payload = {
        "pools": [],
        "storage": {
            "volumes": [
                {
                    "id": "pool-a",
                    "label": "Main",
                    "state": "healthy",
                    "usage": {"total": 50_000, "used": 25_000},
                }
            ]
        },
    }

    pools = sensor_module._pools(payload)

    assert len(pools) == 1
    assert sensor_module._pool_name(pools[0], 0) == "Main"
    assert sensor_module._pool_usage(pools[0]) == 25_000


def test_storage_parser_does_not_treat_state_only_disk_records_as_pools() -> None:
    """Weak disk-shaped objects in data wrappers should not become pools."""
    payload = {
        "data": [
            {"id": "disk-0", "state": "online"},
            {"serial": "disk-1", "slotId": "1", "state": "online"},
            {"serial": "disk-2", "slotId": "2", "size": 10_000, "state": "online"},
        ]
    }

    assert sensor_module._pools(payload) == []


def test_storage_parser_accepts_sparse_explicit_pool_lists() -> None:
    """Explicit pool list keys should not need the generic wrapper signature."""
    payload = {"storagePools": [{"id": "pool-a", "state": "healthy"}]}

    pools = sensor_module._pools(payload)

    assert len(pools) == 1
    assert sensor_module._pool_status(pools[0]) == "healthy"


def test_pool_status_extracts_nested_health_status() -> None:
    """Mapping-valued health fields should not become literal state strings."""
    assert sensor_module._pool_status({"health": {"status": "healthy"}}) == "healthy"
    assert sensor_module._pool_status({"health": {"state": "degraded"}}) == "degraded"


def test_drive_like_filter_ignores_container_like_nodes() -> None:
    """Only drive-like nested entries should be collected from raid payloads."""
    payload = {
        "raidGroups": [
            {
                "id": "rg-main",
                "status": "active",
                "state": "online",
                "slotId": "1",
                "poolId": "pool-1",
            },
            {
                "name": "Bay 1",
                "poolId": "pool-1",
                "slotId": "1",
                "temperature": 34.0,
                "healthScore": 5,
            },
            {"children": [{"serial": "SLOT2", "poolId": "pool-1", "temp": 31.0}]},
        ]
    }

    drives = sensor_module._collect_drive_like_dicts(payload["raidGroups"])

    assert len(drives) == 2
    assert any(drive.get("serial") == "SLOT2" for drive in drives)
    assert any(drive.get("name") == "Bay 1" and drive.get("healthScore") == 5 for drive in drives)
    assert not any(
        not item.get("serial") and item.get("status") == "online"
        for item in drives
    )


def test_drive_like_filter_keeps_identity_only_raid_members() -> None:
    """Drive entries with identity and placement should not require metrics."""
    payload = {
        "raidGroups": [
            {
                "id": "rg-main",
                "status": "active",
                "state": "online",
                "slotId": "1",
                "poolId": "pool-1",
            },
            {"serial": "SLOT2", "poolId": "pool-1", "slotId": "2"},
        ]
    }

    drives = sensor_module._collect_drive_like_dicts(payload["raidGroups"])

    assert drives == [{"serial": "SLOT2", "poolId": "pool-1", "slotId": "2"}]


def test_system_metadata_helpers_extract_unifi_os_values() -> None:
    """System metadata should expose the values shown in UniFi OS."""
    payload = {
        "_system": {
            "ip": "192.0.2.10",
            "uptime": 41724.48,
            "deviceState": "updateAvailable",
            "hardware": {"firmwareVersion": "5.0.17"},
            "cpu": {"temperature": 52.9},
            "apps": {
                "controllers": [
                    {
                        "name": "drive",
                        "version": "4.1.16",
                        "versionRaw": "4.1.16",
                    }
                ]
            },
        }
    }

    assert sensor_module._system_ip(payload) == "192.0.2.10"
    assert sensor_module._system_uptime_hours(payload) == 11.6
    assert sensor_module._unifi_os_version(payload) == "5.0.17"
    assert sensor_module._drive_version(payload) == "4.1.16"
    assert sensor_module._cpu_temperature(payload) == 52.9
    assert sensor_module._system_status(payload) == "update_available"


def test_system_metadata_helpers_handle_alternate_network_and_app_shapes() -> None:
    """System metadata should tolerate common UniFi OS payload variants."""
    payload = {
        "_system": {
            "interfaces": [
                {"ipv4": "127.0.0.1"},
                {"ipAddress": "198.51.100.20/24"},
            ],
            "uptimeMs": 7_200_000,
            "cpuTemperature": "48.5",
            "firmware_version": "5.0.18",
            "applications": [
                {
                    "slug": "unifi-drive",
                    "currentVersion": "4.2.0",
                }
            ],
        }
    }

    assert sensor_module._system_ip(payload) == "198.51.100.20"
    assert sensor_module._system_uptime_hours(payload) == 2.0
    assert sensor_module._cpu_temperature(payload) == 48.5
    assert sensor_module._unifi_os_version(payload) == "5.0.18"
    assert sensor_module._drive_version(payload) == "4.2.0"


def test_system_uptime_readable_formats_human_duration() -> None:
    """Readable uptime should break hours into compact d/h units."""
    # 73.3 h -> 3d 1h (whole-hour granularity, HA short-unit convention).
    assert (
        sensor_module._system_uptime_readable({"_system": {"uptime": 73.3 * 3600}})
        == "3d 1h"
    )
    # Long uptime shows up to three most-significant units.
    assert (
        sensor_module._system_uptime_readable({"_system": {"uptime": 1500 * 3600}})
        == "2mo 2d 12h"
    )
    # Under an hour falls back to minutes.
    assert (
        sensor_module._system_uptime_readable({"_system": {"uptime": 30 * 60}})
        == "30m"
    )
    # No uptime data -> None (sensor unavailable).
    assert sensor_module._system_uptime_readable({"_system": {}}) is None


def test_cpu_temperature_is_rounded_to_recorded_precision() -> None:
    """CPU temperature states should not churn on insignificant payload jitter."""
    assert (
        sensor_module._cpu_temperature({"_system": {"cpuTemperature": 48.54}})
        == 48.5
    )
    assert sensor_module._cpu_temperature({"_system": {"cpu": {"temp": 48.55}}}) == 48.5
    assert (
        sensor_module._cpu_temperature(
            {"_system": {"thermal": {"temperature": 48.56}}}
        )
        == 48.6
    )


def test_system_ip_accepts_ipv6_literals() -> None:
    """System IP monitoring should support IPv6 payload shapes."""
    payload = {"_system": {"ip": "[2001:0db8::10]"}}

    assert sensor_module._system_ip(payload) == "2001:db8::10"


def test_cpu_percent_scales_device_info_load_fraction() -> None:
    """CPU usage should convert the 0-1 device-info load into a percentage."""
    assert (
        sensor_module._cpu_percent({"_device_info": {"cpu": {"currentload": 0.156}}})
        == 15.6
    )
    # A value above 1 is assumed to already be a percentage.
    assert (
        sensor_module._cpu_percent({"_device_info": {"cpu": {"currentload": 42}}})
        == 42.0
    )
    assert sensor_module._cpu_percent({"_device_info": {"cpu": {}}}) is None


def test_memory_percent_derives_used_from_available() -> None:
    """Memory usage should use the available-memory basis when present."""
    payload = {
        "_device_info": {
            "memory": {"free": 404736, "total": 3970688, "available": 1417728}
        }
    }

    assert sensor_module._memory_percent(payload) == 64.3


def test_memory_percent_falls_back_to_free_then_used() -> None:
    """Memory usage should tolerate payloads without an available field."""
    assert (
        sensor_module._memory_percent(
            {"_device_info": {"memory": {"total": 1000, "free": 250}}}
        )
        == 75.0
    )
    assert (
        sensor_module._memory_percent(
            {"_device_info": {"memory": {"total": 1000, "used": 400}}}
        )
        == 40.0
    )
    assert sensor_module._memory_percent({"_device_info": {"memory": {}}}) is None



def test_system_ip_falls_back_to_nested_ipv6_interfaces() -> None:
    """Nested network interfaces should expose IPv6 when IPv4 is unavailable."""
    payload = {
        "_system": {
            "interfaces": [
                {"ipv4": "127.0.0.1"},
                {"ipv6Address": "2001:0db8::20/64"},
            ]
        }
    }

    assert sensor_module._system_ip(payload) == "2001:db8::20"


def test_system_ip_reads_deep_network_address_lists() -> None:
    """System IP monitoring should handle network wrappers with address lists."""
    payload = {
        "_system": {
            "network": {
                "interfaces": [
                    {"addresses": ["127.0.0.1/8", "[2001:0db8::30]/64"]},
                ]
            }
        }
    }

    assert sensor_module._system_ip(payload) == "2001:db8::30"


def test_drive_version_skips_matching_app_entries_without_versions() -> None:
    """Drive version lookup should keep scanning after empty matching entries."""
    payload = {
        "_system": {
            "applications": [
                {"slug": "unifi-drive"},
                {"id": "drive", "currentVersion": "4.2.1"},
            ],
        }
    }

    assert sensor_module._drive_version(payload) == "4.2.1"


def test_system_status_prefers_device_online_offline() -> None:
    """Device online/offline status should override generic deviceState text."""
    payload_online = {
        "_system": {
            "deviceState": "setup",
            "devices": {"unifiOS": [{"status": "online"}]},
        }
    }
    payload_offline = {
        "_system": {
            "deviceState": "updateAvailable",
            "devices": {"unifiOS": [{"status": "offline"}]},
        }
    }

    assert sensor_module._system_status(payload_online) == "online"
    assert sensor_module._system_status(payload_offline) == "offline"


def test_system_status_uses_offline_system_marker() -> None:
    """Synthetic offline marker on `_system` should force offline status."""
    payload = {"_system": {"status": "offline", "deviceState": "online"}}
    assert sensor_module._system_status(payload) == "offline"


def test_system_status_prefers_nested_offline_over_top_level_online() -> None:
    """Nested device offline status should override stale top-level online."""
    payload = {
        "_system": {
            "status": "online",
            "devices": {"unifiOS": [{"status": "offline"}]},
        }
    }

    assert sensor_module._system_status(payload) == "offline"


def test_system_status_preserves_top_level_status_when_nested_status_is_unknown() -> None:
    """Unknown nested device status should not erase top-level status."""
    payload = {
        "_system": {
            "status": "online",
            "devices": {"unifiOS": [{"status": "setup"}]},
        }
    }

    assert sensor_module._system_status(payload) == "online"


def test_system_status_prefers_device_state_over_top_level_online() -> None:
    """Richer deviceState should override a generic top-level online marker."""
    payload = {
        "_system": {
            "status": "online",
            "deviceState": "updateAvailable",
            "devices": {"unifiOS": [{"status": "setup"}]},
        }
    }

    assert sensor_module._system_status(payload) == "update_available"


def test_system_status_maps_updateavailable_status_field() -> None:
    """`_system.status` should map update-available to the sensor state."""
    payload = {"_system": {"status": "updateAvailable"}}
    assert sensor_module._system_status(payload) == "update_available"


def test_system_status_prefers_device_state_over_stale_updateavailable_status() -> None:
    """Device state should override a stale top-level update-available marker."""
    payload = {
        "_system": {
            "status": "updateAvailable",
            "deviceState": "offline",
        }
    }

    assert sensor_module._system_status(payload) == "offline"


def test_system_status_maps_setup_state() -> None:
    """Setup deviceState should map to setup when online/offline is unavailable."""
    payload_setup = {"_system": {"deviceState": "setup"}}
    assert sensor_module._system_status(payload_setup) == "setup"


def test_system_status_accepts_state_field_variants() -> None:
    """Alternate firmware payloads may expose system state without deviceState."""
    payload_update = {"_system": {"state": "updateAvailable"}}
    payload_online = {"_system": {"state": "online"}}

    assert sensor_module._system_status(payload_update) == "update_available"
    assert sensor_module._system_status(payload_online) == "online"


def test_system_status_ignores_structured_state_payloads() -> None:
    """Structured state metadata should not override scalar status fields."""
    payload = {"_system": {"status": "online", "state": {"status": "setup"}}}

    assert sensor_module._system_status(payload) == "online"


def test_system_status_preserves_known_status_over_unknown_state() -> None:
    """Unknown state tokens should not replace recognized status values."""
    payload = {"_system": {"status": "online", "state": "ready"}}

    assert sensor_module._system_status(payload) == "online"


def test_update_helpers_extract_unifi_os_and_drive_versions() -> None:
    """Update entities should use UniFi OS and Drive update metadata."""
    payload = {
        "_system": {
            "latestUpdate": {"version": "v5.1.8+d8da07a"},
            "apps": {
                "controllers": [
                    {
                        "name": "drive",
                        "versionRaw": "4.1.16",
                        "updateAvailable": "4.2.2",
                    }
                ]
            },
        }
    }

    assert update_module._unifi_os_latest_version(payload) == "5.1.8"
    assert update_module._drive_latest_version(payload) == "4.2.2"
    assert update_module._system_model_name(
        {"_system": {"hardware": {"shortname": "UNAS2"}}}
    ) == "UNAS2"
    assert update_module._drive_application_name(payload) == "Drive"


def test_update_helpers_ignore_boolean_update_available() -> None:
    """Boolean no-update markers should not become display versions."""
    payload = {
        "_system": {
            "apps": {
                "controllers": [
                    {
                        "name": "drive",
                        "versionRaw": "4.1.16",
                        "updateAvailable": False,
                    }
                ]
            },
        }
    }

    assert update_module._drive_latest_version(payload) is None


def test_pool_maintenance_evaluation_requires_positive_in_progress_value() -> None:
    """Maintenance detection should not treat 0% as active maintenance."""
    pool_idle = {"rebuildProgress": 0}
    pool_running = {"rebuildProgress": 42}
    pool_done = {"rebuildProgress": 100}

    assert sensor_module._pool_in_maintenance(pool_idle) is False
    assert sensor_module._pool_in_maintenance(pool_running) is True
    assert sensor_module._pool_in_maintenance(pool_done) is False
