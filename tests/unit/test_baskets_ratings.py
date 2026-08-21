from __future__ import annotations

import pandas as pd
import pytest

from naim_risk.baskets import (
    combine_memberships,
    evaluate_expression,
    impact_preview,
    weighted_basket_summary,
)
from naim_risk.baskets.engine import UnsafeBasketExpression
from naim_risk.ratings import (
    calculate_rating,
    rate_memberships,
    rate_partners,
)


def test_basket_set_operations_are_deterministic():
    assert combine_memberships(["B", "A"], ["B", "C"], "union") == ["A", "B", "C"]
    assert combine_memberships(["B", "A"], ["B", "C"], "intersection") == ["B"]
    assert combine_memberships(["B", "A"], ["B", "C"], "subtract") == ["A"]


def test_service_basket_reproducibility_hash_is_canonical(service):
    first = service.combine_baskets(
        {
            "left_members": ["B", "A"],
            "right_members": ["C"],
            "operation": "union",
        }
    )
    second = service.combine_baskets(
        {
            "left_members": ["C"],
            "right_members": ["A", "B"],
            "operation": "union",
        }
    )

    assert first["members"] == second["members"] == ["A", "B", "C"]
    assert first["frozen_reproducibility_hash"] == second["frozen_reproducibility_hash"]
    assert len(first["frozen_reproducibility_hash"]) == 64


def test_safe_dynamic_basket_expression_and_code_rejection():
    frame = pd.DataFrame({"region": ["East", "West"], "score": [80, 40]})
    mask = evaluate_expression(frame, "region == 'East' and score >= 70")
    assert mask.tolist() == [True, False]
    with pytest.raises(UnsafeBasketExpression):
        evaluate_expression(frame, "__import__('os').system('echo unsafe')")


def test_weighted_basket_math_and_impact_preview():
    frame = pd.DataFrame(
        {
            "id": ["A", "B", "C"],
            "value": [10.0, 20.0, 40.0],
            "weight": [1.0, 2.0, 1.0],
        }
    )
    summary = weighted_basket_summary(
        frame,
        entity_id_column="id",
        members=["A", "B"],
        metric_columns=["value"],
        weight_column="weight",
    )
    assert summary["metrics"]["value"]["total"] == 30
    assert summary["metrics"]["value"]["weighted_average"] == pytest.approx(50 / 3)
    preview = impact_preview(
        frame,
        entity_id_column="id",
        original_members=["A", "B"],
        revised_members=["B", "C"],
        metric_columns=["value"],
    )
    assert preview["affected_entities"] == 2
    assert preview["metric_differences"]["value"] == 30


def test_rating_weights_reconcile_and_missing_data_is_explicit():
    methodology = {
        "quality": {"weight": 0.6, "direction": "higher"},
        "risk": {"weight": 0.4, "direction": "lower"},
    }
    thresholds = [
        {"minimum": 80, "grade": "Grade 1: Strong"},
        {"minimum": 0, "grade": "Grade 5: Critical"},
    ]
    result = calculate_rating(
        {"quality": 90, "risk": 20}, methodology, thresholds, methodology_version="1"
    )
    assert result["score"] == pytest.approx(86)
    assert result["grade"] == "Grade 1: Strong"
    missing = calculate_rating(
        {"quality": 90, "risk": None}, methodology, thresholds, methodology_version="1"
    )
    assert missing["score"] == 90
    with pytest.raises(ValueError):
        calculate_rating(
            {"quality": 90},
            {"quality": {"weight": 0.9, "direction": "higher"}},
            thresholds,
        )


def test_partner_rating_is_monotonic_for_risk_and_concentration(test_config):
    base = {
        "month": pd.Timestamp("2026-01-01"),
        "active_accounts": 100,
        "expected_profit": 100.0,
        "SLA_breach_count": 0,
    }
    risk_frame = pd.DataFrame(
        [
            {
                **base,
                "partner_id": "LOW-RISK",
                "credit_loss": 1.0,
                "confirmed_fraud_loss": 0.0,
                "transaction_value": 100.0,
            },
            {
                **base,
                "partner_id": "HIGH-RISK",
                "credit_loss": 20.0,
                "confirmed_fraud_loss": 0.0,
                "transaction_value": 100.0,
            },
        ]
    )
    risk_scores = {
        row["partner_id"]: row["score"] for row in rate_partners(risk_frame, test_config.ratings)
    }
    assert risk_scores["LOW-RISK"] > risk_scores["HIGH-RISK"]

    concentration_frame = pd.DataFrame(
        [
            {
                **base,
                "partner_id": "LOW-CONCENTRATION",
                "credit_loss": 1.0,
                "confirmed_fraud_loss": 0.0,
                "transaction_value": 100.0,
            },
            {
                **base,
                "partner_id": "HIGH-CONCENTRATION",
                "credit_loss": 1.0,
                "confirmed_fraud_loss": 0.0,
                "transaction_value": 1_000.0,
            },
        ]
    )
    concentration_scores = {
        row["partner_id"]: row["score"]
        for row in rate_partners(concentration_frame, test_config.ratings)
    }
    assert concentration_scores["LOW-CONCENTRATION"] > concentration_scores["HIGH-CONCENTRATION"]


def test_membership_rating_is_monotonic_for_risk(test_config):
    frame = pd.DataFrame(
        [
            {
                "membership_tier_id": "LOW-RISK",
                "expected_contribution": 100.0,
                "transaction_value": 1_000.0,
                "attrition_rate": 0.01,
                "credit_loss": 1.0,
                "fraud_loss": 0.0,
            },
            {
                "membership_tier_id": "HIGH-RISK",
                "expected_contribution": 100.0,
                "transaction_value": 1_000.0,
                "attrition_rate": 0.01,
                "credit_loss": 20.0,
                "fraud_loss": 0.0,
            },
        ]
    )
    scores = {
        row["membership_tier_id"]: row["score"]
        for row in rate_memberships(frame, test_config.ratings)
    }

    assert scores["LOW-RISK"] > scores["HIGH-RISK"]
