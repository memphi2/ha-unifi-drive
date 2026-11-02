"""Static contract probes using imported HA types, never run against a live HA."""

from typing import assert_type

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from custom_components.unifi_unas.coordinator import UnifiUnasCoordinator
from custom_components.unifi_unas.device import build_device_info, device_registry_metadata
from custom_components.unifi_unas.entry_options import ConfigEntryLike
from custom_components.unifi_unas.runtime import coordinator_from_entry


def check_runtime_and_device_contract(
    hass: HomeAssistant,
    entry: ConfigEntry[UnifiUnasCoordinator],
) -> None:
    """Type-check integration boundaries without hiding imported types as Any."""
    coordinator = coordinator_from_entry(entry)
    assert_type(coordinator, UnifiUnasCoordinator)
    assert_type(build_device_info(coordinator, entry, "synthetic-device"), DeviceInfo)
    info = build_device_info(coordinator, entry, "synthetic-device")
    assert_type(device_registry_metadata(info), dict[str, str])
    compatible_entry: ConfigEntryLike = entry
    assert_type(compatible_entry, ConfigEntryLike)
    options: dict[str, object] = {"scan_interval": 60}
    hass.config_entries.async_update_entry(entry, options=options)
