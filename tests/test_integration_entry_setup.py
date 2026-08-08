"""Integration tests for config-entry setup and unload behavior."""

from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CUSTOM_COMPONENTS = str(ROOT / "custom_components")


def _ensure_repo_custom_components_path() -> None:
    """Keep Home Assistant's test package from shadowing this integration."""
    import custom_components

    if CUSTOM_COMPONENTS not in custom_components.__path__:
        custom_components.__path__.append(CUSTOM_COMPONENTS)


@pytest.fixture
def hass_config_dir() -> str:
    """Point Home Assistant at this repository's test config directory."""
    return str(ROOT)


@pytest.fixture(autouse=True)
def _enable_custom_integrations(enable_custom_integrations) -> None:
    """Allow Home Assistant to load the integration from custom_components."""


def _entry_data(*, wol_enabled: bool = False) -> dict[str, object]:
    """Build minimal valid config-entry data for tests."""
    _ensure_repo_custom_components_path()
    from homeassistant.const import (
        CONF_HOST,
        CONF_PASSWORD,
        CONF_PORT,
        CONF_SCAN_INTERVAL,
        CONF_SSL,
        CONF_USERNAME,
        CONF_VERIFY_SSL,
    )

    from custom_components.unifi_unas.const import (
        CONF_WOL_ENABLED,
        DEFAULT_PORT,
        DEFAULT_SCAN_INTERVAL,
        DEFAULT_SSL,
        DEFAULT_VERIFY_SSL,
    )

    return {
        CONF_HOST: "unas.local",
        CONF_PORT: DEFAULT_PORT,
        CONF_SSL: DEFAULT_SSL,
        CONF_VERIFY_SSL: DEFAULT_VERIFY_SSL,
        CONF_USERNAME: "test-user",
        CONF_PASSWORD: "test-pass",
        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
        CONF_WOL_ENABLED: wol_enabled,
    }


@pytest.mark.asyncio
async def test_config_entry_update_listener_reloads_entry(hass) -> None:
    """Config-entry updates should reload the integration."""
    _ensure_repo_custom_components_path()

    from custom_components.unifi_unas import _async_config_entry_updated

    entry = SimpleNamespace(entry_id="entry-options")
    with patch.object(hass.config_entries, "async_reload", AsyncMock()) as reload:
        await _async_config_entry_updated(hass, entry)

    reload.assert_awaited_once_with("entry-options")


@pytest.mark.asyncio
async def test_config_entry_update_listener_ignores_discovery_metadata(hass) -> None:
    """Discovery timestamp updates should not unload and reload entities."""
    _ensure_repo_custom_components_path()

    from custom_components.unifi_unas import (
        _async_config_entry_updated,
    )
    from custom_components.unifi_unas.const import DOMAIN
    from custom_components.unifi_unas.entry_reload import entry_reload_signature

    entry = SimpleNamespace(
        entry_id="entry-discovery",
        data={
            "host": "unas.local",
            "username": "test-user",
            "discovery_last_seen": "2026-05-19T21:00:00Z",
        },
        options={"scan_interval": 30},
    )
    coordinator = SimpleNamespace(entry_reload_signature=entry_reload_signature(entry))
    entry.data = {
        **entry.data,
        "discovery_last_seen": "2026-05-19T21:01:00Z",
        "discovery_confidence": 85,
    }
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    with patch.object(hass.config_entries, "async_reload", AsyncMock()) as reload:
        await _async_config_entry_updated(hass, entry)

    reload.assert_not_awaited()
    assert coordinator.entry_reload_signature == entry_reload_signature(entry)


@pytest.mark.asyncio
async def test_config_entry_update_listener_reloads_runtime_changes(hass) -> None:
    """Runtime config changes should still reload the integration."""
    _ensure_repo_custom_components_path()

    from custom_components.unifi_unas import (
        _async_config_entry_updated,
    )
    from custom_components.unifi_unas.const import DOMAIN
    from custom_components.unifi_unas.entry_reload import entry_reload_signature

    entry = SimpleNamespace(
        entry_id="entry-runtime",
        data={"host": "unas.local", "username": "test-user"},
        options={"scan_interval": 30},
    )
    coordinator = SimpleNamespace(entry_reload_signature=entry_reload_signature(entry))
    entry.options = {"scan_interval": 60}
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    with patch.object(hass.config_entries, "async_reload", AsyncMock()) as reload:
        await _async_config_entry_updated(hass, entry)

    reload.assert_awaited_once_with("entry-runtime")
    assert coordinator.entry_reload_signature == entry_reload_signature(entry)


