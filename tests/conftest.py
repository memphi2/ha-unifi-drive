"""Pytest collection cleanup for lightweight module-stub tests."""

from __future__ import annotations

from importlib.util import find_spec
from types import ModuleType
import sys

import pytest

HA_BACKED_TEST_FILES = {
    "test_api_http_safety.py",
    "test_config_flow_sessions.py",
    "test_control_entity_states.py",
    "test_core_monitoring_entity_states.py",
    "test_integration_entry_setup.py",
    "test_snapshot_control_entity_states.py",
}

_MISSING = object()
_MODULE_ROOTS_TO_RESTORE = (
    "aiohttp",
    "custom_components",
    "homeassistant",
    "voluptuous",
)
_ORIGINAL_MODULES = {
    name: module
    for name, module in sys.modules.items()
    if any(
        name == root or name.startswith(f"{root}.")
        for root in _MODULE_ROOTS_TO_RESTORE
    )
}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Remove collection-time stubs before pytest-homeassistant fixtures run.

    Several helper tests import integration modules with tiny Home Assistant
    stubs at module import time. Those direct module references remain valid for
    the helper tests, but leaving the stubs in ``sys.modules`` breaks the real
    Home Assistant pytest plugin and the integration setup tests.
    """
    _skip_ha_backed_tests_without_plugin(items)
    _remove_collection_stubs()
    _prime_homeassistant_plugin_modules()


def _skip_ha_backed_tests_without_plugin(items: list[pytest.Item]) -> None:
    """Skip HA-backed tests when the Home Assistant pytest plugin is unavailable."""
    if find_spec("pytest_homeassistant_custom_component") is not None:
        return

    skip = pytest.mark.skip(
        reason="HA-backed tests require pytest-homeassistant-custom-component"
    )
    for item in items:
        if item.path.name in HA_BACKED_TEST_FILES:
            item.add_marker(skip)


def _remove_collection_stubs() -> None:
    """Clear stub modules that were installed only to import pure helpers."""
    if find_spec("pytest_homeassistant_custom_component") is None:
        return

    for name, module in list(sys.modules.items()):
        if _is_collection_stub(name, module):
            _restore_original_module(name)


def _is_collection_stub(name: str, module: ModuleType) -> bool:
    """Return whether a module is one of the local import-time stubs."""
    if name == "custom_components":
        return _has_no_file(module)
    if name.startswith("custom_components.unifi_unas"):
        return True
    if name in {"aiohttp", "voluptuous"}:
        return _has_no_file(module)
    if name == "homeassistant" or name.startswith("homeassistant."):
        return _has_no_file(module)
    return False


def _has_no_file(module: ModuleType) -> bool:
    """Return whether a module looks like a hand-built ModuleType stub."""
    return getattr(module, "__file__", None) is None


def _restore_original_module(name: str) -> None:
    """Restore the module object that existed before test collection."""
    original = _ORIGINAL_MODULES.get(name, _MISSING)
    if original is _MISSING:
        sys.modules.pop(name, None)
    else:
        sys.modules[name] = original


def _prime_homeassistant_plugin_modules() -> None:
    """Import HA modules that pytest-homeassistant patches by dotted path."""
    try:
        import homeassistant.helpers.aiohttp_client
        import homeassistant.util.logging
    except ModuleNotFoundError:
        return

    _bind_parent_modules("homeassistant.helpers.aiohttp_client")
    _bind_parent_modules("homeassistant.util.logging")


def _bind_parent_modules(module_name: str) -> None:
    """Expose imported submodules as attributes on their parent packages."""
    parts = module_name.split(".")
    for index in range(1, len(parts)):
        parent_name = ".".join(parts[:index])
        child_name = ".".join(parts[: index + 1])
        parent = sys.modules.get(parent_name)
        child = sys.modules.get(child_name)
        if parent is not None and child is not None:
            setattr(parent, parts[index], child)
