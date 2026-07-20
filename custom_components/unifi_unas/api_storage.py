"""Storage/system read operations for the UniFi Drive API client."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .api_errors import CannotConnect, InvalidAuth, UnexpectedResponse
from .const import DRIVE_DEVICE_INFO_PATH, DRIVE_STORAGE_PATH, NETWORK_IO_PATH, SYSTEM_PATH
from .security import safe_error_text

_LOGGER = logging.getLogger(__name__)


class ApiStorageMixin:
    """Storage reads split from the main API client class."""

    _authenticated: bool
    _last_fan_mode: str | None
    _system_info: dict[str, Any] | None
    _use_api_key_auth: bool

    if TYPE_CHECKING:
        async def _ensure_authenticated(self) -> None: ...
        async def async_login(self) -> None: ...
        async def _request_json(self, method: str, path: str) -> dict[str, Any]: ...
        def _extract_fan_mode(self, payload: Any) -> str | None: ...

    async def async_check_connection(self) -> dict[str, Any]:
        """Validate credentials and return storage data."""
        if self._use_api_key_auth:
            self._authenticated = True
        else:
            await self.async_login()
        return await self.async_get_storage()

    async def async_get_storage(self) -> dict[str, Any]:
        """Return UniFi Drive storage information."""
        await self._ensure_authenticated()
        try:
            data = await self._request_json("GET", DRIVE_STORAGE_PATH)
        except InvalidAuth:
            _LOGGER.debug("UNAS session expired; retrying login once")
            self._authenticated = False
            await self.async_login()
            data = await self._request_json("GET", DRIVE_STORAGE_PATH)

        if mode := self._extract_fan_mode(data):
            self._last_fan_mode = mode
        try:
            system_data = await self._request_json("GET", SYSTEM_PATH)
            data["_system"] = system_data
            self._system_info = system_data
        except (CannotConnect, InvalidAuth, UnexpectedResponse) as err:
            _LOGGER.debug(
                "Could not read UniFi OS system metadata: %s",
                safe_error_text(err),
            )
        try:
            data["_network_io"] = await self._request_json("GET", NETWORK_IO_PATH)
        except (CannotConnect, InvalidAuth, UnexpectedResponse) as err:
            _LOGGER.debug(
                "Could not read UniFi Drive network I/O metadata: %s",
                safe_error_text(err),
            )
        try:
            data["_device_info"] = await self._request_json(
                "GET", DRIVE_DEVICE_INFO_PATH
            )
        except (CannotConnect, InvalidAuth, UnexpectedResponse) as err:
            _LOGGER.debug(
                "Could not read UniFi Drive device-info metadata: %s",
                safe_error_text(err),
            )
        return data
