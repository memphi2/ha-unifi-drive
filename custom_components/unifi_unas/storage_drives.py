"""Drive and pool-member helper functions."""

from __future__ import annotations

import re
from typing import Any

from .storage_common import (
    DISK_PROBLEM_HINTS,
    _dict_values,
    _first_number,
    _slug,
    _text,
)
from .system_metadata import normalized_token as _normalized_token

DRIVE_INDEX_KEY_RE = re.compile(r"(?:^|_)drive_(\d+)$")
DRIVE_ID_KEYS = (
    "serial",
    "slotId",
    "slot",
    "bay",
    "diskName",
    "disk_name",
)
DRIVE_STRONG_ID_KEYS = (
    "serial",
    "diskName",
    "disk_name",
)
DRIVE_METRIC_KEYS = (
    "temperature",
    "temp",
    "temperatureC",
    "temperature_c",
    "tempC",
    "temp_c",
    "powerOnHours",
    "power_on_hours",
    "powerOnTimeHours",
    "healthScore",
    "health",
    "health_status",
    "healthStatus",
    "smart",
    "smartStatus",
)
DRIVE_POOL_KEYS = (
    "poolId",
    "pool_id",
    "poolGuid",
    "pool_guid",
    "poolUuid",
    "pool_uuid",
    "poolName",
    "pool_name",
    "storagePoolId",
    "storage_pool_id",
    "volumeId",
    "volume_id",
    "raidGroupId",
    "raid_group_id",
    "activeRaidGroupId",
    "active_raid_group_id",
)
DRIVE_EXPLICIT_POOL_REFERENCE_KEYS = (
    "poolId",
    "pool_id",
    "poolGuid",
    "pool_guid",
    "poolUuid",
    "pool_uuid",
    "poolName",
    "pool_name",
    "storagePoolId",
    "storage_pool_id",
    "volumeId",
    "volume_id",
    "raidGroupId",
    "raid_group_id",
    "activeRaidGroupId",
    "active_raid_group_id",
)
DRIVE_IDENTITY_KEY_GROUPS = (
    ("stable_id", ("id", "uuid", "guid")),
    ("serial", ("serial", "wwn")),
    ("disk_name", ("diskName", "disk_name")),
    ("location", ("slotId", "slot", "bay")),
)
DRIVE_STRONG_IDENTITY_GROUPS = ("stable_id", "serial")
DRIVE_NON_POOL_BOOL_KEYS = (
    "empty",
    "hotSpare",
    "hot_spare",
    "isEmpty",
    "isHotSpare",
    "isSpare",
    "isUnassigned",
    "spare",
    "unassigned",
)
DRIVE_NON_POOL_HINTS = (
    "available",
    "empty",
    "free",
    "hotspare",
    "notinstalled",
    "notpresent",
    "spare",
    "unallocated",
    "unassigned",
    "unused",
)
DRIVE_STATUS_HINT_KEYS = (
    "allocation",
    "condition",
    "health",
    "healthStatus",
    "memberState",
    "mode",
    "role",
    "slotStatus",
    "smartStatus",
    "state",
    "status",
    "type",
    "usage",
)
POOL_DRIVE_COUNT_KEYS = (
    "driveCount",
    "diskCount",
    "memberCount",
    "numDrives",
    "numDisks",
    "numberOfDisks",
    "diskNum",
    "memberNum",
)
DRIVE_DETAIL_CONTAINER_KEYS = (
    "details",
    "disk",
    "drive",
    "health",
    "metrics",
    "smart",
    "smartData",
    "stats",
)
DRIVE_TEMPERATURE_KEYS = (
    "temperature",
    "temp",
    "temperatureC",
    "temperature_c",
    "tempC",
    "temp_c",
    "driveTemp",
    "drive_temp",
    "currentTemperature",
)
DRIVE_POWER_ON_HOUR_KEYS = (
    "powerOnHours",
    "power_on_hours",
    "powerOnTimeHours",
    "uptimeHours",
    "hours",
    "lifeHours",
)
DRIVE_HEALTH_KEYS = (
    "health",
    "healthStatus",
    "smartStatus",
    "smart",
    "status",
    "state",
    "condition",
    "value",
)


