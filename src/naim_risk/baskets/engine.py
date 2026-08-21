"""Safe dynamic basket evaluation, set operations and impact previews."""

from __future__ import annotations

import ast
from collections.abc import Iterable
from typing import Any, Literal

import numpy as np
import pandas as pd


class UnsafeBasketExpression(ValueError):
    """Raised when a basket expression uses unsupported syntax."""


def _evaluate_node(node: ast.AST, frame: pd.DataFrame) -> Any:
    if isinstance(node, ast.Expression):
        return _evaluate_node(node.body, frame)
    if isinstance(node, ast.Name):
        if node.id not in frame.columns:
            raise UnsafeBasketExpression(f"Unknown basket field: {node.id}")
        return frame[node.id]
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.List):
        return [_evaluate_node(item, frame) for item in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_evaluate_node(item, frame) for item in node.elts)
    if isinstance(node, ast.BoolOp):
        values = [_evaluate_node(item, frame) for item in node.values]
        result = values[0]
        for value in values[1:]:
            result = result & value if isinstance(node.op, ast.And) else result | value
        return result
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return ~_evaluate_node(node.operand, frame)
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and len(node.comparators) == 1:
        left = _evaluate_node(node.left, frame)
        right = _evaluate_node(node.comparators[0], frame)
        operation = node.ops[0]
        if isinstance(operation, ast.Eq):
            return left == right
        if isinstance(operation, ast.NotEq):
            return left != right
        if isinstance(operation, ast.Gt):
            return left > right
        if isinstance(operation, ast.GtE):
            return left >= right
        if isinstance(operation, ast.Lt):
            return left < right
        if isinstance(operation, ast.LtE):
            return left <= right
        if isinstance(operation, ast.In):
            return left.isin(right)
        if isinstance(operation, ast.NotIn):
            return ~left.isin(right)
    raise UnsafeBasketExpression(
        f"Unsupported basket syntax: {type(node).__name__}; only boolean comparisons are allowed"
    )


def evaluate_expression(frame: pd.DataFrame, expression: str) -> pd.Series:
    """Evaluate an allowlisted boolean expression without arbitrary code execution."""

    tree = ast.parse(expression, mode="eval")
    disallowed = (
        ast.Call,
        ast.Attribute,
        ast.Subscript,
        ast.Lambda,
        ast.BinOp,
        ast.Dict,
        ast.Set,
        ast.IfExp,
    )
    if any(isinstance(node, disallowed) for node in ast.walk(tree)):
        raise UnsafeBasketExpression(
            "Function calls, attributes and arbitrary arithmetic are prohibited"
        )
    result = _evaluate_node(tree, frame)
    if not isinstance(result, pd.Series) or result.dtype != bool:
        raise UnsafeBasketExpression("Basket expression must resolve to a boolean record mask")
    return result.fillna(False)


def combine_memberships(
    left: Iterable[str],
    right: Iterable[str],
    operation: Literal["union", "intersection", "subtract"],
) -> list[str]:
    """Apply deterministic set operations to basket members."""

    left_set, right_set = set(left), set(right)
    if operation == "union":
        result = left_set | right_set
    elif operation == "intersection":
        result = left_set & right_set
    elif operation == "subtract":
        result = left_set - right_set
    else:
        raise ValueError(f"Unsupported basket operation: {operation}")
    return sorted(result)


def weighted_basket_summary(
    frame: pd.DataFrame,
    *,
    entity_id_column: str,
    members: Iterable[str],
    metric_columns: Iterable[str],
    weight_column: str | None = None,
) -> dict[str, Any]:
    """Calculate totals and explicit simple or weighted averages."""

    selected = frame[frame[entity_id_column].isin(set(members))].copy()
    if selected.empty:
        return {"member_count": 0, "row_count": 0, "metrics": {}}
    if weight_column is None:
        weights = np.ones(len(selected), dtype=float)
        weighting = "equal"
    else:
        weights = selected[weight_column].fillna(0).clip(lower=0).to_numpy(dtype=float)
        weighting = weight_column
    weight_total = float(weights.sum())
    metrics: dict[str, Any] = {}
    for column in metric_columns:
        values = selected[column].to_numpy(dtype=float)
        metrics[column] = {
            "total": float(np.nansum(values)),
            "simple_average": float(np.nanmean(values)) if len(values) else None,
            "weighted_average": (
                float(np.nansum(values * weights) / weight_total) if weight_total > 0 else None
            ),
            "median": float(np.nanmedian(values)) if len(values) else None,
        }
    return {
        "member_count": int(selected[entity_id_column].nunique()),
        "row_count": int(len(selected)),
        "weighting": weighting,
        "weight_total": weight_total,
        "metrics": metrics,
    }


def impact_preview(
    frame: pd.DataFrame,
    *,
    entity_id_column: str,
    original_members: Iterable[str],
    revised_members: Iterable[str],
    metric_columns: Iterable[str],
) -> dict[str, Any]:
    """Preview population and additive-metric change before basket approval."""

    original = weighted_basket_summary(
        frame,
        entity_id_column=entity_id_column,
        members=original_members,
        metric_columns=metric_columns,
    )
    revised = weighted_basket_summary(
        frame,
        entity_id_column=entity_id_column,
        members=revised_members,
        metric_columns=metric_columns,
    )
    differences = {}
    for metric in metric_columns:
        original_total = original["metrics"].get(metric, {}).get("total", 0.0)
        revised_total = revised["metrics"].get(metric, {}).get("total", 0.0)
        differences[metric] = float(revised_total - original_total)
    return {
        "original": original,
        "revised": revised,
        "affected_entities": len(set(original_members) ^ set(revised_members)),
        "metric_differences": differences,
        "approval_required": True,
    }
