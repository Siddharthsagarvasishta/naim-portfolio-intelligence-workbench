from __future__ import annotations

import pandas as pd
import pytest

from naim_risk.metrics import enrich_performance
from naim_risk.vintage import calculate_vintages


def test_cumulative_vintage_loss_rate_uses_cumulative_average_receivables(
    pipeline_data,
) -> None:
    performance = pipeline_data.tables["monthly_account_performance"].copy()
    seeded_loss_index = performance.sort_values(["month", "account_id"]).index[0]
    performance.loc[seeded_loss_index, "chargeoff_amount"] = 100.0
    performance.loc[seeded_loss_index, "recovery_amount"] = 10.0
    master = pipeline_data.tables["customer_account_master"]
    rows = calculate_vintages(performance, master)
    target = next(
        row
        for row in rows
        if row["cumulative_average_receivables"] > 0 and row["cumulative_net_credit_loss"] > 0
    )

    frame = enrich_performance(performance, master)
    frame["vintage"] = pd.to_datetime(frame["origination_date"]).dt.to_period("M").astype(str)
    aligned = frame[
        (frame["vintage"] == target["vintage"])
        & (frame["months_on_book"] <= target["months_on_book"])
    ]
    expected_numerator = float(aligned["chargeoff_amount"].sum() - aligned["recovery_amount"].sum())
    expected_denominator = float(aligned["average_daily_balance"].sum())

    assert target["cumulative_net_credit_loss"] == pytest.approx(expected_numerator)
    assert target["cumulative_average_receivables"] == pytest.approx(expected_denominator)
    assert target["cumulative_net_loss_rate"] == pytest.approx(
        expected_numerator / expected_denominator
    )
    assert target["cumulative_net_loss_rate_unit"] == "ratio"
    assert "cumulative average receivables" in target["denominator_definition"]
