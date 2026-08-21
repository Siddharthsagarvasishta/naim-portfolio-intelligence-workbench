from __future__ import annotations

import copy
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from naim_risk.config import CORE_METRIC_IDS, REPOSITORY_ROOT, metric_lookup
from naim_risk.metrics.governance import (
    bind_runtime_evidence,
    data_source_diagnostics,
    governed_metric_fields,
)
from naim_risk.runtime_modes import DataMode, SourceContext


def _canonical_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _registry_paths() -> tuple[Path, Path]:
    return (
        REPOSITORY_ROOT / "config" / "metric_registry.json",
        REPOSITORY_ROOT
        / "src"
        / "naim_risk"
        / "resources"
        / "config"
        / "metric_registry.json",
    )


def test_registry_covers_every_executable_kpi_with_non_placeholder_lineage() -> None:
    root, bundled = _registry_paths()
    assert root.read_bytes() == bundled.read_bytes()
    registry = json.loads(root.read_text(encoding="utf-8"))
    assert registry["registry_version"] == "2.0.0"
    assert registry["calculation_version"] == "2.0.0"
    metrics = {row["metric_id"]: row for row in registry["metrics"]}
    assert set(metrics) == set(CORE_METRIC_IDS)
    assert len(metrics) == 15

    placeholders = {"", "n/a", "na", "none", "null", "tbd", "unknown"}
    for metric_id, definition in metrics.items():
        assert definition["source"] == "validated.monthly_account_performance"
        assert definition["source"].strip().lower() not in placeholders
        assert definition["source_fields"]
        assert all(str(field).strip().lower() not in placeholders for field in definition["source_fields"])
        assert definition["source_grain"] == (
            "one validated row per account_id and calendar month"
        )
        assert definition["supporting_sources"]
        assert definition["supporting_sources"][0]["source"] == (
            "validated.customer_account_master"
        )
        assert definition["transformation"] == {
            "module": "naim_risk.metrics.core",
            "callable": "calculate_period_kpis",
            "calculation_version": registry["calculation_version"],
        }
        assert definition["metric_version"] == definition["version"]
        refresh = definition["refresh_facts"]
        assert refresh["watermark_field"] == "month"
        assert refresh["runtime_watermark_source"] == "run_manifest.maximum_data_date"
        assert "completion_timestamp" in refresh["refresh_time_source"]
        assert "publication_allowed" in refresh["publication_gate"]
        assert metric_id in definition["guardrail_rule"]["rule_id"]

    expected_profit_sources = {
        item["source"] for item in metrics["EXPECTED_PROFIT"]["supporting_sources"]
    }
    assert "config/economic_scenarios.json#scenarios.Baseline" in expected_profit_sources


def test_every_interpretation_guardrail_and_assessment_is_metric_specific() -> None:
    root, _ = _registry_paths()
    definitions = json.loads(root.read_text(encoding="utf-8"))["metrics"]
    conclusions: set[tuple[str, ...]] = set()
    exclusions: set[tuple[str, ...]] = set()
    for definition in definitions:
        boundary = definition["interpretation_boundary"]
        assert isinstance(boundary["can_conclude"], list) and boundary["can_conclude"]
        assert isinstance(boundary["cannot_conclude"], list) and boundary["cannot_conclude"]
        assert boundary["directionality"] in {"higher_is_better", "lower_is_better"}
        assert boundary["caveats"]
        assert boundary["permitted_next_action"]
        conclusions.add(tuple(boundary["can_conclude"]))
        exclusions.add(tuple(boundary["cannot_conclude"]))

        adequacy = definition["adequacy_rule"]
        assert adequacy["minimum_sample"] > 0
        assert adequacy["status_when_met"] == "ADEQUATE"
        assert adequacy["status_when_unmet"] == "INADEQUATE"
        assert adequacy["denominator_rule"]

        statistical = definition["statistical_rule"]
        assert statistical["inference_performed"] is False
        assert statistical["status"] == "NOT_RUN"
        assert statistical["method"] == "descriptive_only"

        materiality = definition["practical_materiality_rule"]
        assert materiality["comparison_basis"] == "absolute_month_over_month_change"
        assert materiality["threshold"] > 0
        assert materiality["status_when_material"] == "MATERIAL"
        assert materiality["status_when_immaterial"] == "IMMATERIAL"

        guardrail = definition["guardrail_rule"]
        assert guardrail["directionality"] == boundary["directionality"]
        assert guardrail["rule_version"] == "1.0.0"
        assert guardrail["denominator_rule"]
        assert guardrail["explanation_template"]
        assert {row["status"] for row in guardrail["thresholds"]} == {
            "CRITICAL",
            "ADVERSE",
            "WATCH",
            "FAVOURABLE",
            "NEUTRAL",
        }
    assert len(conclusions) == len(definitions)
    assert len(exclusions) == len(definitions)