def _drive_key(drive: dict[str, Any], index: int) -> str:
    """Return a stable-ish key for a drive."""
    for key in (
        "id",
        "uuid",
        "guid",
        "serial",
        "wwn",
        "diskName",
        "disk_name",
        "name",
        "slotId",
        "slot",
        "bay",
    ):
        value = drive.get(key)
        if value not in (None, ""):
            return _slug(str(value))
    return f"drive_{index + 1}"


def _legacy_drive_index(drive_key: str) -> int | None:
    """Return 0-based legacy drive index if key contains drive_<n>."""
    match = DRIVE_INDEX_KEY_RE.search(drive_key)
    if not match:
        return None
    index = int(match.group(1)) - 1
    return index if index >= 0 else None


def _drive_name(drive: dict[str, Any], index: int) -> str:
    """Return display name for a drive."""
    for key in ("name", "label", "displayName", "display_name", "diskName", "disk_name"):
        text = _text(drive.get(key))
        if text:
            return text
    slot = _text(drive.get("slotId")) or _text(drive.get("slot")) or _text(drive.get("bay"))
    if slot:
        return f"Drive {slot}"
    return f"Drive {index + 1}"


def _pool_drive_count(pool: dict[str, Any]) -> int | None:
    """Return drive count for a pool."""
    drives = _pool_drives(pool)
    if drives:
        return len(drives)

    direct = _declared_pool_drive_count(pool)
    if direct is None:
        return None
    return direct


def _pool_at_risk_drive_count(pool: dict[str, Any]) -> int | None:
    """Return how many drives in a pool look unhealthy."""
    drives = _pool_drives(pool)
    if not drives:
        return 0
    return sum(1 for drive in drives if _drive_is_at_risk(drive))


def _pool_average_drive_temperature(pool: dict[str, Any]) -> float | None:
    """Return average drive temperature for a pool."""
    values = _pool_drive_temperatures(pool)
    if not values:
        return None
    return round(sum(values) / len(values), 1)


def _pool_drives(pool: dict[str, Any]) -> list[dict[str, Any]]:
    """Return best-effort list of drives for a pool."""
    for collector in (
        _collect_direct_pool_drives,
        _collect_nested_pool_drives,
        _collect_nested_raid_drives,
        _collect_global_reference_drives,
        _collect_raid_group_reference_drives,
    ):
        drives = collector(pool)
        if drives:
            return _complete_single_pool_global_drives(pool, drives)

    return _collect_single_pool_global_drives(pool)


def _declared_pool_drive_count(pool: dict[str, Any]) -> int | None:
    """Return the drive count declared directly by a pool payload."""
    direct = _first_number(pool, POOL_DRIVE_COUNT_KEYS)
    if direct is None:
        return None
    return int(round(direct))


