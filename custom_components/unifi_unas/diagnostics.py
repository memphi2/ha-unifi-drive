"""Diagnostics support for the UniFi Drive integration."""

from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
import re
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import (
    CONF_DISCOVERY_HOST_ALIASES,
    CONF_DISCOVERY_CONFIDENCE,
    CONF_DISCOVERY_DEBUG,
    CONF_DISCOVERY_IDENTITY_SOURCE,
    CONF_DISCOVERY_LAST_SEEN,
    CONF_DISCOVERY_MAC_ADDRESS,
    CONF_WOL_MAC_ADDRESS,
    DEFAULT_DISCOVERY_DEBUG,
    DEFAULT_NAME,
    DOMAIN,
    PLATFORMS,
)
from .const import CONF_WOL_BROADCAST_ADDRESS
from .coordinator import UnifiUnasCoordinator
from .discovery_identity import (
    discovery_confidence_score,
    discovery_identity_conflicts_for_entry,
    discovery_identity_token,
    discovery_mac_key,
    entry_discovery_host_keys,
    normalize_discovery_timestamp,
)
from .entry_options import merged_entry_data_options
from .runtime import UnifiDriveConfigEntry, coordinator_from_entry_or_none
from .snapshot_inventory import snapshot_inventory_error_is_sticky
from .snapshot_types import snapshot_target_key, snapshot_target_type
from .storage_capacity import (
    _aggregate_available,
    _aggregate_capacity,
    _aggregate_usage,
)
from .storage_pools import (
    _aggregate_status,
    _at_risk_disk_count,
    _degraded_pool_count,
    _maintenance_pool_count,
    _pools,
)
from .storage_drives import _pool_drives
from .storage_system import _system_status
from .storage_throughput import (
    _read_throughput_mb_s,
    _write_throughput_mb_s,
)

DIAGNOSTICS_SCHEMA_VERSION = 1
_MANIFEST_PATH = Path(__file__).with_name("manifest.json")
_SAFE_STORAGE_PAYLOAD_KEYS = frozenset(
    {
        "_system",
        "_device_info",
        "activeRaidGroupId",
        "active_raid_group_id",
        "apps",
        "available",
        "availableBytes",
        "available_bytes",
        "backupStatus",
        "bay",
        "capacity",
        "cpu",
        "createdAt",
        "created_at",
        "data",
        "deviceState",
        "devices",
        "disks",
        "firmware",
        "firmwareVersion",
        "firmware_version",
        "guid",
        "hardware",
        "health",
        "healthScore",
        "id",
        "label",
        "latestUpdate",
        "limit",
        "mount",
        "mountPath",
        "mount_path",
        "name",
        "offset",
        "platform",
        "pool",
        "poolId",
        "pool_id",
        "pools",
        "power",
        "powerOnHours",
        "product",
        "progress",
        "raid",
        "raidGroups",
        "read",
        "readRate",
        "readThroughput",
        "result",
        "results",
        "rows",
        "serial",
        "serialNumber",
        "serial_number",
        "shares",
        "shortname",
        "slot",
        "slotId",
        "snapshotTargets",
        "state",
        "status",
        "storage",
        "system",
        "temperature",
        "time",
        "total",
        "totalCount",
        "total_count",
        "type",
        "ucore_version",
        "unit",
        "units",
        "updateAvailable",
        "uptime",
        "used",
        "usedBytes",
        "used_bytes",
        "uuid",
        "version",
        "versionRaw",
        "write",
        "writeRate",
        "writeThroughput",
    }
)

