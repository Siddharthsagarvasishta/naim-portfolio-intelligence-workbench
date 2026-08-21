"""Deterministic nearest-neighbour peer matching with transparent diagnostics."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def match_peer_analogues(
    frame: pd.DataFrame,
    *,
    entity_id_column: str,
    entity_id: str,
    feature_columns: list[str],
    comparison_metric: str,
    peer_count: int = 3,
) -> dict[str, Any]:
    """Match an entity to standardised-feature peers and report peer statistics."""

    if entity_id_column not in frame or entity_id not in set(frame[entity_id_column]):
        raise ValueError(f"Unknown {entity_id_column}: {entity_id}")
    if comparison_metric not in frame:
        raise ValueError(f"Unknown comparison metric: {comparison_metric}")
    usable_features = [
        column
        for column in feature_columns
        if column in frame and pd.api.types.is_numeric_dtype(frame[column])
    ]
    if not usable_features:
        raise ValueError("No numeric matching features are available")
    working = frame[[entity_id_column, comparison_metric, *usable_features]].copy()
    for column in [comparison_metric, *usable_features]:
        working[column] = pd.to_numeric(working[column], errors="coerce")
        working[column] = working[column].fillna(working[column].median())
    location = working[usable_features].median()
    scale = working[usable_features].std(ddof=0).replace(0, 1).fillna(1)
    standardised = (working[usable_features] - location) / scale
    target_index = working.index[working[entity_id_column] == entity_id][0]
    target = standardised.loc[target_index]
    distances = np.sqrt(((standardised - target) ** 2).mean(axis=1))
    candidates = working.assign(_distance=distances)
    candidates = candidates[candidates[entity_id_column] != entity_id]
    selected = candidates.sort_values(["_distance", entity_id_column]).head(peer_count)
    if selected.empty:
        raise ValueError("At least two entities are required for peer matching")
    peer_metric = selected[comparison_metric]
    target_metric = float(working.loc[target_index, comparison_metric])
    population_metric = working[comparison_metric]
    peer_median = float(peer_metric.median())
    lower_quartile = float(peer_metric.quantile(0.25))
    upper_quartile = float(peer_metric.quantile(0.75))
    percentile_rank = float((population_metric <= target_metric).mean())
    peer_rows = [
        {
            "entity_id": str(row[entity_id_column]),
            "distance": float(row["_distance"]),
            "similarity_score": float(1 / (1 + row["_distance"])),
            "comparison_value": float(row[comparison_metric]),
        }
        for row in selected.to_dict(orient="records")
    ]
    maximum_distance = float(selected["_distance"].max())
    return {
        "entity_id": entity_id,
        "entity_id_field": entity_id_column,
        "selected_peer_population": peer_rows,
        "peer_count": len(peer_rows),
        "variables_used": usable_features,
        "standardisation": "Median-centred population standard deviation",
        "distance_method": "Root-mean-square standardised Euclidean distance",
        "comparison_metric": comparison_metric,
        "entity_value": target_metric,
        "percentile_rank": percentile_rank,
        "peer_median": peer_median,
        "peer_interquartile_range": [lower_quartile, upper_quartile],
        "best_quartile_result": upper_quartile,
        "worst_quartile_result": lower_quartile,
        "distance_from_peer_median": target_metric - peer_median,
        "confidence": "Low" if len(peer_rows) < 3 or maximum_distance > 2 else "Moderate",
        "confidence_warning": (
            "Peer evidence is weak because the peer group is small or distant."
            if len(peer_rows) < 3 or maximum_distance > 2
            else None
        ),
        "causal_status": "DESCRIPTIVE",
    }
