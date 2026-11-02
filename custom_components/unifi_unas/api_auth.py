"""Authentication helpers for the UniFi Drive API client."""

from __future__ import annotations

from json import JSONDecodeError, loads
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, TypeVar

from aiohttp import ClientResponse, ClientSession

from .api_errors import CannotConnect, InvalidAuth
from .api_transport import read_response_body, read_response_text, reject_redirect
from .const import LOGIN_PATH
from .security import safe_response_summary
from .wake_on_lan import normalize_mac_address

# Cookie name only, not a secret value.
TOKEN_COOKIE_NAME = "TOKEN"  # nosec B105
_T = TypeVar("_T")


class ApiAuthMixin:
    """Auth/session behavior split from the main client class."""

    _authenticated: bool
    _login_data: dict[str, Any] | None
    _password: str
    _session: ClientSession
    _system_info: dict[str, Any] | None
    _token_cookie: str | None
    _use_api_key_auth: bool
    _username: str

    if TYPE_CHECKING:
        @property
        def _ssl(self) -> bool | None: ...
        @property
        def base_url(self) -> str: ...
        def _headers(self) -> dict[str, str]: ...
        def _update_csrf_token(self, response: ClientResponse) -> None: ...
        def _url(self, path: str) -> str: ...
        async def _request_with_timeout(
            self,
            action: Callable[[], Awaitable[_T]],
        ) -> _T: ...

    @property
    def device_unique_id(self) -> str | None:
        """Return best-effort stable device identifier from login payload."""
        unique_ids = self.device_unique_ids
        return unique_ids[0] if unique_ids else None

    @property
    def device_unique_ids(self) -> tuple[str, ...]:
        """Return all known stable device identifiers in preferred order."""
        unique_ids: list[str] = []

        def _add(value: Any) -> None:
            if value in (None, ""):
                return
            text = str(value).strip()
            if text and text not in unique_ids:
                unique_ids.append(text)

        system_id = self._system_device_unique_id()
        _add(system_id)

        if isinstance(self._login_data, dict):
            for key in ("unique_id", "uniqueId", "id", "deviceId"):
                _add(self._login_data.get(key))

        return tuple(unique_ids)

    @property
    def device_scoped_unique_ids(self) -> tuple[str, ...]:
        """Return identifiers known to describe this device, not just the account."""
        system_id = self._system_device_unique_id()
        return (system_id,) if system_id else ()

    def _system_device_unique_id(self) -> str | None:
        """Return a stable identifier from system metadata when available."""
        if not isinstance(self._system_info, dict):
            return None

        system_payload = self._system_info

        candidates = self._system_field_candidates(
            system_payload,
            include_fallback_id=False,
        )
        if candidates:
            return candidates

        hardware = system_payload.get("hardware")
        if isinstance(hardware, dict):
            candidates = self._system_field_candidates(hardware)
            if candidates:
                return candidates

        devices = system_payload.get("devices")
        if isinstance(devices, dict):
            candidate = self._first_valid_system_identifier_from_system_section(devices)
            if candidate:
                return candidate

        candidates = self._system_field_candidates(
            system_payload,
            include_fallback_id=True,
        )
        if candidates:
            return candidates

        return None

    @staticmethod
    def _first_valid_system_identifier_from_system_section(
        system_section: dict[str, Any],
    ) -> str | None:
        """Return the first system identifier from nested ``devices.unifiOS``."""
        unifi_os = system_section.get("unifiOS")
        if not isinstance(unifi_os, list):
            return None

        for device in unifi_os:
            if not isinstance(device, dict):
                continue
            candidate = ApiAuthMixin._system_field_candidates(device)
            if candidate:
                return candidate
        return None

    @staticmethod
    def _system_field_candidates(
        payload: dict[str, Any],
        *,
        include_fallback_id: bool = True,
    ) -> str | None:
        """Return first non-empty identifier from an ordered system payload."""
        mac_keys = {"mac", "macAddress", "mac_address"}
        keys: tuple[str, ...] = (
            "systemId",
            "system_id",
            "uuid",
            "serial",
            "serialNumber",
            "serial_number",
            "unique_id",
            "uniqueId",
            "deviceId",
            "mac",
            "macAddress",
            "mac_address",
        )

        for key in keys:
            value = payload.get(key)
            if value in (None, ""):
                continue
            text = str(value).strip()
            if text:
                if key in mac_keys:
                    try:
                        return normalize_mac_address(text)
                    except ValueError:
                        continue
                return text

        if include_fallback_id:
            value = payload.get("id")
            if value not in (None, ""):
                text = str(value).strip()
                if text:
                    return text
        return None

    @property
    def poweroff_permission_hint(self) -> bool | None:
        """Return whether login metadata indicates poweroff permission."""
        if not self._login_data:
            return None

        if self._login_data.get("isSuperAdmin") is True:
            return True

        scope_hint: bool | None = None
        scopes = self._login_data.get("scopes")
        if isinstance(scopes, list):
            scope_hint = "edit:os-settings:poweroff" in scopes

        ucore_hint: bool | None = None
        ucore_permission = self._login_data.get("ucorePermission")
        if isinstance(ucore_permission, dict):
            value = ucore_permission.get("hasPoweroffConsolePermission")
            if isinstance(value, bool):
                ucore_hint = value

        if scope_hint is True or ucore_hint is True:
            return True
        if scope_hint is False or ucore_hint is False:
            return False
        return None

    async def async_login(self) -> None:
        """Authenticate against UniFi OS and keep the session cookie."""
        if self._use_api_key_auth:
            self._authenticated = True
            return

        if not self._username or not self._password:
            raise InvalidAuth(
                "UniFi username and password are required when no API key is configured"
            )

        await self._prime_csrf_token()

        payload = {
            "username": self._username,
            "password": self._password,
            "remember": True,
            "rememberMe": True,
        }

        async def _execute_login() -> dict[str, Any] | None:
            response = await self._session.post(
                self._url(LOGIN_PATH),
                json=payload,
                headers=self._headers(),
                ssl=self._ssl,
                allow_redirects=False,
            )
            async with response:
                reject_redirect(response)
                return await self._consume_login_response(response)

        data = await self._request_with_timeout(_execute_login)

        self._login_data = data if isinstance(data, dict) else None
        self._authenticated = True

    async def _ensure_authenticated(self) -> None:
        """Log in if we do not currently have a valid session."""
        if self._use_api_key_auth:
            self._authenticated = True
            return
        if not self._authenticated:
            await self.async_login()

    async def _prime_csrf_token(self) -> None:
        """Fetch the console root once to pick up a CSRF token when provided."""
        async def _read_root() -> None:
            response = await self._session.get(
                self.base_url, ssl=self._ssl, allow_redirects=False
            )
            async with response:
                self._update_csrf_token(response)
                await read_response_body(response)

        await self._request_with_timeout(_read_root)

    async def _consume_login_response(
        self,
        response: ClientResponse,
    ) -> dict[str, Any] | None:
        """Validate login response, update CSRF token and return login JSON."""
        self._update_csrf_token(response)
        self._capture_token_cookie(response)

        if response.status in (401, 403):
            raise InvalidAuth("Invalid UniFi username or password")

        if response.status >= 400:
            body = await read_response_text(response)
            raise CannotConnect(
                f"Login failed with HTTP {response.status}: {safe_response_summary(body)}"
            )

        body = await read_response_text(response)
        try:
            data = loads(body)
        except JSONDecodeError:
            return None

        return data if isinstance(data, dict) else None

    def _capture_token_cookie(self, response: ClientResponse) -> None:
        """Capture UniFi's auth token cookie when aiohttp cannot store it."""
        for raw_cookie in response.headers.getall("Set-Cookie", []):
            token = self._extract_set_cookie_value(raw_cookie, TOKEN_COOKIE_NAME)
            if token:
                self._token_cookie = token
                return

    @staticmethod
    def _extract_set_cookie_value(raw_cookie: str, name: str) -> str | None:
        """Return a Set-Cookie value without parsing unsupported attributes."""
        first_part = raw_cookie.split(";", 1)[0].strip()
        prefix = f"{name}="
        if not first_part.startswith(prefix):
            return None
        value = first_part[len(prefix) :].strip()
        return value or None
