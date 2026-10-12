#!/usr/bin/env python3
"""Repository checks for HA/HACS compatibility and baseline quality."""

from __future__ import annotations

import configparser
import ipaddress
import json
import os
import re
# This script only uses fixed argv lists.
import subprocess  # nosec B404
import shutil
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
INTEGRATION_DIR = ROOT / "custom_components" / "unifi_unas"
MANIFEST_PATH = INTEGRATION_DIR / "manifest.json"
HACS_PATH = ROOT / "hacs.json"
README_PATH = ROOT / "README.md"
CHANGELOG_PATH = ROOT / "CHANGELOG.md"
RELEASE_NOTES_DIR = ROOT / ".github" / "release-notes"
LICENSE_PATH = ROOT / "LICENSE"
LEGAL_PATH = ROOT / "docs" / "legal.md"
LTS_PATH = ROOT / "docs" / "lts.md"
STRINGS_PATH = INTEGRATION_DIR / "strings.json"
ICONS_PATH = INTEGRATION_DIR / "icons.json"
TRANSLATION_DIR = INTEGRATION_DIR / "translations"
QUALITY_SCALE_PATH = INTEGRATION_DIR / "quality_scale.yaml"
CONFIG_FLOW_PATH = INTEGRATION_DIR / "config_flow.py"
PY_TYPED_PATH = INTEGRATION_DIR / "py.typed"
COVERAGE_PATH = ROOT / ".coveragerc"
MYPY_PATH = ROOT / "mypy.ini"
VALIDATE_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "validate.yml"
RELEASE_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "release.yml"
RELEASE_ZIP_CHECK_PATH = ROOT / "scripts" / "check_release_zip.py"
GITHUB_SURFACE_AUDIT_PATH = ROOT / "scripts" / "audit_github_public_surfaces.py"

QUALITY_RULES_BY_TIER = {
    "bronze": (
        "action-setup",
        "appropriate-polling",
        "brands",
        "common-modules",
        "config-flow-test-coverage",
        "config-flow",
        "dependency-transparency",
        "docs-actions",
        "docs-high-level-description",
        "docs-installation-instructions",
        "docs-removal-instructions",
        "entity-event-setup",
        "entity-unique-id",
        "has-entity-name",
        "runtime-data",
        "test-before-configure",
        "test-before-setup",
        "unique-config-entry",
    ),
    "silver": (
        "action-exceptions",
        "config-entry-unloading",
        "docs-configuration-parameters",
        "docs-installation-parameters",
        "entity-unavailable",
        "integration-owner",
        "log-when-unavailable",
        "parallel-updates",
        "reauthentication-flow",
        "test-coverage",
    ),
    "gold": (
        "devices",
        "diagnostics",
        "discovery-update-info",
        "discovery",
        "docs-data-update",
        "docs-examples",
        "docs-known-limitations",
        "docs-supported-devices",
        "docs-supported-functions",
        "docs-troubleshooting",
        "docs-use-cases",
        "dynamic-devices",
        "entity-category",
        "entity-device-class",
        "entity-disabled-by-default",
        "entity-translations",
        "exception-translations",
        "icon-translations",
        "reconfiguration-flow",
        "repair-issues",
        "stale-devices",
    ),
    "platinum": (
        "async-dependency",
        "inject-websession",
        "strict-typing",
    ),
}
BRONZE_QUALITY_RULES = QUALITY_RULES_BY_TIER["bronze"]
QUALITY_RULE_STATUSES = {"done", "todo", "exempt"}
PLATFORM_PARALLEL_UPDATES = {
    "binary_sensor.py": 0,
    "button.py": 1,
    "number.py": 1,
    "select.py": 1,
    "sensor.py": 0,
    "switch.py": 1,
    "time.py": 1,
    "update.py": 1,
}
TYPED_CONFIG_ENTRY_FILES = (
    "__init__.py",
    "binary_sensor.py",
    "button.py",
    "coordinator.py",
    "device.py",
    "diagnostics.py",
    "entities.py",
    "entity_base.py",
    "entry_reload.py",
    "number.py",
    "runtime.py",
    "select.py",
    "services.py",
    "snapshot_entities.py",
    "snapshot_repairs.py",
    "switch.py",
    "time.py",
    "update.py",
)
DEPRECATED_NODE20_WORKFLOW_ACTIONS = {
    "actions/checkout@v4": "actions/checkout@v6",
    "actions/setup-python@v5": "actions/setup-python@v6",
    "actions/upload-artifact@v4": "actions/upload-artifact@v7",
    "softprops/action-gh-release@v2": "softprops/action-gh-release@v3",
}
RELEASE_WORKFLOW_PRIVACY_MARKERS = (
    "uses: actions/setup-python@v6",
    "python scripts/audit_github_public_surfaces.py --repo \"$GITHUB_REPOSITORY\"",
    "python scripts/check_repo.py",
    "python scripts/check_release_zip.py dist/unifi_unas.zip",
)
VALIDATE_WORKFLOW_HA_REQUIREMENT_PATTERN = re.compile(
    r"homeassistant==\$\{\{\s*matrix\.homeassistant\s*\}\}"
)
VALIDATE_WORKFLOW_PYTHON_PATTERN = re.compile(r"python:\s*[\"']?3\.14[\"']?")
VALIDATE_WORKFLOW_MINIMUM_PYTHON_PATTERN = re.compile(r"python:\s*[\"']?3\.12[\"']?")
RELEASE_WORKFLOW_PYTHON_PATTERN = re.compile(r"python-version:\s*[\"']?3\.14[\"']?")
CURRENT_HOMEASSISTANT_TARGET = "2026.10.0"
CURRENT_PYTEST_HOMEASSISTANT = "0.13.371"
WORKFLOW_HOMEASSISTANT_MATRIX_PATTERN = re.compile(
    r"homeassistant:\s*[\"']([^\"']+)[\"']"
)
CONFIG_FLOW_RELOAD_METHOD_PATTERNS = {
    "async_schedule_reload": re.compile(r"\.async_schedule_reload\("),
    "async_reload": re.compile(r"\.async_reload\("),
    "async_update_reload_and_abort": re.compile(r"\basync_update_reload_and_abort\("),
}
DEPRECATED_HOMEASSISTANT_API_PATTERNS = {
    "DeviceEntry.primary_config_entry": re.compile(r"\bprimary_config_entry\b"),
    "DeviceEntry.config_entries_subentries": re.compile(
        r"\bconfig_entries_subentries\b"
    ),
    "DeviceEntry.config_entries": re.compile(
        r"\b(?:device|device_entry)\.config_entries\b"
    ),
}

