"""Data coordinator for the UniFi Drive integration."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    CannotConnect,
    InvalidAuth,
    UnexpectedResponse,
    UnifiUnasApiClient,
    UnsupportedFeature,
)
from .const import (
    CONF_FAN_CONTROL_ENABLED,
    CONF_SNAPSHOT_BUTTONS_ENABLED,
    DEFAULT_FAN_CONTROL_ENABLED,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SNAPSHOT_BUTTONS_ENABLED,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .entry_options import entry_bool, entry_int
from .entry_reload import EntryReloadSignature
from .snapshot_inventory import (
    SNAPSHOT_INVENTORY_REASON_CONNECTION,
    SNAPSHOT_INVENTORY_REASON_PERMISSION,
    SNAPSHOT_INVENTORY_REASON_UNEXPECTED_RESPONSE,
    SNAPSHOT_INVENTORY_REASON_UNKNOWN,
    SNAPSHOT_INVENTORY_REASON_UNSUPPORTED,
)
from .snapshot_repairs import (
    async_clear_snapshot_issues,
    async_create_snapshot_read_issue,
    async_update_snapshot_read_issue,
)
from .security import safe_error_text
from .storage_view import StorageView
from .snapshot_types import snapshot_target_key, snapshot_target_type

if TYPE_CHECKING:
    from .runtime import UnifiDriveConfigEntry

_LOGGER = logging.getLogger(__name__)
_SNAPSHOT_INVENTORY_UNAVAILABLE_MARKER = "not available on this system"
_SNAPSHOT_INVENTORY_REFRESH_INTERVAL = timedelta(minutes=10)
_CONNECTION_FAILURES_BEFORE_OFFLINE = 2
_OPTIONAL_REFRESH_TIMEOUT = 10


class UnifiUnasCoordinator(DataUpdateCoordinator[dict[str, Any]]):  # type: ignore[misc]
    """Coordinate polling of UniFi Drive storage data."""

    config_entry: UnifiDriveConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        client: UnifiUnasApiClient,
        entry: UnifiDriveConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        self.client = client
        self.config_entry = entry
        self.fan_control_enabled = entry_bool(
            entry,
            CONF_FAN_CONTROL_ENABLED,
            DEFAULT_FAN_CONTROL_ENABLED,
        )
        self.snapshot_buttons_enabled = entry_bool(
            entry,
            CONF_SNAPSHOT_BUTTONS_ENABLED,
            DEFAULT_SNAPSHOT_BUTTONS_ENABLED,
        )
        self.is_device_online = True
        self.fan_mode: str | None = None
        self.backup_tasks: list[dict[str, Any]] = []
        self.snapshot_settings: list[dict[str, Any]] = []
        self.snapshot_settings_available = False
        self.snapshot_inventory: dict[str, dict[str, Any]] = {}
        self.snapshot_inventory_errors: dict[str, str] = {}
        self.snapshot_inventory_skip_reasons: dict[str, str] = {}
        self.entry_reload_signature: EntryReloadSignature | None = None
        self._connection_failure_count = 0
        self._connection_transient_logged = False
        self._connection_offline_logged = False
        self._snapshot_inventory_last_refresh: datetime | None = None
        self._snapshot_inventory_refresh_requested = False
        self._snapshot_inventory_target_keys: set[str] = set()
        self._snapshot_inventory_pending_targets: dict[str, None] | None = None
        self._snapshot_inventory_batch_started: datetime | None = None
        self._first_refresh_core_only = False
        self._optional_refresh_lock = asyncio.Lock()
        self._optional_refresh_timed_out = False
        self._storage_view: StorageView | None = None
        interval = entry_int(entry, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        interval = max(MIN_SCAN_INTERVAL, min(MAX_SCAN_INTERVAL, interval))

        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )

    def async_update_listeners(self) -> None:
        """Invalidate derived data even when a caller updates a payload in place."""
        self._storage_view = None
        super().async_update_listeners()

    async def async_config_entry_first_refresh(self) -> None:
        """Fetch core data first so entities can be registered quickly."""
        self._first_refresh_core_only = True
        try:
            await super().async_config_entry_first_refresh()
        finally:
            self._first_refresh_core_only = False

    async def async_refresh_optional_features(self) -> None:
        """Refresh optional local endpoints after core entities exist."""
        if not isinstance(self.data, dict):
            return

        await self._async_refresh_optional_features()
        self.async_set_updated_data(self.data)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch storage data from the UNAS."""
        try:
            storage = await self.client.async_get_storage()
            self._handle_connection_recovered()
            self._connection_failure_count = 0
            self.is_device_online = True
        except CannotConnect as err:
            return self._handle_connection_failure(err)
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed("Invalid UniFi Drive credentials") from err
        except UnexpectedResponse as err:
            raise UpdateFailed(safe_error_text(err)) from err

        if self._first_refresh_core_only:
            return storage

        await self._async_refresh_optional_features()
        return storage

    async def _async_refresh_optional_features(self) -> None:
        """Bound optional polling latency and avoid overlapping startup refreshes."""
        if self._optional_refresh_lock.locked():
            return
        async with self._optional_refresh_lock:
            refreshers = [self._refresh_backup_tasks]
            if self.fan_control_enabled:
                refreshers.insert(0, self._refresh_fan_mode)
            if self.snapshot_buttons_enabled:
                refreshers.append(self._refresh_snapshot_settings)
            else:
                self._clear_snapshot_settings_state()

            loop = asyncio.get_running_loop()
            deadline = loop.time() + _OPTIONAL_REFRESH_TIMEOUT
            timed_out = False
            for index, refresh in enumerate(refreshers):
                # Reserve time for later features without concurrent login requests.
                budget = max(0.0, deadline - loop.time()) / (len(refreshers) - index)
                try:
                    async with asyncio.timeout(budget):
                        await refresh()
                except TimeoutError:
                    timed_out = True
            if timed_out:
                if not self._optional_refresh_timed_out:
                    _LOGGER.debug(
                        "Optional polling exceeded its time budget; publishing core storage data"
                    )
                self._optional_refresh_timed_out = True
            else:
                if self._optional_refresh_timed_out:
                    _LOGGER.debug("Optional polling recovered within its time budget")
                self._optional_refresh_timed_out = False

    def _handle_connection_recovered(self) -> None:
        """Log once when polling recovers after a connection failure."""
        if self._connection_offline_logged:
            _LOGGER.info("UniFi Drive connection restored")
        self._connection_transient_logged = False
        self._connection_offline_logged = False

    def _handle_connection_failure(self, err: CannotConnect) -> dict[str, Any]:
        """Return cached data during tolerated connection failures."""
        message = safe_error_text(err)
        cached_data = self.data if isinstance(self.data, dict) else None
        if cached_data is None:
            self.is_device_online = False
            self._connection_failure_count = _CONNECTION_FAILURES_BEFORE_OFFLINE
            raise UpdateFailed(message) from err

        self._connection_failure_count += 1
        if self._should_keep_cached_data_online():
            if not self._connection_transient_logged:
                _LOGGER.debug(
                    "UniFi Drive storage poll failed once, keeping device "
                    "online with last known data: %s",
                    message,
                )
                self._connection_transient_logged = True
            return cached_data

        self.is_device_online = False
        if not self._connection_offline_logged:
            _LOGGER.warning(
                "UniFi Drive is unavailable, keeping last known data: %s",
                message,
            )
            self._connection_offline_logged = True
        return self._with_offline_status(cached_data)

    def _should_keep_cached_data_online(self) -> bool:
        """Return whether a transient failure should keep the device online."""
        return (
            self.is_device_online
            and self._connection_failure_count < _CONNECTION_FAILURES_BEFORE_OFFLINE
        )

    async def _refresh_fan_mode(self) -> None:
        """Refresh fan mode without treating optional endpoint failures as fatal."""
        if not self.fan_control_enabled:
            return

        try:
            mode = await self.client.async_get_fan_mode()
        except (CannotConnect, InvalidAuth, UnexpectedResponse, UnsupportedFeature) as err:
            _LOGGER.debug(
                "Could not read UniFi Drive fan mode: %s",
                safe_error_text(err),
            )
            return

        if mode:
            self.fan_mode = mode

    async def _refresh_backup_tasks(self) -> None:
        """Refresh backup tasks while tolerating optional API gaps."""
        try:
            self.backup_tasks = await self.client.async_get_backup_tasks()
        except (CannotConnect, InvalidAuth, UnexpectedResponse, UnsupportedFeature) as err:
            _LOGGER.debug(
                "Could not read UniFi Drive backup tasks: %s",
                safe_error_text(err),
            )
            self.backup_tasks = []

    async def _refresh_snapshot_settings(self) -> None:
        """Refresh snapshot settings and trigger inventory refresh if possible."""
        try:
            settings = await self.client.async_get_snapshot_settings()
        except asyncio.CancelledError:
            self.snapshot_settings_available = False
            raise
        except (
            CannotConnect,
            InvalidAuth,
            UnexpectedResponse,
            UnsupportedFeature,
        ) as err:
            # Snapshot settings and inventory are optional features.
            _LOGGER.debug(
                "Could not read UniFi Drive snapshot settings: %s",
                safe_error_text(err),
            )
            if not isinstance(err, CannotConnect):
                async_create_snapshot_read_issue(self.hass, self.config_entry, err)
            self.snapshot_settings_available = False
            return

        self.snapshot_settings_available = self.client.snapshot_settings_read_supported is not False
        if not self.snapshot_settings_available:
            async_update_snapshot_read_issue(self.hass, self.config_entry, supported=False)
            return
        self.snapshot_settings = settings
        async_update_snapshot_read_issue(
            self.hass,
            self.config_entry,
            supported=self.client.snapshot_settings_read_supported,
        )
        await self._async_refresh_snapshot_inventory_if_due()

    def _clear_snapshot_settings_state(self, *, clear_issues: bool = True) -> None:
        """Clear cached snapshot state and optionally clear snapshot repairs."""
        self.snapshot_settings = []
        self.snapshot_settings_available = False
        self.snapshot_inventory = {}
        self.snapshot_inventory_errors = {}
        self.snapshot_inventory_skip_reasons = {}
        self._snapshot_inventory_target_keys = set()
        self._snapshot_inventory_last_refresh = None
        self._snapshot_inventory_refresh_requested = False
        self._snapshot_inventory_pending_targets = None
        self._snapshot_inventory_batch_started = None
        if clear_issues:
            async_clear_snapshot_issues(self.hass, self.config_entry)

    def request_snapshot_inventory_refresh(self) -> None:
        """Force the next coordinator refresh to read snapshot inventory."""
        self._snapshot_inventory_refresh_requested = True

    async def _async_refresh_snapshot_inventory_if_due(self) -> None:
        """Refresh snapshot inventory on a slower cadence than storage polling."""
        active_target_keys = self._snapshot_inventory_active_target_keys()
        if active_target_keys != self._snapshot_inventory_target_keys:
            if self._snapshot_inventory_pending_targets is None:
                self._snapshot_inventory_refresh_requested = True
            else:
                self._snapshot_inventory_pending_targets = {
                    key: None for key in self._snapshot_inventory_pending_targets
                    if key in active_target_keys
                }
                self._snapshot_inventory_pending_targets.update(dict.fromkeys(
                    sorted(active_target_keys - self._snapshot_inventory_target_keys)
                ))
            self._snapshot_inventory_target_keys = active_target_keys

        self._prune_snapshot_inventory_state(active_target_keys)
        now = datetime.now(UTC)
        if not self._snapshot_inventory_refresh_due(now):
            return

        refresh_requested = self._snapshot_inventory_refresh_requested
        batch_expired = (
            self._snapshot_inventory_batch_started is not None
            and now - self._snapshot_inventory_batch_started >= _SNAPSHOT_INVENTORY_REFRESH_INTERVAL
        )
        if self._snapshot_inventory_pending_targets is None:
            self._snapshot_inventory_refresh_requested = False
            self._snapshot_inventory_pending_targets = dict.fromkeys(sorted(active_target_keys))
            self._snapshot_inventory_batch_started = now
        elif refresh_requested or batch_expired:
            # Revisit completed targets after writes or a full cadence, even if a peer stalls.
            for key in sorted(active_target_keys):
                self._snapshot_inventory_pending_targets.setdefault(key, None)
            self._snapshot_inventory_refresh_requested = False
            self._snapshot_inventory_batch_started = now
        try:
            self.snapshot_inventory = await self._async_get_snapshot_inventory(active_target_keys)
        except (RuntimeError, TypeError, ValueError) as err:
            self._snapshot_inventory_pending_targets = None
            self._snapshot_inventory_batch_started = None
            if refresh_requested:
                self._snapshot_inventory_refresh_requested = True
            _LOGGER.debug(
                "Unexpected error while refreshing snapshot inventory: %s",
                safe_error_text(err),
            )
            self._snapshot_inventory_last_refresh = now
            return

        self._snapshot_inventory_pending_targets = None
        self._snapshot_inventory_batch_started = None
        self._snapshot_inventory_last_refresh = datetime.now(UTC)

    def _snapshot_inventory_refresh_due(self, now: datetime) -> bool:
        """Return whether snapshot inventory should be read now."""
        if (
            self._snapshot_inventory_refresh_requested
            or self._snapshot_inventory_pending_targets is not None
        ):
            return True
        if self._snapshot_inventory_last_refresh is None:
            return True
        return now - self._snapshot_inventory_last_refresh >= (
            _SNAPSHOT_INVENTORY_REFRESH_INTERVAL
        )

    def _snapshot_inventory_active_target_keys(self) -> set[str]:
        """Return valid snapshot target keys from the current settings payload."""
        active_target_keys: set[str] = set()
        for target in self.snapshot_settings:
            if not isinstance(target, dict):
                continue
            target_key = snapshot_target_key(target)
            if target_key:
                active_target_keys.add(target_key)
        return active_target_keys

    def _prune_snapshot_inventory_state(self, active_target_keys: set[str]) -> None:
        """Drop cached snapshot inventory state for targets no longer advertised."""
        self.snapshot_inventory = {
            target_key: inventory
            for target_key, inventory in self.snapshot_inventory.items()
            if target_key in active_target_keys
        }
        self.snapshot_inventory_errors = {
            target_key: reason
            for target_key, reason in self.snapshot_inventory_errors.items()
            if target_key in active_target_keys
        }
        self.snapshot_inventory_skip_reasons = {
            target_key: reason
            for target_key, reason in self.snapshot_inventory_skip_reasons.items()
            if target_key in active_target_keys
        }

    async def _async_get_snapshot_inventory(
        self, active_target_keys: set[str] | None = None
    ) -> dict[str, dict[str, Any]]:
        """Return inventory summaries keyed by stable snapshot target key."""
        if active_target_keys is None:
            active_target_keys = self._snapshot_inventory_active_target_keys()
        pending = self._snapshot_inventory_pending_targets
        inventory = dict(self.snapshot_inventory) if pending is not None else {}
        inventory_errors = dict(self.snapshot_inventory_errors) if pending is not None else {}
        snapshot_inventory_supported_by_type = _snapshot_inventory_type_support_map(
            self.client
        )
        targets: dict[str, dict[str, Any]] = {}
        for raw_target in self.snapshot_settings:
            if not isinstance(raw_target, dict):
                continue
            target_key = snapshot_target_key(raw_target)
            if target_key and target_key in active_target_keys:
                targets[target_key] = raw_target

        for target_key in tuple(pending) if pending is not None else targets:
            target = targets.get(target_key)
            if target is None:
                if pending is not None:
                    pending.pop(target_key, None)
                continue
            target_type = snapshot_target_type(target)
            if skip_reason := self.snapshot_inventory_skip_reasons.get(target_key):
                inventory_errors[target_key] = skip_reason
            elif _snapshot_inventory_type_is_unsupported(
                snapshot_inventory_supported_by_type,
                target_type,
            ):
                reason = SNAPSHOT_INVENTORY_REASON_UNSUPPORTED
                inventory_errors[target_key] = reason
                self.snapshot_inventory_skip_reasons[target_key] = reason
            else:
                try:
                    inventory[target_key] = (
                        await self.client.async_get_snapshot_inventory_target(target)
                    )
                    inventory_errors.pop(target_key, None)
                    self.snapshot_inventory_skip_reasons.pop(target_key, None)
                except asyncio.CancelledError:
                    if pending is not None:
                        # Retry later without letting one stalled target starve its peers.
                        pending.pop(target_key, None)
                        pending[target_key] = None
                    raise
                except (
                    CannotConnect,
                    InvalidAuth,
                    UnexpectedResponse,
                    UnsupportedFeature,
                ) as err:
                    inventory_errors[target_key] = _snapshot_inventory_error_reason(err)
                    if _snapshot_inventory_read_should_be_skipped(err):
                        self.snapshot_inventory_skip_reasons[target_key] = (
                            inventory_errors[target_key]
                        )
                    _LOGGER.debug(
                        "Could not read UniFi Drive snapshot inventory for %s: %s",
                        target_type,
                        safe_error_text(err),
                    )
                except (RuntimeError, TypeError, ValueError) as err:
                    inventory_errors[target_key] = _snapshot_inventory_error_reason(err)
                    _LOGGER.debug(
                        "Unexpectedly failed to read snapshot inventory for %s: %s",
                        target_type,
                        safe_error_text(err),
                    )
            if target_key in inventory_errors:
                inventory.pop(target_key, None)
            if pending is not None:
                self.snapshot_inventory = inventory
                self.snapshot_inventory_errors = inventory_errors
                pending.pop(target_key, None)
        self.snapshot_inventory_skip_reasons = {
            target_key: reason
            for target_key, reason in self.snapshot_inventory_skip_reasons.items()
            if target_key in active_target_keys
        }
        self.snapshot_inventory_errors = inventory_errors
        return inventory

    @staticmethod
    def _with_offline_status(data: dict[str, Any]) -> dict[str, Any]:
        """Return a defensive shallow copy with `_system.status=offline`."""
        payload = dict(data)
        system = payload.get("_system")
        if not isinstance(system, dict):
            system = {}
        else:
            system = dict(system)
        payload["_system"] = system
        system["status"] = "offline"
        return payload


