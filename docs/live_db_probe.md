# Live DB Write Probe

Historical evidence only: this short probe predates the current release branch.
The original record does not identify the exact HA version or commit; its row
counts are not a current performance guarantee.

Current recorder policy keeps snapshot previews, names, IDs and descriptions
in live HA attributes, but excludes them from recorded attributes. Pool binary
sensors likewise exclude duplicate rebuild/sync progress attributes; dedicated
progress sensors remain recordable. Counts, timestamps and health history remain.
Snapshot controls exclude duplicate total/locked counts from recorded attributes;
the inventory sensor remains the source of recorded count history.
Tests use HA's recorder serializer and verify that identical refreshes do not
emit new snapshot sensor state-change events. This reduces attribute payloads;
it does not promise zero state rows when live-only attributes change. A new
long-duration live DB probe is still required for device-specific row rates.

## Next Authorized Soak Test

Record the tested commit, HA/Python versions, NAS firmware, enabled entities,
poll interval, Recorder exclusions and retention first. Keep connection details
and credentials in local environment variables, not reports or tracked files.

1. Measure a one-hour idle baseline, then a representative 24-hour workload.
   Record HA RSS, CPU, pending tasks/listeners, API request rate and per-domain
   `states`/`state_attributes` row deltas. Compare rates, not just total DB size.
2. Exercise reload, normal offline/online recovery and a slow optional endpoint.
   Confirm resource counts settle after each cycle. Do not infer a leak solely
   from allocator RSS remaining above its initial value.
3. Compare unchanged refreshes, snapshot count changes and real control state
   changes. Do not create snapshots or power-cycle the NAS without explicit
   authorization; metadata-only changes still create normal HA state events.
4. Repeat with unnecessary controls excluded from Recorder. Preserve the
   inventory/count history needed by the user and publish only aggregate results.

The automated lifecycle and serializer tests complement this measurement; they
do not replace it or claim a current live-test result.

This report documents the live recorder/config-entry write probe performed
during discovery write-throttle hardening on the Home Assistant test instance.
It excludes credentials, tokens, private hostnames, and local network details.

## Scope

- integration under test: `custom_components/unifi_unas`
- action pattern: idle window + three explicit `reload_config_entry` cycles
- focus:
  - `states` growth
  - `state_attributes` growth
  - `events` growth
  - `unifi_unas` state row growth
  - config-entry storage touch (`.storage/core.config_entries`)

## Baseline Behavior Before Throttle Deployment

- repeated reloads updated `discovery_last_seen` each cycle
- `.storage/core.config_entries` changed on each reload cycle

Observed step deltas:

- `idle_30s`: `state+301`, `attr+0`, `event+398`, `unifi_rows+63`, `cfg_touch=yes`
- `reload_1_plus30s`: `state+157`, `attr+1`, `event+1`, `unifi_rows+120`, `cfg_touch=yes`
- `reload_2_plus30s`: `state+158`, `attr+0`, `event+1`, `unifi_rows+120`, `cfg_touch=yes`
- `reload_3_plus30s`: `state+160`, `attr+0`, `event+1`, `unifi_rows+120`, `cfg_touch=yes`

## Behavior After Throttle Deployment

- `discovery_last_seen` changed only once inside the short reload window
- `.storage/core.config_entries` changed on first reload only
- subsequent short-window reloads did not touch config-entry storage

Observed step deltas:

- `idle_30s`: `state+36`, `attr+0`, `event+0`, `unifi_rows+2`, `cfg_touch=no`
- `reload_1_plus30s`: `state+156`, `attr+0`, `event+1`, `unifi_rows+120`, `cfg_touch=yes`
- `reload_2_plus30s`: `state+160`, `attr+0`, `event+1`, `unifi_rows+120`, `cfg_touch=no`
- `reload_3_plus30s`: `state+159`, `attr+1`, `event+1`, `unifi_rows+120`, `cfg_touch=no`

## Interpretation

- The discovery write-throttle is effective for short-interval metadata-only
  discovery updates.
- Explicit reloads still generate normal recorder writes for entities; this is
  expected because entities are reloaded and state is republished.
- No sign of repeated config-entry write churn after the first reload within the
  throttle window.
