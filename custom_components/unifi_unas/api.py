"""Async client for local UniFi Drive / UniFi OS endpoints."""

from __future__ import annotations

import asyncio
from typing import Any

from aiohttp import ClientSession

from .api_auth import ApiAuthMixin
from .api_backup import ApiBackupMixin
from .api_fan import ApiFanMixin
from .api_snapshot import ApiSnapshotMixin
from .api_storage import ApiStorageMixin
from .api_system import ApiSystemMixin
from .api_transport import ApiTransportMixin
from .api_updates import ApiUpdatesMixin
from .api_errors import (
    CannotConnect,
    InvalidAuth,
    UnexpectedResponse,
    UnifiUnasApiError,
    UnsupportedFeature,
)
from .url_helpers import build_console_url, format_host_for_url

__all__ = [
    "UnifiUnasApiClient",
    "CannotConnect",
    "InvalidAuth",
    "UnexpectedResponse",
    "UnifiUnasApiError",
    "UnsupportedFeature",
]


class UnifiUnasApiClient(
    ApiUpdatesMixin,
    ApiSnapshotMixin,
    ApiBackupMixin,
    ApiFanMixin,
    ApiSystemMixin,
    ApiStorageMixin,
    ApiAuthMixin,
    ApiTransportMixin,
):
    """Small async client for the local UniFi Drive and UniFi OS endpoints."""

    def __init__(
        self,
        session: ClientSession,
        *,
        host: str,
        username: str = "",
        password: str = "",
        api_key: str | None = None,
        port: int = 443,
        use_ssl: bool = True,
        verify_ssl: bool = False,
        timeout: int = 15,
    ) -> None:
        """Initialize the API client."""
        self._session = session
        self._host = format_host_for_url(host)
        self._username = username.strip()
        self._password = password
        self._api_key = api_key.strip() if api_key else None
        self._use_api_key_auth = bool(
            self._api_key and not (self._username and self._password)
        )
        self._port = port
        self._scheme = "https" if use_ssl else "http"
        self._verify_ssl = verify_ssl
        self._timeout = timeout
        self._csrf_token: str | None = None
        self._token_cookie: str | None = None
        self._authenticated = self._use_api_key_auth
        self._login_data: dict[str, Any] | None = None
        self._system_info: dict[str, Any] | None = None
        self._system_metadata_cached_at: float | None = None
        self._system_metadata_generation = 0
        self._last_fan_mode: str | None = None
        self._fan_mode_read_supported: bool | None = None
        self._fan_mode_write_supported: bool | None = None
        self._fan_mode_write_payload_hint: str | None = None
        self._backup_tasks_read_supported: bool | None = None
        self._snapshot_settings_read_supported: bool | None = None
        self._snapshot_settings_lock = asyncio.Lock()
        self._snapshot_settings_write_supported: bool | None = None
        self._snapshot_settings_write_supported_by_type: dict[str, bool] = {}
        self._snapshot_create_supported: bool | None = None
        self._snapshot_create_supported_by_type: dict[str, bool] = {}
        self._snapshot_inventory_supported: bool | None = None
        self._snapshot_inventory_supported_by_type: dict[str, bool] = {}

    @property
    def base_url(self) -> str:
        """Return the console base URL."""
        return build_console_url(self._scheme, self._host, self._port)

    @property
    def host(self) -> str:
        """Return configured host."""
        return self._host
