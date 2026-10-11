"""Unit tests for UniFi Drive service helpers."""

from __future__ import annotations

import asyncio
from enum import Enum
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
import types

import pytest


def _load_services_module():
    root = Path(__file__).resolve().parents[1]
    package_root = root / "custom_components" / "unifi_unas"

    for module_name in tuple(sys.modules):
        if module_name.startswith("custom_components.unifi_unas"):
            sys.modules.pop(module_name, None)

    custom_components_pkg = types.ModuleType("custom_components")
    custom_components_pkg.__path__ = [str(root / "custom_components")]
    sys.modules.setdefault("custom_components", custom_components_pkg)

    drive_pkg = types.ModuleType("custom_components.unifi_unas")
    drive_pkg.__path__ = [str(package_root)]
    sys.modules["custom_components.unifi_unas"] = drive_pkg

    ha_pkg = types.ModuleType("homeassistant")
    sys.modules["homeassistant"] = ha_pkg

    config_entries_pkg = types.ModuleType("homeassistant.config_entries")
    config_entries_pkg.ConfigEntry = object
    sys.modules["homeassistant.config_entries"] = config_entries_pkg

    const_pkg = types.ModuleType("homeassistant.const")

    class Platform(str, Enum):
        BINARY_SENSOR = "binary_sensor"
        BUTTON = "button"
        NUMBER = "number"
        SELECT = "select"
        SENSOR = "sensor"
        SWITCH = "switch"
        TIME = "time"
        UPDATE = "update"

    const_pkg.Platform = Platform
    sys.modules["homeassistant.const"] = const_pkg

    core_pkg = types.ModuleType("homeassistant.core")
    core_pkg.HomeAssistant = object
    core_pkg.ServiceCall = object
    sys.modules["homeassistant.core"] = core_pkg

    helpers_pkg = types.ModuleType("homeassistant.helpers")
    sys.modules["homeassistant.helpers"] = helpers_pkg

    issue_registry_pkg = types.ModuleType("homeassistant.helpers.issue_registry")
    issue_registry_pkg.IssueSeverity = types.SimpleNamespace(WARNING="warning")
    issue_registry_pkg.async_create_issue = lambda *args, **kwargs: None
    issue_registry_pkg.async_delete_issue = lambda *args, **kwargs: None
    sys.modules["homeassistant.helpers.issue_registry"] = issue_registry_pkg

    exceptions_pkg = types.ModuleType("homeassistant.exceptions")

    class HomeAssistantError(Exception):
        """Base Home Assistant error stub."""

        def __init__(
            self,
            *args,
            translation_domain=None,
            translation_key=None,
            translation_placeholders=None,
        ) -> None:
            super().__init__(*args)
            self.translation_domain = translation_domain
            self.translation_key = translation_key
            self.translation_placeholders = translation_placeholders

    class ServiceValidationError(HomeAssistantError):
        """Service validation error stub."""

    exceptions_pkg.HomeAssistantError = HomeAssistantError
    exceptions_pkg.ServiceValidationError = ServiceValidationError
    sys.modules["homeassistant.exceptions"] = exceptions_pkg

    vol_pkg = types.ModuleType("voluptuous")
    vol_pkg.Invalid = ValueError
    vol_pkg.Required = lambda key, default=None: key
    vol_pkg.Optional = lambda key, default=None: key
    vol_pkg.Schema = lambda schema: schema
    vol_pkg.All = lambda *validators: validators[-1] if validators else (lambda value: value)
    vol_pkg.Coerce = lambda target: target
    vol_pkg.In = lambda options: (lambda value: value if value in options else None)
    vol_pkg.Range = lambda **kwargs: (lambda value: value)
    sys.modules["voluptuous"] = vol_pkg

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
    sys.modules["custom_components.unifi_unas.api"] = api_pkg

    coordinator_pkg = types.ModuleType("custom_components.unifi_unas.coordinator")

    class UnifiUnasCoordinator:
        """Coordinator type stub."""

    coordinator_pkg.UnifiUnasCoordinator = UnifiUnasCoordinator
    sys.modules["custom_components.unifi_unas.coordinator"] = coordinator_pkg

    wol_pkg = types.ModuleType("custom_components.unifi_unas.wake_on_lan")
    wol_pkg.WakeOnLanError = Exception

    async def _send_magic_packet(*args, **kwargs):
        return None

    wol_pkg.async_send_magic_packet = _send_magic_packet
    sys.modules["custom_components.unifi_unas.wake_on_lan"] = wol_pkg

    const_spec = spec_from_file_location(
        "custom_components.unifi_unas.const",
        package_root / "const.py",
    )
    if const_spec is None or const_spec.loader is None:
        raise RuntimeError("Could not load const module spec")
    const_module = module_from_spec(const_spec)
    sys.modules["custom_components.unifi_unas.const"] = const_module
    const_spec.loader.exec_module(const_module)

    services_spec = spec_from_file_location(
        "custom_components.unifi_unas.services",
        package_root / "services.py",
    )
    if services_spec is None or services_spec.loader is None:
        raise RuntimeError("Could not load services module spec")
    services_module = module_from_spec(services_spec)
    sys.modules["custom_components.unifi_unas.services"] = services_module
    services_spec.loader.exec_module(services_module)
    return services_module, UnifiUnasCoordinator


