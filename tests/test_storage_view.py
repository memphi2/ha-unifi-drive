"""Regression checks for bounded per-refresh normalization."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tests.storage_fixtures import multi_pool_storage


@pytest.mark.parametrize("drive_count", [4, 7, 8])
@pytest.mark.parametrize("nested", [False, True], ids=["global", "pool-local"])
def test_multi_pool_layout_keeps_data_and_cache_identity_separate(drive_count, nested):
    """Exercise invented layouts without treating them as real-model fixtures."""
    from custom_components.unifi_unas import storage_view as module

    payload = multi_pool_storage(drive_count, nested=nested)
    coordinator = SimpleNamespace(data=payload)
    with patch.object(module, "_pool_drives", wraps=module._pool_drives) as normalize:
        view = module.storage_view(coordinator)
        for _ in range(10):
            for index, pool in enumerate(view.pools):
                members = view.drives(pool)
                assert {disk["id"] for disk in members} == {
                    f"disk-{slot}" for slot in range(index, drive_count, 2)
                }
                assert all(disk["poolId"] == pool["id"] for disk in members)
        assert normalize.call_count == 2
        assert len(view._drives) == 2
        assert set(view.cache_drives) == {"id_disk_0", "id_disk_1"}
        assert sum(len(view.drives(pool)) for pool in view.pools) == drive_count


def test_multi_pool_layout_does_not_guess_membership_for_extra_global_disks():
    """Spare, unassigned, empty and foreign-pool disks cannot fill another pool."""
    from custom_components.unifi_unas.storage_view import StorageView

    payload = multi_pool_storage()
    payload["disks"].extend([
        {"id": "spare", "isHotSpare": True},
        {"id": "unassigned", "temperature": 32},
        {"slotId": 9, "state": "empty"},
        {"id": "foreign", "poolId": "another-pool", "temperature": 32},
    ])
    view = StorageView(payload)
    assert [len(view.drives(pool)) for pool in view.pools] == [4, 4]


def test_storage_view_reuses_normalization_and_preserves_legacy_lookup():
    from custom_components.unifi_unas import storage_view as module

    payload = {"pools": [{"id": "pool-a", "name": "Primary", "drives": [
        {"serial": "drive-a", "temperature": 31},
    ]}]}
    coordinator = SimpleNamespace(data=payload)
    with patch.object(module, "_pool_drives", wraps=module._pool_drives) as normalize:
        view = module.storage_view(coordinator)
        pool = view.pool("pool_a")
        assert pool is view.pool("Primary")
        assert pool is view.pool("pool_1")
        assert pool is not None
        for _ in range(72):
            assert module.storage_view(coordinator) is view
            assert view.drives(pool)[0]["temperature"] == 31
        assert normalize.call_count == 1
        assert len(view._drives) == 1
        assert view.pool("missing") is None

    assert "__global_disks" not in payload["pools"][0]
    coordinator.data = {"pools": []}
    replacement = module.storage_view(coordinator)
    assert replacement is not view
    assert replacement.pool("pool_a") is None
    assert replacement._drives == {}


def test_storage_view_explicit_invalidation_handles_in_place_updates():
    from custom_components.unifi_unas.storage_view import storage_view

    coordinator = SimpleNamespace(data={"pools": []})
    previous = storage_view(coordinator)
    coordinator.data["pools"].append({"id": "new-pool"})
    coordinator._storage_view = None
    assert storage_view(coordinator) is not previous
    assert storage_view(coordinator).pool("new_pool") is not None
