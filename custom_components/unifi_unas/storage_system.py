"""UniFi OS system metadata helper functions."""

from __future__ import annotations

from datetime import UTC, datetime
from ipaddress import ip_address
from typing import Any

from .storage_common import _dict_values, _first_number, _text
from .system_metadata import (
    normalized_token as _normalized_token,
    system_payload as _system_payload,
)

NETWORK_ADDRESS_KEYS = (
    "ip",
    "ipv4",
    "ipv6",
    "ipAddress",
    "ip_address",
    "ipv4Address",
    "ipv4_address",
    "ipv6Address",
    "ipv6_address",
    "address",
    "localIp",
    "local_ip",
)
NETWORK_CONTAINER_KEYS = (
    "addresses",
    "ipAddresses",
    "ip_addresses",
    "wans",
    "lans",
    "interfaces",
    "networkInterfaces",
    "networks",
    "ports",
)


def _system_ip(data: dict[str, Any]) -> str | None:
    """Return the system IP address."""
    system = _system_payload(data)
    for key in NETWORK_ADDRESS_KEYS:
        if ip := _ip_text(system.get(key)):
            return ip

    for key in NETWORK_CONTAINER_KEYS:
        values = system.get(key)
        if ip := _ip_from_value(values):
            return ip

    for nested in _dict_values(system, ("network", "wan", "lan", "ethernet")):
        if ip := _ip_from_mapping(nested):
            return ip
    return None


def _system_uptime_hours(data: dict[str, Any]) -> float | None:
    """Return UniFi OS uptime in hours."""
    system = _system_payload(data)
    uptime_seconds = _first_number(
        system,
        ("uptime", "uptimeSeconds", "uptime_seconds", "uptimeSec", "uptime_sec"),
    )
    if uptime_seconds is not None:
        return round(uptime_seconds / 3600, 1)

    uptime_ms = _first_number(system, ("uptimeMs", "uptime_ms", "uptimeMillis"))
    if uptime_ms is not None:
        return round(uptime_ms / 3_600_000, 1)

    return _uptime_hours_from_startup(system)


def _uptime_hours_from_startup(system: dict[str, Any]) -> float | None:
    """Return uptime derived from a Drive device-info startup timestamp.

    The Drive ``device-info`` payload has no numeric uptime; it reports an ISO
    ``startupTime`` instead, which is the only uptime source under API-key auth.
    """
    for key in ("startupTime", "startup_time", "startedAt", "bootTime", "boot_time"):
        raw = system.get(key)
        if not isinstance(raw, str) or not raw.strip():
            continue
        text = raw.strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            started = datetime.fromisoformat(text)
        except ValueError:
            continue
        if started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
        seconds = (datetime.now(UTC) - started).total_seconds()
        if seconds < 0:
            return None
        return round(seconds / 3600, 1)
    return None


def _cpu_temperature(data: dict[str, Any]) -> float | None:
    """Return UniFi OS CPU temperature in Celsius."""
    system = _system_payload(data)
    direct = _first_number(
        system,
        ("cpuTemperature", "cpu_temperature", "cpuTemp", "cpu_temp"),
    )
    if direct is not None:
        return round(direct, 1)

    cpu = system.get("cpu")
    if isinstance(cpu, dict):
        value = _first_number(
            cpu,
            ("temperature", "temperatureC", "temperature_c", "temp", "tempC"),
        )
        if value is not None:
            return round(value, 1)

    for nested in _dict_values(system, ("thermal", "temperatures", "sensors")):
        value = _first_number(
            nested,
            ("cpu", "cpuTemperature", "cpu_temperature", "temperature", "temp"),
        )
        if value is not None:
            return round(value, 1)
    return None


def _cpu_percent(data: dict[str, Any]) -> float | None:
    """Return CPU utilization as a percentage.

    The Drive ``device-info`` payload reports ``cpu.currentload`` as a 0-1
    utilization fraction, which is the only CPU-load source (it is reachable
    under API-key auth, unlike the UniFi OS ``/api/system`` payload). Values in
    ``(0, 1]`` are treated as fractions and scaled to a percentage; a value
    above ``1`` is assumed to already be a percentage.
    """
    system = _system_payload(data)
    cpu = system.get("cpu")
    if isinstance(cpu, dict):
        load = _first_number(
            cpu,
            ("currentload", "currentLoad", "current_load", "load", "usage", "percent"),
        )
        if load is not None:
            return round(load * 100 if load <= 1 else load, 1)

    load = _first_number(
        system,
        ("cpuLoad", "cpu_load", "cpuUsage", "cpu_usage", "cpuPercent", "cpu_percent"),
    )
    if load is not None:
        return round(load * 100 if load <= 1 else load, 1)
    return None


