# Repository Instructions

## Release Reviews

- Follow the release gates in `docs/validation.md` and the applicable release
  checklist. Keep normal Code Review and dedicated Security Review separate.
- Before merging for release, tagging or publishing, require both reviews to
  complete for the exact final PR head. Request `@codex review` and
  `@codex security review` separately unless each already has a verified result
  for that commit. Record the commit SHA and both evidence links in the PR.
- Inspect the dedicated task's Security Report, including findings below the
  GitHub reporting threshold. Resolve actionable findings from both reviews.
  A normal review with a security-focused prompt is not a dedicated Security
  Review. CI success, a reaction, silence, or an error is not security clearance.
- Any new commit invalidates the previous pair of review results. Pending,
  failed or inaccessible reviews block release; report the blocker rather than
  marking it passed. Do not expose sensitive report contents in public comments.
- These instructions do not enable Codex account automation or create an
  enforced GitHub status check. Do not claim either without verification.
- Preserve branch protections. Reviews do not authorize a merge or release;
  obtain explicit user approval and verify the published code matches the
  reviewed changes.
