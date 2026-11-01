"""Time entities for UniFi Drive snapshot settings."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import time
from typing import Any

from homeassistant.components.time import TimeEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import UnifiUnasCoordinator
from .runtime import UnifiDriveConfigEntry, coordinator_from_entry
from .snapshot_entities import (
    UnifiUnasSnapshotTargetEntity,
    async_setup_snapshot_target_entities,
)
from .snapshot_schedule import _schedule_time_parts

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UnifiDriveConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up UniFi Drive time entities from a config entry."""
    coordinator = coordinator_from_entry(entry)
    async_setup_snapshot_target_entities(
        entry,
        coordinator,
        async_add_entities,
        lambda target: (UnifiUnasSnapshotScheduleTime(coordinator, entry, target),),
    )


class UnifiUnasSnapshotScheduleTime(
    UnifiUnasSnapshotTargetEntity, TimeEntity
):  # type: ignore[misc]
    """Time entity that configures snapshot schedule time."""

    def __init__(
        self,
        coordinator: UnifiUnasCoordinator,
        entry: UnifiDriveConfigEntry,
        target: Mapping[str, Any],
    ) -> None:
        """Initialize the snapshot schedule time entity."""
        super().__init__(
            coordinator,
            entry,
            target,
            entity_key="schedule_time",
        )

    @property
    def native_value(self) -> time | None:
        """Return the current schedule time."""
        target = self._current_target()
        value = None if target is None else target.get("schedule_time")
        if not value:
            return None
        parsed_time = _parse_schedule_time(value)
        if parsed_time is None:
            return None
        return parsed_time

    async def async_set_value(self, value: time) -> None:
        """Set the snapshot schedule time."""
        await self._async_update_snapshot_target(
            schedule_time=f"{value.hour:02d}:{value.minute:02d}",
        )


def _parse_schedule_time(value: Any) -> time | None:
    """Parse a schedule time value defensively."""
    if isinstance(value, time):
        return value

    if value is None:
        return None

    try:
        hour, minute = _schedule_time_parts(value)
    except ValueError:
        return None

    return time(hour=hour, minute=minute)