services_module, CoordinatorBase = _load_services_module()


class _FakeSnapshotClient:
    def __init__(self, *, targets: list[dict] | None = None) -> None:
        self.targets = list(targets or [])
        self.snapshot_settings_read_supported = True
        self.read_count = 0
        self.created: list[tuple[dict, dict]] = []
        self.updated: list[tuple[dict, dict]] = []

    async def async_get_snapshot_settings(self) -> list[dict]:
        self.read_count += 1
        return list(self.targets)

    async def async_create_snapshot_target(
        self,
        target: dict,
        *,
        description: str = "",
        locked: bool = False,
    ) -> None:
        self.created.append(
            (target, {"description": description, "locked": locked})
        )

    async def async_update_snapshot_target_settings(
        self,
        target: dict,
        **kwargs,
    ) -> None:
        self.updated.append((target, kwargs))


class _FakeServiceClient(_FakeSnapshotClient):
    def __init__(self, *, targets: list[dict] | None = None) -> None:
        super().__init__(targets=targets)
        self.reboot_count = 0
        self.poweroff_count = 0
        self.fan_modes: list[str] = []
        self.fail_next: Exception | None = None
        self.snapshot_settings_read_supported = True

    async def _maybe_fail(self) -> None:
        if self.fail_next is not None:
            err = self.fail_next
            self.fail_next = None
            raise err

    async def async_reboot(self) -> None:
        await self._maybe_fail()
        self.reboot_count += 1

    async def async_poweroff(self) -> None:
        await self._maybe_fail()
        self.poweroff_count += 1

    async def async_set_fan_mode(self, mode: str) -> str:
        await self._maybe_fail()
        self.fan_modes.append(mode)
        return mode


class _FakeCoordinator(CoordinatorBase):
    def __init__(
        self,
        *,
        online: bool,
        snapshot_settings: list[dict] | None = None,
        client: _FakeSnapshotClient | None = None,
    ) -> None:
        self.is_device_online = online
        self.snapshot_settings = list(snapshot_settings or [])
        self.client = client or _FakeSnapshotClient()
        self.refresh_count = 0
        self.snapshot_inventory_refresh_requested = False
        self.config_entry = None
        self.hass = None

    async def async_request_refresh(self) -> None:
        self.refresh_count += 1

    def request_snapshot_inventory_refresh(self) -> None:
        self.snapshot_inventory_refresh_requested = True


def _service_call(data: dict | None = None):
    return types.SimpleNamespace(data=data or {})


def _hass_for_loaded_entry(
    coordinator: _FakeCoordinator,
    *,
    entry_id: str = "entry-1",
):
    entry = types.SimpleNamespace(
        domain=services_module.DOMAIN,
        entry_id=entry_id,
        runtime_data=coordinator,
    )
    return types.SimpleNamespace(
        data={services_module.DOMAIN: {entry_id: coordinator}},
        config_entries=types.SimpleNamespace(
            async_get_entry=lambda requested_id: (
                entry if requested_id == entry_id else None
            ),
            async_entries=lambda domain=None: [entry]
            if domain in (None, services_module.DOMAIN)
            else [],
        ),
    )


