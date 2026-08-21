"""Export a bounded, machine-readable interoperability snapshot from live analytics.

This script deliberately calls the same WorkbenchService methods used by the API.
It does not reimplement governed metric formulas.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from naim_risk.config import load_config
from naim_risk.service import WorkbenchService


def _ranked(
    rows: list[dict[str, Any]], value_path: tuple[str, ...], limit: int = 6
) -> list[dict[str, Any]]:
    def value(row: dict[str, Any]) -> float:
        current: Any = row
        for key in value_path:
            current = current.get(key, {}) if isinstance(current, dict) else {}
        return float(current or 0)

    return sorted(rows, key=value, reverse=True)[:limit]


def build_snapshot(profile: str) -> dict[str, Any]:
    service = WorkbenchService(load_config(profile))
    metadata = service.metadata()
    trends = service.trends()["data"]
    loss_points = [
        row
        for row in trends
        if row["metric_id"] == "ANNUALISED_NET_LOSS_RATE" and row["value"] is not None
    ]
    selected_period = max(loss_points, key=lambda row: float(row["value"]))["month"]
    kpis = service.kpis(period=selected_period)["data"]
    root = service.root_cause(period=selected_period)
    strategy = service.strategy_comparison()
    partners = service.partners()["data"]
    vendors = service.vendors()["data"]
    memberships = service.memberships()["data"]
    alerts = service.alerts()["data"]
    data_quality = service.data_quality()
    scenarios = [
        service.scenario_run({"scenario_name": name, "horizon_months": 12})
        for name in ("Baseline", "Mild Downturn", "Severe Downturn", "Fraud Shock")
    ]
    snapshot: dict[str, Any] = {
        "schema_version": "1.0.0",
        "evidence_id": f"NAIM-{metadata['run_id']}",
        "generation_method": f"WorkbenchService(load_config({profile!r}))",
        "source_ref": "src/naim_risk/service.py",
        "synthetic_data_flag": True,
        "metadata": metadata,
        "selected_reporting_period": selected_period,
        "selection_rule": "Peak calculated annualised net loss rate in the generated history",
        "kpis": kpis,
        "trends": trends,
        "root_cause": root,
        "strategy_comparison": strategy,
        "partners": _ranked(partners, ("rating", "score")),
        "vendors": _ranked(vendors, ("rating", "score")),
        "memberships": _ranked(memberships, ("rating", "score")),
        "scenarios": scenarios,
        "alerts": alerts,
        "data_quality": {
            "status": data_quality["status"],
            "score": data_quality["score"],
            "publication_allowed": data_quality["publication_allowed"],
            "completeness_percentage": data_quality["completeness_percentage"],
            "checks": data_quality["checks"],
        },
        "limitations": [
            "Synthetic, institution-neutral demonstration data.",
            "Root-cause and observational comparisons are associational unless a valid randomised design is identified.",
            "Scenario outputs are conditional estimates, not regulatory stress results.",
        ],
    }
    canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False)
    snapshot["evidence_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return snapshot


def reconciliation_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = snapshot["metadata"]
    rows: list[dict[str, Any]] = []
    for item in snapshot["kpis"]:
        rows.append(
            {
                "evidence_id": snapshot["evidence_id"],
                "reporting_period": item["reporting_period"],
                "comparison_period": item["comparison_period"],
                "scope": "All portfolio",
                "metric_id": item["metric_id"],
                "current_value": item["value"],
                "prior_value": item["prior_value"],
                "absolute_change": item["absolute_change"],
                "unit": item["unit"],
                "tolerance": 1e-9,
                "metric_version": item["metric_version"],
                "source_run_id": metadata["run_id"],
            }
        )
    finding = snapshot["root_cause"].get("finding") or {}
    for metric_id, field in (
        ("OBSERVED_CHANGE_BPS", "observed_change_bps"),
        ("MIX_CONTRIBUTION_BPS", "mix_contribution_bps"),
        ("PERFORMANCE_CONTRIBUTION_BPS", "within_segment_contribution_bps"),
        ("RECONCILIATION_RESIDUAL_BPS", "reconciliation_residual_bps"),
    ):
        rows.append(
            {
                "evidence_id": snapshot["evidence_id"],
                "reporting_period": metadata["as_of"],
                "comparison_period": finding.get("comparison_period"),
                "scope": "Root cause",
                "metric_id": metric_id,
                "current_value": finding.get(field),
                "prior_value": 0,
                "absolute_change": finding.get(field),
                "unit": "basis_points",
                "tolerance": 1e-9,
                "metric_version": metadata["metric_registry_version"],
                "source_run_id": metadata["run_id"],
            }
        )
    baseline_profit = float(snapshot["scenarios"][0]["summary"]["total_expected_profit"])
    for scenario in snapshot["scenarios"]:
        summary = scenario["summary"]
        rows.append(
            {
                "evidence_id": snapshot["evidence_id"],
                "reporting_period": metadata["as_of"],
                "comparison_period": "Baseline",
                "scope": f"Scenario: {scenario['scenario']}",
                "metric_id": "SCENARIO_TOTAL_EXPECTED_PROFIT",
                "current_value": summary["total_expected_profit"],
                "prior_value": baseline_profit,
                "absolute_change": summary["total_expected_profit"] - baseline_profit,
                "unit": "currency",
                "tolerance": 1e-6,
                "metric_version": metadata["assumption_version"],
                "source_run_id": metadata["run_id"],
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="default")
    parser.add_argument("--output-dir", type=Path, default=Path("exports/validation"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    snapshot = build_snapshot(args.profile)
    snapshot_path = args.output_dir / "interop_evidence_snapshot.json"
    snapshot_path.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    rows = reconciliation_rows(snapshot)
    csv_path = args.output_dir / "interop_reconciliation_totals.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(
        json.dumps(
            {
                "evidence": str(snapshot_path),
                "reconciliation": str(csv_path),
                "evidence_id": snapshot["evidence_id"],
                "sha256": snapshot["evidence_sha256"],
                "kpi_count": len(snapshot["kpis"]),
                "row_count": snapshot["metadata"]["row_counts"]["monthly_account_performance"],
                "quality_status": snapshot["data_quality"]["status"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
