// @vitest-environment node
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { normalizeConfig } from "../src/config";
import { discoverEntities } from "../src/discovery";
import type { HomeAssistant } from "../src/types";

// Executed temporarily inside the pinned card checkout against a fresh HA export.
const source = process.env.UNAS_CARD_CONTRACT_FIXTURE;
if (!source) throw new Error("A fresh HA entity export is required");
const contract = JSON.parse(readFileSync(source, "utf8"));

describe("entities exported by the real UNAS integration", () => {
  it("preserves discovery and dynamic grouping through registry metadata", () => {
    expect(contract.schema_version).toBe(1);
    const hass: HomeAssistant = { ...contract, callService: async () => undefined };
    const found = discoverEntities(hass, normalizeConfig({ device_id: "contract-device" }));
    for (const key of ["read_throughput", "write_throughput", "device_online", "fan_mode"]) {
      expect(found.entityIds[key]).toBeTruthy();
    }
    for (const [kind, key] of [["pool", "pool_status"], ["drive", "drive_status"],
      ["snapshot", "snapshot_limit"], ["backup", "backup_run"]] as const) {
      expect(found.groups[kind]).toHaveLength(1);
      expect(found.groups[kind][0]?.entityIds[key]).toBeTruthy();
    }
    const selected = new Set([
      ...Object.values(found.entityIds),
      ...Object.values(found.groups).flatMap(groups => groups.flatMap(group => Object.values(group.entityIds))),
    ]);
    for (const id of selected) expect(hass.states[id]).toBeDefined();
  });
});