def test_service_offline_guard_blocks_write_actions() -> None:
    """Service helpers should reject offline write actions before calling clients."""
    coordinator = _FakeCoordinator(online=False)

    try:
        services_module._raise_if_device_offline(coordinator, "restart")
    except services_module.ServiceValidationError as err:
        assert "offline" in str(err)
        assert err.translation_domain == services_module.DOMAIN
        assert err.translation_key == "device_offline"
        assert err.translation_placeholders == {"action": "restart"}
    else:
        raise AssertionError("offline services should raise ServiceValidationError")


def test_service_validation_errors_are_translatable() -> None:
    """Service validation helpers should keep fallback text and translation keys."""
    try:
        services_module._snapshot_limit_service_value("not-a-number")
    except services_module.ServiceValidationError as err:
        assert "whole number" in str(err)
        assert err.translation_domain == services_module.DOMAIN
        assert err.translation_key == "snapshot_limit_whole_number"
    else:
        raise AssertionError("invalid limit should raise ServiceValidationError")


def test_service_schema_values_normalize_and_reject_invalid_inputs() -> None:
    """Service schemas should normalize valid values and raise safe schema errors."""
    assert services_module._snapshot_limit_service_value("3") == 3
    assert services_module._snapshot_schedule_service_option("daily") == "Daily"
    assert services_module._snapshot_schedule_time_service_value("12:15 am") == "00:15"
    assert services_module._snapshot_weekday_service_value("Friday") == "5"
    assert services_module._snapshot_weekday_service_value("6") == "6"
    assert services_module._snapshot_monthday_service_value("31") == "31"

    invalid_inputs = (
        services_module._snapshot_limit_schema_value,
        services_module._snapshot_schedule_schema_value,
        services_module._snapshot_schedule_time_schema_value,
        services_module._snapshot_weekday_schema_value,
        services_module._snapshot_monthday_schema_value,
    )
    for validator in invalid_inputs:
        try:
            validator(object())
        except Exception as err:
            assert isinstance(err, services_module.vol.Invalid)
        else:
            raise AssertionError(f"{validator.__name__} should reject invalid input")

    for value in (1.2, services_module.MAX_SNAPSHOT_LIMIT + 1):
        try:
            services_module._snapshot_limit_service_value(value)
        except services_module.ServiceValidationError:
            pass
        else:
            raise AssertionError("invalid snapshot limit should fail")

    for value in (1.5, 0, 32):
        try:
            services_module._snapshot_monthday_service_value(value)
        except services_module.ServiceValidationError:
            pass
        else:
            raise AssertionError("invalid month day should fail")


def test_service_client_action_does_not_run_while_offline() -> None:
    """Offline power services should not call into the client action."""
    called = False

    async def _action() -> None:
        nonlocal called
        called = True

    try:
        asyncio.run(
            services_module._async_call_client_action(
                _FakeCoordinator(online=False),
                action_name="restart",
                action=_action,
            )
        )
    except services_module.ServiceValidationError:
        pass
    else:
        raise AssertionError("offline client action should fail")

    assert called is False


def test_resolve_entry_and_coordinator_supports_entry_id_and_fallbacks() -> None:
    """Service targeting should resolve explicit and implicit loaded entries."""
    coordinator = _FakeCoordinator(online=True)
    hass = _hass_for_loaded_entry(coordinator)

    entry, resolved = services_module._resolve_entry_and_coordinator(hass, "entry-1")
    assert entry.entry_id == "entry-1"
    assert resolved is coordinator

    entry, resolved = services_module._resolve_entry_and_coordinator(hass, None)
    assert entry.entry_id == "entry-1"
    assert resolved is coordinator

    stale_hass = types.SimpleNamespace(
        data={services_module.DOMAIN: {"entry-1": coordinator}},
        config_entries=types.SimpleNamespace(
            async_get_entry=lambda entry_id: None,
            async_entries=lambda domain=None: [],
        ),
    )
    try:
        services_module._resolve_entry_and_coordinator(stale_hass, "missing")
    except services_module.ServiceValidationError as err:
        assert err.translation_key == "config_entry_not_found"
    else:
        raise AssertionError("missing entry should fail")


