"""Unit tests for config-flow helper normalization."""

import asyncio
import json
from types import MappingProxyType
from pathlib import Path
from typing import Any
import sys
import types

import pytest

from tests.module_stubs import (
    install_aiohttp_stub,
    install_homeassistant_const_stub,
    install_package_stubs,
    load_const_module,
    load_integration_module,
)


_UTF8_BOM = b"\xef\xbb\xbf"


def _load_json_translation(path: Path) -> dict[str, Any]:
    """Load JSON data with strict UTF-8 and fail if a BOM is present."""
    raw = path.read_bytes()
    assert (
        not raw.startswith(_UTF8_BOM)
    ), f"{path.name} is stored with UTF-8 BOM bytes"
    return json.loads(raw.decode("utf-8"))


def _install_base_stubs() -> None:
    install_package_stubs()
    ha_pkg = types.ModuleType("homeassistant")
    sys.modules["homeassistant"] = ha_pkg

    config_entries_pkg = types.ModuleType("homeassistant.config_entries")

    class ConfigFlow:
        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__()

    class OptionsFlow:
        """Minimal OptionsFlow stub."""

    config_entries_pkg.ConfigFlow = ConfigFlow
    config_entries_pkg.ConfigEntry = object
    config_entries_pkg.ConfigFlowResult = dict
    config_entries_pkg.OptionsFlow = OptionsFlow
    sys.modules["homeassistant.config_entries"] = config_entries_pkg
    ha_pkg.config_entries = config_entries_pkg

    install_homeassistant_const_stub(
        CONF_API_KEY="api_key",
        CONF_HOST="host",
        CONF_PASSWORD="password",
        CONF_PORT="port",
        CONF_SCAN_INTERVAL="scan_interval",
        CONF_SSL="ssl",
        CONF_USERNAME="username",
        CONF_VERIFY_SSL="verify_ssl",
    )

    core_pkg = types.ModuleType("homeassistant.core")
    core_pkg.callback = lambda func: func
    core_pkg.HomeAssistant = object
    sys.modules["homeassistant.core"] = core_pkg

    util_pkg = types.ModuleType("homeassistant.util")
    util_logging_pkg = types.ModuleType("homeassistant.util.logging")
    util_logging_pkg.log_exception = lambda *args, **kwargs: None
    util_pkg.logging = util_logging_pkg
    ha_pkg.util = util_pkg
    sys.modules["homeassistant.util"] = util_pkg
    sys.modules["homeassistant.util.logging"] = util_logging_pkg

    helpers_pkg = types.ModuleType("homeassistant.helpers")
    sys.modules["homeassistant.helpers"] = helpers_pkg

    aiohttp_client_pkg = types.ModuleType("homeassistant.helpers.aiohttp_client")
    aiohttp_client_pkg.async_create_clientsession = lambda *args, **kwargs: object()
    sys.modules["homeassistant.helpers.aiohttp_client"] = aiohttp_client_pkg

    install_aiohttp_stub(include_cookie_jar=True)

    vol_pkg = types.ModuleType("voluptuous")
    vol_pkg.Invalid = ValueError
    vol_pkg.Required = lambda key, default=None: key
    vol_pkg.Optional = lambda key, default=None: key
    vol_pkg.Schema = lambda schema: schema
    vol_pkg.All = lambda *validators: validators[-1] if validators else (lambda value: value)
    vol_pkg.Coerce = lambda target: target
    vol_pkg.In = lambda values: values
    vol_pkg.Range = lambda **kwargs: (lambda value: value)
    sys.modules["voluptuous"] = vol_pkg

    api_pkg = types.ModuleType("custom_components.unifi_unas.api")

    class CannotConnect(Exception):
        """Raised by the API stub when the device is unreachable."""

    class InvalidAuth(Exception):
        """Raised by the API stub when auth fails."""

    class UnexpectedResponse(Exception):
        """Raised by the API stub for unsupported payloads."""

    api_pkg.CannotConnect = CannotConnect
    api_pkg.InvalidAuth = InvalidAuth
    api_pkg.UnexpectedResponse = UnexpectedResponse
    api_pkg.UnifiUnasApiClient = type("UnifiUnasApiClient", (), {})
    sys.modules["custom_components.unifi_unas.api"] = api_pkg

    wol_pkg = types.ModuleType("custom_components.unifi_unas.wake_on_lan")

    def _normalize_mac_address(value: str) -> str:
        compact = "".join(
            char for char in value.strip() if char.lower() in "0123456789abcdef"
        )
        if len(compact) != 12:
            raise ValueError("Invalid MAC address")
        return ":".join(compact[index : index + 2] for index in range(0, 12, 2)).lower()

    wol_pkg.normalize_mac_address = _normalize_mac_address
    wol_pkg.validate_ipv4_address = lambda value: value
    sys.modules["custom_components.unifi_unas.wake_on_lan"] = wol_pkg


def _load_config_flow_module():
    _install_base_stubs()
    load_const_module()
    return load_integration_module("config_flow")


config_flow_module = _load_config_flow_module()
config_flow_schema_module = sys.modules[
    "custom_components.unifi_unas.config_flow_schema"
]
discovery_module = sys.modules["custom_components.unifi_unas.discovery"]


def _load_discovery_module():
    return discovery_module


def test_config_flow_translations_cover_all_form_fields() -> None:
    """Config-flow forms should not expose raw option keys in the UI."""
    root = Path(__file__).resolve().parents[1]
    package_root = root / "custom_components" / "unifi_unas"
    translation_paths = (
        package_root / "strings.json",
        package_root / "translations" / "en.json",
        package_root / "translations" / "de.json",
    )
    connection_fields = set(config_flow_module._connection_schema_fields())
    feature_fields = set(config_flow_module._feature_schema_fields())
    discovery_fields = {config_flow_module.CONF_DISCOVERED_DEVICE}
    reauth_fields = {"username", "password", "api_key"}

    expected_by_step = {
        "user": connection_fields | feature_fields,
        "zeroconf_confirm": connection_fields,
        "discovery_select": discovery_fields,
        "features": feature_fields,
        "reauth_confirm": reauth_fields,
        "reconfigure_connection": connection_fields,
        "reconfigure_features": feature_fields,
    }
    expected_options_by_step = {
        "init": feature_fields,
    }
    expected_menu_options = {
        "reconfigure": {"reconfigure_connection", "reconfigure_features"},
    }
    expected_options_errors = {
        "invalid_scan_interval",
        "mac_required",
        "invalid_mac_address",
        "invalid_broadcast_address",
        "offline_without_wol",
    }
    expected_abort_reasons = {
        "already_in_progress",
        "already_configured",
        "not_unas_device",
        "reauth_successful",
        "reconfigure_successful",
        "wrong_device",
    }

    for path in translation_paths:
        translations = _load_json_translation(path)
        steps = translations["config"]["step"]
        for step_id, expected_fields in expected_by_step.items():
            assert step_id in steps, f"{path.name} missing step {step_id}"
            data = steps[step_id].get("data", {})
            missing = expected_fields - set(data)
            assert not missing, f"{path.name} {step_id} missing {sorted(missing)}"
        for step_id, expected_options in expected_menu_options.items():
            assert step_id in steps, f"{path.name} missing step {step_id}"
            menu_options = steps[step_id].get("menu_options", {})
            missing = expected_options - set(menu_options)
            assert (
                not missing
            ), f"{path.name} {step_id} menu missing {sorted(missing)}"
        abort = translations["config"].get("abort", {})
        missing_abort = expected_abort_reasons - set(abort)
        assert (
            not missing_abort
        ), f"{path.name} abort missing {sorted(missing_abort)}"
        options_steps = translations["options"]["step"]
        for step_id, expected_fields in expected_options_by_step.items():
            assert step_id in options_steps, f"{path.name} missing option step {step_id}"
            data = options_steps[step_id].get("data", {})
            missing = expected_fields - set(data)
            assert not missing, f"{path.name} option {step_id} missing {sorted(missing)}"
        options_errors = translations["options"].get("error", {})
        missing_option_errors = expected_options_errors - set(options_errors)
        assert (
            not missing_option_errors
        ), f"{path.name} options error missing {sorted(missing_option_errors)}"


def test_config_flow_schema_sanitizes_corrupted_numeric_defaults() -> None:
    """Damaged stored numeric defaults should not break config forms."""
    defaults = config_flow_schema_module._feature_defaults(
        {
            "scan_interval": "not-an-integer",
            "wol_port": "also-bad",
        }
    )

    assert defaults["scan_interval"] == config_flow_schema_module.DEFAULT_SCAN_INTERVAL
    assert defaults["wol_port"] == config_flow_schema_module.DEFAULT_WOL_PORT


def test_config_flow_schema_bounds_numeric_defaults() -> None:
    """Out-of-range stored defaults should fall back to safe values."""
    defaults = config_flow_schema_module._feature_defaults(
        {
            "scan_interval": 1,
            "wol_port": 70000,
        }
    )

    assert defaults["scan_interval"] == config_flow_schema_module.DEFAULT_SCAN_INTERVAL
    assert defaults["wol_port"] == config_flow_schema_module.DEFAULT_WOL_PORT


def test_unifi_discovery_filters_multiple_unas_devices_and_wol_defaults() -> None:
    """UniFi discovery should keep multiple UNAS devices and WOL state."""
    discovery_module = _load_discovery_module()

    devices = [
        types.SimpleNamespace(
            source_ip="192.0.2.10",
            hw_addr="AA:BB:CC:DD:EE:10",
            hostname="unas-one",
            model="UNAS Pro",
            platform="UNAS-Pro",
            product_name="UniFi Drive",
            wol_enabled=True,
        ),
        types.SimpleNamespace(
            source_ip="192.0.2.11",
            hw_addr="AA:BB:CC:DD:EE:11",
            hostname="unas-two",
            model="UNAS Pro",
            platform="UNAS-Pro",
            product_name="UniFi Drive",
            wol_enabled=False,
        ),
        types.SimpleNamespace(
            source_ip="192.0.2.12",
            hw_addr="AA:BB:CC:DD:EE:12",
            hostname="gateway",
            model="UDM Pro",
            platform="UDM-Pro",
            product_name="UniFi Network",
        ),
    ]

    result = discovery_module.discovered_unas_devices_from_scan(devices)

    assert [device.host for device in result] == ["192.0.2.10", "192.0.2.11"]
    assert result[0].wol_enabled is True
    assert result[1].wol_enabled is False
    assert discovery_module.feature_defaults_from_discovery(result[0]) == {
        "wol_enabled": True,
        "wol_mac_address": "AA:BB:CC:DD:EE:10",
    }
    assert discovery_module.feature_defaults_from_discovery(result[1]) == {
        "wol_enabled": False,
        "wol_mac_address": "AA:BB:CC:DD:EE:11",
    }


