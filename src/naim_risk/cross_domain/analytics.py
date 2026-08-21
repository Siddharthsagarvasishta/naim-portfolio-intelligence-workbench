"""Live cross-domain calculations on canonical generated tables."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from naim_risk.common.math import gini, hhi, safe_divide


def partner_analytics(
    partner_performance: pd.DataFrame,
    partner_master: pd.DataFrame,
    partner_contract: pd.DataFrame,
) -> dict[str, Any]:
    latest = partner_performance[
        partner_performance["month"] == partner_performance["month"].max()
    ].copy()
    latest = latest.merge(partner_master, on="partner_id", how="left", validate="many_to_one")
    latest = latest.merge(
        partner_contract[
            ["partner_id", "contract_version", "fraud_loss_share", "benefit_cost_share"]
        ],
        on="partner_id",
        how="left",
        validate="many_to_one",
    )
    latest["partner_contribution"] = (
        latest["partner_revenue"]
        + latest["rebate_value"]
        - latest["partner_fee"]
        - latest["benefit_cost"] * (1 - latest["benefit_cost_share"])
        - latest["credit_loss"]
        - latest["confirmed_fraud_loss"] * (1 - latest["fraud_loss_share"])
        - latest["servicing_cost"]
    )
    latest["fraud_bps"] = np.divide(
        latest["confirmed_fraud_loss"] * 10_000,
        latest["transaction_value"],
        out=np.zeros(len(latest)),
        where=latest["transaction_value"].to_numpy() != 0,
    )
    latest["complaint_rate_per_1000"] = np.divide(
        latest["complaints"] * 1000,
        latest["active_accounts"],
        out=np.zeros(len(latest)),
        where=latest["active_accounts"].to_numpy() != 0,
    )
    total_transaction = float(latest["transaction_value"].sum())
    return {
        "data": latest.replace({np.nan: None}).to_dict(orient="records"),
        "summary": {
            "active_partners": int(latest["partner_id"].nunique()),
            "transaction_value": total_transaction,
            "partner_contribution": float(latest["partner_contribution"].sum()),
            "transaction_concentration_hhi": hhi(latest["transaction_value"]),
            "top_partner_dependency": (
                float(latest["transaction_value"].max() / total_transaction)
                if total_transaction
                else None
            ),
        },
    }


def vendor_analytics(
    vendor_performance: pd.DataFrame,
    vendor_master: pd.DataFrame,
    vendor_contract: pd.DataFrame,
) -> dict[str, Any]:
    latest = vendor_performance[
        vendor_performance["month"] == vendor_performance["month"].max()
    ].copy()
    latest = latest.merge(vendor_master, on="vendor_id", how="left", validate="many_to_one")
    latest = latest.merge(
        vendor_contract[["vendor_id", "contract_version", "maximum_capacity", "switching_cost"]],
        on="vendor_id",
        how="left",
        validate="many_to_one",
    )
    latest["contract_capacity_utilisation"] = np.divide(
        latest["cases_received"],
        latest["maximum_capacity"],
        out=np.zeros(len(latest)),
        where=latest["maximum_capacity"].to_numpy() != 0,
    )
    latest["sla_rate"] = 1.0 - np.divide(
        latest["SLA_breach_count"],
        np.maximum(latest["cases_received"], 1),
    )
    latest["exit_readiness_score"] = np.clip(
        100
        - latest["switching_cost"] / 2500
        - latest["criticality_tier"] * 8
        - latest["fourth_party_dependency_flag"] * 12
        + (1 - latest["contract_capacity_utilisation"].clip(0, 1)) * 20,
        0,
        100,
    )
    total_volume = float(latest["process_volume"].sum())
    return {
        "data": latest.replace({np.nan: None}).to_dict(orient="records"),
        "summary": {
            "active_vendors": int(latest["vendor_id"].nunique()),
            "critical_vendors": int((latest["criticality_tier"] == 1).sum()),
            "total_process_volume": total_volume,
            "total_vendor_cost": float(latest["total_vendor_cost"].sum()),
            "volume_concentration_hhi": hhi(latest["process_volume"]),
            "weighted_capacity_utilisation": (
                float(
                    np.average(
                        latest["contract_capacity_utilisation"],
                        weights=np.maximum(latest["process_volume"], 1),
                    )
                )
                if len(latest)
                else None
            ),
        },
    }


def membership_analytics(
    performance: pd.DataFrame,
    master: pd.DataFrame,
    membership_master: pd.DataFrame,
    benefit_usage: pd.DataFrame,
) -> dict[str, Any]:
    joined = performance.merge(
        master[["account_id", "membership_tier_id"]],
        on="account_id",
        how="left",
        validate="many_to_one",
    )
    latest = joined[joined["month"] == joined["month"].max()].copy()
    latest["_active"] = ((latest["inactive_flag"] == 0) & (latest["chargeoff_flag"] == 0)).astype(
        int
    )
    latest["_loss"] = latest["chargeoff_amount"] - latest["recovery_amount"]
    grouped = latest.groupby("membership_tier_id", as_index=False).agg(
        active_members=("_active", "sum"),
        transaction_value=("transaction_value", "sum"),
        balance=("account_balance", "sum"),
        credit_loss=("_loss", "sum"),
        fraud_loss=("confirmed_fraud_loss", "sum"),
        complaints=("complaint_count", "sum"),
        attritions=("attrition_flag", "sum"),
    )
    benefit = (
        benefit_usage.groupby("membership_tier_id", as_index=False).agg(
            benefit_users=("account_id", "nunique"),
            benefit_usage_count=("usage_count", "sum"),
            benefit_cost=("recognised_cost", "sum"),
            partner_funded_value=("partner_funded_value", "sum"),
        )
        if len(benefit_usage)
        else pd.DataFrame(
            columns=[
                "membership_tier_id",
                "benefit_users",
                "benefit_usage_count",
                "benefit_cost",
                "partner_funded_value",
            ]
        )
    )
    grouped = grouped.merge(benefit, on="membership_tier_id", how="left").fillna(0)
    grouped = grouped.merge(
        membership_master[["membership_tier_id", "membership_tier_name", "annual_fee"]],
        on="membership_tier_id",
        how="left",
        validate="many_to_one",
    )
    grouped["annual_fee_revenue"] = grouped["active_members"] * grouped["annual_fee"] / 12.0
    grouped["attrition_rate"] = np.divide(
        grouped["attritions"],
        grouped["active_members"].clip(lower=1),
    )
    grouped["benefit_utilisation"] = np.divide(
        grouped["benefit_users"],
        grouped["active_members"].clip(lower=1),
    )
    grouped["expected_contribution"] = (
        grouped["annual_fee_revenue"]
        + grouped["transaction_value"] * 0.0065
        - grouped["benefit_cost"]
        - grouped["credit_loss"]
        - grouped["fraud_loss"]
        - grouped["active_members"] * 2.2
    )
    return {
        "data": grouped.replace({np.nan: None}).to_dict(orient="records"),
        "summary": {
            "active_members": int(grouped["active_members"].sum()),
            "annual_fee_revenue": float(grouped["annual_fee_revenue"].sum()),
            "benefit_cost": float(grouped["benefit_cost"].sum()),
            "expected_contribution": float(grouped["expected_contribution"].sum()),
        },
    }


def finance_analytics(
    performance: pd.DataFrame,
    partner_performance: pd.DataFrame,
    vendor_performance: pd.DataFrame,
    assumptions: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    assumptions = assumptions or {
        "revenue_rate": 0.017,
        "transaction_revenue_rate": 0.007,
        "funding_cost_rate": 0.0038,
        "operating_cost_per_active_account": 7.5,
        "review_cost_per_case": 4.25,
        "customer_friction_cost_per_event": 2.75,
    }
    months = sorted(pd.to_datetime(performance["month"]).unique())
    current = performance[performance["month"] == months[-1]]
    prior = performance[performance["month"] == months[-2]] if len(months) > 1 else current

    def profit_components(frame: pd.DataFrame) -> dict[str, float]:
        active = float(((frame["inactive_flag"] == 0) & (frame["chargeoff_flag"] == 0)).sum())
        average_receivables = float(frame["average_daily_balance"].sum())
        transaction_value = float(frame["transaction_value"].sum())
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
        return {
            "Balance revenue effect": average_receivables * float(assumptions["revenue_rate"]),
            "Transaction revenue effect": transaction_value
            * float(assumptions["transaction_revenue_rate"]),
            "Funding-cost effect": -average_receivables * float(assumptions["funding_cost_rate"]),
            "Account-volume operating-cost effect": -active
            * float(assumptions["operating_cost_per_active_account"]),
            "Credit-loss effect": -float(
                frame["chargeoff_amount"].sum() - frame["recovery_amount"].sum()
            ),
            "Fraud-loss effect": -float(frame["confirmed_fraud_loss"].sum()),
            "Manual-review cost effect": -float(frame["manual_review_count"].sum())
            * float(assumptions["review_cost_per_case"]),
            "Customer-friction cost effect": -friction_events
            * float(assumptions["customer_friction_cost_per_event"]),
        }

    prior_components = profit_components(prior)
    current_components = profit_components(current)
    prior_expected_profit = float(sum(prior_components.values()))
    current_expected_profit = float(sum(current_components.values()))
    effects = {name: current_components[name] - prior_components[name] for name in prior_components}
    bridge = [
        {
            "component": "Prior expected profit",
            "value": prior_expected_profit,
            "group": "opening",
        },
        *[
            {
                "component": name,
                "value": value,
                "group": "favourable" if value >= 0 else "adverse",
            }
            for name, value in effects.items()
        ],
        {
            "component": "Current expected profit",
            "value": current_expected_profit,
            "group": "closing",
        },
    ]
    reconciliation_residual = (
        prior_expected_profit + sum(effects.values()) - current_expected_profit
    )
    latest_partner = partner_performance[
        partner_performance["month"] == partner_performance["month"].max()
    ]
    latest_vendor = vendor_performance[
        vendor_performance["month"] == vendor_performance["month"].max()
    ]
    active = int(((current["inactive_flag"] == 0) & (current["chargeoff_flag"] == 0)).sum())
    return {
        "bridge": bridge,
        "bridge_reconciliation": {
            "opening_expected_profit": prior_expected_profit,
            "effect_total": float(sum(effects.values())),
            "closing_expected_profit": current_expected_profit,
            "residual": float(reconciliation_residual),
            "reconciled": bool(abs(reconciliation_residual) < 1e-8),
            "assumption_source": "Baseline governed scenario assumptions",
        },
        "unit_economics": {
            "loss_per_active_account": safe_divide(
                float(current["chargeoff_amount"].sum() - current["recovery_amount"].sum()),
                active,
            ),
            "fraud_loss_per_1000_transactions": safe_divide(
                float(current["confirmed_fraud_loss"].sum()) * 1000,
                float(current["transaction_count"].sum()),
            ),
            "review_cost_per_case": 4.25,
            "partner_cost_per_active_customer": safe_divide(
                float(latest_partner["partner_fee"].sum()), active
            ),
            "vendor_cost_per_processed_case": safe_divide(
                float(latest_vendor["total_vendor_cost"].sum()),
                float(latest_vendor["cases_completed"].sum()),
            ),
        },
        "concentration": {
            "partner_transaction_hhi": hhi(latest_partner["transaction_value"]),
            "vendor_volume_hhi": hhi(latest_vendor["process_volume"]),
            "partner_transaction_gini": gini(latest_partner["transaction_value"]),
            "vendor_volume_gini": gini(latest_vendor["process_volume"]),
        },
        "notice": "Risk-adjusted contribution measures are synthetic planning analogues, not regulatory capital measures.",
    }
