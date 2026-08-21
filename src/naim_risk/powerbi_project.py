"""Source-control-friendly Power BI Project scaffold and static validation.

The generator deliberately creates a PBIP source project, never a fabricated PBIX.
Power BI Desktop and Power BI Service validation remain explicit operator gates.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from naim_risk.config import REPOSITORY_ROOT
from naim_risk.runtime_modes import dataset_hash

PROJECT_NAME = "nAIM.PowerBIProject"
PRODUCT_NAME = "nAIM Portfolio Intelligence Workbench"
TAGLINE = "Name the movement. Own the evidence."
CAPABILITY_STATUS = "INTEGRATION_ONLY"
SCHEMA_VERSION = "2.0.0"
TMDL_COMPATIBILITY_LEVEL = 1601
_LINEAGE_NAMESPACE = uuid.UUID("099c8a04-f898-48f2-8931-9b8164aa3607")


class PowerBIProjectError(RuntimeError):
    """Raised when the project cannot be generated or statically validated."""


class PowerBIPublisherConfigurationError(PowerBIProjectError):
    """Raised when publication is enabled without complete credentials or an adapter."""


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    data_type: str
    m_type: str
    format_string: str | None = None
    hidden: bool = False


@dataclass(frozen=True)
class TableSpec:
    name: str
    source_file: str
    columns: tuple[ColumnSpec, ...]


@dataclass(frozen=True)
class MeasureSpec:
    name: str
    expression: str
    format_string: str


@dataclass(frozen=True)
class PowerBIPublishSettings:
    """Credential references for an explicitly injected publisher adapter."""

    tenant_id: str
    client_id: str
    client_secret: str
    workspace_id: str

    @classmethod
    def from_environment(cls) -> PowerBIPublishSettings | None:
        enabled = os.getenv("NAIM_POWERBI_PUBLISH_ENABLED", "false").strip().lower()
        if enabled not in {"true", "1", "yes"}:
            return None
        names = {
            "tenant_id": "NAIM_POWERBI_TENANT_ID",
            "client_id": "NAIM_POWERBI_CLIENT_ID",
            "client_secret": "NAIM_POWERBI_CLIENT_SECRET",
            "workspace_id": "NAIM_POWERBI_WORKSPACE_ID",
        }
        values = {field: os.getenv(variable, "").strip() for field, variable in names.items()}
        missing = [names[field] for field, value in values.items() if not value]
        if missing:
            raise PowerBIPublisherConfigurationError(
                "Power BI publication is enabled but required environment variables are missing: "
                + ", ".join(sorted(missing))
            )
        return cls(**values)


@dataclass(frozen=True)
class PowerBIPublishTarget:
    semantic_model_name: str
    report_name: str


@dataclass(frozen=True)
class PowerBIPublishResult:
    status: str
    published: bool
    detail: str
    remote_identifier: str | None = None


class PowerBIPublisher(Protocol):
    """Boundary for an operator-supplied, credential-backed publication adapter."""

    def publish(
        self,
        project_root: Path,
        settings: PowerBIPublishSettings | None,
        target: PowerBIPublishTarget,
    ) -> PowerBIPublishResult:
        """Publish an already Desktop-validated project to an approved workspace."""


class DisabledPowerBIPublisher:
    """Safe publisher default: it performs no authentication and no network calls."""

    def publish(
        self,
        project_root: Path,
        settings: PowerBIPublishSettings | None,
        target: PowerBIPublishTarget,
    ) -> PowerBIPublishResult:
        del project_root, settings, target
        return PowerBIPublishResult(
            status="DISABLED",
            published=False,
            detail=(
                "Power BI publication is disabled. Validate the project in Power BI Desktop, "
                "configure environment credentials, and inject an approved publisher adapter."
            ),
        )


def publisher_from_environment(
    adapter: PowerBIPublisher | None = None,
) -> tuple[PowerBIPublisher, PowerBIPublishSettings | None]:
    """Resolve the publisher without ever falling back to an implicit network action."""

    settings = PowerBIPublishSettings.from_environment()
    if settings is None:
        return DisabledPowerBIPublisher(), None
    if adapter is None:
        raise PowerBIPublisherConfigurationError(
            "Power BI credentials are configured, but no approved publisher adapter was supplied"
        )
    return adapter, settings


def _c(
    name: str,
    data_type: str = "string",
    m_type: str = "type text",
    format_string: str | None = None,
    *,
    hidden: bool = False,
) -> ColumnSpec:
    return ColumnSpec(name, data_type, m_type, format_string, hidden)


TABLES: tuple[TableSpec, ...] = (
    TableSpec(
        "evidence_scope",
        "evidence_scope.csv",
        (
            _c("evidence_scope_key", hidden=True),
            _c("evidence_id"),
            _c("run_id"),
            _c("reporting_period", "dateTime", "type date", "yyyy-mm-dd"),
            _c("metric_registry_version"),
            _c("synthetic_data_flag", "boolean", "type logical"),
            _c("latest_available_period", "dateTime", "type date", "yyyy-mm-dd"),
            _c("evidence_sha256"),
            _c("quality_status"),
            _c("quality_score", "double", "type number", "0.0"),
            _c("publication_allowed", "boolean", "type logical"),
            _c("account_month_rows", "int64", "Int64.Type", "#,0"),
        ),
    ),
    TableSpec(
        "kpi_snapshot",
        "kpi_snapshot.csv",
        (
            _c("evidence_scope_key", hidden=True),
            _c("evidence_id", hidden=True),
            _c("run_id", hidden=True),
            _c("reporting_period", "dateTime", "type date", "yyyy-mm-dd"),
            _c("metric_registry_version"),
            _c("synthetic_data_flag", "boolean", "type logical"),
            _c("absolute_change", "double", "type number", "0.00"),
            _c("comparison_period", "dateTime", "type date", "yyyy-mm-dd"),
            _c("definition"),
            _c("denominator", "double", "type number", "#,0.00"),
            _c("metric_id"),
            _c("metric_version"),
            _c("name"),
            _c("prior_value", "double", "type number", "0.00"),
            _c("relative_change", "double", "type number", "0.00%"),
            _c("statistical_status"),
            _c("status"),
            _c("unit"),
            _c("value", "double", "type number", "0.00"),
        ),
    ),
    TableSpec(
        "metric_dictionary",
        "metric_dictionary.csv",
        (
            _c("metric_id"),
            _c("metric_name"),
            _c("business_definition"),
            _c("formula"),
            _c("numerator"),
            _c("denominator_definition"),
            _c("unit"),
            _c("aggregation_behaviour"),
            _c("minimum_sample_rule", "int64", "Int64.Type", "#,0"),
            _c("metric_owner"),
            _c("metric_version"),
            _c("caveats"),
            _c("registry_version"),
            _c("effective_date", "dateTime", "type date", "yyyy-mm-dd"),
        ),
    ),
    TableSpec(
        "strategy_snapshot",
        "strategy_snapshot.csv",
        (
            _c("evidence_scope_key", hidden=True),
            _c("evidence_id", hidden=True),
            _c("run_id", hidden=True),
            _c("reporting_period", "dateTime", "type date", "yyyy-mm-dd"),
            _c("metric_registry_version"),
            _c("synthetic_data_flag", "boolean", "type logical"),
            _c("assignment_count", "int64", "Int64.Type", "#,0"),
            _c("assignment_share", "double", "type number", "0.00%"),
            _c("attrition_rate", "double", "type number", "0.00%"),
            _c("complaint_rate_per_1000", "double", "type number", "0.0"),
            _c("customer_friction_rate", "double", "type number", "0.00%"),
            _c("eligible_accounts", "int64", "Int64.Type", "#,0"),
            _c("expected_profit", "double", "type number", "#,0;(#,0);-"),
            _c("false_positive_rate", "double", "type number", "0.00%"),
            _c("fraud_bps", "double", "type number", '0.0 "bps"'),
            _c("fraud_event_ci_lower", "double", "type number", "0.00%"),
            _c("fraud_event_ci_upper", "double", "type number", "0.00%"),
            _c("loss_rate", "double", "type number", "0.00%"),
            _c("manual_review_rate", "double", "type number", "0.00%"),
            _c("minimum_sample_met", "boolean", "type logical"),
            _c("net_credit_loss", "double", "type number", "#,0;(#,0);-"),
            _c("operational_minutes", "double", "type number", "#,0"),
            _c("strategy"),
            _c("transaction_value", "double", "type number", "#,0;(#,0);-"),
        ),
    ),
    TableSpec(
        "entity_rating_snapshot",
        "entity_rating_snapshot.csv",
        (
            _c("evidence_scope_key", hidden=True),
            _c("evidence_id", hidden=True),
            _c("run_id", hidden=True),
            _c("reporting_period", "dateTime", "type date", "yyyy-mm-dd"),
            _c("metric_registry_version"),
            _c("synthetic_data_flag", "boolean", "type logical"),
            _c("entity_type"),
            _c("entity_id"),
            _c("entity_name"),
            _c("rating_score", "double", "type number", "0.0"),
            _c("rating_grade"),
            _c("rating_confidence"),
            _c("expected_contribution", "double", "type number", "#,0;(#,0);-"),
            _c("total_vendor_cost", "double", "type number", "#,0;(#,0);-"),
            _c("capacity_utilisation", "double", "type number", "0.00%"),
            _c("transaction_value", "double", "type number", "#,0;(#,0);-"),
        ),
    ),
    TableSpec(
        "scenario_snapshot",
        "scenario_snapshot.csv",
        (
            _c("evidence_scope_key", hidden=True),
            _c("evidence_id", hidden=True),
            _c("run_id", hidden=True),
            _c("reporting_period", "dateTime", "type date", "yyyy-mm-dd"),
            _c("metric_registry_version"),
            _c("synthetic_data_flag", "boolean", "type logical"),
            _c("scenario"),
            _c("horizon_months", "int64", "Int64.Type", "#,0"),
            _c("total_expected_profit", "double", "type number", "#,0;(#,0);-"),
            _c("profit_delta_from_baseline", "double", "type number", "#,0;(#,0);-"),
            _c("cumulative_net_credit_loss", "double", "type number", "#,0;(#,0);-"),
            _c("loss_difference_from_baseline", "double", "type number", "#,0;(#,0);-"),
            _c("scenario_notice"),
        ),
    ),
)


MEASURES: tuple[MeasureSpec, ...] = (
    MeasureSpec(
        "Annualised Net Loss Rate",
        "CALCULATE ( MAX ( 'kpi_snapshot'[value] ), 'kpi_snapshot'[metric_id] = \"ANNUALISED_NET_LOSS_RATE\" )",
        "0.00%",
    ),
    MeasureSpec(
        "Annualised Net Loss Rate Prior",
        "CALCULATE ( MAX ( 'kpi_snapshot'[prior_value] ), 'kpi_snapshot'[metric_id] = \"ANNUALISED_NET_LOSS_RATE\" )",
        "0.00%",
    ),
    MeasureSpec(
        "Loss Rate Movement bps",
        "( [Annualised Net Loss Rate] - [Annualised Net Loss Rate Prior] ) * 10000",
        '0.0 "bps"',
    ),
    MeasureSpec(
        "30+ Delinquency Rate",
        "CALCULATE ( MAX ( 'kpi_snapshot'[value] ), 'kpi_snapshot'[metric_id] = \"DELINQUENCY_30_ACCOUNT_RATE\" )",
        "0.00%",
    ),
    MeasureSpec(
        "Confirmed Fraud bps",
        "CALCULATE ( MAX ( 'kpi_snapshot'[value] ), 'kpi_snapshot'[metric_id] = \"FRAUD_BPS\" )",
        '0.0 "bps"',
    ),
    MeasureSpec(
        "Manual Review Rate",
        "CALCULATE ( MAX ( 'kpi_snapshot'[value] ), 'kpi_snapshot'[metric_id] = \"MANUAL_REVIEW_RATE\" )",
        "0.00%",
    ),
    MeasureSpec(
        "False Positive Rate",
        "CALCULATE ( MAX ( 'kpi_snapshot'[value] ), 'kpi_snapshot'[metric_id] = \"FALSE_POSITIVE_RATE\" )",
        "0.00%",
    ),
    MeasureSpec(
        "Customer Friction Rate",
        "CALCULATE ( MAX ( 'kpi_snapshot'[value] ), 'kpi_snapshot'[metric_id] = \"CUSTOMER_FRICTION_RATE\" )",
        "0.00%",
    ),
    MeasureSpec(
        "Expected Profit",
        "CALCULATE ( MAX ( 'kpi_snapshot'[value] ), 'kpi_snapshot'[metric_id] = \"EXPECTED_PROFIT\" )",
        "#,0;(#,0);-",
    ),
    MeasureSpec(
        "Active Accounts",
        "CALCULATE ( MAX ( 'kpi_snapshot'[value] ), 'kpi_snapshot'[metric_id] = \"ACTIVE_ACCOUNTS\" )",
        "#,0",
    ),
    MeasureSpec("Selected KPI Value", "MAX ( 'kpi_snapshot'[value] )", "0.00"),
    MeasureSpec("Selected KPI Prior", "MAX ( 'kpi_snapshot'[prior_value] )", "0.00"),
    MeasureSpec("Selected KPI Change", "MAX ( 'kpi_snapshot'[absolute_change] )", "0.00"),
    MeasureSpec("Selected KPI Denominator", "MAX ( 'kpi_snapshot'[denominator] )", "#,0.00"),
    MeasureSpec(
        "Strategy Expected Profit",
        "SUM ( 'strategy_snapshot'[expected_profit] )",
        "#,0;(#,0);-",
    ),
    MeasureSpec("Strategy Fraud bps", "AVERAGE ( 'strategy_snapshot'[fraud_bps] )", '0.0 "bps"'),
    MeasureSpec(
        "Strategy False Positive Rate",
        "AVERAGE ( 'strategy_snapshot'[false_positive_rate] )",
        "0.00%",
    ),
    MeasureSpec("Entity Rating Score", "AVERAGE ( 'entity_rating_snapshot'[rating_score] )", "0.0"),
    MeasureSpec(
        "Entity Expected Contribution",
        "SUM ( 'entity_rating_snapshot'[expected_contribution] )",
        "#,0;(#,0);-",
    ),
    MeasureSpec(
        "Scenario Total Expected Profit",
        "SUM ( 'scenario_snapshot'[total_expected_profit] )",
        "#,0;(#,0);-",
    ),
    MeasureSpec(
        "Scenario Profit Impact",
        "SUM ( 'scenario_snapshot'[profit_delta_from_baseline] )",
        "#,0;(#,0);-",
    ),
    MeasureSpec("Evidence Quality Score", "MAX ( 'evidence_scope'[quality_score] )", "0.0"),
    MeasureSpec("Evidence Row Count", "MAX ( 'evidence_scope'[account_month_rows] )", "#,0"),
    MeasureSpec(
        "Evidence Publication Allowed",
        'IF ( MAX ( \'evidence_scope\'[publication_allowed] ) = TRUE (), "Yes", "No" )',
        "General",
    ),
)


RELATIONSHIPS = (
    ("kpi_snapshot", "evidence_scope_key", "evidence_scope", "evidence_scope_key"),
    ("strategy_snapshot", "evidence_scope_key", "evidence_scope", "evidence_scope_key"),
    ("entity_rating_snapshot", "evidence_scope_key", "evidence_scope", "evidence_scope_key"),
    ("scenario_snapshot", "evidence_scope_key", "evidence_scope", "evidence_scope_key"),
    ("kpi_snapshot", "metric_id", "metric_dictionary", "metric_id"),
)


REPORT_PAGES = (
    (
        "ReportSectionExecutiveCommandCentre",
        "Executive Command Centre",
        "SUPPORTED_BY_INCLUDED_EXTRACTS",
        "What changed, is the evidence publishable, and what needs attention?",
        ("KPI strip", "selected-versus-prior bridge", "quality gate", "evidence footer"),
    ),
    (
        "ReportSectionStrategyImpact",
        "Strategy Impact",
        "SUPPORTED_BY_INCLUDED_EXTRACTS",
        "What trade-offs are visible across approved strategies?",
        ("strategy matrix", "profit bars", "fraud and friction comparison", "validity warning"),
    ),
    (
        "ReportSectionEntityOversight",
        "Entity Oversight",
        "SUPPORTED_BY_INCLUDED_EXTRACTS",
        "Which partner, vendor, or membership entities need review?",
        ("rating table", "contribution chart", "entity-type filter", "rating caveat"),
    ),
    (
        "ReportSectionForecastStress",
        "Forecast and Stress",
        "SUPPORTED_BY_INCLUDED_EXTRACTS",
        "How does expected profit move under approved synthetic scenarios?",
        ("scenario bars", "impact table", "horizon label", "scenario disclaimer"),
    ),
    (
        "ReportSectionDataQuality",
        "Data Quality",
        "SUPPORTED_BY_INCLUDED_EXTRACTS",
        "Is the evidence safe to use and does it reconcile?",
        ("publication status", "quality score", "row count", "evidence hash"),
    ),
    (
        "ReportSectionMetricDictionary",
        "Metric Dictionary",
        "SUPPORTED_BY_INCLUDED_EXTRACTS",
        "What does each governed result mean?",
        ("searchable definition", "formula", "owner", "version and caveats"),
    ),
)


def _stable_uuid(value: str) -> str:
    return str(uuid.uuid5(_LINEAGE_NAMESPACE, value))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=False, ensure_ascii=False) + "\n"


def _safe_target(root: Path, relative_path: str) -> Path:
    candidate = (root / relative_path).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise PowerBIProjectError(f"Unsafe project path: {relative_path}")
    candidate.parent.mkdir(parents=True, exist_ok=True)
    return candidate


def _write_text(root: Path, relative_path: str, content: str) -> Path:
    path = _safe_target(root, relative_path)
    path.write_text(content, encoding="utf-8", newline="\n")
    return path


def _validate_source_headers(table: TableSpec, source: Path) -> int:
    with source.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise PowerBIProjectError(f"Source extract is empty: {source}") from exc
        expected = [column.name for column in table.columns]
        if header != expected:
            raise PowerBIProjectError(
                f"Unexpected columns for {table.source_file}: expected {expected}, got {header}"
            )
        rows = sum(1 for _ in reader)
    if rows < 1:
        raise PowerBIProjectError(f"Source extract has no evidence rows: {source}")
    return rows


def _column_tmdl(table_name: str, column: ColumnSpec) -> str:
    lines = [f"\tcolumn {column.name}", f"\t\tdataType: {column.data_type}"]
    if column.format_string:
        lines.append(f"\t\tformatString: {column.format_string}")
    if column.hidden:
        lines.append("\t\tisHidden")
    lines.extend(
        [
            f"\t\tlineageTag: {_stable_uuid(f'{table_name}.{column.name}')}",
            "\t\tsummarizeBy: none",
            f"\t\tsourceColumn: {column.name}",
            "",
            "\t\tannotation SummarizationSetBy = Automatic",
        ]
    )
    return "\n".join(lines)


def _measure_tmdl(measure: MeasureSpec) -> str:
    return "\n".join(
        [
            f"\tmeasure '{measure.name}' = {measure.expression}",
            f"\t\tformatString: {measure.format_string}",
            f"\t\tlineageTag: {_stable_uuid(f'measure.{measure.name}')}",
        ]
    )


def _table_tmdl(table: TableSpec) -> str:
    columns = "\n\n".join(_column_tmdl(table.name, column) for column in table.columns)
    transformations = ",\n".join(
        f'\t\t\t\t\t\t\t{{"{column.name}", {column.m_type}}}' for column in table.columns
    )
    measures = ""
    if table.name == "kpi_snapshot":
        measures = "\n\n" + "\n\n".join(_measure_tmdl(measure) for measure in MEASURES)
    return (
        f"table {table.name}\n"
        f"\tlineageTag: {_stable_uuid(f'table.{table.name}')}\n\n"
        f"{columns}{measures}\n\n"
        f"\tpartition {table.name} = m\n"
        "\t\tmode: import\n"
        "\t\tsource =\n"
        "\t\t\t\tlet\n"
        "\t\t\t\t\tSource = Csv.Document(\n"
        f'\t\t\t\t\t\tFile.Contents(nAIMExportRoot & "/{table.source_file}"),\n'
        f'\t\t\t\t\t\t[Delimiter = ",", Columns = {len(table.columns)}, '
        "Encoding = 65001, QuoteStyle = QuoteStyle.Csv]\n"
        "\t\t\t\t\t),\n"
        "\t\t\t\t\tPromotedHeaders = Table.PromoteHeaders("
        "Source, [PromoteAllScalars = true]),\n"
        "\t\t\t\t\tTyped = Table.TransformColumnTypes(\n"
        "\t\t\t\t\t\tPromotedHeaders,\n"
        "\t\t\t\t\t\t{\n"
        f"{transformations}\n"
        "\t\t\t\t\t\t},\n"
        '\t\t\t\t\t\t"en-US"\n'
        "\t\t\t\t\t)\n"
        "\t\t\t\tin\n"
        "\t\t\t\t\tTyped\n\n"
        "\tannotation PBI_NavigationStepName = Navigation\n"
        "\tannotation PBI_ResultType = Table\n"
    )


def _measures_dax() -> str:
    blocks = [
        "-- Governed nAIM snapshot measures generated from config/metric_registry.json.",
        "-- Values are synthetic evidence; this file is a reviewable companion to TMDL.",
        "",
    ]
    for measure in MEASURES:
        blocks.extend(
            [
                f"MEASURE 'kpi_snapshot'[{measure.name}] = {measure.expression}",
                f"-- Format string: {measure.format_string}",
                "",
            ]
        )
    return "\n".join(blocks).rstrip() + "\n"


def _relationships_tmdl() -> str:
    blocks: list[str] = []
    for from_table, from_column, to_table, to_column in RELATIONSHIPS:
        relationship_id = _stable_uuid(
            f"relationship.{from_table}.{from_column}.{to_table}.{to_column}"
        )
        blocks.append(
            "\n".join(
                [
                    f"relationship {relationship_id}",
                    f"\tfromColumn: {from_table}.{from_column}",
                    f"\ttoColumn: {to_table}.{to_column}",
                    "\tcrossFilteringBehavior: oneDirection",
                ]
            )
        )
    return "\n\n".join(blocks) + "\n"


def _report_page_specification() -> dict[str, object]:
    return {
        "$schema": "../../schemas/report-pages.schema.json",
        "schema_version": SCHEMA_VERSION,
        "capability_status": CAPABILITY_STATUS,
        "desktop_validation_performed": False,
        "required_visible_context": [
            "reporting period",
            "comparison period",
            "filter scope",
            "refresh timestamp",
            "metric-registry version",
            "synthetic-data disclaimer",
        ],
        "pages": [
            {
                "page_id": page_id,
                "display_name": name,
                "support_level": support,
                "question": question,
                "required_visuals": list(visuals),
            }
            for page_id, name, support, question, visuals in REPORT_PAGES
        ],
        "extension_pages": [
            {
                "display_name": name,
                "support_level": "REQUIRES_NATIVE_APPLICATION_MARTS",
            }
            for name in (
                "Portfolio Trends",
                "Vintage Explorer",
                "Migration Analysis",
                "Root-Cause Detail",
                "Basket Drill-through",
                "Vendor Capacity History",
                "Account Drill-through",
            )
        ],
    }


def _calculation_group_specification() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "name": "Comparison Mode",
        "status": "SPECIFICATION_REQUIRES_DESKTOP_VALIDATION",
        "precedence": 10,
        "scope": "Apply only to approved display measures; do not apply to text or evidence controls.",
        "items": [
            {"name": "Actual", "ordinal": 0, "expression": "SELECTEDMEASURE()"},
            {
                "name": "Prior Period",
                "ordinal": 1,
                "expression": (
                    "IF ( ISSELECTEDMEASURE ( [Selected KPI Value] ), "
                    "[Selected KPI Prior], BLANK () )"
                ),
            },
            {
                "name": "Variance",
                "ordinal": 2,
                "expression": (
                    "IF ( ISSELECTEDMEASURE ( [Selected KPI Value] ), "
                    "[Selected KPI Change], BLANK () )"
                ),
            },
            {
                "name": "Variance %",
                "ordinal": 3,
                "expression": (
                    "IF ( ISSELECTEDMEASURE ( [Selected KPI Value] ), "
                    "DIVIDE ( [Selected KPI Change], [Selected KPI Prior] ), BLANK () )"
                ),
                "format_string_expression": '"0.00%"',
            },
            {
                "name": "Scenario",
                "ordinal": 4,
                "expression": (
                    "IF ( ISSELECTEDMEASURE ( [Scenario Total Expected Profit] ), "
                    "SELECTEDMEASURE (), BLANK () )"
                ),
            },
        ],
        "unsupported_item": {
            "name": "YoY",
            "reason": "The included evidence extract is a bounded selected-period snapshot.",
        },
    }


def _field_parameters_specification() -> dict[str, object]:
    metric_items = tuple(
        (
            name,
            f"'kpi_snapshot'[{name}]",
        )
        for name in (
            "Annualised Net Loss Rate",
            "30+ Delinquency Rate",
            "Confirmed Fraud bps",
            "Manual Review Rate",
            "False Positive Rate",
            "Customer Friction Rate",
            "Expected Profit",
            "Active Accounts",
        )
    )
    dimension_items = (
        ("Metric", "'kpi_snapshot'[name]"),
        ("Strategy", "'strategy_snapshot'[strategy]"),
        ("Entity type", "'entity_rating_snapshot'[entity_type]"),
        ("Entity", "'entity_rating_snapshot'[entity_name]"),
        ("Scenario", "'scenario_snapshot'[scenario]"),
    )

    def parameter(name: str, kind: str, items: tuple[tuple[str, str], ...]) -> dict[str, object]:
        dax_rows = ",\n    ".join(
            f'("{label}", NAMEOF ( {field} ), {index})'
            for index, (label, field) in enumerate(items)
        )
        return {
            "name": name,
            "kind": kind,
            "parameter_metadata": {"version": 3, "kind": 2},
            "calculated_table_expression": "{\n    " + dax_rows + "\n}",
            "columns": [
                {"name": name, "source": "Value1", "sort_by": f"{name} Order"},
                {
                    "name": f"{name} Fields",
                    "source": "Value2",
                    "hidden": True,
                    "extended_property": "ParameterMetadata",
                },
                {"name": f"{name} Order", "source": "Value3", "hidden": True},
            ],
            "items": [
                {"label": label, "field": field, "ordinal": index}
                for index, (label, field) in enumerate(items)
            ],
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "SPECIFICATION_REQUIRES_DESKTOP_VALIDATION",
        "parameters": [
            parameter("Governed Metric", "measure", metric_items),
            parameter("Approved Dimension", "column", dimension_items),
        ],
        "guardrails": [
            "Only governed measures may be added.",
            "Rates must not be aggregated by sum.",
            "Independent snapshot grains must not be cross-joined.",
        ],
    }


def _theme() -> dict[str, object]:
    return {
        "name": "nAIM Portfolio Intelligence",
        "dataColors": [
            "#00ABA9",
            "#57B4E8",
            "#EEA12F",
            "#C43D4A",
            "#6C7F93",
            "#754FC6",
            "#1F7A8C",
            "#A8BAC8",
        ],
        "background": "#FFFFFF",
        "foreground": "#162436",
        "tableAccent": "#00ABA9",
        "good": "#11845B",
        "neutral": "#EEA12F",
        "bad": "#C43D4A",
        "maximum": "#0A1830",
        "center": "#D9E6EF",
        "minimum": "#F7FAFC",
        "textClasses": {
            "title": {"fontFace": "Segoe UI Semibold", "fontSize": 16, "color": "#162436"},
            "header": {"fontFace": "Segoe UI Semibold", "fontSize": 12, "color": "#162436"},
            "label": {"fontFace": "Segoe UI", "fontSize": 10, "color": "#5B6D80"},
            "callout": {"fontFace": "Segoe UI Semibold", "fontSize": 24, "color": "#0A1830"},
        },
        "visualStyles": {
            "*": {
                "*": {
                    "title": [
                        {
                            "show": True,
                            "fontFace": "Segoe UI Semibold",
                            "fontSize": 12,
                            "fontColor": {"solid": {"color": "#162436"}},
                            "alignment": "left",
                        }
                    ],
                    "background": [
                        {
                            "show": True,
                            "color": {"solid": {"color": "#FFFFFF"}},
                            "transparency": 0,
                        }
                    ],
                }
            }
        },
    }


def _report_pages_schema() -> dict[str, object]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://naim.invalid/schemas/report-pages.schema.json",
        "title": "nAIM Power BI report-page specification",
        "type": "object",
        "required": [
            "schema_version",
            "capability_status",
            "desktop_validation_performed",
            "required_visible_context",
            "pages",
        ],
        "properties": {
            "schema_version": {"type": "string"},
            "capability_status": {"const": CAPABILITY_STATUS},
            "desktop_validation_performed": {"const": False},
            "required_visible_context": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "string"},
            },
            "pages": {
                "type": "array",
                "minItems": len(REPORT_PAGES),
                "items": {
                    "type": "object",
                    "required": [
                        "page_id",
                        "display_name",
                        "support_level",
                        "question",
                        "required_visuals",
                    ],
                },
            },
        },
        "additionalProperties": True,
    }


def _validation_controls(row_counts: dict[str, int], registry_version: str) -> str:
    rows = [
        (
            "PBI-001",
            "BLOCKER",
            "capability_status",
            CAPABILITY_STATUS,
            "exact",
            "Build/project-manifest.json",
            "PENDING_DESKTOP_VALIDATION",
        ),
        (
            "PBI-002",
            "BLOCKER",
            "metric_registry_version",
            registry_version,
            "exact",
            "config/metric_registry.json",
            "STATIC_PASS",
        ),
        (
            "PBI-003",
            "BLOCKER",
            "synthetic_data_flag",
            "true",
            "exact",
            "Data/evidence_scope.csv",
            "STATIC_PASS",
        ),
        (
            "PBI-004",
            "BLOCKER",
            "relationship_cross_filter",
            "single direction",
            "exact",
            "SemanticModel/definition/relationships.tmdl",
            "STATIC_PASS",
        ),
        (
            "PBI-005",
            "BLOCKER",
            "report_semantic_model_pointer",
            "../SemanticModel",
            "exact",
            "Report/definition.pbir",
            "STATIC_PASS",
        ),
    ]
    for table_name, count in sorted(row_counts.items()):
        rows.append(
            (
                f"PBI-ROW-{table_name.upper()}",
                "BLOCKER",
                f"{table_name}_row_count",
                str(count),
                "exact",
                f"Data/{table_name}.csv",
                "STATIC_PASS",
            )
        )
    output = [
        "control_id,severity,control,expected,tolerance,source,status",
        *[",".join(row) for row in rows],
    ]
    return "\n".join(output) + "\n"


def _readme() -> str:
    return f"""# {PROJECT_NAME}

