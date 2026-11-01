"""Verify short-lived config-flow sessions use HA's connector without leaks."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["success", "connection", "auth", "invalid", "cancel"])
async def test_validation_detaches_sessions_on_every_exit(hass, monkeypatch, outcome: str) -> None:
    from aiohttp import ThreadedResolver
    import custom_components
    from homeassistant.helpers import aiohttp_client
    from homeassistant.helpers.aiohttp_client import async_create_clientsession

    custom_components.__path__.append(str(Path(__file__).resolve().parents[1] / "custom_components"))
    from custom_components.unifi_unas import config_flow_validation as validation
    from custom_components.unifi_unas.api import CannotConnect, InvalidAuth, UnexpectedResponse

    # Older HA creates a pycares worker even though this test makes no requests.
    if hasattr(aiohttp_client, "AsyncResolver"):
        monkeypatch.setattr(aiohttp_client, "AsyncResolver", ThreadedResolver)
    warmup = async_create_clientsession(hass, auto_cleanup=False)
    connector = warmup.connector
    warmup.detach()
    listeners = hass.bus.async_listeners()
    sessions = []
    errors = {"connection": CannotConnect, "auth": InvalidAuth, "cancel": asyncio.CancelledError}

    class Client:
        device_unique_ids = ("test-device",)
        device_scoped_unique_ids = ("test-device",)

        def __init__(self, session, **kwargs):
            sessions.append(session)

        async def async_check_connection(self):
            if outcome in errors:
                raise errors[outcome]()
            return {"pools": {} if outcome == "invalid" else []}

    with patch.object(validation, "UnifiUnasApiClient", Client):
        for _ in range(10):
            call = validation.async_validate_input(hass, {
                "host": "console.example", "port": 443, "ssl": True, "verify_ssl": True,
            })
            if outcome == "success":
                assert (await call)["unique_id"] == "test-device"
            else:
                with pytest.raises(errors.get(outcome, UnexpectedResponse)):
                    await call
    assert all(session.closed for session in sessions)
    assert connector is not None and not connector.closed
    assert hass.bus.async_listeners() == listeners
