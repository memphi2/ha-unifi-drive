# Maintenance and LTS Policy

This document describes the maintenance policy for this custom integration. It is
not an official Home Assistant or vendor support promise; it defines how this
repository keeps a stable release line dependable for Marketplace and HACS users.

## Supported Home Assistant Versions

The minimum supported Home Assistant version is the version declared in
`hacs.json`. That version must also be tested in the validation workflow.

The validation workflow must cover:

- the Home Assistant minimum advertised in `hacs.json`
- the current Home Assistant target line used for forward compatibility checks
- the Python version required by each tested Home Assistant line

If the HACS minimum version is raised, the change must be made deliberately and
must be reflected in CI, release notes and user-facing documentation.

## Dependency Maintenance Cadence

Routine tool updates are reviewed quarterly, with at most one open version-update
PR for GitHub Actions and one for Python CI tools. Each ecosystem uses a single
Dependabot group. Action references remain pinned to commit SHAs.

`requirements/ci/requirements.txt` is the only maintained manifest for the direct
CI tools Ruff, Mypy and Bandit. Its versions must work on both Python matrix legs.
It is a hand-maintained direct-dependency list, not a generated environment lock:
do not put `pip freeze` output, transitive dependencies, HA, its test helper or
remote HA constraint includes into it. Dependabot's pip job is scoped to that
directory. CI installs the file together with the matrix's HA/helper pair and
that HA release's constraints, then runs `pip check`.

The bootstrap pip comes from the selected Python environment; CI no longer
upgrades it to the latest release on every run. Transitive tool dependencies are
not fully locked, so the weekly validation remains important. Repository tests
guard the direct-only manifest, update cadence and security-update separation.

Security fixes are exceptions to the quarterly schedule: triage alerts promptly
and handle security PRs separately, without waiting for a routine update bundle.
Dependabot alerts and automatic security updates must remain enabled on GitHub.
The version-update PR limit does not cap security PRs; GitHub manages their
separate limit. Do not add blanket ignores or redirect Dependabot to a non-default
branch, which would change how security configuration applies.

Dependabot can only fix dependencies it recognizes. This tool manifest does not
claim full security coverage of HA's resolved environment or the integration's
runtime requirements in `manifest.json`. Review upstream HA/runtime advisories
and resolve applicable vulnerabilities through a tested compatibility update.

Compatibility checks still run weekly and on branch pushes/PRs. Review new HA
releases and announced API removals separately from routine tooling updates.
Change HA and its matching test helper together, keep the minimum-version leg,
and address required Python/HA migrations before their deadlines. Security and
compatibility fixes must not wait for the next quarter.

References: [Dependabot schedule and PR limits](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference),
[security updates](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/secure-your-dependencies/configure-security-updates).

## November 2026 Compatibility Review

Reviewed on `2026-11-01`. Home Assistant `2026.11` is still a beta at this review
date. The configured CI targets remain `2024.8.0` / Python `3.12` and `2026.10.0` /
Python `3.14`. Marketplace documentation and catalog metadata alone do not prove
runtime compatibility with the November release.

The `v0.8.9` [release checklist](release_0.8.9.md) tracks the remaining gates.
Release notes are prepared, but no November stable compatibility claim or live
Marketplace test result is implied.

| Area | Current status | Required follow-up |
| --- | --- | --- |
| Marketplace | Already in the shared catalog; `hacs.json` stays unchanged and the manifest declares `computers_network.nas_servers`. | Test a fresh install, HACS takeover, update and removal in HA `2026.11`; do not require reinstalling working `0.8.0+` entries. |
| HA test baseline | November is not yet a CI matrix target. | Validate the full suite with matching HA/test-helper versions, including the real HA-backed tests, before updating the target and declaring support. Keep the advertised minimum leg. |
| `DeviceInfo` dataclass | Registry metadata reads dataclass attributes; dictionary access is restricted to the legacy representation. Only non-empty strings are synchronized, so `UNDEFINED` cannot clear or corrupt existing fields. | Keep tests for both representations, missing firmware and unchanged metadata. The full November HA baseline remains a separate gate. |
| Config-flow reloads | Reauth/reconfigure use `async_update_and_abort`; the entry listener owns reloads. Repository checks reject competing reload helpers. | Preserve this behavior: combining a reload helper with the listener becomes an error in HA `2026.12`. |
| Restore state | No direct `RestoreStateData.last_states` use exists in the integration; a repository guard rejects reintroduction. | Keep using supported restore APIs. The removed `last_states` API is not a reason to rewrite this integration. |
| Other platform changes | No climate/water-heater platform, HA Modbus helper or custom statistics-import path is implemented here. | Do not introduce unrelated migrations for those APIs; continue reviewing the APIs actually used by UNAS. |

