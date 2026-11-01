"""Fan-control operations for the UniFi Drive API client."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from .api_errors import InvalidAuth, UnexpectedResponse, UnsupportedFeature
from .const import FAN_CONTROL_PATH, FAN_MODE_API_VALUES
from .security import safe_response_summary

_LOGGER = logging.getLogger(__name__)

FAN_MODE_EXACT_KEYS = {
    "fanmode",
    "fan_mode",
    "profile",
    "currentprofile",
    "fanprofilecurrent",
    "fanprofile",
    "fan_profile",
    "fancontrolmode",
    "fan_control_mode",
    "fanpolicy",
    "fan_policy",
    "thermalmode",
    "thermal_mode",
}
FAN_MODE_NOT_FOUND_HTTP_STATUSES = {404, 405}


class ApiFanMixin:
    """Fan-control behavior split from the main API client class."""

    _authenticated: bool
    _fan_mode_read_supported: bool | None
    _fan_mode_write_payload_hint: str | None
    _fan_mode_write_supported: bool | None
    _last_fan_mode: str | None
    _system_info: dict[str, Any] | None

    if TYPE_CHECKING:
        async def _ensure_authenticated(self) -> None: ...
        async def async_login(self) -> None: ...
        async def _request_json(self, method: str, path: str) -> dict[str, Any]: ...
        async def _request_raw(
            self,
            method: str,
            path: str,
            *,
            json_body: dict[str, Any] | None = None,
        ) -> tuple[int, Any]: ...

    @property
    def native_fan_mode(self) -> str | None:
        """Return the last native Drive fan mode seen or set."""
        return self._last_fan_mode

    @property
    def fan_mode_read_supported(self) -> bool | None:
        """Return whether the fan-mode read endpoint is known to be supported."""
        return self._fan_mode_read_supported

    @property
    def fan_mode_write_supported(self) -> bool | None:
        """Return whether the fan-mode write endpoint is known to be supported."""
        return self._fan_mode_write_supported

    @property
    def fan_mode_write_payload_hint(self) -> str | None:
        """Return the fan-mode payload shape that last succeeded, if known."""
        return self._fan_mode_write_payload_hint

    async def async_get_fan_control(self) -> dict[str, Any]:
        """Return UniFi Drive fan-control data when the endpoint is available."""
        await self._ensure_authenticated()
        try:
            data = await self._request_json("GET", FAN_CONTROL_PATH)
        except InvalidAuth:
            _LOGGER.debug(
                "UNAS session expired before fan-control read; retrying login once"
            )
            self._authenticated = False
            await self.async_login()
            data = await self._request_json("GET", FAN_CONTROL_PATH)

        if mode := self._extract_fan_mode(data):
            self._last_fan_mode = mode
        return data

    async def async_get_fan_mode(self) -> str | None:
        """Return the native UniFi Drive fan mode if a readable endpoint exposes it."""
        await self._ensure_authenticated()
        try:
            return await self._async_get_fan_mode_once()
        except InvalidAuth:
            _LOGGER.debug("UNAS session expired before fan-mode read; retrying login once")
            self._authenticated = False
            await self.async_login()
            return await self._async_get_fan_mode_once()

    async def async_set_fan_mode(self, option: str) -> str:
        """Set native UniFi Drive fan mode and return the canonical option name."""
        canonical = self._normalize_fan_mode(option)
        if canonical is None:
            raise UnexpectedResponse(f"Unsupported fan mode option: {option}")

        await self._ensure_authenticated()
        try:
            return await self._async_set_fan_mode_once(canonical)
        except InvalidAuth:
            _LOGGER.debug("UNAS session expired before fan-mode write; retrying login once")
            self._authenticated = False
            await self.async_login()
            return await self._async_set_fan_mode_once(canonical)

    async def _async_get_fan_mode_once(self) -> str | None:
        """Read native Drive fan mode from the configured endpoint."""
        if self._fan_mode_read_supported is False:
            return self._last_fan_mode

        status, payload = await self._request_raw("GET", FAN_CONTROL_PATH)
        if status in FAN_MODE_NOT_FOUND_HTTP_STATUSES:
            self._fan_mode_read_supported = False
            return self._last_fan_mode
        if status < 200 or status >= 300:
            _LOGGER.debug(
                "Fan-mode endpoint %s returned HTTP %s", FAN_CONTROL_PATH, status
            )
            return self._last_fan_mode

        self._fan_mode_read_supported = True
        if mode := self._extract_fan_mode(payload):
            self._last_fan_mode = mode
            return mode
        return self._last_fan_mode

    async def _async_set_fan_mode_once(self, canonical: str) -> str:
        """Set native Drive fan mode through the configured endpoint."""
        if self._fan_mode_write_supported is False:
            raise UnsupportedFeature(
                "Native UniFi Drive fan-mode endpoint is not available on this system."
            )

        raw_values = FAN_MODE_API_VALUES.get(canonical, (canonical.lower(), canonical))
        payloads = self._fan_mode_write_payloads(raw_values[0])

        last_status: int | None = None
        last_response_payload: Any = None
        for payload in payloads:
            status, response_payload = await self._request_raw(
                "PUT",
                FAN_CONTROL_PATH,
                json_body=payload,
            )
            last_status = status
            last_response_payload = response_payload
            if 200 <= status < 300:
                response_mode = self._extract_fan_mode(response_payload)
                self._last_fan_mode = response_mode or canonical
                self._fan_mode_write_supported = True
                self._fan_mode_write_payload_hint = self._fan_mode_payload_signature(
                    payload
                )
                return self._last_fan_mode

            if status in FAN_MODE_NOT_FOUND_HTTP_STATUSES:
                self._fan_mode_write_supported = False
                break

        if last_status in FAN_MODE_NOT_FOUND_HTTP_STATUSES:
            self._fan_mode_write_supported = False
        raise UnsupportedFeature(
            f"Native UniFi Drive fan-mode endpoint {FAN_CONTROL_PATH} returned "
            f"HTTP {last_status}: {safe_response_summary(last_response_payload)}"
        )

    def _fan_mode_write_payloads(self, value: str) -> tuple[dict[str, Any], ...]:
        """Return firmware-aware fan-mode payload variants."""
        payloads: list[dict[str, Any]] = [
            {"profile": value},
            {"profile": value, "apply": True},
        ]

        # Prefer the payload shape that worked previously during this runtime.
        hint = self._fan_mode_write_payload_hint
        if hint:
            payloads.sort(
                key=lambda candidate: 0
                if self._fan_mode_payload_signature(candidate) == hint
                else 1
            )
            return tuple(payloads)

        # Older firmware can require an explicit apply flag.
        if self._firmware_prefers_apply_payload():
            payloads.sort(
                key=lambda candidate: 0 if "apply" in candidate else 1
            )
        return tuple(payloads)

    def _firmware_prefers_apply_payload(self) -> bool:
        """Return whether version hints suggest `apply=true` should be tried first."""
        system = self._system_info if isinstance(self._system_info, dict) else {}
        firmware_version = self._read_version_string(system, ("hardware", "firmwareVersion"))
        drive_version = self._read_drive_controller_version(system)
        if drive_version and self._version_lt(drive_version, "4.2.0"):
            return True
        return bool(firmware_version and self._version_lt(firmware_version, "5.1.0"))

    @staticmethod
    def _fan_mode_payload_signature(payload: dict[str, Any]) -> str:
        """Return a stable signature for fan write payload variants."""
        return "profile_apply" if "apply" in payload else "profile_only"

    @staticmethod
    def _read_version_string(system: dict[str, Any], path: tuple[str, ...]) -> str | None:
        """Read a dotted version string from a nested system payload path."""
        current: Any = system
        for part in path:
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        if not isinstance(current, str) or not current.strip():
            return None
        return current.strip()

    @classmethod
    def _read_drive_controller_version(cls, system: dict[str, Any]) -> str | None:
        """Read UniFi Drive app/controller version from the system payload."""
        apps = system.get("apps")
        if not isinstance(apps, dict):
            return None
        controllers = apps.get("controllers")
        if not isinstance(controllers, list):
            return None
        for controller in controllers:
            if not isinstance(controller, dict):
                continue
            name = str(controller.get("name", "")).strip().lower()
            if name != "drive":
                continue
            for key in ("versionRaw", "version"):
                value = controller.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return None

    @staticmethod
    def _version_lt(left: str, right: str) -> bool:
        """Return whether dotted version string `left` is lower than `right`."""
        left_parts = [int(part) for part in re.findall(r"\d+", left)]
        right_parts = [int(part) for part in re.findall(r"\d+", right)]
        if not left_parts:
            return False
        length = max(len(left_parts), len(right_parts))
        left_parts.extend([0] * (length - len(left_parts)))
        right_parts.extend([0] * (length - len(right_parts)))
        return left_parts < right_parts

    @classmethod
    def _extract_fan_mode(cls, payload: Any) -> str | None:
        """Extract a canonical fan mode from nested Drive JSON if present."""
        return cls._walk_for_fan_mode(payload, context="")

    @classmethod
    def _walk_for_fan_mode(cls, value: Any, *, context: str) -> str | None:
        """Walk nested JSON-like data looking for fan mode values."""
        if isinstance(value, dict):
            for key, item in value.items():
                key_normalized = str(key).replace("-", "_").lower()
                compact_key = key_normalized.replace("_", "")

                if (
                    compact_key in FAN_MODE_EXACT_KEYS
                    or key_normalized in FAN_MODE_EXACT_KEYS
                ) and (mode := cls._normalize_fan_mode(item)):
                    return mode

                if key_normalized == "mode" and (
                    "fan" in context.lower() or "thermal" in context.lower()
                ) and (mode := cls._normalize_fan_mode(item)):
                    return mode

                if isinstance(item, (dict, list)):
                    child_context = f"{context}.{key}" if context else str(key)
                    if mode := cls._walk_for_fan_mode(item, context=child_context):
                        return mode

            return None

        if isinstance(value, list):
            for item in value:
                if mode := cls._walk_for_fan_mode(item, context=context):
                    return mode

        return None

    @staticmethod
    def _normalize_fan_mode(value: Any) -> str | None:
        """Normalize common fan mode representations to the HA option label."""
        if not isinstance(value, str):
            return None

        normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
        if normalized in {"quiet", "silent", "low"}:
            return "Quiet"
        if normalized in {
            "balance",
            "balanced",
            "normal",
            "auto",
            "default",
            "default_profile",
        }:
            return "Balance"
        if normalized in {"cooling", "cool", "high", "performance", "perf"}:
            return "Cooling"
        return None
