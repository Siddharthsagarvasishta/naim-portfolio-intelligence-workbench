"""Schema, key, integrity and business-rule validation with quarantine."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import numpy as np
import pandas as pd

from naim_risk.types import ValidationCheck, ValidationResult

MASTER_REQUIRED = {
    "customer_id",
    "account_id",
    "origination_date",
    "product_type",
    "acquisition_channel",
    "geography",
    "customer_segment",
    "original_risk_band",
    "current_strategy_version",
    "credit_limit",
    "initial_risk_score",
    "expected_probability_of_default",
    "account_status",
    "synthetic_data_flag",
}
PERFORMANCE_REQUIRED = {
    "month",
    "customer_id",
    "account_id",
    "months_on_book",
    "account_balance",
    "average_daily_balance",
    "credit_limit",
    "transaction_value",
    "transaction_count",
    "payment_amount",
    "utilization",
    "days_past_due",
    "delinquency_status",
    "prior_delinquency_status",
    "chargeoff_flag",
    "chargeoff_amount",
    "recovery_amount",
    "fraud_alert_count",
    "manual_review_count",
    "confirmed_fraud_loss",
    "false_positive_count",
    "strategy_version",
    "data_quality_status",
}
VALID_RISK_BANDS = {
    "A: Very Low Risk",
    "B: Low Risk",
    "C: Moderate Risk",
    "D: Elevated Risk",
    "E: High Risk",
}
VALID_STRATEGIES = {
    "Champion A",
    "Challenger B",
    "Challenger C",
    "Legacy",
    "Targeted Review",
}
VALID_DELINQUENCY = {"Current", "30-59", "60-89", "90+", "Charge-Off"}


def _check(
    checks: list[ValidationCheck],
    *,
    check_id: str,
    severity: str,
    affected_rows: int,
    business_impact: str,
    recommendation: str,
    details: Mapping[str, object] | None = None,
) -> None:
    checks.append(
        ValidationCheck(
            check_id=check_id,
            severity=severity,
            status="PASS" if affected_rows == 0 else "FAIL",
            affected_rows=int(affected_rows),
            business_impact=business_impact,
            recommendation=recommendation,
            details=details or {},
        )
    )


def _required_column_check(
    checks: list[ValidationCheck],
    table_name: str,
    frame: pd.DataFrame,
    required: Iterable[str],
) -> set[str]:
    missing = set(required).difference(frame.columns)
    _check(
        checks,
        check_id=f"{table_name}.required_columns",
        severity="Critical",
        affected_rows=len(missing),
        business_impact="Missing required columns prevent a governed calculation.",
        recommendation="Restore the canonical data contract before publication.",
        details={"missing_columns": sorted(missing)},
    )
    return missing


def validate_tables(tables: Mapping[str, pd.DataFrame]) -> ValidationResult:
    """Validate canonical raw tables and return accepted and quarantined rows.

    Critical structural failures block publication. Row-level business-rule
    failures are quarantined and lower the quality score.
    """

    checks: list[ValidationCheck] = []
    master = tables.get("customer_account_master", pd.DataFrame()).copy()
    performance = tables.get("monthly_account_performance", pd.DataFrame()).copy()
    missing_master = _required_column_check(
        checks, "customer_account_master", master, MASTER_REQUIRED
    )
    missing_performance = _required_column_check(
        checks, "monthly_account_performance", performance, PERFORMANCE_REQUIRED
    )
    if missing_master or missing_performance:
        accepted = {name: frame.copy() for name, frame in tables.items()}
        return ValidationResult(
            status="BLOCKED",
            quality_score=0.0,
            checks=checks,
            accepted=accepted,
            quarantined={},
        )
    master_invalid = pd.Series(False, index=master.index)
    performance_invalid = pd.Series(False, index=performance.index)
    duplicate_master = master["account_id"].duplicated(keep=False)
    master_invalid |= duplicate_master
    _check(
        checks,
        check_id="customer_account_master.unique_account_id",
        severity="Critical",
        affected_rows=int(duplicate_master.sum()),
        business_impact="Duplicate account keys break star-schema joins and population totals.",
        recommendation="Deduplicate upstream account records using a governed survivor rule.",
    )
    duplicate_month = performance.duplicated(["month", "account_id"], keep=False)
    performance_invalid |= duplicate_month
    _check(
        checks,
        check_id="monthly_account_performance.unique_account_month",
        severity="Critical",
        affected_rows=int(duplicate_month.sum()),
        business_impact="Duplicate account-month rows inflate balances, losses and rates.",
        recommendation="Resolve duplicates before analytical publication.",
    )
    orphan = ~performance["account_id"].isin(set(master["account_id"]))
    performance_invalid |= orphan
    _check(
        checks,
        check_id="monthly_account_performance.account_fk",
        severity="Critical",
        affected_rows=int(orphan.sum()),
        business_impact="Orphan observations cannot inherit governed dimensions.",
        recommendation="Load the parent account or quarantine the orphan observation.",
    )
    invalid_master_enum = ~master["original_risk_band"].isin(VALID_RISK_BANDS) | ~master[
        "current_strategy_version"
    ].isin(VALID_STRATEGIES)
    master_invalid |= invalid_master_enum
    _check(
        checks,
        check_id="customer_account_master.permitted_enumerations",
        severity="High",
        affected_rows=int(invalid_master_enum.sum()),
        business_impact="Unknown risk or strategy labels create uncontrolled reporting groups.",
        recommendation="Map values through the approved canonical enumeration.",
    )
    invalid_perf_enum = ~performance["strategy_version"].isin(VALID_STRATEGIES) | ~performance[
        "delinquency_status"
    ].isin(VALID_DELINQUENCY)
    performance_invalid |= invalid_perf_enum
    _check(
        checks,
        check_id="monthly_account_performance.permitted_enumerations",
        severity="High",
        affected_rows=int(invalid_perf_enum.sum()),
        business_impact="Unknown strategy or delinquency labels invalidate transitions.",
        recommendation="Correct or explicitly map the source labels.",
    )
    required_master_nulls = master[list(MASTER_REQUIRED)].isna().any(axis=1)
    master_invalid |= required_master_nulls
    _check(
        checks,
        check_id="customer_account_master.required_completeness",
        severity="High",
        affected_rows=int(required_master_nulls.sum()),
        business_impact="Incomplete dimensions can bias filters and joins.",
        recommendation="Populate mandatory fields or quarantine the record.",
    )
    required_perf_nulls = performance[list(PERFORMANCE_REQUIRED)].isna().any(axis=1)
    performance_invalid |= required_perf_nulls
    _check(
        checks,
        check_id="monthly_account_performance.required_completeness",
        severity="High",
        affected_rows=int(required_perf_nulls.sum()),
        business_impact="Incomplete measures can bias KPI numerators or denominators.",
        recommendation="Populate mandatory fields or quarantine the record.",
    )
    numeric_nonnegative = [
        "account_balance",
        "average_daily_balance",
        "credit_limit",
        "transaction_value",
        "transaction_count",
        "confirmed_fraud_loss",
        "chargeoff_amount",
        "recovery_amount",
        "fraud_alert_count",
        "manual_review_count",
        "false_positive_count",
    ]
    negative = (performance[numeric_nonnegative].fillna(0) < -0.01).any(axis=1)
    performance_invalid |= negative
    _check(
        checks,
        check_id="monthly_account_performance.nonnegative_measures",
        severity="High",
        affected_rows=int(negative.sum()),
        business_impact="Impossible negative volumes or losses corrupt financial reconciliation.",
        recommendation="Correct sign conventions or map explicit reversal fields.",
    )
    expected_utilization = np.divide(
        performance["account_balance"].to_numpy(dtype=float),
        performance["credit_limit"].to_numpy(dtype=float),
        out=np.zeros(len(performance), dtype=float),
        where=performance["credit_limit"].to_numpy(dtype=float) != 0,
    )
    utilization_bad = (
        np.abs(performance["utilization"].to_numpy(dtype=float) - expected_utilization) > 0.005
    )
    utilization_bad = pd.Series(utilization_bad, index=performance.index)
    performance_invalid |= utilization_bad
    _check(
        checks,
        check_id="monthly_account_performance.utilization_reconciliation",
        severity="High",
        affected_rows=int(utilization_bad.sum()),
        business_impact="Unreconciled utilization can misstate a primary risk driver.",
        recommendation="Recalculate utilization as balance divided by credit limit.",
    )
    false_positive_bad = performance["false_positive_count"] > performance["fraud_alert_count"]
    performance_invalid |= false_positive_bad
    _check(
        checks,
        check_id="monthly_account_performance.false_positive_integrity",
        severity="High",
        affected_rows=int(false_positive_bad.sum()),
        business_impact="False positives cannot exceed the flagged-event population.",
        recommendation="Reconcile resolved fraud-alert outcomes.",
    )
    review_bad = performance["manual_review_count"] > performance["fraud_alert_count"]
    performance_invalid |= review_bad
    _check(
        checks,
        check_id="monthly_account_performance.review_integrity",
        severity="High",
        affected_rows=int(review_bad.sum()),
        business_impact="Reviews exceeding relevant decisions overstate workload.",
        recommendation="Reconcile review events with eligible alert decisions.",
    )
    fraud_loss_bad = performance["confirmed_fraud_loss"] > performance["transaction_value"] + 0.01
    performance_invalid |= fraud_loss_bad
    _check(
        checks,
        check_id="monthly_account_performance.fraud_loss_ceiling",
        severity="High",
        affected_rows=int(fraud_loss_bad.sum()),
        business_impact="Fraud loss above eligible transaction value requires an explicit exception.",
        recommendation="Correct the transaction denominator or document a synthetic exception.",
    )
    dpd = performance["days_past_due"]
    expected_status = np.select(
        [dpd >= 120, dpd >= 90, dpd >= 60, dpd >= 30],
        ["Charge-Off", "90+", "60-89", "30-59"],
        default="Current",
    )
    dpd_bad = performance["delinquency_status"].to_numpy() != expected_status
    dpd_bad = pd.Series(dpd_bad, index=performance.index)
    performance_invalid |= dpd_bad
    _check(
        checks,
        check_id="monthly_account_performance.dpd_status_alignment",
        severity="High",
        affected_rows=int(dpd_bad.sum()),
        business_impact="Inconsistent delinquency labels invalidate roll-rate analysis.",
        recommendation="Derive the status from approved days-past-due bands.",
    )
    chargeoff_bad = (performance["chargeoff_flag"] == 1) & (
        performance["prior_delinquency_status"] != "90+"
    )
    performance_invalid |= chargeoff_bad
    _check(
        checks,
        check_id="monthly_account_performance.chargeoff_sequence",
        severity="High",
        affected_rows=int(chargeoff_bad.sum()),
        business_impact="Charge-off must follow credible severe delinquency.",
        recommendation="Correct the delinquency history or quarantine the charge-off.",
    )
    ordered = performance.sort_values(["account_id", "month"]).copy()
    prior_chargeoff = (
        ordered.groupby("account_id")["chargeoff_flag"]
        .cumsum()
        .groupby(ordered["account_id"])
        .shift(1)
    ).fillna(0)
    recovery_bad_ordered = (ordered["recovery_amount"] > 0) & (prior_chargeoff <= 0)
    recovery_bad = pd.Series(False, index=performance.index)
    recovery_bad.loc[ordered.index] = recovery_bad_ordered.to_numpy()
    performance_invalid |= recovery_bad
    _check(
        checks,
        check_id="monthly_account_performance.recovery_sequence",
        severity="High",
        affected_rows=int(recovery_bad.sum()),
        business_impact="Recoveries before charge-off misstate net credit loss.",
        recommendation="Link recovery records to a prior charge-off.",
    )
    joined = performance[["account_id", "month", "transaction_count", "months_on_book"]].merge(
        master[["account_id", "origination_date", "close_date"]],
        on="account_id",
        how="left",
    )
    post_close_activity = (
        joined["close_date"].notna()
        & (pd.to_datetime(joined["month"]) > pd.to_datetime(joined["close_date"]))
        & (joined["transaction_count"] > 0)
    )
    post_close_bad = pd.Series(post_close_activity.to_numpy(), index=performance.index)
    performance_invalid |= post_close_bad
    _check(
        checks,
        check_id="monthly_account_performance.closed_account_activity",
        severity="High",
        affected_rows=int(post_close_bad.sum()),
        business_impact="Closed accounts cannot generate ordinary new activity.",
        recommendation="Suppress post-closure activity except explicit recovery records.",
    )
    expected_mob = (
        pd.to_datetime(joined["month"]).dt.to_period("M")
        - pd.to_datetime(joined["origination_date"]).dt.to_period("M")
    ).map(lambda value: int(value.n))
    mob_bad = joined["months_on_book"].to_numpy() != expected_mob.to_numpy()
    mob_bad = pd.Series(mob_bad, index=performance.index)
    performance_invalid |= mob_bad
    _check(
        checks,
        check_id="monthly_account_performance.months_on_book",
        severity="High",
        affected_rows=int(mob_bad.sum()),
        business_impact="Incorrect tenure breaks vintage maturity alignment.",
        recommendation="Recalculate month-on-book from origination and reporting month.",
    )
    observed_months = pd.DatetimeIndex(sorted(pd.to_datetime(performance["month"]).unique()))
    expected_months = (
        pd.date_range(observed_months.min(), observed_months.max(), freq="MS")
        if len(observed_months)
        else pd.DatetimeIndex([])
    )
    missing_months = expected_months.difference(observed_months)
    _check(
        checks,
        check_id="monthly_account_performance.month_completeness",
        severity="Critical",
        affected_rows=len(missing_months),
        business_impact="Missing reporting periods invalidate trends and adjacent-period transitions.",
        recommendation="Load all required reporting partitions before publication.",
        details={"missing_months": [str(value.date()) for value in missing_months]},
    )
    quarantine_master = master.loc[master_invalid].copy()
    quarantine_performance = performance.loc[performance_invalid].copy()
    accepted: dict[str, pd.DataFrame] = {
        name: frame.copy() for name, frame in tables.items() if not name.startswith("_")
    }
    accepted["customer_account_master"] = master.loc[~master_invalid].copy()
    accepted["monthly_account_performance"] = performance.loc[~performance_invalid].copy()
    critical_failures = [
        check for check in checks if check.severity == "Critical" and check.status == "FAIL"
    ]
    any_failures = [check for check in checks if check.status == "FAIL"]
    affected = sum(check.affected_rows for check in any_failures)
    denominator = max(1, len(master) + len(performance))
    score = max(0.0, 100.0 * (1.0 - min(1.0, affected / denominator)))
    status = "BLOCKED" if critical_failures else "PASS_WITH_WARNINGS" if any_failures else "PASS"
    quarantined = {
        name: frame
        for name, frame in {
            "customer_account_master": quarantine_master,
            "monthly_account_performance": quarantine_performance,
        }.items()
        if not frame.empty
    }
    return ValidationResult(
        status=status,
        quality_score=score,
        checks=checks,
        accepted=accepted,
        quarantined=quarantined,
    )
