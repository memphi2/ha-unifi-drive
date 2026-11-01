"""Config-flow API validation helpers."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

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
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import CannotConnect, InvalidAuth, UnexpectedResponse, UnifiUnasApiClient
from .config_flow_identity import _entry_info
from .const import CONF_WOL_MAC_ADDRESS
from .discovery import feature_defaults_from_system_payload
from .discovery_identity import discovery_mac_key
from .security import safe_error_text

_LOGGER = logging.getLogger(__name__)

FlowValidator = Callable[[HomeAssistant, dict[str, Any]], Awaitable[dict[str, Any]]]


def _validation_error_reason(
    err: CannotConnect | InvalidAuth | UnexpectedResponse,
) -> str:
    """Return the config-flow error key for a validation exception."""
    if isinstance(err, CannotConnect):
        return "cannot_connect"
    if isinstance(err, InvalidAuth):
        return "invalid_auth"
    return "unsupported_response"


async def async_validate_for_form(
    hass: HomeAssistant,
    data: dict[str, Any],
    *,
    validator: FlowValidator,
) -> tuple[dict[str, Any] | None, str | None]:
    """Validate flow data and return a form error key instead of raising."""
    try:
        return await validator(hass, data), None
    except (CannotConnect, InvalidAuth, UnexpectedResponse) as err:
        return None, _validation_error_reason(err)
    except Exception as err:
        _LOGGER.debug(
            "Validation failed with unexpected exception: %s",
            safe_error_text(err),
        )
        return None, "unknown"


async def async_validate_input(
    hass: HomeAssistant,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Validate that the user input allows us to connect."""
    session = async_create_clientsession(
        hass,
        verify_ssl=bool(data[CONF_VERIFY_SSL]),
        cookie_jar=aiohttp.CookieJar(unsafe=True),
        auto_cleanup=False,
    )
    try:
        client = UnifiUnasApiClient(
            session,
            host=data[CONF_HOST],
            username=data.get(CONF_USERNAME, ""),
            password=data.get(CONF_PASSWORD, ""),
            api_key=data.get(CONF_API_KEY) or None,
            port=int(data[CONF_PORT]),
            use_ssl=bool(data[CONF_SSL]),
            verify_ssl=bool(data[CONF_VERIFY_SSL]),
        )
        storage = await client.async_check_connection()
    finally:
        session.detach()
    pools = storage.get("pools")
    if pools is not None and not isinstance(pools, list):
        raise UnexpectedResponse("Storage response contains a non-list pools value")

    unique_ids = client.device_unique_ids
    defaults = feature_defaults_from_system_payload(storage.get("_system"))
    fallback_unique_id = (
        None
        if unique_ids
        else discovery_mac_key(defaults.get(CONF_WOL_MAC_ADDRESS))
    )
    info = _entry_info(
        data,
        unique_id=unique_ids[0] if unique_ids else fallback_unique_id,
        unique_ids=unique_ids,
        device_scoped_unique_ids=client.device_scoped_unique_ids,
    )
    if defaults:
        info["feature_defaults"] = defaults
    return info
