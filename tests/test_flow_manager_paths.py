"""Exercise transactional config changes through Home Assistant's flow manager."""

from unittest.mock import AsyncMock, patch

import pytest


def connection():
    return {"host": "console.example", "port": 443, "ssl": True, "verify_ssl": True,
            "username": "test-user", "password": "test-pass"}


def identity(device="synthetic-device"):
    return {"title": "UNAS", "unique_id": device, "unique_ids": (device,),
            "device_scoped_unique_ids": (device,), "host": "console.example", "port": 443}


@pytest.mark.parametrize("failure,reason", [
    ("CannotConnect", "cannot_connect"), ("InvalidAuth", "invalid_auth"),
    ("UnexpectedResponse", "unsupported_response"), ("RuntimeError", "unknown"),
])
async def test_setup_failure_then_retry_is_transactional(hass, failure, reason):
    from custom_components.unifi_unas import api_errors
    from custom_components.unifi_unas.const import DOMAIN

    error = getattr(api_errors, failure, RuntimeError)("synthetic failure")
    with patch("custom_components.unifi_unas.config_flow.async_discover_unas_devices", return_value=()), \
         patch("custom_components.unifi_unas.config_flow.async_validate_input",
               side_effect=[error, identity()]), \
         patch("custom_components.unifi_unas.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], connection())
        assert result["errors"] == {"base": reason}
        assert not hass.config_entries.async_entries(DOMAIN)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], connection())
        assert result["step_id"] == "features"
        assert not hass.config_entries.async_entries(DOMAIN)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        assert result["type"] == "create_entry"
        await hass.async_block_till_done()
    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    assert entries[0].unique_id == "synthetic-device"
    assert not hass.config_entries.flow.async_progress()


async def test_aborted_feature_form_leaves_no_entry_and_can_restart(hass):
    from custom_components.unifi_unas.const import DOMAIN

    with patch("custom_components.unifi_unas.config_flow.async_discover_unas_devices", return_value=()), \
         patch("custom_components.unifi_unas.config_flow.async_validate_input", return_value=identity()):
        for _ in range(2):
            result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
            result = await hass.config_entries.flow.async_configure(result["flow_id"], connection())
            assert result["step_id"] == "features"
            hass.config_entries.flow.async_abort(result["flow_id"])
            assert not hass.config_entries.async_entries(DOMAIN)
            assert not hass.config_entries.flow.async_progress()


@pytest.mark.parametrize("source", ["reauth", "reconfigure"])
async def test_identity_rejection_preserves_entry_then_valid_retry(hass, source):
    from homeassistant.setup import async_setup_component
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from custom_components.unifi_unas.const import DOMAIN
    from tests.test_core_monitoring_entity_states import _MonitoringClient

    assert await async_setup_component(hass, DOMAIN, {})
    entry = MockConfigEntry(domain=DOMAIN, title="UNAS", unique_id="synthetic-device",
                            data=connection(), options={"scan_interval": 60,
                                "fan_control_enabled": False, "snapshot_buttons_enabled": False})
    entry.add_to_hass(hass)
    with patch("custom_components.unifi_unas.async_create_clientsession", return_value=object()), \
         patch("custom_components.unifi_unas.UnifiUnasApiClient", return_value=_MonitoringClient()):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    original_id = entry.unique_id
    original_data, original_options = dict(entry.data), dict(entry.options)
    with patch("custom_components.unifi_unas.config_flow.async_validate_input",
               side_effect=[identity("different-device"), identity(original_id)]), \
         patch.object(hass.config_entries, "async_reload", new=AsyncMock(return_value=True)) as reload:
        async def start():
            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": source, "entry_id": entry.entry_id},
                data=dict(entry.data) if source == "reauth" else None,
            )
            if source == "reconfigure":
                result = await hass.config_entries.flow.async_configure(
                    result["flow_id"], {"next_step_id": "reconfigure_connection"})
            return result

        result = await start()
        submitted = connection() if source == "reconfigure" else {
            "username": "test-user", "password": "new-pass"}
        result = await hass.config_entries.flow.async_configure(result["flow_id"], submitted)
        if source == "reauth":
            assert result["reason"] == "wrong_device"
        else:
            assert result["errors"] == {"base": "wrong_device"}
        assert dict(entry.data) == original_data
        assert dict(entry.options) == original_options
        reload.assert_not_called()
        if source == "reauth":
            result = await start()
        else:
            submitted["host"] = "replacement.example"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], submitted)
        assert result["type"] == "abort"
        assert result["reason"] == f"{source}_successful"
        await hass.async_block_till_done()
        reload.assert_awaited_once_with(entry.entry_id)
    assert entry.unique_id == original_id
    assert entry.options["scan_interval"] == original_options["scan_interval"]
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_permission_repair_deduplication_recovery_and_entry_isolation(hass):
    from homeassistant.helpers import issue_registry as ir
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from custom_components.unifi_unas import snapshot_repairs as repairs
    from custom_components.unifi_unas.api_errors import InvalidAuth
    from custom_components.unifi_unas.const import DOMAIN

    entries = [MockConfigEntry(domain=DOMAIN, title="UNAS", data=connection()) for _ in range(2)]
    registry = ir.async_get(hass)
    for entry in entries:
        entry.add_to_hass(hass)
        for _ in range(3):
            repairs.async_create_snapshot_read_issue(hass, entry, InvalidAuth("token=private-fixture"))
    assert len(registry.issues) == 2
    for issue in registry.issues.values():
        assert issue.translation_key == "snapshot_read_permission"
        assert "private-fixture" not in str(issue.translation_placeholders)
    repairs.async_update_snapshot_read_issue(hass, entries[0], supported=False)
    assert len(registry.issues) == 2
    assert registry.async_get_issue(DOMAIN, f"{entries[0].entry_id}_snapshot_read_permission") is None
    repairs.async_update_snapshot_read_issue(hass, entries[0], supported=True)
    assert len(registry.issues) == 1
    repairs.async_clear_snapshot_issues(hass, entries[1])
    assert not registry.issues


async def test_options_invalid_input_then_valid_update_reloads_once(hass):
    from tests.test_core_monitoring_entity_states import _MonitoringClient, _async_setup_monitoring_entry

    entry = await _async_setup_monitoring_entry(hass, _MonitoringClient())
    original = dict(entry.options)
    with patch.object(hass.config_entries, "async_reload", new=AsyncMock(return_value=True)) as reload:
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"wol_enabled": True, "wol_mac_address": "invalid"})
        assert result["type"] == "form"
        assert result["errors"]
        assert dict(entry.options) == original
        reload.assert_not_called()
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"scan_interval": 90, "wol_enabled": False})
        assert result["type"] == "create_entry"
        await hass.async_block_till_done()
        reload.assert_awaited_once_with(entry.entry_id)
        assert entry.options["scan_interval"] == 90
    assert await hass.config_entries.async_unload(entry.entry_id)
