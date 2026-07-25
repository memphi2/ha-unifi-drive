"""Sensor entities for the UniFi Drive integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import UnifiUnasCoordinator
from .entity_base import UnifiUnasDeviceInfoMixin
from .runtime import UnifiDriveConfigEntry, coordinator_from_entry
from .sensor_descriptions import (
    AGGREGATE_SENSOR_TYPES,
    DRIVE_SENSOR_TYPES,
    POOL_SENSOR_TYPES,
    AggregateSensorDescription,
    DriveSensorDescription,
    PoolSensorDescription,
)
from .snapshot_entities import (
    UnifiUnasSnapshotTargetEntity,
    async_setup_snapshot_target_entities,
)
from .snapshot_inventory import (
    SNAPSHOT_INVENTORY_PREVIEW_LIMIT,
    SNAPSHOT_INVENTORY_STATUS_FALLBACK,
    SNAPSHOT_INVENTORY_STATUS_OK,
)
from .storage_helpers import (
    _drive_attributes,
    _drive_key,
    _drive_name,
    _legacy_drive_index,
    _normalized_token,
    _pool_drives,
    _pool_from_key,
    _pool_key,
    _pool_name,
    _pools,
    _raw_drive_health,
    _raw_pool_status,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UnifiDriveConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up UniFi Drive sensors from a config entry."""
    coordinator = coordinator_from_entry(entry)

    async_add_entities(
        [
            UnifiUnasAggregateSensor(coordinator, entry, description)
            for description in AGGREGATE_SENSOR_TYPES
        ]
    )

    known_pool_keys: set[str] = set()
    known_drive_keys: set[str] = set()

    def _add_missing_pool_sensors() -> None:
        """Create pool sensors when pool data becomes available."""
        new_entities: list[SensorEntity] = []
        for index, pool in enumerate(_pools(coordinator.data)):
            pool_key = _pool_key(pool, index)
            if pool_key in known_pool_keys:
                continue
            known_pool_keys.add(pool_key)
            pool_name = _pool_name(pool, index)
            new_entities.extend(
                UnifiUnasPoolSensor(
                    coordinator, entry, description, pool_key, pool_name
                )
                for description in POOL_SENSOR_TYPES
            )
            for drive_index, drive in enumerate(_pool_drives(pool)):
                drive_key = _drive_key(drive, drive_index)
                full_drive_key = f"{pool_key}_{drive_key}"
                if full_drive_key in known_drive_keys:
                    continue
                known_drive_keys.add(full_drive_key)
                drive_name = _drive_name(drive, drive_index)
                new_entities.extend(
                    UnifiUnasDriveSensor(
                        coordinator,
                        entry,
                        description,
                        pool_key,
                        full_drive_key,
                        pool_name,
                        drive_name,
                    )
                    for description in DRIVE_SENSOR_TYPES
                )

        if new_entities:
            async_add_entities(new_entities)

    _add_missing_pool_sensors()
    entry.async_on_unload(coordinator.async_add_listener(_add_missing_pool_sensors))
    async_setup_snapshot_target_entities(
        entry,
        coordinator,
        async_add_entities,
        lambda target: (UnifiUnasSnapshotInventorySensor(coordinator, entry, target),),
    )


class UnifiUnasBaseSensor(
    UnifiUnasDeviceInfoMixin,
    CoordinatorEntity[UnifiUnasCoordinator],
    SensorEntity,
):  # type: ignore[misc]
    """Common base for UniFi Drive sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: UnifiUnasCoordinator,
        entry: UnifiDriveConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._set_device_context(entry)


class UnifiUnasAggregateSensor(UnifiUnasBaseSensor):
    """Aggregate UNAS storage sensor."""

    entity_description: AggregateSensorDescription

    def __init__(
        self,
        coordinator: UnifiUnasCoordinator,
        entry: UnifiDriveConfigEntry,
        description: AggregateSensorDescription,
    ) -> None:
        """Initialize the aggregate sensor."""
        super().__init__(coordinator, entry)
        self.entity_description = description
        self._attr_unique_id = f"{self._device_identifier}_{description.key}"

    @property
    def native_value(self) -> StateType:
        """Return the current state."""
        if (
            self.entity_description.key == "system_status"
            and not self.coordinator.last_update_success
        ):
            return "offline"
        if not self.coordinator.data:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def available(self) -> bool:
        """Return entity availability."""
        if self.entity_description.key == "system_status":
            return True
        return bool(super().available)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return useful storage attributes."""
        if self.entity_description.key != "overall_status" or not self.coordinator.data:
            return None
        pools = _pools(self.coordinator.data)
        return {
            "pool_count": len(pools),
            "pool_names": [_pool_name(pool, index) for index, pool in enumerate(pools)],
            "raw_statuses": [_raw_pool_status(pool) for pool in pools],
        }


