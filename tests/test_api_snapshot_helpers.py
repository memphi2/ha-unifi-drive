"""Unit tests for UniFi Drive snapshot API helper logic."""

import asyncio

import pytest

from tests.api_client_stubs import (
    SnapshotStatusClient,
    SnapshotWriteClient,
    UnifiUnasApiClient,
    api_snapshot_module,
)


class SnapshotAuthRetryClient(SnapshotWriteClient):
    """Fake snapshot client that fails one wrapper call with InvalidAuth."""

    def __init__(self) -> None:
        super().__init__()
        self._authenticated = True
        self._login_data = {"id": "current-user"}
        self.login_count = 0
        self.fail_once = True

    async def async_login(self) -> None:
        self.login_count += 1
        self._authenticated = True


def test_extract_snapshot_settings_from_section_payload() -> None:
    """Snapshot settings should expose My Drive and shared-drive targets."""
    payload = {
        "data": {
            "personal": [
                {
                    "user": {"id": "other-user", "username": "Other"},
                    "maxCount": 8,
                },
                {
                    "user": {"id": "current-user", "username": "Current User"},
                    "maxCount": 12,
                    "totalCount": 3,
                    "lockedCount": 1,
                    "schedule": {"enable": True},
                },
            ],
            "shared": [
                {
                    "sharedDrive": {"id": "shared-1", "name": "Team"},
                    "enabled": True,
                    "max_count": "20",
                    "total_count": "4",
                }
            ],
        }
    }

    settings = UnifiUnasApiClient._extract_snapshot_settings(
        payload,
        current_user_id="current-user",
    )

    assert settings == [
        {
            "id": "other-user",
            "name": "Other",
            "type": "mydrive",
            "user_id": "other-user",
            "is_current_user": False,
            "shared_drive_name": None,
            "enabled": True,
            "max_count": 8,
            "total_count": None,
            "locked_count": None,
            "paused": False,
            "restoring_drive": False,
            "schedule_enabled": False,
            "schedule_frequency": "Never",
            "schedule_time": None,
            "schedule_weekdays": None,
            "schedule_monthdays": None,
        },
        {
            "id": "current-user",
            "name": "Current User",
            "type": "mydrive",
            "user_id": "current-user",
            "is_current_user": True,
            "shared_drive_name": None,
            "enabled": True,
            "max_count": 12,
            "total_count": 3,
            "locked_count": 1,
            "paused": False,
            "restoring_drive": False,
            "schedule_enabled": True,
            "schedule_frequency": "Daily",
            "schedule_time": None,
            "schedule_weekdays": None,
            "schedule_monthdays": None,
        },
        {
            "id": "shared-1",
            "name": "Team",
            "type": "shared",
            "user_id": None,
            "is_current_user": False,
            "shared_drive_name": "Team",
            "enabled": True,
            "max_count": 20,
            "total_count": 4,
            "locked_count": None,
            "paused": False,
            "restoring_drive": False,
            "schedule_enabled": False,
            "schedule_frequency": "Never",
            "schedule_time": None,
            "schedule_weekdays": None,
            "schedule_monthdays": None,
        },
    ]


def test_snapshot_schedule_helpers_cover_unknown_and_disabled_values() -> None:
    """Schedule helpers should preserve unknown API values and disabled states."""
    assert api_snapshot_module._snapshot_schedule_api_value("custom") == "custom"
    assert api_snapshot_module._snapshot_schedule_option("daily") == "Daily"
    assert api_snapshot_module._snapshot_schedule_option("custom") == "custom"
    assert api_snapshot_module._snapshot_schedule_option(None) is None

    assert api_snapshot_module._snapshot_schedule_frequency({}, False) == "Never"
    assert (
        api_snapshot_module._snapshot_schedule_frequency(
            {"frequency": "weekly"},
            True,
        )
        == "Weekly"
    )
    assert api_snapshot_module._snapshot_schedule_frequency({"interval": 60}, None) == "Daily"
    assert api_snapshot_module._snapshot_schedule_frequency({}, None) == "Never"


def test_snapshot_schedule_days_rejects_invalid_user_values() -> None:
    """Schedule write helpers should reject invalid day selector values."""
    assert (
        api_snapshot_module._snapshot_schedule_days("1, 2, 2", minimum=1, maximum=31)
        == "1,2"
    )
    assert api_snapshot_module._snapshot_schedule_days(None, minimum=1, maximum=31) is None

    with pytest.raises(ValueError, match="between 1 and 31"):
        api_snapshot_module._snapshot_schedule_days("0", minimum=1, maximum=31)

    with pytest.raises(ValueError, match="between 1 and 31"):
        api_snapshot_module._snapshot_schedule_days("bad", minimum=1, maximum=31)

    with pytest.raises(ValueError, match="between 1 and 31"):
        api_snapshot_module._snapshot_schedule_days("", minimum=1, maximum=31)


def test_extract_snapshot_settings_from_list_payload() -> None:
    """List-shaped snapshot payloads should be normalized defensively."""
    payload = {
        "data": [
            {
                "type": "personal",
                "user_id": "list-user",
                "name": "My Drive",
                "enable": "true",
                "paused": "false",
                "restoring_drive": "0",
            },
            {
                "target_type": "shared_drive",
                "shared_drive_id": "shared-2",
                "shared_drive_name": "Archive",
                "enabled": "false",
            },
        ]
    }

    settings = UnifiUnasApiClient._extract_snapshot_settings(payload)

    assert [setting["type"] for setting in settings] == ["mydrive", "shared"]
    assert settings[0]["enabled"] is True
    assert settings[0]["id"] == "list-user"
    assert settings[0]["name"] == "My Drive"
    assert settings[1]["id"] == "shared-2"
    assert settings[1]["shared_drive_name"] == "Archive"
    assert settings[1]["enabled"] is False


