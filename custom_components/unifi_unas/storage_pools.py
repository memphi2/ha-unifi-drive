"""Storage pool status and progress helper functions."""

from __future__ import annotations

import re
from typing import Any

from .storage_common import (
    DEGRADED_STATUSES,
    DISK_PROBLEM_HINTS,
    HEALTHY_STATUSES,
    POOL_MAINTENANCE_HINTS,
    _first_number,
    _looks_like_machine_identifier,
    _normalize_percent,
    _slug,
    _text,
)
from .storage_drives import _pool_at_risk_drive_count, _pool_drive_temperatures
from .system_metadata import normalized_token as _normalized_token

RAID_LEVEL_KEYS = (
    "raidType",
    "raid_type",
    "raidLevel",
    "raid_level",
    "poolType",
    "pool_type",
    "protection",
    "protectionLevel",
    "protection_level",
    "layout",
    "type",
    "preferLevel",
)
POOL_INDEX_KEY_RE = re.compile(r"^pool_(\d+)$")
POOL_LIST_KEYS = (
    "pools",
    "storagePools",
    "storage_pools",
    "volumes",
    "volumeList",
)
POOL_CONTAINER_KEYS = (
    "storage",
    "storageInfo",
    "storage_info",
    "data",
    "result",
)
POOL_LIKE_KEYS = {
    "available",
    "availableBytes",
    "capacity",
    "disks",
    "drives",
    "free",
    "freeBytes",
    "members",
    "raid",
    "raidGroup",
    "raidLevel",
    "raidType",
    "size",
    "status",
    "state",
    "total",
    "totalBytes",
    "used",
    "usedBytes",
    "usage",
}
POOL_IDENTITY_KEYS = {
    "displayName",
    "display_name",
    "guid",
    "id",
    "label",
    "name",
    "poolGuid",
    "pool_guid",
    "poolId",
    "pool_id",
    "poolName",
    "pool_name",
    "storagePoolId",
    "storage_pool_id",
    "uuid",
    "volumeId",
    "volume_id",
}
POOL_REFERENCE_IDENTITY_KEYS = {
    "poolGuid",
    "pool_guid",
    "poolId",
    "pool_id",
    "storagePoolId",
    "storage_pool_id",
    "volumeId",
    "volume_id",
}
POOL_SPARSE_IDENTITY_KEYS = POOL_IDENTITY_KEYS - POOL_REFERENCE_IDENTITY_KEYS
POOL_SPECIFIC_IDENTITY_KEYS = {
    "poolName",
    "pool_name",
}
POOL_STATUS_KEYS = {"condition", "health", "healthStatus", "state", "status"}
POOL_CAPACITY_KEYS = {
    "available",
    "availableBytes",
    "capacity",
    "free",
    "freeBytes",
    "size",
    "total",
    "totalBytes",
    "used",
    "usedBytes",
    "usage",
}
POOL_RAID_KEYS = {"raid", "raidGroup", "raidLevel", "raidType"}
POOL_MEMBER_KEYS = {"disks", "drives", "members"}
DRIVE_IDENTITY_KEYS = {
    "bay",
    "diskName",
    "disk_name",
    "serial",
    "slot",
    "slotId",
    "wwn",
}


