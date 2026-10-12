"""Config-flow schemas and user-input normalization."""

from __future__ import annotations

from collections.abc import Callable
from ipaddress import IPv4Address, IPv6Address, ip_address
import re
from typing import Any
from urllib.parse import urlsplit

from homeassistant.const import (
    CONF_API_KEY,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_SSL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)

from .const import (
    CONF_FAN_CONTROL_ENABLED,
    CONF_DISCOVERY_DEBUG,
    CONF_SNAPSHOT_BUTTONS_ENABLED,
    CONF_WOL_BROADCAST_ADDRESS,
    CONF_WOL_ENABLED,
    CONF_WOL_MAC_ADDRESS,
    CONF_WOL_PORT,
    DEFAULT_FAN_CONTROL_ENABLED,
    DEFAULT_DISCOVERY_DEBUG,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SNAPSHOT_BUTTONS_ENABLED,
    DEFAULT_SSL,
    DEFAULT_VERIFY_SSL,
    DEFAULT_WOL_BROADCAST_ADDRESS,
    DEFAULT_WOL_ENABLED,
    DEFAULT_WOL_PORT,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from . import ha_validation as vol
from .wake_on_lan import normalize_mac_address, validate_ipv4_address

HOSTNAME_LABEL_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)


class FlowInputError(Exception):
    """Raised when user input is syntactically invalid."""

    def __init__(self, field: str, reason: str) -> None:
        """Initialize the flow input error."""
        super().__init__(reason)
        self.field = field
        self.reason = reason


def _connection_schema(
    defaults: dict[str, Any] | None = None,
) -> vol.Schema:
    """Return the connection/auth input schema."""
    return vol.Schema(_connection_schema_fields(defaults))


def _feature_schema(
    defaults: dict[str, Any] | None = None,
) -> vol.Schema:
    """Return the optional feature input schema."""
    return vol.Schema(_feature_schema_fields(defaults))


def _connection_schema_fields(
    defaults: dict[str, Any] | None = None,
) -> dict[Any, Any]:
    """Return connection/auth schema fields."""
    defaults = defaults or {}
    password_key = vol.Optional(CONF_PASSWORD, default="")
    username_key = vol.Optional(CONF_USERNAME, default=defaults.get(CONF_USERNAME, ""))

    return {
        vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
        vol.Required(
            CONF_PORT,
            default=_int_default(defaults.get(CONF_PORT), DEFAULT_PORT, minimum=1, maximum=65535),
        ): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
        vol.Required(
            CONF_SSL,
            default=bool(defaults.get(CONF_SSL, DEFAULT_SSL)),
        ): bool,
        vol.Required(
            CONF_VERIFY_SSL,
            default=bool(defaults.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)),
        ): bool,
        username_key: str,
        password_key: str,
        vol.Optional(
            CONF_API_KEY,
            default=defaults.get(CONF_API_KEY, ""),
        ): str,
    }


def _feature_schema_fields(
    defaults: dict[str, Any] | None = None,
) -> dict[Any, Any]:
    """Return optional feature schema fields."""
    defaults = _feature_defaults(defaults)
    return {
        vol.Required(
            CONF_SCAN_INTERVAL,
            default=int(defaults[CONF_SCAN_INTERVAL]),
        ): vol.All(
            vol.Coerce(int),
            vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
        ),
        vol.Required(
            CONF_FAN_CONTROL_ENABLED,
            default=bool(defaults[CONF_FAN_CONTROL_ENABLED]),
        ): bool,
        vol.Required(
            CONF_SNAPSHOT_BUTTONS_ENABLED,
            default=bool(defaults[CONF_SNAPSHOT_BUTTONS_ENABLED]),
        ): bool,
        vol.Required(
            CONF_DISCOVERY_DEBUG,
            default=bool(defaults[CONF_DISCOVERY_DEBUG]),
        ): bool,
        vol.Required(
            CONF_WOL_ENABLED,
            default=bool(defaults[CONF_WOL_ENABLED]),
        ): bool,
        vol.Optional(
            CONF_WOL_MAC_ADDRESS,
            default=defaults[CONF_WOL_MAC_ADDRESS],
        ): str,
        vol.Optional(
            CONF_WOL_BROADCAST_ADDRESS,
            default=defaults[CONF_WOL_BROADCAST_ADDRESS],
        ): str,
        vol.Optional(
            CONF_WOL_PORT,
            default=int(defaults[CONF_WOL_PORT]),
        ): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
    }


