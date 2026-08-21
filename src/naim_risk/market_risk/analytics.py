"""Executable volatility, option, tail-risk, and regime analytics."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import pandas as pd
from scipy import optimize, stats
from scipy.special import expit, logit

from naim_risk.market_risk.providers import MarketDataError, MarketPriceFrame

Frequency = Literal["daily", "weekly", "monthly"]
ReturnType = Literal["simple", "log"]
_ANNUALISATION = {"daily": 252, "weekly": 52, "monthly": 12}


def _finite_series(values: pd.Series | np.ndarray | list[float], *, minimum: int = 3) -> pd.Series:
    series = pd.Series(values, dtype=float).replace([np.inf, -np.inf], np.nan).dropna()
    if len(series) < minimum:
        raise MarketDataError(f"At least {minimum} finite return observations are required")
    return series.reset_index(drop=True)


def _number(value: float | np.floating[Any] | None) -> float | None:
    if value is None or not np.isfinite(float(value)):
        return None
    return float(value)


def _dated_values(dates: pd.Series, values: pd.Series | np.ndarray) -> list[dict[str, Any]]:
    result = []
    for observed_date, value in zip(dates, values, strict=True):
        result.append(
            {
                "date": pd.Timestamp(observed_date).date().isoformat(),
                "value": _number(value),
            }
        )
    return result


@dataclass
class ReturnPreparation:
    """Prepared return observations and their disclosed transformations."""

    data: pd.DataFrame
    selected_return: str
    frequency: Frequency
    annualisation_factor: int
    price_field: str | None
    summary: dict[str, Any]

    @property
    def returns(self) -> pd.Series:
        return self.data[self.selected_return]

    def evidence(self, *, include_observations: bool = True) -> dict[str, Any]:
        payload = {
            "selected_return": self.selected_return,
            "frequency": self.frequency,
            "annualisation_factor": self.annualisation_factor,
            "price_field": self.price_field,
            "summary": self.summary,
        }
        if include_observations:
            payload["observations"] = [
                {
                    "date": pd.Timestamp(row.date).date().isoformat(),
                    "simple_return": _number(row.simple_return),
                    "log_return": _number(row.log_return),
                }
                for row in self.data.itertuples(index=False)
            ]
        return payload


def _validate_market_frame(market: MarketPriceFrame) -> pd.DataFrame:
    frame = market.data.copy()
    if "date" not in frame:
        raise MarketDataError("Market data must include a date column")
    frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce")
    if frame["date"].isna().any():
        raise MarketDataError("Market data contains invalid dates")
    frame = frame.sort_values("date")
    if frame["date"].duplicated().any():
        raise MarketDataError("Market data contains duplicate timestamps")
    numeric_fields = [field for field in market.fields if field in frame and field != "date"]
    for field in numeric_fields:
        frame[field] = pd.to_numeric(frame[field], errors="coerce")
        if frame[field].isna().all():
            raise MarketDataError(f"Market-data field {field!r} contains no numeric values")
    price_fields = [
        field for field in ["open", "high", "low", "close", "adjusted_close"] if field in frame
    ]
    if price_fields and (frame[price_fields] <= 0).any().any():
        raise MarketDataError("Price fields must be strictly positive")
    if {"high", "low"}.issubset(frame) and (frame["high"] < frame["low"]).any():
        raise MarketDataError("High prices cannot be below low prices")
    if {"open", "high", "low"}.issubset(frame):
        invalid_open = (frame["open"] > frame["high"]) | (frame["open"] < frame["low"])
        if invalid_open.any():
            raise MarketDataError("Open prices must fall between low and high")
    if {"close", "high", "low"}.issubset(frame):
        invalid_close = (frame["close"] > frame["high"]) | (frame["close"] < frame["low"])
        if invalid_close.any():
            raise MarketDataError("Close prices must fall between low and high")
    return frame.reset_index(drop=True)


def prepare_returns(
    market: MarketPriceFrame,
    *,
    frequency: Frequency = "daily",
    return_type: ReturnType = "log",
    direct_return_type: ReturnType = "simple",
) -> ReturnPreparation:
    """Prepare periodic simple and log returns from prices or an uploaded return series."""

    if frequency not in _ANNUALISATION:
        raise MarketDataError(f"Unsupported return frequency: {frequency}")
    if return_type not in {"simple", "log"} or direct_return_type not in {"simple", "log"}:
        raise MarketDataError("Return type must be simple or log")
    frame = _validate_market_frame(market)
    price_field = next(
        (field for field in ["adjusted_close", "close"] if field in frame),
        None,
    )
    direct_return = price_field is None and "return" in frame
    if price_field is None and not direct_return:
        raise MarketDataError("Returns require adjusted_close, close, or an uploaded return field")
    if direct_return:
        periodic = frame[["date", "return"]].dropna().set_index("date")
        if direct_return_type == "simple":
            simple_daily = periodic["return"]
            if (simple_daily <= -1).any():
                raise MarketDataError("Simple returns must be greater than -100%")
            log_daily = np.log1p(simple_daily)
        else:
            log_daily = periodic["return"]
            simple_daily = np.expm1(log_daily)
        base = pd.DataFrame({"simple_return": simple_daily, "log_return": log_daily})
        if frequency != "daily":
            rule = "W-FRI" if frequency == "weekly" else "ME"
            base = pd.DataFrame(
                {
                    "simple_return": (1 + base["simple_return"]).resample(rule).prod() - 1,
                    "log_return": base["log_return"].resample(rule).sum(),
                }
            )
    else:
        prices = frame[["date", price_field]].dropna().set_index("date")[price_field]
        if frequency != "daily":
            rule = "W-FRI" if frequency == "weekly" else "ME"
            prices = prices.resample(rule).last().dropna()
        base = pd.DataFrame(
            {
                "simple_return": prices.pct_change(fill_method=None),
                "log_return": np.log(prices).diff(),
            }
        )
    base = base.replace([np.inf, -np.inf], np.nan).dropna().reset_index()
    if len(base) < 3:
        raise MarketDataError("Selected period yields fewer than three return observations")
    selected = f"{return_type}_return"
    values = base[selected].to_numpy(dtype=float)
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    robust_z = np.zeros(len(values)) if mad == 0 else 0.67448975 * (values - median) / mad
    outlier_positions = np.flatnonzero(np.abs(robust_z) > 6)
    jb = stats.jarque_bera(values)
    corporate_warning = False
    corporate_detail = "No large unadjusted/adjusted divergence detected."
    if {"close", "adjusted_close"}.issubset(frame):
        unadjusted = frame["close"].pct_change(fill_method=None)
        adjusted = frame["adjusted_close"].pct_change(fill_method=None)
        divergent = (unadjusted - adjusted).abs() > 0.05
        corporate_warning = bool(divergent.fillna(False).any())
        if corporate_warning:
            corporate_detail = "Large adjusted-versus-unadjusted return divergence detected; review corporate actions."
    elif price_field == "close" and frame["close"].pct_change(fill_method=None).abs().max() > 0.25:
        corporate_warning = True
        corporate_detail = "A daily unadjusted price move above 25% may reflect a corporate action."
    annualisation = _ANNUALISATION[frequency]
    mean = float(np.mean(values))
    standard_deviation = float(np.std(values, ddof=1))
    summary = {
        "observations": int(len(values)),
        "source_missing_business_dates": int(len(market.missing_dates)),
        "source_missing_date_examples": market.missing_dates[:20],
        "outliers": int(len(outlier_positions)),
        "outlier_dates": [
            pd.Timestamp(base.iloc[position]["date"]).date().isoformat()
            for position in outlier_positions[:20]
        ],
        "outlier_rule": "absolute robust z-score above 6 using median absolute deviation",
        "corporate_action_warning": corporate_warning,
        "corporate_action_detail": corporate_detail,
        "annualisation_factor": annualisation,
        "mean": mean,
        "annualised_mean": mean * annualisation,
        "standard_deviation": standard_deviation,
        "annualised_standard_deviation": standard_deviation * math.sqrt(annualisation),
        "skewness": float(stats.skew(values, bias=False)),
        "excess_kurtosis": float(stats.kurtosis(values, fisher=True, bias=False)),
        "jarque_bera_statistic": float(jb.statistic),
        "jarque_bera_p_value": float(jb.pvalue),
        "price_basis": market.price_basis,
        "return_basis": (
            f"direct uploaded {direct_return_type} return" if direct_return else price_field
        ),
    }
    return ReturnPreparation(base, selected, frequency, annualisation, price_field, summary)


def historical_volatility(
    market: MarketPriceFrame,
    prepared: ReturnPreparation,
    *,
    windows: tuple[int, ...] = (21, 63, 126, 252),
) -> dict[str, Any]:
    """Calculate close-to-close and field-dependent historical estimators."""

    values = _finite_series(prepared.returns)
    factor = prepared.annualisation_factor
    if not windows or any(window < 2 or window > 5_000 for window in windows):
        raise MarketDataError("Volatility windows must be between 2 and 5,000 observations")
    dates = prepared.data["date"]
    rolling: dict[str, Any] = {}
    expanding = prepared.returns.expanding(min_periods=2).std(ddof=1) * math.sqrt(factor)
    for window in dict.fromkeys(windows):
        series = prepared.returns.rolling(window, min_periods=window).std(ddof=1) * math.sqrt(
            factor
        )
        rolling[str(window)] = {
            "window": window,
            "latest": _number(series.iloc[-1]),
            "series": _dated_values(dates, series),
        }
    downside = np.minimum(values.to_numpy(), 0)
    upside = np.maximum(values.to_numpy(), 0)
    estimators: dict[str, dict[str, Any]] = {
        "close_to_close": {
            "status": "implemented",
            "required_fields": [prepared.price_field or "return"],
            "annualised_volatility": float(values.std(ddof=1) * math.sqrt(factor)),
        },
        "downside": {
            "status": "implemented",
            "required_fields": ["return"],
            "annualised_volatility": float(
                np.sqrt(np.mean(np.square(downside))) * math.sqrt(factor)
            ),
            "definition": "square root of mean squared negative returns, annualised",
        },
        "upside": {
            "status": "implemented",
            "required_fields": ["return"],
            "annualised_volatility": float(np.sqrt(np.mean(np.square(upside))) * math.sqrt(factor)),
            "definition": "square root of mean squared positive returns, annualised",
        },
    }
    frame = _validate_market_frame(market)
    daily_counts = frame.groupby(frame["date"].dt.normalize()).size()
    if daily_counts.max() > 1 and (prepared.price_field or "close") in frame:
        price_field = prepared.price_field or "close"
        intraday = frame.set_index("date")[price_field]
        intraday_log_return = np.log(intraday).groupby(intraday.index.normalize()).diff()
        realised_daily = intraday_log_return.pow(2).groupby(intraday.index.normalize()).sum()
        estimators["realised"] = {
            "status": "implemented",
            "required_fields": [price_field, "intraday timestamp"],
            "annualised_volatility": float(np.sqrt(realised_daily.mean() * 252)),
            "daily_series": _dated_values(
                realised_daily.index.to_series(), np.sqrt(realised_daily)
            ),
        }
    else:
        estimators["realised"] = {
            "status": "unavailable_for_selected_data",
            "required_fields": ["intraday timestamp", prepared.price_field or "close"],
            "reason": "Selected data has at most one observation per day.",
        }
    if {"high", "low"}.issubset(frame):
        log_range = np.log(frame["high"] / frame["low"])
        parkinson_variance = float(np.mean(np.square(log_range)) / (4 * math.log(2)))
        estimators["parkinson"] = {
            "status": "implemented",
            "required_fields": ["high", "low"],
            "annualised_volatility": math.sqrt(max(0, factor * parkinson_variance)),
        }
    else:
        estimators["parkinson"] = {
            "status": "unavailable_for_selected_data",
            "required_fields": ["high", "low"],
            "reason": "High and low prices were not both supplied.",
        }
    if {"open", "high", "low", "close"}.issubset(frame):
        log_range = np.log(frame["high"] / frame["low"])
        log_close_open = np.log(frame["close"] / frame["open"])
        gk_variance = float(
            np.mean(0.5 * np.square(log_range) - (2 * math.log(2) - 1) * np.square(log_close_open))
        )
        rs_terms = np.log(frame["high"] / frame["close"]) * np.log(
            frame["high"] / frame["open"]
        ) + np.log(frame["low"] / frame["close"]) * np.log(frame["low"] / frame["open"])
        estimators["garman_klass"] = {
            "status": "implemented",
            "required_fields": ["open", "high", "low", "close"],
            "annualised_volatility": math.sqrt(max(0, factor * gk_variance)),
        }
        estimators["rogers_satchell"] = {
            "status": "implemented",
            "required_fields": ["open", "high", "low", "close"],
            "annualised_volatility": math.sqrt(max(0, factor * float(rs_terms.mean()))),
        }
    else:
        for estimator in ["garman_klass", "rogers_satchell"]:
            estimators[estimator] = {
                "status": "unavailable_for_selected_data",
                "required_fields": ["open", "high", "low", "close"],
                "reason": "Complete OHLC prices were not supplied.",
            }
    return {
        "annualisation_factor": factor,
        "estimators": estimators,
        "rolling": rolling,
        "expanding": {
            "latest": _number(expanding.iloc[-1]),
            "series": _dated_values(dates, expanding),
        },
        "limitations": [
            "Volatility is annualised from observed periodic returns.",
            "Range estimators assume internally consistent positive OHLC prices.",
            "Historical estimates are backward-looking and are not loss limits.",
        ],
    }


def ewma_volatility(
    returns: pd.Series | np.ndarray | list[float],
    *,
    decay: float = 0.94,
    annualisation_factor: int = 252,
    dates: pd.Series | None = None,
) -> dict[str, Any]:
    """Exponentially weighted variance with an explicit backcast initialisation."""

    if not 0.80 <= decay < 0.9999:
        raise MarketDataError("EWMA lambda must be between 0.80 and 0.9999")
    values = _finite_series(returns)
    initial_window = min(30, len(values))
    initial_variance = float(values.iloc[:initial_window].var(ddof=1))
    variances = np.empty(len(values), dtype=float)
    variances[0] = initial_variance
    for position in range(1, len(values)):
        variances[position] = (
            decay * variances[position - 1] + (1 - decay) * values.iloc[position - 1] ** 2
        )
    forecast_variance = decay * variances[-1] + (1 - decay) * values.iloc[-1] ** 2
    sensitivity = []
    for candidate in sorted({0.90, 0.94, 0.97, round(decay, 6)}):
        candidate_variance = initial_variance
        for value in values:
            candidate_variance = candidate * candidate_variance + (1 - candidate) * value**2
        sensitivity.append(
            {
                "lambda": candidate,
                "annualised_forecast_volatility": math.sqrt(
                    candidate_variance * annualisation_factor
                ),
            }
        )
    volatility = np.sqrt(np.maximum(variances, 0) * annualisation_factor)
    if dates is None:
        series: list[dict[str, Any]] = [
            {"observation": position, "value": float(value)}
            for position, value in enumerate(volatility)
        ]
    else:
        usable_dates = pd.Series(dates).iloc[-len(volatility) :].reset_index(drop=True)
        series = _dated_values(usable_dates, volatility)
    return {
        "status": "implemented",
        "lambda": decay,
        "effective_memory_observations": 1 / (1 - decay),
        "half_life_observations": math.log(0.5) / math.log(decay),
        "initialisation_method": f"sample variance of first {initial_window} observations",
        "initial_variance": initial_variance,
        "latest_annualised_volatility": float(volatility[-1]),
        "one_step_variance_forecast": float(forecast_variance),
        "one_step_annualised_volatility_forecast": math.sqrt(
            forecast_variance * annualisation_factor
        ),
        "sensitivity": sensitivity,
        "series": series,
    }


def _garch_transform(theta: np.ndarray, model: str) -> tuple[float, float, float, float]:
    mean = float(theta[0])
    omega = float(np.exp(np.clip(theta[1], -30, 30)))
    alpha = float(0.999 * expit(theta[2]))
    if model == "arch":
        return mean, omega, alpha, 0.0
    remaining = max(0.999 - alpha, 1e-9)
    beta = float(remaining * expit(theta[3]))
    return mean, omega, alpha, beta


def _conditional_variances(
    values: np.ndarray,
    mean: float,
    omega: float,
    alpha: float,
    beta: float,
    initial_variance: float,
) -> np.ndarray:
    variance = np.empty(len(values), dtype=float)
    variance[0] = max(initial_variance, 1e-10)
    for position in range(1, len(values)):
        residual = values[position - 1] - mean
        variance[position] = max(
            omega + alpha * residual**2 + beta * variance[position - 1],
            1e-10,
        )
    return variance


def _negative_garch_log_likelihood(theta: np.ndarray, values: np.ndarray, model: str) -> float:
    mean, omega, alpha, beta = _garch_transform(theta, model)
    initial = float(np.var(values, ddof=1))
    variance = _conditional_variances(values, mean, omega, alpha, beta, initial)
    residual = values - mean
    return float(0.5 * np.sum(np.log(2 * np.pi) + np.log(variance) + residual**2 / variance))


def _finite_difference_hessian(
    function: Any,
    point: np.ndarray,
    *,
    relative_step: float = 1e-4,
) -> np.ndarray:
    size = len(point)
    hessian = np.empty((size, size), dtype=float)
    steps = relative_step * np.maximum(np.abs(point), 1.0)
    base = float(function(point))
    for row in range(size):
        row_step = np.zeros(size)
        row_step[row] = steps[row]
        hessian[row, row] = (
            float(function(point + row_step)) - 2 * base + float(function(point - row_step))
        ) / steps[row] ** 2
        for column in range(row + 1, size):
            column_step = np.zeros(size)
            column_step[column] = steps[column]
            value = (
                float(function(point + row_step + column_step))
                - float(function(point + row_step - column_step))
                - float(function(point - row_step + column_step))
                + float(function(point - row_step - column_step))
            ) / (4 * steps[row] * steps[column])
            hessian[row, column] = value
            hessian[column, row] = value
    return hessian


def _transformation_jacobian(theta: np.ndarray, model: str) -> np.ndarray:
    output_size = 3 if model == "arch" else 4
    jacobian = np.empty((output_size, len(theta)), dtype=float)
    steps = 1e-5 * np.maximum(np.abs(theta), 1.0)
    base = np.asarray(_garch_transform(theta, model)[:output_size])
    for column, step in enumerate(steps):
        shifted = theta.copy()
        shifted[column] += step
        jacobian[:, column] = (
            np.asarray(_garch_transform(shifted, model)[:output_size]) - base
        ) / step
    return jacobian


def fit_conditional_volatility(
    returns: pd.Series | np.ndarray | list[float],
    *,
    model: Literal["arch", "garch"] = "garch",
    annualisation_factor: int = 252,
    forecast_horizon: int = 10,
) -> dict[str, Any]:
    """Fit normal-error ARCH(1) or GARCH(1,1) by constrained maximum likelihood."""

    values_unscaled = _finite_series(returns, minimum=40).to_numpy(dtype=float)
    if model not in {"arch", "garch"}:
        raise MarketDataError("Conditional-volatility model must be arch or garch")
    if not 1 <= forecast_horizon <= 252:
        raise MarketDataError("forecast_horizon must be between 1 and 252")
    values = values_unscaled * 100.0
    sample_variance = max(float(np.var(values, ddof=1)), 1e-6)
    if model == "arch":
        initial = np.asarray(
            [float(np.mean(values)), math.log(sample_variance * 0.90), logit(0.08 / 0.999)]
        )
    else:
        alpha_start = 0.08
        beta_start = 0.88
        initial = np.asarray(
            [
                float(np.mean(values)),
                math.log(sample_variance * (1 - alpha_start - beta_start)),
                logit(alpha_start / 0.999),
                logit(beta_start / (0.999 - alpha_start)),
            ]
        )

    def objective(theta: np.ndarray) -> float:
        return _negative_garch_log_likelihood(theta, values, model)

    result = optimize.minimize(
        objective,
        initial,
        method="L-BFGS-B",
        options={"maxiter": 2_000, "ftol": 1e-12, "gtol": 1e-7, "maxls": 50},
    )
    mean_pct, omega_pct, alpha, beta = _garch_transform(result.x, model)
    conditional_pct = _conditional_variances(
        values,
        mean_pct,
        omega_pct,
        alpha,
        beta,
        sample_variance,
    )
    stationary = alpha + beta < 1
    converged = bool(result.success and np.isfinite(result.fun) and stationary)
    parameter_names = ["mean", "omega", "alpha"] + (["beta"] if model == "garch" else [])
    parameter_values = np.asarray([mean_pct / 100, omega_pct / 10_000, alpha, beta])[
        : len(parameter_names)
    ]
    standard_errors: np.ndarray | None = None
    try:
        theta_covariance = np.linalg.pinv(_finite_difference_hessian(objective, result.x))
        jacobian = _transformation_jacobian(result.x, model)
        covariance = jacobian @ theta_covariance @ jacobian.T
        scale = np.asarray([0.01, 0.0001, 1.0, 1.0])[: len(parameter_names)]
        covariance = np.diag(scale) @ covariance @ np.diag(scale)
        diagonal = np.diag(covariance)
        if np.all(np.isfinite(diagonal)) and np.all(diagonal >= 0):
            standard_errors = np.sqrt(diagonal)
    except (np.linalg.LinAlgError, ValueError, FloatingPointError):
        standard_errors = None
    parameters = []
    for position, (name, value) in enumerate(zip(parameter_names, parameter_values, strict=True)):
        error = None if standard_errors is None else float(standard_errors[position])
        parameters.append(
            {
                "name": name,
                "estimate": float(value),
                "standard_error": error,
                "confidence_interval_95": (
                    None
                    if error is None
                    else [float(value - 1.96 * error), float(value + 1.96 * error)]
                ),
            }
        )
    forecast_pct = []
    first = omega_pct + alpha * (values[-1] - mean_pct) ** 2 + beta * conditional_pct[-1]
    forecast_pct.append(max(first, 1e-10))
    for _ in range(1, forecast_horizon):
        forecast_pct.append(max(omega_pct + (alpha + beta) * forecast_pct[-1], 1e-10))
    forecast_variance = np.asarray(forecast_pct) / 10_000
    standardised = (values - mean_pct) / np.sqrt(conditional_pct)
    observations = len(values)
    parameter_count = len(parameter_names)
    log_likelihood = -float(result.fun)
    unconditional = omega_pct / (1 - alpha - beta) / 10_000 if stationary else None
    return {
        "status": "implemented" if converged else "fit_failed",
        "model": "ARCH(1)" if model == "arch" else "GARCH(1,1)",
        "error_distribution": "normal",
        "parameters": parameters,
        "log_likelihood": log_likelihood,
        "aic": 2 * parameter_count - 2 * log_likelihood,
        "bic": math.log(observations) * parameter_count - 2 * log_likelihood,
        "persistence": alpha + beta,
        "unconditional_variance": unconditional,
        "stationarity_condition": "alpha + beta < 1",
        "stationary": stationary,
        "convergence": {
            "converged": converged,
            "optimizer_success": bool(result.success),
            "message": str(result.message),
            "iterations": int(getattr(result, "nit", 0)),
            "gradient_norm": _number(np.linalg.norm(getattr(result, "jac", np.asarray([np.nan])))),
        },
        "variance_forecast": forecast_variance.tolist() if converged else None,
        "annualised_volatility_forecast": (
            np.sqrt(forecast_variance * annualisation_factor).tolist() if converged else None
        ),
        "return_forecast_interval_95": (
            [
                [
                    float(mean_pct / 100 - 1.96 * math.sqrt(value)),
                    float(mean_pct / 100 + 1.96 * math.sqrt(value)),
                ]
                for value in forecast_variance
            ]
            if converged
            else None
        ),
        "conditional_variance": (conditional_pct / 10_000).tolist(),
        "standardised_residuals": standardised.tolist(),
        "limitations": [
            "Normal conditional errors are assumed.",
            "Parameters are fitted to returns scaled to percentage points for numerical stability.",
            "A failed or non-stationary fit is returned with status fit_failed and no valid forecast.",
        ],
    }


def volatility_diagnostics(
    returns: pd.Series | np.ndarray | list[float],
    fitted_model: dict[str, Any],
    *,
    lags: int = 10,
) -> dict[str, Any]:
    """Residual and conditional-heteroskedasticity diagnostics with chart-ready data."""

    values = _finite_series(returns, minimum=max(20, lags + 5)).to_numpy(dtype=float)
    if fitted_model.get("status") != "implemented":
        return {
            "status": "unavailable",
            "reason": "Diagnostics require a converged conditional-volatility model.",
            "convergence": fitted_model.get("convergence"),
        }
    standardised = np.asarray(fitted_model["standardised_residuals"], dtype=float)
    try:
        from statsmodels.stats.diagnostic import acorr_ljungbox, het_arch
        from statsmodels.tsa.stattools import acf
    except (ImportError, ModuleNotFoundError) as exc:
        return {
            "status": "dependency_unavailable",
            "reason": f"statsmodels analytics extra is required: {exc}",
        }
    effective_lags = min(lags, max(1, len(values) // 5))
    return_acf = acf(values, nlags=effective_lags, fft=True)
    squared_acf = acf(np.square(values), nlags=effective_lags, fft=True)
    residual_lb = acorr_ljungbox(standardised, lags=[effective_lags], return_df=True).iloc[0]
    squared_lb = acorr_ljungbox(
        np.square(standardised), lags=[effective_lags], return_df=True
    ).iloc[0]
    arch_lm = het_arch(standardised, nlags=effective_lags)
    counts, edges = np.histogram(standardised, bins="auto")
    probability_points = (np.arange(1, len(standardised) + 1) - 0.5) / len(standardised)
    theoretical = stats.norm.ppf(probability_points)
    ordered = np.sort(standardised)
    conditional_variance = np.asarray(fitted_model["conditional_variance"], dtype=float)
    forecast_errors = np.square(values - np.mean(values)) - conditional_variance
    return {
        "status": "implemented",
        "lags": effective_lags,
        "acf_returns": [
            {"lag": index, "value": float(value)} for index, value in enumerate(return_acf)
        ],
        "acf_squared_returns": [
            {"lag": index, "value": float(value)} for index, value in enumerate(squared_acf)
        ],
        "ljung_box_standardised_residuals": {
            "statistic": float(residual_lb["lb_stat"]),
            "p_value": float(residual_lb["lb_pvalue"]),
        },
        "ljung_box_squared_standardised_residuals": {
            "statistic": float(squared_lb["lb_stat"]),
            "p_value": float(squared_lb["lb_pvalue"]),
        },
        "arch_lm": {
            "statistic": float(arch_lm[0]),
            "p_value": float(arch_lm[1]),
            "f_statistic": float(arch_lm[2]),
            "f_p_value": float(arch_lm[3]),
        },
        "residual_histogram": {
            "bin_edges": edges.tolist(),
            "counts": counts.tolist(),
        },
        "qq_plot": [
            {"theoretical": float(expected), "observed": float(observed)}
            for expected, observed in zip(theoretical, ordered, strict=True)
        ],
        "standardised_residual_plot": standardised.tolist(),
        "forecast_error_plot": forecast_errors.tolist(),
        "convergence": fitted_model["convergence"],
        "diagnostic_status": (
            "review"
            if residual_lb["lb_pvalue"] < 0.05
            or squared_lb["lb_pvalue"] < 0.05
            or arch_lm[1] < 0.05
            else "no_issue_detected"
        ),
    }


def _black_scholes_price(
    option_type: str,
    spot: float,
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float,
    dividend_yield: float,
    volatility: float,
) -> float:
    discount_r = math.exp(-risk_free_rate * time_to_expiry)
    discount_q = math.exp(-dividend_yield * time_to_expiry)
    root_time = math.sqrt(time_to_expiry)
    d1 = (
        math.log(spot / strike)
        + (risk_free_rate - dividend_yield + 0.5 * volatility**2) * time_to_expiry
    ) / (volatility * root_time)
    d2 = d1 - volatility * root_time
    if option_type == "call":
        return spot * discount_q * stats.norm.cdf(d1) - strike * discount_r * stats.norm.cdf(d2)
    return strike * discount_r * stats.norm.cdf(-d2) - spot * discount_q * stats.norm.cdf(-d1)


def implied_volatility(
    *,
    option_type: Literal["call", "put"],
    spot: float,
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float,
    dividend_yield: float,
    observed_option_price: float,
) -> dict[str, Any]:
    """Solve Black--Scholes implied volatility after checking no-arbitrage bounds."""

    if option_type not in {"call", "put"}:
        raise MarketDataError("option_type must be call or put")
    if spot <= 0 or strike <= 0 or time_to_expiry <= 0 or observed_option_price < 0:
        raise MarketDataError("Spot, strike, and expiry must be positive; price cannot be negative")
    discount_r = math.exp(-risk_free_rate * time_to_expiry)
    discount_q = math.exp(-dividend_yield * time_to_expiry)
    if option_type == "call":
        lower = max(0.0, spot * discount_q - strike * discount_r)
        upper = spot * discount_q
    else:
        lower = max(0.0, strike * discount_r - spot * discount_q)
        upper = strike * discount_r
    tolerance = 1e-10 * max(spot, strike, 1)
    if observed_option_price < lower - tolerance or observed_option_price > upper + tolerance:
        raise MarketDataError(
            f"Observed option price violates no-arbitrage bounds [{lower:.8f}, {upper:.8f}]"
        )
    if observed_option_price <= lower + tolerance:
        volatility = 1e-8
        converged = True
        iterations = 0
    elif observed_option_price >= upper - tolerance:
        raise MarketDataError("Observed option price is at the finite-volatility upper bound")
    else:

        def objective(sigma: float) -> float:
            return (
                _black_scholes_price(
                    option_type,
                    spot,
                    strike,
                    time_to_expiry,
                    risk_free_rate,
                    dividend_yield,
                    sigma,
                )
                - observed_option_price
            )

        root, solver = optimize.brentq(
            objective,
            1e-8,
            8.0,
            xtol=1e-12,
            rtol=1e-12,
            maxiter=200,
            full_output=True,
        )
        volatility = float(root)
        converged = bool(solver.converged)
        iterations = int(solver.iterations)
    reconstructed = _black_scholes_price(
        option_type,
        spot,
        strike,
        time_to_expiry,
        risk_free_rate,
        dividend_yield,
        volatility,
    )
    root_time = math.sqrt(time_to_expiry)
    d1 = (
        math.log(spot / strike)
        + (risk_free_rate - dividend_yield + 0.5 * volatility**2) * time_to_expiry
    ) / (max(volatility, 1e-12) * root_time)
    d2 = d1 - volatility * root_time
    normal_density = stats.norm.pdf(d1)
    if option_type == "call":
        delta = discount_q * stats.norm.cdf(d1)
        theta = (
            -spot * discount_q * normal_density * volatility / (2 * root_time)
            - risk_free_rate * strike * discount_r * stats.norm.cdf(d2)
            + dividend_yield * spot * discount_q * stats.norm.cdf(d1)
        )
        rho = strike * time_to_expiry * discount_r * stats.norm.cdf(d2)
    else:
        delta = discount_q * (stats.norm.cdf(d1) - 1)
        theta = (
            -spot * discount_q * normal_density * volatility / (2 * root_time)
            + risk_free_rate * strike * discount_r * stats.norm.cdf(-d2)
            - dividend_yield * spot * discount_q * stats.norm.cdf(-d1)
        )
        rho = -strike * time_to_expiry * discount_r * stats.norm.cdf(-d2)
    gamma = discount_q * normal_density / (spot * max(volatility, 1e-12) * root_time)
    vega = spot * discount_q * normal_density * root_time
    return {
        "status": "implemented" if converged else "fit_failed",
        "implied_volatility": volatility if converged else None,
        "solver_method": "Brent bracketed root finder",
        "converged": converged,
        "iterations": iterations,
        "no_arbitrage_bounds": {"lower": lower, "upper": upper},
        "reconstructed_price": reconstructed,
        "price_reconstruction_error": reconstructed - observed_option_price,
        "greeks": {
            "delta": float(delta),
            "gamma": float(gamma),
            "vega_per_unit_volatility": float(vega),
            "theta_per_year": float(theta),
            "rho_per_unit_rate": float(rho),
        },
        "inputs": {
            "option_type": option_type,
            "spot": spot,
            "strike": strike,
            "time_to_expiry_years": time_to_expiry,
            "risk_free_rate_continuous": risk_free_rate,
            "dividend_yield_continuous": dividend_yield,
            "observed_option_price": observed_option_price,
        },
        "assumptions": [
            "European exercise and Black--Scholes lognormal dynamics.",
            "Constant volatility, risk-free rate, and dividend yield through expiry.",
            "No transaction costs or liquidity adjustment.",
            "The option price is user supplied; no option chain is inferred or fetched.",
        ],
    }


def calculate_var_es(
    returns: pd.Series | np.ndarray | list[float],
    *,
    confidence: float = 0.99,
    forecast_volatility: float | None = None,
) -> dict[str, Any]:
    """Estimate one-period positive-loss VaR and Expected Shortfall by four methods."""

    if not 0.90 <= confidence < 1:
        raise MarketDataError("VaR confidence must be in [0.90, 1.0)")
    values = _finite_series(returns, minimum=30).to_numpy(dtype=float)
    tail_probability = 1 - confidence
    mean = float(np.mean(values))
    standard_deviation = float(np.std(values, ddof=1))
    historical_quantile = float(np.quantile(values, tail_probability))
    historical_tail = values[values <= historical_quantile]
    z_score = float(stats.norm.ppf(tail_probability))
    normal_quantile = mean + standard_deviation * z_score
    normal_es_return = mean - standard_deviation * stats.norm.pdf(z_score) / tail_probability
    methods: dict[str, Any] = {
        "historical": {
            "var": max(0.0, -historical_quantile),
            "expected_shortfall": max(0.0, -float(np.mean(historical_tail))),
            "tail_observations": int(len(historical_tail)),
        },
        "parametric_normal": {
            "var": max(0.0, -normal_quantile),
            "expected_shortfall": max(0.0, -float(normal_es_return)),
            "parameters": {"mean": mean, "standard_deviation": standard_deviation},
        },
    }
    try:
        degrees, location, scale = stats.t.fit(values)
        student_quantile = float(stats.t.ppf(tail_probability, degrees, loc=location, scale=scale))
        standard_tail = stats.t.expect(
            lambda value: value,
            args=(degrees,),
            lb=-np.inf,
            ub=stats.t.ppf(tail_probability, degrees),
            conditional=True,
        )
        student_es_return = float(location + scale * standard_tail)
        methods["parametric_student_t"] = {
            "status": "implemented" if degrees > 2 else "review",
            "var": max(0.0, -student_quantile),
            "expected_shortfall": max(0.0, -student_es_return),
            "parameters": {
                "degrees_of_freedom": float(degrees),
                "location": float(location),
                "scale": float(scale),
            },
            "warning": None
            if degrees > 2
            else "Fitted degrees of freedom imply infinite variance.",
        }
    except (ValueError, FloatingPointError, RuntimeError) as exc:
        methods["parametric_student_t"] = {
            "status": "fit_failed",
            "reason": str(exc),
        }
    ewma = ewma_volatility(values, annualisation_factor=1)
    current_volatility = (
        float(forecast_volatility)
        if forecast_volatility is not None
        else math.sqrt(float(ewma["one_step_variance_forecast"]))
    )
    if current_volatility <= 0:
        raise MarketDataError("Forecast volatility must be positive")
    conditional_volatility = np.sqrt(
        np.maximum(
            np.asarray([row["value"] for row in ewma["series"]], dtype=float) ** 2,
            1e-16,
        )
    )
    standardised = values / conditional_volatility
    filtered_returns = standardised * current_volatility
    filtered_quantile = float(np.quantile(filtered_returns, tail_probability))
    filtered_tail = filtered_returns[filtered_returns <= filtered_quantile]
    methods["filtered_historical_simulation"] = {
        "var": max(0.0, -filtered_quantile),
        "expected_shortfall": max(0.0, -float(np.mean(filtered_tail))),
        "volatility_forecast": current_volatility,
        "filter": "EWMA lambda 0.94",
    }
    return {
        "status": "implemented",
        "confidence": confidence,
        "horizon": "one return period",
        "loss_convention": "positive number denotes loss magnitude",
        "methods": methods,
        "warning": "VaR is a quantile estimate, not the maximum possible loss.",
    }


def backtest_var(
    returns: pd.Series | np.ndarray | list[float],
    var_forecasts: pd.Series | np.ndarray | list[float],
    *,
    confidence: float = 0.99,
    dates: pd.Series | None = None,
) -> dict[str, Any]:
    """Kupiec and Christoffersen tests for a positive-loss VaR forecast series."""

    if not 0.90 <= confidence < 1:
        raise MarketDataError("Backtest confidence must be in [0.90, 1.0)")
    observed = np.asarray(returns, dtype=float)
    forecasts = np.asarray(var_forecasts, dtype=float)
    if observed.shape != forecasts.shape:
        raise MarketDataError("Returns and VaR forecasts must have identical lengths")
    valid = np.isfinite(observed) & np.isfinite(forecasts) & (forecasts >= 0)
    observed = observed[valid]
    forecasts = forecasts[valid]
    if len(observed) < 30:
        raise MarketDataError("At least 30 aligned observations are required for VaR backtesting")
    breaches = observed < -forecasts
    count = int(breaches.sum())
    observations = len(observed)
    expected_probability = 1 - confidence
    observed_probability = count / observations
    epsilon = 1e-12
    p_hat = float(np.clip(observed_probability, epsilon, 1 - epsilon))
    p_expected = float(np.clip(expected_probability, epsilon, 1 - epsilon))
    log_null = (observations - count) * math.log(1 - p_expected) + count * math.log(p_expected)
    log_alternative = (observations - count) * math.log(1 - p_hat) + count * math.log(p_hat)
    kupiec_lr = max(0.0, -2 * (log_null - log_alternative))
    transitions = {(0, 0): 0, (0, 1): 0, (1, 0): 0, (1, 1): 0}
    for previous, current in zip(breaches[:-1], breaches[1:], strict=True):
        transitions[(int(previous), int(current))] += 1
    n00, n01 = transitions[(0, 0)], transitions[(0, 1)]
    n10, n11 = transitions[(1, 0)], transitions[(1, 1)]
    pi0 = n01 / max(n00 + n01, 1)
    pi1 = n11 / max(n10 + n11, 1)
    pi = (n01 + n11) / max(n00 + n01 + n10 + n11, 1)

    def bernoulli_log_likelihood(successes: int, failures: int, probability: float) -> float:
        probability = float(np.clip(probability, epsilon, 1 - epsilon))
        return successes * math.log(probability) + failures * math.log(1 - probability)

    independent_log = bernoulli_log_likelihood(n01 + n11, n00 + n10, pi)
    dependent_log = bernoulli_log_likelihood(n01, n00, pi0) + bernoulli_log_likelihood(
        n11, n10, pi1
    )
    independence_lr = max(0.0, -2 * (independent_log - dependent_log))
    green_limit = int(stats.binom.ppf(0.95, observations, expected_probability))
    amber_limit = int(stats.binom.ppf(0.9999, observations, expected_probability))
    traffic_light = "green" if count <= green_limit else "amber" if count <= amber_limit else "red"
    if dates is None:
        timeline = [int(index) for index in np.flatnonzero(breaches)]
    else:
        usable_dates = pd.Series(dates)[valid].reset_index(drop=True)
        timeline = [
            pd.Timestamp(usable_dates.iloc[index]).date().isoformat()
            for index in np.flatnonzero(breaches)
        ]
    return {
        "status": "implemented",
        "observations": observations,
        "breach_count": count,
        "expected_breach_probability": expected_probability,
        "observed_breach_rate": observed_probability,
        "breach_timeline": timeline,
        "kupiec_unconditional_coverage": {
            "statistic": kupiec_lr,
            "p_value": float(stats.chi2.sf(kupiec_lr, 1)),
        },
        "christoffersen_independence": {
            "statistic": independence_lr,
            "p_value": float(stats.chi2.sf(independence_lr, 1)),
            "transition_counts": {
                f"{left}{right}": value for (left, right), value in transitions.items()
            },
        },
        "traffic_light": {
            "status": traffic_light,
            "green_max_breaches": green_limit,
            "amber_max_breaches": amber_limit,
            "label": "Analytical binomial convention; not a regulatory classification.",
        },
    }


def compare_volatility_models(
    returns: pd.Series | np.ndarray | list[float],
    *,
    annualisation_factor: int = 252,
    rolling_window: int = 63,
    test_fraction: float = 0.20,
    implied_volatility_value: float | None = None,
) -> dict[str, Any]:
    """Compare forecasts on a held-out tail rather than in-sample fit alone."""

    values = _finite_series(returns, minimum=max(120, rolling_window + 40)).to_numpy(dtype=float)
    if not 0.10 <= test_fraction <= 0.40:
        raise MarketDataError("test_fraction must be between 0.10 and 0.40")
    split = max(80, int(len(values) * (1 - test_fraction)))
    train, test = values[:split], values[split:]
    actual_variance = np.square(test)
    forecasts: dict[str, np.ndarray] = {}
    forecasts["historical"] = np.full(len(test), np.var(train, ddof=1))
    rolling_history = list(train)
    rolling_forecast = []
    for value in test:
        rolling_forecast.append(float(np.var(rolling_history[-rolling_window:], ddof=1)))
        rolling_history.append(float(value))
    forecasts["rolling"] = np.asarray(rolling_forecast)
    ewma_variance = float(np.var(train[: min(30, len(train))], ddof=1))
    for value in train:
        ewma_variance = 0.94 * ewma_variance + 0.06 * value**2
    ewma_forecast = []
    for value in test:
        ewma_forecast.append(ewma_variance)
        ewma_variance = 0.94 * ewma_variance + 0.06 * value**2
    forecasts["ewma"] = np.asarray(ewma_forecast)
    fitted_models: dict[str, dict[str, Any]] = {}
    for model_name in ["arch", "garch"]:
        fitted = fit_conditional_volatility(
            train, model=model_name, annualisation_factor=annualisation_factor
        )
        fitted_models[model_name] = fitted
        if fitted["status"] != "implemented":
            continue
        parameters = {row["name"]: row["estimate"] for row in fitted["parameters"]}
        mean = parameters["mean"]
        omega = parameters["omega"]
        alpha = parameters["alpha"]
        beta = parameters.get("beta", 0.0)
        variance = fitted["conditional_variance"][-1]
        last_return = train[-1]
        model_forecast = []
        for value in test:
            variance = omega + alpha * (last_return - mean) ** 2 + beta * variance
            model_forecast.append(max(variance, 1e-16))
            last_return = value
        forecasts[model_name] = np.asarray(model_forecast)
    rows = []
    epsilon = 1e-16
    for name, forecast in forecasts.items():
        errors = forecast - actual_variance
        direction_actual = np.sign(np.diff(actual_variance))
        direction_forecast = np.sign(np.diff(forecast))
        rows.append(
            {
                "model": name,
                "latest_annualised_volatility": float(
                    math.sqrt(forecast[-1] * annualisation_factor)
                ),
                "one_step_forecast": float(math.sqrt(forecast[-1] * annualisation_factor)),
                "multi_step_forecast": (
                    fitted_models[name]["annualised_volatility_forecast"]
                    if name in fitted_models and fitted_models[name]["status"] == "implemented"
                    else [float(math.sqrt(forecast[-1] * annualisation_factor))] * 10
                ),
                "out_of_sample_mae_variance": float(np.mean(np.abs(errors))),
                "out_of_sample_rmse_variance": float(np.sqrt(np.mean(np.square(errors)))),
                "out_of_sample_qlike": float(
                    np.mean(
                        np.log(np.maximum(forecast, epsilon))
                        + actual_variance / np.maximum(forecast, epsilon)
                    )
                ),
                "directional_accuracy_variance_change": float(
                    np.mean(direction_actual == direction_forecast)
                ),
                "model_stability": float(
                    np.std(np.sqrt(forecast)) / max(np.mean(np.sqrt(forecast)), epsilon)
                ),
                "parameter_persistence": (
                    fitted_models[name]["persistence"] if name in fitted_models else None
                ),
                "diagnostic_status": (
                    fitted_models[name]["status"] if name in fitted_models else "non_parametric"
                ),
            }
        )
    if implied_volatility_value is not None:
        if implied_volatility_value <= 0:
            raise MarketDataError("Implied volatility comparison value must be positive")
        rows.append(
            {
                "model": "implied_volatility_user_input",
                "latest_annualised_volatility": float(implied_volatility_value),
                "one_step_forecast": None,
                "multi_step_forecast": None,
                "out_of_sample_mae_variance": None,
                "out_of_sample_rmse_variance": None,
                "out_of_sample_qlike": None,
                "directional_accuracy_variance_change": None,
                "model_stability": None,
                "parameter_persistence": None,
                "diagnostic_status": "not_backtested_user_input",
            }
        )
    eligible = [row for row in rows if row["out_of_sample_qlike"] is not None]
    ranking = sorted(eligible, key=lambda row: row["out_of_sample_qlike"])
    return {
        "status": "implemented",
        "training_observations": int(len(train)),
        "test_observations": int(len(test)),
        "test_split": "chronological held-out tail",
        "models": rows,
        "qlike_ranking": [row["model"] for row in ranking],
        "selection_warning": (
            "Ranking is descriptive for this held-out period; no model is selected from in-sample fit alone."
        ),
    }


def volatility_regimes(
    returns: pd.Series | np.ndarray | list[float],
    *,
    dates: pd.Series | None = None,
    window: int = 21,
    annualisation_factor: int = 252,
) -> dict[str, Any]:
    """Classify rolling-volatility percentiles and flag robust level changes."""

    values = _finite_series(returns, minimum=max(40, window + 10))
    if not 10 <= window < len(values):
        raise MarketDataError("Regime window must be at least 10 and shorter than the series")
    rolling = values.rolling(window, min_periods=window).std(ddof=1) * math.sqrt(
        annualisation_factor
    )
    valid = rolling.dropna()
    percentiles = valid.rank(pct=True)
    mean = valid.rolling(max(window, 20), min_periods=max(window, 20)).mean()
    standard_deviation = valid.rolling(max(window, 20), min_periods=max(window, 20)).std(ddof=1)
    z_score = (valid - mean) / standard_deviation.replace(0, np.nan)
    labels = pd.Series(
        np.where(
            percentiles <= 0.50, "calm", np.where(percentiles <= 0.85, "elevated", "stressed")
        ),
        index=valid.index,
    )
    median = float(valid.median())
    mad = float(np.median(np.abs(valid - median)))
    level = valid.to_numpy()
    shift_flags = np.zeros(len(valid), dtype=bool)
    if mad > 0:
        before = pd.Series(level).rolling(window, min_periods=window).median().shift(1)
        after = (
            pd.Series(level[::-1]).rolling(window, min_periods=window).median().shift(1).iloc[::-1]
        )
        shift_flags = ((after - before).abs() > 3 * mad).fillna(False).to_numpy()
    positions = valid.index.to_numpy()
    if dates is None:
        date_values: list[Any] = positions.tolist()
    else:
        source_dates = pd.Series(dates).reset_index(drop=True)
        date_values = [
            pd.Timestamp(source_dates.iloc[position]).date().isoformat() for position in positions
        ]
    series = [
        {
            "date": date_value,
            "annualised_volatility": float(volatility),
            "percentile": float(percentile),
            "rolling_z_score": _number(score),
            "regime": str(regime),
            "change_point_indicator": bool(shift),
        }
        for date_value, volatility, percentile, score, regime, shift in zip(
            date_values,
            valid,
            percentiles,
            z_score.reindex(valid.index),
            labels,
            shift_flags,
            strict=True,
        )
    ]
    durations: list[dict[str, Any]] = []
    start = 0
    label_values = labels.tolist()
    for position in range(1, len(label_values) + 1):
        if position == len(label_values) or label_values[position] != label_values[start]:
            durations.append(
                {
                    "regime": label_values[start],
                    "start": date_values[start],
                    "end": date_values[position - 1],
                    "observations": position - start,
                }
            )
            start = position
    summary = pd.Series(label_values).value_counts().rename_axis("regime").to_dict()
    return {
        "status": "implemented",
        "method": "rolling volatility empirical percentiles",
        "thresholds": {"calm_max_percentile": 0.50, "elevated_max_percentile": 0.85},
        "series": series,
        "duration_summary": durations,
        "observation_counts": {str(key): int(value) for key, value in summary.items()},
        "scenario_overlay": {
            "label": "External risk-regime overlay",
            "causal_status": "associational scenario input only",
            "warning": "A market regime is not asserted to cause credit or fraud deterioration.",
        },
    }


def run_market_risk_lab(
    market: MarketPriceFrame,
    *,
    frequency: Frequency = "daily",
    return_type: ReturnType = "log",
    windows: tuple[int, ...] = (21, 63, 126, 252),
    ewma_decay: float = 0.94,
    confidence: float = 0.99,
    option_inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the offline-capable analytical lab and return JSON-serialisable evidence."""

    prepared = prepare_returns(market, frequency=frequency, return_type=return_type)
    values = prepared.returns
    arch = fit_conditional_volatility(
        values,
        model="arch",
        annualisation_factor=prepared.annualisation_factor,
    )
    garch = fit_conditional_volatility(
        values,
        model="garch",
        annualisation_factor=prepared.annualisation_factor,
    )
    implied = (
        implied_volatility(**option_inputs)
        if option_inputs
        else {
            "status": "not_requested",
            "reason": "No user-supplied option price and contract inputs were provided.",
        }
    )
    comparison = compare_volatility_models(
        values,
        annualisation_factor=prepared.annualisation_factor,
        rolling_window=min(63, max(20, len(values) // 4)),
        implied_volatility_value=implied.get("implied_volatility"),
    )
    backtest_window = min(252, max(60, len(values) // 4))
    backtest_returns = values.iloc[backtest_window:].reset_index(drop=True)
    backtest_forecasts = np.asarray(
        [
            max(
                0.0,
                -float(
                    np.quantile(
                        values.iloc[position - backtest_window : position],
                        1 - confidence,
                    )
                ),
            )
            for position in range(backtest_window, len(values))
        ]
    )
    var_backtesting = backtest_var(
        backtest_returns,
        backtest_forecasts,
        confidence=confidence,
        dates=prepared.data["date"].iloc[backtest_window:].reset_index(drop=True),
    )
    validation_checks = {
        "source_hash_present": bool(market.raw_source_sha256),
        "return_observations_at_least_120": len(values) >= 120,
        "arch_converged": arch.get("status") == "implemented",
        "garch_converged": garch.get("status") == "implemented",
        "garch_stationary": bool(garch.get("stationary")),
        "tail_risk_backtest_completed": var_backtesting.get("status") == "implemented",
        "source_basis_disclosed": bool(market.price_basis),
    }
    return {
        "schema_version": "1.0.0",
        "module": "Market Risk and Volatility Lab",
        "status": "implemented",
        "purpose": "Quantitative model comparison and risk diagnostics; not a trading recommendation.",
        "source": market.metadata(),
        "returns": prepared.evidence(),
        "historical_volatility": historical_volatility(market, prepared, windows=windows),
        "ewma": ewma_volatility(
            values,
            decay=ewma_decay,
            annualisation_factor=prepared.annualisation_factor,
            dates=prepared.data["date"],
        ),
        "conditional_volatility": {"arch": arch, "garch": garch},
        "diagnostics": volatility_diagnostics(values, garch),
        "implied_volatility": implied,
        "model_comparison": comparison,
        "var_expected_shortfall": calculate_var_es(values, confidence=confidence),
        "var_backtesting": var_backtesting,
        "regimes": volatility_regimes(
            values,
            dates=prepared.data["date"],
            window=min(21, max(10, len(values) // 4)),
            annualisation_factor=prepared.annualisation_factor,
        ),
        "governance": {
            "external_data_used": not market.source_is_synthetic
            and market.provider != "uploaded_file",
            "trading_recommendation": False,
            "causal_claim": False,
            "limitations": [
                "Results depend on data quality, price basis, sample period, and modelling assumptions.",
                "Forecasts and tail-risk estimates can fail under structural change or extreme illiquidity.",
                "No output is investment advice, a trade signal, or a maximum-loss estimate.",
            ],
        },
        "validation": {
            "status": "PASS" if all(validation_checks.values()) else "FAIL",
            "checks": validation_checks,
            "publication_allowed": bool(
                all(validation_checks.values()) and market.redistribution_permitted
            ),
            "publication_basis": (
                "Source redistribution is permitted and executable checks passed."
                if all(validation_checks.values()) and market.redistribution_permitted
                else "Publication requires passing calculations and source redistribution permission."
            ),
        },
    }
