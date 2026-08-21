"""Twelve-month scenario projections with exposed assumptions and elasticities."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from naim_risk.config import NaimConfig
from naim_risk.metrics.core import calculate_period_kpis


def list_scenarios(config: NaimConfig) -> list[dict[str, Any]]:
    return [
        {
            "scenario_name": name,
            "assumptions": dict(values),
            "notice": "Synthetic portfolio-planning scenario; not a regulatory capital scenario.",
        }
        for name, values in config.scenarios.items()
    ]


def run_scenario(
    performance: pd.DataFrame,
    master: pd.DataFrame,
    config: NaimConfig,
    *,
    scenario_name: str = "Baseline",
    custom_assumptions: Mapping[str, float] | None = None,
    horizon_months: int = 12,
) -> dict[str, Any]:
    """Project transparent portfolio outcomes from the latest validated state."""

    if horizon_months < 1 or horizon_months > 24:
        raise ValueError("Scenario horizon must be between 1 and 24 months")
    if scenario_name not in config.scenarios and scenario_name != "Custom":
        raise ValueError(f"Unknown scenario: {scenario_name}")
    baseline_assumptions = dict(config.scenarios["Baseline"])
    assumptions = (
        dict(config.scenarios.get(scenario_name, baseline_assumptions))
        if scenario_name != "Custom"
        else dict(baseline_assumptions)
    )
    if custom_assumptions:
        allowed = set(baseline_assumptions)
        unknown = set(custom_assumptions).difference(allowed)
        if unknown:
            raise ValueError(f"Unsupported scenario assumptions: {sorted(unknown)}")
        assumptions.update({key: float(value) for key, value in custom_assumptions.items()})
    kpis = {
        row["metric_id"]: row
        for row in calculate_period_kpis(
            performance,
            master,
            period=None,
            assumptions=baseline_assumptions,
            metric_registry=config.metrics,
        )
    }
    latest_month = pd.Timestamp(performance["month"].max()).to_period("M").to_timestamp()
    active = float(kpis["ACTIVE_ACCOUNTS"]["value"] or 0)
    receivables = float(kpis["ENDING_RECEIVABLES"]["value"] or 0)
    delinquency = float(kpis["DELINQUENCY_30_ACCOUNT_RATE"]["value"] or 0)
    annual_loss = float(kpis["ANNUALISED_NET_LOSS_RATE"]["value"] or 0)
    fraud_bps = float(kpis["FRAUD_BPS"]["value"] or 0)
    review_rate = float(kpis["MANUAL_REVIEW_RATE"]["value"] or 0)
    friction_rate = float(kpis["CUSTOMER_FRICTION_RATE"]["value"] or 0)
    transaction_value = float(kpis["TRANSACTION_VALUE"]["value"] or 0)
    baseline_stress = float(baseline_assumptions["consumer_stress_index"])
    baseline_unemployment = float(baseline_assumptions["unemployment_rate"])
    baseline_fraud_pressure = float(baseline_assumptions["fraud_pressure_index"])
    gdp_delta = float(assumptions["gdp_growth_rate"]) - float(
        baseline_assumptions["gdp_growth_rate"]
    )
    stress_delta = float(assumptions["consumer_stress_index"]) - baseline_stress
    unemployment_delta = float(assumptions["unemployment_rate"]) - baseline_unemployment
    fraud_pressure_ratio = float(assumptions["fraud_pressure_index"]) / baseline_fraud_pressure
    balance_growth = 0.003 + gdp_delta * float(config.elasticities["balance_growth_to_gdp"])
    attrition_rate = float(kpis["ATTRITION_RATE"]["value"] or 0.003)
    rows = []
    cumulative_loss = 0.0
    cumulative_fraud = 0.0
    for offset in range(1, horizon_months + 1):
        seasonal = 1.0 + 0.035 * np.sin((latest_month.month + offset - 1) * np.pi / 6.0)
        active *= max(0.8, 1.002 - attrition_rate * (1 + stress_delta * 0.4))
        receivables *= max(0.7, 1.0 + balance_growth) * seasonal
        projected_delinquency = np.clip(
            delinquency
            * (
                1.0
                + stress_delta * float(config.elasticities["delinquency_to_consumer_stress"])
                + unemployment_delta * 3.0
            )
            * (1 + offset * 0.003),
            0,
            0.65,
        )
        projected_annual_loss = np.clip(
            annual_loss
            * float(assumptions["credit_loss_multiplier"])
            * (1.0 + unemployment_delta * float(config.elasticities["loss_to_unemployment_delta"]))
            * (1 + offset * 0.004),
            0,
            0.95,
        )
        monthly_loss = receivables * projected_annual_loss / 12.0
        projected_fraud_bps = (
            fraud_bps
            * float(assumptions["fraud_loss_multiplier"])
            * fraud_pressure_ratio ** float(config.elasticities["fraud_to_pressure"])
        )
        projected_transaction = transaction_value * (
            active / max(kpis["ACTIVE_ACCOUNTS"]["value"], 1)
        )
        fraud_loss = projected_transaction * projected_fraud_bps / 10_000
        projected_review_rate = review_rate * (
            1 + (fraud_pressure_ratio - 1) * float(config.elasticities["review_to_fraud_pressure"])
        )
        projected_reviews = projected_transaction / 85.0 * projected_review_rate
        projected_friction = friction_rate * (
            1
            + max(projected_review_rate - review_rate, 0)
            * float(config.elasticities["friction_to_review_growth"])
            * 10
        )
        revenue = receivables * float(assumptions["revenue_rate"]) + projected_transaction * float(
            assumptions["transaction_revenue_rate"]
        )
        expected_profit = (
            revenue
            - receivables * float(assumptions["funding_cost_rate"])
            - active * float(assumptions["operating_cost_per_active_account"])
            - monthly_loss
            - fraud_loss
            - projected_reviews * float(assumptions["review_cost_per_case"])
            - active * projected_friction * float(assumptions["customer_friction_cost_per_event"])
        )
        cumulative_loss += monthly_loss
        cumulative_fraud += fraud_loss
        interval_width = 1.96 * np.sqrt(max(monthly_loss, 1.0)) * 2.5
        rows.append(
            {
                "month": str((latest_month + pd.DateOffset(months=offset)).date()),
                "active_accounts": float(active),
                "receivables": float(receivables),
                "delinquency_30_rate": float(projected_delinquency),
                "annualised_net_loss_rate": float(projected_annual_loss),
                "net_credit_loss": float(monthly_loss),
                "net_credit_loss_interval_lower": float(max(0, monthly_loss - interval_width)),
                "net_credit_loss_interval_upper": float(monthly_loss + interval_width),
                "fraud_bps": float(projected_fraud_bps),
                "confirmed_fraud_loss": float(fraud_loss),
                "manual_reviews": float(projected_reviews),
                "customer_friction_rate": float(projected_friction),
                "expected_profit": float(expected_profit),
                "cumulative_net_credit_loss": float(cumulative_loss),
                "cumulative_fraud_loss": float(cumulative_fraud),
            }
        )
    baseline_projection = (
        None
        if scenario_name == "Baseline" or scenario_name == "Custom"
        else run_scenario(
            performance,
            master,
            config,
            scenario_name="Baseline",
            horizon_months=horizon_months,
        )
    )
    baseline_cumulative = (
        baseline_projection["summary"]["cumulative_net_credit_loss"]
        if baseline_projection
        else cumulative_loss
    )
    return {
        "scenario": scenario_name,
        "assumptions": assumptions,
        "elasticities": dict(config.elasticities),
        "projections": rows,
        "summary": {
            "horizon_months": horizon_months,
            "cumulative_net_credit_loss": cumulative_loss,
            "cumulative_fraud_loss": cumulative_fraud,
            "total_expected_profit": float(sum(row["expected_profit"] for row in rows)),
            "loss_difference_from_baseline": cumulative_loss - baseline_cumulative,
        },
        "validation": {
            "method": "Transparent state projection with scenario elasticities",
            "naive_baseline_comparison": "Historical latest-state persistence is the reference.",
            "limitations": "Planning scenario only; uncertainty interval is an illustrative analytical range, not regulatory or model-risk approval.",
        },
        "notice": "Scenario estimate — assumptions are synthetic and editable.",
    }
