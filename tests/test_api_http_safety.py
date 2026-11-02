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


@pytest.mark.parametrize("operation", ["read", "raw", "no_json", "login", "root", "error"])
@pytest.mark.parametrize("encoding", ["plain", "chunked", "gzip"])
async def test_response_limits_and_recovery(aiohttp_server, socket_enabled, monkeypatch, operation, encoding):
    """Limit every body path, including decompressed streams, without poisoning the client."""
    import gzip
    from aiohttp import ClientSession, TCPConnector, ThreadedResolver, web
    from custom_components.unifi_unas import api_transport
    from custom_components.unifi_unas.api import UnifiUnasApiClient, UnexpectedResponse

    monkeypatch.setattr(api_transport, "MAX_RESPONSE_BYTES", 1024)
    oversized = True

    async def source(request):
        if request.path == "/" and operation != "root":
            return web.json_response({})
        body = b'{"value":"' + b"x" * (2048 if oversized else 20) + b'"}'
        status = 500 if operation == "error" and oversized else 200
        if encoding == "chunked":
            reply = web.StreamResponse(status=status)
            reply.enable_chunked_encoding()
            await reply.prepare(request)
            await reply.write(body[:512])
            await reply.write(body[512:])
            await reply.write_eof()
            return reply
        headers = {"Content-Encoding": "gzip"} if encoding == "gzip" else {}
        return web.Response(body=gzip.compress(body) if encoding == "gzip" else body,
                            status=status, headers=headers)

    app = web.Application()
    app.router.add_route("*", "/{path:.*}", source)
    server = await aiohttp_server(app)
    async with ClientSession(connector=TCPConnector(resolver=ThreadedResolver())) as session:
        client = UnifiUnasApiClient(session, host=server.host, port=server.port, use_ssl=False,
                                    username="test-user", password="test-pass")

        async def call():
            if operation == "login":
                return await client.async_login()
            if operation == "root":
                return await client._prime_csrf_token()
            if operation == "raw":
                return await client._request_raw("PUT", "/test")
            if operation == "no_json":
                return await client._request_no_json("POST", "/test")
            return await client._request_json("GET", "/test")

        with pytest.raises(UnexpectedResponse, match="safety limit") as error:
            await call()
        assert "xxxxxxxx" not in str(error.value)
        oversized = False
        await call()


async def test_response_limit_accepts_exact_boundary(aiohttp_server, socket_enabled, monkeypatch):
    from aiohttp import ClientSession, TCPConnector, ThreadedResolver, web
    from custom_components.unifi_unas import api_transport

    monkeypatch.setattr(api_transport, "MAX_RESPONSE_BYTES", 1024)

    async def source(request):
        return web.Response(body=b"x" * 1024)

    app = web.Application()
    app.router.add_get("/", source)
    server = await aiohttp_server(app)
    async with ClientSession(connector=TCPConnector(resolver=ThreadedResolver())) as session:
        async with session.get(server.make_url("/")) as response:
            assert len(await api_transport.read_response_body(response)) == 1024
