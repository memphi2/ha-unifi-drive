"""Binary sensors for the UniFi Drive integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .binary_sensor_descriptions import (
    AGGREGATE_BINARY_SENSOR_TYPES,
    POOL_BINARY_SENSOR_TYPES,
    AggregateBinarySensorDescription,
    PoolBinarySensorDescription,
)
from .coordinator import UnifiUnasCoordinator
from .entity_base import UnifiUnasDeviceInfoMixin
from .runtime import UnifiDriveConfigEntry, coordinator_from_entry
from .storage_view import storage_view
from .storage_helpers import (
    _aggregate_status,
    _at_risk_disk_count,
    _pool_in_maintenance,
    _pool_key,
    _pool_name,
    _pool_rebuild_progress,
    _pool_sync_progress,
    _pools,
    _raw_pool_status,
)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UnifiDriveConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up UniFi Drive binary sensors from a config entry."""
    coordinator = coordinator_from_entry(entry)

    async_add_entities(
        [
            UnifiUnasAggregateBinarySensor(coordinator, entry, description)
            for description in AGGREGATE_BINARY_SENSOR_TYPES
        ]
    )

    known_pool_keys: set[str] = set()

    def _add_missing_pool_binary_sensors() -> None:
        """Create pool binary sensors when pool data becomes available."""
        new_entities: list[BinarySensorEntity] = []
        for index, pool in enumerate(storage_view(coordinator).pools):
            pool_key = _pool_key(pool, index)
            if pool_key in known_pool_keys:
                continue
            known_pool_keys.add(pool_key)
            pool_name = _pool_name(pool, index)
            new_entities.extend(
                UnifiUnasPoolBinarySensor(
                    coordinator,
                    entry,
                    description,
                    pool_key,
                    pool_name,
                )
                for description in POOL_BINARY_SENSOR_TYPES
            )

        if new_entities:
            async_add_entities(new_entities)

    _add_missing_pool_binary_sensors()
    entry.async_on_unload(
        coordinator.async_add_listener(_add_missing_pool_binary_sensors)
    )


class UnifiUnasBaseBinarySensor(
    UnifiUnasDeviceInfoMixin,
    CoordinatorEntity[UnifiUnasCoordinator],
    BinarySensorEntity,
):  # type: ignore[misc]
    """Common base for UniFi Drive binary sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: UnifiUnasCoordinator,
        entry: UnifiDriveConfigEntry,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._set_device_context(entry)


class UnifiUnasAggregateBinarySensor(UnifiUnasBaseBinarySensor):
    """Aggregate UNAS binary sensor."""

    entity_description: AggregateBinarySensorDescription

    def __init__(
        self,
        coordinator: UnifiUnasCoordinator,
        entry: UnifiDriveConfigEntry,
        description: AggregateBinarySensorDescription,
    ) -> None:
        """Initialize the aggregate binary sensor."""
        super().__init__(coordinator, entry)
        self.entity_description = description
        self._attr_unique_id = f"{self._device_identifier}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        """Return the current binary state."""
        if self.entity_description.key == "device_online":
            return self.coordinator.is_device_online
        if not self.coordinator.data:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def available(self) -> bool:
        """Return availability."""
        if self.entity_description.key == "device_online":
            return True
        return bool(super().available)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return aggregate diagnostic attributes."""
        if not self.coordinator.data:
            return None

        if self.entity_description.key == "storage_problem":
            return {
                "overall_status": _aggregate_status(self.coordinator.data),
                "at_risk_disk_count": _at_risk_disk_count(self.coordinator.data),
            }

        if self.entity_description.key == "maintenance_active":
            return {
                "pool_count": len(_pools(self.coordinator.data)),
                "maintenance_pool_count": sum(
                    1
                    for pool in _pools(self.coordinator.data)
                    if _pool_in_maintenance(pool)
                ),
            }

        return None


class UnifiUnasPoolBinarySensor(UnifiUnasBaseBinarySensor):
    """Per-pool UNAS binary sensor."""

    _unrecorded_attributes = frozenset({"rebuild_progress", "sync_progress"})
    entity_description: PoolBinarySensorDescription

    def __init__(
        self,
        coordinator: UnifiUnasCoordinator,
        entry: UnifiDriveConfigEntry,
        description: PoolBinarySensorDescription,
        pool_key: str,
        pool_name: str,
    ) -> None:
        """Initialize the pool binary sensor."""
        super().__init__(coordinator, entry)
        self.entity_description = description
        self._pool_key = pool_key
        self._pool_name = pool_name
        self._attr_translation_placeholders = {"pool_name": pool_name}
        self._attr_unique_id = (
            f"{self._device_identifier}_{self._pool_key}_{description.key}"
        )

    @property
    def available(self) -> bool:
        """Return if the pool still exists."""
        return bool(super().available) and self._pool() is not None

    @property
    def is_on(self) -> bool | None:
        """Return the current binary state."""
        pool = self._pool()
        if pool is None:
            return None
        return self.entity_description.value_fn(pool)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return pool binary diagnostics."""
        pool = self._pool()
        if pool is None:
            return None

        return {
            "pool_key": self._pool_key,
            "pool_name": self._pool_name,
            "raw_status": _raw_pool_status(pool),
            "rebuild_progress": _pool_rebuild_progress(pool),
            "sync_progress": _pool_sync_progress(pool),
        }

    def _pool(self) -> dict[str, Any] | None:
        """Return the currently matching pool by key."""
        return storage_view(self.coordinator).pool(self._pool_key)
