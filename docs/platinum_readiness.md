# Platinum Readiness Audit

This audit records the current higher-tier Home Assistant Quality Scale status
for the unofficial UniFi Drive / UNAS custom integration. It is intentionally
conservative: a rule is marked as remaining work when implementation, tests,
documentation, and repository checks do not all support a `done` claim.

## What Improved

- Added explicit `PARALLEL_UPDATES` declarations for every platform.
- Expanded `quality_scale.yaml` from Bronze-only tracking to the full
  Bronze/Silver/Gold/Platinum rule list with conservative statuses.
- Added a typed `UnifiDriveConfigEntry` runtime-data alias and `py.typed` marker
  as the foundation for strict typing.
- Added a strict `mypy` CI gate for config-entry setup/unload, coordinator,
  runtime, API client and mixins, config-flow helper, entry-reload, device-info,
  diagnostics, discovery, shared entity base, repair, service, snapshot,
  storage, security, URL, WOL, exception, and API-error modules that already
  have practical Home Assistant-compatible type boundaries, with sensor and binary
  entity-description metadata classes moved under strict typing scope.
- Converted service and entity action failures to Home Assistant translatable
  exception keys while preserving fallback messages.
- Strengthened repository checks so they validate higher-tier rule tracking,
  README quality sections, platform parallel-update declarations, typed
  runtime-entry usage, strict mypy gate structure, translated exceptions, icon
  translations, and the coverage gate.
- Added Bandit and coverage enforcement to CI repository validation.
- Documented data-update behavior, supported device scope, safe automation
  examples, and the Silver/Gold/Platinum roadmap in the README.

## Current Higher-Tier Status

| Area | Status | Notes |
| --- | --- | --- |
| Config-entry lifecycle | Strong | Runtime data, unload cleanup, update listener cleanup, metadata-only reload skip, and delayed discovery cleanup are implemented. |
| Coordinator/offline behavior | Strong | Transient cached data and single outage/recovery logging are implemented; optional endpoints are isolated from core monitoring. |
| Entity model | Strong | Unique IDs, device info, entity categories, disabled-by-default noisy telemetry, availability, and coordinator usage are covered. |
| Diagnostics/privacy | Strong | Diagnostics are versioned, grouped, and redacted for local identifiers and snapshot target details. |
| Discovery | Strong beta | UniFi discovery and zeroconf use trusted identity hints and avoid pre-confirmation credential use against uncertain hosts. |
| Repairs | Good | Snapshot-target issues are actionable, privacy-safe, and clear when the condition resolves; powered-off/offline devices do not create snapshot-read repairs. |
| Typing | Strong partial | Runtime data uses a typed config-entry alias, `py.typed` is present, and CI enforces strict mypy on setup/unload, coordinator, runtime, the API client/mixins, config-flow helper, diagnostics, discovery, shared entity base, repairs, services, snapshot, storage and support modules; full integration-wide mypy remains open. |
| Test coverage | Strong | Latest local line coverage for `custom_components/unifi_unas` is above 95% and CI enforces the coverage gate. |
| Documentation | Strong | README now covers installation, removal, options, data updates, capabilities, diagnostics, limitations, use cases, and roadmap. |
| CI | Strong | CI runs HACS, Hassfest, repository checks, Ruff, Bandit, coverage-backed pytest, compileall, and whitespace checks. |

## Silver And Gold Baseline

The tracked rules include implemented behavior and documented gaps; complete
Bronze, Silver, and Gold compliance is not claimed. In particular, flow coverage,
per-module coverage and cached sensor availability remain open. Keep adding
HA-backed and live-device coverage for reload,
offline startup, recovery, update, backup, fan, and snapshot permission profiles
so future firmware differences do not erode that baseline.

## Remaining Gaps Before Platinum

- Extend the strict mypy gate from the typed lifecycle/API/helper layer to the full
  Home Assistant entity platform layer, config-flow service surfaces, and the
  remaining platform runtime paths without weakening strict checks.
- Keep dependency/session behavior documented when external dependencies change.
- Avoid marking strict typing complete until the gate is part of the normal
  validation path.

## Intentional Experimental Areas

- Snapshot settings, inventory, and create controls remain opt-in and
  firmware-dependent.
- Backup-task buttons remain endpoint-dependent.
- Fan mode, restart, shutdown, and update install remain console-level local
  controls requiring appropriate permissions.
- Discovery remains conservative when VLANs, multiple interfaces, stale DNS, or
  incomplete mDNS metadata prevent trusted identity matching.

## Risk Assessment

- Core read-only monitoring risk is low.
- Optional control risk is moderate because local UniFi Drive / UniFi OS
  endpoints and permissions vary by firmware.
- Discovery risk is moderate in heterogeneous networks, but current identity
  handling favors manual confirmation over unsafe duplicate suppression.
- Privacy risk is low as long as future diagnostics additions keep raw payload
  values and local identifiers out of exports.