{PRODUCT_NAME} — {TAGLINE}

Status: **{CAPABILITY_STATUS}**

This is a source-control-friendly Power BI Project scaffold. It is not a PBIX file and it is
not a finished report. Static validation confirms the project shape, governed source hashes,
TMDL references, relationships, measures, format strings, page definitions, and absence of
embedded secrets. Power BI Desktop validation and a real Power BI Service publication test
have not been performed.

## Open and validate

1. Copy this whole directory to a Windows environment with a supported Power BI Desktop.
2. Open `nAIM.pbip`.
3. Set the Power Query parameter `nAIMExportRoot` to the absolute path of this project's
   `Data` directory. The committed placeholder is intentionally non-machine-specific.
4. Refresh all tables and confirm there are no type-conversion errors.
5. Review relationships: filters must flow from `evidence_scope` and `metric_dictionary` into
   their snapshot facts, never between independent fact grains.
6. Import `Report/theme/nAIM-theme.json`, then implement only the approved visual
   specifications in `Report/specifications/report-pages.json`.
7. Reconcile the selected evidence to `Validation/reconciliation_snapshot.csv` and complete
   `Deployment/deployment-checklist.md`.
8. Save the project only after the Desktop validation gate passes.

Calculation-group and field-parameter files are controlled specifications because their
behaviour must be applied and exercised in Desktop. The bounded snapshot does not support a
YoY item or native time-series pages; those require the application's point-in-time marts.