def test_extract_snapshot_settings_skips_personal_targets_without_stable_id() -> None:
    """Personal snapshot targets without stable IDs should not create entities."""
    payload = {
        "data": {
            "personal": [
                {"user": {"username": "Missing Id"}, "maxCount": 8},
                {"name": "List Personal", "type": "personal", "maxCount": 4},
            ],
            "shared": [],
        }
    }

    assert UnifiUnasApiClient._extract_snapshot_settings(payload) == []


def test_extract_snapshot_settings_preserves_list_personal_item_ids() -> None:
    """List-shaped personal targets should use per-item IDs when user IDs are absent."""
    payload = {
        "data": [
            {
                "type": "personal",
                "id": "personal-1",
                "name": "One",
                "maxCount": 8,
            },
            {
                "type": "personal",
                "id": "personal-2",
                "name": "Two",
                "maxCount": 4,
            },
        ]
    }

    settings = UnifiUnasApiClient._extract_snapshot_settings(payload)

    assert [setting["id"] for setting in settings] == ["personal-1", "personal-2"]


def test_extract_snapshot_settings_accepts_top_level_sections() -> None:
    """Snapshot settings may be returned without a data wrapper."""
    payload = {
        "personal": [
            {
                "user": {"id": "current-user", "username": "Current User"},
                "maxCount": 2,
            }
        ],
        "shared": [],
    }

    settings = UnifiUnasApiClient._extract_snapshot_settings(
        payload,
        current_user_id="current-user",
    )

    assert len(settings) == 1
    assert settings[0]["type"] == "mydrive"
    assert settings[0]["enabled"] is True


def test_extract_snapshot_settings_prefers_personal_drive_full_name() -> None:
    """Personal snapshot targets should use the user's display name when present."""
    payload = {
        "data": {
            "personal": [
                {
                    "user": {
                        "id": "backup-user",
                        "username": "backup_user",
                        "firstName": "Backup",
                        "lastName": "User",
                    },
                    "maxCount": 2,
                }
            ],
            "shared": [],
        }
    }

    settings = UnifiUnasApiClient._extract_snapshot_settings(payload)

    assert settings[0]["name"] == "Backup User"


def test_snapshot_settings_write_body_uses_unifi_shape() -> None:
    """Snapshot settings writes should use the observed UniFi payload shape."""
    target = {
        "id": "user-1",
        "type": "mydrive",
        "name": "backup_user",
        "user_id": "user-1",
        "enabled": False,
        "max_count": 0,
        "schedule_frequency": "Never",
        "schedule_time": None,
    }

    body = api_snapshot_module._snapshot_settings_write_body(
        target,
        enabled=True,
        max_count=2,
        schedule_enabled=None,
        schedule_frequency="Never",
        schedule_time=None,
    )

    assert body == {
        "name": "",
        "enabled": True,
        "maxSnapshots": 2,
        "schedule": {
            "interval": 60,
            "weekdays": "*",
            "monthdays": "",
            "enable": False,
            "firstRunTime": "0:00",
            "lastRunTime": "0:00",
        },
    }


def test_snapshot_settings_write_body_keeps_name_empty_for_shared_targets() -> None:
    """Shared-drive writes should address the target in the URL, not the body."""
    target = {
        "id": "shared-id",
        "type": "shared",
        "name": "Shared_Drive",
        "shared_drive_name": "Shared_Drive",
        "enabled": False,
        "max_count": 0,
        "schedule_frequency": "Never",
        "schedule_time": "00:00",
    }

    body = api_snapshot_module._snapshot_settings_write_body(
        target,
        enabled=True,
        max_count=64,
        schedule_enabled=None,
        schedule_frequency="Daily",
        schedule_time="00:00",
    )

    assert body["name"] == ""
    assert body["enabled"] is True
    assert body["maxSnapshots"] == 64
    assert body["schedule"]["enable"] is True


def test_snapshot_schedule_supports_weekly_and_monthly_payloads() -> None:
    """Weekly and monthly options should map to UniFi weekday/monthday fields."""
    target = {
        "id": "shared-id",
        "type": "shared",
        "enabled": True,
        "max_count": 64,
        "schedule_time": "12:30",
    }

    weekly = api_snapshot_module._snapshot_settings_write_body(
        target,
        enabled=None,
        max_count=None,
        schedule_enabled=None,
        schedule_frequency="Weekly",
        schedule_time=None,
    )
    monthly = api_snapshot_module._snapshot_settings_write_body(
        target,
        enabled=None,
        max_count=None,
        schedule_enabled=None,
        schedule_frequency="Monthly",
        schedule_time=None,
    )

    assert weekly["schedule"] == {
        "interval": 60,
        "weekdays": "1",
        "monthdays": "",
        "enable": True,
        "firstRunTime": "12:30",
        "lastRunTime": "12:30",
    }
    assert monthly["schedule"] == {
        "interval": 60,
        "weekdays": "",
        "monthdays": "1",
        "enable": True,
        "firstRunTime": "12:30",
        "lastRunTime": "12:30",
    }


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("00:00", (0, 0)),
        ("7:5", (7, 5)),
        ("07:05:00", (7, 5)),
        ("12:30 pm", (12, 30)),
        ("12:30pm", (12, 30)),
        ("12:30:00 PM", (12, 30)),
        ("12:00 am", (0, 0)),
        ("11:59 pm", (23, 59)),
    ],
)
def test_snapshot_schedule_time_parts_accepts_payload_variants(
    raw: str,
    expected: tuple[int, int],
) -> None:
    """A small matrix should accept common schedule time payload strings."""
    assert api_snapshot_module._schedule_time_parts(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", "bad", "12", "12:60", "24:00", "12 am", "01:xx", "13:00 pm", "07:05:xx"],
)
def test_snapshot_schedule_time_parts_rejects_invalid_payload_variants(raw: str) -> None:
    """Invalid or truncated schedule strings should fail fast."""
    try:
        api_snapshot_module._schedule_time_parts(raw)
    except ValueError:
        return
    raise AssertionError(f"invalid schedule time should raise ValueError: {raw!r}")


