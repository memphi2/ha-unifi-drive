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
                target = _snapshot_target_with_controls()
                for count in range(12):
                    coordinator.client.snapshot_settings = [
                        {**target, "id": f"synthetic-target-{count % 3}", "total_count": count}
                    ]
                    coordinator.async_set_updated_data(await coordinator._async_update_data())
                    await hass.async_block_till_done()
                coordinator.client.snapshot_settings = [target]
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


async def test_continuously_loaded_runtime_and_distinct_targets(hass, caplog):
    """Separate intentional registry retention from cache or per-refresh leaks."""
    from homeassistant.helpers import entity_registry as er
    from custom_components.unifi_unas.snapshot_types import snapshot_target_key
    from scripts.check_runtime_soak import steady_errors
    from tests.test_snapshot_control_entity_states import (
        _SnapshotIntegrationClient, _snapshot_target_with_controls, _setup_snapshot_controls,
        _snapshot_entity_ids_by_unique_id,
    )

    refreshes = int(os.environ.get("UNAS_STEADY_REFRESHES", "60"))
    targets = int(os.environ.get("UNAS_STEADY_TARGETS", "12"))
    target = _snapshot_target_with_controls()
    client = _SnapshotIntegrationClient([target])
    entry, _ = await _setup_snapshot_controls(hass, client)
    coordinator = entry.runtime_data
    coordinator.update_interval = None
    entities_per_target = len(_snapshot_entity_ids_by_unique_id(hass, entry))
    assert entities_per_target > 0
    registry = er.async_get(hass)

    async def refresh(index):
        client.snapshot_settings = [{**target, "id": f"distinct-target-{index}", "total_count": index}]
        coordinator.async_set_updated_data(await coordinator._async_update_data())
        await hass.async_block_till_done()
        key = snapshot_target_key(client.snapshot_settings[0])
        for cache in (coordinator.snapshot_inventory, coordinator.snapshot_inventory_errors,
                      coordinator.snapshot_inventory_skip_reasons):
            assert set(cache) <= {key}
        client.inventory_requests.clear()
        caplog.clear()

    # Each real target legitimately owns an entity group, retained for automations.
    for index in range(targets):
        await refresh(index)
        assert len(_snapshot_entity_ids_by_unique_id(hass, entry)) == entities_per_target * (index + 2)
    retained_entities = len(er.async_entries_for_config_entry(registry, entry.entry_id))
    samples = []
    tracing = tracemalloc.is_tracing()
    if not tracing:
        tracemalloc.start()
    try:
        for index in range(refreshes + 10):
            await refresh(index % targets)
            if index < 10 or (index - 10) % max(1, refreshes // 5):
                continue
            gc.collect()
            memory = tracemalloc.take_snapshot()
            own_bytes = sum(stat.size for stat in memory.statistics("filename")
                            if "/custom_components/unifi_unas/" in stat.traceback[0].filename)
            try:
                rss = int(Path("/proc/self/statm").read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE")
            except (OSError, ValueError, IndexError, AttributeError):
                rss = None
            samples.append({
                "phase": "steady", "integration_bytes": own_bytes, "rss_bytes": rss,
                "tasks": len(asyncio.all_tasks()),
                "timers": sum(not handle.cancelled() for handle in hass.loop._scheduled),
                "listeners": len(coordinator._listeners),
                "registry_entities": len(er.async_entries_for_config_entry(registry, entry.entry_id)),
                "inventory_entries": len(coordinator.snapshot_inventory),
            })
        assert all(item["registry_entities"] == retained_entities for item in samples)
        errors = steady_errors(samples)
        report = {"refreshes": refreshes, "targets": targets, "samples": samples, "errors": errors,
                  "retained_entities": retained_entities, "entities_per_target": entities_per_target,
                  "measurement": "Single loaded entry; distinct-target retention followed by repeated target reuse"}
        if output := os.environ.get("UNAS_STEADY_REPORT"):
            Path(output).write_text(json.dumps(report, indent=2) + "\n")
        assert not errors, errors
    finally:
        if not tracing:
            tracemalloc.stop()
        assert await hass.config_entries.async_unload(entry.entry_id)
    assert not coordinator._listeners
