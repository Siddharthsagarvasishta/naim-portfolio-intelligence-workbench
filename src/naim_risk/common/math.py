"""Numerically safe helpers used by governed metrics."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

import numpy as np


def safe_divide(numerator: float, denominator: float) -> float | None:
    """Return ``None`` for a zero, missing, or non-finite denominator."""

    if denominator is None or not math.isfinite(float(denominator)) or float(denominator) == 0:
        return None
    value = float(numerator) / float(denominator)
    return value if math.isfinite(value) else None


def sigmoid(value: np.ndarray | float) -> np.ndarray | float:
    """Stable logistic transform."""

    clipped = np.clip(value, -30.0, 30.0)
    return 1.0 / (1.0 + np.exp(-clipped))


def wilson_interval(
    successes: float, total: float, z: float = 1.96
) -> tuple[float | None, float | None]:
    """Wilson score interval for a binomial proportion."""

    if total <= 0:
        return None, None
    proportion = successes / total
    denominator = 1.0 + (z * z / total)
    centre = (proportion + z * z / (2.0 * total)) / denominator
    margin = (
        z
        * math.sqrt((proportion * (1.0 - proportion) + z * z / (4.0 * total)) / total)
        / denominator
    )
    return max(0.0, centre - margin), min(1.0, centre + margin)


def benjamini_hochberg(p_values: Sequence[float]) -> list[float]:
    """Return false-discovery-rate adjusted p-values."""

    if not p_values:
        return []
    values = np.asarray(p_values, dtype=float)
    order = np.argsort(values)
    adjusted = np.empty(len(values), dtype=float)
    running = 1.0
    for reverse_rank, index in enumerate(order[::-1], start=1):
        rank = len(values) - reverse_rank + 1
        running = min(running, values[index] * len(values) / rank)
        adjusted[index] = running
    return np.clip(adjusted, 0.0, 1.0).tolist()


def hhi(values: Iterable[float]) -> float | None:
    """Herfindahl-Hirschman concentration index on non-negative exposures."""

    array = np.asarray(list(values), dtype=float)
    array = array[np.isfinite(array) & (array >= 0)]
    total = float(array.sum())
    if total <= 0:
        return None
    shares = array / total
    return float(np.square(shares).sum())


def gini(values: Iterable[float]) -> float | None:
    """Gini coefficient for non-negative contribution values."""

    array = np.asarray(list(values), dtype=float)
    array = array[np.isfinite(array) & (array >= 0)]
    if array.size == 0 or float(array.sum()) == 0:
        return None
    ordered = np.sort(array)
    n = ordered.size
    return float((2.0 * np.dot(np.arange(1, n + 1), ordered) / ordered.sum() - (n + 1)) / n)
