"""Number entities for UniFi Drive snapshot settings."""

from __future__ import annotations

from collections.abc import Mapping
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from typing import Any

from .const import MAX_SNAPSHOT_LIMIT, MIN_SNAPSHOT_LIMIT
from .coordinator import UnifiUnasCoordinator
from .exceptions import unifi_unas_validation_error
from .runtime import UnifiDriveConfigEntry, coordinator_from_entry
from .snapshot_entities import (
    UnifiUnasSnapshotTargetEntity,
    async_setup_snapshot_target_entities,
)
from .snapshot_schedule import _snapshot_first_schedule_day

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UnifiDriveConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up UniFi Drive number entities from a config entry."""
    coordinator = coordinator_from_entry(entry)
    async_setup_snapshot_target_entities(
        entry,
        coordinator,
        async_add_entities,
        lambda target: (
            UnifiUnasSnapshotLimitNumber(coordinator, entry, target),
            UnifiUnasSnapshotMonthlyDayNumber(coordinator, entry, target),
        ),
    )


class UnifiUnasSnapshotLimitNumber(
    UnifiUnasSnapshotTargetEntity, NumberEntity  # type: ignore[misc]
):
    """Number that configures snapshot retention limit for a target."""

    _attr_native_min_value = MIN_SNAPSHOT_LIMIT
    _attr_native_max_value = MAX_SNAPSHOT_LIMIT
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        coordinator: UnifiUnasCoordinator,
        entry: UnifiDriveConfigEntry,
        target: Mapping[str, Any],
    ) -> None:
        """Initialize the snapshot limit number."""
        super().__init__(
            coordinator,
            entry,
            target,
            entity_key="limit",
        )

    @property
    def native_value(self) -> int | None:
        """Return the current snapshot limit."""
        target = self._current_target()
        if target is None:
            return None
        value = target.get("max_count")
        if value in (None, 0):
            return None
        return int(value) if isinstance(value, (int, float, str)) else None

    async def async_set_native_value(self, value: float) -> None:
        """Set the snapshot limit."""
        limit = int(value)
        if limit < MIN_SNAPSHOT_LIMIT or limit > MAX_SNAPSHOT_LIMIT:
            raise unifi_unas_validation_error(
                f"Snapshot limit must be between {MIN_SNAPSHOT_LIMIT} and "
                f"{MAX_SNAPSHOT_LIMIT}",
                "snapshot_limit_range",
                min=str(MIN_SNAPSHOT_LIMIT),
                max=str(MAX_SNAPSHOT_LIMIT),
            )
        await self._async_update_snapshot_target(max_count=limit)


class UnifiUnasSnapshotMonthlyDayNumber(
    UnifiUnasSnapshotTargetEntity, NumberEntity  # type: ignore[misc]
):
    """Number that configures the primary monthly snapshot day."""

    _attr_native_min_value = 1
    _attr_native_max_value = 31
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        coordinator: UnifiUnasCoordinator,
        entry: UnifiDriveConfigEntry,
        target: Mapping[str, Any],
    ) -> None:
        """Initialize the snapshot monthly day number."""
        super().__init__(
            coordinator,
            entry,
            target,
            entity_key="month_day",
        )

    @property
    def native_value(self) -> int | None:
        """Return the first configured monthly snapshot day."""
        target = self._current_target()
        if target is None:
            return None
        return _snapshot_first_schedule_day(
            target.get("schedule_monthdays"),
            minimum=1,
            maximum=31,
        )

    async def async_set_native_value(self, value: float) -> None:
        """Set a single monthly snapshot day and switch the schedule to monthly."""
        day = int(value)
        if day < 1 or day > 31:
            raise unifi_unas_validation_error(
                "Snapshot month day must be between 1 and 31",
                "snapshot_monthday_range",
            )
        await self._async_update_snapshot_target(
            schedule_frequency="Monthly",
            schedule_monthdays=str(day),
        )
