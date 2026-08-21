"""Real Tableau Hyper extract generation and disabled-by-default publishing interface."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import pandas as pd

from naim_risk.config import REPOSITORY_ROOT
from naim_risk.runtime_modes import dataset_hash
from naim_risk.service import WorkbenchService


class HyperUnavailable(RuntimeError):
    """Raised when the optional official Tableau Hyper API is absent."""


@dataclass(frozen=True)
class PublishTarget:
    server_url: str
    site_id: str
    project_id: str
    datasource_name: str


@dataclass(frozen=True)
class PublishResult:
    status: str
    published: bool
    detail: str
    remote_identifier: str | None = None


class TableauPublisher(Protocol):
    def publish(self, artifact: Path, target: PublishTarget) -> PublishResult:
        """Publish an already validated extract to an explicitly configured target."""


class DisabledTableauPublisher:
    """Safe default publisher that never transmits an artifact."""

    def publish(self, artifact: Path, target: PublishTarget) -> PublishResult:
        del artifact, target
        return PublishResult(
            status="DISABLED",
            published=False,
            detail=(
                "Tableau publication is disabled. Configure a credential-backed publisher "
                "and an explicit project target before use."
            ),
        )


def publisher_from_environment() -> TableauPublisher:
    """Return the non-publishing default unless a real adapter is supplied by the operator."""

    if os.getenv("NAIM_TABLEAU_PUBLISH_ENABLED", "false").lower() == "true":
        raise HyperUnavailable(
            "Publishing was requested but no credential-bearing Tableau adapter is installed"
        )
    return DisabledTableauPublisher()


def _hyper_api() -> Any:
    try:
        import tableauhyperapi as hyper
    except ImportError as exc:
        raise HyperUnavailable(
            "Install the optional interop dependency: pip install -e '.[interop]'"
        ) from exc
    return hyper


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sql_type(series: pd.Series, hyper: Any) -> Any:
    if pd.api.types.is_datetime64_any_dtype(series.dtype):
        return hyper.SqlType.date()
    if pd.api.types.is_bool_dtype(series.dtype):
        return hyper.SqlType.bool()
    if pd.api.types.is_integer_dtype(series.dtype):
        return hyper.SqlType.big_int()
    if pd.api.types.is_float_dtype(series.dtype):
        return hyper.SqlType.double()
    return hyper.SqlType.text()


def _value(value: Any, series: pd.Series) -> Any:
    if value is None:
        return None
    if isinstance(value, np.generic):
        value = value.item()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if pd.api.types.is_datetime64_any_dtype(series.dtype):
        converted = pd.Timestamp(value)
        return date(converted.year, converted.month, converted.day)
    if pd.api.types.is_bool_dtype(series.dtype):
        return bool(value)
    if pd.api.types.is_integer_dtype(series.dtype):
        return int(value)
    if pd.api.types.is_float_dtype(series.dtype):
        converted = float(value)
        return converted if math.isfinite(converted) else None
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(value, sort_keys=True, default=str)
    return str(value)


def _write_frame(
    connection: Any,
    schema: str,
    table_name: str,
    frame: pd.DataFrame,
    hyper: Any,
) -> int:
    clean = frame.copy()
    definition = hyper.TableDefinition(
        hyper.TableName(schema, table_name),
        [
            hyper.TableDefinition.Column(
                str(column),
                _sql_type(clean[column], hyper),
                hyper.Nullability.NULLABLE,
            )
            for column in clean.columns
        ],
    )
    connection.catalog.create_table(definition)
    with hyper.Inserter(connection, definition) as inserter:
        rows: Iterable[list[Any]] = (
            [_value(row[column], clean[column]) for column in clean.columns]
            for _, row in clean.iterrows()
        )
        inserter.add_rows(rows)
        inserter.execute()
    return len(clean)


def _extract_tables(service: WorkbenchService) -> dict[str, pd.DataFrame]:
    preferred_marts = (
        "FactAccountMonth",
        "FactStrategyDecision",
        "DimAccount",
        "DimDate",
        "DimProduct",
        "DimCustomerSegment",
        "DimAcquisitionChannel",
        "DimGeography",
        "DimRiskBand",
        "DimStrategy",
        "DimModelVersion",
        "MartPortfolioMonth",
        "MartSegmentMonth",
    )
    tables = {
        name: service.data.marts[name] for name in preferred_marts if name in service.data.marts
    }
    if not tables:
        tables = {
            "FactAccountMonth": service.tables["monthly_account_performance"],
            "DimAccount": service.tables["customer_account_master"],
        }
    return tables


def _in_memory_dataset_hash(tables: dict[str, pd.DataFrame]) -> str:
    """Hash the exact extract inputs when no persisted run manifest exists."""

    digest = hashlib.sha256()
    for name, frame in sorted(tables.items()):
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(
            frame.to_json(
                orient="split",
                date_format="iso",
                date_unit="ns",
                default_handler=str,
            ).encode("utf-8")
        )
        digest.update(b"\0")
    return digest.hexdigest()


def generate_hyper_extract(
    service: WorkbenchService,
    *,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Generate and reopen a typed Hyper extract, validating all control totals."""

    hyper = _hyper_api()
    target = (
        output_path or REPOSITORY_ROOT / "outputs" / "tableau" / "nAIM_Portfolio_Intelligence.hyper"
    ).resolve()
    if output_path is None and not target.is_relative_to((REPOSITORY_ROOT / "outputs").resolve()):
        raise ValueError("Hyper output must remain below outputs/")
    target.parent.mkdir(parents=True, exist_ok=True)
    tables = _extract_tables(service)
    metadata = service.metadata()
    loss_points = [
        row
        for row in service.trends()["data"]
        if row["metric_id"] == "ANNUALISED_NET_LOSS_RATE" and row["value"] is not None
    ]
    selected_loss = max(loss_points, key=lambda row: float(row["value"]))
    reporting_period = str(
        selected_loss.get("reporting_period") or selected_loss.get("month") or metadata["as_of"]
    )
    comparison_period = selected_loss.get("comparison_period")
    if comparison_period is None:
        comparison_period = (
            pd.Timestamp(reporting_period) - pd.offsets.MonthBegin(1)
        ).strftime("%Y-%m-%d")
    comparison_period = str(comparison_period)
    run_manifest = (
        service.config.data_root
        / "manifests"
        / str(metadata["run_id"])
        / "run_manifest.json"
    )
    if run_manifest.is_file():
        dataset_digest, dataset_basis = dataset_hash(run_manifest, service.config.data_root)
        source_dependencies = [
            str(run_manifest.relative_to(service.config.data_root)),
            "config/metric_registry.json",
        ]
    else:
        dataset_digest = _in_memory_dataset_hash(tables)
        dataset_basis = "in-memory-extract-tables"
        source_dependencies = ["in-memory-workbench-service", "config/metric_registry.json"]
    quality = service.data_quality()
    created_at = datetime.now(UTC).isoformat()
    metric_versions = pd.DataFrame(
        [
            {
                "metric_id": metric["metric_id"],
                "metric_name": metric["name"],
                "unit": metric["unit"],
                "metric_version": metric.get("version", "1.0.0"),
            }
            for metric in service.config.metrics
        ]
    )
    metadata_table = pd.DataFrame(
        [
            {"metadata_key": "product", "metadata_value": metadata["product"]},
            {"metadata_key": "run_id", "metadata_value": metadata["run_id"]},
            {"metadata_key": "configuration_hash", "metadata_value": service.config.config_hash},
            {"metadata_key": "dataset_hash", "metadata_value": dataset_digest},
            {"metadata_key": "dataset_hash_basis", "metadata_value": dataset_basis},
            {"metadata_key": "evidence_id", "metadata_value": f"NAIM-{metadata['run_id']}"},
            {
                "metadata_key": "metric_registry_version",
                "metadata_value": metadata["metric_registry_version"],
            },
                {
                    "metadata_key": "selected_reporting_period",
                    "metadata_value": reporting_period,
                },
                {
                    "metadata_key": "comparison_period",
                    "metadata_value": comparison_period,
            },
            {"metadata_key": "maximum_data_date", "metadata_value": metadata["as_of"]},
            {"metadata_key": "refresh_timestamp", "metadata_value": created_at},
            {"metadata_key": "synthetic_data", "metadata_value": "true"},
            {"metadata_key": "quality_status", "metadata_value": metadata["quality_status"]},
        ]
    )
    expected_counts = {name: len(frame) for name, frame in tables.items()}
    validation_table = pd.DataFrame(
        [
            {
                "table_name": name,
                "expected_rows": count,
                "validation_status": "PENDING",
            }
            for name, count in expected_counts.items()
        ]
    )

    with tempfile.TemporaryDirectory(prefix="naim-hyper-") as temp_directory:
        temporary_path = Path(temp_directory) / target.name
        log_directory = Path(temp_directory) / "logs"
        log_directory.mkdir()
        with hyper.HyperProcess(
            hyper.Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU,
            parameters={"log_dir": str(log_directory)},
        ) as process:
            with hyper.Connection(
                endpoint=process.endpoint,
                database=temporary_path,
                create_mode=hyper.CreateMode.CREATE_AND_REPLACE,
            ) as connection:
                connection.catalog.create_schema("Extract")
                for name, frame in tables.items():
                    _write_frame(connection, "Extract", name, frame, hyper)
                _write_frame(connection, "Extract", "Metadata", metadata_table, hyper)
                _write_frame(connection, "Extract", "MetricVersion", metric_versions, hyper)
                _write_frame(connection, "Extract", "ValidationTotals", validation_table, hyper)

            actual_counts: dict[str, int] = {}
            with hyper.Connection(process.endpoint, temporary_path) as connection:
                for name in expected_counts:
                    table = hyper.TableName("Extract", name)
                    actual_counts[name] = int(
                        connection.execute_scalar_query(f"SELECT COUNT(*) FROM {table}")
                    )
            if actual_counts != expected_counts:
                raise ValueError(
                    f"Hyper control-total mismatch: expected {expected_counts}, got {actual_counts}"
                )
        os.replace(temporary_path, target)

    artifact_hash = _sha256(target)
    manifest_path = target.with_suffix(".manifest.json")
    limitations = [
        "The Hyper extract contains synthetic demonstration data only.",
        "Tableau Desktop workbook authoring and publication were not executed in this environment.",
        "The extract is a local import artifact, not a live connection.",
    ]
    result = {
        "status": "PASS",
        "available": True,
        "artifact_id": f"HYPER-{artifact_hash[:20].upper()}",
        "artifact_type": "TABLEAU_HYPER_EXTRACT",
        "artifact_version": "2.0.0",
        "created_at": created_at,
        "created_at_utc": created_at,
        "created_by_component": "naim_risk.tableau",
        "source_workspace": "all_portfolio_control",
        "filename": target.name,
        "file_name": target.name,
        "size_bytes": target.stat().st_size,
        "file_size": target.stat().st_size,
        "sha256": artifact_hash,
        "run_id": metadata["run_id"],
        "source_snapshot_id": metadata["run_id"],
        "data_mode": "OFFLINE_SNAPSHOT",
        "reporting_period": reporting_period,
        "comparison_period": comparison_period,
        "filter_scope": {
            "headline_scope": "all_portfolio",
            "approved_reference_basket": "BASKET-001",
        },
        "dataset_profile": service.config.profile.name,
        "dataset_hash": dataset_digest,
        "dataset_hash_basis": dataset_basis,
        "configuration_hash": service.config.config_hash,
        "metric_registry_version": metadata["metric_registry_version"],
        "code_version": "2.0.0",
        "evidence_ids": [f"NAIM-{metadata['run_id']}"],
        "data_quality_status": quality["status"],
        "synthetic": True,
        "synthetic_data_flag": True,
        "dependencies": source_dependencies,
        "validation_status": "PASS",
        "validation_tests": [
            "official_tableau_hyper_api_execution",
            "typed_table_creation",
            "extract_reopen",
            "table_row_control_totals",
            "artifact_sha256",
        ],
        "known_limitations": limitations,
        "tables": [
            {
                "table": name,
                "expected_rows": expected_counts[name],
                "actual_rows": expected_counts[name],
                "status": "PASS",
            }
            for name in expected_counts
        ],
        "metadata_table": "Extract.Metadata",
        "metric_version_table": "Extract.MetricVersion",
        "validation_table": "Extract.ValidationTotals",
        "publishing": asdict(
            publisher_from_environment().publish(
                target,
                PublishTarget("disabled", "disabled", "disabled", target.stem),
            )
        ),
        "limitations": limitations,
    }
    manifest_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result
