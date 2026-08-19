# Changelog

## v0.8.7 - Dynamic drive entity discovery

Bug fix release for `v0.8.7`:

- Adds missing dynamic entity creation for drives added to an already known
  storage pool after initial setup.
- Fixes the case where a RAID expansion updates pool drive count, but the new
  drive's Status, Temperature and Power-On Hours entities are not created after
  reload or reconfigure.
- Keeps existing pool entities stable and only adds the missing drive entities
  when the coordinator sees new drive data.

## v0.8.6 - HA 2026.8 compatibility and issue reporting

Patch release for `v0.8.6`:

- Uses Home Assistant's config-entry-scoped device-registry lookup for
  `2026.8` and later while keeping the legacy fallback for older supported Home
  Assistant versions.
- Removes use of the deprecated Home Assistant `PERCENTAGE` unit constant for
  percentage sensors while keeping sensor units as `%`.
- Adds structured GitHub issue templates for bug reports, support questions and
  feature requests.
- Keeps discovery, diagnostics, snapshot inventory and optional local controls
  unchanged.

## v0.8.5 - LTS and runtime efficiency hardening

Patch release for `v0.8.5`:

- Reduces snapshot inventory memory and offline-cache overhead by keeping only
  the target metadata needed for entity state, diagnostics and repairs.
- Limits retained snapshot inventory metadata to stable, support-relevant fields
  so repeated polling does not keep unnecessary payload fragments alive.
- Rounds CPU temperature sensor states for better recorder stability and fewer
  noisy database writes.
- Removes config-flow reload calls that conflict with Home Assistant's
  config-entry update-listener deprecation path for `2026.6` and later.
- Adds repository validation to prevent that deprecated config-flow reload
  pattern from returning.
- Documents the maintenance/LTS policy for the `0.8.x` line and validates that
  the Home Assistant minimum advertised to HACS remains covered by CI.

## v0.8.4 - Throughput fallback and compatibility validation

Patch release for `v0.8.4`:

- Adds a read-only network I/O fallback for live throughput sensors on devices
  whose storage payload reports zero throughput while the device UI shows active
  SMB traffic.
- Keeps storage-payload throughput preferred when it reports non-zero values and
  preserves zero as a valid idle state when no fallback source has traffic.
- Adds privacy-safe throughput diagnostics that report selected source and
  zero/non-zero/missing status without exposing raw payload values.
- Adds a Home Assistant validation matrix for the advertised minimum support
  line and the final `2026.6.0` line.
- Pins the matching `pytest-homeassistant-custom-component` release for each
  Home Assistant test line and isolates the plugin's Home Assistant dependency
  so the final Home Assistant target controls the tested runtime.
- Keeps `mypy` syntax targeting on Python `3.12` while HACS still advertises
  Home Assistant `2024.8.0` compatibility.
- Keeps release preflight jobs on Python `3.14` and verifies that repository
  checks enforce the compatibility matrix.
- Removes a pytest option that is only understood by newer pytest-asyncio
  versions so the older supported Home Assistant test line runs cleanly.

## v0.8.2 - Release privacy and legal audit hardening

Bug fix release for `v0.8.2`:

- Adds release ZIP privacy, legal and layout validation for the generated HACS
  artifact.
- Adds public GitHub surface auditing for releases, release ZIP assets, PRs,
  issues, reviews, and the active HACS PR.
- Keeps local/private marker checks generic in the repository and reads
  environment-specific marker values only from `UNIFI_UNAS_FORBIDDEN_MARKERS`.
- Removes local-address example literals from user-facing strings and tests.
- Keeps the `v0.8.0` setup reliability, device-registry behavior, discovery
  write-throttle, diagnostics, HACS metadata, snapshot inventory and optional
  local control behavior unchanged.

## v0.8.1 - Reinstall guidance and device metadata fixes

Patch release for `v0.8.1`:

- Clarifies the breaking-change upgrade path for users coming from versions
  before `0.8.0`.
