"""Keep hardware reports usable across the public support forms."""

from pathlib import Path

import pytest
import yaml


TEMPLATES = Path(__file__).resolve().parents[1] / ".github" / "ISSUE_TEMPLATE"


@pytest.mark.parametrize("name", ["bug_report", "support_question", "hardware_report"])
def test_model_forms_include_larger_unas_without_duplicate_fields(name: str) -> None:
    form = yaml.safe_load((TEMPLATES / f"{name}.yml").read_text(encoding="utf-8"))
    fields = [field for field in form["body"] if "id" in field]
    assert len({field["id"] for field in fields}) == len(fields)
    model = next(field for field in fields if field["id"] == "device_model")
    assert model["validations"]["required"] is True
    assert {"UNAS Pro", "UNAS Pro4", "UNAS Pro8"} <= set(model["attributes"]["options"])


def test_hardware_report_requires_evidence_context_but_not_a_private_attachment() -> None:
    form = yaml.safe_load((TEMPLATES / "hardware_report.yml").read_text(encoding="utf-8"))
    fields = {field["id"]: field for field in form["body"] if "id" in field}
    for key in ("device_model", "versions", "observation_date", "auth_method", "permissions", "storage_layout", "results"):
        assert fields[key]["validations"]["required"] is True
    assert not fields["diagnostics"].get("validations", {}).get("required", False)
    assert all(option["required"] for option in fields["privacy"]["attributes"]["options"])
