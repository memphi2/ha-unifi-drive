"""Snapshot operations for the UniFi Drive API client."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from .api_errors import CannotConnect, InvalidAuth, UnexpectedResponse, UnsupportedFeature
from .const import (
    DEFAULT_SNAPSHOT_LIMIT,
    MAX_SNAPSHOT_LIMIT,
    MIN_SNAPSHOT_LIMIT,
    SNAPSHOT_SCHEDULE_API_VALUES,
)
from .snapshot_paths import (
    PERSONAL_DRIVE_SNAPSHOTS_PATH,
    SHARED_DRIVE_SNAPSHOTS_PATH,
    SNAPSHOT_ENDPOINT_UNAVAILABLE_HTTP_STATUSES,
    SNAPSHOT_SETTING_PERSONAL_PATH,
    SNAPSHOT_SETTING_SHARED_PATH,
    SNAPSHOT_SETTINGS_PATH,
    _snapshot_create_paths,
    _snapshot_inventory_paths,
    _snapshot_settings_write_paths,
)
from .snapshot_inventory import extract_snapshot_inventory
from .security import safe_response_summary
# Re-export helper names from this legacy module path for tests and local callers.
from .snapshot_payload import (
    _extract_snapshot_settings_from_list,
    _personal_snapshot_identity,
    _snapshot_setting_from_item,
    _snapshot_target_is_current_user,
    _snapshot_target_type,
    _snapshot_target_type_normalized,
    _user_display_name,
    extract_snapshot_settings,
)
from .snapshot_schedule import (
    _schedule_time_parts,
    _snapshot_existing_schedule_days,
    _snapshot_first_schedule_day,
    _snapshot_schedule_api_value,
    _snapshot_schedule_days,
    _snapshot_schedule_first_run_time,
    _snapshot_schedule_frequency,
    _snapshot_schedule_monthdays,
    _snapshot_schedule_option,
    _snapshot_schedule_time,
    _snapshot_schedule_weekdays,
)
from .snapshot_types import normalize_snapshot_target_type, snapshot_target_key, snapshot_target_type
from .snapshot_values import (
    _bool_value,
    _dict_from_item,
    _first_bool_value,
    _first_int_value,
    _int_value,
    _payload_debug_shape,
    _value_from_dict,
)
from .snapshot_write import (
    SnapshotSettingsUpdate,
    _snapshot_settings_delete_required,
    _snapshot_settings_schedule_body,
    _snapshot_settings_write_body,
)

_LOGGER = logging.getLogger(__name__)
_SNAPSHOT_CAPABILITY_TARGET_TYPES = ("shared", "mydrive")


def _snapshot_capability_target_type(target_type: str | None) -> str | None:
    """Return the canonical target type used for capability tracking."""
    value = normalize_snapshot_target_type(target_type)
    return value or None


def _snapshot_capability_aggregate(flags: dict[str, bool]) -> bool | None:
    """Return a backwards-compatible aggregate for target-specific flags."""
    if any(value is True for value in flags.values()):
        return True
    if all(
        flags.get(target_type) is False
        for target_type in _SNAPSHOT_CAPABILITY_TARGET_TYPES
    ):
        return False
    return None


class ApiSnapshotMixin:
    """Snapshot behavior split from the main API client class."""

    _authenticated: bool
    _login_data: dict[str, Any] | None
    _snapshot_create_supported: bool | None
    _snapshot_create_supported_by_type: dict[str, bool]
    _snapshot_inventory_supported: bool | None
    _snapshot_inventory_supported_by_type: dict[str, bool]
    _snapshot_settings_read_supported: bool | None
    _snapshot_settings_lock: asyncio.Lock
    _snapshot_settings_write_supported: bool | None
    _snapshot_settings_write_supported_by_type: dict[str, bool]

    if TYPE_CHECKING:
        async def _ensure_authenticated(self) -> None: ...
        async def async_login(self) -> None: ...
        async def _request_raw(
            self,
            method: str,
            path: str,
            *,
            json_body: dict[str, Any] | None = None,
        ) -> tuple[int, Any]: ...

    @property
    def snapshot_settings_read_supported(self) -> bool | None:
        """Return whether snapshot settings are known to be readable."""
        return self._snapshot_settings_read_supported

    @property
    def snapshot_create_supported(self) -> bool | None:
        """Return whether manual snapshot creation is known to be supported."""
        return self._snapshot_create_supported

    @property
    def snapshot_create_supported_by_type(self) -> dict[str, bool]:
        """Return known manual snapshot creation support by target type."""
        return dict(self._snapshot_capability_flags("_snapshot_create_supported_by_type"))

    @property
    def snapshot_inventory_supported(self) -> bool | None:
        """Return whether snapshot inventory reads are known to be supported."""
        return self._snapshot_inventory_supported

    @property
    def snapshot_inventory_supported_by_type(self) -> dict[str, bool]:
        """Return known snapshot inventory read support by target type."""
        return dict(
            self._snapshot_capability_flags("_snapshot_inventory_supported_by_type")
        )

    @property
    def snapshot_settings_write_supported(self) -> bool | None:
        """Return whether snapshot settings are known to be writable."""
        return self._snapshot_settings_write_supported

    @property
    def snapshot_settings_write_supported_by_type(self) -> dict[str, bool]:
        """Return known snapshot settings write support by target type."""
        return dict(
            self._snapshot_capability_flags(
                "_snapshot_settings_write_supported_by_type"
            )
        )

    async def async_get_snapshot_settings(self) -> list[dict[str, Any]]:
        """Return normalized snapshot targets when the endpoint is available."""
        await self._ensure_authenticated()
        try:
            return await self._async_get_snapshot_settings_once()
        except InvalidAuth:
            _LOGGER.debug(
                "UNAS session expired before snapshot settings read; "
                "retrying login once"
            )
            self._authenticated = False
            await self.async_login()
            return await self._async_get_snapshot_settings_once()

    async def async_create_shared_drive_snapshot(
        self,
        shared_drive_name: str,
        *,
        description: str = "",
        locked: bool = False,
    ) -> None:
        """Create a snapshot of a shared drive."""
        shared_drive_name = str(shared_drive_name).strip()
        if not shared_drive_name:
            raise UnexpectedResponse("Shared drive name is empty")

        await self._async_create_snapshot(
            SHARED_DRIVE_SNAPSHOTS_PATH.format(
                shared_drive_name=quote(shared_drive_name, safe="")
            ),
            description=description,
            locked=locked,
            target_type="shared",
        )

    async def async_create_snapshot_target(
        self,
        target: dict[str, Any],
        *,
        description: str = "",
        locked: bool = False,
    ) -> None:
        """Create a snapshot for a specific target."""
        paths = _snapshot_create_paths(target)
        await self._async_create_snapshot(
            paths,
            description=description,
            locked=locked,
            target_type=snapshot_target_type(target),
        )

    async def async_get_snapshot_inventory_target(
        self,
        target: dict[str, Any],
    ) -> dict[str, Any]:
        """Return a compact snapshot inventory summary for one target."""
        paths = _snapshot_inventory_paths(target)
        target_type = snapshot_target_type(target)
        await self._ensure_authenticated()
        try:
            return await self._async_get_snapshot_inventory_with_paths(
                paths,
                target_type=target_type,
            )
        except InvalidAuth:
            _LOGGER.debug(
                "UNAS session expired before snapshot inventory read; "
                "retrying login once"
            )
            self._authenticated = False
            await self.async_login()
            return await self._async_get_snapshot_inventory_with_paths(
                paths,
                target_type=target_type,
            )

    async def async_update_snapshot_target_settings(
        self,
        target: dict[str, Any],
        *,
        enabled: bool | None = None,
        max_count: int | None = None,
        schedule_enabled: bool | None = None,
        schedule_frequency: str | None = None,
        schedule_time: str | None = None,
        schedule_weekdays: str | None = None,
        schedule_monthdays: str | None = None,
    ) -> None:
        """Update snapshot settings for a normalized target."""
        update = SnapshotSettingsUpdate(
            enabled=enabled,
            max_count=max_count,
            schedule_enabled=schedule_enabled,
            schedule_frequency=schedule_frequency,
            schedule_time=schedule_time,
            schedule_weekdays=schedule_weekdays,
            schedule_monthdays=schedule_monthdays,
        )
        # Settings are full-document writes. Serialize across platforms and
        # services, and never merge a change into a caller's stale target copy.
        async with self._snapshot_settings_lock:
            target_key = snapshot_target_key(target)
            current = next(
                (item for item in await self.async_get_snapshot_settings()
                 if target_key and snapshot_target_key(item) == target_key),
                None,
            )
            if current is None:
                raise UnexpectedResponse(
                    "Snapshot target is no longer available. Refresh the target list before retrying."
                )
            try:
                await self._async_update_snapshot_target_settings_once(current, update)
            except InvalidAuth:
                _LOGGER.debug(
                    "UNAS session expired before snapshot settings write; "
                    "retrying login once"
                )
                self._authenticated = False
                await self.async_login()
                await self._async_update_snapshot_target_settings_once(current, update)

    async def _async_get_snapshot_settings_once(self) -> list[dict[str, Any]]:
        """Read snapshot settings from the configured endpoint."""
        if self._snapshot_settings_read_supported is False:
            return []

        status, payload = await self._request_raw("GET", SNAPSHOT_SETTINGS_PATH)
        if status in SNAPSHOT_ENDPOINT_UNAVAILABLE_HTTP_STATUSES:
            self._snapshot_settings_read_supported = False
            return []
        if status < 200 or status >= 300:
            raise CannotConnect(
                f"Snapshot settings could not be read (HTTP {status}). Retry later."
            )

        self._snapshot_settings_read_supported = True
        current_user_id = self._current_user_id()
        settings = self._extract_snapshot_settings(
            payload,
            current_user_id=current_user_id,
        )
        _LOGGER.debug(
            "Snapshot settings endpoint %s returned %s target(s)",
            SNAPSHOT_SETTINGS_PATH,
            len(settings),
        )
        if not settings:
            _LOGGER.debug(
                "Snapshot settings payload shape: %s",
                _payload_debug_shape(payload),
            )
        return settings

    async def _async_create_snapshot(
        self,
        path: str | tuple[str, ...],
        *,
        description: str,
        locked: bool,
        target_type: str | None = None,
    ) -> None:
        """Create a snapshot through a known local Drive endpoint."""
        await self._ensure_authenticated()
        payload = {"description": str(description), "locked": bool(locked)}
        try:
            await self._async_create_snapshot_with_paths(
                path,
                payload,
                target_type=target_type,
            )
        except InvalidAuth:
            _LOGGER.debug(
                "UNAS session expired before snapshot creation; retrying login once"
            )
            self._authenticated = False
            await self.async_login()
            await self._async_create_snapshot_with_paths(
                path,
                payload,
                target_type=target_type,
            )

    async def _async_create_snapshot_with_paths(
        self,
        path: str | tuple[str, ...],
        payload: dict[str, Any],
        *,
        target_type: str | None = None,
    ) -> None:
        """Create a snapshot using one or more candidate endpoint paths."""
        paths = (path,) if isinstance(path, str) else path
        last_error: UnsupportedFeature | None = None
        for candidate in paths:
            try:
                await self._async_create_snapshot_once(
                    candidate,
                    payload,
                    target_type=target_type,
                )
            except UnsupportedFeature as err:
                last_error = err
                continue
            return

        if last_error is not None:
            raise last_error
        raise UnsupportedFeature("Manual snapshot endpoint is not configured.")

    async def _async_get_snapshot_inventory_with_paths(
        self,
        paths: tuple[str, ...],
        *,
        target_type: str | None = None,
    ) -> dict[str, Any]:
        """Read snapshot inventory using one or more candidate endpoint paths."""
        last_error: UnsupportedFeature | None = None
        for candidate in paths:
            try:
                return await self._async_get_snapshot_inventory_once(
                    candidate,
                    target_type=target_type,
                )
            except UnsupportedFeature as err:
                last_error = err
                continue

        if last_error is not None:
            raise last_error
        raise UnsupportedFeature("Snapshot inventory endpoint is not configured.")

    async def _async_get_snapshot_inventory_once(
        self,
        path: str,
        *,
        target_type: str | None = None,
    ) -> dict[str, Any]:
        """Read and normalize one snapshot inventory endpoint."""
        status, payload = await self._request_raw("GET", path)
        if 200 <= status < 300:
            self._set_snapshot_capability(
                "_snapshot_inventory_supported",
                "_snapshot_inventory_supported_by_type",
                target_type,
                True,
            )
            inventory = extract_snapshot_inventory(payload)
            _LOGGER.debug(
                "Snapshot inventory endpoint returned %s snapshot(s)",
                inventory["snapshot_count"],
            )
            return inventory

        if status in SNAPSHOT_ENDPOINT_UNAVAILABLE_HTTP_STATUSES:
            self._set_snapshot_capability(
                "_snapshot_inventory_supported",
                "_snapshot_inventory_supported_by_type",
                target_type,
                False,
            )
            raise UnsupportedFeature(
                "Snapshot inventory endpoint is not available on this system."
            )
        raise UnsupportedFeature(
            f"Snapshot inventory endpoint returned HTTP {status}: "
            f"{safe_response_summary(payload)}"
        )

    async def _async_create_snapshot_once(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        target_type: str | None = None,
    ) -> None:
        """Create a snapshot once and map endpoint errors."""
        status, response_payload = await self._request_raw(
            "POST",
            path,
            json_body=payload,
        )
        if 200 <= status < 300:
            self._set_snapshot_capability(
                "_snapshot_create_supported",
                "_snapshot_create_supported_by_type",
                target_type,
                True,
            )
            return

        if status in SNAPSHOT_ENDPOINT_UNAVAILABLE_HTTP_STATUSES:
            self._set_snapshot_capability(
                "_snapshot_create_supported",
                "_snapshot_create_supported_by_type",
                target_type,
                False,
            )
            raise UnsupportedFeature(
                "Manual snapshot endpoint is not available on this system."
            )
        raise CannotConnect(
            f"Manual snapshot endpoint returned HTTP {status}: "
            f"{safe_response_summary(response_payload)}"
        )

    async def _async_update_snapshot_target_settings_once(
        self,
        target: dict[str, Any],
        update: SnapshotSettingsUpdate | None = None,
        *,
        enabled: bool | None = None,
        max_count: int | None = None,
        schedule_enabled: bool | None = None,
        schedule_frequency: str | None = None,
        schedule_time: str | None = None,
        schedule_weekdays: str | None = None,
        schedule_monthdays: str | None = None,
    ) -> None:
        """Update one snapshot target setting against the local Drive endpoint."""
        update = update or SnapshotSettingsUpdate(
            enabled=enabled,
            max_count=max_count,
            schedule_enabled=schedule_enabled,
            schedule_frequency=schedule_frequency,
            schedule_time=schedule_time,
            schedule_weekdays=schedule_weekdays,
            schedule_monthdays=schedule_monthdays,
        )
        target_type = _snapshot_capability_target_type(
            snapshot_target_type(target)
        )
        if (
            target_type
            and self._snapshot_capability_flags(
                "_snapshot_settings_write_supported_by_type"
            ).get(target_type)
            is False
        ):
            raise UnsupportedFeature(
                "Snapshot settings write endpoint is not available on this system."
            )

        delete_settings = _snapshot_settings_delete_required(update)
        put_body = _snapshot_settings_write_body(target, update)
        write_attempts: list[tuple[str, dict[str, Any] | None]] = [("PUT", put_body)]
        if delete_settings:
            write_attempts.insert(0, ("DELETE", None))

        for method, body in write_attempts:
            for path in _snapshot_settings_write_paths(target):
                write_status, write_response = await self._request_raw(
                    method,
                    path,
                    json_body=body,
                )
                if 200 <= write_status < 300:
                    self._set_snapshot_capability(
                        "_snapshot_settings_write_supported",
                        "_snapshot_settings_write_supported_by_type",
                        target_type,
                        True,
                    )
                    return

                if write_status not in SNAPSHOT_ENDPOINT_UNAVAILABLE_HTTP_STATUSES:
                    # The write may have succeeded before the error response.
                    raise CannotConnect(
                        f"Snapshot settings {method.lower()} endpoint returned HTTP "
                        f"{write_status}: {safe_response_summary(write_response)}"
                    )

            if method == "PUT":
                self._set_snapshot_capability(
                    "_snapshot_settings_write_supported",
                    "_snapshot_settings_write_supported_by_type",
                    target_type,
                    False,
                )
                raise UnsupportedFeature(
                    "Snapshot settings write endpoint is not available on this system."
                )

    def _current_user_id(self) -> str | None:
        """Return the authenticated user id when login metadata exposes it."""
        if not isinstance(self._login_data, dict):
            return None
        user_id = self._login_data.get("id") or self._login_data.get("unique_id")
        if user_id in (None, ""):
            return None
        return str(user_id)

    def _snapshot_capability_flags(self, attr: str) -> dict[str, bool]:
        """Return mutable target-type capability flags for older test fakes too."""
        flags = getattr(self, attr, None)
        if not isinstance(flags, dict):
            flags = {}
            setattr(self, attr, flags)
        return flags

    def _set_snapshot_capability(
        self,
        aggregate_attr: str,
        typed_attr: str,
        target_type: str | None,
        supported: bool,
    ) -> None:
        """Set a snapshot capability globally or for a specific target type."""
        capability_type = _snapshot_capability_target_type(target_type)
        if capability_type is None:
            setattr(self, aggregate_attr, supported)
            return

        flags = self._snapshot_capability_flags(typed_attr)
        flags[capability_type] = supported
        setattr(self, aggregate_attr, _snapshot_capability_aggregate(flags))

    _extract_snapshot_settings = staticmethod(extract_snapshot_settings)
