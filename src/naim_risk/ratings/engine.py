"""Configurable 0–100 rating methodologies with exposed weights and grades."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd


def _grade(score: float, thresholds: list[Mapping[str, Any]]) -> str:
    for item in sorted(thresholds, key=lambda value: float(value["minimum"]), reverse=True):
        if score >= float(item["minimum"]):
            return str(item["grade"])
    return "Grade 5: Critical"


def calculate_rating(
    components: Mapping[str, float | None],
    methodology: Mapping[str, Mapping[str, Any]],
    grade_thresholds: list[Mapping[str, Any]],
    *,
    methodology_version: str = "1.0.0",
) -> dict[str, Any]:
    """Calculate a transparent rating, reweighting only over present components."""

    configured_weight = sum(float(item["weight"]) for item in methodology.values())
    if abs(configured_weight - 1.0) > 1e-9:
        raise ValueError("Rating component weights must reconcile to 1.0")
    available = {
        name: value
        for name, value in components.items()
        if name in methodology and value is not None and np.isfinite(float(value))
    }
    available_weight = sum(float(methodology[name]["weight"]) for name in available)
    if available_weight <= 0:
        return {
            "score": None,
            "grade": None,
            "confidence": "Insufficient data",
            "methodology_version": methodology_version,
            "components": [],
        }
    rows = []
    total = 0.0
    for name, raw_value in available.items():
        spec = methodology[name]
        normalised = float(np.clip(float(raw_value), 0.0, 100.0))
        directional = 100.0 - normalised if spec["direction"] == "lower" else normalised
        effective_weight = float(spec["weight"]) / available_weight
        contribution = directional * effective_weight
        total += contribution
        rows.append(
            {
                "component": name,
                "raw_score": float(raw_value),
                "direction": spec["direction"],
                "normalised_score": directional,
                "configured_weight": float(spec["weight"]),
                "effective_weight": effective_weight,
                "contribution": contribution,
            }
        )
    return {
        "score": float(total),
        "grade": _grade(total, grade_thresholds),
        "confidence": "High" if available_weight >= 0.9 else "Medium",
        "missing_data_treatment": "Weights re-normalised over present approved components",
        "methodology_version": methodology_version,
        "components": rows,
    }


def _percentile_score(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    score = series.rank(pct=True, method="average") * 100.0
    return score if higher_is_better else 100.0 - score


def rate_partners(
    performance: pd.DataFrame,
    methodology_config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    latest = performance[performance["month"] == performance["month"].max()].copy()
    latest["growth_score"] = _percentile_score(latest["active_accounts"])
    latest["profit_score"] = _percentile_score(latest["expected_profit"])
    latest["quality_score"] = _percentile_score(-latest["SLA_breach_count"])
    latest["risk_score"] = _percentile_score(latest["credit_loss"] + latest["confirmed_fraud_loss"])
    latest["concentration_score"] = _percentile_score(latest["transaction_value"])
    rows = []
    for row in latest.itertuples(index=False):
        rating = calculate_rating(
            {
                "growth_score": row.growth_score,
                "profit_score": row.profit_score,
                "quality_score": row.quality_score,
                "risk_score": row.risk_score,
                "concentration_score": row.concentration_score,
            },
            methodology_config["partner"],
            methodology_config["grade_thresholds"],
            methodology_version=str(methodology_config["methodology_version"]),
        )
        rows.append({"partner_id": row.partner_id, **rating})
    return rows


def rate_vendors(
    performance: pd.DataFrame,
    methodology_config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    latest = performance[performance["month"] == performance["month"].max()].copy()
    latest["sla_score"] = np.clip(100 - latest["SLA_breach_count"] * 30, 0, 100)
    latest["capacity_score"] = np.clip(
        100 - np.maximum(latest["capacity_utilisation"] - 0.75, 0) * 220, 0, 100
    )
    latest["cost_score"] = _percentile_score(latest["unit_cost"])
    rows = []
    for row in latest.itertuples(index=False):
        rating = calculate_rating(
            {
                "quality_score": row.quality_score,
                "sla_score": row.sla_score,
                "capacity_score": row.capacity_score,
                "cost_score": row.cost_score,
                "risk_score": row.risk_score,
            },
            methodology_config["vendor"],
            methodology_config["grade_thresholds"],
            methodology_version=str(methodology_config["methodology_version"]),
        )
        rows.append({"vendor_id": row.vendor_id, **rating})
    return rows


def rate_memberships(
    membership_performance: pd.DataFrame,
    methodology_config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    frame = membership_performance.copy()
    frame["profit_score"] = _percentile_score(frame["expected_contribution"])
    frame["engagement_score"] = _percentile_score(frame["transaction_value"])
    frame["retention_score"] = np.clip(100 - frame["attrition_rate"] * 1000, 0, 100)
    frame["risk_score"] = _percentile_score(frame["credit_loss"] + frame["fraud_loss"])
    rows = []
    for row in frame.itertuples(index=False):
        rating = calculate_rating(
            {
                "profit_score": row.profit_score,
                "engagement_score": row.engagement_score,
                "retention_score": row.retention_score,
                "risk_score": row.risk_score,
            },
            methodology_config["membership"],
            methodology_config["grade_thresholds"],
            methodology_version=str(methodology_config["methodology_version"]),
        )
        rows.append({"membership_tier_id": row.membership_tier_id, **rating})
    return rows
