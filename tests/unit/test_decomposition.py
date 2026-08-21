from __future__ import annotations

import math

import pandas as pd
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from naim_risk.root_cause import decompose_rate


def test_symmetric_decomposition_reconciles_exactly():
    baseline = pd.DataFrame(
        {
            "segment": ["A", "B"],
            "loss": [10.0, 18.0],
            "balance": [1000.0, 1000.0],
        }
    )
    current = pd.DataFrame(
        {
            "segment": ["A", "B"],
            "loss": [18.0, 36.0],
            "balance": [800.0, 1600.0],
        }
    )
    result = decompose_rate(
        baseline,
        current,
        segment_column="segment",
        numerator_column="loss",
        denominator_column="balance",
        scale=10_000,
    )
    assert abs(result["reconciliation_residual"]) < 1e-10
    assert math.isclose(
        result["observed_change"],
        result["mix_contribution"] + result["within_segment_contribution"],
        abs_tol=1e-10,
    )


@given(
    base_a=st.floats(100, 10000, allow_nan=False, allow_infinity=False),
    base_b=st.floats(100, 10000, allow_nan=False, allow_infinity=False),
    current_a=st.floats(100, 10000, allow_nan=False, allow_infinity=False),
    current_b=st.floats(100, 10000, allow_nan=False, allow_infinity=False),
    rate_a0=st.floats(0, 0.5, allow_nan=False, allow_infinity=False),
    rate_b0=st.floats(0, 0.5, allow_nan=False, allow_infinity=False),
    rate_a1=st.floats(0, 0.5, allow_nan=False, allow_infinity=False),
    rate_b1=st.floats(0, 0.5, allow_nan=False, allow_infinity=False),
)
@settings(suppress_health_check=[HealthCheck.too_slow])
def test_decomposition_reconciliation_property(
    base_a,
    base_b,
    current_a,
    current_b,
    rate_a0,
    rate_b0,
    rate_a1,
    rate_b1,
):
    baseline = pd.DataFrame(
        {
            "segment": ["A", "B"],
            "loss": [base_a * rate_a0, base_b * rate_b0],
            "balance": [base_a, base_b],
        }
    )
    current = pd.DataFrame(
        {
            "segment": ["A", "B"],
            "loss": [current_a * rate_a1, current_b * rate_b1],
            "balance": [current_a, current_b],
        }
    )
    result = decompose_rate(
        baseline,
        current,
        segment_column="segment",
        numerator_column="loss",
        denominator_column="balance",
    )
    assert abs(result["reconciliation_residual"]) < 1e-10