def _complete_single_pool_global_drives(
    pool: dict[str, Any], drives: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Prefer complete single-pool global disk data when local drive lists lag."""
    global_drives = _collect_single_pool_global_drives(pool, known_drives=drives)
    if len(global_drives) > len(drives):
        return global_drives
    return drives


def _collect_single_pool_global_drives(
    pool: dict[str, Any], *, known_drives: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """Collect global disks when a single-pool payload declares them as members."""
    pool_count = pool.get("__pool_count")
    if pool_count != 1:
        return []

    expected_count = _declared_pool_drive_count(pool)
    if expected_count is None or expected_count < 1:
        return []

    global_disks = pool.get("__global_disks")
    if not isinstance(global_disks, list):
        return []

    drives = [disk for disk in global_disks if isinstance(disk, dict)]
    pool_drives = _global_pool_member_drives(
        pool, drives, expected_count, known_drives or []
    )
    if len(pool_drives) != expected_count:
        return []
    return pool_drives


def _global_pool_member_drives(
    pool: dict[str, Any],
    drives: list[dict[str, Any]],
    expected_count: int,
    known_drives: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return global drives that can be safely treated as pool members."""
    pool_references = _pool_reference_values(pool)
    members: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []

    for drive in drives:
        if _drive_looks_non_pool_member(drive):
            continue
        if _drive_references_foreign_pool(drive, pool_references):
            continue
        if known_drive := _matching_known_drive(drive, known_drives):
            _append_unique_drive(members, _merge_drive_entries(drive, known_drive))
            continue
        if pool_references and any(
            _drive_pool_reference_matches(drive, pool_reference)
            for pool_reference in pool_references
        ):
            _append_unique_drive(members, drive)
            continue
        if _drive_has_explicit_pool_reference(drive):
            continue
        _append_unique_drive(candidates, drive)

    if len(members) > expected_count:
        return []

    missing = expected_count - len(members)
    if missing > 0 and len(candidates) == missing:
        for candidate in candidates:
            _append_unique_drive(members, candidate)

    return members


def _drive_references_foreign_pool(
    drive: dict[str, Any], pool_references: list[str]
) -> bool:
    """Return whether a drive explicitly references a different pool."""
    if not _drive_has_explicit_pool_reference(drive):
        return False
    return not any(
        _drive_pool_reference_matches(drive, pool_reference)
        for pool_reference in pool_references
    )


def _append_unique_drive(drives: list[dict[str, Any]], drive: dict[str, Any]) -> None:
    """Append a drive if its known identity is not already present."""
    if any(_drive_identity_matches(drive, item) for item in drives):
        return
    drives.append(drive)


def _matching_known_drive(
    drive: dict[str, Any], known_drives: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Return a known drive matching a global drive by stable identity."""
    if not _drive_identity_groups(drive):
        return None

    for known_drive in known_drives:
        if _drive_identity_matches(drive, known_drive):
            return known_drive
    return None


def _merge_drive_entries(
    global_drive: dict[str, Any], local_drive: dict[str, Any]
) -> dict[str, Any]:
    """Merge a global drive record with richer local pool-member data."""
    merged = dict(global_drive)
    for key, value in local_drive.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _merge_drive_entries(current, value)
        elif not _is_missing_drive_value(value):
            merged[key] = value
        elif key not in merged:
            merged[key] = value
    return merged


def _is_missing_drive_value(value: Any) -> bool:
    """Return whether a drive field carries no useful value."""
    return value in (None, "", [], {})


def _drive_identity_matches(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Return whether two drive records share a compatible identity value."""
    left_groups = _drive_identity_groups(left)
    if not left_groups:
        return False

    right_groups = _drive_identity_groups(right)
    if _drive_identity_has_strong_conflict(left_groups, right_groups):
        return False

    return any(
        bool(values & right_groups.get(group, set()))
        for group, values in left_groups.items()
    )


def _drive_identity_has_strong_conflict(
    left_groups: dict[str, set[str]], right_groups: dict[str, set[str]]
) -> bool:
    """Return whether strong drive identity groups are contradictory."""
    for group in DRIVE_STRONG_IDENTITY_GROUPS:
        left_values = left_groups.get(group)
        right_values = right_groups.get(group)
        if left_values and right_values and not left_values & right_values:
            return True
    return False


def _drive_identity_groups(drive: dict[str, Any]) -> dict[str, set[str]]:
    """Return grouped drive identity values for safe reconciliation."""
    groups: dict[str, set[str]] = {}
    for group, keys in DRIVE_IDENTITY_KEY_GROUPS:
        values = {
            _normalized_token(value)
            for key in keys
            if (value := _text(drive.get(key)))
        }
        if values:
            groups[group] = values
    return groups


def _drive_looks_non_pool_member(drive: dict[str, Any]) -> bool:
    """Return whether a global disk looks like a spare or unassigned device."""
    for key in DRIVE_NON_POOL_BOOL_KEYS:
        if drive.get(key) is True:
            return True

    for key in DRIVE_STATUS_HINT_KEYS:
        value = _text(drive.get(key))
        if not value:
            continue
        normalized = _normalized_token(value)
        if any(hint in normalized for hint in DRIVE_NON_POOL_HINTS):
            return True
    return False


def _drive_has_explicit_pool_reference(drive: dict[str, Any]) -> bool:
    """Return whether a drive explicitly references a storage pool."""
    if any(_text(drive.get(key)) for key in DRIVE_EXPLICIT_POOL_REFERENCE_KEYS):
        return True

    pool = drive.get("pool")
    if not isinstance(pool, dict):
        return False

    return any(
        _text(pool.get(key))
        for key in (
            "id",
            "uuid",
            "guid",
            "name",
            "label",
            "poolId",
            "pool_id",
            "storagePoolId",
            "storage_pool_id",
            "volumeId",
            "volume_id",
            "raidGroupId",
            "raid_group_id",
            "activeRaidGroupId",
            "active_raid_group_id",
        )
    )


def _collect_direct_pool_drives(pool: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect drives exposed in common direct pool keys."""
    for key in ("drives", "disks", "members", "devices", "hdds", "slots"):
        drives = pool.get(key)
        if isinstance(drives, list):
            return [item for item in drives if isinstance(item, dict)]
    return []


def _collect_nested_pool_drives(pool: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect drives exposed in nested pool/raid structures."""
    for key in ("raid", "raidGroup", "raid_group", "storage", "media"):
        candidate = pool.get(key)
        if not isinstance(candidate, dict):
            continue
        for nested_key in ("drives", "disks", "members", "devices"):
            drives = candidate.get(nested_key)
            if isinstance(drives, list):
                return [item for item in drives if isinstance(item, dict)]
    return []


def _collect_nested_raid_drives(pool: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect drives nested under a payload's raid group subtree."""
    return _collect_drive_like_dicts(pool.get("raidGroups"))


def _collect_global_reference_drives(pool: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect drives from global pool refs for this pool."""
    pool_references = _pool_reference_values(pool)
    global_disks = pool.get("__global_disks")
    if not pool_references or not isinstance(global_disks, list):
        return []

    matched: list[dict[str, Any]] = []
    for disk in global_disks:
        if not isinstance(disk, dict):
            continue
        if any(
            _drive_pool_reference_matches(disk, pool_reference)
            for pool_reference in pool_references
        ):
            matched.append(disk)
    return matched


def _collect_raid_group_reference_drives(pool: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect drives by active raid-group reference if no direct ref exists."""
    global_disks = pool.get("__global_disks")
    if not isinstance(global_disks, list):
        return []

    active_raid_group_id = _text(pool.get("activeRaidGroupId")) or _text(
        pool.get("active_raid_group_id")
    )
    if not active_raid_group_id:
        return []

    drives: list[dict[str, Any]] = []
    for disk in global_disks:
        if not isinstance(disk, dict):
            continue
        if _disk_references_active_raid_group(disk, active_raid_group_id):
            drives.append(disk)
    return drives


def _disk_references_active_raid_group(disk: dict[str, Any], reference: str) -> bool:
    """Return whether a disk references the active raid-group."""
    return bool(
        _text(disk.get("raidGroupId")) == reference
        or _text(disk.get("raid_group_id")) == reference
    )


def _drive_number(drive: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    """Return a drive metric from direct or nested detail containers."""
    direct = _first_number(drive, keys)
    if direct is not None:
        return direct

    for nested in _dict_values(drive, DRIVE_DETAIL_CONTAINER_KEYS):
        value = _first_number(nested, keys)
        if value is not None:
            return value
    return None


def _drive_pool_reference_matches(drive: dict[str, Any], pool_id: str) -> bool:
    """Return whether a global drive entry references a pool identifier."""
    for key in DRIVE_POOL_KEYS:
        if _text(drive.get(key)) == pool_id:
            return True

    pool = drive.get("pool")
    if isinstance(pool, dict):
        for key in (
            "id",
            "uuid",
            "guid",
            "name",
            "label",
            "poolId",
            "pool_id",
            "storagePoolId",
            "storage_pool_id",
            "volumeId",
            "volume_id",
            "raidGroupId",
            "raid_group_id",
            "activeRaidGroupId",
            "active_raid_group_id",
        ):
            if _text(pool.get(key)) == pool_id:
                return True
    return False


def _pool_reference_values(pool: dict[str, Any]) -> list[str]:
    """Return known identifiers that global disks may use for a pool."""
    values: list[str] = []
    for key in (
        "id",
        "poolId",
        "pool_id",
        "poolGuid",
        "pool_guid",
        "uuid",
        "guid",
        "storagePoolId",
        "storage_pool_id",
        "volumeId",
        "volume_id",
        "raidGroupId",
        "raid_group_id",
        "activeRaidGroupId",
        "active_raid_group_id",
        "name",
        "label",
        "poolName",
        "pool_name",
    ):
        value = _text(pool.get(key))
        if value and value not in values:
            values.append(value)
    return values


def _collect_drive_like_dicts(value: Any) -> list[dict[str, Any]]:
    """Collect nested dicts that look like drive objects."""
    found: list[dict[str, Any]] = []

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            keys = {str(key) for key in node}
            if _is_drive_like_dict(node, keys):
                found.append(node)
            for child in node.values():
                _walk(child)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(value)

    # De-duplicate by serial/id if present; otherwise by object identity order.
    dedup: dict[str, dict[str, Any]] = {}
    for item in found:
        key = _text(item.get("serial")) or _text(item.get("id")) or str(id(item))
        dedup[key] = item
    return list(dedup.values())


def _is_drive_like_dict(node: dict[str, Any], keys: set[str] | None = None) -> bool:
    """Return whether a dictionary is likely a drive entry."""
    if not node:
        return False

    if keys is None:
        keys = {str(key) for key in node}

    has_drive_id = any(key in keys for key in DRIVE_ID_KEYS)
    has_strong_drive_id = any(key in keys for key in DRIVE_STRONG_ID_KEYS)
    has_pool_hint = any(key in keys for key in DRIVE_POOL_KEYS)
    has_metric = any(key in keys for key in DRIVE_METRIC_KEYS)
    has_slot_hint = any(key in keys for key in ("slotId", "slot", "bay"))

    return has_drive_id and (
        ((has_pool_hint or has_slot_hint) and has_metric)
        or (has_strong_drive_id and has_pool_hint and has_slot_hint)
    )


def _drive_is_at_risk(drive: dict[str, Any]) -> bool:
    """Return whether a drive status suggests risk/failure."""
    health_score = _drive_number(drive, ("healthScore", "health_score"))
    if health_score is not None:
        return health_score < 5

    for key in (
        "status",
        "state",
        "health",
        "healthStatus",
        "smartStatus",
        "smart",
        "condition",
    ):
        value = drive.get(key)
        if value is None:
            continue
        normalized = _normalized_token(str(value))
        if not normalized:
            continue
        if normalized in {"healthy", "good", "ok", "normal", "passed"}:
            continue
        if any(hint in normalized for hint in DISK_PROBLEM_HINTS):
            return True
    return False


def _pool_drive_temperatures(pool: dict[str, Any]) -> list[float]:
    """Return known drive temperatures in Celsius for a pool."""
    values: list[float] = []
    for drive in _pool_drives(pool):
        value = _drive_temperature(drive)
        if value is not None:
            values.append(value)
    return values


def _drive_temperature(drive: dict[str, Any]) -> float | None:
    """Return drive temperature in Celsius."""
    value = _drive_number(drive, DRIVE_TEMPERATURE_KEYS)
    return round(value, 1) if value is not None else None


def _raw_drive_health(drive: dict[str, Any]) -> str | None:
    """Return raw drive health/status field."""
    for key in DRIVE_HEALTH_KEYS:
        if text := _drive_health_text(drive.get(key)):
            return text
    for nested in _dict_values(drive, DRIVE_DETAIL_CONTAINER_KEYS):
        for key in DRIVE_HEALTH_KEYS:
            if text := _drive_health_text(nested.get(key)):
                return text
    return None


def _drive_health_text(value: Any) -> str | None:
    """Return a scalar drive health value from direct or nested payloads."""
    if isinstance(value, dict):
        for key in DRIVE_HEALTH_KEYS:
            if text := _drive_health_text(value.get(key)):
                return text
        return None
    if isinstance(value, list):
        return None
    return _text(value)


def _drive_health(drive: dict[str, Any]) -> str | None:
    """Return normalized drive health label."""
    health_score = _drive_number(drive, ("healthScore", "health_score"))
    if health_score is not None:
        # UNAS diagnostics commonly report score 5 as healthy.
        if health_score >= 5:
            return "optimal"
        return "at_risk"

    raw = _raw_drive_health(drive)
    if raw is None:
        return None
    normalized = _normalized_token(raw)
    if normalized in {"healthy", "good", "ok", "normal", "passed", "optimal"}:
        return "optimal"
    if any(hint in normalized for hint in DISK_PROBLEM_HINTS):
        return "at_risk"
    return raw


def _drive_power_on_hours(drive: dict[str, Any]) -> int | None:
    """Return drive power-on hours."""
    value = _drive_number(drive, DRIVE_POWER_ON_HOUR_KEYS)
    if value is None:
        return None
    return int(round(value))