class UnifiUnasPoolSensor(UnifiUnasBaseSensor):
    """Per-pool UNAS storage sensor."""

    entity_description: PoolSensorDescription

    def __init__(
        self,
        coordinator: UnifiUnasCoordinator,
        entry: UnifiDriveConfigEntry,
        description: PoolSensorDescription,
        pool_key: str,
        pool_name: str,
    ) -> None:
        """Initialize the pool sensor."""
        super().__init__(coordinator, entry)
        self.entity_description = description
        self._pool_key = pool_key
        self._pool_name = pool_name
        suffix = description.name or description.key
        self._attr_name = f"{pool_name} {suffix}"
        self._attr_unique_id = (
            f"{self._device_identifier}_{self._pool_key}_{description.key}"
        )

    @property
    def available(self) -> bool:
        """Return if the pool still exists."""
        return bool(super().available) and self._pool() is not None

    @property
    def native_value(self) -> StateType:
        """Return the current state."""
        pool = self._pool()
        if pool is None:
            return None
        return self.entity_description.value_fn(pool)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return pool metadata."""
        pool = self._pool()
        if pool is None:
            return None
        return {
            "pool_key": self._pool_key,
            "pool_name": self._pool_name,
            "raw_status": _raw_pool_status(pool),
        }

    def _pool(self) -> dict[str, Any] | None:
        """Return the currently matching pool by key."""
        pool, _ = _pool_from_key(self.coordinator.data, self._pool_key)
        return pool


class UnifiUnasDriveSensor(UnifiUnasBaseSensor):
    """Per-drive UNAS sensor."""

    entity_description: DriveSensorDescription

    def __init__(
        self,
        coordinator: UnifiUnasCoordinator,
        entry: UnifiDriveConfigEntry,
        description: DriveSensorDescription,
        pool_key: str,
        drive_key: str,
        pool_name: str,
        drive_name: str,
    ) -> None:
        """Initialize the drive sensor."""
        super().__init__(coordinator, entry)
        self.entity_description = description
        self._pool_key = pool_key
        self._drive_key = drive_key
        self._pool_name = pool_name
        self._drive_name = drive_name
        suffix = description.name or description.key
        self._attr_name = f"{pool_name} {drive_name} {suffix}"
        self._attr_unique_id = (
            f"{self._device_identifier}_{self._drive_key}_{description.key}"
        )

    @property
    def available(self) -> bool:
        """Return if the drive still exists."""
        return bool(super().available) and self._drive() is not None

    @property
    def native_value(self) -> StateType:
        """Return the current state."""
        drive = self._drive()
        if drive is None:
            return None
        return self.entity_description.value_fn(drive)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return drive metadata."""
        drive = self._drive()
        if drive is None:
            return None
        return {
            "pool_key": self._pool_key,
            "pool_name": self._pool_name,
            "drive_key": self._drive_key,
            "drive_name": self._drive_name,
            "raw_health": _raw_drive_health(drive),
            **_drive_attributes(drive),
        }

    def _drive(self) -> dict[str, Any] | None:
        """Return currently matching drive by key."""
        pool, _ = _pool_from_key(self.coordinator.data, self._pool_key)
        if pool is None:
            return None

        drives = _pool_drives(pool)
        for drive_index, drive in enumerate(drives):
            if f"{self._pool_key}_{_drive_key(drive, drive_index)}" == self._drive_key:
                return drive

        # Backward compatibility for older unique IDs that used positional drive keys.
        legacy_drive_index = _legacy_drive_index(self._drive_key)
        if legacy_drive_index is not None and legacy_drive_index < len(drives):
            return drives[legacy_drive_index]

        # Additional compatibility: match only the drive-key suffix.
        suffix = self._drive_key
        pool_prefix = f"{self._pool_key}_"
        if suffix.startswith(pool_prefix):
            suffix = suffix[len(pool_prefix) :]
        suffix_normalized = _normalized_token(suffix)
        if suffix_normalized:
            for drive_index, drive in enumerate(drives):
                if _normalized_token(_drive_key(drive, drive_index)) == suffix_normalized:
                    return drive

        return None