TO_REDACT = {
    CONF_HOST,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_API_KEY,
    CONF_DISCOVERY_HOST_ALIASES,
    CONF_DISCOVERY_MAC_ADDRESS,
    CONF_WOL_MAC_ADDRESS,
    CONF_WOL_BROADCAST_ADDRESS,
    "host",
    "hostname",
    "ip",
    "ipAddress",
    "ip_address",
    "mac",
    "macAddress",
    "mac_address",
    "serial",
    "serialNumber",
    "serial_number",
    "token",
    "access_token",
    "refresh_token",
    "apiToken",
    "api_token",
    "key",
    "secret",
    "authorization",
    "csrf",
    "cookie",
    "session",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: UnifiDriveConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = coordinator_from_entry_or_none(entry) or hass.data.get(
        DOMAIN, {}
    ).get(entry.entry_id)
    storage = coordinator.data if coordinator else None
    integration = await hass.async_add_executor_job(_integration_summary)
    entry_data = async_redact_data(dict(entry.data), TO_REDACT)
    entry_options = async_redact_data(
        dict(getattr(entry, "options", {}) or {}),
        TO_REDACT,
    )
    capabilities = _capability_summary(coordinator)
    storage_summary = _storage_summary(storage)
    runtime = _runtime_summary(coordinator, entry)
    return {
        "schema_version": DIAGNOSTICS_SCHEMA_VERSION,
        "integration": integration,
        "config_entry": _config_entry_summary(
            entry,
            redacted_data=entry_data,
            redacted_options=entry_options,
        ),
        "runtime": runtime,
        "capabilities": capabilities,
        "data_shape": {
            "storage": storage_summary,
        },
        "privacy": _privacy_summary(),
    }


def _integration_summary() -> dict[str, Any]:
    """Return stable integration metadata for diagnostics."""
    manifest = _load_manifest()
    return {
        "domain": manifest.get("domain", DOMAIN),
        "name": manifest.get("name", DEFAULT_NAME),
        "version": manifest.get("version"),
        "iot_class": manifest.get("iot_class"),
        "integration_type": manifest.get("integration_type"),
        "config_flow": manifest.get("config_flow"),
        "platforms": sorted(str(platform.value) for platform in PLATFORMS),
    }


def _load_manifest() -> dict[str, Any]:
    """Load manifest metadata without failing diagnostics on file errors."""
    try:
        with _MANIFEST_PATH.open(encoding="utf-8") as manifest_file:
            manifest = json.load(manifest_file)
    except (OSError, json.JSONDecodeError):
        return {}
    return manifest if isinstance(manifest, dict) else {}


def _config_entry_summary(
    entry: UnifiDriveConfigEntry,
    *,
    redacted_data: dict[str, Any],
    redacted_options: dict[str, Any],
) -> dict[str, Any]:
    """Return standard config-entry diagnostics without local identifiers."""
    data = dict(entry.data)
    options = dict(getattr(entry, "options", {}) or {})
    disabled_by = getattr(entry, "disabled_by", None)
    return {
        "entry_id_present": bool(getattr(entry, "entry_id", "")),
        "has_unique_id": bool(getattr(entry, "unique_id", None)),
        "version": getattr(entry, "version", None),
        "minor_version": getattr(entry, "minor_version", None),
        "source": getattr(entry, "source", None),
        "disabled_by": str(disabled_by) if disabled_by is not None else None,
        "pref_disable_new_entities": getattr(
            entry,
            "pref_disable_new_entities",
            None,
        ),
        "data_keys": sorted(str(key) for key in data),
        "option_keys": sorted(str(key) for key in options),
        "data": redacted_data,
        "options": redacted_options,
    }


def _runtime_summary(
    coordinator: UnifiUnasCoordinator | None,
    entry: UnifiDriveConfigEntry,
) -> dict[str, Any]:
    """Return runtime diagnostics grouped by concern."""
    discovery = _discovery_health_summary(entry)
    if coordinator is None:
        return {
            "coordinator_available": False,
            "device_online": None,
            "last_update_success": None,
            "discovery": discovery,
            "features": {},
            "fan": {},
            "monitoring_health": _monitoring_health_summary(None, None),
            "power": {},
        }

    client = coordinator.client
    storage = coordinator.data if isinstance(coordinator.data, dict) else None
    return {
        "coordinator_available": True,
        "device_online": coordinator.is_device_online,
        "last_update_success": coordinator.last_update_success,
        "discovery": discovery,
        "features": {
            "fan_control_enabled": coordinator.fan_control_enabled,
            "snapshot_buttons_enabled": coordinator.snapshot_buttons_enabled,
        },
        "fan": {
            "native_mode_present": bool(client.native_fan_mode),
            "coordinator_mode_present": bool(coordinator.fan_mode),
            "read_supported": client.fan_mode_read_supported,
            "write_supported": client.fan_mode_write_supported,
            "write_payload_hint": client.fan_mode_write_payload_hint,
        },
        "monitoring_health": _monitoring_health_summary(coordinator, storage),
        "power": {
            "poweroff_permission_hint": client.poweroff_permission_hint,
        },
    }


def _privacy_summary() -> dict[str, Any]:
    """Return diagnostics privacy guarantees for support tooling."""
    return {
        "redaction_helper": "homeassistant.components.diagnostics.async_redact_data",
        "redacted_keys": sorted(TO_REDACT),
        "raw_storage_payload_values_included": False,
        "snapshot_target_identifiers_aliased": True,
        "local_network_identifiers_redacted": True,
        "discovery_identity_values_redacted": True,
    }


def _discovery_health_summary(entry: UnifiDriveConfigEntry) -> dict[str, Any]:
    """Return support-safe discovery identity health diagnostics."""
    current = merged_entry_data_options(entry)
    conflicts = discovery_identity_conflicts_for_entry(entry)
    host_alias_count = len(entry_discovery_host_keys(entry))
    discovery_mac = discovery_mac_key(current.get(CONF_DISCOVERY_MAC_ADDRESS))
    unique_id_mac = discovery_mac_key(getattr(entry, "unique_id", None))
    last_seen = normalize_discovery_timestamp(current.get(CONF_DISCOVERY_LAST_SEEN))

    return {
        "debug_enabled": bool(
            current.get(CONF_DISCOVERY_DEBUG, DEFAULT_DISCOVERY_DEBUG)
        ),
        "last_seen": last_seen,
        "preferred_identity_source": discovery_identity_token(
            current.get(CONF_DISCOVERY_IDENTITY_SOURCE)
        ),
        "confidence": discovery_confidence_score(
            current.get(CONF_DISCOVERY_CONFIDENCE)
        ),
        "host_alias_count": host_alias_count,
        "mac_identity_present": bool(discovery_mac or unique_id_mac),
        "prompt_dedupe_ready": bool(
            discovery_mac or unique_id_mac or host_alias_count
        ),
        "restart_persistence_ready": bool(
            last_seen and (discovery_mac or unique_id_mac or host_alias_count)
        ),
        "multi_interface_ready": bool(discovery_mac or host_alias_count > 1),
        "conflicting_identity_hint_count": len(conflicts),
        "conflicting_identity_hints": list(conflicts),
    }

def _capability_summary(
    coordinator: UnifiUnasCoordinator | None,
) -> dict[str, Any] | None:
    """Return safe feature capability diagnostics for the config entry."""
    if coordinator is None:
        return None

    client = coordinator.client
    backup_tasks = coordinator.backup_tasks
    snapshot_settings = coordinator.snapshot_settings
    snapshot_inventory = getattr(coordinator, "snapshot_inventory", {}) or {}
    snapshot_inventory_errors = (
        getattr(coordinator, "snapshot_inventory_errors", {}) or {}
    )
    snapshot_inventory_skip_reasons = (
        getattr(coordinator, "snapshot_inventory_skip_reasons", {}) or {}
    )
    snapshot_target_missing_counts = (
        getattr(coordinator, "snapshot_target_missing_counts", {}) or {}
    )
    snapshot_target_aliases = _snapshot_target_aliases(
        snapshot_settings,
        snapshot_inventory,
        snapshot_inventory_errors,
        snapshot_inventory_skip_reasons,
        snapshot_target_missing_counts,
    )
    snapshot_target_count = len(snapshot_settings)
    snapshot_target_valid_count = 0
    snapshot_target_invalid_count = 0
    snapshot_target_types: set[str] = set()

    for target in snapshot_settings:
        if not isinstance(target, Mapping):
            snapshot_target_invalid_count += 1
            continue
        target_key = snapshot_target_key(target)
        if target_key:
            snapshot_target_valid_count += 1
            snapshot_target_types.add(str(snapshot_target_type(target)))
        else:
            snapshot_target_invalid_count += 1

    return {
        "device_online": coordinator.is_device_online,
        "last_update_success": coordinator.last_update_success,
        "fan_control_enabled": coordinator.fan_control_enabled,
        "fan_mode_read_supported": client.fan_mode_read_supported,
        "fan_mode_write_supported": client.fan_mode_write_supported,
        "fan_mode_write_payload_hint": client.fan_mode_write_payload_hint,
        "backup_tasks_read_supported": client.backup_tasks_read_supported,
        "backup_task_count": len(backup_tasks),
        "has_backup_tasks": bool(backup_tasks),
        "snapshot_buttons_enabled": coordinator.snapshot_buttons_enabled,
        "snapshot_settings_read_supported": client.snapshot_settings_read_supported,
        "snapshot_settings_write_supported": client.snapshot_settings_write_supported,
        "snapshot_settings_write_supported_by_type": dict(
            getattr(client, "snapshot_settings_write_supported_by_type", {}) or {}
        ),
        "snapshot_create_supported": client.snapshot_create_supported,
        "snapshot_create_supported_by_type": dict(
            getattr(client, "snapshot_create_supported_by_type", {}) or {}
        ),
        "snapshot_inventory_supported": client.snapshot_inventory_supported,
        "snapshot_inventory_supported_by_type": dict(
            getattr(client, "snapshot_inventory_supported_by_type", {}) or {}
        ),
        "snapshot_inventory_supported_by_target": (
            _snapshot_inventory_supported_by_target(
                snapshot_settings,
                snapshot_inventory,
                snapshot_inventory_errors,
                snapshot_inventory_skip_reasons,
                snapshot_target_aliases,
            )
        ),
        "snapshot_target_count": snapshot_target_count,
        "snapshot_target_valid_count": snapshot_target_valid_count,
        "snapshot_target_invalid_count": snapshot_target_invalid_count,
        "has_snapshot_targets": bool(snapshot_target_valid_count),
        "snapshot_inventory_target_count": len(snapshot_inventory),
        "snapshot_inventory_error_count": len(snapshot_inventory_errors),
        "snapshot_inventory_errors": _aliased_string_map(
            snapshot_inventory_errors,
            snapshot_target_aliases,
        ),
        "snapshot_inventory_skipped_target_count": len(
            snapshot_inventory_skip_reasons
        ),
        "snapshot_inventory_skip_reasons": _aliased_string_map(
            snapshot_inventory_skip_reasons,
            snapshot_target_aliases,
        ),
        "snapshot_missing_target_count": len(snapshot_target_missing_counts),
        "snapshot_missing_targets": _snapshot_missing_targets_summary(
            snapshot_target_missing_counts,
            snapshot_target_aliases,
        ),
        "snapshot_target_types": sorted(snapshot_target_types),
    }


def _monitoring_health_summary(
    coordinator: UnifiUnasCoordinator | None,
    storage: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return compact, non-identifying core monitoring diagnostics."""
    device_online = (
        coordinator.is_device_online if coordinator is not None else None
    )
    last_update_success = (
        coordinator.last_update_success if coordinator is not None else None
    )
    if not storage:
        return {
            "payload_present": False,
            "device_online": device_online,
            "last_update_success": last_update_success,
            "offline_cached_payload": False,
            "system_status": None,
            "storage_status": None,
            "pool_count": 0,
            "drive_count": 0,
            "degraded_pool_count": 0,
            "maintenance_pool_count": 0,
            "at_risk_disk_count": 0,
            "storage_problem": False,
            "maintenance_active": False,
            "capacity_metrics_available": False,
            "throughput_metrics_available": False,
            "throughput": _throughput_diagnostics(None),
            "monitoring_ready": False,
        }

    pools = _pools(storage)
    drive_count = sum(len(_pool_drives(pool)) for pool in pools)
    storage_status = _aggregate_status(storage)
    at_risk_disk_count = _at_risk_disk_count(storage)
    degraded_pool_count = _degraded_pool_count(storage)
    maintenance_pool_count = _maintenance_pool_count(storage)
    capacity_metrics_available = any(
        value is not None
        for value in (
            _aggregate_capacity(storage),
            _aggregate_usage(storage),
            _aggregate_available(storage),
        )
    )
    throughput_metrics_available = any(
        value is not None
        for value in (
            _read_throughput_mb_s(storage),
            _write_throughput_mb_s(storage),
        )
    )

    return {
        "payload_present": True,
        "device_online": device_online,
        "last_update_success": last_update_success,
        "offline_cached_payload": device_online is False,
        "system_status": _system_status(storage),
        "storage_status": storage_status,
        "pool_count": len(pools),
        "drive_count": drive_count,
        "degraded_pool_count": degraded_pool_count,
        "maintenance_pool_count": maintenance_pool_count,
        "at_risk_disk_count": at_risk_disk_count,
        "storage_problem": storage_status == "degraded" or at_risk_disk_count > 0,
        "maintenance_active": maintenance_pool_count > 0,
        "capacity_metrics_available": capacity_metrics_available,
        "throughput_metrics_available": throughput_metrics_available,
        "throughput": _throughput_diagnostics(storage),
        "monitoring_ready": bool(pools or capacity_metrics_available),
    }


def _throughput_diagnostics(storage: dict[str, Any] | None) -> dict[str, Any]:
    """Return privacy-safe throughput source diagnostics."""
    if not storage:
        return {
            "read": _throughput_direction_diagnostics(None, direction="read"),
            "write": _throughput_direction_diagnostics(None, direction="write"),
        }
    return {
        "read": _throughput_direction_diagnostics(storage, direction="read"),
        "write": _throughput_direction_diagnostics(storage, direction="write"),
    }


def _throughput_direction_diagnostics(
    storage: dict[str, Any] | None,
    *,
    direction: str,
) -> dict[str, str | bool]:
    """Return selected source and status for one throughput direction."""
    if not storage:
        return {
            "selected_source": "none",
            "selected_status": "missing",
            "storage_status": "missing",
            "network_io_present": False,
            "network_io_status": "missing",
        }

    storage_without_network_io = dict(storage)
    network_io = storage_without_network_io.pop("_network_io", None)
    network_payload = (
        {"_network_io": network_io}
        if isinstance(network_io, dict)
        else None
    )
    value_fn = (
        _read_throughput_mb_s
        if direction == "read"
        else _write_throughput_mb_s
    )
    selected_value = value_fn(storage)
    storage_value = value_fn(storage_without_network_io)
    network_value = value_fn(network_payload) if network_payload is not None else None
    selected_source = _throughput_selected_source(
        selected_value=selected_value,
        storage_value=storage_value,
        network_value=network_value,
    )

    return {
        "selected_source": selected_source,
        "selected_status": _throughput_value_status(selected_value),
        "storage_status": _throughput_value_status(storage_value),
        "network_io_present": network_payload is not None,
        "network_io_status": _throughput_value_status(network_value),
    }


def _throughput_selected_source(
    *,
    selected_value: float | None,
    storage_value: float | None,
    network_value: float | None,
) -> str:
    """Return the selected throughput source without exposing the value."""
    if selected_value is None:
        return "none"
    if (
        network_value is not None
        and network_value != 0
        and selected_value == network_value
        and (storage_value is None or storage_value == 0)
    ):
        return "network_io"
    return "storage"


def _throughput_value_status(value: float | None) -> str:
    """Return a non-identifying status for a throughput value."""
    if value is None:
        return "missing"
    if value == 0:
        return "zero"
    return "non_zero"


def _snapshot_inventory_supported_by_target(
    snapshot_settings: list[Any],
    snapshot_inventory: dict[str, dict[str, Any]],
    snapshot_inventory_errors: dict[str, str],
    snapshot_inventory_skip_reasons: dict[str, str],
    target_aliases: dict[str, str],
) -> dict[str, bool | None]:
    """Return target-level snapshot inventory capability diagnostics."""
    supported_by_target: dict[str, bool | None] = {}
    for target in snapshot_settings:
        if not isinstance(target, Mapping):
            continue
        target_key = snapshot_target_key(target)
        if not target_key:
            continue
        target_alias = target_aliases.get(target_key, "snapshot_target")
        if target_key in snapshot_inventory:
            supported_by_target[target_alias] = True
            continue
        reason = snapshot_inventory_skip_reasons.get(
            target_key,
            snapshot_inventory_errors.get(target_key),
        )
        if snapshot_inventory_error_is_sticky(reason):
            supported_by_target[target_alias] = False
        else:
            supported_by_target[target_alias] = None
    return supported_by_target


def _snapshot_target_aliases(
    snapshot_settings: list[Any],
    *key_sources: Mapping[str, object],
) -> dict[str, str]:
    """Return non-identifying aliases for snapshot target diagnostic keys."""
    aliases: dict[str, str] = {}
    counters: dict[str, int] = {}

    def add_alias(target_key: str, target_type: str) -> None:
        if not target_key or target_key in aliases:
            return
        safe_type = target_type if target_type in {"mydrive", "shared"} else "snapshot"
        counters[safe_type] = counters.get(safe_type, 0) + 1
        aliases[target_key] = f"{safe_type}_target_{counters[safe_type]}"

    for target in snapshot_settings:
        if not isinstance(target, Mapping):
            continue
        add_alias(snapshot_target_key(target), snapshot_target_type(target))

    for source in key_sources:
        if not isinstance(source, Mapping):
            continue
        for target_key in source:
            text_key = str(target_key)
            target_type = text_key.split("_", 1)[0]
            add_alias(text_key, target_type)

    return aliases


def _aliased_string_map(
    values: Mapping[str, str],
    target_aliases: Mapping[str, str],
) -> dict[str, str]:
    """Return a keyed diagnostics mapping without raw snapshot target IDs."""
    return {
        target_aliases.get(str(target_key), "snapshot_target"): str(reason)
        for target_key, reason in values.items()
    }


def _snapshot_missing_targets_summary(
    values: Mapping[str, Any],
    target_aliases: Mapping[str, str],
) -> dict[str, dict[str, Any]]:
    """Return missing-target diagnostics without raw IDs or target names."""
    summary: dict[str, dict[str, Any]] = {}
    for target_key, value in values.items():
        if not isinstance(value, Mapping):
            continue
        summary[target_aliases.get(str(target_key), "snapshot_target")] = {
            "missing_count": value.get("missing_count"),
            "target_type": value.get("target_type"),
        }
    return summary


def _storage_summary(storage: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return safe diagnostics about the latest storage payload."""
    if not storage:
        return None

    pools = storage.get("pools")
    disks = storage.get("disks")

    pool_sample_keys = _object_keys_from_list(pools, limit=4)
    disk_sample_keys = _object_keys_from_list(disks, limit=8)
    candidate_paths = _candidate_field_paths(storage, limit=120)

    return {
        "top_level_keys": sorted({_safe_payload_key(key) for key in storage}),
        "pool_count": len(pools) if isinstance(pools, list) else None,
        "has_pools": isinstance(pools, list),
        "disk_count": len(disks) if isinstance(disks, list) else None,
        "has_disks": isinstance(disks, list),
        "pool_sample_keys": pool_sample_keys,
        "disk_sample_keys": disk_sample_keys,
        "candidate_field_paths": candidate_paths,
    }


def _object_keys_from_list(value: Any, *, limit: int) -> list[str]:
    """Return merged keys from first list objects."""
    if not isinstance(value, list):
        return []

    merged: set[str] = set()
    for item in value[:limit]:
        if isinstance(item, dict):
            merged.update(_safe_payload_key(key) for key in item)
    return sorted(merged)


def _safe_payload_key(key: object) -> str:
    """Return a diagnostics-safe representation of an API payload key."""
    text = str(key).strip()
    if text in _SAFE_STORAGE_PAYLOAD_KEYS:
        return text
    return "<key>"


def _candidate_field_paths(storage: dict[str, Any], *, limit: int) -> list[str]:
    """Return interesting key paths for metric mapping diagnostics."""
    patterns = (
        "read",
        "write",
        "throughput",
        "speed",
        "rate",
        "smb",
        "nfs",
        "health",
        "status",
        "temp",
        "temperature",
        "power",
        "hour",
        "uptime",
        "mount",
        "connection",
        "backup",
    )
    matches: list[str] = []
    seen: set[str] = set()

    def add_match(candidate: str) -> None:
        if candidate in seen or len(matches) >= limit:
            return
        seen.add(candidate)
        matches.append(candidate)

    def walk(value: Any, path: str = "") -> None:
        if len(matches) >= limit:
            return

        if isinstance(value, dict):
            for key, child in value.items():
                safe_key = _safe_payload_key(key)
                child_path = f"{path}.{safe_key}" if path else safe_key
                normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
                if any(pattern in normalized for pattern in patterns):
                    add_match(
                        f"{child_path}=[complex]"
                        if isinstance(child, (dict, list))
                        else f"{child_path}=[redacted]"
                    )
                walk(child, child_path)
            return

        if isinstance(value, list):
            for idx, item in enumerate(value[:20]):
                walk(item, f"{path}[{idx}]")

    walk(storage)
    return matches
