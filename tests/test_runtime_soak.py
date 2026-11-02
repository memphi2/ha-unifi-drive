"""Observe bounded setup, recovery, snapshot churn and teardown resources."""

import asyncio
import gc
import json
import os
from pathlib import Path
import time
import tracemalloc
from unittest.mock import patch
import weakref


async def test_repeated_runtime_resources(hass, monkeypatch, caplog):
    from aiohttp import ThreadedResolver
    from homeassistant.helpers import aiohttp_client
    from homeassistant.setup import async_setup_component
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.unifi_unas.const import DOMAIN, CONF_SNAPSHOT_BUTTONS_ENABLED
    from custom_components.unifi_unas.api_errors import CannotConnect
    from scripts.check_runtime_soak import sample_errors
    from tests.test_core_monitoring_entity_states import _entry_data
    from tests.test_snapshot_control_entity_states import (
        _SnapshotIntegrationClient, _snapshot_target_with_controls,
    )

    class Client(_SnapshotIntegrationClient):
        offline = False

        async def async_get_storage(self):
            if self.offline:
                raise CannotConnect("Synthetic offline transition")
            return await super().async_get_storage()

    if hasattr(aiohttp_client, "AsyncResolver"):
        monkeypatch.setattr(aiohttp_client, "AsyncResolver", ThreadedResolver)
    assert await async_setup_component(hass, DOMAIN, {})
    entry = MockConfigEntry(domain=DOMAIN, title="UNAS", unique_id="soak-device",
                            data={**_entry_data(), CONF_SNAPSHOT_BUTTONS_ENABLED: True})
    entry.add_to_hass(hass)
    cycles = int(os.environ.get("UNAS_SOAK_CYCLES", "3"))
    idle = float(os.environ.get("UNAS_SOAK_IDLE", "0"))
    references, sessions, samples = [], [], []

    def create_client(session, **kwargs):
        sessions.append(weakref.ref(session))
        return Client([_snapshot_target_with_controls()])

    def snapshot(phase, coordinator=None):
        gc.collect()
        tasks = [task for task in asyncio.all_tasks() if not task.done()]
        memory = tracemalloc.take_snapshot()
        own_bytes = sum(stat.size for stat in memory.statistics("filename")
                        if "/custom_components/unifi_unas/" in stat.traceback[0].filename)
        try:
            rss = int(Path("/proc/self/statm").read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE")
        except (OSError, ValueError, IndexError, AttributeError):
            rss = None
        return {"phase": phase, "integration_bytes": own_bytes, "rss_bytes": rss,
                "tasks": len(tasks), "timers": sum(not handle.cancelled() for handle in hass.loop._scheduled),
                "listeners": len(coordinator._listeners) if coordinator else 0,
                "retained_coordinators": sum(ref() is not None for ref in references),
                "open_sessions": sum(ref() is not None and not ref().closed for ref in sessions),
                "owned_tasks": sum("/custom_components/unifi_unas/" in
                                   getattr(getattr(task.get_coro(), "cr_code", None), "co_filename", "")
                                   for task in tasks)}

    tracing = tracemalloc.is_tracing()
    if not tracing:
        tracemalloc.start()
    start_cpu, start_wall = time.process_time(), time.monotonic()
    try:
        with patch("custom_components.unifi_unas.UnifiUnasApiClient", side_effect=create_client):
            for cycle in range(cycles + 2):
                assert await hass.config_entries.async_setup(entry.entry_id)
                await hass.async_block_till_done()
                coordinator = entry.runtime_data
                references.append(weakref.ref(coordinator))
                if cycle >= 2:
                    samples.append(snapshot("loaded", coordinator))
                coordinator.client.offline = True
                coordinator.async_set_updated_data(await coordinator._async_update_data())
                coordinator.client.offline = False
                for count in range(4):
                    coordinator.client.snapshot_settings[0]["total_count"] = count
                    coordinator.async_set_updated_data(await coordinator._async_update_data())
                await hass.async_block_till_done()
                await asyncio.sleep(idle)
                if cycle >= 2:
                    samples.append(snapshot("recovered", coordinator))
                assert await hass.config_entries.async_unload(entry.entry_id)
                del coordinator
                await hass.async_block_till_done()
                caplog.clear()
                if cycle >= 2:
                    samples.append(snapshot("unloaded"))
        errors = sample_errors(samples)
        report = {"cycles": cycles, "idle_seconds": idle, "samples": samples, "errors": errors,
                  "cpu_seconds": time.process_time() - start_cpu,
                  "wall_seconds": time.monotonic() - start_wall,
                  "measurement": "Synthetic HA lifecycle with fake API, not a live NAS soak"}
        if output := os.environ.get("UNAS_SOAK_REPORT"):
            Path(output).write_text(json.dumps(report, indent=2) + "\n")
        assert not errors, errors
    finally:
        if not tracing:
            tracemalloc.stop()
