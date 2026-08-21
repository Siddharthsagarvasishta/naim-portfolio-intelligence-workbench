"""Governed advanced-statistics methods with explicit assumptions and diagnostics."""

from naim_risk.advanced.behavioural import run_behavioural_diagnostics
from naim_risk.advanced.causal import (
    difference_in_differences,
    propensity_weighted_comparison,
)
from naim_risk.advanced.changepoint import (
    detect_change_points,
    validate_change_point_method,
)
from naim_risk.advanced.survival import (
    AdvancedStatisticsError,
    kaplan_meier,
    log_rank_test,
    run_survival_analysis,
)

__all__ = [
    "AdvancedStatisticsError",
    "kaplan_meier",
    "log_rank_test",
    "run_survival_analysis",
    "detect_change_points",
    "validate_change_point_method",
    "run_behavioural_diagnostics",
    "difference_in_differences",
    "propensity_weighted_comparison",
]