def test_resolve_entry_and_coordinator_uses_domain_data_fallback() -> None:
    """Implicit targeting should support loaded coordinators during HA startup."""
    coordinator = _FakeCoordinator(online=True)
    entry = types.SimpleNamespace(
        domain=services_module.DOMAIN,
        entry_id="entry-1",
        runtime_data=None,
    )
    hass = types.SimpleNamespace(
        data={services_module.DOMAIN: {"entry-1": coordinator}},
        config_entries=types.SimpleNamespace(
            async_get_entry=lambda entry_id: entry if entry_id == "entry-1" else None,
            async_entries=lambda domain=None: [],
        ),
    )

    resolved_entry, resolved = services_module._resolve_entry_and_coordinator(
        hass,
        None,
    )

    assert resolved_entry is entry
    assert resolved is coordinator


def test_resolve_entry_and_coordinator_rejects_ambiguous_loaded_entries() -> None:
    """Implicit targeting should require an entry ID when multiple entries are loaded."""
    coordinators = {
        "entry-1": _FakeCoordinator(online=True),
        "entry-2": _FakeCoordinator(online=True),
    }
    entries = [
        types.SimpleNamespace(
            domain=services_module.DOMAIN,
            entry_id=entry_id,
            runtime_data=coordinator,
        )
        for entry_id, coordinator in coordinators.items()
    ]
    hass = types.SimpleNamespace(
        data={services_module.DOMAIN: coordinators},
        config_entries=types.SimpleNamespace(
            async_get_entry=lambda entry_id: next(
                (entry for entry in entries if entry.entry_id == entry_id),
                None,
            ),
            async_entries=lambda domain=None: entries,
        ),
    )

    try:
        services_module._resolve_entry_and_coordinator(hass, None)
    except services_module.ServiceValidationError as err:
        assert err.translation_key == "multiple_loaded_entries"
    else:
        raise AssertionError("ambiguous loaded entries should fail")


def test_resolve_entry_and_coordinator_requires_loaded_entry() -> None:
    """Service targeting should reject entries that are known but not loaded."""
    entry = types.SimpleNamespace(domain=services_module.DOMAIN)
    hass = types.SimpleNamespace(
        data={services_module.DOMAIN: {}},
        config_entries=types.SimpleNamespace(
            async_get_entry=lambda entry_id: entry if entry_id == "entry-1" else None
        ),
    )

    try:
        services_module._resolve_entry_and_coordinator(hass, "entry-1")
    except services_module.ServiceValidationError as err:
        assert "not loaded" in str(err)
    else:
        raise AssertionError("unloaded entry should not resolve")


def test_snapshot_services_are_registered() -> None:
    """Snapshot automation services should be registered with other services."""

    class FakeServiceRegistry:
        def __init__(self) -> None:
            self.registered: list[str] = []

        def has_service(self, domain: str, service: str) -> bool:
            return False

        def async_register(self, domain: str, service: str, handler, schema) -> None:
            self.registered.append(service)

    services = FakeServiceRegistry()
    services_module.async_register_services(types.SimpleNamespace(services=services))

    assert services_module.SERVICE_CREATE_SNAPSHOT in services.registered
    assert services_module.SERVICE_SET_SNAPSHOT_LIMIT in services.registered
    assert services_module.SERVICE_SET_SNAPSHOT_SCHEDULE in services.registered


def test_service_registration_is_idempotent() -> None:
    """Service registration should return early once the first service exists."""

    class FakeServiceRegistry:
        def __init__(self) -> None:
            self.registered: list[str] = []

        def has_service(self, domain: str, service: str) -> bool:
            return True

        def async_register(self, domain: str, service: str, handler, schema) -> None:
            self.registered.append(service)

    services = FakeServiceRegistry()
    services_module.async_register_services(types.SimpleNamespace(services=services))

    assert services.registered == []


def test_power_and_fan_service_handlers_call_clients() -> None:
    """Registered power and fan handlers should resolve entries and call clients."""
    client = _FakeServiceClient()
    coordinator = _FakeCoordinator(online=True, client=client)
    hass = _hass_for_loaded_entry(coordinator)

    asyncio.run(
        services_module._async_service_reboot(hass)(
            _service_call({services_module.ATTR_ENTRY_ID: "entry-1"})
        )
    )
    asyncio.run(
        services_module._async_service_shutdown(hass)(
            _service_call({services_module.ATTR_ENTRY_ID: "entry-1"})
        )
    )
    asyncio.run(
        services_module._async_service_set_fan_mode(hass)(
            _service_call(
                {
                    services_module.ATTR_ENTRY_ID: "entry-1",
                    services_module.ATTR_FAN_MODE: "Cooling",
                }
            )
        )
    )

    assert client.reboot_count == 1
    assert client.poweroff_count == 1
    assert client.fan_modes == ["Cooling"]
    assert coordinator.refresh_count == 1


