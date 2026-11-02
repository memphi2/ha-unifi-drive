"""Update entities for the UniFi Drive integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityDescription,
    UpdateEntityFeature,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo

from .api import (
    CannotConnect,
    InvalidAuth,
    UnexpectedResponse,
    UnifiUnasApiClient,
    UnsupportedFeature,
)
from .coordinator import UnifiUnasCoordinator
from .device import build_device_info
from .exceptions import unifi_unas_error, unifi_unas_validation_error
from .runtime import UnifiDriveConfigEntry, coordinator_from_entry
from .security import safe_error_text
from .system_metadata import (
    drive_version as _drive_version,
    normalized_token as _normalized_token,
    system_payload as _system_payload,
    unifi_os_version as _unifi_os_version,
)

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class UnifiDriveUpdateDescription(UpdateEntityDescription):  # type: ignore[misc]
    """Description of a UniFi Drive update entity."""

    installed_version_fn: Callable[[dict[str, Any]], str | None]
    latest_version_fn: Callable[[dict[str, Any]], str | None]
    install_fn: Callable[[UnifiUnasApiClient], Awaitable[None]]
    title_fn: Callable[[dict[str, Any]], str]
    in_progress_fn: Callable[[dict[str, Any]], bool | None] = lambda _data: None
    update_percentage_fn: Callable[[dict[str, Any]], int | float | None] = lambda _data: None


UPDATE_TYPES: tuple[UnifiDriveUpdateDescription, ...] = (
    UnifiDriveUpdateDescription(
        key="unifi_os",
        translation_key="unifi_os",
        entity_category=EntityCategory.CONFIG,
        device_class=UpdateDeviceClass.FIRMWARE,
        installed_version_fn=lambda data: _clean_version(_unifi_os_version(data)),
        latest_version_fn=lambda data: (
            _unifi_os_latest_version(data) or _clean_version(_unifi_os_version(data))
        ),
        install_fn=lambda client: client.async_install_unifi_os_update(),
        title_fn=lambda data: f"UniFi OS / {_system_model_name(data)}",
        in_progress_fn=lambda data: _unifi_os_update_in_progress(data),
        update_percentage_fn=lambda data: _unifi_os_update_percentage(data),
    ),
    UnifiDriveUpdateDescription(
        key="drive",
        translation_key="drive",
        entity_category=EntityCategory.CONFIG,
        installed_version_fn=lambda data: _clean_version(_drive_version(data)),
        latest_version_fn=lambda data: (
            _drive_latest_version(data) or _clean_version(_drive_version(data))
        ),
        install_fn=lambda client: client.async_install_drive_update(),
        title_fn=lambda data: f"Application / {_drive_application_name(data)}",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UnifiDriveConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up UniFi Drive update entities from a config entry."""
    coordinator = coordinator_from_entry(entry)

    async_add_entities(
        UnifiDriveUpdateEntity(coordinator, entry, description)
        for description in UPDATE_TYPES
    )


class UnifiDriveUpdateEntity(
    CoordinatorEntity[UnifiUnasCoordinator],  # type: ignore[misc]
    UpdateEntity,  # type: ignore[misc]
):
    """UniFi OS or Drive update entity."""

    entity_description: UnifiDriveUpdateDescription
    _attr_has_entity_name = True
    _attr_supported_features = UpdateEntityFeature.INSTALL

    def __init__(
        self,
        coordinator: UnifiUnasCoordinator,
        entry: UnifiDriveConfigEntry,
        description: UnifiDriveUpdateDescription,
    ) -> None:
        """Initialize the update entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
        self._device_identifier = entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{self._device_identifier}_{description.key}_update"

    @property
    def device_info(self) -> DeviceInfo:
        """Build dynamic device info from the latest coordinator payload."""
        return build_device_info(
            self.coordinator,
            self._entry,
            self._device_identifier,
        )

    @property
    def available(self) -> bool:
        """Return whether enough update metadata is available."""
        return (
            bool(super().available)
            and self.coordinator.is_device_online
            and bool(self.coordinator.data)
            and self.installed_version is not None
        )

    @property
    def installed_version(self) -> str | None:
        """Return the currently installed version."""
        if not self.coordinator.data:
            return None
        return self.entity_description.installed_version_fn(self.coordinator.data)

    @property
    def latest_version(self) -> str | None:
        """Return the latest available version."""
        if not self.coordinator.data:
            return None
        return self.entity_description.latest_version_fn(self.coordinator.data)

    @property
    def title(self) -> str:
        """Return the software title shown by Home Assistant update cards."""
        if not self.coordinator.data:
            return self.entity_description.title_fn({})
        return self.entity_description.title_fn(self.coordinator.data)

    @property
    def in_progress(self) -> bool:
        """Return whether an update is currently running."""
        if not self.coordinator.data:
            return False
        return self.entity_description.in_progress_fn(self.coordinator.data) is True

    @property
    def update_percentage(self) -> int | float | None:
        """Return update progress when UniFi OS exposes it."""
        if not self.coordinator.data:
            return None
        return self.entity_description.update_percentage_fn(self.coordinator.data)

    @property
    def release_summary(self) -> str:
        """Return an action warning shown by Home Assistant update dialogs."""
        return (
            "Experimental local UniFi OS update action. Behavior can depend on "
            "firmware version and requires a sufficiently privileged account or API key."
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return update action metadata for UI inspection."""
        return {
            "action_note": "Experimental local UniFi OS endpoint",
            "firmware_dependent": True,
            "requires_privileged_account": True,
        }

    async def async_install(
        self,
        version: str | None,
        _backup: bool,
        **_kwargs: Any,
    ) -> None:
        """Install the currently offered update."""
        latest_version = self.latest_version
        if version and latest_version and _clean_version(version) != latest_version:
            raise unifi_unas_validation_error(
                f"Installing a specific {self.entity_description.key} version is not supported",
                "update_version_not_supported",
                update=self.entity_description.key,
            )
        if not self.coordinator.is_device_online:
            raise unifi_unas_validation_error(
                "Cannot install update actions while the UniFi Drive device is offline",
                "device_offline",
                action="install update actions",
            )

        try:
            await self.entity_description.install_fn(self.coordinator.client)
        except (CannotConnect, InvalidAuth, UnexpectedResponse, UnsupportedFeature) as err:
            error = safe_error_text(err)
            raise unifi_unas_error(
                error,
                "update_install_failed",
                error=error,
            ) from err

        await self.coordinator.async_request_refresh()


