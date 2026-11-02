"""Check generated HA entities against a local companion-card checkout."""

import argparse
import os
from pathlib import Path
import shutil
# explicit local test commands, no shell.
import subprocess  # nosec B404
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--card-root", required=True, type=Path)
    parser.add_argument("--json-output", type=Path, help="retain the synthetic export for CI evidence")
    args = parser.parse_args()
    card = args.card_root.resolve()
    if not (card / "test").is_dir() or not (card / "src/discovery.ts").is_file():
        parser.error("expected a companion-card source checkout")
    npm = shutil.which("npm")
    if npm is None:
        parser.error("npm is required for companion-card tests")
    with tempfile.TemporaryDirectory(prefix="unas-contract-") as directory:
        output = Path(directory) / "entities.json"
        # fixed test command.
        result = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests/test_card_contract.py"],  # nosec B603
                                cwd=ROOT, env={**os.environ, "UNAS_CARD_CONTRACT_OUTPUT": str(output)},
                                check=False)
        if result.returncode:
            return result.returncode
        if not output.is_file():
            print("FAIL: HA entity export did not run")
            return 1
        if args.json_output:
            shutil.copyfile(output, args.json_output)
        # Exclusive creation prevents overwriting a developer's existing test.
        test = card / "test/unas-generated-contract.test.ts"
        with test.open("x") as target:
            target.write((ROOT / "scripts/card_contract.test.ts").read_text())
        try:
            # resolved tool, fixed arguments.
            return subprocess.run([npm, "test", "--", f"test/{test.name}"],  # nosec B603
                                  cwd=card, env={**os.environ, "UNAS_CARD_CONTRACT_FIXTURE": str(output)},
                                  check=False).returncode
        finally:
            test.unlink()


if __name__ == "__main__":
    raise SystemExit(main())
