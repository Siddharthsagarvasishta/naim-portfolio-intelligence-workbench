# Machine-Learning Workbench

## Intended use

The workbench supports segmentation, risk ranking, forecasting, behavioural diagnostics and challenger comparison. Models do not calculate governed accounting/risk metrics and do not autonomously change strategy.

## Pipeline

Define purpose and target → freeze development data → leakage review → preprocessing → cross-validation → benchmark → calibration and segment diagnostics → validation → controlled release → monitoring.

## Required evidence

- Dataset/run, feature and code/config versions.
- Target/event window and observation window.
- Exclusions, missing treatment and leakage controls.
- Benchmark and train/validation/test split rationale.
- Discrimination, calibration, stability and operational/profit impact.
- Approved-segment performance and minimum samples.
- Explanation method and non-causal caveat.
- Owner, validator, approval and monitoring thresholds.

## Challenger and threshold review

Compare current, challenger and simple benchmark on accuracy-appropriate metrics, calibration, stability, complexity, explainability, false positives, segment outcomes, operations capacity and expected profit. Threshold optimization shows the full trade-off curve and enforces configured guardrails; a user must approve a new version.

## Drift

Monitor input distribution, missingness, score distribution, calibration, discrimination and outcome performance. PSI is one signal, not the decision. Trigger investigation or revalidation based on persistence and materiality.

## Explainability

SHAP and surrogate trees explain model associations within measured features. They do not establish causal drivers or justify adverse action without policy and validation review.

