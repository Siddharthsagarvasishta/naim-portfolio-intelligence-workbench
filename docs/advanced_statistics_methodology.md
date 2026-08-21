# Advanced statistics methodology

The live advanced-statistics package deliberately implements a small governed set of methods rather than advertising a broad catalogue of placeholders. Every output states its assumptions, diagnostic decision, causal status, and limitations. These methods support analysis in the **nAIM Portfolio Intelligence Workbench**; they are not automatic customer-level decisions.

## Survival analysis

`kaplan_meier` implements the product-limit estimator with tied-event handling, numbers at risk, events, censoring counts, median survival where reached, and restricted mean survival through the observed horizon. Pointwise confidence bands use Greenwood variance with a log-minus-log transformation.

`log_rank_test` implements a two-group log-rank statistic using pooled event-time risk sets. `run_survival_analysis` applies both methods to time to attrition and time to first 30+ delinquency, with optional group curves. Inputs must contain finite non-negative durations and binary event indicators.

The workflow requires review of time origin, event definition, right-censoring, competing risks, and the non-informative censoring assumption. Results are labelled associational. Cox proportional hazards is explicitly `not_implemented`; no coefficient or hazard ratio is exposed without validated proportional-hazards diagnostics.

## Next-month delinquency behavioral diagnostics

`run_behavioural_diagnostics` fits a live `RandomForestClassifier` for 30+ delinquency in the next observed account period and a standardised logistic-regression benchmark. When the target is absent, it is constructed within account by shifting current delinquency one period forward; final rows without a future outcome are excluded.

Distinct dates are split chronologically into approximately 60% train, 20% validation, and 20% test. Every split must contain at least 20 observations and both classes. Training medians impute missing numeric features. The random forest uses fixed seed, bounded depth, minimum leaves, and balanced bootstrap class weights. Platt logistic calibration is fitted only on validation predictions. Test evidence includes ROC AUC, PR AUC, Brier score, pre/post-calibration metrics, quantile calibration data, expected calibration error, a threshold table, and the threshold chosen from validation F1.

Feature controls reject the target, names containing future/next-month/target/outcome/label tokens, exact target reproductions, and protected attributes. Current-period features are at time `t`; the target is at `t+1`. Protected attributes are not used.

The optional `shap` package is capability-gated:

- when installed and successfully executed, a `TreeExplainer` global summary is returned;
- when absent, `shap.status` is `dependency_unavailable`;
- when an incompatible SHAP installation fails, the status is `execution_failed`.

The live fallback is tree impurity importance plus one-at-a-time median perturbation. It provides global ranking, segment diagnostics, and a local synthetic-record explanation. It is explicitly labelled **not SHAP**, may not sum to the prediction, and can be unreliable for correlated or unrealistic substitutions. Neither SHAP nor fallback contributions are causal effects.

## Robust change-point detection

`detect_change_points` implements a robust single-break scan. It compares:

1. a constant median model;
2. a robust Huber linear trend;
3. two median levels separated at each allowed split.

The decision requires the level-shift model to beat constant and linear models by a BIC margin, a within-segment robust effect threshold, and a Mann–Whitney p-value Bonferroni-adjusted across all scanned splits. A supplied seasonal period is removed by phase medians before scanning. A preferred gradual linear trend is reported as `gradual_trend`, not a structural break. The live method finds at most one break.

`validate_change_point_method` executes deterministic no-change, known abrupt shift, gradual trend, and seasonal challenge series. Its pass criteria require no false break for no-change, gradual, and seasonally adjusted data, and recovery of the known shift within two observations.

## Propensity-weighted observational comparison

`propensity_weighted_comparison` fits a standardised logistic propensity model using declared pre-treatment numeric covariates. It reports propensity ROC AUC, 1st-to-99th percentile common support, shares of each group in common support, probability clipping, stabilised inverse-probability weights, symmetric tail trimming, and effective sample size.

Covariate balance is reported as standardised mean differences before and after weighting, with chart-ready paired values and a 0.10 absolute threshold. The weighted outcome contrast includes treated and comparison means, a sandwich-style weighted standard error, and a 95% interval. `status` becomes `review_required` when overlap, balance, or effective sample controls fail.

Protected attributes are rejected. The causal status is “observational association after measured-covariate adjustment.” The result is not described as randomised and retains a sensitivity warning for unmeasured confounding, timing, measurement error, and model misspecification.

## Difference-in-differences

`difference_in_differences` runs only when `synthetic_policy_use_case=True`. It requires an explicit treatment group, comparison group, outcome, time field, and policy date. The main model includes group, post-period, and group-by-post interaction. It uses cluster-robust uncertainty when at least ten clusters are supplied and HC1 robust uncertainty otherwise.

The method reports:

- pre- and post-period counts;
- difference-in-differences estimate, robust standard error, interval, and p-value;
- a pre-period group-by-linear-time interaction test;
- a placebo policy test inside the pre-period;
- chart-ready event-study coefficients with period `-1` as the preferred reference;
- the uncertainty estimator and assumption decision.

At least three pre-periods and two post-periods are required. If the pretrend interaction or placebo is significant at 5%, or the period controls fail, the exact status is `not_interpretable` and the interpretation is “not interpretable.” Passing diagnostics do not prove the assumptions; concurrent differential shocks can still invalidate the estimate.

## Callable schemas for API integration

```python
run_survival_analysis(
    frame: pd.DataFrame,
    *,
    group_column: str | None = None,
    outcomes: dict[str, tuple[str, str]] | None = None,
    confidence: float = 0.95,
) -> dict

run_behavioural_diagnostics(
    frame: pd.DataFrame,
    *,
    account_column: str = "account_id",
    time_column: str = "month",
    target_column: str = "next_month_delinquent",
    current_delinquency_column: str = "days_past_due",
    feature_columns: Sequence[str] | None = None,
    segment_column: str | None = None,
    seed: int = 73421,
) -> dict

detect_change_points(
    series: Sequence[float],
    *,
    min_segment: int = 12,
    seasonal_period: int | None = None,
    significance: float = 0.05,
    minimum_robust_effect: float = 1.5,
) -> dict

propensity_weighted_comparison(
    frame: pd.DataFrame,
    *,
    treatment_column: str,
    outcome_column: str,
    covariates: Sequence[str],
    trim_quantile: float = 0.99,
    seed: int = 73421,
) -> dict

difference_in_differences(
    frame: pd.DataFrame,
    *,
    outcome_column: str,
    treatment_column: str,
    time_column: str,
    policy_date: str | pd.Timestamp,
    cluster_column: str | None = None,
    synthetic_policy_use_case: bool = False,
) -> dict
```

Focused verification:

```text
PYTHONPATH=src .venv/bin/pytest -q tests/unit/test_advanced_statistics_extensions.py
PYTHONPATH=src .venv/bin/ruff check src/naim_risk/advanced tests/unit/test_advanced_statistics_extensions.py
```