@pytest.mark.parametrize(
    ("raw", "minimum", "maximum", "expected"),
    [
        ("2,8,bad,2", 0, 6, 2),
        ("0,32,13,bad,13", 1, 31, 13),
        ("*,bad", 0, 6, None),
    ],
)
def test_snapshot_first_schedule_day_returns_first_valid_value(
    raw: str,
    minimum: int,
    maximum: int,
    expected: int | None,
) -> None:
    """Day selectors should share the same sanitized first-day parser."""
    assert (
        api_snapshot_module._snapshot_first_schedule_day(
            raw,
            minimum=minimum,
            maximum=maximum,
        )
        == expected
    )


def test_snapshot_schedule_preserves_weekly_and_monthly_selectors() -> None:
    """Existing UniFi weekday/monthday lists should survive frequency writes."""
    weekly_target = {
        "id": "shared-id",
        "type": "shared",
        "enabled": True,
        "max_count": 64,
        "schedule_time": "00:00",
        "schedule_weekdays": "2,0,1,6",
    }
    monthly_target = {
        "id": "shared-id",
        "type": "shared",
        "enabled": True,
        "max_count": 64,
        "schedule_time": "00:00",
        "schedule_monthdays": "2,13",
    }

    weekly = api_snapshot_module._snapshot_settings_write_body(
        weekly_target,
        enabled=None,
        max_count=None,
        schedule_enabled=None,
        schedule_frequency="Weekly",
        schedule_time=None,
    )
    monthly = api_snapshot_module._snapshot_settings_write_body(
        monthly_target,
        enabled=None,
        max_count=None,
        schedule_enabled=None,
        schedule_frequency="Monthly",
        schedule_time=None,
    )

    assert weekly["schedule"]["weekdays"] == "2,0,1,6"
    assert weekly["schedule"]["monthdays"] == ""
    assert monthly["schedule"]["weekdays"] == ""
    assert monthly["schedule"]["monthdays"] == "2,13"


def test_snapshot_schedule_sanitizes_existing_day_selectors() -> None:
    """Malformed stored day lists should not be echoed back into write payloads."""
    weekly_target = {
        "id": "shared-id",
        "type": "shared",
        "enabled": True,
        "max_count": 64,
        "schedule_time": "00:00",
        "schedule_weekdays": "2,8,bad,2",
    }
    monthly_target = {
        "id": "shared-id",
        "type": "shared",
        "enabled": True,
        "max_count": 64,
        "schedule_time": "00:00",
        "schedule_monthdays": "0,32,13,bad,13",
    }

    weekly = api_snapshot_module._snapshot_settings_write_body(
        weekly_target,
        enabled=None,
        max_count=None,
        schedule_enabled=None,
        schedule_frequency="Weekly",
        schedule_time=None,
    )
    monthly = api_snapshot_module._snapshot_settings_write_body(
        monthly_target,
        enabled=None,
        max_count=None,
        schedule_enabled=None,
        schedule_frequency="Monthly",
        schedule_time=None,
    )

    assert weekly["schedule"]["weekdays"] == "2"
    assert monthly["schedule"]["monthdays"] == "13"


def test_snapshot_schedule_write_body_falls_back_from_invalid_existing_time() -> None:
    """Malformed stored times should not block unrelated schedule writes."""
    target = {
        "id": "shared-id",
        "type": "shared",
        "enabled": True,
        "max_count": 64,
        "schedule_frequency": "Daily",
        "schedule_time": "bad",
    }

    body = api_snapshot_module._snapshot_settings_write_body(
        target,
        enabled=None,
        max_count=None,
        schedule_enabled=None,
        schedule_frequency="Never",
        schedule_time=None,
    )

    assert body["schedule"]["firstRunTime"] == "0:00"
    assert body["schedule"]["lastRunTime"] == "0:00"


def test_snapshot_schedule_detects_weekly_and_monthly_payloads() -> None:
    """Read payloads should expose Weekly and Monthly schedule options."""
    payload = {
        "data": {
            "personal": [],
            "shared": [
                {
                    "sharedDrive": {"id": "weekly", "name": "Weekly"},
                    "maxCount": 64,
                    "schedule": {
                        "enable": True,
                        "interval": 60,
                        "weekdays": "1",
                        "monthdays": "",
                    },
                },
                {
                    "sharedDrive": {"id": "monthly", "name": "Monthly"},
                    "maxCount": 64,
                    "schedule": {
                        "enable": True,
                        "interval": 60,
                        "weekdays": "",
                        "monthdays": "1",
                    },
                },
            ],
        }
    }

    settings = UnifiUnasApiClient._extract_snapshot_settings(payload)

    assert [setting["schedule_frequency"] for setting in settings] == [
        "Weekly",
        "Monthly",
    ]
    assert settings[0]["schedule_weekdays"] == "1"
    assert settings[1]["schedule_monthdays"] == "1"


