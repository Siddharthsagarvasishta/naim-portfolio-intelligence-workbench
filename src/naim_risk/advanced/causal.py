"""Governed observational comparisons with explicit identification diagnostics."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

from naim_risk.advanced.survival import AdvancedStatisticsError

# FastAPI executes synchronous route handlers in a worker thread. Importing the
# native scikit-learn/statsmodels stacks for the first time from that worker can
# deadlock on macOS import/runtime locks. Resolve optional dependencies while
# this module is imported, then keep the existing fail-closed optional behavior.
try:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
except (ImportError, ModuleNotFoundError) as exc:  # pragma: no cover - environment dependent
    LogisticRegression = None  # type: ignore[assignment,misc]
    StandardScaler = None  # type: ignore[assignment,misc]
    make_pipeline = None  # type: ignore[assignment]
    roc_auc_score = None  # type: ignore[assignment]
    _SKLEARN_IMPORT_ERROR: Exception | None = exc
else:
    _SKLEARN_IMPORT_ERROR = None

try:
    from statsmodels.regression.linear_model import OLS as StatsmodelsOLS
except (ImportError, ModuleNotFoundError) as exc:  # pragma: no cover - environment dependent
    StatsmodelsOLS = None  # type: ignore[assignment,misc]
    _STATSMODELS_IMPORT_ERROR: Exception | None = exc
else:
    _STATSMODELS_IMPORT_ERROR = None

_PROTECTED_NAMES = {
    "age",
    "disability",
    "ethnicity",
    "gender",
    "nationality",
    "pregnancy",
    "race",
    "religion",
    "sex",
    "sexual_orientation",
}


def _is_protected(name: str) -> bool:
    normalised = name.casefold().replace("-", "_").replace(" ", "_")
    return bool(
        set(normalised.split("_")).intersection(_PROTECTED_NAMES)
        | ({normalised} & _PROTECTED_NAMES)
    )


def _weighted_moments(values: np.ndarray, weights: np.ndarray) -> tuple[float, float]:
    total = float(weights.sum())
    if total <= 0:
        raise AdvancedStatisticsError("Weights must have positive mass")
    mean = float(np.sum(weights * values) / total)
    variance = float(np.sum(weights * np.square(values - mean)) / total)
    return mean, variance


def _standardised_mean_difference(
    values: np.ndarray,
    treatment: np.ndarray,
    weights: np.ndarray,
) -> float:
    treated_mean, treated_variance = _weighted_moments(values[treatment], weights[treatment])
    control_mean, control_variance = _weighted_moments(values[~treatment], weights[~treatment])
    pooled = math.sqrt(max((treated_variance + control_variance) / 2, 1e-16))
    return (treated_mean - control_mean) / pooled


def propensity_weighted_comparison(
    frame: pd.DataFrame,
    *,
    treatment_column: str,
    outcome_column: str,
    covariates: Sequence[str],
    trim_quantile: float = 0.99,
    seed: int = 73421,
) -> dict[str, Any]:
    """Estimate a stabilised-IPTW outcome contrast with overlap and balance diagnostics."""

    covariate_names = list(dict.fromkeys(covariates))
    required = {treatment_column, outcome_column, *covariate_names}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise AdvancedStatisticsError(f"Propensity input is missing columns: {missing}")
    if not covariate_names:
        raise AdvancedStatisticsError("At least one pre-treatment covariate is required")
    protected = sorted(name for name in covariate_names if _is_protected(name))
    if protected:
        raise AdvancedStatisticsError(f"Protected attributes are prohibited: {protected}")
    if not 0.90 <= trim_quantile < 1:
        raise AdvancedStatisticsError("trim_quantile must be in [0.90, 1.0)")
    working = frame[[treatment_column, outcome_column, *covariate_names]].dropna().copy()
    treatment_values = set(pd.unique(working[treatment_column]).tolist())
    if not treatment_values.issubset({0, 1}) or len(treatment_values) != 2:
        raise AdvancedStatisticsError("Treatment must be binary with both groups represented")
    treatment = working[treatment_column].astype(bool).to_numpy()
    outcome = pd.to_numeric(working[outcome_column], errors="coerce").to_numpy(dtype=float)
    matrix = working[covariate_names].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    if not np.all(np.isfinite(outcome)) or not np.all(np.isfinite(matrix)):
        raise AdvancedStatisticsError("Outcome and covariates must be finite numeric values")
    if min(treatment.sum(), (~treatment).sum()) < 20:
        raise AdvancedStatisticsError("Each treatment group requires at least 20 observations")
    if _SKLEARN_IMPORT_ERROR is not None:
        return {
            "status": "dependency_unavailable",
            "reason": f"scikit-learn analytics extra is required: {_SKLEARN_IMPORT_ERROR}",
        }
    assert LogisticRegression is not None
    assert StandardScaler is not None
    assert make_pipeline is not None
    assert roc_auc_score is not None
    propensity_model = make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=2_000, random_state=seed),
    )
    propensity_model.fit(matrix, treatment.astype(int))
    raw_propensity = propensity_model.predict_proba(matrix)[:, 1]
    propensity = np.clip(raw_propensity, 0.01, 0.99)
    treated_bounds = np.quantile(propensity[treatment], [0.01, 0.99])
    control_bounds = np.quantile(propensity[~treatment], [0.01, 0.99])
    common_lower = float(max(treated_bounds[0], control_bounds[0]))
    common_upper = float(min(treated_bounds[1], control_bounds[1]))
    in_common_support = (propensity >= common_lower) & (propensity <= common_upper)
    overlap = {
        "common_support_lower": common_lower,
        "common_support_upper": common_upper,
        "treated_share_in_common_support": float(in_common_support[treatment].mean()),
        "control_share_in_common_support": float(in_common_support[~treatment].mean()),
        "propensity_min": float(propensity.min()),
        "propensity_max": float(propensity.max()),
    }
    treatment_rate = float(treatment.mean())
    weights_raw = np.where(
        treatment,
        treatment_rate / propensity,
        (1 - treatment_rate) / (1 - propensity),
    )
    lower_weight, upper_weight = np.quantile(
        weights_raw,
        [1 - trim_quantile, trim_quantile],
    )
    weights = np.clip(weights_raw, lower_weight, upper_weight)
    balance = []
    unit_weights = np.ones(len(working), dtype=float)
    for index, name in enumerate(covariate_names):
        before = _standardised_mean_difference(matrix[:, index], treatment, unit_weights)
        after = _standardised_mean_difference(matrix[:, index], treatment, weights)
        balance.append(
            {
                "covariate": name,
                "smd_before": float(before),
                "absolute_smd_before": abs(float(before)),
                "smd_after": float(after),
                "absolute_smd_after": abs(float(after)),
                "balance_threshold": 0.10,
                "balanced_after": abs(after) <= 0.10,
            }
        )
    treated_mean, _ = _weighted_moments(outcome[treatment], weights[treatment])
    control_mean, _ = _weighted_moments(outcome[~treatment], weights[~treatment])
    effect = treated_mean - control_mean
    treated_total = float(weights[treatment].sum())
    control_total = float(weights[~treatment].sum())
    treated_variance = float(
        np.sum(np.square(weights[treatment]) * np.square(outcome[treatment] - treated_mean))
        / treated_total**2
    )
    control_variance = float(
        np.sum(np.square(weights[~treatment]) * np.square(outcome[~treatment] - control_mean))
        / control_total**2
    )
    standard_error = math.sqrt(max(treated_variance + control_variance, 0))
    effective_sample = {
        "treated": float(treated_total**2 / np.sum(np.square(weights[treatment]))),
        "control": float(control_total**2 / np.sum(np.square(weights[~treatment]))),
    }
    overlap_adequate = bool(
        common_lower < common_upper
        and overlap["treated_share_in_common_support"] >= 0.80
        and overlap["control_share_in_common_support"] >= 0.80
    )
    balance_adequate = bool(max(row["absolute_smd_after"] for row in balance) <= 0.10)
    precision_adequate = min(effective_sample.values()) >= 20
    interpretable = overlap_adequate and balance_adequate and precision_adequate
    return {
        "status": "implemented" if interpretable else "review_required",
        "estimand": "stabilised inverse-probability-weighted average treatment effect",
        "observations": int(len(working)),
        "propensity_model": {
            "algorithm": "standardised logistic regression",
            "roc_auc": float(roc_auc_score(treatment.astype(int), raw_propensity)),
            "probability_clipping": [0.01, 0.99],
        },
        "overlap": overlap,
        "weighting": {
            "method": "stabilised inverse probability of treatment weights",
            "trim_quantile": trim_quantile,
            "raw_weight_max": float(weights_raw.max()),
            "trimmed_weight_min": float(weights.min()),
            "trimmed_weight_max": float(weights.max()),
            "effective_sample_size": effective_sample,
        },
        "balance": balance,
        "balance_plot_data": [
            {
                "covariate": row["covariate"],
                "before": row["absolute_smd_before"],
                "after": row["absolute_smd_after"],
            }
            for row in balance
        ],
        "weighted_outcome": {
            "treated_mean": treated_mean,
            "control_mean": control_mean,
            "difference": effect,
            "robust_standard_error": standard_error,
            "confidence_interval_95": [
                effect - 1.96 * standard_error,
                effect + 1.96 * standard_error,
            ],
        },
        "diagnostic_decision": {
            "interpretable_with_assumptions": interpretable,
            "overlap_adequate": overlap_adequate,
            "balance_adequate": balance_adequate,
            "effective_sample_adequate": precision_adequate,
        },
        "causal_status": "observational association after measured-covariate adjustment",
        "sensitivity_warning": (
            "Unmeasured confounding, treatment timing, measurement error, and model misspecification "
            "can change the weighted estimate; this is not a randomised result."
        ),
    }


def _fit_robust_ols(
    outcome: np.ndarray,
    design: np.ndarray,
    clusters: np.ndarray | None,
) -> tuple[Any, str]:
    if _STATSMODELS_IMPORT_ERROR is not None or StatsmodelsOLS is None:
        raise AdvancedStatisticsError(
            f"statsmodels analytics extra is required: {_STATSMODELS_IMPORT_ERROR}"
        ) from _STATSMODELS_IMPORT_ERROR
    fitted = StatsmodelsOLS(outcome, design).fit()
    if clusters is not None and len(pd.unique(clusters)) >= 10:
        return fitted.get_robustcov_results(cov_type="cluster", groups=clusters), "cluster"
    return fitted.get_robustcov_results(cov_type="HC1"), "HC1"


def difference_in_differences(
    frame: pd.DataFrame,
    *,
    outcome_column: str,
    treatment_column: str,
    time_column: str,
    policy_date: str | pd.Timestamp,
    cluster_column: str | None = None,
    synthetic_policy_use_case: bool = False,
) -> dict[str, Any]:
    """Estimate a synthetic-policy DiD with pre-trend, event-study, and placebo diagnostics."""

    if not synthetic_policy_use_case:
        raise AdvancedStatisticsError(
            "The live DiD workflow is restricted to an explicitly declared synthetic policy use case"
        )
    required = {outcome_column, treatment_column, time_column}
    if cluster_column:
        required.add(cluster_column)
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise AdvancedStatisticsError(f"DiD input is missing columns: {missing}")
    columns = [outcome_column, treatment_column, time_column] + (
        [cluster_column] if cluster_column else []
    )
    working = frame[columns].dropna().copy()
    working[time_column] = pd.to_datetime(working[time_column], errors="coerce")
    if working[time_column].isna().any():
        raise AdvancedStatisticsError("DiD input contains invalid time values")
    treatment_values = set(pd.unique(working[treatment_column]).tolist())
    if not treatment_values.issubset({0, 1}) or len(treatment_values) != 2:
        raise AdvancedStatisticsError("DiD requires treatment and comparison observations")
    treatment = working[treatment_column].astype(int).to_numpy()
    outcome = pd.to_numeric(working[outcome_column], errors="coerce").to_numpy(dtype=float)
    if not np.all(np.isfinite(outcome)):
        raise AdvancedStatisticsError("DiD outcome must be finite and numeric")
    policy = pd.Timestamp(policy_date)
    unique_times = np.sort(working[time_column].unique())
    if policy.tzinfo is not None:
        policy = policy.tz_localize(None)
    time_values = (
        working[time_column].dt.tz_localize(None)
        if working[time_column].dt.tz is not None
        else working[time_column]
    )
    post = (time_values >= policy).astype(int).to_numpy()
    pre_periods = np.sum(unique_times < np.datetime64(policy))
    post_periods = np.sum(unique_times >= np.datetime64(policy))
    clusters = working[cluster_column].to_numpy() if cluster_column else None
    design = np.column_stack([np.ones(len(working)), treatment, post, treatment * post])
    main_fit, uncertainty = _fit_robust_ols(outcome, design, clusters)
    effect = float(main_fit.params[3])
    effect_standard_error = float(main_fit.bse[3])
    effect_p_value = float(main_fit.pvalues[3])
    pre = post == 0
    parallel_p_value = 1.0
    pretrend_coefficient = 0.0
    if pre.sum() >= 20 and pre_periods >= 3:
        ordered_time = {value: index for index, value in enumerate(unique_times)}
        numeric_time = working[time_column].map(ordered_time).to_numpy(dtype=float)
        centred_pre_time = numeric_time[pre] - np.mean(numeric_time[pre])
        pre_design = np.column_stack(
            [
                np.ones(pre.sum()),
                treatment[pre],
                centred_pre_time,
                treatment[pre] * centred_pre_time,
            ]
        )
        pre_clusters = clusters[pre] if clusters is not None else None
        pre_fit, _ = _fit_robust_ols(outcome[pre], pre_design, pre_clusters)
        pretrend_coefficient = float(pre_fit.params[3])
        parallel_p_value = float(pre_fit.pvalues[3])
    time_index = {value: index for index, value in enumerate(unique_times)}
    policy_index = next(
        (index for index, value in enumerate(unique_times) if value >= np.datetime64(policy)),
        len(unique_times),
    )
    event_time = working[time_column].map(time_index).to_numpy(dtype=int) - policy_index
    event_levels = sorted(set(event_time))
    reference = -1 if -1 in event_levels else max(level for level in event_levels if level < 0)
    time_dummies = []
    for level in unique_times[1:]:
        time_dummies.append((working[time_column].to_numpy() == level).astype(float))
    interaction_levels = [level for level in event_levels if level != reference]
    interactions = [
        (treatment * (event_time == level)).astype(float) for level in interaction_levels
    ]
    event_design = np.column_stack([np.ones(len(working)), treatment, *time_dummies, *interactions])
    event_fit, event_uncertainty = _fit_robust_ols(outcome, event_design, clusters)
    interaction_start = 2 + len(time_dummies)
    event_study = []
    for offset, level in enumerate(interaction_levels):
        coefficient = float(event_fit.params[interaction_start + offset])
        standard_error = float(event_fit.bse[interaction_start + offset])
        event_study.append(
            {
                "event_time": int(level),
                "coefficient": coefficient,
                "standard_error": standard_error,
                "confidence_interval_95": [
                    coefficient - 1.96 * standard_error,
                    coefficient + 1.96 * standard_error,
                ],
                "reference_period": False,
            }
        )
    event_study.append(
        {
            "event_time": int(reference),
            "coefficient": 0.0,
            "standard_error": None,
            "confidence_interval_95": [0.0, 0.0],
            "reference_period": True,
        }
    )
    event_study.sort(key=lambda row: row["event_time"])
    placebo_p_value = 1.0
    placebo_effect = 0.0
    if pre_periods >= 4:
        pre_times = unique_times[unique_times < np.datetime64(policy)]
        placebo_date = pre_times[len(pre_times) // 2]
        placebo_sample = working[working[time_column] < policy].copy()
        placebo_treatment = placebo_sample[treatment_column].astype(int).to_numpy()
        placebo_post = (placebo_sample[time_column].to_numpy() >= placebo_date).astype(int)
        placebo_design = np.column_stack(
            [
                np.ones(len(placebo_sample)),
                placebo_treatment,
                placebo_post,
                placebo_treatment * placebo_post,
            ]
        )
        placebo_clusters = placebo_sample[cluster_column].to_numpy() if cluster_column else None
        placebo_fit, _ = _fit_robust_ols(
            placebo_sample[outcome_column].to_numpy(dtype=float),
            placebo_design,
            placebo_clusters,
        )
        placebo_effect = float(placebo_fit.params[3])
        placebo_p_value = float(placebo_fit.pvalues[3])
    periods_adequate = pre_periods >= 3 and post_periods >= 2
    parallel_supported = parallel_p_value >= 0.05
    placebo_supported = placebo_p_value >= 0.05
    interpretable = periods_adequate and parallel_supported and placebo_supported
    return {
        "status": "implemented" if interpretable else "not_interpretable",
        "interpretation": (
            "conditionally interpretable synthetic-policy DiD estimate"
            if interpretable
            else "not interpretable"
        ),
        "use_case": "synthetic policy-change evaluation",
        "groups": {"treatment": 1, "comparison": 0},
        "periods": {
            "policy_date": policy.date().isoformat(),
            "pre_distinct_periods": int(pre_periods),
            "post_distinct_periods": int(post_periods),
        },
        "estimate": {
            "difference_in_differences": effect,
            "standard_error": effect_standard_error,
            "confidence_interval_95": [
                effect - 1.96 * effect_standard_error,
                effect + 1.96 * effect_standard_error,
            ],
            "p_value": effect_p_value,
            "uncertainty": uncertainty,
        },
        "parallel_trend_assessment": {
            "pre_period_treatment_trend_interaction": pretrend_coefficient,
            "p_value": parallel_p_value,
            "supported_at_5_percent": parallel_supported,
        },
        "placebo_test": {
            "effect": placebo_effect,
            "p_value": placebo_p_value,
            "supported_at_5_percent": placebo_supported,
        },
        "event_study_plot_data": event_study,
        "event_study_uncertainty": event_uncertainty,
        "assumption_decision": {
            "periods_adequate": periods_adequate,
            "parallel_trends_not_rejected": parallel_supported,
            "placebo_null_not_rejected": placebo_supported,
        },
        "causal_status": (
            "conditional synthetic-design estimate; assumptions required"
            if interpretable
            else "no interpretable effect claim"
        ),
        "limitations": [
            "Parallel-trend and placebo tests have finite-sample power limitations.",
            "Concurrent group-specific shocks can invalidate the estimate.",
            "The live workflow is restricted to synthetic policy-change demonstrations.",
        ],
    }
