"""Low-level value helpers for UniFi Drive snapshot payloads."""

from __future__ import annotations

from typing import Any


def _dict_from_item(value: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    """Return the first dict value from the provided keys."""
    for key in keys:
        item = value.get(key)
        if isinstance(item, dict):
            return item
    return {}


def _value_from_dict(value: Any, keys: tuple[str, ...]) -> str | None:
    """Return first non-empty string value from a dict."""
    if not isinstance(value, dict):
        return None
    for key in keys:
        item = value.get(key)
        if item not in (None, ""):
            return str(item)
    return None


def _first_int_value(value: dict[str, Any], keys: tuple[str, ...]) -> int | None:
    """Return first integer value from a dict."""
    for key in keys:
        result = _int_value(value.get(key))
        if result is not None:
            return result
    return None


def _int_value(value: Any) -> int | None:
    """Return an integer value when possible."""
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _first_bool_value(value: dict[str, Any], keys: tuple[str, ...]) -> bool | None:
    """Return first boolean-like value from a dict."""
    for key in keys:
        result = _bool_value(value.get(key))
        if result is not None:
            return result
    return None


def _bool_value(value: Any) -> bool | None:
    """Return a boolean value when possible."""
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "on", "enabled"}:
        return True
    if normalized in {"false", "0", "no", "off", "disabled"}:
        return False
    return None


def _payload_debug_shape(payload: Any) -> dict[str, Any] | str:
    """Return only structure counts; object keys may be local identifiers too."""
    if not isinstance(payload, dict):
        return type(payload).__name__

    shape: dict[str, Any] = {"top_level_count": len(payload)}
    data = payload.get("data")
    if isinstance(data, dict):
        shape["data_type"] = "dict"
        shape["data_count"] = len(data)
    elif isinstance(data, list):
        shape["data_type"] = "list"
        shape["data_count"] = len(data)
    return shape
