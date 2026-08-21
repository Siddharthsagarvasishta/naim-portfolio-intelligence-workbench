"""Symmetric mix-versus-performance decomposition with exact reconciliation."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import numpy as np
import pandas as pd

from naim_risk.metrics.core import apply_filters, enrich_performance


def decompose_rate(
    baseline: pd.DataFrame,
    current: pd.DataFrame,
    *,
    segment_column: str,
    numerator_column: str,
    denominator_column: str,
    scale: float = 1.0,
) -> dict[str, Any]:
    """Decompose a rate change using a symmetric, exactly reconciling formula."""

    base = baseline.groupby(segment_column, dropna=False).agg(
        numerator=(numerator_column, "sum"), denominator=(denominator_column, "sum")
    )
    curr = current.groupby(segment_column, dropna=False).agg(
        numerator=(numerator_column, "sum"), denominator=(denominator_column, "sum")
    )
    combined = base.join(curr, how="outer", lsuffix="_0", rsuffix="_1").fillna(0.0)
    total_denom_0 = float(combined["denominator_0"].sum())
    total_denom_1 = float(combined["denominator_1"].sum())
    combined["w0"] = combined["denominator_0"] / total_denom_0 if total_denom_0 else 0.0
    combined["w1"] = combined["denominator_1"] / total_denom_1 if total_denom_1 else 0.0
    combined["r0"] = np.divide(
        combined["numerator_0"],
        combined["denominator_0"],
        out=np.zeros(len(combined), dtype=float),
        where=combined["denominator_0"].to_numpy() != 0,
    )
    combined["r1"] = np.divide(
        combined["numerator_1"],
        combined["denominator_1"],
        out=np.zeros(len(combined), dtype=float),
        where=combined["denominator_1"].to_numpy() != 0,
    )
    combined["mix"] = 0.5 * (combined["w1"] - combined["w0"]) * (combined["r0"] + combined["r1"])
    combined["performance"] = (
        0.5 * (combined["r1"] - combined["r0"]) * (combined["w0"] + combined["w1"])
    )
    combined["total"] = combined["mix"] + combined["performance"]
    rate_0 = float(combined["numerator_0"].sum() / total_denom_0) if total_denom_0 else 0.0
    rate_1 = float(combined["numerator_1"].sum() / total_denom_1) if total_denom_1 else 0.0
    observed = rate_1 - rate_0
    reconciled = float(combined["total"].sum())
    rows = []
    for segment, row in combined.iterrows():
        rows.append(
            {
                "dimension": segment_column,
                "segment": str(segment),
                "baseline_weight": float(row["w0"]),
                "current_weight": float(row["w1"]),
                "baseline_rate": float(row["r0"]),
                "current_rate": float(row["r1"]),
                "mix_contribution": float(row["mix"] * scale),
                "within_segment_contribution": float(row["performance"] * scale),
                "total_contribution": float(row["total"] * scale),
                "baseline_denominator": float(row["denominator_0"]),
                "current_denominator": float(row["denominator_1"]),
            }
        )
    rows.sort(key=lambda item: abs(item["total_contribution"]), reverse=True)
    return {
        "dimension": segment_column,
        "baseline_rate": rate_0,
        "current_rate": rate_1,
        "observed_change": observed * scale,
        "mix_contribution": float(combined["mix"].sum() * scale),
        "within_segment_contribution": float(combined["performance"].sum() * scale),
        "reconciled_change": reconciled * scale,
        "reconciliation_residual": (observed - reconciled) * scale,
        "segments": rows,
    }


def root_cause_finding(
    performance: pd.DataFrame,
    master: pd.DataFrame,
    *,
    period: str | pd.Timestamp | None = None,
    filters: Mapping[str, Any] | None = None,
    quality_status: str = "PASS",
    dimensions: Iterable[str] = (
        "product_type",
        "acquisition_channel",
        "customer_segment",
        "geography",
        "original_risk_band",
        "strategy_version",
    ),
) -> dict[str, Any]:
    """Create a structured, associational loss-rate root-cause finding."""

    frame = apply_filters(enrich_performance(performance, master), filters)
    months = pd.DatetimeIndex(sorted(frame["month"].unique()))
    if len(months) < 2:
        return {"finding": None, "lenses": []}
    current_period = (
        months.max() if period is None else pd.Timestamp(period).to_period("M").to_timestamp()
    )
    frame = frame[frame["month"] <= current_period]
    months = pd.DatetimeIndex(sorted(frame["month"].unique()))
    if len(months) < 2 or current_period not in months:
        return {"finding": None, "lenses": []}
    prior = months[months < current_period]
    if prior.empty:
        return {"finding": None, "lenses": []}
    baseline_period = prior.max()
    selected = frame[frame["month"].isin([baseline_period, current_period])].copy()
    selected["_net_loss"] = selected["chargeoff_amount"] - selected["recovery_amount"]
    selected["_average_receivables"] = selected["average_daily_balance"]
    baseline = selected[selected["month"] == baseline_period]
    current = selected[selected["month"] == current_period]
    lenses = []
    for dimension in dimensions:
        if dimension in selected.columns:
            lenses.append(
                decompose_rate(
                    baseline,
                    current,
                    segment_column=dimension,
                    numerator_column="_net_loss",
                    denominator_column="_average_receivables",
                    scale=120_000.0,
                )
            )
    if not lenses:
        return {"finding": None, "lenses": []}
    primary_lens = max(
        lenses,
        key=lambda item: abs(item["segments"][0]["total_contribution"]) if item["segments"] else 0,
    )
    primary_segment = primary_lens["segments"][0] if primary_lens["segments"] else {}
    observed = primary_lens["observed_change"]
    contribution = float(primary_segment.get("total_contribution", 0.0))
    finding = {
        "metric_id": "ANNUALISED_NET_LOSS_RATE",
        "comparison_period": f"{current_period:%Y-%m} versus {baseline_period:%Y-%m}",
        "observed_change_bps": observed,
        "data_quality_status": quality_status,
        "primary_dimension": primary_lens["dimension"],
        "primary_driver": primary_segment.get("segment"),
        "contribution_share": (abs(contribution / observed) if abs(observed) > 1e-12 else None),
        "mix_contribution_bps": primary_lens["mix_contribution"],
        "within_segment_contribution_bps": primary_lens["within_segment_contribution"],
        "reconciliation_residual_bps": primary_lens["reconciliation_residual"],
        "supporting_drivers": [
            "acquisition mix",
            "utilization and payment behaviour",
            "months-on-book performance",
            "strategy review intensity",
        ],
        "causal_status": "ASSOCIATIONAL",
        "recommended_investigation": [
            "review acquisition quality and maturity-aligned vintages",
            "review Challenger B eligibility and operational guardrails",
            "inspect payment behaviour and utilization for the concentrated segment",
        ],
    }
    return {"finding": finding, "lenses": lenses}
