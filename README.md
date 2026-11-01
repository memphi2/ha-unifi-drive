# Home Assistant integration for UniFi Drive / UNAS (Unofficial)

[![Validate](https://github.com/memphi2/ha-unifi-drive/actions/workflows/validate.yml/badge.svg)](https://github.com/memphi2/ha-unifi-drive/actions/workflows/validate.yml)
[![Quality](https://img.shields.io/badge/Quality-HA%20QS%20Platinum%20Track-0366d6?style=flat-square)](custom_components/unifi_unas/quality_scale.yaml)
[![GitHub Release](https://img.shields.io/github/v/release/memphi2/ha-unifi-drive?display_name=tag&sort=semver&label=release)](https://github.com/memphi2/ha-unifi-drive/releases/latest)
[![License MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Monitor your UniFi Drive / UNAS storage in Home Assistant and automate the local
actions you choose to enable. The integration connects directly to your NAS;
normal operation does not use UniFi cloud services.

<p align="center">
  <img src="docs/images/drive-storage-card.png" alt="Example UniFi Drive storage dashboard" width="420">
</p>

## Features

| Feature | What you get |
| --- | --- |
| Storage monitoring | Pool and drive health, capacity, usage, temperatures and throughput. |
| System monitoring | Uptime, firmware versions and supported system metrics. |
| Discovery | UniFi local discovery and Zeroconf/mDNS, with duplicate-device protection. |
| Wake-on-LAN | Optional startup of a powered-off NAS. |
| Snapshot inventory | Optional snapshot counts and target information where supported. |
| Local controls | Optional snapshot creation/settings, fan controls, backup tasks, updates, restart and shutdown. |

**Local controls are experimental** and dependent on firmware and account
permissions. Fan and snapshot entities are enabled through options; all control
actions require an explicit user or automation request. Snapshot delete and
restore actions are not provided. Lowering retention may let the NAS expire older snapshots.

See the [entity overview](docs/entities.md) for the available sensors and controls.

## Options

Open `Settings` -> `Devices & services` -> **UniFi Drive / UNAS** -> `Configure`.

- Enable Wake-on-LAN and provide the device's MAC address.
- Choose the polling interval and enable fan or snapshot entities as needed.
- Enable discovery diagnostics temporarily when investigating detection problems.

For a monitoring-only dashboard, disable unwanted control entities. Backup-task,
restart/shutdown and update entities are not separate feature switches in options.

## Supported Devices

Live testing and community feedback cover **UNAS2** and **UNAS4**, with different
coverage by feature and firmware. Other UniFi Drive / UNAS models are not yet
verified; non-UniFi NAS devices are unsupported.

Check the [device and firmware matrix](docs/firmware_matrix.md) for the tested
combinations and the scope of each result.

## Installation

Requires Home Assistant `2024.8.0` or newer and local network access to the NAS.

### Home Assistant Marketplace

[![Open your Home Assistant instance and open this repository in the Marketplace](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=memphi2&repository=ha-unifi-drive&category=integration)

On Home Assistant `2026.11+`:

1. Open the button above, or go to `Settings` -> `Marketplace`.
2. Find **UniFi Drive / UNAS** by **memphi2**, install it and confirm the
   community-integration notice.
3. Follow any restart request, then add **UniFi Drive / UNAS** under
   `Settings` -> `Devices & services`.

The integration is in the shared catalog; no custom repository is needed.

### HACS

On Home Assistant versions before `2026.11`, find **UniFi Drive / UNAS** in
HACS, download it and restart Home Assistant. Then add the integration under
`Settings` -> `Devices & services`. No custom repository is needed.

For manual installation, see the [installation guide](docs/installation.md).

## First Setup

Select a discovered device or enter its address manually. Manual setup remains
available when discovery cannot cross VLANs or does not find the NAS.

| Setting | What to enter |
| --- | --- |
| Host | The NAS IP address or DNS name. |
| Port | Usually `443` with SSL, or `80` without it. |
| SSL and certificate verification | Match the device's local connection settings. |
| Username and password | A local account with permissions for the features you need. |
| API key | An optional alternative when supported by the device. |

When both credential types are configured, the local account session is tried
first. After connecting, select the optional features you want to expose.

To change the device address, use `Reconfigure` on the existing integration
entry. For expired or changed credentials, follow the reauthentication prompt
instead of adding a second device.

## Updates

Back up Home Assistant and read the [release notes](https://github.com/memphi2/ha-unifi-drive/releases).
Install the update offered by Marketplace under `Settings` -> `Updates`,
or by HACS on older HA versions, then complete any restart request.

Keep existing entries when updating integration `0.8.0+`. Moving from HACS to
Marketplace does not require a reinstall.

Versions before `0.8.0` must be removed and reinstalled; follow the
[legacy upgrade instructions](docs/installation.md#upgrading-from-before-080).

## Data Updates

Monitoring uses local polling with a minimum interval of 30 seconds. Optional
polling shares a ten-second budget with time reserved for each enabled feature,
so a slow endpoint cannot block later features or core updates indefinitely.
Snapshot inventory normally refreshes every ten minutes. Larger batches resume
over subsequent polls without discarding completed target reads; interrupted
targets do not prevent other targets from progressing.

After two consecutive connection failures, `Device online` reports off and
`System status` reports offline. Core monitoring sensors retain their last known
readings; these are cached values, not current measurements. Gate automations on
`Device online` before using them. Local controls become unavailable while offline.

A powered-off NAS is expected. Being offline alone does not trigger repair prompts.
Wake-on-LAN remains available when configured; discovery and broadcast delivery
depend on your network, especially across VLANs.

## Services

Available actions include `unifi_unas.wake_on_lan`, `reboot`, `shutdown`,
`set_fan_mode`, `create_snapshot`, `set_snapshot_limit` and
`set_snapshot_schedule`, all under the `unifi_unas` domain.

For multiple configured devices, pass `entry_id` to select the intended NAS.
Except for Wake-on-LAN, control actions require an online device and the relevant
device-side permissions.

## Automation Examples

Use storage-health changes for notifications, capacity thresholds for alerts,
or Wake-on-LAN before a backup window. See the ready-to-adapt
[automation examples](docs/examples.md).

## Privacy And Diagnostics

Download diagnostics from the integration entry when reporting an issue.
The export includes runtime, discovery and capability information; credentials,
local addresses, device identifiers and snapshot/share names are redacted or
reduced to presence flags.

Snapshot preview lists, IDs, names and descriptions remain visible in current
entity attributes but are excluded from Recorder history. Counts and timestamps
remain recordable. Large previews therefore do not duplicate their full contents
in the database on each change.
Snapshot controls also exclude duplicate total/locked counts from recorded
attributes; the inventory sensor retains count history. Live attribute changes
can still generate Recorder state rows even when the recorded attributes are
unchanged. Exclude individual control entities in your Recorder configuration
if you do not need their history.

Review attachments before posting. Do not share credentials or unredacted device
API responses. Report reproducible problems through
[GitHub issues](https://github.com/memphi2/ha-unifi-drive/issues).

## Troubleshooting

| Problem | What to check |
| --- | --- |
| Cannot connect | Host, port, SSL settings and reachability from Home Assistant. |
| Authentication fails | Local account permissions or API-key validity; use reauthentication for changed credentials. |
| Device is not discovered | Add it manually; mDNS may not cross your VLANs. |
| Device is unavailable | Check whether it is powered off; use Wake-on-LAN when configured. |
| Monitoring works, controls fail | The firmware or account may not support the optional endpoint. |
| Snapshot target repair | Check the target still exists and review the snapshot options. |
| Update is not offered | Check the minimum HA version and allow time for the catalog to refresh. |

More detailed checks are in the [troubleshooting guide](docs/troubleshooting.md).

## Known Limitations

- Firmware and permissions determine which optional endpoints are available.
- Discovery and Wake-on-LAN depend on local routing and broadcast support.
- Test coverage on one model/firmware does not guarantee every feature on another.

See [known limitations](docs/known_limitations.md) before enabling local controls.

## Removal

1. Delete the integration's entries under `Settings` -> `Devices & services`.
2. To remove the code too, uninstall it through Marketplace or HACS and complete
   the restart request. For a manual install, follow the [removal guide](docs/installation.md#removal).
3. Review dashboards and automations that referenced the removed entities.

Removal does not delete NAS data or revoke device-side accounts/API keys.

## Maturity And Roadmap

Core monitoring is mature beta, discovery is hardened beta, and snapshot
inventory is beta. Local controls remain experimental.

Development is Platinum-oriented, but full Bronze/Silver/Gold compliance is not
claimed. Flow coverage, per-module coverage, cached sensor availability and strict
typing still have documented gaps in
[quality_scale.yaml](custom_components/unifi_unas/quality_scale.yaml) and the
[quality roadmap](docs/platinum_readiness.md). This is not official Home Assistant
Core certification.

## Documentation

- [Installation, updates and removal](docs/installation.md)
- [Entities](docs/entities.md) and [automation examples](docs/examples.md)
- [Device and firmware compatibility](docs/firmware_matrix.md)
- [Troubleshooting](docs/troubleshooting.md) and [limitations](docs/known_limitations.md)
- [Maintenance and LTS policy](docs/lts.md)
- [Validation and contribution checks](docs/validation.md)

## Legal Notes

This is an unofficial community integration. It does not claim affiliation,
sponsorship or endorsement by Ubiquiti Inc., Home Assistant or HACS. Product names
are used only as descriptive compatibility references.

Ubiquiti and UniFi product names and marks belong to Ubiquiti Inc.; other marks
belong to their respective owners.

The repository does not include official Ubiquiti logos or proprietary Ubiquiti
source code. See [docs/legal.md](docs/legal.md) for the legal and asset policy.

Licensed under the [MIT License](LICENSE).
