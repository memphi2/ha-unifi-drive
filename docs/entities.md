# Entity Overview

The integration exposes one Home Assistant device per configured UniFi Drive /
UNAS entry.

## Core Monitoring Entities

| Platform | Examples |
| --- | --- |
| `sensor` | capacity, used/available, usage %, pool health, drive health, temperatures |
| `sensor` | throughput, uptime, system status, UniFi OS version, Drive version |
| `binary_sensor` | storage problem, maintenance states |

With API-key authentication, the integration also attempts the local Drive
`systems/device-info` endpoint for CPU temperature, network address, firmware,
Drive version and startup time. These supplement existing entities; they do not
change device identity or enable controls. UniFi OS metadata takes precedence.
Startup-derived uptime is sampled on successful reads and stays frozen offline.

Rebuild progress can fall back to data RAID-group percentages. It reports the
least advanced active group, excluding SSD-cache groups. The new group fields
are interpreted as percentages (1 means 1%, not 100%); missing or invalid values
remain unknown. Explicit pool progress retains its existing precedence.
Data scrubbing contributes to maintenance state, including a reported running
operation at 0%. It is not relabeled as synchronization or rebuild progress.

## Optional Diagnostics And Controls

### Optional Drive Diagnostics

Data drives and occupied SSD-cache slots can expose remaining life (`lifeSpan`),
bad sectors (`badSectorCount`) and uncorrectable sectors
(`uncorrectableSectorCount`). Only reported, valid values create these entities;
unsupported metrics do not create permanently unknown diagnostics. New fields
appearing later are detected without duplicating existing entities.

These diagnostics, including cache temperature/status where reported, are
disabled by default. Enable the individual entities under the device's entity
list when needed. Values are not duplicated as attributes on other sensors.
Changing values are recorded only after an entity is enabled (unless excluded
from Recorder). No global Recorder or statistics settings are changed.

Cache identities use device IDs or slot identifiers, never list positions or
display names. Missing cache drives become unavailable; returning drives reuse
their identities. Historical entities are retained, as for data drives.

### Controls

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
