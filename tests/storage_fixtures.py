"""Invented storage layouts, not captured payloads or hardware support evidence."""

from __future__ import annotations

from typing import Any


def multi_pool_storage(drive_count: int = 8, *, nested: bool = False) -> dict[str, Any]:
    """Build two pools and two cache SSDs using already-supported payload fields.

    Cache and data disks deliberately share local IDs/slot numbers. The separate
    namespaces must prevent cache metrics from replacing pool-member readings.
    """
    pools = [
        {
            "id": f"pool-{letter}",
            "label": f"Synthetic pool {letter}",
            "status": "healthy",
            "capacity": 10 * 1024**4,
            "used": 4 * 1024**4,
        }
        for letter in ("a", "b")
    ]
    disks = [
        {
            "id": f"disk-{index}",
            "serial": f"synthetic-data-serial-{index}",
            "slotId": index,
            "poolId": pools[index % 2]["id"],
            "healthScore": 5,
            "temperature": 30 + index,
            "powerOnHours": 1200 + index,
            "badSectorCount": 0,
            "uncorrectableSectorCount": 0,
        }
        for index in range(drive_count)
    ]
    if nested:
        for pool in pools:
            pool["drives"] = [disk for disk in disks if disk["poolId"] == pool["id"]]
    return {
        "_system": {"status": "online"},
        "pools": pools,
        "disks": disks,
        "cacheSlots": [
            {
                "id": f"disk-{index}",
                "serial": f"synthetic-cache-serial-{index}",
                "slotId": index,
                "name": f"Synthetic cache {index}",
                "healthScore": 5,
                "temperature": 40 + index,
                "lifeSpan": 98 - index,
                "badSectorCount": 0,
                "uncorrectableSectorCount": 0,
            }
            for index in range(2)
        ],
    }
