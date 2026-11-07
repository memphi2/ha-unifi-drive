"""Shared UniFi OS metadata helper functions."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any


def normalized_token(value: str) -> str:
    """Normalize text for fuzzy comparisons."""
    return re.sub(r"[^a-z0-9]", "", value.lower())


def system_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Fill monitoring gaps without mixing Drive identity/status into UniFi OS."""
    system = data.get("_system")
    system = system if isinstance(system, dict) else {}
    device_info = data.get("_device_info")
    if not isinstance(device_info, dict):
        return system
    merged = dict(system)
    for key in ("cpu", "networkInterfaces"):
        fallback = device_info.get(key)
        current = system.get(key)
        if not isinstance(fallback, (dict, list)) or not fallback:
            continue
        if isinstance(fallback, dict) and isinstance(current, dict):
            merged[key] = {
                **fallback,
                **{name: value for name, value in current.items() if value not in (None, "")},
            }
        elif current in (None, "", [], {}):
            merged[key] = fallback
    uptime_keys = (
        "uptime", "uptimeSeconds", "uptime_seconds", "uptimeSec", "uptime_sec",
        "uptimeMs", "uptime_ms", "uptimeMillis",
    )
    if not any(system.get(key) is not None for key in uptime_keys):
        merged["uptime"] = device_info.get("uptime")
    return merged


def sampled_device_info(payload: dict[str, Any], now: datetime) -> dict[str, Any]:
    """Sample startup-derived uptime once per successful read, not per property."""
    result = dict(payload)
    # Only the sampled value is used: an old startupTime must not advance offline.
    result.pop("uptime", None)
    started = payload.get("startupTime")
    if not isinstance(started, str):
        return result
    try:
        timestamp = datetime.fromisoformat(started.replace("Z", "+00:00"))
    except ValueError:
        return result
    if timestamp.tzinfo is not None:
        seconds = (now - timestamp).total_seconds()
        if seconds >= 0:
            result["uptime"] = seconds
    return result


def unifi_os_version(data: dict[str, Any]) -> str | None:
    """Return UniFi OS firmware version."""
    system = system_payload(data)
    hardware = system.get("hardware")
    if isinstance(hardware, dict) and (version := _text(hardware.get("firmwareVersion"))):
        return version
    version = (
        _text(system.get("firmwareVersion"))
        or _text(system.get("firmware_version"))
        or _text(system.get("ucore_version"))
        or _text(system.get("version"))
    )
    if version:
        return version
    device_info = data.get("_device_info")
    if isinstance(device_info, dict):
        return _text(device_info.get("firmwareVersion"))
    return None


def drive_version(data: dict[str, Any]) -> str | None:
    """Return installed UniFi Drive application version."""
    system = system_payload(data)
    apps = system.get("apps")
    if isinstance(apps, dict):
        for key in ("controllers", "apps", "applications"):
            if version := _drive_version_from_items(apps.get(key)):
                return version

    for key in ("controllers", "apps", "applications"):
        if version := _drive_version_from_items(system.get(key)):
            return version
    device_info = data.get("_device_info")
    if isinstance(device_info, dict):
        return _text(device_info.get("version"))
    return None


def _drive_version_from_items(value: Any) -> str | None:
    """Return a Drive application version from a list-like payload."""
    if not isinstance(value, list):
        return None
    for item in value:
        if not isinstance(item, dict):
            continue
        app_name = normalized_token(
            str(item.get("name") or item.get("id") or item.get("slug") or "")
        )
        if app_name not in {"drive", "unifidrive"}:
            continue
        version = (
            _text(item.get("versionRaw"))
            or _text(item.get("version"))
            or _text(item.get("uiVersion"))
            or _text(item.get("currentVersion"))
        )
        if version:
            return version
    return None


def _text(value: Any) -> str | None:
    """Return a version/name string without rendering structured payload values."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None
