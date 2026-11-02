# Validation And Release Checks

This document defines the validation gates used for branch hardening and release
validation.

## Required Local Gate

Additional regression commands and their scope:

- [Recorder measurements and history profiles](recorder.md)
- [Bounded RAM/task lifecycle measurements](runtime_measurements.md)

Verify a committed candidate locally with `python scripts/release_check.py`.
After publication, verify the exact approved tag, release notes and downloaded
installation ZIP against Git content:

```bash
python scripts/release_check.py --ref v0.8.9 --published
```

Use the tag being checked, not an unrelated development HEAD. The release
workflow now runs the published-artifact check automatically after upload.
This command is read-only on GitHub and does not merge, tag or publish anything.

```bash
python scripts/check_repo.py
python scripts/audit_github_public_surfaces.py --repo memphi2/ha-unifi-drive
rm -rf dist
mkdir -p dist
(cd custom_components && zip -q -r ../dist/unifi_unas.zip unifi_unas -x "*/__pycache__/*" "*.pyc")
python scripts/check_release_zip.py dist/unifi_unas.zip
python -m pytest -q
python -m compileall -q custom_components/unifi_unas tests
git diff --check
```

## Additional Quality Gates

Run when the environment provides the tooling:

```bash
python -m ruff check custom_components tests scripts
mypy --config-file mypy.ini
mypy --config-file mypy-ha.ini
python -m bandit -q -r custom_components scripts
```

## What These Checks Cover

- release metadata alignment (`manifest`, `CHANGELOG`, release notes)
- HACS metadata safety (`hacs.json`)
- Marketplace installation/update/removal documentation and the UNAS catalog category
- legal, trademark and asset hygiene checks
- tracked-file secret checks and release ZIP privacy/legal/layout checks
- public GitHub release, PR, issue and release-asset hygiene checks
- generic RFC1918 local-address checks and optional local denylist marker checks
  through `UNIFI_UNAS_FORBIDDEN_MARKERS`
- quality-scale status validation
- translation structure validation
- typed runtime-data baseline and strict mypy gate structure
- an additional imported-HA type gate for runtime, read-only entry and device
  metadata contracts, run against each matrix environment's actual HA types
- icon/exception translation baseline
- full integration unit/fixture test suite

## Marketplace And HA Version Checks

HACS validation still applies to Marketplace: both use `hacs.json` and the same
catalog. Do not rename the metadata file, change the domain or require users to
reinstall solely for Marketplace. The user-facing procedures are in
[installation.md](installation.md).

For each newly supported HA line, use the required Python version and compatible
HA test helpers. Run `python -m pip check` and inspect pytest's skip summary as
well as the exit code. Without `pytest-homeassistant-custom-component`, this
repository intentionally skips the HA-backed tests; that helper-only run cannot
establish HA compatibility or satisfy the release coverage gate. The compatibility
work still outstanding for November is tracked in [lts.md](lts.md).

Before declaring Marketplace runtime compatibility, verify on a separate test HA:

1. A fresh catalog install and initial setup without duplicate config entries.
2. HACS takeover with existing `unifi_unas` entries and entity identities intact.
3. An offered version update, required restart and successful entry reload.
4. Reauthentication, reconfiguration and offline recovery after the update.
5. Config-entry deletion followed by repository uninstall and restart.

Keep the old pre-`0.8.0` domain migration separate from these tests. Record the
tested HA/integration versions and outcomes, not credentials or local identifiers.

## Live Validation Notes

- `docs/live_test_report_v0.6.2.md` tracks full HA live validation including
  restart/reload/reauth/reconfigure and firmware-update checks.
- `docs/live_db_probe.md` tracks recorder/config-entry write behavior for
  discovery write-throttle hardening.

## Code Review

Require completed Code Review of the final PR head and resolve actionable findings.
Record its SHA and evidence link in the PR. New commits require fresh review.
Allow automatic reviews to finish without duplicate manual requests.
Separate Security Review and access to its full report are optional, not release
gates. Do not claim clearance for uninspected reports. CodeQL, Bandit, dependency
checks and privacy/legal audits remain required. Preserve branch protections.

## Release Readiness Rule

Do not finalize release work while any of these are failing, missing or pending:

- repository checks
- public GitHub surface audit
- release ZIP privacy/legal/layout check
- pytest suite
- compile checks
- HACS validation workflow
- Hassfest workflow
- Code Review of the final PR head, with actionable findings resolved

Release publication first calls the complete validation workflow on the tagged
commit, including both HA matrix legs, HA-backed tests and the 95% coverage floor.
The publish job cannot run if that workflow fails, and non-tag manual runs do
not publish. The tag must match the manifest version.

The workflow does not currently verify Codex task completion. Review evidence is
a separate release-owner gate, not something implied by successful CI. After
merging, verify the release contains the reviewed content and no additional
changes; changed content requires fresh review before publication. A clean review
does not grant permission to merge, tag or publish without explicit approval.

The HA `2026.10.4` maintenance release has a separate
[v0.8.9 checklist](release_0.8.9.md). HA `2026.11` and Marketplace lifecycle
validation are follow-up gates for claiming that compatibility, not prerequisites
for this release on the tested HA baseline. Do not treat beta smoke tests as proof
of stable HA or Marketplace compatibility.

Release publication also runs `scripts/check_repo.py` before building the ZIP and
`scripts/check_release_zip.py` before uploading the release asset. It also runs
`scripts/audit_github_public_surfaces.py` to scan existing public releases, PRs,
issues and release ZIP assets for privacy, copyright and branding-risk markers.
Release notes, PR bodies and public support comments should use redacted examples
only and must not include live hostnames, local addresses, credentials, tokens,
cookies, personal usernames, test-user names, snapshot target names, official
vendor assets, proprietary vendor source material, or wording that implies vendor
endorsement.

Personal or environment-specific marker strings must not be committed to the
repository. Keep them in the `UNIFI_UNAS_FORBIDDEN_MARKERS` environment variable
locally and in the matching GitHub Actions variable for CI/release runs.
Set that variable in a private shell environment before running the commands
above when local marker coverage is needed.

When a HACS submission is part of the release cycle, include that public PR in
the audit as well:

```bash
python scripts/audit_github_public_surfaces.py \
  --repo memphi2/ha-unifi-drive \
  --hacs-repo hacs/default \
  --hacs-pr <number>
```
