"""Switch entities for UniFi Drive snapshot settings."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import UnifiUnasCoordinator
from .runtime import UnifiDriveConfigEntry, coordinator_from_entry
from .snapshot_entities import (
    UnifiUnasSnapshotTargetEntity,
    async_setup_snapshot_target_entities,
)

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UnifiDriveConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up UniFi Drive switch entities from a config entry."""
    coordinator = coordinator_from_entry(entry)
    async_setup_snapshot_target_entities(
        entry,
        coordinator,
        async_add_entities,
        lambda target: (UnifiUnasSnapshotEnabledSwitch(coordinator, entry, target),),
    )


class UnifiUnasSnapshotEnabledSwitch(
    UnifiUnasSnapshotTargetEntity, SwitchEntity  # type: ignore[misc]
):
    """Switch that enables snapshot protection for a target."""

    def __init__(
        self,
        coordinator: UnifiUnasCoordinator,
        entry: UnifiDriveConfigEntry,
        target: Mapping[str, Any],
    ) -> None:
        """Initialize the snapshot enabled switch."""
        super().__init__(
            coordinator,
            entry,
            target,
            entity_key="enabled",
        )

    @property
    def is_on(self) -> bool | None:
        """Return whether snapshots are enabled for this target."""
        target = self._current_target()
        return None if target is None else bool(target.get("enabled"))

    async def async_turn_on(self, **_kwargs: Any) -> None:
        """Enable snapshots for this target."""
        await self._async_update_snapshot_target(enabled=True)

    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Disable snapshots for this target."""
        await self._async_update_snapshot_target(enabled=False)
