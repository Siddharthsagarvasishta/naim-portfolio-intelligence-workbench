"""Coherent, deterministic synthetic card-portfolio generator.

The generator intentionally models dependencies between acquisition mix, latent
risk, payment behaviour, strategy treatment, fraud pressure, operational
friction, attrition and losses. It never creates real or identifying customer
information.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from naim_risk.common.math import sigmoid
from naim_risk.config import NaimConfig

PRODUCTS = np.array(
    [
        "Consumer Revolving Card",
        "Consumer Charge Card",
        "Small Business Card",
        "Co-Branded Card",
    ]
)
CHANNELS = np.array(
    [
        "Direct Digital",
        "Branch or Assisted",
        "Affiliate",
        "Partner",
        "Pre-Approved",
        "Existing-Customer Cross-Sell",
    ]
)
GEOGRAPHIES = np.array(["North", "South", "East", "West", "Central", "International"])
SEGMENTS = np.array(
    [
        "New to Credit",
        "Mass Market",
        "Emerging Affluent",
        "Affluent",
        "Small Business",
        "Established Customer",
    ]
)
RISK_BANDS = np.array(
    [
        "A: Very Low Risk",
        "B: Low Risk",
        "C: Moderate Risk",
        "D: Elevated Risk",
        "E: High Risk",
    ]
)
STRATEGIES = np.array(["Champion A", "Challenger B", "Challenger C", "Legacy", "Targeted Review"])
PARTNER_NAMES = [
    "NorthStar Travel Network",
    "Meridian Rewards Alliance",
    "Atlas Digital Acquisition",
    "Horizon Hospitality Group",
    "Pioneer Commerce Collective",
    "Summit Mobility Services",
]
VENDOR_NAMES = [
    "Keystone Review Services",
    "BluePeak Processing",
    "Cedarline Data Services",
    "Orion Dispute Support",
    "Harbor Identity Labs",
    "Granite Servicing Collective",
]
MEMBERSHIP_TIERS = ["Core", "Silver", "Gold", "Platinum", "Premium Business"]
BENEFITS = [
    "Airport-service access",
    "Travel credit",
    "Dining credit",
    "Retail offer",
    "Mobility credit",
    "Insurance support",
    "Digital subscription",
    "Rewards accelerator",
    "Emergency assistance",
]


def _delinquency_label(days_past_due: np.ndarray) -> np.ndarray:
    return np.select(
        [
            days_past_due >= 90,
            days_past_due >= 60,
            days_past_due >= 30,
        ],
        ["90+", "60-89", "30-59"],
        default="Current",
    )


def _choice(
    rng: np.random.Generator, values: Iterable[str], size: int, probabilities: Iterable[float]
) -> np.ndarray:
    values_array = np.asarray(list(values))
    return rng.choice(values_array, size=size, p=np.asarray(list(probabilities), dtype=float))


def _master_data(
    config: NaimConfig,
    rng: np.random.Generator,
    months: pd.DatetimeIndex,
) -> tuple[pd.DataFrame, dict[str, np.ndarray | int]]:
    n = config.profile.accounts
    expansion_start = min(
        int(config.deterioration["expansion_start_month_index"]), max(2, len(months) // 3)
    )
    expansion_end = min(
        int(config.deterioration["expansion_end_month_index"]),
        max(expansion_start + 1, len(months) // 2),
    )
    is_expansion_cohort = rng.random(n) < 0.22
    origination_index = rng.integers(-18, 0, size=n)
    if is_expansion_cohort.any():
        origination_index[is_expansion_cohort] = rng.integers(
            expansion_start, expansion_end + 1, size=int(is_expansion_cohort.sum())
        )
    origination_dates = pd.DatetimeIndex(
        [months[0] + pd.DateOffset(months=int(index)) for index in origination_index]
    )
    product = _choice(rng, PRODUCTS, n, [0.48, 0.17, 0.16, 0.19])
    geography = _choice(rng, GEOGRAPHIES, n, [0.18, 0.17, 0.17, 0.18, 0.19, 0.11])
    segment = _choice(rng, SEGMENTS, n, [0.12, 0.34, 0.16, 0.13, 0.12, 0.13])
    risk_band = _choice(rng, RISK_BANDS, n, [0.18, 0.29, 0.30, 0.16, 0.07])
    channel = np.empty(n, dtype=object)
    regular = ~is_expansion_cohort
    channel[regular] = _choice(
        rng, CHANNELS, int(regular.sum()), [0.31, 0.15, 0.12, 0.12, 0.15, 0.15]
    )
    channel[is_expansion_cohort] = _choice(
        rng,
        CHANNELS,
        int(is_expansion_cohort.sum()),
        [0.19, 0.07, 0.47, 0.12, 0.08, 0.07],
    )
    seeded_affiliate = is_expansion_cohort & (channel == "Affiliate")
    # The deterioration is deliberately concentrated enough to be discoverable
    # through hierarchical analysis, while the source fields remain ordinary
    # institution-neutral portfolio dimensions.
    focus_product_draw = rng.random(n)
    focus_region_draw = rng.random(n)
    product[seeded_affiliate & (focus_product_draw < 0.70)] = "Consumer Revolving Card"
    geography[seeded_affiliate & (focus_region_draw < 0.60)] = "East"
    seeded_focus = seeded_affiliate & (product == "Consumer Revolving Card") & (geography == "East")
    band_risk = {
        "A: Very Low Risk": -1.25,
        "B: Low Risk": -0.68,
        "C: Moderate Risk": 0.0,
        "D: Elevated Risk": 0.72,
        "E: High Risk": 1.35,
    }
    latent_risk = np.asarray([band_risk[value] for value in risk_band], dtype=float)
    latent_risk += rng.normal(0.0, 0.34, n)
    latent_risk += seeded_affiliate.astype(float) * 0.48
    latent_risk += seeded_focus.astype(float) * 0.38
    strategy = _choice(rng, STRATEGIES, n, [0.54, 0.18, 0.12, 0.10, 0.06])
    affiliate_draw = rng.random(n)
    b_share = float(config.deterioration["challenger_b_affiliate_share"])
    strategy[seeded_affiliate & (affiliate_draw < b_share)] = "Challenger B"
    strategy[seeded_affiliate & (affiliate_draw >= b_share) & (affiliate_draw < b_share + 0.20)] = (
        "Champion A"
    )
    product_limit = {
        "Consumer Revolving Card": 9000.0,
        "Consumer Charge Card": 15000.0,
        "Small Business Card": 18500.0,
        "Co-Branded Card": 11000.0,
    }
    segment_multiplier = {
        "New to Credit": 0.55,
        "Mass Market": 0.82,
        "Emerging Affluent": 1.12,
        "Affluent": 1.62,
        "Small Business": 1.45,
        "Established Customer": 1.22,
    }
    credit_limit = np.asarray([product_limit[item] for item in product])
    credit_limit *= np.asarray([segment_multiplier[item] for item in segment])
    credit_limit *= np.exp(rng.normal(0.0, 0.22, n) - latent_risk * 0.08)
    credit_limit = np.round(np.clip(credit_limit, 1500.0, 45000.0), -1)
    initial_score = np.clip(705.0 - latent_risk * 58.0 + rng.normal(0.0, 18.0, n), 350, 850)
    initial_pd = np.clip(sigmoid(-3.55 + 0.88 * latent_risk), 0.002, 0.45)
    partner_id = np.asarray([f"PARTNER-{index % len(PARTNER_NAMES) + 1:02d}" for index in range(n)])
    partner_id[channel == "Affiliate"] = "PARTNER-03"
    partner_id[channel == "Partner"] = "PARTNER-05"
    vendor_id = np.asarray([f"VENDOR-{index % len(VENDOR_NAMES) + 1:02d}" for index in range(n)])
    membership_index = (
        np.asarray([np.where(SEGMENTS == item)[0][0] for item in segment]) + rng.integers(0, 3, n)
    ) % len(MEMBERSHIP_TIERS)
    membership_tier_id = np.asarray([f"TIER-{index + 1:02d}" for index in membership_index])
    account_id = np.asarray([f"ACCT-{index + 1:08d}" for index in range(n)])
    customer_id = np.asarray([f"CUST-{index + 1:08d}" for index in range(n)])
    master = pd.DataFrame(
        {
            "customer_id": customer_id,
            "account_id": account_id,
            "origination_date": origination_dates,
            "product_type": product,
            "acquisition_channel": channel,
            "geography": geography,
            "customer_segment": segment,
            "original_risk_band": risk_band,
            "current_strategy_version": strategy,
            "credit_limit": credit_limit,
            "initial_risk_score": np.round(initial_score, 2),
            "expected_probability_of_default": np.round(initial_pd, 6),
            "account_status": "Open",
            "close_date": pd.NaT,
            "closure_reason": None,
            "synthetic_data_flag": True,
            "partner_id": partner_id,
            "vendor_id": vendor_id,
            "membership_tier_id": membership_tier_id,
        }
    )
    state: dict[str, np.ndarray | int] = {
        "origination_index": origination_index,
        "latent_risk": latent_risk,
        "seeded_affiliate": seeded_affiliate,
        "seeded_focus": seeded_focus,
        "expansion_start": expansion_start,
        "expansion_end": expansion_end,
    }
    return master, state


def _strategy_history(months: pd.DatetimeIndex) -> pd.DataFrame:
    bounds = {
        "Champion A": (350, 850, 0.83, "Balanced monitoring"),
        "Challenger B": (400, 850, 0.90, "Growth-oriented monitoring"),
        "Challenger C": (350, 790, 0.76, "Tighter review"),
        "Legacy": (350, 850, 0.88, "Legacy rule set"),
        "Targeted Review": (350, 720, 0.68, "Enhanced manual review"),
    }
    rows = []
    for index, strategy in enumerate(STRATEGIES, start=1):
        lower, upper, utilization, rule = bounds[strategy]
        rows.append(
            {
                "strategy_id": f"STRAT-{index:02d}",
                "strategy_name": strategy,
                "strategy_version": strategy,
                "effective_start_date": months[0] - pd.DateOffset(years=2),
                "effective_end_date": months[-1] + pd.offsets.MonthEnd(12),
                "product_type": "All eligible products",
                "eligible_segment": "Configured eligible population",
                "risk_score_lower_bound": lower,
                "risk_score_upper_bound": upper,
                "utilization_threshold": utilization,
                "fraud_alert_threshold": 0.72 + index * 0.025,
                "review_rule": rule,
                "control_action": "Route to governed decision workflow",
                "champion_challenger_status": (
                    "Champion" if strategy == "Champion A" else "Challenger"
                ),
                "random_assignment_probability": (
                    0.54
                    if strategy == "Champion A"
                    else 0.18
                    if strategy == "Challenger B"
                    else 0.12
                ),
                "strategy_owner": "Synthetic Risk Strategy",
                "approval_status": "Approved",
                "change_reason": "Synthetic portfolio demonstration",
                "created_timestamp": months[0] - pd.DateOffset(years=2),
            }
        )
    return pd.DataFrame(rows)


def _economic_scenarios(config: NaimConfig, months: pd.DatetimeIndex) -> pd.DataFrame:
    rows = []
    for scenario_name, values in config.scenarios.items():
        for offset, month in enumerate(months):
            row = {
                "scenario_name": scenario_name,
                "month": month,
                **values,
                "assumption_type": "Synthetic portfolio-planning scenario",
            }
            if scenario_name == "Baseline":
                row["consumer_stress_index"] = values["consumer_stress_index"] * (
                    1.0 + max(0, offset - 12) * 0.006
                )
                row["fraud_pressure_index"] = values["fraud_pressure_index"] * (
                    1.0 + max(0, offset - 13) * 0.01
                )
            rows.append(row)
    return pd.DataFrame(rows)


def _monthly_performance(
    config: NaimConfig,
    master: pd.DataFrame,
    state: dict[str, np.ndarray | int],
    rng: np.random.Generator,
    months: pd.DatetimeIndex,
) -> pd.DataFrame:
    n = len(master)
    origination_index = np.asarray(state["origination_index"], dtype=int)
    latent_risk = np.asarray(state["latent_risk"], dtype=float)
    seeded_affiliate = np.asarray(state["seeded_affiliate"], dtype=bool)
    seeded_focus = np.asarray(state["seeded_focus"], dtype=bool)
    weak_start = int(config.deterioration["weak_mob_start"])
    weak_end = int(config.deterioration["weak_mob_end"])
    review_inflation_start = min(
        int(config.deterioration["review_inflation_start_month_index"]),
        max(4, len(months) * 2 // 3),
    )
    limits = master["credit_limit"].to_numpy(dtype=float)
    balance = limits * rng.beta(2.0, 5.2, size=n)
    prior_dpd = np.zeros(n, dtype=int)
    friction_history = np.zeros(n, dtype=float)
    closed = np.zeros(n, dtype=bool)
    chargeoff_index = np.full(n, -10_000, dtype=int)
    close_reason = np.full(n, None, dtype=object)
    frames: list[pd.DataFrame] = []
    for month_index, month in enumerate(months):
        normal_indices = np.flatnonzero((origination_index <= month_index) & ~closed)
        recovery_indices = np.flatnonzero(chargeoff_index == month_index - 1)
        if normal_indices.size:
            idx = normal_indices
            size = idx.size
            mob = month_index - origination_index[idx]
            prior = prior_dpd[idx].copy()
            seasonality = 1.0 + 0.12 * np.sin((month.month - 1) * np.pi / 6.0)
            tenure_factor = np.clip(0.72 + 0.05 * mob, 0.72, 1.18)
            product_factor = (
                master.iloc[idx]["product_type"]
                .map(
                    {
                        "Consumer Revolving Card": 1.0,
                        "Consumer Charge Card": 1.18,
                        "Small Business Card": 1.38,
                        "Co-Branded Card": 1.13,
                    }
                )
                .to_numpy()
            )
            activity_lambda = np.clip(
                16.0
                * product_factor
                * tenure_factor
                * seasonality
                * np.exp(-0.08 * latent_risk[idx]),
                1.0,
                65.0,
            )
            transaction_count = rng.poisson(activity_lambda).astype(int)
            ticket = rng.gamma(shape=2.4, scale=36.0, size=size)
            transaction_value = transaction_count * ticket
            cash_advance = transaction_value * rng.beta(0.8, 18.0, size=size)
            stress = 1.0 + max(0, month_index - 12) * 0.017
            payment_ratio = np.clip(
                rng.beta(2.4, 2.8, size=size)
                - 0.075 * latent_risk[idx]
                - 0.018 * (stress - 1.0)
                - 0.12 * (prior >= 30),
                0.02,
                1.15,
            )
            pre_payment_balance = np.maximum(
                0.0, balance[idx] + transaction_value * 0.42 + cash_advance
            )
            minimum_due = np.maximum(25.0, pre_payment_balance * 0.025)
            payment_amount = np.minimum(pre_payment_balance, pre_payment_balance * payment_ratio)
            new_balance = np.clip(pre_payment_balance - payment_amount, 0.0, limits[idx] * 1.18)
            utilization = np.divide(
                new_balance,
                limits[idx],
                out=np.zeros(size, dtype=float),
                where=limits[idx] > 0,
            )
            in_weak_window = seeded_affiliate[idx] & (mob >= weak_start) & (mob <= weak_end)
            missed_logit = (
                -4.75
                + 0.88 * latent_risk[idx]
                + 2.55 * utilization
                + 1.15 * (prior >= 30)
                + 0.55 * (prior >= 60)
                + 0.38 * (stress - 1.0) * 10
                + float(config.deterioration["affiliate_risk_logit"]) * in_weak_window
                + 0.90 * seeded_focus[idx] * (mob >= weak_start) * (mob <= weak_end)
            )
            missed = rng.random(size) < sigmoid(missed_logit)
            current_dpd = prior.copy()
            current_dpd[(prior == 0) & missed] = 30
            current_dpd[(prior == 30) & missed] = 60
            current_dpd[(prior == 60) & missed] = 90
            current_dpd[(prior >= 90) & missed] = 90
            curing = ~missed
            cure_draw = rng.random(size)
            current_dpd[(prior == 30) & curing & (cure_draw < 0.64)] = 0
            current_dpd[(prior == 60) & curing & (cure_draw < 0.50)] = 30
            current_dpd[(prior >= 90) & curing & (cure_draw < 0.36)] = 60
            focus_loss_window = seeded_focus[idx] & (mob >= weak_start + 3) & (mob <= weak_end + 4)
            chargeoff_probability = np.clip(
                0.10 + 0.07 * (latent_risk[idx] > 1) + 0.58 * focus_loss_window,
                0.04,
                0.82,
            )
            chargeoff = (prior >= 90) & (rng.random(size) < chargeoff_probability)
            chargeoff_amount = np.where(chargeoff, new_balance, 0.0)
            fraud_pressure = 1.0 + max(0, month_index - review_inflation_start) * 0.035
            strategy = master.iloc[idx]["current_strategy_version"].to_numpy()
            challenger_b = strategy == "Challenger B"
            tighter = np.isin(strategy, ["Challenger C", "Targeted Review"])
            inflated_rule = (
                (month_index >= review_inflation_start)
                & seeded_affiliate[idx]
                & (strategy == "Challenger B")
            )
            alert_probability = np.clip(
                0.0032
                * fraud_pressure
                * (1.0 + 0.25 * np.maximum(latent_risk[idx], 0))
                * np.where(tighter, 1.45, 1.0)
                * np.where(inflated_rule, 2.55, 1.0),
                0.0005,
                0.18,
            )
            fraud_alert_count = rng.binomial(transaction_count, alert_probability)
            confirm_probability = np.clip(
                0.24
                + 0.05 * np.maximum(latent_risk[idx], 0)
                - 0.04 * tighter
                - 0.13 * challenger_b
                - 0.12 * inflated_rule,
                0.05,
                0.42,
            )
            confirmed_events = rng.binomial(fraud_alert_count, confirm_probability)
            false_positives = np.maximum(fraud_alert_count - confirmed_events, 0)
            review_probability = np.clip(0.72 + 0.15 * tighter + 0.08 * inflated_rule, 0.0, 0.98)
            manual_reviews = rng.binomial(fraud_alert_count, review_probability)
            confirmed_fraud_loss = np.minimum(
                confirmed_events
                * rng.gamma(2.1, 72.0, size=size)
                * np.where(challenger_b, 0.58, 1.0),
                transaction_value * 0.85,
            )
            declined_count = rng.binomial(
                transaction_count,
                np.clip(0.008 + 0.015 * utilization + 0.01 * tighter, 0.001, 0.12),
            )
            step_up_count = rng.binomial(
                transaction_count,
                np.clip(0.006 + 0.012 * tighter + 0.01 * inflated_rule, 0.001, 0.14),
            )
            legitimate_declines = np.minimum(declined_count, false_positives + 1)
            contact_count = rng.binomial(
                np.maximum(manual_reviews + legitimate_declines + step_up_count, 1),
                np.clip(0.10 + 0.08 * inflated_rule, 0.0, 0.60),
            )
            friction_events = legitimate_declines + manual_reviews + step_up_count + contact_count
            complaint_count = rng.binomial(friction_events, 0.035)
            dispute_count = rng.binomial(transaction_count, 0.0025)
            friction_history[idx] = friction_history[idx] * 0.82 + np.minimum(friction_events, 5)
            inactivity = transaction_count == 0
            attrition_probability = np.clip(
                0.0014
                + 0.0018 * friction_history[idx]
                + 0.012 * inactivity
                + 0.001 * np.maximum(latent_risk[idx], 0),
                0,
                0.08,
            )
            attrition = (rng.random(size) < attrition_probability) & ~chargeoff
            risk_score = np.clip(
                master.iloc[idx]["initial_risk_score"].to_numpy()
                - current_dpd * 0.72
                - utilization * 28
                + rng.normal(0, 8, size),
                300,
                850,
            )
            expected_pd = np.clip(
                sigmoid(-3.7 + 0.82 * latent_risk[idx] + 0.018 * current_dpd + 1.15 * utilization),
                0.001,
                0.95,
            )
            prior_label = _delinquency_label(prior)
            current_label = _delinquency_label(current_dpd)
            current_label = np.where(chargeoff, "Charge-Off", current_label)
            frame = pd.DataFrame(
                {
                    "month": month,
                    "customer_id": master.iloc[idx]["customer_id"].to_numpy(),
                    "account_id": master.iloc[idx]["account_id"].to_numpy(),
                    "months_on_book": mob,
                    "account_balance": np.round(np.where(chargeoff, 0.0, new_balance), 2),
                    "statement_balance": np.round(pre_payment_balance, 2),
                    "average_daily_balance": np.round((balance[idx] + new_balance) / 2.0, 2),
                    "credit_limit": limits[idx],
                    "available_credit": np.round(np.maximum(limits[idx] - new_balance, 0), 2),
                    "transaction_value": np.round(transaction_value, 2),
                    "transaction_count": transaction_count,
                    "cash_advance_value": np.round(cash_advance, 2),
                    "inflows": np.round(payment_amount, 2),
                    "outflows": np.round(transaction_value + cash_advance, 2),
                    "payment_amount": np.round(payment_amount, 2),
                    "minimum_payment_due": np.round(minimum_due, 2),
                    "utilization": np.round(np.where(chargeoff, 0.0, utilization), 8),
                    "missed_payment_flag": missed.astype(int),
                    "days_past_due": np.where(chargeoff, 120, current_dpd),
                    "delinquency_status": current_label,
                    "prior_delinquency_status": prior_label,
                    "chargeoff_flag": chargeoff.astype(int),
                    "chargeoff_amount": np.round(chargeoff_amount, 2),
                    "recovery_amount": 0.0,
                    "fraud_alert_count": fraud_alert_count,
                    "manual_review_count": manual_reviews,
                    "confirmed_fraud_event_count": confirmed_events,
                    "confirmed_fraud_loss": np.round(confirmed_fraud_loss, 2),
                    "false_positive_count": false_positives,
                    "dispute_count": dispute_count,
                    "declined_transaction_count": declined_count,
                    "step_up_authentication_count": step_up_count,
                    "customer_contact_count": contact_count,
                    "complaint_count": complaint_count,
                    "inactive_flag": inactivity.astype(int),
                    "attrition_flag": attrition.astype(int),
                    "risk_score": np.round(risk_score, 2),
                    "expected_probability_of_default": np.round(expected_pd, 6),
                    "strategy_version": strategy,
                    "strategy_assignment_type": np.where(
                        np.isin(strategy, ["Champion A", "Challenger B", "Challenger C"]),
                        "Randomised test",
                        "Rule-based",
                    ),
                    "model_version": "Delinquency Baseline v1.0",
                    "data_quality_status": "PASS",
                }
            )
            frames.append(frame)
            balance[idx] = np.where(chargeoff, 0.0, new_balance)
            prior_dpd[idx] = np.where(chargeoff, 120, current_dpd)
            closing = chargeoff | attrition
            closing_indices = idx[closing]
            if closing_indices.size:
                closed[closing_indices] = True
                master.loc[closing_indices, "close_date"] = month
                master.loc[closing_indices, "account_status"] = np.where(
                    chargeoff[closing], "Charged Off", "Closed"
                )
                close_reason[closing_indices] = np.where(
                    chargeoff[closing], "Risk-driven charge-off", "Voluntary attrition"
                )
                chargeoff_index[idx[chargeoff]] = month_index
        if recovery_indices.size:
            idx = recovery_indices
            recovery_amount = np.round(
                master.iloc[idx]["credit_limit"].to_numpy()
                * rng.uniform(0.006, 0.018, size=idx.size),
                2,
            )
            zero_float = np.zeros(idx.size, dtype=float)
            zero_int = np.zeros(idx.size, dtype=int)
            recovery_frame = pd.DataFrame(
                {
                    "month": month,
                    "customer_id": master.iloc[idx]["customer_id"].to_numpy(),
                    "account_id": master.iloc[idx]["account_id"].to_numpy(),
                    "months_on_book": month_index - origination_index[idx],
                    "account_balance": zero_float,
                    "statement_balance": zero_float,
                    "average_daily_balance": zero_float,
                    "credit_limit": master.iloc[idx]["credit_limit"].to_numpy(),
                    "available_credit": zero_float,
                    "transaction_value": zero_float,
                    "transaction_count": zero_int,
                    "cash_advance_value": zero_float,
                    "inflows": recovery_amount,
                    "outflows": zero_float,
                    "payment_amount": zero_float,
                    "minimum_payment_due": zero_float,
                    "utilization": zero_float,
                    "missed_payment_flag": zero_int,
                    "days_past_due": np.full(idx.size, 120),
                    "delinquency_status": "Charge-Off",
                    "prior_delinquency_status": "Charge-Off",
                    "chargeoff_flag": zero_int,
                    "chargeoff_amount": zero_float,
                    "recovery_amount": recovery_amount,
                    "fraud_alert_count": zero_int,
                    "manual_review_count": zero_int,
                    "confirmed_fraud_event_count": zero_int,
                    "confirmed_fraud_loss": zero_float,
                    "false_positive_count": zero_int,
                    "dispute_count": zero_int,
                    "declined_transaction_count": zero_int,
                    "step_up_authentication_count": zero_int,
                    "customer_contact_count": zero_int,
                    "complaint_count": zero_int,
                    "inactive_flag": np.ones(idx.size, dtype=int),
                    "attrition_flag": zero_int,
                    "risk_score": master.iloc[idx]["initial_risk_score"].to_numpy(),
                    "expected_probability_of_default": np.ones(idx.size),
                    "strategy_version": master.iloc[idx]["current_strategy_version"].to_numpy(),
                    "strategy_assignment_type": "Recovery-only",
                    "model_version": "Delinquency Baseline v1.0",
                    "data_quality_status": "PASS",
                }
            )
            frames.append(recovery_frame)
    master["closure_reason"] = close_reason
    performance = pd.concat(frames, ignore_index=True)
    performance.sort_values(["month", "account_id"], inplace=True, ignore_index=True)
    return performance


def _strategy_decisions(performance: pd.DataFrame, master: pd.DataFrame) -> pd.DataFrame:
    strategy_id = {
        "Champion A": "STRAT-01",
        "Challenger B": "STRAT-02",
        "Challenger C": "STRAT-03",
        "Legacy": "STRAT-04",
        "Targeted Review": "STRAT-05",
    }
    normal = performance[performance["strategy_assignment_type"] != "Recovery-only"].copy()
    sequence = np.arange(1, len(normal) + 1)
    review = normal["manual_review_count"].to_numpy()
    fraud = normal["confirmed_fraud_event_count"].to_numpy()
    legitimate = (normal["false_positive_count"].to_numpy() > 0).astype(int)
    friction = (
        normal[
            [
                "manual_review_count",
                "declined_transaction_count",
                "step_up_authentication_count",
                "customer_contact_count",
            ]
        ].sum(axis=1)
        > 0
    ).astype(int)
    return pd.DataFrame(
        {
            "decision_id": [f"DEC-{value:010d}" for value in sequence],
            "decision_date": normal["month"].to_numpy(),
            "account_id": normal["account_id"].to_numpy(),
            "strategy_id": normal["strategy_version"].map(strategy_id).to_numpy(),
            "decision_type": "Monthly risk-strategy observation",
            "decision_outcome": np.where(fraud > 0, "Confirmed event", "No confirmed event"),
            "manual_review_flag": (review > 0).astype(int),
            "review_outcome": np.where(
                fraud > 0,
                "Confirmed fraud",
                np.where(review > 0, "Legitimate activity", "Not reviewed"),
            ),
            "legitimate_activity_flag": legitimate,
            "fraud_confirmed_flag": (fraud > 0).astype(int),
            "customer_friction_flag": friction,
            "operational_minutes": review * 8.0,
            "estimated_review_cost": review * 4.25,
            "estimated_friction_cost": friction * 2.75,
        }
    )


def _partner_master() -> pd.DataFrame:
    partner_types = [
        "Travel partner",
        "Loyalty partner",
        "Digital acquisition partner",
        "Hospitality partner",
        "Co-brand partner",
        "Mobility partner",
    ]
    return pd.DataFrame(
        {
            "partner_id": [f"PARTNER-{i + 1:02d}" for i in range(len(PARTNER_NAMES))],
            "partner_name": PARTNER_NAMES,
            "partner_type": partner_types,
            "partner_category": [
                "Strategic",
                "Rewards",
                "Acquisition",
                "Benefits",
                "Co-brand",
                "Service",
            ],
            "primary_region": GEOGRAPHIES.tolist(),
            "operating_regions": [", ".join(GEOGRAPHIES)] * len(PARTNER_NAMES),
            "supported_products": [", ".join(PRODUCTS)] * len(PARTNER_NAMES),
            "supported_membership_tiers": [", ".join(MEMBERSHIP_TIERS)] * len(PARTNER_NAMES),
            "onboarding_date": pd.to_datetime(
                ["2019-01-01", "2020-06-01", "2021-03-01", "2018-09-01", "2022-02-01", "2021-11-01"]
            ),
            "termination_date": pd.NaT,
            "partner_status": "Active",
            "strategic_importance": ["High", "Medium", "High", "Medium", "High", "Medium"],
            "criticality_tier": [1, 2, 1, 2, 1, 3],
            "contractual_currency": "Synthetic Currency Unit",
            "ownership_type": "Independent fictional entity",
            "concentration_category": ["High", "Medium", "High", "Low", "Medium", "Low"],
            "synthetic_data_flag": True,
        }
    )


def _vendor_master() -> pd.DataFrame:
    categories = [
        "Fraud review",
        "Transaction processing",
        "Data services",
        "Dispute processing",
        "Identity verification",
        "Customer servicing",
    ]
    return pd.DataFrame(
        {
            "vendor_id": [f"VENDOR-{i + 1:02d}" for i in range(len(VENDOR_NAMES))],
            "vendor_name": VENDOR_NAMES,
            "vendor_category": categories,
            "service_type": categories,
            "primary_region": GEOGRAPHIES.tolist(),
            "delivery_regions": [", ".join(GEOGRAPHIES)] * len(VENDOR_NAMES),
            "supported_products": [", ".join(PRODUCTS)] * len(VENDOR_NAMES),
            "supported_processes": categories,
            "onboarding_date": pd.to_datetime(
                ["2018-01-01", "2019-07-01", "2020-02-01", "2021-01-01", "2022-04-01", "2020-10-01"]
            ),
            "contract_end_date": pd.to_datetime(
                ["2027-12-31", "2028-06-30", "2027-09-30", "2028-12-31", "2027-03-31", "2029-01-31"]
            ),
            "vendor_status": "Active",
            "criticality_tier": [1, 1, 2, 2, 1, 2],
            "subcontractor_flag": [0, 1, 0, 1, 0, 1],
            "fourth_party_dependency_flag": [0, 1, 1, 0, 1, 0],
            "business_continuity_rating": [82, 76, 79, 73, 85, 75],
            "information_security_rating": [84, 80, 77, 78, 88, 76],
            "operational_risk_rating": [78, 72, 80, 70, 86, 74],
            "financial_stability_rating": [81, 79, 75, 77, 83, 72],
            "concentration_category": ["High", "High", "Medium", "Low", "Medium", "Low"],
            "synthetic_data_flag": True,
        }
    )


def _partner_contracts(months: pd.DatetimeIndex) -> pd.DataFrame:
    rows = []
    pricing_models = ["Revenue share", "Fixed plus variable", "Volume tier"]
    for index in range(len(PARTNER_NAMES)):
        rows.append(
            {
                "contract_id": f"PCON-{index + 1:03d}",
                "partner_id": f"PARTNER-{index + 1:02d}",
                "effective_start_date": months[0] - pd.DateOffset(years=2),
                "effective_end_date": months[-1] + pd.DateOffset(years=2),
                "contract_version": "1.0",
                "pricing_model": pricing_models[index % len(pricing_models)],
                "revenue_share_rate": 0.012 + index * 0.001,
                "fixed_fee": 20000.0 + index * 4500,
                "variable_fee_rate": 0.001 + index * 0.00015,
                "incentive_rate": 0.0003,
                "rebate_rate": 0.0004,
                "minimum_commitment": 500000.0 + index * 100000,
                "maximum_commitment": 5000000.0 + index * 750000,
                "performance_bonus": 12000.0,
                "performance_penalty": 9000.0,
                "benefit_cost_share": 0.25 + index * 0.05,
                "dispute_cost_share": 0.15 + index * 0.02,
                "fraud_loss_share": 0.08 + index * 0.015,
                "service_level_target": 0.96,
                "renewal_option": True,
                "termination_notice_days": 120,
                "contract_status": "Active",
                "approval_status": "Approved",
                "owner_role": "Synthetic Partner Management",
            }
        )
    return pd.DataFrame(rows)


def _vendor_contracts(months: pd.DatetimeIndex) -> pd.DataFrame:
    rows = []
    for index in range(len(VENDOR_NAMES)):
        rows.append(
            {
                "vendor_contract_id": f"VCON-{index + 1:03d}",
                "vendor_id": f"VENDOR-{index + 1:02d}",
                "effective_start_date": months[0] - pd.DateOffset(years=2),
                "effective_end_date": months[-1] + pd.DateOffset(years=2),
                "contract_version": "1.0",
                "fixed_cost": 18500.0 + (index + 1) * 1250,
                "unit_cost": 2.2 + (index + 1) * 0.16,
                "volume_tier": f"Tier {index % 3 + 1}",
                "service_level_target": 0.95 - index * 0.003,
                "penalty_rate": 0.04,
                "incentive_rate": 0.02,
                "minimum_volume": 150 + index * 50,
                "maximum_capacity": 1500 + index * 300,
                "currency": "Synthetic Currency Unit",
                "renewal_option": True,
                "exit_cost": 45000.0 + index * 6000,
                "switching_cost": 70000.0 + index * 9000,
                "contract_status": "Active",
                "approval_status": "Approved",
                "owner_role": "Synthetic Vendor Management",
            }
        )
    return pd.DataFrame(rows)


def _membership_master(months: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "membership_tier_id": [f"TIER-{i + 1:02d}" for i in range(len(MEMBERSHIP_TIERS))],
            "membership_tier_name": MEMBERSHIP_TIERS,
            "membership_category": ["Entry", "Value", "Rewards", "Premium", "Business"],
            "annual_fee": [0, 60, 140, 310, 360],
            "target_customer_segment": SEGMENTS[:5],
            "target_product": PRODUCTS[[0, 0, 3, 1, 2]],
            "benefit_package_id": [f"PACKAGE-{i + 1:02d}" for i in range(5)],
            "minimum_eligibility_score": [350, 520, 600, 680, 620],
            "launch_date": months[0] - pd.DateOffset(years=4),
            "retirement_date": pd.NaT,
            "active_flag": True,
            "synthetic_data_flag": True,
        }
    )


def _benefit_master(months: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "benefit_id": [f"BEN-{i + 1:02d}" for i in range(len(BENEFITS))],
            "benefit_name": BENEFITS,
            "benefit_category": [
                "Travel",
                "Travel",
                "Dining",
                "Retail",
                "Mobility",
                "Protection",
                "Digital",
                "Rewards",
                "Assistance",
            ],
            "benefit_provider_type": "Fictional partner",
            "partner_id": [
                f"PARTNER-{i % len(PARTNER_NAMES) + 1:02d}" for i in range(len(BENEFITS))
            ],
            "eligible_membership_tier": [
                MEMBERSHIP_TIERS[min(i // 2, len(MEMBERSHIP_TIERS) - 1)]
                for i in range(len(BENEFITS))
            ],
            "eligible_product": [PRODUCTS[i % len(PRODUCTS)] for i in range(len(BENEFITS))],
            "benefit_start_date": months[0] - pd.DateOffset(years=2),
            "benefit_end_date": pd.NaT,
            "usage_limit": [4, 2, 12, 8, 12, 2, 12, 24, 4],
            "customer_value_per_use": [45, 80, 18, 12, 16, 90, 10, 8, 35],
            "issuer_cost_per_use": [22, 52, 12, 8, 10, 45, 6, 4, 20],
            "partner_funded_percentage": [0.5, 0.35, 0.45, 0.6, 0.5, 0.25, 0.4, 0.55, 0.3],
            "breakage_assumption": [0.18, 0.22, 0.30, 0.34, 0.28, 0.40, 0.26, 0.20, 0.35],
            "fraud_exposure_category": [
                "Medium",
                "Medium",
                "Low",
                "Low",
                "Medium",
                "Low",
                "Low",
                "Medium",
                "Low",
            ],
            "accounting_treatment_category": "Synthetic planning expense",
            "active_flag": True,
        }
    )


def _cross_domain_tables(
    config: NaimConfig,
    master: pd.DataFrame,
    performance: pd.DataFrame,
    rng: np.random.Generator,
    months: pd.DatetimeIndex,
) -> dict[str, pd.DataFrame]:
    joined = performance.merge(
        master[
            [
                "account_id",
                "product_type",
                "geography",
                "partner_id",
                "vendor_id",
                "membership_tier_id",
            ]
        ],
        on="account_id",
        how="left",
        validate="many_to_one",
    )
    active = (joined["inactive_flag"] == 0) & (joined["chargeoff_flag"] == 0)
    joined["_active"] = active.astype(int)
    joined["_friction"] = (
        joined[
            [
                "manual_review_count",
                "declined_transaction_count",
                "step_up_authentication_count",
                "customer_contact_count",
            ]
        ].sum(axis=1)
        > 0
    ).astype(int)
    partner_group = joined.groupby(["month", "partner_id"], as_index=False).agg(
        acquired_accounts=("account_id", lambda values: int(values.nunique() * 0.015)),
        active_accounts=("_active", "sum"),
        transaction_value=("transaction_value", "sum"),
        transaction_count=("transaction_count", "sum"),
        average_balance=("account_balance", "mean"),
        confirmed_fraud_loss=("confirmed_fraud_loss", "sum"),
        credit_loss=("chargeoff_amount", "sum"),
        disputes=("dispute_count", "sum"),
        complaints=("complaint_count", "sum"),
        customer_friction_events=("_friction", "sum"),
        attrition_count=("attrition_flag", "sum"),
    )
    partner_group["region"] = partner_group["partner_id"].map(
        dict(zip([f"PARTNER-{i + 1:02d}" for i in range(6)], GEOGRAPHIES, strict=True))
    )
    partner_group["product_type"] = "Multi-product"
    partner_group["membership_tier"] = "Multi-tier"
    partner_group["benefit_redemptions"] = np.round(
        partner_group["transaction_count"] * 0.006
    ).astype(int)
    partner_group["benefit_cost"] = partner_group["benefit_redemptions"] * 9.5
    partner_group["partner_revenue"] = partner_group["transaction_value"] * 0.006
    partner_group["partner_fee"] = partner_group["transaction_value"] * 0.0014
    partner_group["rebate_value"] = partner_group["transaction_value"] * 0.0004
    partner_group["incentive_value"] = partner_group["transaction_value"] * 0.0002
    partner_group["servicing_cost"] = partner_group["active_accounts"] * 1.9
    partner_group["SLA_breach_count"] = (
        partner_group["partner_id"].str[-2:].astype(int) + partner_group["month"].dt.month
    ) % 3
    partner_group["expected_profit"] = (
        partner_group["partner_revenue"]
        - partner_group["partner_fee"]
        - partner_group["benefit_cost"]
        - partner_group["credit_loss"]
        - partner_group["confirmed_fraud_loss"]
        - partner_group["servicing_cost"]
    )
    partner_group["data_quality_status"] = "PASS"
    vendor_group = joined.groupby(["month", "vendor_id"], as_index=False).agg(
        process_volume=("transaction_count", "sum"),
        cases_received=("fraud_alert_count", "sum"),
        manual_review_count=("manual_review_count", "sum"),
        confirmed_fraud_detected=("confirmed_fraud_event_count", "sum"),
        false_positive_count=("false_positive_count", "sum"),
        customer_friction_events=("_friction", "sum"),
        complaints=("complaint_count", "sum"),
    )
    vendor_group["cases_completed"] = np.maximum(
        0, np.round(vendor_group["cases_received"] * 0.94).astype(int)
    )
    vendor_group["cases_pending"] = vendor_group["cases_received"] - vendor_group["cases_completed"]
    vendor_number = vendor_group["vendor_id"].str[-2:].astype(int)
    vendor_group["service_type"] = vendor_number.map(
        {
            1: "Fraud review",
            2: "Transaction processing",
            3: "Data services",
            4: "Dispute processing",
            5: "Identity verification",
            6: "Customer servicing",
        }
    )
    vendor_group["region"] = vendor_number.map(dict(enumerate(GEOGRAPHIES, start=1)))
    vendor_group["product_type"] = "Multi-product"
    vendor_group["average_processing_minutes"] = 9.0 + vendor_number * 0.8
    vendor_group["percentile_90_processing_minutes"] = (
        vendor_group["average_processing_minutes"] * 1.75
    )
    vendor_group["first_time_right_rate"] = np.clip(
        0.97 - vendor_number * 0.008 - vendor_group["cases_pending"] * 0.00005, 0.72, 0.99
    )
    vendor_group["rework_rate"] = 1.0 - vendor_group["first_time_right_rate"]
    vendor_group["error_count"] = np.round(
        vendor_group["cases_completed"] * vendor_group["rework_rate"]
    ).astype(int)
    vendor_group["critical_error_count"] = np.round(vendor_group["error_count"] * 0.04).astype(int)
    vendor_group["operational_incident_count"] = (
        (vendor_group["month"].dt.month + vendor_number) % 11 == 0
    ).astype(int)
    vendor_group["downtime_minutes"] = vendor_group["operational_incident_count"] * (
        40 + vendor_number * 9
    )
    vendor_group["SLA_breach_count"] = (
        vendor_group["cases_pending"] > np.maximum(2, vendor_group["cases_received"] * 0.07)
    ).astype(int)
    vendor_group["fixed_cost"] = 18500 + vendor_number * 1250
    vendor_group["variable_cost"] = vendor_group["cases_completed"] * (2.2 + vendor_number * 0.16)
    vendor_group["penalty_value"] = vendor_group["SLA_breach_count"] * 650
    vendor_group["incentive_value"] = (vendor_group["SLA_breach_count"] == 0).astype(int) * 350
    vendor_group["total_vendor_cost"] = (
        vendor_group["fixed_cost"]
        + vendor_group["variable_cost"]
        + vendor_group["penalty_value"]
        - vendor_group["incentive_value"]
    )
    vendor_group["unit_cost"] = np.divide(
        vendor_group["total_vendor_cost"],
        vendor_group["cases_completed"].clip(lower=1),
    )
    capacity = 1200 + vendor_number * 300
    vendor_group["capacity_utilisation"] = np.clip(
        vendor_group["cases_received"] / capacity, 0, 1.5
    )
    vendor_group["quality_score"] = vendor_group["first_time_right_rate"] * 100
    vendor_group["risk_score"] = np.clip(
        100
        - vendor_group["quality_score"]
        + vendor_group["SLA_breach_count"] * 10
        + vendor_group["capacity_utilisation"] * 8,
        0,
        100,
    )
    vendor_group["data_quality_status"] = "PASS"
    membership_master = _membership_master(months)
    membership_name = membership_master.set_index("membership_tier_id")[
        "membership_tier_name"
    ].to_dict()
    membership_history = master[
        [
            "customer_id",
            "account_id",
            "membership_tier_id",
            "origination_date",
            "current_strategy_version",
        ]
    ].copy()
    membership_history["effective_start_date"] = membership_history["origination_date"]
    membership_history["effective_end_date"] = pd.NaT
    membership_history["change_type"] = "Initial enrolment"
    membership_history["prior_membership_tier"] = None
    membership_history["new_membership_tier"] = membership_history["membership_tier_id"].map(
        membership_name
    )
    membership_history["upgrade_flag"] = 0
    membership_history["downgrade_flag"] = 0
    membership_history["retention_offer_flag"] = 0
    fee_map = membership_master.set_index("membership_tier_id")["annual_fee"].to_dict()
    membership_history["annual_fee_value"] = membership_history["membership_tier_id"].map(fee_map)
    membership_history["waived_fee_value"] = 0.0
    membership_history["change_reason"] = "Synthetic initial assignment"
    membership_history.rename(
        columns={"current_strategy_version": "strategy_version"}, inplace=True
    )
    transition_mask = rng.random(len(membership_history)) < 0.08
    transition_source = membership_history.loc[transition_mask].copy()
    if len(transition_source):
        transition_date = months[max(1, len(months) // 2)]
        old_index = transition_source["membership_tier_id"].str[-2:].astype(int).to_numpy() - 1
        upgrade = rng.random(len(transition_source)) < 0.62
        new_index = np.clip(old_index + np.where(upgrade, 1, -1), 0, len(MEMBERSHIP_TIERS) - 1)
        transition_source["effective_start_date"] = transition_date
        transition_source["effective_end_date"] = pd.NaT
        transition_source["change_type"] = np.where(upgrade, "Upgrade", "Downgrade")
        transition_source["prior_membership_tier"] = [
            MEMBERSHIP_TIERS[index] for index in old_index
        ]
        transition_source["membership_tier_id"] = [f"TIER-{index + 1:02d}" for index in new_index]
        transition_source["new_membership_tier"] = [MEMBERSHIP_TIERS[index] for index in new_index]
        transition_source["upgrade_flag"] = upgrade.astype(int)
        transition_source["downgrade_flag"] = (~upgrade).astype(int)
        transition_source["retention_offer_flag"] = (
            (~upgrade) & (rng.random(len(transition_source)) < 0.35)
        ).astype(int)
        transition_source["annual_fee_value"] = transition_source["membership_tier_id"].map(fee_map)
        transition_source["waived_fee_value"] = (
            transition_source["retention_offer_flag"] * transition_source["annual_fee_value"] * 0.5
        )
        transition_source["change_reason"] = np.where(
            upgrade,
            "Synthetic engagement-led transition",
            "Synthetic value-risk transition",
        )
        membership_history.loc[transition_mask, "effective_end_date"] = (
            transition_date - pd.Timedelta(days=1)
        )
        membership_history = pd.concat([membership_history, transition_source], ignore_index=True)
    usage_pool = joined[(joined["transaction_count"] > 0) & (joined["inactive_flag"] == 0)].copy()
    usage_pool = usage_pool[rng.random(len(usage_pool)) < 0.035].copy()
    benefit_master = _benefit_master(months)
    if len(usage_pool):
        benefit_index = (
            usage_pool["account_id"].str[-4:].astype(int).to_numpy()
            + usage_pool["month"].dt.month.to_numpy()
        ) % len(BENEFITS)
        usage_pool["benefit_id"] = [f"BEN-{value + 1:02d}" for value in benefit_index]
        usage_pool = usage_pool.merge(
            benefit_master[
                [
                    "benefit_id",
                    "customer_value_per_use",
                    "issuer_cost_per_use",
                    "partner_funded_percentage",
                ]
            ],
            on="benefit_id",
            how="left",
        )
        usage_count = np.maximum(1, rng.poisson(1.3, len(usage_pool)))
        benefit_usage = pd.DataFrame(
            {
                "benefit_usage_id": [f"USE-{i + 1:010d}" for i in range(len(usage_pool))],
                "usage_date": usage_pool["month"].to_numpy(),
                "month": usage_pool["month"].to_numpy(),
                "customer_id": usage_pool["customer_id"].to_numpy(),
                "account_id": usage_pool["account_id"].to_numpy(),
                "benefit_id": usage_pool["benefit_id"].to_numpy(),
                "partner_id": usage_pool["partner_id"].to_numpy(),
                "membership_tier_id": usage_pool["membership_tier_id"].to_numpy(),
                "transaction_id": [f"TXN-SYN-{i + 1:010d}" for i in range(len(usage_pool))],
                "usage_count": usage_count,
                "customer_value": usage_count * usage_pool["customer_value_per_use"].to_numpy(),
                "issuer_cost": usage_count * usage_pool["issuer_cost_per_use"].to_numpy(),
                "partner_funded_value": usage_count
                * usage_pool["issuer_cost_per_use"].to_numpy()
                * usage_pool["partner_funded_percentage"].to_numpy(),
                "recognised_cost": usage_count
                * usage_pool["issuer_cost_per_use"].to_numpy()
                * (1 - usage_pool["partner_funded_percentage"].to_numpy()),
                "accrued_cost": 0.0,
                "fraud_suspected_flag": (usage_pool["fraud_alert_count"].to_numpy() > 0).astype(
                    int
                ),
                "fraud_confirmed_flag": (
                    usage_pool["confirmed_fraud_event_count"].to_numpy() > 0
                ).astype(int),
                "dispute_flag": (usage_pool["dispute_count"].to_numpy() > 0).astype(int),
                "reversal_flag": 0,
                "customer_friction_flag": usage_pool["_friction"].to_numpy(),
                "fulfilment_status": "Completed",
                "fulfilment_minutes": np.round(rng.gamma(2.0, 8.0, len(usage_pool)), 2),
            }
        )
    else:
        benefit_usage = pd.DataFrame(
            columns=[
                "benefit_usage_id",
                "usage_date",
                "month",
                "customer_id",
                "account_id",
                "benefit_id",
                "partner_id",
                "membership_tier_id",
                "transaction_id",
                "usage_count",
                "customer_value",
                "issuer_cost",
                "partner_funded_value",
                "recognised_cost",
                "accrued_cost",
                "fraud_suspected_flag",
                "fraud_confirmed_flag",
                "dispute_flag",
                "reversal_flag",
                "customer_friction_flag",
                "fulfilment_status",
                "fulfilment_minutes",
            ]
        )
    holdings = joined.groupby(
        ["customer_id", "month", "product_type", "membership_tier_id"], as_index=False
    ).agg(
        active_product_flag=("_active", "max"),
        account_count=("account_id", "nunique"),
        product_tenure_months=("months_on_book", "max"),
        transaction_value=("transaction_value", "sum"),
        balance=("account_balance", "sum"),
        product_engagement_score=("transaction_count", "mean"),
        cross_product_count=("product_type", "nunique"),
    )
    holdings["membership_tier"] = holdings["membership_tier_id"].map(membership_name)
    holdings["primary_product_flag"] = 1
    holdings["benefit_engagement_score"] = np.clip(holdings["transaction_value"] / 5000.0, 0, 100)
    incidents = pd.DataFrame(
        {
            "incident_id": ["INC-0001", "INC-0002", "INC-0003"],
            "incident_start_timestamp": [
                months[max(1, len(months) // 3)],
                months[max(2, len(months) * 2 // 3)],
                months[-2] if len(months) > 2 else months[-1],
            ],
            "incident_end_timestamp": [
                months[max(1, len(months) // 3)] + pd.Timedelta(hours=2),
                months[max(2, len(months) * 2 // 3)] + pd.Timedelta(hours=5),
                months[-2] + pd.Timedelta(hours=1) if len(months) > 2 else months[-1],
            ],
            "partner_id": ["PARTNER-03", "PARTNER-01", "PARTNER-05"],
            "vendor_id": ["VENDOR-01", "VENDOR-02", "VENDOR-04"],
            "service_type": ["Fraud review", "Transaction processing", "Dispute processing"],
            "region": ["West", "International", "North"],
            "product_type": ["Consumer Revolving Card", "Co-Branded Card", "Small Business Card"],
            "severity": ["Medium", "High", "Low"],
            "customer_accounts_affected": [220, 510, 85],
            "transactions_affected": [430, 1120, 140],
            "estimated_financial_impact": [18000.0, 62000.0, 7400.0],
            "complaint_count": [7, 19, 2],
            "fraud_exposure": [2500.0, 8000.0, 600.0],
            "root_cause_category": ["Capacity", "Service interruption", "Process quality"],
            "remediation_status": ["Closed", "Monitoring", "Closed"],
            "owner": "Synthetic Operations Risk",
            "closure_timestamp": [
                months[max(1, len(months) // 3)] + pd.Timedelta(days=2),
                pd.NaT,
                months[-1],
            ],
        }
    )
    basket_definition = pd.DataFrame(
        [
            {
                "basket_id": "BASKET-001",
                "basket_name": "Affiliate Challenger B MOB 4-8",
                "basket_type": "account",
                "basket_description": "Dynamic diagnostic population",
                "entity_type": "account",
                "owner": "Synthetic Analyst",
                "status": "Approved",
                "version": 1,
                "basket_expression": "acquisition_channel == 'Affiliate' and current_strategy_version == 'Challenger B'",
                "locked_flag": False,
                "approved_flag": True,
                "valid_from": months[0],
                "valid_to": pd.NaT,
            },
            {
                "basket_id": "BASKET-002",
                "basket_name": "Critical Vendor Portfolio",
                "basket_type": "vendor",
                "basket_description": "Tier-one vendor oversight basket",
                "entity_type": "vendor",
                "owner": "Synthetic Vendor Oversight",
                "status": "Approved",
                "version": 1,
                "basket_expression": "criticality_tier == 1",
                "locked_flag": True,
                "approved_flag": True,
                "valid_from": months[0],
                "valid_to": pd.NaT,
            },
            {
                "basket_id": "BASKET-003",
                "basket_name": "Strategic Partners",
                "basket_type": "partner",
                "basket_description": "High-importance partners",
                "entity_type": "partner",
                "owner": "Synthetic Partner Analytics",
                "status": "Approved",
                "version": 1,
                "basket_expression": "strategic_importance == 'High'",
                "locked_flag": False,
                "approved_flag": True,
                "valid_from": months[0],
                "valid_to": pd.NaT,
            },
            {
                "basket_id": "BASKET-004",
                "basket_name": "Premium Memberships",
                "basket_type": "membership",
                "basket_description": "Premium and business membership propositions",
                "entity_type": "membership",
                "owner": "Synthetic Membership Analytics",
                "status": "Draft",
                "version": 1,
                "basket_expression": "annual_fee >= 300",
                "locked_flag": False,
                "approved_flag": False,
                "valid_from": months[0],
                "valid_to": pd.NaT,
            },
        ]
    )
    basket_membership_rows = []
    for account_id in master.loc[
        (master["acquisition_channel"] == "Affiliate")
        & (master["current_strategy_version"] == "Challenger B"),
        "account_id",
    ]:
        basket_membership_rows.append(
            {
                "basket_id": "BASKET-001",
                "basket_version": 1,
                "entity_id": account_id,
                "entity_type": "account",
                "effective_start_date": months[0],
                "effective_end_date": pd.NaT,
                "inclusion_reason": "Approved dynamic expression",
                "weight": 1.0,
                "override_flag": False,
                "override_reason": None,
                "added_by": "Generator",
                "added_timestamp": months[0],
            }
        )
    workspace_definition = pd.DataFrame(
        [
            {
                "workspace_id": "WORKSPACE-001",
                "workspace_name": "Monthly Portfolio Review",
                "owner": "Synthetic Portfolio Analyst",
                "workspace_type": "Recurring review",
                "business_question": "What changed and what drove the portfolio movement?",
                "reporting_period": months[-1],
                "comparison_period": months[-2] if len(months) > 1 else months[-1],
                "selected_metrics": "ANNUALISED_NET_LOSS_RATE,DELINQUENCY_30_ACCOUNT_RATE,EXPECTED_PROFIT",
                "selected_dimensions": "product_type,acquisition_channel,strategy_version",
                "selected_baskets": "BASKET-001",
                "selected_scenarios": "Baseline,Mild Downturn",
                "selected_templates": "Monthly KPI Movement",
                "filter_configuration": "{}",
                "visual_configuration": "{}",
                "commentary_configuration": '{"provider":"template"}',
                "export_configuration": "{}",
                "version": 1,
                "status": "Approved",
                "created_timestamp": months[0],
                "modified_timestamp": months[-1],
                "approved_flag": True,
            },
            {
                "workspace_id": "WORKSPACE-002",
                "workspace_name": "Vendor Oversight Review",
                "owner": "Synthetic Vendor Analyst",
                "workspace_type": "Control review",
                "business_question": "Which vendors face capacity or service-quality pressure?",
                "reporting_period": months[-1],
                "comparison_period": months[-2] if len(months) > 1 else months[-1],
                "selected_metrics": "capacity_utilisation,quality_score,total_vendor_cost",
                "selected_dimensions": "vendor_id,service_type",
                "selected_baskets": "BASKET-002",
                "selected_scenarios": "Baseline",
                "selected_templates": "Partner and Vendor Benchmark",
                "filter_configuration": "{}",
                "visual_configuration": "{}",
                "commentary_configuration": '{"provider":"template"}',
                "export_configuration": "{}",
                "version": 1,
                "status": "Approved",
                "created_timestamp": months[0],
                "modified_timestamp": months[-1],
                "approved_flag": True,
            },
            {
                "workspace_id": "WORKSPACE-003",
                "workspace_name": "Membership Profitability Review",
                "owner": "Synthetic Membership Analyst",
                "workspace_type": "Analytical review",
                "business_question": "How do membership economics and engagement compare?",
                "reporting_period": months[-1],
                "comparison_period": months[-2] if len(months) > 1 else months[-1],
                "selected_metrics": "membership_contribution,benefit_cost,attrition_rate",
                "selected_dimensions": "membership_tier_id,product_type",
                "selected_baskets": "BASKET-004",
                "selected_scenarios": "Baseline",
                "selected_templates": "Benefit Profitability",
                "filter_configuration": "{}",
                "visual_configuration": "{}",
                "commentary_configuration": '{"provider":"template"}',
                "export_configuration": "{}",
                "version": 1,
                "status": "Draft",
                "created_timestamp": months[0],
                "modified_timestamp": months[-1],
                "approved_flag": False,
            },
        ]
    )
    return {
        "partner_master": _partner_master(),
        "vendor_master": _vendor_master(),
        "partner_contract": _partner_contracts(months),
        "vendor_contract": _vendor_contracts(months),
        "membership_master": membership_master,
        "benefit_master": benefit_master,
        "partner_monthly_performance": partner_group,
        "vendor_monthly_performance": vendor_group,
        "customer_membership_history": membership_history,
        "benefit_usage_fact": benefit_usage,
        "customer_product_holding": holdings,
        "service_incident_fact": incidents,
        "portfolio_basket_definition": basket_definition,
        "portfolio_basket_membership": pd.DataFrame(basket_membership_rows),
        "workspace_definition": workspace_definition,
    }


def generate_synthetic_portfolio(config: NaimConfig) -> dict[str, pd.DataFrame]:
    """Generate all canonical raw entities for one deterministic configuration."""

    rng = np.random.default_rng(config.seed)
    months = pd.date_range(config.start_month, periods=config.profile.months, freq="MS")
    master, state = _master_data(config, rng, months)
    performance = _monthly_performance(config, master, state, rng, months)
    strategy_history = _strategy_history(months)
    decisions = _strategy_decisions(performance, master)
    cross_domain = _cross_domain_tables(config, master, performance, rng, months)
    ground_truth = pd.DataFrame(
        [
            {
                "story_id": "SEEDED-DETERIORATION-001",
                "expansion_start_month": months[int(state["expansion_start"])],
                "expansion_end_month": months[int(state["expansion_end"])],
                "primary_acquisition_channel": "Affiliate",
                "concentrated_product": "Consumer Revolving Card",
                "concentrated_region": "East",
                "disproportionate_strategy": "Challenger B",
                "weak_mob_start": config.deterioration["weak_mob_start"],
                "weak_mob_end": config.deterioration["weak_mob_end"],
                "expected_driver_set": "acquisition mix|within-segment performance|strategy review inflation|macro stress",
                "ui_exposure_allowed": False,
            }
        ]
    )
    alert_configuration = pd.DataFrame(list(config.alert_rules))
    return {
        "customer_account_master": master,
        "monthly_account_performance": performance,
        "risk_strategy_history": strategy_history,
        "strategy_decision_fact": decisions,
        "economic_scenario_assumptions": _economic_scenarios(config, months),
        "alert_configuration": alert_configuration,
        "investigation_log": pd.DataFrame(
            columns=[
                "investigation_id",
                "alert_id",
                "opened_timestamp",
                "owner",
                "status",
                "hypothesis",
                "supporting_evidence",
                "action_taken",
                "resolution",
                "closed_timestamp",
                "reviewer",
                "audit_timestamp",
            ]
        ),
        **cross_domain,
        "_ground_truth_deterioration": ground_truth,
    }
