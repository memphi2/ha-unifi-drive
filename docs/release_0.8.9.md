# v0.8.9 Release Checklist

Release scope on `2026-11-02`: maintenance for HA `2026.10.4`, retaining the
HA `2024.8.0` minimum. HA `2026.11` is not a runtime requirement or a prerequisite
for this release. Publication remains conditional on the gates below, including
Code Review of the final PR commit.

## Prepared

- Manifest, changelog and release notes use `0.8.9`; `hacs.json` retains the
  `2024.8.0` minimum and has no `zip_release` or `filename` override.
- Marketplace guidance and the NAS/server category are present.
- `DeviceInfo` supports attributes and the legacy dictionary representation;
  missing values preserve registry metadata and unchanged values avoid writes.
- Quality-scale statuses document the remaining Core branding, flow-coverage,
  availability, per-module coverage and typing gaps; this work does not claim certification.
- Release publication depends on the same complete validation used for PRs.
- Routine Actions/CI-tool updates are quarterly and grouped; security updates
  remain separate. Weekly validation and the HA minimum leg remain required.

## Required Before Release

- [ ] Validate the pinned HA `2026.10.4` / Python `3.14` / helper `0.13.375`
  baseline and HA `2024.8.0` / Python `3.12` / helper `0.13.152` minimum.
  Resolve each helper's exact HA dependency normally; do not bypass dependencies.
- [ ] Dependency checks, HACS, Hassfest, Ruff, Mypy, Bandit, full pytest, at least
  95% coverage, compileall and whitespace checks pass for the final PR commit.
  Confirm the HA-backed tests actually ran; a helper-only run is insufficient.
- [ ] Confirm the regression suite covers firmware after fresh setup, refresh
  and recovery, preservation of missing metadata, stable entity identities,
  repeated setup/unload and offline recovery on the supported HA baseline.
  Report automated results separately from live-device evidence.
- [ ] Run the public GitHub and packaged ZIP privacy/legal checks. Personal
  marker lists come only from environment/Actions variables, never tracked files.
- [ ] Complete normal Code Review of the final PR head and resolve actionable
  findings. Record the full SHA and review link in the PR.
- [ ] Record the final SHA, exact tested versions, run URLs and review evidence
  in the PR. Keep release wording limited to completed checks; do not claim new
  live HA/NAS, Marketplace or long-running RAM/Recorder validation.

## Later HA 2026.11 And Marketplace Validation

These checks are required before declaring the newer runtime and Marketplace
lifecycle validated. They do not block the HA `2026.10.4` maintenance release.

- [ ] Select stable HA `2026.11` and a published helper with a matching exact
  dependency. Do not reuse October fixtures or beta-only results as evidence.
- [ ] Update the HA/helper pair in `.github/workflows/validate.yml`, the matching
  targets in `scripts/check_repo.py`, their tests and `docs/lts.md` together.
  Retain the HA `2024.8.0` / Python `3.12` minimum leg and run every quality gate.
- [ ] On a separately authorized test HA, record fresh Marketplace installation,
  existing HACS takeover, update/restart, reload, reauth, reconfigure, offline
  recovery and removal. Preserve config-entry/device/entity identities on
  supported in-place updates. See [validation.md](validation.md).
- [ ] Confirm firmware after fresh setup, refresh and recovery, preservation of
  missing metadata and absence of duplicate devices/entities in that live run.
- [ ] Record anonymized versions and outcomes before making compatibility claims.

## Evidence

The numeric results below describe preparation commit `a03ae5a`, before the
release-scope documentation update. Rerun all gates for the final release head
and record its evidence in the PR; earlier reviews do not approve later changes.

| Gate | Evidence |
| --- | --- |
| HA 2024.8.0 / Python 3.12.13 / helper 0.13.152 | 702 tests passed, no skips; coverage 95.33%; `pip check`, Ruff, Mypy, Bandit and compileall passed with the pinned CI tools |
| HA 2026.10.4 / Python 3.14.4 / helper 0.13.375 | 702 tests passed, no skips; coverage 95.85%; `pip check`, Ruff, Mypy, Bandit, repository checks and compileall passed with the pinned CI tools |
| Public surfaces and archive | Existing public GitHub surfaces and locally built release ZIP passed the automated privacy/legal/layout audit |
| Stable HA 2026.11 / matching test helper | Follow-up; not claimed by this maintenance release |
| November `DeviceInfo` | Focused check against actual HA `2026.11.0b1` passed; not a full compatibility result |
| Marketplace live lifecycle | Follow-up; no new live-test claim |
| Final CI / Code Review | Record final head and run/review URLs in the PR |

## Publication After Approval

1. Verify the final head, all checks, Code Review and this checklist again.
2. Merge only after explicit release approval. Verify `main` contains the
   approved code and `manifest.json` version `0.8.9`.
3. Create tag `v0.8.9` on that exact commit. The release workflow reruns complete
   validation before building and publishing the archive and release notes.
4. Verify the published tag, release body and `unifi_unas.zip` independently.
   Confirm the archive layout and manifest version, then check Marketplace/HACS
   catalog visibility. Catalog refresh can lag publication.
