"""Services for the UniFi Drive integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from datetime import time
from typing import Any, Mapping, NotRequired, TypeAlias, TypedDict, cast

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .api import CannotConnect, InvalidAuth, UnexpectedResponse, UnsupportedFeature
from .const import (
    ATTR_DESCRIPTION,
    ATTR_ENTRY_ID,
    ATTR_FAN_MODE,
    ATTR_LOCKED,
    ATTR_SNAPSHOT_LIMIT,
    ATTR_SNAPSHOT_MONTHDAY,
    ATTR_SNAPSHOT_SCHEDULE,
    ATTR_SNAPSHOT_SCHEDULE_TIME,
    ATTR_SNAPSHOT_TARGET_ID,
    ATTR_SNAPSHOT_TARGET_KEY,
    ATTR_SNAPSHOT_TARGET_NAME,
    ATTR_SNAPSHOT_TARGET_TYPE,
    ATTR_SNAPSHOT_WEEKDAY,
    CONF_WOL_BROADCAST_ADDRESS,
    CONF_WOL_ENABLED,
    CONF_WOL_MAC_ADDRESS,
    CONF_WOL_PORT,
    DEFAULT_WOL_BROADCAST_ADDRESS,
    DEFAULT_WOL_ENABLED,
    DEFAULT_WOL_PORT,
    DOMAIN,
    FAN_MODE_OPTIONS,
    MAX_SNAPSHOT_LIMIT,
    MIN_SNAPSHOT_LIMIT,
    SERVICE_CREATE_SNAPSHOT,
    SERVICE_REBOOT,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_SNAPSHOT_LIMIT,
    SERVICE_SET_SNAPSHOT_SCHEDULE,
    SERVICE_SHUTDOWN,
    SERVICE_WAKE_ON_LAN,
    SNAPSHOT_SCHEDULE_API_VALUES,
    SNAPSHOT_SCHEDULE_OPTIONS,
    SNAPSHOT_WEEKDAY_OPTIONS,
)
from .coordinator import UnifiUnasCoordinator
from .entry_options import entry_bool, entry_int, entry_str
from .exceptions import unifi_unas_error, unifi_unas_validation_error
from .snapshot_schedule import _schedule_time_parts
from .snapshot_repairs import (
    async_clear_snapshot_action_issues,
    async_create_snapshot_action_issue,
    async_create_snapshot_read_issue,
    async_update_snapshot_read_issue,
)
from .runtime import UnifiDriveConfigEntry, coordinator_from_entry_or_none
from .security import safe_error_text
from .snapshot_types import (
    normalize_snapshot_target_type,
    snapshot_target_key,
    snapshot_target_name,
    snapshot_target_type,
)
from . import ha_validation as vol
from .wake_on_lan import WakeOnLanError, async_send_magic_packet

ServiceHandler = Callable[[ServiceCall], Awaitable[None]]
ServiceHandlerFactory = Callable[[HomeAssistant], ServiceHandler]


JSONPrimitive: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONPrimitive | list["JSONValue"] | dict[str, "JSONValue"]
SnapshotTarget: TypeAlias = Mapping[str, JSONValue]


class SnapshotScheduleServiceUpdate(TypedDict):
    """Typed keyword arguments for snapshot schedule writes."""

    schedule_frequency: str
    schedule_time: NotRequired[str]
    schedule_weekdays: NotRequired[str]
    schedule_monthdays: NotRequired[str]


def _service_validation_error(
    message: str,
    translation_key: str,
    **placeholders: str,
) -> ServiceValidationError:
    """Return a translatable service validation error with a fallback message."""
    return unifi_unas_validation_error(message, translation_key, **placeholders)


def _service_error(
    message: str,
    translation_key: str,
    **placeholders: str,
) -> HomeAssistantError:
    """Return a translatable Home Assistant service error with a fallback message."""
    return unifi_unas_error(message, translation_key, **placeholders)


def _snapshot_limit_schema_value(value: JSONValue) -> int:
    """Validate a snapshot limit for Home Assistant service schemas."""
    try:
        return _snapshot_limit_service_value(value)
    except ServiceValidationError as err:
        raise vol.Invalid(safe_error_text(err)) from err


def _snapshot_limit_service_value(value: JSONValue) -> int:
    """Return a validated snapshot retention limit."""
    limit = _to_intish_service_value(
        value,
        whole_number_message="Snapshot limit must be a whole number",
        whole_number_key="snapshot_limit_whole_number",
    )
    if limit < MIN_SNAPSHOT_LIMIT or limit > MAX_SNAPSHOT_LIMIT:
        message = (
            f"Snapshot limit must be between {MIN_SNAPSHOT_LIMIT} and "
            f"{MAX_SNAPSHOT_LIMIT}"
        )
        raise _service_validation_error(
            message,
            "snapshot_limit_range",
            min=str(MIN_SNAPSHOT_LIMIT),
            max=str(MAX_SNAPSHOT_LIMIT),
        )
    return limit


def _to_intish_service_value(
    value: JSONValue,
    *,
    whole_number_message: str,
    whole_number_key: str,
) -> int:
    """Convert JSON-ish scalar values into a validated integer."""
    if isinstance(value, (list, dict, bool, type(None))):
        raise _service_validation_error(
            whole_number_message,
            whole_number_key,
        )
    if isinstance(value, float) and not value.is_integer():
        raise _service_validation_error(
            whole_number_message,
            whole_number_key,
        )

    try:
        return int(value)
    except (TypeError, ValueError) as err:
        raise _service_validation_error(
            whole_number_message,
            whole_number_key,
        ) from err


def _snapshot_schedule_schema_value(value: JSONValue) -> str:
    """Validate a snapshot schedule option for Home Assistant service schemas."""
    try:
        return _snapshot_schedule_service_option(value)
    except ServiceValidationError as err:
        raise vol.Invalid(safe_error_text(err)) from err


def _snapshot_schedule_service_option(value: JSONValue) -> str:
    """Return a canonical snapshot schedule option."""
    normalized = str(value).strip().lower()
    for option in SNAPSHOT_SCHEDULE_OPTIONS:
        if (
            normalized == option.lower()
            or normalized in SNAPSHOT_SCHEDULE_API_VALUES.get(option, ())
        ):
            return option
    options = ", ".join(SNAPSHOT_SCHEDULE_OPTIONS)
    raise _service_validation_error(
        f"Snapshot schedule must be one of: {options}",
        "snapshot_schedule_option",
        options=options,
    )


def _snapshot_schedule_time_schema_value(value: JSONValue) -> str:
    """Validate a snapshot schedule time for Home Assistant service schemas."""
    try:
        return _snapshot_schedule_time_service_value(value)
    except ServiceValidationError as err:
        raise vol.Invalid(safe_error_text(err)) from err


def _snapshot_schedule_time_service_value(value: JSONValue) -> str:
    """Return a normalized HH:MM schedule time."""
    if isinstance(value, time):
        return f"{value.hour:02d}:{value.minute:02d}"

    try:
        hour, minute = _schedule_time_parts(value)
    except ValueError as err:
        error = safe_error_text(err)
        raise _service_validation_error(
            f"Invalid snapshot schedule time: {error}",
            "snapshot_schedule_time",
            error=error,
        ) from err
    return f"{hour:02d}:{minute:02d}"


def _snapshot_weekday_schema_value(value: JSONValue) -> str:
    """Validate a weekly snapshot day for Home Assistant service schemas."""
    try:
        return _snapshot_weekday_service_value(value)
    except ServiceValidationError as err:
        raise vol.Invalid(safe_error_text(err)) from err


def _snapshot_weekday_service_value(value: JSONValue) -> str:
    """Return a UniFi weekday value from a label or numeric input."""
    text = str(value).strip()
    if text:
        try:
            day = int(text)
        except ValueError:
            day = None
        if day is not None and 0 <= day <= 6:
            return str(day)

    normalized = text.lower()
    for index, option in enumerate(SNAPSHOT_WEEKDAY_OPTIONS):
        if normalized == option.lower():
            return str(index)
    raise _service_validation_error(
        "Snapshot weekday must be Sunday, Monday, Tuesday, Wednesday, Thursday, "
        "Friday, Saturday, or a value from 0 to 6",
        "snapshot_weekday",
    )


def _snapshot_monthday_schema_value(value: JSONValue) -> str:
    """Validate a monthly snapshot day for Home Assistant service schemas."""
    try:
        return _snapshot_monthday_service_value(value)
    except ServiceValidationError as err:
        raise vol.Invalid(safe_error_text(err)) from err


def _snapshot_monthday_service_value(value: JSONValue) -> str:
    """Return a UniFi month-day value."""
    day = _to_intish_service_value(
        value,
        whole_number_message="Snapshot month day must be a whole number",
        whole_number_key="snapshot_monthday_whole_number",
    )

    if day < 1 or day > 31:
        raise _service_validation_error(
            "Snapshot month day must be between 1 and 31",
            "snapshot_monthday_range",
        )
    return str(day)


_SERVICE_ENTRY_SCHEMA = vol.Schema({vol.Optional(ATTR_ENTRY_ID): str})
_SERVICE_SET_FAN_MODE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): str,
        vol.Required(ATTR_FAN_MODE): vol.In(FAN_MODE_OPTIONS),
    }
)
_SNAPSHOT_TARGET_SCHEMA_FIELDS = {
    vol.Optional(ATTR_ENTRY_ID): str,
    vol.Optional(ATTR_SNAPSHOT_TARGET_KEY): str,
    vol.Optional(ATTR_SNAPSHOT_TARGET_ID): str,
    vol.Optional(ATTR_SNAPSHOT_TARGET_NAME): str,
    vol.Optional(ATTR_SNAPSHOT_TARGET_TYPE): str,
}
_SERVICE_CREATE_SNAPSHOT_SCHEMA = vol.Schema(
    {
        **_SNAPSHOT_TARGET_SCHEMA_FIELDS,
        vol.Optional(ATTR_DESCRIPTION, default=""): str,
        vol.Optional(ATTR_LOCKED, default=False): bool,
    }
)
_SERVICE_SET_SNAPSHOT_LIMIT_SCHEMA = vol.Schema(
    {
        **_SNAPSHOT_TARGET_SCHEMA_FIELDS,
        vol.Required(ATTR_SNAPSHOT_LIMIT): _snapshot_limit_schema_value,
    }
)
_SERVICE_SET_SNAPSHOT_SCHEDULE_SCHEMA = vol.Schema(
    {
        **_SNAPSHOT_TARGET_SCHEMA_FIELDS,
        vol.Required(ATTR_SNAPSHOT_SCHEDULE): _snapshot_schedule_schema_value,
        vol.Optional(ATTR_SNAPSHOT_SCHEDULE_TIME): _snapshot_schedule_time_schema_value,
        vol.Optional(ATTR_SNAPSHOT_WEEKDAY): _snapshot_weekday_schema_value,
        vol.Optional(ATTR_SNAPSHOT_MONTHDAY): _snapshot_monthday_schema_value,
    }
)


def async_register_services(hass: HomeAssistant) -> None:
    """Register integration-level services once."""
    if hass.services.has_service(DOMAIN, SERVICE_WAKE_ON_LAN):
        return

    registrations: tuple[tuple[str, ServiceHandlerFactory, vol.Schema], ...] = (
        (SERVICE_WAKE_ON_LAN, _async_service_wake_on_lan, _SERVICE_ENTRY_SCHEMA),
        (SERVICE_REBOOT, _async_service_reboot, _SERVICE_ENTRY_SCHEMA),
        (SERVICE_SHUTDOWN, _async_service_shutdown, _SERVICE_ENTRY_SCHEMA),
        (SERVICE_SET_FAN_MODE, _async_service_set_fan_mode, _SERVICE_SET_FAN_MODE_SCHEMA),
        (SERVICE_CREATE_SNAPSHOT, _async_service_create_snapshot, _SERVICE_CREATE_SNAPSHOT_SCHEMA),
        (
            SERVICE_SET_SNAPSHOT_LIMIT,
            _async_service_set_snapshot_limit,
            _SERVICE_SET_SNAPSHOT_LIMIT_SCHEMA,
        ),
        (
            SERVICE_SET_SNAPSHOT_SCHEDULE,
            _async_service_set_snapshot_schedule,
            _SERVICE_SET_SNAPSHOT_SCHEDULE_SCHEMA,
        ),
    )

    for service, handler, schema in registrations:
        hass.services.async_register(DOMAIN, service, handler(hass), schema=schema)


def _async_service_wake_on_lan(hass: HomeAssistant) -> ServiceHandler:
    async def _handler(call: ServiceCall) -> None:
        entry, _ = _resolve_entry_and_coordinator(
            hass,
            cast(str | None, call.data.get(ATTR_ENTRY_ID)),
        )
        if not entry_bool(entry, CONF_WOL_ENABLED, DEFAULT_WOL_ENABLED):
            raise _service_validation_error(
                "Wake-on-LAN is disabled for this UniFi Drive entry",
                "wake_on_lan_disabled",
            )

        mac_address = entry_str(entry, CONF_WOL_MAC_ADDRESS).strip()
        if not mac_address:
            raise _service_validation_error(
                "Wake-on-LAN MAC address is missing for this UniFi Drive entry",
                "wake_on_lan_mac_missing",
            )

        broadcast_address = entry_str(
            entry,
            CONF_WOL_BROADCAST_ADDRESS,
            DEFAULT_WOL_BROADCAST_ADDRESS,
        )
        broadcast_port = entry_int(entry, CONF_WOL_PORT, DEFAULT_WOL_PORT)

        try:
            await async_send_magic_packet(
                mac_address,
                broadcast_address=broadcast_address,
                port=broadcast_port,
            )
        except (ValueError, WakeOnLanError) as err:
            error = safe_error_text(err)
            raise _service_error(
                f"Could not send Wake-on-LAN packet to UniFi Drive: {error}",
                "wake_on_lan_send_failed",
                error=error,
            ) from err

    return _handler


def _async_service_reboot(hass: HomeAssistant) -> ServiceHandler:
    async def _handler(call: ServiceCall) -> None:
        _, coordinator = _resolve_entry_and_coordinator(
            hass,
            cast(str | None, call.data.get(ATTR_ENTRY_ID)),
        )
        await _async_call_client_action(
            coordinator,
            action_name="restart",
            action=coordinator.client.async_reboot,
        )

    return _handler


def _async_service_shutdown(hass: HomeAssistant) -> ServiceHandler:
    async def _handler(call: ServiceCall) -> None:
        _, coordinator = _resolve_entry_and_coordinator(
            hass,
            cast(str | None, call.data.get(ATTR_ENTRY_ID)),
        )
        await _async_call_client_action(
            coordinator,
            action_name="shut down",
            action=coordinator.client.async_poweroff,
        )

    return _handler


def _async_service_set_fan_mode(hass: HomeAssistant) -> ServiceHandler:
    async def _handler(call: ServiceCall) -> None:
        _, coordinator = _resolve_entry_and_coordinator(
            hass,
            cast(str | None, call.data.get(ATTR_ENTRY_ID)),
        )
        _raise_if_device_offline(coordinator, "set fan mode")
        option = str(call.data[ATTR_FAN_MODE])
        try:
            mode = await coordinator.client.async_set_fan_mode(option)
        except InvalidAuth as err:
            raise _service_error(
                "The configured UniFi account/API key cannot change the native "
                "UniFi Drive fan mode",
                "fan_mode_permission",
            ) from err
        except UnsupportedFeature as err:
            error = safe_error_text(err)
            raise _service_error(
                "Could not change native UniFi Drive fan mode with the currently "
                f"known local Drive endpoints: {error}",
                "fan_mode_unsupported",
                error=error,
            ) from err
        except (CannotConnect, UnexpectedResponse) as err:
            error = safe_error_text(err)
            raise _service_error(
                f"Could not change native UniFi Drive fan mode: {error}",
                "fan_mode_failed",
                error=error,
            ) from err

        coordinator.fan_mode = mode if mode in FAN_MODE_OPTIONS else option
        await coordinator.async_request_refresh()

    return _handler


def _async_service_create_snapshot(hass: HomeAssistant) -> ServiceHandler:
    async def _handler(call: ServiceCall) -> None:
        _, coordinator = _resolve_entry_and_coordinator(
            hass,
            cast(str | None, call.data.get(ATTR_ENTRY_ID)),
        )
        target = await _async_snapshot_target_from_call(
            coordinator,
            call.data,
            action_name="create a snapshot",
        )
        description = str(call.data.get(ATTR_DESCRIPTION, ""))
        locked = bool(call.data.get(ATTR_LOCKED, False))
        await _async_call_snapshot_action(
            coordinator,
            target,
            action_name="create snapshot",
            action=lambda: coordinator.client.async_create_snapshot_target(
                target,
                description=description,
                locked=locked,
            ),
        )

    return _handler


def _async_service_set_snapshot_limit(hass: HomeAssistant) -> ServiceHandler:
    async def _handler(call: ServiceCall) -> None:
        _, coordinator = _resolve_entry_and_coordinator(
            hass,
            cast(str | None, call.data.get(ATTR_ENTRY_ID)),
        )
        target = await _async_snapshot_target_from_call(
            coordinator,
            call.data,
            action_name="set snapshot limit",
        )
        limit = _snapshot_limit_service_value(call.data[ATTR_SNAPSHOT_LIMIT])
        await _async_call_snapshot_action(
            coordinator,
            target,
            action_name="change snapshot limit",
            action=lambda: coordinator.client.async_update_snapshot_target_settings(
                target,
                max_count=limit,
            ),
        )

    return _handler


def _async_service_set_snapshot_schedule(hass: HomeAssistant) -> ServiceHandler:
    async def _handler(call: ServiceCall) -> None:
        _, coordinator = _resolve_entry_and_coordinator(
            hass,
            call.data.get(ATTR_ENTRY_ID),
        )
        target = await _async_snapshot_target_from_call(
            coordinator,
            call.data,
            action_name="set snapshot schedule",
        )
        update = _snapshot_schedule_update_from_call_data(call.data)
        await _async_call_snapshot_action(
            coordinator,
            target,
            action_name="change snapshot schedule",
            action=lambda: coordinator.client.async_update_snapshot_target_settings(
                target,
                **update,
            ),
        )

    return _handler


def _resolve_entry_and_coordinator(
    hass: HomeAssistant,
    entry_id: str | None,
) -> tuple[UnifiDriveConfigEntry, UnifiUnasCoordinator]:
    """Resolve a target config entry and loaded coordinator for a service call."""
    domain_data = cast(
        Mapping[str, UnifiUnasCoordinator],
        hass.data.get(DOMAIN, {}),
    )

    if entry_id:
        entry_id_str = str(entry_id)
        entry = hass.config_entries.async_get_entry(entry_id_str)
        if entry is None or entry.domain != DOMAIN:
            raise _service_validation_error(
                f"Config entry '{entry_id_str}' was not found for {DOMAIN}",
                "config_entry_not_found",
                entry_id=entry_id_str,
            )

        coordinator = coordinator_from_entry_or_none(entry) or domain_data.get(
            entry_id_str
        )
        if not isinstance(coordinator, UnifiUnasCoordinator):
            raise _service_validation_error(
                f"Config entry '{entry_id_str}' for {DOMAIN} is not loaded",
                "config_entry_not_loaded",
                entry_id=entry_id_str,
            )
        return entry, coordinator

    async_entries = getattr(hass.config_entries, "async_entries", None)
    entries = async_entries(DOMAIN) if callable(async_entries) else ()
    loaded_entries = [
        entry
        for entry in entries
        if coordinator_from_entry_or_none(entry) is not None
        or isinstance(domain_data.get(entry.entry_id), UnifiUnasCoordinator)
    ]

    if not loaded_entries:
        if len(domain_data) == 1:
            only_id, coordinator = next(iter(domain_data.items()))
            entry = hass.config_entries.async_get_entry(only_id)
            if entry is not None and isinstance(coordinator, UnifiUnasCoordinator):
                return entry, coordinator
        raise _service_validation_error(
            f"No loaded {DOMAIN} config entries available",
            "no_loaded_entries",
        )

    if len(loaded_entries) > 1:
        raise _service_validation_error(
            f"Multiple {DOMAIN} entries are loaded. Pass '{ATTR_ENTRY_ID}' to "
            "target one.",
            "multiple_loaded_entries",
        )

    entry = loaded_entries[0]
    coordinator = coordinator_from_entry_or_none(entry) or domain_data[entry.entry_id]
    return entry, coordinator


def _raise_if_device_offline(
    coordinator: UnifiUnasCoordinator,
    action_name: str,
) -> None:
    """Raise a validation error when a write action is attempted offline."""
    if not coordinator.is_device_online:
        raise _service_validation_error(
            f"Cannot {action_name} while UniFi Drive is offline",
            "device_offline",
            action=action_name,
        )


async def _async_call_client_action(
    coordinator: UnifiUnasCoordinator,
    *,
    action_name: str,
    action: Callable[[], Awaitable[None]],
) -> None:
    """Run a client power action and translate exceptions for service calls."""
    _raise_if_device_offline(coordinator, action_name)

    try:
        await action()
    except InvalidAuth as err:
        raise _service_error(
            "The configured UniFi account/API key cannot perform this system action",
            "system_action_permission",
        ) from err
    except (CannotConnect, UnexpectedResponse, UnsupportedFeature) as err:
        error = safe_error_text(err)
        raise _service_error(
            f"Could not {action_name} UniFi Drive: {error}",
            "system_action_failed",
            action=action_name,
            error=error,
        ) from err


async def _async_snapshot_target_from_call(
    coordinator: UnifiUnasCoordinator,
    data: Mapping[str, JSONValue],
    *,
    action_name: str,
) -> dict[str, Any]:
    """Resolve the snapshot target addressed by a service call."""
    _raise_if_device_offline(coordinator, action_name)
    targets = await _async_snapshot_targets_for_service(coordinator)
    return _snapshot_target_from_call_data(targets, data)


async def _async_snapshot_targets_for_service(
    coordinator: UnifiUnasCoordinator,
) -> list[dict[str, Any]]:
    """Return cached snapshot targets or fetch them on demand for services."""
    cached_targets = getattr(coordinator, "snapshot_settings", None)
    if cached_targets:
        return list(cached_targets)

    try:
        targets = await coordinator.client.async_get_snapshot_settings()
    except InvalidAuth as err:
        _create_snapshot_read_issue_for_coordinator(coordinator, err)
        raise _service_error(
            "The configured UniFi account/API key cannot read snapshot targets",
            "snapshot_targets_permission",
        ) from err
    except (CannotConnect, UnexpectedResponse, UnsupportedFeature) as err:
        if isinstance(err, UnsupportedFeature):
            _create_snapshot_read_issue_for_coordinator(coordinator, err)
        error = safe_error_text(err)
        raise _service_error(
            f"Could not read UniFi Drive snapshot targets: {error}",
            "snapshot_targets_read_failed",
            error=error,
        ) from err

    coordinator.snapshot_settings = list(targets or [])
    _update_snapshot_read_issue_for_coordinator(coordinator)
    return list(coordinator.snapshot_settings)


def _snapshot_target_from_call_data(
    targets: Sequence[SnapshotTarget],
    data: Mapping[str, JSONValue],
) -> dict[str, Any]:
    """Return the single snapshot target matching service-call target fields."""
    candidates = [target for target in targets if isinstance(target, dict)]
    if not candidates:
        raise _service_validation_error(
            "No snapshot targets are available for this UniFi Drive entry",
            "snapshot_targets_empty",
        )

    filters = _snapshot_target_filters(data)
    if not filters:
        if len(candidates) == 1:
            return candidates[0]
        raise _service_validation_error(
            "Multiple snapshot targets are available. Pass target_key, target_id, "
            "target_name, or target_type to select one.",
            "snapshot_targets_ambiguous",
        )

    matches = [
        target
        for target in candidates
        if _snapshot_target_matches_filters(target, filters)
    ]
    if not matches:
        raise _service_validation_error(
            "No snapshot target matches the provided target fields",
            "snapshot_target_no_match",
        )
    if len(matches) > 1:
        raise _service_validation_error(
            "Multiple snapshot targets match the provided target fields. Add "
            "target_key or target_id to select one.",
            "snapshot_target_multiple_matches",
        )
    return matches[0]


def _snapshot_target_filters(data: Mapping[str, JSONValue]) -> dict[str, str]:
    """Return non-empty target filters from service-call data."""
    filters: dict[str, str] = {}
    for key in (
        ATTR_SNAPSHOT_TARGET_KEY,
        ATTR_SNAPSHOT_TARGET_ID,
        ATTR_SNAPSHOT_TARGET_NAME,
    ):
        value = _normalized_filter_value(data.get(key))
        if value:
            filters[key] = value

    target_type = _normalized_filter_value(data.get(ATTR_SNAPSHOT_TARGET_TYPE))
    if target_type:
        normalized_type = normalize_snapshot_target_type(target_type)
        if normalized_type not in {"shared", "mydrive"}:
            raise _service_validation_error(
                "Snapshot target_type must be 'shared' or 'mydrive'",
                "snapshot_target_type",
            )
        filters[ATTR_SNAPSHOT_TARGET_TYPE] = normalized_type
    return filters


def _snapshot_target_matches_filters(
    target: SnapshotTarget,
    filters: dict[str, str],
) -> bool:
    """Return whether a target matches all requested service-call filters."""
    target_key = filters.get(ATTR_SNAPSHOT_TARGET_KEY)
    if (
        target_key
        and _normalized_filter_value(snapshot_target_key(target)) != target_key
    ):
        return False

    target_id = filters.get(ATTR_SNAPSHOT_TARGET_ID)
    if target_id and target_id not in {
        _normalized_filter_value(value)
        for value in _snapshot_target_identity_values(target)
    }:
        return False

    target_name = filters.get(ATTR_SNAPSHOT_TARGET_NAME)
    if target_name and target_name not in {
        _normalized_filter_value(value)
        for value in _snapshot_target_name_values(target)
    }:
        return False

    target_type = filters.get(ATTR_SNAPSHOT_TARGET_TYPE)
    return not (target_type and snapshot_target_type(target) != target_type)


def _snapshot_target_identity_values(target: SnapshotTarget) -> tuple[JSONValue | None, ...]:
    """Return target identifiers accepted by service calls."""
    return (
        target.get("id"),
        target.get("user_id"),
        target.get("shared_drive_id"),
    )


def _snapshot_target_name_values(target: SnapshotTarget) -> tuple[JSONValue | None, ...]:
    """Return target names accepted by service calls."""
    return (
        target.get("name"),
        target.get("shared_drive_name"),
        snapshot_target_name(target),
    )


def _normalized_filter_value(value: object) -> str:
    """Return a normalized service target filter value."""
    return str(value or "").strip().lower()


def _snapshot_schedule_update_from_call_data(
    data: Mapping[str, JSONValue],
) -> SnapshotScheduleServiceUpdate:
    """Return API update fields for a snapshot schedule service call."""
    update: SnapshotScheduleServiceUpdate = {
        "schedule_frequency": _snapshot_schedule_service_option(
            data[ATTR_SNAPSHOT_SCHEDULE]
        )
    }
    if ATTR_SNAPSHOT_SCHEDULE_TIME in data:
        update["schedule_time"] = _snapshot_schedule_time_service_value(
            data[ATTR_SNAPSHOT_SCHEDULE_TIME]
        )
    if ATTR_SNAPSHOT_WEEKDAY in data:
        update["schedule_weekdays"] = _snapshot_weekday_service_value(
            data[ATTR_SNAPSHOT_WEEKDAY]
        )
    if ATTR_SNAPSHOT_MONTHDAY in data:
        update["schedule_monthdays"] = _snapshot_monthday_service_value(
            data[ATTR_SNAPSHOT_MONTHDAY]
        )
    return update


async def _async_call_snapshot_action(
    coordinator: UnifiUnasCoordinator,
    target: dict[str, Any],
    *,
    action_name: str,
    action: Callable[[], Awaitable[None]],
) -> None:
    """Run a snapshot action and translate API exceptions for service calls."""
    _raise_if_device_offline(coordinator, action_name)
    target_name = snapshot_target_name(target)
    repair_action = _snapshot_repair_action(action_name)
    try:
        await action()
    except InvalidAuth as err:
        _create_snapshot_action_issue_for_coordinator(
            coordinator,
            action=repair_action,
            target=target,
            err=err,
        )
        permission_action = (
            "create snapshots"
            if repair_action == "create"
            else "change snapshot settings"
        )
        raise _service_error(
            f"The configured UniFi account/API key cannot {permission_action}",
            "snapshot_action_permission",
            permission_action=permission_action,
        ) from err
    except UnsupportedFeature as err:
        _create_snapshot_action_issue_for_coordinator(
            coordinator,
            action=repair_action,
            target=target,
            err=err,
        )
        error = safe_error_text(err)
        raise _service_error(
            f"Could not {action_name} for snapshot target '{target_name}' with the "
            f"currently known local Drive endpoints: {error}",
            "snapshot_action_unsupported",
            action=action_name,
            target_name=target_name,
            error=error,
        ) from err
    except (CannotConnect, UnexpectedResponse) as err:
        error = safe_error_text(err)
        raise _service_error(
            f"Could not {action_name} for snapshot target '{target_name}': {error}",
            "snapshot_action_failed",
            action=action_name,
            target_name=target_name,
            error=error,
        ) from err

    _clear_snapshot_action_issues_for_coordinator(
        coordinator,
        action=repair_action,
        target=target,
    )
    coordinator.request_snapshot_inventory_refresh()
    await coordinator.async_request_refresh()


def _snapshot_repair_action(action_name: str) -> str:
    """Return the repairs action bucket for a service action name."""
    return "create" if "create" in action_name else "settings"


def _create_snapshot_read_issue_for_coordinator(
    coordinator: UnifiUnasCoordinator,
    err: Exception,
) -> None:
    """Create a snapshot-read repairs issue when coordinator context is present."""
    entry = getattr(coordinator, "config_entry", None)
    if entry is not None:
        async_create_snapshot_read_issue(getattr(coordinator, "hass", None), entry, err)


def _update_snapshot_read_issue_for_coordinator(
    coordinator: UnifiUnasCoordinator,
) -> None:
    """Update snapshot-read repairs state when coordinator context is present."""
    entry = getattr(coordinator, "config_entry", None)
    if entry is not None:
        async_update_snapshot_read_issue(
            getattr(coordinator, "hass", None),
            entry,
            supported=getattr(
                coordinator.client,
                "snapshot_settings_read_supported",
                None,
            ),
        )


def _create_snapshot_action_issue_for_coordinator(
    coordinator: UnifiUnasCoordinator,
    *,
    action: str,
    target: dict[str, Any],
    err: Exception,
) -> None:
    """Create a snapshot-action repairs issue when coordinator context is present."""
    entry = getattr(coordinator, "config_entry", None)
    if entry is not None:
        async_create_snapshot_action_issue(
            getattr(coordinator, "hass", None),
            entry,
            action=action,
            target=target,
            err=err,
        )


def _clear_snapshot_action_issues_for_coordinator(
    coordinator: UnifiUnasCoordinator,
    *,
    action: str,
    target: dict[str, Any],
) -> None:
    """Clear snapshot-action repairs issues when coordinator context is present."""
    entry = getattr(coordinator, "config_entry", None)
    if entry is not None:
        async_clear_snapshot_action_issues(
            getattr(coordinator, "hass", None),
            entry,
            action=action,
            target=target,
        )
