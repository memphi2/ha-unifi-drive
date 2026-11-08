"""Load Home Assistant before plugins import libraries it needs to alias."""

from importlib.util import find_spec

if find_spec("homeassistant") is not None:
    import homeassistant  # noqa: F401