def _snapshot_inventory_read_should_be_skipped(err: Exception) -> bool:
    """Return whether an inventory read error should be treated as sticky."""
    if isinstance(err, InvalidAuth):
        return True
    if isinstance(err, UnsupportedFeature):
        return _snapshot_inventory_error_text_has_unavailable_marker(err)
    return False


def _snapshot_inventory_type_support_map(client: object) -> dict[str, bool]:
    """Return a validated snapshot inventory support map from a client."""
    support_map = getattr(client, "snapshot_inventory_supported_by_type", {})
    if not isinstance(support_map, dict):
        _LOGGER.debug(
            "Ignoring invalid snapshot inventory support cache type for client %s",
            type(client).__name__,
        )
        return {}

    validated: dict[str, bool] = {}
    for key, value in support_map.items():
        if isinstance(key, str) and isinstance(value, bool):
            validated[key] = value
    if len(validated) != len(support_map):
        _LOGGER.debug(
            "Ignoring malformed snapshot inventory support cache entries for client %s",
            type(client).__name__,
        )
    return validated


def _snapshot_inventory_type_is_unsupported(
    snapshot_inventory_supported_by_type: Mapping[str, bool],
    target_type: str,
) -> bool:
    """Return whether snapshot inventory reads should be skipped for the target type."""
    if snapshot_inventory_supported_by_type.get(target_type) is False:
        return True
    return (
        target_type == "mydrive"
        and snapshot_inventory_supported_by_type.get("personal") is False
    )


def _snapshot_inventory_error_text_has_unavailable_marker(err: Exception) -> bool:
    """Return whether an error message contains the unsupported snapshot marker."""
    message = safe_error_text(err).lower()
    return _SNAPSHOT_INVENTORY_UNAVAILABLE_MARKER in message


def _snapshot_inventory_error_reason(err: Exception) -> str:
    """Return a stable user-facing category for inventory read failures."""
    if isinstance(err, InvalidAuth):
        return SNAPSHOT_INVENTORY_REASON_PERMISSION
    if isinstance(err, UnsupportedFeature):
        if _snapshot_inventory_error_text_has_unavailable_marker(err):
            return SNAPSHOT_INVENTORY_REASON_UNSUPPORTED
        return SNAPSHOT_INVENTORY_REASON_UNEXPECTED_RESPONSE
    if isinstance(err, CannotConnect):
        return SNAPSHOT_INVENTORY_REASON_CONNECTION
    if isinstance(err, UnexpectedResponse):
        return SNAPSHOT_INVENTORY_REASON_UNEXPECTED_RESPONSE
    return SNAPSHOT_INVENTORY_REASON_UNKNOWN
