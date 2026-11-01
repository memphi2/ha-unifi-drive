"""Shared helpers for UniFi Drive snapshot target entities."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from contextlib import suppress
from typing import Any
from weakref import WeakKeyDictionary, WeakSet

from homeassistant.const import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import CannotConnect, InvalidAuth, UnexpectedResponse, UnsupportedFeature
from .const import (
    CONF_SNAPSHOT_BUTTONS_ENABLED,
    DEFAULT_SNAPSHOT_BUTTONS_ENABLED,
)
from .coordinator import UnifiUnasCoordinator
from .entity_base import UnifiUnasDeviceInfoMixin
from .entry_options import entry_bool
from .exceptions import unifi_unas_error, unifi_unas_validation_error
from .runtime import UnifiDriveConfigEntry
from .snapshot_types import (
    snapshot_target_key,
    snapshot_target_name,
    snapshot_target_slug,
    snapshot_target_type,
)
from .snapshot_repairs import (
    async_clear_snapshot_action_issues,
    async_clear_snapshot_target_missing_issue,
    async_create_snapshot_action_issue,
    async_update_snapshot_target_missing_issue,
)
from .security import safe_error_text

SnapshotTargetEntityFactory = Callable[
    [Mapping[str, object]],
    Iterable["UnifiUnasSnapshotTargetEntity"],
]
SnapshotTargetFilter = Callable[[Mapping[str, object]], bool]
_SNAPSHOT_TARGET_ENTITIES: WeakKeyDictionary[
    UnifiUnasCoordinator, dict[str, WeakSet["UnifiUnasSnapshotTargetEntity"]]
] = WeakKeyDictionary()
_SNAPSHOT_TARGET_ENTITIES_BY_ID: dict[
    int,
    dict[str, WeakSet["UnifiUnasSnapshotTargetEntity"]],
] = {}
_SNAPSHOT_TARGET_MISSING_REPAIR_THRESHOLD = 3
_SNAPSHOT_TARGET_MISSING_STATE = "_unifi_unas_snapshot_target_missing_state"


def _snapshot_target_bucket(
    coordinator: UnifiUnasCoordinator,
) -> dict[str, WeakSet["UnifiUnasSnapshotTargetEntity"]]:
    """Return per-coordinator storage for snapshot target entities."""
    try:
        return _SNAPSHOT_TARGET_ENTITIES.setdefault(coordinator, {})
    except TypeError:
        return _SNAPSHOT_TARGET_ENTITIES_BY_ID.setdefault(id(coordinator), {})


def _clear_snapshot_target_entities_for_coordinator(
    coordinator: UnifiUnasCoordinator,
) -> None:
    """Drop cached snapshot entity buckets for a coordinator."""
    # Coordinator objects used in lightweight tests may not be weakrefable.
    with suppress(TypeError):
        _SNAPSHOT_TARGET_ENTITIES.pop(coordinator, None)
    _SNAPSHOT_TARGET_ENTITIES_BY_ID.pop(id(coordinator), None)


def snapshot_entities_enabled(entry: UnifiDriveConfigEntry) -> bool:
    """Return whether snapshot target entities are enabled for an entry."""
    return bool(
        entry_bool(
            entry,
            CONF_SNAPSHOT_BUTTONS_ENABLED,
            DEFAULT_SNAPSHOT_BUTTONS_ENABLED,
        )
    )


def async_setup_snapshot_target_entities(
    entry: UnifiDriveConfigEntry,
    coordinator: UnifiUnasCoordinator,
    async_add_entities: AddEntitiesCallback,
    entity_factory: SnapshotTargetEntityFactory,
    *,
    target_filter: SnapshotTargetFilter | None = None,
) -> None:
    """Set up snapshot target entities for one platform when enabled."""
    if not snapshot_entities_enabled(entry):
        return

    async_track_snapshot_target_entities(
        entry,
        coordinator,
        async_add_entities,
        entity_factory,
        target_filter=target_filter,
    )


def async_track_snapshot_target_entities(
    entry: UnifiDriveConfigEntry,
    coordinator: UnifiUnasCoordinator,
    async_add_entities: AddEntitiesCallback,
    entity_factory: SnapshotTargetEntityFactory,
    *,
    target_filter: SnapshotTargetFilter | None = None,
) -> None:
    """Add one factory batch per snapshot target as coordinator data appears."""
    known_target_keys: set[str] = set()

    def _add_missing_entities() -> None:
        new_entities: list[UnifiUnasSnapshotTargetEntity] = []
        for target in getattr(coordinator, "snapshot_settings", ()):
            if not isinstance(target, Mapping):
                continue
            if target_filter is not None and not target_filter(target):
                continue
            target_key = snapshot_target_key(target)
            if not target_key or target_key in known_target_keys:
                continue
            entities = list(entity_factory(target))
            if not entities:
                continue
            known_target_keys.add(target_key)
            new_entities.extend(entities)

        if new_entities:
            async_add_entities(new_entities)
        _update_snapshot_target_missing_state(coordinator, entry)

    _add_missing_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_missing_entities))


def _update_snapshot_target_missing_state(
    coordinator: UnifiUnasCoordinator,
    entry: UnifiDriveConfigEntry,
) -> None:
    """Track snapshot targets that disappeared without deleting their entities."""
    if not getattr(coordinator, "snapshot_settings_available", True):
        return
    current_targets = tuple(
        target
        for target in getattr(coordinator, "snapshot_settings", ())
        if isinstance(target, Mapping)
    )
    current_target_keys = {
        target_key
        for target in current_targets
        if (target_key := snapshot_target_key(target))
    }
    current_settings_id = id(getattr(coordinator, "snapshot_settings", None))
    state = getattr(coordinator, _SNAPSHOT_TARGET_MISSING_STATE, None)
    if not isinstance(state, dict):
        state = {"settings_id": None, "counts": {}}
        setattr(coordinator, _SNAPSHOT_TARGET_MISSING_STATE, state)

    counts = state.setdefault("counts", {})
    should_increment = state.get("settings_id") != current_settings_id
    if should_increment:
        state["settings_id"] = current_settings_id

    missing_summary: dict[str, dict[str, Any]] = {}
    bucket = _snapshot_target_bucket(coordinator)
    for target_key, target_entities in list(bucket.items()):
        entities = list(target_entities)
        if not entities:
            continue
        first_entity = entities[0]
        if target_key in current_target_keys:
            if counts.pop(target_key, 0):
                async_clear_snapshot_target_missing_issue(
                    getattr(coordinator, "hass", None),
                    entry,
                    target_key=target_key,
                )
            for entity in entities:
                entity._set_snapshot_target_missing_count(0)
            continue

        if should_increment:
            counts[target_key] = int(counts.get(target_key, 0)) + 1
        missing_count = int(counts.get(target_key, 0))
        for entity in entities:
            entity._set_snapshot_target_missing_count(missing_count)
        missing_summary[target_key] = {
            "missing_count": missing_count,
            "target_name": first_entity._target_name,
            "target_type": first_entity._target_type,
        }
        async_update_snapshot_target_missing_issue(
            getattr(coordinator, "hass", None),
            entry,
            target_key=target_key,
            target_name=first_entity._target_name,
            target_type=first_entity._target_type,
            missing_count=missing_count,
            threshold=_SNAPSHOT_TARGET_MISSING_REPAIR_THRESHOLD,
        )

    coordinator.snapshot_target_missing_counts = missing_summary


class UnifiUnasSnapshotTargetEntity(
    UnifiUnasDeviceInfoMixin,
    CoordinatorEntity[UnifiUnasCoordinator],
):
    """Base entity for one UniFi Drive snapshot target."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: UnifiUnasCoordinator,
        entry: UnifiDriveConfigEntry,
        target: Mapping[str, Any],
        *,
        entity_key: str,
        name_suffix: str,
        icon: str | None = None,
    ) -> None:
        """Initialize the snapshot target entity."""
        super().__init__(coordinator)
        self._entry = entry
        self._set_device_context(entry)
        self._target_key = snapshot_target_key(target)
        self._target_name = snapshot_target_name(target)
        self._target_type = snapshot_target_type(target)
        self._snapshot_target_missing_count = 0
        self._attr_name = f"{self._target_name} {name_suffix}"
        self._attr_translation_key = f"snapshot_{entity_key}"
        self._attr_unique_id = (
            f"{self._device_identifier}_snapshot_{snapshot_target_slug(self._target_key)}"
            f"_{entity_key}"
        )
        if self._target_key:
            target_entities = _snapshot_target_bucket(coordinator).setdefault(
                self._target_key, WeakSet()
            )
            target_entities.add(self)

    @property
    def available(self) -> bool:
        """Return whether the snapshot target can be configured."""
        return (
            bool(super().available)
            and self.coordinator.is_device_online
            and getattr(self.coordinator, "snapshot_settings_available", True)
            and self._current_target() is not None
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return snapshot target metadata for UI inspection."""
        target = self._current_target()
        if target is None:
            return {
                "target_key": self._target_key,
                "target_name": self._target_name,
                "target_type": self._target_type,
                "snapshot_target_present": False,
                "snapshot_target_missing_count": self._snapshot_target_missing_count,
                "snapshot_target_missing_threshold": (
                    _SNAPSHOT_TARGET_MISSING_REPAIR_THRESHOLD
                ),
            }

        return {
            "target_key": snapshot_target_key(target),
            "target_id": target.get("id"),
            "target_type": snapshot_target_type(target),
            "target_name": snapshot_target_name(target),
            "snapshot_target_present": True,
            "snapshot_target_missing_count": self._snapshot_target_missing_count,
            "snapshot_enabled": bool(target.get("enabled")),
            "max_count": target.get("max_count"),
            "total_count": target.get("total_count"),
            "locked_count": target.get("locked_count"),
            "schedule_enabled": bool(target.get("schedule_enabled")),
            "schedule_frequency": target.get("schedule_frequency"),
            "schedule_time": target.get("schedule_time"),
            "schedule_weekdays": target.get("schedule_weekdays"),
            "schedule_monthdays": target.get("schedule_monthdays"),
            "paused": bool(target.get("paused")),
        }

    def _current_target(self) -> dict[str, Any] | None:
        """Return the latest coordinator target for this entity."""
        if not self._target_key:
            return None

        for target in getattr(self.coordinator, "snapshot_settings", ()):
            if not isinstance(target, Mapping):
                continue
            if snapshot_target_key(target) == self._target_key:
                return dict(target)
        return None

    def _set_snapshot_target_missing_count(self, missing_count: int) -> None:
        """Update consecutive missing-target refresh count."""
        self._snapshot_target_missing_count = max(0, missing_count)

    def _validated_target(self, action: str) -> dict[str, Any]:
        """Return the current target or raise a user-facing error."""
        if not self.coordinator.is_device_online:
            raise unifi_unas_validation_error(
                f"Cannot {action} while the UniFi Drive device is offline",
                "device_offline",
                action=action,
            )

        target = self._current_target()
        if target is None:
            raise unifi_unas_error(
                f"Snapshot target '{self._target_name}' is no longer exposed "
                "by UniFi Drive",
                "snapshot_target_missing",
                target_name=self._target_name,
            )
        return target

    async def _async_update_snapshot_target(
        self,
        *,
        enabled: bool | None = None,
        max_count: int | None = None,
        schedule_frequency: str | None = None,
        schedule_time: str | None = None,
        schedule_weekdays: str | None = None,
        schedule_monthdays: str | None = None,
    ) -> None:
        """Update this snapshot target through the API client."""
        target = self._validated_target("change snapshot settings")
        try:
            await self.coordinator.client.async_update_snapshot_target_settings(
                target,
                enabled=enabled,
                max_count=max_count,
                schedule_frequency=schedule_frequency,
                schedule_time=schedule_time,
                schedule_weekdays=schedule_weekdays,
                schedule_monthdays=schedule_monthdays,
            )
        except InvalidAuth as err:
            async_create_snapshot_action_issue(
                getattr(self.coordinator, "hass", None),
                self._entry,
                action="settings",
                target=target,
                err=err,
            )
            raise unifi_unas_error(
                "The configured UniFi account/API key cannot change snapshot settings",
                "snapshot_action_permission",
                permission_action="change snapshot settings",
            ) from err
        except UnsupportedFeature as err:
            async_create_snapshot_action_issue(
                getattr(self.coordinator, "hass", None),
                self._entry,
                action="settings",
                target=target,
                err=err,
            )
            error = safe_error_text(err)
            raise unifi_unas_error(
                f"Could not change snapshot settings for '{self._target_name}': {error}",
                "snapshot_settings_unsupported",
                target_name=self._target_name,
                error=error,
            ) from err
        except (CannotConnect, UnexpectedResponse) as err:
            error = safe_error_text(err)
            raise unifi_unas_error(
                f"Could not change snapshot settings for '{self._target_name}': {error}",
                "snapshot_settings_failed",
                target_name=self._target_name,
                error=error,
            ) from err

        async_clear_snapshot_action_issues(
            getattr(self.coordinator, "hass", None),
            self._entry,
            action="settings",
            target=target,
        )
        self.coordinator.request_snapshot_inventory_refresh()
        await self.coordinator.async_request_refresh()
        self._write_all_target_entity_states()

    def _write_all_target_entity_states(self) -> None:
        """Write HA state updates for all snapshot entities on this target."""
        if not self._target_key:
            self.async_write_ha_state()
            return

        target_entities = _snapshot_target_bucket(self.coordinator).get(
            self._target_key, ()
        )
        if not target_entities:
            self.async_write_ha_state()
            return

        for entity in target_entities:
            entity.async_write_ha_state()
