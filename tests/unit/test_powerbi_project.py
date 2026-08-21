from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from naim_risk.config import REPOSITORY_ROOT
from naim_risk.powerbi_project import (
    CAPABILITY_STATUS,
    MEASURES,
    DisabledPowerBIPublisher,
    PowerBIPublisherConfigurationError,
    PowerBIPublishResult,
    PowerBIPublishTarget,
    build_powerbi_project,
    publisher_from_environment,
    validate_powerbi_project,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _build(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    target = tmp_path / "nAIM.PowerBIProject"
    result = build_powerbi_project(repository_root=REPOSITORY_ROOT, output_root=target)
    return target, result


def test_pbip_scaffold_is_relative_governed_and_source_control_friendly(tmp_path: Path) -> None:
    target, result = _build(tmp_path)
    assert result["capability_status"] == CAPABILITY_STATUS == "INTEGRATION_ONLY"
    assert result["contains_pbix"] is False
    assert result["desktop_validation"]["performed"] is False
    assert result["publication_validation"]["performed"] is False
    assert result["static_validation"]["status"] == "PASS"
    assert not list(target.rglob("*.pbix"))
    assert not list(target.rglob("*.pbit"))

    pbip = json.loads((target / "nAIM.pbip").read_text(encoding="utf-8"))
    assert pbip["artifacts"] == [{"report": {"path": "Report"}}]
    pointer = json.loads((target / "Report/definition.pbir").read_text(encoding="utf-8"))
    assert pointer["datasetReference"]["byPath"]["path"] == "../SemanticModel"
    assert not Path(pointer["datasetReference"]["byPath"]["path"]).is_absolute()

    for path in target.rglob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))
    json.loads((target / "Report/.platform").read_text(encoding="utf-8"))
    json.loads((target / "SemanticModel/.platform").read_text(encoding="utf-8"))

    manifest = json.loads((target / "Build/project-manifest.json").read_text(encoding="utf-8"))
    required_provenance = {
        "artifact_id",
        "artifact_type",
        "artifact_version",
        "created_at",
        "created_by_component",
        "source_workspace",
        "reporting_period",
        "comparison_period",
        "filter_scope",
        "dataset_profile",
        "dataset_hash",
        "configuration_hash",
        "metric_registry_version",
        "code_version",
        "evidence_ids",
        "data_quality_status",
        "synthetic_data_flag",
        "file_name",
        "file_size",
        "sha256",
        "dependencies",
        "validation_status",
        "validation_tests",
        "known_limitations",
    }
    assert required_provenance <= manifest.keys()
    assert manifest["validation_status"] == "STATIC_VALIDATION_PASS"
    assert manifest["desktop_validation"]["performed"] is False
    for item in manifest["files"]:
        artifact = target / item["path"]
        assert artifact.is_file()
        assert _sha256(artifact) == item["sha256"]
        assert not Path(item["path"]).is_absolute()

    registry = json.loads((target / "Governance/metric-registry.json").read_text())
    governed_ids = {metric["metric_id"] for metric in registry["metrics"]}
    with (target / "Data/kpi_snapshot.csv").open(newline="") as handle:
        kpi_ids = {row["metric_id"] for row in csv.DictReader(handle)}
    assert kpi_ids == governed_ids
    assert result["row_counts"]["kpi_snapshot"] == len(governed_ids)