def test_kpis_bind_deterministic_evidence_without_fabricated_reconciliation(service) -> None:
    first = service.kpis(filters={"geography": ["East", "West"]})["data"]
    second = service.kpis(filters={"geography": ["East", "West"]})["data"]
    assert len(first) == len(CORE_METRIC_IDS)
    assert [row["runtime_evidence"] for row in first] == [
        row["runtime_evidence"] for row in second
    ]
    registry = metric_lookup(service.config)
    for row in first:
        assert row["source"] != "N/A"
        assert row["source"] == registry[row["metric_id"]]["source"]
        assert row["source_fields"] == registry[row["metric_id"]]["source_fields"]
        assert row["source_grain"] == registry[row["metric_id"]]["source_grain"]
        assert row["lineage"]["transformation"]["calculation_version"] == "2.0.0"
        assert row["statistical_status"] == "NOT_RUN"
        assert row["statistical_assessment"]["inference_performed"] is False
        assert row["statistical_assessment"]["status"] == "NOT_RUN"
        assert row["reconciliation"]["status"] == "NOT_RUN"
        assert row["reconciliation"]["checked_at"] is None
        assert "no cross-artifact reconciliation" in row["reconciliation"]["detail"]
        assert row["guardrail"]["rule_id"]
        assert row["guardrail"]["rule_version"] == "1.0.0"
        assert row["guardrail"]["explanation"]
        assert row["guardrail"]["directionality"] in {
            "higher_is_better",
            "lower_is_better",
        }
        if row["sample_adequacy"]["status"] == "INADEQUATE":
            assert row["guardrail"]["status"] == "INSUFFICIENT_DATA"
            assert row["status"] == "insufficient_data"

        evidence = row["runtime_evidence"]
        assert evidence["configuration_hash"] == service.config.config_hash
        assert evidence["run_id"] == service.data.run_id
        assert evidence["dataset_hash"]
        binding = {
            "metric_id": row["metric_id"],
            "metric_version": row["metric_version"],
            "calculation_version": row["calculation_version"],
            "dataset_hash": evidence["dataset_hash"],
            "dataset_hash_basis": evidence["dataset_hash_basis"],
            "configuration_hash": evidence["configuration_hash"],
            "run_id": evidence["run_id"],
            "reporting_period": row["reporting_period"],
            "comparison_period": row["comparison_period"],
            "filter_scope": {"geography": ["East", "West"]},
            "value": row["value"],
            "prior_value": row["prior_value"],
            "denominator": row["denominator"],
        }
        expected_hash = _canonical_hash(binding)
        assert evidence["binding_sha256"] == expected_hash
        assert evidence["evidence_id"] == f"KPI-EVIDENCE-{expected_hash[:20].upper()}"


