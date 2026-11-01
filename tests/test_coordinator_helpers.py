"""Unit tests for coordinator helper behavior."""

from __future__ import annotations

import asyncio
import logging
import sys
import types

import pytest

from tests.module_stubs import (
    install_homeassistant_const_stub,
    install_package_stubs,
    load_const_module,
    load_integration_module,
)


def _load_coordinator_module():
    install_package_stubs()
    install_homeassistant_const_stub(CONF_SCAN_INTERVAL="scan_interval")

    config_entries_pkg = types.ModuleType("homeassistant.config_entries")
    config_entries_pkg.ConfigEntry = object
    sys.modules["homeassistant.config_entries"] = config_entries_pkg

    core_pkg = types.ModuleType("homeassistant.core")
    core_pkg.HomeAssistant = object
    sys.modules["homeassistant.core"] = core_pkg

    exceptions_pkg = types.ModuleType("homeassistant.exceptions")

    class ConfigEntryAuthFailed(Exception):
        """Config entry auth failure stub."""

    exceptions_pkg.ConfigEntryAuthFailed = ConfigEntryAuthFailed
    sys.modules["homeassistant.exceptions"] = exceptions_pkg

    helpers_pkg = types.ModuleType("homeassistant.helpers")
    sys.modules["homeassistant.helpers"] = helpers_pkg

    update_coordinator_pkg = types.ModuleType("homeassistant.helpers.update_coordinator")

    class UpdateFailed(Exception):
        """Update failure stub."""

    class DataUpdateCoordinator:
        """Data update coordinator stub."""

        @classmethod
        def __class_getitem__(cls, item):
            return cls

        def __init__(self, hass, *, logger, name, update_interval) -> None:
            self.hass = hass
            self.logger = logger
            self.name = name
            self.update_interval = update_interval
            self.last_update_success = True
            self.data = None

        async def async_config_entry_first_refresh(self) -> None:
            self.data = await self._async_update_data()

        def async_set_updated_data(self, data) -> None:
            self.data = data

    update_coordinator_pkg.DataUpdateCoordinator = DataUpdateCoordinator
    update_coordinator_pkg.UpdateFailed = UpdateFailed
    sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator_pkg

    api_pkg = types.ModuleType("custom_components.unifi_unas.api")

    class CannotConnect(Exception):
        """API connection error stub."""

    class InvalidAuth(Exception):
        """API auth error stub."""

    class UnexpectedResponse(Exception):
        """API response error stub."""

    class UnsupportedFeature(Exception):
        """Unsupported feature error stub."""

    api_pkg.CannotConnect = CannotConnect
    api_pkg.InvalidAuth = InvalidAuth
    api_pkg.UnexpectedResponse = UnexpectedResponse
    api_pkg.UnsupportedFeature = UnsupportedFeature
    api_pkg.UnifiUnasApiClient = object
    sys.modules["custom_components.unifi_unas.api"] = api_pkg

    snapshot_repairs_pkg = types.ModuleType(
        "custom_components.unifi_unas.snapshot_repairs"
    )
    snapshot_repairs_pkg.async_clear_snapshot_issues = lambda *args, **kwargs: None
    snapshot_repairs_pkg.async_clear_snapshot_action_issues = (
        lambda *args, **kwargs: None
    )
    snapshot_repairs_pkg.async_clear_snapshot_target_missing_issue = (
        lambda *args, **kwargs: None
    )
    snapshot_repairs_pkg.async_create_snapshot_action_issue = lambda *args, **kwargs: None
    snapshot_repairs_pkg.async_create_snapshot_read_issue = (
        lambda *args, **kwargs: None
    )
    snapshot_repairs_pkg.async_update_snapshot_target_missing_issue = (
        lambda *args, **kwargs: None
    )
    snapshot_repairs_pkg.async_update_snapshot_read_issue = (
        lambda *args, **kwargs: None
    )
    sys.modules["custom_components.unifi_unas.snapshot_repairs"] = snapshot_repairs_pkg

    load_const_module()
    load_integration_module("snapshot_types")
    return load_integration_module("coordinator")


coordinator_module = _load_coordinator_module()


class _FakeEntry:
    data = {"scan_interval": 30}


class _FakeInventoryClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def async_get_snapshot_inventory_target(self, target: dict) -> dict:
        self.calls.append(target["id"])
        if target["id"] == "foreign-user":
            raise coordinator_module.UnsupportedFeature(
                "Snapshot inventory endpoint is not available on this system."
            )
        if target["id"] == "casey-user":
            raise coordinator_module.UnsupportedFeature(
                "Snapshot inventory endpoint is Not Available on This System."
            )
        if target["id"] == "transient-user":
            raise coordinator_module.UnsupportedFeature(
                "Snapshot inventory endpoint returned HTTP 500"
            )
        return {"snapshot_count": 1}


class _FakeTypedInventoryClient:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.snapshot_inventory_supported_by_type = {"mydrive": False}

    async def async_get_snapshot_inventory_target(self, target: dict) -> dict:
        self.calls.append(target["id"])
        return {"snapshot_count": 1}


class _FakeBadCacheInventoryClient(_FakeTypedInventoryClient):
    def __init__(self) -> None:
        super().__init__()
        self.snapshot_inventory_supported_by_type = []  # type: ignore[assignment]


class _FakeMalformedTypedCacheClient(_FakeTypedInventoryClient):
    def __init__(self) -> None:
        super().__init__()
        self.snapshot_inventory_supported_by_type = {"mydrive": "false", 1: True}


class _FakeNoCacheInventoryClient(_FakeTypedInventoryClient):
    def __init__(self) -> None:
        self.calls = []


