"""Payload normalization helpers for UniFi Drive snapshot targets."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .api_errors import UnexpectedResponse
from .snapshot_schedule import _snapshot_schedule_frequency, _snapshot_schedule_time
from .snapshot_types import normalize_snapshot_target_type
from .snapshot_values import (
    _dict_from_item,
    _first_bool_value,
    _first_int_value,
    _value_from_dict,
)


def validated_snapshot_settings(
    payload: Any, *, current_user_id: str | None = None,
) -> list[dict[str, Any]]:
    """Reject malformed reads before they can replace the known target list."""
    data = payload.get("data", payload) if isinstance(payload, dict) else payload
    if isinstance(data, list):
        item_count = len(data)
    elif isinstance(data, dict) and {"personal", "shared"}.intersection(data):
        sections = [data[key] for key in ("personal", "shared") if key in data]
        if not all(isinstance(section, list) for section in sections):
            raise UnexpectedResponse("Invalid snapshot settings response structure")
        item_count = sum(len(section) for section in sections)
    else:
        raise UnexpectedResponse("Invalid snapshot settings response structure")

    settings = extract_snapshot_settings(payload, current_user_id=current_user_id)
    if len(settings) != item_count:
        raise UnexpectedResponse("Snapshot settings response contains unreadable targets")
    return settings


def extract_snapshot_settings(
    payload: Any,
    *,
    current_user_id: str | None = None,
) -> list[dict[str, Any]]:
    """Extract normalized snapshot target settings from endpoint payload."""
    data = payload.get("data", payload) if isinstance(payload, dict) else payload
    if isinstance(data, list):
        return _extract_snapshot_settings_from_list(
            data,
            current_user_id=current_user_id,
        )
    if not isinstance(data, dict):
        return []

    return (
        _extract_snapshot_personal_from_payload(
            data.get("personal"),
            current_user_id=current_user_id,
        )
        + _extract_snapshot_shared_from_payload(
            data.get("shared"),
        )
    )


def _extract_snapshot_personal_from_payload(
    value: Any,
    *,
    current_user_id: str | None,
) -> list[dict[str, Any]]:
    """Extract personal snapshot settings from a list payload."""
    if not isinstance(value, list):
        return []
    return _extract_snapshot_personal_from_items(
        value,
        current_user_id=current_user_id,
    )


def _extract_snapshot_shared_from_payload(value: Any) -> list[dict[str, Any]]:
    """Extract shared snapshot settings from a list payload."""
    if not isinstance(value, list):
        return []
    return _extract_snapshot_shared_from_items(value)


def _snapshot_shared_target_id(item: dict[str, Any]) -> str | None:
    """Return shared snapshot target id with fallback to display name."""
    shared_drive = _dict_from_item(item, ("sharedDrive", "shared_drive", "drive"))
    return (
        _value_from_dict(shared_drive, ("id", "uuid", "name"))
        or _value_from_dict(item, ("sharedDriveId", "shared_drive_id"))
        or _value_from_dict(item, ("id",))
        or _value_from_dict(shared_drive, ("name", "id", "uuid"))
        or _value_from_dict(item, ("sharedDriveName", "shared_drive_name", "name"))
    )


def _snapshot_shared_target_name(item: dict[str, Any]) -> str | None:
    """Return shared snapshot target display name if discoverable."""
    shared_drive = _dict_from_item(item, ("sharedDrive", "shared_drive", "drive"))
    return (
        _value_from_dict(shared_drive, ("name", "id", "uuid"))
        or _value_from_dict(item, ("sharedDriveName", "shared_drive_name", "name"))
    )


def _extract_snapshot_settings_from_list(
    items: list[Any],
    *,
    current_user_id: str | None,
) -> list[dict[str, Any]]:
    """Extract snapshot targets from list-shaped payload variants."""
    settings: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        target_type = _snapshot_target_type(item)
        if target_type == "mydrive":
            settings.extend(
                _extract_snapshot_personal_from_items([item], current_user_id=current_user_id)
            )
            continue

        if target_type != "shared":
            continue

        settings.extend(_extract_snapshot_shared_from_items([item]))

    return settings


def _extract_snapshot_personal_from_items(
    items: list[dict[str, Any]],
    *,
    current_user_id: str | None,
) -> list[dict[str, Any]]:
    """Map one or more list-like payload items to personal snapshot settings."""
    settings: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        user = _dict_from_item(item, ("user", "owner"))
        target_id, user_id = _personal_snapshot_identity(item, user)
        if target_id is None:
            continue
        settings.append(
            _snapshot_setting_from_item(
                item,
                target_type="mydrive",
                target_id=target_id,
                target_name=(
                    _user_display_name(user)
                    or _value_from_dict(item, ("name", "targetName"))
                    or "My Drive"
                ),
                user_id=user_id,
                is_current_user=_snapshot_target_is_current_user(
                    current_user_id,
                    user_id,
                    target_id,
                ),
            )
        )
    return settings


def _extract_snapshot_shared_from_items(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Map one or more list-like payload items to shared snapshot settings."""
    settings: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        shared_name = _snapshot_shared_target_name(item)
        if not shared_name:
            continue
        shared_id = _snapshot_shared_target_id(item) or shared_name
        settings.append(
            _snapshot_setting_from_item(
                item,
                target_type="shared",
                target_id=shared_id,
                target_name=shared_name,
                shared_drive_name=shared_name,
            )
        )
    return settings


