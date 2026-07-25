"""Runtime-path tests for the local UniFi Drive API client."""

from __future__ import annotations

import asyncio
from json import JSONDecodeError
from typing import Any

import pytest
from tests.api_client_stubs import UnifiUnasApiClient

from custom_components.unifi_unas import api_transport as api_transport_module
from custom_components.unifi_unas.api import (
    CannotConnect,
    InvalidAuth,
    UnexpectedResponse,
    UnsupportedFeature,
)
from custom_components.unifi_unas.const import (
    FAN_CONTROL_PATH,
    NETWORK_IO_PATH,
    POWEROFF_PATH,
    REBOOT_PATH,
)


class _Headers(dict):
    """Small header mapping with aiohttp-style getall support."""

    def getall(self, key: str, default: list[str] | None = None) -> list[str]:
        """Return all header values for ``key``."""
        value = self.get(key)
        if value is None:
            return [] if default is None else default
        if isinstance(value, list):
            return value
        return [str(value)]


class _Response:
    """Minimal async aiohttp response double."""

    def __init__(
        self,
        status: int = 200,
        *,
        payload: Any = None,
        text: str | None = None,
        headers: dict[str, Any] | None = None,
        json_error: Exception | None = None,
    ) -> None:
        self.status = status
        self._payload = payload
        self._text = text
        self.headers = _Headers(headers or {})
        self._json_error = json_error
        self.read_called = False

    async def __aenter__(self) -> "_Response":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def json(self, **_kwargs: Any) -> Any:
        if self._json_error is not None:
            raise self._json_error
        return self._payload

    async def text(self) -> str:
        if self._text is not None:
            return self._text
        return str(self._payload)

    async def read(self) -> bytes:
        self.read_called = True
        return (self._text or "").encode()


