"""Shared namespace setup for real Home Assistant tests."""

from pathlib import Path
from importlib.util import find_spec

ROOT = Path(__file__).resolve().parents[1]


def ha_test_plugin_available() -> bool:
    """Support official Core helpers and the legacy minimum-version package."""
    return any(find_spec(name) is not None for name in (
        "pytest_homeassistant", "pytest_homeassistant_custom_component",
    ))


def ensure_repo_custom_components_path() -> None:
    """Extend HA's test namespace once without replacing its installed modules."""
    import custom_components

    path = str(ROOT / "custom_components")
    if not hasattr(custom_components, "__path__"):
        custom_components.__path__ = []
    if path not in custom_components.__path__:
        custom_components.__path__.append(path)