def _memory_percent(data: dict[str, Any]) -> float | None:
    """Return used memory as a percentage of total memory.

    The Drive ``device-info`` payload exposes ``memory`` as
    ``{total, free, available}``. Used memory is derived from ``available``
    (the Linux memory-pressure basis) when present, otherwise from ``free`` or
    an explicit ``used`` value.
    """
    system = _system_payload(data)
    memory = system.get("memory")
    if not isinstance(memory, dict):
        return None

    total = _first_number(memory, ("total", "totalBytes", "total_bytes", "totalKb"))
    if not total or total <= 0:
        return None

    available = _first_number(
        memory, ("available", "availableBytes", "available_bytes")
    )
    if available is not None:
        used = total - available
    else:
        free = _first_number(memory, ("free", "freeBytes", "free_bytes"))
        if free is not None:
            used = total - free
        else:
            used = _first_number(memory, ("used", "usedBytes", "used_bytes"))
            if used is None:
                return None

    return round(max(0.0, min(100.0, used / total * 100)), 1)


def _system_status(data: dict[str, Any]) -> str | None:
    """Return a user-facing UniFi OS system status."""
    system = _system_payload(data)
    top_level_status = _normalized_token(_scalar_text(system.get("status")) or "")
    if top_level_status == "offline":
        return "offline"

    status_from_devices = _system_status_from_device_payload(system)
    if status_from_devices is not None:
        return status_from_devices

    state_status, state_fallback = _system_status_from_state_fields(system)
    if state_status is not None:
        return state_status

    if top_level_status in {"updateavailable", "online", "setup"}:
        return (
            "update_available"
            if top_level_status == "updateavailable"
            else top_level_status
        )

    if state_fallback:
        return state_fallback

    return None


def _system_status_from_device_payload(system: dict[str, Any]) -> str | None:
    """Resolve status from nested device payloads where available."""
    devices = system.get("devices")
    if not isinstance(devices, dict):
        return None

    unifi_os = devices.get("unifiOS")
    if not isinstance(unifi_os, list):
        return None

    for device in unifi_os:
        if not isinstance(device, dict):
            continue
        device_status = _normalized_token(str(device.get("status", "")))
        if device_status in {"online", "offline"}:
            return device_status
    return None


def _system_status_from_state_fields(
    system: dict[str, Any],
) -> tuple[str | None, str | None]:
    """Resolve status from top-level state keys."""
    state_status: str | None = None
    state_fallback: str | None = None
    for state_key in ("deviceState", "state"):
        state_text = _scalar_text(system.get(state_key))
        if state_text is None:
            continue
        state = _normalized_token(state_text)
        if state == "updateavailable":
            state_status = "update_available"
            break
        if state in {"setup", "offline", "online"}:
            state_status = state
            break
        if state:
            state_fallback = state
    return state_status, state_fallback


def _ip_from_mapping(value: dict[str, Any]) -> str | None:
    """Return the first valid IP address from a network mapping."""
    for key in NETWORK_ADDRESS_KEYS:
        if ip := _ip_text(value.get(key)):
            return ip
    for key in NETWORK_CONTAINER_KEYS:
        if ip := _ip_from_value(value.get(key)):
            return ip
    return None


def _ip_from_value(value: Any) -> str | None:
    """Return the first valid IP address from nested network values."""
    if ip := _ip_text(value):
        return ip
    if isinstance(value, dict):
        return _ip_from_mapping(value)
    if isinstance(value, list):
        for item in value:
            if ip := _ip_from_value(item):
                return ip
    return None


def _ip_text(value: Any) -> str | None:
    """Return a normalized IPv4 or IPv6 address string."""
    text = _text(value)
    if not text:
        return None

    candidate = text.split("/", 1)[0].strip().strip("[]")
    try:
        parsed = ip_address(candidate)
    except ValueError:
        return None
    if parsed.is_loopback or parsed.is_unspecified or parsed.is_multicast:
        return None
    return str(parsed)


def _scalar_text(value: Any) -> str | None:
    """Return text only for scalar payload values."""
    if isinstance(value, (dict, list, tuple, set)):
        return None
    return _text(value)