def test_unifi_discovery_uses_injected_async_scanner() -> None:
    """Discovery should use the injected scanner without importing network tools."""
    discovery_module = _load_discovery_module()

    class _Scanner:
        async def async_scan(self, *, timeout: int, consoles_only: bool = True):
            assert timeout == 3
            assert consoles_only is True
            return [
                types.SimpleNamespace(
                    source_ip="192.0.2.10",
                    hostname="unas-one",
                    model="UNAS Pro",
                    product_name="UniFi Drive",
                )
            ]

    result = asyncio.run(
        discovery_module.async_discover_unas_devices(
            timeout=3,
            scanner_factory=_Scanner,
        )
    )

    assert len(result) == 1
    assert result[0].host == "192.0.2.10"
    assert result[0].source == "unifi_discovery"


def test_unifi_discovery_returns_empty_when_scanner_dependency_is_missing(
    monkeypatch,
) -> None:
    """Discovery should fail closed when the optional scanner is unavailable."""
    discovery_module = _load_discovery_module()

    def _import_module(name: str) -> object:
        if name == "unifi_discovery":
            raise ImportError("unavailable")
        raise AssertionError(f"Unexpected import: {name}")

    monkeypatch.setattr(discovery_module, "import_module", _import_module)

    assert asyncio.run(discovery_module.async_discover_unas_devices()) == ()


def test_unifi_discovery_skips_unas_candidates_without_host() -> None:
    """UNAS-looking discovery records without a usable host should be ignored."""
    discovery_module = _load_discovery_module()

    result = discovery_module.discovered_unas_devices_from_scan(
        [
            types.SimpleNamespace(
                hostname="unas-without-address",
                model="UNAS Pro",
                product_name="UniFi Drive",
            )
        ]
    )

    assert result == ()


def test_unifi_discovery_reads_nested_host_containers() -> None:
    """Nested address containers should provide a usable discovery host."""
    discovery_module = _load_discovery_module()

    result = discovery_module.discovered_unas_devices_from_scan(
        [
            types.SimpleNamespace(
                hostname="unas-list",
                model="UNAS Pro",
                product_name="UniFi Drive",
                ip_info=[{}, {"address": "192.0.2.20"}],
            ),
            types.SimpleNamespace(
                hostname="unas-dict",
                model="UNAS Pro",
                product_name="UniFi Drive",
                addr_entry={"host": "192.0.2.21"},
            ),
        ]
    )

    assert [device.host for device in result] == ["192.0.2.21", "192.0.2.20"]


def test_unifi_discovery_dedupes_normalized_hosts_and_macs() -> None:
    """UniFi discovery should collapse equivalent host and MAC forms."""
    discovery_module = _load_discovery_module()

    devices = [
        types.SimpleNamespace(
            source_ip="[2001:0db8::0001]",
            hostname="unas-one",
            model="UNAS Pro",
            product_name="UniFi Drive",
        ),
        types.SimpleNamespace(
            source_ip="2001:db8::1",
            hostname="unas-one-alias",
            model="UNAS Pro",
            product_name="UniFi Drive",
        ),
        types.SimpleNamespace(
            source_ip="192.0.2.10",
            hw_addr="AA-BB-CC-DD-EE-FF",
            hostname="unas-two",
            model="UNAS Pro",
            product_name="UniFi Drive",
        ),
        types.SimpleNamespace(
            source_ip="192.0.2.11",
            hw_addr="aabb.ccdd.eeff",
            hostname="unas-two-alias",
            model="UNAS Pro",
            product_name="UniFi Drive",
        ),
    ]

    result = discovery_module.discovered_unas_devices_from_scan(devices)

    assert [device.key for device in result] == [
        "host:2001:db8::1",
        "mac:aa:bb:cc:dd:ee:ff",
    ]


def test_zeroconf_discovery_uses_wol_switch_state_as_default() -> None:
    """Zeroconf metadata should prefill WOL only when the device reports it."""
    discovery_module = _load_discovery_module()
    info = types.SimpleNamespace(
        name="UNAS Pro._https._tcp.local.",
        hostname="unas-pro.local.",
        host="unas-pro.local",
        port=443,
        properties={
            b"model": b"UNAS Pro",
            b"product": b"UniFi Drive",
            b"mac": b"AA:BB:CC:DD:EE:FF",
            b"wol_enabled": b"true",
        },
    )

    device = discovery_module.discovered_unas_device_from_zeroconf(info)

    assert device is not None
    assert device.host == "unas-pro.local"
    assert device.wol_enabled is True
    assert discovery_module.connection_defaults_from_discovery(device) == {
        "host": "unas-pro.local",
        "port": 443,
        "ssl": True,
        "verify_ssl": False,
    }
    assert discovery_module.feature_defaults_from_discovery(device) == {
        "wol_enabled": True,
        "wol_mac_address": "AA:BB:CC:DD:EE:FF",
    }


def test_zeroconf_smb_discovery_uses_api_port_default() -> None:
    """SMB zeroconf should discover UNAS without using the SMB port as API port."""
    discovery_module = _load_discovery_module()
    info = types.SimpleNamespace(
        name="UNAS._smb._tcp.local.",
        hostname="UNAS.local.",
        type="_smb._tcp.local.",
        host="unas.local",
        ip_addresses=["192.0.2.10", "fe80::a8bb:ccff:fedd:eeff"],
        port=445,
        properties={},
    )

    device = discovery_module.discovered_unas_device_from_zeroconf(info)

    assert device is not None
    assert device.host == "unas.local"
    assert device.hw_addr == "aa:bb:cc:dd:ee:ff"
    assert device.label == "UNAS (aa:bb:cc:dd:ee:ff)"
    assert device.port == 443
    assert device.use_ssl is True
    assert discovery_module.connection_defaults_from_discovery(device) == {
        "host": "unas.local",
        "port": 443,
        "ssl": True,
        "verify_ssl": False,
    }


def test_zeroconf_discovery_tracks_conflicting_mac_sources() -> None:
    """Zeroconf diagnostics should surface conflicting identity hints."""
    discovery_module = _load_discovery_module()
    info = types.SimpleNamespace(
        name="UNAS._smb._tcp.local.",
        hostname="UNAS.local.",
        type="_smb._tcp.local.",
        host="unas.local",
        ip_addresses=["fe80::a8bb:ccff:fedd:eeff"],
        port=445,
        properties={"mac": "11:22:33:44:55:66", "product": "UniFi Drive"},
    )

    device = discovery_module.discovered_unas_device_from_zeroconf(info)

    assert device is not None
    assert device.hw_addr == "11:22:33:44:55:66"
    assert device.identity_source == "zeroconf_property_mac"
    assert device.identity_conflicts == ("zeroconf_mac_eui64_mismatch",)
    assert device.confidence == 65


def test_zeroconf_discovery_prefers_hostname_for_service_instance_host() -> None:
    """Service-instance hostnames should prefer a real hostname or IP."""
    discovery_module = _load_discovery_module()
    info = types.SimpleNamespace(
        name="UNAS._smb._tcp.local.",
        hostname="unas-pro.local.",
        host="UNAS._smb._tcp.local.",
        ip_address="192.0.2.10",
        type="_smb._tcp.local.",
        properties={
            "model": "UNAS Pro",
            "product": "UniFi Drive",
        },
    )

    device = discovery_module.discovered_unas_device_from_zeroconf(info)

    assert device is not None
    assert device.host == "unas-pro.local"


def test_zeroconf_discovery_uses_ip_when_hostname_is_missing() -> None:
    """Service-instance only hosts should still map to a stable network host."""
    discovery_module = _load_discovery_module()
    info = types.SimpleNamespace(
        name="UNAS._smb._tcp.local.",
        host="UNAS._smb._tcp.local.",
        ip_address="192.0.2.10",
        type="_smb._tcp.local.",
        properties={
            "model": "UNAS Pro",
            "product": "UniFi Drive",
        },
    )

    device = discovery_module.discovered_unas_device_from_zeroconf(info)

    assert device is not None
    assert device.host == "192.0.2.10"


def test_zeroconf_discovery_uses_ip_addresses_when_no_hostname_or_ip() -> None:
    """Zeroconf should fall back to Home Assistant ip_addresses metadata."""
    discovery_module = _load_discovery_module()
    info = types.SimpleNamespace(
        name="UNAS._smb._tcp.local.",
        host="UNAS._smb._tcp.local.",
        ip_addresses=["192.0.2.30"],
        type="_smb._tcp.local.",
        properties={"product": "UniFi Drive"},
    )

    device = discovery_module.discovered_unas_device_from_zeroconf(info)

    assert device is not None
    assert device.host == "192.0.2.30"
    assert device.port == 443


def test_zeroconf_discovery_normalizes_instance_hostnames() -> None:
    """Service-instance hostnames should normalize into usable local names."""
    discovery_module = _load_discovery_module()
    info = types.SimpleNamespace(
        name="UNAS._https._tcp.local.",
        host="unas.local._https._tcp.local.",
        type="_https._tcp.local.",
        properties={"product": "UniFi Drive"},
    )

    device = discovery_module.discovered_unas_device_from_zeroconf(info)

    assert device is not None
    assert device.host == "unas.local"


def test_zeroconf_discovery_uses_default_port_for_invalid_api_ports() -> None:
    """Malformed zeroconf ports must not become connection defaults."""
    discovery_module = _load_discovery_module()
    invalid_text = types.SimpleNamespace(
        name="UNAS._https._tcp.local.",
        host="unas.local",
        type="_https._tcp.local.",
        port="not-a-port",
        properties={"product": "UniFi Drive"},
    )
    invalid_range = types.SimpleNamespace(
        name="UNAS._https._tcp.local.",
        host="unas.local",
        type="_https._tcp.local.",
        port=70_000,
        properties={"product": "UniFi Drive"},
    )

    text_device = discovery_module.discovered_unas_device_from_zeroconf(invalid_text)
    range_device = discovery_module.discovered_unas_device_from_zeroconf(invalid_range)

    assert text_device is not None
    assert range_device is not None
    assert text_device.port == 443
    assert range_device.port == 443


def test_zeroconf_discovery_tracks_invalid_advertised_mac() -> None:
    """Invalid advertised MAC values should be reported as identity conflicts."""
    discovery_module = _load_discovery_module()
    info = types.SimpleNamespace(
        name="UNAS._https._tcp.local.",
        host="unas.local",
        type="_https._tcp.local.",
        properties={"product": "UniFi Drive", "mac": "definitely-not-a-mac"},
    )

    device = discovery_module.discovered_unas_device_from_zeroconf(info)

    assert device is not None
    assert device.hw_addr is None
    assert device.identity_source == "host"
    assert device.identity_conflicts == ("invalid_zeroconf_mac",)


