from __future__ import annotations

import pytest

from naim_risk.alerts import generate_alerts
from naim_risk.commentary import CommentaryEvidence, MockCommentaryProvider


def _evidence():
    return CommentaryEvidence(
        reporting_period="2025-08-01",
        comparison_period="2025-07-01",
        metric_values={"LOSS": 0.05},
        validated_movements={"LOSS": 0.01},
        root_cause_contributions={"contribution_share": 0.45},
        alert_status=[],
        statistical_confidence={"LOSS": "minimum sample met"},
        caveats=["Synthetic"],
        recommended_investigation_steps=["Inspect vintage"],
        data_quality_status="PASS",
    )


def test_commentary_verifier_accepts_supported_and_rejects_invented_numbers():
    supported = MockCommentaryProvider("Loss was 5.0% with a 1.0% movement.").generate(_evidence())
    assert supported.verification_status == "PASS"
    unsupported = MockCommentaryProvider("Loss was 77.7%.").generate(_evidence())
    assert unsupported.verification_status == "REJECTED"
    assert unsupported.unsupported_numbers == [77.7]


def test_alert_engine_applies_threshold_and_minimum_denominator():
    trends = [
        {"month": "2025-01-01", "metric_id": "LOSS", "value": 0.04, "denominator": 1000},
        {"month": "2025-02-01", "metric_id": "LOSS", "value": 0.08, "denominator": 1000},
    ]
    rules = [
        {
            "alert_rule_id": "R1",
            "metric_id": "LOSS",
            "alert_name": "Loss guardrail",
            "comparison_method": "absolute_threshold",
            "absolute_threshold": 0.07,
            "minimum_denominator": 100,
            "consecutive_periods": 1,
            "severity": "High",
            "cooldown_period": 1,
            "owner_role": "Risk",
            "recommended_investigation": "Investigate",
        }
    ]
    alerts = generate_alerts(trends, rules, quality_status="PASS")
    assert len(alerts) == 1
    assert alerts[0]["current_value"] == 0.08


def test_persistent_alert_enforces_relative_threshold_each_period():
    rule = {
        "alert_rule_id": "PERSIST",
        "metric_id": "DELINQ",
        "alert_name": "Persistent delinquency",
        "comparison_method": "persistent_increase",
        "relative_threshold": 5,
        "minimum_denominator": 100,
        "consecutive_periods": 2,
        "severity": "High",
        "cooldown_period": 1,
        "owner_role": "Risk",
        "recommended_investigation": "Investigate",
    }
    small_increases = [
        {"month": "2025-01-01", "metric_id": "DELINQ", "value": 0.040, "denominator": 1000},
        {"month": "2025-02-01", "metric_id": "DELINQ", "value": 0.041, "denominator": 1000},
        {"month": "2025-03-01", "metric_id": "DELINQ", "value": 0.042, "denominator": 1000},
    ]
    material_increases = [
        {"month": "2025-01-01", "metric_id": "DELINQ", "value": 0.040, "denominator": 1000},
        {"month": "2025-02-01", "metric_id": "DELINQ", "value": 0.043, "denominator": 1000},
        {"month": "2025-03-01", "metric_id": "DELINQ", "value": 0.046, "denominator": 1000},
    ]

    assert generate_alerts(small_increases, [rule], quality_status="PASS") == []
    assert len(generate_alerts(material_increases, [rule], quality_status="PASS")) == 1


def test_scenario_exposes_assumptions_and_is_deterministic(service):
    first = service.scenario_run({"scenario_name": "Mild Downturn", "horizon_months": 4})
    second = service.scenario_run({"scenario_name": "Mild Downturn", "horizon_months": 4})
    assert first == second
    assert len(first["projections"]) == 4
    assert "elasticities" in first
    assert "scenario estimate" in first["notice"].lower()


def test_scenario_catalogue_contains_live_projection_summaries(service):
    first = service.scenarios()
    second = service.scenarios()
    rows = first["data"]

    assert first == second
    assert {row["scenario_name"] for row in rows} == {
        "Baseline",
        "Mild Downturn",
        "Severe Downturn",
        "Fraud Shock",
    }
    assert all(len(row["projections"]) == 12 for row in rows)
    assert all(row["cumulative_loss"] >= 0 for row in rows)
    assert all(row["cumulative_fraud"] >= 0 for row in rows)
    baseline = next(row for row in rows if row["scenario_name"] == "Baseline")
    assert baseline["delta_from_baseline"] == 0
    for row in rows:
        assert row["delta_from_baseline"] == pytest.approx(
            row["expected_profit"] - baseline["expected_profit"]
        )
        assert row["cumulative_loss"] == pytest.approx(row["summary"]["cumulative_net_credit_loss"])
    assert first["units"]["projection_rates"] == "ratio"
