"""Device metadata helpers for the UniFi Drive integration."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .const import DEFAULT_NAME
from .runtime import UnifiDriveConfigEntry
from .system_metadata import (
    _text,
    system_payload as _system_payload,
    unifi_os_version as _unifi_os_version,
)


def build_device_info(
    coordinator: Any,
    entry: UnifiDriveConfigEntry,
    device_identifier: str,
    *,
    configuration_url: str | None = None,
) -> DeviceInfo:
    """Build Home Assistant device metadata from UniFi OS system data."""
    payload = _device_metadata_payload(coordinator)
    system = _system_payload(payload)
    hardware_value = system.get("hardware")
    hardware: dict[str, Any] = (
        hardware_value if isinstance(hardware_value, dict) else {}
    )
    model = (
        _text(hardware.get("shortname"))
        or _text(hardware.get("name"))
        or DEFAULT_NAME
    )
    sw_version = _unifi_os_version(payload)

    kwargs: dict[str, Any] = {
        "identifiers": {(DOMAIN, device_identifier)},
        "manufacturer": "Ubiquiti",
        "model": model,
        "name": entry.title,
        "configuration_url": configuration_url
        or getattr(getattr(coordinator, "client", None), "base_url", None),
    }
    if sw_version:
        kwargs["sw_version"] = sw_version
    return DeviceInfo(**kwargs)


def device_registry_metadata(device_info: DeviceInfo) -> dict[str, str]:
    """Extract non-empty registry text from modern or legacy HA device info."""
    metadata: dict[str, str] = {}
    for key in ("manufacturer", "model", "sw_version", "configuration_url"):
        if isinstance(device_info, dict):
            # Home Assistant before 2026.11 represents DeviceInfo as a dict.
            value = device_info.get(key)
        else:
            value = getattr(device_info, key, None)
        # Unset dataclass fields contain truthy UNDEFINED, not None.
        if isinstance(value, str) and value:
            metadata[key] = value
    return metadata


def _device_metadata_payload(coordinator: Any) -> dict[str, Any]:
    """Return the best available system metadata payload for device info."""
    payload = getattr(coordinator, "data", None)
    if isinstance(payload, dict):
        if _system_payload(payload):
            return payload
        if _looks_like_system_payload(payload):
            return {"_system": payload}

    client_system = getattr(getattr(coordinator, "client", None), "_system_info", None)
    if isinstance(client_system, dict):
        return {"_system": client_system}

    return {}


def _looks_like_system_payload(payload: dict[str, Any]) -> bool:
    """Return whether a raw payload looks like UniFi OS system metadata."""
    return any(
        key in payload
        for key in (
            "hardware",
            "firmwareVersion",
            "firmware_version",
            "ucore_version",
            "version",
        )
    )