def _feature_defaults(defaults: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return normalized defaults for optional feature settings."""
    defaults = defaults or {}
    return {
        CONF_SCAN_INTERVAL: _int_default(
            defaults.get(CONF_SCAN_INTERVAL),
            DEFAULT_SCAN_INTERVAL,
            minimum=MIN_SCAN_INTERVAL,
            maximum=MAX_SCAN_INTERVAL,
        ),
        CONF_FAN_CONTROL_ENABLED: bool(
            defaults.get(CONF_FAN_CONTROL_ENABLED, DEFAULT_FAN_CONTROL_ENABLED)
        ),
        CONF_SNAPSHOT_BUTTONS_ENABLED: bool(
            defaults.get(
                CONF_SNAPSHOT_BUTTONS_ENABLED,
                DEFAULT_SNAPSHOT_BUTTONS_ENABLED,
            )
        ),
        CONF_DISCOVERY_DEBUG: bool(
            defaults.get(CONF_DISCOVERY_DEBUG, DEFAULT_DISCOVERY_DEBUG)
        ),
        CONF_WOL_ENABLED: bool(defaults.get(CONF_WOL_ENABLED, DEFAULT_WOL_ENABLED)),
        CONF_WOL_MAC_ADDRESS: defaults.get(CONF_WOL_MAC_ADDRESS, ""),
        CONF_WOL_BROADCAST_ADDRESS: defaults.get(
            CONF_WOL_BROADCAST_ADDRESS,
            DEFAULT_WOL_BROADCAST_ADDRESS,
        ),
        CONF_WOL_PORT: _int_default(
            defaults.get(CONF_WOL_PORT),
            DEFAULT_WOL_PORT,
            minimum=1,
            maximum=65535,
        ),
    }


def _int_default(
    value: Any,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    """Return a bounded integer default without trusting stored JSON."""
    try:
        candidate = int(value)
    except (TypeError, ValueError):
        return default
    if candidate < minimum or candidate > maximum:
        return default
    return candidate


def _merge_feature_defaults(
    data: dict[str, Any],
    defaults: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return input data with missing optional feature settings filled."""
    merged = dict(_feature_defaults(defaults))
    merged.update(data)
    return merged


def _merged_reauth_data(
    current: dict[str, Any],
    user_input: dict[str, Any],
) -> dict[str, Any]:
    """Return current entry data with updated authentication values."""
    data = dict(current)
    data[CONF_USERNAME] = str(user_input.get(CONF_USERNAME, "")).strip()
    data[CONF_PASSWORD] = _password_or_current(current, user_input)
    data[CONF_API_KEY] = _api_key_or_current(current, user_input)
    return data


def _merged_reconfigure_data(
    current: dict[str, Any],
    user_input: dict[str, Any],
) -> dict[str, Any]:
    """Return current entry data with reconfigure input applied."""
    merged = dict(current)
    merged.update(user_input)
    merged[CONF_PASSWORD] = _password_or_current(current, merged)
    merged[CONF_API_KEY] = _api_key_or_current(current, user_input)
    return _merge_feature_defaults(merged, current)


def _password_or_current(
    current: dict[str, Any],
    user_input: dict[str, Any],
) -> str:
    """Return a new password unless the form left it blank."""
    password = str(user_input.get(CONF_PASSWORD, ""))
    return password if password else str(current.get(CONF_PASSWORD, ""))


def _api_key_or_current(
    current: dict[str, Any],
    user_input: dict[str, Any],
) -> str:
    """Return a new API key when submitted, otherwise keep the current value."""
    if CONF_API_KEY in user_input:
        return str(user_input.get(CONF_API_KEY, "")).strip()
    return str(current.get(CONF_API_KEY, "")).strip()


def _normalize_user_input(
    user_input: dict[str, Any],
    *,
    mac_normalizer: Callable[[str], str] = normalize_mac_address,
    broadcast_validator: Callable[[str], str] = validate_ipv4_address,
) -> dict[str, Any]:
    """Normalize host, scheme, port and optional feature settings."""
    data = dict(user_input)
    host_input = str(data[CONF_HOST]).strip().rstrip("/")
    try:
        normalized_host, parsed_port, parsed_ssl = _normalize_host_input(host_input)
    except ValueError as err:
        raise FlowInputError(CONF_HOST, "invalid_host") from err

    data[CONF_HOST] = normalized_host
    if parsed_port is not None:
        data[CONF_PORT] = parsed_port
    if parsed_ssl is not None:
        data[CONF_SSL] = parsed_ssl

    data[CONF_PORT] = int(data.get(CONF_PORT, DEFAULT_PORT))
    data[CONF_SSL] = bool(data.get(CONF_SSL, DEFAULT_SSL))
    data[CONF_VERIFY_SSL] = bool(data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL))
    scan_interval = int(data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
    if scan_interval < MIN_SCAN_INTERVAL or scan_interval > MAX_SCAN_INTERVAL:
        raise FlowInputError(CONF_SCAN_INTERVAL, "invalid_scan_interval")
    data[CONF_SCAN_INTERVAL] = scan_interval
    data[CONF_FAN_CONTROL_ENABLED] = bool(
        data.get(CONF_FAN_CONTROL_ENABLED, DEFAULT_FAN_CONTROL_ENABLED)
    )
    data[CONF_SNAPSHOT_BUTTONS_ENABLED] = bool(
        data.get(CONF_SNAPSHOT_BUTTONS_ENABLED, DEFAULT_SNAPSHOT_BUTTONS_ENABLED)
    )
    data[CONF_DISCOVERY_DEBUG] = bool(
        data.get(CONF_DISCOVERY_DEBUG, DEFAULT_DISCOVERY_DEBUG)
    )
    data[CONF_WOL_ENABLED] = bool(data.get(CONF_WOL_ENABLED, DEFAULT_WOL_ENABLED))
    data[CONF_USERNAME] = str(data.get(CONF_USERNAME, "")).strip()
    data[CONF_PASSWORD] = str(data.get(CONF_PASSWORD, ""))
    data[CONF_API_KEY] = str(data.get(CONF_API_KEY, "")).strip()

    if (
        not data[CONF_API_KEY]
        and (not data[CONF_USERNAME] or not data[CONF_PASSWORD])
    ):
        raise FlowInputError(CONF_PASSWORD, "credentials_or_api_key_required")

    mac_address = str(data.get(CONF_WOL_MAC_ADDRESS, "")).strip()
    if mac_address:
        try:
            data[CONF_WOL_MAC_ADDRESS] = mac_normalizer(mac_address)
        except ValueError as err:
            raise FlowInputError(CONF_WOL_MAC_ADDRESS, "invalid_mac_address") from err
    elif data[CONF_WOL_ENABLED]:
        raise FlowInputError(CONF_WOL_MAC_ADDRESS, "mac_required")
    else:
        data[CONF_WOL_MAC_ADDRESS] = ""

    broadcast_address = str(
        data.get(CONF_WOL_BROADCAST_ADDRESS, DEFAULT_WOL_BROADCAST_ADDRESS)
        or DEFAULT_WOL_BROADCAST_ADDRESS
    ).strip()
    try:
        data[CONF_WOL_BROADCAST_ADDRESS] = broadcast_validator(broadcast_address)
    except ValueError as err:
        raise FlowInputError(
            CONF_WOL_BROADCAST_ADDRESS,
            "invalid_broadcast_address",
        ) from err

    data[CONF_WOL_PORT] = int(data.get(CONF_WOL_PORT, DEFAULT_WOL_PORT))
    return data


def _normalize_host_input(host_input: str) -> tuple[str, int | None, bool | None]:
    """Normalize host input from plain host/IP, host:port or full URL."""
    if not host_input:
        raise ValueError("Host is empty")

    if host_input.startswith(("http://", "https://")):
        parsed = urlsplit(host_input)
        host = parsed.hostname
        if host is None:
            raise ValueError("Missing hostname")
        return _validate_host(host), parsed.port, parsed.scheme == "https"

    if _is_ip_literal(host_input):
        return _validate_host(host_input), None, None

    parsed = urlsplit(f"//{host_input}")
    host = parsed.hostname
    if host is None:
        raise ValueError("Missing hostname")
    return _validate_host(host), parsed.port, None


def _is_ip_literal(value: str) -> bool:
    """Return whether the value is a valid IPv4/IPv6 literal."""
    candidate = value.strip()
    if candidate.startswith("[") and candidate.endswith("]"):
        candidate = candidate[1:-1]
    try:
        ip_address(candidate)
    except ValueError:
        return False
    return True


def _validate_host(host: str) -> str:
    """Validate a host as IP literal or RFC1123-like hostname."""
    candidate = host.strip().rstrip(".")
    if not candidate:
        raise ValueError("Host is empty")

    ip_literal = _parse_ip_literal(candidate)
    if ip_literal is not None:
        if isinstance(ip_literal, IPv6Address):
            return f"[{ip_literal.compressed}]"
        return str(ip_literal)

    labels = candidate.split(".")
    if any(not label for label in labels):
        raise ValueError("Hostname contains empty label")
    if len(candidate) > 253:
        raise ValueError("Hostname too long")
    if all(label.isdigit() for label in labels):
        raise ValueError("Invalid numeric host")
    if not all(
        len(label) <= 63 and HOSTNAME_LABEL_RE.fullmatch(label) for label in labels
    ):
        raise ValueError("Invalid hostname label")
    return candidate


def _parse_ip_literal(value: str) -> IPv4Address | IPv6Address | None:
    """Return a parsed IP literal, accepting bracketed IPv6 input."""
    candidate = value.strip()
    if candidate.startswith("[") and candidate.endswith("]"):
        candidate = candidate[1:-1]
    try:
        return ip_address(candidate)
    except ValueError:
        return None