def test_power_and_fan_service_handlers_translate_api_errors() -> None:
    """Power and fan service handlers should map API failures to HA errors."""
    client = _FakeServiceClient()
    coordinator = _FakeCoordinator(online=True, client=client)
    hass = _hass_for_loaded_entry(coordinator)

    client.fail_next = services_module.InvalidAuth("forbidden")
    try:
        asyncio.run(
            services_module._async_service_reboot(hass)(
                _service_call({services_module.ATTR_ENTRY_ID: "entry-1"})
            )
        )
    except services_module.HomeAssistantError as err:
        assert err.translation_key == "system_action_permission"
    else:
        raise AssertionError("permission failure should be translated")

    client.fail_next = services_module.UnexpectedResponse("bad response")
    try:
        asyncio.run(
            services_module._async_service_shutdown(hass)(
                _service_call({services_module.ATTR_ENTRY_ID: "entry-1"})
            )
        )
    except services_module.HomeAssistantError as err:
        assert err.translation_key == "system_action_failed"
    else:
        raise AssertionError("system action failures should be translated")

    for api_error, translation_key in (
        (services_module.UnsupportedFeature("missing"), "fan_mode_unsupported"),
        (services_module.CannotConnect("offline"), "fan_mode_failed"),
        (services_module.InvalidAuth("forbidden"), "fan_mode_permission"),
    ):
        client.fail_next = api_error
        try:
            asyncio.run(
                services_module._async_service_set_fan_mode(hass)(
                    _service_call(
                        {
                            services_module.ATTR_ENTRY_ID: "entry-1",
                            services_module.ATTR_FAN_MODE: "Quiet",
                        }
                    )
                )
            )
        except services_module.HomeAssistantError as err:
            assert err.translation_key == translation_key
        else:
            raise AssertionError(f"{translation_key} should be raised")


def test_wake_on_lan_service_sends_packet_and_reports_configuration_errors(
    monkeypatch,
) -> None:
    """WOL service should stay usable when the device is powered off."""
    coordinator = _FakeCoordinator(online=False)
    hass = _hass_for_loaded_entry(coordinator)
    entry = hass.config_entries.async_get_entry("entry-1")
    entry.data = {
        services_module.CONF_WOL_ENABLED: True,
        services_module.CONF_WOL_MAC_ADDRESS: "aa:bb:cc:dd:ee:ff",
        services_module.CONF_WOL_BROADCAST_ADDRESS: "192.0.2.255",
        services_module.CONF_WOL_PORT: 9,
    }
    sent: list[tuple[str, str, int]] = []

    async def _send_magic_packet(mac_address: str, *, broadcast_address: str, port: int):
        sent.append((mac_address, broadcast_address, port))

    monkeypatch.setattr(services_module, "async_send_magic_packet", _send_magic_packet)

    asyncio.run(
        services_module._async_service_wake_on_lan(hass)(
            _service_call({services_module.ATTR_ENTRY_ID: "entry-1"})
        )
    )

    assert sent == [("aa:bb:cc:dd:ee:ff", "192.0.2.255", 9)]

    entry.data[services_module.CONF_WOL_ENABLED] = False
    try:
        asyncio.run(
            services_module._async_service_wake_on_lan(hass)(
                _service_call({services_module.ATTR_ENTRY_ID: "entry-1"})
            )
        )
    except services_module.ServiceValidationError as err:
        assert err.translation_key == "wake_on_lan_disabled"
    else:
        raise AssertionError("disabled WOL should fail")

    entry.data[services_module.CONF_WOL_ENABLED] = True
    entry.data[services_module.CONF_WOL_MAC_ADDRESS] = ""
    try:
        asyncio.run(
            services_module._async_service_wake_on_lan(hass)(
                _service_call({services_module.ATTR_ENTRY_ID: "entry-1"})
            )
        )
    except services_module.ServiceValidationError as err:
        assert err.translation_key == "wake_on_lan_mac_missing"
    else:
        raise AssertionError("missing WOL MAC should fail")