EXPECTED_README_TITLE = "Home Assistant integration for UniFi Drive / UNAS (Unofficial)"
README_LEGAL_MARKERS = (
    EXPECTED_README_TITLE,
    "[docs/legal.md](docs/legal.md)",
    "unofficial community integration",
    "does not claim affiliation",
    "Ubiquiti Inc.",
    "does not include official Ubiquiti logos",
    "proprietary Ubiquiti source code",
)
LEGAL_DOC_MARKERS = (
    "unofficial community project",
    "no affiliation",
    "descriptive compatibility references",
    "official Ubiquiti logos",
    "proprietary Ubiquiti source code",
    "observed interoperability behavior only",
)
README_BRONZE_DOC_MARKERS = (
    "## Current Maturity",
    "## Installation",
    "## Removal",
    "## Services",
    "## Privacy And Diagnostics",
    "## Known Limitations",
    "## Troubleshooting",
)
README_HIGHER_QUALITY_DOC_MARKERS = (
    "## Supported Devices",
    "## Data Updates",
    "## Use Cases And Automation Examples",
    "## Silver Gold Platinum Roadmap",
)

MOJIBAKE_MARKERS = ("\u00c3", "\u00c2", "\u00e2\u20ac", "\ufffd")
TEXT_GLOBS = ("*.md", "*.json", "*.py", "*.yml", "*.yaml", "*.ini", "*.example")
IGNORED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tmp-pip",
    ".tmp-venvs",
    ".venv",
    "__pycache__",
    "node_modules",
}
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


def load_json(path: Path) -> dict[str, Any]:
    """Load JSON file with UTF-8 and no BOM."""
    text = path.read_text(encoding="utf-8")
    if text.startswith("\ufeff"):
        fail(f"{path} has UTF-8 BOM; use UTF-8 without BOM")
    data = json.loads(text)
    if not isinstance(data, dict):
        fail(f"{path} must contain a JSON object")
    return data


def _hacs_homeassistant_minimum() -> str:
    """Return the Home Assistant minimum version advertised to HACS users."""
    hacs = load_json(HACS_PATH)
    minimum = hacs.get("homeassistant")
    if not isinstance(minimum, str) or not minimum.strip():
        fail("hacs.json must define a non-empty homeassistant minimum version")
    return minimum


def _workflow_homeassistant_versions(workflow_text: str) -> set[str]:
    """Return Home Assistant matrix versions from the validate workflow."""
    return set(WORKFLOW_HOMEASSISTANT_MATRIX_PATTERN.findall(workflow_text))


def ensure_file(path: Path) -> None:
    """Ensure a file exists and is not empty."""
    if not path.exists():
        fail(f"Missing file: {path}")
    if path.stat().st_size == 0:
        fail(f"Empty file: {path}")
    ok(f"Found file: {path.name}")


