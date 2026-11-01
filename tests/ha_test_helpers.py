"""Shared namespace setup for real Home Assistant tests."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def ensure_repo_custom_components_path() -> None:
    """Extend HA's test namespace once without replacing its installed modules."""
    import custom_components

    path = str(ROOT / "custom_components")
    if not hasattr(custom_components, "__path__"):
        custom_components.__path__ = []
    if path not in custom_components.__path__:
        custom_components.__path__.append(path)
