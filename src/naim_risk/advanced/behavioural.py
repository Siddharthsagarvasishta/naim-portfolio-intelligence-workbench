"""Time-split next-period delinquency models and non-causal contribution diagnostics."""

from __future__ import annotations

import importlib.util
import math
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

from naim_risk.advanced.survival import AdvancedStatisticsError

# Synchronous API routes run in a worker thread. Load the optional native
# scikit-learn stack during module import to avoid first-import deadlocks in
# that worker, while retaining an explicit dependency-unavailable result.
try:
    from sklearn.calibration import calibration_curve
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
except (ImportError, ModuleNotFoundError) as exc:  # pragma: no cover - environment dependent
    RandomForestClassifier = None  # type: ignore[assignment,misc]
    LogisticRegression = None  # type: ignore[assignment,misc]
    StandardScaler = None  # type: ignore[assignment,misc]
    average_precision_score = None  # type: ignore[assignment]
    brier_score_loss = None  # type: ignore[assignment]
    calibration_curve = None  # type: ignore[assignment]
    make_pipeline = None  # type: ignore[assignment]
    roc_auc_score = None  # type: ignore[assignment]
    _SKLEARN_IMPORT_ERROR: Exception | None = exc
else:
    _SKLEARN_IMPORT_ERROR = None

_PROTECTED_TOKENS = {
    "age",
    "disability",
    "ethnicity",
    "gender",
    "nationality",
    "pregnancy",
    "race",
    "religion",
    "sex",
    "sexual_orientation",
}
_LEAKAGE_TOKENS = {"future", "next_month", "target", "outcome", "label"}


def _name_tokens(name: str) -> set[str]:
    normalised = name.casefold().replace("-", "_").replace(" ", "_")
    tokens = set(normalised.split("_"))
    tokens.add(normalised)
    return tokens


def _binary_metrics(observed: np.ndarray, probability: np.ndarray) -> dict[str, float]:
    assert average_precision_score is not None
    assert brier_score_loss is not None
    assert roc_auc_score is not None
    return {
        "roc_auc": float(roc_auc_score(observed, probability)),
        "pr_auc": float(average_precision_score(observed, probability)),
        "brier_score": float(brier_score_loss(observed, probability)),
    }


def _threshold_rows(observed: np.ndarray, probability: np.ndarray) -> list[dict[str, float]]:
    rows = []
    for threshold in np.linspace(0.05, 0.95, 19):
        predicted = probability >= threshold
        true_positive = int(np.sum(predicted & (observed == 1)))
        false_positive = int(np.sum(predicted & (observed == 0)))
        true_negative = int(np.sum(~predicted & (observed == 0)))
        false_negative = int(np.sum(~predicted & (observed == 1)))
        precision = true_positive / max(true_positive + false_positive, 1)
        recall = true_positive / max(true_positive + false_negative, 1)
        specificity = true_negative / max(true_negative + false_positive, 1)
        rows.append(
            {
                "threshold": float(threshold),
                "alerts": int(predicted.sum()),
                "alert_rate": float(predicted.mean()),
                "precision": float(precision),
                "recall": float(recall),
                "specificity": float(specificity),
                "false_positive_rate": float(1 - specificity),
                "f1": float(2 * precision * recall / max(precision + recall, 1e-12)),
            }
        )
    return rows


def _calibration_rows(
    observed: np.ndarray, probability: np.ndarray
) -> tuple[list[dict[str, Any]], float]:
    assert calibration_curve is not None
    observed_rate, predicted_mean = calibration_curve(
        observed,
        probability,
        n_bins=min(10, max(3, int(math.sqrt(len(observed))))),
        strategy="quantile",
    )
    rows = [
        {
            "mean_predicted_probability": float(predicted),
            "observed_event_rate": float(actual),
        }
        for predicted, actual in zip(predicted_mean, observed_rate, strict=True)
    ]
    edges = np.linspace(0, 1, 11)
    bins = np.clip(np.digitize(probability, edges) - 1, 0, 9)
    error = 0.0
    for bin_number in range(10):
        selected = bins == bin_number
        if selected.any():
            error += float(selected.mean()) * abs(
                float(probability[selected].mean()) - float(observed[selected].mean())
            )
    return rows, error