class _FakeLegacyAliasCacheInventoryClient(_FakeTypedInventoryClient):
    def __init__(self) -> None:
        super().__init__()
        self.snapshot_inventory_supported_by_type = {"personal": False}


class _FakePollingInventoryClient:
    snapshot_settings_read_supported = True
    snapshot_inventory_supported_by_type: dict[str, bool] = {}

    def __init__(self) -> None:
        self.inventory_calls: list[str] = []
        self.snapshot_settings = [{"id": "shared-1", "type": "shared"}]

    async def async_get_storage(self) -> dict:
        return {"_system": {"status": "online"}}

    async def async_get_backup_tasks(self) -> list:
        return []

    async def async_get_snapshot_settings(self) -> list[dict]:
        return list(self.snapshot_settings)

    async def async_get_snapshot_inventory_target(self, target: dict) -> dict:
        self.inventory_calls.append(target["id"])
        return {"snapshot_count": len(self.inventory_calls)}


class _FakeStartupOptionalClient(_FakePollingInventoryClient):
    def __init__(self) -> None:
        super().__init__()
        self.backup_calls = 0
        self.fan_calls = 0
        self.snapshot_settings_calls = 0

    async def async_get_fan_mode(self) -> str:
        self.fan_calls += 1
        return "Balance"

    async def async_get_backup_tasks(self) -> list:
        self.backup_calls += 1
        return [{"id": "backup-1", "name": "Backup"}]

    async def async_get_snapshot_settings(self) -> list[dict]:
        self.snapshot_settings_calls += 1
        return await super().async_get_snapshot_settings()


class _FakeRequestDuringInventoryClient(_FakePollingInventoryClient):
    def __init__(self) -> None:
        super().__init__()
        self.refresh_callback = None

    async def async_get_snapshot_inventory_target(self, target: dict) -> dict:
        self.inventory_calls.append(target["id"])
        if self.refresh_callback is not None:
            refresh_callback = self.refresh_callback
            self.refresh_callback = None
            refresh_callback()
        return {"snapshot_count": len(self.inventory_calls)}


class _FakeUnexpectedErrorInventoryClient(_FakePollingInventoryClient):
    async def async_get_snapshot_inventory_target(self, target: dict) -> dict:
        raise RuntimeError("inventory target broke unexpectedly")


class _FakeTransientStorageClient(_FakePollingInventoryClient):
    def __init__(self) -> None:
        super().__init__()
        self.storage_failures_remaining = 0

    async def async_get_storage(self) -> dict:
        if self.storage_failures_remaining > 0:
            self.storage_failures_remaining -= 1
            raise coordinator_module.CannotConnect("startup api not ready")
        return {"_system": {"status": "online"}}


class _FakeAuthFailureClient(_FakePollingInventoryClient):
    async def async_get_storage(self) -> dict:
        raise coordinator_module.InvalidAuth("bad credentials")


class _FakeUnexpectedStorageClient(_FakePollingInventoryClient):
    async def async_get_storage(self) -> dict:
        raise coordinator_module.UnexpectedResponse("bad payload")


class _FakeOptionalFailureClient(_FakePollingInventoryClient):
    def __init__(self) -> None:
        super().__init__()
        self.snapshot_settings_read_supported = True

    async def async_get_fan_mode(self) -> str:
        raise coordinator_module.UnsupportedFeature("fan endpoint missing")

    async def async_get_backup_tasks(self) -> list:
        raise coordinator_module.CannotConnect("backup endpoint offline")


class _FakeSnapshotPollingEntry:
    data = {
        "scan_interval": 30,
        "fan_control_enabled": False,
        "snapshot_buttons_enabled": True,
    }
    entry_id = "entry"
    unique_id = "device"


class _FakeOptionsEntry:
    data = {
        "scan_interval": 30,
        "fan_control_enabled": True,
        "snapshot_buttons_enabled": False,
    }
    options = {
        "scan_interval": 120,
        "fan_control_enabled": False,
        "snapshot_buttons_enabled": True,
    }
    entry_id = "entry"
    unique_id = "device"


def _coordinator(client: _FakeInventoryClient):
    coordinator = coordinator_module.UnifiUnasCoordinator(
        types.SimpleNamespace(),
        client,
        _FakeEntry(),
    )
    coordinator.snapshot_settings = [
        {"id": "shared-1", "type": "shared"},
        {"id": "foreign-user", "type": "mydrive"},
    ]
    return coordinator


def _transient_storage_coordinator():
    client = _FakeTransientStorageClient()
    coordinator = coordinator_module.UnifiUnasCoordinator(
        types.SimpleNamespace(),
        client,
        _FakeSnapshotPollingEntry(),
    )
    return client, coordinator


def test_coordinator_prefers_entry_options_for_feature_settings() -> None:
    """Coordinator feature toggles should be ready for entry.options."""
    coordinator = coordinator_module.UnifiUnasCoordinator(
        types.SimpleNamespace(),
        object(),
        _FakeOptionsEntry(),
    )

    assert coordinator.update_interval.total_seconds() == 120
    assert coordinator.fan_control_enabled is False
    assert coordinator.snapshot_buttons_enabled is True


