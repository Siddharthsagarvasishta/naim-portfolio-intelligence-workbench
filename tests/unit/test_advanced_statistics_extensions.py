from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from naim_risk.advanced import (
    AdvancedStatisticsError,
    difference_in_differences,
    kaplan_meier,
    log_rank_test,
    propensity_weighted_comparison,
    run_behavioural_diagnostics,
    run_survival_analysis,
    validate_change_point_method,
)


def test_kaplan_meier_confidence_bands_and_log_rank():
    durations = [1, 2, 2, 3, 4, 4, 5, 6]
    events = [1, 1, 0, 1, 0, 1, 1, 0]
    result = kaplan_meier(durations, events)
    probabilities = [row["survival_probability"] for row in result["curve"]]
    assert probabilities == sorted(probabilities, reverse=True)
    assert all(
        0 <= row["confidence_lower"] <= row["survival_probability"] <= row["confidence_upper"] <= 1
        for row in result["curve"]
    )
    groups = ["A", "A", "A", "A", "B", "B", "B", "B"]
    test = log_rank_test(durations, events, groups)
    assert test["status"] == "implemented"
    assert 0 <= test["p_value"] <= 1


def test_survival_workflow_covers_attrition_and_first_delinquency():
    frame = pd.DataFrame(
        {
            "time_to_attrition": [3, 5, 4, 8, 6, 9, 10, 7],
            "attrition_event": [1, 0, 1, 1, 0, 1, 0, 1],
            "time_to_first_30_plus_delinquency": [2, 6, 4, 7, 5, 8, 9, 3],
            "delinquency_30_event": [1, 0, 1, 0, 1, 0, 0, 1],
            "segment": ["A", "A", "A", "A", "B", "B", "B", "B"],
        }
    )
    result = run_survival_analysis(frame, group_column="segment")
    assert set(result["outcomes"]) == {
        "time_to_attrition",
        "time_to_first_30_plus_delinquency",
    }
    assert result["outcomes"]["time_to_attrition"]["log_rank"]["status"] == "implemented"
    assert result["cox_proportional_hazards"]["status"] == "not_implemented"
    assert result["causal_status"] == "associational"


def test_change_point_required_challenge_suite_passes():
    validation = validate_change_point_method(seed=73421)
    assert validation["status"] == "passed"
    assert all(validation["checks"].values())
    assert validation["known_shift_position"] == [60]


def _behavioural_frame() -> pd.DataFrame:
    rng = np.random.default_rng(73421)
    rows = []
    for account in range(180):
        latent_risk = rng.normal()
        for month in range(18):
            utilisation = np.clip(0.45 + 0.15 * latent_risk + rng.normal(0, 0.12), 0, 1)
            probability = 1 / (
                1 + np.exp(-(-2.8 + 1.2 * latent_risk + 1.5 * utilisation + 0.04 * month))
            )
            rows.append(
                {
                    "account_id": account,
                    "month": pd.Timestamp("2023-01-01") + pd.DateOffset(months=month),
                    "utilisation": utilisation,
                    "balance": max(0, 1_000 + 400 * latent_risk + rng.normal(0, 300)),
                    "payment_ratio": np.clip(0.7 - 0.1 * latent_risk + rng.normal(0, 0.1), 0, 1),
                    "days_past_due": 30 if rng.random() < probability else 0,
                    "segment": "higher" if latent_risk > 0 else "lower",
                }
            )
    return pd.DataFrame(rows)


def test_live_behavioural_model_time_split_calibration_and_explanations():
    result = run_behavioural_diagnostics(_behavioural_frame(), segment_column="segment")
    assert result["status"] == "implemented"
    assert result["target"]["constructed_from_next_period"] is True
    assert result["splits"]["train_end"] < result["splits"]["validation_end"]
    assert 0.5 <= result["tree_model"]["test_metrics"]["roc_auc"] <= 1
    assert result["tree_model"]["test_metrics"]["brier_score"] >= 0
    assert len(result["tree_model"]["threshold_analysis_test"]) == 19
    assert result["leakage_test"]["status"] == "passed"
    assert result["governance"]["protected_attributes_used"] is False
    assert result["governance"]["causal_status"] == "predictive association only"
    assert result["contribution_diagnostics"]["local_synthetic_record"]["features"]
    if result["shap"]["status"] != "implemented":
        assert result["shap"]["status"] in {"dependency_unavailable", "execution_failed"}
        assert "not SHAP values" in result["contribution_diagnostics"]["limitation"]