def _fallback_contributions(
    model: Any,
    train_matrix: np.ndarray,
    test_matrix: np.ndarray,
    feature_names: list[str],
    test_segments: pd.Series | None,
) -> dict[str, Any]:
    medians = np.median(train_matrix, axis=0)
    importances = np.asarray(model.feature_importances_, dtype=float)
    order = np.argsort(importances)[::-1]
    global_rows = [
        {"feature": feature_names[index], "importance": float(importances[index])}
        for index in order
    ]
    synthetic = medians.copy()
    for index in order[: min(5, len(order))]:
        synthetic[index] = np.quantile(train_matrix[:, index], 0.75)
    prediction = float(model.predict_proba(synthetic.reshape(1, -1))[0, 1])
    baseline_prediction = float(model.predict_proba(medians.reshape(1, -1))[0, 1])
    local_rows = []
    for index in order:
        counterfactual = synthetic.copy()
        counterfactual[index] = medians[index]
        local_rows.append(
            {
                "feature": feature_names[index],
                "synthetic_value": float(synthetic[index]),
                "training_median": float(medians[index]),
                "prediction_difference_when_reset_to_median": float(
                    prediction - model.predict_proba(counterfactual.reshape(1, -1))[0, 1]
                ),
            }
        )
    segment_rows: dict[str, list[dict[str, Any]]] = {}
    if test_segments is not None:
        for segment in pd.unique(test_segments):
            selected = np.asarray(test_segments == segment)
            if not selected.any():
                continue
            segment_matrix = test_matrix[selected]
            base_probability = model.predict_proba(segment_matrix)[:, 1]
            rows = []
            for index in order[: min(10, len(order))]:
                perturbed = segment_matrix.copy()
                perturbed[:, index] = medians[index]
                contribution = base_probability - model.predict_proba(perturbed)[:, 1]
                rows.append(
                    {
                        "feature": feature_names[index],
                        "mean_prediction_difference": float(np.mean(contribution)),
                        "mean_absolute_prediction_difference": float(np.mean(np.abs(contribution))),
                    }
                )
            segment_rows[str(segment)] = rows
    return {
        "method": "tree impurity importance plus one-at-a-time median perturbation",
        "global": global_rows,
        "segments": segment_rows,
        "local_synthetic_record": {
            "prediction": prediction,
            "all_feature_median_prediction": baseline_prediction,
            "features": local_rows,
            "synthetic_record": {
                feature: float(value)
                for feature, value in zip(feature_names, synthetic, strict=True)
            },
        },
        "limitation": (
            "Perturbation contributions need not sum to the prediction and are not SHAP values; "
            "correlated-feature substitutions may be unrealistic."
        ),
    }


def _optional_shap(
    model: Any,
    train_matrix: np.ndarray,
    test_matrix: np.ndarray,
    feature_names: list[str],
) -> dict[str, Any]:
    if importlib.util.find_spec("shap") is None:
        return {
            "status": "dependency_unavailable",
            "dependency": "shap",
            "reason": "The optional shap package is not installed; fallback contributions are live.",
        }
    try:
        import shap

        background = train_matrix[: min(200, len(train_matrix))]
        sample = test_matrix[: min(500, len(test_matrix))]
        explainer = shap.TreeExplainer(model, data=background)
        values = np.asarray(explainer.shap_values(sample))
        if values.ndim == 3:
            values = values[:, :, -1]
        elif values.ndim == 2 and values.shape[1] == len(sample):
            values = values[-1]
        if values.shape != sample.shape:
            raise ValueError(f"Unexpected SHAP shape {values.shape}; expected {sample.shape}")
        importance = np.mean(np.abs(values), axis=0)
        order = np.argsort(importance)[::-1]
        return {
            "status": "implemented",
            "method": "TreeExplainer",
            "sample_observations": int(len(sample)),
            "summary": [
                {"feature": feature_names[index], "mean_absolute_shap": float(importance[index])}
                for index in order
            ],
        }
    except Exception as exc:  # optional dependency version mismatches must not fake success
        return {
            "status": "execution_failed",
            "dependency": "shap",
            "reason": f"SHAP execution failed; fallback contributions remain available: {exc}",
        }