def test_config_entry_first_refresh_defers_optional_endpoint_reads() -> None:
    """Startup setup should register entities before slow optional endpoint reads."""
    client = _FakeStartupOptionalClient()
    entry = types.SimpleNamespace(
        data={
            "scan_interval": 30,
            "fan_control_enabled": True,
            "snapshot_buttons_enabled": True,
        },
        options={},
        entry_id="entry",
        unique_id="device",
    )
    coordinator = coordinator_module.UnifiUnasCoordinator(
        types.SimpleNamespace(),
        client,
        entry,
    )

    asyncio.run(coordinator.async_config_entry_first_refresh())

    assert coordinator.data == {"_system": {"status": "online"}}
    assert client.fan_calls == 0
    assert client.backup_calls == 0
    assert client.snapshot_settings_calls == 0
    assert client.inventory_calls == []

    asyncio.run(coordinator.async_refresh_optional_features())

    assert client.fan_calls == 1
    assert client.backup_calls == 1
    assert client.snapshot_settings_calls == 1
    assert client.inventory_calls == ["shared-1"]
    assert coordinator.backup_tasks == [{"id": "backup-1", "name": "Backup"}]
    assert coordinator.snapshot_inventory == {
        "shared_shared-1": {"snapshot_count": 1}
    }


def test_snapshot_inventory_skips_sticky_unsupported_targets() -> None:
    """Unsupported target inventory reads should not retry every poll."""
    client = _FakeInventoryClient()
    coordinator = _coordinator(client)

    inventory = asyncio.run(coordinator._async_get_snapshot_inventory())

    assert inventory == {"shared_shared-1": {"snapshot_count": 1}}
    assert coordinator.snapshot_inventory_errors == {
        "mydrive_foreign-user": "unsupported"
    }
    assert coordinator.snapshot_inventory_skip_reasons == {
        "mydrive_foreign-user": "unsupported"
    }
    assert client.calls == ["shared-1", "foreign-user"]

    inventory = asyncio.run(coordinator._async_get_snapshot_inventory())

    assert inventory == {"shared_shared-1": {"snapshot_count": 1}}
    assert coordinator.snapshot_inventory_errors == {
        "mydrive_foreign-user": "unsupported"
    }
    assert coordinator.snapshot_inventory_skip_reasons == {
        "mydrive_foreign-user": "unsupported"
    }
    assert client.calls == ["shared-1", "foreign-user", "shared-1"]


def test_snapshot_inventory_skips_invalid_snapshot_settings_entries() -> None:
    """Invalid snapshot_settings entries should be ignored while polling inventory."""
    client = _FakeInventoryClient()
    coordinator = _coordinator(client)
    coordinator.snapshot_settings = [
        None,
        "bad-entry",
        {"id": "shared-1", "type": "shared"},
        123,
        {"id": "foreign-user", "type": "mydrive"},
    ]

    inventory = asyncio.run(coordinator._async_get_snapshot_inventory())

    assert inventory == {"shared_shared-1": {"snapshot_count": 1}}
    assert coordinator.snapshot_inventory_errors == {
        "mydrive_foreign-user": "unsupported"
    }
    assert coordinator.snapshot_inventory_skip_reasons == {
        "mydrive_foreign-user": "unsupported"
    }
    assert client.calls == ["shared-1", "foreign-user"]


def test_snapshot_inventory_skip_cache_prunes_removed_targets() -> None:
    """Skip reasons should disappear when a target is no longer advertised."""
    client = _FakeInventoryClient()
    coordinator = _coordinator(client)
    coordinator.snapshot_inventory_skip_reasons = {
        "mydrive_foreign-user": "unsupported",
        "mydrive_old-user": "unsupported",
    }
    coordinator.snapshot_settings = [{"id": "shared-1", "type": "shared"}]

    asyncio.run(coordinator._async_get_snapshot_inventory())

    assert coordinator.snapshot_inventory_skip_reasons == {}


def test_snapshot_inventory_skips_targets_for_cached_unsupported_type() -> None:
    """Avoid API calls for snapshot types already known to be unsupported."""
    client = _FakeTypedInventoryClient()
    coordinator = _coordinator(client)
    coordinator.snapshot_settings = [
        {"id": "shared-1", "type": "shared"},
        {"id": "foreign-user", "type": "personal"},
        {"id": "other-user", "type": "mydrive"},
    ]

    inventory = asyncio.run(coordinator._async_get_snapshot_inventory())

    assert inventory == {"shared_shared-1": {"snapshot_count": 1}}
    assert coordinator.snapshot_inventory_errors == {
        "mydrive_foreign-user": "unsupported",
        "mydrive_other-user": "unsupported",
    }
    assert coordinator.snapshot_inventory_skip_reasons == {
        "mydrive_foreign-user": "unsupported",
        "mydrive_other-user": "unsupported",
    }
    assert client.calls == ["shared-1"]


def test_snapshot_inventory_tolerates_malformed_type_cache() -> None:
    """A malformed type cache should not break snapshot inventory polling."""
    client = _FakeBadCacheInventoryClient()
    coordinator = _coordinator(client)
    coordinator.snapshot_settings = [
        {"id": "shared-1", "type": "shared"},
    ]

    inventory = asyncio.run(coordinator._async_get_snapshot_inventory())

    assert inventory == {"shared_shared-1": {"snapshot_count": 1}}
    assert coordinator.snapshot_inventory_errors == {}
    assert coordinator.snapshot_inventory_skip_reasons == {}
    assert client.calls == ["shared-1"]


def test_snapshot_inventory_tolerates_case_variants_in_unsupported_marker() -> None:
    """Unsupported marker matching should be case-insensitive."""
    client = _FakeInventoryClient()
    coordinator = _coordinator(client)
    coordinator.snapshot_settings = [
        {"id": "casey-user", "type": "mydrive"},
    ]

    asyncio.run(coordinator._async_get_snapshot_inventory())

    assert coordinator.snapshot_inventory_errors == {
        "mydrive_casey-user": "unsupported"
    }
    assert coordinator.snapshot_inventory_skip_reasons == {
        "mydrive_casey-user": "unsupported"
    }
    assert client.calls == ["casey-user"]

    asyncio.run(coordinator._async_get_snapshot_inventory())

    assert coordinator.snapshot_inventory_errors == {
        "mydrive_casey-user": "unsupported"
    }
    assert coordinator.snapshot_inventory_skip_reasons == {
        "mydrive_casey-user": "unsupported"
    }
    assert client.calls == ["casey-user"]