def test_zeroconf_private_helpers_tolerate_sparse_metadata() -> None:
    """Sparse zeroconf shapes should normalize without leaking exceptions."""
    discovery_module = _load_discovery_module()

    assert discovery_module._zeroconf_addresses(
        types.SimpleNamespace(addresses="192.0.2.40")
    ) == ("192.0.2.40",)
    assert discovery_module._zeroconf_property(None, "model") is None
    assert discovery_module._zeroconf_bool_property(["bad"], "wol") is None
    assert discovery_module._zeroconf_property_values("bad") == ()
    assert discovery_module._zeroconf_service_instance_name(None, "_smb._tcp.local.") is None
    assert (
        discovery_module._zeroconf_label(
            product=None,
            name=None,
            hostname=None,
            host="unas.local",
            hw_addr=None,
        )
        == "unas.local"
    )


def test_system_payload_wol_switch_state_becomes_feature_default() -> None:
    """Validated system metadata should drive the WOL option default."""
    discovery_module = _load_discovery_module()
    payload = {
        "hardware": {
            "macAddress": "AA:BB:CC:DD:EE:FE",
        },
        "settings": {
            "wakeOnLanEnabled": True,
        },
    }

    assert discovery_module.feature_defaults_from_system_payload(payload) == {
        "wol_enabled": True,
        "wol_mac_address": "AA:BB:CC:DD:EE:FE",
    }


def test_system_payload_reads_nested_browser_wol_switch() -> None:
    """Nested UniFi OS WOL settings should also drive the option default."""
    discovery_module = _load_discovery_module()
    payload = {
        "hardware": {
            "macAddress": "AA:BB:CC:DD:EE:FD",
        },
        "settings": {
            "wakeOnLan": {
                "enabled": "on",
            },
        },
    }

    assert discovery_module.feature_defaults_from_system_payload(payload) == {
        "wol_enabled": True,
        "wol_mac_address": "AA:BB:CC:DD:EE:FD",
    }


def test_system_payload_reads_unifi_os_device_list_wol_defaults() -> None:
    """System metadata should read WOL defaults from UniFi OS device records."""
    discovery_module = _load_discovery_module()
    payload = {
        "devices": {
            "unifiOS": [
                {
                    "macAddress": "AA:BB:CC:DD:EE:FC",
                    "wakeOnLanEnabled": "true",
                }
            ]
        }
    }

    assert discovery_module.feature_defaults_from_system_payload(payload) == {
        "wol_enabled": True,
        "wol_mac_address": "AA:BB:CC:DD:EE:FC",
    }


def test_validated_wol_defaults_override_discovery_guess() -> None:
    """Browser/API WOL state should override earlier discovery defaults."""
    data = config_flow_module._apply_validated_feature_defaults(
        {
            "host": "unas.local",
            "port": 443,
            "ssl": True,
            "verify_ssl": False,
            "username": "",
            "password": "",
            "api_key": "token",
        },
        {
            "feature_defaults": {
                "wol_enabled": True,
                "wol_mac_address": "AA:BB:CC:DD:EE:FE",
            }
        },
        {
            "wol_enabled": False,
            "wol_mac_address": "AA:BB:CC:DD:EE:FF",
        },
    )

    assert data["wol_enabled"] is True
    assert data["wol_mac_address"] == "aa:bb:cc:dd:ee:fe"


def test_config_flow_discovery_selection_prefills_connection_and_wol() -> None:
    """Selecting a discovered UNAS should prefill connection and WOL defaults."""
    device = config_flow_module.DiscoveredUnasDevice(
        key="mac:aa:bb:cc:dd:ee:ff",
        label="UNAS Pro (unas-pro, 192.0.2.10)",
        host="192.0.2.10",
        hw_addr="aa:bb:cc:dd:ee:ff",
        wol_enabled=True,
    )
    flow = config_flow_module.UnifiUnasConfigFlow()
    _patch_config_flow_result_helpers(flow)

    original_discovery = config_flow_module.async_discover_unas_devices

    async def _discover():
        return (device,)

    config_flow_module.async_discover_unas_devices = _discover
    try:
        result = asyncio.run(flow.async_step_user())
        assert result["type"] == "form"
        assert result["step_id"] == "discovery_select"

        result = asyncio.run(
            flow.async_step_discovery_select(
                {"discovered_device": "mac:aa:bb:cc:dd:ee:ff"}
            )
        )
    finally:
        config_flow_module.async_discover_unas_devices = original_discovery

    assert result["type"] == "form"
    assert result["step_id"] == "user"
    assert flow._connection_defaults == {
        "host": "192.0.2.10",
        "port": 443,
        "ssl": True,
        "verify_ssl": False,
    }
    assert flow._feature_defaults == {
        "wol_enabled": True,
        "wol_mac_address": "aa:bb:cc:dd:ee:ff",
    }
    assert flow._identity_defaults == {
        "discovery_host_aliases": ["192.0.2.10"],
        "discovery_identity_source": "discovery_mac",
        "discovery_mac_address": "aa:bb:cc:dd:ee:ff",
    }


def test_discovery_identity_defaults_persist_mac_outside_wol_options() -> None:
    """Discovery MAC should remain an identity hint even if WOL is changed."""
    data = config_flow_module._apply_discovery_identity_defaults(
        {
            "host": "unas.local",
            "port": 443,
            "ssl": True,
            "verify_ssl": False,
            "username": "",
            "password": "",
            "api_key": "token",
            "wol_enabled": False,
            "wol_mac_address": "",
        },
        {},
        {"discovery_mac_address": "AA:BB:CC:DD:EE:FF"},
    )

    assert data["discovery_mac_address"] == "aa:bb:cc:dd:ee:ff"
    assert data["discovery_host_aliases"] == ["unas.local"]


def test_discovery_identity_defaults_persist_host_aliases_without_mac() -> None:
    """Discovery host aliases should persist when no MAC is advertised."""
    device = config_flow_module.DiscoveredUnasDevice(
        key="host:192.0.2.10",
        label="UNAS",
        host="192.0.2.10",
        hostname="UNAS.local.",
    )

    defaults = config_flow_module._discovery_identity_defaults_from_device(device)
    data = config_flow_module._apply_discovery_identity_defaults(
        {
            "host": "unas.local",
            "port": 443,
            "ssl": True,
            "verify_ssl": False,
            "username": "",
            "password": "",
            "api_key": "token",
        },
        {"host": "unas.local"},
        defaults,
    )

    assert data["discovery_host_aliases"] == [
        "192.0.2.10",
        "unas.local",
    ]


def test_discovery_identity_defaults_preserve_existing_host_aliases() -> None:
    """Validated identity updates should not drop previously learned aliases."""
    data = config_flow_module._apply_discovery_identity_defaults(
        {
            "host": "unas.local",
            "port": 443,
            "ssl": True,
            "verify_ssl": False,
            "username": "",
            "password": "",
            "api_key": "token",
            "discovery_host_aliases": ["192.0.2.10", "old-unas.local"],
        },
        {"host": "unas-vlan.local"},
        {
            "discovery_identity_source": "validated_system",
            "discovery_confidence": 85,
        },
    )

    assert data["discovery_host_aliases"] == [
        "192.0.2.10",
        "old-unas.local",
        "unas-vlan.local",
        "unas.local",
    ]


def test_discovery_identity_defaults_use_validated_system_mac() -> None:
    """Validated system metadata should also persist a dedupe MAC hint."""
    data = config_flow_module._apply_discovery_identity_defaults(
        {
            "host": "unas.local",
            "port": 443,
            "ssl": True,
            "verify_ssl": False,
            "username": "",
            "password": "",
            "api_key": "token",
            "wol_enabled": True,
            "wol_mac_address": "aa:bb:cc:dd:ee:ff",
        },
        {
            "feature_defaults": {
                "wol_mac_address": "AA:BB:CC:DD:EE:FE",
            }
        },
        None,
    )

    assert data["discovery_mac_address"] == "aa:bb:cc:dd:ee:fe"


def test_config_flow_discovery_search_hides_configured_host_alias() -> None:
    """Discovery search should hide an already configured device by hostname."""
    device = config_flow_module.DiscoveredUnasDevice(
        key="mac:aa:bb:cc:dd:ee:ff",
        label="UNAS Pro (192.0.2.10)",
        host="192.0.2.10",
        hostname="unas-pro.local.",
        hw_addr="aa:bb:cc:dd:ee:ff",
    )
    entry = types.SimpleNamespace(
        data={"host": "unas-pro.local", "port": 443},
        options={},
        unique_id="system-id",
    )
    flow = config_flow_module.UnifiUnasConfigFlow()
    _patch_config_flow_result_helpers(flow, entries=[entry])

    original_discovery = config_flow_module.async_discover_unas_devices

    async def _discover():
        return (device,)

    config_flow_module.async_discover_unas_devices = _discover
    try:
        result = asyncio.run(flow.async_step_user())
    finally:
        config_flow_module.async_discover_unas_devices = original_discovery

    assert result["type"] == "form"
    assert result["step_id"] == "user"
    assert flow._discovered_devices == {}


def test_config_flow_discovery_search_hides_configured_mac() -> None:
    """Discovery search should hide the same device even if the host changed."""
    device = config_flow_module.DiscoveredUnasDevice(
        key="mac:aa:bb:cc:dd:ee:ff",
        label="UNAS Pro (192.0.2.10)",
        host="192.0.2.10",
        hw_addr="AA:BB:CC:DD:EE:FF",
    )
    entry = types.SimpleNamespace(
        data={"host": "unas-pro.local", "port": 443},
        options={"wol_mac_address": "aa:bb:cc:dd:ee:ff"},
        unique_id="system-id",
    )

    assert config_flow_module._discovered_device_already_configured(
        types.SimpleNamespace(
            config_entries=types.SimpleNamespace(
                async_entries=lambda domain: [entry]
            )
        ),
        device,
    )


def test_config_flow_discovery_search_hides_stored_identity_mac() -> None:
    """Discovery search should use the internal MAC even if WOL MAC is cleared."""
    device = config_flow_module.DiscoveredUnasDevice(
        key="mac:aa:bb:cc:dd:ee:ff",
        label="UNAS Pro (192.0.2.10)",
        host="192.0.2.10",
        hw_addr="AA:BB:CC:DD:EE:FF",
    )
    entry = types.SimpleNamespace(
        data={
            "host": "other-alias.local",
            "port": 443,
            "discovery_mac_address": "aa:bb:cc:dd:ee:ff",
        },
        options={"wol_mac_address": ""},
        unique_id="system-id",
    )

    assert config_flow_module._discovered_device_already_configured(
        types.SimpleNamespace(
            config_entries=types.SimpleNamespace(
                async_entries=lambda domain: [entry]
            )
        ),
        device,
    )


