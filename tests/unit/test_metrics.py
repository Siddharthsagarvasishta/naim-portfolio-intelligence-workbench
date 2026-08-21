from __future__ import annotations

import math

from naim_risk.common.math import safe_divide, wilson_interval
from naim_risk.metrics import calculate_roll_rates


def test_safe_divide_returns_none_for_zero_denominator():
    assert safe_divide(5, 0) is None
    assert safe_divide(5, float("nan")) is None
    assert safe_divide(6, 3) == 2


def test_weighted_utilization_and_annualisation_match_hand_calculation(service):
    result = {row["metric_id"]: row for row in service.kpis()["data"]}
    month = service.performance["month"].max()
    current = service.performance[service.performance["month"] == month]
    expected_utilization = current["account_balance"].sum() / current["credit_limit"].sum()
    net_loss = current["chargeoff_amount"].sum() - current["recovery_amount"].sum()
    expected_annualised_loss = (
        net_loss / current["average_daily_balance"].sum() * 12
        if current["average_daily_balance"].sum()
        else None
    )
    assert math.isclose(result["UTILIZATION"]["value"], expected_utilization, rel_tol=1e-12)
    if expected_annualised_loss is None:
        assert result["ANNUALISED_NET_LOSS_RATE"]["value"] is None
    else:
        assert math.isclose(
            result["ANNUALISED_NET_LOSS_RATE"]["value"],
            expected_annualised_loss,
            rel_tol=1e-12,
        )


def test_false_positive_metric_uses_resolved_alert_denominator(service):
    result = {row["metric_id"]: row for row in service.kpis()["data"]}
    month = service.performance["month"].max()
    current = service.performance[service.performance["month"] == month]
    expected = current["false_positive_count"].sum() / current["fraud_alert_count"].sum()
    assert math.isclose(result["FALSE_POSITIVE_RATE"]["value"], expected, rel_tol=1e-12)
    assert result["FALSE_POSITIVE_RATE"]["denominator"] == current["fraud_alert_count"].sum()


def test_roll_rate_rows_reconcile_to_each_origin_population(service):
    result = calculate_roll_rates(service.performance, service.master)
    origin_statuses = {row["from_status"] for row in result["matrix"]}
    for origin in origin_statuses:
        rows = [
            row
            for row in result["matrix"]
            if row["from_status"] == origin and row["denominator"] > 0
        ]
        if rows:
            assert math.isclose(sum(row["rate"] for row in rows), 1.0, abs_tol=1e-12)


def test_wilson_interval_contains_observed_rate():
    lower, upper = wilson_interval(25, 100)
    assert lower < 0.25 < upper
