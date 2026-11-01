#!/usr/bin/env python3
"""Validate release ZIP layout, privacy and legal hygiene."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
import sys
from zipfile import BadZipFile, ZipFile


SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from repo_hygiene import (  # noqa: E402
    BRANDING_CLAIM_PATTERNS,
    GENERATED_ARTIFACT_PATH_PATTERNS,
    OFFICIAL_VENDOR_ASSET_PATH_PATTERNS,
    PROPRIETARY_VENDOR_CONTENT_PATTERNS,
    SECRET_PATH_PATTERNS,
    _path_matches_any,
    content_scan_issues,
    fail,
    local_identifier_issues,
    ok,
)


EXPECTED_ROOT = "unifi_unas/"
REQUIRED_MEMBERS = (
    "unifi_unas/__init__.py",
    "unifi_unas/manifest.json",
    "unifi_unas/LICENSE",
)


def _normalized_member_name(name: str) -> str:
    """Return a normalized POSIX ZIP member name."""
    return name.replace("\\", "/")


def _has_unsafe_member_path(name: str) -> bool:
    """Return whether a ZIP member name could escape the release root."""
    path = PurePosixPath(name)
    return path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts)


def _release_zip_issues(zip_path: Path) -> list[str]:
    """Return release ZIP privacy, legal and layout issues."""
    issues: list[str] = []
    if not zip_path.exists():
        return [f"missing release ZIP: {zip_path}"]
    if zip_path.is_dir():
        return [f"release ZIP path is a directory: {zip_path}"]

    try:
        with ZipFile(zip_path) as archive:
            infos = archive.infolist()
            names = {_normalized_member_name(info.filename) for info in infos}
            if not names:
                return ["release ZIP is empty"]

            for required in REQUIRED_MEMBERS:
                if required not in names:
                    issues.append(f"missing required member: {required}")

            for info in infos:
                member = _normalized_member_name(info.filename)
                if not member:
                    issues.append("empty ZIP member name")
                    continue

                if _has_unsafe_member_path(member):
                    issues.append(f"unsafe ZIP member path: {member}")
                    continue

                if not member.startswith(EXPECTED_ROOT):
                    issues.append(f"unexpected member outside {EXPECTED_ROOT}: {member}")
                    continue

                if member.endswith("/"):
                    continue

                if _path_matches_any(member, SECRET_PATH_PATTERNS):
                    issues.append(f"secret-like path in release ZIP: {member}")
                    continue
                if _path_matches_any(member, GENERATED_ARTIFACT_PATH_PATTERNS):
                    issues.append(f"generated artifact in release ZIP: {member}")
                    continue
                if _path_matches_any(member, OFFICIAL_VENDOR_ASSET_PATH_PATTERNS):
                    issues.append(f"official/vendor asset path in release ZIP: {member}")
                    continue
                local_path_issues = local_identifier_issues(
                    "release ZIP member path",
                    member.encode("utf-8", errors="ignore"),
                )
                if local_path_issues:
                    issues.extend(local_path_issues)
                    continue

                data = archive.read(info)
                if member == "unifi_unas/LICENSE" and data != (
                    SCRIPTS_DIR.parent / "LICENSE"
                ).read_bytes():
                    issues.append("release LICENSE differs from the repository license")
                if b"\0" in data[:4096]:
                    continue

                issues.extend(content_scan_issues(member, data))

                for label, pattern in PROPRIETARY_VENDOR_CONTENT_PATTERNS:
                    if pattern.search(data):
                        issues.append(f"{member}: possible {label}")
                        break

                issues.extend(local_identifier_issues(member, data))

                for label, pattern in BRANDING_CLAIM_PATTERNS:
                    if pattern.search(data):
                        issues.append(f"{member}: possible {label}")
                        break
    except BadZipFile:
        return [f"invalid ZIP file: {zip_path}"]

    return issues


def check_release_zip(zip_path: Path) -> None:
    """Fail if the release ZIP is unsafe for publication."""
    issues = _release_zip_issues(zip_path)
    if issues:
        fail("release ZIP privacy/legal/layout scan failed:\n" + "\n".join(issues))
    ok("Release ZIP privacy, legal and layout scan passed")


def main(argv: list[str] | None = None) -> None:
    """Run the release ZIP check."""
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        fail("Usage: scripts/check_release_zip.py <release-zip>")
    check_release_zip(Path(args[0]))


if __name__ == "__main__":
    main()