def test_entry_reload_signature_handles_mixed_nested_values() -> None:
    """Reload signatures should be stable for mixed config value types."""
    _ensure_repo_custom_components_path()

    from custom_components.unifi_unas.entry_reload import entry_reload_signature

    entry = SimpleNamespace(
        data={
            "host": "unas.local",
            "nested": {"numbers": {2, "1"}, "items": [True, None, 3]},
            "discovery_last_seen": "2026-05-19T21:00:00Z",
        },
        options={"scan_interval": 30},
    )

    assert entry_reload_signature(entry) == entry_reload_signature(entry)


def test_backfills_discovery_mac_identity(hass) -> None:
    """Setup helpers should persist a MAC identity for existing entries."""
    _ensure_repo_custom_components_path()
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.unifi_unas import _async_backfill_discovery_mac
    from custom_components.unifi_unas.const import CONF_DISCOVERY_MAC_ADDRESS, DOMAIN

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="UNAS",
        unique_id="unas-mac-backfill",
        data=_entry_data(),
    )
    entry.add_to_hass(hass)

    assert _async_backfill_discovery_mac(hass, entry, "AA:BB:CC:DD:EE:FF") is True
    assert entry.data[CONF_DISCOVERY_MAC_ADDRESS] == "aa:bb:cc:dd:ee:ff"


def test_backfill_discovery_mac_keeps_existing_identity(hass) -> None:
    """Existing discovery MAC metadata should not be overwritten."""
    _ensure_repo_custom_components_path()
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.unifi_unas import _async_backfill_discovery_mac
    from custom_components.unifi_unas.const import CONF_DISCOVERY_MAC_ADDRESS, DOMAIN

    data = _entry_data()
    data[CONF_DISCOVERY_MAC_ADDRESS] = "11:22:33:44:55:66"
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="UNAS",
        unique_id="unas-mac-existing",
        data=data,
    )
    entry.add_to_hass(hass)

    assert _async_backfill_discovery_mac(hass, entry, "AA:BB:CC:DD:EE:FF") is False
    assert entry.data[CONF_DISCOVERY_MAC_ADDRESS] == "11:22:33:44:55:66"


@pytest.mark.asyncio
async def test_remove_config_entry_device_allows_only_stale_device_removal(hass) -> None:
    """Stale device removal should not force users through a restart cycle."""
    _ensure_repo_custom_components_path()

    from custom_components.unifi_unas import async_remove_config_entry_device
    from custom_components.unifi_unas.const import DOMAIN

    entry = SimpleNamespace(unique_id="device-1", entry_id="entry-1")

    assert (
        await async_remove_config_entry_device(
            hass,
            entry,
            SimpleNamespace(identifiers={(DOMAIN, "device-1")}),
        )
        is False
    )
    assert (
        await async_remove_config_entry_device(
            hass,
            entry,
            SimpleNamespace(identifiers={(DOMAIN, "old-device")}),
        )
        is True
    )
    assert (
        await async_remove_config_entry_device(
            hass,
            entry,
            SimpleNamespace(identifiers={("unifi_drive", "device-1")}),
        )
        is True
    )


