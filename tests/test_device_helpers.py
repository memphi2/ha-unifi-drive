"""Unit tests for Home Assistant device metadata helpers."""

from dataclasses import dataclass
from enum import Enum
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
import types

import pytest


def _load_device_module():
    root = Path(__file__).resolve().parents[1]
    package_root = root / "custom_components" / "unifi_unas"

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

    helpers_pkg = types.ModuleType("homeassistant.helpers")
    sys.modules["homeassistant.helpers"] = helpers_pkg

    device_registry_pkg = types.ModuleType("homeassistant.helpers.device_registry")
    device_registry_pkg.DeviceInfo = dict
    sys.modules["homeassistant.helpers.device_registry"] = device_registry_pkg

    const_spec = spec_from_file_location(
        "custom_components.unifi_unas.const",
        package_root / "const.py",
    )
    if const_spec is None or const_spec.loader is None:
        raise RuntimeError("Could not load const module spec")
    const_module = module_from_spec(const_spec)
    sys.modules["custom_components.unifi_unas.const"] = const_module
    const_spec.loader.exec_module(const_module)

    device_spec = spec_from_file_location(
        "custom_components.unifi_unas.device",
        package_root / "device.py",
    )
    if device_spec is None or device_spec.loader is None:
        raise RuntimeError("Could not load device module spec")
    device_module = module_from_spec(device_spec)
    sys.modules["custom_components.unifi_unas.device"] = device_module
    device_spec.loader.exec_module(device_module)
    return device_module


device_module = _load_device_module()


class _FakeClient:
    base_url = "https://unas.local"


class _FakeCoordinator:
    client = _FakeClient()
    data = {
        "_system": {
            "hardware": {
                "shortname": "UNAS2",
                "name": "UniFi Drive UNAS",
                "firmwareVersion": "5.0.17",
            }
        }
    }


class _FakeEntry:
    title = "Keller"


_UNDEFINED = object()


@dataclass(kw_only=True, slots=True)
class _AttributeDeviceInfo:
    """Model the new attribute API without allowing compatibility methods."""

    identifiers: object = _UNDEFINED
    name: object = _UNDEFINED
    manufacturer: object = _UNDEFINED
    model: object = _UNDEFINED
    sw_version: object = _UNDEFINED
    configuration_url: object = _UNDEFINED

    def get(self, *args: object) -> object:
        raise AssertionError("Modern DeviceInfo must not use the dict compatibility API")


@pytest.mark.parametrize("factory", (dict, _AttributeDeviceInfo))
def test_device_registry_metadata_extracts_only_registry_text(factory) -> None:
    """Only the four synchronized text fields belong in registry updates."""
    expected = {
        "manufacturer": "Ubiquiti",
        "model": "UNAS2",
        "sw_version": "5.1.10",
        "configuration_url": "https://unas.example",
    }
    info = factory(**expected, identifiers={("unifi_unas", "device-1")}, name="UNAS")

    assert device_module.device_registry_metadata(info) == expected


@pytest.mark.parametrize("factory", (dict, _AttributeDeviceInfo))
def test_device_registry_metadata_skips_missing_fields(factory) -> None:
    """Missing keys and unset dataclass attributes must not clear cached values."""
    info = factory(model="UNAS2")

    assert device_module.device_registry_metadata(info) == {"model": "UNAS2"}


@pytest.mark.parametrize("factory", (dict, _AttributeDeviceInfo))
@pytest.mark.parametrize("value", (None, "", _UNDEFINED))
def test_device_registry_metadata_skips_empty_and_undefined_text(factory, value) -> None:
    """Never pass empty values or HA's truthy unset sentinel to the registry."""
    info = factory(
        manufacturer=value, model=value, sw_version=value, configuration_url=value
    )

    assert device_module.device_registry_metadata(info) == {}


def test_build_device_info_supports_attribute_constructor(monkeypatch) -> None:
    """The existing builder must also work with keyword-only dataclasses."""
    monkeypatch.setattr(device_module, "DeviceInfo", _AttributeDeviceInfo)

    info = device_module.build_device_info(_FakeCoordinator(), _FakeEntry(), "device-1")

    assert info.identifiers == {("unifi_unas", "device-1")}
    assert info.model == "UNAS2"
    assert info.sw_version == "5.0.17"
    assert device_module.device_registry_metadata(info)["sw_version"] == "5.0.17"


def test_device_info_uses_dynamic_model_and_firmware_version() -> None:
    """DeviceInfo should reflect UniFi OS hardware metadata when available."""
    info = device_module.build_device_info(_FakeCoordinator(), _FakeEntry(), "dev-1")

    assert info["model"] == "UNAS2"
    assert info["sw_version"] == "5.0.17"
    assert info["name"] == "Keller"
    assert info["configuration_url"] == "https://unas.local"


def test_device_info_falls_back_to_hardware_name_and_ucore_version() -> None:
    """DeviceInfo should keep useful metadata when shortname/firmware are absent."""
    coordinator = types.SimpleNamespace(
        client=types.SimpleNamespace(base_url="https://backup.local"),
        data={
            "_system": {
                "ucore_version": "5.1.0",
                "hardware": {
                    "shortname": "",
                    "name": "UniFi Drive Backup",
                    "firmwareVersion": "",
                },
            }
        },
    )

    info = device_module.build_device_info(
        coordinator,
        _FakeEntry(),
        "backup-user",
        configuration_url="https://override.local",
    )

    assert info["identifiers"] == {("unifi_unas", "backup-user")}
    assert info["model"] == "UniFi Drive Backup"
    assert info["sw_version"] == "5.1.0"
    assert info["configuration_url"] == "https://override.local"


def test_device_info_uses_raw_system_payload_version_fields() -> None:
    """DeviceInfo should accept system metadata that is not nested under _system."""
    coordinator = types.SimpleNamespace(
        client=types.SimpleNamespace(base_url="https://raw.local"),
        data={
            "hardware": {"shortname": "UNAS2W"},
            "firmware_version": "5.1.10",
        },
    )

    info = device_module.build_device_info(coordinator, _FakeEntry(), "raw-system")

    assert info["model"] == "UNAS2W"
    assert info["sw_version"] == "5.1.10"


def test_device_info_uses_client_cached_system_metadata() -> None:
    """Fresh installs should keep firmware metadata when only the client has it."""
    coordinator = types.SimpleNamespace(
        client=types.SimpleNamespace(
            base_url="https://cached.local",
            _system_info={
                "hardware": {
                    "shortname": "UNAS2W",
                    "firmwareVersion": "5.1.10",
                }
            },
        ),
        data={"pools": []},
    )

    info = device_module.build_device_info(coordinator, _FakeEntry(), "cached-system")

    assert info["model"] == "UNAS2W"
    assert info["sw_version"] == "5.1.10"


def test_device_info_uses_default_model_without_system_payload() -> None:
    """DeviceInfo should remain stable while the device is offline."""
    coordinator = types.SimpleNamespace(
        client=types.SimpleNamespace(base_url=None),
        data=None,
    )

    info = device_module.build_device_info(coordinator, _FakeEntry(), "offline-entry")

    assert info["identifiers"] == {("unifi_unas", "offline-entry")}
    assert info["model"] == "UniFi Drive / UNAS"
    assert "sw_version" not in info
    assert info["configuration_url"] is None


def test_device_info_rejects_non_text_configuration_url() -> None:
    coordinator = types.SimpleNamespace(client=types.SimpleNamespace(base_url=object()), data={})
    info = device_module.build_device_info(coordinator, _FakeEntry(), "synthetic-device")
    assert info["configuration_url"] is None