def check_mojibake(path: Path) -> None:
    """Fail if BOM or likely mojibake markers are present."""
    content = path.read_text(encoding="utf-8")
    if content.startswith("\ufeff"):
        fail(f"{path} has UTF-8 BOM; use UTF-8 without BOM")
    for marker in MOJIBAKE_MARKERS:
        if marker in content:
            fail(f"Mojibake marker {marker!r} found in {path}")
    ok(f"No mojibake markers in {path.relative_to(ROOT)}")


def check_all_text_files_for_mojibake() -> None:
    """Fail if likely mojibake markers are present in repo text files."""
    checked = 0
    for pattern in TEXT_GLOBS:
        for path in ROOT.rglob(pattern):
            if any(part in IGNORED_DIRS or part.startswith(".venv") for part in path.parts):
                continue
            check_mojibake(path)
            checked += 1
    ok(f"Mojibake scan covered {checked} text files")


def _missing_text_markers(text: str, markers: tuple[str, ...]) -> list[str]:
    """Return required text markers that are missing, ignoring case and wraps."""
    normalized = " ".join(text.lower().split())
    return [
        marker
        for marker in markers
        if " ".join(marker.lower().split()) not in normalized
    ]


def check_legal_docs() -> None:
    """Validate legal/disclaimer text and asset-hygiene documentation."""
    readme = README_PATH.read_text(encoding="utf-8")
    legal = LEGAL_PATH.read_text(encoding="utf-8")

    missing_readme = _missing_text_markers(readme, README_LEGAL_MARKERS)
    if missing_readme:
        fail(f"README.md missing legal/branding markers: {missing_readme}")

    missing_legal = _missing_text_markers(legal, LEGAL_DOC_MARKERS)
    if missing_legal:
        fail(f"docs/legal.md missing legal/asset markers: {missing_legal}")

    ok("Legal disclaimer and asset hygiene docs validated")


def check_bronze_docs() -> None:
    """Validate core Bronze documentation sections."""
    readme = README_PATH.read_text(encoding="utf-8")
    markers = README_BRONZE_DOC_MARKERS + README_HIGHER_QUALITY_DOC_MARKERS
    missing = _missing_text_markers(readme, markers)
    if missing:
        fail(f"README.md missing quality-scale documentation markers: {missing}")
    ok("Quality-scale documentation sections validated")


