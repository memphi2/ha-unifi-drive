"""Exercise HTTP security boundaries with real local aiohttp servers."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["read", "write", "login", "root"])
@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
async def test_console_redirects_never_forward_credentials(
    aiohttp_server, socket_enabled, operation: str, status: int
) -> None:
    """Neither credential headers nor login bodies may reach a redirect target."""
    from aiohttp import ClientSession, TCPConnector, ThreadedResolver, web

    from custom_components.unifi_unas.api import CannotConnect, UnifiUnasApiClient

    received = []

    async def sink(request):
        received.append(request)
        return web.json_response({})

    sink_app = web.Application()
    sink_app.router.add_route("*", "/sink", sink)
    target = await aiohttp_server(sink_app)

    async def source(request):
        if request.path == "/" and operation != "root":
            return web.json_response({})
        return web.Response(status=status, headers={"Location": str(target.make_url("/sink"))})

    source_app = web.Application()
    source_app.router.add_route("*", "/{path:.*}", source)
    origin = await aiohttp_server(source_app)
    # Loopback literals need no DNS or optional resolver background threads.
    async with ClientSession(connector=TCPConnector(resolver=ThreadedResolver())) as session:
        client = UnifiUnasApiClient(
            session, host=origin.host, port=origin.port, use_ssl=False,
            username="test-user" if operation == "login" else "",
            password="test-pass" if operation == "login" else "",
            api_key=None if operation == "login" else "test-api-key",
        )
        if operation == "root":
            await client._prime_csrf_token()
        else:
            with pytest.raises(CannotConnect, match="redirected"):
                if operation == "read":
                    await client._request_json("GET", "/api/test")
                elif operation == "write":
                    await client._request_raw("PUT", "/api/test", json_body={"enabled": True})
                else:
                    await client.async_login()
    assert received == []
