"""Unit tests for API helper normalization/parsing logic."""

import asyncio

import pytest

from tests.api_client_stubs import UnifiUnasApiClient
from aiohttp import ClientError
from custom_components.unifi_unas.api import CannotConnect
from custom_components.unifi_unas.security import safe_error_text, safe_response_summary


def test_response_summaries_expose_shape_only() -> None:
    """Neither keys nor values of server responses belong in logs or repairs."""
    assert safe_response_summary({"private-user": "private-share"}) == "object response (1 fields)"
    assert safe_response_summary(["private-user"]) == "array response (1 items)"
    assert safe_response_summary("private-host") == "text response (12 characters)"
    assert safe_response_summary(None) == "empty response"
    assert safe_response_summary(42) == "scalar response"
    assert "private-user" not in safe_error_text('username="private-user"')


def test_normalize_fan_mode_variants() -> None:
    """Fan mode aliases should normalize to canonical HA options."""
    assert UnifiUnasApiClient._normalize_fan_mode("quiet") == "Quiet"
    assert UnifiUnasApiClient._normalize_fan_mode("cooling") == "Cooling"
    assert UnifiUnasApiClient._normalize_fan_mode("cool") == "Cooling"
    assert UnifiUnasApiClient._normalize_fan_mode("balanced") == "Balance"
    assert UnifiUnasApiClient._normalize_fan_mode("default") == "Balance"
    assert UnifiUnasApiClient._normalize_fan_mode("default_profile") == "Balance"
    assert UnifiUnasApiClient._normalize_fan_mode("performance") == "Cooling"
    assert UnifiUnasApiClient._normalize_fan_mode("  QUIET  ") == "Quiet"
    assert UnifiUnasApiClient._normalize_fan_mode("Default-Profile") == "Balance"
    assert UnifiUnasApiClient._normalize_fan_mode("unknown") is None
    assert UnifiUnasApiClient._normalize_fan_mode(123) is None


def test_extract_backup_tasks_from_list_payload() -> None:
    """Task list payload should map ids and names correctly."""
    payload = [
        {"id": "abc", "name": "Daily Backup"},
        {"task_id": "def", "taskName": "Weekly Backup"},
    ]

    tasks = UnifiUnasApiClient._extract_backup_tasks(payload)

    assert len(tasks) == 2
    assert tasks[0]["id"] == "abc"
    assert tasks[0]["name"] == "Daily Backup"
    assert tasks[1]["id"] == "def"
    assert tasks[1]["name"] == "Weekly Backup"


def test_extract_backup_tasks_with_fallback_fields() -> None:
    """Nested payload should support common id/name fallback keys."""
    payload = {
        "data": [
            {"uuid": "u1", "title": "Monthly"},
            {"_id": "u2"},
        ]
    }

    tasks = UnifiUnasApiClient._extract_backup_tasks(payload)

    assert [task["id"] for task in tasks] == ["u1", "u2"]
    assert tasks[0]["name"] == "Monthly"
    assert tasks[1]["name"] == "Backup Task 2"


def test_extract_backup_tasks_generates_stable_fallback_id() -> None:
    """Missing id fields should generate deterministic fallback task ids."""
    payload = {"tasks": [{"name": "No Id Task"}]}

    tasks = UnifiUnasApiClient._extract_backup_tasks(payload)

    assert len(tasks) == 1
    assert tasks[0]["id"] == "task_1"
    assert tasks[0]["name"] == "No Id Task"


def test_auth_prefers_session_when_credentials_and_api_key_are_present() -> None:
    """Username/password should take precedence over API key when both are set."""
    client = UnifiUnasApiClient(
        None,
        host="unas.local",
        username="user",
        password="pass",
        api_key="abc123",
    )

    assert client._use_api_key_auth is False
    assert client._authenticated is False
    assert "X-API-Key" not in client._headers()


