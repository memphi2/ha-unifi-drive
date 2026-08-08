"""The UniFi Drive integration."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
import logging
from typing import cast

import aiohttp

from homeassistant.const import (
    CONF_API_KEY,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SSL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.typing import ConfigType

from .api import UnifiUnasApiClient
from .const import (
    CONF_DISCOVERY_CONFIDENCE,
    CONF_DISCOVERY_HOST_ALIASES,
    CONF_DISCOVERY_IDENTITY_SOURCE,
    CONF_DISCOVERY_MAC_ADDRESS,
    CONF_WOL_ENABLED,
    CONF_WOL_MAC_ADDRESS,
    DEFAULT_PORT,
    DEFAULT_SSL,
    DEFAULT_VERIFY_SSL,
    DEFAULT_WOL_ENABLED,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import UnifiUnasCoordinator
from .discovery import feature_defaults_from_system_payload
from .discovery_identity import (
    apply_discovery_identity_defaults,
    discovery_mac_key,
    entry_matches_discovery_flow_context,
    should_write_discovery_identity_update,
)
from .device import build_device_info
from .entry_options import (
    entry_bool,
    entry_value,
)
from .entry_reload import entry_reload_signature
from .runtime import UnifiDriveConfigEntry, coordinator_from_entry_or_none
from .services import async_register_services
from .snapshot_types import (
    snapshot_create_button_supported_for_inventory,
    snapshot_target_key,
    snapshot_target_slug,
)

# Import platform modules at module import time so Home Assistant does not need
# to import them for the first time during config-entry setup.
from . import binary_sensor as _binary_sensor
from . import button as _button
from . import number as _number
from . import select as _select
from . import sensor as _sensor
from . import switch as _switch
from . import time as _time

_LOGGER = logging.getLogger(__name__)
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
_DISCOVERY_FLOW_CLEANUP_DELAYS = (5, 15, 30)
_DISCOVERY_METADATA_WRITE_INTERVAL_SECONDS = 5 * 60


async def async_setup(hass: HomeAssistant, _config: ConfigType) -> bool:
    """Set up the UniFi Drive integration."""
    async_register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: UnifiDriveConfigEntry) -> bool:
    """Set up UniFi Drive from a config entry."""
    _async_backfill_discovery_mac(
        hass,
        entry,
        entry_value(entry, CONF_WOL_MAC_ADDRESS, ""),
    )
    _async_abort_matching_discovery_flows(hass, entry)

    host = str(entry.data.get(CONF_HOST, "")).strip()
    if not host:
        raise ConfigEntryError(
            "UniFi Drive config entry is missing a host; reconfigure the integration"
        )

    verify_ssl = bool(entry.data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL))
    session = async_create_clientsession(
        hass,
        verify_ssl=verify_ssl,
        cookie_jar=aiohttp.CookieJar(unsafe=True),
    )

    client = UnifiUnasApiClient(
        session,
        host=host,
        username=entry.data.get(CONF_USERNAME, ""),
        password=entry.data.get(CONF_PASSWORD, ""),
        api_key=entry.data.get(CONF_API_KEY),
        port=_entry_data_int(entry, CONF_PORT, DEFAULT_PORT),
        use_ssl=bool(entry.data.get(CONF_SSL, DEFAULT_SSL)),
        verify_ssl=verify_ssl,
    )
    coordinator = UnifiUnasCoordinator(hass, client, entry)

    wol_enabled = entry_bool(entry, CONF_WOL_ENABLED, DEFAULT_WOL_ENABLED)
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        if not wol_enabled:
            raise
        _LOGGER.debug(
            "Initial UniFi Drive poll failed, but Wake-on-LAN is configured; "
            "continuing so the Start button remains available"
        )

    storage = coordinator.data if isinstance(coordinator.data, dict) else {}
    system_defaults = feature_defaults_from_system_payload(storage.get("_system"))
    _async_backfill_discovery_mac(
        hass,
        entry,
        system_defaults.get(CONF_WOL_MAC_ADDRESS),
    )
    _async_record_validated_discovery_identity(hass, entry, system_defaults)
    entry.runtime_data = coordinator
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    coordinator.entry_reload_signature = entry_reload_signature(entry)
    remove_update_listener = entry.add_update_listener(_async_config_entry_updated)
    remove_snapshot_cleanup_listener: Callable[[], None] | None = None
    remove_device_registry_listener: Callable[[], None] | None = None
    try:
        remove_snapshot_cleanup_listener = (
            _async_track_unsupported_snapshot_create_button_cleanup(
                hass,
                entry,
                coordinator,
                register_unload=False,
            )
        )
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        remove_device_registry_listener = (
            _async_track_device_registry_metadata_updates(hass, entry, coordinator)
        )
        entry.async_create_background_task(
            hass,
            coordinator.async_refresh_optional_features(),
            f"{DOMAIN} optional feature startup refresh",
        )
    except Exception:
        remove_update_listener()
        if remove_snapshot_cleanup_listener is not None:
            remove_snapshot_cleanup_listener()
        if remove_device_registry_listener is not None:
            remove_device_registry_listener()
        _async_clear_entry_runtime(hass, entry)
        raise

    entry.async_on_unload(remove_update_listener)
    if remove_snapshot_cleanup_listener is not None:
        entry.async_on_unload(remove_snapshot_cleanup_listener)
    if remove_device_registry_listener is not None:
        entry.async_on_unload(remove_device_registry_listener)
    _async_schedule_discovery_flow_cleanup(hass, entry)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: UnifiDriveConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        from .snapshot_entities import _clear_snapshot_target_entities_for_coordinator

        coordinator = coordinator_from_entry_or_none(entry) or hass.data.get(
            DOMAIN, {}
        ).get(entry.entry_id)
        if coordinator is not None:
            _clear_snapshot_target_entities_for_coordinator(coordinator)
        _async_clear_entry_runtime(hass, entry)
    return cast(bool, unload_ok)


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    entry: UnifiDriveConfigEntry,
    device_entry: dr.DeviceEntry,
) -> bool:
    """Allow Home Assistant to remove stale device-registry entries."""
    device_identifier = getattr(entry, "unique_id", None) or getattr(
        entry, "entry_id", ""
    )
    return (DOMAIN, device_identifier) not in device_entry.identifiers


def _async_clear_entry_runtime(hass: HomeAssistant, entry: UnifiDriveConfigEntry) -> None:
    """Remove config-entry runtime mirrors after unload or setup failure."""
    entry.runtime_data = None
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)


def _entry_data_int(
    entry: UnifiDriveConfigEntry,
    key: str,
    default: int,
) -> int:
    """Read an integer value from entry data without trusting stored JSON."""
    try:
        return int(entry.data.get(key, default))
    except (TypeError, ValueError):
        _LOGGER.warning(
            "Invalid UniFi Drive config entry value for %s; using the default",
            key,
        )
        return default


async def _async_config_entry_updated(
    hass: HomeAssistant,
    entry: UnifiDriveConfigEntry,
) -> None:
    """Reload the config entry after options or data changes."""
    coordinator = coordinator_from_entry_or_none(entry) or hass.data.get(
        DOMAIN, {}
    ).get(entry.entry_id)
    signature = entry_reload_signature(entry)
    if (
        coordinator is not None
        and getattr(coordinator, "entry_reload_signature", None) == signature
    ):
        coordinator.entry_reload_signature = signature
        _LOGGER.debug(
            "Skipped UniFi Drive reload for discovery metadata-only entry update"
        )
        return

    if coordinator is not None:
        coordinator.entry_reload_signature = signature
    await hass.config_entries.async_reload(entry.entry_id)


def _async_backfill_discovery_mac(
    hass: HomeAssistant,
    entry: UnifiDriveConfigEntry,
    *candidates: object,
) -> bool:
    """Persist a stable discovery MAC for existing config entries."""
    if discovery_mac_key(entry.data.get(CONF_DISCOVERY_MAC_ADDRESS)):
        return False

    for candidate in candidates:
        if mac_address := discovery_mac_key(candidate):
            data = dict(entry.data)
            data[CONF_DISCOVERY_MAC_ADDRESS] = mac_address
            hass.config_entries.async_update_entry(entry, data=data)
            _LOGGER.debug(
                "Backfilled UniFi Drive discovery MAC identity for config entry"
            )
            return True
    return False


def _async_record_validated_discovery_identity(
    hass: HomeAssistant,
    entry: UnifiDriveConfigEntry,
    system_defaults: dict[str, object],
) -> bool:
    """Persist refreshed identity metadata after a validated API poll."""
    if not system_defaults:
        return False

    existing_defaults = {
        CONF_DISCOVERY_HOST_ALIASES: entry.data.get(CONF_DISCOVERY_HOST_ALIASES),
        CONF_DISCOVERY_IDENTITY_SOURCE: "validated_system",
        CONF_DISCOVERY_CONFIDENCE: 85,
    }
    data = apply_discovery_identity_defaults(
        dict(entry.data),
        {
            "feature_defaults": system_defaults,
            "host": entry.data.get(CONF_HOST),
        },
        existing_defaults,
    )
    if not should_write_discovery_identity_update(
        existing=entry.data,
        incoming=data,
        now=datetime.now(UTC),
        update_interval=timedelta(seconds=_DISCOVERY_METADATA_WRITE_INTERVAL_SECONDS),
    ):
        return False

    hass.config_entries.async_update_entry(entry, data=data)
    _LOGGER.debug(
        "Updated UniFi Drive discovery identity metadata from validated system data"
    )
    return True


def _async_abort_matching_discovery_flows(
    hass: HomeAssistant,
    entry: UnifiDriveConfigEntry,
) -> None:
    """Abort pending zeroconf flows that match an existing config entry."""
    flow_manager = hass.config_entries.flow
    for progress in flow_manager.async_progress_by_handler(DOMAIN):
        context = progress.get("context")
        flow_id = progress.get("flow_id")
        if (
            isinstance(context, dict)
            and isinstance(flow_id, str)
            and context.get("dismiss_protected") is not True
            and entry_matches_discovery_flow_context(entry, context)
        ):
            flow_manager.async_abort(flow_id)
            _LOGGER.debug(
                "Aborted duplicate UniFi Drive discovery flow for existing entry"
            )


def _async_schedule_discovery_flow_cleanup(
    hass: HomeAssistant,
    entry: UnifiDriveConfigEntry,
) -> None:
    """Clean matching discovery flows now and shortly after startup discovery."""
    _async_abort_matching_discovery_flows(hass, entry)

    for delay in _DISCOVERY_FLOW_CLEANUP_DELAYS:

        def _cleanup(
            _now: object,
            *,
            config_entry: UnifiDriveConfigEntry = entry,
        ) -> None:
            _async_abort_matching_discovery_flows(hass, config_entry)

        entry.async_on_unload(async_call_later(hass, delay, _cleanup))


def _async_track_device_registry_metadata_updates(
    hass: HomeAssistant,
    entry: UnifiDriveConfigEntry,
    coordinator: UnifiUnasCoordinator,
) -> Callable[[], None]:
    """Keep HA device registry firmware metadata aligned after updates."""

    def _sync_metadata() -> None:
        _async_sync_device_registry_metadata(hass, entry, coordinator)

    _sync_metadata()
    return cast(Callable[[], None], coordinator.async_add_listener(_sync_metadata))


def _async_get_device_registry_entry(
    device_registry: dr.DeviceRegistry,
    entry: UnifiDriveConfigEntry,
    device_identifier: str,
) -> dr.DeviceEntry | None:
    """Return this config entry's device registry entry."""
    async_get_device_by_identifier = getattr(
        device_registry,
        "async_get_device_by_identifier",
        None,
    )
    if async_get_device_by_identifier is not None:
        return cast(
            dr.DeviceEntry | None,
            async_get_device_by_identifier((DOMAIN, device_identifier), entry.entry_id),
        )

    return device_registry.async_get_device(identifiers={(DOMAIN, device_identifier)})


