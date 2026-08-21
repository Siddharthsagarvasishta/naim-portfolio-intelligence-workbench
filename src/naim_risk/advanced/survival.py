"""Kaplan--Meier and two-sample log-rank survival analysis."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats


class AdvancedStatisticsError(ValueError):
    """Raised when an advanced-statistics contract is invalid."""


def _survival_inputs(
    durations: Sequence[float] | pd.Series,
    events: Sequence[int | bool] | pd.Series,
) -> tuple[np.ndarray, np.ndarray]:
    time = np.asarray(durations, dtype=float)
    observed = np.asarray(events)
    if time.ndim != 1 or observed.ndim != 1 or len(time) != len(observed):
        raise AdvancedStatisticsError("Durations and event indicators must be aligned vectors")
    if len(time) < 2 or not np.all(np.isfinite(time)) or np.any(time < 0):
        raise AdvancedStatisticsError(
            "Durations must contain at least two finite non-negative values"
        )
    unique_events = set(np.unique(observed).tolist())
    if not unique_events.issubset({0, 1}):
        raise AdvancedStatisticsError("Event indicators must be binary")
    return time, observed.astype(bool)


def kaplan_meier(
    durations: Sequence[float] | pd.Series,
    events: Sequence[int | bool] | pd.Series,
    *,
    confidence: float = 0.95,
) -> dict[str, Any]:
    """Estimate a Kaplan--Meier curve with log-minus-log confidence bands."""

    if not 0.80 <= confidence < 1:
        raise AdvancedStatisticsError("Confidence must be in [0.80, 1.0)")
    time, observed = _survival_inputs(durations, events)
    z_score = float(stats.norm.ppf(0.5 + confidence / 2))
    event_times = np.sort(np.unique(time[observed]))
    survival = 1.0
    greenwood = 0.0
    curve = [
        {
            "time": 0.0,
            "at_risk": int(len(time)),
            "events": 0,
            "censored": 0,
            "survival_probability": 1.0,
            "confidence_lower": 1.0,
            "confidence_upper": 1.0,
        }
    ]
    for event_time in event_times:
        at_risk = int(np.sum(time >= event_time))
        event_count = int(np.sum((time == event_time) & observed))
        censored_count = int(np.sum((time == event_time) & ~observed))
        survival *= 1 - event_count / at_risk
        if at_risk > event_count:
            greenwood += event_count / (at_risk * (at_risk - event_count))
        if 0 < survival < 1 and greenwood > 0:
            transformed = math.log(-math.log(survival))
            transformed_error = math.sqrt(greenwood) / abs(math.log(survival))
            lower = math.exp(-math.exp(transformed + z_score * transformed_error))
            upper = math.exp(-math.exp(transformed - z_score * transformed_error))
        elif survival == 1:
            lower = upper = 1.0
        else:
            lower = upper = 0.0
        curve.append(
            {
                "time": float(event_time),
                "at_risk": at_risk,
                "events": event_count,
                "censored": censored_count,
                "survival_probability": float(survival),
                "confidence_lower": float(max(0, lower)),
                "confidence_upper": float(min(1, upper)),
            }
        )
    median_rows = [row for row in curve if row["survival_probability"] <= 0.5]
    median_survival = median_rows[0]["time"] if median_rows else None
    horizon = float(np.max(time))
    restricted_mean = 0.0
    previous_time = 0.0
    previous_survival = 1.0
    for row in curve[1:]:
        restricted_mean += (row["time"] - previous_time) * previous_survival
        previous_time = row["time"]
        previous_survival = row["survival_probability"]
    restricted_mean += (horizon - previous_time) * previous_survival
    return {
        "status": "implemented",
        "estimator": "Kaplan-Meier product limit",
        "observations": int(len(time)),
        "events": int(observed.sum()),
        "censored": int((~observed).sum()),
        "confidence_level": confidence,
        "confidence_method": "Greenwood variance with log-minus-log transform",
        "median_survival_time": median_survival,
        "restricted_mean_survival_time": float(restricted_mean),
        "restricted_mean_horizon": horizon,
        "curve": curve,
        "limitations": [
            "Censoring is assumed non-informative conditional on the analysis design.",
            "Confidence bands are pointwise, not simultaneous.",
            "Survival differences are associations unless supported by a separate causal design.",
        ],
    }


def log_rank_test(
    durations: Sequence[float] | pd.Series,
    events: Sequence[int | bool] | pd.Series,
    groups: Sequence[Any] | pd.Series,
) -> dict[str, Any]:
    """Perform the standard two-sample log-rank test."""

    time, observed = _survival_inputs(durations, events)
    group = np.asarray(groups)
    if group.ndim != 1 or len(group) != len(time):
        raise AdvancedStatisticsError("Group labels must align with durations")
    levels = pd.unique(group)
    if len(levels) != 2:
        raise AdvancedStatisticsError("Log-rank test currently requires exactly two groups")
    first = group == levels[0]
    observed_first = 0.0
    expected_first = 0.0
    variance = 0.0
    for event_time in np.sort(np.unique(time[observed])):
        at_risk = time >= event_time
        events_at_time = (time == event_time) & observed
        total_risk = int(at_risk.sum())
        total_events = int(events_at_time.sum())
        first_risk = int((at_risk & first).sum())
        first_events = int((events_at_time & first).sum())
        observed_first += first_events
        expected_first += total_events * first_risk / total_risk
        if total_risk > 1:
            variance += (
                first_risk
                * (total_risk - first_risk)
                * total_events
                * (total_risk - total_events)
                / (total_risk**2 * (total_risk - 1))
            )
    statistic = (observed_first - expected_first) ** 2 / variance if variance > 0 else 0.0
    return {
        "status": "implemented",
        "groups": [str(level) for level in levels],
        "statistic": float(statistic),
        "degrees_of_freedom": 1,
        "p_value": float(stats.chi2.sf(statistic, 1)),
        "observed_events_first_group": float(observed_first),
        "expected_events_first_group": float(expected_first),
        "variance": float(variance),
        "interpretation": "Tests equality of survival functions; it does not establish causality.",
    }


def run_survival_analysis(
    frame: pd.DataFrame,
    *,
    group_column: str | None = None,
    outcomes: dict[str, tuple[str, str]] | None = None,
    confidence: float = 0.95,
) -> dict[str, Any]:
    """Run governed attrition and first-30+-delinquency time-to-event analyses."""

    configured = outcomes or {
        "time_to_attrition": ("time_to_attrition", "attrition_event"),
        "time_to_first_30_plus_delinquency": (
            "time_to_first_30_plus_delinquency",
            "delinquency_30_event",
        ),
    }
    missing = sorted(
        {
            column
            for duration_column, event_column in configured.values()
            for column in (duration_column, event_column)
            if column not in frame
        }
    )
    if group_column is not None and group_column not in frame:
        missing.append(group_column)
    if missing:
        raise AdvancedStatisticsError(f"Survival input is missing columns: {sorted(set(missing))}")
    results: dict[str, Any] = {}
    for name, (duration_column, event_column) in configured.items():
        selected = frame[
            [duration_column, event_column] + ([group_column] if group_column else [])
        ].dropna()
        outcome = {
            "overall": kaplan_meier(
                selected[duration_column],
                selected[event_column],
                confidence=confidence,
            ),
            "groups": {},
            "log_rank": None,
        }
        if group_column:
            levels = pd.unique(selected[group_column])
            for level in levels:
                group_frame = selected[selected[group_column] == level]
                outcome["groups"][str(level)] = kaplan_meier(
                    group_frame[duration_column],
                    group_frame[event_column],
                    confidence=confidence,
                )
            if len(levels) == 2:
                outcome["log_rank"] = log_rank_test(
                    selected[duration_column],
                    selected[event_column],
                    selected[group_column],
                )
            else:
                outcome["log_rank"] = {
                    "status": "not_run",
                    "reason": "The live log-rank implementation supports exactly two groups.",
                }
        results[name] = outcome
    return {
        "status": "implemented",
        "outcomes": results,
        "cox_proportional_hazards": {
            "status": "not_implemented",
            "reason": "Optional Cox modelling is withheld until assumption diagnostics are validated.",
        },
        "causal_status": "associational",
        "governance": {
            "required_review": [
                "event definition",
                "time origin",
                "right-censoring rule",
                "competing risks",
                "non-informative censoring assumption",
            ]
        },
    }