def test_status_thresholds_are_configured_and_adequacy_is_not_inference(service) -> None:
    metadata = copy.deepcopy(metric_lookup(service.config)["ACTIVE_ACCOUNTS"])
    critical = governed_metric_fields(
        metadata,
        value=100.0,
        absolute_change=-6.0,
        denominator=100.0,
    )
    assert critical["guardrail"]["status"] == "CRITICAL"
    assert critical["guardrail"]["threshold_applied"]["value"] == -5.0

    metadata["guardrail_rule"]["thresholds"][0]["value"] = -10.0
    governed_by_changed_config = governed_metric_fields(
        metadata,
        value=100.0,
        absolute_change=-6.0,
        denominator=100.0,
    )
    assert governed_by_changed_config["guardrail"]["status"] == "ADVERSE"

    inadequate = governed_metric_fields(
        metadata,
        value=100.0,
        absolute_change=-6.0,
        denominator=0.0,
    )
    assert inadequate["sample_adequacy"]["status"] == "INADEQUATE"
    assert inadequate["guardrail"]["status"] == "INSUFFICIENT_DATA"
    assert inadequate["statistical_assessment"] == {
        "inference_performed": False,
        "status": "NOT_RUN",
        "method": "descriptive_only",
        "explanation": (
            "Minimum-sample adequacy is a data sufficiency check; no confidence interval, "
            "hypothesis test, or causal inference was run for this KPI response."
        ),
    }
    assert inadequate["practical_materiality"]["status"] == "MATERIAL"


def test_runtime_binding_rejects_conflicting_context(service) -> None:
    row = service.kpis()["data"][0]
    with pytest.raises(ValueError, match="configuration_hash does not match"):
        bind_runtime_evidence(
            [row],
            context={
                "active_mode": "OFFLINE_SNAPSHOT",
                "configured_mode": "OFFLINE_SNAPSHOT",
                "configuration_hash": "foreign-configuration",
                "dataset_hash": "foreign-dataset",
                "dataset_hash_basis": "foreign-basis",
                "run_id": "foreign-run",
            },
            manifest=service.data.manifest,
            configuration_hash=service.config.config_hash,
            run_id=service.data.run_id,
            filters=None,
        )


def test_server_diagnostics_separate_active_mode_from_freshness() -> None:
    context = SourceContext(
        active_mode=DataMode.OFFLINE_SNAPSHOT,
        configured_mode=DataMode.OFFLINE_SNAPSHOT,
        snapshot_date="2026-08-10",
        configuration_hash="config-sha",
        dataset_hash="dataset-sha",
        dataset_hash_basis="validated-and-mart-files",
        run_id="demo-run",
        synthetic=True,
        reason=None,
    )
    manifest = {
        "run_id": "demo-run",
        "configuration_hash": "config-sha",
        "completion_timestamp": "2026-08-10T00:00:00+00:00",
        "maximum_data_date": "2026-08-10",
    }
    current = data_source_diagnostics(
        context=context,
        manifest=manifest,
        stale_after_seconds=172800,
        current_governed_configuration_hash="config-sha",
        observed_at=datetime(2026, 8, 11, tzinfo=UTC),
    )
    stale = data_source_diagnostics(
        context=context,
        manifest=manifest,
        stale_after_seconds=3600,
        current_governed_configuration_hash="config-sha",
        observed_at=datetime(2026, 8, 11, tzinfo=UTC),
    )
    assert current["active_mode"] == stale["active_mode"] == "OFFLINE_SNAPSHOT"
    assert current["diagnostic_status"] == "CURRENT"
    assert stale["diagnostic_status"] == "STALE"
    assert stale["snapshot"]["freshness_status"] == "STALE"
    assert stale["snapshot"]["age_seconds"] == 86400.0
    assert stale["provenance"] == {
        "dataset_hash": "dataset-sha",
        "dataset_hash_basis": "validated-and-mart-files",
        "configuration_hash": "config-sha",
        "current_governed_configuration_hash": "config-sha",
        "configuration_match": True,
        "run_id": "demo-run",
    }
    assert "request_history" not in json.dumps(stale).lower()

    unknown = data_source_diagnostics(
        context=context,
        manifest={**manifest, "completion_timestamp": "not-a-timestamp"},
        stale_after_seconds=3600,
        current_governed_configuration_hash="config-sha",
        observed_at=datetime(2026, 8, 11, tzinfo=UTC),
    )
    assert unknown["diagnostic_status"] == "UNKNOWN"
    assert unknown["snapshot"]["freshness_status"] == "UNKNOWN"
    assert unknown["snapshot"]["age_seconds"] is None
