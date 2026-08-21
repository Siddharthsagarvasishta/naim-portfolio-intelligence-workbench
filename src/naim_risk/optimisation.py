"""Transparent constrained allocation optimisation for governed nAIM scenarios."""

from __future__ import annotations

import math
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import linprog

from naim_risk.workflow import WorkflowStore

SUPPORTED_DIMENSIONS = {
    "acquisition_channel",
    "product_mix",
    "region_mix",
    "strategy_assignment",
    "partner_allocation",
    "vendor_volume",
    "membership_mix",
    "benefit_funding",
    "manual_review_capacity",
}
SUPPORTED_OBJECTIVES = {
    "maximise_expected_profit",
    "maximise_risk_adjusted_contribution",
    "minimise_expected_loss",
    "minimise_fraud_loss",
    "minimise_customer_friction",
    "minimise_vendor_cost",
    "multi_objective_weighted_score",
}
EFFECT_FIELDS = (
    "expected_profit",
    "expected_loss",
    "fraud_bps",
    "customer_friction",
    "vendor_cost",
    "review_load",
    "customer_coverage",
    "regional_service",
)


@dataclass(frozen=True)
class ConstraintRow:
    name: str
    coefficients: np.ndarray
    bound: float
    direction: str


def _finite(value: Any, *, field: str) -> float:
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError(f"{field} must be finite")
    return converted


def _objective_coefficients(
    items: Sequence[Mapping[str, Any]],
    objective: str,
    weights: Mapping[str, float],
) -> np.ndarray:
    columns = {
        field: np.array([_finite(item.get(field, 0.0), field=field) for item in items])
        for field in EFFECT_FIELDS
    }
    if objective == "maximise_expected_profit":
        return -columns["expected_profit"]
    if objective == "maximise_risk_adjusted_contribution":
        risk_weight = _finite(weights.get("expected_loss", 1.0), field="expected_loss weight")
        fraud_weight = _finite(weights.get("fraud_bps", 0.01), field="fraud_bps weight")
        friction_weight = _finite(
            weights.get("customer_friction", 1.0), field="customer_friction weight"
        )
        return -(
            columns["expected_profit"]
            - risk_weight * columns["expected_loss"]
            - fraud_weight * columns["fraud_bps"]
            - friction_weight * columns["customer_friction"]
        )
    field_by_objective = {
        "minimise_expected_loss": "expected_loss",
        "minimise_fraud_loss": "fraud_bps",
        "minimise_customer_friction": "customer_friction",
        "minimise_vendor_cost": "vendor_cost",
    }
    if objective in field_by_objective:
        return columns[field_by_objective[objective]]
    coefficients = np.zeros(len(items), dtype=float)
    for field, weight in weights.items():
        if field not in columns:
            raise ValueError(f"Unsupported multi-objective field: {field}")
        coefficients += _finite(weight, field=f"{field} weight") * columns[field]
    if not np.any(coefficients):
        raise ValueError("Multi-objective optimisation requires at least one non-zero weight")
    return coefficients


def _effects(items: Sequence[Mapping[str, Any]], allocation: np.ndarray) -> dict[str, float]:
    return {
        field: float(
            np.dot(
                allocation,
                np.array([_finite(item.get(field, 0.0), field=field) for item in items]),
            )
        )
        for field in EFFECT_FIELDS
    }


def _constraint_rows(
    items: Sequence[Mapping[str, Any]],
    constraints: Mapping[str, Any],
) -> list[ConstraintRow]:
    specs = (
        ("loss_rate_max", "expected_loss", "max"),
        ("fraud_bps_max", "fraud_bps", "max"),
        ("friction_max", "customer_friction", "max"),
        ("review_capacity_max", "review_load", "max"),
        ("vendor_cost_max", "vendor_cost", "max"),
        ("minimum_customer_coverage", "customer_coverage", "min"),
        ("regional_service_min", "regional_service", "min"),
    )
    rows: list[ConstraintRow] = []
    for constraint_name, field, direction in specs:
        if constraints.get(constraint_name) is None:
            continue
        coefficients = np.array(
            [_finite(item.get(field, 0.0), field=field) for item in items], dtype=float
        )
        bound = _finite(constraints[constraint_name], field=constraint_name)
        rows.append(ConstraintRow(constraint_name, coefficients, bound, direction))
    return rows


def _infeasibility_checks(
    total: float,
    bounds: Sequence[tuple[float, float]],
) -> list[str]:
    reasons: list[str] = []
    minimum_total = sum(lower for lower, _ in bounds)
    maximum_total = sum(upper for _, upper in bounds)
    if minimum_total > total + 1e-9:
        reasons.append(
            f"Allocation minima total {minimum_total:.6g}, above required total {total:.6g}."
        )
    if maximum_total < total - 1e-9:
        reasons.append(
            f"Allocation maxima total {maximum_total:.6g}, below required total {total:.6g}."
        )
    return reasons