def test_snapshot_inventory_tolerates_malformed_entries_in_type_cache() -> None:
    """Only valid bool cache entries should be used for skip decisions."""
    client = _FakeMalformedTypedCacheClient()
    coordinator = _coordinator(client)
    coordinator.snapshot_settings = [
        {"id": "shared-1", "type": "shared"},
        {"id": "foreign-user", "type": "mydrive"},
    ]

    inventory = asyncio.run(coordinator._async_get_snapshot_inventory())

    assert inventory == {
        "shared_shared-1": {"snapshot_count": 1},
        "mydrive_foreign-user": {"snapshot_count": 1},
    }
    assert coordinator.snapshot_inventory_errors == {}
    assert coordinator.snapshot_inventory_skip_reasons == {}
    assert client.calls == ["shared-1", "foreign-user"]


def test_snapshot_inventory_respects_legacy_cache_type_aliases() -> None:
    """Legacy per-target type flags should still skip unsupported inventory reads."""
    client = _FakeLegacyAliasCacheInventoryClient()
    coordinator = _coordinator(client)
    coordinator.snapshot_settings = [
        {"id": "shared-1", "type": "shared"},
        {"id": "legacy-user", "type": "mydrive"},
    ]

    inventory = asyncio.run(coordinator._async_get_snapshot_inventory())

    assert inventory == {"shared_shared-1": {"snapshot_count": 1}}
    assert coordinator.snapshot_inventory_errors == {
        "mydrive_legacy-user": "unsupported",
    }
    assert coordinator.snapshot_inventory_skip_reasons == {
        "mydrive_legacy-user": "unsupported",
    }
    assert client.calls == ["shared-1"]


def test_snapshot_inventory_uses_cache_when_type_map_missing() -> None:
    """Missing type cache should not block inventory polling."""
    client = _FakeNoCacheInventoryClient()
    coordinator = _coordinator(client)
    coordinator.snapshot_settings = [
        {"id": "shared-1", "type": "shared"},
    ]

    inventory = asyncio.run(coordinator._async_get_snapshot_inventory())

    assert inventory == {"shared_shared-1": {"snapshot_count": 1}}
    assert coordinator.snapshot_inventory_errors == {}
    assert coordinator.snapshot_inventory_skip_reasons == {}
    assert client.calls == ["shared-1"]


def test_snapshot_inventory_retries_transient_unsupported_feature_errors() -> None:
    """Ambiguous UnsupportedFeature errors should not become sticky skips."""
    client = _FakeInventoryClient()
    coordinator = _coordinator(client)
    coordinator.snapshot_settings = [
        {"id": "transient-user", "type": "mydrive"},
    ]

    asyncio.run(coordinator._async_get_snapshot_inventory())

    assert coordinator.snapshot_inventory_errors == {
        "mydrive_transient-user": "unexpected_response"
    }
    assert coordinator.snapshot_inventory_skip_reasons == {}
    assert client.calls == ["transient-user"]

    asyncio.run(coordinator._async_get_snapshot_inventory())

    assert coordinator.snapshot_inventory_errors == {
        "mydrive_transient-user": "unexpected_response"
    }
    assert coordinator.snapshot_inventory_skip_reasons == {}
    assert client.calls == ["transient-user", "transient-user"]


def test_snapshot_inventory_is_throttled_between_storage_polls() -> None:
    """Regular coordinator refreshes should not read snapshot inventory every poll."""
    client = _FakePollingInventoryClient()
    coordinator = coordinator_module.UnifiUnasCoordinator(
        types.SimpleNamespace(),
        client,
        _FakeSnapshotPollingEntry(),
    )

    asyncio.run(coordinator._async_update_data())
    asyncio.run(coordinator._async_update_data())

    assert client.inventory_calls == ["shared-1"]
    assert coordinator.snapshot_inventory == {
        "shared_shared-1": {"snapshot_count": 1}
    }

    coordinator.request_snapshot_inventory_refresh()
    asyncio.run(coordinator._async_update_data())

    assert client.inventory_calls == ["shared-1", "shared-1"]
    assert coordinator.snapshot_inventory == {
        "shared_shared-1": {"snapshot_count": 2}
    }


def test_snapshot_inventory_preserves_refresh_requested_during_fetch() -> None:
    """Requests raised during an inventory fetch should trigger the next poll."""
    client = _FakeRequestDuringInventoryClient()
    coordinator = coordinator_module.UnifiUnasCoordinator(
        types.SimpleNamespace(),
        client,
        _FakeSnapshotPollingEntry(),
    )
    client.refresh_callback = coordinator.request_snapshot_inventory_refresh
    coordinator.request_snapshot_inventory_refresh()

    asyncio.run(coordinator._async_update_data())

    assert client.inventory_calls == ["shared-1"]
    assert coordinator._snapshot_inventory_refresh_requested is True

    asyncio.run(coordinator._async_update_data())

    assert client.inventory_calls == ["shared-1", "shared-1"]
    assert coordinator._snapshot_inventory_refresh_requested is False
    assert coordinator.snapshot_inventory == {
        "shared_shared-1": {"snapshot_count": 2}
    }