class _Session:
    """Minimal session double with queued responses."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict[str, Any]]] = []
        self.request_responses: list[_Response | Exception] = []
        self.get_responses: list[_Response | Exception] = []
        self.post_responses: list[_Response | Exception] = []

    async def request(self, method: str, url: str, **kwargs: Any) -> _Response:
        self.requests.append((method, url, kwargs))
        return self._next(self.request_responses)

    async def get(self, url: str, **kwargs: Any) -> _Response:
        self.requests.append(("GET", url, kwargs))
        return self._next(self.get_responses)

    async def post(self, url: str, **kwargs: Any) -> _Response:
        self.requests.append(("POST", url, kwargs))
        return self._next(self.post_responses)

    @staticmethod
    def _next(queue: list[_Response | Exception]) -> _Response:
        if not queue:
            raise AssertionError("No queued response")
        response = queue.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _client(session: _Session | None = None, **kwargs: Any) -> UnifiUnasApiClient:
    """Build a client using the fake session."""
    return UnifiUnasApiClient(
        session or _Session(),
        host=kwargs.pop("host", "unas.local"),
        username=kwargs.pop("username", "user"),
        password=kwargs.pop("password", "pass"),
        **kwargs,
    )


def test_transport_json_request_updates_headers_and_csrf_token() -> None:
    """JSON requests should build auth headers, URL, SSL option and CSRF token."""
    session = _Session()
    session.request_responses.append(
        _Response(200, payload={"ok": True}, headers={"x-csrf-token": "csrf-1"})
    )
    client = _client(session, username="", password="", api_key="api-key", verify_ssl=True)

    data = asyncio.run(client._request_json("GET", "proxy/drive/api/v2/storage"))

    assert data == {"ok": True}
    assert client._csrf_token == "csrf-1"
    method, url, kwargs = session.requests[-1]
    assert method == "GET"
    assert url == "https://unas.local/proxy/drive/api/v2/storage"
    assert kwargs["ssl"] is True
    assert kwargs["headers"]["X-API-Key"] == "api-key"


def test_transport_no_json_reads_response_body() -> None:
    """No-JSON requests should still consume the response body."""
    session = _Session()
    response = _Response(204, text="accepted")
    session.request_responses.append(response)
    client = _client(session)
    client._authenticated = True

    assert asyncio.run(client._request_no_json("POST", "/api/system/reboot")) is None
    assert response.read_called is True


def test_transport_maps_auth_http_and_invalid_json_errors() -> None:
    """Transport should map common HTTP and payload failures to HA API errors."""
    client = _client(_Session(), username="", password="", api_key="api-key")

    client._session.request_responses.append(_Response(401, text="nope"))
    with pytest.raises(InvalidAuth, match="API key"):
        asyncio.run(client._request_json("GET", "/api/test"))

    client._session.request_responses.append(
        _Response(500, text="host=192.0.2.10 token=secret-token")
    )
    with pytest.raises(CannotConnect) as err:
        asyncio.run(client._request_json("GET", "/api/test"))
    assert "192.0.2.10" not in str(err.value)
    assert "secret-token" not in str(err.value)

    client._session.request_responses.append(
        _Response(
            200,
            text="not json",
            json_error=JSONDecodeError("bad", "not json", 0),
        )
    )
    with pytest.raises(UnexpectedResponse, match="Expected JSON"):
        asyncio.run(client._request_json("GET", "/api/test"))


def test_transport_raw_response_parses_json_text_and_empty_bodies() -> None:
    """Raw requests should expose status plus parsed JSON, plain text or None."""
    session = _Session()
    session.request_responses.extend(
        [
            _Response(202, text='{"data": "OK"}'),
            _Response(202, text="plain response"),
            _Response(204, text=""),
        ]
    )
    client = _client(session)

    assert asyncio.run(client._request_raw("POST", "/one", json_body={})) == (
        202,
        {"data": "OK"},
    )
    assert asyncio.run(client._request_raw("POST", "/two")) == (202, "plain response")
    assert asyncio.run(client._request_raw("POST", "/three")) == (204, None)


def test_transport_timeout_wrapper_sanitizes_aiohttp_errors() -> None:
    """Aiohttp client errors should be mapped without raw endpoint details."""
    client = _client(_Session())

    async def _raise_client_error() -> None:
        raise api_transport_module.ClientError(
            "http://192.0.2.1 Authorization: Bearer token"
        )

    with pytest.raises(CannotConnect) as err:
        asyncio.run(client._request_with_timeout(_raise_client_error))

    assert "UniFi Drive host" in str(err.value)
    assert "192.0.2.1" not in str(err.value)
    assert "token" not in str(err.value)


def test_login_primes_csrf_and_captures_cookie() -> None:
    """Session login should prime CSRF, submit credentials and keep TOKEN cookie."""
    session = _Session()
    session.get_responses.append(_Response(200, headers={"x-updated-csrf-token": "csrf"}))
    session.post_responses.append(
        _Response(
            200,
            payload={"unique_id": "user-id"},
            headers={"Set-Cookie": ["TOKEN=token-value; path=/; httponly"]},
        )
    )
    client = _client(session)

    asyncio.run(client.async_login())

    assert client._authenticated is True
    assert client._csrf_token == "csrf"
    assert client._token_cookie == "token-value"
    assert client._login_data == {"unique_id": "user-id"}
    assert session.requests[-1][2]["headers"]["X-CSRF-Token"] == "csrf"


def test_login_handles_api_key_missing_credentials_and_bad_payloads() -> None:
    """Login should no-op for API keys and reject incomplete session auth."""
    api_key_client = _client(username="", password="", api_key="key")
    asyncio.run(api_key_client.async_login())
    assert api_key_client._authenticated is True

    with pytest.raises(InvalidAuth):
        asyncio.run(_client(username="", password="").async_login())

    session = _Session()
    session.get_responses.append(_Response(200))
    session.post_responses.append(
        _Response(200, json_error=JSONDecodeError("bad", "", 0))
    )
    client = _client(session)
    asyncio.run(client.async_login())
    assert client._login_data is None
    assert client._authenticated is True


def test_login_response_maps_invalid_auth_and_http_failures() -> None:
    """Login response handling should preserve auth and HTTP failure semantics."""
    client = _client(_Session())

    with pytest.raises(InvalidAuth):
        asyncio.run(client._consume_login_response(_Response(403)))

    with pytest.raises(CannotConnect) as err:
        asyncio.run(
            client._consume_login_response(
                _Response(500, text="password=secret host=192.0.2.44")
            )
        )
    assert "secret" not in str(err.value)
    assert "192.0.2.44" not in str(err.value)


def test_auth_identifier_and_permission_helpers_cover_nested_payloads() -> None:
    """Auth helpers should find stable device ids and permission hints."""
    client = _client(_Session())
    client._system_info = {
        "devices": {
            "unifiOS": [
                "bad",
                {"macAddress": "AA-BB-CC-DD-EE-FF"},
            ]
        },
        "id": "fallback-id",
    }
    client._login_data = {
        "id": "account-id",
        "scopes": ["edit:os-settings:poweroff"],
        "ucorePermission": {"hasPoweroffConsolePermission": False},
    }

    assert client.device_unique_id == "aa:bb:cc:dd:ee:ff"
    assert client.device_scoped_unique_ids == ("aa:bb:cc:dd:ee:ff",)
    assert client.poweroff_permission_hint is True

    client._system_info = {"hardware": {"macAddress": "not-a-mac"}, "id": "system-id"}
    assert client.device_unique_id == "system-id"
    client._login_data = {"scopes": [], "ucorePermission": {}}
    assert client.poweroff_permission_hint is False


def test_storage_read_retries_auth_and_keeps_system_metadata() -> None:
    """Storage reads should retry expired auth and attach system metadata."""
    client = _client(_Session())
    calls: list[tuple[str, str]] = []
    client._authenticated = True

    async def _request_json(method: str, path: str) -> dict[str, Any]:
        calls.append((method, path))
        if len(calls) == 1:
            raise InvalidAuth("expired")
        if path.endswith("/storage"):
            return {"fan": {"mode": "cool"}}
        if path == NETWORK_IO_PATH:
            return {"receiveKBPS": 2.5, "transmitKBPS": 1.5}
        return {"hardware": {"firmwareVersion": "v1.2.3"}}

    async def _login() -> None:
        client._authenticated = True

    client._request_json = _request_json
    client.async_login = _login

    data = asyncio.run(client.async_get_storage())

    assert data["_system"] == {"hardware": {"firmwareVersion": "v1.2.3"}}
    assert data["_network_io"] == {"receiveKBPS": 2.5, "transmitKBPS": 1.5}
    assert client._system_info == data["_system"]
    assert client.native_fan_mode == "Cooling"
    assert calls == [
        ("GET", "/proxy/drive/api/v2/storage"),
        ("GET", "/proxy/drive/api/v2/storage"),
        ("GET", "/api/system"),
        ("GET", NETWORK_IO_PATH),
        ("GET", "/proxy/drive/api/v2/systems/device-info"),
    ]


def test_storage_read_tolerates_missing_system_metadata() -> None:
    """Storage reads should remain usable when system metadata fails."""
    client = _client(_Session())
    client._authenticated = True

    async def _request_json(_method: str, path: str) -> dict[str, Any]:
        if path.endswith("/storage"):
            return {"storage": True}
        raise CannotConnect("offline")

    client._request_json = _request_json
    data = asyncio.run(client.async_get_storage())

    assert data == {"storage": True}
    assert client._system_info is None


def test_system_power_actions_check_permission_and_retry_auth() -> None:
    """Power actions should honor permission hints and retry expired sessions once."""
    client = _client(_Session())
    client._authenticated = True
    client._login_data = {"scopes": []}

    with pytest.raises(InvalidAuth, match="permission"):
        asyncio.run(client.async_poweroff())

    calls: list[str] = []
    client._login_data = {"isSuperAdmin": True}

    async def _request_no_json(method: str, path: str) -> None:
        calls.append(f"{method} {path}")
        if len(calls) == 1:
            raise InvalidAuth("expired")

    async def _login() -> None:
        client._login_data = {"isSuperAdmin": True}

    client._request_no_json = _request_no_json
    client.async_login = _login

    asyncio.run(client.async_reboot())
    assert calls == [f"POST {REBOOT_PATH}", f"POST {REBOOT_PATH}"]


def test_backup_read_and_run_cover_optional_endpoint_states() -> None:
    """Backup endpoints should handle supported, unsupported and failed cases."""
    client = _client(_Session())
    client._authenticated = True

    async def _request_raw_read(method: str, path: str, *, json_body=None):
        assert method == "GET"
        assert json_body is None
        return 200, {"data": [{"id": "task-1", "name": "Nightly"}]}

    client._request_raw = _request_raw_read
    assert asyncio.run(client.async_get_backup_tasks())[0]["id"] == "task-1"
    assert client.backup_tasks_read_supported is True

    client._backup_tasks_read_supported = False
    assert asyncio.run(client._async_get_backup_tasks_once()) == []

    async def _request_raw_404(*_args, **_kwargs):
        return 404, {"error": "missing"}

    client._backup_tasks_read_supported = None
    client._request_raw = _request_raw_404
    assert asyncio.run(client._async_get_backup_tasks_once()) == []
    assert client.backup_tasks_read_supported is False

    async def _request_raw_500(*_args, **_kwargs):
        return 500, {"error": "down"}

    client._backup_tasks_read_supported = None
    client._request_raw = _request_raw_500
    assert asyncio.run(client._async_get_backup_tasks_once()) == []

    with pytest.raises(UnexpectedResponse):
        asyncio.run(client.async_run_backup_task(""))

    async def _request_raw_run_ok(method: str, path: str, *, json_body=None):
        assert method == "POST"
        assert path.endswith("/task-1")
        assert json_body == {}
        return 200, {"data": "QUEUED"}

    client._request_raw = _request_raw_run_ok
    asyncio.run(client.async_run_backup_task(" task-1 "))

    async def _request_raw_run_unsupported(*_args, **_kwargs):
        return 405, {"error": "unsupported"}

    client._request_raw = _request_raw_run_unsupported
    with pytest.raises(UnsupportedFeature):
        asyncio.run(client._async_run_backup_task_once("task-1"))

    async def _request_raw_run_failed(*_args, **_kwargs):
        return 500, {"error": "failed"}

    client._request_raw = _request_raw_run_failed
    with pytest.raises(UnsupportedFeature):
        asyncio.run(client._async_run_backup_task_once("task-1"))


def test_backup_and_update_retry_expired_auth() -> None:
    """Backup and update public actions should retry InvalidAuth once."""
    client = _client(_Session())
    client._authenticated = True
    calls = {"login": 0, "backup": 0, "update": 0}

    async def _login() -> None:
        calls["login"] += 1
        client._authenticated = True

    async def _backup_once() -> list[dict[str, Any]]:
        calls["backup"] += 1
        if calls["backup"] == 1:
            raise InvalidAuth("expired")
        return [{"id": "task"}]

    async def _update_once(*_args: Any, **_kwargs: Any) -> None:
        calls["update"] += 1
        if calls["update"] == 1:
            raise InvalidAuth("expired")

    client.async_login = _login
    client._async_get_backup_tasks_once = _backup_once
    client._async_update_action_once = _update_once

    assert asyncio.run(client.async_get_backup_tasks()) == [{"id": "task"}]
    asyncio.run(client.async_install_unifi_os_update())
    assert calls == {"login": 2, "backup": 2, "update": 2}


def test_fan_read_and_write_optional_endpoint_states() -> None:
    """Fan endpoints should handle cached, unsupported and supported states."""
    client = _client(_Session())
    client._last_fan_mode = "Balance"
    client._fan_mode_read_supported = False
    assert asyncio.run(client._async_get_fan_mode_once()) == "Balance"

    async def _request_raw_404(*_args, **_kwargs):
        return 404, {"error": "missing"}

    client._fan_mode_read_supported = None
    client._request_raw = _request_raw_404
    assert asyncio.run(client._async_get_fan_mode_once()) == "Balance"
    assert client.fan_mode_read_supported is False

    async def _request_raw_read_ok(method: str, path: str, *, json_body=None):
        assert method == "GET"
        assert path == FAN_CONTROL_PATH
        return 200, {"thermal": {"mode": "quiet"}}

    client._fan_mode_read_supported = None
    client._request_raw = _request_raw_read_ok
    assert asyncio.run(client._async_get_fan_mode_once()) == "Quiet"
    assert client.fan_mode_read_supported is True

    client._fan_mode_write_supported = False
    with pytest.raises(UnsupportedFeature):
        asyncio.run(client._async_set_fan_mode_once("Cooling"))

    writes: list[dict[str, Any]] = []

    async def _request_raw_write_ok(method: str, path: str, *, json_body=None):
        assert method == "PUT"
        assert path == FAN_CONTROL_PATH
        writes.append(json_body)
        return 200, {"profile": "cooling"}

    client._fan_mode_write_supported = None
    client._request_raw = _request_raw_write_ok
    client._authenticated = True
    assert asyncio.run(client.async_set_fan_mode("cool")) == "Cooling"
    assert writes == [{"profile": "cooling"}]
    assert client.fan_mode_write_supported is True
    assert client.fan_mode_write_payload_hint == "profile_only"

    with pytest.raises(UnexpectedResponse):
        asyncio.run(client.async_set_fan_mode("invalid"))


def test_fan_write_failures_and_auth_retry() -> None:
    """Fan write should classify missing endpoints and retry expired auth."""
    client = _client(_Session())

    async def _request_raw_missing(*_args, **_kwargs):
        return 404, {"error": "missing"}

    client._request_raw = _request_raw_missing
    with pytest.raises(UnsupportedFeature):
        asyncio.run(client._async_set_fan_mode_once("Cooling"))
    assert client.fan_mode_write_supported is False

    client._fan_mode_write_supported = None

    async def _request_raw_failed(*_args, **_kwargs):
        return 500, {"error": "failed"}

    client._request_raw = _request_raw_failed
    with pytest.raises(UnsupportedFeature):
        asyncio.run(client._async_set_fan_mode_once("Cooling"))

    calls = {"login": 0, "set": 0, "get": 0, "control": 0}

    async def _login() -> None:
        calls["login"] += 1
        client._authenticated = True

    async def _set_once(_mode: str) -> str:
        calls["set"] += 1
        if calls["set"] == 1:
            raise InvalidAuth("expired")
        return "Quiet"

    async def _get_once() -> str:
        calls["get"] += 1
        if calls["get"] == 1:
            raise InvalidAuth("expired")
        return "Balance"

    async def _request_json(_method: str, _path: str) -> dict[str, Any]:
        calls["control"] += 1
        if calls["control"] == 1:
            raise InvalidAuth("expired")
        return {"profile": "cooling"}

    client.async_login = _login
    client._async_set_fan_mode_once = _set_once
    client._async_get_fan_mode_once = _get_once
    client._request_json = _request_json

    client._authenticated = True
    assert asyncio.run(client.async_set_fan_mode("quiet")) == "Quiet"
    client._authenticated = True
    assert asyncio.run(client.async_get_fan_mode()) == "Balance"
    client._authenticated = True
    assert asyncio.run(client.async_get_fan_control()) == {"profile": "cooling"}
    assert client.native_fan_mode == "Cooling"
    assert calls == {"login": 3, "set": 2, "get": 2, "control": 2}


def test_fan_read_edge_paths_and_version_helpers() -> None:
    """Fan helpers should handle HTTP failures and malformed version payloads."""
    client = _client(_Session())
    client._last_fan_mode = "Balance"
    client._fan_mode_read_supported = None

    async def _request_raw_http_error(*_args, **_kwargs):
        return 500, {"error": "down"}

    client._request_raw = _request_raw_http_error
    assert asyncio.run(client._async_get_fan_mode_once()) == "Balance"

    async def _request_raw_without_mode(*_args, **_kwargs):
        return 200, {"fan": {"profile": "unknown"}}

    client._request_raw = _request_raw_without_mode
    assert asyncio.run(client._async_get_fan_mode_once()) == "Balance"

    assert client._read_version_string({"hardware": {"firmwareVersion": 42}}, ("hardware", "firmwareVersion")) is None
    assert client._read_drive_controller_version({"apps": {"controllers": "bad"}}) is None
    assert client._read_drive_controller_version(
        {
            "apps": {
                "controllers": [
                    "invalid",
                    {"name": "Protect", "version": "1.0.0"},
                    {"name": "Drive", "version": ""},
                ]
            }
        }
    ) is None
    assert client._version_lt("unknown", "5.1.0") is False
    assert client._walk_for_fan_mode([{"fan": {"profile": "invalid"}}], context="fan") is None


def test_backup_retry_and_payload_edge_paths() -> None:
    """Backup helpers should retry auth once and normalize malformed payloads."""
    client = _client(_Session())
    client._authenticated = True
    calls = {"login": 0, "run": 0}

    async def _login() -> None:
        calls["login"] += 1
        client._authenticated = True

    async def _run_once(_task_id: str) -> None:
        calls["run"] += 1
        if calls["run"] == 1:
            raise InvalidAuth("expired")

    client.async_login = _login
    client._async_run_backup_task_once = _run_once
    asyncio.run(client.async_run_backup_task("task-1"))
    assert calls == {"login": 1, "run": 2}

    async def _request_raw_run_ok(*_args, **_kwargs):
        return 200, {"data": "DONE"}

    client._request_raw = _request_raw_run_ok
    asyncio.run(client._async_run_backup_task_once("task-1"))

    assert client._extract_backup_tasks({"data": "not-a-list"}) == []
    assert client._extract_backup_tasks({"data": [123, {}]}) == [
        {
            "id": "task_2",
            "name": "Backup Task 2",
            "raw": {},
        }
    ]


def test_update_action_paths_and_system_power_paths() -> None:
    """Public update and system actions should call the expected endpoints."""
    client = _client(_Session())
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    async def _request_raw(method: str, path: str, *, json_body=None):
        calls.append((method, path, json_body))
        return 202, {"data": "OK"}

    async def _request_no_json(method: str, path: str) -> None:
        calls.append((method, path, None))

    client._request_raw = _request_raw
    client._request_no_json = _request_no_json
    client._login_data = {"isSuperAdmin": True}
    client._authenticated = True

    asyncio.run(client.async_install_unifi_os_update())
    asyncio.run(client.async_install_drive_update())
    asyncio.run(client.async_poweroff())

    assert calls[0] == ("POST", "/api/firmware/update", {})
    assert calls[1] == ("POST", "/api/applications/drive/update", {})
    assert calls[2] == ("POST", POWEROFF_PATH, None)