def test_tmdl_measures_relationships_and_report_specs_are_statically_complete(
    tmp_path: Path,
) -> None:
    target, _ = _build(tmp_path)
    relationships = (target / "SemanticModel/definition/relationships.tmdl").read_text(
        encoding="utf-8"
    )
    assert relationships.count("relationship ") == 5
    assert relationships.count("crossFilteringBehavior: oneDirection") == 5
    assert "bothDirections" not in relationships

    measures_tmdl = (target / "SemanticModel/definition/tables/kpi_snapshot.tmdl").read_text(
        encoding="utf-8"
    )
    for measure in MEASURES:
        assert f"measure '{measure.name}'" in measures_tmdl
        assert f"formatString: {measure.format_string}" in measures_tmdl
    assert "REPLACE_WITH_ABSOLUTE_PATH_TO_EXTRACTS" in (
        target / "SemanticModel/definition/expressions.tmdl"
    ).read_text(encoding="utf-8")

    calculation_group = json.loads(
        (target / "SemanticModel/specifications/calculation-group.json").read_text()
    )
    assert calculation_group["status"] == "SPECIFICATION_REQUIRES_DESKTOP_VALIDATION"
    assert {item["name"] for item in calculation_group["items"]} == {
        "Actual",
        "Prior Period",
        "Variance",
        "Variance %",
        "Scenario",
    }
    assert calculation_group["unsupported_item"]["name"] == "YoY"

    field_parameters = json.loads(
        (target / "SemanticModel/specifications/field-parameters.json").read_text()
    )
    assert {parameter["kind"] for parameter in field_parameters["parameters"]} == {
        "measure",
        "column",
    }
    assert all(
        parameter["parameter_metadata"] == {"version": 3, "kind": 2}
        for parameter in field_parameters["parameters"]
    )
    assert all(
        "NAMEOF" in parameter["calculated_table_expression"]
        for parameter in field_parameters["parameters"]
    )
    pages = json.loads((target / "Report/specifications/report-pages.json").read_text())
    assert len(pages["pages"]) == 6
    assert all(page["required_visuals"] for page in pages["pages"])
    theme = json.loads((target / "Report/theme/nAIM-theme.json").read_text())
    assert theme["name"] == "nAIM Portfolio Intelligence"
    assert len(theme["dataColors"]) >= 6


def test_static_validator_rejects_absolute_paths_secrets_and_binary_claims(tmp_path: Path) -> None:
    target, _ = _build(tmp_path)
    pointer_path = target / "Report/definition.pbir"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["datasetReference"]["byPath"]["path"] = "/Users/example/model"
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")
    (target / "leaked.txt").write_text(
        "client_secret=ThisMustNeverBeCommitted12345", encoding="utf-8"
    )
    (target / "fabricated.pbix").write_bytes(b"not-a-real-pbix")

    validation = validate_powerbi_project(target)
    assert validation["status"] == "FAIL"
    combined = " ".join(validation["errors"])
    assert "Absolute PBIP path" in combined
    assert "Potential secret" in combined
    assert "Fabricated binary" in combined


def test_publisher_is_disabled_by_default_and_requires_explicit_adapter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in (
        "NAIM_POWERBI_PUBLISH_ENABLED",
        "NAIM_POWERBI_TENANT_ID",
        "NAIM_POWERBI_CLIENT_ID",
        "NAIM_POWERBI_CLIENT_SECRET",
        "NAIM_POWERBI_WORKSPACE_ID",
    ):
        monkeypatch.delenv(name, raising=False)
    publisher, settings = publisher_from_environment()
    assert isinstance(publisher, DisabledPowerBIPublisher)
    assert settings is None
    result = publisher.publish(
        tmp_path,
        settings,
        PowerBIPublishTarget("nAIM Model", "nAIM Report"),
    )
    assert result.status == "DISABLED"
    assert result.published is False
    assert result.remote_identifier is None

    monkeypatch.setenv("NAIM_POWERBI_PUBLISH_ENABLED", "true")
    with pytest.raises(PowerBIPublisherConfigurationError, match="required environment"):
        publisher_from_environment()

    monkeypatch.setenv("NAIM_POWERBI_TENANT_ID", "tenant")
    monkeypatch.setenv("NAIM_POWERBI_CLIENT_ID", "client")
    monkeypatch.setenv("NAIM_POWERBI_CLIENT_SECRET", "secret-value")
    monkeypatch.setenv("NAIM_POWERBI_WORKSPACE_ID", "workspace")
    with pytest.raises(PowerBIPublisherConfigurationError, match="no approved publisher adapter"):
        publisher_from_environment()

    class RecordingPublisher:
        def publish(self, project_root, configured, target):  # type: ignore[no-untyped-def]
            assert project_root == tmp_path
            assert configured.client_secret == "secret-value"
            assert target.report_name == "nAIM Report"
            return PowerBIPublishResult("TEST_ONLY", False, "No network call")

    adapter, configured = publisher_from_environment(RecordingPublisher())
    assert configured is not None
    injected = adapter.publish(
        tmp_path,
        configured,
        PowerBIPublishTarget("nAIM Model", "nAIM Report"),
    )
    assert injected.status == "TEST_ONLY"
    assert injected.published is False
