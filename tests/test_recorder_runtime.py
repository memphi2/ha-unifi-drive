"""Measure actual SQLite Recorder writes from integration entities."""

from __future__ import annotations

import pytest


@pytest.fixture
def persistent_database():
    return True


@pytest.fixture
def recorder_config(request):
    return {"auto_purge": False, "exclude": {"entities": getattr(request, "param", [])}}


async def counts(hass, recorder):
    """Flush events before querying the real database off the event loop."""
    from sqlalchemy import text

    await hass.async_block_till_done()
    await recorder.async_block_till_done()

    def query():
        with recorder.engine.connect() as connection:
            rows = dict(connection.execute(text(
                "SELECT m.entity_id, count(*) FROM states s "
                "JOIN states_meta m USING(metadata_id) GROUP BY m.entity_id"
            )).all())
            attributes = connection.execute(text(
                "SELECT count(*) FROM state_attributes"
            )).scalar_one()
            return rows, attributes

    return await hass.async_add_executor_job(query)


async def setup_monitoring(hass):
    from tests.test_core_monitoring_entity_states import (
        _MonitoringClient, _async_setup_monitoring_entry,
    )

    client = _MonitoringClient()
    entry = await _async_setup_monitoring_entry(hass, client)
    entry.runtime_data.update_interval = None
    return client, entry


async def refresh(hass, entry):
    coordinator = entry.runtime_data
    coordinator.async_set_updated_data(await coordinator._async_update_data())
    await hass.async_block_till_done()


async def test_idle_refreshes_do_not_write_states(recorder_mock, hass):
    """Polling identical device data must not grow recorded history."""
    _, entry = await setup_monitoring(hass)
    before = await counts(hass, recorder_mock)
    for _ in range(20):
        await refresh(hass, entry)
    assert await counts(hass, recorder_mock) == before
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("recorder_config", [[], [
    "sensor.unas_read_throughput", "sensor.unas_write_throughput",
]], indirect=True, ids=["full", "lean"])
async def test_throughput_history_profiles(recorder_mock, hass, recorder_config):
    """Exclusions remove history, not live readings or other storage history."""
    from tests.test_core_monitoring_entity_states import _entity_id_for_unique_id

    client, entry = await setup_monitoring(hass)
    read = _entity_id_for_unique_id(hass, entry, "device-1_read_throughput")
    used = _entity_id_for_unique_id(hass, entry, "device-1_used_storage")
    before, _ = await counts(hass, recorder_mock)
    for value in range(20, 30):
        client.storage["readThroughput"] = f"{value} MB/s"
        client.storage["pools"][0]["used"] += 1024**3 // 10
        await refresh(hass, entry)
    after, _ = await counts(hass, recorder_mock)
    assert hass.states.get(read).state not in {"unknown", "unavailable"}
    assert after.get(used, 0) > before.get(used, 0)
    if recorder_config["exclude"]["entities"]:
        assert read in recorder_config["exclude"]["entities"]
        assert read not in after
    else:
        assert after[read] - before[read] == 10
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_offline_cache_does_not_rewrite_unchanged_storage(recorder_mock, hass):
    from tests.test_core_monitoring_entity_states import _entity_id_for_unique_id

    client, entry = await setup_monitoring(hass)
    capacity = _entity_id_for_unique_id(hass, entry, "device-1_total_storage")
    online = _entity_id_for_unique_id(hass, entry, "device-1_device_online")
    before, _ = await counts(hass, recorder_mock)
    client.offline = True
    for _ in range(10):
        await refresh(hass, entry)
    client.offline = False
    await refresh(hass, entry)
    after, _ = await counts(hass, recorder_mock)
    assert after[capacity] == before[capacity]
    assert after[online] - before[online] == 2
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_snapshot_counts_do_not_duplicate_recorded_control_attributes(recorder_mock, hass):
    from tests.test_snapshot_control_entity_states import (
        _SnapshotIntegrationClient, _setup_snapshot_controls,
        _snapshot_target_with_controls,
    )

    target = _snapshot_target_with_controls()
    client = _SnapshotIntegrationClient([target])
    entry, controls = await _setup_snapshot_controls(hass, client)
    entry.runtime_data.update_interval = None
    await counts(hass, recorder_mock)

    async def control_attributes():
        from sqlalchemy import text

        await counts(hass, recorder_mock)
        def query():
            with recorder_mock.engine.connect() as connection:
                return connection.execute(text(
                    "SELECT count(DISTINCT s.attributes_id) FROM states s "
                    "JOIN states_meta m USING(metadata_id) WHERE m.entity_id = :entity"
                ), {"entity": controls["limit"]}).scalar_one()
        return await hass.async_add_executor_job(query)

    before = await control_attributes()
    assert before == 1
    for value in range(5, 15):
        target["total_count"] = value
        await refresh(hass, entry)
    assert hass.states.get(controls["limit"]).attributes["total_count"] == 14
    assert await control_attributes() == before
    assert await hass.config_entries.async_unload(entry.entry_id)
