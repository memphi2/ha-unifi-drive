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
DRIVE_LIFE_SPAN_KEYS = (
    "lifeSpan",
    "life_span",
    "lifespan",
    "lifeLeft",
    "life_left",
    "lifeRemaining",
    "life_remaining",
    "remainingLife",
    "remaining_life",
    "percentageLifeLeft",
)
DRIVE_MODEL_KEYS = (
    "model",
    "modelName",
    "model_name",
    "product",
    "productName",
)
DRIVE_CAPACITY_KEYS = (
    "size",
    "capacity",
    "sizeBytes",
    "size_bytes",
    "capacityBytes",
    "capacity_bytes",
)
DRIVE_BAD_SECTOR_KEYS = (
    "badSectorCount",
    "bad_sector_count",
    "reallocatedSectorCount",
    "reallocated_sector_count",
)
DRIVE_UNCORRECTABLE_SECTOR_KEYS = (
    "uncorrectableSectorCount",
    "uncorrectable_sector_count",
    "uncorrectableErrors",
)
DRIVE_MEDIA_TYPE_KEYS = (
    "type",
    "mediaType",
    "media_type",
    "media",
)
DRIVE_FIRMWARE_KEYS = (
    "firmware",
    "firmwareVersion",
    "firmware_version",
    "fwVersion",
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
    """Return display name for a drive.

    Falls back to a media-type-aware label ("SSD 1"/"HDD 1") so drives keep
    unique, suggestive names even when HDDs and SSDs reuse the same slot
    numbers across separate slot groups.
    """
    for key in ("name", "label", "displayName", "display_name", "diskName", "disk_name"):
        text = _text(drive.get(key))
        if text:
            return text
    slot = _text(drive.get("slotId")) or _text(drive.get("slot")) or _text(drive.get("bay"))
    prefix = _drive_media_type(drive) or "Drive"
    if slot:
        return f"{prefix} {slot}"
    return f"{prefix} {index + 1}"


def _pool_drive_count(pool: dict[str, Any]) -> int | None:
    """Return drive count for a pool."""
    drives = _pool_drives(pool)
    if drives:
        return len(drives)

    direct = _first_number(
        pool,
        (
            "driveCount",
            "diskCount",
            "memberCount",
            "numDrives",
            "numDisks",
            "numberOfDisks",
            "diskNum",
            "memberNum",
        ),
    )
    if direct is None:
        return None
    return int(round(direct))


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
    direct_drives = _collect_direct_pool_drives(pool)
    if direct_drives:
        return direct_drives

    nested_drives = _collect_nested_pool_drives(pool)
    if nested_drives:
        return nested_drives

    nested_raid_drives = _collect_nested_raid_drives(pool)
    if nested_raid_drives:
        return nested_raid_drives

    global_ref_drives = _collect_global_reference_drives(pool)
    if global_ref_drives:
        return global_ref_drives

    return _collect_raid_group_reference_drives(pool)


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


def _drive_life_span(drive: dict[str, Any]) -> int | None:
    """Return remaining-life percentage for a drive.

    Only SSDs report a ``lifeSpan`` field (0-100, higher is healthier); HDDs
    omit it entirely, so this returns ``None`` for spinning drives and the
    sensor stays unavailable for them.
    """
    value = _drive_number(drive, DRIVE_LIFE_SPAN_KEYS)
    if value is None:
        return None
    return int(round(max(0.0, min(100.0, value))))


def _drive_text(drive: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    """Return a drive text field from direct or nested detail containers."""
    for key in keys:
        if text := _text(drive.get(key)):
            return text
    for nested in _dict_values(drive, DRIVE_DETAIL_CONTAINER_KEYS):
        for key in keys:
            if text := _text(nested.get(key)):
                return text
    return None


def _drive_media_type(drive: dict[str, Any]) -> str | None:
    """Return the drive media type label (e.g. ``SSD``/``HDD``)."""
    return _drive_text(drive, DRIVE_MEDIA_TYPE_KEYS)


def _drive_model(drive: dict[str, Any]) -> str | None:
    """Return the drive model/product string."""
    return _drive_text(drive, DRIVE_MODEL_KEYS)


def _drive_capacity(drive: dict[str, Any]) -> float | None:
    """Return the drive capacity in bytes."""
    return _drive_number(drive, DRIVE_CAPACITY_KEYS)


def _drive_bad_sectors(drive: dict[str, Any]) -> int | None:
    """Return the drive bad/reallocated sector count."""
    value = _drive_number(drive, DRIVE_BAD_SECTOR_KEYS)
    if value is None:
        return None
    return int(round(value))


def _drive_uncorrectable_sectors(drive: dict[str, Any]) -> int | None:
    """Return the drive uncorrectable-sector count."""
    value = _drive_number(drive, DRIVE_UNCORRECTABLE_SECTOR_KEYS)
    if value is None:
        return None
    return int(round(value))


def _drive_attributes(drive: dict[str, Any]) -> dict[str, Any]:
    """Return per-drive SMART/identity metadata for entity attributes.

    Covers the fields that are not promoted to their own sensors, so a single
    drive entity carries the full context (media type, firmware, error rates,
    hot-spare flags) without one entity per field.
    """
    attrs: dict[str, Any] = {}
    for out_key, in_keys in (
        ("media_type", DRIVE_MEDIA_TYPE_KEYS),
        ("firmware", DRIVE_FIRMWARE_KEYS),
        ("nvme_version", ("nvmeVersion", "nvme_version")),
        ("state", ("state",)),
    ):
        if (value := _drive_text(drive, in_keys)) is not None:
            attrs[out_key] = value

    for out_key, in_keys in (
        ("rpm", ("rpm",)),
        ("read_error_rate", ("readErrorRate", "read_error_rate")),
        ("smart_read_error_count", ("smartReadErrorCount", "smart_read_error_count")),
    ):
        if (value := _drive_number(drive, in_keys)) is not None:
            attrs[out_key] = int(round(value))

    for out_key, in_key in (
        ("smart_test_supported", "smartTestSupported"),
        ("is_global_hot_spare", "isGlobalHotSpare"),
        ("is_local_hot_spare", "isLocalHotSpare"),
    ):
        value = drive.get(in_key)
        if isinstance(value, bool):
            attrs[out_key] = value

    return attrs