def test_wake_on_lan_service_reports_send_failures(monkeypatch) -> None:
    """WOL packet send failures should preserve a translatable HA error."""
    coordinator = _FakeCoordinator(online=False)
    hass = _hass_for_loaded_entry(coordinator)
    entry = hass.config_entries.async_get_entry("entry-1")
    entry.data = {
        services_module.CONF_WOL_ENABLED: True,
        services_module.CONF_WOL_MAC_ADDRESS: "bad-mac",
    }

    async def _send_magic_packet(*args, **kwargs):
        raise ValueError("invalid target")

    monkeypatch.setattr(services_module, "async_send_magic_packet", _send_magic_packet)

    try:
        asyncio.run(
            services_module._async_service_wake_on_lan(hass)(
                _service_call({services_module.ATTR_ENTRY_ID: "entry-1"})
            )
        )
    except services_module.HomeAssistantError as err:
        assert err.translation_key == "wake_on_lan_send_failed"
        assert err.translation_placeholders == {"error": "invalid target"}
    else:
        raise AssertionError("WOL send failure should be translated")


def test_snapshot_target_from_call_data_resolves_stable_key() -> None:
    """Service target filters should resolve dynamic snapshot targets."""
    targets = [
        {"id": "shared-1", "type": "shared", "name": "Shared Drive"},
        {"id": "backup-user", "type": "mydrive", "name": "Backup User"},
    ]

    target = services_module._snapshot_target_from_call_data(
        targets,
        {services_module.ATTR_SNAPSHOT_TARGET_KEY: "mydrive_backup-user"},
    )

    assert target["name"] == "Backup User"


def test_snapshot_target_from_call_data_resolves_all_filter_types() -> None:
    """Snapshot target filters should match keys, IDs, names and canonical types."""
    targets = [
        {
            "id": "shared-1",
            "type": "shared",
            "name": "Shared Drive",
            "shared_drive_name": "Shared Drive",
        },
        {
            "id": "backup-user",
            "user_id": "user-1",
            "type": "mydrive",
            "name": "Backup User",
        },
    ]

    assert (
        services_module._snapshot_target_from_call_data(
            targets,
            {services_module.ATTR_SNAPSHOT_TARGET_ID: "user-1"},
        )["id"]
        == "backup-user"
    )
    assert (
        services_module._snapshot_target_from_call_data(
            targets,
            {services_module.ATTR_SNAPSHOT_TARGET_NAME: "shared drive"},
        )["id"]
        == "shared-1"
    )
    assert (
        services_module._snapshot_target_from_call_data(
            targets,
            {services_module.ATTR_SNAPSHOT_TARGET_TYPE: "personal"},
        )["id"]
        == "backup-user"
    )

    for data, translation_key in (
        ({}, "snapshot_targets_ambiguous"),
        ({services_module.ATTR_SNAPSHOT_TARGET_ID: "missing"}, "snapshot_target_no_match"),
        ({services_module.ATTR_SNAPSHOT_TARGET_TYPE: "invalid"}, "snapshot_target_type"),
    ):
        try:
            services_module._snapshot_target_from_call_data(targets, data)
        except services_module.ServiceValidationError as err:
            assert err.translation_key == translation_key
        else:
            raise AssertionError(f"{translation_key} should be raised")

    try:
        services_module._snapshot_target_from_call_data([], {})
    except services_module.ServiceValidationError as err:
        assert err.translation_key == "snapshot_targets_empty"
    else:
        raise AssertionError("empty target list should fail")


def test_snapshot_target_from_call_data_rejects_ambiguous_targets() -> None:
    """Ambiguous service calls should require a more specific target filter."""
    targets = [
        {"id": "shared-1", "type": "shared", "name": "Shared Drive"},
        {"id": "shared-2", "type": "shared", "name": "Archive"},
    ]

    try:
        services_module._snapshot_target_from_call_data(
            targets,
            {services_module.ATTR_SNAPSHOT_TARGET_TYPE: "shared"},
        )
    except services_module.ServiceValidationError as err:
        assert "Multiple" in str(err)
    else:
        raise AssertionError("ambiguous snapshot target should not resolve")


