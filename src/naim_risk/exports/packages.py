"""Excel and Power BI-ready packages with reconciliation metadata."""

from __future__ import annotations

import json
import tempfile
import zipfile
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:
    from naim_risk.service import WorkbenchService


def _neutralise_formula_injection(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in result.select_dtypes(include=["object", "string"]).columns:
        result[column] = result[column].map(
            lambda value: (
                f"'{value}"
                if isinstance(value, str) and value.startswith(("=", "+", "-", "@"))
                else value
            )
        )
    return result


def _export_root(service: WorkbenchService) -> Path:
    path = service.config.data_root / "generated_exports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_exports(service: WorkbenchService) -> list[dict[str, Any]]:
    root = _export_root(service)
    return [
        {
            "artifact_id": sha256(path.name.encode()).hexdigest()[:24],
            "filename": path.name,
            "size_bytes": path.stat().st_size,
            "modified_timestamp": path.stat().st_mtime,
        }
        for path in sorted(root.glob("*"))
        if path.is_file()
    ]


def generate_excel_export(service: WorkbenchService) -> Path:
    """Create a multi-sheet workbook from live validated calculations."""

    try:
        import openpyxl  # noqa: F401
    except (ImportError, ModuleNotFoundError) as exc:
        raise RuntimeError(
            "Excel export requires the locked openpyxl dependency; install requirements.lock."
        ) from exc
    target = _export_root(service) / f"naim-excel-{service.data.run_id}.xlsx"
    sheets = {
        "KPI Summary": pd.DataFrame(service.kpis()["data"]),
        "KPI Trends": pd.DataFrame(service.trends()["data"]),
        "Alerts": pd.DataFrame(service.alerts()["data"]),
        "Partner Portfolio": pd.DataFrame(service.partners()["data"]),
        "Vendor Portfolio": pd.DataFrame(service.vendors()["data"]),
        "Membership Portfolio": pd.DataFrame(service.memberships()["data"]),
        "Metric Registry": pd.DataFrame(list(service.config.metrics)),
        "Scenario Assumptions": pd.DataFrame(
            [
                {"scenario": scenario, **values}
                for scenario, values in service.config.scenarios.items()
            ]
        ),
        "Provenance": pd.DataFrame(
            [
                {
                    "run_id": service.data.run_id,
                    "synthetic_data": True,
                    "quality_status": service.data.validation.status,
                    "configuration_hash": service.config.config_hash,
                    "minimum_data_date": service.data.manifest["minimum_data_date"],
                    "maximum_data_date": service.data.manifest["maximum_data_date"],
                    "metric_registry_version": "1.0.0",
                    "detail_exported": False,
                }
            ]
        ),
    }
    with pd.ExcelWriter(target, engine="openpyxl") as writer:
        for sheet_name, frame in sheets.items():
            _neutralise_formula_injection(frame).to_excel(
                writer, sheet_name=sheet_name[:31], index=False
            )
            worksheet = writer.book[sheet_name[:31]]
            worksheet.freeze_panes = "A2"
            worksheet.auto_filter.ref = worksheet.dimensions
            for column_cells in worksheet.columns:
                width = min(
                    55,
                    max(
                        10,
                        max(
                            len(str(cell.value)) if cell.value is not None else 0
                            for cell in column_cells
                        )
                        + 2,
                    ),
                )
                worksheet.column_dimensions[column_cells[0].column_letter].width = width
    return target


def generate_powerbi_package(service: WorkbenchService) -> Path:
    """Create Power BI-ready CSV facts/dimensions plus relationships and metrics."""

    target = _export_root(service) / f"naim-powerbi-{service.data.run_id}.zip"
    relationship_spec = {
        "model": "nAIM synthetic analytical star schema",
        "relationships": [
            {
                "from": "FactAccountMonth.account_key",
                "to": "DimAccount.account_key",
                "cardinality": "many-to-one",
                "active": True,
            },
            {
                "from": "FactAccountMonth.date_key",
                "to": "DimDate.date_key",
                "cardinality": "many-to-one",
                "active": True,
            },
            {
                "from": "FactAccountMonth.strategy_key",
                "to": "DimStrategy.strategy_key",
                "cardinality": "many-to-one",
                "active": True,
            },
        ],
        "many_to_many_relationships": [],
        "null_handling": "Missing measures are not silently treated as zero.",
    }
    with tempfile.TemporaryDirectory(prefix="naim-powerbi-") as temporary:
        staging = Path(temporary)
        selected = {
            name: frame
            for name, frame in service.data.marts.items()
            if name
            in {
                "DimDate",
                "DimAccount",
                "DimProduct",
                "DimAcquisitionChannel",
                "DimGeography",
                "DimCustomerSegment",
                "DimRiskBand",
                "DimStrategy",
                "FactAccountMonth",
                "FactStrategyDecision",
                "MartPortfolioMonth",
                "MartSegmentMonth",
            }
        }
        for name, frame in selected.items():
            _neutralise_formula_injection(frame).to_csv(staging / f"{name}.csv", index=False)
        (staging / "relationships.json").write_text(
            json.dumps(relationship_spec, indent=2), encoding="utf-8"
        )
        (staging / "metric_registry.json").write_text(
            json.dumps({"version": "1.0.0", "metrics": list(service.config.metrics)}, indent=2),
            encoding="utf-8",
        )
        (staging / "reconciliation.json").write_text(
            json.dumps(
                {
                    "run_id": service.data.run_id,
                    "quality_status": service.data.validation.status,
                    "row_counts": service.data.manifest["mart_row_counts"],
                    "synthetic_data": True,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        with zipfile.ZipFile(target, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(staging.glob("*")):
                archive.write(path, arcname=path.name)
    return target