@pytest.mark.parametrize(
    ("schedule", "expected"),
    [
        ({"firstRunTime": "12:30"}, "12:30"),
        ({"time": "07:05:00"}, "07:05"),
        ({"start_time": "5:9"}, "05:09"),
        ({"hour": "7", "minute": "9"}, "07:09"),
        ({"hour": "23", "minute": 59}, "23:59"),
        ({}, None),
        ({"firstRunTime": "bad"}, None),
        ({"firstRunTime": "24:00"}, None),
        ({"hour": 7, "minute": 99}, None),
    ],
)
def test_snapshot_schedule_time_payload_matrix(
    schedule: dict[str, object],
    expected: str | None,
) -> None:
    """Normalize varying API schedule payload shapes into HH:MM or None."""
    assert api_snapshot_module._snapshot_schedule_time(schedule) == expected


def test_snapshot_settings_delete_only_when_turning_off_without_other_changes() -> None:
    """Switch-off should mirror the UI DELETE, while Never remains a PUT setting."""
    assert api_snapshot_module._snapshot_settings_delete_required(
        enabled=False,
        max_count=None,
        schedule_enabled=None,
        schedule_frequency=None,
        schedule_time=None,
    )
    assert not api_snapshot_module._snapshot_settings_delete_required(
        enabled=True,
        max_count=None,
        schedule_enabled=None,
        schedule_frequency="Never",
        schedule_time=None,
    )


def test_snapshot_settings_turn_off_uses_delete_route() -> None:
    """Turning snapshots off should use the UniFi UI's DELETE endpoint."""
    client = SnapshotWriteClient()
    target = {
        "id": "shared-id",
        "type": "shared",
        "shared_drive_name": "Shared_Drive",
        "enabled": True,
        "max_count": 64,
    }

    asyncio.run(
        client._async_update_snapshot_target_settings_once(
            target,
            enabled=False,
            max_count=None,
            schedule_enabled=None,
            schedule_frequency=None,
            schedule_time=None,
            schedule_weekdays=None,
            schedule_monthdays=None,
        )
    )

    assert client.calls == [
        (
            "DELETE",
            "/proxy/drive/api/v1/snapshot-settings/shared/Shared_Drive",
            None,
        )
    ]


def test_snapshot_settings_delete_405_falls_back_to_put_without_disabling_writes() -> None:
    """DELETE 405 should not mark snapshot settings writes unsupported globally."""
    client = SnapshotWriteClient()
    client.responses = [
        (405, {"error": "Method Not Allowed"}),
        (200, {"data": "OK"}),
    ]
    target = {
        "id": "user-1",
        "type": "mydrive",
        "user_id": "user-1",
        "enabled": True,
        "max_count": 2,
    }

    asyncio.run(
        client._async_update_snapshot_target_settings_once(
            target,
            enabled=False,
            max_count=None,
            schedule_enabled=None,
            schedule_frequency=None,
            schedule_time=None,
            schedule_weekdays=None,
            schedule_monthdays=None,
        )
    )

    assert client._snapshot_settings_write_supported is True
    assert [call[0] for call in client.calls] == ["DELETE", "PUT"]
    assert client.calls[1][1] == (
        "/proxy/drive/api/v1/snapshot-settings/personal/user-1"
    )
    assert client.calls[1][2]["enabled"] is False


def test_snapshot_settings_write_support_is_tracked_per_target_type() -> None:
    """A shared write miss should not block a later personal write attempt."""
    client = SnapshotWriteClient()
    shared_target = {
        "id": "shared-id",
        "type": "shared",
        "enabled": True,
        "max_count": 64,
    }
    personal_target = {
        "id": "user-1",
        "type": "mydrive",
        "user_id": "user-1",
        "enabled": True,
        "max_count": 2,
    }

    client.responses = [(405, {"error": "Method Not Allowed"})]
    with pytest.raises(api_snapshot_module.UnsupportedFeature):
        asyncio.run(
            client._async_update_snapshot_target_settings_once(
                shared_target,
                enabled=True,
                max_count=None,
                schedule_enabled=None,
                schedule_frequency=None,
                schedule_time=None,
                schedule_weekdays=None,
                schedule_monthdays=None,
            )
        )

    assert client.snapshot_settings_write_supported is None
    assert client.snapshot_settings_write_supported_by_type == {"shared": False}

    client.responses = [(200, {"data": "OK"})]
    asyncio.run(
        client._async_update_snapshot_target_settings_once(
            personal_target,
            enabled=True,
            max_count=None,
            schedule_enabled=None,
            schedule_frequency=None,
            schedule_time=None,
            schedule_weekdays=None,
            schedule_monthdays=None,
        )
    )

    assert client.snapshot_settings_write_supported is True
    assert client.snapshot_settings_write_supported_by_type == {
        "mydrive": True,
        "shared": False,
    }


def test_snapshot_settings_never_schedule_uses_put_route() -> None:
    """Selecting Never should update the schedule without disabling snapshots."""
    client = SnapshotWriteClient()
    target = {
        "id": "user-1",
        "type": "mydrive",
        "user_id": "user-1",
        "enabled": True,
        "max_count": 2,
        "schedule_frequency": "Daily",
        "schedule_time": "00:00",
    }

    asyncio.run(
        client._async_update_snapshot_target_settings_once(
            target,
            enabled=None,
            max_count=None,
            schedule_enabled=None,
            schedule_frequency="Never",
            schedule_time=None,
            schedule_weekdays=None,
            schedule_monthdays=None,
        )
    )

    assert client.calls[0][0] == "PUT"
    assert client.calls[0][1] == (
        "/proxy/drive/api/v1/snapshot-settings/personal/user-1"
    )
    assert client.calls[0][2]["enabled"] is True
    assert client.calls[0][2]["schedule"]["enable"] is False


