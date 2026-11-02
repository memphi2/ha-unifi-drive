"""Regression checks for bounded per-refresh normalization."""

from types import SimpleNamespace
from unittest.mock import patch


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