No publisher runs by default. Environment variable names and the publisher boundary are
documented in `Deployment/deployment-checklist.md`; credentials must never be written here.
"""


def _deployment_checklist() -> str:
    return """# Power BI deployment checklist

Capability remains `INTEGRATION_ONLY` until both local Desktop validation and a real,
authorised publication test are recorded. Every box below begins intentionally unchecked.

## Desktop gate

- [ ] Open `nAIM.pbip` in a currently supported Power BI Desktop release.
- [ ] Record the Desktop version and validation date in an external release record.
- [ ] Set `nAIMExportRoot` to the local `Data` folder; do not commit the absolute path.
- [ ] Refresh all six tables with zero Power Query errors.
- [ ] Confirm the five relationships and single-direction filters.
- [ ] Confirm metric IDs and registry version against `config/metric_registry.json`.
- [ ] Confirm every governed measure and format string.
- [ ] Apply and test the calculation-group specification only on approved measures.
- [ ] Apply and test both field-parameter specifications.
- [ ] Import and visually inspect the nAIM theme for contrast and readability.
- [ ] Build and inspect the six supported pages; do not infer unavailable time series.
- [ ] Display reporting period, comparison period, scope, refresh time, metric version,
      evidence ID, and synthetic-data disclaimer on every page.
- [ ] Reconcile every value in `Validation/reconciliation_snapshot.csv` within its tolerance.
- [ ] Test blank, missing, duplicate-key, and zero-denominator handling.
- [ ] Confirm there are no bidirectional or many-to-many relationships.
- [ ] Save the PBIP source changes and peer-review the diff.