def test_snapshot_settings_write_paths_use_personal_id_and_shared_name_first() -> None:
    """Personal targets write by user id; shared targets prefer Drive name."""
    personal = {
        "id": "user-1",
        "type": "mydrive",
        "user_id": "user-1",
    }
    shared = {
        "id": "shared-id",
        "type": "shared",
        "shared_drive_name": "Shared_Drive",
    }

    assert api_snapshot_module._snapshot_settings_write_paths(personal) == (
        "/proxy/drive/api/v1/snapshot-settings/personal/user-1",
    )
    assert api_snapshot_module._snapshot_settings_write_paths(shared) == (
        "/proxy/drive/api/v1/snapshot-settings/shared/Shared_Drive",
        "/proxy/drive/api/v1/snapshot-settings/shared/shared-id",
    )


def test_snapshot_settings_write_paths_raise_for_invalid_target_type() -> None:
    """Invalid target objects should fail with a deterministic UnexpectedResponse."""
    with pytest.raises(api_snapshot_module.UnexpectedResponse) as err:
        api_snapshot_module._snapshot_settings_write_paths("not-a-target")
    assert "Snapshot target type is missing" in str(err.value)

    with pytest.raises(api_snapshot_module.UnexpectedResponse) as err:
        api_snapshot_module._snapshot_create_paths({})
    assert "Snapshot target type is missing" in str(err.value)

    with pytest.raises(api_snapshot_module.UnexpectedResponse) as err:
        api_snapshot_module._snapshot_create_paths({"type": "mydrive"})
    assert "Snapshot target id is missing" in str(err.value)

    with pytest.raises(api_snapshot_module.UnexpectedResponse) as err:
        api_snapshot_module._snapshot_inventory_paths("not-a-target")
    assert "Snapshot target type is missing" in str(err.value)


def test_snapshot_create_paths_use_target_identifiers() -> None:
    """Personal snapshots should use user ids; shared snapshots should prefer names."""
    personal = {
        "id": "user-1",
        "type": "mydrive",
        "user_id": "user-1",
    }
    personal_alias = {
        "id": "user-2",
        "type": "personal",
        "user_id": "user-2",
    }
    personal_mixed_case = {
        "id": "user-3",
        "type": "MY_DRIVE",
        "user_id": "user-3",
    }
    shared_with_name = {
        "id": "shared-id",
        "type": "shared",
        "shared_drive_name": "Team Drive",
    }
    shared_without_name = {
        "id": "shared-id",
        "type": "shared",
    }

    assert api_snapshot_module._snapshot_create_paths(personal) == (
        "/proxy/drive/api/v1/snapshots/personal/user-1",
    )
    assert api_snapshot_module._snapshot_create_paths(personal_alias) == (
        "/proxy/drive/api/v1/snapshots/personal/user-2",
    )
    assert api_snapshot_module._snapshot_create_paths(personal_mixed_case) == (
        "/proxy/drive/api/v1/snapshots/personal/user-3",
    )
    assert api_snapshot_module._snapshot_create_paths(shared_with_name) == (
        "/proxy/drive/api/v1/snapshots/shared/Team%20Drive",
        "/proxy/drive/api/v1/snapshots/shared/shared-id",
    )
    assert api_snapshot_module._snapshot_create_paths(shared_without_name) == (
        "/proxy/drive/api/v1/snapshots/shared/shared-id",
    )


def test_snapshot_create_target_calls_target_specific_api_route() -> None:
    """Creating a snapshot should route through the target-specific create API."""
    client = SnapshotWriteClient()
    target = {
        "id": "shared-id",
        "type": "shared",
        "shared_drive_name": "Team Drive",
        "enabled": True,
    }

    asyncio.run(
        client.async_create_snapshot_target(
            target,
            description="team snapshot",
            locked=True,
        )
    )

    assert client.calls == [
        (
            "POST",
            "/proxy/drive/api/v1/snapshots/shared/Team%20Drive",
            {"description": "team snapshot", "locked": True},
        )
    ]


def test_snapshot_create_shared_drive_validates_names_and_quotes_path() -> None:
    """Shared-drive snapshot helper should reject empty names and URL-quote paths."""
    client = SnapshotWriteClient()

    with pytest.raises(api_snapshot_module.UnexpectedResponse):
        asyncio.run(client.async_create_shared_drive_snapshot(" "))

    asyncio.run(
        client.async_create_shared_drive_snapshot(
            "Team Drive",
            description="manual",
            locked=True,
        )
    )

    assert client.calls == [
        (
            "POST",
            "/proxy/drive/api/v1/snapshots/shared/Team%20Drive",
            {"description": "manual", "locked": True},
        )
    ]


def test_snapshot_create_target_falls_back_to_second_path_on_405() -> None:
    """One failing shared create route should fall back to the id route."""
    client = SnapshotWriteClient()
    client.responses = [
        (405, {"error": "Method Not Allowed"}),
        (200, {"data": "OK"}),
    ]
    target = {
        "id": "shared-id",
        "type": "shared",
        "shared_drive_name": "Team Drive",
        "enabled": True,
    }

    asyncio.run(client.async_create_snapshot_target(target))

    assert [call[1] for call in client.calls] == [
        "/proxy/drive/api/v1/snapshots/shared/Team%20Drive",
        "/proxy/drive/api/v1/snapshots/shared/shared-id",
    ]


