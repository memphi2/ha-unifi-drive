# v0.9.0 Release Checklist

Runtime safety and quality validation on HA `2026.10.4`, retaining the supported
HA `2024.8.0` minimum. The update preserves existing `0.8.0+` entries. No new
feature surface, destructive snapshot action or Recorder retention change.

## Candidate Gates

- [ ] Manifest, changelog and release notes agree on `0.9.0`; HACS metadata and
  the `unifi_unas` domain remain unchanged.
- [ ] Both pinned HA/Python/test-helper matrix legs pass all tests without skips,
  with at least 95% aggregate coverage and valid installed dependencies.
- [ ] Repository checks, Ruff, both Mypy gates, Bandit, compileall, whitespace,
  HACS and Hassfest pass on the final PR head.
- [ ] Privacy/legal checks pass for public GitHub surfaces and the packaged ZIP.
- [ ] Final-head Code Review completes and actionable findings are resolved.
- [ ] Record final SHA, CI URLs and Code Review evidence in the PR. Pending
  required checks are not a passed gate. A separate Security Review or full
  Security Report is not required for release.

Local development validation: 762 tests per HA baseline, aggregate coverage above
95%, plus 30 synthetic lifecycle cycles and 300 continuous refreshes with 30 new
snapshot targets. Rerun required checks for the final head and record results in
the PR rather than changing this checklist after review.

## Boundaries

- No claim of new live HA/NAS testing, 24-hour resource stability, or completed
  HA `2026.11` / Marketplace lifecycle validation.
- Snapshot entities are retained for previously observed targets; unlimited new
  target identities are not a constant-memory workload.
- Additional Recorder statistics, retention and purge work remains deferred.
- The integration has no companion-card test or Node/npm dependency in CI.
- Quality Scale gaps stay explicit in `quality_scale.yaml`.

## Publication

1. Verify final-head checks and review evidence; retain branch protections.
2. After owner approval, merge and verify that `main` has exactly the reviewed
   tree and manifest version `0.9.0`.
3. Tag that commit `v0.9.0`; the release workflow reruns validation before publishing.
4. Run `python scripts/release_check.py --ref v0.9.0 --published` to compare the
   remote tag, release notes and downloaded installation ZIP with Git source.
5. Check release visibility and catalog update availability separately; catalog
   refresh may lag publication. No automatic live HA deployment is implied.
