"""Check generated HA entities against a local companion-card checkout."""

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--card-root", required=True, type=Path)
    args = parser.parse_args()
    card = args.card_root.resolve()
    if not (card / "test/real-integration-contract.test.ts").is_file():
        parser.error("card checkout must contain the real integration contract test")
    with tempfile.TemporaryDirectory(prefix="unas-contract-") as directory:
        output = Path(directory) / "entities.json"
        result = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests/test_card_contract.py"],
                                cwd=ROOT, env={**os.environ, "UNAS_CARD_CONTRACT_OUTPUT": str(output)},
                                check=False)
        if result.returncode:
            return result.returncode
        if not output.is_file():
            print("FAIL: HA entity export did not run")
            return 1
        return subprocess.run(["npm", "test", "--", "test/real-integration-contract.test.ts"],
                              cwd=card, env={**os.environ, "UNAS_CARD_CONTRACT_FIXTURE": str(output)},
                              check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
