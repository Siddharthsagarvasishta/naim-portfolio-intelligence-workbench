from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from naim_risk.market_risk import (
    ConfiguredExternalProvider,
    DeterministicSampleProvider,
    ExternalProviderConfiguration,
    ExternalProviderUnavailable,
    MarketDataError,
    UploadedFileProvider,
    backtest_var,
    calculate_var_es,
    export_market_risk_bundle,
    fit_conditional_volatility,
    historical_volatility,
    implied_volatility,
    prepare_returns,
    run_market_risk_lab,
)


@pytest.fixture(scope="module")
def market_frame():
    return DeterministicSampleProvider(seed=73421).get_prices(
        "NAIM-DEMO-INDEX",
        date(2022, 1, 1),
        date(2025, 12, 31),
        ["open", "high", "low", "close", "adjusted_close", "volume"],
    )


@pytest.fixture(scope="module")
def market_analysis(market_frame):
    return run_market_risk_lab(market_frame)


def test_deterministic_provider_and_governed_metadata(market_frame):
    repeated = DeterministicSampleProvider(seed=73421).get_prices(
        "NAIM-DEMO-INDEX",
        date(2022, 1, 1),
        date(2025, 12, 31),
        ["open", "high", "low", "close", "adjusted_close", "volume"],
    )
    assert repeated.raw_source_sha256 == market_frame.raw_source_sha256
    assert market_frame.source_is_synthetic is True
    assert market_frame.redistribution_permitted is True
    assert market_frame.price_basis
    assert market_frame.missing_dates == []
    with pytest.raises(MarketDataError, match="supports only"):
        DeterministicSampleProvider().get_prices(
            "UNSUPPORTED",
            date(2024, 1, 1),
            date(2024, 12, 31),
            ["close"],
        )


def test_uploaded_csv_and_configuration_only_external_provider(tmp_path):
    source = tmp_path / "prices.csv"
    dates = pd.bdate_range("2024-01-01", periods=30)
    pd.DataFrame(
        {
            "date": dates,
            "close": np.linspace(100, 110, len(dates)),
            "adjusted_close": np.linspace(100, 110, len(dates)),
        }
    ).to_csv(source, index=False)
    uploaded = UploadedFileProvider(source).get_prices(
        "UPLOADED-1",
        dates.min().date(),
        dates.max().date(),
        ["close", "adjusted_close"],
    )
    assert uploaded.provider == "uploaded_file"
    assert uploaded.redistribution_permitted is False
    assert len(uploaded.raw_source_sha256 or "") == 64
    external = ConfiguredExternalProvider(
        ExternalProviderConfiguration(
            "licensed-feed", tmp_path / "cache", "https://example.invalid"
        )
    )
    with pytest.raises(ExternalProviderUnavailable, match="connector"):
        external.get_prices(
            "ABC",
            date(2024, 1, 1),
            date(2024, 12, 31),
            ["adjusted_close"],
        )


def test_return_preparation_and_historical_estimators(market_frame):
    prepared = prepare_returns(market_frame, frequency="daily", return_type="log")
    assert prepared.summary["observations"] > 1_000
    assert prepared.annualisation_factor == 252
    assert prepared.summary["jarque_bera_statistic"] >= 0
    result = historical_volatility(market_frame, prepared)
    for estimator in [
        "close_to_close",
        "downside",
        "upside",
        "parkinson",
        "garman_klass",
        "rogers_satchell",
    ]:
        assert result["estimators"][estimator]["status"] == "implemented"
        assert result["estimators"][estimator]["annualised_volatility"] >= 0
    assert result["estimators"]["realised"]["status"] == "unavailable_for_selected_data"


def test_arch_and_garch_are_converged_stationary_and_diagnostic(market_analysis):
    for model in ["arch", "garch"]:
        fitted = market_analysis["conditional_volatility"][model]
        assert fitted["status"] == "implemented"
        assert fitted["convergence"]["converged"] is True
        assert fitted["stationary"] is True
        assert fitted["persistence"] < 1
        assert len(fitted["variance_forecast"]) == 10
        assert all(value > 0 for value in fitted["variance_forecast"])
        assert all(row["standard_error"] is not None for row in fitted["parameters"])
    assert market_analysis["diagnostics"]["status"] == "implemented"
    assert "ljung_box_squared_standardised_residuals" in market_analysis["diagnostics"]
    assert market_analysis["validation"]["status"] == "PASS"
    assert market_analysis["validation"]["publication_allowed"] is True


def test_failed_fit_is_not_represented_as_a_valid_forecast():
    rng = np.random.default_rng(73421)
    with pytest.raises(MarketDataError, match="40"):
        fit_conditional_volatility(rng.normal(size=20), model="garch")


def test_implied_volatility_bounds_solver_and_greeks():
    result = implied_volatility(
        option_type="call",
        spot=100,
        strike=100,
        time_to_expiry=1,
        risk_free_rate=0.05,
        dividend_yield=0,
        observed_option_price=10.450583572185565,
    )
    assert result["converged"] is True
    assert result["implied_volatility"] == pytest.approx(0.20, abs=1e-8)
    assert abs(result["price_reconstruction_error"]) < 1e-9
    assert result["greeks"]["gamma"] > 0
    with pytest.raises(MarketDataError, match="no-arbitrage"):
        implied_volatility(
            option_type="call",
            spot=100,
            strike=100,
            time_to_expiry=1,
            risk_free_rate=0,
            dividend_yield=0,
            observed_option_price=101,
        )


def test_var_es_and_backtesting_have_explicit_loss_convention(market_analysis):
    returns = pd.Series([row["log_return"] for row in market_analysis["returns"]["observations"]])
    result = calculate_var_es(returns, confidence=0.99)
    assert result["loss_convention"].startswith("positive")
    for name in [
        "historical",
        "parametric_normal",
        "parametric_student_t",
        "filtered_historical_simulation",
    ]:
        assert result["methods"][name]["var"] >= 0
        assert result["methods"][name]["expected_shortfall"] >= result["methods"][name]["var"]
    forecasts = pd.Series(np.full(len(returns), result["methods"]["historical"]["var"]))
    backtest = backtest_var(returns, forecasts, confidence=0.99)
    assert backtest["status"] == "implemented"
    assert backtest["breach_count"] >= 0
    assert "Analytical" in backtest["traffic_light"]["label"]


def test_market_risk_export_bundle_is_portable_and_structurally_complete(
    tmp_path,
    market_frame,
    market_analysis,
):
    manifest = export_market_risk_bundle(market_analysis, tmp_path, market=market_frame)
    paths = {row["path"] for row in manifest["files"]}
    assert "market_risk_evidence.json" in paths
    assert "nAIM_Market_Risk_Volatility_Lab.xlsx" in paths
    assert "nAIM_Market_Risk_Volatility_Lab.pptx" in paths
    assert "prepared_returns.parquet" in paths
    assert all(not path.startswith("/") for path in paths)
    assert all(len(row["sha256"]) == 64 and row["bytes"] > 0 for row in manifest["files"])
    workbook = pd.ExcelFile(tmp_path / "nAIM_Market_Risk_Volatility_Lab.xlsx")
    assert len(workbook.sheet_names) == 14
    evidence = json.loads((tmp_path / "market_risk_evidence.json").read_text())
    assert evidence["governance"]["trading_recommendation"] is False
    assert manifest["capabilities"]["pdf"].startswith("not_generated")
