# Troubleshooting

## Installation Or Update Not Visible

- Use Marketplace on Home Assistant `2026.11+`, HACS on older HA versions.
- Search the shared catalog for `UniFi Drive / UNAS`; a custom repository is not needed.
- Check the release's minimum HA version and allow time for catalog refreshes.
- Follow any restart request after replacing loaded integration code.
- Keep working config entries. See [installation and recovery](installation.md)
  for manual layouts and the separate pre-`0.8.0` upgrade procedure.

## Device Cannot Be Reached

- Verify host/IP, port, SSL and certificate settings.
- Confirm Home Assistant host can reach the UNAS host on the local network.
- A redirected API/login request is rejected to protect credentials. Configure
  the final console address, correct port and SSL setting rather than a redirecting proxy.

## Discovery Card Keeps Appearing

- Check diagnostics discovery health fields (confidence/conflicts/source).
- In mixed VLAN or multi-interface environments, manual confirmation can still
  be expected by design.

## Authentication Fails

- Validate local account credentials or API key validity.
- Use the reauthentication prompt for changed credentials, or Reconfigure for
  connection changes. Do not add a second entry for the same device.

## Monitoring Works But Controls Fail

- This usually indicates permission scope differences on local endpoints.
- Verify account/API key privileges for fan/update/snapshot/backup actions.

## Snapshot Targets Missing Or Unavailable

- Enable snapshot controls in options/reconfigure.
- Verify snapshot endpoint permissions for the configured identity.
- Use inventory status attributes to distinguish unsupported vs. permission
  failures.
- Failed reads retain the last known targets and make snapshot entities
  unavailable. A missing-target repair requires successful reads without that target.
- Slow optional polling is bounded; check console load before reducing the poll interval.

## Device Powered Off

- Offline state is expected and should not become a repair storm.
- Use Wake-on-LAN when configured to recover normal monitoring.
- Monitoring sensors retain cached values. Check Device online/System status;
  do not treat cached temperatures, throughput or capacity as live measurements.