def _tracked_file_paths() -> list[str]:
    """Return tracked paths from git."""
    git_bin = shutil.which("git")
    if git_bin is None:
        fail("Could not find git executable")

    # Fixed git argv, not user-controlled.
    proc = subprocess.run(  # nosec B603
        [git_bin, "ls-files", "-z", "--cached"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        fail("Could not list tracked files")
    return [path for path in proc.stdout.split("\0") if path]


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


def check_tracked_file_hygiene() -> None:
    """Fail on tracked secret material, generated artifacts or vendor assets."""
    failures = _tracked_file_hygiene_issues(ROOT, _tracked_file_paths())
    if failures:
        fail("tracked-file legal/secret scan failed:\n" + "\n".join(failures))
    ok("Tracked-file legal, asset and secret hygiene scan passed")


def check_manifest() -> None:
    """Validate HA manifest core fields."""
    manifest = load_json(MANIFEST_PATH)
    required_keys = {
        "domain",
        "name",
        "version",
        "config_flow",
        "documentation",
        "issue_tracker",
        "iot_class",
        "integration_type",
        "codeowners",
    }
    missing = sorted(required_keys - set(manifest))
    if missing:
        fail(f"manifest.json missing keys: {missing}")

    if manifest["domain"] != "unifi_unas":
        fail("manifest domain must be 'unifi_unas'")
    if manifest["config_flow"] is not True:
        fail("manifest config_flow must be true")
    if manifest["integration_type"] != "device":
        fail("manifest integration_type must be 'device'")
    if not isinstance(manifest.get("requirements"), list):
        fail("manifest requirements must be a list")
    if not manifest.get("codeowners"):
        fail("manifest codeowners must not be empty")
    ok("manifest.json validated")


def check_entity_name_rule() -> None:
    """Fail if an entity explicitly opts out of Home Assistant entity names."""
    offenders = []
    for path in INTEGRATION_DIR.glob("*.py"):
        content = path.read_text(encoding="utf-8")
        if re.search(r"_attr_has_entity_name\s*=\s*False\b", content):
            try:
                offenders.append(path.relative_to(ROOT).as_posix())
            except ValueError:
                offenders.append(path.as_posix())
    if offenders:
        fail("Entities must not opt out of has_entity_name: " + ", ".join(offenders))
    ok("Entity has_entity_name rule validated")


def _manifest_version_tag(manifest: dict[str, Any]) -> str:
    """Return the release tag expected for the manifest version."""
    version = manifest.get("version")
    if not isinstance(version, str) or not version.strip():
        fail("manifest.json version must be a non-empty string")
    return version if version.startswith("v") else f"v{version}"


def _has_changelog_release_entry(changelog: str, version_tag: str) -> bool:
    """Return whether the changelog has a release heading for a tag."""
    return (
        re.search(
            rf"^##\s+{re.escape(version_tag)}(?:\s|$)",
            changelog,
            re.MULTILINE,
        )
        is not None
    )


def check_hacs() -> None:
    """Validate HACS metadata."""
    hacs = load_json(HACS_PATH)
    manifest = load_json(MANIFEST_PATH)
    forbidden_keys = {"filename", "zip_release"}
    forbidden = sorted(forbidden_keys & set(hacs))
    if forbidden:
        fail(f"hacs.json must not define release artifact keys: {forbidden}")
    supported_keys = {
        "name",
        "content_in_root",
        "render_readme",
        "hide_default_branch",
        "country",
        "homeassistant",
        "hacs",
        "persistent_directory",
    }
    unsupported = sorted(set(hacs) - supported_keys)
    if unsupported:
        fail(f"hacs.json contains unsupported keys: {unsupported}")
    expected_name = manifest.get("name")
    if not isinstance(expected_name, str) or not expected_name.strip():
        fail("manifest.json name must be a non-empty string")
    if hacs.get("name") != expected_name:
        fail(f"hacs.json name must match manifest.json name {expected_name!r}")
    _hacs_homeassistant_minimum()
    if hacs.get("render_readme") is not True:
        fail("hacs.json must set render_readme true when info.md is absent")
    ok("hacs.json validated")


def check_release_metadata() -> None:
    """Validate release files are aligned with the manifest version."""
    manifest = load_json(MANIFEST_PATH)
    version_tag = _manifest_version_tag(manifest)
    changelog = CHANGELOG_PATH.read_text(encoding="utf-8")
    if not _has_changelog_release_entry(changelog, version_tag):
        fail(f"CHANGELOG.md must contain a release entry for {version_tag}")

    release_notes = RELEASE_NOTES_DIR / f"{version_tag}.md"
    if not release_notes.exists():
        fail(f"Missing release notes file: {release_notes.relative_to(ROOT)}")
    if release_notes.stat().st_size == 0:
        fail(f"Empty release notes file: {release_notes.relative_to(ROOT)}")
    ok(f"Release metadata validated for {version_tag}")


def check_translations() -> None:
    """Validate translation files are parseable JSON and structurally aligned."""
    if not TRANSLATION_DIR.exists():
        fail(f"Missing translations directory: {TRANSLATION_DIR}")

    strings = load_json(STRINGS_PATH)
    _check_config_step_data_descriptions(strings, STRINGS_PATH.name)
    source_keys = _flatten_keys(strings)
    for file in sorted(TRANSLATION_DIR.glob("*.json")):
        translation = load_json(file)
        _check_config_step_data_descriptions(translation, file.name)
        translation_keys = _flatten_keys(translation)
        if translation_keys != source_keys:
            missing = sorted(source_keys - translation_keys)
            extra = sorted(translation_keys - source_keys)
            fail(
                f"Translation keys mismatch in {file.name}; "
                f"missing={missing}, extra={extra}"
            )
        ok(f"Translation JSON valid: {file.name}")


def _check_config_step_data_descriptions(
    translation: dict[str, Any],
    label: str,
) -> None:
    """Require Home Assistant config-flow descriptions for every field."""
    config = translation.get("config", {})
    steps = config.get("step", {}) if isinstance(config, dict) else {}
    if not isinstance(steps, dict):
        fail(f"{label} config.step must be a JSON object")

    for step_id, step in steps.items():
        if not isinstance(step, dict):
            continue
        data = step.get("data", {})
        if not isinstance(data, dict) or not data:
            continue
        data_description = step.get("data_description", {})
        if not isinstance(data_description, dict):
            fail(f"{label} config.step.{step_id}.data_description must be an object")
        missing = sorted(set(data) - set(data_description))
        if missing:
            fail(
                f"{label} config.step.{step_id} missing data_description keys: "
                f"{missing}"
            )


def _flatten_keys(value: Any, prefix: str = "") -> set[str]:
    """Return all nested JSON key paths."""
    if not isinstance(value, dict):
        return {prefix} if prefix else set()

    keys: set[str] = set()
    for key, item in value.items():
        child = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(item, dict):
            keys.update(_flatten_keys(item, child))
        else:
            keys.add(child)
    return keys


def check_python_compile() -> None:
    """Compile integration sources."""
    # Fixed compileall argv, not user-controlled.
    proc = subprocess.run(  # nosec B603
        [sys.executable, "-m", "compileall", str(INTEGRATION_DIR)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        fail("Python compileall failed")
    ok("Python compileall passed")


def _load_quality_scale_rules(path: Path) -> dict[str, str]:
    """Load simple quality_scale.yaml rule statuses without extra dependencies."""
    rules: dict[str, str] = {}
    current_rule: str | None = None
    in_rules = False

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line:
            continue
        if line == "rules:":
            in_rules = True
            current_rule = None
            continue
        if not in_rules:
            continue

        direct = re.fullmatch(r"  ([a-z0-9-]+):(?:\s*(.+))?", line)
        if direct:
            current_rule = direct.group(1)
            status = (direct.group(2) or "").strip()
            if status:
                rules[current_rule] = status
            continue

        nested_status = re.fullmatch(r"    status:\s*(.+)", line)
        if nested_status and current_rule:
            rules[current_rule] = nested_status.group(1).strip()

    return rules


def check_quality_scale() -> None:
    """Validate quality-scale rule tracking without overclaiming."""
    rules = _load_quality_scale_rules(QUALITY_SCALE_PATH)
    all_expected = {
        rule for rules_for_tier in QUALITY_RULES_BY_TIER.values() for rule in rules_for_tier
    }
    missing_all = sorted(all_expected - set(rules))
    if missing_all:
        fail(f"quality_scale.yaml missing quality-scale rules: {missing_all}")

    invalid_statuses = {
        rule: status for rule, status in rules.items() if status not in QUALITY_RULE_STATUSES
    }
    if invalid_statuses:
        fail(f"quality_scale.yaml has unsupported statuses: {invalid_statuses}")

    required_quality_rules = (
        QUALITY_RULES_BY_TIER["bronze"]
        + QUALITY_RULES_BY_TIER["silver"]
        + QUALITY_RULES_BY_TIER["gold"]
    )
    missing = [rule for rule in required_quality_rules if rule not in rules]
    if missing:
        fail(f"quality_scale.yaml missing Bronze/Silver/Gold rules: {missing}")

    incomplete = {
        rule: rules[rule]
        for rule in required_quality_rules
        if rules[rule] != "done"
    }
    if incomplete:
        fail(f"Bronze, Silver and Gold quality rules must be done: {incomplete}")

    ok("quality_scale.yaml quality status validated")


def check_coverage_gate() -> None:
    """Validate that CI enforces the Silver coverage baseline."""
    coverage_text = COVERAGE_PATH.read_text(encoding="utf-8")
    workflow_text = VALIDATE_WORKFLOW_PATH.read_text(encoding="utf-8")

    if "source = custom_components/unifi_unas" not in coverage_text:
        fail(".coveragerc must measure custom_components/unifi_unas")
    if "fail_under = 95" not in coverage_text:
        fail(".coveragerc must enforce at least 95% coverage")
    if "coverage run -m pytest -q" not in workflow_text:
        fail("Validate workflow must run pytest through coverage")
    if "coverage report" not in workflow_text:
        fail("Validate workflow must report/enforce coverage")
    ok("Coverage gate validated")


def check_config_flow_reload_methods() -> None:
    """Avoid config-flow reload calls that conflict with update listeners."""
    config_flow_text = CONFIG_FLOW_PATH.read_text(encoding="utf-8")
    offenders = [
        method
        for method, pattern in CONFIG_FLOW_RELOAD_METHOD_PATTERNS.items()
        if pattern.search(config_flow_text)
    ]

    if offenders:
        fail(
            "config_flow.py must use async_update_and_abort without reload methods: "
            + ", ".join(offenders)
        )
    ok("Config-flow reload compatibility validated")


def check_homeassistant_deprecation_guards() -> None:
    """Reject Home Assistant APIs that are already deprecated for custom integrations."""
    offenders: list[str] = []
    for path in sorted(INTEGRATION_DIR.glob("*.py")):
        content = path.read_text(encoding="utf-8")
        for label, pattern in DEPRECATED_HOMEASSISTANT_API_PATTERNS.items():
            if pattern.search(content):
                offenders.append(f"{path.name}: {label}")

    if offenders:
        fail("Deprecated Home Assistant API usage found:\n" + "\n".join(offenders))
    ok("Home Assistant deprecation guard validated")


def check_workflow_action_versions() -> None:
    """Keep GitHub Actions workflows off deprecated Node.js 20 actions."""
    offenders: list[str] = []
    for workflow_path in (VALIDATE_WORKFLOW_PATH, RELEASE_WORKFLOW_PATH):
        workflow_text = workflow_path.read_text(encoding="utf-8")
        for deprecated, replacement in DEPRECATED_NODE20_WORKFLOW_ACTIONS.items():
            if re.search(rf"uses:\s*{re.escape(deprecated)}\b", workflow_text):
                offenders.append(
                    f"{workflow_path.relative_to(ROOT)}: replace {deprecated} "
                    f"with {replacement}"
                )

    if offenders:
        fail(
            "Deprecated Node.js 20 GitHub Actions remain:\n"
            + "\n".join(offenders)
        )
    ok("GitHub Actions Node.js runtime versions validated")


def check_workflow_python_versions() -> None:
    """Validate that Python-based CI jobs cover supported Python lines."""
    offenders: list[str] = []

    validate_text = VALIDATE_WORKFLOW_PATH.read_text(encoding="utf-8")
    if not VALIDATE_WORKFLOW_MINIMUM_PYTHON_PATTERN.search(validate_text):
        offenders.append(".github/workflows/validate.yml: missing Python 3.12 matrix leg")
    if not VALIDATE_WORKFLOW_PYTHON_PATTERN.search(validate_text):
        offenders.append(".github/workflows/validate.yml: missing Python 3.14 matrix leg")
    if "check-latest: true" not in validate_text:
        offenders.append(".github/workflows/validate.yml: missing check-latest")

    release_text = RELEASE_WORKFLOW_PATH.read_text(encoding="utf-8")
    if not RELEASE_WORKFLOW_PYTHON_PATTERN.search(release_text):
        offenders.append(".github/workflows/release.yml: missing Python 3.14")
    if "check-latest: true" not in release_text:
        offenders.append(".github/workflows/release.yml: missing check-latest")

    if offenders:
        fail("Workflow Python version gate failed:\n" + "\n".join(offenders))
    ok("Workflow Python compatibility versions validated")


def check_validate_workflow_homeassistant_target() -> None:
    """Validate that CI runs tests against the current Home Assistant target."""
    workflow_text = VALIDATE_WORKFLOW_PATH.read_text(encoding="utf-8")
    workflow_versions = _workflow_homeassistant_versions(workflow_text)
    hacs_minimum = _hacs_homeassistant_minimum()
    missing: list[str] = []

    if hacs_minimum not in workflow_versions:
        missing.append(f"Home Assistant HACS minimum matrix leg {hacs_minimum}")
    if CURRENT_HOMEASSISTANT_TARGET not in workflow_versions:
        missing.append(f"Home Assistant current target matrix leg {CURRENT_HOMEASSISTANT_TARGET}")
    if '"0.13.152"' not in workflow_text:
        missing.append("pytest-homeassistant-custom-component 0.13.152")
    if f'"{CURRENT_PYTEST_HOMEASSISTANT}"' not in workflow_text:
        missing.append(
            "pytest-homeassistant-custom-component "
            f"{CURRENT_PYTEST_HOMEASSISTANT}"
        )
    if not VALIDATE_WORKFLOW_HA_REQUIREMENT_PATTERN.search(workflow_text):
        missing.append('"homeassistant==${{ matrix.homeassistant }}"')
    if "package_constraints.txt" not in workflow_text:
        missing.append("Home Assistant package constraints")
    if "pytest-homeassistant-custom-component==${{ matrix.pytest_homeassistant }}" not in workflow_text:
        missing.append('"pytest-homeassistant-custom-component==${{ matrix.pytest_homeassistant }}"')
    if "pip install --no-deps" not in workflow_text:
        missing.append("pytest-homeassistant dependency isolation")
    if 'Requirement(requirement).name == "homeassistant"' not in workflow_text:
        missing.append("pytest-homeassistant Home Assistant dependency filter")
    if "josepy<2.0; python_version < '3.13'" not in workflow_text:
        missing.append("Python 3.12 josepy compatibility pin")
    if "md.version(\"homeassistant\")" not in workflow_text:
        missing.append("Home Assistant installed-version check")
    if "version != expected" not in workflow_text:
        missing.append("Home Assistant exact version assertion")

    if missing:
        fail(f"Validate workflow missing Home Assistant compatibility gates: {missing}")
    ok("Validate workflow Home Assistant compatibility targets validated")


def check_release_workflow_privacy_gates() -> None:
    """Validate that published release assets pass privacy and layout checks."""
    workflow_text = RELEASE_WORKFLOW_PATH.read_text(encoding="utf-8")
    missing = [
        marker for marker in RELEASE_WORKFLOW_PRIVACY_MARKERS if marker not in workflow_text
    ]
    if missing:
        fail(f"Release workflow missing privacy/layout gates: {missing}")
    ok("Release workflow privacy/layout gates validated")


def _platform_parallel_updates(path: Path) -> int | None:
    """Return the platform PARALLEL_UPDATES value if it is declared."""
    match = re.search(
        r"^PARALLEL_UPDATES\s*=\s*(\d+)\s*$",
        path.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    return None if match is None else int(match.group(1))


def check_parallel_updates_rule() -> None:
    """Validate each platform declares a deliberate parallel update limit."""
    failures: list[str] = []
    for filename, expected in PLATFORM_PARALLEL_UPDATES.items():
        path = INTEGRATION_DIR / filename
        observed = _platform_parallel_updates(path)
        if observed is None:
            failures.append(f"{filename}: missing PARALLEL_UPDATES")
        elif observed != expected:
            failures.append(
                f"{filename}: expected PARALLEL_UPDATES = {expected}, got {observed}"
            )

    if failures:
        fail("parallel update declaration check failed:\n" + "\n".join(failures))
    ok("Platform PARALLEL_UPDATES declarations validated")


def _mypy_configured_files(path: Path) -> tuple[str, ...]:
    """Return source files listed in the mypy gate."""
    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")
    if not parser.has_section("mypy"):
        fail("mypy.ini must contain a [mypy] section")
    if parser.get("mypy", "strict", fallback="").strip().lower() != "true":
        fail("mypy.ini must set strict = True")
    if parser.get("mypy", "python_version", fallback="").strip() != "3.12":
        fail("mypy.ini must set python_version = 3.12")
    if parser.get("mypy", "follow_imports", fallback="").strip() != "skip":
        fail("mypy.ini must set follow_imports = skip")

    raw_files = parser.get("mypy", "files", fallback="")
    files = tuple(item.strip() for item in raw_files.split(",") if item.strip())
    if not files:
        fail("mypy.ini must list files for the tracked strict typing gate")
    duplicates = sorted({item for item in files if files.count(item) > 1})
    if duplicates:
        fail(f"mypy.ini contains duplicate file entries: {duplicates}")
    return files


def _relative_integration_path(path: Path) -> str:
    """Return a repo-relative integration path."""
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        # Tests monkeypatch INTEGRATION_DIR into a temporary repo-like tree.
        return path.relative_to(INTEGRATION_DIR.parents[1]).as_posix()


def check_strict_typing_foundation() -> None:
    """Validate the runtime-data typing baseline for Platinum readiness."""
    if not PY_TYPED_PATH.exists():
        fail("custom_components/unifi_unas/py.typed is required for PEP 561 typing")
    if not MYPY_PATH.exists():
        fail("mypy.ini is required for the tracked strict typing gate")

    runtime_content = (INTEGRATION_DIR / "runtime.py").read_text(encoding="utf-8")
    if "UnifiDriveConfigEntry" not in runtime_content:
        fail("runtime.py must define UnifiDriveConfigEntry")
    if "ConfigEntry[UnifiUnasCoordinator]" not in runtime_content:
        fail("UnifiDriveConfigEntry must bind ConfigEntry runtime_data to coordinator")

    offenders: list[str] = []
    for filename in TYPED_CONFIG_ENTRY_FILES:
        path = INTEGRATION_DIR / filename
        content = path.read_text(encoding="utf-8")
        if filename != "runtime.py" and "UnifiDriveConfigEntry" not in content:
            offenders.append(f"{filename}: missing UnifiDriveConfigEntry")
        if filename != "runtime.py" and re.search(
            r"from homeassistant\.config_entries import ConfigEntry\b",
            content,
        ):
            offenders.append(f"{filename}: imports raw ConfigEntry")

    if offenders:
        fail("typed ConfigEntry baseline failed:\n" + "\n".join(offenders))

    mypy_files = _mypy_configured_files(MYPY_PATH)
    missing_files = [path for path in mypy_files if not (ROOT / path).is_file()]
    if missing_files:
        fail(f"mypy.ini references missing files: {missing_files}")

    expected_api_files = sorted(
        _relative_integration_path(path)
        for path in INTEGRATION_DIR.glob("api*.py")
    )
    missing_api_files = sorted(set(expected_api_files) - set(mypy_files))
    if missing_api_files:
        fail(f"mypy.ini must cover all API client modules: {missing_api_files}")

    workflow_text = VALIDATE_WORKFLOW_PATH.read_text(encoding="utf-8")
    required_mypy_files = (
        "custom_components/unifi_unas/__init__.py",
        "custom_components/unifi_unas/runtime.py",
        "custom_components/unifi_unas/api.py",
        "custom_components/unifi_unas/api_auth.py",
        "custom_components/unifi_unas/api_fan.py",
        "custom_components/unifi_unas/api_snapshot.py",
        "custom_components/unifi_unas/api_storage.py",
        "custom_components/unifi_unas/api_transport.py",
        "custom_components/unifi_unas/api_updates.py",
        "custom_components/unifi_unas/coordinator.py",
        "custom_components/unifi_unas/config_flow_validation.py",
        "custom_components/unifi_unas/diagnostics.py",
        "custom_components/unifi_unas/discovery.py",
        "custom_components/unifi_unas/discovery_identity.py",
        "custom_components/unifi_unas/entity_base.py",
        "custom_components/unifi_unas/services.py",
        "custom_components/unifi_unas/storage_helpers.py",
        "custom_components/unifi_unas/snapshot_payload.py",
    )
    missing_mypy = sorted(set(required_mypy_files) - set(mypy_files))
    if missing_mypy:
        fail(f"mypy.ini missing strict typing gate files: {missing_mypy}")
    if "mypy --config-file mypy.ini" not in workflow_text:
        fail("Validate workflow must run mypy --config-file mypy.ini")
    ok("Typed ConfigEntry runtime-data and mypy helper gate validated")


def check_exception_translations() -> None:
    """Validate that user-facing HA exceptions are raised with translation keys."""
    offenders: list[str] = []
    for path in sorted(INTEGRATION_DIR.glob("*.py")):
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if re.search(r"raise\s+(?:HomeAssistantError|ServiceValidationError)\(", line):
                offenders.append(f"{path.name}:{line_number}: {line.strip()}")
    if offenders:
        fail(
            "User-facing HA exceptions must use translation helpers:\n"
            + "\n".join(offenders)
        )

    helper_content = (INTEGRATION_DIR / "exceptions.py").read_text(encoding="utf-8")
    for helper in ("unifi_unas_error(", "unifi_unas_validation_error("):
        if helper not in helper_content:
            fail(f"exceptions.py missing translatable exception helper {helper}")
    ok("Exception translation baseline validated")


def check_icon_translations() -> None:
    """Validate the Gold icon translation baseline."""
    icons = load_json(ICONS_PATH)
    entity_icons = icons.get("entity")
    if not isinstance(entity_icons, dict) or not entity_icons:
        fail("icons.json must define entity icon translations")

    entity_keys = _entity_translation_keys()
    for platform, platform_icons in entity_icons.items():
        if not isinstance(platform_icons, dict):
            fail(f"icons.json entity.{platform} must be an object")
        known_keys = entity_keys.get(str(platform), set())
        unknown = sorted(str(key) for key in platform_icons if str(key) not in known_keys)
        if unknown:
            fail(f"icons.json has unknown {platform} translation keys: {unknown}")

    for platform in entity_keys:
        platform_icons = entity_icons.get(platform)
        if not isinstance(platform_icons, dict):
            fail(f"icons.json missing entity.{platform}")

    offenders: list[str] = []
    for path in sorted(INTEGRATION_DIR.glob("*.py")):
        content = path.read_text(encoding="utf-8")
        for pattern in (r"\b_attr_icon\b", r"icon\s*=\s*['\"]mdi:"):
            if re.search(pattern, content):
                offenders.append(path.name)
                break
    if offenders:
        fail(
            "Entity icons must be supplied through icons.json, not Python state: "
            + ", ".join(offenders)
        )
    ok("Icon translation baseline validated")


def _entity_translation_keys() -> dict[str, set[str]]:
    """Return all entity translation keys declared in strings.json."""
    strings = load_json(STRINGS_PATH)
    entity = strings.get("entity")
    if not isinstance(entity, dict):
        fail("strings.json must define entity translations")
    result: dict[str, set[str]] = {}
    for platform, entries in entity.items():
        if isinstance(entries, dict):
            result[str(platform)] = {str(key) for key in entries}
    return result


def main() -> None:
    """Run all checks."""
    ensure_file(README_PATH)
    ensure_file(CHANGELOG_PATH)
    ensure_file(LICENSE_PATH)
    ensure_file(LEGAL_PATH)
    ensure_file(LTS_PATH)
    ensure_file(MANIFEST_PATH)
    ensure_file(HACS_PATH)
    ensure_file(QUALITY_SCALE_PATH)
    ensure_file(ICONS_PATH)
    ensure_file(COVERAGE_PATH)
    ensure_file(MYPY_PATH)
    ensure_file(VALIDATE_WORKFLOW_PATH)
    ensure_file(RELEASE_WORKFLOW_PATH)
    ensure_file(RELEASE_ZIP_CHECK_PATH)
    ensure_file(GITHUB_SURFACE_AUDIT_PATH)

    check_all_text_files_for_mojibake()
    check_legal_docs()
    check_bronze_docs()
    check_tracked_file_hygiene()
    check_manifest()
    check_entity_name_rule()
    check_hacs()
    check_release_metadata()
    check_translations()
    check_quality_scale()
    check_coverage_gate()
    check_config_flow_reload_methods()
    check_homeassistant_deprecation_guards()
    check_workflow_action_versions()
    check_workflow_python_versions()
    check_validate_workflow_homeassistant_target()
    check_release_workflow_privacy_gates()
    check_parallel_updates_rule()
    check_strict_typing_foundation()
    check_exception_translations()
    check_icon_translations()
    check_python_compile()

    print("[OK] All checks passed")


if __name__ == "__main__":
    main()
