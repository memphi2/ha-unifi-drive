# Repository Instructions

## Release Reviews

- Follow `docs/validation.md` and the applicable release checklist.
- Require completed Code Review of the final PR head; resolve actionable findings.
- Allow automatic reviews to finish without duplicate manual requests.
- New commits require fresh Code Review; record the SHA and evidence in the PR.
- Separate Security Review and full-report access are optional, not release gates.
  Do not request these as a release prerequisite or block publication on access
  to them. This applies to future releases too unless the owner changes the policy.
- Keep CodeQL, Bandit, privacy audits and required CI checks enabled.
- Preserve branch protections and require owner approval before publication.
