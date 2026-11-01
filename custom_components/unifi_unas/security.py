"""Security helpers for diagnostics, logging and user-facing errors."""

from __future__ import annotations

from typing import Any
import re

_REDACTED = "<redacted>"

_BEARER_RE = re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s\"']+")
_COOKIE_RE = re.compile(r"(?i)((?:set-cookie|cookie)\s*[:=]\s*)[^\n\r;,]+")
_HEADER_SECRET_RE = re.compile(
    r"(?i)((?:x-api-key|x-csrf-token|x-updated-csrf-token)\s*[:=]\s*)[^\n\r;,]+"
)
_QUERY_SECRET_RE = re.compile(
    r"(?i)([?&](?:access_token|refresh_token|token|code|state|api_key|key|secret)=)"
    r"[^&#\s\"']+"
)
_URL_AUTHORITY_RE = re.compile(r"(?i)\b(https?://)(\[[^\]]+\]|[^/?#\s\"'(),]+)")
_LOCAL_HOSTNAME_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9_-])"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"(?:home\.arpa|local|lan|home|internal|private|corp)"
    r"(?::\d{1,5})?"
    r"(?![A-Za-z0-9_-])"
)
_KEY_VALUE_SECRET_RE = re.compile(
    r"(?ix)"
    r"((?:\"|')?"
    r"(?:username|user_name|share|share_name|password|passwd|token|access_token|refresh_token|api[_-]?key|secret|"
    r"authorization|csrf|cookie|session|host|hostname|ip|ipaddress|ip_address|"
    r"mac|macaddress|mac_address|serial|serialnumber|serial_number|key)"
    r"(?:\"|')?\s*[:=]\s*)"
    r"(\"[^\"]*\"|'[^']*'|[^\s,}]+)"
)
_JWT_RE = re.compile(
    r"\b[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{8,}\b"
)
_MAC_RE = re.compile(r"(?i)\b[0-9a-f]{2}(?::[0-9a-f]{2}){5}\b")
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_BRACKETED_IPV6_RE = re.compile(r"\[[0-9a-fA-F:.%]{2,}\]")
_BARE_IPV6_RE = re.compile(
    r"(?<![\w:])(?:[0-9a-fA-F]{0,4}:){2,}[0-9a-fA-F]{0,4}(?:%[A-Za-z0-9_.-]+)?(?![\w:])"
)


def redact_sensitive_text(value: Any) -> str:
    """Return text with credentials, identifiers and local addresses redacted."""
    text = str(value)
    for pattern in (
        _BEARER_RE,
        _COOKIE_RE,
        _HEADER_SECRET_RE,
        _QUERY_SECRET_RE,
    ):
        text = pattern.sub(r"\1" + _REDACTED, text)
    text = _KEY_VALUE_SECRET_RE.sub(_redact_key_value_secret, text)
    text = _URL_AUTHORITY_RE.sub(_redact_url_authority, text)
    text = _LOCAL_HOSTNAME_RE.sub(_REDACTED, text)
    for pattern in (_JWT_RE, _MAC_RE, _IPV4_RE, _BRACKETED_IPV6_RE, _BARE_IPV6_RE):
        text = pattern.sub(_REDACTED, text)
    return text


def _redact_key_value_secret(match: re.Match[str]) -> str:
    """Return a redacted key-value pair without reprocessing query placeholders."""
    value = match.group(2)
    if value.startswith(_REDACTED):
        return match.group(0)
    return f"{match.group(1)}{_REDACTED}"


def _redact_url_authority(match: re.Match[str]) -> str:
    """Return a URL with its authority redacted while preserving separators."""
    authority = match.group(2)
    trailing = authority[len(authority.rstrip(".,;")) :]
    return f"{match.group(1)}{_REDACTED}{trailing}"


def safe_error_text(value: Any, *, limit: int = 500) -> str:
    """Return bounded redacted text for logs, repairs and exceptions."""
    text = redact_sensitive_text(value).strip() or "No error details were returned."
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def safe_response_summary(value: object) -> str:
    """Describe untrusted HTTP response bodies without exposing keys or values."""
    if value is None:
        return "empty response"
    if isinstance(value, dict):
        return f"object response ({len(value)} fields)"
    if isinstance(value, list):
        return f"array response ({len(value)} items)"
    if isinstance(value, str):
        return f"text response ({len(value)} characters)"
    return "scalar response"