def _async_sync_device_registry_metadata(
    hass: HomeAssistant,
    entry: UnifiDriveConfigEntry,
    coordinator: UnifiUnasCoordinator,
) -> bool:
    """Update device registry metadata that can change after firmware updates."""
    device_identifier = entry.unique_id or entry.entry_id
    device_registry = dr.async_get(hass)
    device_entry = _async_get_device_registry_entry(
        device_registry,
        entry,
        device_identifier,
    )
    if device_entry is None:
        return False

    device_info = build_device_info(coordinator, entry, device_identifier)
    updates: dict[str, object] = {}
    for key in ("manufacturer", "model", "sw_version", "configuration_url"):
        value = device_info.get(key)
        if value and getattr(device_entry, key) != value:
            updates[key] = value

    if not updates:
        return False

    device_registry.async_update_device(device_entry.id, **updates)
    return True


def _async_track_unsupported_snapshot_create_button_cleanup(
    hass: HomeAssistant,
    entry: UnifiDriveConfigEntry,
    coordinator: UnifiUnasCoordinator,
    *,
    register_unload: bool = True,
) -> Callable[[], None] | None:
    """Remove stale create buttons now and after delayed snapshot discovery."""

    def _remove_unsupported_snapshot_create_buttons() -> None:
        _async_remove_unsupported_snapshot_create_buttons(hass, entry, coordinator)

    _remove_unsupported_snapshot_create_buttons()
    unsubscribe = coordinator.async_add_listener(
        _remove_unsupported_snapshot_create_buttons
    )
    if register_unload and unsubscribe is not None:
        entry.async_on_unload(unsubscribe)
    return cast(Callable[[], None] | None, unsubscribe)


