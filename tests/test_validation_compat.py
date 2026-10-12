"""Tests for Home Assistant validation engine compatibility."""

from __future__ import annotations

import importlib
import types

import pytest

from tests.module_stubs import ROOT, load_repo_module


def _stub_validation_module() -> types.ModuleType:
    """Return a minimal validation module stub."""
    module = types.ModuleType("validation_stub")
    for name in (
        "All",
        "Coerce",
        "In",
        "Invalid",
        "Optional",
        "Range",
        "Required",
        "Schema",
    ):
        setattr(module, name, object())
    return module


def _load_validation_module(module_name: str) -> types.ModuleType:
    """Load the validation compatibility module under an isolated name."""
    return load_repo_module(
        module_name,
        ROOT / "custom_components" / "unifi_unas" / "ha_validation.py",
    )


def test_validation_compat_prefers_voluptuous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The compatibility layer should prefer voluptuous without an HA hint."""
    voluptuous = _stub_validation_module()

    def import_module(name: str) -> types.ModuleType:
        if name == "homeassistant.const":
            raise ModuleNotFoundError(name)
        if name == "voluptuous":
            return voluptuous
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.setattr(importlib, "import_module", import_module)

    module = _load_validation_module("ha_validation_voluptuous_for_tests")

    assert module.Schema is voluptuous.Schema


def test_validation_compat_falls_back_to_probatio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The compatibility layer should use Probatio when voluptuous is absent."""
    probatio = _stub_validation_module()

    def import_module(name: str) -> types.ModuleType:
        if name == "homeassistant.const":
            raise ModuleNotFoundError(name)
        if name == "voluptuous":
            raise ModuleNotFoundError(name)
        if name == "probatio":
            return probatio
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.setattr(importlib, "import_module", import_module)

    module = _load_validation_module("ha_validation_probatio_for_tests")

    assert module.Schema is probatio.Schema


def test_validation_compat_uses_probatio_for_new_homeassistant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Home Assistant 2026.10+ should use Probatio even if voluptuous exists."""
    ha_const = types.ModuleType("homeassistant.const")
    ha_const.__version__ = "2026.10.0"
    probatio = _stub_validation_module()
    voluptuous = _stub_validation_module()

    def import_module(name: str) -> types.ModuleType:
        if name == "homeassistant.const":
            return ha_const
        if name == "probatio":
            return probatio
        if name == "voluptuous":
            return voluptuous
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.setattr(importlib, "import_module", import_module)

    module = _load_validation_module("ha_validation_new_ha_for_tests")

    assert module.Schema is probatio.Schema


def test_validation_compat_keeps_voluptuous_for_homeassistant_2026_9(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Home Assistant 2026.9 should keep voluptuous schemas."""
    ha_const = types.ModuleType("homeassistant.const")
    ha_const.__version__ = "2026.9.0"
    voluptuous = _stub_validation_module()

    def import_module(name: str) -> types.ModuleType:
        if name == "homeassistant.const":
            return ha_const
        if name == "voluptuous":
            return voluptuous
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.setattr(importlib, "import_module", import_module)

    module = _load_validation_module("ha_validation_2026_9_for_tests")

    assert module.Schema is voluptuous.Schema


def test_validation_compat_keeps_voluptuous_for_old_homeassistant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Older supported Home Assistant versions should keep voluptuous schemas."""
    ha_const = types.ModuleType("homeassistant.const")
    ha_const.__version__ = "2026.8.0"
    voluptuous = _stub_validation_module()

    def import_module(name: str) -> types.ModuleType:
        if name == "homeassistant.const":
            return ha_const
        if name == "voluptuous":
            return voluptuous
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.setattr(importlib, "import_module", import_module)

    module = _load_validation_module("ha_validation_old_ha_for_tests")

    assert module.Schema is voluptuous.Schema
