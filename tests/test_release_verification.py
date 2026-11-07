"""Negative release checks must fail without trusting archive names or tag labels."""

from copy import deepcopy
from zipfile import ZipFile, ZipInfo

import pytest

from scripts.release_check import remote_tag_commit, verify_archive, verify_release_metadata
from scripts.release_version import is_prerelease, validate_version


@pytest.mark.parametrize("version,beta", [("0.9.0", False), ("0.9.0b1", True), ("0.9.0rc2", True)])
def test_canonical_release_versions_and_channels(version, beta):
    assert validate_version(version) == version
    assert is_prerelease(f"v{version}") is beta
    release = {"tag_name": f"v{version}", "draft": False, "prerelease": beta,
               "body": "Notes", "assets": [{"name": "unifi_unas.zip", "size": 100}]}
    verify_release_metadata(release, f"v{version}", "Notes")
    for invalid in (not beta, None, "true", 1 if beta else 0):
        with pytest.raises(ValueError, match="channel"):
            verify_release_metadata({**release, "prerelease": invalid}, f"v{version}", "Notes")


@pytest.mark.parametrize("value", ["0.9.01b1", "0.9.0b0", "0.9.0b01", "0.9.0-rc1", "0.9.0+local", "0.9.0\n", "v0.9.0", "", None])
def test_release_version_rejects_ambiguous_or_noncanonical_input(value):
    with pytest.raises(ValueError):
        validate_version(value)


def test_release_channel_rejects_unversioned_tags():
    with pytest.raises(ValueError):
        is_prerelease("0.9.0b1")


@pytest.mark.parametrize("version,beta,latest", [
    ("0.9.0", "false", "true"), ("0.9.0b1", "true", "false"), ("0.9.0rc1", "true", "false"),
])
def test_release_workflow_outputs_correct_channel(tmp_path, monkeypatch, version, beta, latest):
    """Execute the workflow's metadata step and verify the publication wiring."""
    import json
    from pathlib import Path
    import yaml

    workflow = yaml.safe_load((Path(__file__).resolve().parents[1] / ".github/workflows/release.yml").read_text())
    steps = workflow["jobs"]["build_and_release"]["steps"]
    metadata = next(step for step in steps if step.get("id") == "release_metadata")
    publish = next(step for step in steps if step.get("uses", "").startswith("softprops/action-gh-release@"))
    assert publish["with"]["prerelease"] == "${{ steps.release_metadata.outputs.prerelease }}"
    assert publish["with"]["make_latest"] == "${{ steps.release_metadata.outputs.make_latest }}"
    assert publish["with"]["files"] == "dist/unifi_unas.zip"
    script = metadata["run"].split("python - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    manifest = tmp_path / "custom_components/unifi_unas/manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"version": version}))
    output = tmp_path / "output.txt"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RELEASE_TAG", f"v{version}")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    exec(compile(script, "release-workflow", "exec"), {})
    assert output.read_text() == f"prerelease={beta}\nmake_latest={latest}\n"
    output.unlink()
    monkeypatch.setenv("RELEASE_TAG", "v0.0.1")
    with pytest.raises(SystemExit, match="Release tag must be"):
        exec(compile(script, "release-workflow", "exec"), {})
    assert not output.exists()


def test_archive_requires_exact_file_set_and_contents(tmp_path):
    expected = {"unifi_unas/a.py": b"original"}
    archive = tmp_path / "release.zip"
    for files in ({}, {"unifi_unas/a.py": b"changed"}, {**expected, "extra.py": b"extra"}):
        with ZipFile(archive, "w") as output:
            for name, data in files.items():
                output.writestr(name, data)
        with pytest.raises(ValueError):
            verify_archive(archive, expected)
    with ZipFile(archive, "w") as output:
        output.writestr("unifi_unas/a.py", b"original")
    verify_archive(archive, expected)
    with ZipFile(archive, "a") as output, pytest.warns(UserWarning):
        output.writestr("unifi_unas/a.py", b"original")
    with pytest.raises(ValueError, match="duplicate"):
        verify_archive(archive, expected)


def test_archive_rejects_symlink_disguised_as_expected_file(tmp_path):
    archive = tmp_path / "release.zip"
    info = ZipInfo("unifi_unas/a.py")
    info.create_system = 3
    info.external_attr = 0o120777 << 16
    with ZipFile(archive, "w") as output:
        output.writestr(info, b"original")
    with pytest.raises(ValueError, match="file type"):
        verify_archive(archive, {"unifi_unas/a.py": b"original"})


@pytest.mark.parametrize("field,value", [
    ("tag_name", "v0.0.2"), ("draft", True), ("prerelease", True),
    ("body", "different"), ("assets", []),
    ("assets", [{"name": "wrong.zip", "size": 1}]),
    ("assets", [{"name": "unifi_unas.zip", "size": 0}]),
])
def test_published_metadata_rejects_mismatch(field, value):
    release = {"tag_name": "v0.0.1", "draft": False, "prerelease": False,
               "body": "Notes\r\n", "assets": [{"name": "unifi_unas.zip", "size": 100}]}
    verify_release_metadata(release, "v0.0.1", "Notes\n")
    invalid = deepcopy(release)
    invalid[field] = value
    with pytest.raises(ValueError):
        verify_release_metadata(invalid, "v0.0.1", "Notes\n")


@pytest.mark.parametrize("annotated", [False, True])
def test_remote_tag_peels_annotated_tags(monkeypatch, annotated):
    import json
    from scripts import release_check

    commit = {"type": "commit", "sha": "a" * 40}
    replies = [{"object": {"type": "tag", "sha": "b" * 40}}, {"object": commit}] if annotated else [{"object": commit}]
    monkeypatch.setattr(release_check, "run", lambda args: json.dumps(replies.pop(0)).encode())
    assert remote_tag_commit("example/integration", "v0.0.1") == "a" * 40
    assert not replies


def test_remote_tag_rejects_non_commit_target(monkeypatch):
    from scripts import release_check

    monkeypatch.setattr(release_check, "run", lambda args: b'{"object":{"type":"tree","sha":"example"}}')
    with pytest.raises(ValueError, match="commit"):
        remote_tag_commit("example/integration", "v0.0.1")


def test_release_runner_rejects_unapproved_tools():
    from scripts.release_check import run

    with pytest.raises(ValueError, match="unsupported"):
        run(["unexpected-program"])


def test_release_workflow_verifies_published_artifact():
    from pathlib import Path

    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/release.yml").read_text()
    assert workflow.index("scripts/release_check.py") > workflow.index("softprops/action-gh-release")
    assert '--ref "$GITHUB_SHA" --published' in workflow
