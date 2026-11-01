"""Guard the low-churn tooling policy without freezing the HA environment."""

from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version
import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
TOOLS_PATH = ROOT / "requirements" / "ci" / "requirements.txt"


@pytest.mark.parametrize(
    ("ecosystem", "directory"),
    (("github-actions", "/"), ("pip", "/requirements/ci")),
)
def test_dependabot_limits_only_normal_updates(ecosystem: str, directory: str) -> None:
    """Routine updates are quarterly; security updates must not be filtered out."""
    config = yaml.safe_load((ROOT / ".github" / "dependabot.yml").read_text())
    assert config["version"] == 2
    entries = config["updates"]
    assert {entry["package-ecosystem"] for entry in entries} == {"github-actions", "pip"}
    matches = [entry for entry in entries if entry["package-ecosystem"] == ecosystem]
    assert len(matches) == 1
    entry = matches[0]
    assert entry["directory"] == directory
    assert entry["schedule"]["interval"] == "quarterly"
    assert "day" not in entry["schedule"]
    assert entry["open-pull-requests-limit"] == 1
    assert not {"ignore", "allow", "target-branch", "exclude-paths"} & entry.keys()
    groups = list(entry["groups"].values())
    assert len(groups) == 1
    assert groups[0] == {"applies-to": "version-updates", "patterns": ["*"]}


def test_ci_tool_manifest_contains_only_direct_stable_pins() -> None:
    """Prevent generated or runtime dependencies from entering the tooling file."""
    requirements = [
        Requirement(line)
        for raw_line in TOOLS_PATH.read_text().splitlines()
        if (line := raw_line.strip()) and not line.startswith("#")
    ]
    assert len(requirements) == 3
    assert {requirement.name for requirement in requirements} == {"bandit", "mypy", "ruff"}
    for requirement in requirements:
        assert not requirement.extras
        assert requirement.marker is None
        assert requirement.url is None
        specifiers = list(requirement.specifier)
        assert len(specifiers) == 1
        specifier = specifiers[0]
        assert specifier.operator == "=="
        version = Version(specifier.version)
        assert not version.is_prerelease
        assert not version.is_devrelease


def test_weekly_validation_uses_the_shared_tool_manifest() -> None:
    """Tool update cadence must not reduce compatibility checks or bypass pins."""
    # BaseLoader preserves the Actions 'on' key instead of YAML 1.1's boolean.
    workflow = yaml.load(
        (ROOT / ".github" / "workflows" / "validate.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    assert workflow["on"]["schedule"] == [{"cron": "0 3 * * 0"}]
    steps = workflow["jobs"]["repository_checks"]["steps"]
    installs = [step for step in steps if step.get("name") == "Install test dependencies"]
    assert len(installs) == 1
    install = installs[0]["run"]
    assert "-r requirements/ci/requirements.txt" in install
    assert "--upgrade" not in install
    assert "--no-deps" not in install
    assert "python -m pip check" in install
    assert '"homeassistant==${{ matrix.homeassistant }}"' in install
    assert '"pytest-homeassistant-custom-component==${{ matrix.pytest_homeassistant }}"' in install
