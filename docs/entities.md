# Entity Overview

The integration exposes one Home Assistant device per configured UniFi Drive /
UNAS entry.

## Core Monitoring Entities

| Platform | Examples |
| --- | --- |
| `sensor` | capacity, used/available, usage %, pool health, drive health, temperatures |
| `sensor` | throughput, uptime, system status, UniFi OS version, Drive version |
| `binary_sensor` | storage problem, maintenance states |

## Optional Control Entities

| Platform | Examples | Notes |
| --- | --- | --- |
| `button` | Wake-on-LAN, restart, shutdown | local action endpoints |
| `select` | fan mode | permission-dependent |
| `update` | UniFi OS / Drive updates | uses HA update semantics |
| `button` | backup task actions | shown when task metadata is available |
| `switch`/`number`/`select`/`time` | snapshot per-target controls | opt-in and endpoint-dependent |

## Availability Model

- After two consecutive connection failures, Device online reports off and
  System status reports offline. Core monitoring sensors keep last-known values;
  they are cached observations, not current measurements. Gate automations on
  Device online before using these readings.
- Local controls become unavailable offline; configured Wake-on-LAN stays
  available. Offline alone is expected and does not create a repair issue.
- Optional feature entities can stay unavailable when endpoints are unsupported
  or blocked by permissions.
- No direct API calls happen from entity properties.

## Names And History

Pool, drive, snapshot and backup names combine the device-provided name with a
translated entity label. Unique IDs are unchanged; user-assigned entity names
and existing registry IDs are preserved.

Snapshot controls keep live total/locked counts for dashboards but exclude
those duplicate attributes from Recorder. The inventory sensor retains count
history. Excluded attributes can still cause state rows when their live values
change; use Recorder entity exclusions for controls whose history is unnecessary.