def optimise_allocation(
    payload: Mapping[str, Any],
    *,
    store: WorkflowStore | None = None,
    actor: str = "workbench.service",
) -> dict[str, Any]:
    """Solve a bounded linear allocation scenario without applying it."""

    dimension = str(payload.get("decision_dimension", ""))
    objective = str(payload.get("objective", ""))
    if dimension not in SUPPORTED_DIMENSIONS:
        raise ValueError(f"Unsupported decision dimension: {dimension}")
    if objective not in SUPPORTED_OBJECTIVES:
        raise ValueError(f"Unsupported objective: {objective}")
    raw_items = payload.get("items")
    if not isinstance(raw_items, Sequence) or isinstance(raw_items, (str, bytes)):
        raise ValueError("items must be a non-empty list")
    items = [dict(item) for item in raw_items]
    if len(items) < 2:
        raise ValueError("At least two allocation items are required")
    names = [str(item.get("name", "")).strip() for item in items]
    if any(not name for name in names) or len(names) != len(set(names)):
        raise ValueError("Each allocation item requires a unique non-empty name")

    constraints = dict(payload.get("constraints") or {})
    total = _finite(constraints.get("allocation_total", 1.0), field="allocation_total")
    if total <= 0:
        raise ValueError("allocation_total must be positive")
    concentration_limit = constraints.get("concentration_limit")
    concentration = (
        total
        if concentration_limit is None
        else _finite(concentration_limit, field="concentration_limit")
    )
    bounds: list[tuple[float, float]] = []
    for item in items:
        lower = _finite(item.get("minimum", 0.0), field="minimum")
        upper = min(_finite(item.get("maximum", total), field="maximum"), concentration)
        if item.get("eligible", True) is False:
            lower, upper = 0.0, 0.0
        if lower < 0 or upper < lower:
            raise ValueError(f"Invalid allocation bounds for {item['name']}")
        bounds.append((lower, upper))

    baseline = np.array(
        [_finite(item.get("baseline", 0.0), field="baseline") for item in items],
        dtype=float,
    )
    if np.any(baseline < 0) or not math.isclose(float(baseline.sum()), total, abs_tol=1e-7):
        raise ValueError("Baseline allocations must be non-negative and total allocation_total")

    reasons = _infeasibility_checks(total, bounds)
    rows = _constraint_rows(items, constraints)
    a_ub: list[np.ndarray] = []
    b_ub: list[float] = []
    for row in rows:
        if row.direction == "max":
            a_ub.append(row.coefficients)
            b_ub.append(row.bound)
        else:
            a_ub.append(-row.coefficients)
            b_ub.append(-row.bound)

    coefficients = _objective_coefficients(items, objective, dict(payload.get("weights") or {}))
    result = linprog(
        coefficients,
        A_ub=np.vstack(a_ub) if a_ub else None,
        b_ub=np.array(b_ub) if b_ub else None,
        A_eq=np.ones((1, len(items))),
        b_eq=np.array([total]),
        bounds=bounds,
        method="highs",
    )
    scenario_id = f"OPT-{uuid.uuid4().hex[:16].upper()}"
    if not result.success:
        if result.message:
            reasons.append(str(result.message))
        return {
            "scenario_id": scenario_id,
            "feasible": False,
            "solver_status": int(result.status),
            "objective": objective,
            "decision_dimension": dimension,
            "infeasibility_explanation": reasons or ["The configured constraints conflict."],
            "applied": False,
            "saved": False,
            "approval_required": True,
            "limitations": [
                "This linear model depends on supplied marginal effects and does not prove causality.",
                "No allocation is applied automatically.",
            ],
        }

    optimised = np.asarray(result.x, dtype=float)
    baseline_effects = _effects(items, baseline)
    optimised_effects = _effects(items, optimised)
    constraint_details: list[dict[str, Any]] = []
    marginals = list(getattr(result.ineqlin, "marginals", [])) if a_ub else []
    for index, row in enumerate(rows):
        achieved = float(np.dot(row.coefficients, optimised))
        slack = row.bound - achieved if row.direction == "max" else achieved - row.bound
        constraint_details.append(
            {
                "constraint": row.name,
                "direction": row.direction,
                "bound": row.bound,
                "achieved": achieved,
                "slack": slack,
                "binding": abs(slack) <= 1e-7,
                "shadow_value": float(marginals[index]) if index < len(marginals) else None,
            }
        )
    allocations = [
        {
            "name": name,
            "baseline": float(baseline[index]),
            "optimised": float(optimised[index]),
            "change": float(optimised[index] - baseline[index]),
        }
        for index, name in enumerate(names)
    ]
    saved = bool(payload.get("save_scenario", False))
    output: dict[str, Any] = {
        "scenario_id": scenario_id,
        "feasible": True,
        "solver_status": int(result.status),
        "solver_message": str(result.message),
        "objective": objective,
        "objective_value": float(-result.fun if objective.startswith("maximise") else result.fun),
        "decision_dimension": dimension,
        "baseline_allocation": {row["name"]: row["baseline"] for row in allocations},
        "optimised_allocation": {row["name"]: row["optimised"] for row in allocations},
        "changed_allocations": [row for row in allocations if abs(row["change"]) > 1e-9],
        "expected_financial_effect": {
            field: optimised_effects[field] - baseline_effects[field]
            for field in ("expected_profit", "vendor_cost")
        },
        "expected_risk_effect": {
            field: optimised_effects[field] - baseline_effects[field]
            for field in ("expected_loss", "fraud_bps", "customer_friction")
        },
        "expected_operational_effect": {
            field: optimised_effects[field] - baseline_effects[field]
            for field in ("review_load", "customer_coverage", "regional_service")
        },
        "binding_constraints": [row["constraint"] for row in constraint_details if row["binding"]],
        "sensitivity": constraint_details,
        "applied": False,
        "saved": saved,
        "approval_required": True,
        "approval_state": "DRAFT",
        "limitations": [
            "Supplied marginal effects are treated as linear over the allocation range.",
            "Shadow values are local solver sensitivities, not guaranteed business impacts.",
            "The result is a governed scenario and is never applied automatically.",
        ],
    }
    if saved:
        if store is None:
            raise ValueError("A workflow store is required to save an optimisation scenario")
        store.create(
            "scenario_run",
            scenario_id,
            output,
            actor=actor,
            approval_state="DRAFT",
        )
    return output
