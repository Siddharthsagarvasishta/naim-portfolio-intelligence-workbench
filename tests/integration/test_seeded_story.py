from __future__ import annotations

import pandas as pd
import pytest

from naim_risk.config import load_config
from naim_risk.data_generation import generate_synthetic_portfolio
from naim_risk.strategies import compare_strategies


@pytest.mark.slow
@pytest.mark.integration
def test_default_profile_volume_and_seeded_story(tmp_path):
    config = load_config("default", data_root=tmp_path)
    tables = generate_synthetic_portfolio(config)
    performance = tables["monthly_account_performance"]
    master = tables["customer_account_master"]
    truth = tables["_ground_truth_deterioration"].iloc[0]
    assert 500_000 <= len(performance) <= 600_000

    strategy = compare_strategies(
        performance,
        master,
        assumptions=config.scenarios["Baseline"],
        seed=config.seed,
    )
    rows = {row["strategy"]: row for row in strategy["strategies"]}
    champion, challenger = rows["Champion A"], rows["Challenger B"]
    assert challenger["fraud_bps"] < champion["fraud_bps"]
    assert challenger["manual_review_rate"] > champion["manual_review_rate"]
    assert challenger["customer_friction_rate"] > champion["customer_friction_rate"]

    enriched = performance.merge(
        master[["account_id", "product_type", "acquisition_channel", "geography"]],
        on="account_id",
        how="left",
        validate="many_to_one",
    )
    enriched["net_credit_loss"] = enriched["chargeoff_amount"] - enriched["recovery_amount"]
    post_start = pd.Timestamp(truth["expansion_end_month"]) + pd.DateOffset(months=4)
    post_end = post_start + pd.DateOffset(months=5)
    pre_start = post_start - pd.DateOffset(years=1)
    pre_end = post_end - pd.DateOffset(years=1)
    dimensions = ["product_type", "acquisition_channel", "geography"]
    baseline = (
        enriched[(enriched["month"] >= pre_start) & (enriched["month"] <= pre_end)]
        .groupby(dimensions)["net_credit_loss"]
        .sum()
    )
    deterioration = (
        enriched[(enriched["month"] >= post_start) & (enriched["month"] <= post_end)]
        .groupby(dimensions)["net_credit_loss"]
        .sum()
    )
    changes = deterioration.sub(baseline, fill_value=0)
    positive_change = changes[changes > 0].sum()
    focus = (
        truth["concentrated_product"],
        truth["primary_acquisition_channel"],
        truth["concentrated_region"],
    )
    focus_share = changes.loc[focus] / positive_change
    assert focus_share > 0.40
