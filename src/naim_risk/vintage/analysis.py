"""Vintage curves using original booked populations and maturity warnings."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

from naim_risk.common.math import wilson_interval
from naim_risk.metrics.core import apply_filters, enrich_performance


def calculate_vintages(
    performance: pd.DataFrame,
    master: pd.DataFrame,
    *,
    filters: Mapping[str, Any] | None = None,
    minimum_sample: int = 30,
    through_period: str | pd.Timestamp | None = None,
) -> list[dict[str, Any]]:
    """Calculate maturity-aligned monthly vintage outcomes."""

    frame = apply_filters(enrich_performance(performance, master), filters)
    if through_period is not None:
        cutoff = pd.Timestamp(through_period).to_period("M").to_timestamp()
        frame = frame[frame["month"] <= cutoff]
    frame["vintage"] = pd.to_datetime(frame["origination_date"]).dt.to_period("M").astype(str)
    cohort = master.copy()
    cohort["vintage"] = pd.to_datetime(cohort["origination_date"]).dt.to_period("M").astype(str)
    cohort_sizes = cohort.groupby("vintage")["account_id"].nunique()
    grouped = frame.groupby(["vintage", "months_on_book"], as_index=False).agg(
        observed_accounts=("account_id", "nunique"),
        delinquent_30_accounts=("days_past_due", lambda values: int((values >= 30).sum())),
        delinquent_90_accounts=("days_past_due", lambda values: int((values >= 90).sum())),
        net_credit_loss=("chargeoff_amount", lambda values: float(values.sum())),
        recoveries=("recovery_amount", "sum"),
        average_balance=("average_daily_balance", "sum"),
        fraud_loss=("confirmed_fraud_loss", "sum"),
        transaction_value=("transaction_value", "sum"),
        attritions=("attrition_flag", "sum"),
        ending_balance=("account_balance", "sum"),
    )
    grouped["net_credit_loss"] = grouped["net_credit_loss"] - grouped["recoveries"]
    grouped.sort_values(["vintage", "months_on_book"], inplace=True)
    grouped["cumulative_net_credit_loss"] = grouped.groupby("vintage")["net_credit_loss"].cumsum()
    grouped["cumulative_average_receivables"] = grouped.groupby("vintage")[
        "average_balance"
    ].cumsum()
    grouped["cumulative_fraud_loss"] = grouped.groupby("vintage")["fraud_loss"].cumsum()
    grouped["cumulative_transaction_value"] = grouped.groupby("vintage")[
        "transaction_value"
    ].cumsum()
    max_mob = int(grouped["months_on_book"].max()) if len(grouped) else 0
    output: list[dict[str, Any]] = []
    for row in grouped.itertuples(index=False):
        original_accounts = int(cohort_sizes.get(row.vintage, 0))
        lower, upper = wilson_interval(row.delinquent_30_accounts, row.observed_accounts)
        output.append(
            {
                "vintage": row.vintage,
                "months_on_book": int(row.months_on_book),
                "cohort_size": original_accounts,
                "observed_accounts": int(row.observed_accounts),
                "delinquency_30_rate": (
                    row.delinquent_30_accounts / row.observed_accounts
                    if row.observed_accounts
                    else None
                ),
                "delinquency_90_rate": (
                    row.delinquent_90_accounts / row.observed_accounts
                    if row.observed_accounts
                    else None
                ),
                "delinquency_30_ci_lower": lower,
                "delinquency_30_ci_upper": upper,
                "cumulative_net_loss_per_booked_account": (
                    row.cumulative_net_credit_loss / original_accounts
                    if original_accounts
                    else None
                ),
                "cumulative_net_credit_loss": float(row.cumulative_net_credit_loss),
                "cumulative_average_receivables": float(row.cumulative_average_receivables),
                "cumulative_net_loss_rate": (
                    row.cumulative_net_credit_loss / row.cumulative_average_receivables
                    if row.cumulative_average_receivables
                    else None
                ),
                "cumulative_net_loss_rate_unit": "ratio",
                "cumulative_net_loss_rate_denominator": (
                    "Sum of monthly average_daily_balance from MOB 0 through the "
                    "reported MOB for the same origination vintage."
                ),
                "cumulative_fraud_bps": (
                    row.cumulative_fraud_loss / row.cumulative_transaction_value * 10_000
                    if row.cumulative_transaction_value
                    else None
                ),
                "attrition_rate_on_original_book": (
                    row.attritions / original_accounts if original_accounts else None
                ),
                "ending_balance": float(row.ending_balance),
                "maturity_warning": int(row.months_on_book) > max_mob - 3,
                "minimum_sample_warning": int(row.observed_accounts) < minimum_sample,
                "denominator_definition": (
                    "Cumulative net loss rate uses cumulative average receivables; "
                    "per-booked-account outcomes use original booked accounts; "
                    "point-in-time delinquency uses remaining observed accounts."
                ),
            }
        )
    return output
