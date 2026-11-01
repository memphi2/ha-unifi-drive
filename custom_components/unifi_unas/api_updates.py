"""Update-action operations for the UniFi Drive API client."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .api_backup import BACKUP_NOT_FOUND_HTTP_STATUSES
from .api_errors import InvalidAuth, UnsupportedFeature
from .const import DRIVE_APPLICATION_UPDATE_PATH, UNIFI_OS_UPDATE_PATH
from .security import safe_response_summary

_LOGGER = logging.getLogger(__name__)


class ApiUpdatesMixin:
    """Update-action behavior split from the main API client class."""

    _authenticated: bool

    if TYPE_CHECKING:
        async def _ensure_authenticated(self) -> None: ...
        async def async_login(self) -> None: ...
        async def _request_raw(
            self,
            method: str,
            path: str,
            *,
            json_body: dict[str, Any] | None = None,
        ) -> tuple[int, Any]: ...

    async def async_install_unifi_os_update(self) -> None:
        """Request installation of the currently offered UniFi OS update."""
        await self._async_update_action("UniFi OS", UNIFI_OS_UPDATE_PATH, {})

    async def async_install_drive_update(self) -> None:
        """Request installation of the currently offered UniFi Drive update."""
        await self._async_update_action("UniFi Drive", DRIVE_APPLICATION_UPDATE_PATH, {})

    async def _async_update_action(
        self,
        name: str,
        path: str,
        payload: dict[str, Any],
    ) -> None:
        """Run an update action against a known local UniFi OS endpoint."""
        await self._ensure_authenticated()
        try:
            await self._async_update_action_once(name, path, payload)
        except InvalidAuth:
            _LOGGER.debug("UNAS session expired before %s update; retrying login once", name)
            self._authenticated = False
            await self.async_login()
            await self._async_update_action_once(name, path, payload)

    async def _async_update_action_once(
        self,
        name: str,
        path: str,
        payload: dict[str, Any],
    ) -> None:
        """Run the configured update action endpoint once."""
        status, response_payload = await self._request_raw(
            "POST",
            path,
            json_body=payload,
        )
        if 200 <= status < 300:
            _LOGGER.debug("%s update request accepted by %s", name, path)
            return
        if status == 409:
            _LOGGER.debug(
                "%s update endpoint reports no update needed (HTTP 409): %s",
                name,
                safe_response_summary(response_payload),
            )
            return

        if status in BACKUP_NOT_FOUND_HTTP_STATUSES:
            raise UnsupportedFeature(f"{name} update endpoint is not available.")
        raise UnsupportedFeature(
            f"{name} update endpoint {path} returned HTTP {status}: "
            f"{safe_response_summary(response_payload)}"
        )