def test_config_flow_discovery_search_hides_mapping_entry_data_mac() -> None:
    """Real Home Assistant config-entry data mappings should dedupe too."""
    device = config_flow_module.DiscoveredUnasDevice(
        key="mac:aa:bb:cc:dd:ee:ff",
        label="UNAS Pro",
        host="192.0.2.10",
        hw_addr="AA:BB:CC:DD:EE:FF",
    )
    entry = types.SimpleNamespace(
        data=MappingProxyType(
            {
                "host": "other-alias.local",
                "port": 443,
                "discovery_mac_address": "aa:bb:cc:dd:ee:ff",
            }
        ),
        options=MappingProxyType({}),
        unique_id="system-id",
    )

    assert config_flow_module._discovered_device_already_configured(
        types.SimpleNamespace(
            config_entries=types.SimpleNamespace(
                async_entries=lambda domain: [entry]
            )
        ),
        device,
    )


def test_config_flow_discovery_search_hides_same_host_on_different_port() -> None:
    """Discovery search should not offer a second entry for the same host."""
    device = config_flow_module.DiscoveredUnasDevice(
        key="host:unas-pro.local",
        label="UNAS Pro",
        host="unas-pro.local",
        port=443,
    )
    entry = types.SimpleNamespace(
        data={"host": "unas-pro.local", "port": 80},
        options={},
        unique_id="system-id",
    )

    assert config_flow_module._discovered_device_already_configured(
        types.SimpleNamespace(
            config_entries=types.SimpleNamespace(
                async_entries=lambda domain: [entry]
            )
        ),
        device,
    )


def test_config_flow_discovery_search_hides_stored_host_alias() -> None:
    """Discovery search should dedupe IP and hostname aliases without a MAC."""
    device = config_flow_module.DiscoveredUnasDevice(
        key="host:192.0.2.10",
        label="UNAS",
        host="192.0.2.10",
        port=443,
    )
    entry = types.SimpleNamespace(
        data={
            "host": "unas.local",
            "port": 443,
            "discovery_host_aliases": ["unas.local", "192.0.2.10"],
        },
        options={},
        unique_id="unas.local:443",
    )

    assert config_flow_module._discovered_device_already_configured(
        types.SimpleNamespace(
            config_entries=types.SimpleNamespace(
                async_entries=lambda domain: [entry]
            )
        ),
        device,
    )


def test_config_flow_discovery_search_hides_matching_fallback_unique_id() -> None:
    """Discovery search should dedupe host fallback unique IDs."""
    device = config_flow_module.DiscoveredUnasDevice(
        key="host:unas.local",
        label="UNAS",
        host="unas.local",
        port=443,
    )
    entry = types.SimpleNamespace(
        data={"host": "other-alias.local", "port": 443},
        options={},
        unique_id="unas.local:443",
    )

    assert config_flow_module._discovered_device_already_configured(
        types.SimpleNamespace(
            config_entries=types.SimpleNamespace(
                async_entries=lambda domain: [entry]
            )
        ),
        device,
    )


def test_config_flow_discovery_search_records_alias_for_matching_mac() -> None:
    """Matching MAC discovery should persist new host aliases for restarts."""
    device = config_flow_module.DiscoveredUnasDevice(
        key="mac:aa:bb:cc:dd:ee:ff",
        label="UNAS Pro",
        host="192.0.2.50",
        hw_addr="AA:BB:CC:DD:EE:FF",
    )
    entry = types.SimpleNamespace(
        data={
            "host": "unas.local",
            "port": 443,
            "discovery_mac_address": "aa:bb:cc:dd:ee:ff",
        },
        options={},
        unique_id="system-id",
    )

    class _ConfigEntries:
        def async_entries(self, domain):
            assert domain == config_flow_module.DOMAIN
            return [entry]

        def async_update_entry(self, config_entry, *, data):
            config_entry.data = data

    assert config_flow_module._discovered_device_already_configured(
        types.SimpleNamespace(config_entries=_ConfigEntries()),
        device,
    )
    assert entry.data["discovery_host_aliases"] == [
        "192.0.2.50",
        "unas.local",
    ]
    assert entry.data["discovery_identity_source"] == "discovery_mac"
    assert entry.data["discovery_last_seen"].endswith("Z")


def test_config_flow_discovery_search_does_not_spam_recent_metadata_updates() -> None:
    """Repeated discovery observations within interval should not spam entry writes."""
    device = config_flow_module.DiscoveredUnasDevice(
        key="mac:aa:bb:cc:dd:ee:ff",
        label="UNAS Pro",
        host="192.0.2.50",
        hw_addr="AA:BB:CC:DD:EE:FF",
    )
    entry = types.SimpleNamespace(
        data={
            "host": "unas.local",
            "port": 443,
            "discovery_mac_address": "aa:bb:cc:dd:ee:ff",
            "discovery_host_aliases": ["192.0.2.50", "unas.local"],
            "discovery_last_seen": "2026-05-22T00:00:00Z",
            "discovery_identity_source": "discovery_mac",
        },
        options={},
        unique_id="system-id",
    )

    writes: list[dict[str, object]] = []

    class _ConfigEntries:
        def async_entries(self, domain):
            assert domain == config_flow_module.DOMAIN
            return [entry]

        def async_update_entry(self, config_entry, *, data):
            writes.append(data)
            config_entry.data = data

    flow_context = types.SimpleNamespace(config_entries=_ConfigEntries())

    assert config_flow_module._discovered_device_already_configured(flow_context, device)
    assert config_flow_module._discovered_device_already_configured(flow_context, device)

    assert len(writes) == 1


def test_config_flow_discovery_search_keeps_conflicting_mac_visible() -> None:
    """A host match with a different MAC should not hide a discovery card."""
    device = config_flow_module.DiscoveredUnasDevice(
        key="mac:11:22:33:44:55:66",
        label="UNAS Pro",
        host="unas.local",
        hw_addr="11:22:33:44:55:66",
        confidence=90,
    )
    entry = types.SimpleNamespace(
        data={
            "host": "unas.local",
            "port": 443,
            "discovery_mac_address": "aa:bb:cc:dd:ee:ff",
        },
        options={},
        unique_id="system-id",
    )

    class _ConfigEntries:
        def async_entries(self, domain):
            assert domain == config_flow_module.DOMAIN
            return [entry]

        def async_update_entry(self, config_entry, *, data):
            config_entry.data = data

    assert not config_flow_module._discovered_device_already_configured(
        types.SimpleNamespace(config_entries=_ConfigEntries()),
        device,
    )
    assert entry.data["discovery_identity_source"] == "conflicting_discovery"
    assert entry.data["discovery_confidence"] == 90
    assert entry.data["discovery_identity_conflicts"] == [
        "configured_mac_discovery_mac_mismatch"
    ]
    assert "discovery_host_aliases" not in entry.data


def test_config_flow_zeroconf_prefills_wol_enabled_default() -> None:
    """Zeroconf flow should carry WOL state into the feature defaults."""
    flow = config_flow_module.UnifiUnasConfigFlow()
    _patch_config_flow_result_helpers(flow)
    info = types.SimpleNamespace(
        name="UNAS Pro._https._tcp.local.",
        hostname="unas-pro.local.",
        host="unas-pro.local",
        port=443,
        properties={
            "model": "UNAS Pro",
            "product": "UniFi Drive",
            "mac": "aa:bb:cc:dd:ee:ff",
            "wake_on_lan_enabled": "yes",
        },
    )

    result = asyncio.run(flow.async_step_zeroconf(info))

    assert result["type"] == "form"
    assert result["step_id"] == "zeroconf_confirm"
    assert result["description_placeholders"] == {
        "name": "UniFi Drive (aa:bb:cc:dd:ee:ff)"
    }
    assert flow.context["title_placeholders"] == {
        "name": "UniFi Drive (aa:bb:cc:dd:ee:ff)"
    }
    assert flow.context["unifi_unas_discovery_mac"] == "aa:bb:cc:dd:ee:ff"
    assert flow.context["unifi_unas_discovery_hosts"] == [
        "unas-pro.local"
    ]
    assert flow._unique_id == "aa:bb:cc:dd:ee:ff"
    assert flow._connection_defaults["host"] == "unas-pro.local"
    assert flow._feature_defaults == {
        "wol_enabled": True,
        "wol_mac_address": "aa:bb:cc:dd:ee:ff",
    }


def test_config_flow_zeroconf_confirm_validates_then_shows_features() -> None:
    """Zeroconf confirmation should reuse setup validation before features."""
    flow = config_flow_module.UnifiUnasConfigFlow()
    _patch_config_flow_result_helpers(flow)
    flow._feature_defaults = {
        "wol_enabled": True,
        "wol_mac_address": "aa:bb:cc:dd:ee:ff",
    }
    flow._identity_defaults = {
        "discovery_mac_address": "aa:bb:cc:dd:ee:ff",
    }
    flow._discovery_placeholders = {"name": "UNAS Pro"}
    original_validate = config_flow_module._async_validate_for_form

    async def _validate(hass, data):
        return (
            {
                "title": "UNAS Pro",
                "unique_id": "system-id",
                "feature_defaults": {"wol_enabled": True},
            },
            None,
        )

    config_flow_module._async_validate_for_form = _validate
    try:
        result = asyncio.run(
            flow.async_step_zeroconf_confirm(
                {
                    "host": "unas-pro.local",
                    "port": 443,
                    "ssl": True,
                    "verify_ssl": False,
                    "username": "",
                    "password": "",
                    "api_key": "token",
                }
            )
        )
    finally:
        config_flow_module._async_validate_for_form = original_validate

    assert result["type"] == "form"
    assert result["step_id"] == "features"
    assert flow._unique_id == "system-id"
    assert flow._pending_user_state.data["discovery_mac_address"] == (
        "aa:bb:cc:dd:ee:ff"
    )
    assert flow._pending_user_state.data["wol_enabled"] is True


def test_config_flow_zeroconf_duplicate_flow_aborts_before_form() -> None:
    """The same zeroconf host must not open a second setup form."""
    flow = config_flow_module.UnifiUnasConfigFlow()
    _patch_config_flow_result_helpers(flow)
    info = types.SimpleNamespace(
        name="UNAS Pro._https._tcp.local.",
        hostname="unas-pro.local.",
        host="unas-pro.local.",
        port=443,
        properties={
            "model": "UNAS Pro",
            "product": "UniFi Drive",
            "mac": "aa:bb:cc:dd:ee:ff",
        },
    )

    class AlreadyInProgress(Exception):
        """Raised by the stub when Home Assistant finds a duplicate flow."""

    async def _async_set_unique_id(
        unique_id: str | None = None,
        *,
        raise_on_progress: bool = True,
    ) -> None:
        assert unique_id == "aa:bb:cc:dd:ee:ff"
        assert raise_on_progress is True
        raise AlreadyInProgress("already_in_progress")

    flow.async_set_unique_id = _async_set_unique_id

    with pytest.raises(AlreadyInProgress, match="already_in_progress"):
        asyncio.run(flow.async_step_zeroconf(info))

    assert flow._connection_defaults is None
    assert flow._feature_defaults is None


