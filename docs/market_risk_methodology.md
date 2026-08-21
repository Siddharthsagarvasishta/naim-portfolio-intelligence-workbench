# Market Risk and Volatility Lab methodology

The Market Risk and Volatility Lab is an optional, isolated module of the **nAIM Portfolio Intelligence Workbench**. It compares quantitative methods, exposes assumptions, and creates reproducible evidence. It is not a trading recommendation system, an investment-advice service, or a statement of maximum possible loss.

## Execution and data-provider contract

The live provider interface is `MarketDataProvider.get_prices(instrument, start_date, end_date, fields) -> MarketPriceFrame`. A `MarketPriceFrame` carries observations plus provider, retrieval time, requested dates and fields, price basis, raw-source SHA-256, missing business dates, cache reference, synthetic-source status, redistribution permission, provider terms, and source notes.

The following providers are executable:

| Provider | Status | Use |
|---|---|---|
| `DeterministicSampleProvider` | Live | Bundled, seeded, redistribution-safe synthetic OHLCV data; no network required |
| `UploadedFileProvider` | Live | CSV, XLSX, or XLSM data with a 50 MB default limit, field validation, date filtering, duplicate-date control, and raw-file hash |
| `StaticMarketDataProvider` | Live | Controlled contract and unit tests |
| `ConfiguredExternalProvider` | Configuration only | Describes a future licensed connector and fails closed when called; it does not pretend to retrieve public data |

Supported instrument types are index, equity, uploaded instrument, and uploaded portfolio return series. Validated periods are one, three, or five trailing years, or a custom period of no more than ten years. The instrument identifier is length- and character-constrained. Requested fields must be selected from open, high, low, close, adjusted close, volume, and return.

The external adapter intentionally contains no credentials or hidden network fallback. A production connector must separately preserve its raw licensed response, cache it, record retrieval metadata, disclose adjusted/unadjusted basis and missing dates, and comply with provider redistribution terms.

## Return preparation

`prepare_returns` selects adjusted close before close when both exist. It calculates simple and logarithmic returns and supports daily, Friday-ending weekly, and month-ending frequency. An uploaded portfolio return series can explicitly declare whether the supplied values are simple or logarithmic returns. Annualisation factors are 252, 52, and 12 respectively.

The evidence reports observations, source missing dates, robust outliers, annualisation, periodic and annualised mean and standard deviation, skewness, excess kurtosis, and the Jarque–Bera statistic and p-value. An outlier is an absolute median/MAD robust z-score above six. Corporate-action review is raised when adjusted and unadjusted daily returns diverge by more than five percentage points, or when a close-only unadjusted series moves by more than 25% in one day. These rules are diagnostics, not automatic corrections.

Prices must be positive. High must be no lower than low, and open and close must be inside the reported daily range. Volatility models use prepared returns, never raw price levels.

## Historical and EWMA volatility

Close-to-close volatility is the sample standard deviation of periodic returns multiplied by the square root of the annualisation factor. Rolling and expanding series preserve their configured observation windows; supported governed examples are 21, 63, 126, and 252. Downside and upside estimators are the annualised root mean squared negative and positive returns respectively.

Field-dependent estimators are only marked implemented when their inputs exist:

- realised volatility requires more than one timestamp per day and a close or adjusted-close field;
- Parkinson requires high and low;
- Garman–Klass requires OHLC;
- Rogers–Satchell requires OHLC.

EWMA uses

```text
variance[t] = lambda * variance[t-1] + (1-lambda) * return[t-1]^2
```

The controlled lambda range is 0.80 to 0.9999. The initial variance is the sample variance of the first 30 observations, or the available shorter sample. Output includes lambda, effective memory `1/(1-lambda)`, half-life, current estimate, one-step forecast, full series, and sensitivity at 0.90, 0.94, 0.97, and the requested lambda.

## ARCH and GARCH

The live implementation fits normal-error ARCH(1) and GARCH(1,1) by maximum likelihood. Returns are scaled to percentage points during optimisation and converted back to return units in evidence. Positive parameters and GARCH stationarity are enforced by smooth parameter transformations; the governing test is `alpha + beta < 1`.

Evidence includes mean, omega, alpha, beta where applicable, numerical-Hessian standard errors, 95% confidence intervals, log likelihood, AIC, BIC, persistence, unconditional variance where defined, optimiser result, gradient norm, variance forecast, annualised volatility forecast, and a normal-error return forecast interval. A failed optimiser or non-stationary result has `status: fit_failed` and no valid forecast. It is never displayed as a successful model.

The shipped implementation does not claim EGARCH, GJR-GARCH, skewed-t errors, or Student-t conditional errors. Those remain unavailable until an optional library and its convergence/diagnostic behavior are independently validated.

