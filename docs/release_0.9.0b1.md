# v0.9.0b1 Beta Release Checklist

Runtime safety and quality validation on stable HA `2026.11.0`, retaining the supported
HA `2024.8.0` minimum. The update preserves existing `0.8.0+` entries. Optional
cache/SMART diagnostics remain disabled by default. There is no destructive
snapshot action, new config-entry migration or Recorder retention change.

## Candidate Gates

- [ ] Manifest, changelog and release notes agree on `0.9.0b1`; HACS metadata and
  the `unifi_unas` domain remain unchanged.
- [ ] Both pinned HA/Python/test-helper matrix legs pass all tests without skips,
  with at least 95% aggregate coverage and valid installed dependencies.
- [ ] Repository checks, Ruff, both Mypy gates, Bandit, compileall, whitespace,
  HACS and Hassfest pass on the final PR head.
- [ ] Privacy/legal checks pass for public GitHub surfaces and the packaged ZIP.
- [ ] Final-head Code Review completes and actionable findings are resolved.
- [ ] GitHub publication uses `prerelease: true` and `make_latest: false`, with
  channel tests covering stable, beta and RC versions.
- [ ] Record final SHA, CI URLs and Code Review evidence in the PR. Pending
  required checks are not a passed gate. A separate Security Review or full
  Security Report is not required for release.

Rerun required checks for the final head and record counts, coverage and evidence
in the PR rather than changing this checklist after review. Prior resource
measurements covered 30 synthetic lifecycle cycles and 300 continuous refreshes
with 30 new snapshot targets. Storage regression fixtures include multiple data
pools and two cache SSDs; they do not establish actual Pro-model compatibility.

## Boundaries

- No claim of new live HA/NAS testing, Pro/Pro4/Pro8 support, 24-hour resource stability, or completed
  live Marketplace lifecycle validation.
- Snapshot entities are retained for previously observed targets; unlimited new
  target identities are not a constant-memory workload.
- Additional Recorder statistics, retention and purge work remains deferred.
- The integration has no companion-card test or Node/npm dependency in CI.
- Quality Scale gaps stay explicit in `quality_scale.yaml`.

## Publication

1. Verify final-head checks and review evidence; retain branch protections.
2. After owner approval, verify the release commit contains exactly the reviewed
   tree and manifest version `0.9.0b1`. A beta can be tagged from its reviewed
   release branch without merging into `main`.
3. Tag that commit `v0.9.0b1`; the release workflow reruns validation before publishing.
4. Run `python scripts/release_check.py --ref v0.9.0b1 --published` to compare the
   remote tag, release notes and downloaded installation ZIP with Git source.
5. Verify it is a prerelease and the latest stable tag is unchanged. Check opt-in
   catalog visibility separately; catalog refresh may lag publication. No
   automatic live HA deployment is implied.