def test_config_flow_zeroconf_does_not_offer_already_configured_service_instance() -> None:
    """Service-instance discovery should be hidden when the device is already configured."""
    flow = config_flow_module.UnifiUnasConfigFlow()
    entry = types.SimpleNamespace(
        data={"host": "unas-pro.local", "port": 443},
        options={},
        unique_id="system-id",
    )
    _patch_config_flow_result_helpers(flow, entries=[entry])

    info = types.SimpleNamespace(
        name="UNAS._smb._tcp.local.",
        hostname="unas-pro.local.",
        host="UNAS._smb._tcp.local.",
        ip_address="192.0.2.10",
        type="_smb._tcp.local.",
        properties={
            "model": "UNAS Pro",
            "product": "UniFi Drive",
            "mac": "aa:bb:cc:dd:ee:ff",
        },
    )

    result = asyncio.run(flow.async_step_zeroconf(info))

    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"


def test_zeroconf_discovery_unique_id_prefers_mac_identity() -> None:
    """Zeroconf should dedupe host aliases for the same MAC."""
    first = config_flow_module.DiscoveredUnasDevice(
        key="mac:aa:bb:cc:dd:ee:ff",
        label="UNAS Pro",
        host="unas-pro.local.",
        port=443,
        hw_addr="aa:bb:cc:dd:ee:ff",
    )
    second = config_flow_module.DiscoveredUnasDevice(
        key="mac:aa-bb-cc-dd-ee-ff",
        label="UNAS Pro",
        host="unas-pro-alias.local",
        port=80,
        hw_addr="aa-bb-cc-dd-ee-ff",
    )

    assert config_flow_module._zeroconf_discovery_unique_id(first) == (
        "aa:bb:cc:dd:ee:ff"
    )
    assert config_flow_module._zeroconf_discovery_unique_id(first) == (
        config_flow_module._zeroconf_discovery_unique_id(second)
    )


def test_zeroconf_discovery_unique_id_falls_back_to_host() -> None:
    """Zeroconf should still dedupe by host when MAC metadata is missing."""
    first = config_flow_module.DiscoveredUnasDevice(
        key="host:unas-pro.local",
        label="UNAS Pro",
        host="unas-pro.local.",
        port=443,
    )
    second = config_flow_module.DiscoveredUnasDevice(
        key="host:unas-pro.local",
        label="UNAS Pro",
        host="unas-pro.local",
        port=443,
    )

    assert config_flow_module._zeroconf_discovery_unique_id(first) == (
        "unas-pro.local:443"
    )
    assert config_flow_module._zeroconf_discovery_unique_id(first) == (
        config_flow_module._zeroconf_discovery_unique_id(second)
    )


def test_discovery_host_key_normalizes_ipv6_literals() -> None:
    """IPv6 forms should dedupe when zeroconf supplies equivalent literals."""
    discovery_module = _load_discovery_module()

    assert discovery_module.discovery_host_key("[2001:0db8::0001]") == (
        "2001:db8::1"
    )
    assert discovery_module.discovery_host_key("2001:db8::1") == "2001:db8::1"


def _entry_with_feature_data(**overrides: Any) -> types.SimpleNamespace:
    """Return a config entry stub with complete connection and feature data."""
    data = {
        "host": "unas.local",
        "port": 443,
        "ssl": True,
        "verify_ssl": False,
        "username": "",
        "password": "",
        "api_key": "token",
        "scan_interval": 30,
        "fan_control_enabled": True,
        "snapshot_buttons_enabled": True,
        "wol_enabled": False,
        "wol_mac_address": "",
        "wol_broadcast_address": "255.255.255.255",
        "wol_port": 9,
    }
    data.update(overrides)
    return types.SimpleNamespace(
        data=data,
        entry_id="entry-1",
        options={},
        state="loaded",
    )


def _patch_options_flow_result_helpers(flow: Any) -> None:
    """Patch Home Assistant flow result helpers onto the OptionsFlow stub."""
    flow.hass = types.SimpleNamespace(data={})
    flow.async_create_entry = lambda **kwargs: {"type": "create_entry", **kwargs}
    flow.async_show_form = lambda **kwargs: {"type": "form", **kwargs}


def _patch_config_flow_result_helpers(
    flow: Any,
    *,
    entries: list[Any] | None = None,
) -> None:
    """Patch Home Assistant flow result helpers onto the ConfigFlow stub."""

    class _ConfigEntries:
        def async_entries(self, domain: str) -> list[Any]:
            assert domain == config_flow_module.DOMAIN
            return entries or []

    flow.hass = types.SimpleNamespace(config_entries=_ConfigEntries())
    flow.context = {}
    flow.async_abort = lambda **kwargs: {"type": "abort", **kwargs}
    flow.async_show_form = lambda **kwargs: {"type": "form", **kwargs}
    flow.async_show_menu = lambda **kwargs: {"type": "menu", **kwargs}
    flow.async_create_entry = lambda **kwargs: {"type": "create_entry", **kwargs}
    flow.async_update_and_abort = (
        lambda entry, **kwargs: {"type": "abort", "reason": "reconfigure_successful", **kwargs}
    )
    flow._abort_if_unique_id_mismatch = lambda **kwargs: None

    async def _async_set_unique_id(
        unique_id: str | None = None,
        *,
        raise_on_progress: bool = True,
    ) -> None:
        flow._unique_id = unique_id

    flow.async_set_unique_id = _async_set_unique_id
    flow._abort_if_unique_id_configured = lambda *args, **kwargs: None


def _complete_flow_input(**overrides: Any) -> dict[str, Any]:
    """Return complete normalized flow input for setup/reconfigure tests."""
    data = {
        "host": "unas.local",
        "port": 443,
        "ssl": True,
        "verify_ssl": False,
        "username": "",
        "password": "",
        "api_key": "token",
        "scan_interval": 30,
        "fan_control_enabled": True,
        "snapshot_buttons_enabled": False,
        "wol_enabled": False,
        "wol_mac_address": "",
        "wol_broadcast_address": "255.255.255.255",
        "wol_port": 9,
    }
    data.update(overrides)
    return data


def test_options_flow_writes_feature_settings_to_options_only() -> None:
    """OptionsFlow should save runtime feature settings without auth data."""
    entry = _entry_with_feature_data()
    entry.options = {"scan_interval": 60, "unrelated_option": "keep"}
    flow = config_flow_module.UnifiUnasOptionsFlow(entry)
    _patch_options_flow_result_helpers(flow)

    result = asyncio.run(
        flow.async_step_init(
            {
                "scan_interval": 120,
                "fan_control_enabled": False,
                "snapshot_buttons_enabled": True,
                "wol_enabled": True,
                "wol_mac_address": "AA:BB:CC:DD:EE:FF",
                "wol_broadcast_address": "192.0.2.255",
                "wol_port": 7,
            }
        )
    )

    assert result == {
        "type": "create_entry",
        "title": "",
        "data": {
            "scan_interval": 120,
            "fan_control_enabled": False,
            "snapshot_buttons_enabled": True,
            "discovery_debug": False,
            "wol_enabled": True,
            "wol_mac_address": "aa:bb:cc:dd:ee:ff",
            "wol_broadcast_address": "192.0.2.255",
            "wol_port": 7,
            "unrelated_option": "keep",
        },
    }
    assert "host" not in result["data"]
    assert "username" not in result["data"]
    assert "password" not in result["data"]
    assert "api_key" not in result["data"]


def test_config_flow_static_options_flow_factory() -> None:
    """Config flow should return the integration options-flow handler."""
    entry = _entry_with_feature_data()

    assert isinstance(
        config_flow_module.UnifiUnasConfigFlow.async_get_options_flow(entry),
        config_flow_module.UnifiUnasOptionsFlow,
    )


def test_config_flow_connection_form_handles_input_errors_and_duplicate() -> None:
    """Connection step should surface field errors and abort duplicates."""
    flow = config_flow_module.UnifiUnasConfigFlow()
    _patch_config_flow_result_helpers(flow)

    result = asyncio.run(
        flow.async_step_user(_complete_flow_input(wol_enabled=True, wol_mac_address=""))
    )
    assert result["type"] == "form"
    assert result["errors"] == {"wol_mac_address": "mac_required"}

    original_validate = config_flow_module._async_validate_for_form

    async def _validate(hass, data):
        return (
            {
                "title": "UNAS",
                "unique_id": "system-id",
                "unique_ids": ("system-id",),
                "device_scoped_unique_ids": ("system-id",),
                "host": "unas.local",
                "port": 443,
            },
            None,
        )

    config_flow_module._async_validate_for_form = _validate
    duplicate = types.SimpleNamespace(
        unique_id="system-id",
        data={"host": "unas.local", "port": 443},
    )
    _patch_config_flow_result_helpers(flow, entries=[duplicate])
    try:
        result = asyncio.run(flow.async_step_user(_complete_flow_input()))
    finally:
        config_flow_module._async_validate_for_form = original_validate

    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"


def test_config_flow_connection_form_sets_unique_id_without_progress_abort() -> None:
    """Manual setup should not abort when a parallel discovery flow is active."""
    flow = config_flow_module.UnifiUnasConfigFlow()
    _patch_config_flow_result_helpers(flow)
    captured: dict[str, Any] = {}

    async def _async_set_unique_id(
        unique_id: str | None = None,
        *,
        raise_on_progress: bool = True,
    ) -> None:
        captured["unique_id"] = unique_id
        captured["raise_on_progress"] = raise_on_progress
        flow._unique_id = unique_id

    flow.async_set_unique_id = _async_set_unique_id
    original_validate = config_flow_module._async_validate_for_form

    async def _validate(hass, data):
        return (
            {
                "title": "UNAS",
                "unique_id": "system-id",
                "unique_ids": ("system-id",),
                "device_scoped_unique_ids": ("system-id",),
                "host": "unas.local",
                "port": 443,
            },
            None,
        )

    config_flow_module._async_validate_for_form = _validate
    try:
        result = asyncio.run(flow.async_step_user(_complete_flow_input()))
    finally:
        config_flow_module._async_validate_for_form = original_validate

    assert result["type"] == "form"
    assert result["step_id"] == "features"
    assert captured == {"unique_id": "system-id", "raise_on_progress": False}