def run_behavioural_diagnostics(
    frame: pd.DataFrame,
    *,
    account_column: str = "account_id",
    time_column: str = "month",
    target_column: str = "next_month_delinquent",
    current_delinquency_column: str = "days_past_due",
    feature_columns: Sequence[str] | None = None,
    segment_column: str | None = None,
    seed: int = 73421,
) -> dict[str, Any]:
    """Fit a time-split tree model and logistic benchmark for next-month delinquency."""

    required = {account_column, time_column}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise AdvancedStatisticsError(f"Behavioural input is missing columns: {missing}")
    working = frame.copy()
    working[time_column] = pd.to_datetime(working[time_column], errors="coerce")
    if working[time_column].isna().any():
        raise AdvancedStatisticsError("Behavioural input contains invalid time values")
    target_constructed = target_column not in working
    if target_constructed:
        if current_delinquency_column not in working:
            raise AdvancedStatisticsError(
                f"Target is absent and {current_delinquency_column!r} is unavailable"
            )
        working = working.sort_values([account_column, time_column])
        next_value = working.groupby(account_column)[current_delinquency_column].shift(-1)
        working[target_column] = np.where(
            next_value.notna(), (next_value >= 30).astype(float), np.nan
        )
    working = working.dropna(subset=[target_column]).copy()
    working[target_column] = working[target_column].astype(int)
    if not set(working[target_column].unique()).issubset({0, 1}):
        raise AdvancedStatisticsError("Behavioural target must be binary")
    excluded = {account_column, time_column, target_column}
    if segment_column:
        if segment_column not in working:
            raise AdvancedStatisticsError(f"Segment column {segment_column!r} is missing")
        excluded.add(segment_column)
    if feature_columns is None:
        selected_features = [
            column
            for column in working.select_dtypes(include=[np.number, "bool"]).columns
            if column not in excluded
        ]
    else:
        selected_features = list(dict.fromkeys(feature_columns))
    if not selected_features:
        raise AdvancedStatisticsError("At least one numeric behavioural feature is required")
    missing_features = sorted(set(selected_features).difference(working.columns))
    if missing_features:
        raise AdvancedStatisticsError(f"Behavioural features are missing: {missing_features}")
    protected = sorted(
        feature
        for feature in selected_features
        if _name_tokens(feature).intersection(_PROTECTED_TOKENS)
    )
    if protected:
        raise AdvancedStatisticsError(f"Protected attributes are prohibited: {protected}")
    named_leakage = sorted(
        feature
        for feature in selected_features
        if feature == target_column or _name_tokens(feature).intersection(_LEAKAGE_TOKENS)
    )
    if named_leakage:
        raise AdvancedStatisticsError(
            f"Potential future/target leakage features rejected: {named_leakage}"
        )
    numeric = working[selected_features].apply(pd.to_numeric, errors="coerce")
    exact_leakage = [
        feature
        for feature in selected_features
        if numeric[feature].notna().all()
        and np.array_equal(numeric[feature].to_numpy(), working[target_column].to_numpy())
    ]
    if exact_leakage:
        raise AdvancedStatisticsError(f"Features exactly reproduce the target: {exact_leakage}")
    times = np.sort(working[time_column].unique())
    if len(times) < 10:
        raise AdvancedStatisticsError(
            "At least ten distinct periods are required for time splitting"
        )
    train_end = times[max(1, int(len(times) * 0.60)) - 1]
    validation_end = times[max(2, int(len(times) * 0.80)) - 1]
    split_masks = {
        "train": working[time_column] <= train_end,
        "validation": (working[time_column] > train_end) & (working[time_column] <= validation_end),
        "test": working[time_column] > validation_end,
    }
    for split, mask in split_masks.items():
        if mask.sum() < 20 or working.loc[mask, target_column].nunique() < 2:
            raise AdvancedStatisticsError(
                f"{split} split needs at least 20 observations and both target classes"
            )
    train_matrix = numeric.loc[split_masks["train"]].to_numpy(dtype=float)
    validation_matrix = numeric.loc[split_masks["validation"]].to_numpy(dtype=float)
    test_matrix = numeric.loc[split_masks["test"]].to_numpy(dtype=float)
    medians = np.nanmedian(train_matrix, axis=0)
    if np.isnan(medians).any():
        invalid = [selected_features[index] for index in np.flatnonzero(np.isnan(medians))]
        raise AdvancedStatisticsError(f"Features contain no finite training values: {invalid}")

    def impute(matrix: np.ndarray) -> np.ndarray:
        return np.where(np.isfinite(matrix), matrix, medians)

    train_matrix = impute(train_matrix)
    validation_matrix = impute(validation_matrix)
    test_matrix = impute(test_matrix)
    train_target = working.loc[split_masks["train"], target_column].to_numpy(dtype=int)
    validation_target = working.loc[split_masks["validation"], target_column].to_numpy(dtype=int)
    test_target = working.loc[split_masks["test"], target_column].to_numpy(dtype=int)
    if _SKLEARN_IMPORT_ERROR is not None:
        return {
            "status": "dependency_unavailable",
            "reason": f"scikit-learn analytics extra is required: {_SKLEARN_IMPORT_ERROR}",
        }
    assert RandomForestClassifier is not None
    assert LogisticRegression is not None
    assert StandardScaler is not None
    assert make_pipeline is not None
    tree = RandomForestClassifier(
        n_estimators=250,
        min_samples_leaf=max(5, int(len(train_matrix) * 0.005)),
        max_depth=8,
        class_weight="balanced_subsample",
        random_state=seed,
        n_jobs=1,
    )
    tree.fit(train_matrix, train_target)
    raw_validation_probability = tree.predict_proba(validation_matrix)[:, 1]
    raw_test_probability = tree.predict_proba(test_matrix)[:, 1]
    calibrator = LogisticRegression(random_state=seed)
    validation_logit = np.log(
        np.clip(raw_validation_probability, 1e-6, 1 - 1e-6)
        / np.clip(1 - raw_validation_probability, 1e-6, 1)
    ).reshape(-1, 1)
    calibrator.fit(validation_logit, validation_target)
    test_logit = np.log(
        np.clip(raw_test_probability, 1e-6, 1 - 1e-6) / np.clip(1 - raw_test_probability, 1e-6, 1)
    ).reshape(-1, 1)
    test_probability = calibrator.predict_proba(test_logit)[:, 1]
    logistic = make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=2_000, class_weight="balanced", random_state=seed),
    )
    logistic.fit(train_matrix, train_target)
    logistic_probability = logistic.predict_proba(test_matrix)[:, 1]
    calibration, expected_calibration_error = _calibration_rows(test_target, test_probability)
    threshold_analysis = _threshold_rows(test_target, test_probability)
    validation_thresholds = _threshold_rows(validation_target, raw_validation_probability)
    selected_threshold = max(validation_thresholds, key=lambda row: row["f1"])["threshold"]
    test_segments = (
        working.loc[split_masks["test"], segment_column].reset_index(drop=True)
        if segment_column
        else None
    )
    fallback = _fallback_contributions(
        tree,
        train_matrix,
        test_matrix,
        selected_features,
        test_segments,
    )
    shap_result = _optional_shap(tree, train_matrix, test_matrix, selected_features)
    return {
        "status": "implemented",
        "target": {
            "name": target_column,
            "definition": "30+ delinquency in the next observed account period",
            "constructed_from_next_period": target_constructed,
            "current_feature_time": "t",
            "target_time": "t+1",
        },
        "splits": {
            "method": "chronological 60% train / 20% validation / 20% test by distinct period",
            "train_end": pd.Timestamp(train_end).date().isoformat(),
            "validation_end": pd.Timestamp(validation_end).date().isoformat(),
            "test_end": pd.Timestamp(times[-1]).date().isoformat(),
            "observations": {split: int(mask.sum()) for split, mask in split_masks.items()},
            "event_rates": {
                split: float(working.loc[mask, target_column].mean())
                for split, mask in split_masks.items()
            },
        },
        "features": selected_features,
        "tree_model": {
            "algorithm": "RandomForestClassifier",
            "test_metrics": _binary_metrics(test_target, test_probability),
            "raw_test_metrics_before_calibration": _binary_metrics(
                test_target, raw_test_probability
            ),
            "calibration_method": "Platt logistic calibration fitted on validation predictions",
            "calibration_curve": calibration,
            "expected_calibration_error": expected_calibration_error,
            "threshold_selected_on_validation_f1": selected_threshold,
            "threshold_analysis_test": threshold_analysis,
        },
        "logistic_benchmark": {
            "algorithm": "standardised logistic regression",
            "test_metrics": _binary_metrics(test_target, logistic_probability),
        },
        "shap": shap_result,
        "contribution_diagnostics": fallback,
        "leakage_test": {
            "status": "passed",
            "target_excluded": target_column not in selected_features,
            "future_named_features": named_leakage,
            "exact_target_reproductions": exact_leakage,
            "last_account_observations_without_future_target_removed": target_constructed,
        },
        "governance": {
            "protected_attributes_used": False,
            "causal_status": "predictive association only",
            "approved_use": "Behavioural diagnostics on validated analytical data",
            "prohibited_use": "Unreviewed production credit decisions or protected-class inference",
            "limitations": [
                "Feature importance and local contributions are not causal effects.",
                "Performance may drift after the test horizon.",
                "Calibration and thresholds require portfolio-specific validation before operational use.",
            ],
        },
    }
