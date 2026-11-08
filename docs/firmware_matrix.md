# Device And Firmware Matrix

This matrix separates real-device evidence from automated tests. A result applies
only to the listed model, versions, authentication method and tested features;
neither a passing synthetic test nor another integration's support list confirms
hardware compatibility here. An unverified model is not necessarily incompatible.

## Status Meanings

| Status | Meaning |
| --- | --- |
| `tested` | reproduced on real hardware with Home Assistant; limited to the recorded scope |
| `community_confirmed` | reported working by a user with device/software versions; not reproduced on the maintainer's hardware |
| `fixture_verified` | parser/entity behavior tested against a documented, anonymized real-device fixture; not a live lifecycle result |
| `synthetic_only` | automated tests use invented payloads; no model-specific hardware claim |
| `unverified` | no direct evidence for this integration and model yet |

## Real-Device Matrix

| Device scope | UniFi OS firmware | Feature scope | Status | Coverage notes |
| --- | --- | --- | --- | --- |
| UNAS2 | 5.1.8 | integration lifecycle | tested | setup/reload/reconfigure/reauth, offline/WOL recovery, diagnostics privacy |
| UNAS2 | 5.1.10 | integration lifecycle and optional controls | tested | update-entity flow, post-update recovery, diagnostics, optional feature checks |
| UNAS2 | 5.1.19, Drive 4.3.6 | throughput | tested | read/write throughput confirmed |
| UNAS4 | 5.1.16, Drive 4.3.6 | throughput | community_confirmed | throughput sensors were reported stuck at zero on 0.8.2 while the device UI showed SMB traffic; the 0.8.4 network I/O fallback was confirmed to restore read/write throughput |
| UNAS Pro | not recorded | general compatibility | unverified | real-device evidence and anonymized API fixtures needed |
| UNAS Pro4 | not recorded | general compatibility, multiple pools and SSD cache where present | unverified | real-device evidence and anonymized API fixtures needed |
| UNAS Pro8 | not recorded | general compatibility, multiple pools and SSD cache where present | unverified | real-device evidence and anonymized API fixtures needed |
| Other UniFi Drive / UNAS models | not recorded | general compatibility | unverified | depends on actual endpoint shapes and permissions |

The historical reports do not establish every authentication method or optional
control on each model. New reports must record authentication and permission
scope explicitly. Controls remain experimental even when one operation succeeds.

## Automated Storage Coverage

These are development-branch tests, not new live-device results or a claim that
every published release contains the tested behavior.

| Layout / behavior | Status | Evidence |
| --- | --- | --- |
| Four, seven and eight data disks across two pools; two cache SSDs with overlapping local IDs/slot numbers | synthetic_only | `tests/storage_fixtures.py`, `tests/test_storage_view.py` |
| Global and pool-local disk lists, unrelated/unassigned disks excluded from pool membership | synthetic_only | `tests/test_storage_view.py` |
| Opt-in diagnostics, reordered payloads without duplicate entities, enabled readings across pool/cache disappearance and offline recovery | synthetic_only | `tests/test_core_monitoring_entity_states.py` |
| Multi-pool diagnostics retain counts without raw pool/disk/cache identifiers | synthetic_only | `tests/test_diagnostics_helpers.py` |

No model-specific Pro/Pro4/Pro8 fixture is recorded yet. A future
`fixture_verified` entry must identify its source report, model, OS/Drive versions,
authentication scope and sanitized fixture/test path. Synthetic layouts must
never be relabeled as captured device data.

## Evidence References

- [live_test_report_v0.6.2.md](live_test_report_v0.6.2.md)
- [live_db_probe.md](live_db_probe.md)
- Community feedback: UNAS4 throughput fallback confirmed on 0.8.4

## Contributing Evidence

Follow the [hardware validation guide](hardware_validation.md) and use the
[hardware compatibility form](https://github.com/memphi2/ha-unifi-drive/issues/new?template=hardware_report.yml).
Positive and negative results are useful. You do not need to shut down the NAS,
remove drives, change pools or run write actions to report monitoring support.

Use this when adding a verified row:

```text
Device scope:
UniFi OS / Drive versions:
Home Assistant / integration versions:
Authentication method / permission role (no username):
Storage layout (counts and types only):
Validation date:
Branch/tag:
Evidence type (live / community / real-device fixture / synthetic):
Source report / sanitized fixture and regression test:
Coverage:
- setup/discovery
- reload/restart/recovery
- diagnostics/privacy
- optional control paths
Result:
Not tested:
Notes:
```
