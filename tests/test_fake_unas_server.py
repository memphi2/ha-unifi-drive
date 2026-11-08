"""Exercise complete client sessions against a stateful local HTTP server."""

from contextlib import asynccontextmanager

import pytest

from tests.fake_unas_server import FakeUnasServer


@asynccontextmanager
async def connected_client(aiohttp_server):
    from aiohttp import ClientSession, TCPConnector, ThreadedResolver
    from custom_components.unifi_unas.api import UnifiUnasApiClient

    fake = FakeUnasServer()
    server = await aiohttp_server(fake.app)
    async with ClientSession(connector=TCPConnector(resolver=ThreadedResolver())) as session:
        yield fake, UnifiUnasApiClient(session, host=server.host, port=server.port,
                                      use_ssl=False, username="test-user", password="test-pass")
    assert session.closed


async def test_session_cookie_expiry_and_identity(aiohttp_server, socket_enabled):
    async with connected_client(aiohttp_server) as (server, client):
        assert (await client.async_check_connection())["readThroughput"] == "12 MB/s"
        identity = client.device_scoped_unique_ids
        assert identity == ("synthetic-unas",)
        await client.async_get_storage()
        assert server.login_count == 1
        server.expire_session()
        await client.async_get_storage()
        assert server.login_count == 2
        assert client.device_scoped_unique_ids == identity


async def test_failed_reauthentication_is_bounded_then_recovers(aiohttp_server, socket_enabled):
    from custom_components.unifi_unas.api_errors import InvalidAuth

    async with connected_client(aiohttp_server) as (server, client):
        await client.async_check_connection()
        server.expire_session()
        server.reject_login = True
        with pytest.raises(InvalidAuth):
            await client.async_get_storage()
        assert server.login_count == 2
        server.reject_login = False
        assert await client.async_get_storage()
        assert server.login_count == 3


async def test_malformed_core_response_recovers_without_login_loop(aiohttp_server, socket_enabled):
    from custom_components.unifi_unas.api_errors import UnexpectedResponse
    from custom_components.unifi_unas.const import DRIVE_STORAGE_PATH

    async with connected_client(aiohttp_server) as (server, client):
        await client.async_check_connection()
        server.malformed.add(DRIVE_STORAGE_PATH)
        with pytest.raises(UnexpectedResponse):
            await client.async_get_storage()
        server.malformed.clear()
        assert await client.async_get_storage()
        assert server.login_count == 1


async def test_slow_optional_metadata_and_unsupported_snapshots_are_isolated(
    aiohttp_server, socket_enabled, monkeypatch,
):
    from custom_components.unifi_unas.const import SYSTEM_PATH, NETWORK_IO_PATH
    from custom_components.unifi_unas.snapshot_paths import SNAPSHOT_SETTINGS_PATH

    monkeypatch.setattr("custom_components.unifi_unas.api_storage._METADATA_REQUEST_TIMEOUT", 0.02)
    async with connected_client(aiohttp_server) as (server, client):
        server.delays[SYSTEM_PATH] = 0.1
        server.statuses[NETWORK_IO_PATH] = 404
        data = await client.async_get_storage()
        assert data["readThroughput"] == "12 MB/s"
        assert "_system" not in data
        server.statuses[SNAPSHOT_SETTINGS_PATH] = 404
        assert await client.async_get_snapshot_settings() == []
        assert client.snapshot_settings_read_supported is False
        assert await client.async_get_snapshot_settings() == []
        assert server.calls[("GET", SNAPSHOT_SETTINGS_PATH)] == 1
        assert await client.async_get_storage()
        server.delays.clear()
        server.statuses.clear()
        assert "_system" in await client.async_get_storage()
        assert server.login_count == 1


async def test_core_timeout_keeps_client_usable(aiohttp_server, socket_enabled):
    from custom_components.unifi_unas.api_errors import CannotConnect
    from custom_components.unifi_unas.const import DRIVE_STORAGE_PATH

    async with connected_client(aiohttp_server) as (server, client):
        await client.async_check_connection()
        client._timeout = 0.02
        server.delays[DRIVE_STORAGE_PATH] = 0.1
        with pytest.raises(CannotConnect) as error:
            await client.async_get_storage()
        assert isinstance(error.value.__cause__, TimeoutError)
        server.delays.clear()
        assert await client.async_get_storage()
        assert server.login_count == 1


@pytest.mark.parametrize("core_status", [200, 401, 403])
async def test_api_key_device_info_complements_restricted_core_metadata(
    aiohttp_server, socket_enabled, core_status,
):
    from custom_components.unifi_unas.const import DRIVE_DEVICE_INFO_PATH, SYSTEM_PATH
    from custom_components.unifi_unas.system_metadata import drive_version, unifi_os_version
    from custom_components.unifi_unas.storage_system import _cpu_temperature, _system_ip, _system_uptime_hours

    async with connected_client(aiohttp_server) as (server, client):
        server.api_key = "synthetic-key"
        client._api_key = server.api_key
        client._use_api_key_auth = True
        server.payloads[SYSTEM_PATH] = {"status": "online"}
        if core_status != 200:
            server.statuses[SYSTEM_PATH] = core_status
        server.payloads[DRIVE_DEVICE_INFO_PATH] = {
            "version": "4.3.6", "firmwareVersion": "5.1.10", "cpu": {"temperature": 42},
            "startupTime": "2026-01-01T00:00:00Z",
            "networkInterfaces": [{"ipAddress": "192.0.2.10"}],
        }
        data = await client.async_check_connection()
        assert data["readThroughput"] == "12 MB/s"
        assert unifi_os_version(data) == "5.1.10"
        assert drive_version(data) == "4.3.6"
        assert _cpu_temperature(data) == 42
        assert _system_ip(data) == "192.0.2.10"
        assert _system_uptime_hours(data) is not None
        assert server.login_count == 0
        server.statuses[DRIVE_DEVICE_INFO_PATH] = 404
        data = await client.async_get_storage()
        assert "_device_info" not in data
        assert data["readThroughput"] == "12 MB/s"