def test_auth_uses_api_key_when_no_password_is_provided() -> None:
    """API key mode should stay active when no credentials are available."""
    client = UnifiUnasApiClient(
        None,
        host="unas.local",
        username="",
        password="",
        api_key="abc123",
    )

    assert client._use_api_key_auth is True
    assert client._authenticated is True
    assert client._headers()["X-API-Key"] == "abc123"


def test_base_url_brackets_ipv6_literals() -> None:
    """Runtime URLs should be valid when legacy entry data stores raw IPv6."""
    client = UnifiUnasApiClient(None, host="2001:0db8::1", port=8443)

    assert client.host == "[2001:db8::1]"
    assert client.base_url == "https://[2001:db8::1]:8443"
    assert client._url("/proxy/drive/api/v1/systems") == (
        "https://[2001:db8::1]:8443/proxy/drive/api/v1/systems"
    )


def test_base_url_keeps_bracketed_ipv6_default_port() -> None:
    """Already bracketed IPv6 hosts should keep a clean default-port URL."""
    client = UnifiUnasApiClient(None, host="[2001:db8::2]", port=443)

    assert client.host == "[2001:db8::2]"
    assert client.base_url == "https://[2001:db8::2]"


def test_partitioned_token_cookie_is_used_for_session_auth() -> None:
    """UniFi OS partitioned auth cookies should survive lightweight parsing."""
    client = UnifiUnasApiClient(
        None,
        host="unas.local",
        username="user",
        password="pass",
    )

    token = client._extract_set_cookie_value(
        "TOKEN=abc.def.ghi; path=/; expires=Sun, 14 Jun 2026 17:57:28 GMT; "
        "samesite=none; secure; httponly; partitioned",
        "TOKEN",
    )

    assert token == "abc.def.ghi"
    client._token_cookie = token
    assert client._headers()["Cookie"] == "TOKEN=abc.def.ghi"


def test_transport_client_errors_do_not_expose_host_or_raw_error() -> None:
    """Connection errors should not leak configured host, IPs or auth fragments."""
    client = UnifiUnasApiClient(None, host="192.0.2.44", api_key="abc123")

    async def _raise_client_error():
        raise ClientError(
            "https://192.0.2.44 Authorization: Bearer raw-token X-API-Key=abc123"
        )

    with pytest.raises(CannotConnect) as err:
        asyncio.run(client._request_with_timeout(_raise_client_error))
    message = str(err.value)

    assert "UniFi Drive host" in message
    assert "192.0.2.44" not in message
    assert "raw-token" not in message
    assert "abc123" not in message


def test_safe_error_text_redacts_credentials_and_network_identifiers() -> None:
    """Error text redaction should cover common response and header shapes."""
    redacted = safe_error_text(
        {
            "host": "192.0.2.44",
            "password": "secret-password",
            "token": "secret-token",
            "macAddress": "aa:bb:cc:dd:ee:ff",
            "message": "Authorization: Bearer raw-token",
            "detail": "GET https://unas.private.local:443/api?token=query-token",
        }
    )

    assert "192.0.2.44" not in redacted
    assert "secret-password" not in redacted
    assert "secret-token" not in redacted
    assert "aa:bb:cc:dd:ee:ff" not in redacted
    assert "raw-token" not in redacted
    assert "unas.private.local" not in redacted
    assert "query-token" not in redacted
    assert "https://<redacted>/api" in redacted


def test_safe_error_text_url_redaction_preserves_delimiters() -> None:
    """URL redaction should not swallow query, fragment or prose punctuation."""
    redacted = safe_error_text(
        "See (https://unas.private.local:443/api?token=query-token#frag), next."
    )

    assert "unas.private.local" not in redacted
    assert "query-token" not in redacted
    assert redacted == "See (https://<redacted>/api?token=<redacted>#frag), next."


def test_safe_error_text_redacts_bare_local_hostnames() -> None:
    """Plain local hostnames in exception messages should not leak."""
    redacted = safe_error_text(
        "Could not resolve unas.private.local:443; fallback nas.home.arpa timed out."
    )

    assert "unas.private.local" not in redacted
    assert "nas.home.arpa" not in redacted
    assert redacted == (
        "Could not resolve <redacted>; fallback <redacted> timed out."
    )


