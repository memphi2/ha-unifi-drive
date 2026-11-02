"""Keep cross-repository checks fail-closed and leave the card checkout intact."""

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from scripts import check_card_contract as runner


@pytest.mark.parametrize("exit_code", [0, 1])
def test_runner_exports_entities_and_cleans_temporary_test(tmp_path, monkeypatch, exit_code):
    card = tmp_path / "card"
    (card / "test").mkdir(parents=True)
    (card / "src").mkdir()
    (card / "src/discovery.ts").write_text("")
    output = tmp_path / "evidence.json"
    monkeypatch.setattr("sys.argv", ["check", "--card-root", str(card), "--json-output", str(output)])
    monkeypatch.setattr(runner.shutil, "which", lambda name: "/synthetic/npm")
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            Path(kwargs["env"]["UNAS_CARD_CONTRACT_OUTPUT"]).write_text('{"schema_version":1}')
            return SimpleNamespace(returncode=0)
        assert (card / "test/unas-generated-contract.test.ts").is_file()
        assert Path(kwargs["env"]["UNAS_CARD_CONTRACT_FIXTURE"]).is_file()
        return SimpleNamespace(returncode=exit_code)

    monkeypatch.setattr(runner.subprocess, "run", run)
    assert runner.main() == exit_code
    assert output.is_file()
    assert len(calls) == 2
    assert not list((card / "test").iterdir())


def test_runner_rejects_missing_export(tmp_path, monkeypatch):
    (tmp_path / "test").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "src/discovery.ts").write_text("")
    monkeypatch.setattr("sys.argv", ["check", "--card-root", str(tmp_path)])
    monkeypatch.setattr(runner.shutil, "which", lambda name: "/synthetic/npm")
    monkeypatch.setattr(runner.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0))
    assert runner.main() == 1
    assert not list((tmp_path / "test").iterdir())


def test_extended_ci_is_scheduled_pinned_and_retains_evidence():
    workflow = yaml.safe_load((runner.ROOT / ".github/workflows/validate.yml").read_text())
    steps = workflow["jobs"]["repository_checks"]["steps"]
    checkout = next(step for step in steps if step.get("with", {}).get("repository") == "memphi2/ha-unifi-drive-card")
    assert len(checkout["with"]["ref"]) == 40
    assert checkout["with"]["persist-credentials"] is False
    for label in ("Measure extended runtime resources", "Verify fresh HA entities against the card",
                  "Retain synthetic runtime and contract evidence"):
        step = next(step for step in steps if step["name"] == label)
        assert "schedule" in step["if"] and "workflow_dispatch" in step["if"]
    upload = steps[-1]
    assert upload["with"]["retention-days"] == 14
    assert upload["with"]["if-no-files-found"] == "error"
