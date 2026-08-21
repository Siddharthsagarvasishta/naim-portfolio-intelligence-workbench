"""Restartable raw-to-mart pipeline with manifest and publication gate."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from naim_risk.config import NaimConfig
from naim_risk.data_generation import generate_synthetic_portfolio
from naim_risk.metrics.core import enrich_performance
from naim_risk.storage import build_analytical_catalogue, read_table, write_layer, write_table
from naim_risk.transformations import build_marts
from naim_risk.types import PipelineData, ValidationCheck, ValidationResult
from naim_risk.validation import validate_tables


def _git_commit() -> str | None:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
            or None
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _curated_tables(accepted: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    master = accepted["customer_account_master"].copy()
    performance = enrich_performance(accepted["monthly_account_performance"], master)
    performance["net_credit_loss"] = (
        performance["chargeoff_amount"] - performance["recovery_amount"]
    )
    performance["active_account_flag"] = (
        (performance["inactive_flag"] == 0) & (performance["chargeoff_flag"] == 0)
    ).astype(int)
    performance["payment_to_statement_ratio"] = np.divide(
        performance["payment_amount"],
        performance["statement_balance"],
        out=np.zeros(len(performance), dtype=float),
        where=performance["statement_balance"].to_numpy(dtype=float) != 0,
    )
    performance["customer_friction_flag"] = (
        performance[
            [
                "manual_review_count",
                "declined_transaction_count",
                "step_up_authentication_count",
                "customer_contact_count",
            ]
        ].sum(axis=1)
        > 0
    ).astype(int)
    performance["months_on_book_band"] = pd.cut(
        performance["months_on_book"],
        bins=[-1, 3, 6, 9, 12, 18, 24, np.inf],
        labels=["0-3", "4-6", "7-9", "10-12", "13-18", "19-24", "25+"],
    ).astype(str)
    performance["current_risk_band"] = pd.cut(
        performance["risk_score"],
        bins=[-np.inf, 520, 600, 680, 740, np.inf],
        labels=[
            "E: High Risk",
            "D: Elevated Risk",
            "C: Moderate Risk",
            "B: Low Risk",
            "A: Very Low Risk",
        ],
    ).astype(str)
    return {
        "curated_customer_account": master,
        "curated_account_month": performance,
    }


def run_pipeline(config: NaimConfig, *, persist: bool = True) -> PipelineData:
    """Run deterministic generation, validation, curation and mart creation."""

    started = datetime.now(UTC)
    run_id = f"{config.profile.name}-{config.seed}-{config.config_hash[:12]}"
    raw_tables = generate_synthetic_portfolio(config)
    ground_truth = raw_tables.pop("_ground_truth_deterioration")
    paths: dict[str, Path] = {}
    if persist:
        raw_paths = write_layer(raw_tables, config.data_root / "raw" / run_id)
        paths.update({f"raw.{name}": path for name, path in raw_paths.items()})
        truth_path = write_table(ground_truth, config.data_root / "demo" / "ground_truth" / run_id)
        paths["test_only.ground_truth"] = truth_path
    validation = validate_tables({**raw_tables, "_ground_truth_deterioration": ground_truth})
    if persist and validation.quarantined:
        quarantine_paths = write_layer(
            validation.quarantined, config.data_root / "quarantine" / run_id
        )
        paths.update({f"quarantine.{name}": path for name, path in quarantine_paths.items()})
        for check in validation.checks:
            if check.status == "FAIL":
                table_name = check.check_id.split(".", 1)[0]
                path = quarantine_paths.get(table_name)
                if path is not None:
                    check.quarantine_location = str(path)
    marts: dict[str, pd.DataFrame] = {}
    storage_engine = "not_built"
    if validation.publication_allowed:
        curated = _curated_tables(validation.accepted)
        marts = build_marts(validation.accepted)
        if persist:
            validated_paths = write_layer(
                validation.accepted, config.data_root / "validated" / run_id
            )
            curated_paths = write_layer(curated, config.data_root / "curated" / run_id)
            mart_paths = write_layer(marts, config.data_root / "marts" / run_id)
            paths.update({f"validated.{name}": path for name, path in validated_paths.items()})
            paths.update({f"curated.{name}": path for name, path in curated_paths.items()})
            paths.update({f"mart.{name}": path for name, path in mart_paths.items()})
            catalogue_path, storage_engine = build_analytical_catalogue(
                validated_paths,
                mart_paths,
                config.data_root / "catalogue" / run_id,
            )
            paths["catalogue"] = catalogue_path
    performance = raw_tables["monthly_account_performance"]
    completed = datetime.now(UTC)
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "random_seed": config.seed,
        "profile": config.profile.name,
        "configured_accounts": config.profile.accounts,
        "configured_months": config.profile.months,
        "generation_timestamp": started.isoformat(),
        "completion_timestamp": completed.isoformat(),
        "duration_seconds": (completed - started).total_seconds(),
        "configuration_hash": config.config_hash,
        "code_version": _git_commit(),
        "synthetic_data": True,
        "synthetic_label": config.synthetic_label,
        "row_counts": {name: int(len(frame)) for name, frame in raw_tables.items()},
        "mart_row_counts": {name: int(len(frame)) for name, frame in marts.items()},
        "minimum_data_date": str(pd.Timestamp(performance["month"].min()).date()),
        "maximum_data_date": str(pd.Timestamp(performance["month"].max()).date()),
        "validation_status": validation.status,
        "publication_allowed": validation.publication_allowed,
        "quality_score": validation.quality_score,
        "rejected_row_counts": {
            name: int(len(frame)) for name, frame in validation.quarantined.items()
        },
        "storage_engine": storage_engine,
        "storage_format": "Parquet when PyArrow is available; CSV fallback otherwise",
        "paths": {name: str(path) for name, path in paths.items()},
        "ground_truth_ui_exposure_allowed": False,
    }
    if persist:
        manifest_root = config.data_root / "manifests" / run_id
        manifest_root.mkdir(parents=True, exist_ok=True)
        manifest_path = manifest_root / "run_manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        paths["manifest"] = manifest_path
        latest_path = config.data_root / "manifests" / "latest.json"
        latest_path.write_text(
            json.dumps({"run_id": run_id, "manifest": str(manifest_path)}, indent=2),
            encoding="utf-8",
        )
    return PipelineData(
        run_id=run_id,
        tables=validation.accepted if validation.publication_allowed else raw_tables,
        marts=marts,
        manifest=manifest,
        validation=validation,
        paths=paths,
    )


def load_pipeline_data(manifest_path: str | Path) -> PipelineData:
    """Reload a persisted validated run from its audit manifest."""

    path = Path(manifest_path)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    tables: dict[str, pd.DataFrame] = {}
    marts: dict[str, pd.DataFrame] = {}
    for key, value in manifest.get("paths", {}).items():
        source = Path(value)
        if key.startswith("validated.") and source.exists():
            tables[key.split(".", 1)[1]] = read_table(source)
        elif key.startswith("mart.") and source.exists():
            marts[key.split(".", 1)[1]] = read_table(source)
    validation = ValidationResult(
        status=str(manifest["validation_status"]),
        quality_score=float(manifest["quality_score"]),
        checks=[
            ValidationCheck(
                check_id="persisted_manifest",
                severity="Warning",
                status="PASS",
                affected_rows=0,
                business_impact="Reloaded from a previously validated manifest.",
                recommendation="Re-run validation after any source change.",
            )
        ],
        accepted=tables,
        quarantined={},
    )
    return PipelineData(
        run_id=str(manifest["run_id"]),
        tables=tables,
        marts=marts,
        manifest=manifest,
        validation=validation,
        paths={"manifest": path},
    )
