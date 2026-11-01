# Bronze Readiness Assessment

This document summarizes the Home Assistant Bronze Quality Scale readiness work
for the unofficial UniFi Drive / UNAS custom integration. This is historical
implementation evidence, not proof of complete tier compliance. Current gaps
are tracked in `quality_scale.yaml`.

## What Improved

- Added `custom_components/unifi_unas/quality_scale.yaml` with every Bronze
  rule tracked as implemented.
- Stored the loaded coordinator on `ConfigEntry.runtime_data` while preserving
  the existing `hass.data` compatibility mirror.
- Reduced repeated connection-failure logging and added a single recovery log
  when the local API becomes reachable again.
- Added config-flow field descriptions for setup, zeroconf confirmation,
  discovery selection, reauthentication, reconfigure, and optional feature
  forms.
- Aligned update entities with Home Assistant's `has_entity_name` naming
  convention.
- Strengthened repository checks for quality-scale status, config-flow field
  descriptions, HACS metadata safety, release-note existence, changelog
  consistency, translation alignment, and tracked-file hygiene.
- Expanded CI to run on release branches and execute the complete test suite.
- Added translated service/entity action errors, icon translations, stale-device
  removal support, and a coverage gate above 95% as the later Silver/Gold
  baseline.
- Documented current maturity, removal, known limitations, privacy-safe
  diagnostics, experimental snapshot behavior, and support-oriented
  troubleshooting.

## Silver And Gold Baseline

CI enforces an aggregate 95% coverage floor, not HA's per-module requirement.
Complete flow coverage and monitoring availability also remain open. Continue adding real-device or
recorded-response coverage for permission-denied fan, update, backup, and
snapshot write endpoints so firmware changes do not regress the baseline.

## Intentional Experimental Areas

- Snapshot settings, inventory, and create controls remain opt-in and
  experimental because firmware and permission behavior varies.
- Backup-task buttons remain endpoint-dependent and hidden or unavailable when
  task metadata is not exposed.
- Fan control, restart, shutdown, and update install remain local console-level
  controls and require appropriate UniFi permissions.
- Discovery confidence and identity matching reduce duplicate prompts but do
  not force-match uncertain hosts across VLAN or interface changes.

## Risk Assessment

- Runtime risk is moderate for optional controls because UniFi local endpoints
  are not documented as stable public APIs.
- Discovery risk is moderate in heterogeneous networks with multiple interfaces,
  VLANs, stale DNS, or incomplete mDNS metadata.
- Monitoring risk is low for read-only storage/system entities because failures
  are contained by the coordinator and entities become unavailable when needed.
- Privacy risk is low after diagnostics redaction and aliasing, assuming future
  diagnostics additions keep raw payload values out of exports.

## Recommended Next Roadmap

1. Add reauthentication coverage for invalid credentials and expired sessions.
2. Add targeted live-smoke scenarios for reload, restart, offline startup, and
   recovery without availability flapping.
3. Keep the coverage gate above 95% while adding targeted HA-backed tests for
   new runtime paths.
4. Extend diagnostics schema only through additive versioned fields.
5. Promote snapshot controls from experimental only after testing multiple
   firmware versions and permission profiles.
6. Prepare a strict-typing checklist before claiming Platinum readiness.
