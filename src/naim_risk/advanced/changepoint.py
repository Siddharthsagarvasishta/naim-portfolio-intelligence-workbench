"""Robust single level-shift detection with trend and seasonality controls."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np
from scipy import optimize, stats

from naim_risk.advanced.survival import AdvancedStatisticsError


def _huber_loss(residuals: np.ndarray, scale: float) -> float:
    standardised = residuals / max(scale, 1e-12)
    absolute = np.abs(standardised)
    return float(
        np.sum(np.where(absolute <= 1.345, 0.5 * standardised**2, 1.345 * absolute - 0.9045125))
    )


def _robust_linear_fit(values: np.ndarray, scale: float) -> tuple[np.ndarray, tuple[float, float]]:
    positions = np.arange(len(values), dtype=float)
    initial = np.polyfit(positions, values, 1)

    def residuals(parameters: np.ndarray) -> np.ndarray:
        return (values - (parameters[0] + parameters[1] * positions)) / max(scale, 1e-12)

    fitted = optimize.least_squares(
        residuals,
        np.asarray([initial[1], initial[0]]),
        loss="huber",
        f_scale=1.345,
    )
    intercept, slope = fitted.x
    return intercept + slope * positions, (float(intercept), float(slope))


def _seasonal_adjust(values: np.ndarray, period: int | None) -> tuple[np.ndarray, dict[str, Any]]:
    if period is None:
        return values.copy(), {"applied": False, "period": None}
    if period < 2 or period > len(values) // 4:
        raise AdvancedStatisticsError(
            "Seasonal period must be at least 2 and leave at least four complete cycles"
        )
    phases = np.arange(len(values)) % period
    phase_medians = np.asarray([np.median(values[phases == phase]) for phase in range(period)])
    adjusted = values - phase_medians[phases] + np.median(values)
    return adjusted, {
        "applied": True,
        "period": period,
        "method": "phase-median seasonal adjustment",
        "phase_effects": (phase_medians - np.median(values)).tolist(),
    }


def detect_change_points(
    series: Sequence[float] | np.ndarray,
    *,
    min_segment: int = 12,
    seasonal_period: int | None = None,
    significance: float = 0.05,
    minimum_robust_effect: float = 1.5,
) -> dict[str, Any]:
    """Detect one abrupt level shift while distinguishing a linear trend and seasonality."""

    values = np.asarray(series, dtype=float)
    if values.ndim != 1 or len(values) < 2 * min_segment:
        raise AdvancedStatisticsError("Series must be one-dimensional with two complete segments")
    if not np.all(np.isfinite(values)):
        raise AdvancedStatisticsError("Change-point series must contain only finite values")
    if min_segment < 6:
        raise AdvancedStatisticsError("min_segment must be at least 6")
    if not 0.001 <= significance <= 0.20:
        raise AdvancedStatisticsError("significance must be between 0.001 and 0.20")
    adjusted, seasonal = _seasonal_adjust(values, seasonal_period)
    centre = float(np.median(adjusted))
    scale = float(1.4826 * np.median(np.abs(adjusted - centre)))
    if scale <= 1e-12:
        scale = max(float(np.std(adjusted, ddof=1)), 1e-12)
    null_loss = _huber_loss(adjusted - centre, scale)
    linear_fit, (intercept, slope) = _robust_linear_fit(adjusted, scale)
    linear_loss = _huber_loss(adjusted - linear_fit, scale)
    candidates = []
    for position in range(min_segment, len(adjusted) - min_segment + 1):
        before = adjusted[:position]
        after = adjusted[position:]
        before_level = float(np.median(before))
        after_level = float(np.median(after))
        loss = _huber_loss(before - before_level, scale) + _huber_loss(after - after_level, scale)
        test = stats.mannwhitneyu(before, after, alternative="two-sided", method="asymptotic")
        candidates.append(
            {
                "position": position,
                "loss": loss,
                "before_level": before_level,
                "after_level": after_level,
                "raw_p_value": float(test.pvalue),
            }
        )
    best = min(candidates, key=lambda row: row["loss"])
    tests = len(candidates)
    adjusted_p = min(1.0, best["raw_p_value"] * tests)
    n = len(values)
    null_bic = 2 * null_loss + math.log(n)
    linear_bic = 2 * linear_loss + 2 * math.log(n)
    step_bic = 2 * best["loss"] + 3 * math.log(n)
    before_values = adjusted[: best["position"]]
    after_values = adjusted[best["position"] :]
    before_scale = 1.4826 * np.median(np.abs(before_values - best["before_level"]))
    after_scale = 1.4826 * np.median(np.abs(after_values - best["after_level"]))
    within_scale = math.sqrt(
        (len(before_values) * before_scale**2 + len(after_values) * after_scale**2) / len(adjusted)
    )
    robust_effect = abs(best["after_level"] - best["before_level"]) / max(
        within_scale,
        1e-12,
    )
    break_supported = bool(
        adjusted_p < significance
        and robust_effect >= minimum_robust_effect
        and step_bic + 2 < null_bic
        and step_bic + 2 < linear_bic
    )
    linear_preferred = bool(linear_bic + 2 < min(null_bic, step_bic))
    if break_supported:
        classification = "structural_level_shift"
        points = [int(best["position"])]
    elif linear_preferred and abs(slope) * n / scale >= minimum_robust_effect:
        classification = "gradual_trend"
        points = []
    elif seasonal["applied"]:
        classification = "no_break_after_seasonal_adjustment"
        points = []
    else:
        classification = "no_change_detected"
        points = []
    indicators = [position in points for position in range(n)]
    return {
        "status": "implemented",
        "method": "robust single-break scan with Huber loss and BIC trend comparator",
        "classification": classification,
        "change_points": points,
        "indicators": indicators,
        "candidate": {
            "position": int(best["position"]),
            "before_level": float(best["before_level"]),
            "after_level": float(best["after_level"]),
            "level_change": float(best["after_level"] - best["before_level"]),
            "robust_effect": float(robust_effect),
            "raw_mann_whitney_p_value": float(best["raw_p_value"]),
            "scan_adjusted_p_value": float(adjusted_p),
        },
        "model_comparison": {
            "constant_bic": float(null_bic),
            "linear_trend_bic": float(linear_bic),
            "level_shift_bic": float(step_bic),
            "robust_linear_intercept": intercept,
            "robust_linear_slope_per_observation": slope,
        },
        "seasonal_adjustment": seasonal,
        "decision_controls": {
            "minimum_segment": min_segment,
            "significance": significance,
            "multiple_scan_adjustment": "Bonferroni across candidate split positions",
            "minimum_robust_effect": minimum_robust_effect,
            "bic_margin": 2,
        },
        "limitations": [
            "The live method detects at most one abrupt level shift.",
            "A known seasonal period should be supplied when seasonality is plausible.",
            "A gradual trend is reported separately and is not labelled a structural break.",
        ],
    }


def validate_change_point_method(*, seed: int = 73421) -> dict[str, Any]:
    """Execute four deterministic challenge cases required by the method contract."""

    rng = np.random.default_rng(seed)
    observations = 120
    no_change = rng.normal(0, 0.20, observations)
    known_shift = np.r_[
        rng.normal(0, 0.20, observations // 2),
        rng.normal(2.0, 0.20, observations // 2),
    ]
    gradual = np.linspace(0, 2.0, observations) + rng.normal(0, 0.15, observations)
    seasonal = 1.5 * np.sin(2 * np.pi * np.arange(observations) / 12) + rng.normal(
        0, 0.15, observations
    )
    results = {
        "no_change": detect_change_points(no_change),
        "known_shift": detect_change_points(known_shift),
        "gradual_trend": detect_change_points(gradual),
        "seasonal": detect_change_points(seasonal, seasonal_period=12),
    }
    checks = {
        "no_change_not_flagged": results["no_change"]["change_points"] == [],
        "known_shift_detected": bool(results["known_shift"]["change_points"])
        and abs(results["known_shift"]["change_points"][0] - observations // 2) <= 2,
        "gradual_not_called_break": results["gradual_trend"]["change_points"] == [],
        "seasonal_not_called_break": results["seasonal"]["change_points"] == [],
    }
    return {
        "status": "passed" if all(checks.values()) else "failed",
        "seed": seed,
        "checks": checks,
        "classifications": {name: result["classification"] for name, result in results.items()},
        "known_shift_position": results["known_shift"]["change_points"],
    }
