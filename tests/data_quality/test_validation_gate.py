from __future__ import annotations

import pandas as pd

from naim_risk.data_generation import generate_synthetic_portfolio
from naim_risk.validation import validate_tables


def test_generated_data_passes_quality_gate(test_config):
    result = validate_tables(generate_synthetic_portfolio(test_config))
    assert result.status == "PASS"
    assert result.quality_score == 100
    assert result.publication_allowed


def test_duplicate_account_month_blocks_publication(test_config):
    tables = generate_synthetic_portfolio(test_config)
    performance = tables["monthly_account_performance"]
    tables["monthly_account_performance"] = pd.concat(
        [performance, performance.iloc[[0]]], ignore_index=True
    )
    result = validate_tables(tables)
    assert result.status == "BLOCKED"
    check = next(
        item
        for item in result.checks
        if item.check_id == "monthly_account_performance.unique_account_month"
    )
    assert check.affected_rows == 2


def test_invalid_utilization_is_quarantined(test_config):
    tables = generate_synthetic_portfolio(test_config)
    tables["monthly_account_performance"].loc[0, "utilization"] = 99.0
    result = validate_tables(tables)
    assert result.status == "PASS_WITH_WARNINGS"
    assert len(result.quarantined["monthly_account_performance"]) == 1
    assert (
        len(result.accepted["monthly_account_performance"])
        == len(tables["monthly_account_performance"]) - 1
    )
