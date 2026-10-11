"""Config flow for the UniFi Drive integration."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from collections.abc import Mapping
from dataclasses import dataclass
import logging
from typing import Any, TypeAlias

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import (
    CONF_API_KEY,
    CONF_PASSWORD,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant

from .api import CannotConnect
from .config_flow_identity import (
    _any_unique_id_configured,
    _entry_info,
    _entry_matches_validated_device,
    _entry_unique_id_matches,
    _feature_reconfigure_would_reload_offline_without_wol,
)
from .config_flow_schema import (
    FlowInputError,
    _connection_schema,
    _connection_schema_fields as _connection_schema_fields_impl,
    _feature_schema_fields as _feature_schema_fields_impl,
    _feature_schema,
    _merge_feature_defaults,
    _merged_reauth_data,
    _merged_reconfigure_data,
    _normalize_user_input as _normalize_user_input_impl,
    _normalize_host_input as _normalize_host_input_impl,
)
from .config_flow_validation import (
    FlowValidator,
    async_validate_for_form,
    async_validate_input,
)
from .const import (
    CONF_DISCOVERY_CONFIDENCE,
    CONF_DISCOVERY_DEBUG,
    CONF_DISCOVERY_IDENTITY_CONFLICTS,
    CONF_DISCOVERY_IDENTITY_SOURCE,
    CONF_WOL_ENABLED,
    CONF_WOL_MAC_ADDRESS,
    DOMAIN,
)
from .discovery import (
    CONF_DISCOVERED_DEVICE,
    MANUAL_DISCOVERY_VALUE,
    DiscoveredUnasDevice,
    async_discover_unas_devices,
    connection_defaults_from_discovery,
    discovery_options,
    discovered_unas_device_from_zeroconf,
    feature_defaults_from_discovery,
)
from .discovery_identity import (
    apply_discovery_identity_defaults as _apply_discovery_identity_defaults,
    discovery_observation_entry_data as _discovery_observation_entry_data,
    discovered_device_host_keys as _discovered_device_host_keys,
    entry_discovery_host_keys as _entry_discovery_host_keys,
    discovery_flow_context_from_device as _discovery_flow_context_from_device,
    discovery_identity_defaults_from_device as _discovery_identity_defaults_from_device,
    discovery_mac_key as _discovery_mac_key,
    should_write_discovery_identity_update as _should_write_discovery_identity_update,
    entry_discovery_mac_keys as _entry_discovery_mac_keys,
    zeroconf_discovery_unique_id as _zeroconf_discovery_unique_id,
)
from .entry_options import (
    data_without_feature_options,
    entry_data_from_data,
    feature_options_from_data,
    feature_options_from_entry,
    merged_entry_data_options,
    merged_entry_data_with_connection_updates,
    merged_feature_options,
)
from . import ha_validation as vol
from .runtime import UnifiDriveConfigEntry
from .wake_on_lan import normalize_mac_address, validate_ipv4_address
from .security import safe_error_text

_LOGGER = logging.getLogger(__name__)
_DISCOVERY_METADATA_WRITE_INTERVAL_SECONDS = 5 * 60


FlowFormInput: TypeAlias = dict[str, object]


@dataclass(slots=True)
class _FlowState:
    """Internal state carried between multi-step config-flow forms."""

    data: FlowFormInput
    info: Mapping[str, object] | None = None


class UnifiUnasOptionsFlow(config_entries.OptionsFlow):  # type: ignore[misc]
    """Handle option updates for UniFi Drive runtime feature settings."""

    def __init__(self, entry: UnifiDriveConfigEntry) -> None:
        """Initialize the options flow."""
        self._entry = entry

    async def async_step_init(
        self, user_input: FlowFormInput | None = None
    ) -> ConfigFlowResult:
        """Handle optional feature settings."""
        errors: dict[str, str] = {}
        current = merged_entry_data_options(self._entry)

        if user_input is not None:
            try:
                data = _normalize_user_input(
                    _merged_reconfigure_data(current, user_input)
                )
            except FlowInputError as err:
                errors[err.field] = err.reason
            else:
                if _feature_reconfigure_would_reload_offline_without_wol(
                    self.hass,
                    self._entry,
                    data,
                ):
                    errors["base"] = "offline_without_wol"
                else:
                    return self.async_create_entry(
                        title="",
                        data=merged_feature_options(self._entry, data),
                    )

        return self.async_show_form(
            step_id="init",
            data_schema=_feature_schema(current),
            errors=errors,
            last_step=True,
        )


def _normalize_user_input(user_input: FlowFormInput) -> FlowFormInput:
    """Normalize form input through the compatibility helper."""
    return _normalize_user_input_impl(
        user_input,
        mac_normalizer=normalize_mac_address,
        broadcast_validator=validate_ipv4_address,
    )


def _connection_schema_fields(
    defaults: FlowFormInput | None = None,
) -> dict[Any, Any]:
    """Compatibility wrapper for config-flow schema tests."""
    return _connection_schema_fields_impl(defaults)


def _feature_schema_fields(defaults: FlowFormInput | None = None) -> dict[Any, Any]:
    """Compatibility wrapper for config-flow schema tests."""
    return _feature_schema_fields_impl(defaults)


def _normalize_host_input(host_input: str) -> tuple[str, int | None, bool | None]:
    """Compatibility wrapper for host normalization tests."""
    return _normalize_host_input_impl(host_input)


async def _async_validate_for_form(
    hass: HomeAssistant,
    data: dict[str, Any],
    *,
    validator: FlowValidator | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Validate flow data and return a form error key instead of raising."""
    return await async_validate_for_form(
        hass,
        data,
        validator=validator or _validate_input,
    )


