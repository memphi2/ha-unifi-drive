"""Verify credential detections never print matched contents in audit reports."""

from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

import pytest

from tests.module_stubs import ROOT, load_repo_module


def _detection_cases() -> list[tuple[str, str, str]]:
    """Construct synthetic fixtures without storing credential-shaped literals."""
    value = "synthetic-" + "value" * 4
    github = "gh" + "p_" + "a" * 40
    jwt = ".".join(("eyJ" + "a" * 20, "b" * 20, "c" * 20))
    key_header = "-----BEGIN " + "PRIVATE KEY-----"
    return [
        (key_header, "private key", key_header),
        (github, "github token", github),
        ("HA_SMOKE_" + f'PASSWORD="{value}"', "literal HA smoke password", value),
        ('"password": "' + value + '"', "plain password assignment", value),
        ('"access_token": "' + value + '"', "JSON access token", value),
        (jwt, "JWT-like token", jwt),
        ("TOKEN=" + value, "UniFi token cookie", value),
    ]


@pytest.mark.parametrize("payload,category,matched", _detection_cases())
@pytest.mark.parametrize("surface", ["repository", "archive", "github"])
def test_audit_failure_reports_categories_without_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    surface: str,
    payload: str,
    category: str,
    matched: str,
) -> None:
    """All three reporting entrypoints must reject fixtures without echoing them."""
    filename = {
        "repository": "check_repo.py",
        "archive": "check_release_zip.py",
        "github": "audit_github_public_surfaces.py",
    }[surface]
    module = load_repo_module(f"hygiene_output_{surface}", ROOT / "scripts" / filename)
    with pytest.raises(SystemExit) as error:
        if surface == "repository":
            (tmp_path / "fixture.txt").write_text(payload, encoding="utf-8")
            monkeypatch.setattr(module, "ROOT", tmp_path)
            monkeypatch.setattr(module, "_tracked_file_paths", lambda: ["fixture.txt"])
            module.check_tracked_file_hygiene()
        elif surface == "archive":
            archive_path = tmp_path / "fixture.zip"
            with ZipFile(archive_path, "w") as archive:
                archive.writestr("unifi_unas/__init__.py", "")
                archive.writestr("unifi_unas/manifest.json", "{}")
                archive.writestr("unifi_unas/LICENSE", (ROOT / "LICENSE").read_bytes())
                archive.writestr("unifi_unas/fixture.txt", payload)
            module.check_release_zip(archive_path)
        else:
            monkeypatch.setattr(
                module,
                "_paginated_api_items",
                lambda path: [{"tag_name": "v1.0.0", "body": payload}]
                if path == "repos/owner/repo/releases" else [],
            )
            module.main(["--repo", "owner/repo"])

    output = capsys.readouterr()
    assert error.value.code == 1
    assert f"possible {category}" in output.out
    assert matched not in output.out + output.err


@pytest.mark.parametrize("surface", ["repository", "archive"])
@pytest.mark.parametrize("suffix", [".storage/auth", "__pycache__/x.pyc", "unifi-logo.png", "../x.txt", "note.txt"])
def test_rejected_paths_do_not_echo_private_markers(tmp_path, monkeypatch, capsys, surface, suffix):
    """Filename rejection must be private even before content checks run."""
    marker = "example-private-marker"
    monkeypatch.setenv("UNIFI_UNAS_FORBIDDEN_MARKERS", marker)
    member = f"unifi_unas/{marker}/{suffix}"
    filename = "check_repo.py" if surface == "repository" else "check_release_zip.py"
    module = load_repo_module(f"hygiene_paths_{surface}", ROOT / "scripts" / filename)
    with pytest.raises(SystemExit):
        if surface == "repository":
            monkeypatch.setattr(module, "ROOT", tmp_path)
            monkeypatch.setattr(module, "_tracked_file_paths", lambda: [member])
            monkeypatch.setattr(module, "ensure_file", lambda path: None)
            module.main()
        else:
            archive_path = tmp_path / "example.zip"
            with ZipFile(archive_path, "w") as archive:
                archive.writestr(member, "{}")
            module.check_release_zip(archive_path)
    output = capsys.readouterr()
    assert marker not in output.out + output.err
