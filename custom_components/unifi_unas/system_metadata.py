"""Shared UniFi OS metadata helper functions."""

from __future__ import annotations

import re
from typing import Any


def normalized_token(value: str) -> str:
    """Normalize text for fuzzy comparisons."""
    return re.sub(r"[^a-z0-9]", "", value.lower())


def system_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Return the merged UniFi OS system metadata payload.

    Two sources feed the system sensors:

    - ``_system`` is the UniFi OS core ``/api/system`` response. It is the
      richest source, but UniFi API keys cannot read it, so under API-key auth
      it degrades to a reduced anonymous payload lacking cpu/uptime/versions.
    - ``_device_info`` is the Drive application ``systems/device-info``
      response, which IS reachable with an API key and exposes cpu temperature,
      firmware/app versions, startup time and the network address.

    The Drive payload is used as the base and the core payload overlays it, so
    the core response keeps precedence when available (username/password auth)
    while the Drive payload transparently fills the gaps under API-key auth.
    """
    if not isinstance(data, dict):
        return {}
    system = data.get("_system")
    system = system if isinstance(system, dict) else {}
    device_info = data.get("_device_info")
    if isinstance(device_info, dict) and device_info:
        return {**device_info, **system}
    return system


def unifi_os_version(data: dict[str, Any]) -> str | None:
    """Return UniFi OS firmware version."""
    system = system_payload(data)
    hardware = system.get("hardware")
    if isinstance(hardware, dict) and (version := _text(hardware.get("firmwareVersion"))):
        return version
    return (
        _text(system.get("firmwareVersion"))
        or _text(system.get("firmware_version"))
        or _text(system.get("ucore_version"))
        or _text(system.get("version"))
    )


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

    # The Drive application ``device-info`` payload exposes the controller
    # version at the top level, which is the only source under API-key auth.
    return _text(system.get("version"))


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
    """Return stripped text for non-empty non-boolean values."""
    if isinstance(value, bool) or value in (None, ""):
        return None
    text = str(value).strip()
    return text or None