def _snapshot_setting_from_item(
    item: dict[str, Any],
    *,
    target_type: str,
    target_id: str,
    target_name: str,
    user_id: str | None = None,
    is_current_user: bool = False,
    shared_drive_name: str | None = None,
) -> dict[str, Any]:
    """Return a normalized snapshot target setting."""
    schedule = item.get("schedule")
    if not isinstance(schedule, dict):
        schedule = {}

    max_count = _first_int_value(item, ("maxCount", "max_count"))
    total_count = _first_int_value(item, ("totalCount", "total_count"))
    locked_count = _first_int_value(item, ("lockedCount", "locked_count"))
    explicit_enabled = _first_bool_value(item, ("enabled", "enable"))
    schedule_enabled = _first_bool_value(schedule, ("enable", "enabled"))
    schedule_frequency = _snapshot_schedule_frequency(schedule, schedule_enabled)
    schedule_time = _snapshot_schedule_time(schedule)
    enabled = (
        explicit_enabled
        if explicit_enabled is not None
        else bool(max_count and max_count > 0)
    )

    return {
        "id": str(target_id),
        "name": str(target_name),
        "type": target_type,
        "user_id": user_id,
        "is_current_user": is_current_user,
        "shared_drive_name": shared_drive_name,
        "enabled": enabled,
        "max_count": max_count,
        "total_count": total_count,
        "locked_count": locked_count,
        "paused": _first_bool_value(item, ("paused",)) or False,
        "restoring_drive": _first_bool_value(
            item,
            ("restoringDrive", "restoring_drive"),
        )
        or False,
        "schedule_enabled": schedule_enabled or False,
        "schedule_frequency": schedule_frequency,
        "schedule_time": schedule_time,
        "schedule_weekdays": _value_from_dict(
            schedule,
            ("weekdays", "weekDays", "week_days"),
        ),
        "schedule_monthdays": _value_from_dict(
            schedule,
            ("monthdays", "monthDays", "month_days"),
        ),
    }


def _snapshot_target_type(item: Any) -> str | None:
    """Return a normalized snapshot target type for list-shaped payload items."""
    if not isinstance(item, Mapping):
        return None

    value = normalize_snapshot_target_type(
        item.get("type")
        or item.get("targetType")
        or item.get("target_type")
        or ""
    )
    if value in {"mydrive", "shared"}:
        return value
    if any(key in item for key in ("sharedDrive", "shared_drive", "sharedDriveName")):
        return "shared"
    if any(key in item for key in ("user", "owner")):
        return "mydrive"
    return None


def _snapshot_target_type_normalized(target: Any) -> str:
    """Return the normalized snapshot target type string."""
    return _snapshot_target_type(target) or ""


def _personal_snapshot_identity(
    item: dict[str, Any],
    user: dict[str, Any],
) -> tuple[str | None, str | None]:
    """Return stable target/user identifiers for a personal snapshot target."""
    user_id = (
        _value_from_dict(user, ("id", "unique_id", "uuid"))
        or _value_from_dict(
            item,
            (
                "userId",
                "user_id",
                "ownerId",
                "owner_id",
                "accountId",
                "account_id",
            ),
        )
    )
    target_id = user_id or _value_from_dict(
        item,
        (
            "targetId",
            "target_id",
            "driveId",
            "drive_id",
            "personalDriveId",
            "personal_drive_id",
            "id",
            "uuid",
        ),
    )
    return target_id, user_id


def _snapshot_target_is_current_user(
    current_user_id: str | None,
    user_id: str | None,
    target_id: str,
) -> bool:
    """Return whether a personal snapshot target belongs to the logged-in user."""
    return current_user_id is not None and current_user_id in (user_id, target_id)


def _user_display_name(user: dict[str, Any]) -> str | None:
    """Return the preferred display name for a personal drive user."""
    first_name = _value_from_dict(user, ("firstName", "first_name"))
    last_name = _value_from_dict(user, ("lastName", "last_name"))
    name_parts = [
        part
        for part in (first_name, last_name)
        if isinstance(part, str) and part
    ]
    full_name = " ".join(name_parts).strip()
    if full_name:
        return full_name

    return _value_from_dict(user, ("displayName", "display_name", "name", "username"))
