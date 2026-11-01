"""Low-level HTTP transport helpers for the UniFi Drive API client."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from json import JSONDecodeError, loads
from typing import TYPE_CHECKING, Any, TypeVar

from aiohttp import ClientConnectorError, ClientError, ClientResponse, ClientSession

from .api_errors import CannotConnect, InvalidAuth, UnexpectedResponse
from .security import safe_error_text

_T = TypeVar("_T")


def reject_redirect(response: ClientResponse) -> None:
    """Do not follow console redirects or treat them as successful writes."""
    if 300 <= response.status < 400:
        raise CannotConnect(
            "The console redirected the request. Check the configured host, port "
            "and SSL settings; automatic redirects are not permitted."
        )


class ApiTransportMixin:
    """Shared request/response helpers."""

    _api_key: str | None
    _csrf_token: str | None
    _scheme: str
    _session: ClientSession
    _timeout: int
    _token_cookie: str | None
    _use_api_key_auth: bool
    _verify_ssl: bool

    if TYPE_CHECKING:
        @property
        def base_url(self) -> str: ...

    @property
    def _ssl(self) -> bool | None:
        """Return aiohttp SSL validation option."""
        if self._scheme != "https":
            return None
        return self._verify_ssl

    def _url(self, path: str) -> str:
        """Build an absolute URL."""
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{self.base_url}{path}"

    def _headers(self) -> dict[str, str]:
        """Return request headers."""
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self._use_api_key_auth and self._api_key:
            headers["X-API-Key"] = self._api_key
        if not self._use_api_key_auth and self._token_cookie:
            headers["Cookie"] = f"TOKEN={self._token_cookie}"
        if self._csrf_token:
            headers["X-CSRF-Token"] = self._csrf_token
        return headers

    def _auth_error_message(self) -> str:
        """Return an auth error message for the active auth mode."""
        if self._use_api_key_auth and self._api_key:
            return "UniFi API key is invalid or does not have the required permission"
        return "UniFi session is not authenticated"

    def _update_csrf_token(self, response: ClientResponse) -> None:
        """Update CSRF token from UniFi response headers."""
        token = response.headers.get("x-csrf-token") or response.headers.get(
            "x-updated-csrf-token"
        )
        if token:
            self._csrf_token = token

    async def _request_with_timeout(
        self,
        action: Callable[[], Awaitable[_T]],
    ) -> _T:
        """Run an aiohttp operation with consistent timeout/error mapping."""
        try:
            async with asyncio.timeout(self._timeout):
                return await action()
        except (ClientConnectorError, TimeoutError) as err:
            raise CannotConnect("Cannot connect to UniFi Drive host") from err
        except ClientError as err:
            raise CannotConnect(
                "HTTP error while connecting to UniFi Drive host: "
                f"{type(err).__name__}"
            ) from err

    async def _request_json(self, method: str, path: str) -> dict[str, Any]:
        """Perform a JSON request against the local console."""
        data = await self._request(method, path, expect_json=True)
        if not isinstance(data, dict):
            raise UnexpectedResponse(f"Expected JSON object from {path}")
        return data

    async def _request_no_json(self, method: str, path: str) -> None:
        """Perform a request where no JSON response is required."""
        await self._request(method, path, expect_json=False)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        expect_json: bool,
    ) -> dict[str, Any] | None:
        """Perform a request against the local console."""
        async def _execute() -> dict[str, Any] | None:
            response = await self._session.request(
                method,
                self._url(path),
                headers=self._headers(),
                ssl=self._ssl,
                allow_redirects=False,
            )
            async with response:
                reject_redirect(response)
                self._update_csrf_token(response)

                if response.status in (401, 403):
                    raise InvalidAuth(self._auth_error_message())

                if response.status >= 400:
                    body = await response.text()
                    raise CannotConnect(
                        f"Request to {path} failed with HTTP {response.status}: "
                        f"{safe_error_text(body)}"
                    )

                if not expect_json:
                    await response.read()
                    return None

                try:
                    data = await response.json(content_type=None)
                except JSONDecodeError as err:
                    body = await response.text()
                    raise UnexpectedResponse(
                        f"Expected JSON from {path}, got: {safe_error_text(body)}"
                    ) from err

            return data if isinstance(data, dict) else None

        return await self._request_with_timeout(_execute)

    async def _request_raw(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
        """Perform a request and return HTTP status plus parsed or text payload."""
        async def _execute() -> tuple[int, str]:
            response = await self._session.request(
                method,
                self._url(path),
                headers=self._headers(),
                json=json_body,
                ssl=self._ssl,
                allow_redirects=False,
            )
            async with response:
                reject_redirect(response)
                self._update_csrf_token(response)
                status = response.status

                if status in (401, 403):
                    raise InvalidAuth(self._auth_error_message())

                text = await response.text()
                return status, text

        status, text = await self._request_with_timeout(_execute)

        if not text:
            return status, None

        try:
            return status, loads(text)
        except JSONDecodeError:
            return status, text
