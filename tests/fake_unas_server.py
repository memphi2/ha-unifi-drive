"""Stateful synthetic UniFi OS/Drive server, only for loopback tests."""

import asyncio
from collections import Counter


class FakeUnasServer:
    def __init__(self):
        from aiohttp import web
        from custom_components.unifi_unas.const import DRIVE_STORAGE_PATH, SYSTEM_PATH, NETWORK_IO_PATH
        from custom_components.unifi_unas.snapshot_paths import SNAPSHOT_SETTINGS_PATH

        self.app = web.Application()
        self.app.router.add_route("*", "/{path:.*}", self.handle)
        self.calls = Counter()
        self.login_count = 0
        self.generation = 0
        self.reject_login = False
        self.api_key = None
        self.statuses = {}
        self.delays = {}
        self.malformed = set()
        self.payloads = {
            DRIVE_STORAGE_PATH: {"pools": [], "readThroughput": "12 MB/s"},
            SYSTEM_PATH: {"systemId": "synthetic-unas", "hardware": {"firmwareVersion": "5.1.10"}},
            NETWORK_IO_PATH: {},
            SNAPSHOT_SETTINGS_PATH: {"data": []},
        }

    def expire_session(self):
        self.generation += 1

    async def handle(self, request):
        from aiohttp import web
        from custom_components.unifi_unas.const import LOGIN_PATH

        self.calls[(request.method, request.path)] += 1
        if delay := self.delays.get(request.path):
            await asyncio.sleep(delay)
        if request.path == "/":
            return web.Response(headers={"x-csrf-token": "synthetic-csrf"})
        if request.path == LOGIN_PATH:
            self.login_count += 1
            credentials = await request.json()
            if (self.reject_login or credentials.get("username") != "test-user"
                    or credentials.get("password") != "test-pass"
                    or request.headers.get("X-CSRF-Token") != "synthetic-csrf"):
                return web.Response(status=401)
            self.generation += 1
            response = web.json_response({"id": "synthetic-user"})
            response.set_cookie("TOKEN", f"synthetic-session-{self.generation}")
            return response
        key_authenticated = self.api_key is not None and request.headers.get("X-API-Key") == self.api_key
        if not key_authenticated and request.cookies.get("TOKEN") != f"synthetic-session-{self.generation}":
            return web.Response(status=401)
        if status := self.statuses.get(request.path):
            return web.Response(status=status)
        if request.path in self.malformed:
            return web.Response(text="synthetic malformed response", content_type="application/json")
        if request.path not in self.payloads:
            return web.Response(status=404)
        return web.json_response(self.payloads[request.path])
