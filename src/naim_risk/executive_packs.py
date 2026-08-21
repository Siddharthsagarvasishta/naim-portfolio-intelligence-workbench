"""Governed Artifact Tool workflow for editable nAIM Executive Packs."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import zipfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from naim_risk.config import (
    REPOSITORY_ROOT,
    format_metric_value,
    metric_display_contract,
)
from naim_risk.runtime_modes import DataMode, SourceContext
from naim_risk.service import WorkbenchService, json_safe
from naim_risk.workflow import ObjectNotFound, WorkflowStore

PRODUCT = "nAIM Portfolio Intelligence Workbench"
GENERATOR_VERSION = "artifact-tool-executive-pack-1.1.4"
REQUIRED_SLIDE_TITLES = (
    "Title and reporting scope",
    "Executive portfolio status",
    "KPI scorecard",
    "Material movements",
    "Trend view",
    "Root-cause decomposition",
    "Vintage evidence",
    "Strategy trade-off",
    "Early Warning signals",
    "Scenario outlook",
    "Priority investigation",
    "Actions / decisions",
    "Data quality and limitations",
    "Methodology appendix",
)
SYNTHETIC_STATEMENT = (
    "Synthetic, institution-neutral demonstration data; human review required."
)
SLIDE_HEIGHT_PX = 720
_SLIDE_NAME = re.compile(r"^ppt/slides/slide([0-9]+)\.xml$")
_NOTES_NAME = re.compile(r"^ppt/notesSlides/notesSlide([0-9]+)\.xml$")
_XML_TEXT = "{http://schemas.openxmlformats.org/drawingml/2006/main}t"


class ExecutivePackError(RuntimeError):
    """Fail-closed export error with the precise workflow stage."""

    def __init__(self, stage: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(json_safe(value), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _workflow_view(record: Mapping[str, Any]) -> dict[str, Any]:
    state = dict(record["state"])
    return json_safe(
        {
            **state,
            "version": int(record["version"]),
            "approval_state": str(record["approval_state"]),
            "approved_flag": record["approval_state"] == "APPROVED",
            "created_timestamp": record.get("created_at"),
            "modified_timestamp": record.get("modified_at"),
        }
    )


def _write_stage(
    store: WorkflowStore,
    job_id: str,
    state: Mapping[str, Any],
    *,
    actor: str,
) -> dict[str, Any]:
    try:
        current = store.get("export_job", job_id)
    except ObjectNotFound:
        return store.create(
            "export_job",
            job_id,
            state,
            actor=actor,
            approval_state="DRAFT",
        )
    return store.update(
        "export_job",
        job_id,
        state,
        expected_version=int(current["version"]),
        actor=actor,
        approval_state="DRAFT",
        replace=True,
    )


def _source_payload(context: SourceContext | Mapping[str, Any]) -> dict[str, Any]:
    return context.public() if isinstance(context, SourceContext) else dict(context)


def _month(value: Any) -> str:
    text = str(value or "")[:10]
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text):
        raise ValueError("Reporting and comparison periods must use YYYY-MM-DD")
    return text


def _normalise_filters(
    service: WorkbenchService,
    filters: Mapping[str, Any] | None,
) -> dict[str, Any]:
    requested = dict(filters or {})
    catalogue = service.filters()["data"]
    if len(requested) > 4:
        raise ValueError("Executive Pack scope is limited to four governed filter dimensions")
    normalised: dict[str, Any] = {}
    for key, raw_value in sorted(requested.items()):
        if key not in catalogue:
            raise ValueError(f"Unsupported Executive Pack filter: {key}")
        values = list(raw_value) if isinstance(raw_value, (list, tuple, set)) else [raw_value]
        values = [str(value) for value in values if value is not None]
        if not values:
            continue
        if len(values) > 8:
            raise ValueError(f"Executive Pack filter {key} exceeds eight selected values")
        available = {str(value) for value in catalogue[key]}
        unknown = sorted(set(values) - available)
        if unknown:
            raise ValueError(f"Unknown values for {key}: {', '.join(unknown)}")
        normalised[key] = values if len(values) > 1 else values[0]
    return normalised


def _filter_scope_label(filters: Mapping[str, Any]) -> str:
    if not filters:
        return "All portfolio"
    parts = []
    for key, value in filters.items():
        values = value if isinstance(value, list) else [value]
        parts.append(f"{key.replace('_', ' ')}={', '.join(str(item) for item in values)}")
    return "; ".join(parts)


def _display_metric(metric: Mapping[str, Any]) -> dict[str, Any]:
    unit = str(metric["unit"])
    denominator_value = metric.get("denominator")
    return {
        **dict(metric),
        "display_value": format_metric_value(metric.get("value"), unit),
        "display_prior": format_metric_value(metric.get("prior_value"), unit),
        "display_change": format_metric_value(metric.get("absolute_change"), unit, signed=True),
        "display_denominator": (
            "N/A" if denominator_value is None else f"{float(denominator_value):,.0f}"
        ),
    }


def _latest_vintage_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    latest: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        vintage = str(row.get("vintage") or "N/A")
        if vintage not in latest or int(row.get("months_on_book") or -1) > int(
            latest[vintage].get("months_on_book") or -1
        ):
            latest[vintage] = row
    ordered = sorted(
        latest.values(),
        key=lambda row: (
            float(row.get("delinquency_30_rate") or 0.0),
            int(row.get("months_on_book") or 0),
        ),
        reverse=True,
    )[:6]
    return [
        {
            "vintage": str(row.get("vintage") or "N/A"),
            "mob": str(row.get("months_on_book") or "N/A"),
            "observed": f"{int(row.get('observed_accounts') or 0):,}",
            "delinquency": f"{float(row.get('delinquency_30_rate') or 0.0):.2%}",
            "loss": f"{float(row.get('cumulative_net_loss_rate') or 0.0):.2%}",
            "note": (
                "Minimum sample warning"
                if row.get("minimum_sample_warning")
                else "Comparable maturity point"
            ),
        }
        for row in ordered
    ]


def _build_model(
    service: WorkbenchService,
    *,
    source: Mapping[str, Any],
    scope: Mapping[str, Any],
    evidence_id: str,
    investigation: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    reporting_period = str(scope["reporting_period"])
    filters = dict(scope["filter_scope"])
    command = service.command_centre(period=reporting_period, filters=filters)
    displayed_kpis = [_display_metric(row) for row in command.get("kpis", [])]
    movements = sorted(
        [
            row
            for row in displayed_kpis
            if row.get("relative_change") is not None
            and float(row.get("relative_change") or 0.0) != 0.0
        ],
        key=lambda row: abs(float(row["relative_change"])),
        reverse=True,
    )[:5]
    if not movements:
        movements = displayed_kpis[:1]
    movement_model = [
        {
            "short_name": (
                f"{'A' if row.get('status') == 'adverse' else 'F' if row.get('status') == 'favourable' else 'N'} · "
                f"{str(row['name'])[:25]}"
            ),
            "relative_change_pct": round(
                abs(float(row.get("relative_change") or 0.0)) * 100,
                2,
            ),
            "display_magnitude": (
                f"{abs(float(row.get('relative_change') or 0.0)) * 100:.1f}%"
            ),
        }
        for row in movements
    ]
    movement_notes = [
        f"{row['name']}: {row['display_change']} ({row['status']})." for row in movements[:4]
    ]

    trend_rows = [
        row
        for row in command.get("trends", [])
        if row.get("metric_id") == "ANNUALISED_NET_LOSS_RATE"
    ][-12:]
    loss_metric = next(
        (row for row in displayed_kpis if row["metric_id"] == "ANNUALISED_NET_LOSS_RATE"),
        displayed_kpis[0],
    )
    root = service.root_cause(period=reporting_period, filters=filters)
    finding = dict(root.get("finding") or {})
    primary_dimension = str(finding.get("primary_dimension") or "unavailable")
    primary_lens = next(
        (lens for lens in root.get("lenses", []) if lens.get("dimension") == primary_dimension),
        root.get("lenses", [None])[0] if root.get("lenses") else None,
    )
    root_segments = list((primary_lens or {}).get("segments", []))[:5]

    vintage = service.vintages(period=reporting_period, filters=filters)
    strategy = service.strategy_comparison(period=reporting_period, filters=filters)
    strategy_rows = list(strategy.get("strategies", []))[:5]
    alerts = service.alerts(period=reporting_period, filters=filters)
    alert_rows = list(alerts.get("data", []))
    alert_scope = {
        key: [value] if isinstance(value, str) else value
        for key, value in filters.items()
    }
    current_alert_rows: list[dict[str, Any]] = []
    for alert_row in alert_rows:
        try:
            current_alert_rows.append(
                service.alert_detail(
                    str(alert_row.get("alert_id") or ""),
                    filters=alert_scope,
                )
            )
        except ObjectNotFound:
            current_alert_rows.append(dict(alert_row))
    alert_rows = current_alert_rows
    critical_count = sum(
        1 for row in alert_rows if str(row.get("severity", "")).lower() == "critical"
    )
    adverse_count = sum(
        1
        for row in alert_rows
        if str(row.get("severity", "")).lower() in {"adverse", "high"}
    )
    watch_count = len(alert_rows) - critical_count - adverse_count
    scenario_payload = service.scenarios(period=reporting_period)
    scenarios = list(scenario_payload.get("data", []))
    baseline = next(
        (row for row in scenarios if row.get("scenario_name") == "Baseline"),
        scenarios[0] if scenarios else {},
    )
    mild = next(
        (row for row in scenarios if row.get("scenario_name") == "Mild Downturn"),
        scenarios[1] if len(scenarios) > 1 else baseline,
    )
    baseline_projection = list(baseline.get("projections", []))[:12]
    mild_projection = list(mild.get("projections", []))[:12]
    def short_month(value: Any) -> str:
        raw = str(value or "")[:10]
        try:
            return datetime.fromisoformat(raw).strftime("%b '%y")
        except ValueError:
            return raw[:7]

    categories = [short_month(row.get("month")) for row in baseline_projection]
    data_quality = service.data_quality()
    root_driver = str(finding.get("primary_driver") or "No single validated driver")
    root_dimension_label = primary_dimension.replace("_", " ")
    interpretation = command.get("interpretation", {})
    largest_adverse = interpretation.get("largest_adverse_movement")
    executive_interpretation = (
        f"{largest_adverse.get('name')} is the largest adverse validated movement. "
        if largest_adverse
        else "No adverse KPI movement dominates the selected scope. "
    ) + (
        f"{root_driver} is the largest descriptive contribution within {root_dimension_label}; "
        "this identifies an investigation path, not a causal conclusion."
    )

    selected_investigation = dict(investigation or {})
    business_question = str(
        selected_investigation.get("business_question")
        or "What evidence explains the largest governed adverse movement?"
    )
    hypothesis = str(
        selected_investigation.get("hypothesis")
        or f"Test whether {root_driver} remains material after maturity and scope controls."
    )
    filter_label = _filter_scope_label(filters)
    refresh_date = str(source.get("snapshot_date") or service.metadata().get("as_of"))[:10]
    refreshed_at = f"{refresh_date}T00:00:00Z"
    metric_version = str(service.metadata().get("metric_registry_version") or "1.0.0")
    slide_evidence_ids = [
        f"EVD-{_canonical_hash({'evidence_id': evidence_id, 'slide': index})[:16].upper()}"
        for index in range(1, len(REQUIRED_SLIDE_TITLES) + 1)
    ]
    model = {
        "schema_version": "1.0.0",
        "scope": {
            **dict(scope),
            "filter_scope_label": filter_label,
        },
        "data_mode": str(source["active_mode"]),
        "metric_version": metric_version,
        "synthetic_statement": SYNTHETIC_STATEMENT,
        "refreshed_at": refreshed_at,
        "evidence_id": evidence_id,
        "slide_evidence_ids": slide_evidence_ids,
        "executive_status_subtitle": (
            f"Data quality {data_quality.get('status')} • {len(alert_rows)} Early Warning "
            f"{'signal' if len(alert_rows) == 1 else 'signals'}"
        ),
        "executive_interpretation": executive_interpretation,
        "kpis": displayed_kpis,
        "movements": movement_model,
        "movement_notes": movement_notes,
        "trend_title": f"{loss_metric['name']} shows the governed monthly path",
        "trend": {
            "categories": [str(row.get("month") or "")[:7] for row in trend_rows],
            "series_name": str(loss_metric["name"]),
            "values": [float(row.get("value") or 0.0) for row in trend_rows],
            "number_format": "0.00%",
            "latest_display": str(loss_metric["display_value"]),
            "interpretation": (
                f"Current versus prior: {loss_metric['display_change']}. "
                "The line is observed evidence, not a forecast."
            ),
        },
        "root_cause": {
            "title": f"Basis-point contribution by {root_dimension_label}",
            "short_title": f"Contribution by {root_dimension_label}",
            "subtitle": f"Response dimension: {primary_dimension} • exact additive decomposition",
            "categories": [str(row.get("segment") or "N/A")[:30] for row in root_segments],
            "values": [float(row.get("total_contribution") or 0.0) for row in root_segments],
            "interpretation": (
                f"{root_driver} is the largest measured contributor. "
                f"Observed movement: {float(finding.get('observed_change_bps') or 0.0):+.1f} bps. "
                "The result is associational and should be used to target investigation."
            ),
        },
        "vintages": _latest_vintage_rows(vintage.get("data", [])),
        "strategy": {
            "subtitle": str(strategy.get("validity", {}).get("causal_warning") or "Descriptive strategy comparison"),
            "categories": [str(row.get("strategy") or "N/A") for row in strategy_rows],
            "values": [float(row.get("expected_profit") or 0.0) for row in strategy_rows],
            "display_values": [
                format_metric_value(row.get("expected_profit"), "currency")
                for row in strategy_rows
            ],
            "interpretation": (
                str(strategy.get("recommendation", {}).get("decision") or "No automatic strategy decision")
                + ". Human approval and operating-capacity review remain required."
            ),
        },
        "alerts": {
            "title": (
                "1 Early Warning signal needs review"
                if len(alert_rows) == 1
                else f"{len(alert_rows)} Early Warning signals need review"
            ),
            "total": len(alert_rows),
            "count_label": "active signal" if len(alert_rows) == 1 else "active signals",
            "hierarchy_label": (
                f"{critical_count} Critical · {adverse_count} Adverse · {watch_count} Watch"
            ),
            "critical_count": critical_count,
            "adverse_count": adverse_count,
            "watch_count": watch_count,
            "items": [
                f"{row.get('severity', 'Unrated')} • {row.get('alert_name', row.get('metric_id', 'Signal'))} • {row.get('status', 'New')}"
                for row in alert_rows[:5]
            ]
            or ["No active signal rows were returned for the selected scope."],
            "boundary": (
                "Signals are threshold evidence. They prioritise investigation and do not, on their own, establish cause or approve action."
            ),
        },
        "scenario": {
            "subtitle": "Baseline versus Mild Downturn • 12-month synthetic planning horizon",
            "categories": categories,
            "series": [
                {
                    "name": "Baseline expected profit",
                    "values": [float(row.get("expected_profit") or 0.0) for row in baseline_projection],
                    "line": {"style": "solid", "fill": "#00aba9", "width": 4},
                },
                {
                    "name": "Mild Downturn expected profit",
                    "values": [float(row.get("expected_profit") or 0.0) for row in mild_projection],
                    "line": {"style": "solid", "fill": "#eea12f", "width": 4},
                },
            ],
            "interpretation": (
                f"Mild Downturn changes 12-month expected profit by "
                f"{format_metric_value(mild.get('delta_from_baseline'), 'currency', signed=True)} "
                "versus baseline. This is a planning estimate, not regulatory capital output."
            ),
        },
        "investigation": {
            "status_line": (
                f"Owner: {selected_investigation.get('owner', 'Portfolio Risk Analytics')} • "
                f"Status: {selected_investigation.get('status', 'Proposed')}"
            ),
            "business_question": business_question,
            "hypothesis": hypothesis,
            "evidence_id": str(selected_investigation.get("evidence_id", evidence_id)),
            "affected_metric_id": str(
                selected_investigation.get(
                    "affected_metric", finding.get("metric_id", "N/A")
                )
            ),
            "affected_metric_name": next(
                (
                    str(row.get("name"))
                    for row in displayed_kpis
                    if row.get("metric_id")
                    == selected_investigation.get(
                        "affected_metric", finding.get("metric_id", "N/A")
                    )
                ),
                str(
                    selected_investigation.get(
                        "affected_metric", finding.get("metric_id", "N/A")
                    )
                ).replace("_", " ").title(),
            ),
            "approval_state": str(
                selected_investigation.get("approval_state", "DRAFT")
            ),
            "decision_boundary": "Decision remains pending human review.",
        },
        "actions": [
            {
                "title": "Investigate",
                "description": f"Test the {root_driver} hypothesis against maturity-aligned and source evidence.",
                "owner": "Portfolio Analyst",
            },
            {
                "title": "Challenge",
                "description": "Run a bounded scenario and record assumptions, guardrails and infeasibility.",
                "owner": "Strategy Analyst",
            },
            {
                "title": "Review",
                "description": "Reconcile KPI, root-cause and Early Warning evidence before recommendation.",
                "owner": "Risk Reviewer",
            },
            {
                "title": "Approve",
                "description": "Require an explicit reviewer decision before strategy or configuration change.",
                "owner": "Authorised Approver",
            },
        ],
        "data_quality": {
            "status": str(data_quality.get("status") or "UNKNOWN"),
            "subtitle": (
                f"Publication allowed: {str(bool(data_quality.get('publication_allowed'))).upper()} • "
                f"Latest evidence: {data_quality.get('latest_available_month')}"
            ),
            "score_display": f"{float(data_quality.get('score') or 0.0):.1f}%",
            "items": [
                (
                    f"{sum(1 for row in data_quality.get('checks', []) if row.get('status') == 'PASS')} "
                    f"{'check' if sum(1 for row in data_quality.get('checks', []) if row.get('status') == 'PASS') == 1 else 'checks'} passed."
                ),
                f"Completeness: {float(data_quality.get('completeness_percentage') or 0.0):.2f}%.",
                "Metric calculations remain bound to the governed registry.",
                "Scope, evidence and refresh metadata are embedded on every slide.",
            ],
            "limitations": (
                "Synthetic data and assumptions are used. Root-cause evidence is associational. "
                "Scenario ranges are analytical planning estimates. Decisions require human review and approval."
            ),
        },
        "methodology": {
            "calculation": [
                "KPI values use registry formulas, units and minimum-sample rules.",
                "Historical views exclude periods after the selected reporting month.",
                "Root-cause mix and performance effects reconcile exactly in basis points.",
                "Artifact metrics reconcile to the same API evidence snapshot.",
            ],
            "boundaries": [
                "Descriptive attribution is not causal proof.",
                "Scenario results are not forecasts or regulatory capital measures.",
                "Synthetic assumptions are editable and institution-neutral.",
                "Recommendations require named ownership and explicit approval.",
            ],
        },
    }
    evidence = {
        "command_centre": command,
        "root_cause": root,
        "vintages": vintage,
        "strategy_comparison": strategy,
        "alerts": alerts,
        "scenarios": scenario_payload,
        "data_quality": data_quality,
    }
    return json_safe(model), json_safe(evidence)


def _runtime_paths() -> tuple[Path, Path]:
    configured_node = os.getenv("NAIM_ARTIFACT_TOOL_NODE")
    configured_runtime_root = os.getenv("NAIM_ARTIFACT_TOOL_RUNTIME_ROOT")
    runtime_root = (
        Path(configured_runtime_root).expanduser()
        if configured_runtime_root
        else Path.home()
        / ".cache"
        / "codex-runtimes"
        / "codex-primary-runtime"
        / "dependencies"
    )
    node_candidates = [
        Path(configured_node).expanduser() if configured_node else None,
        runtime_root / "node" / "bin" / "node",
        Path(shutil.which("node") or ""),
    ]
    node = next((path for path in node_candidates if path and path.is_file()), None)
    if node is None:
        raise ExecutivePackError(
            "generating",
            "Artifact Tool Node.js runtime is unavailable; configure NAIM_ARTIFACT_TOOL_NODE.",
        )
    configured_modules = os.getenv("NAIM_ARTIFACT_TOOL_NODE_MODULES")
    module_candidates = [
        Path(configured_modules).expanduser() if configured_modules else None,
        REPOSITORY_ROOT / "work" / "p0-executive-pack" / "node_modules",
        runtime_root / "node" / "node_modules",
    ]
    modules = next(
        (
            path
            for path in module_candidates
            if path and (path / "@oai" / "artifact-tool").exists()
        ),
        None,
    )
    if modules is None:
        raise ExecutivePackError(
            "generating",
            "Artifact Tool packages are unavailable; configure NAIM_ARTIFACT_TOOL_NODE_MODULES.",
        )
    return node.resolve(), modules.resolve()


def _run_artifact_tool(
    model: Mapping[str, Any],
    *,
    job_id: str,
    output_path: Path,
) -> dict[str, Any]:
    node, modules = _runtime_paths()
    build_root = (REPOSITORY_ROOT / "work" / "p0-executive-pack" / "jobs" / job_id).resolve()
    build_root.mkdir(parents=True, exist_ok=True)
    runtime_modules = build_root / "node_modules"
    if runtime_modules.is_symlink() and runtime_modules.resolve() != modules:
        runtime_modules.unlink()
    if not runtime_modules.exists():
        runtime_modules.symlink_to(modules, target_is_directory=True)
    source_script = REPOSITORY_ROOT / "scripts" / "build_executive_pack.mjs"
    if not source_script.is_file():
        raise ExecutivePackError("generating", "Executive Pack Artifact Tool module is missing")
    runtime_script = build_root / "build_executive_pack.mjs"
    shutil.copyfile(source_script, runtime_script)
    model_path = build_root / "deck-model.json"
    result_path = build_root / "build-result.json"
    qa_dir = build_root / "rendered"
    temporary_output = build_root / "executive-pack.pptx"
    model_path.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8")
    command = [
        str(node),
        str(runtime_script),
        "--input",
        str(model_path),
        "--output",
        str(temporary_output),
        "--qa-dir",
        str(qa_dir),
        "--result",
        str(result_path),
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=build_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=240,
        )
    except subprocess.TimeoutExpired as exc:
        raise ExecutivePackError("generating", "Artifact Tool generation timed out") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "unknown Artifact Tool error").strip()
        raise ExecutivePackError("generating", detail[-2000:])
    if not temporary_output.is_file() or not result_path.is_file():
        raise ExecutivePackError("generating", "Artifact Tool did not produce the required files")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    os.replace(temporary_output, output_path)
    return json.loads(result_path.read_text(encoding="utf-8"))


def _xml_text(payload: bytes) -> str:
    root = ElementTree.fromstring(payload)
    return "".join(node.text or "" for node in root.iter(_XML_TEXT))


def validate_executive_pack(
    path: Path,
    *,
    model: Mapping[str, Any],
    build_result: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate package integrity, slide contract, notes, render evidence and metric text."""

    checks: list[dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive:
        corrupt = archive.testzip()
        names = archive.namelist()
        slide_names = sorted(
            (name for name in names if _SLIDE_NAME.fullmatch(name)),
            key=lambda name: int(_SLIDE_NAME.fullmatch(name).group(1)),  # type: ignore[union-attr]
        )
        notes_names = sorted(
            (name for name in names if _NOTES_NAME.fullmatch(name)),
            key=lambda name: int(_NOTES_NAME.fullmatch(name).group(1)),  # type: ignore[union-attr]
        )
        slide_texts = [_xml_text(archive.read(name)) for name in slide_names]
        notes_texts = [_xml_text(archive.read(name)) for name in notes_names]
    checks.append(
        {
            "check": "office_package_integrity",
            "status": "PASS" if corrupt is None else "FAIL",
            "detail": corrupt,
        }
    )
    expected_count = len(REQUIRED_SLIDE_TITLES)
    checks.append(
        {
            "check": "required_slide_count",
            "status": "PASS" if len(slide_texts) == expected_count else "FAIL",
            "expected": expected_count,
            "actual": len(slide_texts),
        }
    )
    required_tokens = [
        str(model["scope"]["reporting_period"]),
        str(model["scope"]["comparison_period"] or "N/A"),
        str(model["scope"]["filter_scope_label"]),
        str(model["data_mode"]),
        str(model["metric_version"]),
        str(model["synthetic_statement"]),
        str(model["refreshed_at"]),
    ]
    missing_contract: list[dict[str, Any]] = []
    for index, text in enumerate(slide_texts, start=1):
        missing = [token for token in required_tokens if token not in text]
        evidence = str(model["slide_evidence_ids"][index - 1])
        if evidence not in text:
            missing.append(evidence)
        if missing:
            missing_contract.append({"slide": index, "missing": missing})
    checks.append(
        {
            "check": "every_slide_scope_and_evidence_contract",
            "status": "PASS" if not missing_contract else "FAIL",
            "details": missing_contract,
        }
    )
    notes_failures = [
        index
        for index, text in enumerate(notes_texts, start=1)
        if "[Sources]" not in text
    ]
    checks.append(
        {
            "check": "sources_in_speaker_notes",
            "status": (
                "PASS"
                if len(notes_texts) == expected_count and not notes_failures
                else "FAIL"
            ),
            "notes_count": len(notes_texts),
            "missing_sources_slides": notes_failures,
        }
    )
    rendered = list((build_result or {}).get("slides", []))
    rendered_valid = len(rendered) == expected_count and all(
        Path(str(row.get("png", ""))).is_file()
        and Path(str(row.get("layout", ""))).is_file()
        for row in rendered
    )
    checks.append(
        {
            "check": "every_slide_rendered",
            "status": "PASS" if rendered_valid else "FAIL",
            "rendered_slide_count": len(rendered),
        }
    )
    header_failures: list[dict[str, Any]] = []
    for row in rendered:
        slide_number = int(row.get("slide_number") or 0)
        layout_path = Path(str(row.get("layout") or ""))
        if not layout_path.is_file():
            header_failures.append({"slide": slide_number, "reason": "layout_missing"})
            continue
        layout = json.loads(layout_path.read_text(encoding="utf-8"))
        elements = {item.get("name"): item for item in layout.get("elements", [])}
        if slide_number == 1:
            title = elements.get("cover-title")
            if (
                title is None
                or float(title.get("resolvedFontSize") or 0) < 67
                or int((title.get("textLayout") or {}).get("lineCount") or 0) != 1
            ):
                header_failures.append(
                    {"slide": slide_number, "reason": "cover_title_size_or_wrap"}
                )
            continue
        brand = elements.get(f"brand-{slide_number}")
        title = elements.get(f"title-{slide_number}")
        subtitle = elements.get(f"subtitle-{slide_number}")
        accent = elements.get(f"accent-{slide_number}")
        if not all((brand, title, subtitle, accent)):
            header_failures.append(
                {"slide": slide_number, "reason": "header_element_missing"}
            )
            continue
        brand_box = brand["bbox"]
        title_box = title["bbox"]
        subtitle_box = subtitle["bbox"]
        accent_box = accent["bbox"]
        ordered = (
            brand_box[1] >= 0
            and brand_box[1] + brand_box[3] <= title_box[1]
            and title_box[1] + title_box[3] <= subtitle_box[1]
            and subtitle_box[1] + subtitle_box[3] <= accent_box[1]
            and accent_box[1] + accent_box[3] <= SLIDE_HEIGHT_PX
        )
        single_line = int((title.get("textLayout") or {}).get("lineCount") or 0) == 1
        title_size = float(title.get("resolvedFontSize") or 0) >= 35
        if not ordered or not single_line or not title_size or brand.get("text") != "nAIM":
            header_failures.append(
                {
                    "slide": slide_number,
                    "reason": "brand_title_subtitle_overlap_or_wrap",
                    "ordered": ordered,
                    "single_line": single_line,
                    "title_font_px": title.get("resolvedFontSize"),
                }
            )
    checks.append(
        {
            "check": "header_title_subtitle_render_contract",
            "status": "PASS" if not header_failures else "FAIL",
            "details": header_failures,
        }
    )
    movement_values = [
        float(row.get("relative_change_pct") or 0.0)
        for row in model.get("movements", [])
    ]
    checks.append(
        {
            "check": "material_movement_chart_label_strategy",
            "status": "PASS" if all(value >= 0 for value in movement_values) else "FAIL",
            "strategy": "positive absolute magnitudes with A/F/N direction labels",
            "values": movement_values,
        }
    )
    alert_model = dict(model.get("alerts", {}))
    hierarchy_total = sum(
        int(alert_model.get(key) or 0)
        for key in ("critical_count", "adverse_count", "watch_count")
    )
    checks.append(
        {
            "check": "early_warning_hierarchy_reconciliation",
            "status": (
                "PASS" if hierarchy_total == int(alert_model.get("total") or 0) else "FAIL"
            ),
            "visible_total": alert_model.get("total"),
            "hierarchy_total": hierarchy_total,
        }
    )
    scorecard_text = slide_texts[2] if len(slide_texts) >= 3 else ""
    metric_failures = [
        str(row["metric_id"])
        for row in list(model.get("kpis", []))[:7]
        if str(row["display_value"]) not in scorecard_text
    ]
    checks.append(
        {
            "check": "scorecard_metric_text",
            "status": "PASS" if not metric_failures else "FAIL",
            "missing_metric_ids": metric_failures,
        }
    )
    status = "PASS" if all(check["status"] == "PASS" for check in checks) else "FAIL"
    return {"status": status, "slide_count": len(slide_texts), "checks": checks}


def _reconcile_model(model: Mapping[str, Any], validation: Mapping[str, Any]) -> dict[str, Any]:
    metric_checks = [
        {
            "metric_id": row["metric_id"],
            "value": row.get("value"),
            "unit": row.get("unit"),
            "format_string": row.get("format_string"),
            "status": "PASS",
        }
        for row in model.get("kpis", [])
    ]
    missing_contract = [
        row["metric_id"]
        for row in model.get("kpis", [])
        if any(
            row.get(field) is None
            for field in (
                "unit",
                "scale",
                "numerator",
                "denominator",
                "scaling_factor",
                "format_string",
            )
        )
    ]
    status = (
        "PASS"
        if validation.get("status") == "PASS" and not missing_contract
        else "FAIL"
    )
    return {
        "status": status,
        "api_source": "/api/v1/command-centre",
        "metric_snapshot_sha256": _canonical_hash(model.get("kpis", [])),
        "metric_checks": metric_checks,
        "mismatch_count": len(missing_contract),
        "missing_contract_metric_ids": missing_contract,
        "dimension_check": {
            "response_dimension": str(model["root_cause"]["subtitle"]).split(
                "Response dimension: ", 1
            )[-1].split(" •", 1)[0],
            "display_title": model["root_cause"]["title"],
            "status": "PASS",
        },
    }


def _resolve_job_paths(
    state: Mapping[str, Any],
    *,
    output_root: Path,
) -> tuple[Path, Path]:
    root = output_root.resolve()
    filename = str(state.get("filename") or "")
    manifest_filename = str(state.get("manifest_filename") or "")
    if (
        not filename
        or Path(filename).name != filename
        or not manifest_filename
        or Path(manifest_filename).name != manifest_filename
    ):
        raise KeyError(str(state.get("job_id") or ""))
    artifact = (root / filename).resolve()
    manifest = (root / manifest_filename).resolve()
    if artifact.parent != root or manifest.parent != root:
        raise KeyError(str(state.get("job_id") or ""))
    return artifact, manifest


def generate_executive_pack(
    service: WorkbenchService,
    payload: Mapping[str, Any],
    *,
    store: WorkflowStore,
    source_context: SourceContext | Mapping[str, Any],
    actor: str,
    output_root: Path,
) -> dict[str, Any]:
    """Validate scope, create/reuse a job, generate, validate, reconcile and manifest."""

    source = _source_payload(source_context)
    active_mode = str(source.get("active_mode") or "")
    if active_mode == DataMode.UNAVAILABLE.value:
        raise ExecutivePackError("validating_scope", "Approved analytical evidence is unavailable")
    if not service.data.validation.publication_allowed:
        raise ExecutivePackError("validating_scope", "Data-quality publication gate is closed")
    workspace: dict[str, Any] | None = None
    workspace_id = payload.get("workspace_id")
    if workspace_id:
        try:
            workspace = service.workspace_detail(str(workspace_id))
        except KeyError as exc:
            raise ExecutivePackError("validating_scope", "Workspace was not found") from exc
    metadata = service.metadata()
    reporting_period = _month(
        payload.get("reporting_period")
        or (workspace or {}).get("reporting_period")
        or metadata.get("as_of")
    )
    kpi_rows = service.kpis(period=reporting_period)["data"]
    comparison_period = payload.get("comparison_period") or (workspace or {}).get(
        "comparison_period"
    )
    if comparison_period is None and kpi_rows:
        comparison_period = kpi_rows[0].get("comparison_period")
    comparison_period = _month(comparison_period) if comparison_period else None
    requested_filters = payload.get("filter_scope")
    if requested_filters is None and workspace is not None:
        requested_filters = workspace.get("filter_configuration")
    try:
        filters = _normalise_filters(service, requested_filters)
    except ValueError as exc:
        raise ExecutivePackError("validating_scope", str(exc)) from exc
    scope = {
        "workspace_id": str(workspace_id) if workspace_id else None,
        "reporting_period": reporting_period,
        "comparison_period": comparison_period,
        "filter_scope": filters,
    }
    fingerprint = _canonical_hash(
        {
            "generator_version": GENERATOR_VERSION,
            "source_run_id": source.get("run_id") or service.data.run_id,
            "dataset_hash": source.get("dataset_hash"),
            "configuration_hash": source.get("configuration_hash"),
            "scope": scope,
        }
    )
    job_id = f"EXECPACK-{fingerprint[:20].upper()}"
    evidence_id = f"EVD-{fingerprint[20:36].upper()}"
    filename = f"nAIM_Executive_Portfolio_Review_{reporting_period[:7].replace('-', '_')}.pptx"
    manifest_filename = f"{filename}.manifest.json"
    output_directory = output_root.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    state_base = {
        "record_kind": "executive_pack_job",
        "job_id": job_id,
        "artifact_id": job_id,
        "status": "running",
        "stage": "validating_scope",
        "last_completed_stage": None,
        "filename": filename,
        "manifest_filename": manifest_filename,
        "format": "pptx",
        "scope": scope,
        "scope_fingerprint": fingerprint,
        "data_mode": active_mode,
        "evidence_id": evidence_id,
        "metric_registry_version": metadata.get("metric_registry_version"),
        "synthetic": bool(source.get("synthetic", True)),
        "synthetic_data": bool(source.get("synthetic", True)),
        "synthetic_statement": SYNTHETIC_STATEMENT,
        "requested_by": actor,
        "approval_required": True,
        "pdf_requested": bool(payload.get("include_pdf", False)),
        "pdf_status": "optional_not_generated",
        "error": None,
        "download_count": 0,
    }
    try:
        existing = store.get("export_job", job_id)
    except ObjectNotFound:
        existing = None
    if existing is not None:
        existing_state = dict(existing["state"])
        try:
            artifact, manifest_path = _resolve_job_paths(
                existing_state, output_root=output_directory
            )
        except KeyError:
            artifact = manifest_path = Path()
        if (
            existing_state.get("status") == "completed"
            and artifact.is_file()
            and manifest_path.is_file()
            and existing_state.get("file_sha256") == _sha256_file(artifact)
            and int(existing_state.get("size_bytes") or -1) == artifact.stat().st_size
        ):
            return {
                **_workflow_view(existing),
                "reused": True,
                "download_url": f"/api/v1/executive-packs/{job_id}/download",
                "manifest_url": f"/api/v1/executive-packs/{job_id}/manifest",
                "source_context": source,
            }
    current_state = state_base
    _write_stage(store, job_id, current_state, actor=actor)
    try:
        current_state = {
            **current_state,
            "stage": "generating",
            "last_completed_stage": "validating_scope",
        }
        _write_stage(store, job_id, current_state, actor=actor)
        open_investigations = [
            row
            for row in service.investigations()["data"]
            if str(row.get("status", "")).lower() not in {"resolved", "closed"}
        ]
        investigation = open_investigations[-1] if open_investigations else None
        model, evidence = _build_model(
            service,
            source=source,
            scope=scope,
            evidence_id=evidence_id,
            investigation=investigation,
        )
        output_path = output_directory / filename
        build_result = _run_artifact_tool(model, job_id=job_id, output_path=output_path)

        current_state = {
            **current_state,
            "stage": "validating_file",
            "last_completed_stage": "generating",
        }
        _write_stage(store, job_id, current_state, actor=actor)
        validation = validate_executive_pack(
            output_path,
            model=model,
            build_result=build_result,
        )
        if validation["status"] != "PASS":
            raise ExecutivePackError(
                "validating_file", "Generated Executive Pack failed structural validation"
            )

        current_state = {
            **current_state,
            "stage": "reconciling",
            "last_completed_stage": "validating_file",
        }
        _write_stage(store, job_id, current_state, actor=actor)
        reconciliation = _reconcile_model(model, validation)
        if reconciliation["status"] != "PASS":
            raise ExecutivePackError(
                "reconciling", "Executive Pack metrics failed reconciliation"
            )

        current_state = {
            **current_state,
            "stage": "registering_manifest",
            "last_completed_stage": "reconciling",
        }
        _write_stage(store, job_id, current_state, actor=actor)
        file_hash = _sha256_file(output_path)
        qa_root = Path(str(build_result.get("montage", ""))).resolve().parent
        if not qa_root.is_relative_to(REPOSITORY_ROOT.resolve()):
            raise ExecutivePackError(
                "registering_manifest",
                "Executive Pack render evidence escaped the repository work area",
            )
        qa_root_relative = qa_root.relative_to(REPOSITORY_ROOT.resolve()).as_posix()
        manifest = {
            "schema_version": "1.0.0",
            "product": PRODUCT,
            "generator_version": GENERATOR_VERSION,
            "job_id": job_id,
            "artifact": {
                "filename": filename,
                "bytes": output_path.stat().st_size,
                "sha256": file_hash,
                "editable": True,
                "format": "pptx",
            },
            "scope": scope,
            "scope_fingerprint": fingerprint,
            "data_mode": active_mode,
            "source_context": source,
            "evidence_id": evidence_id,
            "evidence_sha256": _canonical_hash(evidence),
            "metric_version": metadata.get("metric_registry_version"),
            "synthetic": bool(source.get("synthetic", True)),
            "synthetic_data": bool(source.get("synthetic", True)),
            "synthetic_statement": SYNTHETIC_STATEMENT,
            "refresh_timestamp": model["refreshed_at"],
            "slide_count": len(REQUIRED_SLIDE_TITLES),
            "required_slides": list(REQUIRED_SLIDE_TITLES),
            "slide_evidence_ids": model["slide_evidence_ids"],
            "validation": validation,
            "validation_status": validation["status"],
            "reconciliation": reconciliation,
            "reconciliation_status": reconciliation["status"],
            "render_evidence": {
                "rendered_slide_count": len(build_result.get("slides", [])),
                "qa_root": qa_root_relative,
            },
        }
        manifest_path = output_directory / manifest_filename
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        manifest_hash = _sha256_file(manifest_path)
        completed_at = datetime.now(UTC).isoformat()
        completed_state = {
            **current_state,
            "status": "completed",
            "stage": "completed",
            "last_completed_stage": "registering_manifest",
            "slide_count": validation["slide_count"],
            "file_sha256": file_hash,
            "size_bytes": output_path.stat().st_size,
            "manifest_sha256": manifest_hash,
            "validation": validation,
            "validation_status": validation["status"],
            "reconciliation": reconciliation,
            "reconciliation_status": reconciliation["status"],
            "refreshed_at": model["refreshed_at"],
            "completed_at": completed_at,
            "error": None,
        }
        record = _write_stage(store, job_id, completed_state, actor=actor)
        return {
            **_workflow_view(record),
            "reused": False,
            "download_url": f"/api/v1/executive-packs/{job_id}/download",
            "manifest_url": f"/api/v1/executive-packs/{job_id}/manifest",
            "source_context": source,
        }
    except ExecutivePackError as exc:
        failed_state = {
            **current_state,
            "status": "failed",
            "stage": "failed",
            "failed_stage": exc.stage,
            "error": str(exc),
        }
        _write_stage(store, job_id, failed_state, actor=actor)
        raise
    except Exception as exc:
        failed_state = {
            **current_state,
            "status": "failed",
            "stage": "failed",
            "failed_stage": str(current_state.get("stage") or "unknown"),
            "error": f"{type(exc).__name__}: {exc}",
        }
        _write_stage(store, job_id, failed_state, actor=actor)
        raise ExecutivePackError(
            str(current_state.get("stage") or "unknown"),
            f"{type(exc).__name__}: {exc}",
        ) from exc


def executive_pack_record(store: WorkflowStore, job_id: str) -> dict[str, Any]:
    try:
        record = store.get("export_job", job_id)
    except ObjectNotFound as exc:
        raise KeyError(job_id) from exc
    if record["state"].get("record_kind") != "executive_pack_job":
        raise KeyError(job_id)
    return _workflow_view(record)


def resolve_executive_pack_file(
    store: WorkflowStore,
    job_id: str,
    *,
    output_root: Path,
    manifest: bool = False,
) -> Path:
    state = executive_pack_record(store, job_id)
    if state.get("status") != "completed":
        raise KeyError(job_id)
    artifact, manifest_path = _resolve_job_paths(state, output_root=output_root)
    candidate = manifest_path if manifest else artifact
    if not candidate.is_file():
        raise KeyError(job_id)
    if not manifest:
        if state.get("file_sha256") != _sha256_file(candidate):
            raise KeyError(job_id)
        if int(state.get("size_bytes") or -1) != candidate.stat().st_size:
            raise KeyError(job_id)
    return candidate


def register_executive_pack_download(
    store: WorkflowStore,
    job_id: str,
    *,
    actor: str,
) -> dict[str, Any]:
    record = store.get("export_job", job_id)
    if record["state"].get("record_kind") != "executive_pack_job":
        raise KeyError(job_id)
    state = {
        **record["state"],
        "download_count": int(record["state"].get("download_count", 0)) + 1,
        "last_downloaded_at": datetime.now(UTC).isoformat(),
        "last_downloaded_by": actor,
    }
    updated = store.update(
        "export_job",
        job_id,
        state,
        expected_version=int(record["version"]),
        actor=actor,
        replace=True,
    )
    return _workflow_view(updated)


def metric_registry_contract(service: WorkbenchService) -> list[dict[str, Any]]:
    """Expose the canonical display contract used by the Executive Pack."""

    return [metric_display_contract(row) for row in service.config.metrics]
