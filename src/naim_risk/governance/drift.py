"""Population Stability Index and Jensen-Shannon drift diagnostics."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _distributions(
    baseline: pd.Series, current: pd.Series, bins: int = 10
) -> tuple[np.ndarray, np.ndarray]:
    if pd.api.types.is_numeric_dtype(baseline):
        edges = np.unique(np.nanquantile(baseline.astype(float), np.linspace(0, 1, bins + 1)))
        if len(edges) < 2:
            edges = np.array([-np.inf, np.inf])
        else:
            edges[0], edges[-1] = -np.inf, np.inf
        baseline_counts, _ = np.histogram(baseline.astype(float), bins=edges)
        current_counts, _ = np.histogram(current.astype(float), bins=edges)
    else:
        categories = sorted(set(baseline.dropna().astype(str)) | set(current.dropna().astype(str)))
        baseline_counts = (
            baseline.astype(str).value_counts().reindex(categories, fill_value=0).to_numpy()
        )
        current_counts = (
            current.astype(str).value_counts().reindex(categories, fill_value=0).to_numpy()
        )
    p = np.clip(baseline_counts / max(baseline_counts.sum(), 1), 1e-6, None)
    q = np.clip(current_counts / max(current_counts.sum(), 1), 1e-6, None)
    p /= p.sum()
    q /= q.sum()
    return p, q


def calculate_population_drift(
    performance: pd.DataFrame,
    master: pd.DataFrame,
    *,
    baseline_period: str | pd.Timestamp | None = None,
    current_period: str | pd.Timestamp | None = None,
) -> dict[str, Any]:
    frame = performance.merge(
        master[
            [
                "account_id",
                "product_type",
                "acquisition_channel",
                "customer_segment",
            ]
        ],
        on="account_id",
        how="left",
        validate="many_to_one",
    )
    frame["month"] = pd.to_datetime(frame["month"]).dt.to_period("M").dt.to_timestamp()
    months = pd.DatetimeIndex(sorted(frame["month"].unique()))
    current = (
        months.max()
        if current_period is None
        else pd.Timestamp(current_period).to_period("M").to_timestamp()
    )
    baseline = (
        months[max(0, len(months) - 7)]
        if baseline_period is None
        else pd.Timestamp(baseline_period).to_period("M").to_timestamp()
    )
    base = frame[frame["month"] == baseline]
    curr = frame[frame["month"] == current]
    features = [
        "risk_score",
        "utilization",
        "transaction_value",
        "acquisition_channel",
        "product_type",
        "customer_segment",
        "strategy_version",
    ]
    rows = []
    for feature in features:
        p, q = _distributions(base[feature], curr[feature])
        psi = float(np.sum((q - p) * np.log(q / p)))
        midpoint = 0.5 * (p + q)
        js = float(0.5 * np.sum(p * np.log(p / midpoint)) + 0.5 * np.sum(q * np.log(q / midpoint)))
        rows.append(
            {
                "feature": feature,
                "psi": psi,
                "jensen_shannon_distance": float(np.sqrt(max(js, 0))),
                "status": "high" if psi >= 0.25 else "watch" if psi >= 0.10 else "stable",
                "baseline_sample": int(len(base)),
                "current_sample": int(len(curr)),
            }
        )
    return {
        "baseline_period": str(baseline.date()),
        "current_period": str(current.date()),
        "features": rows,
        "thresholds": {"watch": 0.10, "high": 0.25},
        "limitations": "Population drift is not proof of performance or concept drift.",
    }
