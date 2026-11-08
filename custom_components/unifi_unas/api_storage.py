"""Storage/system read operations for the UniFi Drive API client."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import logging
from time import monotonic
from typing import TYPE_CHECKING, Any

from .api_errors import CannotConnect, InvalidAuth, UnexpectedResponse
from .const import DRIVE_DEVICE_INFO_PATH, DRIVE_STORAGE_PATH, NETWORK_IO_PATH, SYSTEM_PATH
from .security import safe_error_text
from .system_metadata import sampled_device_info

_LOGGER = logging.getLogger(__name__)
_METADATA_REQUEST_TIMEOUT = 2.5
_STATIC_SYSTEM_METADATA_TTL = 600


class ApiStorageMixin:
    """Storage reads split from the main API client class."""

    _authenticated: bool
    _last_fan_mode: str | None
    _system_info: dict[str, Any] | None
    _use_api_key_auth: bool
    _system_metadata_cached_at: float | None
    _system_metadata_generation: int

    if TYPE_CHECKING:
        async def _ensure_authenticated(self) -> None: ...
        async def async_login(self) -> None: ...
        async def _request_json(self, method: str, path: str) -> dict[str, Any]: ...
        def _extract_fan_mode(self, payload: Any) -> str | None: ...

    async def async_check_connection(self) -> dict[str, Any]:
        """Validate credentials and return storage data."""
        self.invalidate_system_metadata()
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
            self.invalidate_system_metadata()
            _LOGGER.debug("UNAS session expired; retrying login once")
            self._authenticated = False
            await self.async_login()
            data = await self._request_json("GET", DRIVE_STORAGE_PATH)
        except CannotConnect:
            self.invalidate_system_metadata()
            raise

        if mode := self._extract_fan_mode(data):
            self._last_fan_mode = mode
        # Authentication and core storage are complete before independent metadata
        # reads overlap. TaskGroup also joins/cancels every child on unload.
        async with asyncio.TaskGroup() as group:
            system = group.create_task(self._read_system_metadata())
            network = group.create_task(self._read_metadata(NETWORK_IO_PATH, "network I/O"))
            device = (
                group.create_task(self._read_metadata(DRIVE_DEVICE_INFO_PATH, "device"))
                if self._use_api_key_auth else None
            )
        if (system_data := system.result()) is not None:
            data["_system"] = system_data
        if (network_data := network.result()) is not None:
            data["_network_io"] = network_data
        if device is not None and (device_data := device.result()) is not None:
            data["_device_info"] = sampled_device_info(device_data, datetime.now(UTC))
        return data

    def invalidate_system_metadata(self) -> None:
        """Make explicit refreshes and recovery bypass the static metadata cache."""
        self._system_metadata_cached_at = None
        self._system_metadata_generation += 1

    async def _read_metadata(self, path: str, label: str) -> dict[str, Any] | None:
        """Keep failures local to one bounded, optional metadata read."""
        try:
            async with asyncio.timeout(_METADATA_REQUEST_TIMEOUT):
                return await self._request_json("GET", path)
        except (CannotConnect, InvalidAuth, UnexpectedResponse, TimeoutError) as err:
            _LOGGER.debug("Could not read UniFi Drive %s metadata: %s", label, safe_error_text(err))
            return None

    async def _read_system_metadata(self) -> dict[str, Any] | None:
        """Reuse static information until expiry or explicit invalidation."""
        cached_at = self._system_metadata_cached_at
        if cached_at is not None and monotonic() - cached_at < _STATIC_SYSTEM_METADATA_TTL:
            return self._system_info
        generation = self._system_metadata_generation
        self._system_metadata_cached_at = None
        result = await self._read_metadata(SYSTEM_PATH, "system")
        if result is not None:
            self._system_info = result
            if (
                generation == self._system_metadata_generation
                and self._use_api_key_auth
                and _is_static_system_metadata(result)
            ):
                self._system_metadata_cached_at = monotonic()
        return result


def _is_static_system_metadata(data: dict[str, Any]) -> bool:
    """Cache only explicitly static payloads; unknown fields may be live metrics."""
    fields = {
        "firmwareVersion", "firmware_version", "ucore_version", "version",
        "systemId", "uuid", "serial", "serialNumber",
    }
    if not data or not data.keys() <= fields | {"hardware"}:
        return False
    hardware = data.get("hardware", {})
    return isinstance(hardware, dict) and hardware.keys() <= fields | {
        "name", "shortname", "model", "mac", "macAddress",
    }