## Service publication gate

- [ ] Complete tenant approval, workspace selection, data classification, and access review.
- [ ] Configure these environment variables outside source control:
      `NAIM_POWERBI_PUBLISH_ENABLED`, `NAIM_POWERBI_TENANT_ID`,
      `NAIM_POWERBI_CLIENT_ID`, `NAIM_POWERBI_CLIENT_SECRET`, and
      `NAIM_POWERBI_WORKSPACE_ID`.
- [ ] Inject an approved publisher adapter; the repository default never transmits data.
- [ ] Confirm the target workspace and item names before any write.
- [ ] Publish using least-privilege credentials and retain the remote operation ID.
- [ ] Refresh and reconcile the published semantic model.
- [ ] Validate permissions, row-level security if later added, export restrictions, and audit.
- [ ] Record rollback steps and remove temporary credentials.
- [ ] Change capability status to `LIVE` only after the real publication test passes.

PBIP publication mechanics vary by tenant and Fabric/Power BI API capability. This package
does not fabricate a remote success and does not contain a PBIX.
"""


def _build_report_definition(project_root: Path) -> None:
    _write_text(
        project_root,
        "Report/definition/version.json",
        _json(
            {
                "$schema": (
                    "https://developer.microsoft.com/json-schemas/fabric/item/report/"
                    "definition/version/1.0.0/schema.json"
                ),
                "version": "2.0.0",
            }
        ),
    )
    _write_text(
        project_root,
        "Report/definition/report.json",
        _json(
            {
                "$schema": (
                    "https://developer.microsoft.com/json-schemas/fabric/item/report/"
                    "definition/report/2.1.0/schema.json"
                ),
                "themeCollection": {
                    "baseTheme": {
                        "name": "CY24SU10",
                        "reportVersionAtImport": "5.58",
                        "type": "SharedResources",
                    }
                },
                "layoutOptimization": 0,
            }
        ),
    )
    page_ids = [page[0] for page in REPORT_PAGES]
    _write_text(
        project_root,
        "Report/definition/pages/pages.json",
        _json(
            {
                "$schema": (
                    "https://developer.microsoft.com/json-schemas/fabric/item/report/"
                    "definition/pagesMetadata/1.0.0/schema.json"
                ),
                "pageOrder": page_ids,
                "activePageName": page_ids[0],
            }
        ),
    )
    for page_id, display_name, _, _, _ in REPORT_PAGES:
        _write_text(
            project_root,
            f"Report/definition/pages/{page_id}/page.json",
            _json(
                {
                    "$schema": (
                        "https://developer.microsoft.com/json-schemas/fabric/item/report/"
                        "definition/page/2.0.0/schema.json"
                    ),
                    "name": page_id,
                    "displayName": display_name,
                    "displayOption": "FitToPage",
                    "height": 720,
                    "width": 1280,
                }
            ),
        )


def _platform_file(item_type: str, display_name: str, logical_name: str) -> dict[str, object]:
    return {
        "$schema": (
            "https://developer.microsoft.com/json-schemas/fabric/item/"
            "platformProperties/2.0.0/schema.json"
        ),
        "metadata": {
            "type": item_type,
            "displayName": display_name,
            "description": (
                f"{PRODUCT_NAME} synthetic demonstration {item_type.lower()}; "
                f"status {CAPABILITY_STATUS}."
            ),
        },
        "config": {"version": "2.0", "logicalId": _stable_uuid(logical_name)},
    }


def _copy_sources(
    project_root: Path, source_root: Path, registry_path: Path
) -> tuple[dict[str, int], list[dict[str, object]], str]:
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry_version = str(registry["registry_version"])
    governed_metric_ids = {str(metric["metric_id"]) for metric in registry["metrics"]}
    row_counts: dict[str, int] = {}
    source_manifest: list[dict[str, object]] = []
    for table in TABLES:
        source = source_root / table.source_file
        if not source.is_file():
            raise PowerBIProjectError(f"Missing governed source extract: {source}")
        _validate_source_headers(table, source)
        destination = _safe_target(project_root, f"Data/{table.source_file}")
        transformation = "none"
        if table.name == "kpi_snapshot":
            with source.open(encoding="utf-8", newline="") as input_handle:
                reader = csv.DictReader(input_handle)
                selected = [
                    row for row in reader if str(row.get("metric_id")) in governed_metric_ids
                ]
                if {str(row["metric_id"]) for row in selected} != governed_metric_ids:
                    raise PowerBIProjectError(
                        "KPI evidence does not cover every metric in config/metric_registry.json"
                    )
                with destination.open("w", encoding="utf-8", newline="") as output_handle:
                    writer = csv.DictWriter(
                        output_handle,
                        fieldnames=[column.name for column in table.columns],
                        lineterminator="\n",
                    )
                    writer.writeheader()
                    writer.writerows(selected)
            row_counts[table.name] = len(selected)
            transformation = "allowlist metric_id to config/metric_registry.json"
        else:
            shutil.copyfile(source, destination)
            row_counts[table.name] = _validate_source_headers(table, destination)
        source_manifest.append(
            {
                "source": f"exports/powerbi/data/{table.source_file}",
                "project_path": f"Data/{table.source_file}",
                "source_sha256": _sha256(source),
                "project_sha256": _sha256(destination),
                "rows": row_counts[table.name],
                "transformation": transformation,
            }
        )
    registry_copy = _safe_target(project_root, "Governance/metric-registry.json")
    shutil.copyfile(registry_path, registry_copy)
    source_manifest.append(
        {
            "source": "config/metric_registry.json",
            "project_path": "Governance/metric-registry.json",
            "source_sha256": _sha256(registry_path),
            "project_sha256": _sha256(registry_copy),
            "registry_version": registry_version,
            "transformation": "none",
        }
    )
    return row_counts, source_manifest, registry_version


def _project_files(project_root: Path) -> list[dict[str, object]]:
    files: list[dict[str, object]] = []
    for path in sorted(project_root.rglob("*")):
        if not path.is_file() or path.name == "project-manifest.json":
            continue
        files.append(
            {
                "path": path.relative_to(project_root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    return files


def build_powerbi_project(
    *,
    repository_root: Path = REPOSITORY_ROOT,
    output_root: Path | None = None,
) -> dict[str, object]:
    """Build the deterministic PBIP scaffold from governed evidence extracts."""

    repository_root = repository_root.resolve()
    project_root = (output_root or repository_root / "outputs" / "powerbi" / PROJECT_NAME).resolve()
    project_root.mkdir(parents=True, exist_ok=True)
    source_root = repository_root / "exports" / "powerbi" / "data"
    registry_path = repository_root / "config" / "metric_registry.json"
    validation_source = repository_root / "exports" / "powerbi" / "validation_snapshot.csv"

    row_counts, source_manifest, registry_version = _copy_sources(
        project_root, source_root, registry_path
    )

    _write_text(project_root, "README.md", _readme())
    _write_text(
        project_root,
        "schemas/report-pages.schema.json",
        _json(_report_pages_schema()),
    )
    _write_text(
        project_root,
        ".gitignore",
        "**/.pbi/localSettings.json\n**/.pbi/cache.abf\n**/.pbi/unappliedChanges.json\n"
        "**/.pbi/editorSettings.json\n**/.pbi/packageCache/\n**/.pbi/desktopSettings.json\n",
    )
    _write_text(
        project_root,
        "nAIM.pbip",
        _json(
            {
                "$schema": (
                    "https://developer.microsoft.com/json-schemas/fabric/pbip/"
                    "pbipProperties/1.0.0/schema.json"
                ),
                "version": "1.0",
                "artifacts": [{"report": {"path": "Report"}}],
                "settings": {"enableAutoRecovery": True},
            }
        ),
    )
    _write_text(
        project_root,
        "Report/definition.pbir",
        _json(
            {
                "$schema": (
                    "https://developer.microsoft.com/json-schemas/fabric/item/report/"
                    "definitionProperties/1.0.0/schema.json"
                ),
                "version": "4.0",
                "datasetReference": {"byPath": {"path": "../SemanticModel"}},
            }
        ),
    )
    _write_text(
        project_root,
        "Report/.platform",
        _json(_platform_file("Report", "nAIM Portfolio Intelligence", "report")),
    )
    _build_report_definition(project_root)
    _write_text(
        project_root,
        "Report/specifications/report-pages.json",
        _json(_report_page_specification()),
    )
    _write_text(project_root, "Report/theme/nAIM-theme.json", _json(_theme()))

    _write_text(
        project_root,
        "SemanticModel/definition.pbism",
        _json(
            {
                "$schema": (
                    "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/"
                    "definitionProperties/1.0.0/schema.json"
                ),
                "version": "4.0",
                "settings": {},
            }
        ),
    )
    _write_text(
        project_root,
        "SemanticModel/.platform",
        _json(
            _platform_file("SemanticModel", "nAIM Portfolio Intelligence Model", "semantic-model")
        ),
    )
    _write_text(
        project_root,
        "SemanticModel/definition/database.tmdl",
        f"database\n\tcompatibilityLevel: {TMDL_COMPATIBILITY_LEVEL}\n",
    )
    table_refs = "\n\n".join(f"ref table {table.name}" for table in TABLES)
    _write_text(
        project_root,
        "SemanticModel/definition/model.tmdl",
        "model Model\n"
        "\tculture: en-US\n"
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3\n"
        "\tsourceQueryCulture: en-US\n"
        "\tdataAccessOptions\n"
        "\t\tlegacyRedirects\n"
        "\t\treturnErrorValuesAsNull\n\n"
        f"{table_refs}\n",
    )
    _write_text(
        project_root,
        "SemanticModel/definition/expressions.tmdl",
        "expression nAIMExportRoot =\n"
        '\t\t"REPLACE_WITH_ABSOLUTE_PATH_TO_EXTRACTS"\n'
        '\t\tmeta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]\n'
        f"\tlineageTag: {_stable_uuid('expression.nAIMExportRoot')}\n",
    )
    for table in TABLES:
        _write_text(
            project_root,
            f"SemanticModel/definition/tables/{table.name}.tmdl",
            _table_tmdl(table),
        )
    _write_text(
        project_root,
        "SemanticModel/definition/relationships.tmdl",
        _relationships_tmdl(),
    )
    _write_text(project_root, "SemanticModel/measures.dax", _measures_dax())
    _write_text(
        project_root,
        "SemanticModel/specifications/calculation-group.json",
        _json(_calculation_group_specification()),
    )
    _write_text(
        project_root,
        "SemanticModel/specifications/field-parameters.json",
        _json(_field_parameters_specification()),
    )

    if not validation_source.is_file():
        raise PowerBIProjectError(f"Missing validation snapshot: {validation_source}")
    validation_destination = _safe_target(project_root, "Validation/reconciliation_snapshot.csv")
    shutil.copyfile(validation_source, validation_destination)
    _write_text(
        project_root,
        "Validation/controls.csv",
        _validation_controls(row_counts, registry_version),
    )
    _write_text(project_root, "Deployment/deployment-checklist.md", _deployment_checklist())

    files = _project_files(project_root)
    aggregate = hashlib.sha256(
        "\n".join(f"{item['path']}:{item['sha256']}" for item in files).encode()
    ).hexdigest()
    evidence = json.loads(
        (repository_root / "exports/validation/interop_evidence_snapshot.json").read_text(
            encoding="utf-8"
        )
    )
    metadata = evidence["metadata"]
    run_manifest = (
        repository_root
        / "data"
        / "manifests"
        / str(metadata["run_id"])
        / "run_manifest.json"
    )
    if not run_manifest.is_file():
        raise PowerBIProjectError("Canonical run manifest is missing")
    dataset_digest, _dataset_basis = dataset_hash(run_manifest, repository_root / "data")
    created_at = datetime.now(UTC).isoformat()
    comparison_period = next(
        (
            row.get("comparison_period")
            for row in evidence.get("kpis", [])
            if row.get("metric_id") == "ANNUALISED_NET_LOSS_RATE"
        ),
        None,
    )
    limitations = [
        "The included extracts are bounded synthetic evidence snapshots.",
        "Empty report pages are structural placeholders, not finished visual designs.",
        "Calculation-group and field-parameter specifications require Desktop application.",
        "No Power BI Desktop or Service claim is made.",
    ]
    manifest: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": f"PBIP-{aggregate[:20].upper()}",
        "artifact_type": "POWER_BI_SOURCE_PROJECT",
        "artifact_version": SCHEMA_VERSION,
        "created_at": created_at,
        "created_at_utc": created_at,
        "created_by_component": "naim_risk.powerbi_project",
        "source_workspace": "all_portfolio_control",
        "project_name": PROJECT_NAME,
        "product": PRODUCT_NAME,
        "tagline": TAGLINE,
        "capability_status": CAPABILITY_STATUS,
        "source_control_format": "PBIP with TMDL and PBIR",
        "desktop_validation": {
            "performed": False,
            "reason": "Power BI Desktop is not available in this build environment.",
        },
        "publication_validation": {
            "performed": False,
            "reason": "No authorised Power BI Service publication test was requested.",
        },
        "contains_pbix": False,
        "metric_registry_version": registry_version,
        "source_snapshot_id": metadata["run_id"],
        "data_mode": "OFFLINE_SNAPSHOT",
        "dataset_profile": metadata["profile"],
        "dataset_hash": dataset_digest,
        "configuration_hash": metadata["configuration_hash"],
        "code_version": SCHEMA_VERSION,
        "reporting_period": evidence["selected_reporting_period"],
        "comparison_period": comparison_period,
        "filter_scope": {
            "headline_scope": "all_portfolio",
            "approved_reference_basket": "BASKET-001",
        },
        "evidence_ids": [evidence["evidence_id"]],
        "data_quality_result": evidence["data_quality"]["status"],
        "data_quality_status": evidence["data_quality"]["status"],
        "synthetic_data": evidence["synthetic_data_flag"],
        "synthetic_data_flag": evidence["synthetic_data_flag"],
        "file_name": PROJECT_NAME,
        "file_size": sum(int(item["bytes"]) for item in files),
        "sha256": aggregate,
        "dependencies": [str(item["source"]) for item in source_manifest],
        "validation_status": "STATIC_VALIDATION_PASS",
        "validation_tests": [
            "required_project_files",
            "portable_relative_paths",
            "governed_metric_registry_alignment",
            "file_ledger_sha256",
            "secret_and_binary_scan",
        ],
        "known_limitations": limitations,
        "source_inputs": source_manifest,
        "row_counts": row_counts,
        "files": files,
        "project_sha256": aggregate,
        "limitations": limitations,
    }
    _write_text(project_root, "Build/project-manifest.json", _json(manifest))
    validation = validate_powerbi_project(project_root)
    if validation["status"] != "PASS":
        raise PowerBIProjectError(f"Generated Power BI project failed validation: {validation}")
    manifest["static_validation"] = validation
    _write_text(project_root, "Build/project-manifest.json", _json(manifest))
    return {**manifest, "static_validation": validation}


def _resolve_relative_inside(base: Path, reference: str, project_root: Path) -> Path:
    if Path(reference).is_absolute() or re.match(r"^[A-Za-z]:[\\/]", reference):
        raise PowerBIProjectError(f"Absolute PBIP path is prohibited: {reference}")
    resolved = (base / reference).resolve()
    if not resolved.is_relative_to(project_root.resolve()):
        raise PowerBIProjectError(f"PBIP path escapes project root: {reference}")
    return resolved


def _secret_findings(project_root: Path) -> list[str]:
    patterns = (
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        re.compile(
            r"(?i)(?:password|client_secret|access_token)\s*[:=]\s*['\"]?[A-Za-z0-9+/]{12,}"
        ),
        re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}"),
        re.compile(r"/Users/[^/\s]+/"),
        re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+\\"),
    )
    findings: list[str] = []
    for path in sorted(project_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(pattern.search(text) for pattern in patterns):
            findings.append(path.relative_to(project_root).as_posix())
    return findings


def validate_powerbi_project(project_root: Path) -> dict[str, object]:
    """Perform deterministic static checks without claiming Desktop validation."""

    project_root = project_root.resolve()
    errors: list[str] = []
    required = {
        "nAIM.pbip",
        "Report/definition.pbir",
        "Report/.platform",
        "Report/definition/report.json",
        "Report/definition/version.json",
        "Report/definition/pages/pages.json",
        "Report/specifications/report-pages.json",
        "Report/theme/nAIM-theme.json",
        "SemanticModel/definition.pbism",
        "SemanticModel/.platform",
        "SemanticModel/definition/database.tmdl",
        "SemanticModel/definition/model.tmdl",
        "SemanticModel/definition/expressions.tmdl",
        "SemanticModel/definition/relationships.tmdl",
        "SemanticModel/measures.dax",
        "SemanticModel/specifications/calculation-group.json",
        "SemanticModel/specifications/field-parameters.json",
        "Validation/controls.csv",
        "Validation/reconciliation_snapshot.csv",
        "Deployment/deployment-checklist.md",
        "Build/project-manifest.json",
        "schemas/report-pages.schema.json",
    }
    actual = {
        path.relative_to(project_root).as_posix()
        for path in project_root.rglob("*")
        if path.is_file()
    }
    missing = sorted(required - actual)
    if missing:
        errors.append(f"Missing required files: {missing}")

    prohibited = sorted(path for path in actual if Path(path).suffix.lower() in {".pbix", ".pbit"})
    if prohibited:
        errors.append(f"Fabricated binary Power BI files are prohibited: {prohibited}")

    for path in sorted(project_root.rglob("*.json")):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"Invalid JSON {path.relative_to(project_root)}: {exc}")
    for special in (project_root / "Report/.platform", project_root / "SemanticModel/.platform"):
        if special.is_file():
            try:
                json.loads(special.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                errors.append(f"Invalid JSON {special.relative_to(project_root)}: {exc}")

    pbip_path = project_root / "nAIM.pbip"
    report_pointer_path = project_root / "Report/definition.pbir"
    if pbip_path.is_file():
        pbip = json.loads(pbip_path.read_text(encoding="utf-8"))
        try:
            report_reference = str(pbip["artifacts"][0]["report"]["path"])
            report_path = _resolve_relative_inside(project_root, report_reference, project_root)
            if not report_path.is_dir():
                errors.append("PBIP report path does not resolve to Report/")
        except (KeyError, IndexError, TypeError, PowerBIProjectError) as exc:
            errors.append(f"Invalid PBIP report pointer: {exc}")
    if report_pointer_path.is_file():
        pointer = json.loads(report_pointer_path.read_text(encoding="utf-8"))
        try:
            model_reference = str(pointer["datasetReference"]["byPath"]["path"])
            model_path = _resolve_relative_inside(
                report_pointer_path.parent, model_reference, project_root
            )
            if not (model_path / "definition.pbism").is_file():
                errors.append("Report byPath does not resolve to the semantic model")
        except (KeyError, TypeError, PowerBIProjectError) as exc:
            errors.append(f"Invalid report-to-model byPath: {exc}")

    relationships_path = project_root / "SemanticModel/definition/relationships.tmdl"
    if relationships_path.is_file():
        relationships_text = relationships_path.read_text(encoding="utf-8")
        if relationships_text.count("relationship ") != len(RELATIONSHIPS):
            errors.append("Relationship count does not match the governed specification")
        if "crossFilteringBehavior: bothDirections" in relationships_text:
            errors.append("Bidirectional relationships are prohibited")

    measure_table_path = project_root / "SemanticModel/definition/tables/kpi_snapshot.tmdl"
    if measure_table_path.is_file():
        measure_text = measure_table_path.read_text(encoding="utf-8")
        for measure in MEASURES:
            if f"measure '{measure.name}'" not in measure_text:
                errors.append(f"Missing governed measure: {measure.name}")
            if f"formatString: {measure.format_string}" not in measure_text:
                errors.append(f"Missing format string for measure: {measure.name}")

    registry_copy = project_root / "Governance/metric-registry.json"
    dictionary_copy = project_root / "Data/metric_dictionary.csv"
    kpi_copy = project_root / "Data/kpi_snapshot.csv"
    if registry_copy.is_file() and dictionary_copy.is_file() and kpi_copy.is_file():
        registry = json.loads(registry_copy.read_text(encoding="utf-8"))
        governed_ids = {str(metric["metric_id"]) for metric in registry.get("metrics", [])}
        with dictionary_copy.open(encoding="utf-8", newline="") as handle:
            dictionary_rows = list(csv.DictReader(handle))
        with kpi_copy.open(encoding="utf-8", newline="") as handle:
            kpi_rows = list(csv.DictReader(handle))
        dictionary_ids = {str(row.get("metric_id")) for row in dictionary_rows}
        kpi_ids = {str(row.get("metric_id")) for row in kpi_rows}
        if dictionary_ids != governed_ids:
            errors.append("Metric dictionary does not exactly match the governed registry")
        if kpi_ids != governed_ids:
            errors.append("Semantic-model KPI evidence is not restricted to governed metric IDs")
        if any(
            str(row.get("registry_version")) != registry.get("registry_version")
            for row in dictionary_rows
        ):
            errors.append("Metric dictionary registry versions are inconsistent")

    manifest_path = project_root / "Build/project-manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("capability_status") != CAPABILITY_STATUS:
            errors.append("Capability status must remain INTEGRATION_ONLY")
        if manifest.get("contains_pbix") is not False:
            errors.append("Manifest must explicitly state contains_pbix=false")
        if manifest.get("desktop_validation", {}).get("performed") is not False:
            errors.append("Desktop validation must remain false until externally verified")
        for item in manifest.get("files", []):
            relative = str(item.get("path", ""))
            try:
                path = _resolve_relative_inside(project_root, relative, project_root)
            except PowerBIProjectError as exc:
                errors.append(str(exc))
                continue
            if not path.is_file():
                errors.append(f"Manifest file missing: {relative}")
            elif _sha256(path) != item.get("sha256"):
                errors.append(f"Manifest hash mismatch: {relative}")
        for item in manifest.get("source_inputs", []):
            project_relative = str(item.get("project_path", ""))
            try:
                project_path = _resolve_relative_inside(
                    project_root, project_relative, project_root
                )
            except PowerBIProjectError as exc:
                errors.append(str(exc))
                continue
            if not project_path.is_file():
                errors.append(f"Governed project input missing: {project_relative}")
                continue
            if _sha256(project_path) != item.get("project_sha256"):
                errors.append(f"Governed project input hash mismatch: {project_relative}")
            if "rows" in item and project_path.suffix.lower() == ".csv":
                with project_path.open(encoding="utf-8", newline="") as handle:
                    actual_rows = sum(1 for _ in csv.DictReader(handle))
                if actual_rows != item.get("rows"):
                    errors.append(f"Governed project input row-count mismatch: {project_relative}")

    secret_findings = _secret_findings(project_root)
    if secret_findings:
        errors.append(f"Potential secret or machine-specific path in: {secret_findings}")

    return {
        "status": "PASS" if not errors else "FAIL",
        "capability_status": CAPABILITY_STATUS,
        "desktop_validation_performed": False,
        "publication_validation_performed": False,
        "checked_files": len(actual),
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    arguments = parser.parse_args()
    target = (
        arguments.output_root or arguments.repository_root / "outputs" / "powerbi" / PROJECT_NAME
    )
    result = (
        validate_powerbi_project(target)
        if arguments.validate_only
        else build_powerbi_project(
            repository_root=arguments.repository_root,
            output_root=arguments.output_root,
        )
    )
    print(json.dumps(result, indent=2, default=asdict))
    if (
        result.get("status") == "FAIL"
        or result.get("static_validation", {}).get("status") == "FAIL"
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