class UnifiUnasSnapshotInventorySensor(
    UnifiUnasSnapshotTargetEntity,
    SensorEntity,
):  # type: ignore[misc]
    """Read-only snapshot count sensor for one snapshot target."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: UnifiUnasCoordinator,
        entry: UnifiDriveConfigEntry,
        target: Mapping[str, Any],
    ) -> None:
        """Initialize the snapshot inventory sensor."""
        super().__init__(
            coordinator,
            entry,
            target,
            entity_key="inventory",
            name_suffix="Snapshot Inventory",
        )

    @property
    def native_value(self) -> StateType:
        """Return the snapshot count for this target."""
        inventory = self._inventory()
        if inventory is not None:
            return inventory.get("snapshot_count")

        target = self._current_target()
        return None if target is None else target.get("total_count")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return compact snapshot inventory metadata."""
        attributes = super().extra_state_attributes
        inventory = self._inventory()
        if inventory is None:
            attributes.update(
                {
                    "snapshot_inventory_available": False,
                    "snapshot_inventory_status": self._inventory_error()
                    or SNAPSHOT_INVENTORY_STATUS_FALLBACK,
                    "snapshot_count_source": "snapshot_settings_total_count",
                    "returned_snapshot_count": None,
                    "inventory_total": None,
                    "inventory_offset": None,
                    "inventory_limit": None,
                    "inventory_truncated": False,
                    "snapshot_metadata_truncated": False,
                    "snapshot_metadata_limit": SNAPSHOT_INVENTORY_PREVIEW_LIMIT,
                    "recent_snapshots": [],
                }
            )
            return attributes

        attributes.update(
            {
                "snapshot_inventory_available": True,
                "snapshot_inventory_status": SNAPSHOT_INVENTORY_STATUS_OK,
                "snapshot_count_source": inventory.get("snapshot_count_source"),
                "returned_snapshot_count": inventory.get("returned_snapshot_count"),
                "inventory_locked_count": inventory.get("locked_count"),
                "inventory_total": inventory.get("inventory_total"),
                "inventory_offset": inventory.get("inventory_offset"),
                "inventory_limit": inventory.get("inventory_limit"),
                "inventory_truncated": inventory.get("inventory_truncated", False),
                "latest_snapshot_time": inventory.get("latest_snapshot_time"),
                "oldest_snapshot_time": inventory.get("oldest_snapshot_time"),
                "latest_snapshot_id": inventory.get("latest_snapshot_id"),
                "oldest_snapshot_id": inventory.get("oldest_snapshot_id"),
                "latest_snapshot_name": inventory.get("latest_snapshot_name"),
                "oldest_snapshot_name": inventory.get("oldest_snapshot_name"),
                "latest_snapshot_description": inventory.get(
                    "latest_snapshot_description"
                ),
                "oldest_snapshot_description": inventory.get(
                    "oldest_snapshot_description"
                ),
                "snapshot_ids": inventory.get("snapshot_ids", []),
                "snapshot_names": inventory.get("snapshot_names", []),
                "snapshot_descriptions": inventory.get("snapshot_descriptions", []),
                "snapshot_metadata_truncated": inventory.get(
                    "snapshot_metadata_truncated",
                    False,
                ),
                "snapshot_metadata_limit": inventory.get(
                    "snapshot_metadata_limit",
                    SNAPSHOT_INVENTORY_PREVIEW_LIMIT,
                ),
                "recent_snapshots": inventory.get("recent_snapshots", []),
                "recent_snapshot_count": inventory.get("recent_snapshot_count"),
                "recent_snapshot_limit": inventory.get("recent_snapshot_limit"),
            }
        )
        return attributes

    def _inventory(self) -> dict[str, Any] | None:
        """Return current inventory for this snapshot target."""
        inventory = getattr(self.coordinator, "snapshot_inventory", {})
        if not isinstance(inventory, dict):
            return None
        value = inventory.get(self._target_key)
        return value if isinstance(value, dict) else None

    def _inventory_error(self) -> str | None:
        """Return current inventory error category for this snapshot target."""
        errors = getattr(self.coordinator, "snapshot_inventory_errors", {})
        if not isinstance(errors, dict):
            return None
        value = errors.get(self._target_key)
        return value if isinstance(value, str) else None