def test_aborts_matching_discovery_flow_by_mac() -> None:
    """Setup should clear stale discovery cards for an existing MAC identity."""
    _ensure_repo_custom_components_path()

    from custom_components.unifi_unas import _async_abort_matching_discovery_flows
    from custom_components.unifi_unas.const import (
        CONF_DISCOVERY_MAC_ADDRESS,
        DOMAIN,
    )
    from custom_components.unifi_unas.discovery_identity import (
        DISCOVERY_FLOW_CONTEXT_MAC,
    )

    aborted: list[str] = []

    class _FlowManager:
        def async_progress_by_handler(self, domain: str) -> list[dict[str, object]]:
            assert domain == DOMAIN
            return [
                {
                    "flow_id": "matching-flow",
                    "context": {
                        DISCOVERY_FLOW_CONTEXT_MAC: "AA-BB-CC-DD-EE-FF",
                    },
                },
                {
                    "flow_id": "active-user-flow",
                    "context": {
                        DISCOVERY_FLOW_CONTEXT_MAC: "AA-BB-CC-DD-EE-FF",
                        "dismiss_protected": True,
                    },
                },
                {
                    "flow_id": "other-flow",
                    "context": {
                        DISCOVERY_FLOW_CONTEXT_MAC: "11:22:33:44:55:66",
                    },
                },
            ]

        def async_abort(self, flow_id: str) -> None:
            aborted.append(flow_id)

    hass = SimpleNamespace(config_entries=SimpleNamespace(flow=_FlowManager()))
    entry = SimpleNamespace(
        data={CONF_DISCOVERY_MAC_ADDRESS: "aa:bb:cc:dd:ee:ff"},
        options={},
        unique_id="system-id",
    )

    _async_abort_matching_discovery_flows(hass, entry)

    assert aborted == ["matching-flow"]


def test_schedules_delayed_discovery_flow_cleanup() -> None:
    """Setup should retry duplicate discovery-flow cleanup after startup."""
    _ensure_repo_custom_components_path()

    from custom_components.unifi_unas import (
        _DISCOVERY_FLOW_CLEANUP_DELAYS,
        _async_schedule_discovery_flow_cleanup,
    )

    scheduled: list[int] = []
    unloads: list[object] = []

    class _FlowManager:
        def async_progress_by_handler(self, domain: str) -> list[dict[str, object]]:
            return []

        def async_abort(self, flow_id: str) -> None:
            raise AssertionError("No flow should be aborted in this test")

    def _schedule(hass, delay, action):
        scheduled.append(delay)
        action(None)
        return f"unsub-{delay}"

    hass = SimpleNamespace(config_entries=SimpleNamespace(flow=_FlowManager()))
    entry = SimpleNamespace(
        data={},
        options={},
        unique_id="system-id",
        async_on_unload=lambda unsubscribe: unloads.append(unsubscribe),
    )

    with patch("custom_components.unifi_unas.async_call_later", _schedule):
        _async_schedule_discovery_flow_cleanup(hass, entry)

    assert scheduled == list(_DISCOVERY_FLOW_CLEANUP_DELAYS)
    assert unloads == [f"unsub-{delay}" for delay in _DISCOVERY_FLOW_CLEANUP_DELAYS]


def test_discovery_flow_context_matches_stored_host_alias() -> None:
    """Pending discovery flows should also match stored host aliases."""
    _ensure_repo_custom_components_path()

    from custom_components.unifi_unas.discovery_identity import (
        DISCOVERY_FLOW_CONTEXT_HOSTS,
        entry_matches_discovery_flow_context,
    )

    entry = SimpleNamespace(
        data={
            "host": "old-host.local",
            "discovery_host_aliases": ["unas.local", "192.0.2.10"],
        },
        options={},
        unique_id="system-id",
    )

    assert entry_matches_discovery_flow_context(
        entry,
        {DISCOVERY_FLOW_CONTEXT_HOSTS: ["UNAS.local."]},
    )