def test_snapshot_create_with_paths_raises_last_or_unconfigured_error() -> None:
    """Create routing should preserve the last unsupported feature error."""
    client = SnapshotWriteClient()
    client.responses = [(405, {"error": "Method Not Allowed"})]

    with pytest.raises(api_snapshot_module.UnsupportedFeature) as err:
        asyncio.run(
            client._async_create_snapshot_with_paths(
                ("/one", "/two"),
                {"description": "", "locked": False},
            )
        )
    assert "not available" in str(err.value)
    assert [call[1] for call in client.calls] == ["/one", "/two"]

    with pytest.raises(api_snapshot_module.UnsupportedFeature) as err:
        asyncio.run(
            client._async_create_snapshot_with_paths(
                (),
                {"description": "", "locked": False},
            )
        )
    assert "not configured" in str(err.value)


def test_snapshot_inventory_target_calls_target_specific_get_route() -> None:
    """Reading inventory should route through the target-specific snapshot API."""
    client = SnapshotWriteClient()
    client.responses = [
        (
            200,
            {
                "data": {
                    "items": [
                        {
                            "snapshotId": "snap-1",
                            "createdAt": "2026-05-16T12:00:00Z",
                            "locked": True,
                        }
                    ]
                }
            },
        )
    ]
    target = {
        "id": "shared-id",
        "type": "shared",
        "shared_drive_name": "Team Drive",
        "enabled": True,
    }

    inventory = asyncio.run(client.async_get_snapshot_inventory_target(target))

    assert client.calls == [
        (
            "GET",
            "/proxy/drive/api/v1/snapshots/shared/Team%20Drive",
            None,
        )
    ]
    assert inventory["snapshot_count"] == 1
    assert inventory["locked_count"] == 1
    assert inventory["latest_snapshot_id"] == "snap-1"


def test_snapshot_inventory_falls_back_to_second_path_on_405() -> None:
    """One failing shared inventory route should fall back to the id route."""
    client = SnapshotWriteClient()
    client.responses = [
        (405, {"error": "Method Not Allowed"}),
        (200, {"data": []}),
    ]
    target = {
        "id": "shared-id",
        "type": "shared",
        "shared_drive_name": "Team Drive",
        "enabled": True,
    }

    inventory = asyncio.run(client.async_get_snapshot_inventory_target(target))

    assert inventory["snapshot_count"] == 0
    assert [call[1] for call in client.calls] == [
        "/proxy/drive/api/v1/snapshots/shared/Team%20Drive",
        "/proxy/drive/api/v1/snapshots/shared/shared-id",
    ]


def test_snapshot_inventory_with_paths_raises_last_or_unconfigured_error() -> None:
    """Inventory routing should preserve the last unsupported feature error."""
    client = SnapshotWriteClient()
    client.responses = [(405, {"error": "Method Not Allowed"})]

    with pytest.raises(api_snapshot_module.UnsupportedFeature) as err:
        asyncio.run(client._async_get_snapshot_inventory_with_paths(("/one", "/two")))
    assert "not available" in str(err.value)
    assert [call[1] for call in client.calls] == ["/one", "/two"]

    with pytest.raises(api_snapshot_module.UnsupportedFeature) as err:
        asyncio.run(client._async_get_snapshot_inventory_with_paths(()))
    assert "not configured" in str(err.value)


def test_snapshot_inventory_support_is_tracked_per_target_type() -> None:
    """A shared inventory miss should not block a later personal read."""
    client = SnapshotWriteClient()
    shared_target = {
        "id": "shared-id",
        "type": "shared",
        "enabled": True,
    }
    personal_target = {
        "id": "user-1",
        "type": "mydrive",
        "user_id": "user-1",
        "enabled": True,
    }

    client.responses = [(405, {"error": "Method Not Allowed"})]
    with pytest.raises(api_snapshot_module.UnsupportedFeature):
        asyncio.run(client.async_get_snapshot_inventory_target(shared_target))

    assert client.snapshot_inventory_supported is None
    assert client.snapshot_inventory_supported_by_type == {"shared": False}

    client.responses = [(200, {"snapshots": [{"id": "snap-1"}]})]
    asyncio.run(client.async_get_snapshot_inventory_target(personal_target))

    assert client.snapshot_inventory_supported is True
    assert client.snapshot_inventory_supported_by_type == {
        "mydrive": True,
        "shared": False,
    }


def test_snapshot_inventory_type_cache_does_not_skip_later_targets() -> None:
    """One unsupported target should not suppress later same-type inventory reads."""
    client = SnapshotWriteClient()
    first_target = {
        "id": "shared-1",
        "type": "shared",
        "enabled": True,
    }
    second_target = {
        "id": "shared-2",
        "type": "shared",
        "enabled": True,
    }

    client.responses = [(405, {"error": "Method Not Allowed"})]
    with pytest.raises(api_snapshot_module.UnsupportedFeature):
        asyncio.run(client.async_get_snapshot_inventory_target(first_target))

    assert len(client.calls) == 1
    client.calls.clear()

    client.responses = [(200, {"snapshots": [{"id": "snap-1"}]})]
    inventory = asyncio.run(client.async_get_snapshot_inventory_target(second_target))

    assert inventory["snapshot_count"] == 1
    assert [call[1] for call in client.calls] == [
        "/proxy/drive/api/v1/snapshots/shared/shared-2"
    ]


