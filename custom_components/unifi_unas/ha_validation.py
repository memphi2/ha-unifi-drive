"""Validation compatibility layer for Home Assistant schema helpers."""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import Any


def _load_validation_module() -> ModuleType:
    """Return the Home Assistant validation engine available at runtime."""
    try:
        return import_module("voluptuous")
    except ModuleNotFoundError:
        return import_module("probatio")


_validation = _load_validation_module()

All: Any = _validation.All
Coerce: Any = _validation.Coerce
In: Any = _validation.In
Invalid: Any = _validation.Invalid
Optional: Any = _validation.Optional
Range: Any = _validation.Range
Required: Any = _validation.Required
Schema: Any = _validation.Schema