@pytest.mark.asyncio
async def test_setup_and_unload_entry_stores_and_removes_coordinator(hass) -> None:
    """Entry setup should store the coordinator and unload should remove it."""
    _ensure_repo_custom_components_path()
    from homeassistant.setup import async_setup_component
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.unifi_unas.const import DOMAIN

    assert await async_setup_component(hass, DOMAIN, {})

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="UNAS",
        unique_id="unas-1",
        data=_entry_data(),
    )
    entry.add_to_hass(hass)

    first_refresh = AsyncMock()
    with (
        patch(
            "custom_components.unifi_unas.async_create_clientsession",
            return_value=object(),
        ),
        patch(
            "custom_components.unifi_unas.UnifiUnasCoordinator.async_config_entry_first_refresh",
            first_refresh,
        ),
        patch(
            "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
            new=AsyncMock(return_value=True),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert entry.runtime_data is coordinator
    first_refresh.assert_awaited_once()

    with patch(
        "homeassistant.config_entries.ConfigEntries.async_unload_platforms",
        new=AsyncMock(return_value=True),
    ):
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.entry_id not in hass.data.get(DOMAIN, {})
    assert getattr(entry, "runtime_data", None) is None


@pytest.mark.asyncio
async def test_setup_entry_cleans_runtime_when_platform_forwarding_fails(
    hass,
) -> None:
    """A failed platform setup should not leave stale runtime objects."""
    _ensure_repo_custom_components_path()
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.unifi_unas import async_setup_entry
    from custom_components.unifi_unas.const import DOMAIN

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="UNAS",
        unique_id="unas-forward-fails",
        data=_entry_data(),
    )
    entry.add_to_hass(hass)

    remove_snapshot_cleanup_listener = Mock()

    with (
        patch(
            "custom_components.unifi_unas.async_create_clientsession",
            return_value=object(),
        ),
        patch(
            "custom_components.unifi_unas.UnifiUnasCoordinator.async_config_entry_first_refresh",
            AsyncMock(),
        ),
        patch(
            "custom_components.unifi_unas.UnifiUnasCoordinator.async_add_listener",
            return_value=remove_snapshot_cleanup_listener,
        ),
        patch(
            "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
            new=AsyncMock(side_effect=RuntimeError("forward setup failed")),
        ),
    ):
        with pytest.raises(RuntimeError, match="forward setup failed"):
            await async_setup_entry(hass, entry)

    assert entry.entry_id not in hass.data.get(DOMAIN, {})
    assert getattr(entry, "runtime_data", None) is None
    remove_snapshot_cleanup_listener.assert_called_once()


@pytest.mark.asyncio
async def test_setup_entry_rejects_corrupted_entry_without_host(hass) -> None:
    """A damaged config entry should fail cleanly when the host is missing."""
    _ensure_repo_custom_components_path()
    from homeassistant.exceptions import ConfigEntryError
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.unifi_unas import async_setup_entry
    from custom_components.unifi_unas.const import DOMAIN

    data = _entry_data()
    data.pop("host")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="UNAS",
        unique_id="unas-missing-host",
        data=data,
    )
    entry.add_to_hass(hass)

    with pytest.raises(ConfigEntryError, match="missing a host"):
        await async_setup_entry(hass, entry)

    assert entry.entry_id not in hass.data.get(DOMAIN, {})
    assert getattr(entry, "runtime_data", None) is None


def test_entry_data_int_uses_default_for_corrupted_values() -> None:
    """Corrupted stored integer fields should fall back to defaults."""
    _ensure_repo_custom_components_path()

    from custom_components.unifi_unas import _entry_data_int

    entry = SimpleNamespace(data={"port": "bad-port"})

    assert _entry_data_int(entry, "port", 443) == 443


def test_device_registry_entry_lookup_prefers_scoped_identifier_api() -> None:
    """Device metadata sync should use the HA 2026.8 scoped device lookup."""
    _ensure_repo_custom_components_path()

    from custom_components.unifi_unas import _async_get_device_registry_entry
    from custom_components.unifi_unas.const import DOMAIN

    device = object()
    scoped_lookup = Mock(return_value=device)
    legacy_lookup = Mock()
    registry = SimpleNamespace(
        async_get_device_by_identifier=scoped_lookup,
        async_get_device=legacy_lookup,
    )
    entry = SimpleNamespace(entry_id="entry-1")

    assert _async_get_device_registry_entry(registry, entry, "system-id") is device
    scoped_lookup.assert_called_once_with((DOMAIN, "system-id"), "entry-1")
    legacy_lookup.assert_not_called()


def test_device_registry_entry_lookup_keeps_legacy_fallback() -> None:
    """Older supported HA versions should keep using the legacy lookup."""
    _ensure_repo_custom_components_path()

    from custom_components.unifi_unas import _async_get_device_registry_entry
    from custom_components.unifi_unas.const import DOMAIN

    device = object()
    legacy_lookup = Mock(return_value=device)
    registry = SimpleNamespace(async_get_device=legacy_lookup)
    entry = SimpleNamespace(entry_id="entry-1")

    assert _async_get_device_registry_entry(registry, entry, "system-id") is device
    legacy_lookup.assert_called_once_with(identifiers={(DOMAIN, "system-id")})


