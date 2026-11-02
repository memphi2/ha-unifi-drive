"""Tests for release ZIP privacy and layout checks."""

from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

import pytest

from tests.module_stubs import ROOT, load_repo_module


def _load_release_zip_module():
    return load_repo_module(
        "check_release_zip_for_tests",
        ROOT / "scripts" / "check_release_zip.py",
    )


def _write_zip(path: Path, members: dict[str, str | bytes], *, include_license: bool = True) -> None:
    """Write a small ZIP fixture."""
    with ZipFile(path, "w") as archive:
        if include_license:
            archive.writestr("unifi_unas/LICENSE", (ROOT / "LICENSE").read_bytes())
        for name, content in members.items():
            archive.writestr(name, content)


@pytest.mark.parametrize("license_text", [None, "wrong license"])
@pytest.mark.parametrize("license_path", ["unifi_unas/LICENSE", "unifi_unas\\LICENSE"])
def test_release_zip_requires_correct_license(tmp_path, license_text, license_path) -> None:
    module = _load_release_zip_module()
    members = {"unifi_unas/__init__.py": "", "unifi_unas/manifest.json": "{}"}
    if license_text is not None:
        members[license_path] = license_text
    path = tmp_path / "release.zip"
    _write_zip(path, members, include_license=False)
    assert any("LICENSE" in issue for issue in module._release_zip_issues(path))


def test_release_zip_accepts_integration_root(tmp_path) -> None:
    """A release ZIP should contain only the integration root."""
    module = _load_release_zip_module()
    zip_path = tmp_path / "unifi_unas.zip"
    _write_zip(
        zip_path,
        {
            "unifi_unas/__init__.py": "# package\n",
            "unifi_unas/manifest.json": '{"domain": "unifi_unas"}\n',
        },
    )

    assert module._release_zip_issues(zip_path) == []


def test_release_zip_rejects_members_outside_integration_root(tmp_path) -> None:
    """Release ZIPs must not include repository-level files."""
    module = _load_release_zip_module()
    zip_path = tmp_path / "unifi_unas.zip"
    _write_zip(
        zip_path,
        {
            "unifi_unas/__init__.py": "# package\n",
            "unifi_unas/manifest.json": "{}\n",
            "README.md": "not part of the HACS release asset\n",
        },
    )

    assert any("outside unifi_unas/" in issue for issue in module._release_zip_issues(zip_path))


def test_release_zip_rejects_absolute_member_paths(tmp_path) -> None:
    """Absolute ZIP members must fail before root-prefix validation."""
    module = _load_release_zip_module()
    zip_path = tmp_path / "unifi_unas.zip"
    _write_zip(
        zip_path,
        {
            "/unifi_unas/__init__.py": "# package\n",
            "unifi_unas/manifest.json": "{}\n",
        },
    )

    issues = module._release_zip_issues(zip_path)

    assert any("unsafe ZIP member path" in issue for issue in issues)


def test_release_zip_rejects_backslash_absolute_member_paths(tmp_path) -> None:
    """Backslash absolute ZIP members must not bypass unsafe-path checks."""
    module = _load_release_zip_module()
    zip_path = tmp_path / "unifi_unas.zip"
    _write_zip(
        zip_path,
        {
            "\\unifi_unas\\__init__.py": "# package\n",
            "unifi_unas/manifest.json": "{}\n",
        },
    )

    issues = module._release_zip_issues(zip_path)

    assert any("unsafe ZIP member path" in issue for issue in issues)


def test_release_zip_rejects_parent_traversal_member_paths(tmp_path) -> None:
    """Parent traversal ZIP members must fail before content scanning."""
    module = _load_release_zip_module()
    zip_path = tmp_path / "unifi_unas.zip"
    _write_zip(
        zip_path,
        {
            "unifi_unas/__init__.py": "# package\n",
            "unifi_unas/manifest.json": "{}\n",
            "unifi_unas/../escape.txt": "escape\n",
        },
    )

    issues = module._release_zip_issues(zip_path)

    assert any("unsafe ZIP member path" in issue for issue in issues)


