# Quality Readiness And Roadmap

This is the canonical quality assessment for the current development branch.
[quality_scale.yaml](../custom_components/unifi_unas/quality_scale.yaml) tracks
individual rules. Neither this document nor a green CI run claims an official
Home Assistant tier.

## Current Maturity

| Area | Status and evidence |
| --- | --- |
| Core monitoring | Mature beta; HA-state tests cover degraded pools, cached offline readings and recovery. |
| Discovery | Hardened beta; identity conflict, dedupe, aliases and metadata-only updates have regression coverage. VLAN behavior still needs representative live networks. |
| Snapshot inventory | Beta; bounded previews, throttled reads and separate failed-read/missing-target handling. |
| Local controls | Experimental; firmware and account permissions determine support. Writes require explicit user actions. |
| Lifecycle and privacy | Runtime ownership, unload cleanup, temporary-session cleanup, redirect boundaries and diagnostics redaction are tested. |
| Performance | Entity normalization is cached only for the current refresh. Metadata reads have separate 2.5-second timeouts and optional controls share a ten-second budget. Large previews and duplicate control counts are not recorded as attributes; live changes can still produce state rows. |

## Open Quality Rules

| Rule | Remaining work |
| --- | --- |
| brands | Custom-integration icons exist in the external brands repository, but the full Core icon/logo requirement is not verified. Asset hygiene and HACS metadata are separate concerns. |
| config-flow-test-coverage | Complete HA-driven tests of every setup, options, reauth and reconfigure branch. Helper coverage alone is insufficient. |
| entity-unavailable | Monitoring intentionally retains last-known readings while Device online reports offline. This does not fully satisfy HA's sensor availability rule. Keep WOL usable and resolve this as an explicit compatibility decision. |
| test-coverage | CI enforces 95% aggregate line coverage. HA requires more than 95% per module; close the gaps with behavior tests, not exclusions. |
| strict-typing | All integration modules are in the strict mypy scope, guarded against omissions. A second seven-file gate follows imported HA types for runtime, reload, device metadata and sensor/binary-sensor descriptions. Remaining work is narrowing Any payload/HA boundaries elsewhere; the main gate still uses follow_imports=skip and targeted base-class ignores. |

Rule references: [flow coverage](https://contributors.home-assistant.io/core/quality-scale/config-flow-test-coverage/),
[availability](https://contributors.home-assistant.io/core/quality-scale/entity-unavailable/),
[test coverage](https://contributors.home-assistant.io/core/quality-scale/test-coverage/).

## Regression Evidence

- Real HA flow-manager tests cover validation failure/retry, aborted setup,
  identity rejection during reauth/reconfigure, option validation, single reload
  and repair deduplication/recovery on both supported CI baselines. Older HA uses
  small compatibility fallbacks for flow helpers introduced after 2024.8.

- Ambiguous snapshot write errors stop immediately; only HTTP 404/405 permits
  endpoint fallback. No destructive snapshot action has been added.
- Malformed or partial snapshot settings preserve cached targets rather than
  generating false missing-target repairs.
- HA-backed tests exercise ten full setup/unload cycles with real HA-managed
  sessions, checking listener cleanup and collection of old coordinators.
  Repeated failed/cancelled setups are covered separately.
- English/German entity tests cover dynamic labels and stable registry identity.
- Recorder serializer tests retain live counts while verifying stable recorded
  control attributes across twenty count changes. This is not a live DB-rate test.
- Real SQLite Recorder tests additionally verify unchanged refreshes, throughput
  exclusions, cached offline data and snapshot control attribute deduplication.
- A bounded resource runner measures allocations, RSS, tasks, timers and retained
  objects after warmup across setup/recovery/unload cycles. It is not a live soak.
- Stateful loopback HTTP tests cover cookie sessions, expiry, reauthentication,
  malformed data, optional endpoint failures, timeouts and recovery.

## Recommended Work Order

1. Complete the HA-backed flow and per-module coverage gaps.
2. Narrow remaining Any boundaries without weakening the complete-module typing gate.
3. Agree on sensor availability semantics before changing cached offline behavior.
4. Repeat long-running RAM/CPU/Recorder measurements with a recorded commit,
   HA/Python versions, firmware, enabled entities, poll interval and workload.
5. Validate optional controls across firmware and permission profiles. Do not
   promote them based on one device or one successful endpoint response.

## Validation And Release

[Validation](validation.md) defines the full local and CI gates, plus independent
final-head Code Review. The [release checklist](release_0.9.0b1.md)
targets stable HA `2026.11.0` and the `2024.8.0` minimum, and separately tracks
Marketplace lifecycle follow-up checks. No live HA/NAS
validation is implied by local synthetic tests.

Historical evidence remains in the [v0.6.2 live report](live_test_report_v0.6.2.md)
and [DB probe](live_db_probe.md). Those reports do not establish current release
compatibility or present-day database growth.