def test_config_flow_discovery_select_manual_invalid_and_empty_paths() -> None:
    """Discovery selection should support manual fallback and invalid selections."""
    flow = config_flow_module.UnifiUnasConfigFlow()
    _patch_config_flow_result_helpers(flow)
    flow._discovery_attempted = True

    result = asyncio.run(flow.async_step_discovery_select())
    assert result["type"] == "form"
    assert result["step_id"] == "user"

    device = config_flow_module.DiscoveredUnasDevice(
        key="host:192.0.2.10",
        label="UNAS",
        host="192.0.2.10",
    )
    flow._discovered_devices = {device.key: device}

    result = asyncio.run(flow.async_step_discovery_select({"discovered_device": "bad"}))
    assert result["type"] == "form"
    assert result["errors"] == {"base": "invalid_discovery_selection"}

    result = asyncio.run(
        flow.async_step_discovery_select(
            {"discovered_device": config_flow_module.MANUAL_DISCOVERY_VALUE}
        )
    )
    assert result["type"] == "form"
    assert result["step_id"] == "user"
    assert flow._connection_defaults is None


def test_config_flow_discovery_prepare_handles_failures_and_single_attempt() -> None:
    """Discovery scan failures should be debug-only and only attempted once."""
    flow = config_flow_module.UnifiUnasConfigFlow()
    _patch_config_flow_result_helpers(flow)
    original_discovery = config_flow_module.async_discover_unas_devices

    async def _raise_timeout():
        raise TimeoutError("scan timed out")

    config_flow_module.async_discover_unas_devices = _raise_timeout
    try:
        assert asyncio.run(flow._async_prepare_discovery_step()) is False
        assert asyncio.run(flow._async_prepare_discovery_step()) is False
    finally:
        config_flow_module.async_discover_unas_devices = original_discovery


def test_config_flow_zeroconf_aborts_non_unas_device() -> None:
    """Non-UNAS zeroconf records should abort before opening a form."""
    flow = config_flow_module.UnifiUnasConfigFlow()
    _patch_config_flow_result_helpers(flow)
    info = types.SimpleNamespace(
        name="Printer._ipp._tcp.local.",
        hostname="printer.local.",
        host="printer.local",
        type="_ipp._tcp.local.",
        properties={"model": "Printer"},
    )

    result = asyncio.run(flow.async_step_zeroconf(info))

    assert result["type"] == "abort"
    assert result["reason"] == "not_unas_device"


def test_config_flow_features_step_handles_missing_state_form_and_errors() -> None:
    """Feature step should fall back safely and keep field-level errors."""
    flow = config_flow_module.UnifiUnasConfigFlow()
    _patch_config_flow_result_helpers(flow)
    flow._discovery_attempted = True

    result = asyncio.run(flow.async_step_features())
    assert result["type"] == "form"
    assert result["step_id"] == "user"

    flow._pending_user_state = config_flow_module._FlowState(
        data=_complete_flow_input(),
        info={"title": "UNAS"},
    )
    created: list[dict[str, Any]] = []
    flow.async_create_entry = lambda **kwargs: created.append(kwargs) or {
        "type": "create_entry",
        **kwargs,
    }

    result = asyncio.run(flow.async_step_features())
    assert result["type"] == "form"
    assert result["step_id"] == "features"
    assert result["last_step"] is True

    result = asyncio.run(
        flow.async_step_features({"wol_enabled": True, "wol_mac_address": ""})
    )
    assert result["type"] == "form"
    assert result["errors"] == {"wol_mac_address": "mac_required"}
    assert created == []

    result = asyncio.run(
        flow.async_step_features(
            {
                "scan_interval": 30,
                "fan_control_enabled": True,
                "snapshot_buttons_enabled": False,
                "discovery_debug": False,
                "wol_enabled": False,
                "wol_mac_address": "",
                "wol_broadcast_address": "255.255.255.255",
                "wol_port": 9,
            }
        )
    )
    assert result["type"] == "create_entry"
    assert len(created) == 1

    result = asyncio.run(
        flow.async_step_features(
            {
                "scan_interval": 30,
                "fan_control_enabled": True,
                "snapshot_buttons_enabled": False,
                "discovery_debug": False,
                "wol_enabled": False,
            }
        )
    )
    assert result["type"] == "form"
    assert result["step_id"] == "user"
    assert len(created) == 1


def test_config_flow_reauth_form_error_and_success_paths() -> None:
    """Reauth should validate credentials and preserve entry identity."""
    entry = _entry_with_feature_data(username="old-user")
    entry.unique_id = "system-id"
    flow = config_flow_module.UnifiUnasConfigFlow()
    _patch_config_flow_result_helpers(flow)
    flow._get_reauth_entry = lambda: entry

    result = asyncio.run(flow.async_step_reauth({}))
    assert result["type"] == "form"
    assert result["step_id"] == "reauth_confirm"

    original_validate = config_flow_module._async_validate_for_form

    async def _validate_error(hass, data):
        return None, "invalid_auth"

    config_flow_module._async_validate_for_form = _validate_error
    try:
        result = asyncio.run(
            flow.async_step_reauth_confirm(
                {"username": "new-user", "password": "", "api_key": "bad-token"}
            )
        )
    finally:
        config_flow_module._async_validate_for_form = original_validate
    assert result["type"] == "form"
    assert result["errors"] == {"base": "invalid_auth"}

    async def _validate_success(hass, data):
        return (
            {
                "title": "UNAS",
                "unique_id": "system-id",
                "unique_ids": ("system-id",),
                "device_scoped_unique_ids": ("system-id",),
                "host": "unas.local",
                "port": 443,
            },
            None,
        )

    reloads: list[str] = []
    flow.hass.config_entries.async_schedule_reload = reloads.append
    config_flow_module._async_validate_for_form = _validate_success
    try:
        result = asyncio.run(
            flow.async_step_reauth_confirm(
                {"username": "new-user", "password": "new-pass", "api_key": ""}
            )
        )
    finally:
        config_flow_module._async_validate_for_form = original_validate

    assert result["type"] == "abort"
    assert result["data"]["username"] == "new-user"
    assert result["data"]["password"] == "new-pass"
    assert reloads == []


def test_config_flow_reauth_sets_unique_id_without_progress_abort() -> None:
    """Reauth should set the entry identity without progress-abort races."""
    entry = _entry_with_feature_data(username="old-user")
    entry.unique_id = "system-id"
    flow = config_flow_module.UnifiUnasConfigFlow()
    _patch_config_flow_result_helpers(flow)
    flow._get_reauth_entry = lambda: entry
    captured: dict[str, Any] = {}

    async def _async_set_unique_id(
        unique_id: str | None = None,
        *,
        raise_on_progress: bool = True,
    ) -> None:
        captured["unique_id"] = unique_id
        captured["raise_on_progress"] = raise_on_progress
        flow._unique_id = unique_id

    flow.async_set_unique_id = _async_set_unique_id
    original_validate = config_flow_module._async_validate_for_form

    async def _validate(hass, data):
        return (
            {
                "title": "UNAS",
                "unique_id": "system-id",
                "unique_ids": ("system-id",),
                "device_scoped_unique_ids": ("system-id",),
                "host": "unas.local",
                "port": 443,
            },
            None,
        )

    config_flow_module._async_validate_for_form = _validate
    try:
        result = asyncio.run(
            flow.async_step_reauth_confirm(
                {"username": "new-user", "password": "new-pass", "api_key": ""}
            )
        )
    finally:
        config_flow_module._async_validate_for_form = original_validate

    assert result["type"] == "abort"
    assert captured == {"unique_id": "system-id", "raise_on_progress": False}


def test_config_flow_reconfigure_menu_connection_and_feature_paths() -> None:
    """Reconfigure flows should cover menu, connection and feature updates."""
    entry = _entry_with_feature_data()
    entry.unique_id = "system-id"
    flow = config_flow_module.UnifiUnasConfigFlow()
    _patch_config_flow_result_helpers(flow)
    flow._get_reconfigure_entry = lambda: entry
    reloads: list[str] = []
    flow.hass.config_entries.async_schedule_reload = reloads.append

    result = asyncio.run(flow.async_step_reconfigure())
    assert result["type"] == "menu"
    assert result["menu_options"] == [
        "reconfigure_connection",
        "reconfigure_features",
    ]

    result = asyncio.run(flow.async_step_reconfigure_connection())
    assert result["type"] == "form"
    assert result["step_id"] == "reconfigure_connection"

    original_validate = config_flow_module._async_validate_for_form

    async def _validate_wrong(hass, data):
        return (
            {
                "title": "Other",
                "unique_id": "other-system-id",
                "unique_ids": ("other-system-id",),
                "device_scoped_unique_ids": ("other-system-id",),
                "host": "other.local",
                "port": 443,
            },
            None,
        )

    config_flow_module._async_validate_for_form = _validate_wrong
    try:
        result = asyncio.run(
            flow.async_step_reconfigure_connection(
                {"host": "other.local", "port": 443}
            )
        )
    finally:
        config_flow_module._async_validate_for_form = original_validate
    assert result["type"] == "form"
    assert result["errors"] == {"base": "wrong_device"}

    async def _validate_success(hass, data):
        return (
            {
                "title": "UNAS",
                "unique_id": "system-id",
                "unique_ids": ("system-id",),
                "device_scoped_unique_ids": ("system-id",),
                "host": "unas.local",
                "port": 443,
            },
            None,
        )

    config_flow_module._async_validate_for_form = _validate_success
    try:
        result = asyncio.run(
            flow.async_step_reconfigure_connection(
                {"username": "changed-user", "password": "changed-pass"}
            )
        )
    finally:
        config_flow_module._async_validate_for_form = original_validate
    assert result["type"] == "abort"
    assert result["data"]["username"] == "changed-user"

    result = asyncio.run(flow.async_step_reconfigure_features())
    assert result["type"] == "form"
    assert result["step_id"] == "reconfigure_features"

    flow.hass.data = {
        config_flow_module.DOMAIN: {
            "entry-1": types.SimpleNamespace(is_device_online=False)
        }
    }
    result = asyncio.run(
        flow.async_step_reconfigure_features(
            {"wol_enabled": False, "wol_mac_address": ""}
        )
    )
    assert result["type"] == "form"
    assert result["errors"] == {"base": "offline_without_wol"}

    result = asyncio.run(
        flow.async_step_reconfigure_features(
            {
                "wol_enabled": True,
                "wol_mac_address": "aa:bb:cc:dd:ee:ff",
            }
        )
    )
    assert result["type"] == "abort"
    assert result["options"]["wol_enabled"] is True