def test_single_cached_storage_failure_does_not_mark_device_offline() -> None:
    """A transient startup poll failure should not flap device availability."""
    client, coordinator = _transient_storage_coordinator()

    storage = asyncio.run(coordinator._async_update_data())
    coordinator.data = storage

    client.storage_failures_remaining = 1
    storage = asyncio.run(coordinator._async_update_data())

    assert coordinator.is_device_online is True
    assert storage["_system"]["status"] == "online"


def test_empty_cached_storage_failure_does_not_mark_device_offline() -> None:
    """An empty cached payload should still count as cached coordinator data."""
    client, coordinator = _transient_storage_coordinator()
    coordinator.data = {}

    client.storage_failures_remaining = 1
    storage = asyncio.run(coordinator._async_update_data())

    assert coordinator.is_device_online is True
    assert storage == {}


def test_initial_storage_failure_without_cache_raises_update_failed() -> None:
    """Startup connection failures without cached data should fail setup."""
    client, coordinator = _transient_storage_coordinator()
    client.storage_failures_remaining = 1

    try:
        asyncio.run(coordinator._async_update_data())
    except coordinator_module.UpdateFailed as err:
        assert "startup api not ready" in str(err)
    else:
        raise AssertionError("startup failure without cache should fail")

    assert coordinator.is_device_online is False


def test_storage_auth_and_payload_failures_are_not_treated_as_offline_cache() -> None:
    """Auth and payload errors should surface through HA coordinator exceptions."""
    for client, expected_error in (
        (_FakeAuthFailureClient(), coordinator_module.ConfigEntryAuthFailed),
        (_FakeUnexpectedStorageClient(), coordinator_module.UpdateFailed),
    ):
        coordinator = coordinator_module.UnifiUnasCoordinator(
            types.SimpleNamespace(),
            client,
            _FakeSnapshotPollingEntry(),
        )
        try:
            asyncio.run(coordinator._async_update_data())
        except expected_error:
            pass
        else:
            raise AssertionError(f"{expected_error.__name__} should be raised")


def test_optional_endpoint_failures_do_not_break_core_storage_refresh() -> None:
    """Fan and backup endpoint failures should not abort core monitoring."""
    client = _FakeOptionalFailureClient()
    entry = types.SimpleNamespace(
        data={"scan_interval": 30},
        options={"fan_control_enabled": True, "snapshot_buttons_enabled": False},
        entry_id="entry",
        unique_id="device",
    )
    coordinator = coordinator_module.UnifiUnasCoordinator(
        types.SimpleNamespace(),
        client,
        entry,
    )

    storage = asyncio.run(coordinator._async_update_data())

    assert storage == {"_system": {"status": "online"}}
    assert coordinator.fan_mode is None
    assert coordinator.backup_tasks == []


def test_repeated_cached_storage_failures_mark_device_offline() -> None:
    """Repeated connection failures should still mark the cached device offline."""
    client, coordinator = _transient_storage_coordinator()

    storage = asyncio.run(coordinator._async_update_data())
    coordinator.data = storage

    client.storage_failures_remaining = 2
    storage = asyncio.run(coordinator._async_update_data())
    coordinator.data = storage
    storage = asyncio.run(coordinator._async_update_data())

    assert coordinator.is_device_online is False
    assert storage["_system"]["status"] == "offline"


def test_offline_cached_storage_status_does_not_mutate_cache() -> None:
    """Offline fallback should not mutate the last successful coordinator payload."""
    client, coordinator = _transient_storage_coordinator()

    cached_storage = asyncio.run(coordinator._async_update_data())
    coordinator.data = cached_storage

    client.storage_failures_remaining = 2
    transient_storage = asyncio.run(coordinator._async_update_data())
    coordinator.data = cached_storage
    offline_storage = asyncio.run(coordinator._async_update_data())

    assert transient_storage is cached_storage
    assert cached_storage["_system"]["status"] == "online"
    assert offline_storage is not cached_storage
    assert offline_storage["_system"]["status"] == "offline"
    assert cached_storage["_system"]["status"] == "online"


def test_connection_failure_logging_is_not_repeated(caplog) -> None:
    """Offline polling should log one unavailable and one recovery message."""
    client, coordinator = _transient_storage_coordinator()
    storage = asyncio.run(coordinator._async_update_data())
    coordinator.data = storage

    caplog.set_level(logging.DEBUG)
    client.storage_failures_remaining = 3
    storage = asyncio.run(coordinator._async_update_data())
    coordinator.data = storage
    storage = asyncio.run(coordinator._async_update_data())
    coordinator.data = storage
    storage = asyncio.run(coordinator._async_update_data())
    coordinator.data = storage

    warning_messages = [
        record.message
        for record in caplog.records
        if record.levelno == logging.WARNING
    ]
    assert warning_messages == [
        "UniFi Drive is unavailable, keeping last known data: startup api not ready"
    ]

    asyncio.run(coordinator._async_update_data())

    info_messages = [
        record.message for record in caplog.records if record.levelno == logging.INFO
    ]
    assert info_messages == ["UniFi Drive connection restored"]


def test_snapshot_inventory_unexpected_errors_do_not_break_storage_update() -> None:
    """Unexpected snapshot inventory failures should not abort coordinator refresh."""
    client = _FakeUnexpectedErrorInventoryClient()
    coordinator = coordinator_module.UnifiUnasCoordinator(
        types.SimpleNamespace(),
        client,
        _FakeSnapshotPollingEntry(),
    )

    storage = asyncio.run(coordinator._async_update_data())

    assert storage == {"_system": {"status": "online"}}
    assert coordinator.snapshot_inventory == {}
    assert coordinator.snapshot_inventory_errors == {
        "shared_shared-1": coordinator_module.SNAPSHOT_INVENTORY_REASON_UNKNOWN
    }
    assert coordinator._snapshot_inventory_last_refresh is not None