- Makes explicit that the old Home Assistant integration entry must be removed
  first and that the old custom integration installation must then be removed in
  HACS so the old `custom_components/unifi_drive` folder is no longer loaded.
- Improves fresh-install device metadata so Home Assistant device info can pick
  up firmware from raw or client-cached UniFi OS system metadata.
- Adds a default-enabled device connection binary sensor so Home Assistant
  activity/logbook views can show online/offline availability transitions while
  core monitoring entities continue to keep cached values during outages.
- Speeds up entry setup/reload by registering core entities after the first
  storage poll and deferring optional Fan, Backup and Snapshot endpoint reads
  until the entities already exist.
- Keeps the `v0.8.0` runtime behavior unchanged.

## v0.8.0 - Reliability and release-line hardening

Release-line update for `v0.8.0`:

- Fixes the frontend setup race that could show `Invalid flow specified` after
  submitting optional features even though the config entry was created.
- Allows Home Assistant-managed device entries for this config entry to be
  removed without requiring a restart first.
- Throttles metadata-only discovery writes to reduce Home Assistant config-entry DB
  churn during rapid repeated discovery events.
- Keeps trusted identity and confidence updates intact while avoiding unnecessary
  runtime-entry updates when only `discovery_last_seen` changes within a short
  window.
- Simplifies config-entry identity handling for current device-scoped IDs and
  strengthens focused test coverage around setup, reauth, reconfigure, and
  discovery dedupe paths.
- Keeps diagnostics, HACS metadata, quality-scale tracking, snapshot inventory,
  and optional local control behavior intact.

## v0.7.1 - Discovery write-throttle hardening

Performance and reliability maintenance release for `v0.7.1`:

- Throttles metadata-only discovery writes to reduce Home Assistant config-entry DB
  churn during rapid repeated discovery events.
- Keeps trusted identity and confidence updates intact while avoiding unnecessary
  runtime-entry updates when only `discovery_last_seen` changes within a short
  window.
- Prevents setup cleanup from aborting the active user-confirmed discovery flow,
  fixing the `Invalid flow specified` dialog after submitting optional features.
- Allows Home Assistant-managed device entries for this config entry to be
  removed without requiring a restart first.
- Adds direct unit coverage for discovery write-throttle behavior and invalid
  discovery timestamps.
- Keeps all previously stable discovery, lifecycle, diagnostics, and control
  behavior unchanged.

## v0.7.0 - Stability and test hardening

Maintenance release to prepare the next distribution point after `v0.6.2`:

- Fixes snapshot target recovery so restored targets do not retain stale missing-state
  counters.
- Avoids over-aggressive local `homeassistant` stub cleanup when the HA test
  helper package is not installed, which prevented some test environments from
  collecting correctly.
- Makes wake-on-LAN helper tests resilient to test-runner plugin variation by
  explicitly executing async helpers with a local event loop.
- Keeps integration architecture and runtime behavior unchanged while improving
  release hygiene and long-run reliability.

## v0.6.2 - Reliability Hardening

Focused maintenance release for the `v0.6.2` branch and the tracked
Bronze/Silver/Gold quality-scale baseline.

- Cleans config-entry runtime data and listener registrations if platform setup
  fails after the coordinator was created.
- Delays duplicate-discovery cleanup scheduling until entry setup has completed
  successfully, avoiding stale delayed callbacks for failed setups.
- Strengthens repository hygiene checks to catch standalone JWT-like long-lived
  tokens in tracked files.
- Adds explicit platform parallel-update declarations, higher-tier
  quality-scale tracking, Bandit CI coverage, and README Platinum-readiness
  documentation without changing the feature surface.
- Adds a typed runtime `ConfigEntry` foundation, `py.typed`, and translated
  service action exceptions as additional Platinum-readiness groundwork.
- Completes the tracked Bronze, Silver, and Gold quality-scale statuses,
  including translated entity action errors, icon translations, stale-device
  removal support, and an enforced coverage gate above 95%.