def _pools(data: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Return storage pools from the API response."""
    if not data:
        return []
    pools = _pool_list(data)
    if not pools:
        return []
    disks_list = _global_disks(data)

    normalized: list[dict[str, Any]] = []
    for pool in pools:
        if not isinstance(pool, dict):
            continue
        pool_with_context = dict(pool)
        pool_with_context["__global_disks"] = disks_list
        normalized.append(pool_with_context)
    return normalized


def _global_disks(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return global disk entries from direct or nested storage payloads."""
    disks: list[dict[str, Any]] = []
    for key in ("disks", "drives", "hdds"):
        value = data.get(key)
        if isinstance(value, list):
            disks.extend(item for item in value if isinstance(item, dict))

    for key in POOL_CONTAINER_KEYS:
        value = data.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    disks.extend(_global_disks(item))
        if isinstance(value, dict):
            disks.extend(_global_disks(value))
    return _dedupe_dicts(disks)


def _dedupe_dicts(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return dictionaries de-duplicated by stable identity fields."""
    deduped: dict[str, dict[str, Any]] = {}
    for index, value in enumerate(values):
        key = (
            _text(value.get("serial"))
            or _text(value.get("id"))
            or _text(value.get("uuid"))
            or _text(value.get("guid"))
            or str(index)
        )
        existing = deduped.get(key)
        deduped[key] = _merge_disk_entries(existing, value) if existing else value
    return list(deduped.values())


def _merge_disk_entries(existing: dict[str, Any], value: dict[str, Any]) -> dict[str, Any]:
    """Merge duplicate disk entries without dropping richer existing fields."""
    merged = dict(existing)
    for key, item in value.items():
        current = merged.get(key)
        if _is_missing_value(current):
            merged[key] = item
        elif isinstance(current, dict) and isinstance(item, dict):
            merged[key] = _merge_disk_entries(current, item)
        elif isinstance(item, dict):
            merged[key] = _merge_disk_entries({"value": current}, item)
        elif isinstance(current, dict) and not _is_missing_value(item):
            merged[key] = _merge_disk_entries(current, {"value": item})
        else:
            merged[key] = item
    return merged


def _is_missing_value(value: Any) -> bool:
    """Return whether a disk field should be filled from a duplicate record."""
    return value in (None, "", [], {})


def _pool_list(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the first known list of pool-like dictionaries."""
    direct = _pool_list_from_direct_container(data)
    if direct:
        return direct

    alternate = _pool_list_from_alternate_keys(data)
    if alternate:
        return alternate

    return _pool_list_from_nested_containers(data)


def _pool_list_from_direct_container(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return direct or standard pool keys before recursive extraction."""
    direct_pools = data.get("pools")
    if isinstance(direct_pools, list):
        pools = [pool for pool in direct_pools if isinstance(pool, dict)]
        if pools:
            return pools
    return []


def _pool_list_from_alternate_keys(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return pool lists from non-direct known alias keys."""
    for key in POOL_LIST_KEYS[1:]:
        value = data.get(key)
        if not isinstance(value, list):
            continue
        pools = _pool_list_from_items(value, require_signature=False)
        if pools:
            return pools
    return []


def _pool_list_from_nested_containers(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return pools from nested container payload sections."""
    for key in POOL_CONTAINER_KEYS:
        value = data.get(key)
        if isinstance(value, list):
            pools = _pool_list_from_items(value)
            if pools:
                return pools
        elif isinstance(value, dict):
            pools = _pool_list(value)
            if pools:
                return pools
    return []


def _pool_list_from_items(
    value: list[Any],
    *,
    require_signature: bool = True,
) -> list[dict[str, Any]]:
    """Return pools from a list, recursing into wrappers before accepting items."""
    pools: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        if not require_signature and _is_explicit_pool_entry(item):
            pools.append(item)
            continue
        nested_pools = _pool_list(item)
        if nested_pools:
            pools.extend(nested_pools)
        elif _is_pool_like(item):
            pools.append(item)
    return pools


def _is_explicit_pool_entry(value: dict[str, Any]) -> bool:
    """Return whether an explicit pool-list item should be kept as a pool."""
    return _is_pool_like(value) or _is_sparse_explicit_pool(value)


def _is_sparse_explicit_pool(value: dict[str, Any]) -> bool:
    """Return whether an explicit pool-list item has sparse pool identity."""
    keys = {str(key) for key in value}
    if {"data", "items", "metadata", "meta", "result"}.intersection(keys):
        return False
    return bool(POOL_SPARSE_IDENTITY_KEYS.intersection(keys)) and bool(
        POOL_STATUS_KEYS.intersection(keys)
    )


def _is_pool_like(value: dict[str, Any]) -> bool:
    """Return whether a dictionary looks like a storage pool."""
    keys = {str(key) for key in value}
    if not POOL_LIKE_KEYS.intersection(keys):
        return False

    has_capacity = bool(POOL_CAPACITY_KEYS.intersection(keys))
    has_identity = bool(POOL_IDENTITY_KEYS.intersection(keys))
    has_pool_identity = bool(POOL_SPECIFIC_IDENTITY_KEYS.intersection(keys))
    has_members = bool(POOL_MEMBER_KEYS.intersection(keys))
    has_raid = bool(POOL_RAID_KEYS.intersection(keys))
    has_status = bool(POOL_STATUS_KEYS.intersection(keys))
    has_drive_identity = bool(DRIVE_IDENTITY_KEYS.intersection(keys))

    if has_drive_identity and not (has_members or has_raid or has_pool_identity):
        return False

    return has_raid or (
        has_capacity and (has_identity or has_status or has_members)
    ) or (has_members and (has_identity or has_status))


def _pool_key(pool: dict[str, Any], index: int) -> str:
    """Return a stable-ish key for a pool."""
    for key in (
        "id",
        "uuid",
        "guid",
        "name",
        "label",
        "poolName",
        "pool_name",
        "poolId",
        "pool_id",
        "storagePoolId",
        "storage_pool_id",
        "volumeId",
        "volume_id",
    ):
        value = pool.get(key)
        if value not in (None, ""):
            return _slug(str(value))
    return f"pool_{index + 1}"


def _pool_from_key(
    data: dict[str, Any] | None,
    key: str,
) -> tuple[dict[str, Any] | None, int | None]:
    """Return pool and index for a pool key, including legacy key formats."""
    pools = _pools(data)
    for index, pool in enumerate(pools):
        if _pool_key(pool, index) == key:
            return pool, index

    legacy_match = POOL_INDEX_KEY_RE.fullmatch(key)
    if legacy_match:
        legacy_index = int(legacy_match.group(1)) - 1
        if 0 <= legacy_index < len(pools):
            return pools[legacy_index], legacy_index

    legacy_normalized = _normalized_token(key)
    if legacy_normalized:
        for index, pool in enumerate(pools):
            for raw_value in (
                _text(pool.get("id")),
                _text(pool.get("uuid")),
                _text(pool.get("guid")),
                _text(pool.get("poolId")),
                _text(pool.get("pool_id")),
                _text(pool.get("storagePoolId")),
                _text(pool.get("storage_pool_id")),
                _text(pool.get("volumeId")),
                _text(pool.get("volume_id")),
                _text(pool.get("name")),
                _text(pool.get("label")),
                _pool_name(pool, index),
            ):
                if raw_value and _normalized_token(raw_value) == legacy_normalized:
                    return pool, index

    return None, None


def _pool_name(pool: dict[str, Any], index: int) -> str:
    """Return display name for a pool."""
    for key in ("name", "label", "displayName", "display_name", "poolName", "pool_name"):
        value = pool.get(key)
        text = _text(value)
        if text:
            return text

    # Keep UUID-like identifiers for diagnostics/unique keys, but avoid exposing
    # them as the primary user-facing pool name.
    for key in (
        "id",
        "uuid",
        "guid",
        "poolId",
        "pool_id",
        "storagePoolId",
        "storage_pool_id",
        "volumeId",
        "volume_id",
    ):
        text = _text(pool.get(key))
        if text and not _looks_like_machine_identifier(text):
            return text

    return f"Pool {index + 1}"


def _raw_pool_status(pool: dict[str, Any]) -> str | None:
    """Return raw pool status."""
    for key in ("status", "state", "health", "healthStatus", "condition"):
        if status := _status_text(pool.get(key)):
            return status
    return None


def _status_text(value: Any) -> str | None:
    """Return a scalar status string from direct or nested status payloads."""
    if isinstance(value, dict):
        for key in ("status", "state", "health", "healthStatus", "condition"):
            if status := _status_text(value.get(key)):
                return status
        return None
    if isinstance(value, list):
        return None
    return _text(value)


def _pool_status(pool: dict[str, Any]) -> str | None:
    """Normalize pool status."""
    raw_status = _raw_pool_status(pool)
    if raw_status is None:
        return None
    status = raw_status.strip()
    normalized = re.sub(r"[^a-z0-9]", "", status.lower())
    if normalized in HEALTHY_STATUSES:
        return "healthy"
    if normalized in DEGRADED_STATUSES:
        return "degraded"
    if any(hint in normalized for hint in DISK_PROBLEM_HINTS):
        return "degraded"
    return status


def _aggregate_status(data: dict[str, Any]) -> str | None:
    """Return aggregate status across all pools."""
    pools = _pools(data)
    if not pools:
        return None

    statuses = [_pool_status(pool) for pool in pools]
    known = [status for status in statuses if status is not None]
    if not known:
        return None
    if any(status == "degraded" for status in known):
        return "degraded"
    if all(status == "healthy" for status in known):
        return "healthy"
    return known[0]


def _cache_status(data: dict[str, Any]) -> str | None:
    """Return normalized SSD cache health status.

    The RAID1 SSD cache health lives in a pool's ``cache`` block
    (``cache.status``, e.g. ``fullyOperational``), separate from the pool's own
    data-array status. Returns None when no pool exposes an SSD cache.
    """
    for pool in _pools(data):
        cache = pool.get("cache")
        if not isinstance(cache, dict):
            continue
        raw_status = _text(cache.get("status"))
        if raw_status is None:
            continue
        normalized = re.sub(r"[^a-z0-9]", "", raw_status.lower())
        if normalized in HEALTHY_STATUSES:
            return "healthy"
        if normalized in DEGRADED_STATUSES:
            return "degraded"
        if any(hint in normalized for hint in DISK_PROBLEM_HINTS):
            return "degraded"
        return raw_status
    return None


def _degraded_pool_count(data: dict[str, Any]) -> int:
    """Return how many pools are currently degraded."""
    return sum(1 for pool in _pools(data) if _pool_status(pool) == "degraded")


def _maintenance_pool_count(data: dict[str, Any]) -> int:
    """Return how many pools are in maintenance (sync/rebuild/repair)."""
    return sum(1 for pool in _pools(data) if _pool_in_maintenance(pool))


def _at_risk_disk_count(data: dict[str, Any]) -> int:
    """Return total at-risk disk count across all pools."""
    return sum(_pool_at_risk_drive_count(pool) or 0 for pool in _pools(data))


def _average_disk_temperature(data: dict[str, Any]) -> float | None:
    """Return average temperature across all known drives."""
    values: list[float] = []
    for pool in _pools(data):
        values.extend(_pool_drive_temperatures(pool))
    if not values:
        return None
    return round(sum(values) / len(values), 1)


def _pool_raid_level(pool: dict[str, Any]) -> str | None:
    """Return the best-effort RAID level for a pool."""
    for key in RAID_LEVEL_KEYS:
        value = _text(pool.get(key))
        if value:
            return value

    data = pool.get("raid")
    if isinstance(data, dict):
        for key in ("type", "level", "name", "mode"):
            value = _text(data.get(key))
            if value:
                return value
    if isinstance(data, str):
        return _text(data)
    return None


def _pool_rebuild_progress(pool: dict[str, Any]) -> float | None:
    """Return rebuild/resilver progress in percent for a pool."""
    value = _pool_progress(
        pool,
        primary_keys=("rebuildProgress", "rebuild_percent", "resilverProgress"),
        context_hints=("rebuild", "resilver"),
    )
    if value is not None:
        return value
    # UniFi Drive (UNAS) reports RAID rebuild/resync progress per raid group.
    return _raid_group_progress(pool)


def _pool_sync_progress(pool: dict[str, Any]) -> float | None:
    """Return sync progress in percent for a pool."""
    value = _pool_progress(
        pool,
        primary_keys=("syncProgress", "sync_percent", "initializeProgress"),
        context_hints=("sync", "initialize"),
    )
    if value is not None:
        return value
    # UniFi Drive (UNAS) exposes data-sync progress under ``dataScrubbing``.
    return _data_scrubbing_progress(pool)


def _raid_group_progress(pool: dict[str, Any]) -> float | None:
    """Return the RAID rebuild/resync progress of a UniFi Drive pool.

    The UNAS payload has no dedicated rebuild field; each data raid group carries
    a generic ``progress`` (0 while healthy/idle, climbing during a rebuild).
    """
    groups = pool.get("raidGroups")
    if not isinstance(groups, list):
        return None
    best: float | None = None
    for group in groups:
        if not isinstance(group, dict) or group.get("isSSDCache"):
            continue
        normalized = _normalize_percent(group.get("progress"))
        if normalized is None:
            continue
        best = normalized if best is None else max(best, normalized)
    return best


def _data_scrubbing_progress(pool: dict[str, Any]) -> float | None:
    """Return the data-scrubbing/sync progress of a UniFi Drive pool.

    When idle the ``dataScrubbing`` object reports a status but no progress
    number, so a running scrub reads its percentage while an idle-but-present
    scrubber reports 0 rather than an unknown state.
    """
    scrub = pool.get("dataScrubbing")
    if not isinstance(scrub, dict):
        return None
    normalized = _normalize_percent(scrub.get("progress"))
    if normalized is not None:
        return normalized
    status = scrub.get("status")
    if isinstance(status, str) and status.strip():
        return 0.0
    return None


def _pool_has_problem(pool: dict[str, Any]) -> bool:
    """Return whether a pool currently has a detected problem."""
    if _pool_status(pool) == "degraded":
        return True
    at_risk = _pool_at_risk_drive_count(pool)
    return bool(at_risk and at_risk > 0)


def _pool_in_maintenance(pool: dict[str, Any]) -> bool:
    """Return whether a pool appears to be syncing/rebuilding."""
    for value in (_pool_rebuild_progress(pool), _pool_sync_progress(pool)):
        if value is not None and 0 < value < 100:
            return True

    raw_status = _raw_pool_status(pool)
    if raw_status:
        normalized = _normalized_token(raw_status)
        if any(hint in normalized for hint in POOL_MAINTENANCE_HINTS):
            return True
    return False


def _pool_progress(
    pool: dict[str, Any],
    *,
    primary_keys: tuple[str, ...],
    context_hints: tuple[str, ...],
) -> float | None:
    """Return a normalized pool progress value in percent."""
    direct = _first_number(pool, primary_keys)
    if direct is None:
        progress = pool.get("progress")
        if isinstance(progress, dict):
            direct = _first_number(progress, primary_keys)

    if direct is None:
        direct = _find_progress_in_tree(pool, context_hints=context_hints)

    return _normalize_percent(direct)


def _find_progress_in_tree(
    value: Any,
    *,
    context: str = "",
    context_hints: tuple[str, ...],
) -> float | None:
    """Find a nested progress value scoped by context hints."""
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            normalized_key = _normalized_token(key_text)
            next_context = f"{context}.{key_text}" if context else key_text
            normalized_context = _normalized_token(next_context)

            if isinstance(child, (int, float, str)) and (
                "progress" in normalized_key
                or "percent" in normalized_key
                or normalized_key == "pct"
            ) and any(hint in normalized_context for hint in context_hints):
                try:
                    return float(child)
                except (TypeError, ValueError):
                    pass

            found = _find_progress_in_tree(
                child,
                context=next_context,
                context_hints=context_hints,
            )
            if found is not None:
                return found

    if isinstance(value, list):
        for item in value:
            found = _find_progress_in_tree(
                item,
                context=context,
                context_hints=context_hints,
            )
            if found is not None:
                return found

    return None