def test_device_registry_metadata_sync_updates_firmware_version(hass) -> None:
    """Coordinator refreshes should keep HA device firmware metadata current."""
    _ensure_repo_custom_components_path()
    from homeassistant.helpers import device_registry as dr
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.unifi_unas import _async_sync_device_registry_metadata
    from custom_components.unifi_unas.const import DOMAIN

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="UNAS",
        unique_id="system-id",
        data=_entry_data(),
    )
    entry.add_to_hass(hass)
    device_registry = dr.async_get(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "system-id")},
        manufacturer="Ubiquiti",
        model="UNAS2W",
        sw_version="5.1.8",
        configuration_url="https://unas.example",
    )
    coordinator = SimpleNamespace(
        data={
            "_system": {
                "hardware": {
                    "shortname": "UNAS2W",
                    "firmwareVersion": "5.1.10",
                }
            }
        },
        client=SimpleNamespace(base_url="https://unas.example"),
    )

    assert _async_sync_device_registry_metadata(hass, entry, coordinator) is True

    updated = device_registry.async_get(device.id)
    assert updated is not None
    assert updated.sw_version == "5.1.10"
    assert updated.model == "UNAS2W"


def test_device_registry_metadata_tracking_registers_refresh_listener(hass) -> None:
    """Device metadata tracking should sync immediately and on coordinator updates."""
    _ensure_repo_custom_components_path()
    from homeassistant.helpers import device_registry as dr
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.unifi_unas import _async_track_device_registry_metadata_updates
    from custom_components.unifi_unas.const import DOMAIN

    listeners: list[object] = []

    def _add_listener(callback):
        listeners.append(callback)
        return "remove-listener"

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="UNAS",
        unique_id="system-id",
        data=_entry_data(),
    )
    entry.add_to_hass(hass)
    device_registry = dr.async_get(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "system-id")},
        manufacturer="Ubiquiti",
        model="UNAS2W",
        sw_version="5.1.8",
    )
    coordinator = SimpleNamespace(
        data={
            "_system": {
                "hardware": {
                    "shortname": "UNAS2W",
                    "firmwareVersion": "5.1.10",
                }
            }
        },
        client=SimpleNamespace(base_url="https://unas.example"),
        async_add_listener=_add_listener,
    )

    remove_listener = _async_track_device_registry_metadata_updates(
        hass,
        entry,
        coordinator,
    )

    assert remove_listener == "remove-listener"
    assert len(listeners) == 1
    updated = device_registry.async_get(device.id)
    assert updated is not None
    assert updated.sw_version == "5.1.10"


@pytest.mark.asyncio
async def test_setup_entry_allows_not_ready_when_wol_enabled(hass) -> None:
    """Not-ready refresh should not block setup when WOL is enabled."""
    _ensure_repo_custom_components_path()
    from homeassistant.exceptions import ConfigEntryNotReady
    from homeassistant.setup import async_setup_component
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.unifi_unas.const import DOMAIN

    assert await async_setup_component(hass, DOMAIN, {})

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="UNAS",
        unique_id="unas-2",
        data=_entry_data(wol_enabled=True),
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.unifi_unas.async_create_clientsession",
            return_value=object(),
        ),
        patch(
            "custom_components.unifi_unas.UnifiUnasCoordinator.async_config_entry_first_refresh",
            AsyncMock(side_effect=ConfigEntryNotReady),
        ),
        patch(
            "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
            new=AsyncMock(return_value=True),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.entry_id in hass.data[DOMAIN]


@pytest.mark.asyncio
async def test_setup_entry_reads_wol_fallback_from_options(hass) -> None:
    """Runtime setup should prefer entry.options for feature settings."""
    _ensure_repo_custom_components_path()
    from homeassistant.exceptions import ConfigEntryNotReady
    from homeassistant.setup import async_setup_component
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.unifi_unas.const import (
        CONF_WOL_ENABLED,
        CONF_WOL_MAC_ADDRESS,
        DOMAIN,
    )

    assert await async_setup_component(hass, DOMAIN, {})

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="UNAS",
        unique_id="unas-options",
        data=_entry_data(wol_enabled=False),
        options={
            CONF_WOL_ENABLED: True,
            CONF_WOL_MAC_ADDRESS: "aa:bb:cc:dd:ee:ff",
        },
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.unifi_unas.async_create_clientsession",
            return_value=object(),
        ),
        patch(
            "custom_components.unifi_unas.UnifiUnasCoordinator.async_config_entry_first_refresh",
            AsyncMock(side_effect=ConfigEntryNotReady),
        ),
        patch(
            "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
            new=AsyncMock(return_value=True),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.entry_id in hass.data[DOMAIN]


@pytest.mark.asyncio
async def test_setup_entry_raises_not_ready_when_wol_disabled(hass) -> None:
    """Not-ready refresh should bubble up when WOL fallback is disabled."""
    _ensure_repo_custom_components_path()
    from homeassistant.exceptions import ConfigEntryNotReady
    from homeassistant.setup import async_setup_component
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.unifi_unas.const import DOMAIN

    assert await async_setup_component(hass, DOMAIN, {})

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="UNAS",
        unique_id="unas-3",
        data=_entry_data(wol_enabled=False),
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.unifi_unas.async_create_clientsession",
            return_value=object(),
        ),
        patch(
            "custom_components.unifi_unas.UnifiUnasCoordinator.async_config_entry_first_refresh",
            AsyncMock(side_effect=ConfigEntryNotReady),
        ),
        patch(
            "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
            new=AsyncMock(return_value=True),
        ),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.entry_id not in hass.data.get(DOMAIN, {})


