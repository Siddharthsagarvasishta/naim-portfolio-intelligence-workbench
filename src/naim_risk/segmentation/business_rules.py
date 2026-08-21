"""Configurable-style business-rule segmentation without protected attributes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from naim_risk.metrics.core import apply_filters, enrich_performance


def business_rule_segments(
    performance: pd.DataFrame,
    master: pd.DataFrame,
    *,
    filters: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    frame = apply_filters(enrich_performance(performance, master), filters)
    latest = frame[frame["month"] == frame["month"].max()].copy()
    friction = latest[
        [
            "manual_review_count",
            "declined_transaction_count",
            "step_up_authentication_count",
            "customer_contact_count",
        ]
    ].sum(axis=1)
    labels = np.select(
        [
            (latest["account_balance"] >= latest["account_balance"].quantile(0.70))
            & (latest["risk_score"] >= 680),
            (latest["account_balance"] >= latest["account_balance"].quantile(0.70))
            & (latest["risk_score"] < 620),
            (latest["utilization"] >= 0.75),
            (latest["fraud_alert_count"] > 0),
            (friction >= 2),
            (latest["months_on_book"] <= 6),
            (latest["transaction_count"] == 0),
        ],
        [
            "High Value, Low Risk",
            "High Value, Emerging Risk",
            "Revolving and High Utilization",
            "Fraud-Exposed",
            "Operationally Friction-Heavy",
            "New and Unseasoned",
            "Dormant or Attrition Risk",
        ],
        default="Low Activity, Stable",
    )
    latest["business_segment"] = labels
    latest["_loss"] = latest["chargeoff_amount"] - latest["recovery_amount"]
    latest["_friction"] = (friction > 0).astype(int)
    grouped = latest.groupby("business_segment", as_index=False).agg(
        accounts=("account_id", "nunique"),
        balances=("account_balance", "sum"),
        transaction_value=("transaction_value", "sum"),
        average_utilization=("utilization", "mean"),
        average_risk_score=("risk_score", "mean"),
        fraud_loss=("confirmed_fraud_loss", "sum"),
        net_credit_loss=("_loss", "sum"),
        friction_accounts=("_friction", "sum"),
        attritions=("attrition_flag", "sum"),
    )
    total_accounts = int(grouped["accounts"].sum())
    return [
        {
            **row._asdict(),
            "share_of_accounts": row.accounts / total_accounts if total_accounts else None,
            "method": "Approved business-rule segmentation",
            "causal_status": "DESCRIPTIVE",
        }
        for row in grouped.itertuples(index=False)
    ]
