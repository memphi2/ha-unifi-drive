# v0.6.2 Live Test Report

Historical report: these results apply to the versions and device below, not
to the current development branch or Home Assistant release.

This report records the live Home Assistant validation performed for the
`v0.6.2` branch. It intentionally avoids local host addresses, usernames,
passwords, tokens, MAC addresses, and snapshot target names.

## Test Environment

| Item | Value |
| --- | --- |
| Integration version | 0.6.2 |
| Home Assistant | 2026.5.3 |
| UniFi OS firmware | Started on 5.1.8, updated to 5.1.10 during the follow-up pass |
| UniFi Drive app | 4.2.2 |
| Test scope | UNAS2 on a local Home Assistant test instance |
| Firmware update | UniFi OS 5.1.10 installed through the integration update entity |

## Local Validation

These gates were run locally before and during the live pass:

| Gate | Result |
| --- | --- |
| `python scripts/check_repo.py` | Passed |
| `ruff check custom_components tests scripts` | Passed |
| `bandit -q -r custom_components scripts` | Passed |
| `python -m compileall -q custom_components/unifi_unas tests` | Passed |
| `git diff --check` | Passed |
| `python -m coverage run -m pytest -q` | 447 tests passed before the live destructive pass |
| `python -m coverage report` | 95% line coverage before the live destructive pass |

The destructive pass also added focused regression tests for corrupted numeric
config defaults, missing required config-entry host data, and fallback integer
handling.

The 5.1.10 follow-up pass added regression coverage for live device-registry
firmware metadata updates after coordinator refreshes.

## Live Install And Startup

| Test | Result |
| --- | --- |
| Install `custom_components/unifi_unas` to the HA test config share | Passed |
| Verify installed manifest version | Passed, 0.6.2 |
| Full Home Assistant restart | Passed |
| Config entry returns to `loaded` after restart | Passed |
| Core entities return to available state | Passed |
| Post-start 90 second stability poll | Passed, no `unknown`, `unavailable`, or HTTP state gaps |

## Reload And Lifecycle

| Test | Result |
| --- | --- |
| Reload config entry through Home Assistant service | Passed |
| Reload after shutdown/WOL recovery | Passed |
| Reload after UniFi OS 5.1.10 update | Passed |
| Runtime state after reload | `systemstatus` online, storage health healthy |
| Config-entry/device registry consistency | Passed, one entry, one device, expected entity set |
| Open UniFi Drive config/discovery flow check | Passed, no stale UniFi Drive flows left open |

## UniFi OS 5.1.10 Firmware Update

| Test | Result |
| --- | --- |
| Pre-update UniFi OS update entity | Passed, installed `5.1.8`, latest `5.1.10`, state `on` |
| Reject mismatched requested update version | No update started; Home Assistant REST service returned a generic HTTP 500 instead of a detailed validation response |
| Start offered UniFi OS update through update entity | Passed, service accepted the update request |
| Device enters reboot/update window | Passed, device API became unreachable and `systemstatus` later changed to `offline` |
| Home Assistant stays available during device update | Passed |
| Recovery to UniFi OS 5.1.10 | Passed, version sensor and update entity reported `5.1.10` |
| Post-update stability window | Passed, stable for 120 seconds after recovery |
| Device Registry firmware metadata | Initially stale at `5.1.8`; fixed so coordinator refresh updates HA device `sw_version` to `5.1.10` |
| HA Device Info after fix | Passed, device info shows firmware `5.1.10` |
| Repairs after firmware update | Passed, no UniFi Drive repair issues |
| Diagnostics after firmware update | Passed, diagnostics schema remained versioned and privacy scan found no credential leaks |

Observed firmware-update timing:

- The device API became unreachable about 40 seconds after the update request.
- Home Assistant marked the system-status sensor offline after the local API had
  been unreachable for a short period.
- The device API returned about 2.5 minutes after the update request.
- Home Assistant reported `5.1.10` and stable online state about 4 minutes after
  the update request.

Negative finding kept for follow-up: calling Home Assistant's REST service for a
specific, unsupported update version does not start an update, but HA returns a
generic HTTP 500 response. The integration now raises a `ServiceValidationError`
for that path, but the REST API still surfaces the error generically in this test
environment.

## Firmware-Specific Feature Validation On 5.1.10

After the system reported UniFi OS 5.1.10 consistently, the firmware-dependent
control paths were validated again without running destructive actions.

| Area | Test | Result |
| --- | --- | --- |
| Fan control | Native fan mode no-op write through the integration service | Passed, accepted by the local endpoint and the select stayed on a valid option |
| Fan control | Invalid native fan mode | Passed, rejected by Home Assistant service validation before a device write |
| Snapshot settings | Snapshot schedule no-op write | Passed |
| Snapshot settings | Snapshot limit no-op write | Passed |
| Snapshot settings | Snapshot enabled switch no-op write | Passed |
| Snapshot inventory | Inventory entities after 5.1.10 | Passed, one target reported live inventory and one target reported the documented unsupported fallback |
| Snapshot action safety | Invalid snapshot target for a settings service | Passed, no target was changed; Home Assistant REST surfaced a generic HTTP 500 for the translated service exception |
| Update entity | Installed/latest version after update | Passed, installed `5.1.10`, latest `5.1.10`, update state `off` |
| Update action safety | Invalid explicit firmware version | Passed, no update started; Home Assistant REST surfaced the same generic HTTP 500 behavior as the earlier negative test |
| System buttons | Restart/shutdown button exposure after update | Passed, buttons remained present and were intentionally not pressed again |
| Backup buttons | Backup task exposure | Passed, no backup task button was exposed by this test system |
| Repairs | UniFi Drive repair issue count after firmware-specific writes | Passed, 0 issues |
| Diagnostics | Schema and privacy after firmware-specific writes | Passed, schema version 1 and no credential, token, host, UNAS credential, or local device address leaked |
| Device registry | Firmware metadata after firmware-specific writes | Passed, HA device registry still reported `5.1.10` |

