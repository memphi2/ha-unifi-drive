"""Tests for repository validation helpers."""

from __future__ import annotations

import json

import pytest

from tests.module_stubs import ROOT, load_repo_module


def _load_check_repo_module():
    return load_repo_module("check_repo_for_tests", ROOT / "scripts" / "check_repo.py")


@pytest.mark.parametrize("name", ["Snapshot-Limit", "{wrong} Snapshot-Limit", "{target_name", None])
def test_entity_translation_rejects_missing_or_invalid_placeholders(name):
    module = _load_check_repo_module()
    source = {"entity": {"number": {"snapshot_limit": {"name": "{target_name} Snapshot limit"}}}}
    translated = {"entity": {"number": {"snapshot_limit": {"name": name}}}}
    with pytest.raises(SystemExit):
        module._check_entity_name_placeholders(source, translated, "example.json")


def test_entity_translation_accepts_reordered_placeholders():
    module = _load_check_repo_module()
    source = {"entity": {"sensor": {"drive": {"name": "{pool_name} {drive_name} Temperature"}}}}
    translated = {"entity": {"sensor": {"drive": {"name": "Temperatur {drive_name} ({pool_name})"}}}}
    module._check_entity_name_placeholders(source, translated, "example.json")


def test_manifest_version_tag_adds_release_prefix() -> None:
    """Manifest versions should map to GitHub release tag names."""
    module = _load_check_repo_module()

    assert module._manifest_version_tag({"version": "0.3.6"}) == "v0.3.6"
    assert module._manifest_version_tag({"version": "0.9.0b1"}) == "v0.9.0b1"
    assert module._manifest_version_tag({"version": "0.9.0rc1"}) == "v0.9.0rc1"


@pytest.mark.parametrize("version", ["v0.3.6", "0.9.01b1", "0.9.0b0", "0.9.0+local", "0.9.0\n", None])
def test_manifest_version_tag_rejects_noncanonical_versions(version):
    module = _load_check_repo_module()
    with pytest.raises(SystemExit):
        module._manifest_version_tag({"version": version})


def test_manifest_version_tag_rejects_missing_version() -> None:
    """Release metadata validation should fail when the manifest has no version."""
    module = _load_check_repo_module()

    with pytest.raises(SystemExit):
        module._manifest_version_tag({})


def test_manifest_has_unas_marketplace_category() -> None:
    """The shipped manifest must identify the NAS, not its individual sensors."""
    _load_check_repo_module().check_manifest()


