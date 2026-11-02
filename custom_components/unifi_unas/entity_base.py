"""Shared entity helpers for UniFi Drive platforms."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo

from .coordinator import UnifiUnasCoordinator
from .device import build_device_info
from .runtime import UnifiDriveConfigEntry


class UnifiUnasDeviceInfoMixin:
    """Mixin for entities that expose the dynamic UniFi Drive device."""

    coordinator: UnifiUnasCoordinator
    _entry: UnifiDriveConfigEntry
    _device_identifier: str

    def _set_device_context(self, entry: UnifiDriveConfigEntry) -> None:
        """Store config-entry context for device info and unique IDs."""
        self._entry = entry
        self._device_identifier = entry.unique_id or entry.entry_id

    @property
    def device_info(self) -> DeviceInfo:
        """Build dynamic device info from the latest coordinator payload."""
        return build_device_info(
            self.coordinator,
            self._entry,
            self._device_identifier,
        )