@pytest.mark.asyncio
async def test_removes_unsupported_snapshot_create_buttons(hass) -> None:
    """Setup should purge old create buttons for foreign personal targets."""
    _ensure_repo_custom_components_path()
    from homeassistant.helpers import entity_registry as er
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.unifi_unas import (
        _async_remove_unsupported_snapshot_create_buttons,
    )
    from custom_components.unifi_unas.const import DOMAIN
    from custom_components.unifi_unas.snapshot_types import (
        snapshot_target_key,
        snapshot_target_slug,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="UNAS",
        unique_id="device-1",
        data=_entry_data(),
    )
    entry.add_to_hass(hass)

    registry = er.async_get(hass)
    foreign_target = {
        "type": "personal",
        "id": "backup-user",
        "is_current_user": False,
    }
    current_target = {
        "type": "mydrive",
        "id": "current-user",
        "is_current_user": True,
    }
    api_key_target = {
        "type": "mydrive",
        "id": "api-key-user",
        "is_current_user": False,
    }
    transient_target = {
        "type": "mydrive",
        "id": "api-key-transient",
        "is_current_user": False,
    }
    shared_target = {"type": "shared", "id": "shared-drive"}
    foreign_create_unique_id = (
        f"device-1_snapshot_{snapshot_target_slug(snapshot_target_key(foreign_target))}"
    )
    current_create_unique_id = (
        f"device-1_snapshot_{snapshot_target_slug(snapshot_target_key(current_target))}"
    )
    shared_create_unique_id = (
        f"device-1_snapshot_{snapshot_target_slug(snapshot_target_key(shared_target))}"
    )
    api_key_create_unique_id = (
        f"device-1_snapshot_{snapshot_target_slug(snapshot_target_key(api_key_target))}"
    )
    transient_create_unique_id = (
        f"device-1_snapshot_{snapshot_target_slug(snapshot_target_key(transient_target))}"
    )
    foreign_switch_unique_id = f"{foreign_create_unique_id}_enabled"

    registry.async_get_or_create(
        "button",
        DOMAIN,
        foreign_create_unique_id,
        config_entry=entry,
    )
    registry.async_get_or_create(
        "button",
        DOMAIN,
        current_create_unique_id,
        config_entry=entry,
    )
    registry.async_get_or_create(
        "button",
        DOMAIN,
        shared_create_unique_id,
        config_entry=entry,
    )
    registry.async_get_or_create(
        "button",
        DOMAIN,
        api_key_create_unique_id,
        config_entry=entry,
    )
    registry.async_get_or_create(
        "button",
        DOMAIN,
        transient_create_unique_id,
        config_entry=entry,
    )
    registry.async_get_or_create(
        "switch",
        DOMAIN,
        foreign_switch_unique_id,
        config_entry=entry,
    )

    coordinator = SimpleNamespace(
        snapshot_settings=[
            foreign_target,
            current_target,
            shared_target,
            api_key_target,
            transient_target,
        ],
        snapshot_inventory={
            snapshot_target_key(api_key_target): {"snapshot_count": 1}
        },
        snapshot_inventory_errors={
            snapshot_target_key(foreign_target): "unsupported"
        },
    )

    _async_remove_unsupported_snapshot_create_buttons(hass, entry, coordinator)

    assert (
        registry.async_get_entity_id("button", DOMAIN, foreign_create_unique_id)
        is None
    )
    assert registry.async_get_entity_id("button", DOMAIN, current_create_unique_id)
    assert registry.async_get_entity_id("button", DOMAIN, shared_create_unique_id)
    assert registry.async_get_entity_id("button", DOMAIN, api_key_create_unique_id)
    assert registry.async_get_entity_id("button", DOMAIN, transient_create_unique_id)
    assert registry.async_get_entity_id("switch", DOMAIN, foreign_switch_unique_id)