def test_initial_feature_step_writes_feature_settings_to_options() -> None:
    """New entries should keep feature settings out of entry data."""
    flow = config_flow_module.UnifiUnasConfigFlow()
    flow.async_create_entry = lambda **kwargs: {"type": "create_entry", **kwargs}
    flow._pending_user_state = config_flow_module._FlowState(
        data={
            "host": "unas.local",
            "port": 443,
            "ssl": True,
            "verify_ssl": False,
            "username": "",
            "password": "",
            "api_key": "token",
            "discovery_mac_address": "aa:bb:cc:dd:ee:ff",
            "scan_interval": 30,
            "fan_control_enabled": True,
            "snapshot_buttons_enabled": True,
            "wol_enabled": False,
            "wol_mac_address": "",
            "wol_broadcast_address": "255.255.255.255",
            "wol_port": 9,
        },
        info={"title": "UniFi Drive (unas.local)"},
    )

    result = asyncio.run(
        flow.async_step_features(
            {
                "scan_interval": 120,
                "fan_control_enabled": False,
                "snapshot_buttons_enabled": True,
                "wol_enabled": True,
                "wol_mac_address": "AA:BB:CC:DD:EE:FF",
                "wol_broadcast_address": "192.0.2.255",
                "wol_port": 7,
            }
        )
    )

    assert result["type"] == "create_entry"
    assert result["title"] == "UniFi Drive (unas.local)"
    assert result["data"] == {
        "host": "unas.local",
        "port": 443,
        "ssl": True,
        "verify_ssl": False,
        "username": "",
        "password": "",
        "api_key": "token",
        "discovery_mac_address": "aa:bb:cc:dd:ee:ff",
    }
    assert result["options"] == {
        "scan_interval": 120,
        "fan_control_enabled": False,
        "snapshot_buttons_enabled": True,
        "discovery_debug": False,
        "wol_enabled": True,
        "wol_mac_address": "aa:bb:cc:dd:ee:ff",
        "wol_broadcast_address": "192.0.2.255",
        "wol_port": 7,
    }


def test_options_flow_returns_feature_field_errors() -> None:
    """OptionsFlow should surface feature validation errors on the form."""
    entry = _entry_with_feature_data()
    flow = config_flow_module.UnifiUnasOptionsFlow(entry)
    _patch_options_flow_result_helpers(flow)

    result = asyncio.run(
        flow.async_step_init(
            {
                "scan_interval": 120,
                "fan_control_enabled": True,
                "snapshot_buttons_enabled": True,
                "wol_enabled": True,
                "wol_mac_address": "",
                "wol_broadcast_address": "255.255.255.255",
                "wol_port": 9,
            }
        )
    )

    assert result["type"] == "form"
    assert result["step_id"] == "init"
    assert result["errors"] == {"wol_mac_address": "mac_required"}


def test_options_flow_keeps_offline_guard() -> None:
    """Feature option writes should keep the offline reload protection."""
    entry = _entry_with_feature_data()
    entry.state = "setup_retry"
    flow = config_flow_module.UnifiUnasOptionsFlow(entry)
    _patch_options_flow_result_helpers(flow)

    result = asyncio.run(
        flow.async_step_init(
            {
                "scan_interval": 120,
                "fan_control_enabled": True,
                "snapshot_buttons_enabled": True,
                "wol_enabled": False,
                "wol_mac_address": "",
                "wol_broadcast_address": "255.255.255.255",
                "wol_port": 9,
            }
        )
    )

    assert result["type"] == "form"
    assert result["step_id"] == "init"
    assert result["errors"] == {"base": "offline_without_wol"}


def test_config_flow_does_not_call_reload_methods() -> None:
    """Config flows must not reload entries when an update listener is registered."""
    source = Path(config_flow_module.__file__).read_text(encoding="utf-8")

    assert "async_schedule_reload" not in source
    assert "async_update_reload_and_abort" not in source


def test_normalize_host_accepts_dns_names_urls_and_ports() -> None:
    """Host normalization should support DNS names, URLs and host:port input."""
    normalize = config_flow_module._normalize_host_input

    assert normalize("unas.local") == ("unas.local", None, None)
    assert normalize("https://unas.example.lan:8443") == (
        "unas.example.lan",
        8443,
        True,
    )
    assert normalize("http://unas.example.lan") == ("unas.example.lan", None, False)
    assert normalize("192.0.2.10:7443") == ("192.0.2.10", 7443, None)


def test_normalize_host_accepts_ipv6_and_rejects_numeric_hostname() -> None:
    """IPv6 literals should be bracketed and numeric-only hostnames rejected."""
    normalize = config_flow_module._normalize_host_input

    assert normalize("2001:db8::1") == ("[2001:db8::1]", None, None)
    assert normalize("[2001:db8::1]:443") == ("[2001:db8::1]", 443, None)
    assert normalize("https://[2001:db8::10]:8443") == (
        "[2001:db8::10]",
        8443,
        True,
    )

    try:
        normalize("12345")
    except ValueError:
        pass
    else:
        raise AssertionError("numeric-only host should be rejected")


def test_normalize_user_input_requires_wol_mac_when_enabled() -> None:
    """WOL-enabled input without MAC should fail fast with a field error."""
    data = {
        "host": "unas.local",
        "port": 443,
        "ssl": True,
        "verify_ssl": False,
        "username": "",
        "password": "",
        "api_key": "token",
        "scan_interval": 30,
        "fan_control_enabled": True,
        "wol_enabled": True,
        "wol_mac_address": "",
        "wol_broadcast_address": "255.255.255.255",
        "wol_port": 9,
    }

    try:
        config_flow_module._normalize_user_input(data)
    except config_flow_module.FlowInputError as err:
        assert err.field == "wol_mac_address"
        assert err.reason == "mac_required"
    else:
        raise AssertionError("missing WOL MAC should raise FlowInputError")


def test_normalize_user_input_rejects_invalid_wol_mac() -> None:
    """Invalid WOL MAC values should map to the expected field-level error."""
    original_normalizer = config_flow_module.normalize_mac_address

    def _raise_invalid_mac(value: str) -> str:
        raise ValueError("invalid mac")

    config_flow_module.normalize_mac_address = _raise_invalid_mac
    try:
        data = {
            "host": "unas.local",
            "port": 443,
            "ssl": True,
            "verify_ssl": False,
            "username": "",
            "password": "",
            "api_key": "token",
            "scan_interval": 30,
            "fan_control_enabled": True,
            "wol_enabled": True,
            "wol_mac_address": "invalid-mac",
            "wol_broadcast_address": "255.255.255.255",
            "wol_port": 9,
        }

        try:
            config_flow_module._normalize_user_input(data)
        except config_flow_module.FlowInputError as err:
            assert err.field == "wol_mac_address"
            assert err.reason == "invalid_mac_address"
        else:
            raise AssertionError("invalid WOL MAC should raise FlowInputError")
    finally:
        config_flow_module.normalize_mac_address = original_normalizer


def test_normalize_user_input_rejects_invalid_wol_broadcast() -> None:
    """Invalid WOL broadcast addresses should map to the expected field error."""

    original_validator = config_flow_module.validate_ipv4_address

    def _raise_invalid_ipv4(value: str) -> str:
        raise ValueError("invalid ipv4")

    config_flow_module.validate_ipv4_address = _raise_invalid_ipv4
    try:
        data = {
            "host": "unas.local",
            "port": 443,
            "ssl": True,
            "verify_ssl": False,
            "username": "",
            "password": "",
            "api_key": "token",
            "scan_interval": 30,
            "fan_control_enabled": True,
            "wol_enabled": True,
            "wol_mac_address": "AA:BB:CC:DD:EE:FF",
            "wol_broadcast_address": "not-an-ip",
            "wol_port": 9,
        }

        try:
            config_flow_module._normalize_user_input(data)
        except config_flow_module.FlowInputError as err:
            assert err.field == "wol_broadcast_address"
            assert err.reason == "invalid_broadcast_address"
        else:
            raise AssertionError("invalid WOL broadcast should raise FlowInputError")
    finally:
        config_flow_module.validate_ipv4_address = original_validator


def test_normalize_user_input_handles_snapshot_buttons_default_and_override() -> None:
    """Snapshot buttons should default off and preserve explicit opt-in."""
    base_data = {
        "host": "unas.local",
        "port": 443,
        "ssl": True,
        "verify_ssl": False,
        "username": "",
        "password": "",
        "api_key": "token",
        "scan_interval": 30,
        "fan_control_enabled": True,
        "wol_enabled": False,
        "wol_mac_address": "",
        "wol_broadcast_address": "255.255.255.255",
        "wol_port": 9,
    }

    data = config_flow_module._normalize_user_input(base_data)
    assert data["snapshot_buttons_enabled"] is False

    data = config_flow_module._normalize_user_input(
        {**base_data, "snapshot_buttons_enabled": True}
    )
    assert data["snapshot_buttons_enabled"] is True


def test_merged_reconfigure_data_supports_feature_only_updates() -> None:
    """Feature reconfigure should not require resubmitting connection settings."""
    current = {
        "host": "unas.local",
        "port": 443,
        "ssl": True,
        "verify_ssl": False,
        "username": "test-user",
        "password": "stored-password",
        "api_key": "stored-token",
        "scan_interval": 30,
        "fan_control_enabled": True,
        "snapshot_buttons_enabled": False,
        "wol_enabled": False,
        "wol_mac_address": "",
        "wol_broadcast_address": "255.255.255.255",
        "wol_port": 9,
    }

    data = config_flow_module._merged_reconfigure_data(
        current,
        {
            "scan_interval": 60,
            "snapshot_buttons_enabled": True,
        },
    )

    assert data["host"] == "unas.local"
    assert data["username"] == "test-user"
    assert data["password"] == "stored-password"
    assert data["api_key"] == "stored-token"
    assert data["scan_interval"] == 60
    assert data["snapshot_buttons_enabled"] is True


def test_validate_input_or_allow_wol_offline_uses_updated_feature_data() -> None:
    """Offline reconfigure should allow saving only after WOL details are provided."""
    original_validate = config_flow_module._validate_input

    async def _raise_cannot_connect(hass, data):
        raise config_flow_module.CannotConnect

    config_flow_module._validate_input = _raise_cannot_connect
    try:
        base_data = {
            "host": "unas.local",
            "port": 443,
            "ssl": True,
            "verify_ssl": False,
            "username": "",
            "password": "",
            "api_key": "token",
            "scan_interval": 30,
            "fan_control_enabled": True,
            "snapshot_buttons_enabled": True,
            "wol_enabled": False,
            "wol_mac_address": "",
            "wol_broadcast_address": "255.255.255.255",
            "wol_port": 9,
        }

        try:
            asyncio.run(
                config_flow_module._validate_input_or_allow_wol_offline(
                    object(),
                    base_data,
                )
            )
        except config_flow_module.CannotConnect:
            pass
        else:
            raise AssertionError("offline reconfigure without WOL should fail")

        info = asyncio.run(
            config_flow_module._validate_input_or_allow_wol_offline(
                object(),
                {
                    **base_data,
                    "wol_enabled": True,
                    "wol_mac_address": "aa:bb:cc:dd:ee:ff",
                },
            )
        )
    finally:
        config_flow_module._validate_input = original_validate

    assert info["title"] == "UniFi Drive (unas.local)"
    assert info["host"] == "unas.local"


