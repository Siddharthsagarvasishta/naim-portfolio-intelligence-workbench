"""Flatten the live interoperability evidence into tool-neutral CSV extracts."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path
from typing import Any


def safe(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"Refusing to create empty extract: {path}")
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: safe(row.get(key)) for key in fields})


def flatten(input_path: Path, export_root: Path) -> None:
    evidence = json.loads(input_path.read_text(encoding="utf-8"))
    registry = json.loads(Path("config/metric_registry.json").read_text(encoding="utf-8"))
    metadata = evidence["metadata"]
    reporting_period = evidence["selected_reporting_period"]
    evidence_scope_key = "|".join([evidence["evidence_id"], metadata["run_id"], reporting_period])
    common = {
        "evidence_scope_key": evidence_scope_key,
        "evidence_id": evidence["evidence_id"],
        "run_id": metadata["run_id"],
        "reporting_period": reporting_period,
        "metric_registry_version": metadata["metric_registry_version"],
        "synthetic_data_flag": True,
    }
    # Keep the interoperability extract deliberately scalar and stable. Rich
    # governance objects (lineage, guardrails, evidence bindings) remain in the
    # canonical JSON and must not leak into the flat Power BI/Tableau/SAS schema.
    kpis = [
        {
            **common,
            "absolute_change": row.get("absolute_change"),
            "comparison_period": row.get("comparison_period"),
            "definition": row.get("definition"),
            "denominator": row.get("denominator"),
            "metric_id": row.get("metric_id"),
            "metric_version": row.get("metric_version"),
            "name": row.get("name"),
            "prior_value": row.get("prior_value"),
            "relative_change": row.get("relative_change"),
            "statistical_status": row.get("statistical_status"),
            "status": row.get("status"),
            "unit": row.get("unit"),
            "value": row.get("value"),
        }
        for row in evidence["kpis"]
    ]
    strategies = [{**common, **row} for row in evidence["strategy_comparison"]["strategies"]]
    entities: list[dict[str, Any]] = []
    for entity_type, rows, id_key, name_key in (
        ("partner", evidence["partners"], "partner_id", "partner_name"),
        ("vendor", evidence["vendors"], "vendor_id", "vendor_name"),
        ("membership", evidence["memberships"], "membership_tier_id", "membership_tier_name"),
    ):
        for row in rows:
            rating = row.get("rating") or {}
            entities.append(
                {
                    **common,
                    "entity_type": entity_type,
                    "entity_id": row.get(id_key),
                    "entity_name": row.get(name_key),
                    "rating_score": rating.get("score"),
                    "rating_grade": rating.get("grade"),
                    "rating_confidence": rating.get("confidence"),
                    "expected_contribution": row.get(
                        "partner_contribution", row.get("expected_contribution")
                    ),
                    "total_vendor_cost": row.get("total_vendor_cost"),
                    "capacity_utilisation": row.get("capacity_utilisation"),
                    "transaction_value": row.get("transaction_value"),
                }
            )
    baseline_profit = float(evidence["scenarios"][0]["summary"]["total_expected_profit"])
    scenarios = [
        {
            **common,
            "scenario": row["scenario"],
            "horizon_months": row["summary"]["horizon_months"],
            "total_expected_profit": row["summary"]["total_expected_profit"],
            "profit_delta_from_baseline": row["summary"]["total_expected_profit"] - baseline_profit,
            "cumulative_net_credit_loss": row["summary"]["cumulative_net_credit_loss"],
            "loss_difference_from_baseline": row["summary"]["loss_difference_from_baseline"],
            "scenario_notice": row["notice"],
        }
        for row in evidence["scenarios"]
    ]
    tables = {
        "evidence_scope.csv": [
            {
                **common,
                "latest_available_period": metadata["as_of"],
                "evidence_sha256": evidence["evidence_sha256"],
                "quality_status": evidence["data_quality"]["status"],
                "quality_score": evidence["data_quality"]["score"],
                "publication_allowed": evidence["data_quality"]["publication_allowed"],
                "account_month_rows": metadata["row_counts"]["monthly_account_performance"],
            }
        ],
        "kpi_snapshot.csv": kpis,
        "strategy_snapshot.csv": strategies,
        "entity_rating_snapshot.csv": entities,
        "scenario_snapshot.csv": scenarios,
        "metric_dictionary.csv": [
            {
                "metric_id": row["metric_id"],
                "metric_name": row["name"],
                "business_definition": row["business_definition"],
                "formula": row["formula"],
                "numerator": row["numerator"],
                "denominator_definition": row.get("denominator"),
                "unit": row["unit"],
                "aggregation_behaviour": row["aggregation_behaviour"],
                "minimum_sample_rule": row["minimum_sample_rule"],
                "metric_owner": row["owner"],
                "metric_version": row["version"],
                "caveats": row["caveats"],
                "registry_version": registry["registry_version"],
                "effective_date": registry["effective_date"],
            }
            for row in registry["metrics"]
        ],
    }
    for name, rows in tables.items():
        write_rows(export_root / "powerbi" / "data" / name, rows)
        write_rows(export_root / "tableau" / "data" / name, rows)
        write_rows(export_root / "sas" / "data" / name, rows)
    shutil.copyfile(
        export_root / "validation" / "interop_reconciliation_totals.csv",
        export_root / "powerbi" / "validation_snapshot.csv",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("exports/validation/interop_evidence_snapshot.json"),
    )
    parser.add_argument("--export-root", type=Path, default=Path("exports"))
    args = parser.parse_args()
    flatten(args.input, args.export_root)
    print(f"Flattened live evidence from {args.input}")


if __name__ == "__main__":
    main()