def _clean_version(value: Any) -> str | None:
    """Return a compact display version from UniFi version strings."""
    if isinstance(value, bool):
        return None
    text = str(value).strip() if value not in (None, "") else ""
    if not text:
        return None
    if text.lower().startswith("v"):
        text = text[1:]
    if "+" in text:
        text = text.split("+", 1)[0]
    return text.strip() or None


def _unifi_os_latest_version(data: dict[str, Any]) -> str | None:
    """Return the offered UniFi OS version."""
    system = _system_payload(data)
    for payload in (
        system.get("latestUpdate"),
        (system.get("firmware") or {}).get("latest")
        if isinstance(system.get("firmware"), dict)
        else None,
    ):
        if isinstance(payload, dict) and (version := _clean_version(payload.get("version"))):
            return version

    devices = system.get("devices")
    if isinstance(devices, dict):
        unifi_os_devices = devices.get("unifiOS")
        if isinstance(unifi_os_devices, list):
            for device in unifi_os_devices:
                if isinstance(device, dict) and (
                    version := _clean_version(device.get("updateAvailable"))
                ):
                    return version
    return None


def _system_model_name(data: dict[str, Any]) -> str:
    """Return a compact UniFi OS hardware identifier for update titles."""
    system = _system_payload(data)
    hardware = system.get("hardware")
    if isinstance(hardware, dict):
        for key in ("shortname", "platform", "model", "name"):
            if value := _clean_text(hardware.get(key)):
                return value

    latest_update = system.get("latestUpdate")
    if isinstance(latest_update, dict) and (platform := _clean_text(latest_update.get("platform"))):
        return platform

    return "UNAS"


def _drive_latest_version(data: dict[str, Any]) -> str | None:
    """Return the offered UniFi Drive application version."""
    controller = _drive_controller(data)
    if controller is None:
        return None

    for key in (
        "updateAvailable",
        "latestVersion",
        "latest_version",
        "availableVersion",
        "available_version",
        "updateVersion",
        "upgradeVersion",
        "targetVersion",
    ):
        if version := _clean_version(controller.get(key)):
            return version

    for key in ("update", "latestUpdate", "availableUpdate", "release", "updateInfo"):
        nested = controller.get(key)
        if isinstance(nested, dict) and (version := _nested_version(nested)):
            return version

    return None


def _drive_application_name(data: dict[str, Any]) -> str:
    """Return the Drive application name from UniFi OS controller metadata."""
    controller = _drive_controller(data)
    if controller is not None:
        for key in ("displayName", "display_name", "title", "name"):
            if value := _clean_text(controller.get(key)):
                return value.title()
    return "Drive"


def _drive_controller(data: dict[str, Any]) -> dict[str, Any] | None:
    """Return the Drive controller object from UniFi OS system metadata."""
    apps = _system_payload(data).get("apps")
    if not isinstance(apps, dict):
        return None

    for key in ("controllers", "apps"):
        items = apps.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if (
                isinstance(item, dict)
                and _normalized_token(str(item.get("name", ""))) == "drive"
            ):
                return item
    return None


def _nested_version(payload: dict[str, Any]) -> str | None:
    """Return a likely version field from a nested update payload."""
    for key in (
        "version",
        "versionRaw",
        "latestVersion",
        "latest_version",
        "availableVersion",
        "updateVersion",
    ):
        if version := _clean_version(payload.get(key)):
            return version
    return None


def _clean_text(value: Any) -> str | None:
    """Return stripped text for non-empty non-boolean values."""
    if isinstance(value, bool) or value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def _unifi_os_update_in_progress(data: dict[str, Any]) -> bool | None:
    """Return whether UniFi OS reports an update running."""
    firmware = _system_payload(data).get("firmware")
    if not isinstance(firmware, dict):
        return None

    update = firmware.get("update")
    if not isinstance(update, dict):
        return None

    state = _normalized_token(str(update.get("state", "")))
    if not state:
        return None
    return state not in {"notstarted", "done", "idle", "completed", "none"}


def _unifi_os_update_percentage(data: dict[str, Any]) -> int | float | None:
    """Return UniFi OS update progress percentage when available."""
    firmware = _system_payload(data).get("firmware")
    if not isinstance(firmware, dict):
        return None
    update = firmware.get("update")
    if not isinstance(update, dict):
        return None

    for key in ("progress", "percentage", "percent", "updatePercentage"):
        value = update.get(key)
        if isinstance(value, int | float) and 0 <= value <= 100:
            return value
    return None
