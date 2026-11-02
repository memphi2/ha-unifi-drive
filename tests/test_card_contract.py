"""Export a synthetic contract from actual HA entities, never from a live HA."""

import json
import os
from pathlib import Path
from unittest.mock import patch


async def test_export_real_entity_contract(hass):
    from homeassistant.helpers import entity_registry as er
    from homeassistant.setup import async_setup_component
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from custom_components.unifi_unas.const import DOMAIN, CONF_SNAPSHOT_BUTTONS_ENABLED
    from tests.test_control_entity_states import _ControlIntegrationClient, _entry_data
    from tests.test_core_monitoring_entity_states import _storage_payload
    from tests.test_snapshot_control_entity_states import (
        _SnapshotIntegrationClient, _snapshot_target_with_controls,
    )

    class Client(_ControlIntegrationClient, _SnapshotIntegrationClient):
        snapshot_settings_read_supported = True

        def __init__(self):
            _ControlIntegrationClient.__init__(self)
            _SnapshotIntegrationClient.__init__(self, [_snapshot_target_with_controls()])

        async def async_get_storage(self):
            data = _storage_payload()
            data.update(await _ControlIntegrationClient.async_get_storage(self))
            return data

    assert await async_setup_component(hass, DOMAIN, {})
    entry = MockConfigEntry(domain=DOMAIN, title="UNAS", unique_id="contract-device",
                            data=_entry_data(**{CONF_SNAPSHOT_BUTTONS_ENABLED: True}))
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    with patch("custom_components.unifi_unas.UnifiUnasApiClient", return_value=Client()), patch(
        "custom_components.unifi_unas.async_create_clientsession", return_value=object(),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        for item in er.async_entries_for_config_entry(registry, entry.entry_id):
            if item.disabled_by is not None:
                registry.async_update_entity(item.entity_id, disabled_by=None)
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        entities, states = {}, {}
        allowed = {"pool_key", "pool_name", "drive_key", "drive_name", "target_key",
                   "target_name", "target_type", "task_id", "task_name"}
        for item in er.async_entries_for_config_entry(registry, entry.entry_id):
            state = hass.states.get(item.entity_id)
            if state is None:
                continue
            entities[item.entity_id] = {"platform": DOMAIN, "config_entry_id": "contract-entry",
                                       "device_id": "contract-device", "translation_key": item.translation_key,
                                       "unique_id": item.unique_id}
            states[item.entity_id] = {"state": state.state, "attributes": {
                key: value for key, value in state.attributes.items() if key in allowed
            }}
        keys = {item["translation_key"] for item in entities.values()}
        assert {"read_throughput", "pool_status", "drive_status", "snapshot_limit",
                "snapshot_inventory", "backup_task", "fan_mode", "device_online"} <= keys
        contract = {"schema_version": 1, "entities": entities, "states": states}
        encoded = json.dumps(contract, indent=2, sort_keys=True) + "\n"
        assert "test-pass" not in encoded and "unas.local" not in encoded
        if output := os.environ.get("UNAS_CARD_CONTRACT_OUTPUT"):
            Path(output).write_text(encoded)
        assert await hass.config_entries.async_unload(entry.entry_id)
