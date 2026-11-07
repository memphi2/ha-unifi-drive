"""Validated SMART values and stable SSD-cache identity."""

from importlib import import_module

import pytest
from tests.module_stubs import load_api_module

load_api_module()
drives = import_module("custom_components.unifi_unas.storage_drives")


@pytest.mark.parametrize("raw,expected", [
    (0, 0), (100, 100), ("92.5", 92.5), (101, None), (-1, None),
    (True, None), ("bad", None), ([], None), (float("inf"), None), (float("nan"), None),
])
def test_remaining_life_is_validated_without_clamping(raw, expected):
    assert drives._drive_remaining_life({"lifeSpan": raw}) == expected


@pytest.mark.parametrize("key,helper", [
    ("badSectorCount", drives._drive_bad_sectors),
    ("uncorrectableSectorCount", drives._drive_uncorrectable_sectors),
])
@pytest.mark.parametrize("raw,expected", [(0, 0), ("2", 2), (1.5, None), (-1, None), (True, None), (None, None)])
def test_sector_counts_are_integral_and_non_negative(key, helper, raw, expected):
    assert helper({key: raw}) == expected


def test_cache_slots_ignore_empty_anonymous_and_duplicate_drives():
    disk = {"id": "cache-a", "name": "Cache SSD", "lifeSpan": 95}
    payload = {"cacheSlots": [disk, dict(disk), {"slotId": 2, "state": "empty"},
                              {"id": "absent", "present": False}, {"name": "anonymous"}, None]}
    assert drives._cache_drives(payload) == [disk]
    renamed = {**disk, "name": "New label"}
    assert drives._cache_drive_key(renamed) == drives._cache_drive_key(disk)
    assert drives._cache_drive_key({"slotId": 0}) == "slotid_0"
    assert drives._cache_drives(None) == []
    assert drives._cache_drives({"cacheSlots": {}}) == []