The diagnostics privacy scan matched the text
`homeassistant.components.diagnostics.async_redact_data` inside the static
`privacy.redaction_helper` field. This is the Home Assistant helper path, not a
local CIFS username, credential, host name, device identity, or runtime payload
value.

## Options, Reconfigure, And Reauth

| Test | Result |
| --- | --- |
| Options flow start and abort | Passed |
| Reconfigure menu start and abort | Passed |
| Reconfigure connection step | Passed |
| Reconfigure with unreachable host | Passed, form error `cannot_connect` |
| Reconfigure with valid connection data | Passed, abort reason `reconfigure_successful` |
| Entry identity after reconfigure | Preserved entry ID and unique identity state |
| Wrong password in stored config entry | Passed, entry moved to `setup_error` and HA opened one UniFi Drive reauth flow |
| Restore wrong-password case | Passed through reconfigure plus explicit reload |

## Offline, Repairs, And Wake-on-LAN

| Test | Result |
| --- | --- |
| Shutdown through integration service | Passed |
| Device becomes unreachable after shutdown | Passed |
| Offline device creates repair issue | Passed, no UniFi Drive repair issue created |
| `systemstatus` changes to `offline` | Passed |
| Wake-on-LAN through integration service | Passed |
| Device returns after WOL | Passed |
| `systemstatus` returns to `online` | Passed |
| Storage health returns to `healthy` | Passed |
| WOL button remains available while device is offline | Passed |

Expected behavior: a powered-off device is not treated as a repair condition.
This is required so Wake-on-LAN remains useful.

## Diagnostics And Privacy

| Test | Result |
| --- | --- |
| Diagnostics endpoint returns JSON | Passed |
| Diagnostics schema version | 1 |
| HA API token leak scan | Passed |
| UNAS credential leak scan | Passed |
| CIFS password leak scan | Passed |
| Local host/address leak scan | Passed |
| Snapshot target identifier/name leak scan | Covered by existing tests and live diagnostics shape |

One local CIFS username string matched only inside the diagnostics
`privacy.redaction_helper` metadata field. It was not present in config-entry
data, runtime payloads, discovery data, snapshot data, or credentials.

## Corrupted Config Entry Tests

The tests below used valid JSON storage mutations only. Syntactically broken
Home Assistant storage JSON was intentionally not tested because that validates
Home Assistant's storage loader rather than this integration.

| Damage case | Live result | Follow-up |
| --- | --- | --- |
| Wrong stored password | Entry moved to `setup_error`; one reauth flow opened; no repair issue | Restored through reconfigure plus reload |
| Missing host | Entry moved to `setup_error`; HA stayed available; no repair issue | Runtime setup now raises a clean `ConfigEntryError` instead of relying on a raw missing-key failure |
| Missing username | Entry moved to `setup_error`; one reauth flow opened; no repair issue | Restored through reconfigure plus reload |
| Missing password | Did not produce a stable damaged state in this live run because HA can rewrite loaded in-memory entry data during restart | Auth-loss behavior is covered by wrong-password and missing-username cases |
| Corrupted `scan_interval` option type | Entry stayed `loaded`, but the feature reconfigure form initially returned HTTP 500 | Fixed by sanitizing numeric config-flow defaults; retest passed and restored `scan_interval` to `30` |

Important operational finding: restoring `.storage/core.config_entries` while
Home Assistant is running is not reliable. Home Assistant may write its
in-memory config entry back to storage during shutdown. Live recovery should use
Home Assistant's reconfigure flow plus an explicit config-entry reload whenever
possible.

## Code Fixes From Live Findings

The live damage tests produced targeted hardening changes:

- Corrupted integer option values now fall back to defaults instead of breaking
  runtime setup.
- Missing config-entry host data now fails with a clear `ConfigEntryError`.
- Config-flow schemas now sanitize corrupted numeric defaults before rendering
  reconfigure/options forms.
- Device-registry firmware metadata now follows coordinator refreshes so HA
  Device Info updates from `5.1.8` to `5.1.10` after firmware updates.
- Unsupported explicit update-version requests now use a service-validation
  error path instead of a generic integration error.
- Regression tests cover corrupted numeric defaults, corrupted integer option
  fallback, missing-host setup behavior, and dynamic device firmware metadata.

## Final State

After restoration and retesting:

| Check | Result |
| --- | --- |
| Config entry | `loaded` |
| Device state sensor | `online` |
| Storage health sensor | `healthy` |
| UniFi OS version sensor | `5.1.10` |
| UniFi OS update entity | `off`, installed `5.1.10`, latest `5.1.10` |
| HA Device Info firmware | `5.1.10` |
| Drive version sensor | `4.2.2` |
| Wake-on-LAN button | Available |
| UniFi Drive repair issues | 0 |
| Open UniFi Drive flows | 0 |
| Stored `scan_interval` | 30 |
| Stored credential field names | Present; values were not exported or documented |

## Not Run In This Pass

- Syntactically broken Home Assistant `.storage` JSON.
- Destructive snapshot delete/restore actions. The integration does not expose
  destructive snapshot delete actions and this pass did not add any.
