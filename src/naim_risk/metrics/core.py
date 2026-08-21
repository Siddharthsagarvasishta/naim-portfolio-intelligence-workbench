"""Single-source governed calculations for portfolio KPIs."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd

from naim_risk.common.math import safe_divide
from naim_risk.config import CORE_METRIC_IDS, metric_display_contract
from naim_risk.metrics.governance import governed_metric_fields

DIMENSION_COLUMNS = [
    "product_type",
    "acquisition_channel",
    "geography",
    "customer_segment",
    "original_risk_band",
    "origination_date",
    "partner_id",
    "vendor_id",
    "membership_tier_id",
]


def enrich_performance(performance: pd.DataFrame, master: pd.DataFrame) -> pd.DataFrame:
    """Join governed dimensions to account-month measures exactly once."""

    existing = [column for column in DIMENSION_COLUMNS if column in performance.columns]
    missing = [column for column in DIMENSION_COLUMNS if column not in existing]
    if not missing:
        result = performance.copy()
    else:
        result = performance.merge(
            master[["account_id", *missing]],
            on="account_id",
            how="left",
            validate="many_to_one",
        )
    result["month"] = pd.to_datetime(result["month"]).dt.to_period("M").dt.to_timestamp()
    return result


def apply_filters(frame: pd.DataFrame, filters: Mapping[str, Any] | None) -> pd.DataFrame:
    """Apply allowlisted exact-match filters; values may be scalar or collections."""

    if not filters:
        return frame
    result = frame
    allowed = set(DIMENSION_COLUMNS + ["strategy_version", "model_version", "months_on_book"])
    for column, value in filters.items():
        if column not in allowed or column not in result.columns or value is None:
            continue
        if isinstance(value, (list, tuple, set)):
            result = result[result[column].isin(list(value))]
        else:
            result = result[result[column] == value]
    return result


def _active_mask(frame: pd.DataFrame) -> pd.Series:
    return (frame["inactive_flag"] == 0) & (frame["chargeoff_flag"] == 0)


def _friction_mask(frame: pd.DataFrame) -> pd.Series:
    return (
        frame[
            [
                "manual_review_count",
                "declined_transaction_count",
                "step_up_authentication_count",
                "customer_contact_count",
            ]
        ].sum(axis=1)
        > 0
    ) & (frame["confirmed_fraud_event_count"] == 0)


def _profit_components(frame: pd.DataFrame, assumptions: Mapping[str, float]) -> dict[str, float]:
    average_receivables = float(frame["average_daily_balance"].sum())
    transaction_value = float(frame["transaction_value"].sum())
    active_accounts = int(_active_mask(frame).sum())
    manual_reviews = float(frame["manual_review_count"].sum())
    friction_events = float(
        frame[
            [
                "manual_review_count",
                "declined_transaction_count",
                "step_up_authentication_count",
                "customer_contact_count",
            ]
        ]
        .sum(axis=1)
        .sum()
    )
    net_credit_loss = float(frame["chargeoff_amount"].sum() - frame["recovery_amount"].sum())
    fraud_loss = float(frame["confirmed_fraud_loss"].sum())
    revenue = average_receivables * float(assumptions["revenue_rate"]) + transaction_value * float(
        assumptions["transaction_revenue_rate"]
    )
    funding_cost = average_receivables * float(assumptions["funding_cost_rate"])
    operating_cost = active_accounts * float(assumptions["operating_cost_per_active_account"])
    review_cost = manual_reviews * float(assumptions["review_cost_per_case"])
    friction_cost = friction_events * float(assumptions["customer_friction_cost_per_event"])
    expected_profit = (
        revenue
        - funding_cost
        - operating_cost
        - net_credit_loss
        - fraud_loss
        - review_cost
        - friction_cost
    )
    return {
        "revenue": revenue,
        "funding_cost": funding_cost,
        "operating_cost": operating_cost,
        "net_credit_loss": net_credit_loss,
        "confirmed_fraud_loss": fraud_loss,
        "manual_review_cost": review_cost,
        "customer_friction_cost": friction_cost,
        "expected_profit": expected_profit,
    }


def _raw_values(
    current: pd.DataFrame,
    previous: pd.DataFrame,
    assumptions: Mapping[str, float],
) -> dict[str, tuple[float | None, float]]:
    active_current = int(_active_mask(current).sum())
    active_previous = int(_active_mask(previous).sum())
    receivables = float(current["account_balance"].sum())
    average_receivables = float(current["average_daily_balance"].sum())
    total_limit = float(current.loc[current["credit_limit"] > 0, "credit_limit"].sum())
    active_eligible = current[_active_mask(current)]
    delinquent_accounts = int((active_eligible["days_past_due"] >= 30).sum())
    net_loss = float(current["chargeoff_amount"].sum() - current["recovery_amount"].sum())
    transaction_value = float(current["transaction_value"].sum())
    transaction_count = float(current["transaction_count"].sum())
    fraud_alerts = float(current["fraud_alert_count"].sum())
    active_transacting = int(
        current.loc[
            _active_mask(current) & (current["transaction_count"] > 0), "account_id"
        ].nunique()
    )
    friction_accounts = int(current.loc[_friction_mask(current), "account_id"].nunique())
    profit = _profit_components(current, assumptions)
    return {
        "ACTIVE_ACCOUNTS": (float(active_current), float(max(active_current, 1))),
        "ACCOUNT_GROWTH": (
            None
            if safe_divide(active_current, active_previous) is None
            else float(active_current / active_previous - 1.0),
            float(active_previous),
        ),
        "ENDING_RECEIVABLES": (receivables, float(active_current)),
        "TRANSACTION_VALUE": (transaction_value, float(active_transacting)),
        "UTILIZATION": (safe_divide(receivables, total_limit), total_limit),
        "DELINQUENCY_30_ACCOUNT_RATE": (
            safe_divide(delinquent_accounts, active_current),
            float(active_current),
        ),
        "ANNUALISED_NET_LOSS_RATE": (
            None
            if safe_divide(net_loss, average_receivables) is None
            else float(net_loss / average_receivables * 12.0),
            average_receivables,
        ),
        "FRAUD_BPS": (
            None
            if safe_divide(float(current["confirmed_fraud_loss"].sum()), transaction_value) is None
            else float(current["confirmed_fraud_loss"].sum() / transaction_value * 10_000.0),
            transaction_value,
        ),
        "FRAUD_ALERT_TRANSACTION_RATE": (
            safe_divide(fraud_alerts, transaction_count),
            transaction_count,
        ),
        "MANUAL_REVIEW_RATE": (
            safe_divide(float(current["manual_review_count"].sum()), transaction_count),
            transaction_count,
        ),
        "FALSE_POSITIVE_RATE": (
            safe_divide(float(current["false_positive_count"].sum()), fraud_alerts),
            fraud_alerts,
        ),
        "CUSTOMER_FRICTION_RATE": (
            safe_divide(friction_accounts, active_transacting),
            float(active_transacting),
        ),
        "COMPLAINT_RATE_PER_1000": (
            None
            if safe_divide(float(current["complaint_count"].sum()), active_current) is None
            else float(current["complaint_count"].sum() / active_current * 1000.0),
            float(active_current),
        ),
        "ATTRITION_RATE": (
            safe_divide(float(current["attrition_flag"].sum()), active_previous),
            float(active_previous),
        ),
        "EXPECTED_PROFIT": (profit["expected_profit"], float(active_current)),
    }


def calculate_period_kpis(
    performance: pd.DataFrame,
    master: pd.DataFrame,
    *,
    period: str | pd.Timestamp | None,
    assumptions: Mapping[str, float],
    metric_registry: Iterable[Mapping[str, Any]],
    filters: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Calculate current and prior KPI values at one consistent filter scope."""

    enriched = apply_filters(enrich_performance(performance, master), filters)
    available = pd.DatetimeIndex(sorted(enriched["month"].dropna().unique()))
    if available.empty:
        return []
    current_period = (
        available.max() if period is None else pd.Timestamp(period).to_period("M").to_timestamp()
    )
    prior_candidates = available[available < current_period]
    previous_period = prior_candidates.max() if len(prior_candidates) else current_period
    current = enriched[enriched["month"] == current_period]
    previous = enriched[enriched["month"] == previous_period]
    registry = {str(item["metric_id"]): dict(item) for item in metric_registry}
    current_values = _raw_values(current, previous, assumptions)
    if set(registry) != set(CORE_METRIC_IDS) or set(current_values) != set(CORE_METRIC_IDS):
        raise ValueError("Executable core KPIs and the governed metric registry are misaligned")
    earlier_candidates = available[available < previous_period]
    pre_previous = (
        enriched[enriched["month"] == earlier_candidates.max()]
        if len(earlier_candidates)
        else previous
    )
    prior_values = _raw_values(previous, pre_previous, assumptions)
    results = []
    for metric_id, (value, denominator) in current_values.items():
        prior_value = prior_values.get(metric_id, (None, 0.0))[0]
        absolute_change = (
            None if value is None or prior_value is None else float(value - prior_value)
        )
        relative_change = (
            None
            if absolute_change is None or prior_value in (None, 0)
            else float(absolute_change / abs(float(prior_value)))
        )
        metadata = registry[metric_id]
        display_contract = metric_display_contract(metadata)
        governed = governed_metric_fields(
            metadata,
            value=value,
            absolute_change=absolute_change,
            denominator=denominator,
        )
        guardrail_status = governed["guardrail"]["status"]
        status = {
            "ADVERSE": "adverse",
            "CRITICAL": "critical",
            "WATCH": "watch",
            "FAVOURABLE": "favourable",
            "INSUFFICIENT_DATA": "insufficient_data",
        }.get(guardrail_status, "neutral")
        results.append(
            {
                "metric_id": metric_id,
                "name": metadata.get("name", metric_id.replace("_", " ").title()),
                "value": value,
                "prior_value": prior_value,
                "absolute_change": absolute_change,
                "relative_change": relative_change,
                "unit": display_contract["unit"],
                "scale": display_contract["scale"],
                "scaling_factor": display_contract["scaling_factor"],
                "format_string": display_contract["format_string"],
                "numerator": metadata["numerator"],
                "denominator": denominator,
                "denominator_definition": metadata["denominator"],
                "status": status,
                "statistical_status": governed["statistical_assessment"]["status"],
                "definition": metadata["business_definition"],
                "metric_version": metadata["metric_version"],
                "calculation_version": metadata["transformation"]["calculation_version"],
                "reporting_period": str(current_period.date()),
                "comparison_period": str(previous_period.date()),
                **governed,
            }
        )
    return results


