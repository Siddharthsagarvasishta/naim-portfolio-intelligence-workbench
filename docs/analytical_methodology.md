# Analytical Methodology

## Publication sequence

1. Validate schema, keys, ranges, effective dates, completeness and reconciliations.
2. Freeze a run manifest and curated population.
3. Calculate governed numerators and denominators.
4. Test materiality and uncertainty.
5. Diagnose exact contribution, maturity-aligned cohorts and behavioural associations.
6. Check alternative explanations, data limitations and operational guardrails.
7. Publish a versioned evidence object; commentary and exports consume it unchanged.

## Comparisons

Period-on-period comparisons use matched metric definitions and populations. Rates are compared as ratio-of-sums. Confidence intervals use an appropriate method for the estimator (for example Wilson intervals for proportions). Multiple subgroup scans use false-discovery control or are explicitly labelled exploratory.

## Exact mix/performance decomposition

For segment share `w` and segment rate `r`, the symmetric decomposition is:

`mix = 0.5 × Σ[(w1 − w0) × (r0 + r1)]`

`performance = 0.5 × Σ[(r1 − r0) × (w0 + w1)]`

The two components must sum to the observed portfolio movement before display rounding. Residuals above tolerance block publication.

## Vintage analysis

Cohorts are defined at origination and compared at the same months-on-book. Curves disclose cohort size, maturity, censoring and confidence intervals. Immature cells are not compared with fully matured averages without an explicit adjustment.

## Strategy evaluation

Randomized tests require sample-ratio, baseline-balance, contamination, minimum-sample and guardrail checks. Observational comparisons require overlap diagnostics and adjusted or matched estimates. Results distinguish statistical significance, practical materiality and operational feasibility. Association is not causation.

## Forecasts and stress

The baseline is compared with a naive benchmark using rolling-origin validation. Scenarios are conditional estimates driven by versioned assumptions, not predictions of what will occur. Outputs include uncertainty bands, assumption sensitivity and divergence from baseline.

## Behavioural models

Predictive models may rank risk or explain measured associations. SHAP and surrogate trees are non-causal. Performance, calibration, drift, fairness-by-approved-segment, stability and operational impact are assessed before use.