def test_snapshot_target_from_call_fetches_targets_when_not_cached() -> None:
    """Snapshot services should work even when snapshot entities are not cached."""
    target = {"id": "backup-user", "type": "mydrive", "name": "Backup User"}
    client = _FakeSnapshotClient(targets=[target])
    coordinator = _FakeCoordinator(online=True, client=client)

    resolved = asyncio.run(
        services_module._async_snapshot_target_from_call(
            coordinator,
            {services_module.ATTR_SNAPSHOT_TARGET_NAME: "Backup User"},
            action_name="create a snapshot",
        )
    )

    assert resolved == target
    assert client.read_count == 1
    assert coordinator.snapshot_settings == [target]


def test_snapshot_target_fetch_errors_are_translated_and_create_repairs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On-demand snapshot target reads should translate endpoint failures."""
    created_read_issues: list[str] = []
    updated_read_issues: list[bool | None] = []

    monkeypatch.setattr(
        services_module,
        "async_create_snapshot_read_issue",
        lambda hass, entry, err: created_read_issues.append(type(err).__name__),
    )
    monkeypatch.setattr(
        services_module,
        "async_update_snapshot_read_issue",
        lambda hass, entry, supported: updated_read_issues.append(supported),
    )

    for api_error, translation_key in (
        (services_module.InvalidAuth("forbidden"), "snapshot_targets_permission"),
        (services_module.UnsupportedFeature("missing"), "snapshot_targets_read_failed"),
        (services_module.CannotConnect("offline"), "snapshot_targets_read_failed"),
    ):
        client = _FakeServiceClient()
        client.async_get_snapshot_settings = _raise_async(api_error)
        coordinator = _FakeCoordinator(online=True, client=client)
        coordinator.config_entry = types.SimpleNamespace(entry_id="entry-1")
        coordinator.hass = object()

        try:
            asyncio.run(services_module._async_snapshot_targets_for_service(coordinator))
        except services_module.HomeAssistantError as err:
            assert err.translation_key == translation_key
        else:
            raise AssertionError(f"{translation_key} should be raised")

    client = _FakeServiceClient(targets=[{"id": "shared-1", "type": "shared"}])
    coordinator = _FakeCoordinator(online=True, client=client)
    coordinator.config_entry = types.SimpleNamespace(entry_id="entry-1")
    coordinator.hass = object()

    assert asyncio.run(services_module._async_snapshot_targets_for_service(coordinator)) == [
        {"id": "shared-1", "type": "shared"}
    ]
    assert updated_read_issues == [True]
    assert "InvalidAuth" in created_read_issues
    assert "UnsupportedFeature" in created_read_issues


def _raise_async(err: Exception):
    async def _raiser(*args, **kwargs):
        raise err

    return _raiser


def test_snapshot_schedule_update_from_call_data_normalizes_payload() -> None:
    """Schedule service data should map to the same API update fields as entities."""
    update = services_module._snapshot_schedule_update_from_call_data(
        {
            services_module.ATTR_SNAPSHOT_SCHEDULE: "weekly",
            services_module.ATTR_SNAPSHOT_SCHEDULE_TIME: "12:00 am",
            services_module.ATTR_SNAPSHOT_WEEKDAY: "Wednesday",
        }
    )

    assert update == {
        "schedule_frequency": "Weekly",
        "schedule_time": "00:00",
        "schedule_weekdays": "3",
    }


def test_snapshot_monthly_schedule_update_from_call_data() -> None:
    """Monthly schedule service data should normalize month-day selectors."""
    update = services_module._snapshot_schedule_update_from_call_data(
        {
            services_module.ATTR_SNAPSHOT_SCHEDULE: "Monthly",
            services_module.ATTR_SNAPSHOT_MONTHDAY: 15,
        }
    )

    assert update == {
        "schedule_frequency": "Monthly",
        "schedule_monthdays": "15",
    }


def test_snapshot_action_refreshes_after_success() -> None:
    """Snapshot services should refresh coordinator data after successful writes."""
    target = {"id": "shared-1", "type": "shared", "name": "Shared Drive"}
    client = _FakeSnapshotClient()
    coordinator = _FakeCoordinator(
        online=True,
        snapshot_settings=[target],
        client=client,
    )

    async def _action() -> None:
        await client.async_create_snapshot_target(
            target,
            description="Before maintenance",
            locked=True,
        )

    asyncio.run(
        services_module._async_call_snapshot_action(
            coordinator,
            target,
            action_name="create snapshot",
            action=_action,
        )
    )

    assert client.created == [
        (target, {"description": "Before maintenance", "locked": True})
    ]
    assert coordinator.snapshot_inventory_refresh_requested is True
    assert coordinator.refresh_count == 1


def test_snapshot_service_handlers_update_targets() -> None:
    """Snapshot service handlers should normalize service data and call the client."""
    target = {"id": "shared-1", "type": "shared", "name": "Shared Drive"}
    client = _FakeServiceClient()
    coordinator = _FakeCoordinator(
        online=True,
        snapshot_settings=[target],
        client=client,
    )
    hass = _hass_for_loaded_entry(coordinator)

    asyncio.run(
        services_module._async_service_create_snapshot(hass)(
            _service_call(
                {
                    services_module.ATTR_ENTRY_ID: "entry-1",
                    services_module.ATTR_DESCRIPTION: "Before update",
                    services_module.ATTR_LOCKED: True,
                }
            )
        )
    )
    asyncio.run(
        services_module._async_service_set_snapshot_limit(hass)(
            _service_call(
                {
                    services_module.ATTR_ENTRY_ID: "entry-1",
                    services_module.ATTR_SNAPSHOT_LIMIT: "9",
                }
            )
        )
    )
    asyncio.run(
        services_module._async_service_set_snapshot_schedule(hass)(
            _service_call(
                {
                    services_module.ATTR_ENTRY_ID: "entry-1",
                    services_module.ATTR_SNAPSHOT_SCHEDULE: "weekly",
                    services_module.ATTR_SNAPSHOT_WEEKDAY: "Monday",
                    services_module.ATTR_SNAPSHOT_SCHEDULE_TIME: "01:30",
                }
            )
        )
    )

    assert client.created == [
        (target, {"description": "Before update", "locked": True})
    ]
    assert client.updated == [
        (target, {"max_count": 9}),
        (
            target,
            {
                "schedule_frequency": "Weekly",
                "schedule_weekdays": "1",
                "schedule_time": "01:30",
            },
        ),
    ]


def test_snapshot_action_errors_are_translated_and_repaired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Snapshot write helpers should translate API errors and update repairs."""
    target = {"id": "shared-1", "type": "shared", "name": "Shared Drive"}
    created_action_issues: list[tuple[str, str]] = []
    cleared_action_issues: list[tuple[str, str]] = []
    monkeypatch.setattr(
        services_module,
        "async_create_snapshot_action_issue",
        lambda hass, entry, *, action, target, err: created_action_issues.append(
            (action, type(err).__name__)
        ),
    )
    monkeypatch.setattr(
        services_module,
        "async_clear_snapshot_action_issues",
        lambda hass, entry, *, action, target: cleared_action_issues.append(
            (action, str(target.get("id")))
        ),
    )

    for api_error, translation_key in (
        (services_module.InvalidAuth("forbidden"), "snapshot_action_permission"),
        (services_module.UnsupportedFeature("missing"), "snapshot_action_unsupported"),
        (services_module.CannotConnect("offline"), "snapshot_action_failed"),
    ):
        coordinator = _FakeCoordinator(online=True)
        coordinator.config_entry = types.SimpleNamespace(entry_id="entry-1")
        coordinator.hass = object()
        try:
            asyncio.run(
                services_module._async_call_snapshot_action(
                    coordinator,
                    target,
                    action_name="create snapshot",
                    action=_raise_async(api_error),
                )
            )
        except services_module.HomeAssistantError as err:
            assert err.translation_key == translation_key
        else:
            raise AssertionError(f"{translation_key} should be raised")

    coordinator = _FakeCoordinator(online=True)
    coordinator.config_entry = types.SimpleNamespace(entry_id="entry-1")
    coordinator.hass = object()

    async def _success() -> None:
        return None

    asyncio.run(
        services_module._async_call_snapshot_action(
            coordinator,
            target,
            action_name="change snapshot schedule",
            action=_success,
        )
    )

    assert ("create", "InvalidAuth") in created_action_issues
    assert ("create", "UnsupportedFeature") in created_action_issues
    assert cleared_action_issues == [("settings", "shared-1")]
