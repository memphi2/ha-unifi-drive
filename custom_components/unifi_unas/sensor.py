"""Compatibility entrypoint for UniFi Drive sensor platform.

The implementation is split across:
- sensor_descriptions.py
- storage_helpers.py
- entities.py
"""

from __future__ import annotations

from . import storage_helpers as _storage_helpers
from .entities import (
    UnifiUnasAggregateSensor,
    UnifiUnasBaseSensor,
    UnifiUnasDriveSensor,
    UnifiUnasPoolSensor,
    UnifiUnasSnapshotInventorySensor,
    async_setup_entry,
)
from .sensor_descriptions import (
    AGGREGATE_SENSOR_TYPES,
    DRIVE_SENSOR_TYPES,
    POOL_SENSOR_TYPES,
    AggregateSensorDescription,
    DriveSensorDescription,
    PoolSensorDescription,
)

PARALLEL_UPDATES = 0

_aggregate_available = _storage_helpers._aggregate_available
_aggregate_capacity = _storage_helpers._aggregate_capacity
_aggregate_status = _storage_helpers._aggregate_status
_aggregate_usage = _storage_helpers._aggregate_usage
_at_risk_disk_count = _storage_helpers._at_risk_disk_count
_average_disk_temperature = _storage_helpers._average_disk_temperature
_bytes_to_gib = _storage_helpers._bytes_to_gib
_cpu_percent = _storage_helpers._cpu_percent
_cpu_temperature = _storage_helpers._cpu_temperature
_degraded_pool_count = _storage_helpers._degraded_pool_count
_drive_health = _storage_helpers._drive_health
_drive_key = _storage_helpers._drive_key
_drive_name = _storage_helpers._drive_name
_drive_power_on_hours = _storage_helpers._drive_power_on_hours
_drive_is_at_risk = _storage_helpers._drive_is_at_risk
_drive_temperature = _storage_helpers._drive_temperature
_drive_version = _storage_helpers._drive_version
_find_progress_in_tree = _storage_helpers._find_progress_in_tree
_first_number = _storage_helpers._first_number
_legacy_drive_index = _storage_helpers._legacy_drive_index
_maintenance_pool_count = _storage_helpers._maintenance_pool_count
_memory_percent = _storage_helpers._memory_percent
_normalize_percent = _storage_helpers._normalize_percent
_normalized_token = _storage_helpers._normalized_token
_percentage = _storage_helpers._percentage
_parse_throughput_value = _storage_helpers._parse_throughput_value
_pool_at_risk_drive_count = _storage_helpers._pool_at_risk_drive_count
_pool_average_drive_temperature = _storage_helpers._pool_average_drive_temperature
_pool_available = _storage_helpers._pool_available
_pool_capacity = _storage_helpers._pool_capacity
_pool_drive_count = _storage_helpers._pool_drive_count
_pool_drive_temperatures = _storage_helpers._pool_drive_temperatures
_pool_drives = _storage_helpers._pool_drives
_pool_from_key = _storage_helpers._pool_from_key
_pool_in_maintenance = _storage_helpers._pool_in_maintenance
_pool_key = _storage_helpers._pool_key
_pool_has_problem = _storage_helpers._pool_has_problem
_pool_raid_level = _storage_helpers._pool_raid_level
_pool_name = _storage_helpers._pool_name
_pool_progress = _storage_helpers._pool_progress
_pool_rebuild_progress = _storage_helpers._pool_rebuild_progress
_pool_usage = _storage_helpers._pool_usage
_pool_status = _storage_helpers._pool_status
_pool_sync_progress = _storage_helpers._pool_sync_progress
_pools = _storage_helpers._pools
_collect_drive_like_dicts = _storage_helpers._collect_drive_like_dicts
_raw_drive_health = _storage_helpers._raw_drive_health
_raw_pool_status = _storage_helpers._raw_pool_status
_read_throughput_mb_s = _storage_helpers._read_throughput_mb_s
_slug = _storage_helpers._slug
_sum_known = _storage_helpers._sum_known
_system_ip = _storage_helpers._system_ip
_system_payload = _storage_helpers._system_payload
_system_status = _storage_helpers._system_status
_system_uptime_hours = _storage_helpers._system_uptime_hours
_text = _storage_helpers._text
_throughput_from_disks_mb_s = _storage_helpers._throughput_from_disks_mb_s
_throughput_key_hints = _storage_helpers._throughput_key_hints
_throughput_mb_s = _storage_helpers._throughput_mb_s
_unifi_os_version = _storage_helpers._unifi_os_version
_write_throughput_mb_s = _storage_helpers._write_throughput_mb_s

__all__ = [
    "AggregateSensorDescription",
    "DriveSensorDescription",
    "PoolSensorDescription",
    "AGGREGATE_SENSOR_TYPES",
    "DRIVE_SENSOR_TYPES",
    "POOL_SENSOR_TYPES",
    "UnifiUnasAggregateSensor",
    "UnifiUnasBaseSensor",
    "UnifiUnasDriveSensor",
    "UnifiUnasPoolSensor",
    "UnifiUnasSnapshotInventorySensor",
    "async_setup_entry",
    "_aggregate_available",
    "_aggregate_capacity",
    "_aggregate_status",
    "_aggregate_usage",
    "_at_risk_disk_count",
    "_average_disk_temperature",
    "_bytes_to_gib",
    "_cpu_percent",
    "_cpu_temperature",
    "_degraded_pool_count",
    "_drive_health",
    "_drive_key",
    "_drive_name",
    "_drive_power_on_hours",
    "_drive_is_at_risk",
    "_drive_temperature",
    "_drive_version",
    "_find_progress_in_tree",
    "_first_number",
    "_legacy_drive_index",
    "_maintenance_pool_count",
    "_memory_percent",
    "_normalize_percent",
    "_normalized_token",
    "_percentage",
    "_parse_throughput_value",
    "_pool_at_risk_drive_count",
    "_pool_average_drive_temperature",
    "_pool_available",
    "_pool_capacity",
    "_pool_drive_count",
    "_pool_drive_temperatures",
    "_pool_drives",
    "_pool_from_key",
    "_pool_in_maintenance",
    "_pool_key",
    "_pool_has_problem",
    "_pool_raid_level",
    "_pool_name",
    "_pool_progress",
    "_pool_rebuild_progress",
    "_pool_usage",
    "_pool_status",
    "_pool_sync_progress",
    "_pools",
    "_collect_drive_like_dicts",
    "_raw_drive_health",
    "_raw_pool_status",
    "_read_throughput_mb_s",
    "_slug",
    "_sum_known",
    "_system_ip",
    "_system_payload",
    "_system_status",
    "_system_uptime_hours",
    "_text",
    "_throughput_from_disks_mb_s",
    "_throughput_key_hints",
    "_throughput_mb_s",
    "_unifi_os_version",
    "_write_throughput_mb_s",
]
