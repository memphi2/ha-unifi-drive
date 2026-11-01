#!/usr/bin/env python3
"""Audit public GitHub surfaces for privacy and legal hygiene."""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess  # nosec B404
import sys
import tempfile
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


def _gh_bin() -> str:
    """Return an absolute GitHub CLI path."""
    gh_bin = shutil.which("gh")
    if gh_bin is None:
        fail("Could not find gh executable")
    return gh_bin


def _gh_json(args: list[str]) -> object:
    """Run ``gh`` and parse JSON output."""
    proc = subprocess.run(  # nosec B603
        [_gh_bin(), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        fail(proc.stderr.strip() or proc.stdout.strip() or "gh command failed")
    return json.loads(proc.stdout or "null")


def _gh_bytes(args: list[str]) -> bytes:
    """Run ``gh`` and return raw stdout bytes."""
    proc = subprocess.run(  # nosec B603
        [_gh_bin(), *args],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="ignore").strip()
        stdout = proc.stdout.decode("utf-8", errors="ignore").strip()
        fail(stderr or stdout or "gh command failed")
    return proc.stdout


def _scan_bytes(label: str, data: bytes) -> list[str]:
    """Return non-secret finding labels for text or asset content."""
    issues = content_scan_issues(label, data)

    for finding, pattern in PROPRIETARY_VENDOR_CONTENT_PATTERNS:
        if pattern.search(data):
            issues.append(f"{label}: possible {finding}")
            break

    issues.extend(local_identifier_issues(label, data))

    for finding, pattern in BRANDING_CLAIM_PATTERNS:
        if pattern.search(data):
            issues.append(f"{label}: possible {finding}")
            break

    return issues


def _scan_text(label: str, value: str | None) -> list[str]:
    """Return non-secret finding labels for public text content."""
    if not value:
        return []
    return _scan_bytes(label, value.encode("utf-8", errors="ignore"))


def _is_release_zip_asset_name(name: str) -> bool:
    """Return whether a release asset name should be audited as a ZIP."""
    return name.casefold().endswith(".zip")


def _normalized_zip_member_name(name: str) -> str:
    """Return a POSIX-normalized ZIP member name without changing absoluteness."""
    return name.replace("\\", "/")


def _has_unsafe_zip_member_path(name: str) -> bool:
    """Return whether a ZIP member path could escape its extraction root."""
    path = PurePosixPath(name)
    return path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts)


def _scan_zip_asset(label: str, path: Path) -> list[str]:
    """Return non-secret finding labels for a public release ZIP asset."""
    issues: list[str] = []
    try:
        with ZipFile(path) as archive:
            for info in archive.infolist():
                member = _normalized_zip_member_name(info.filename)
                if not member:
                    continue

                if _has_unsafe_zip_member_path(member):
                    issues.append(f"{label}: unsafe ZIP member path")
                    continue

                if member.endswith("/"):
                    continue

                if _path_matches_any(member, SECRET_PATH_PATTERNS):
                    issues.append(f"{label}: secret-like path")
                    continue
                if _path_matches_any(member, GENERATED_ARTIFACT_PATH_PATTERNS):
                    issues.append(f"{label}: generated artifact path")
                    continue
                if _path_matches_any(member, OFFICIAL_VENDOR_ASSET_PATH_PATTERNS):
                    issues.append(f"{label}: official/vendor asset path")
                    continue
                asset_path_issues = local_identifier_issues(
                    f"{label} asset path",
                    member.encode("utf-8", errors="ignore"),
                )
                if asset_path_issues:
                    issues.extend(asset_path_issues)
                    continue

                data = archive.read(info)
                if b"\0" in data[:4096]:
                    continue
                issues.extend(_scan_bytes(label, data))
    except BadZipFile:
        issues.append(f"{label}: invalid ZIP file")
    return issues


def _download_release_asset(asset_url: str, destination: Path) -> None:
    """Download one release asset by exact API URL."""
    data = _gh_bytes(
        [
            "api",
            asset_url,
            "-H",
            "Accept: application/octet-stream",
        ]
    )
    destination.write_bytes(data)


def _as_list(value: object) -> list[dict[str, object]]:
    """Return JSON array values as a typed list."""
    if not isinstance(value, list):
        fail("GitHub API returned unexpected non-list JSON")
    return [item for item in value if isinstance(item, dict)]


def _api_collection_page_path(path: str, page: int) -> str:
    """Return a REST collection path for one explicit 100-item page."""
    page_path = path
    separator = "&" if "?" in page_path else "?"
    if "per_page=" not in page_path:
        page_path = f"{page_path}{separator}per_page=100"
        separator = "&"
    return f"{page_path}{separator}page={page}"


def _paginated_api_items(path: str) -> list[dict[str, object]]:
    """Return all pages from a GitHub REST API collection."""
    items: list[dict[str, object]] = []
    page = 1
    while True:
        page_items = _as_list(_gh_json(["api", _api_collection_page_path(path, page)]))
        items.extend(page_items)
        if len(page_items) < 100:
            break
        page += 1
    return items


def _repo_pull_requests(repo: str) -> list[dict[str, object]]:
    """Return every pull request from the repository public history."""
    return _paginated_api_items(f"repos/{repo}/pulls?state=all&per_page=100")


def _repo_issues(repo: str) -> list[dict[str, object]]:
    """Return every non-PR issue from the repository public history."""
    return [
        issue
        for issue in _paginated_api_items(f"repos/{repo}/issues?state=all&per_page=100")
        if "pull_request" not in issue
    ]


def audit_public_surfaces(
    *,
    repo: str,
    hacs_repo: str | None,
    hacs_prs: list[int],
) -> tuple[dict[str, int], list[str]]:
    """Audit public repo surfaces and return counts plus finding labels."""
    counts = {
        "releases": 0,
        "release_assets": 0,
        "repo_prs": 0,
        "repo_issues": 0,
        "repo_comments": 0,
        "repo_reviews": 0,
        "hacs_items": 0,
    }
    issues: list[str] = []

    releases = _paginated_api_items(f"repos/{repo}/releases")
    counts["releases"] = len(releases)
    with tempfile.TemporaryDirectory(prefix="github-surface-audit-") as tmp:
        tmp_path = Path(tmp)
        for release in releases:
            tag = str(release.get("tag_name") or "<unknown>")
            issues.extend(_scan_text(f"release {tag} name", release.get("name")))
            issues.extend(_scan_text(f"release {tag} body", release.get("body")))
            for asset in _as_list(release.get("assets") or []):
                name = str(asset.get("name") or "")
                if not _is_release_zip_asset_name(name):
                    continue
                counts["release_assets"] += 1
                asset_dir = tmp_path / tag
                asset_dir.mkdir(parents=True, exist_ok=True)
                asset_url = asset.get("url")
                if not isinstance(asset_url, str) or not asset_url:
                    issues.append(f"release {tag} asset {name}: missing asset API URL")
                    continue
                asset_path = asset_dir / f"asset-{counts['release_assets']}.zip"
                _download_release_asset(asset_url, asset_path)
                issues.extend(_scan_zip_asset(f"release {tag} asset {name}", asset_path))

    prs = _repo_pull_requests(repo)
    counts["repo_prs"] = len(prs)
    for pr in prs:
        number = int(pr["number"])
        issues.extend(_scan_text(f"PR #{number} title", pr.get("title")))
        issues.extend(_scan_text(f"PR #{number} body", pr.get("body")))
        comments = _paginated_api_items(f"repos/{repo}/issues/{number}/comments")
        counts["repo_comments"] += len(comments)
        for comment in comments:
            issues.extend(_scan_text(f"PR #{number} issue comment", comment.get("body")))
        reviews = _paginated_api_items(f"repos/{repo}/pulls/{number}/reviews")
        counts["repo_reviews"] += len(reviews)
        for review in reviews:
            issues.extend(_scan_text(f"PR #{number} review", review.get("body")))
        review_comments = _paginated_api_items(f"repos/{repo}/pulls/{number}/comments")
        counts["repo_comments"] += len(review_comments)
        for comment in review_comments:
            issues.extend(_scan_text(f"PR #{number} review comment", comment.get("body")))

    repo_issues = _repo_issues(repo)
    counts["repo_issues"] = len(repo_issues)
    for issue in repo_issues:
        number = int(issue["number"])
        issues.extend(_scan_text(f"issue #{number} title", issue.get("title")))
        issues.extend(_scan_text(f"issue #{number} body", issue.get("body")))
        comments = _paginated_api_items(f"repos/{repo}/issues/{number}/comments")
        counts["repo_comments"] += len(comments)
        for comment in comments:
            issues.extend(_scan_text(f"issue #{number} comment", comment.get("body")))

    if hacs_repo and hacs_prs:
        for hacs_pr in hacs_prs:
            hacs = _gh_json(
                [
                    "pr",
                    "view",
                    str(hacs_pr),
                    "--repo",
                    hacs_repo,
                    "--json",
                    "number,title,body,state,url",
                ]
            )
            if not isinstance(hacs, dict):
                fail("GitHub API returned unexpected HACS PR JSON")
            counts["hacs_items"] += 1
            issues.extend(_scan_text(f"HACS PR #{hacs_pr} title", hacs.get("title")))
            issues.extend(_scan_text(f"HACS PR #{hacs_pr} body", hacs.get("body")))
            for endpoint, label in (
                (f"repos/{hacs_repo}/issues/{hacs_pr}/comments", "issue comment"),
                (f"repos/{hacs_repo}/pulls/{hacs_pr}/reviews", "review"),
                (f"repos/{hacs_repo}/pulls/{hacs_pr}/comments", "review comment"),
            ):
                items = _paginated_api_items(endpoint)
                counts["hacs_items"] += len(items)
                for item in items:
                    issues.extend(_scan_text(f"HACS PR #{hacs_pr} {label}", item.get("body")))

    return counts, sorted(set(issues))


def main(argv: list[str] | None = None) -> None:
    """Run the public GitHub surface audit."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="Repository in owner/name form")
    parser.add_argument("--hacs-repo", default=None, help="Optional HACS repository")
    parser.add_argument(
        "--hacs-pr",
        action="append",
        type=int,
        default=[],
        help="Optional HACS pull request number to include",
    )
    args = parser.parse_args(argv)

    counts, issues = audit_public_surfaces(
        repo=args.repo,
        hacs_repo=args.hacs_repo,
        hacs_prs=args.hacs_pr,
    )
    if issues:
        fail("GitHub public-surface privacy/legal audit failed:\n" + "\n".join(issues))

    for key, value in counts.items():
        ok(f"GitHub public-surface audit {key}: {value}")
    ok("GitHub public-surface privacy/legal audit passed")


if __name__ == "__main__":
    main()
