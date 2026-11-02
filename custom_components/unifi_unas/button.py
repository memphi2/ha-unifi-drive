"""Button entities for the UniFi Drive integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SSL, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo

from .api import CannotConnect, InvalidAuth, UnexpectedResponse, UnsupportedFeature
from .const import (
    CONF_WOL_BROADCAST_ADDRESS,
    CONF_WOL_ENABLED,
    CONF_WOL_MAC_ADDRESS,
    CONF_WOL_PORT,
    DEFAULT_PORT,
    DEFAULT_SSL,
    DEFAULT_WOL_BROADCAST_ADDRESS,
    DEFAULT_WOL_ENABLED,
    DEFAULT_WOL_PORT,
    POWEROFF_PATH,
    REBOOT_PATH,
)
from .coordinator import UnifiUnasCoordinator
from .device import build_device_info
from .entry_options import entry_bool, entry_int, entry_str, entry_value
from .exceptions import unifi_unas_error, unifi_unas_validation_error
from .snapshot_entities import (
    UnifiUnasSnapshotTargetEntity,
    async_setup_snapshot_target_entities,
)
from .snapshot_types import (
    snapshot_create_button_supported_for_inventory,
    snapshot_target_slug,
    snapshot_target_type,
)
from .snapshot_repairs import (
    async_clear_snapshot_action_issues,
    async_create_snapshot_action_issue,
)
from .runtime import UnifiDriveConfigEntry, coordinator_from_entry
from .security import safe_error_text
from .url_helpers import build_console_url
from .wake_on_lan import WakeOnLanError, async_send_magic_packet, mask_mac_address

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class SystemButtonDescription(ButtonEntityDescription):  # type: ignore[misc]
    """Description for a UniFi OS system button."""

    endpoint: str
    action_name: str
    call: Callable[[UnifiUnasCoordinator], Awaitable[None]]
    entity_category: EntityCategory | None = EntityCategory.CONFIG


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UnifiDriveConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up UniFi Drive buttons from a config entry."""
    coordinator = coordinator_from_entry(entry)
    entities: list[ButtonEntity] = []

    if _wol_configured(entry):
        entities.append(UnifiUnasWakeOnLanButton(coordinator, entry))

    entities.extend(
        [
            UnifiUnasSystemButton(
                coordinator,
                entry,
                SystemButtonDescription(
                    key="reboot",
                    translation_key="restart",
                    endpoint=REBOOT_PATH,
                    action_name="restart",
                    call=lambda coord: coord.client.async_reboot(),
                ),
            ),
            UnifiUnasSystemButton(
                coordinator,
                entry,
                SystemButtonDescription(
                    key="shutdown",
                    translation_key="shutdown",
                    endpoint=POWEROFF_PATH,
                    action_name="shut down",
                    call=lambda coord: coord.client.async_poweroff(),
                ),
            ),
        ]
    )
    async_add_entities(entities)

    known_backup_task_ids: set[str] = set()

    def _add_missing_backup_buttons() -> None:
        """Create backup trigger buttons when backup tasks become available."""
        new_entities: list[ButtonEntity] = []
        for task in coordinator.backup_tasks:
            task_id = str(task.get("id", "")).strip()
            if not task_id or task_id in known_backup_task_ids:
                continue
            known_backup_task_ids.add(task_id)
            new_entities.append(UnifiUnasBackupTaskButton(coordinator, entry, task))

        if new_entities:
            async_add_entities(new_entities)

    _add_missing_backup_buttons()
    entry.async_on_unload(coordinator.async_add_listener(_add_missing_backup_buttons))

    async_setup_snapshot_target_entities(
        entry,
        coordinator,
        async_add_entities,
        lambda target: (UnifiUnasSnapshotButton(coordinator, entry, dict(target)),),
        target_filter=lambda target: _snapshot_create_button_supported(
            coordinator,
            target,
        ),
    )


def _snapshot_create_button_supported(
    coordinator: UnifiUnasCoordinator,
    target: Mapping[str, Any],
) -> bool:
    """Return whether a manual create button should be exposed for a target."""
    return snapshot_create_button_supported_for_inventory(
        target,
        snapshot_inventory=getattr(coordinator, "snapshot_inventory", {}) or {},
        snapshot_inventory_errors=(
            getattr(coordinator, "snapshot_inventory_errors", {}) or {}
        ),
    )