def test_snapshot_inventory_refresh_runtime_errors_preserve_refresh_request() -> None:
    """Unexpected inventory refresh failures should retry explicit refresh requests."""
    client = _FakePollingInventoryClient()
    coordinator = coordinator_module.UnifiUnasCoordinator(
        types.SimpleNamespace(),
        client,
        _FakeSnapshotPollingEntry(),
    )

    async def _broken_inventory(active_target_keys):
        raise RuntimeError(f"broken for {sorted(active_target_keys)}")

    coordinator._async_get_snapshot_inventory = _broken_inventory
    coordinator.request_snapshot_inventory_refresh()

    asyncio.run(coordinator._refresh_snapshot_settings())

    assert coordinator._snapshot_inventory_refresh_requested is True
    assert coordinator._snapshot_inventory_last_refresh is not None
    assert coordinator.snapshot_inventory == {}


@pytest.mark.parametrize("error_type", [
    coordinator_module.CannotConnect, coordinator_module.UnexpectedResponse,
])
def test_snapshot_settings_transient_errors_preserve_targets_and_recover(error_type) -> None:
    """Failed reads must retain the last target list without advancing missing counts."""
    target = {"id": "target-1", "type": "shared"}

    class Client:
        snapshot_settings_read_supported = True
        fail = True

        async def async_get_snapshot_settings(self):
            if self.fail:
                raise error_type("Snapshot read failed")
            return [target]

    client = Client()
    coordinator = coordinator_module.UnifiUnasCoordinator(
        types.SimpleNamespace(), client, _FakeSnapshotPollingEntry()
    )
    cached = [target]
    coordinator.snapshot_settings = cached
    coordinator._async_refresh_snapshot_inventory_if_due = _noop_refresh
    for _ in range(3):
        asyncio.run(coordinator._refresh_snapshot_settings())
        assert coordinator.snapshot_settings is cached
        assert coordinator.snapshot_settings_available is False
    client.fail = False
    asyncio.run(coordinator._refresh_snapshot_settings())
    assert coordinator.snapshot_settings_available is True
    assert coordinator.snapshot_settings == [target]


async def _noop_refresh():
    """Avoid inventory requests when testing the settings state machine."""


def test_optional_polling_budget_publishes_core_data_and_recovers(monkeypatch) -> None:
    """A stalled optional endpoint cannot hold a storage update indefinitely."""
    monkeypatch.setattr(coordinator_module, "_OPTIONAL_REFRESH_TIMEOUT", 0.01)

    class Client:
        stalled = True
        cancelled = False

        async def async_get_storage(self):
            return {"pools": []}

        async def async_get_backup_tasks(self):
            if self.stalled:
                try:
                    await asyncio.Event().wait()
                finally:
                    self.cancelled = True
            return []

    async def run():
        client = Client()
        coordinator = coordinator_module.UnifiUnasCoordinator(
            types.SimpleNamespace(), client, _FakeSnapshotPollingEntry()
        )
        coordinator.snapshot_buttons_enabled = False
        assert await asyncio.wait_for(coordinator._async_update_data(), timeout=1) == {"pools": []}
        assert client.cancelled
        assert coordinator._optional_refresh_timed_out
        assert not coordinator._optional_refresh_lock.locked()
        client.stalled = False
        await coordinator._async_update_data()
        assert not coordinator._optional_refresh_timed_out
        async with coordinator._optional_refresh_lock:
            await coordinator._async_refresh_optional_features()

    asyncio.run(run())


@pytest.mark.parametrize("stalled,fan_enabled", [("fan", True), ("backup", True), ("backup", False)])
def test_optional_polling_reserves_time_for_later_features(monkeypatch, stalled, fan_enabled) -> None:
    """An earlier timeout on every poll must not starve healthy later endpoints."""
    monkeypatch.setattr(coordinator_module, "_OPTIONAL_REFRESH_TIMEOUT", 0.03)

    class Client(_FakeStartupOptionalClient):
        cancelled = 0

        async def stall(self):
            try:
                await asyncio.Event().wait()
            finally:
                self.cancelled += 1

        async def async_get_fan_mode(self):
            if stalled == "fan":
                await self.stall()
            return await super().async_get_fan_mode()

        async def async_get_backup_tasks(self):
            if stalled == "backup":
                await self.stall()
            return await super().async_get_backup_tasks()

    async def run():
        client = Client()
        coordinator = coordinator_module.UnifiUnasCoordinator(
            types.SimpleNamespace(), client, _FakeSnapshotPollingEntry()
        )
        coordinator.fan_control_enabled = fan_enabled
        for _ in range(3):
            assert await asyncio.wait_for(coordinator._async_update_data(), 1) == {
                "_system": {"status": "online"}
            }
            assert coordinator.snapshot_settings_available
            assert coordinator._optional_refresh_timed_out
            assert not coordinator._optional_refresh_lock.locked()
        assert client.cancelled == 3
        assert client.snapshot_settings_calls == 3
        assert client.inventory_calls == ["shared-1"]
        assert client.backup_calls == (3 if stalled == "fan" else 0)
        assert client.fan_calls == (3 if fan_enabled and stalled != "fan" else 0)

    asyncio.run(run())