def test_remove_unsupported_snapshot_create_buttons_skips_invalid_entries(
    hass,
) -> None:
    """Cleanup should ignore malformed snapshot entries without errors."""
    _ensure_repo_custom_components_path()
    from homeassistant.helpers import entity_registry as er
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.unifi_unas import (
        _async_remove_unsupported_snapshot_create_buttons,
    )
    from custom_components.unifi_unas.const import DOMAIN
    from custom_components.unifi_unas.snapshot_types import (
        snapshot_target_key,
        snapshot_target_slug,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="UNAS",
        unique_id="device-3",
        data=_entry_data(),
    )
    entry.add_to_hass(hass)

    registry = er.async_get(hass)
    foreign_target = {
        "type": "mydrive",
        "id": "backup-user",
        "is_current_user": False,
    }
    foreign_create_unique_id = (
        f"device-3_snapshot_{snapshot_target_slug(snapshot_target_key(foreign_target))}"
    )
    registry.async_get_or_create(
        "button",
        DOMAIN,
        foreign_create_unique_id,
        config_entry=entry,
    )

    coordinator = SimpleNamespace(
        snapshot_settings=[None, "bad", foreign_target],
        snapshot_inventory={},
        snapshot_inventory_errors={snapshot_target_key(foreign_target): "unsupported"},
    )

    _async_remove_unsupported_snapshot_create_buttons(hass, entry, coordinator)

    assert (
        registry.async_get_entity_id("button", DOMAIN, foreign_create_unique_id)
        is None
    )


@pytest.mark.asyncio
async def test_retries_unsupported_snapshot_create_button_cleanup_after_refresh(
    hass,
) -> None:
    """Delayed snapshot discovery should still purge old unsupported buttons."""
    _ensure_repo_custom_components_path()
    from homeassistant.helpers import entity_registry as er
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.unifi_unas import (
        _async_track_unsupported_snapshot_create_button_cleanup,
    )
    from custom_components.unifi_unas.const import DOMAIN
    from custom_components.unifi_unas.snapshot_types import (
        snapshot_target_key,
        snapshot_target_slug,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="UNAS",
        unique_id="device-2",
        data=_entry_data(),
    )
    entry.add_to_hass(hass)

    registry = er.async_get(hass)
    foreign_target = {
        "type": "mydrive",
        "id": "backup-user",
        "is_current_user": False,
    }
    foreign_create_unique_id = (
        f"device-2_snapshot_{snapshot_target_slug(snapshot_target_key(foreign_target))}"
    )
    registry.async_get_or_create(
        "button",
        DOMAIN,
        foreign_create_unique_id,
        config_entry=entry,
    )

    listeners = []
    coordinator = SimpleNamespace(
        snapshot_settings=[],
        snapshot_inventory={},
        snapshot_inventory_errors={},
        async_add_listener=lambda listener: listeners.append(listener),
    )

    _async_track_unsupported_snapshot_create_button_cleanup(hass, entry, coordinator)

    assert registry.async_get_entity_id("button", DOMAIN, foreign_create_unique_id)
    assert len(listeners) == 1

    coordinator.snapshot_settings = [foreign_target]
    coordinator.snapshot_inventory_errors = {
        snapshot_target_key(foreign_target): "unsupported"
    }
    listeners[0]()

    assert (
        registry.async_get_entity_id("button", DOMAIN, foreign_create_unique_id)
        is None
    )
