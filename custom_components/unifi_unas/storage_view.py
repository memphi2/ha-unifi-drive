"""Bounded pool/drive normalization shared by entities for one refresh."""

from __future__ import annotations

from typing import Any

from .storage_drives import _cache_drive_key, _cache_drives, _pool_drives
from .storage_pools import _pool_from_key, _pools


class StorageView:
    """Keep only the current payload's normalized pools and requested drives."""

    def __init__(self, data: dict[str, Any] | None) -> None:
        self.data = data
        self.pools = _pools(data)
        self.cache_drives = {
            key: drive for drive in _cache_drives(data)
            if (key := _cache_drive_key(drive)) is not None
        }
        self._drives: dict[int, list[dict[str, Any]]] = {}

    def pool(self, key: str) -> dict[str, Any] | None:
        """Preserve canonical and legacy pool lookup behavior."""
        return _pool_from_key(None, key, pools=self.pools)[0]

    def drives(self, pool: dict[str, Any]) -> list[dict[str, Any]]:
        """Normalize each pool's drives only once within this view."""
        key = id(pool)
        if key not in self._drives:
            self._drives[key] = _pool_drives(pool)
        return self._drives[key]


def storage_view(coordinator: object) -> StorageView:
    """Return an owner-local cache, never a global payload cache."""
    data = getattr(coordinator, "data", None)
    view = getattr(coordinator, "_storage_view", None)
    if not isinstance(view, StorageView) or view.data is not data:
        view = StorageView(data)
        setattr(coordinator, "_storage_view", view)
    return view