def test_cancelled_optional_polling_releases_lock_without_starting_more_reads(monkeypatch) -> None:
    """Unload cancellation must propagate instead of being treated as a timeout."""
    async def run():
        client = _FakeStartupOptionalClient()
        coordinator = coordinator_module.UnifiUnasCoordinator(
            types.SimpleNamespace(), client, _FakeSnapshotPollingEntry()
        )
        coordinator.fan_control_enabled = True
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def stall():
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        monkeypatch.setattr(client, "async_get_fan_mode", stall)
        task = asyncio.create_task(coordinator._async_refresh_optional_features())
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cancelled.is_set()
        assert not coordinator._optional_refresh_lock.locked()
        assert client.backup_calls == client.snapshot_settings_calls == 0

    asyncio.run(run())


def test_cancelled_snapshot_inventory_keeps_refresh_request() -> None:
    """Timeout/unload cancellation cannot consume an explicit inventory refresh."""
    async def cancel(*args):
        raise asyncio.CancelledError

    async def run():
        coordinator = coordinator_module.UnifiUnasCoordinator(
            types.SimpleNamespace(), object(), _FakeSnapshotPollingEntry()
        )
        coordinator.request_snapshot_inventory_refresh()
        coordinator._async_get_snapshot_inventory = cancel
        try:
            await coordinator._async_refresh_snapshot_inventory_if_due()
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("Cancellation must propagate")
        assert coordinator._snapshot_inventory_pending_targets is not None
        assert coordinator._snapshot_inventory_refresh_due(coordinator_module.datetime.now(coordinator_module.UTC))
        assert coordinator._snapshot_inventory_last_refresh is None

    asyncio.run(run())


def test_snapshot_inventory_resumes_multi_target_batches_after_budget_expires(monkeypatch) -> None:
    """Aggregate latency may exceed one poll without dropping completed target reads."""
    monkeypatch.setattr(coordinator_module, "_OPTIONAL_REFRESH_TIMEOUT", 0.05)

    class Client(_FakePollingInventoryClient):
        def __init__(self):
            super().__init__()
            self.snapshot_settings = [{"id": name, "type": "shared"} for name in ("a", "b", "c")]
            self.completed = []
            self.active = 0
            self.delay = 0.03

        async def async_get_snapshot_inventory_target(self, target):
            self.inventory_calls.append(target["id"])
            self.active += 1
            try:
                await asyncio.sleep(self.delay)
                self.completed.append(target["id"])
                return {"snapshot_count": len(self.completed)}
            finally:
                self.active -= 1

    async def run():
        client = Client()
        coordinator = coordinator_module.UnifiUnasCoordinator(
            types.SimpleNamespace(), client, _FakeSnapshotPollingEntry()
        )
        for _ in range(10):
            assert await asyncio.wait_for(coordinator._async_update_data(), 1) == {
                "_system": {"status": "online"}
            }
            assert client.active == 0
            assert set(coordinator.snapshot_inventory) == {f"shared_{key}" for key in client.completed}
            if coordinator._snapshot_inventory_pending_targets is None:
                break
        assert coordinator._snapshot_inventory_pending_targets is None
        assert sorted(client.completed) == ["a", "b", "c"]
        assert coordinator._snapshot_inventory_last_refresh is not None
        assert coordinator.snapshot_inventory_errors == {}
        calls = list(client.inventory_calls)
        await coordinator._async_update_data()
        assert client.inventory_calls == calls
        client.delay = 0
        coordinator.request_snapshot_inventory_refresh()
        await coordinator._async_update_data()
        assert sorted(client.completed) == ["a", "a", "b", "b", "c", "c"]

    asyncio.run(run())


def test_snapshot_inventory_stalled_target_does_not_starve_peers_or_survive_removal(monkeypatch) -> None:
    """Rotate interrupted targets and reconcile the pending batch with new settings."""
    monkeypatch.setattr(coordinator_module, "_OPTIONAL_REFRESH_TIMEOUT", 0.01)
    read_statuses = []
    monkeypatch.setattr(
        coordinator_module, "async_update_snapshot_read_issue",
        lambda *args, supported: read_statuses.append(supported),
    )

    class Client(_FakePollingInventoryClient):
        async def async_get_snapshot_inventory_target(self, target):
            self.inventory_calls.append(target["id"])
            if target["id"] == "a":
                await asyncio.Event().wait()
            return {"snapshot_count": 1}

    async def run():
        client = Client()
        client.snapshot_settings = [{"id": name, "type": "shared"} for name in ("a", "b", "c")]
        coordinator = coordinator_module.UnifiUnasCoordinator(
            types.SimpleNamespace(), client, _FakeSnapshotPollingEntry()
        )
        await coordinator._async_update_data()
        assert read_statuses == [True]
        assert list(coordinator._snapshot_inventory_pending_targets) == ["shared_b", "shared_c", "shared_a"]
        await coordinator._async_update_data()
        assert set(coordinator.snapshot_inventory) == {"shared_b", "shared_c"}
        assert client.inventory_calls == ["a", "b", "c", "a"]
        coordinator._snapshot_inventory_batch_started -= coordinator_module._SNAPSHOT_INVENTORY_REFRESH_INTERVAL
        await coordinator._async_update_data()
        await coordinator._async_update_data()
        assert client.inventory_calls.count("b") == client.inventory_calls.count("c") == 2
        before_removal = list(client.inventory_calls)
        client.snapshot_settings = [{"id": name, "type": "shared"} for name in ("b", "d")]
        await coordinator._async_update_data()
        assert client.inventory_calls == [*before_removal, "d"]
        assert set(coordinator.snapshot_inventory) == {"shared_b", "shared_d"}
        assert coordinator._snapshot_inventory_pending_targets is None
        coordinator.snapshot_buttons_enabled = False
        await coordinator._async_update_data()
        assert coordinator.snapshot_inventory == {}
        assert coordinator._snapshot_inventory_pending_targets is None

    asyncio.run(run())


