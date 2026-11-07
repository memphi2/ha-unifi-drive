"""Import HA fixtures lazily from the helper installed for the tested baseline."""

from importlib.util import find_spec

if find_spec("pytest_homeassistant") is not None:
    from pytest_homeassistant.common import MockConfigEntry as MockConfigEntry
else:
    from pytest_homeassistant_custom_component.common import MockConfigEntry as MockConfigEntry