def calculate_trends(
    performance: pd.DataFrame,
    master: pd.DataFrame,
    *,
    assumptions: Mapping[str, float],
    metric_registry: Iterable[Mapping[str, Any]],
    filters: Mapping[str, Any] | None = None,
    through_period: str | pd.Timestamp | None = None,
) -> list[dict[str, Any]]:
    """Return long-form monthly trends using the exact KPI implementation."""

    enriched = apply_filters(enrich_performance(performance, master), filters)
    if through_period is not None:
        upper_bound = pd.Timestamp(through_period).to_period("M").to_timestamp()
        enriched = enriched[enriched["month"] <= upper_bound]
    months = sorted(pd.to_datetime(enriched["month"]).unique())
    rows: list[dict[str, Any]] = []
    for month in months:
        for metric in calculate_period_kpis(
            enriched,
            master,
            period=pd.Timestamp(month),
            assumptions=assumptions,
            metric_registry=metric_registry,
        ):
            rows.append(
                {
                    "month": str(pd.Timestamp(month).date()),
                    "metric_id": metric["metric_id"],
                    "value": metric["value"],
                    "unit": metric["unit"],
                    "denominator": metric["denominator"],
                }
            )
    return rows


def calculate_roll_rates(
    performance: pd.DataFrame,
    master: pd.DataFrame,
    *,
    period: str | pd.Timestamp | None = None,
    filters: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Calculate adjacent-period transitions on the same account population."""

    frame = apply_filters(enrich_performance(performance, master), filters)
    months = pd.DatetimeIndex(sorted(frame["month"].unique()))
    if len(months) < 2:
        return {"period": None, "comparison_period": None, "matrix": [], "population": 0}
    current_period = (
        months.max() if period is None else pd.Timestamp(period).to_period("M").to_timestamp()
    )
    prior = months[months < current_period]
    if prior.empty:
        return {
            "period": str(current_period.date()),
            "comparison_period": None,
            "matrix": [],
            "population": 0,
        }
    prior_period = prior.max()
    previous = frame[frame["month"] == prior_period][["account_id", "delinquency_status"]]
    current = frame[frame["month"] == current_period][["account_id", "delinquency_status"]]
    common = previous.merge(
        current, on="account_id", suffixes=("_from", "_to"), validate="one_to_one"
    )
    order = ["Current", "30-59", "60-89", "90+", "Charge-Off"]
    counts = pd.crosstab(common["delinquency_status_from"], common["delinquency_status_to"])
    rows = []
    for from_status in order:
        denominator = int(counts.loc[from_status].sum()) if from_status in counts.index else 0
        for to_status in order:
            count = (
                int(counts.loc[from_status, to_status])
                if from_status in counts.index and to_status in counts.columns
                else 0
            )
            rows.append(
                {
                    "from_status": from_status,
                    "to_status": to_status,
                    "count": count,
                    "rate": safe_divide(count, denominator),
                    "denominator": denominator,
                }
            )
    return {
        "period": str(current_period.date()),
        "comparison_period": str(prior_period.date()),
        "matrix": rows,
        "population": int(len(common)),
        "exclusions": "Accounts absent from either adjacent period",
    }
