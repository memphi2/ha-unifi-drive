"""Runtime-data typing and helpers for the UniFi Drive integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeAlias, cast

from homeassistant.config_entries import ConfigEntry

if TYPE_CHECKING:
    from .coordinator import UnifiUnasCoordinator

    UnifiDriveConfigEntry: TypeAlias = ConfigEntry[UnifiUnasCoordinator]
else:
    # Keep runtime imports compatible with lightweight tests that stub
    # ConfigEntry with a non-subscriptable object.
    UnifiDriveConfigEntry = ConfigEntry


def coordinator_from_entry(entry: UnifiDriveConfigEntry) -> UnifiUnasCoordinator:
    """Return the loaded coordinator stored on ConfigEntry.runtime_data."""
    coordinator: UnifiUnasCoordinator = entry.runtime_data
    return coordinator


def coordinator_from_entry_or_none(
    entry: UnifiDriveConfigEntry | None,
) -> UnifiUnasCoordinator | None:
    """Return the loaded coordinator if runtime data is available."""
    if entry is None:
        return None

    coordinator = getattr(entry, "runtime_data", None)
    if _looks_like_unifi_unas_coordinator(coordinator):
        return cast("UnifiUnasCoordinator", coordinator)
    return None


def _looks_like_unifi_unas_coordinator(value: object) -> bool:
    """Return whether runtime data has the coordinator surface used by support paths."""
    return all(
        hasattr(value, attr)
        for attr in (
            "client",
            "data",
            "is_device_online",
            "last_update_success",
        )
    )
