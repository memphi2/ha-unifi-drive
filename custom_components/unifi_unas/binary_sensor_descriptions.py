"""Binary-sensor descriptions for the UniFi Drive integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory

from .storage_helpers import (
    _aggregate_status,
    _at_risk_disk_count,
    _pool_has_problem,
    _pool_in_maintenance,
    _pools,
)


@dataclass(frozen=True, kw_only=True)
class AggregateBinarySensorDescription(BinarySensorEntityDescription):  # type: ignore[misc]
    """Description of an aggregate UNAS binary sensor."""

    value_fn: Callable[[dict[str, Any]], bool]


@dataclass(frozen=True, kw_only=True)
class PoolBinarySensorDescription(BinarySensorEntityDescription):  # type: ignore[misc]
    """Description of a per-pool UNAS binary sensor."""

    value_fn: Callable[[dict[str, Any]], bool]
    entity_category: EntityCategory | None = EntityCategory.DIAGNOSTIC
    entity_registry_enabled_default: bool = False


AGGREGATE_BINARY_SENSOR_TYPES: tuple[AggregateBinarySensorDescription, ...] = (
    AggregateBinarySensorDescription(
        key="device_online",
        translation_key="device_online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda data: True,
    ),
    AggregateBinarySensorDescription(
        key="storage_problem",
        translation_key="storage_problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda data: (
            _aggregate_status(data) == "degraded" or (_at_risk_disk_count(data) > 0)
        ),
    ),
    AggregateBinarySensorDescription(
        key="maintenance_active",
        translation_key="maintenance_active",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: any(_pool_in_maintenance(pool) for pool in _pools(data)),
    ),
)

POOL_BINARY_SENSOR_TYPES: tuple[PoolBinarySensorDescription, ...] = (
    PoolBinarySensorDescription(
        key="pool_problem",
        translation_key="pool_problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda pool: _pool_has_problem(pool),
    ),
    PoolBinarySensorDescription(
        key="pool_maintenance_active",
        translation_key="pool_maintenance_active",
        value_fn=lambda pool: _pool_in_maintenance(pool),
    ),
)