def test_snapshot_create_support_is_tracked_per_target_type() -> None:
    """A shared create miss should not preclude a later personal create success."""
    client = SnapshotWriteClient()
    shared_target = {
        "id": "shared-id",
        "type": "shared",
        "enabled": True,
    }
    personal_target = {
        "id": "user-1",
        "type": "mydrive",
        "user_id": "user-1",
        "enabled": True,
    }

    client.responses = [(405, {"error": "Method Not Allowed"})]
    with pytest.raises(api_snapshot_module.UnsupportedFeature):
        asyncio.run(client.async_create_snapshot_target(shared_target))

    assert client.snapshot_create_supported is None
    assert client.snapshot_create_supported_by_type == {"shared": False}

    client.responses = [(200, {"data": "OK"})]
    asyncio.run(client.async_create_snapshot_target(personal_target))

    assert client.snapshot_create_supported is True
    assert client.snapshot_create_supported_by_type == {
        "mydrive": True,
        "shared": False,
    }


def test_snapshot_create_error_redacts_target_path_and_payload() -> None:
    """Snapshot endpoint errors should not expose target IDs, names or secrets."""
    client = SnapshotWriteClient()
    target = {
        "id": "shared-secret-id",
        "type": "shared",
        "shared_drive_name": "Team Secret",
        "enabled": True,
    }
    client.responses = [
        (
            500,
            {
                "host": "192.0.2.44",
                "token": "secret-token",
                "message": "Authorization: Bearer raw-token",
            },
        )
    ]

    with pytest.raises(api_snapshot_module.UnsupportedFeature) as err:
        asyncio.run(client.async_create_snapshot_target(target))

    message = str(err.value)
    assert "Team Secret" not in message
    assert "shared-secret-id" not in message
    assert "192.0.2.44" not in message
    assert "secret-token" not in message
    assert "raw-token" not in message


def test_snapshot_inventory_and_write_errors_are_sanitized() -> None:
    """Inventory and settings write errors should expose only safe API details."""
    client = SnapshotWriteClient()
    client.responses = [
        (500, {"token": "secret-token", "message": "Authorization: Bearer raw-token"})
    ]

    with pytest.raises(api_snapshot_module.UnsupportedFeature) as err:
        asyncio.run(client._async_get_snapshot_inventory_once("/inventory"))
    assert "secret-token" not in str(err.value)
    assert "raw-token" not in str(err.value)

    client = SnapshotWriteClient()
    client.responses = [
        (500, {"token": "secret-token", "message": "Authorization: Bearer raw-token"})
    ]
    with pytest.raises(api_snapshot_module.UnsupportedFeature) as err:
        asyncio.run(
            client._async_update_snapshot_target_settings_once(
                {"id": "user-1", "type": "mydrive", "user_id": "user-1"},
                enabled=True,
            )
        )
    assert "secret-token" not in str(err.value)
    assert "raw-token" not in str(err.value)


def test_snapshot_write_uses_update_object_and_respects_cached_unsupported_type() -> None:
    """Snapshot settings writes should accept update objects and honor type caches."""
    client = SnapshotWriteClient()
    client._snapshot_settings_write_supported_by_type = {"shared": False}

    with pytest.raises(api_snapshot_module.UnsupportedFeature):
        asyncio.run(
            client._async_update_snapshot_target_settings_once(
                {"id": "shared-1", "type": "shared"},
                api_snapshot_module.SnapshotSettingsUpdate(enabled=True),
            )
        )

    client = SnapshotWriteClient()
    update = api_snapshot_module.SnapshotSettingsUpdate(
        enabled=True,
        max_count=7,
        schedule_frequency="Daily",
        schedule_time="09:15",
    )
    asyncio.run(
        client._async_update_snapshot_target_settings_once(
            {"id": "user-1", "type": "mydrive", "user_id": "user-1"},
            update,
        )
    )

    assert client.calls[0][2]["maxSnapshots"] == 7
    assert client.calls[0][2]["schedule"]["firstRunTime"] == "9:15"


def test_snapshot_create_paths_requires_supported_target_type() -> None:
    """Creating snapshots for unsupported targets should fail fast."""
    with pytest.raises(api_snapshot_module.UnexpectedResponse):
        api_snapshot_module._snapshot_create_paths({"id": "x", "type": "unknown"})


def test_snapshot_settings_read_404_marks_endpoint_unsupported() -> None:
    """Snapshot read 404 should be handled without a missing-constant NameError."""
    client = SnapshotStatusClient(404)

    assert asyncio.run(client._async_get_snapshot_settings_once()) == []

    assert client._snapshot_settings_read_supported is False
    assert client.calls == [
        (
            "GET",
            "/proxy/drive/api/v1/systems/snapshot",
            None,
        )
    ]


def test_snapshot_settings_read_returns_targets_and_current_user() -> None:
    """Successful snapshot settings reads should set support and current-user flags."""
    client = SnapshotWriteClient()
    client._snapshot_settings_read_supported = None
    client._login_data = {"unique_id": "current-user"}
    client.responses = [
        (
            200,
            {
                "data": {
                    "personal": [
                        {
                            "user": {"id": "current-user", "username": "Current User"},
                            "maxCount": 2,
                        }
                    ],
                    "shared": [],
                }
            },
        )
    ]

    settings = asyncio.run(client._async_get_snapshot_settings_once())

    assert settings[0]["is_current_user"] is True
    assert client.snapshot_settings_read_supported is True


def test_snapshot_settings_read_distinguishes_empty_targets_from_server_errors() -> None:
    """Server failures must not be mistaken for a successful empty target list."""
    client = SnapshotWriteClient()
    client._snapshot_settings_read_supported = None
    client._login_data = {}
    client.responses = [(200, {"unexpected": "shape"})]
    assert asyncio.run(client._async_get_snapshot_settings_once()) == []
    assert client.snapshot_settings_read_supported is True

    client.responses = [(500, {"error": "server"})]
    with pytest.raises(api_snapshot_module.CannotConnect, match="HTTP 500"):
        asyncio.run(client._async_get_snapshot_settings_once())