def test_behavioural_model_rejects_protected_and_leaking_features():
    frame = _behavioural_frame()
    frame["race"] = 1
    with pytest.raises(AdvancedStatisticsError, match="Protected"):
        run_behavioural_diagnostics(frame, feature_columns=["utilisation", "race"])
    frame["future_outcome"] = 0
    with pytest.raises(AdvancedStatisticsError, match="leakage"):
        run_behavioural_diagnostics(frame, feature_columns=["utilisation", "future_outcome"])


def test_propensity_weighting_improves_balance_and_recovers_synthetic_effect():
    rng = np.random.default_rng(73421)
    observations = 1_200
    first = rng.normal(size=observations)
    second = rng.normal(size=observations)
    propensity = 1 / (1 + np.exp(-(-0.2 + 0.7 * first - 0.4 * second)))
    treatment = rng.binomial(1, propensity)
    outcome = 2 * treatment + 0.8 * first - 0.3 * second + rng.normal(size=observations)
    result = propensity_weighted_comparison(
        pd.DataFrame(
            {"treatment": treatment, "outcome": outcome, "first": first, "second": second}
        ),
        treatment_column="treatment",
        outcome_column="outcome",
        covariates=["first", "second"],
    )
    assert result["status"] == "implemented"
    assert result["weighted_outcome"]["difference"] == pytest.approx(2.0, abs=0.25)
    assert max(row["absolute_smd_after"] for row in result["balance"]) < 0.10
    assert result["diagnostic_decision"]["interpretable_with_assumptions"] is True
    assert "not a randomised result" in result["sensitivity_warning"]


def _did_frame(*, failed_pretrend: bool = False) -> pd.DataFrame:
    rng = np.random.default_rng(1)
    rows = []
    for entity in range(120):
        treated = int(entity < 60)
        baseline = rng.normal()
        for period in range(10):
            differential_pretrend = treated * 0.45 * period if failed_pretrend else 0
            effect = treated * 1.5 if period >= 6 else 0
            rows.append(
                {
                    "entity": entity,
                    "date": pd.Timestamp("2024-01-01") + pd.DateOffset(months=period),
                    "treated": treated,
                    "outcome": baseline
                    + 0.15 * period
                    + differential_pretrend
                    + effect
                    + rng.normal(0, 0.4),
                }
            )
    return pd.DataFrame(rows)


def test_difference_in_differences_passes_and_fails_closed_on_assumptions():
    result = difference_in_differences(
        _did_frame(),
        outcome_column="outcome",
        treatment_column="treated",
        time_column="date",
        policy_date="2024-07-01",
        cluster_column="entity",
        synthetic_policy_use_case=True,
    )
    assert result["status"] == "implemented"
    assert result["estimate"]["difference_in_differences"] == pytest.approx(1.5, abs=0.2)
    assert result["estimate"]["uncertainty"] == "cluster"
    assert result["parallel_trend_assessment"]["supported_at_5_percent"] is True
    assert result["placebo_test"]["supported_at_5_percent"] is True
    assert any(row["reference_period"] for row in result["event_study_plot_data"])
    failed = difference_in_differences(
        _did_frame(failed_pretrend=True),
        outcome_column="outcome",
        treatment_column="treated",
        time_column="date",
        policy_date="2024-07-01",
        cluster_column="entity",
        synthetic_policy_use_case=True,
    )
    assert failed["status"] == "not_interpretable"
    assert failed["interpretation"] == "not interpretable"
    with pytest.raises(AdvancedStatisticsError, match="synthetic"):
        difference_in_differences(
            _did_frame(),
            outcome_column="outcome",
            treatment_column="treated",
            time_column="date",
            policy_date="2024-07-01",
        )
