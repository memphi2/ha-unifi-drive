"""Validation compatibility layer for Home Assistant schema helpers."""

from __future__ import annotations

import re
from importlib import import_module
from types import ModuleType
from typing import Any

PROBATIO_HOMEASSISTANT_VERSION = (2026, 10)


def _load_validation_module() -> ModuleType:
    """Return the Home Assistant validation engine available at runtime."""
    if _homeassistant_uses_probatio():
        return import_module("probatio")

    try:
        return import_module("voluptuous")
    except ModuleNotFoundError:
        return import_module("probatio")


def _homeassistant_uses_probatio() -> bool:
    """Return whether the running Home Assistant version uses Probatio."""
    version = _homeassistant_version()
    return version is not None and version >= PROBATIO_HOMEASSISTANT_VERSION


def _homeassistant_version() -> tuple[int, int] | None:
    """Return the running Home Assistant major/minor version."""
    try:
        ha_const = import_module("homeassistant.const")
    except ModuleNotFoundError:
        return None

    version = getattr(ha_const, "__version__", None)
    if not isinstance(version, str):
        return None

    match = re.match(r"^(\d{4})\.(\d+)", version)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


_validation = _load_validation_module()

All: Any = _validation.All
Coerce: Any = _validation.Coerce
In: Any = _validation.In
Invalid: Any = _validation.Invalid
Optional: Any = _validation.Optional
Range: Any = _validation.Range
Required: Any = _validation.Required
Schema: Any = _validation.Schema
