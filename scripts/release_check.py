"""Verify a release's Git tree, metadata and optionally its published artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import stat
# allowlisted tools, argument arrays, no shell.
import subprocess  # nosec B404
import tempfile
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

try:
    from scripts.check_release_zip import check_release_zip
except ModuleNotFoundError:
    from check_release_zip import check_release_zip

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = "custom_components/unifi_unas/"


def run(args: list[str]) -> bytes:
    if not args or args[0] not in {"git", "gh"}:
        raise ValueError("unsupported release verification tool")
    executable = shutil.which(args[0])
    if executable is None:
        raise ValueError("required release verification tool is missing")
    # allowlisted tool, no shell.
    result = subprocess.run([executable, *args[1:]], cwd=ROOT, capture_output=True, check=False)  # nosec B603
    if result.returncode:
        # Remote errors and local paths can contain private identifiers.
        raise ValueError(f"{args[0]} command failed; verify access and the requested ref")
    return result.stdout


def source_files(commit: str) -> dict[str, bytes]:
    files = {}
    listing = run(["git", "ls-tree", "-rz", commit, "--", COMPONENT])
    for record in listing.split(b"\0"):
        if not record:
            continue
        metadata, path = record.split(b"\t", 1)
        mode, kind, object_id = metadata.split()
        if mode not in {b"100644", b"100755"} or kind != b"blob":
            raise ValueError("release source contains a non-regular component file")
        name = path.decode().removeprefix("custom_components/")
        files[name] = run(["git", "cat-file", "blob", object_id.decode()])
    if not files:
        raise ValueError("release source has no integration files")
    return files


def verify_archive(path: Path, expected: dict[str, bytes]) -> None:
    with ZipFile(path) as archive:
        names = [item.filename for item in archive.infolist() if not item.is_dir()]
        if len(names) != len(set(names)):
            raise ValueError("release ZIP has duplicate files")
        if set(names) != set(expected):
            raise ValueError("release ZIP file set differs from the approved commit")
        for info in archive.infolist():
            if info.is_dir():
                continue
            mode = stat.S_IFMT(info.external_attr >> 16)
            if mode not in {0, stat.S_IFREG} or info.file_size != len(expected[info.filename]):
                raise ValueError("release ZIP file type or size differs from the approved commit")
        if any(archive.read(name) != content for name, content in expected.items()):
            raise ValueError("release ZIP contents differ from the approved commit")


def verify_release_metadata(release: dict, tag: str, notes: str) -> None:
    if release.get("tag_name") != tag or release.get("draft") or release.get("prerelease"):
        raise ValueError("published release tag or stable-release status is incorrect")
    if (release.get("body") or "").replace("\r\n", "\n").strip() != notes.strip():
        raise ValueError("published release notes differ from the approved commit")
    assets = release.get("assets", [])
    if len(assets) != 1 or assets[0].get("name") != "unifi_unas.zip" or assets[0].get("size", 0) <= 0:
        raise ValueError("release must contain exactly the nonempty HACS installation ZIP")


def remote_tag_commit(repo: str, tag: str) -> str:
    obj = json.loads(run(["gh", "api", f"repos/{repo}/git/ref/tags/{tag}"]))["object"]
    for _ in range(8):
        if obj.get("type") == "commit":
            return str(obj["sha"])
        if obj.get("type") != "tag":
            break
        obj = json.loads(run(["gh", "api", f"repos/{repo}/git/tags/{obj['sha']}"]))["object"]
    raise ValueError("remote tag does not resolve to a commit")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="HEAD", help="exact approved commit or tag")
    parser.add_argument("--published", action="store_true", help="also verify GitHub tag, notes and downloaded ZIP")
    parser.add_argument("--repo", default="memphi2/ha-unifi-drive")
    parser.add_argument("--archive", type=Path, help="also compare an existing local ZIP")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", args.repo):
        parser.error("invalid owner/repository")
    try:
        if args.ref == "HEAD" and run(["git", "status", "--porcelain"]).strip():
            raise ValueError("commit local changes before validating HEAD")
        commit = run(["git", "rev-parse", "--verify", "--end-of-options", f"{args.ref}^{{commit}}"])
        sha = commit.decode().strip()
        files = source_files(sha)
        version = json.loads(files["unifi_unas/manifest.json"])["version"]
        if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
            raise ValueError("expected a stable semantic version")
        tag = f"v{version}"
        notes = run(["git", "show", f"{sha}:.github/release-notes/{tag}.md"]).decode()
        changelog = run(["git", "show", f"{sha}:CHANGELOG.md"]).decode()
        if not notes.strip() or not re.search(rf"^## {re.escape(tag)}(?:\s|$)", changelog, re.M):
            raise ValueError("release notes or matching changelog section missing")
        with tempfile.TemporaryDirectory(prefix="unas-release-check-") as directory:
            archive = Path(directory) / "unifi_unas.zip"
            if args.published:
                if remote_tag_commit(args.repo, tag) != sha:
                    raise ValueError("remote tag differs from the approved commit")
                release = json.loads(run(["gh", "api", f"repos/{args.repo}/releases/tags/{tag}"]))
                verify_release_metadata(release, tag, notes)
                run(["gh", "release", "download", tag, "--repo", args.repo,
                     "--pattern", "unifi_unas.zip", "--dir", directory])
            else:
                with ZipFile(archive, "w", compression=ZIP_DEFLATED) as output:
                    for name, content in sorted(files.items()):
                        output.writestr(name, content)
            verify_archive(archive, files)
            check_release_zip(archive)
            if args.archive:
                verify_archive(args.archive, files)
                check_release_zip(args.archive)
        print(f"[OK] {tag} matches commit {sha}" + (" including GitHub tag, notes and artifact" if args.published else " (local artifact check)"))
        return 0
    except (ValueError, KeyError, OSError, BadZipFile) as err:
        reason = str(err) if type(err) is ValueError else type(err).__name__
        print(f"[FAIL] Release verification failed: {reason}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