async def _validate_input(
    hass: HomeAssistant,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Validate that the user input allows us to connect."""
    return await async_validate_input(hass, data)


async def _validate_input_or_allow_wol_offline(
    hass: HomeAssistant,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Validate the local API or allow offline setup when WOL is configured."""
    try:
        return await _validate_input(hass, data)
    except CannotConnect:
        if bool(data.get(CONF_WOL_ENABLED)) and data.get(CONF_WOL_MAC_ADDRESS):
            return _entry_info(data)
        raise


def _discovered_device_already_configured(
    hass: HomeAssistant,
    device: DiscoveredUnasDevice,
) -> bool:
    """Return whether the discovered device already has an entry."""
    device_hosts = _discovered_device_host_keys(device)
    device_mac = _discovery_mac_key(device.hw_addr)
    device_unique_id = _zeroconf_discovery_unique_id(device)
    for entry in hass.config_entries.async_entries(DOMAIN):
        entry_macs = _entry_discovery_mac_keys(entry)
        entry_hosts = _entry_discovery_host_keys(entry)
        unique_id_matches = getattr(entry, "unique_id", None) == device_unique_id
        host_matches = bool(device_hosts & entry_hosts)
        mac_matches = bool(device_mac and device_mac in entry_macs)

        if (
            device_mac
            and entry_macs
            and device_mac not in entry_macs
            and (unique_id_matches or host_matches)
        ):
            _record_matched_discovery_observation(
                hass,
                entry,
                device,
                match_reason="identity_conflict",
                trusted=False,
                extra_conflicts=("configured_mac_discovery_mac_mismatch",),
            )
            continue

        if unique_id_matches:
            _record_matched_discovery_observation(
                hass,
                entry,
                device,
                match_reason="unique_id",
            )
            return True
        if host_matches:
            _record_matched_discovery_observation(
                hass,
                entry,
                device,
                match_reason="host",
            )
            return True
        if mac_matches:
            _record_matched_discovery_observation(
                hass,
                entry,
                device,
                match_reason="mac",
            )
            return True
    return False


def _record_matched_discovery_observation(
    hass: HomeAssistant,
    entry: UnifiDriveConfigEntry,
    device: DiscoveredUnasDevice,
    *,
    match_reason: str,
    trusted: bool = True,
    extra_conflicts: tuple[str, ...] = (),
) -> None:
    """Persist safe discovery metadata for an existing config entry."""
    now = datetime.now(UTC)
    data = _discovery_observation_entry_data(
        entry,
        device,
        extra_conflicts=extra_conflicts,
        trusted=trusted,
        now=now,
    )
    if dict(getattr(entry, "data", {}) or {}) == data:
        return

    if not _should_write_discovery_identity_update(
        existing=getattr(entry, "data", None),
        incoming=data,
        now=now,
        update_interval=timedelta(seconds=_DISCOVERY_METADATA_WRITE_INTERVAL_SECONDS),
    ):
        return

    update_entry = getattr(hass.config_entries, "async_update_entry", None)
    if callable(update_entry):
        update_entry(entry, data=data)

    if bool(merged_entry_data_options(entry).get(CONF_DISCOVERY_DEBUG, False)):
        _LOGGER.debug(
            "UniFi Drive discovery observation matched existing entry by %s "
            "(trusted=%s, source=%s, confidence=%s, conflicts=%s)",
            match_reason,
            trusted,
            data.get(CONF_DISCOVERY_IDENTITY_SOURCE),
            data.get(CONF_DISCOVERY_CONFIDENCE),
            data.get(CONF_DISCOVERY_IDENTITY_CONFLICTS, []),
        )


def _apply_validated_feature_defaults(
    user_input: dict[str, Any],
    info: dict[str, Any],
    existing_defaults: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge system-discovered feature defaults after connection validation."""
    defaults = dict(existing_defaults or {})
    if isinstance(info.get("feature_defaults"), dict):
        defaults.update(info["feature_defaults"])
    return _normalize_user_input(_merge_feature_defaults(user_input, defaults))


class UnifiUnasConfigFlow(
    config_entries.ConfigFlow, domain=DOMAIN  # type: ignore[call-arg,misc]
):
    """Handle a config flow for UniFi Drive."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize config-flow discovery state."""
        self._discovery_attempted = False
        self._discovered_devices: dict[str, DiscoveredUnasDevice] = {}
        self._connection_defaults: dict[str, Any] | None = None
        self._feature_defaults: dict[str, Any] | None = None
        self._identity_defaults: dict[str, Any] | None = None
        self._discovery_placeholders: dict[str, str] | None = None

    @staticmethod
    def async_get_options_flow(
        config_entry: UnifiDriveConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow handler."""
        return UnifiUnasOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: FlowFormInput | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        if user_input is None and await self._async_prepare_discovery_step():
            return await self.async_step_discovery_select()

        return await self._async_step_connection_form("user", user_input)

    async def _async_step_connection_form(
        self,
        step_id: str,
        user_input: FlowFormInput | None = None,
        *,
        description_placeholders: dict[str, str] | None = None,
    ) -> ConfigFlowResult:
        """Handle connection and authentication input for setup flows."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                data = _normalize_user_input(
                    _merge_feature_defaults(user_input, self._feature_defaults)
                )
            except FlowInputError as err:
                errors[err.field] = err.reason
            else:
                info, error = await _async_validate_for_form(self.hass, data)
                if error:
                    errors["base"] = error
                elif info is not None:
                    if _any_unique_id_configured(self.hass, info):
                        return self.async_abort(reason="already_configured")
                    await self.async_set_unique_id(
                        info["unique_id"],
                        raise_on_progress=False,
                    )
                    self._abort_if_unique_id_configured()
                    data = _apply_validated_feature_defaults(
                        user_input,
                        info,
                        self._feature_defaults,
                    )
                    data = _apply_discovery_identity_defaults(
                        data,
                        info,
                        self._identity_defaults,
                    )
                    self._pending_user_state = _FlowState(data=data, info=info)
                    return await self.async_step_features()

        return self.async_show_form(
            step_id=step_id,
            data_schema=_connection_schema(self._connection_defaults),
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def async_step_discovery_select(
        self, user_input: FlowFormInput | None = None
    ) -> ConfigFlowResult:
        """Let the user select a discovered UNAS or continue manually."""
        errors: dict[str, str] = {}

        if not self._discovered_devices:
            return await self.async_step_user()

        if user_input is not None:
            selection = str(user_input.get(CONF_DISCOVERED_DEVICE, ""))
            if selection == MANUAL_DISCOVERY_VALUE:
                self._connection_defaults = None
                self._feature_defaults = None
                self._identity_defaults = None
                return await self.async_step_user()
            if device := self._discovered_devices.get(selection):
                self._connection_defaults = connection_defaults_from_discovery(device)
                self._feature_defaults = feature_defaults_from_discovery(device)
                self._identity_defaults = _discovery_identity_defaults_from_device(
                    device
                )
                return await self.async_step_user()
            errors["base"] = "invalid_discovery_selection"

        return self.async_show_form(
            step_id="discovery_select",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_DISCOVERED_DEVICE,
                        default=next(iter(self._discovered_devices)),
                    ): vol.In(discovery_options(tuple(self._discovered_devices.values())))
                }
            ),
            errors=errors,
        )

    async def _async_prepare_discovery_step(self) -> bool:
        """Scan once and return whether a device-selection step is useful."""
        if self._discovery_attempted:
            return False

        self._discovery_attempted = True
        try:
            devices = await async_discover_unas_devices()
        except (RuntimeError, TimeoutError, OSError, ValueError, TypeError) as err:
            _LOGGER.debug(
                "UniFi Drive discovery failed: %s",
                safe_error_text(err),
            )
            return False

        self._discovered_devices = {
            device.key: device
            for device in devices
            if not _discovered_device_already_configured(self.hass, device)
        }
        return bool(self._discovered_devices)

    async def async_step_zeroconf(self, discovery_info: Any) -> ConfigFlowResult:
        """Handle a zeroconf-discovered UniFi Drive / UNAS device."""
        device = discovered_unas_device_from_zeroconf(discovery_info)
        if device is None:
            return self.async_abort(reason="not_unas_device")
        context = getattr(self, "context", None)
        if isinstance(context, dict):
            context.update(_discovery_flow_context_from_device(device))
        if _discovered_device_already_configured(self.hass, device):
            return self.async_abort(reason="already_configured")

        await self.async_set_unique_id(_zeroconf_discovery_unique_id(device))
        self._abort_if_unique_id_configured()
        self._discovery_attempted = True
        self._connection_defaults = connection_defaults_from_discovery(device)
        self._feature_defaults = feature_defaults_from_discovery(device)
        self._identity_defaults = _discovery_identity_defaults_from_device(device)
        self._discovery_placeholders = {"name": device.label}
        if isinstance(context, dict):
            context["title_placeholders"] = self._discovery_placeholders
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: FlowFormInput | None = None
    ) -> ConfigFlowResult:
        """Confirm a zeroconf-discovered UniFi Drive / UNAS device."""
        return await self._async_step_connection_form(
            "zeroconf_confirm",
            user_input,
            description_placeholders=self._discovery_placeholders,
        )

    async def async_step_features(
        self, user_input: FlowFormInput | None = None
    ) -> ConfigFlowResult:
        """Handle optional feature settings after the connection was verified."""
        errors: dict[str, str] = {}
        state = getattr(self, "_pending_user_state", None)
        if not isinstance(state, _FlowState) or state.info is None:
            return await self.async_step_user()

        if user_input is not None:
            merged = dict(state.data)
            merged.update(user_input)
            try:
                data = _normalize_user_input(merged)
            except FlowInputError as err:
                errors[err.field] = err.reason
            else:
                self._pending_user_state = None
                return self.async_create_entry(
                    title=state.info["title"],
                    data=entry_data_from_data(data),
                    options=feature_options_from_data(data),
                )

        return self.async_show_form(
            step_id="features",
            data_schema=_feature_schema(state.data),
            errors=errors,
            last_step=True,
        )

    async def async_step_reauth(
        self, _entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle reauthentication triggered by invalid credentials."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: FlowFormInput | None = None
    ) -> ConfigFlowResult:
        """Ask for new credentials and update the existing config entry."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        current = dict(entry.data)

        if user_input is not None:
            try:
                data = _normalize_user_input(_merged_reauth_data(current, user_input))
            except FlowInputError as err:
                errors[err.field] = err.reason
            else:
                info, error = await _async_validate_for_form(self.hass, data)
                if error:
                    errors["base"] = error
                elif info is not None:
                    unique_id = (
                        entry.unique_id
                        if _entry_unique_id_matches(entry.unique_id, info)
                        else info["unique_id"]
                    )
                    await self.async_set_unique_id(
                        unique_id,
                        raise_on_progress=False,
                    )
                    self._abort_if_unique_id_mismatch(reason="wrong_device")
                    data_updates = {
                        CONF_USERNAME: data[CONF_USERNAME],
                        CONF_PASSWORD: data[CONF_PASSWORD],
                        CONF_API_KEY: data.get(CONF_API_KEY, ""),
                    }
                    entry_data = merged_entry_data_with_connection_updates(
                        entry,
                        dict(entry.data) | data_updates,
                    )
                    options = feature_options_from_entry(entry)
                    return self.async_update_and_abort(
                        entry,
                        data=entry_data,
                        options=options,
                    )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USERNAME,
                        default=current.get(CONF_USERNAME, ""),
                    ): str,
                    vol.Optional(CONF_PASSWORD, default=""): str,
                    vol.Optional(
                        CONF_API_KEY,
                        default=current.get(CONF_API_KEY, ""),
                    ): str,
                }
            ),
            errors=errors,
            last_step=True,
        )

    async def async_step_reconfigure(
        self, _user_input: FlowFormInput | None = None
    ) -> ConfigFlowResult:
        """Let the user choose which part of the config entry to reconfigure."""
        return self.async_show_menu(
            step_id="reconfigure",
            menu_options=[
                "reconfigure_connection",
                "reconfigure_features",
            ],
        )

    async def async_step_reconfigure_connection(
        self, user_input: FlowFormInput | None = None
    ) -> ConfigFlowResult:
        """Handle connection/auth settings during reconfiguration."""
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()
        current = merged_entry_data_options(entry)

        if user_input is not None:
            try:
                data = _normalize_user_input(
                    _merged_reconfigure_data(current, user_input)
                )
            except FlowInputError as err:
                errors[err.field] = err.reason
            else:
                info, error = await _async_validate_for_form(
                    self.hass,
                    data,
                )
                if error:
                    errors["base"] = error
                elif info is not None:
                    if not _entry_matches_validated_device(entry, info):
                        errors["base"] = "wrong_device"
                    else:
                        entry_data = merged_entry_data_with_connection_updates(
                            entry,
                            data,
                        )
                        options = merged_feature_options(entry, data)
                        return self.async_update_and_abort(
                            entry,
                            data=entry_data,
                            options=options,
                        )

        return self.async_show_form(
            step_id="reconfigure_connection",
            data_schema=_connection_schema(current),
            errors=errors,
            last_step=True,
        )

    async def async_step_reconfigure_features(
        self, user_input: FlowFormInput | None = None
    ) -> ConfigFlowResult:
        """Handle optional feature settings during reconfiguration."""
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()
        current = merged_entry_data_options(entry)

        if user_input is not None:
            try:
                data = _normalize_user_input(
                    _merged_reconfigure_data(current, user_input)
                )
            except FlowInputError as err:
                errors[err.field] = err.reason
            else:
                if _feature_reconfigure_would_reload_offline_without_wol(
                    self.hass,
                    entry,
                    data,
                ):
                    errors["base"] = "offline_without_wol"
                else:
                    entry_data = data_without_feature_options(dict(entry.data))
                    options = merged_feature_options(entry, data)
                    return self.async_update_and_abort(
                        entry,
                        data=entry_data,
                        options=options,
                    )

        return self.async_show_form(
            step_id="reconfigure_features",
            data_schema=_feature_schema(current),
            errors=errors,
            last_step=True,
        )
