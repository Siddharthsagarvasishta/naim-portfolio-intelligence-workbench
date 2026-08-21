"""Governed champion-challenger comparison and deterministic recommendation."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import pandas as pd

from naim_risk.common.math import benjamini_hochberg, safe_divide, wilson_interval
from naim_risk.metrics.core import apply_filters, enrich_performance


def _chi_square_survival(statistic: float, degrees_of_freedom: int) -> float:
    try:
        from scipy.stats import chi2

        return float(chi2.sf(statistic, degrees_of_freedom))
    except (ImportError, ModuleNotFoundError):
        if degrees_of_freedom == 1:
            return float(math.erfc(math.sqrt(max(statistic, 0.0) / 2.0)))
        return float(math.exp(-max(statistic, 0.0) / 2.0))


def _two_proportion_p_value(
    success_a: float, total_a: float, success_b: float, total_b: float
) -> float:
    if total_a <= 0 or total_b <= 0:
        return 1.0
    pooled = (success_a + success_b) / (total_a + total_b)
    variance = pooled * (1 - pooled) * (1 / total_a + 1 / total_b)
    if variance <= 0:
        return 1.0
    z = (success_a / total_a - success_b / total_b) / math.sqrt(variance)
    return float(math.erfc(abs(z) / math.sqrt(2.0)))


def _strategy_row(
    group: pd.DataFrame, total_assignments: int, assumptions: Mapping[str, float]
) -> dict[str, Any]:
    eligible_accounts = int(group["account_id"].nunique())
    transaction_value = float(group["transaction_value"].sum())
    transactions = float(group["transaction_count"].sum())
    fraud_alerts = float(group["fraud_alert_count"].sum())
    average_receivables = float(group["average_daily_balance"].sum())
    active = int(((group["inactive_flag"] == 0) & (group["chargeoff_flag"] == 0)).sum())
    friction_mask = (
        group[
            [
                "manual_review_count",
                "declined_transaction_count",
                "step_up_authentication_count",
                "customer_contact_count",
            ]
        ].sum(axis=1)
        > 0
    ) & (group["confirmed_fraud_event_count"] == 0)
    net_loss = float(group["chargeoff_amount"].sum() - group["recovery_amount"].sum())
    revenue = average_receivables * float(assumptions["revenue_rate"]) + transaction_value * float(
        assumptions["transaction_revenue_rate"]
    )
    expected_profit = (
        revenue
        - average_receivables * float(assumptions["funding_cost_rate"])
        - active * float(assumptions["operating_cost_per_active_account"])
        - net_loss
        - float(group["confirmed_fraud_loss"].sum())
        - float(group["manual_review_count"].sum()) * float(assumptions["review_cost_per_case"])
        - float(friction_mask.sum()) * float(assumptions["customer_friction_cost_per_event"])
    )
    loss_rate = safe_divide(net_loss, average_receivables)
    fraud_bps = safe_divide(float(group["confirmed_fraud_loss"].sum()) * 10_000, transaction_value)
    review_rate = safe_divide(float(group["manual_review_count"].sum()), transactions)
    false_positive_rate = safe_divide(float(group["false_positive_count"].sum()), fraud_alerts)
    friction_rate = safe_divide(float(friction_mask.sum()), active)
    complaint_rate = safe_divide(float(group["complaint_count"].sum()) * 1000, active)
    attrition_rate = safe_divide(float(group["attrition_flag"].sum()), active)
    fraud_ci = wilson_interval(
        float(group["confirmed_fraud_event_count"].sum()), max(fraud_alerts, 0)
    )
    return {
        "strategy": str(group["strategy_version"].iloc[0]),
        "eligible_accounts": eligible_accounts,
        "assignment_count": int(len(group)),
        "assignment_share": safe_divide(len(group), total_assignments),
        "transaction_value": transaction_value,
        "net_credit_loss": net_loss,
        "loss_rate": loss_rate,
        "fraud_bps": fraud_bps,
        "manual_review_rate": review_rate,
        "false_positive_rate": false_positive_rate,
        "customer_friction_rate": friction_rate,
        "complaint_rate_per_1000": complaint_rate,
        "attrition_rate": attrition_rate,
        "operational_minutes": float(group["manual_review_count"].sum()) * 8.0,
        "expected_profit": expected_profit,
        "fraud_event_ci_lower": fraud_ci[0],
        "fraud_event_ci_upper": fraud_ci[1],
        "minimum_sample_met": eligible_accounts >= 100,
    }


def compare_strategies(
    performance: pd.DataFrame,
    master: pd.DataFrame,
    *,
    assumptions: Mapping[str, float],
    filters: Mapping[str, Any] | None = None,
    seed: int = 73421,
) -> dict[str, Any]:
    """Compare strategies, report validity, and apply deterministic guardrails."""

    frame = apply_filters(enrich_performance(performance, master), filters)
    frame = frame[frame["strategy_assignment_type"] != "Recovery-only"].copy()
    total = len(frame)
    rows = [
        _strategy_row(group, total, assumptions)
        for _, group in frame.groupby("strategy_version", sort=True)
    ]
    rows.sort(key=lambda item: item["strategy"])
    randomised = frame[frame["strategy_assignment_type"] == "Randomised test"]
    expected_probabilities = {"Champion A": 0.54, "Challenger B": 0.18, "Challenger C": 0.12}
    expected_total = sum(expected_probabilities.values())
    counts = randomised["strategy_version"].value_counts()
    random_n = int(counts.sum())
    chi_square = 0.0
    for strategy, probability in expected_probabilities.items():
        expected = random_n * probability / expected_total
        if expected > 0:
            chi_square += (float(counts.get(strategy, 0)) - expected) ** 2 / expected
    srm_p_value = _chi_square_survival(chi_square, max(len(expected_probabilities) - 1, 1))
    row_lookup = {row["strategy"]: row for row in rows}
    champion = row_lookup.get("Champion A")
    challenger = row_lookup.get("Challenger B")
    p_values: list[float] = []
    outcomes: list[dict[str, Any]] = []
    if champion and challenger:
        for metric, numerator, denominator in [
            ("manual_review_rate", "manual_review_count", "transaction_count"),
            ("false_positive_rate", "false_positive_count", "fraud_alert_count"),
            ("customer_friction_rate", None, None),
        ]:
            if numerator:
                group_a = frame[frame["strategy_version"] == "Champion A"]
                group_b = frame[frame["strategy_version"] == "Challenger B"]
                p_value = _two_proportion_p_value(
                    float(group_a[numerator].sum()),
                    float(group_a[denominator].sum()),
                    float(group_b[numerator].sum()),
                    float(group_b[denominator].sum()),
                )
            else:
                p_value = 1.0
            p_values.append(p_value)
            outcomes.append(
                {
                    "metric": metric,
                    "effect": (
                        None
                        if champion[metric] is None or challenger[metric] is None
                        else challenger[metric] - champion[metric]
                    ),
                    "p_value": p_value,
                }
            )
        adjusted = benjamini_hochberg(p_values)
        for outcome, adjusted_value in zip(outcomes, adjusted, strict=True):
            outcome["adjusted_p_value"] = adjusted_value
            outcome["statistically_significant"] = adjusted_value < 0.05
    rules = []
    if not champion or not challenger:
        decision = "Insufficient evidence"
        rules.append("Required champion and challenger populations were not both available.")
    elif min(champion["eligible_accounts"], challenger["eligible_accounts"]) < 100:
        decision = "Insufficient evidence"
        rules.append("Minimum sample of 100 unique accounts was not met.")
    elif srm_p_value < 0.01:
        decision = "Investigate"
        rules.append("Sample-ratio mismatch test failed at p < 0.01.")
    else:
        profit_uplift = challenger["expected_profit"] - champion["expected_profit"]
        lower_fraud = (
            challenger["fraud_bps"] is not None
            and champion["fraud_bps"] is not None
            and challenger["fraud_bps"] < champion["fraud_bps"]
        )
        friction_breach = (
            challenger["customer_friction_rate"] is not None
            and champion["customer_friction_rate"] is not None
            and challenger["customer_friction_rate"] > champion["customer_friction_rate"] * 1.15
        )
        review_breach = (
            challenger["manual_review_rate"] is not None
            and champion["manual_review_rate"] is not None
            and challenger["manual_review_rate"] > champion["manual_review_rate"] * 1.20
        )
        rules.extend(
            [
                f"Expected-profit difference (B minus A): {profit_uplift:.2f}.",
                f"Fraud-loss guardrail improved: {lower_fraud}.",
                f"Customer-friction guardrail breached: {friction_breach}.",
                f"Operational-review guardrail breached: {review_breach}.",
            ]
        )
        if lower_fraud and not friction_breach and not review_breach and profit_uplift > 0:
            decision = "Expand cautiously"
        elif lower_fraud and (friction_breach or review_breach):
            decision = "Continue test"
        elif profit_uplift < 0 and (friction_breach or review_breach):
            decision = "Maintain champion"
        else:
            decision = "Investigate"
    return {
        "strategies": rows,
        "validity": {
            "assignment_type": "Randomised and rule-based populations are labelled separately",
            "randomised_observations": random_n,
            "sample_ratio_mismatch_statistic": chi_square,
            "sample_ratio_mismatch_p_value": srm_p_value,
            "sample_ratio_mismatch_flag": srm_p_value < 0.01,
            "causal_warning": "Only randomised eligible populations support causal interpretation; all other comparisons are associational.",
            "multiple_comparison_method": "Benjamini-Hochberg",
            "outcomes": outcomes,
        },
        "recommendation": {
            "decision": decision,
            "rule_path": rules,
            "approval_required": True,
            "notice": "Deterministic analytical output; not a final credit-policy decision.",
        },
    }