class UnifiUnasSystemButton(
    CoordinatorEntity[UnifiUnasCoordinator], ButtonEntity  # type: ignore[misc]
):
    """Button that triggers a UniFi OS system action."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: UnifiUnasCoordinator,
        entry: UnifiDriveConfigEntry,
        description: SystemButtonDescription,
    ) -> None:
        """Initialize the system button."""
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
        self._device_identifier = entry.unique_id or entry.entry_id
        self._attr_translation_key = description.translation_key
        self._attr_unique_id = f"{self._device_identifier}_{description.key}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return permission hints for diagnostics and UI inspection."""
        return {
            "endpoint": self.entity_description.endpoint,
            "requires_unifi_permission": "edit:os-settings:poweroff",
            "poweroff_permission_hint": self.coordinator.client.poweroff_permission_hint,
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Build dynamic device info from the latest coordinator payload."""
        return build_device_info(
            self.coordinator,
            self._entry,
            self._device_identifier,
        )

    async def async_press(self) -> None:
        """Trigger the configured system action."""
        if not self.coordinator.is_device_online:
            raise unifi_unas_validation_error(
                "Cannot trigger this UniFi Drive action while the device is offline",
                "device_offline",
                action="trigger this UniFi Drive action",
            )
        try:
            await self.entity_description.call(self.coordinator)
        except InvalidAuth as err:
            raise unifi_unas_error(
                "The configured UniFi account/API key cannot perform this system action.",
                "system_action_permission",
            ) from err
        except (CannotConnect, UnexpectedResponse, UnsupportedFeature) as err:
            error = safe_error_text(err)
            raise unifi_unas_error(
                f"Could not {self.entity_description.action_name} UniFi Drive: "
                f"{error}",
                "system_action_failed",
                action=self.entity_description.action_name,
                error=error,
            ) from err

    @property
    def available(self) -> bool:
        """Return availability based on coordinator and device reachability."""
        return bool(super().available) and self.coordinator.is_device_online


class UnifiUnasWakeOnLanButton(ButtonEntity):  # type: ignore[misc]
    """Button that sends a Wake-on-LAN magic packet to the UNAS."""

    _attr_has_entity_name = True
    _attr_translation_key = "wake_on_lan"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: UnifiUnasCoordinator,
        entry: UnifiDriveConfigEntry,
    ) -> None:
        """Initialize the Wake-on-LAN button."""
        self._coordinator = coordinator
        self._entry = entry
        self._device_identifier = entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{self._device_identifier}_wake_on_lan"
        self._configuration_url = (
            coordinator.client.base_url or _configuration_url_from_entry(entry)
        )

    @property
    def available(self) -> bool:
        """Return availability.

        The WOL button must remain available while the UNAS is powered off.
        """
        return _wol_configured(self._entry)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return WOL target details for UI inspection."""
        return {
            "mac_address": mask_mac_address(
                entry_value(self._entry, CONF_WOL_MAC_ADDRESS)
            ),
            "broadcast_address": entry_value(
                self._entry,
                CONF_WOL_BROADCAST_ADDRESS,
                DEFAULT_WOL_BROADCAST_ADDRESS,
            ),
            "broadcast_port": entry_int(self._entry, CONF_WOL_PORT, DEFAULT_WOL_PORT),
            "packets": 3,
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Build dynamic device info from the latest coordinator payload."""
        return build_device_info(
            self._coordinator,
            self._entry,
            self._device_identifier,
            configuration_url=self._configuration_url,
        )

    async def async_press(self) -> None:
        """Send a Wake-on-LAN magic packet."""
        if not _wol_configured(self._entry):
            raise unifi_unas_error(
                "Wake-on-LAN is not configured for this UniFi Drive entry.",
                "wake_on_lan_mac_missing",
            )

        mac_address = entry_str(self._entry, CONF_WOL_MAC_ADDRESS)
        broadcast_address = entry_str(
            self._entry,
            CONF_WOL_BROADCAST_ADDRESS,
            DEFAULT_WOL_BROADCAST_ADDRESS,
        )
        broadcast_port = entry_int(self._entry, CONF_WOL_PORT, DEFAULT_WOL_PORT)

        try:
            await async_send_magic_packet(
                mac_address,
                broadcast_address=broadcast_address,
                port=broadcast_port,
            )
        except (ValueError, WakeOnLanError) as err:
            error = safe_error_text(err)
            raise unifi_unas_error(
                f"Could not send Wake-on-LAN packet to UniFi Drive: {error}",
                "wake_on_lan_send_failed",
                error=error,
            ) from err


class UnifiUnasBackupTaskButton(
    CoordinatorEntity[UnifiUnasCoordinator], ButtonEntity  # type: ignore[misc]
):
    """Button that triggers a remote-backup task on the UNAS."""

    _attr_has_entity_name = True
    _attr_translation_key = "backup_task"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: UnifiUnasCoordinator,
        entry: UnifiDriveConfigEntry,
        task: dict[str, Any],
    ) -> None:
        """Initialize the backup task button."""
        super().__init__(coordinator)
        self._entry = entry
        self._device_identifier = entry.unique_id or entry.entry_id
        self._task_id = str(task["id"])
        self._task_name = str(task.get("name") or self._task_id)
        self._attr_translation_placeholders = {"task_name": self._task_name}
        self._attr_unique_id = f"{self._device_identifier}_backup_{self._task_id}"

    @property
    def available(self) -> bool:
        """Return whether this backup task still exists."""
        if not bool(super().available):
            return False
        if not self.coordinator.is_device_online:
            return False
        return any(
            str(task.get("id")) == self._task_id for task in self.coordinator.backup_tasks
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return task metadata for UI/diagnostics."""
        for task in self.coordinator.backup_tasks:
            if str(task.get("id")) == self._task_id:
                return {
                    "task_id": self._task_id,
                    "task_name": str(task.get("name", self._task_name)),
                }
        return {
            "task_id": self._task_id,
            "task_name": self._task_name,
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Build dynamic device info from the latest coordinator payload."""
        return build_device_info(
            self.coordinator,
            self._entry,
            self._device_identifier,
        )

    async def async_press(self) -> None:
        """Trigger the backup task."""
        if not self.coordinator.is_device_online:
            raise unifi_unas_validation_error(
                f"Cannot trigger backup task '{self._task_name}' while the device is offline",
                "backup_task_offline",
            )
        try:
            await self.coordinator.client.async_run_backup_task(self._task_id)
        except InvalidAuth as err:
            raise unifi_unas_error(
                "The configured UniFi account/API key cannot trigger this backup task",
                "backup_task_permission",
            ) from err
        except (CannotConnect, UnexpectedResponse, UnsupportedFeature) as err:
            error = safe_error_text(err)
            raise unifi_unas_error(
                f"Could not trigger backup task '{self._task_name}': {error}",
                "backup_task_failed",
                error=error,
            ) from err

        await self.coordinator.async_request_refresh()


class UnifiUnasSnapshotButton(
    UnifiUnasSnapshotTargetEntity, ButtonEntity  # type: ignore[misc]
):
    """Button that creates a snapshot on the UNAS."""

    def __init__(
        self,
        coordinator: UnifiUnasCoordinator,
        entry: UnifiDriveConfigEntry,
        target: Mapping[str, Any],
    ) -> None:
        """Initialize the snapshot button."""
        super().__init__(
            coordinator,
            entry,
            target,
            entity_key="create",
        )
        self._target_type = snapshot_target_type(target)
        # Keep the v0.3.0 create-button unique ID stable while sharing the
        # snapshot target base entity with the config entities.
        self._attr_unique_id = (
            f"{self._device_identifier}_snapshot_{snapshot_target_slug(self._target_key)}"
        )

    @property
    def available(self) -> bool:
        """Return whether this snapshot target can currently create snapshots."""
        target = self._current_target()
        if not bool(super().available) or target is None:
            return False
        return bool(target.get("enabled")) and not bool(target.get("restoring_drive"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return snapshot target metadata for UI/diagnostics."""
        attributes = super().extra_state_attributes
        attributes.setdefault("target_type", self._target_type)
        return attributes

    async def async_press(self) -> None:
        """Create a snapshot for the configured target."""
        target = self._validated_target("create snapshot")
        if not bool(target.get("enabled")):
            raise unifi_unas_error(
                f"Snapshot protection is not enabled for '{self._target_name}' "
                "in UniFi Drive",
                "snapshot_not_enabled",
                target_name=self._target_name,
            )

        try:
            await self.coordinator.client.async_create_snapshot_target(
                target,
            )
        except InvalidAuth as err:
            async_create_snapshot_action_issue(
                getattr(self.coordinator, "hass", None),
                self._entry,
                action="create",
                target=target,
                err=err,
            )
            raise unifi_unas_error(
                "The configured UniFi account/API key cannot create snapshots",
                "snapshot_action_permission",
                permission_action="create snapshots",
            ) from err
        except UnsupportedFeature as err:
            async_create_snapshot_action_issue(
                getattr(self.coordinator, "hass", None),
                self._entry,
                action="create",
                target=target,
                err=err,
            )
            error = safe_error_text(err)
            raise unifi_unas_error(
                f"Could not create snapshot for '{self._target_name}': {error}",
                "snapshot_action_unsupported",
                action="create snapshot",
                target_name=self._target_name,
                error=error,
            ) from err
        except (CannotConnect, UnexpectedResponse) as err:
            error = safe_error_text(err)
            raise unifi_unas_error(
                f"Could not create snapshot for '{self._target_name}': {error}",
                "snapshot_action_failed",
                action="create snapshot",
                target_name=self._target_name,
                error=error,
            ) from err

        async_clear_snapshot_action_issues(
            getattr(self.coordinator, "hass", None),
            self._entry,
            action="create",
            target=target,
        )
        self.coordinator.request_snapshot_inventory_refresh()
        await self.coordinator.async_request_refresh()


def _wol_configured(entry: UnifiDriveConfigEntry) -> bool:
    """Return whether Wake-on-LAN is configured for this entry."""
    return bool(
        entry_bool(entry, CONF_WOL_ENABLED, DEFAULT_WOL_ENABLED)
        and entry_value(entry, CONF_WOL_MAC_ADDRESS)
    )


def _configuration_url_from_entry(entry: UnifiDriveConfigEntry) -> str:
    """Build a console configuration URL from entry data."""
    scheme = "https" if bool(entry.data.get(CONF_SSL, DEFAULT_SSL)) else "http"
    host = str(entry.data[CONF_HOST])
    port = int(entry.data.get(CONF_PORT, DEFAULT_PORT))
    return build_console_url(scheme, host, port)
