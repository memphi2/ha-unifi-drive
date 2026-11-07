# Known Limitations

- This is an unofficial community integration and not vendor-supported.
- Only local UniFi OS / Drive endpoint behavior is covered; no cloud control
  path is implemented.
- Endpoint behavior and permission requirements can vary by firmware.
- API-key device metadata and RAID-group/scrubbing fallbacks have synthetic
  regression coverage, not new live-device validation. Missing metadata remains
  unknown; an optional endpoint failure does not make core storage unavailable.
  Device metadata is attempted once per API-key poll with a 2.5-second timeout;
  username/password polling does not gain an additional request.
- SSD-cache and additional SMART diagnostics depend on firmware-reported fields
  and have synthetic coverage only. Enabled diagnostic entities add history;
  leave them disabled if those readings are not needed. Slots without stable
  identity are ignored rather than creating position-dependent entities.
- Larger layouts have synthetic multi-pool, data-drive and cache coverage, not
  confirmed UNAS Pro/Pro4/Pro8 support. See the [evidence matrix](firmware_matrix.md)
  and [hardware reporting guide](hardware_validation.md) before making a model claim.
- Snapshot entities are opt-in. Reducing retention can cause the NAS to expire
  old snapshots according to its own policy; review the limit before changing it.
- Snapshot delete/restore actions are intentionally not provided.
- Discovery quality depends on local network metadata quality (mDNS/zeroconf,
  MAC hints, aliases, VLAN routing behavior).
- Wake-on-LAN uses IPv4 UDP broadcast and may need directed-broadcast support.
- Offline monitoring retains cached readings. Use Device online to guard
  automations that need current measurements.
- Local synthetic tests do not replace long-running device/Recorder validation.
- HTTP responses larger than 8 MiB are rejected for runtime safety. Very large
  inventories may require follow-up rather than raising the limit blindly.
- Entities for previously observed snapshot targets remain registered for
  existing automations and missing-target handling. Continually creating new
  target IDs therefore grows the registry; repeated polling alone should not.
- Real-device lifecycle validation is strongest on the tested UNAS2 target.
  Throughput has been confirmed for the UNAS2 and UNAS4 firmware combinations
  listed in the firmware matrix, but other feature/model/firmware combinations
  should still be verified before being treated as equivalent.
