"""Queue, vendor capacity and risk-strategy workload translation."""

from __future__ import annotations

from typing import Any

import pandas as pd


def capacity_summary(vendor_performance: pd.DataFrame) -> dict[str, Any]:
    latest = vendor_performance[
        vendor_performance["month"] == vendor_performance["month"].max()
    ].copy()
    rows = []
    for row in latest.itertuples(index=False):
        productive_hours = 160.0
        handling_hours = row.cases_received * row.average_processing_minutes / 60.0
        assumed_staff = max(1.0, row.process_volume / 85000.0)
        internal_capacity_hours = assumed_staff * productive_hours
        rows.append(
            {
                "vendor_id": row.vendor_id,
                "incoming_cases": int(row.cases_received),
                "completed_cases": int(row.cases_completed),
                "backlog": int(row.cases_pending),
                "average_handling_minutes": float(row.average_processing_minutes),
                "assumed_staff": assumed_staff,
                "capacity_hours": internal_capacity_hours,
                "required_hours": handling_hours,
                "capacity_utilisation": handling_hours / internal_capacity_hours,
                "overtime_hours": max(0.0, handling_hours - internal_capacity_hours),
                "sla_risk": "High" if handling_hours > internal_capacity_hours else "Managed",
                "expected_cost": float(row.total_vendor_cost),
            }
        )
    return {
        "as_of": str(pd.Timestamp(latest["month"].max()).date()) if len(latest) else None,
        "data": rows,
    }


def run_capacity_scenario(
    vendor_performance: pd.DataFrame,
    *,
    volume_multiplier: float = 1.0,
    capacity_multiplier: float = 1.0,
    handling_time_multiplier: float = 1.0,
    review_threshold_change: float = 0.0,
) -> dict[str, Any]:
    if not (0.5 <= volume_multiplier <= 3.0):
        raise ValueError("volume_multiplier must be between 0.5 and 3.0")
    if not (0.1 <= capacity_multiplier <= 2.0):
        raise ValueError("capacity_multiplier must be between 0.1 and 2.0")
    if not (0.5 <= handling_time_multiplier <= 3.0):
        raise ValueError("handling_time_multiplier must be between 0.5 and 3.0")
    base = capacity_summary(vendor_performance)
    rows = []
    threshold_volume_effect = max(-0.4, min(0.8, -review_threshold_change * 1.8))
    for row in base["data"]:
        incoming = row["incoming_cases"] * volume_multiplier * (1 + threshold_volume_effect)
        required = incoming * row["average_handling_minutes"] * handling_time_multiplier / 60.0
        capacity = row["capacity_hours"] * capacity_multiplier
        rows.append(
            {
                "vendor_id": row["vendor_id"],
                "projected_cases": incoming,
                "projected_required_hours": required,
                "projected_capacity_hours": capacity,
                "projected_utilisation": required / capacity if capacity else None,
                "capacity_shortfall_hours": max(0.0, required - capacity),
                "incremental_operational_cost": max(0.0, required - capacity) * 32.0,
                "sla_risk": "High" if required > capacity else "Managed",
            }
        )
    return {
        "assumptions": {
            "volume_multiplier": volume_multiplier,
            "capacity_multiplier": capacity_multiplier,
            "handling_time_multiplier": handling_time_multiplier,
            "review_threshold_change": review_threshold_change,
        },
        "data": rows,
        "scenario_notice": "Capacity output is a transparent synthetic scenario estimate.",
    }
