"""Shared privacy, asset and artifact checks for source, ZIPs and GitHub."""

from __future__ import annotations

import ipaddress
import os
from pathlib import Path
import re


FORBIDDEN_MARKERS_ENV = "UNIFI_UNAS_FORBIDDEN_MARKERS"
SECRET_PATTERNS = (
    (
        "private key",
        re.compile(rb"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
    ),
    ("github token", re.compile(rb"\bgh[opsu]_[A-Za-z0-9_]{36,}\b")),
    (
        "literal HA smoke password",
        re.compile(
            rb"HA_(?:SMOKE|TEST)_PASSWORD\s*=\s*['\"][^'\"\r\n]{8,}['\"]"
        ),
    ),
    (
        "plain password assignment",
        re.compile(
            rb"(?i)\b\"?(?:password|passwd|cifs_password)\"?\s*[:=]\s*['\"]?"
            rb"(?!(?:<redacted>|redacted|secret[-_]?password|stored-password|"
            rb"changed-pass|new-pass|test-pass|password|pass|abc)\b)"
            rb"(?:(?:[^\s'\"\r\n]{12,}['\"])|"
            rb"(?=[^\s'\"\r\n]*\d)"
            rb"(?=[^\s'\"\r\n]*[!#$%&()*+,/:;<=>?@\[\]^_`{|}~-])"
            rb"[^\s'\"\r\n.]{12,})"
        ),
    ),
    (
        "JSON access token",
        re.compile(
            rb'"(?:access_token|refresh_token)"\s*:\s*"'
            rb'[A-Za-z0-9._~+/=-]{20,}"'
        ),
    ),
    (
        "JWT-like token",
        re.compile(
            rb"\beyJ[A-Za-z0-9_-]{10,}\."
            rb"[A-Za-z0-9_-]{10,}\."
            rb"[A-Za-z0-9_-]{8,}\b"
        ),
    ),
    ("UniFi token cookie", re.compile(rb"\bTOKEN=[A-Za-z0-9._~+/=-]{20,}\b")),
)
SECRET_PATH_PATTERNS = (
    re.compile(r"(^|/)\.storage(?:/|$)"),
    re.compile(r"(^|/)home-assistant_v2\.db(?:-(?:wal|shm))?$"),
    re.compile(r"(^|/)ha_frontend_smoke\.env$"),
    re.compile(r"(^|/)\.env$"),
)
GENERATED_ARTIFACT_PATH_PATTERNS = (
    re.compile(r"(^|/)__pycache__/"),
    re.compile(r"\.py[co]$"),
    re.compile(r"(^|/)\.coverage$"),
    re.compile(r"(^|/)coverage\.xml$"),
    re.compile(r"(^|/)htmlcov(?:/|$)"),
    re.compile(r"(^|/)\.(?:mypy|pytest|ruff)_cache(?:/|$)"),
)
OFFICIAL_VENDOR_ASSET_PATH_PATTERNS = (
    re.compile(
        r"(^|/)(?:ubiquiti|unifi)[_-]?(?:logo|brand|mark|icon)[^/]*"
        r"\.(?:png|svg|jpg|jpeg|webp)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"(^|/)(?:ubiquiti|unifi)/.*\.(?:png|svg|jpg|jpeg|webp)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"(^|/)(?:official|vendor)[_-]?(?:ubiquiti|unifi|ui)?[_-]?"
        r"(?:logo|brand|mark|icon)[^/]*\.(?:png|svg|jpg|jpeg|webp)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"(^|/)(?:unifi|ubiquiti)[^/]*\.(?:js|css|map|html)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"(^|/)(?:unifi|ubiquiti)/.*\.(?:js|css|map|html)$",
        re.IGNORECASE,
    ),
)
_COPY = b"Copy" + b"right"
_UI = b"Ubi" + b"quiti"
_ALL_RESERVED = b"All rights " + b"reserved"
_LICENSED_PROP = b"licensed " + b"proprietary"
_PROP_CONFIDENTIAL = b"proprietary " + b"and confidential"
_UNAUTHORIZED = b"unauthorized " + b"use"
_IPV4_LITERAL_PATTERN = re.compile(rb"\b(?:\d{1,3}\.){3}\d{1,3}\b")
PROPRIETARY_VENDOR_CONTENT_PATTERNS = (
    (
        "Ubiquiti copyright header",
        re.compile(rb"(?:" + _COPY + rb"|\(c\)|\xc2\xa9).{0,80}" + _UI, re.I | re.S),
    ),
    (
        "Ubiquiti all-rights-reserved marker",
        re.compile(_UI + rb" Inc\.?.{0,80}" + _ALL_RESERVED, re.I | re.S),
    ),
    (
        "proprietary license marker",
        re.compile(rb"(?:" + _LICENSED_PROP + rb"|" + _PROP_CONFIDENTIAL + rb")", re.I),
    ),
    (
        "vendor redistribution prohibition",
        re.compile(
            _UNAUTHORIZED + rb".{0,80}(?:duplication|distribution)",
            re.I | re.S,
        ),
    ),
)
BRANDING_CLAIM_PATTERNS = (
    (
        "official vendor integration claim",
        re.compile(
            rb"\bofficial\s+(?:Ubiquiti|UniFi|UI)\s+"
            rb"(?:integration|app|add-?on|project|repository)\b",
            re.I,
        ),
    ),
    (
        "vendor endorsement claim",
        re.compile(
            rb"\b(?:certified|endorsed|approved)\s+by\s+"
            rb"(?:Ubiquiti|UniFi|UI)\b",
            re.I,
        ),
    ),
    (
        "vendor-owned project claim",
        re.compile(
            rb"\b(?:Ubiquiti|UniFi|UI)\s+"
            rb"(?:official|certified|endorsed|approved)\b",
            re.I,
        ),
    ),
)


def _configured_local_marker_patterns() -> tuple[re.Pattern[bytes], ...]:
    """Return optional local marker denylist patterns from environment."""
    raw = os.environ.get(FORBIDDEN_MARKERS_ENV, "")
    markers = [
        marker.strip()
        for marker in re.split(r"[\n,]", raw)
        if len(marker.strip()) >= 3
    ]
    return tuple(
        re.compile(
            rb"(?<![A-Za-z0-9])"
            + re.escape(marker.encode("utf-8"))
            + rb"(?![A-Za-z0-9])",
            re.I,
        )
        for marker in markers
    )


def _is_rfc1918_ipv4(value: bytes) -> bool:
    """Return whether an IPv4 literal is from RFC1918 private space."""
    try:
        address = ipaddress.IPv4Address(value.decode("ascii"))
    except ValueError:
        return False

    address_int = int(address)
    first = address_int >> 24
    second = (address_int >> 16) & 0xFF
    return (
        first == 0x0A
        or (first == 0xAC and 0x10 <= second <= 0x1F)
        or (first == 0xC0 and second == 0xA8)
    )


def local_identifier_issues(label: str, data: bytes) -> list[str]:
    """Return generic local identity findings without exposing raw values."""
    issues: list[str] = []
    if any(_is_rfc1918_ipv4(match.group(0)) for match in _IPV4_LITERAL_PATTERN.finditer(data)):
        issues.append(f"{label}: possible private local IPv4 address")

    if any(pattern.search(data) for pattern in _configured_local_marker_patterns()):
        issues.append(f"{label}: possible configured local identifier marker")

    return issues


def fail(message: str) -> None:
    """Print failure message and exit."""
    print(f"[FAIL] {message}")
    raise SystemExit(1)


def ok(message: str) -> None:
    """Print success message."""
    print(f"[OK] {message}")


def _path_matches_any(path: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    """Return whether a normalized path matches any pattern."""
    return any(pattern.search(path) for pattern in patterns)


def _tracked_file_hygiene_issues(root: Path, tracked_paths: list[str]) -> list[str]:
    """Return legal, secret and artifact issues in tracked files."""
    failures: list[str] = []

    for relative in tracked_paths:
        normalized = relative.replace("\\", "/")
        if _path_matches_any(normalized, SECRET_PATH_PATTERNS):
            failures.append(f"tracked secret-like path: {relative}")
            continue
        if _path_matches_any(normalized, GENERATED_ARTIFACT_PATH_PATTERNS):
            failures.append(f"tracked generated artifact path: {relative}")
            continue
        if _path_matches_any(normalized, OFFICIAL_VENDOR_ASSET_PATH_PATTERNS):
            failures.append(f"tracked official/vendor asset path: {relative}")
            continue
        local_path_issues = local_identifier_issues(
            "tracked path",
            normalized.encode("utf-8", errors="ignore"),
        )
        if local_path_issues:
            failures.extend(local_path_issues)
            continue

        path = root / relative
        try:
            data = path.read_bytes()
        except OSError as err:
            failures.append(f"could not read tracked file {relative}: {err}")
            continue

        if b"\0" in data[:4096]:
            continue

        for label, pattern in SECRET_PATTERNS:
            if pattern.search(data):
                failures.append(f"{relative}: possible {label}")
                break

        for label, pattern in PROPRIETARY_VENDOR_CONTENT_PATTERNS:
            if pattern.search(data):
                failures.append(f"{relative}: possible {label}")
                break

        failures.extend(local_identifier_issues(relative, data))

        for label, pattern in BRANDING_CLAIM_PATTERNS:
            if pattern.search(data):
                failures.append(f"{relative}: possible {label}")
                break

    return failures