def test_snapshot_inventory_preserves_new_request_across_partial_batch() -> None:
    """A write request during a cancelled batch must requeue completed targets."""
    class Client(_FakePollingInventoryClient):
        interrupted = False
        callback = None

        async def async_get_snapshot_inventory_target(self, target):
            self.inventory_calls.append(target["id"])
            if target["id"] == "b" and not self.interrupted:
                self.interrupted = True
                self.callback()
                raise asyncio.CancelledError
            return {"snapshot_count": len(self.inventory_calls)}

    async def run():
        client = Client()
        client.snapshot_settings = [{"id": name, "type": "shared"} for name in ("a", "b")]
        coordinator = coordinator_module.UnifiUnasCoordinator(
            types.SimpleNamespace(), client, _FakeSnapshotPollingEntry()
        )
        client.callback = coordinator.request_snapshot_inventory_refresh
        with pytest.raises(asyncio.CancelledError):
            await coordinator._refresh_snapshot_settings()
        assert coordinator.snapshot_inventory == {"shared_a": {"snapshot_count": 1}}
        assert coordinator._snapshot_inventory_refresh_requested
        await coordinator._refresh_snapshot_settings()
        assert client.inventory_calls == ["a", "b", "b", "a"]
        assert not coordinator._snapshot_inventory_refresh_requested
        assert coordinator.snapshot_inventory == {
            "shared_a": {"snapshot_count": 4}, "shared_b": {"snapshot_count": 3},
        }
        await coordinator._refresh_snapshot_settings()
        assert client.inventory_calls == ["a", "b", "b", "a"]

    asyncio.run(run())


def test_snapshot_settings_connection_failures_do_not_create_repairs() -> None:
    """Powered-off/offline devices should not create snapshot repair issues."""
    original_create_issue = coordinator_module.async_create_snapshot_read_issue
    original_update_issue = coordinator_module.async_update_snapshot_read_issue
    original_clear_issues = coordinator_module.async_clear_snapshot_issues

    created_errors: list[str] = []
    updated_calls: list[bool | None] = []
    cleared_calls: list[bool] = []

    class _FailingSnapshotSettingsClient:
        snapshot_settings_read_supported = False

        async def async_get_storage(self) -> dict[str, dict[str, str]]:
            return {"_system": {"status": "online"}}

        async def async_get_backup_tasks(self) -> list:
            return []

        async def async_get_snapshot_settings(self) -> list:
            raise coordinator_module.CannotConnect("snapshot controls unavailable")

    try:
        coordinator_module.async_create_snapshot_read_issue = (
            lambda hass, entry, err: created_errors.append(str(err))
        )
        coordinator_module.async_update_snapshot_read_issue = (
            lambda hass, entry, supported: updated_calls.append(supported)
        )
        coordinator_module.async_clear_snapshot_issues = (
            lambda hass, entry: cleared_calls.append(True)
        )

        client = _FailingSnapshotSettingsClient()
        coordinator = coordinator_module.UnifiUnasCoordinator(
            types.SimpleNamespace(),
            client,
            _FakeSnapshotPollingEntry(),
        )
        storage = asyncio.run(coordinator._async_update_data())

        assert storage == {"_system": {"status": "online"}}
        assert coordinator.snapshot_settings == []
        assert created_errors == []
        assert updated_calls == []
        assert cleared_calls == []
    finally:
        coordinator_module.async_create_snapshot_read_issue = original_create_issue
        coordinator_module.async_update_snapshot_read_issue = original_update_issue
        coordinator_module.async_clear_snapshot_issues = original_clear_issues


def test_snapshot_settings_unsupported_failures_keep_snapshot_read_issue() -> None:
    """Unsupported snapshot endpoint failures should create a focused read issue."""
    original_create_issue = coordinator_module.async_create_snapshot_read_issue
    original_update_issue = coordinator_module.async_update_snapshot_read_issue
    original_clear_issues = coordinator_module.async_clear_snapshot_issues

    created_errors: list[str] = []
    updated_calls: list[bool | None] = []
    cleared_calls: list[bool] = []

    class _UnsupportedSnapshotSettingsClient:
        snapshot_settings_read_supported = False

        async def async_get_storage(self) -> dict[str, dict[str, str]]:
            return {"_system": {"status": "online"}}

        async def async_get_backup_tasks(self) -> list:
            return []

        async def async_get_snapshot_settings(self) -> list:
            raise coordinator_module.UnsupportedFeature(
                "snapshot controls unavailable"
            )

    try:
        coordinator_module.async_create_snapshot_read_issue = (
            lambda hass, entry, err: created_errors.append(str(err))
        )
        coordinator_module.async_update_snapshot_read_issue = (
            lambda hass, entry, supported: updated_calls.append(supported)
        )
        coordinator_module.async_clear_snapshot_issues = (
            lambda hass, entry: cleared_calls.append(True)
        )

        client = _UnsupportedSnapshotSettingsClient()
        coordinator = coordinator_module.UnifiUnasCoordinator(
            types.SimpleNamespace(),
            client,
            _FakeSnapshotPollingEntry(),
        )
        storage = asyncio.run(coordinator._async_update_data())

        assert storage == {"_system": {"status": "online"}}
        assert coordinator.snapshot_settings == []
        assert created_errors == ["snapshot controls unavailable"]
        assert updated_calls == []
        assert cleared_calls == []
    finally:
        coordinator_module.async_create_snapshot_read_issue = original_create_issue
        coordinator_module.async_update_snapshot_read_issue = original_update_issue
        coordinator_module.async_clear_snapshot_issues = original_clear_issues
