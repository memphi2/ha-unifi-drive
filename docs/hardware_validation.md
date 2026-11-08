# Hardware Compatibility Reports

Reports from UNAS Pro, Pro4 and Pro8 owners help close the gaps in the
[device and firmware matrix](firmware_matrix.md). Working setups are just as
useful as failures. Report only what you observed with **memphi2/ha-unifi-drive**;
results from another integration do not establish compatibility here.

## What To Include

Use the [hardware compatibility form](https://github.com/memphi2/ha-unifi-drive/issues/new?template=hardware_report.yml).
Record:

- Exact model, Home Assistant and integration versions, UniFi OS and Drive versions.
- Authentication method and account permission role, never the username or key.
- Number of populated data bays, HDD/SSD types, pool count and disks per pool.
- Number of cache SSDs and NVMe/SATA type, if known. Do not list serials or IDs.
- Observed results, observation date and anything not tested.

For example: `8 data HDDs, 2 pools of 4 disks, 2 NVMe cache SSDs`. This describes
a layout, not a confirmed hardware/firmware combination.

## Read-Only Checks

Use an already configured integration where possible. Keep experimental controls
disabled and leave normal workloads running; no special stress test is required.

| Check | What to compare |
| --- | --- |
| Device details | Model and OS/Drive versions agree with the device UI. |
| Pools | Each pool appears once; capacity, usage and health match the UI. Compare capacity using the same units. |
| Data disks | Every populated data bay belongs to the correct pool. Empty bays and spares must not appear as another pool's members. |
| Cache | Cache SSDs are distinct from data disks, including when bay/slot numbers overlap. Only metrics the device reports should appear. |
| SMART | Temporarily enable only the diagnostics needed for comparison. Missing or unsupported fields must not be invented as zero. Disable unneeded entities afterwards to avoid extra Recorder history. |
| Throughput | Compare during an existing transfer, allowing for polling/averaging differences. No transfer is needed if you mark this untested. |
| Stable inventory | Observe several polls. Pool/drive counts and entity IDs should not multiply. |
| Diagnostics | Export diagnostics and inspect them locally before sharing. The file should contain support summaries, not raw device data. |

An integration reload is optional and may briefly interrupt monitoring. Record
whether entities retain their IDs and readings return afterwards. Offline/WOL,
HA restart, firmware updates and all write controls are separate, owner-approved
tests, not prerequisites for a hardware report. Do not remove disks, alter RAID,
delete snapshots or shut down a production NAS for this checklist.

## Privacy And Fixtures

Download diagnostics through `Settings` -> `Devices & services` -> the integration
entry's menu -> `Download diagnostics`. Review the attachment and every pasted
line for private data before submitting. Do not publish raw API responses,
device exports, debug dumps or unredacted screenshots.

Diagnostics deliberately omit payload values and model/firmware details, so
provide the versions separately in the form. They help identify endpoint shape
and capability gaps but cannot reproduce an exact device response by themselves.

If a parser failure needs a real-device fixture, agree on the smallest necessary
field structure first. Sanitization must happen locally before anything is
shared. Keep credentials, tokens, cookies, addresses, hostnames, usernames,
serials, WWNs, share names and snapshot target names out of the repository.
Replace pool/disk/cache IDs with generic aliases consistently so relationships
and namespace collisions remain testable; review dynamic dictionary keys too.
Keep only the fields needed for that regression, not a full device dump.

A maintainer must review the sanitized fixture, add a regression test and record
provenance (model, software versions, auth scope and source report) before marking
it `fixture_verified`. That status verifies only the exercised parser/entity
behavior. Live setup, recovery and optional controls need their own evidence.

## Existing Automated Checks

The invented layouts in `tests/storage_fixtures.py` exercise four, seven and eight
data disks, two pools and two cache SSDs. They are not captures from a Pro model.
Run them in an environment with the Home Assistant test plugin installed:

```bash
python -m pytest -q tests/test_storage_view.py tests/test_core_monitoring_entity_states.py tests/test_diagnostics_helpers.py
```

The full CI suite already includes these files. HA-backed tests that are skipped
because the plugin is missing do not count as a successful hardware/entity gate.