Diagnostics use the installed `statsmodels` analytics extra and include ACF of returns and squared returns, Ljung–Box tests on standardised and squared standardised residuals, ARCH LM, residual histogram, normal Q-Q data, standardised residual data, forecast-error data, and convergence metadata. A missing analytics extra returns `dependency_unavailable` rather than fabricated values.

## User-input implied volatility

`implied_volatility` accepts option type, spot, strike, years to expiry, continuously compounded risk-free rate and dividend yield, and an observed option price. It first tests discounted European call or put no-arbitrage bounds. A bracketed Brent solver searches positive volatility and reports convergence, iterations, reconstructed price and reconstruction error.

The calculator returns delta, gamma, vega per unit volatility, theta per year, and rho per unit rate. It assumes European exercise, Black–Scholes lognormal dynamics, constant inputs, and no transaction-cost or liquidity adjustment. It never invents or fetches an option chain.

## Model comparison

Historical, rolling, EWMA, ARCH, and GARCH forecasts are evaluated on a chronological held-out tail. The table reports the latest annualised estimate, one-step and multi-step forecasts, variance MAE, variance RMSE, QLIKE, directional accuracy of variance changes, a forecast-stability coefficient, parameter persistence, and model/diagnostic status. A user-input implied volatility can appear as a comparison row but has null out-of-sample fields unless a corresponding history is actually supplied.

The QLIKE ordering is descriptive for that holdout. The implementation does not declare a universally best model and never selects from in-sample fit alone.

## VaR, Expected Shortfall, and backtesting

`calculate_var_es` returns positive loss magnitudes for historical, parametric normal, fitted parametric Student-t, and EWMA-filtered historical simulation at a controlled confidence between 90% and 100%. Expected Shortfall is the conditional average loss beyond the method's VaR boundary. VaR is explicitly labelled a quantile estimate, not a maximum possible loss.

`backtest_var` accepts aligned realised returns and positive-loss forecasts. It reports breach count and timeline, Kupiec unconditional coverage, Christoffersen independence, and a binomial green/amber/red traffic-light convention. The traffic light is labelled an analytical convention and is not represented as a regulatory classification. The orchestrated lab runs a rolling historical-quantile backtest over a holdout window.

## Regimes and nAIM overlay

`volatility_regimes` classifies rolling annualised volatility by its empirical percentile: calm through the 50th percentile, elevated above the 50th through the 85th, and stressed above the 85th. It also reports rolling z-scores, robust level-change indicators, episode durations, and observation counts.

The optional scenario field is labelled exactly **External risk-regime overlay**. Its causal status is “associational scenario input only.” No market regime is claimed to cause credit or fraud deterioration.

## Exports and provenance

`export_market_risk_bundle` writes a path-safe bundle containing JSON evidence, prepared-return CSV and Parquet, optional raw-price CSV and Parquet, chart-data JSON, a reproducible notebook, a formatted 14-sheet Excel workbook, an editable PowerPoint, and an export manifest with relative paths, byte counts, and SHA-256 hashes. Workbook tabs cover Overview, Price Data, Return Statistics, Historical Volatility, EWMA, ARCH/GARCH evidence, Diagnostics, Implied Volatility, VaR and Expected Shortfall, Backtesting, Model Comparison, Assumptions, Methodology, and Refresh Control. Excel forbids `/` in a sheet name, so the physical tab is `ARCH GARCH`.

PDF is not silently generated. Its manifest status is `not_generated_requires_separate_render_and_visual_validation`, because the directive permits PDF only after render validation. User-supplied source redistribution remains prohibited unless rights are established.

## Callable schemas for API integration

```python
provider.get_prices(
    instrument: str,
    start_date: date,
    end_date: date,
    fields: list[str],
) -> MarketPriceFrame

run_market_risk_lab(
    market: MarketPriceFrame,
    *,
    frequency: Literal["daily", "weekly", "monthly"] = "daily",
    return_type: Literal["simple", "log"] = "log",
    windows: tuple[int, ...] = (21, 63, 126, 252),
    ewma_decay: float = 0.94,
    confidence: float = 0.99,
    option_inputs: dict | None = None,
) -> dict

export_market_risk_bundle(
    analysis: dict,
    destination: str | Path,
    *,
    market: MarketPriceFrame | None = None,
    include_excel: bool = True,
    include_presentation: bool = True,
) -> dict
```

The orchestrated result has top-level keys `schema_version`, `module`, `status`, `source`, `returns`, `historical_volatility`, `ewma`, `conditional_volatility`, `diagnostics`, `implied_volatility`, `model_comparison`, `var_expected_shortfall`, `var_backtesting`, `regimes`, `governance`, and `validation`. The snapshot publication gate requires executable validation to pass and source redistribution permission to be true.

Focused verification:

```text
PYTHONPATH=src .venv/bin/pytest -q tests/unit/test_market_risk_extensions.py
PYTHONPATH=src .venv/bin/ruff check src/naim_risk/market_risk tests/unit/test_market_risk_extensions.py
```

