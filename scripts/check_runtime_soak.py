"""Run bounded resource measurements without contacting a NAS or live HA."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
# fixed local test command, no shell.
import subprocess  # nosec B404
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LIMITS = {"integration_bytes": 512 * 1024, "rss_bytes": 32 * 1024**2,
          "tasks": 2, "timers": 10, "listeners": 0}


def sample_errors(samples, phases=("loaded", "recovered", "unloaded")):
    errors = []
    for phase in phases:
        group = [item for item in samples if item["phase"] == phase]
        if len(group) < 3:
            errors.append(f"{phase}: insufficient measurements")
            continue
        for key, limit in LIMITS.items():
            values = [item[key] for item in group]
            if key == "rss_bytes" and all(value is None for value in values):
                continue
            if any(not isinstance(value, int) for value in values):
                errors.append(f"{phase}: invalid {key}")
            elif max(values) - values[0] > limit:
                errors.append(f"{phase}: {key} grew beyond its budget")
        if phase == "unloaded" and any(
            item[key] for item in group
            for key in ("listeners", "retained_coordinators", "open_sessions", "owned_tasks")
        ):
            errors.append("unloaded: resources survived cleanup")
    return errors


def steady_errors(samples):
    errors = sample_errors(samples, phases=("steady",))
    if len({item.get("registry_entities") for item in samples}) != 1:
        errors.append("steady: entity registry grew without new targets")
    if any(item.get("inventory_entries", 2) > 1 for item in samples):
        errors.append("steady: inventory retained inactive targets")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycles", type=int, default=30)
    parser.add_argument("--idle-seconds", type=float, default=1)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--refreshes", type=int, default=300)
    parser.add_argument("--targets", type=int, default=30)
    args = parser.parse_args()
    if args.cycles < 3 or not math.isfinite(args.idle_seconds) or args.idle_seconds < 0:
        parser.error("use at least three cycles and a finite nonnegative idle duration")
    if args.refreshes < 30 or args.targets < 3:
        parser.error("use at least 30 steady refreshes and three distinct targets")
    with tempfile.TemporaryDirectory(prefix="unas-soak-") as directory:
        report = Path(directory) / "report.json"
        steady = Path(directory) / "steady.json"
        env = {**os.environ, "UNAS_SOAK_CYCLES": str(args.cycles),
               "UNAS_SOAK_IDLE": str(args.idle_seconds), "UNAS_SOAK_REPORT": str(report),
               "UNAS_STEADY_REFRESHES": str(args.refreshes), "UNAS_STEADY_TARGETS": str(args.targets),
               "UNAS_STEADY_REPORT": str(steady)}
        # fixed interpreter and test path.
        result = subprocess.run(  # nosec B603
            [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_soak.py"],
            cwd=ROOT, env=env, check=False,
        )
        if result.returncode:
            return result.returncode
        if not report.exists() or not steady.exists():
            print("FAIL: no resource measurement report")
            return 1
        data = json.loads(report.read_text())
        continuous = json.loads(steady.read_text())
        if (data.get("cycles") != args.cycles or data.get("idle_seconds") != args.idle_seconds
                or sample_errors(data.get("samples", []))
                or continuous.get("refreshes") != args.refreshes
                or continuous.get("targets") != args.targets
                or steady_errors(continuous.get("samples", []))):
            print("FAIL: incomplete or failing resource measurements")
            return 1
        data["continuous"] = continuous
        if args.json_output:
            args.json_output.write_text(json.dumps(data, indent=2) + "\n")
        print(json.dumps({key: value for key, value in data.items() if key != "samples"}))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
