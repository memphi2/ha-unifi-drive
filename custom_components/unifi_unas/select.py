"""Select entities for the UniFi Drive integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import CannotConnect, InvalidAuth, UnexpectedResponse, UnsupportedFeature
from .const import (
    CONF_FAN_CONTROL_ENABLED,
    DEFAULT_FAN_CONTROL_ENABLED,
    FAN_MODE_OPTIONS,
    SNAPSHOT_SCHEDULE_OPTIONS,
    SNAPSHOT_WEEKDAY_OPTIONS,
)
from .coordinator import UnifiUnasCoordinator
from .device import build_device_info
from .entry_options import entry_bool
from .exceptions import unifi_unas_error, unifi_unas_validation_error
from .runtime import UnifiDriveConfigEntry, coordinator_from_entry
from .security import safe_error_text
from .snapshot_entities import (
    UnifiUnasSnapshotTargetEntity,
    async_setup_snapshot_target_entities,
)
from .snapshot_schedule import _snapshot_first_schedule_day
from homeassistant.helpers.device_registry import DeviceInfo

WEEKDAY_OPTION_VALUES = {
    option: index for index, option in enumerate(SNAPSHOT_WEEKDAY_OPTIONS)
}

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UnifiDriveConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up UniFi Drive select entities from a config entry."""
    coordinator = coordinator_from_entry(entry)
    entities: list[SelectEntity] = []

    if entry_bool(entry, CONF_FAN_CONTROL_ENABLED, DEFAULT_FAN_CONTROL_ENABLED):
        entities.append(UnifiUnasFanModeSelect(coordinator, entry))

    if entities:
        async_add_entities(entities)

    async_setup_snapshot_target_entities(
        entry,
        coordinator,
        async_add_entities,
        lambda target: (
            UnifiUnasSnapshotScheduleSelect(coordinator, entry, target),
            UnifiUnasSnapshotWeekdaySelect(coordinator, entry, target),
        ),
    )


