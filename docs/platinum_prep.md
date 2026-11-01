# Platinum-Track Hardening Plan

This document tracks practical work needed to move the custom integration from
Gold-track evidence toward stronger Platinum-readiness.

It does not claim official Home Assistant Core certification.

## Scope

- No destructive snapshot actions
- No cloud architecture changes
- No feature-surface rewrite

## Current Platinum Status

`custom_components/unifi_unas/quality_scale.yaml` currently keeps:

- `async-dependency`: `done`
- `inject-websession`: `done`
- `strict-typing`: `todo`

Strict typing remains incomplete for platform and flow modules. Lower-tier gaps
also remain: full flow coverage, more than 95% coverage per module, and sensor
availability while core monitoring intentionally retains offline cached values.

## Evidence Already In Place

- Runtime coordinator ownership on typed `ConfigEntry.runtime_data`
- Config-entry lifecycle tests for setup/unload/reload/update-listener behavior
- Discovery identity dedupe, conflict handling, metadata-only reload skip
- Diagnostics schema/versioning with privacy-safe redaction
- Coverage gate above 95%
- CI + repository checks for quality markers, release metadata, HACS safety, and
  translation alignment

## Strict-Typing Workplan

1. Keep strict mypy gate green for current scoped files.
2. Extend strict scope to remaining flow/service/platform modules in small
   reviewable batches.
3. Remove avoidable `Any` in helper boundaries where state shape is stable.
4. Add small TypedDict/dataclass structures only where they improve readability
   and reduce runtime ambiguity.
5. Keep exception chaining and HA-facing translation errors unchanged.

## Runtime And Recorder Hardening Focus

- Continue preventing config-entry write churn from high-frequency discovery
  timestamps.
- Keep discovery metadata persistence bounded and reasoned (signal over noise).
- Preserve optional endpoint isolation so unsupported write features do not
  degrade core monitoring.
- Keep unavailable/recovery logging concise and actionable.

## Validation Gate Per Hardening Round

```bash
python scripts/check_repo.py
python -m pytest -q
python -m compileall -q custom_components/unifi_unas tests
git diff --check
```

Optional local lint/type passes:

```bash
python -m ruff check custom_components tests scripts
mypy --config-file mypy.ini
```

## Done Criteria For Next Platinum Milestone

- `strict-typing` can be moved to `done` with code + tests + docs evidence.
- No regression in discovery dedupe, diagnostics privacy, repairs, or lifecycle.
- Live recorder/config-entry probe continues to show bounded write behavior.
- README and docs remain synchronized with `quality_scale.yaml`.
