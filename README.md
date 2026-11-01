# Home Assistant integration for UniFi Drive / UNAS (Unofficial)

[![Validate](https://github.com/memphi2/ha-unifi-drive/actions/workflows/validate.yml/badge.svg)](https://github.com/memphi2/ha-unifi-drive/actions/workflows/validate.yml)
[![Quality](https://img.shields.io/badge/Quality-HA%20QS%20Platinum%20Track-0366d6?style=flat-square)](custom_components/unifi_unas/quality_scale.yaml)
[![GitHub Release](https://img.shields.io/github/v/release/memphi2/ha-unifi-drive?display_name=tag&sort=semver&label=release)](https://github.com/memphi2/ha-unifi-drive/releases/latest)
[![Marketplace](https://img.shields.io/badge/Home_Assistant-Marketplace-41BDF5?style=flat-square)](https://contributors.home-assistant.io/marketplace/)
[![License MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Local Home Assistant custom integration for compatible UniFi Drive / UNAS
systems.

The integration talks directly to the device on your local network. It does not
use UniFi cloud services for normal operation and is intended for trusted local
Home Assistant installations.

<p align="center">
  <img src="docs/images/drive-storage-card.png" alt="UniFi Drive storage overview card screenshot" width="420">
</p>

## What You Get

- One Home Assistant device per configured UniFi Drive / UNAS system.
- Storage, pool, drive, temperature, throughput, uptime, version and health
  monitoring.
- Discovery through UniFi local discovery and Zeroconf/mDNS, with duplicate
  protection for noisy or mixed networks.
- Stable local polling with quieter offline behavior when the device is shut
  down or temporarily unreachable.
- Optional Wake-on-LAN and local control entities for users who explicitly want
  them.
- Privacy-safe diagnostics for support reports.

## Current Release

- Integration version: `v0.8.9`
- Home Assistant setup: UI config flow, discovery, manual setup, reauth,
  reconfigure and options flow
- Distribution: Home Assistant Marketplace / HACS shared catalog
- IoT class: local polling
- Quality target: Bronze/Silver/Gold tracked as implemented, Platinum-track
  hardening in progress
- CI targets: Home Assistant `2024.8.0` minimum and `2026.10.0`;
  November compatibility follow-up is tracked in [docs/lts.md](docs/lts.md)
- Current maintenance focus: Home Assistant compatibility, device metadata and
  Marketplace installation/update guidance

This is a custom integration and does not claim official Home Assistant Core
certification.

## Feature Matrix

| Area | Default | Notes |
| --- | --- | --- |
| Core monitoring | enabled | Capacity, usage, health, versions, uptime, throughput and temperatures. |
| Discovery | enabled | UniFi local discovery and Zeroconf/mDNS candidates are deduplicated. |
| Wake-on-LAN | optional | Useful when the device may be powered off intentionally. |
| Snapshot inventory | optional | Firmware and permission dependent. |
| Snapshot settings | optional | Non-destructive; no delete or restore actions are provided. |
| Fan, backup and update controls | optional | Local endpoint and permission dependent. |
| Restart/shutdown buttons | optional | Exposed only when enabled; use intentionally. |

## Entities

The integration creates a focused default device page and keeps noisier or
experimental controls out of the way unless enabled.

| Platform | Examples |
| --- | --- |
| `sensor` | capacity, used/available, usage %, pool health, drive health, temperatures, throughput, uptime, versions |
| `binary_sensor` | storage and maintenance problem indicators |
| `button` | Wake-on-LAN, restart, shutdown, backup tasks, snapshot create |
| `switch` / `number` / `select` / `time` | snapshot settings and fan mode controls |
| `update` | UniFi OS / Drive update entities when available |

The complete entity overview is in [docs/entities.md](docs/entities.md).

## Options

Open the integration entry and choose `Configure` to adjust options.

Common choices:

- Enable Wake-on-LAN and provide a MAC address when the device may be off.
- Enable snapshot inventory when you want per-target snapshot visibility.
- Enable snapshot controls only after confirming endpoint support and
  permissions.
- Enable fan, backup or update controls only for accounts that should be able
  to perform those local actions.
- Enable discovery diagnostics only while investigating discovery behavior.

Reconfigure and reauth flows preserve the existing Home Assistant device
identity where possible.

## Supported Devices

Current compatibility evidence is intentionally conservative:

| Device scope | Firmware | Evidence |
| --- | --- | --- |
| UNAS2 | UniFi OS `5.1.8` | integration lifecycle tested |
| UNAS2 | UniFi OS `5.1.10` | integration lifecycle and optional controls tested |
| UNAS2 | UniFi OS `5.1.19`, Drive `4.3.6` | throughput confirmed |
| UNAS4 | UniFi OS `5.1.16`, Drive `4.3.6` | throughput confirmed through community feedback on `v0.8.4` |
| Other UniFi Drive / UNAS models | unknown | expected when endpoint shape and permissions match |
| Non-UniFi NAS devices | any | unsupported |

See [docs/firmware_matrix.md](docs/firmware_matrix.md) for the tracked evidence.

## Installation

Versions before `0.8.0` should be removed and installed again instead of being
upgraded in place. Follow the [legacy upgrade checklist](docs/installation.md#upgrading-from-before-080).

### Home Assistant Marketplace (recommended)

[![Open your Home Assistant instance and open this repository in the Marketplace](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=memphi2&repository=ha-unifi-drive&category=integration)

For Home Assistant `2026.11` and newer:

1. Open `Settings` -> `Marketplace`.
2. Search for `UniFi Drive` and open **UniFi Drive / UNAS** by **memphi2**.
3. Install the integration and confirm the community-integration notice.
4. Add **UniFi Drive / UNAS** from `Settings` -> `Devices & services` and
   complete [First Setup](#first-setup).

The repository is already in the shared catalog; no custom repository is
needed. A first Marketplace install normally loads without a restart. Complete
any restart requested by Home Assistant after an update or removal of loaded code.

### HACS On Older Home Assistant Versions

Before Home Assistant `2026.11`, search for **UniFi Drive / UNAS** in HACS,
download it, restart Home Assistant and then add the integration from
`Settings` -> `Devices & services`. No custom repository is needed here either.

### Manual Installation

For a deliberate manual installation, copy the selected release's
`custom_components/unifi_unas/` directory into `/config/custom_components/`
and restart Home Assistant. See the [installation guide](docs/installation.md#manual-installation)
for the exact layout and update procedure.

### Nested Folder Recovery

`manifest.json` must be directly inside `/config/custom_components/unifi_unas/`,
not inside a second `unifi_unas` directory. Follow the
[folder recovery checklist](docs/installation.md#nested-folder-recovery) rather
than deleting the configured device.

## Updates

Back up Home Assistant, read the release notes under `Settings` -> `Updates`,
install the offered integration version and complete the restart request.
On older Home Assistant versions, use the update offered by HACS.

Keep working config entries when updating integration `0.8.0` or newer.
The move from HACS to Marketplace does not change this repository, the
`unifi_unas` domain or entity identities, and does not require a reinstall.
Do not add a second copy. The separate reinstall requirement for versions
before `0.8.0` still applies.

See [installation, updates and removal](docs/installation.md) for existing
installations, delayed catalog updates and manual recovery.

## First Setup

Add the integration from `Settings` -> `Devices & services` -> `Add integration`
-> `UniFi Drive / UNAS`.

You can start from an automatic discovery card or enter the device manually.
Manual setup remains available even when discovery is blocked by VLANs, mDNS
routing or incomplete network metadata.

The setup form accepts:

| Field | Notes |
| --- | --- |
| Host | IP address or DNS name. URLs with scheme/port are also normalized. |
| Port | Usually `443` for SSL or `80` without SSL. |
| SSL / certificate verification | Match your local UniFi OS endpoint. |
| Username/password | Local account session authentication. |
| API key | Optional local API-key based authentication when supported. |

If both username/password and API key are configured, the local account session
is used first.

After the connection succeeds, the optional-features step lets you choose which
control surfaces should be exposed. Keep optional controls disabled if you only
want monitoring.

## Discovery Behavior

Discovery is treated as a setup hint, not as blind trust.

- Existing configured devices are hidden from normal discovery selection.
- Multiple records for the same device are deduplicated through local identity
  hints.
- Conflicting hints are recorded for diagnostics instead of forcing a risky
  automatic match.
- Discovery metadata updates can refresh known hints without reloading the
  integration or writing config-entry storage on every repeated observation.
- VLANs and multiple interfaces can still require manual setup when mDNS or MAC
  hints are incomplete.

## Offline Behavior

The integration expects that a NAS can be intentionally powered off.

- Offline state should not create repeated repair noise by itself.
- Wake-on-LAN stays useful when configured.
- Core entities stay loaded and become unavailable instead of preserving stale
  live values.
- Recovery is handled through normal coordinator refreshes after the device
  becomes reachable again.

## Data Updates

Core monitoring uses local polling with a minimum update interval of `30s`.

Optional endpoints are isolated from core monitoring. If a snapshot, fan,
backup or update endpoint is unsupported or permission-blocked, the integration
keeps the monitoring surface usable and reports the optional capability state
where possible.

Detailed validation notes are in [docs/validation.md](docs/validation.md).

## Services

Registered domain services:

```text
unifi_unas.wake_on_lan
unifi_unas.reboot
unifi_unas.shutdown
unifi_unas.set_fan_mode
unifi_unas.create_snapshot
unifi_unas.set_snapshot_limit
unifi_unas.set_snapshot_schedule
```

In multi-device setups, pass `entry_id` to target a specific UNAS entry.

Examples are in [docs/examples.md](docs/examples.md).

## Use Cases And Automation Examples

Typical Home Assistant uses:

- Alert when storage health changes or capacity crosses a threshold.
- Show pool, drive and temperature health on a maintenance dashboard.
- Wake the device before a scheduled maintenance or backup window.
- Keep snapshot settings visible for supported targets.
- Track firmware/update availability without opening the UniFi UI.

YAML examples are in [docs/examples.md](docs/examples.md).

## Privacy And Diagnostics

Diagnostics are designed for support without exposing local secrets.

Included:

- runtime state and capability flags
- monitoring and discovery health
- payload shape metadata
- snapshot capability state without raw target names

Redacted or reduced to presence flags:

- credentials and API keys
- hostnames, IP addresses and MAC addresses
- serial-like identifiers and token-like values
- snapshot target identifiers and share names
- raw local API payload values

Export diagnostics from the integration entry when reporting an issue.
Release validation scans tracked files, existing public GitHub release/PR
surfaces and the generated HACS ZIP for common secret, local artifact,
personal identifier, local-network, copyright, trademark/branding and
vendor-asset mistakes before publication.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Setup cannot connect | Verify host, port, SSL and certificate settings from the Home Assistant host. |
| Authentication fails | Recheck local account permissions or API-key validity. |
| Discovery does not show the device | Use manual setup; mDNS often does not cross VLANs without explicit relay support. |
| Discovery card keeps appearing | Check diagnostics for identity confidence, conflicts and prompt-suppression state. |
| Monitoring works but controls fail | The account may not have permission for optional local endpoints. |
| Snapshot targets are missing | Enable snapshot options and verify endpoint support on this firmware. |
| Device is off | This is expected; use Wake-on-LAN when configured. |
| Marketplace is not available | Home Assistant versions before `2026.11` use HACS instead. |
| Integration update is not offered | Check the release's minimum HA version and allow time for the catalog to refresh; do not reinstall to force an update. |

More detail is in [docs/troubleshooting.md](docs/troubleshooting.md).

## Known Limitations

- This is an unofficial community integration and not vendor-supported.
- Endpoint behavior and permission requirements can vary by firmware.
- Snapshot controls are intentionally opt-in and non-destructive.
- Snapshot delete and restore actions are intentionally not provided.
- Discovery quality depends on local network metadata quality.
- Wake-on-LAN may need directed-broadcast support depending on your network.
- Live-device validation is strongest on the tested UNAS2 target.

See [docs/known_limitations.md](docs/known_limitations.md).

## Removal

1. In Home Assistant, open `Settings` -> `Devices & services`.
2. Open the `UniFi Drive / UNAS` integration entry.
3. Choose `Delete`.
4. To remove the integration code too, first delete all its config entries,
   then uninstall the repository through Marketplace (HACS on older HA).
5. For a manual installation, remove only `/config/custom_components/unifi_unas/`.
6. Complete the requested Home Assistant restart after removing the code.

Removing only the files does not delete the Home Assistant config entries.
Removing entries affects entities, dashboards and automations that reference
them; it does not delete data on the NAS. See the [removal checklist](docs/installation.md#removal).

## Documentation

| Topic | Document |
| --- | --- |
| Installation and day-to-day use | This README |
| Marketplace, HACS, updates and removal | [docs/installation.md](docs/installation.md) |
| Entity surface overview | [docs/entities.md](docs/entities.md) |
| Automation examples | [docs/examples.md](docs/examples.md) |
| Troubleshooting guide | [docs/troubleshooting.md](docs/troubleshooting.md) |
| Known limitations | [docs/known_limitations.md](docs/known_limitations.md) |
| Supported model and firmware evidence | [docs/firmware_matrix.md](docs/firmware_matrix.md) |
| Maintenance and LTS policy | [docs/lts.md](docs/lts.md) |
| Validation and release gates | [docs/validation.md](docs/validation.md) |
| Bronze readiness summary | [docs/bronze_readiness.md](docs/bronze_readiness.md) |
| Platinum readiness audit snapshot | [docs/platinum_readiness.md](docs/platinum_readiness.md) |
| Platinum-track implementation plan | [docs/platinum_prep.md](docs/platinum_prep.md) |
| Live HA validation report (`v0.6.2`) | [docs/live_test_report_v0.6.2.md](docs/live_test_report_v0.6.2.md) |
| Live recorder/config-entry DB probe | [docs/live_db_probe.md](docs/live_db_probe.md) |
| Legal and interoperability policy | [docs/legal.md](docs/legal.md) |

## Current Maturity

Core monitoring is treated as mature beta for this custom integration. Discovery,
diagnostics, lifecycle handling, reauth/reconfigure, HACS metadata and
repository validation have focused test coverage and release gates.

Optional local controls remain experimental where they depend on undocumented
local UniFi Drive / UniFi OS endpoint behavior, firmware version and account
permissions.

## Silver Gold Platinum Roadmap

| Level | Current state | Next focus |
| --- | --- | --- |
| Bronze | Implemented in tracked rules | Keep release metadata and docs consistency strict |
| Silver | Implemented in tracked rules | Keep coverage and runtime stability gates green |
| Gold | Implemented in tracked rules | Preserve diagnostics, discovery and repair quality under firmware changes |
| Platinum | In progress | Expand strict typing scope and maintain proof-backed runtime hardening |

The active Platinum-oriented plan is maintained in
[docs/platinum_prep.md](docs/platinum_prep.md).

## Validation

Local repository gates:

```bash
python scripts/check_repo.py
ruff check custom_components tests scripts
python -m pytest -q
python -m compileall -q custom_components/unifi_unas tests
git diff --check
```

Validation flow details and optional live checks are documented in
[docs/validation.md](docs/validation.md).

## Legal Notes

This is an unofficial community integration. It does not claim affiliation,
sponsorship, authorization, approval, or endorsement by Ubiquiti Inc., Home
Assistant, HACS, or their respective owners.

Product names such as UniFi, UniFi Drive, UniFi OS, Ubiquiti, and UNAS are used
only as descriptive compatibility references.

The repository does not include official Ubiquiti logos, copied vendor web
assets, or proprietary Ubiquiti source code.

Protocol and endpoint notes document observed interoperability behavior only.
They are not a copy of, or a substitute for, vendor software or specifications.

See [docs/legal.md](docs/legal.md) for the repository legal and asset hygiene
policy.

## Acknowledgements

Development and hardening work for this project was assisted by OpenAI Codex.

## License

MIT
