from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.generate_artifact_manifests import (
    ManifestContext,
    ProvenanceValue,
    build_manifest,
    validate_artifact_path,
)


def context() -> ManifestContext:
    return ManifestContext(
        source_snapshot_id="snapshot-2025-08",
        data_mode="OFFLINE_SNAPSHOT",
        reporting_period="2025-08",
        comparison_period="2025-07",
        dataset_profile="default",
        dataset_hash=ProvenanceValue("d" * 64),
        configuration_hash=ProvenanceValue("c" * 64),
        model_version=ProvenanceValue(None, "No model is used by this artifact"),
        api_version=ProvenanceValue("1.0.0"),
        script_version=ProvenanceValue("1.0.0"),
        metric_registry_version="1.0.0",
        filter_scope={
            "headline_scope": "all_portfolio",
            "approved_reference_basket": "BASKET-001",
        },
        evidence_ids=("NAIM-snapshot-2025-08",),
        data_quality_result="PASS",
        synthetic_data=True,
        validation_status="PASS",
        validation_evidence=("evidence.json",),
    )


def test_manifest_is_portable_hashed_and_has_deterministic_build_id(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    outputs = repository / "outputs"
    outputs.mkdir(parents=True)
    artifact = outputs / "review.xlsx"
    artifact.write_bytes(b"validated workbook")
    evidence = repository / "evidence.json"
    evidence.write_text("{}", encoding="utf-8")
    source = repository / "source.csv"
    source.write_text("a,b\n1,2\n", encoding="utf-8")

    first = build_manifest(
        artifact,
        context(),
        source_inputs=[source],
        repository_root=repository,
        output_root=outputs,
        built_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    second = build_manifest(
        artifact,
        context(),
        source_inputs=[source],
        repository_root=repository,
        output_root=outputs,
        built_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=1),
    )

    assert first["product"] == "nAIM Portfolio Intelligence Workbench"
    assert first["artifact"]["path"] == "outputs/review.xlsx"
    assert first["artifact"]["bytes"] == len(b"validated workbook")
    assert len(first["artifact"]["sha256"]) == 64
    assert first["source_inputs"][0]["path"] == "source.csv"
    assert first["metric_registry_version"] == "1.0.0"
    assert first["artifact_type"] == "EXCEL_WORKBOOK"
    assert first["artifact_version"] == "1.0.0"
    assert first["created_at"] == first["built_at_utc"]
    assert first["created_by_component"] == "nAIM release pipeline"
    assert first["source_workspace"] == "all_portfolio_control"
    assert first["comparison_period"] == "2025-07"
    assert first["dataset_profile"] == "default"
    assert first["dataset_hash"] == "d" * 64
    assert first["configuration_hash"] == "c" * 64
    assert first["code_version"] == "1.0.0"
    assert first["file_name"] == "review.xlsx"
    assert first["file_size"] == len(b"validated workbook")
    assert first["sha256"] == first["artifact"]["sha256"]
    assert first["validation_status"] == "PASS"
    assert first["data_quality_status"] == "PASS"
    assert first["synthetic_data_flag"] is True
    assert first["artifact_id"] == first["build_id"]
    assert first["filter_scope"]["headline_scope"] == "all_portfolio"
    assert first["evidence_ids"] == ["NAIM-snapshot-2025-08"]
    assert first["data_quality_result"] == "PASS"
    assert first["synthetic_data"] is True
    assert str(tmp_path) not in str(first)
    assert first["build_id"] == second["build_id"]
    assert first["built_at_utc"] != second["built_at_utc"]


def test_artifact_must_exist_and_remain_below_outputs(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    outputs = repository / "outputs"
    outputs.mkdir(parents=True)
    outside = repository / "outside.txt"
    outside.write_text("no", encoding="utf-8")

    with pytest.raises(ValueError, match="outside the output boundary"):
        validate_artifact_path(outside, outputs)
    with pytest.raises(FileNotFoundError):
        validate_artifact_path(outputs / "missing.xlsx", outputs)


def test_manifest_rejects_unsafe_sources_and_invalid_mode(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    outputs = repository / "outputs"
    outputs.mkdir(parents=True)
    artifact = outputs / "review.xlsx"
    artifact.write_bytes(b"ok")
    secret = repository / ".env"
    secret.write_text("SECRET=hidden", encoding="utf-8")

    with pytest.raises(ValueError, match="Secret-bearing"):
        build_manifest(
            artifact,
            context(),
            source_inputs=[secret],
            repository_root=repository,
            output_root=outputs,
        )

    invalid = ManifestContext(**{**context().__dict__, "data_mode": "HYBRID"})
    with pytest.raises(ValueError, match="data_mode"):
        build_manifest(
            artifact,
            invalid,
            repository_root=repository,
            output_root=outputs,
        )


def test_missing_provenance_requires_an_explicit_reason() -> None:
    invalid = ManifestContext(**{**context().__dict__, "model_version": ProvenanceValue(None)})
    with pytest.raises(ValueError, match="model_version requires"):
        invalid.validate()
