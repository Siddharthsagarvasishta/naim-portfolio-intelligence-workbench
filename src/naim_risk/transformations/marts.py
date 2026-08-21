"""Star-schema and query-efficient mart construction."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _dimension(values: pd.Series, key_name: str, label_name: str) -> pd.DataFrame:
    unique = pd.Series(values.dropna().unique()).sort_values().reset_index(drop=True)
    return pd.DataFrame({key_name: np.arange(1, len(unique) + 1), label_name: unique})


def build_marts(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Create a compact governed star schema and aggregate marts."""

    master = tables["customer_account_master"].copy()
    performance = tables["monthly_account_performance"].copy()
    dates = pd.DatetimeIndex(sorted(pd.to_datetime(performance["month"]).unique()))
    dim_date = pd.DataFrame(
        {
            "date_key": [int(value.strftime("%Y%m")) for value in dates],
            "month": dates,
            "year": dates.year,
            "quarter": dates.quarter,
            "month_number": dates.month,
            "month_name": dates.month_name(),
            "is_latest_month": dates == dates.max(),
        }
    )
    dim_account = master.copy().reset_index(drop=True)
    dim_account.insert(0, "account_key", np.arange(1, len(dim_account) + 1))
    dimensions = {
        "DimProduct": _dimension(master["product_type"], "product_key", "product_type"),
        "DimAcquisitionChannel": _dimension(
            master["acquisition_channel"], "acquisition_channel_key", "acquisition_channel"
        ),
        "DimGeography": _dimension(master["geography"], "geography_key", "geography"),
        "DimCustomerSegment": _dimension(
            master["customer_segment"], "customer_segment_key", "customer_segment"
        ),
        "DimRiskBand": _dimension(
            master["original_risk_band"], "risk_band_key", "original_risk_band"
        ),
        "DimStrategy": _dimension(
            performance["strategy_version"], "strategy_key", "strategy_version"
        ),
        "DimModelVersion": _dimension(
            performance["model_version"], "model_version_key", "model_version"
        ),
    }
    fact = performance.merge(
        dim_account[
            [
                "account_key",
                "account_id",
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
        ],
        on="account_id",
        how="left",
        validate="many_to_one",
    )
    fact["date_key"] = pd.to_datetime(fact["month"]).dt.strftime("%Y%m").astype(int)
    for dim_name, _key, label in [
        ("DimProduct", "product_key", "product_type"),
        ("DimAcquisitionChannel", "acquisition_channel_key", "acquisition_channel"),
        ("DimGeography", "geography_key", "geography"),
        ("DimCustomerSegment", "customer_segment_key", "customer_segment"),
        ("DimRiskBand", "risk_band_key", "original_risk_band"),
        ("DimStrategy", "strategy_key", "strategy_version"),
        ("DimModelVersion", "model_version_key", "model_version"),
    ]:
        fact = fact.merge(dimensions[dim_name], on=label, how="left", validate="many_to_one")
    fact.insert(0, "account_month_key", np.arange(1, len(fact) + 1))
    fact["_active"] = ((fact["inactive_flag"] == 0) & (fact["chargeoff_flag"] == 0)).astype(int)
    fact["_delinquent_30"] = ((fact["days_past_due"] >= 30) & (fact["chargeoff_flag"] == 0)).astype(
        int
    )
    fact["_friction_account"] = (
        fact[
            [
                "manual_review_count",
                "declined_transaction_count",
                "step_up_authentication_count",
                "customer_contact_count",
            ]
        ].sum(axis=1)
        > 0
    ).astype(int)
    portfolio_month = fact.groupby("month", as_index=False).agg(
        active_accounts=("_active", "sum"),
        ending_receivables=("account_balance", "sum"),
        average_receivables=("average_daily_balance", "sum"),
        credit_limit=("credit_limit", "sum"),
        transaction_value=("transaction_value", "sum"),
        transaction_count=("transaction_count", "sum"),
        delinquent_30_accounts=("_delinquent_30", "sum"),
        chargeoff_amount=("chargeoff_amount", "sum"),
        recovery_amount=("recovery_amount", "sum"),
        confirmed_fraud_loss=("confirmed_fraud_loss", "sum"),
        fraud_alert_count=("fraud_alert_count", "sum"),
        manual_review_count=("manual_review_count", "sum"),
        false_positive_count=("false_positive_count", "sum"),
        friction_accounts=("_friction_account", "sum"),
        complaints=("complaint_count", "sum"),
        attritions=("attrition_flag", "sum"),
    )
    segment_month = fact.groupby(
        [
            "month",
            "product_type",
            "acquisition_channel",
            "geography",
            "customer_segment",
            "original_risk_band",
            "strategy_version",
        ],
        as_index=False,
    ).agg(
        accounts=("account_id", "nunique"),
        active_accounts=("_active", "sum"),
        balance=("account_balance", "sum"),
        average_receivables=("average_daily_balance", "sum"),
        transaction_value=("transaction_value", "sum"),
        chargeoff_amount=("chargeoff_amount", "sum"),
        recovery_amount=("recovery_amount", "sum"),
        fraud_loss=("confirmed_fraud_loss", "sum"),
        reviews=("manual_review_count", "sum"),
        false_positives=("false_positive_count", "sum"),
        fraud_alerts=("fraud_alert_count", "sum"),
        friction_accounts=("_friction_account", "sum"),
    )
    strategy_fact = tables["strategy_decision_fact"].copy()
    strategy_fact.insert(0, "strategy_decision_key", np.arange(1, len(strategy_fact) + 1))
    marts: dict[str, pd.DataFrame] = {
        "DimDate": dim_date,
        "DimAccount": dim_account,
        **dimensions,
        "FactAccountMonth": fact.drop(columns=["_active", "_delinquent_30", "_friction_account"]),
        "FactStrategyDecision": strategy_fact,
        "MartPortfolioMonth": portfolio_month,
        "MartSegmentMonth": segment_month,
    }
    if "economic_scenario_assumptions" in tables:
        scenario = tables["economic_scenario_assumptions"].copy()
        scenario.insert(0, "scenario_key", pd.factorize(scenario["scenario_name"])[0] + 1)
        marts["DimScenario"] = scenario.drop_duplicates("scenario_name")[
            ["scenario_key", "scenario_name", "assumption_type"]
        ]
    if "alert_configuration" in tables:
        alerts = tables["alert_configuration"].copy()
        alerts.insert(0, "alert_rule_key", np.arange(1, len(alerts) + 1))
        marts["DimAlertRule"] = alerts
    return marts