def _async_remove_unsupported_snapshot_create_buttons(
    hass: HomeAssistant,
    entry: UnifiDriveConfigEntry,
    coordinator: UnifiUnasCoordinator,
) -> None:
    """Remove stale snapshot create buttons for targets that cannot use them."""
    targets = [
        target
        for target in coordinator.snapshot_settings
        if isinstance(target, dict)
    ]
    if not targets:
        return

    device_identifier = entry.unique_id or entry.entry_id
    snapshot_inventory = getattr(coordinator, "snapshot_inventory", {}) or {}
    snapshot_inventory_errors = (
        getattr(coordinator, "snapshot_inventory_errors", {}) or {}
    )
    unsupported_unique_ids: set[str] = set()
    for target in targets:
        target_key = snapshot_target_key(target)
        if not target_key or snapshot_create_button_supported_for_inventory(
            target,
            snapshot_inventory=snapshot_inventory,
            snapshot_inventory_errors=snapshot_inventory_errors,
        ):
            continue
        unsupported_unique_ids.add(
            f"{device_identifier}_snapshot_{snapshot_target_slug(target_key)}"
        )

    if not unsupported_unique_ids:
        return

    entity_registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(entity_registry, entry.entry_id)

    removed = 0
    for entity_entry in entries:
        if not entity_entry.entity_id.startswith("button."):
            continue
        if entity_entry.unique_id in unsupported_unique_ids:
            entity_registry.async_remove(entity_entry.entity_id)
            removed += 1

    if removed:
        _LOGGER.info(
            "Removed %s unsupported UniFi Drive snapshot create buttons",
            removed,
        )
