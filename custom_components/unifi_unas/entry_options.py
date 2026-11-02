"""Helpers for config entry data/options handling."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


class ConfigEntryLike(Protocol):
    """Config-entry shape needed by data/options helpers."""

    @property
    def data(self) -> Mapping[str, Any]: ...

    @property
    def options(self) -> Mapping[str, Any]: ...

FEATURE_OPTION_KEYS: tuple[str, ...] = (
    "scan_interval",
    "fan_control_enabled",
    "snapshot_buttons_enabled",
    "discovery_debug",
    "wol_enabled",
    "wol_mac_address",
    "wol_broadcast_address",
    "wol_port",
)
FEATURE_OPTION_KEY_SET = frozenset(FEATURE_OPTION_KEYS)
ENTRY_DATA_KEYS: tuple[str, ...] = (
    "host",
    "port",
    "ssl",
    "verify_ssl",
    "username",
    "password",
    "api_key",
    "discovery_mac_address",
    "discovery_host_aliases",
    "discovery_last_seen",
    "discovery_identity_source",
    "discovery_confidence",
    "discovery_identity_conflicts",
)


def entry_value(entry: ConfigEntryLike, key: str, default: Any = None) -> Any:
    """Read a config value from options first, then data."""
    options = getattr(entry, "options", {}) or {}
    if key in options:
        return options[key]
    data = getattr(entry, "data", {}) or {}
    return data.get(key, default)


def entry_bool(entry: ConfigEntryLike, key: str, default: bool = False) -> bool:
    """Read a boolean config value from options first, then data."""
    return bool(entry_value(entry, key, default))


def entry_int(entry: ConfigEntryLike, key: str, default: int) -> int:
    """Read an integer config value from options first, then data."""
    try:
        return int(entry_value(entry, key, default))
    except (TypeError, ValueError):
        return default


def entry_str(entry: ConfigEntryLike, key: str, default: str = "") -> str:
    """Read a string config value from options first, then data."""
    return str(entry_value(entry, key, default))


def merged_entry_data_options(entry: ConfigEntryLike) -> dict[str, Any]:
    """Return entry data with options layered on top for form defaults."""
    merged = dict(getattr(entry, "data", {}) or {})
    merged.update(getattr(entry, "options", {}) or {})
    return merged


def feature_options_from_data(data: dict[str, Any]) -> dict[str, Any]:
    """Return only non-identity feature settings from normalized flow data."""
    return {key: data[key] for key in FEATURE_OPTION_KEYS if key in data}


def data_without_feature_options(data: dict[str, Any]) -> dict[str, Any]:
    """Return entry data with runtime feature settings removed."""
    return {
        key: value for key, value in data.items() if key not in FEATURE_OPTION_KEY_SET
    }


def entry_data_from_data(data: dict[str, Any]) -> dict[str, Any]:
    """Return only connection/auth settings for entry data."""
    return {key: data[key] for key in ENTRY_DATA_KEYS if key in data}


def merged_entry_data_with_connection_updates(
    entry: ConfigEntryLike,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Return entry data with normalized connection/auth updates applied."""
    entry_data = data_without_feature_options(dict(getattr(entry, "data", {}) or {}))
    entry_data.update(entry_data_from_data(data))
    return entry_data


def feature_options_from_entry(entry: ConfigEntryLike) -> dict[str, Any]:
    """Return current entry options without importing feature keys from data."""
    return dict(getattr(entry, "options", {}) or {})


def merged_feature_options(
    entry: ConfigEntryLike,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Return entry options with normalized feature settings overlaid."""
    options = dict(getattr(entry, "options", {}) or {})
    options.update(feature_options_from_data(data))
    return options