def test_snapshot_wrapper_methods_retry_once_after_invalid_auth() -> None:
    """High-level snapshot wrappers should retry one expired session."""

    class RetrySettingsClient(SnapshotAuthRetryClient):
        async def _async_get_snapshot_settings_once(self):
            if self.fail_once:
                self.fail_once = False
                raise api_snapshot_module.InvalidAuth("expired")
            return [{"id": "target-1"}]

    client = RetrySettingsClient()
    assert asyncio.run(client.async_get_snapshot_settings()) == [{"id": "target-1"}]
    assert client.login_count == 1

    class RetryInventoryClient(SnapshotAuthRetryClient):
        async def _async_get_snapshot_inventory_with_paths(self, paths, *, target_type=None):
            if self.fail_once:
                self.fail_once = False
                raise api_snapshot_module.InvalidAuth("expired")
            return {"snapshot_count": 2}

    client = RetryInventoryClient()
    assert asyncio.run(
        client.async_get_snapshot_inventory_target(
            {"id": "shared-1", "type": "shared"}
        )
    ) == {"snapshot_count": 2}
    assert client.login_count == 1

    class RetryCreateClient(SnapshotAuthRetryClient):
        async def _async_create_snapshot_with_paths(self, path, payload, *, target_type=None):
            if self.fail_once:
                self.fail_once = False
                raise api_snapshot_module.InvalidAuth("expired")

    client = RetryCreateClient()
    asyncio.run(client.async_create_snapshot_target({"id": "user-1", "type": "mydrive"}))
    assert client.login_count == 1

    class RetryWriteClient(SnapshotAuthRetryClient):
        _snapshot_settings_lock = asyncio.Lock()

        async def async_get_snapshot_settings(self):
            return [{"id": "user-1", "type": "mydrive"}]

        async def _async_update_snapshot_target_settings_once(self, target, update):
            if self.fail_once:
                self.fail_once = False
                raise api_snapshot_module.InvalidAuth("expired")

    client = RetryWriteClient()
    asyncio.run(
        client.async_update_snapshot_target_settings(
            {"id": "user-1", "type": "mydrive"},
            enabled=True,
        )
    )
    assert client.login_count == 1


def test_snapshot_settings_serialize_and_merge_fresh_target_state() -> None:
    """Concurrent limit and schedule writes must preserve both changes."""
    from tests.api_client_stubs import UnifiUnasApiClient

    async def run():
        client = UnifiUnasApiClient(object(), host="console.example", api_key="test-key")
        current = {"id": "target-1", "type": "shared", "max_count": 10, "schedule_time": "01:00"}
        stale = dict(current)
        writes = []

        async def read():
            await asyncio.sleep(0)
            return [dict(current)]

        async def write(target, update):
            await asyncio.sleep(0)
            current.update(target)
            if update.max_count is not None:
                current["max_count"] = update.max_count
            if update.schedule_time is not None:
                current["schedule_time"] = update.schedule_time
            writes.append(dict(current))

        client.async_get_snapshot_settings = read
        client._async_update_snapshot_target_settings_once = write
        await asyncio.gather(
            client.async_update_snapshot_target_settings(stale, max_count=20),
            client.async_update_snapshot_target_settings(stale, schedule_time="02:00"),
        )
        assert current["max_count"] == 20
        assert current["schedule_time"] == "02:00"
        assert len(writes) == 2

        current["id"] = "replacement-target"
        with pytest.raises(api_snapshot_module.UnexpectedResponse, match="no longer available"):
            await client.async_update_snapshot_target_settings(stale, max_count=30)
        assert len(writes) == 2
        assert not client._snapshot_settings_lock.locked()

    asyncio.run(run())


def test_snapshot_create_405_marks_endpoint_unsupported() -> None:
    """Snapshot create 405 should be handled without a missing-constant NameError."""
    client = SnapshotStatusClient(405)

    try:
        asyncio.run(
            client._async_create_snapshot_once(
                "/proxy/drive/api/v1/snapshots/shared/Shared_Drive",
                {"description": "", "locked": False},
            )
        )
    except api_snapshot_module.UnsupportedFeature:
        pass
    else:
        raise AssertionError("405 should raise UnsupportedFeature")

    assert client._snapshot_create_supported is False


def test_snapshot_inventory_405_marks_endpoint_unsupported() -> None:
    """Snapshot inventory 405 should mark the endpoint unsupported."""
    client = SnapshotStatusClient(405)

    try:
        asyncio.run(
            client._async_get_snapshot_inventory_once(
                "/proxy/drive/api/v1/snapshots/shared/Shared_Drive",
            )
        )
    except api_snapshot_module.UnsupportedFeature:
        pass
    else:
        raise AssertionError("405 should raise UnsupportedFeature")

    assert client._snapshot_inventory_supported is False


def test_snapshot_capability_helpers_handle_missing_flags_and_unknown_user() -> None:
    """Capability and current-user helpers should tolerate older fake clients."""
    client = SnapshotWriteClient()
    del client._snapshot_create_supported_by_type

    client._set_snapshot_capability(
        "_snapshot_create_supported",
        "_snapshot_create_supported_by_type",
        "shared",
        True,
    )

    assert client.snapshot_create_supported is True
    assert client.snapshot_create_supported_by_type == {"shared": True}

    client._set_snapshot_capability(
        "_snapshot_create_supported",
        "_snapshot_create_supported_by_type",
        None,
        False,
    )
    assert client.snapshot_create_supported is False

    client._login_data = None
    assert client._current_user_id() is None
    client._login_data = {"id": ""}
    assert client._current_user_id() is None
