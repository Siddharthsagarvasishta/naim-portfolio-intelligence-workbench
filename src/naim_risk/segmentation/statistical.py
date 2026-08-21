"""Reproducible K-Means segmentation with a shallow tree surrogate."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

FEATURES = [
    "average_balance",
    "average_utilization",
    "transaction_frequency",
    "transaction_value",
    "inflow_volatility",
    "payment_ratio",
    "delinquency_incidence",
    "risk_score",
    "fraud_alerts",
    "customer_friction",
    "tenure",
]


def _feature_frame(performance: pd.DataFrame) -> pd.DataFrame:
    frame = performance.sort_values(["account_id", "month"]).copy()
    latest_month = pd.Timestamp(frame["month"].max())
    window = frame[frame["month"] >= latest_month - pd.DateOffset(months=5)].copy()
    window["_payment_ratio"] = np.divide(
        window["payment_amount"],
        window["statement_balance"],
        out=np.zeros(len(window), dtype=float),
        where=window["statement_balance"].to_numpy(dtype=float) != 0,
    )
    window["_delinquent"] = (window["days_past_due"] >= 30).astype(int)
    window["_friction"] = (
        window[
            [
                "manual_review_count",
                "declined_transaction_count",
                "step_up_authentication_count",
                "customer_contact_count",
            ]
        ].sum(axis=1)
        > 0
    ).astype(int)
    return window.groupby("account_id", as_index=False).agg(
        average_balance=("account_balance", "mean"),
        average_utilization=("utilization", "mean"),
        transaction_frequency=("transaction_count", "mean"),
        transaction_value=("transaction_value", "mean"),
        inflow_volatility=("inflows", "std"),
        payment_ratio=("_payment_ratio", "mean"),
        delinquency_incidence=("_delinquent", "mean"),
        risk_score=("risk_score", "mean"),
        fraud_alerts=("fraud_alert_count", "sum"),
        customer_friction=("_friction", "sum"),
        tenure=("months_on_book", "max"),
    )


def statistical_segments(
    performance: pd.DataFrame,
    *,
    seed: int = 73421,
    candidate_clusters: tuple[int, ...] = (3, 4, 5),
) -> dict[str, Any]:
    """Fit K-Means and a governed shallow-tree surrogate on trailing features."""

    try:
        from sklearn.cluster import KMeans
        from sklearn.metrics import adjusted_rand_score, silhouette_score
        from sklearn.preprocessing import StandardScaler
        from sklearn.tree import DecisionTreeClassifier, export_text
    except (ImportError, ModuleNotFoundError) as exc:
        return {
            "status": "dependency_unavailable",
            "limitation": f"scikit-learn is required for statistical segmentation: {exc}",
            "clusters": [],
        }
    features = _feature_frame(performance)
    if len(features) < 60:
        return {
            "status": "insufficient_sample",
            "sample_size": int(len(features)),
            "minimum_sample": 60,
            "clusters": [],
        }
    matrix = features[FEATURES].copy()
    missingness = matrix.isna().mean().to_dict()
    matrix = matrix.fillna(matrix.median(numeric_only=True))
    for column in matrix.columns:
        lower, upper = matrix[column].quantile([0.01, 0.99])
        matrix[column] = matrix[column].clip(lower, upper)
    skew_features = [
        "average_balance",
        "transaction_frequency",
        "transaction_value",
        "inflow_volatility",
        "fraud_alerts",
        "customer_friction",
        "tenure",
    ]
    for column in skew_features:
        minimum = float(matrix[column].min())
        matrix[column] = np.log1p(matrix[column] - min(minimum, 0))
    scaled = StandardScaler().fit_transform(matrix)
    diagnostics = []
    fitted: dict[int, tuple[Any, np.ndarray]] = {}
    valid_candidates = [value for value in candidate_clusters if 2 <= value < len(features)]
    for clusters in valid_candidates:
        model = KMeans(n_clusters=clusters, random_state=seed, n_init=20)
        labels = model.fit_predict(scaled)
        sizes = np.bincount(labels, minlength=clusters)
        silhouette = float(silhouette_score(scaled, labels))
        diagnostics.append(
            {
                "clusters": clusters,
                "inertia": float(model.inertia_),
                "silhouette_score": silhouette,
                "minimum_cluster_share": float(sizes.min() / len(labels)),
                "cluster_size_control_met": bool(sizes.min() / len(labels) >= 0.02),
            }
        )
        fitted[clusters] = (model, labels)
    eligible = [row for row in diagnostics if row["cluster_size_control_met"]]
    selected_diagnostic = max(
        eligible or diagnostics,
        key=lambda row: (row["silhouette_score"], -row["clusters"]),
    )
    selected_k = int(selected_diagnostic["clusters"])
    _, labels = fitted[selected_k]
    stability_model = KMeans(n_clusters=selected_k, random_state=seed + 17, n_init=20)
    stability_labels = stability_model.fit_predict(scaled)
    stability = float(adjusted_rand_score(labels, stability_labels))
    tree = DecisionTreeClassifier(
        max_depth=3,
        min_samples_leaf=max(10, int(len(features) * 0.03)),
        random_state=seed,
    )
    tree.fit(scaled, labels)
    surrogate_accuracy = float(tree.score(scaled, labels))
    features["cluster_id"] = labels
    descriptions = []
    global_means = features[FEATURES].mean()
    for cluster_id, group in features.groupby("cluster_id"):
        means = group[FEATURES].mean()
        ratios = (means / global_means.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)
        defining = ratios.sub(1).abs().sort_values(ascending=False).head(3).index.tolist()
        descriptions.append(
            {
                "cluster_id": int(cluster_id),
                "cluster_name": f"Statistical Segment {int(cluster_id) + 1}",
                "accounts": int(len(group)),
                "share": float(len(group) / len(features)),
                "defining_characteristics": [
                    {
                        "feature": feature,
                        "cluster_mean": float(means[feature]),
                        "portfolio_mean": float(global_means[feature]),
                    }
                    for feature in defining
                ],
            }
        )
    return {
        "status": "implemented",
        "sample_size": int(len(features)),
        "feature_window": "Trailing six reporting months",
        "features": FEATURES,
        "missingness": {key: float(value) for key, value in missingness.items()},
        "preprocessing": [
            "median imputation",
            "1st/99th percentile winsorisation",
            "log1p on skewed non-negative features",
            "StandardScaler",
        ],
        "selection_diagnostics": diagnostics,
        "selected_clusters": selected_k,
        "silhouette_score": selected_diagnostic["silhouette_score"],
        "stability_adjusted_rand_index": stability,
        "clusters": descriptions,
        "surrogate": {
            "algorithm": "DecisionTreeClassifier",
            "depth": int(tree.get_depth()),
            "leaves": int(tree.get_n_leaves()),
            "accuracy": surrogate_accuracy,
            "rules": export_text(tree, feature_names=FEATURES),
            "limitation": "Surrogate rules approximate K-Means membership and are not causal.",
        },
        "governance": {
            "random_seed": seed,
            "protected_attributes_used": False,
            "approved_use": "Synthetic exploratory segmentation",
            "prohibited_use": "Production customer-level credit decision",
        },
    }