@pytest.mark.parametrize(
    "categories",
    (
        None,
        [],
        "computers_network.nas_servers",
        ["nas"],
        ["computers_network.nas_servers", "computers_network.nas_servers"],
    ),
)
def test_manifest_rejects_missing_or_invalid_marketplace_category(
    categories, tmp_path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """Catch missing, mistyped and duplicate categories before catalog validation."""
    module = _load_check_repo_module()
    manifest = module.load_json(module.MANIFEST_PATH)
    if categories is None:
        manifest.pop("categories", None)
    else:
        manifest["categories"] = categories
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(module, "MANIFEST_PATH", path)

    with pytest.raises(SystemExit):
        module.check_manifest()
    assert "manifest categories" in capsys.readouterr().out


def test_changelog_release_entry_matches_version_heading() -> None:
    """Release metadata validation should require a changelog heading."""
    module = _load_check_repo_module()
    changelog = "\n".join(
        [
            "# Changelog",
            "",
            "## Unreleased",
            "",
            "## v0.3.6 - Snapshot Control Hardening",
            "",
        ]
    )

    assert module._has_changelog_release_entry(changelog, "v0.3.6") is True
    assert module._has_changelog_release_entry(changelog, "v0.3.5") is False


def test_legal_check_requires_matching_component_license(tmp_path, monkeypatch) -> None:
    module = _load_check_repo_module()
    monkeypatch.setattr(module, "INTEGRATION_DIR", tmp_path)
    with pytest.raises(SystemExit):
        module.check_legal_docs()
    (tmp_path / "LICENSE").write_text("not the project license", encoding="utf-8")
    with pytest.raises(SystemExit):
        module.check_legal_docs()
    (tmp_path / "LICENSE").write_bytes(module.LICENSE_PATH.read_bytes())
    module.check_legal_docs()


def test_quality_scale_accepts_honest_documented_gaps(
    tmp_path,
    monkeypatch,
) -> None:
    """Complete rule tracking must allow documented gaps without lowering tests."""
    module = _load_check_repo_module()
    quality_scale_path = tmp_path / "quality_scale.yaml"
    all_rules = [
        rule
        for rules_for_tier in module.QUALITY_RULES_BY_TIER.values()
        for rule in rules_for_tier
    ]
    quality_scale_path.write_text(
        "rules:\n"
        + "\n".join(
            f"  {rule}: done"
            if rule
            in (
                module.QUALITY_RULES_BY_TIER["bronze"]
                + module.QUALITY_RULES_BY_TIER["silver"]
                + module.QUALITY_RULES_BY_TIER["gold"]
            )
            else f"  {rule}:\n    status: todo\n    comment: Remaining work."
            for rule in all_rules
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "QUALITY_SCALE_PATH", quality_scale_path)

    module.check_quality_scale()

    complete = quality_scale_path.read_text(encoding="utf-8")
    quality_scale_path.write_text(complete.replace(
        "  test-coverage: done", "  test-coverage:\n    status: todo\n    comment: Per-module coverage pending."
    ), encoding="utf-8")
    module.check_quality_scale()
    quality_scale_path.write_text(complete.replace("  test-coverage: done", "  test-coverage: todo"), encoding="utf-8")
    with pytest.raises(SystemExit, match="1"):
        module.check_quality_scale()

    quality_scale_path.write_text(
        "rules:\n  action-setup: done\n  runtime-data: todo\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        module.check_quality_scale()


def test_quality_scale_rejects_unknown_status(tmp_path, monkeypatch) -> None:
    """Quality scale validation should only allow explicit status values."""
    module = _load_check_repo_module()
    quality_scale_path = tmp_path / "quality_scale.yaml"
    quality_scale_path.write_text(
        "rules:\n"
        + "\n".join(
            f"  {rule}: done"
            for rules_for_tier in module.QUALITY_RULES_BY_TIER.values()
            for rule in rules_for_tier
        )
        + "\n  strict-typing: partial\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "QUALITY_SCALE_PATH", quality_scale_path)

    with pytest.raises(SystemExit):
        module.check_quality_scale()


def test_coverage_gate_requires_config_and_workflow_commands(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repository checks should require the Silver coverage gate in CI."""
    module = _load_check_repo_module()
    coverage_path = tmp_path / ".coveragerc"
    workflow_path = tmp_path / "validate.yml"
    coverage_path.write_text(
        "[run]\nsource = custom_components/unifi_unas\n"
        "[report]\nfail_under = 95\n",
        encoding="utf-8",
    )
    workflow_path.write_text(
        "run: python -m coverage run -m pytest -q\n"
        "run: python -m coverage report\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "COVERAGE_PATH", coverage_path)
    monkeypatch.setattr(module, "VALIDATE_WORKFLOW_PATH", workflow_path)

    module.check_coverage_gate()

    workflow_path.write_text("run: python -m pytest -q\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        module.check_coverage_gate()


def test_config_flow_reload_methods_are_rejected(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Config-flow reload helpers should stay out of config_flow.py."""
    module = _load_check_repo_module()
    config_flow_path = tmp_path / "config_flow.py"
    config_flow_path.write_text(
        "return self.async_update_and_abort(entry)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "CONFIG_FLOW_PATH", config_flow_path)

    module.check_config_flow_reload_methods()

    config_flow_path.write_text(
        "self.hass.config_entries.async_schedule_reload(entry.entry_id)\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        module.check_config_flow_reload_methods()


def test_homeassistant_deprecation_guards_reject_device_entry_shims(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repository checks should reject HA 2026.10 DeviceEntry shim usage."""
    module = _load_check_repo_module()
    integration_dir = tmp_path / "custom_components" / "unifi_unas"
    integration_dir.mkdir(parents=True)
    (integration_dir / "__init__.py").write_text(
        "entry_id = device_entry.config_entry_id\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "INTEGRATION_DIR", integration_dir)

    module.check_homeassistant_deprecation_guards()

    (integration_dir / "__init__.py").write_text(
        "entry_ids = device_entry.config_entries\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        module.check_homeassistant_deprecation_guards()

    (integration_dir / "__init__.py").write_text(
        "entry_id = device.primary_config_entry\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        module.check_homeassistant_deprecation_guards()


def test_homeassistant_deprecation_guards_reject_removed_restore_state_api(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """Do not introduce direct last_states access removed in HA 2026.11."""
    module = _load_check_repo_module()
    integration_dir = tmp_path / "unifi_unas"
    integration_dir.mkdir()
    source = integration_dir / "sensor.py"
    monkeypatch.setattr(module, "INTEGRATION_DIR", integration_dir)
    source.write_text(
        "state = restore_data.async_get_stored_state(entity_id)\n", encoding="utf-8"
    )
    module.check_homeassistant_deprecation_guards()

    source.write_text("state = restore_data.last_states.get(entity_id)\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        module.check_homeassistant_deprecation_guards()
    assert "RestoreStateData.last_states" in capsys.readouterr().out


def test_workflow_action_versions_reject_node20_actions(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repository checks should reject workflow actions with Node.js 20 runtimes."""
    module = _load_check_repo_module()
    pin = "0" * 40
    validate_workflow = tmp_path / "validate.yml"
    release_workflow = tmp_path / "release.yml"
    validate_workflow.write_text(
        "steps:\n"
        f"  - uses: actions/checkout@{pin} # v6\n"
        f"  - uses: actions/setup-python@{pin} # v6\n",
        encoding="utf-8",
    )
    release_workflow.write_text(
        "steps:\n"
        f"  - uses: actions/checkout@{pin} # v6\n"
        f"  - uses: actions/upload-artifact@{pin} # v7\n"
        f"  - uses: softprops/action-gh-release@{pin} # v3\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "WORKFLOWS_DIR", tmp_path)
    monkeypatch.setattr(module, "VALIDATE_WORKFLOW_PATH", validate_workflow)
    monkeypatch.setattr(module, "RELEASE_WORKFLOW_PATH", release_workflow)

    module.check_workflow_action_versions()

    # A workflow added later is covered too, not only the two named files.
    (tmp_path / "extra.yaml").write_text(
        "steps:\n  - uses: actions/stale@v9\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        module.check_workflow_action_versions()
    (tmp_path / "extra.yaml").unlink()

    # A deprecated action is now named by the pin comment, not by the ref.
    validate_workflow.write_text(
        f"steps:\n  - uses: actions/checkout@{pin} # v4\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        module.check_workflow_action_versions()

    # An unpinned reference is rejected whatever version it names.
    validate_workflow.write_text(
        "steps:\n  - uses: actions/checkout@v6\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        module.check_workflow_action_versions()

    # A pin without a readable release comment is rejected too: the comment is
    # what the deprecation table matches on, so a missing one would hide a
    # deprecated action behind an opaque SHA.
    validate_workflow.write_text(
        f"steps:\n  - uses: actions/checkout@{pin}\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        module.check_workflow_action_versions()

    # A minor-level label still has to be matched against its major line, or a
    # deprecated release passes by being spelled more precisely.
    validate_workflow.write_text(
        f"steps:\n  - uses: actions/checkout@{pin} # v4.1.7\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        module.check_workflow_action_versions()

    # A "uses" key GitHub accepts but this audit cannot parse is reported, not
    # skipped: an unreadable spelling must not become a silent bypass.
    validate_workflow.write_text(
        "steps:\n  - uses : actions/checkout@v6\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        module.check_workflow_action_versions()

    # Local and container actions carry no SHA and are exempt -- in every key
    # spelling the detector accepts, not only the canonical one.
    validate_workflow.write_text(
        "steps:\n"
        "  - uses: ./.github/actions/setup\n"
        "  - uses : ../shared/action\n"
        '  - "uses": docker://alpine:3\n'
        f"  - uses: actions/checkout@{pin} # v6\n",
        encoding="utf-8",
    )
    module.check_workflow_action_versions()

    # A flow mapping that puts another key first still has to be seen; it is
    # reported as unreadable rather than skipped.
    validate_workflow.write_text(
        "steps:\n  - {name: Checkout, uses: actions/checkout@v4}\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        module.check_workflow_action_versions()

    # Prose inside a run step is not a key and must not trip the audit.
    validate_workflow.write_text(
        "steps:\n"
        f"  - uses: actions/checkout@{pin} # v6\n"
        '  - run: echo "the build uses: a pinned action"\n',
        encoding="utf-8",
    )
    module.check_workflow_action_versions()


def test_workflow_python_versions_require_compatibility_matrix(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repository checks should keep Python-based CI on supported lines."""
    module = _load_check_repo_module()
    validate_workflow = tmp_path / "validate.yml"
    release_workflow = tmp_path / "release.yml"
    validate_text = (
        "strategy:\n"
        "  matrix:\n"
        "    include:\n"
        "      - homeassistant: \"2024.8.0\"\n"
        "        python: \"3.12\"\n"
        "      - homeassistant: \"2026.10.4\"\n"
        "        python: \"3.14\"\n"
        "steps:\n"
        "  - uses: actions/setup-python@v6\n"
        "    with:\n"
        "      python-version: ${{ matrix.python }}\n"
        "      check-latest: true\n"
    )
    release_text = (
        "steps:\n"
        "  - uses: actions/setup-python@v6\n"
        "    with:\n"
        "      python-version: \"3.14\"\n"
        "      check-latest: true\n"
    )
    validate_workflow.write_text(validate_text, encoding="utf-8")
    release_workflow.write_text(release_text, encoding="utf-8")
    monkeypatch.setattr(module, "VALIDATE_WORKFLOW_PATH", validate_workflow)
    monkeypatch.setattr(module, "RELEASE_WORKFLOW_PATH", release_workflow)

    module.check_workflow_python_versions()

    validate_workflow.write_text(
        validate_text.replace('        python: "3.12"\n', ""),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        module.check_workflow_python_versions()


@pytest.mark.parametrize("removed", [
    '"core"', 'helper_commit: "74cf5a49c63ed8d4d87717844bf14f79c28c9cea"',
    "python -m pip check", 'helper.get("vcs_info", {}).get("commit_id") != commit',
    "pytest-homeassistant @ git+https://github.com/home-assistant/core.git",
])
def test_validate_workflow_requires_homeassistant_compatibility_targets(
    removed, tmp_path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing helper pins, install steps or provenance checks must fail CI."""
    module = _load_check_repo_module()
    source = module.VALIDATE_WORKFLOW_PATH.read_text(encoding="utf-8")
    module.check_validate_workflow_homeassistant_target()
    assert removed in source
    path = tmp_path / "validate.yml"
    path.write_text(source.replace(removed, ""), encoding="utf-8")
    monkeypatch.setattr(module, "VALIDATE_WORKFLOW_PATH", path)
    with pytest.raises(SystemExit):
        module.check_validate_workflow_homeassistant_target()


def test_validate_workflow_must_cover_hacs_minimum(
    tmp_path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CI must test the Home Assistant minimum advertised in hacs.json."""
    module = _load_check_repo_module()
    module.check_validate_workflow_homeassistant_target()
    hacs_path = tmp_path / "hacs.json"
    hacs_path.write_text(
        '{"name": "UniFi Drive / UNAS", "homeassistant": "2025.1.0"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "HACS_PATH", hacs_path)
    with pytest.raises(SystemExit):
        module.check_validate_workflow_homeassistant_target()


@pytest.mark.parametrize(
    "unsafe_install", ("pip install --no-deps helper", 'if Requirement(requirement).name == "homeassistant":')
)
def test_validate_workflow_rejects_dependency_bypasses(
    unsafe_install: str, tmp_path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """A green environment must respect the HA version required by its fixtures."""
    module = _load_check_repo_module()
    source = module.VALIDATE_WORKFLOW_PATH.read_text(encoding="utf-8")
    path = tmp_path / "validate.yml"
    path.write_text(source + "\n" + unsafe_install, encoding="utf-8")
    monkeypatch.setattr(module, "VALIDATE_WORKFLOW_PATH", path)
    with pytest.raises(SystemExit):
        module.check_validate_workflow_homeassistant_target()
    assert "must not be bypassed" in capsys.readouterr().out


@pytest.mark.parametrize(
    "marker",
    (
        "  workflow_call:",
        "    uses: ./.github/workflows/validate.yml",
        "    needs: validation",
        "    if: startsWith(github.ref, 'refs/tags/v')",
        "Verify release tag matches manifest",
        'if os.environ["RELEASE_TAG"] != expected:',
    ),
)
def test_release_workflow_requires_full_validation(
    marker: str, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Removing a publication prerequisite must fail repository validation."""
    module = _load_check_repo_module()
    module.check_release_validation_gate()
    attribute = (
        "VALIDATE_WORKFLOW_PATH" if marker == "  workflow_call:" else "RELEASE_WORKFLOW_PATH"
    )
    source = getattr(module, attribute).read_text(encoding="utf-8")
    path = tmp_path / "workflow.yml"
    path.write_text(source.replace(marker, ""), encoding="utf-8")
    monkeypatch.setattr(module, attribute, path)
    with pytest.raises(SystemExit):
        module.check_release_validation_gate()


def test_release_workflow_requires_privacy_gates(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Release workflow should run repo and release ZIP privacy checks."""
    module = _load_check_repo_module()
    release_workflow = tmp_path / "release.yml"
    release_workflow.write_text(
        "steps:\n"
        "  - uses: actions/setup-python@v6\n"
        '  - run: python scripts/audit_github_public_surfaces.py --repo "$GITHUB_REPOSITORY"\n'
        "  - run: python scripts/check_repo.py\n"
        "  - run: python scripts/check_release_zip.py dist/unifi_unas.zip\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "RELEASE_WORKFLOW_PATH", release_workflow)

    module.check_release_workflow_privacy_gates()

    release_workflow.write_text(
        "steps:\n  - run: python scripts/check_repo.py\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        module.check_release_workflow_privacy_gates()


def test_parallel_updates_are_declared_for_platforms() -> None:
    """Every platform should declare a deliberate parallel update limit."""
    module = _load_check_repo_module()

    module.check_parallel_updates_rule()


def test_strict_typing_foundation_requires_typed_runtime_entry(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Typing checks should require py.typed, typed entries and a mypy gate."""
    module = _load_check_repo_module()
    integration_dir = tmp_path / "custom_components" / "unifi_unas"
    integration_dir.mkdir(parents=True)
    for filename in module.TYPED_CONFIG_ENTRY_FILES:
        content = (
            "from .runtime import UnifiDriveConfigEntry\n"
            "entry: UnifiDriveConfigEntry\n"
        )
        if filename == "runtime.py":
            content = (
                "UnifiDriveConfigEntry = ConfigEntry[UnifiUnasCoordinator]\n"
            )
        (integration_dir / filename).write_text(content, encoding="utf-8")
    mypy_files = (
        "custom_components/unifi_unas/__init__.py",
        "custom_components/unifi_unas/runtime.py",
        "custom_components/unifi_unas/api.py",
        "custom_components/unifi_unas/api_auth.py",
        "custom_components/unifi_unas/api_backup.py",
        "custom_components/unifi_unas/api_errors.py",
        "custom_components/unifi_unas/api_fan.py",
        "custom_components/unifi_unas/api_snapshot.py",
        "custom_components/unifi_unas/api_storage.py",
        "custom_components/unifi_unas/api_system.py",
        "custom_components/unifi_unas/api_transport.py",
        "custom_components/unifi_unas/api_updates.py",
        "custom_components/unifi_unas/coordinator.py",
        "custom_components/unifi_unas/config_flow_validation.py",
        "custom_components/unifi_unas/diagnostics.py",
        "custom_components/unifi_unas/discovery.py",
        "custom_components/unifi_unas/discovery_identity.py",
        "custom_components/unifi_unas/entity_base.py",
        "custom_components/unifi_unas/services.py",
        "custom_components/unifi_unas/storage_helpers.py",
        "custom_components/unifi_unas/snapshot_payload.py",
    )
    mypy_files = tuple(sorted(set(mypy_files) | {
        f"custom_components/unifi_unas/{filename}"
        for filename in module.TYPED_CONFIG_ENTRY_FILES
    }))
    for relative_path in mypy_files:
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text("# typed gate fixture\n", encoding="utf-8")
    py_typed_path = integration_dir / "py.typed"
    py_typed_path.touch()
    mypy_path = tmp_path / "mypy.ini"
    mypy_config = (
        "[mypy]\n"
        "python_version = 3.12\n"
        "strict = True\n"
        "follow_imports = skip\n"
        "files = " + ", ".join(mypy_files) + "\n"
    )
    mypy_path.write_text(mypy_config, encoding="utf-8")
    workflow_path = tmp_path / "validate.yml"
    workflow_path.write_text(
        "run: mypy --config-file mypy.ini\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "INTEGRATION_DIR", integration_dir)
    monkeypatch.setattr(module, "PY_TYPED_PATH", py_typed_path)
    monkeypatch.setattr(module, "MYPY_PATH", mypy_path)
    monkeypatch.setattr(module, "VALIDATE_WORKFLOW_PATH", workflow_path)

    module.check_strict_typing_foundation()

    new_module = integration_dir / "new_platform.py"
    new_module.write_text("VALUE = 1\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        module.check_strict_typing_foundation()
    new_module.unlink()

    mypy_path.write_text(
        mypy_config.replace("custom_components/unifi_unas/api.py, ", ""),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        module.check_strict_typing_foundation()
    mypy_path.write_text(mypy_config, encoding="utf-8")

    (integration_dir / "button.py").write_text(
        "from homeassistant.config_entries import ConfigEntry\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        module.check_strict_typing_foundation()


def test_imported_ha_typing_gate_rejects_skipped_imports(tmp_path, monkeypatch):
    module = _load_check_repo_module()
    files = ("scripts/typecheck_ha_contract.py",) + tuple(
        f"custom_components/unifi_unas/{name}.py"
        for name in ("device", "runtime", "entity_base", "entry_reload",
                     "sensor_descriptions", "binary_sensor_descriptions")
    )
    config = (
        "[mypy]\nstrict = True\nfollow_imports = silent\n"
        "disallow_any_unimported = True\ndisallow_any_expr = True\n"
        f"files = {', '.join(files)}\n"
    )
    path = tmp_path / "mypy-ha.ini"
    path.write_text(config)
    for name in files:
        file = tmp_path / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("# Synthetic typing contract fixture\n")
    workflow = tmp_path / "validate.yml"
    workflow.write_text("run: mypy --config-file mypy-ha.ini\n")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "VALIDATE_WORKFLOW_PATH", workflow)
    module.check_imported_ha_typing_gate()
    path.write_text(config.replace(", custom_components/unifi_unas/runtime.py", ""))
    with pytest.raises(SystemExit):
        module.check_imported_ha_typing_gate()
    path.write_text(config.replace("silent", "skip"))
    with pytest.raises(SystemExit):
        module.check_imported_ha_typing_gate()
    path.write_text(config)
    workflow.write_text("run: true\n")
    with pytest.raises(SystemExit):
        module.check_imported_ha_typing_gate()


def test_exception_translation_check_rejects_direct_raises(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repository checks should keep HA exceptions on translation helpers."""
    module = _load_check_repo_module()
    integration_dir = tmp_path / "custom_components" / "unifi_unas"
    integration_dir.mkdir(parents=True)
    services_path = integration_dir / "services.py"
    services_path.write_text(
        "def safe(): pass\n",
        encoding="utf-8",
    )
    (integration_dir / "exceptions.py").write_text(
        "def unifi_unas_error(): pass\n"
        "def unifi_unas_validation_error(): pass\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "INTEGRATION_DIR", integration_dir)

    module.check_exception_translations()

    services_path.write_text(
        "raise ServiceValidationError('not translated')\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        module.check_exception_translations()


def test_icon_translation_check_requires_icons_json(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repository checks should keep entity icons in icons.json."""
    module = _load_check_repo_module()
    integration_dir = tmp_path / "custom_components" / "unifi_unas"
    integration_dir.mkdir(parents=True)
    strings_path = integration_dir / "strings.json"
    icons_path = integration_dir / "icons.json"
    (integration_dir / "sensor.py").write_text("class Sensor: pass\n", encoding="utf-8")
    strings_path.write_text(
        '{"entity": {"sensor": {"temperature": {"name": "Temperature"}}}}',
        encoding="utf-8",
    )
    icons_path.write_text(
        '{"entity": {"sensor": {"temperature": {"default": "mdi:thermometer"}}}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "INTEGRATION_DIR", integration_dir)
    monkeypatch.setattr(module, "STRINGS_PATH", strings_path)
    monkeypatch.setattr(module, "ICONS_PATH", icons_path)

    module.check_icon_translations()

    (integration_dir / "sensor.py").write_text(
        'class Sensor:\n    _attr_icon = "mdi:thermometer"\n',
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        module.check_icon_translations()


def test_config_flow_data_descriptions_are_required() -> None:
    """Config-flow strings should describe every form field."""
    module = _load_check_repo_module()
    translation = {
        "config": {
            "step": {
                "user": {
                    "data": {
                        "host": "Host",
                        "port": "Port",
                    },
                    "data_description": {
                        "host": "Device host",
                    },
                }
            }
        }
    }

    with pytest.raises(SystemExit):
        module._check_config_step_data_descriptions(translation, "strings.json")

    translation["config"]["step"]["user"]["data_description"]["port"] = (
        "Device port"
    )
    module._check_config_step_data_descriptions(translation, "strings.json")


def test_entity_name_rule_rejects_false_opt_out(tmp_path, monkeypatch) -> None:
    """Bronze validation should reject entities opting out of has_entity_name."""
    module = _load_check_repo_module()
    integration_dir = tmp_path / "custom_components" / "unifi_unas"
    integration_dir.mkdir(parents=True)
    (integration_dir / "sensor.py").write_text(
        "class BadEntity:\n    _attr_has_entity_name = False\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "INTEGRATION_DIR", integration_dir)

    with pytest.raises(SystemExit):
        module.check_entity_name_rule()

    (integration_dir / "sensor.py").write_text(
        "class GoodEntity:\n    _attr_has_entity_name = True\n",
        encoding="utf-8",
    )
    module.check_entity_name_rule()


@pytest.mark.parametrize("key", ("filename", "zip_release"))
def test_hacs_rejects_release_artifact_keys(
    key: str,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HACS metadata should not carry release artifact hints."""
    module = _load_check_repo_module()
    manifest_path = tmp_path / "manifest.json"
    hacs_path = tmp_path / "hacs.json"
    manifest_path.write_text(
        '{"name": "UniFi Drive / UNAS", "version": "0.3.7"}',
        encoding="utf-8",
    )
    hacs_path.write_text(
        (
            '{"name": "UniFi Drive / UNAS", "homeassistant": "2024.8.0", '
            f'"render_readme": true, "{key}": "unifi_unas.zip"}}'
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(module, "HACS_PATH", hacs_path)

    with pytest.raises(SystemExit):
        module.check_hacs()


def test_legal_docs_require_unofficial_disclaimer(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legal checks should require the unofficial disclaimer and legal link."""
    module = _load_check_repo_module()
    readme_path = tmp_path / "README.md"
    legal_path = tmp_path / "legal.md"
    readme_path.write_text(
        "\n".join(
            (
                "Home Assistant integration for UniFi Drive / UNAS (Unofficial)",
                "[docs/legal.md](docs/legal.md)",
                "This project is an unofficial community integration.",
                "The project does not claim affiliation with Ubiquiti Inc.",
                "The repository does not include official Ubiquiti logos.",
                "The repository does not include proprietary Ubiquiti source code.",
            )
        ),
        encoding="utf-8",
    )
    legal_path.write_text(
        "\n".join(
            (
                "This repository is an unofficial community project.",
                "It has no affiliation with any vendor.",
                "Names are descriptive compatibility references.",
                "No official Ubiquiti logos are bundled.",
                "No proprietary Ubiquiti source code is bundled.",
                "It records observed interoperability behavior only.",
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "README_PATH", readme_path)
    monkeypatch.setattr(module, "LEGAL_PATH", legal_path)

    module.check_legal_docs()

    readme_path.write_text("UniFi Drive only\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        module.check_legal_docs()


def test_bronze_docs_require_core_readme_sections(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bronze docs checks should require installation, removal and support sections."""
    module = _load_check_repo_module()
    readme_path = tmp_path / "README.md"
    readme_path.write_text(
        "\n".join(
            module.README_BRONZE_DOC_MARKERS
            + module.README_HIGHER_QUALITY_DOC_MARKERS
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "README_PATH", readme_path)

    module.check_bronze_docs()

    readme_path.write_text("## Installation\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        module.check_bronze_docs()


@pytest.mark.parametrize(
    "missing_section", ("marketplace", "legacy", "upgrade", "removal")
)
def test_marketplace_docs_require_current_and_legacy_instructions(
    missing_section: str, tmp_path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """Keep the Marketplace path and the old-domain migration distinct."""
    module = _load_check_repo_module()
    readme = tmp_path / "README.md"
    installation = tmp_path / "installation.md"
    readme.write_text("\n".join(module.MARKETPLACE_README_MARKERS), encoding="utf-8")
    installation.write_text("\n".join(module.INSTALLATION_DOC_MARKERS), encoding="utf-8")
    monkeypatch.setattr(module, "README_PATH", readme)
    monkeypatch.setattr(module, "INSTALLATION_PATH", installation)
    module.check_marketplace_docs()

    path, marker = {
        "marketplace": (readme, "### Home Assistant Marketplace"),
        "legacy": (installation, "## Home Assistant Before 2026.11"),
        "upgrade": (installation, "## Upgrading From Before 0.8.0"),
        "removal": (installation, "## Removal"),
    }[missing_section]
    path.write_text(path.read_text(encoding="utf-8").replace(marker, ""), encoding="utf-8")
    with pytest.raises(SystemExit):
        module.check_marketplace_docs()
    assert "missing Marketplace documentation" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("tracked_path", "expected"),
    (
        (".storage/core.config_entries", "tracked secret-like path"),
        ("home-assistant_v2.db", "tracked secret-like path"),
        ("ha_frontend_smoke.env", "tracked secret-like path"),
        ("custom_components/unifi_unas/__pycache__/api.pyc", "generated artifact"),
        ("assets/unifi-logo.png", "official/vendor asset"),
        ("assets/ubiquiti/app.js", "official/vendor asset"),
    ),
)
def test_tracked_file_hygiene_rejects_path_markers(
    tracked_path: str,
    expected: str,
    tmp_path,
) -> None:
    """Tracked-file hygiene should reject known unsafe path classes."""
    module = _load_check_repo_module()

    issues = module._tracked_file_hygiene_issues(tmp_path, [tracked_path])

    assert any(expected in issue for issue in issues)


@pytest.mark.parametrize(
    ("content", "expected"),
    (
        ("-----BEGIN " + "PRIVATE KEY-----\nsecret\n", "private key"),
        ("TOKEN=" + "abcdefghijklmnopqrstuvwxyz123456\n", "UniFi token cookie"),
        ("password=" + "A1b2C3d4E5f6!\n", "plain password assignment"),
        ("host=" + ".".join(("10", "1", "2", "3")) + "\n", "private local IPv4 address"),
        ("Copy" + "right 2024 " + "Ubi" + "quiti\n", "Ubiquiti copyright header"),
        ("Ubi" + "quiti Inc. All rights " + "reserved\n", "all-rights-reserved"),
        ("proprietary and " + "confidential\n", "proprietary license marker"),
        (
            "official " + "Ubi" + "quiti integration\n",
            "official vendor integration claim",
        ),
        ("endorsed by " + "Ubi" + "quiti\n", "vendor endorsement claim"),
    ),
)
def test_tracked_file_hygiene_rejects_content_markers(
    content: str,
    expected: str,
    tmp_path,
) -> None:
    """Tracked-file hygiene should reject secrets and proprietary markers."""
    module = _load_check_repo_module()
    note_path = tmp_path / "note.txt"
    note_path.write_text(content, encoding="utf-8")

    issues = module._tracked_file_hygiene_issues(tmp_path, ["note.txt"])

    assert any(expected in issue for issue in issues)


def test_tracked_file_hygiene_rejects_configured_local_marker_paths(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tracked-file hygiene should reject configured local markers in paths."""
    module = _load_check_repo_module()
    marker = "private" + "-user"
    monkeypatch.setenv(module.FORBIDDEN_MARKERS_ENV, marker)
    tracked_path = f"docs/{marker}.md"

    issues = module._tracked_file_hygiene_issues(tmp_path, [tracked_path])

    assert any("configured local identifier marker" in issue for issue in issues)


def test_tracked_file_hygiene_rejects_configured_local_marker_content(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tracked-file hygiene should reject configured local markers in content."""
    module = _load_check_repo_module()
    marker = "private" + "-user"
    monkeypatch.setenv(module.FORBIDDEN_MARKERS_ENV, marker)
    note_path = tmp_path / "note.txt"
    note_path.write_text(f"user={marker}\n", encoding="utf-8")

    issues = module._tracked_file_hygiene_issues(tmp_path, ["note.txt"])

    assert any("configured local identifier marker" in issue for issue in issues)


def test_tracked_file_hygiene_rejects_jwt_like_tokens(tmp_path) -> None:
    """Tracked-file hygiene should catch standalone long-lived token shapes."""
    module = _load_check_repo_module()
    note_path = tmp_path / "note.txt"
    token = ".".join(("eyJ" + "a" * 20, "b" * 20, "c" * 20))
    note_path.write_text(f"token={token}\n", encoding="utf-8")

    issues = module._tracked_file_hygiene_issues(tmp_path, ["note.txt"])

    assert any("JWT-like token" in issue for issue in issues)


def test_tracked_file_hygiene_allows_project_artwork_path(tmp_path) -> None:
    """A generic project artwork path should not be treated as official art."""
    module = _load_check_repo_module()
    asset_path = (
        tmp_path / "custom_components" / "unifi_unas" / "artwork" / "logo.png"
    )
    asset_path.parent.mkdir(parents=True)
    asset_path.write_bytes(b"original project asset placeholder")

    issues = module._tracked_file_hygiene_issues(
        tmp_path,
        ["custom_components/unifi_unas/artwork/logo.png"],
    )

    assert issues == []


@pytest.mark.parametrize(
    "tracked_path",
    (
        "frontend/ui-theme.css",
        "custom_components/unifi_unas/ui.js",
        "assets/ui-logo.png",
    ),
)
def test_tracked_file_hygiene_allows_generic_ui_files(
    tracked_path: str,
    tmp_path,
) -> None:
    """Generic ui-prefixed project files should not look like vendor assets."""
    module = _load_check_repo_module()
    path = tmp_path / tracked_path
    path.parent.mkdir(parents=True)
    path.write_text("original project asset\n", encoding="utf-8")

    issues = module._tracked_file_hygiene_issues(tmp_path, [tracked_path])

    assert issues == []