def test_release_zip_rejects_generated_artifacts(tmp_path) -> None:
    """Generated Python artifacts should never ship in the release ZIP."""
    module = _load_release_zip_module()
    zip_path = tmp_path / "unifi_unas.zip"
    _write_zip(
        zip_path,
        {
            "unifi_unas/__init__.py": "# package\n",
            "unifi_unas/manifest.json": "{}\n",
            "unifi_unas/__pycache__/api.cpython-313.pyc": b"\0pyc",
        },
    )

    assert any("generated artifact" in issue for issue in module._release_zip_issues(zip_path))


def test_release_zip_rejects_secret_material(tmp_path) -> None:
    """Token-like values should fail the release ZIP privacy scan."""
    module = _load_release_zip_module()
    zip_path = tmp_path / "unifi_unas.zip"
    token = ".".join(("eyJ" + "a" * 20, "b" * 20, "c" * 20))
    _write_zip(
        zip_path,
        {
            "unifi_unas/__init__.py": "# package\n",
            "unifi_unas/manifest.json": "{}\n",
            "unifi_unas/debug.txt": f"token={token}\n",
        },
    )

    assert any("JWT-like token" in issue for issue in module._release_zip_issues(zip_path))


def test_release_zip_rejects_local_identity_material(tmp_path) -> None:
    """Local address values should fail the release ZIP privacy scan."""
    module = _load_release_zip_module()
    zip_path = tmp_path / "unifi_unas.zip"
    _write_zip(
        zip_path,
        {
            "unifi_unas/__init__.py": "# package\n",
            "unifi_unas/manifest.json": "{}\n",
            "unifi_unas/debug.txt": "host=" + ".".join(("10", "1", "2", "3")) + "\n",
        },
    )

    assert any("private local IPv4 address" in issue for issue in module._release_zip_issues(zip_path))


def test_release_zip_rejects_configured_local_identity_marker(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configured local identity markers should fail the release ZIP scan."""
    module = _load_release_zip_module()
    marker = "private" + "-user"
    monkeypatch.setenv("UNIFI_UNAS_FORBIDDEN_MARKERS", marker)
    zip_path = tmp_path / "unifi_unas.zip"
    _write_zip(
        zip_path,
        {
            "unifi_unas/__init__.py": "# package\n",
            "unifi_unas/manifest.json": "{}\n",
            "unifi_unas/debug.txt": f"user={marker}\n",
        },
    )

    assert any("configured local identifier marker" in issue for issue in module._release_zip_issues(zip_path))


def test_release_zip_rejects_vendor_copyright_material(tmp_path) -> None:
    """Vendor copyright markers should fail the release ZIP legal scan."""
    module = _load_release_zip_module()
    zip_path = tmp_path / "unifi_unas.zip"
    _write_zip(
        zip_path,
        {
            "unifi_unas/__init__.py": "# package\n",
            "unifi_unas/manifest.json": "{}\n",
            "unifi_unas/vendor.txt": "Copy" + "right 2026 " + "Ubi" + "quiti\n",
        },
    )

    assert any("copyright header" in issue for issue in module._release_zip_issues(zip_path))


def test_release_zip_rejects_vendor_endorsement_claims(tmp_path) -> None:
    """Branding claims should fail the release ZIP legal scan."""
    module = _load_release_zip_module()
    zip_path = tmp_path / "unifi_unas.zip"
    _write_zip(
        zip_path,
        {
            "unifi_unas/__init__.py": "# package\n",
            "unifi_unas/manifest.json": "{}\n",
            "unifi_unas/claim.txt": "official " + "Ubi" + "quiti integration\n",
        },
    )

    assert any("official vendor integration claim" in issue for issue in module._release_zip_issues(zip_path))