- Keeps powered-off/offline devices out of snapshot-read repairs so
  Wake-on-LAN remains the intended recovery path.
- Hardens damaged config-entry handling for missing hosts and corrupted numeric
  option defaults, and documents the live HA test pass on UniFi OS firmware
  5.1.8.
- Documents and validates the live UniFi OS update from 5.1.8 to 5.1.10,
  including the update reboot window, post-update recovery, reload behavior,
  diagnostics, repairs, and the remaining REST negative-path behavior for
  unsupported explicit update versions.
- Extends the 5.1.10 live report with firmware-dependent fan-control,
  snapshot-control, update-safety, diagnostics, repairs, and device-registry
  validation without running destructive snapshot or power actions.
- Adds a strict mypy gate for runtime, the API client/mixins, config-flow
  helper, diagnostics, discovery, repairs, services, snapshot, storage and
  support modules, and fixes the first typing issues found by that gate.
- Extends the strict mypy gate to config-entry setup/unload, coordinator,
  discovery parsing, shared entity base helpers, and typed snapshot schedule
  service updates.
- Expands strict-typing scope to sensor and binary-sensor description modules
  and makes storage helper exports explicit for typed imports.
- Strengthens repository validation so the strict mypy gate must reference
  existing files and cover every API client module.
- Keeps Home Assistant Device Info firmware metadata in sync with coordinator
  refresh data after UniFi OS updates.
- Moves GitHub workflow actions to Node.js 24-capable releases and adds a
  repository check so deprecated Node.js 20 actions do not return unnoticed.
- Keeps the Bronze readiness architecture, HACS metadata, diagnostics schema,
  discovery behavior, and snapshot feature surface unchanged.

## v0.6.0 - Bronze Readiness

Quality-focused release candidate for Home Assistant Bronze Quality Scale
readiness.

- Adds `quality_scale.yaml` with the implemented Bronze rule status.
- Stores loaded runtime coordinator data on `ConfigEntry.runtime_data` while
  retaining the existing compatibility mirror for current platform setup paths.
- Reduces repeated connection-failure logging and records recovery once the
  local API becomes reachable again.
- Adds config-flow field descriptions for setup, reauth, reconfigure, discovery,
  and optional feature forms.
- Aligns update entities with Home Assistant's `has_entity_name` entity naming
  convention.
- Adds explicit README removal instructions for Home Assistant and HACS users.
- Strengthens repository validation for quality-scale status, config-flow field
  descriptions, release metadata, HACS metadata, translations, and tracked-file
  hygiene.
- Expands CI coverage so branch pushes for release work run the complete test
  suite instead of a hand-maintained subset.
- Documents current maturity, known limitations, privacy-safe diagnostics, and
  the remaining Silver-level roadmap.

## v0.5.0 - Initial Release

Initial public release baseline for the unofficial Home Assistant integration
for UniFi Drive / UNAS.

- Provides local Home Assistant entities for storage health, capacity,
  throughput, drive temperatures, UniFi OS and Drive versions, uptime, system
  status, IP addresses, fan mode, updates, Wake-on-LAN, backup tasks, and
  optional snapshot controls.
- Includes config flow, reconfigure support, options flow, diagnostics,
  translations, entity categories, Home Assistant services, and HACS metadata.
- Uses conservative local discovery for UniFi Drive / UNAS candidates with
  trusted identity handling for host aliases, MAC hints, VLAN and
  multi-interface observations, conflict diagnostics, and reduced repeated
  setup prompts.
- Keeps startup and reload behavior stable by preserving cached online data
  during transient startup failures and by avoiding reloads for discovery
  metadata-only entry updates.
- Adds explicit legal and asset hygiene documentation for the unofficial
  project status, descriptive use of UniFi / UNAS / Ubiquiti names, original
  project artwork, and exclusion of official vendor assets or proprietary
  material.
- Extends repository checks to validate release metadata, legal disclaimers,
  tracked-file hygiene, generated artifacts, secrets, official/vendor asset
  paths, and proprietary content markers.