Official references:

- [Marketplace behavior and migration](https://contributors.home-assistant.io/marketplace/how-it-works/)
- [Integration categories](https://contributors.home-assistant.io/core/integrations/categories/)
- [DeviceInfo dataclass and compatibility methods](https://contributors.home-assistant.io/blog/2026/10/13/device-info-class/)
- [Config-entry listener and reload deprecation](https://contributors.home-assistant.io/blog/2026/05/07/config-entry-listener-together-with-reloading-methods/)
- [RestoreStateData.last_states removal](https://contributors.home-assistant.io/blog/2026/10/06/restore-state-last-states-removal/)

## Remaining Maintenance Work

- The runtime requirement `unifi-discovery>=1.5.0` has no upper bound. Its exact
  resolved version can change independently of this integration. Review a tested
  version policy against Home Assistant's own requirements rather than adding
  an arbitrary pin that conflicts with core.
- CI resolves the pinned HA runtime and helper together and runs `pip check`.
  Dependency bypasses are rejected by repository checks. Run the HA-backed
  tests before changing the baseline; installation alone is not compatibility.
- The Python `3.14` test leg sets the fixture event-loop scope explicitly. The
  minimum-version leg keeps its older pytest-asyncio-compatible configuration.
- Release publication now depends on the reusable full validation workflow for
  the same tagged commit. The tag must match the manifest version. A green run
  still does not replace bot review or the required November live-test evidence.
- Keep scheduled drift checks separate from the reproducible supported-version
  matrix. A beta-only green run must not be described as stable-release evidence.

## Stable Patch Releases

Patch releases are intended for low-risk maintenance only:

- compatibility fixes for supported Home Assistant versions
- deprecation fixes before a future Home Assistant release turns them into errors
- privacy, security, diagnostics and repository hygiene fixes
- test, CI and documentation corrections
- bug fixes that preserve existing config entries and entity identities

Patch releases must not introduce intentional breaking changes. In particular,
they must not rename the integration domain, change entity unique ID formats,
drop config-entry compatibility, or remove documented working behavior.

## Minor Releases

Minor releases may include larger compatibility work when it is still safe for
existing users. Examples include new diagnostics fields, additional tests,
documentation restructuring, or opt-in controls.

Any behavior that may require users to reinstall, reconfigure, or manually clean
up entities must be treated as a breaking change and documented clearly.

## Breaking Changes

Breaking changes require a new minor or major release. The release notes must
state:

- what changed
- who is affected
- whether the integration must be removed and reinstalled
- how to preserve or recreate expected entities
- which old files or directories users may need to remove

Breaking changes must not be hidden in patch releases.

## Backport Rules

If a dedicated maintenance branch is used later, only targeted changes should be
backported:

- confirmed bug fixes
- Home Assistant compatibility fixes
- privacy or security hardening
- CI and release validation fixes
- documentation corrections for the maintained line

New feature work, large refactors and entity model changes should remain on the
development line unless they are required to fix a supported regression.

## Deprecation Handling

Known Home Assistant deprecations should be fixed before they become hard
errors. Repository checks should guard against repeating known unsafe patterns
when practical.

Current examples include:

- config flows must not call config-entry reload methods when the integration
  also registers a config-entry update listener
- the advertised HACS minimum must remain covered by CI
- workflow Python versions must cover both the minimum and current Home
  Assistant test lines

## Firmware and Device Scope

Firmware-specific behavior must be documented in the firmware matrix when it is
confirmed by live testing or user evidence. A throughput limitation or endpoint
variation on one firmware/device combination should not be generalized to all
UNAS models unless the evidence supports that.

Optional local controls remain experimental when they depend on undocumented
local endpoints, firmware behavior or account permissions.