def test_safe_error_text_query_redaction_masks_composite_values() -> None:
    """Query tokens containing punctuation should be fully redacted."""
    redacted = safe_error_text(
        "GET https://unas.private.local/api?token=abc,def)&state=ghi,jkl#frag"
    )

    assert "abc" not in redacted
    assert "def" not in redacted
    assert "ghi" not in redacted
    assert "jkl" not in redacted
    assert redacted == (
        "GET https://<redacted>/api?token=<redacted>&state=<redacted>#frag"
    )


def test_safe_error_text_key_value_redaction_masks_ampersand_values() -> None:
    """Unquoted key-value secrets should not leak suffixes after URI delimiters."""
    redacted = safe_error_text(
        "password=abc&def token=ghi#jkl api_key=mno&pqr"
    )

    assert "abc" not in redacted
    assert "def" not in redacted
    assert "ghi" not in redacted
    assert "jkl" not in redacted
    assert "mno" not in redacted
    assert "pqr" not in redacted
    assert redacted == (
        "password=<redacted> token=<redacted> api_key=<redacted>"
    )


def test_device_unique_id_prefers_system_metadata_over_login_id() -> None:
    """Stable per-device identifiers should come from system metadata first."""
    client = UnifiUnasApiClient(None, host="unas.local", username="user", password="pass")
    client._system_info = {
        "hardware": {"serialNumber": "UNAS2-SN-1234"},
        "id": "system-id-ignored",
    }
    client._login_data = {"id": "account-id", "unique_id": "user-1234"}
    assert client.device_unique_id == "UNAS2-SN-1234"
    assert client.device_unique_ids == ("UNAS2-SN-1234", "user-1234", "account-id")
    assert client.device_scoped_unique_ids == ("UNAS2-SN-1234",)


def test_device_unique_id_falls_back_to_login_id_when_system_unknown() -> None:
    """Login IDs remain the fallback when system metadata has no device id."""
    client = UnifiUnasApiClient(None, host="unas.local", username="user", password="pass")
    client._login_data = {"id": "account-id"}
    client._system_info = {}
    assert client.device_unique_id == "account-id"


def test_device_unique_id_normalizes_system_mac_identifier() -> None:
    """MAC-derived identifiers should be stable across formatting variants."""
    client = UnifiUnasApiClient(None, host="unas.local", username="user", password="pass")
    client._system_info = {"macAddress": "AA-BB-CC-DD-EE-FF"}
    assert client.device_unique_id == "aa:bb:cc:dd:ee:ff"


def test_fan_mode_write_payloads_are_minimal_and_stable() -> None:
    """Fan-mode writes should try only the two known-safe payload shapes."""
    client = UnifiUnasApiClient(None, host="unas.local")
    payloads = client._fan_mode_write_payloads("cooling")
    assert payloads == (
        {"profile": "cooling"},
        {"profile": "cooling", "apply": True},
    )


def test_fan_mode_write_payloads_prefer_apply_on_older_firmware() -> None:
    """Older firmware hints should prioritize the apply payload first."""
    client = UnifiUnasApiClient(None, host="unas.local")
    client._system_info = {
        "hardware": {"firmwareVersion": "5.0.17"},
        "apps": {"controllers": [{"name": "drive", "version": "4.1.16"}]},
    }
    payloads = client._fan_mode_write_payloads("cooling")
    assert payloads[0] == {"profile": "cooling", "apply": True}
    assert payloads[1] == {"profile": "cooling"}


def test_fan_mode_write_payloads_use_runtime_hint_first() -> None:
    """A successful payload signature should be preferred on subsequent writes."""
    client = UnifiUnasApiClient(None, host="unas.local")
    client._fan_mode_write_payload_hint = "profile_apply"
    payloads = client._fan_mode_write_payloads("quiet")
    assert payloads[0] == {"profile": "quiet", "apply": True}
    assert payloads[1] == {"profile": "quiet"}
