"""Sensor entity descriptions for the UniFi Drive integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfInformation,
    UnitOfTemperature,
)
from homeassistant.helpers.typing import StateType

from .storage_helpers import (
    _aggregate_available,
    _aggregate_capacity,
    _aggregate_status,
    _aggregate_usage,
    _at_risk_disk_count,
    _average_disk_temperature,
    _bytes_to_gib,
    _cache_status,
    _cpu_percent,
    _cpu_temperature,
    _degraded_pool_count,
    _drive_bad_sectors,
    _drive_capacity,
    _drive_health,
    _drive_life_span,
    _drive_model,
    _drive_power_on_hours,
    _drive_temperature,
    _drive_uncorrectable_sectors,
    _maintenance_pool_count,
    _memory_percent,
    _percentage,
    _pool_at_risk_drive_count,
    _pool_average_drive_temperature,
    _pool_available,
    _pool_capacity,
    _pool_drive_count,
    _pool_raid_level,
    _pool_rebuild_progress,
    _pool_status,
    _pool_sync_progress,
    _pool_usage,
    _pools,
    _read_throughput_mb_s,
    _system_ip,
    _system_status,
    _system_uptime_hours,
    _unifi_os_version,
    _drive_version,
    _write_throughput_mb_s,
)


@dataclass(frozen=True, kw_only=True)
class AggregateSensorDescription(SensorEntityDescription):  # type: ignore[misc]
    """Description of an aggregate UNAS sensor."""

    value_fn: Callable[[dict[str, Any]], StateType]


@dataclass(frozen=True, kw_only=True)
class PoolSensorDescription(SensorEntityDescription):  # type: ignore[misc]
    """Description of a per-pool UNAS sensor."""

    value_fn: Callable[[dict[str, Any]], StateType]
    entity_category: EntityCategory | None = EntityCategory.DIAGNOSTIC
    entity_registry_enabled_default: bool = False


AGGREGATE_SENSOR_TYPES: tuple[AggregateSensorDescription, ...] = (
    AggregateSensorDescription(
        key="read_throughput",
        translation_key="read_throughput",
        native_unit_of_measurement="MB/s",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda data: _read_throughput_mb_s(data),
    ),
    AggregateSensorDescription(
        key="write_throughput",
        translation_key="write_throughput",
        native_unit_of_measurement="MB/s",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda data: _write_throughput_mb_s(data),
    ),
    AggregateSensorDescription(
        key="total_storage",
        translation_key="total_storage",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.GIBIBYTES,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda data: _bytes_to_gib(_aggregate_capacity(data)),
    ),
    AggregateSensorDescription(
        key="used_storage",
        translation_key="used_storage",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.GIBIBYTES,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda data: _bytes_to_gib(_aggregate_usage(data)),
    ),
    AggregateSensorDescription(
        key="available_storage",
        translation_key="available_storage",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.GIBIBYTES,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda data: _bytes_to_gib(_aggregate_available(data)),
    ),
    AggregateSensorDescription(
        key="usage_percent",
        translation_key="usage_percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda data: _percentage(_aggregate_usage(data), _aggregate_capacity(data)),
    ),
    AggregateSensorDescription(
        key="pool_count",
        translation_key="pool_count",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: len(_pools(data)),
    ),
    AggregateSensorDescription(
        key="overall_status",
        translation_key="overall_status",
        value_fn=lambda data: _aggregate_status(data),
    ),
    AggregateSensorDescription(
        key="degraded_pool_count",
        translation_key="degraded_pool_count",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _degraded_pool_count(data),
    ),
    AggregateSensorDescription(
        key="maintenance_pool_count",
        translation_key="maintenance_pool_count",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _maintenance_pool_count(data),
    ),
    AggregateSensorDescription(
        key="at_risk_disk_count",
        translation_key="at_risk_disk_count",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _at_risk_disk_count(data),
    ),
    AggregateSensorDescription(
        key="average_disk_temperature",
        translation_key="average_disk_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda data: _average_disk_temperature(data),
    ),
    AggregateSensorDescription(
        key="system_ip",
        translation_key="system_ip",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: _system_ip(data),
    ),
    AggregateSensorDescription(
        key="system_uptime",
        translation_key="system_uptime",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda data: _system_uptime_hours(data),
    ),
    AggregateSensorDescription(
        key="unifi_os_version",
        translation_key="unifi_os_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: _unifi_os_version(data),
    ),
    AggregateSensorDescription(
        key="drive_version",
        translation_key="drive_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: _drive_version(data),
    ),
    AggregateSensorDescription(
        key="cpu_temperature",
        translation_key="cpu_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda data: _cpu_temperature(data),
    ),
    AggregateSensorDescription(
        key="cpu_percent",
        translation_key="cpu_percent",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda data: _cpu_percent(data),
    ),
    AggregateSensorDescription(
        key="memory_percent",
        translation_key="memory_percent",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda data: _memory_percent(data),
    ),
    AggregateSensorDescription(
        key="cache_status",
        translation_key="cache_status",
        value_fn=lambda data: _cache_status(data),
    ),
    AggregateSensorDescription(
        key="system_status",
        translation_key="system_status",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: _system_status(data),
    ),
)

POOL_SENSOR_TYPES: tuple[PoolSensorDescription, ...] = (
    PoolSensorDescription(
        key="pool_status",
        name="Status",
        translation_key="pool_status",
        value_fn=lambda pool: _pool_status(pool),
    ),
    PoolSensorDescription(
        key="pool_capacity",
        name="Capacity",
        translation_key="pool_capacity",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.GIBIBYTES,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
        value_fn=lambda pool: _bytes_to_gib(_pool_capacity(pool)),
    ),
    PoolSensorDescription(
        key="pool_used",
        name="Used",
        translation_key="pool_used",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.GIBIBYTES,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
        value_fn=lambda pool: _bytes_to_gib(_pool_usage(pool)),
    ),
    PoolSensorDescription(
        key="pool_available",
        name="Available",
        translation_key="pool_available",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.GIBIBYTES,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
        value_fn=lambda pool: _bytes_to_gib(_pool_available(pool)),
    ),
    PoolSensorDescription(
        key="pool_usage_percent",
        name="Usage",
        translation_key="pool_usage_percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        value_fn=lambda pool: _percentage(_pool_usage(pool), _pool_capacity(pool)),
    ),
    PoolSensorDescription(
        key="pool_raid_level",
        name="RAID Level",
        translation_key="pool_raid_level",
        value_fn=lambda pool: _pool_raid_level(pool),
    ),
    PoolSensorDescription(
        key="pool_drive_count",
        name="Drive Count",
        translation_key="pool_drive_count",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda pool: _pool_drive_count(pool),
    ),
    PoolSensorDescription(
        key="pool_rebuild_progress",
        name="Rebuild Progress",
        translation_key="pool_rebuild_progress",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        value_fn=lambda pool: _pool_rebuild_progress(pool),
    ),
    PoolSensorDescription(
        key="pool_sync_progress",
        name="Sync Progress",
        translation_key="pool_sync_progress",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        value_fn=lambda pool: _pool_sync_progress(pool),
    ),
    PoolSensorDescription(
        key="pool_at_risk_drive_count",
        name="At-Risk Drive Count",
        translation_key="pool_at_risk_drive_count",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda pool: _pool_at_risk_drive_count(pool),
    ),
    PoolSensorDescription(
        key="pool_average_drive_temperature",
        name="Average Drive Temperature",
        translation_key="pool_average_drive_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        value_fn=lambda pool: _pool_average_drive_temperature(pool),
    ),
)


@dataclass(frozen=True, kw_only=True)
class DriveSensorDescription(SensorEntityDescription):  # type: ignore[misc]
    """Description of a per-drive UNAS sensor."""

    value_fn: Callable[[dict[str, Any]], StateType]
    entity_category: EntityCategory | None = EntityCategory.DIAGNOSTIC
    entity_registry_enabled_default: bool = False


DRIVE_SENSOR_TYPES: tuple[DriveSensorDescription, ...] = (
    DriveSensorDescription(
        key="drive_status",
        name="Status",
        translation_key="drive_status",
        value_fn=lambda drive: _drive_health(drive),
    ),
    DriveSensorDescription(
        key="drive_temperature",
        name="Temperature",
        translation_key="drive_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda drive: _drive_temperature(drive),
    ),
    DriveSensorDescription(
        key="drive_power_on_hours",
        name="Power-On Hours",
        translation_key="drive_power_on_hours",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda drive: _drive_power_on_hours(drive),
    ),
    DriveSensorDescription(
        key="drive_life_span",
        name="Remaining Life",
        translation_key="drive_life_span",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda drive: _drive_life_span(drive),
    ),
    DriveSensorDescription(
        key="drive_model",
        name="Model",
        translation_key="drive_model",
        value_fn=lambda drive: _drive_model(drive),
    ),
    DriveSensorDescription(
        key="drive_capacity",
        name="Capacity",
        translation_key="drive_capacity",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.GIBIBYTES,
        suggested_display_precision=2,
        value_fn=lambda drive: _bytes_to_gib(_drive_capacity(drive)),
    ),
    DriveSensorDescription(
        key="drive_bad_sectors",
        name="Bad Sectors",
        translation_key="drive_bad_sectors",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda drive: _drive_bad_sectors(drive),
    ),
    DriveSensorDescription(
        key="drive_uncorrectable_sectors",
        name="Uncorrectable Sectors",
        translation_key="drive_uncorrectable_sectors",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda drive: _drive_uncorrectable_sectors(drive),
    ),
)