def test_connection_validation_does_not_allow_wol_offline_bypass() -> None:
    """Connection reconfigure should still fail when the API cannot be reached."""
    original_validate = config_flow_module._validate_input

    async def _raise_cannot_connect(hass, data):
        raise config_flow_module.CannotConnect

    config_flow_module._validate_input = _raise_cannot_connect
    try:
        data = {
            "host": "unas.local",
            "port": 443,
            "ssl": True,
            "verify_ssl": False,
            "username": "",
            "password": "",
            "api_key": "token",
            "scan_interval": 30,
            "fan_control_enabled": True,
            "snapshot_buttons_enabled": True,
            "wol_enabled": True,
            "wol_mac_address": "aa:bb:cc:dd:ee:ff",
            "wol_broadcast_address": "255.255.255.255",
            "wol_port": 9,
        }

        info, error = asyncio.run(
            config_flow_module._async_validate_for_form(object(), data)
        )
    finally:
        config_flow_module._validate_input = original_validate

    assert info is None
    assert error == "cannot_connect"


def test_validate_for_form_catches_unexpected_exceptions() -> None:
    """Validator helpers should not leak unexpected exceptions into the flow."""
    original_validate = config_flow_module._validate_input

    async def _raise_key_error(hass, data):
        raise KeyError("missing payload section")

    config_flow_module._validate_input = _raise_key_error
    try:
        info, error = asyncio.run(
            config_flow_module._async_validate_for_form(object(), {"host": "unas.local"})
        )
    finally:
        config_flow_module._validate_input = original_validate

    assert info is None
    assert error == "unknown"


def test_validate_input_uses_system_mac_when_device_id_missing() -> None:
    """Manual setup should use MAC as the fallback unique ID when available."""
    validation_globals = config_flow_module.async_validate_input.__globals__
    original_client = validation_globals["UnifiUnasApiClient"]
    original_session = validation_globals["async_create_clientsession"]

    class _Client:
        device_unique_ids = ()
        device_scoped_unique_ids = ()

        def __init__(self, *args, **kwargs) -> None:
            pass

        async def async_check_connection(self) -> dict[str, Any]:
            return {
                "pools": [],
                "_system": {
                    "wake_on_lan_enabled": True,
                    "macAddress": "AA-BB-CC-DD-EE-FF",
                },
            }

    validation_globals["UnifiUnasApiClient"] = _Client
    validation_globals["async_create_clientsession"] = lambda *args, **kwargs: object()
    try:
        info = asyncio.run(
            config_flow_module.async_validate_input(
                object(),
                {
                    "host": "unas.local",
                    "port": 443,
                    "ssl": True,
                    "verify_ssl": False,
                    "username": "",
                    "password": "",
                    "api_key": "token",
                },
            )
        )
    finally:
        validation_globals["UnifiUnasApiClient"] = original_client
        validation_globals["async_create_clientsession"] = original_session

    assert info["unique_id"] == "aa:bb:cc:dd:ee:ff"
    assert info["unique_ids"] == ("aa:bb:cc:dd:ee:ff",)
    assert info["feature_defaults"]["wol_mac_address"] == "AA-BB-CC-DD-EE-FF"


def test_entry_info_uses_device_scoped_ids_for_reauth() -> None:
    """Validation info should preserve current device-scoped IDs."""
    info = config_flow_module._entry_info(
        {
            "host": "unas.local",
            "port": 443,
        },
        unique_id="system-id",
        unique_ids=("system-id", "legacy-account-id"),
        device_scoped_unique_ids=("system-id",),
    )

    assert info["unique_id"] == "system-id"
    assert info["unique_ids"] == ("system-id", "legacy-account-id")
    assert info["device_scoped_unique_ids"] == ("system-id",)
    assert info["host"] == "unas.local"
    assert info["port"] == 443
    assert config_flow_module._entry_unique_id_matches("system-id", info) is True
    assert (
        config_flow_module._entry_unique_id_matches("legacy-account-id", info)
        is False
    )
    assert config_flow_module._entry_unique_id_matches("other-device", info) is False


def test_reconfigure_device_guard_rejects_different_device_id() -> None:
    """Connection reconfigure must not move an entry to another device."""
    entry = types.SimpleNamespace(
        unique_id="system-id",
        data={"host": "unas.local", "port": 443},
    )
    info = {
        "unique_id": "other-system-id",
        "unique_ids": ("other-system-id",),
        "device_scoped_unique_ids": ("other-system-id",),
        "host": "unas.local",
        "port": 443,
    }

    assert config_flow_module._entry_matches_validated_device(entry, info) is False


def test_reconfigure_device_guard_accepts_legacy_host_id_for_same_connection() -> None:
    """Host:port fallback IDs should remain valid for the same connection."""
    entry = types.SimpleNamespace(
        unique_id="unas.local:443",
        data={"host": "unas.local", "port": 443},
    )
    info = {
        "unique_id": "system-id",
        "unique_ids": ("system-id",),
        "device_scoped_unique_ids": ("system-id",),
        "host": "unas.local",
        "port": 443,
    }

    assert config_flow_module._entry_matches_validated_device(entry, info) is True


def test_reconfigure_device_guard_rejects_legacy_host_id_for_other_connection() -> None:
    """Host:port fallback IDs must not move an entry to another connection."""
    entry = types.SimpleNamespace(
        unique_id="unas.local:443",
        data={"host": "unas.local", "port": 443},
    )
    info = {
        "unique_id": "system-id",
        "unique_ids": ("system-id",),
        "device_scoped_unique_ids": ("system-id",),
        "host": "other-unas.local",
        "port": 443,
    }

    assert config_flow_module._entry_matches_validated_device(entry, info) is False


def test_reconfigure_device_guard_rejects_legacy_alias() -> None:
    """Account-level aliases should not be accepted as device identity."""
    entry = types.SimpleNamespace(
        unique_id="legacy-account-id",
        data={"host": "unas.local", "port": 443},
    )
    info = {
        "unique_id": "system-id",
        "unique_ids": ("system-id", "legacy-account-id"),
        "device_scoped_unique_ids": ("system-id",),
        "host": "other-unas.local",
        "port": 443,
    }

    assert config_flow_module._entry_matches_validated_device(entry, info) is False


def test_feature_reconfigure_blocks_offline_reload_without_wol() -> None:
    """Feature-only reconfigure should not strand an offline entry without WOL."""
    entry = types.SimpleNamespace(entry_id="entry-1")
    hass = types.SimpleNamespace(
        data={
            config_flow_module.DOMAIN: {
                "entry-1": types.SimpleNamespace(is_device_online=False)
            }
        }
    )
    data = {
        "wol_enabled": False,
        "wol_mac_address": "",
    }

    assert (
        config_flow_module._feature_reconfigure_would_reload_offline_without_wol(
            hass,
            entry,
            data,
        )
        is True
    )


def test_feature_reconfigure_blocks_setup_retry_without_coordinator() -> None:
    """Offline setup retry entries have no coordinator but still reload unsafely."""
    entry = types.SimpleNamespace(entry_id="entry-1", state="setup_retry")
    hass = types.SimpleNamespace(data={config_flow_module.DOMAIN: {}})
    data = {
        "wol_enabled": False,
        "wol_mac_address": "",
    }

    assert (
        config_flow_module._feature_reconfigure_would_reload_offline_without_wol(
            hass,
            entry,
            data,
        )
        is True
    )


def test_feature_reconfigure_allows_offline_reload_with_wol() -> None:
    """Offline feature reconfigure remains possible when WOL is configured."""
    entry = types.SimpleNamespace(entry_id="entry-1")
    hass = types.SimpleNamespace(
        data={
            config_flow_module.DOMAIN: {
                "entry-1": types.SimpleNamespace(is_device_online=False)
            }
        }
    )
    data = {
        "wol_enabled": True,
        "wol_mac_address": "aa:bb:cc:dd:ee:ff",
    }

    assert (
        config_flow_module._feature_reconfigure_would_reload_offline_without_wol(
            hass,
            entry,
            data,
        )
        is False
    )


def test_any_unique_id_configured_uses_device_scoped_ids_for_setup() -> None:
    """Initial setup should not block another device by login-level aliases."""
    info = {
        "unique_id": "system-id",
        "unique_ids": ("system-id", "legacy-account-id"),
        "device_scoped_unique_ids": ("system-id",),
    }

    class _Entry:
        def __init__(self, unique_id: str) -> None:
            self.unique_id = unique_id

    class _ConfigEntries:
        def async_entries(self, domain: str):
            assert domain == config_flow_module.DOMAIN
            return [_Entry("legacy-account-id")]

    hass = types.SimpleNamespace(config_entries=_ConfigEntries())

    assert config_flow_module._any_unique_id_configured(hass, info) is False


def test_any_unique_id_configured_ignores_legacy_alias_on_same_connection() -> None:
    """Account-level aliases should not dedupe current setup flows."""
    info = {
        "unique_id": "system-id",
        "unique_ids": ("system-id", "legacy-account-id"),
        "device_scoped_unique_ids": ("system-id",),
        "host": "unas.local",
        "port": 443,
    }

    class _Entry:
        unique_id = "legacy-account-id"
        data = {"host": "unas.local", "port": 443}

    class _ConfigEntries:
        def async_entries(self, domain: str):
            assert domain == config_flow_module.DOMAIN
            return [_Entry()]

    hass = types.SimpleNamespace(config_entries=_ConfigEntries())

    assert config_flow_module._any_unique_id_configured(hass, info) is False


def test_any_unique_id_configured_matches_legacy_host_id_on_same_connection() -> None:
    """Initial setup should still dedupe older host:port fallback entries."""
    info = {
        "unique_id": "system-id",
        "unique_ids": ("system-id",),
        "device_scoped_unique_ids": ("system-id",),
        "host": "unas.local",
        "port": 443,
    }

    class _Entry:
        unique_id = "UNAS.LOCAL:443"
        data = {"host": "unas.local", "port": 443}

    class _ConfigEntries:
        def async_entries(self, domain: str):
            assert domain == config_flow_module.DOMAIN
            return [_Entry()]

    hass = types.SimpleNamespace(config_entries=_ConfigEntries())

    assert config_flow_module._any_unique_id_configured(hass, info) is True


def test_any_unique_id_configured_matches_existing_device_scoped_id() -> None:
    """Initial setup should still dedupe when the device ID is already present."""
    info = {
        "unique_id": "system-id",
        "unique_ids": ("system-id", "legacy-account-id"),
        "device_scoped_unique_ids": ("system-id",),
    }

    class _Entry:
        def __init__(self, unique_id: str) -> None:
            self.unique_id = unique_id

    class _ConfigEntries:
        def async_entries(self, domain: str):
            assert domain == config_flow_module.DOMAIN
            return [_Entry("system-id")]

    hass = types.SimpleNamespace(config_entries=_ConfigEntries())

    assert config_flow_module._any_unique_id_configured(hass, info) is True
