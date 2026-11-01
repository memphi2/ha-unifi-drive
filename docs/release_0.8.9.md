# v0.8.9 Release Checklist

Status on `2026-11-01`: prepared for review, **not approved for publication**.
Do not tag, merge for release or publish automatically when HA `2026.11` appears.
The release owner must complete the gates below on the final PR commit.

## Prepared

- Manifest, changelog and release notes use `0.8.9`; `hacs.json` retains the
  `2024.8.0` minimum and has no `zip_release` or `filename` override.
- Marketplace guidance and the NAS/server category are present.
- `DeviceInfo` supports attributes and the legacy dictionary representation;
  missing values preserve registry metadata and unchanged values avoid writes.
- Quality-scale statuses are unchanged; this work does not claim certification.
- Release publication depends on the same complete validation used for PRs.
- Routine Actions/CI-tool updates are quarterly and grouped; security updates
  remain separate. Weekly validation and the HA minimum leg remain required.

## Required Before Release

- [ ] HA `2026.11` has a stable release, not only a beta or release candidate.
- [ ] Select a published `pytest-homeassistant-custom-component` version whose
  declared HA dependency matches that exact stable runtime. Do not guess a
  version, ignore dependencies or reuse October fixtures as November evidence.
- [ ] Update the current HA/helper pair in `.github/workflows/validate.yml`,
  `CURRENT_HOMEASSISTANT_TARGET` / `CURRENT_PYTEST_HOMEASSISTANT` in
  `scripts/check_repo.py`, their tests and the compatibility summary in `docs/lts.md`.
  Keep the HA `2024.8.0` / Python `3.12` leg and Python `3.14` for November.
- [ ] Dependency checks, HACS, Hassfest, Ruff, Mypy, Bandit, full pytest, at least
  95% coverage, compileall and whitespace checks pass for the final PR commit.
  Confirm the HA-backed tests actually ran; a helper-only run is insufficient.
- [ ] On a separately authorized test HA, record fresh Marketplace installation,
  existing HACS takeover, update/restart, reload, reauth, reconfigure, offline
  recovery and removal. Preserve config-entry/device/entity identities on
  supported in-place updates. See [validation.md](validation.md).
- [ ] Confirm firmware remains visible after fresh setup, refresh and recovery;
  missing firmware does not erase it. Check for duplicate devices and entities.
- [ ] Run the public GitHub and packaged ZIP privacy/legal checks. Personal
  marker lists come only from environment/Actions variables, never tracked files.
- [ ] Resolve bot findings and request another review after changes. The final
  reviewed commit must match the PR head; CI success is not bot approval.
- [ ] Record the exact tested versions, run URLs and anonymized live outcomes
  below. Update release wording to reflect only completed checks and remove
  stale preparation notices from the changelog when approving publication.

## Evidence

| Gate | Evidence |
| --- | --- |
| HA 2024.8.0 / Python 3.12.13 / helper 0.13.152 | 571 tests passed, no skips; coverage 95.18%; `pip check`, Ruff, Mypy, Bandit and compileall passed with the pinned CI tools |
| HA 2026.10.4 / Python 3.14.4 / helper 0.13.375 | 571 tests passed, no skips; coverage 95.72%; `pip check`, Ruff, Mypy, Bandit, repository checks and compileall passed with the pinned CI tools |
| Public surfaces and archive | Existing public GitHub surfaces and locally built release ZIP passed the automated privacy/legal/layout audit |
| Stable HA 2026.11 / matching test helper | Pending upstream release and full test run |
| November `DeviceInfo` | Focused check against actual HA `2026.11.0b1` passed; not a full compatibility result |
| Marketplace live lifecycle | Pending; no new live-test claim |
| Final CI / bot review | Record final head and run/review URLs in the PR |

## Publication After Approval

1. Verify the final head, all checks, bot feedback and this checklist again.
2. Merge only after explicit release approval. Verify `main` contains the
   approved code and `manifest.json` version `0.8.9`.
3. Create tag `v0.8.9` on that exact commit. The release workflow reruns complete
   validation before building and publishing the archive and release notes.
4. Verify the published tag, release body and `unifi_unas.zip` independently.
   Confirm the archive layout and manifest version, then check Marketplace/HACS
   catalog visibility. Catalog refresh can lag publication.