class UnifiUnasFanModeSelect(
    CoordinatorEntity[UnifiUnasCoordinator], SelectEntity, RestoreEntity  # type: ignore[misc]
):
    """Select for the native UniFi Drive fan mode."""

    _attr_has_entity_name = True
    _attr_translation_key = "fan_mode"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = list(FAN_MODE_OPTIONS)

    def __init__(
        self,
        coordinator: UnifiUnasCoordinator,
        entry: UnifiDriveConfigEntry,
    ) -> None:
        """Initialize the fan mode select."""
        super().__init__(coordinator)
        self._entry = entry
        self._device_identifier = entry.unique_id or entry.entry_id
        self._current_option: str | None = (
            coordinator.fan_mode or coordinator.client.native_fan_mode
        )
        self._attr_unique_id = f"{self._device_identifier}_fan_mode"

    @property
    def device_info(self) -> DeviceInfo:
        """Build dynamic device info from the latest coordinator payload."""
        return build_device_info(
            self.coordinator,
            self._entry,
            self._device_identifier,
        )

    async def async_added_to_hass(self) -> None:
        """Restore previous state."""
        await super().async_added_to_hass()

        if self._current_option is None:
            last_state = await self.async_get_last_state()
            if last_state and last_state.state in self.options:
                self._current_option = last_state.state

    @property
    def current_option(self) -> str | None:
        """Return the current selected fan mode."""
        fan_mode = self.coordinator.fan_mode
        if isinstance(fan_mode, str) and fan_mode in self.options:
            return fan_mode
        native_mode = self.coordinator.client.native_fan_mode
        if isinstance(native_mode, str) and native_mode in self.options:
            return native_mode
        if self._current_option in self.options:
            return self._current_option
        return "Balance"

    @property
    def available(self) -> bool:
        """Disable writes when the UniFi device is currently unreachable."""
        return bool(super().available) and self.coordinator.is_device_online

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return endpoint diagnostics for UI inspection."""
        return {
            "mode_type": "native_unifi_unas_fan_mode",
            "supported_modes": list(FAN_MODE_OPTIONS),
            "api_note": (
                "UniFi Drive fan-mode endpoint is not publicly documented; set "
                "operation uses the verified local Drive fan-control endpoint."
            ),
        }

    async def async_select_option(self, option: str) -> None:
        """Set the native UniFi Drive fan mode."""
        if option not in self.options:
            raise unifi_unas_error(
                f"Unsupported UniFi Drive fan mode {option!r}. Valid options: {self.options}",
                "fan_mode_unsupported_option",
                option=str(option),
                options=", ".join(self.options),
            )
        if not self.coordinator.is_device_online:
            raise unifi_unas_validation_error(
                "Cannot set fan mode while the UniFi Drive device is offline",
                "device_offline",
                action="set fan mode",
            )

        try:
            mode = await self.coordinator.client.async_set_fan_mode(option)
        except InvalidAuth as err:
            raise unifi_unas_error(
                "The configured UniFi account/API key cannot change the native UniFi Drive "
                "fan mode. Use credentials or an API key with Drive/system settings rights.",
                "fan_mode_permission",
            ) from err
        except UnsupportedFeature as err:
            error = safe_error_text(err)
            raise unifi_unas_error(
                "Could not change native UniFi Drive fan mode with the configured local "
                f"Drive endpoint: {error}",
                "fan_mode_unsupported",
                error=error,
            ) from err
        except (CannotConnect, UnexpectedResponse) as err:
            error = safe_error_text(err)
            raise unifi_unas_error(
                f"Could not change native UniFi Drive fan mode: {error}",
                "fan_mode_failed",
                error=error,
            ) from err

        self.coordinator.fan_mode = mode if mode in self.options else option
        self._current_option = self.coordinator.fan_mode
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()


class UnifiUnasSnapshotScheduleSelect(
    UnifiUnasSnapshotTargetEntity, SelectEntity  # type: ignore[misc]
):
    """Select that configures snapshot schedule frequency."""

    _attr_options = list(SNAPSHOT_SCHEDULE_OPTIONS)

    def __init__(
        self,
        coordinator: UnifiUnasCoordinator,
        entry: UnifiDriveConfigEntry,
        target: Mapping[str, Any],
    ) -> None:
        """Initialize the snapshot schedule select."""
        super().__init__(
            coordinator,
            entry,
            target,
            entity_key="schedule",
        )

    @property
    def current_option(self) -> str | None:
        """Return the current schedule frequency."""
        target = self._current_target()
        if target is None:
            return None
        option = target.get("schedule_frequency")
        if option in self.options:
            return str(option)
        return "Never"

    async def async_select_option(self, option: str) -> None:
        """Set snapshot schedule frequency."""
        if option not in self.options:
            raise unifi_unas_error(
                f"Unsupported UniFi Drive snapshot schedule {option!r}. "
                f"Valid options: {self.options}",
                "snapshot_schedule_option",
                options=", ".join(self.options),
            )
        await self._async_update_snapshot_target(schedule_frequency=option)


class UnifiUnasSnapshotWeekdaySelect(
    UnifiUnasSnapshotTargetEntity, SelectEntity  # type: ignore[misc]
):
    """Select that configures the primary weekly snapshot day."""

    _attr_options = list(SNAPSHOT_WEEKDAY_OPTIONS)

    def __init__(
        self,
        coordinator: UnifiUnasCoordinator,
        entry: UnifiDriveConfigEntry,
        target: Mapping[str, Any],
    ) -> None:
        """Initialize the snapshot weekday select."""
        super().__init__(
            coordinator,
            entry,
            target,
            entity_key="weekday",
        )

    @property
    def current_option(self) -> str | None:
        """Return the first configured weekly snapshot day."""
        target = self._current_target()
        if target is None:
            return None
        day = _snapshot_first_schedule_day(
            target.get("schedule_weekdays"),
            minimum=0,
            maximum=6,
        )
        if day is None:
            return None
        if not isinstance(day, int):
            return None
        return SNAPSHOT_WEEKDAY_OPTIONS[day]

    async def async_select_option(self, option: str) -> None:
        """Set a single weekly snapshot day and switch the schedule to weekly."""
        if option not in WEEKDAY_OPTION_VALUES:
            raise unifi_unas_error(
                f"Unsupported UniFi Drive snapshot weekday {option!r}. "
                f"Valid options: {self.options}",
                "snapshot_weekday",
            )
        await self._async_update_snapshot_target(
            schedule_frequency="Weekly",
            schedule_weekdays=str(WEEKDAY_OPTION_VALUES[option]),
        )
