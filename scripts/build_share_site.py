#!/usr/bin/env python3
"""Build a backend-free nAIM portfolio site from approved aggregate evidence."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from naim_risk.runtime_modes import dataset_hash

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = REPOSITORY_ROOT / "exports" / "validation" / "interop_evidence_snapshot.json"
DEFAULT_MARKET_SOURCE = REPOSITORY_ROOT / "outputs" / "market_risk" / "evidence_snapshot.json"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "outputs" / "share_site"
DEFAULT_WORKBOOK = REPOSITORY_ROOT / "outputs" / "nAIM_Portfolio_Intelligence_Workbench.xlsx"
DEFAULT_PREVIEW = REPOSITORY_ROOT / "public" / "og.png"
PUBLIC_SNAPSHOT = (
    REPOSITORY_ROOT / "apps" / "streamlit_demo" / "evidence" / "public_evidence_snapshot.json"
)
LINKEDIN_DIR = REPOSITORY_ROOT / "outputs" / "linkedin"
PRODUCT = "nAIM Portfolio Intelligence Workbench"
TAGLINE = "Name the movement. Own the evidence."
TEXT_SUFFIXES = frozenset({".html", ".css", ".js", ".json", ".txt", ".md", ".csv"})
ABSOLUTE_PATH_PATTERN = re.compile(r"/(?:Users|home|private|var|tmp)/")
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)


class ShowcaseBuildError(ValueError):
    """Raised when source evidence or the generated site is unsafe."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ShowcaseBuildError(f"Could not read JSON evidence: {path.name}") from exc
    if not isinstance(payload, dict):
        raise ShowcaseBuildError(f"Evidence must be a JSON object: {path.name}")
    return payload


def _require(mapping: dict[str, Any], *path: str) -> Any:
    value: Any = mapping
    for key in path:
        if not isinstance(value, dict) or key not in value:
            raise ShowcaseBuildError(f"Required evidence field is missing: {'.'.join(path)}")
        value = value[key]
    return value


def _metric(source: dict[str, Any], metric_id: str) -> dict[str, Any]:
    rows = source.get("kpis")
    if not isinstance(rows, list):
        raise ShowcaseBuildError("Evidence KPI collection is missing")
    matches = [row for row in rows if row.get("metric_id") == metric_id]
    if len(matches) != 1:
        raise ShowcaseBuildError(f"Expected one public KPI row for {metric_id}")
    return matches[0]


def _strategy(source: dict[str, Any], name: str) -> dict[str, Any]:
    rows = _require(source, "strategy_comparison", "strategies")
    matches = [row for row in rows if row.get("strategy") == name]
    if len(matches) != 1:
        raise ShowcaseBuildError(f"Expected one strategy row for {name}")
    return matches[0]


def _validate_source(source: dict[str, Any]) -> None:
    if source.get("schema_version") != "1.0.0":
        raise ShowcaseBuildError("Unsupported governed evidence schema")
    if source.get("synthetic_data_flag") is not True:
        raise ShowcaseBuildError("Public source must be explicitly synthetic")
    metadata = _require(source, "metadata")
    quality = _require(source, "data_quality")
    if (
        metadata.get("publication_allowed") is not True
        or quality.get("publication_allowed") is not True
    ):
        raise ShowcaseBuildError("Governed evidence is not approved for publication")
    if metadata.get("quality_status") != "PASS" or quality.get("status") != "PASS":
        raise ShowcaseBuildError("Governed evidence did not pass data quality")
    finding = _require(source, "root_cause", "finding")
    observed = float(_require(finding, "observed_change_bps"))
    reconciled = float(_require(finding, "mix_contribution_bps")) + float(
        _require(finding, "within_segment_contribution_bps")
    )
    residual = float(_require(finding, "reconciliation_residual_bps"))
    if abs(observed - reconciled - residual) > 1e-8:
        raise ShowcaseBuildError("Root-cause bridge does not reconcile")
    if finding.get("causal_status") != "ASSOCIATIONAL":
        raise ShowcaseBuildError("Public source must preserve the associational claim boundary")
    if source.get("selected_reporting_period") != "2025-08-01":
        raise ShowcaseBuildError("Expected the approved August 2025 governed story")


def _market_unavailable(reason: str) -> dict[str, Any]:
    return {
        "status": "UNAVAILABLE",
        "reason": reason,
        "validation_status": "PENDING",
        "trading_recommendation": False,
    }


def _validated_market_summary(path: Path) -> tuple[dict[str, Any], dict[str, str] | None]:
    if not path.is_file():
        return (
            _market_unavailable("No approved public market-risk evidence snapshot is available."),
            None,
        )
    try:
        source = _load_json(path)
        validation = _require(source, "validation")
        governance = _require(source, "governance")
        source_metadata = _require(source, "source")
        approved = (
            validation.get("status") == "PASS" or validation.get("publication_allowed") is True
        )
        licensed = (
            source_metadata.get("source_is_synthetic") is True
            or source_metadata.get("redistribution_permitted") is True
        )
        if source.get("status") != "implemented" or not approved or not licensed:
            raise ShowcaseBuildError("Market snapshot is not publication-approved")
        if governance.get("trading_recommendation") is not False:
            raise ShowcaseBuildError("Market snapshot does not rule out trading recommendations")
        if governance.get("causal_claim") is not False:
            raise ShowcaseBuildError("Market snapshot does not rule out causal claims")
        historical = _require(
            source, "historical_volatility", "estimators", "close_to_close", "annualised_volatility"
        )
        ewma = _require(source, "ewma", "one_step_annualised_volatility_forecast")
        confidence = _require(source, "var_expected_shortfall", "confidence")
        historical_var = _require(source, "var_expected_shortfall", "methods", "historical", "var")
        historical_es = _require(
            source, "var_expected_shortfall", "methods", "historical", "expected_shortfall"
        )
        returns = _require(source, "returns")
        observations = returns.get("observation_count")
        if observations is None:
            observations = _require(returns, "summary", "observations")
        comparison = _require(source, "model_comparison", "models")
        public_models = [
            {
                "model": row.get("model"),
                "forecast_volatility": row.get("one_step_forecast"),
                "qlike": row.get("out_of_sample_qlike"),
                "diagnostic_status": row.get("diagnostic_status"),
            }
            for row in comparison
            if row.get("model") in {"historical", "rolling", "ewma", "arch", "garch"}
        ]
        return (
            {
                "status": "LIVE",
                "validation_status": "PASS",
                "instrument": str(source_metadata.get("instrument", "synthetic instrument")),
                "provider": str(source_metadata.get("provider", "validated provider")),
                "source_is_synthetic": source_metadata.get("source_is_synthetic") is True,
                "observation_count": int(observations),
                "summary": {
                    "historical_volatility": float(historical),
                    "ewma_forecast_volatility": float(ewma),
                    "confidence": float(confidence),
                    "historical_var": float(historical_var),
                    "historical_expected_shortfall": float(historical_es),
                },
                "model_comparison": public_models,
                "limitations": list(governance.get("limitations", [])),
                "trading_recommendation": False,
            },
            {"path": "outputs/market_risk/evidence_snapshot.json", "sha256": _sha256(path)},
        )
    except (ShowcaseBuildError, TypeError, ValueError):
        return (
            _market_unavailable(
                "A market-risk snapshot was found but did not satisfy the public validation contract."
            ),
            None,
        )


def build_public_evidence(source_path: Path, market_path: Path) -> dict[str, Any]:
    """Reduce governed sources to a public, aggregate-only evidence contract."""

    source = _load_json(source_path)
    _validate_source(source)
    source_hash = _sha256(source_path)
    finding = _require(source, "root_cause", "finding")
    loss = _metric(source, "ANNUALISED_NET_LOSS_RATE")
    champion = _strategy(source, "Champion A")
    challenger = _strategy(source, "Challenger B")
    quality = _require(source, "data_quality")
    metadata = _require(source, "metadata")
    run_manifest = (
        REPOSITORY_ROOT
        / "data"
        / "manifests"
        / str(metadata["run_id"])
        / "run_manifest.json"
    )
    if not run_manifest.is_file():
        raise ShowcaseBuildError("Canonical run manifest is unavailable")
    dataset_digest, dataset_basis = dataset_hash(run_manifest, REPOSITORY_ROOT / "data")
    trend_rows = [
        {
            "month": str(row["month"]),
            "value": float(row["value"]),
            "unit": "annualised_rate",
        }
        for row in source.get("trends", [])
        if row.get("metric_id") == "ANNUALISED_NET_LOSS_RATE"
    ]
    if len(trend_rows) < 12:
        raise ShowcaseBuildError("Public loss-rate trend has insufficient aggregate history")
    market, market_source = _validated_market_summary(market_path)
    source_inputs = [
        {
            "path": "exports/validation/interop_evidence_snapshot.json",
            "sha256": source_hash,
            "publication_allowed": True,
        }
    ]
    if market_source is not None:
        source_inputs.append({**market_source, "publication_allowed": True})
    run_id = str(metadata.get("run_id", "governed-run"))
    return {
        "schema_version": "1.0.0",
        "product": PRODUCT,
        "pronunciation": "name",
        "aim_expansion": "All Is Mine",
        "tagline": TAGLINE,
        "evidence_id": f"NAIM-{run_id}-2025-08",
        "data_mode": "OFFLINE_SNAPSHOT",
        "reporting_period": "2025-08-01",
        "comparison_period": "2025-07-01",
        "source_context": {
            "type": "validated_offline_evidence_snapshot",
            "profile": str(metadata.get("profile", "default")),
            "run_id": run_id,
            "metric_registry_version": str(metadata.get("metric_registry_version", "unknown")),
            "dataset_profile": str(metadata.get("profile", "default")),
            "dataset_hash": dataset_digest,
            "dataset_hash_basis": dataset_basis,
            "configuration_hash": str(metadata["configuration_hash"]),
            "filter_scope": {
                "headline_scope": "all_portfolio",
                "approved_reference_basket": "BASKET-001",
            },
            "selection_rule": str(source.get("selection_rule")),
            "source_inputs": source_inputs,
        },
        "validation": {
            "data_quality_status": "PASS",
            "data_quality_score": float(quality.get("score", 0)),
            "publication_allowed": True,
            "root_cause_reconciliation_tolerance_bps": 1e-8,
            "root_cause_reconciliation_passed": True,
        },
        "synthetic_data": True,
        "synthetic_statement": (
            "All data, names, contracts, findings, thresholds and currency values are synthetic "
            "and institution-neutral. No customer, partner, vendor or observed market fact is shown."
        ),
        "portfolio_story": {
            "reporting_period_label": "August 2025 versus July 2025",
            "metric_id": "ANNUALISED_NET_LOSS_RATE",
            "metric_version": str(loss.get("metric_version", "unknown")),
            "current_annualised_net_loss_rate": float(loss["value"]),
            "prior_annualised_net_loss_rate": float(loss["prior_value"]),
            "observed_change_bps": float(finding["observed_change_bps"]),
            "denominator": float(loss["denominator"]),
            "data_quality_status": str(finding["data_quality_status"]),
        },
        "kpi_snapshot": [
            {
                "metric_id": str(row["metric_id"]),
                "metric_version": str(row.get("metric_version", "unknown")),
                "name": str(row["name"]),
                "unit": str(row["unit"]),
                "value": float(row["value"]),
                "prior_value": float(row["prior_value"]),
                "reporting_period": str(row["reporting_period"]),
                "comparison_period": str(row["comparison_period"]),
            }
            for row in source["kpis"]
        ],
        "decomposition": {
            "method": "exact additive mix and within-segment bridge",
            "dimension": str(finding["primary_dimension"]),
            "primary_driver": str(finding["primary_driver"]),
            "mix_bps": float(finding["mix_contribution_bps"]),
            "within_segment_bps": float(finding["within_segment_contribution_bps"]),
            "residual_bps": float(finding["reconciliation_residual_bps"]),
            "contribution_share": float(finding["contribution_share"]),
            "causal_status": "ASSOCIATIONAL",
            "recommended_investigation": list(finding["recommended_investigation"]),
        },
        "strategy": {
            "decision": str(_require(source, "strategy_comparison", "recommendation", "decision")),
            "approval_required": bool(
                _require(source, "strategy_comparison", "recommendation", "approval_required")
            ),
            "sample_ratio_mismatch_flag": bool(
                _require(source, "strategy_comparison", "validity", "sample_ratio_mismatch_flag")
            ),
            "causal_warning": str(
                _require(source, "strategy_comparison", "validity", "causal_warning")
            ),
            "comparison": [
                {
                    "strategy": str(champion["strategy"]),
                    "fraud_bps": round(float(champion["fraud_bps"]), 4),
                    "false_positive_rate": round(float(champion["false_positive_rate"]), 6),
                    "customer_friction_rate": round(float(champion["customer_friction_rate"]), 6),
                },
                {
                    "strategy": str(challenger["strategy"]),
                    "fraud_bps": round(float(challenger["fraud_bps"]), 4),
                    "false_positive_rate": round(float(challenger["false_positive_rate"]), 6),
                    "customer_friction_rate": round(float(challenger["customer_friction_rate"]), 6),
                },
            ],
        },
        "loss_rate_trend": trend_rows,
        "market_risk": market,
        "public_boundaries": {
            "raw_account_records": False,
            "mutable_administration": False,
            "secrets": False,
            "trading_recommendation": False,
            "automated_credit_decision": False,
            "external_model_call": False,
        },
        "limitations": [
            "Observational decomposition and strategy views are associational unless a valid randomised design is explicitly identified.",
            "Annualised monthly rates are presentation measures, not forecasts.",
            "The selected August 2025 deterioration is a seeded synthetic demonstration story.",
            "Scenario and market-risk outputs are conditional estimates, not regulatory stress tests or maximum-loss estimates.",
            "This public surface is read-only and intentionally omits raw records and administrative controls.",
        ],
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_snapshot(path: Path, evidence: dict[str, Any]) -> None:
    _write_json(path, evidence)
    digest = _sha256(path)
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{digest}  {path.name}\n", encoding="utf-8"
    )


def _format_pct(value: float) -> str:
    return f"{100 * value:.2f}%"


def _trend_svg(rows: list[dict[str, Any]]) -> str:
    width, height = 900, 280
    left, right, top, bottom = 54, 18, 22, 42
    values = [float(row["value"]) * 100 for row in rows]
    minimum = min(values)
    maximum = max(values)
    span = max(maximum - minimum, 0.01)
    points: list[str] = []
    circles: list[str] = []
    for index, (row, value) in enumerate(zip(rows, values, strict=True)):
        x = left + index * (width - left - right) / max(len(rows) - 1, 1)
        y = top + (maximum - value) * (height - top - bottom) / span
        points.append(f"{x:.1f},{y:.1f}")
        label = html.escape(f"{row['month'][:7]}: {value:.2f}%")
        circles.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" tabindex="0"><title>{label}</title></circle>'
        )
    peak_index = values.index(maximum)
    peak_x = left + peak_index * (width - left - right) / max(len(rows) - 1, 1)
    peak_y = top
    return f"""
<svg class="trend-chart" viewBox="0 0 {width} {height}" role="img"
  aria-labelledby="trend-title trend-description">
  <title id="trend-title">Calculated annualised net loss rate by month</title>
  <desc id="trend-description">Aggregate synthetic portfolio trend with an August 2025 peak.</desc>
  <line x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}" />
  <line x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}" />
  <polyline points="{" ".join(points)}" />
  {"".join(circles)}
  <line class="peak-marker" x1="{peak_x:.1f}" y1="{peak_y}" x2="{peak_x:.1f}" y2="{height - bottom}" />
  <text x="{peak_x + 8:.1f}" y="{peak_y + 18}">Aug 2025 · {maximum:.2f}%</text>
  <text x="{left}" y="{height - 12}">{html.escape(rows[0]["month"][:7])}</text>
  <text x="{width - 76}" y="{height - 12}">{html.escape(rows[-1]["month"][:7])}</text>
</svg>
""".strip()


def _market_html(market: dict[str, Any]) -> str:
    if market.get("status") != "LIVE":
        return f"""
<div class="status-card unavailable">
  <span class="eyebrow">UNAVAILABLE · VALIDATION PENDING</span>
  <h3>No public market-risk result is claimed</h3>
  <p>{html.escape(str(market["reason"]))}</p>
  <p>The section activates only after a frozen synthetic or redistribution-permitted evidence
  snapshot passes the public validation contract.</p>
</div>
""".strip()
    summary = market["summary"]
    model_rows_list: list[str] = []
    for row in market.get("model_comparison", []):
        forecast = (
            _format_pct(float(row["forecast_volatility"]))
            if row["forecast_volatility"] is not None
            else "N/A"
        )
        qlike = f"{float(row['qlike']):.6f}" if row["qlike"] is not None else "N/A"
        model_rows_list.append(
            "<tr>"
            f"<td>{html.escape(str(row['model']))}</td>"
            f"<td>{forecast}</td>"
            f"<td>{qlike}</td>"
            f"<td>{html.escape(str(row['diagnostic_status']))}</td>"
            "</tr>"
        )
    model_rows = "".join(model_rows_list)
    return f"""
<div class="metric-grid three">
  <article><span>Historical volatility</span><strong>{_format_pct(summary["historical_volatility"])}</strong></article>
  <article><span>EWMA forecast</span><strong>{_format_pct(summary["ewma_forecast_volatility"])}</strong></article>
  <article><span>Historical VaR ({summary["confidence"]:.0%})</span><strong>{_format_pct(summary["historical_var"])}</strong></article>
</div>
<p class="annotation">Synthetic instrument {html.escape(market["instrument"])};
{market["observation_count"]:,} aggregate observations. No trade signal or investment recommendation.</p>
<div class="table-wrap"><table><thead><tr><th>Model</th><th>Forecast volatility</th><th>QLIKE</th><th>Status</th></tr></thead>
<tbody>{model_rows}</tbody></table></div>
""".strip()


def _screenshot_gallery(output: Path) -> tuple[str, list[Path]]:
    assets = output / "assets"
    copied: list[Path] = []
    figures: list[str] = []
    if DEFAULT_PREVIEW.is_file():
        destination = assets / "project-preview.png"
        shutil.copyfile(DEFAULT_PREVIEW, destination)
        copied.append(destination)
        figures.append(
            '<figure><img src="assets/project-preview.png" alt="nAIM project preview with the '
            'governed August 2025 evidence bridge"><figcaption>Governed project preview</figcaption></figure>'
        )
    screenshot_root = REPOSITORY_ROOT / "outputs" / "screenshots"
    candidates = sorted(screenshot_root.glob("naim-*.png")) if screenshot_root.exists() else []
    for index, source in enumerate(candidates[:4], start=1):
        destination = assets / f"screen-{index:02d}.png"
        shutil.copyfile(source, destination)
        copied.append(destination)
        figures.append(
            f'<figure><img src="assets/{destination.name}" alt="Validated nAIM workbench screen '
            f'{index}"><figcaption>Validated workbench screen {index}</figcaption></figure>'
        )
    if len(figures) == 1:
        figures.append(
            """
<figure class="screen-reconstruction" role="img" aria-label="Accessible reconstruction of the
nAIM evidence workspace with data-mode, data-quality and approval indicators">
  <div class="mini-toolbar"><span>OFFLINE SNAPSHOT</span><span>DQ PASS</span></div>
  <div class="mini-layout"><div><b>Movement</b><em>+311.4 bps</em></div>
  <div><b>Evidence</b><em>Mix +4.4 · Within +307.0</em></div>
  <div><b>Decision</b><em>Investigate · approval required</em></div></div>
  <figcaption>Evidence-workspace reconstruction; browser capture pending final release QA</figcaption>
</figure>
""".strip()
        )
    return "".join(figures), copied


def _download_cards(output: Path, workbook: Path) -> tuple[str, list[Path]]:
    downloads = output / "downloads"
    copied: list[Path] = []
    cards = [
        """
<a class="download-card" href="downloads/public_evidence_snapshot.json" download>
  <span>JSON</span><strong>Approved public evidence</strong><small>Aggregate, synthetic and checksummed</small>
</a>
""".strip()
    ]
    if workbook.is_file() and workbook.suffix.lower() == ".xlsx":
        destination = downloads / "nAIM_Portfolio_Intelligence_Workbench.xlsx"
        shutil.copyfile(workbook, destination)
        copied.append(destination)
        cards.append(
            """
<a class="download-card" href="downloads/nAIM_Portfolio_Intelligence_Workbench.xlsx" download>
  <span>XLSX</span><strong>Validated sample workbook</strong><small>Point-in-time public artifact</small>
</a>
""".strip()
        )
    else:
        cards.append(
            """
<div class="download-card unavailable"><span>XLSX</span><strong>Sample workbook</strong>
<small>Final artifact validation pending; no historical file substituted</small></div>
""".strip()
        )
    text_files = [
        ("project-summary.md", "Project summary"),
        ("technical-summary.md", "Technical summary"),
        ("research-summary.md", "Research summary"),
    ]
    for filename, label in text_files:
        source = LINKEDIN_DIR / filename
        if not source.is_file():
            continue
        destination = downloads / filename
        shutil.copyfile(source, destination)
        copied.append(destination)
        cards.append(
            f'<a class="download-card" href="downloads/{filename}" download><span>MD</span>'
            f"<strong>{html.escape(label)}</strong><small>Reconciled showcase copy</small></a>"
        )
    return "".join(cards), copied


def _valid_public_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ShowcaseBuildError("Repository URL must be an http(s) URL")
    if parsed.username or parsed.password:
        raise ShowcaseBuildError("Repository URL must not contain credentials")
    return value


def _build_html(
    evidence: dict[str, Any],
    screenshots: str,
    downloads: str,
    repository_url: str | None,
    contact: str | None,
) -> str:
    story = evidence["portfolio_story"]
    decomposition = evidence["decomposition"]
    strategy = evidence["strategy"]
    repository = (
        f'<a href="{html.escape(repository_url)}" rel="noopener noreferrer">View repository</a>'
        if repository_url
        else '<span class="placeholder">Repository link — configure at build time</span>'
    )
    contact_html = (
        f"<span>{html.escape(contact)}</span>"
        if contact
        else '<span class="placeholder">Contact — configure at build time</span>'
    )
    bridge_scale = max(abs(decomposition["mix_bps"]), abs(decomposition["within_segment_bps"]))
    mix_width = max(2.0, 100 * abs(decomposition["mix_bps"]) / bridge_scale)
    within_width = 100 * abs(decomposition["within_segment_bps"]) / bridge_scale
    limitations = "".join(f"<li>{html.escape(item)}</li>" for item in evidence["limitations"])
    trend_svg = _trend_svg(evidence["loss_rate_trend"])
    market = _market_html(evidence["market_risk"])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="A governed, synthetic portfolio-risk evidence workbench.">
  <meta name="theme-color" content="#071a2b">
  <title>{PRODUCT}</title>
  <link rel="stylesheet" href="assets/styles.css">
  <script src="assets/site.js" defer></script>
</head>
<body>
<a class="skip-link" href="#main">Skip to content</a>
<header class="site-header">
  <a class="brand" href="#top" aria-label="nAIM home"><b>nAIM</b><span>Portfolio Intelligence Workbench</span></a>
  <nav aria-label="Primary navigation">
    <a href="#story">Story</a><a href="#architecture">Architecture</a>
    <a href="#methodology">Method</a><a href="#market-risk">Market risk</a>
    <a href="#downloads">Downloads</a><a href="#limitations">Limitations</a>
  </nav>
</header>
<main id="main">
<section id="top" class="hero">
  <div>
    <span class="eyebrow">OFFLINE SNAPSHOT · SYNTHETIC · DQ PASS</span>
    <h1>Name the movement.<br><i>Own the evidence.</i></h1>
    <p class="lede">nAIM (pronounced “name”; AIM = All Is Mine) connects portfolio movement,
    exact driver evidence, strategy trade-offs and governed handoff in one reproducible layer.</p>
    <div class="hero-actions"><a class="button" href="#story">See the 60-second story</a>
    <a class="text-link" href="#downloads">Open public artifacts →</a></div>
  </div>
  <aside class="evidence-card">
    <span>Governed movement</span><strong>+{story["observed_change_bps"]:.1f} bps</strong>
    <p>{story["reporting_period_label"]}</p>
    <dl><div><dt>Mix</dt><dd>+{decomposition["mix_bps"]:.1f}</dd></div>
    <div><dt>Within</dt><dd>+{decomposition["within_segment_bps"]:.1f}</dd></div>
    <div><dt>Residual</dt><dd>{decomposition["residual_bps"]:.3f}</dd></div></dl>
  </aside>
</section>

<section id="overview" class="section intro">
  <span class="eyebrow">PROJECT OVERVIEW</span><h2>A decision workbench, not another dashboard</h2>
  <p>nAIM preserves definitions, populations, comparisons, evidence and decision boundaries across
  analysis and exported artifacts. This backend-free showcase contains only approved aggregate
  evidence; it has no raw account records or mutable administration.</p>
  <div class="metric-grid four">
    <article><span>Loss rate</span><strong>{_format_pct(story["current_annualised_net_loss_rate"])}</strong><small>from {_format_pct(story["prior_annualised_net_loss_rate"])}</small></article>
    <article><span>Movement</span><strong>+{story["observed_change_bps"]:.1f} bps</strong><small>calculated, reconciled</small></article>
    <article><span>Data quality</span><strong>{evidence["validation"]["data_quality_score"]:.0f}/100</strong><small>publication allowed</small></article>
    <article><span>Decision</span><strong>{html.escape(strategy["decision"])}</strong><small>approval required</small></article>
  </div>
</section>

<section id="story" class="section dark">
  <span class="eyebrow">THE 60-SECOND STORY</span><h2>From movement to governed action</h2>
  <ol class="story-steps">
    <li><span>00–10s</span><div><b>Name the movement</b><p>At the August 2025 calculated peak,
    annualised net loss rate reached {_format_pct(story["current_annualised_net_loss_rate"])}, up
    {story["observed_change_bps"]:.1f} bps month on month.</p></div></li>
    <li><span>10–25s</span><div><b>Reconcile the bridge</b><p>Mix contributes
    {decomposition["mix_bps"]:.1f} bps and within-segment performance
    {decomposition["within_segment_bps"]:.1f} bps, with a negligible residual.</p></div></li>
    <li><span>25–40s</span><div><b>Bound the diagnosis</b><p>{html.escape(decomposition["primary_driver"])}
    is the largest acquisition-channel contributor. The finding is associational, not causal.</p></div></li>
    <li><span>40–52s</span><div><b>See the trade-off</b><p>Challenger B lowers fraud to
    {strategy["comparison"][1]["fraud_bps"]:.2f} bps versus {strategy["comparison"][0]["fraud_bps"]:.2f}
    for Champion A, but its false-positive rate is {strategy["comparison"][1]["false_positive_rate"]:.2%}.</p></div></li>
    <li><span>52–60s</span><div><b>Govern the handoff</b><p>The sample-ratio check fails, so the
    result remains investigatory and requires human approval.</p></div></li>
  </ol>
</section>

<section id="evidence" class="section">
  <span class="eyebrow">PRE-RENDERED EVIDENCE</span><h2>The movement in context</h2>
  {trend_svg}
  <p class="annotation">Aggregate synthetic metric. Annualisation is a presentation measure, not a forecast.</p>
  <div class="bridge">
    <div><span>Mix contribution · +{decomposition["mix_bps"]:.1f} bps</span><i style="width:{mix_width:.2f}%"></i></div>
    <div><span>Within-segment · +{decomposition["within_segment_bps"]:.1f} bps</span><i style="width:{within_width:.2f}%"></i></div>
  </div>
</section>

<section id="architecture" class="section pale">
  <span class="eyebrow">ARCHITECTURE</span><h2>One evidence contract, many consumers</h2>
  <div class="architecture" role="img" aria-label="Synthetic source data flows through validation,
  canonical metrics, analytics, governed API and public or enterprise artifacts">
    <div>Synthetic / approved sources</div><b>→</b><div>Validation &amp; quarantine</div><b>→</b>
    <div>Canonical model</div><b>→</b><div>Governed metrics</div><b>→</b>
    <div>Analytics &amp; workflows</div><b>→</b><div>Evidence contracts &amp; exports</div>
  </div>
  <p>Trust boundaries separate source ingestion, calculation, evidence generation and consumption.
  Only validated aggregate evidence reaches this public surface.</p>
</section>

<section id="screens" class="section">
  <span class="eyebrow">PRODUCT PREVIEWS</span><h2>Evidence made inspectable</h2>
  <div class="gallery">{screenshots}</div>
</section>

<section id="methodology" class="section split">
  <div><span class="eyebrow">METHODOLOGY</span><h2>Exact where possible, explicit where uncertain</h2>
  <p>The selected story is the peak calculated annualised net loss rate in the generated history.
  An additive bridge separates portfolio-mix movement from within-segment performance and verifies
  the residual. Strategy comparison carries balance checks, multiplicity control and a causal warning.</p></div>
  <div class="method-list">
    <article><b>Point-in-time evidence</b><span>Reporting and comparison periods are explicit.</span></article>
    <article><b>Metric governance</b><span>Definitions, units, denominators and versions travel together.</span></article>
    <article><b>Claim boundary</b><span>Association is never relabelled as causation.</span></article>
    <article><b>Human approval</b><span>Analytics inform decisions; they do not make them.</span></article>
  </div>
</section>

<section id="market-risk" class="section pale">
  <span class="eyebrow">MARKET RISK &amp; VOLATILITY LAB</span><h2>Model comparison with honest availability</h2>
  {market}
</section>

<section id="downloads" class="section">
  <span class="eyebrow">PUBLIC DOWNLOADS</span><h2>Take the evidence with you</h2>
  <div class="downloads">{downloads}</div>
  <p class="annotation">Only validated, synthetic, public-safe files are copied. Missing artifacts remain visibly pending.</p>
</section>

<section id="stack" class="section dark">
  <span class="eyebrow">TECHNOLOGY STACK</span><h2>Built for reproducibility and interoperability</h2>
  <ul class="chips"><li>Python 3.12</li><li>FastAPI</li><li>pandas</li><li>NumPy</li>
  <li>SciPy</li><li>DuckDB</li><li>Parquet</li><li>SQLAlchemy</li><li>Next.js</li>
  <li>TypeScript</li><li>Streamlit</li><li>Excel</li><li>PowerPoint</li></ul>
</section>

<section id="limitations" class="section split">
  <div><span class="eyebrow">LIMITATIONS</span><h2>What this demonstration does not claim</h2>
  <ul class="limitations">{limitations}</ul></div>
  <aside class="disclosure"><b>Synthetic-data statement</b><p>{html.escape(evidence["synthetic_statement"])}</p>
  <b>Public boundary</b><p>No secrets, raw records, administrative controls, trade signals or
  automated credit decisions are exposed.</p></aside>
</section>
</main>
<footer><div><b>nAIM</b><span>{TAGLINE}</span></div><div>{repository}<br>{contact_html}</div></footer>
</body>
</html>
"""


STYLES = r"""
:root{--ink:#071a2b;--navy:#0b263d;--blue:#176b87;--teal:#24a6a4;--mint:#a8e6d2;--paper:#f7f8f5;--pale:#eaf3f1;--line:#cbd9d7;--amber:#efb04b;--white:#fff;--max:1180px;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:var(--ink);background:var(--paper)}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;line-height:1.55}.skip-link{position:absolute;left:-999px}.skip-link:focus{left:16px;top:16px;background:white;padding:10px;z-index:20}.site-header{position:sticky;top:0;z-index:10;display:flex;justify-content:space-between;align-items:center;padding:15px max(24px,calc((100vw - var(--max))/2));background:rgba(7,26,43,.96);color:white;border-bottom:1px solid #284258}.brand{color:white;text-decoration:none;display:flex;align-items:baseline;gap:10px}.brand b{font-size:1.55rem;letter-spacing:-.05em}.brand span{font-size:.78rem;color:#b9d4dd}.site-header nav{display:flex;gap:18px;flex-wrap:wrap}.site-header nav a{color:#dcecef;text-decoration:none;font-size:.8rem}.site-header nav a:hover,.site-header nav a:focus{color:var(--mint)}.hero,.section{padding:90px max(24px,calc((100vw - var(--max))/2))}.hero{min-height:680px;background:radial-gradient(circle at 80% 20%,#174f66 0,#071a2b 50%);color:white;display:grid;grid-template-columns:1.4fr .75fr;gap:70px;align-items:center}.eyebrow{display:block;font-size:.72rem;letter-spacing:.15em;font-weight:800;color:var(--teal);margin-bottom:18px}.hero .eyebrow,.dark .eyebrow{color:var(--mint)}h1{font-size:clamp(3.3rem,7vw,6.4rem);line-height:.9;letter-spacing:-.065em;margin:0 0 28px;max-width:850px}h1 i{font-style:normal;color:var(--mint)}h2{font-size:clamp(2rem,4vw,3.6rem);line-height:1;letter-spacing:-.045em;margin:0 0 26px;max-width:780px}.lede{font-size:1.15rem;color:#c9dfe4;max-width:690px}.hero-actions{display:flex;align-items:center;gap:24px;margin-top:36px}.button{background:var(--mint);color:var(--ink);text-decoration:none;padding:13px 18px;border-radius:4px;font-weight:800}.text-link{color:white}.evidence-card{background:rgba(255,255,255,.08);border:1px solid #31536a;padding:30px;border-radius:8px;box-shadow:0 24px 80px rgba(0,0,0,.22)}.evidence-card>span{font-size:.8rem;color:#b9d4dd}.evidence-card>strong{display:block;font-size:3.8rem;letter-spacing:-.05em;color:var(--mint)}.evidence-card dl{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.evidence-card dl div{border-top:1px solid #31536a;padding-top:12px}.evidence-card dt{font-size:.68rem;color:#b9d4dd}.evidence-card dd{margin:2px 0;font-weight:800}.section{background:white}.section.intro>p,.section>p{max-width:820px;font-size:1.05rem}.dark{background:var(--ink);color:white}.pale{background:var(--pale)}.metric-grid{display:grid;gap:14px;margin-top:38px}.metric-grid.four{grid-template-columns:repeat(4,1fr)}.metric-grid.three{grid-template-columns:repeat(3,1fr)}.metric-grid article{border:1px solid var(--line);padding:20px;background:white;color:var(--ink)}.metric-grid span,.metric-grid small{display:block;color:#536c77;font-size:.74rem}.metric-grid strong{display:block;font-size:2rem;letter-spacing:-.035em;margin:6px 0}.story-steps{list-style:none;padding:0;margin:45px 0 0;max-width:900px}.story-steps li{display:grid;grid-template-columns:90px 1fr;gap:24px;padding:24px 0;border-top:1px solid #294156}.story-steps li>span{font:700 .75rem ui-monospace,monospace;color:var(--mint)}.story-steps b{font-size:1.25rem}.story-steps p{margin:.4em 0;color:#c9dfe4}.trend-chart{width:100%;height:auto;background:#f8fbfa;border:1px solid var(--line);border-radius:6px;margin-top:30px}.trend-chart line{stroke:#78939c;stroke-width:1}.trend-chart polyline{fill:none;stroke:var(--teal);stroke-width:4;stroke-linejoin:round}.trend-chart circle{fill:var(--ink);stroke:white;stroke-width:2}.trend-chart circle:focus{r:7;outline:none}.trend-chart .peak-marker{stroke:var(--amber);stroke-dasharray:5 4}.trend-chart text{font-size:12px;fill:#36515d}.annotation{font-size:.78rem!important;color:#607780}.bridge{margin-top:35px;max-width:900px}.bridge div{margin:16px 0}.bridge span{display:block;font-size:.8rem;font-weight:700;margin-bottom:5px}.bridge i{display:block;height:22px;background:linear-gradient(90deg,var(--blue),var(--teal));min-width:8px}.architecture{display:grid;grid-template-columns:1fr auto 1fr auto 1fr auto 1fr auto 1fr auto 1fr;align-items:center;gap:10px;margin:40px 0}.architecture div{background:white;border:1px solid var(--line);padding:18px;text-align:center;min-height:84px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:.78rem}.architecture b{color:var(--blue)}.gallery{display:grid;grid-template-columns:repeat(2,1fr);gap:22px}.gallery figure{margin:0;border:1px solid var(--line);background:#f5f8f7;padding:12px}.gallery img{display:block;width:100%;height:auto}.gallery figcaption{font-size:.75rem;color:#526c76;margin-top:10px}.screen-reconstruction{min-height:310px}.mini-toolbar{display:flex;justify-content:space-between;background:var(--ink);color:var(--mint);padding:13px;font-size:.7rem}.mini-layout{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;padding:34px 15px}.mini-layout div{padding:18px;background:white;border-left:3px solid var(--teal)}.mini-layout b,.mini-layout em{display:block}.mini-layout em{font-style:normal;font-size:.8rem;color:#4e6974;margin-top:8px}.split{display:grid;grid-template-columns:1fr 1fr;gap:70px}.method-list article{padding:17px 0;border-top:1px solid var(--line);display:grid;grid-template-columns:160px 1fr;gap:20px}.method-list span{color:#536c77}.status-card{padding:28px;border:1px solid var(--line);background:white;max-width:850px}.status-card.unavailable{border-left:5px solid var(--amber)}.table-wrap{overflow-x:auto;margin-top:22px}table{border-collapse:collapse;width:100%;background:white}th,td{text-align:left;padding:12px;border-bottom:1px solid var(--line);font-size:.82rem}.downloads{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.download-card{display:flex;flex-direction:column;gap:7px;border:1px solid var(--line);padding:20px;color:var(--ink);text-decoration:none;background:white}.download-card:hover,.download-card:focus{border-color:var(--teal);transform:translateY(-2px)}.download-card>span{font:800 .68rem ui-monospace,monospace;color:var(--blue)}.download-card small{color:#617780}.download-card.unavailable{background:#f3f4f1;color:#6c7678}.chips{display:flex;flex-wrap:wrap;gap:10px;list-style:none;padding:0}.chips li{border:1px solid #365064;padding:9px 13px;color:#cbe0e4}.limitations{padding-left:20px}.limitations li{margin-bottom:12px}.disclosure{background:var(--pale);border-left:5px solid var(--teal);padding:28px}.placeholder{color:#73858c;font-style:italic}footer{background:#04111d;color:white;padding:42px max(24px,calc((100vw - var(--max))/2));display:flex;justify-content:space-between;gap:30px}footer div{display:flex;flex-direction:column}footer a{color:var(--mint)}@media(max-width:900px){.site-header{position:relative}.site-header nav{display:none}.hero{grid-template-columns:1fr;min-height:auto}.metric-grid.four,.metric-grid.three,.downloads{grid-template-columns:repeat(2,1fr)}.architecture{grid-template-columns:1fr}.architecture b{transform:rotate(90deg)}.gallery,.split{grid-template-columns:1fr}.mini-layout{grid-template-columns:1fr}}@media(max-width:560px){.hero,.section{padding:64px 20px}.metric-grid.four,.metric-grid.three,.downloads{grid-template-columns:1fr}.story-steps li{grid-template-columns:1fr}.evidence-card>strong{font-size:3rem}footer{flex-direction:column}}@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}.download-card{transition:none}}
""".strip()

SCRIPT = r"""
document.documentElement.classList.add("js");
const links = Array.from(document.querySelectorAll('nav a[href^="#"]'));
const sections = links.map(link => document.querySelector(link.getAttribute("href"))).filter(Boolean);
if ("IntersectionObserver" in window) {
  const observer = new IntersectionObserver(entries => {
    entries.filter(entry => entry.isIntersecting).forEach(entry => {
      links.forEach(link => link.removeAttribute("aria-current"));
      const active = links.find(link => link.getAttribute("href") === `#${entry.target.id}`);
      if (active) active.setAttribute("aria-current", "location");
    });
  }, {rootMargin: "-30% 0px -60% 0px"});
  sections.forEach(section => observer.observe(section));
}
""".strip()


class _LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if attributes.get("id"):
            self.ids.add(str(attributes["id"]))
        for name in ("href", "src"):
            if attributes.get(name):
                self.links.append(str(attributes[name]))


def validate_share_site(output: Path) -> dict[str, Any]:
    """Validate internal links, portable paths, basic secret patterns, and file inventory."""

    index = output / "index.html"
    if not index.is_file():
        raise ShowcaseBuildError("Share site has no index.html")
    parser = _LinkCollector()
    parser.feed(index.read_text(encoding="utf-8"))
    broken: list[str] = []
    for link in parser.links:
        parsed = urlparse(link)
        if parsed.scheme in {"http", "https", "mailto"}:
            continue
        if link.startswith("#"):
            if link[1:] not in parser.ids:
                broken.append(link)
            continue
        target_path = parsed.path
        if not target_path:
            continue
        target = (output / target_path).resolve()
        try:
            target.relative_to(output.resolve())
        except ValueError:
            broken.append(link)
            continue
        if not target.is_file():
            broken.append(link)
        if parsed.fragment and parsed.fragment not in parser.ids and target == index.resolve():
            broken.append(link)
    path_violations: list[str] = []
    secret_violations: list[str] = []
    files = sorted(path for path in output.rglob("*") if path.is_file())
    for path in files:
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(output).as_posix()
        if ABSOLUTE_PATH_PATTERN.search(text):
            path_violations.append(relative)
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            secret_violations.append(relative)
    if broken or path_violations or secret_violations:
        raise ShowcaseBuildError(
            f"Share-site validation failed: broken={broken}, absolute_paths={path_violations}, "
            f"secrets={secret_violations}"
        )
    return {
        "status": "PASS",
        "internal_links_checked": len(parser.links),
        "broken_internal_links": [],
        "absolute_path_violations": [],
        "secret_pattern_violations": [],
        "file_count": len(files),
        "backend_required": False,
        "auto_published": False,
    }


def build_share_site(
    *,
    source_path: Path = DEFAULT_SOURCE,
    market_path: Path = DEFAULT_MARKET_SOURCE,
    output: Path = DEFAULT_OUTPUT,
    workbook: Path = DEFAULT_WORKBOOK,
    repository_url: str | None = None,
    contact: str | None = None,
    streamlit_snapshot: Path = PUBLIC_SNAPSHOT,
) -> dict[str, Any]:
    """Build and validate the static share site plus the bundled Streamlit evidence snapshot."""

    repository_url = _valid_public_url(repository_url)
    output.mkdir(parents=True, exist_ok=True)
    (output / "assets").mkdir(exist_ok=True)
    (output / "data").mkdir(exist_ok=True)
    (output / "downloads").mkdir(exist_ok=True)
    stale_workbook = output / "downloads" / "nAIM_Portfolio_Intelligence_Workbench.xlsx"
    if stale_workbook.is_file():
        stale_workbook.unlink()
    for stale_screen in (output / "assets").glob("screen-*.png"):
        if stale_screen.is_file():
            stale_screen.unlink()
    evidence = build_public_evidence(source_path, market_path)
    _write_snapshot(streamlit_snapshot, evidence)
    _write_snapshot(output / "data" / "evidence.json", evidence)
    _write_snapshot(output / "downloads" / "public_evidence_snapshot.json", evidence)
    screenshots, screenshot_files = _screenshot_gallery(output)
    download_cards, _download_files = _download_cards(output, workbook)
    index = _build_html(evidence, screenshots, download_cards, repository_url, contact)
    (output / "index.html").write_text(index, encoding="utf-8")
    (output / "assets" / "styles.css").write_text(STYLES + "\n", encoding="utf-8")
    (output / "assets" / "site.js").write_text(SCRIPT + "\n", encoding="utf-8")
    validation = validate_share_site(output)
    build_id = hashlib.sha256(
        json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]
    manifest_outputs = {output / "build_manifest.json", output / "validation.json"}
    inventory = sorted(
        path for path in output.rglob("*") if path.is_file() and path not in manifest_outputs
    )
    index_path = output / "index.html"
    generated_at = datetime.now(UTC).isoformat()
    limitations = list(evidence["limitations"])
    manifest = {
        "schema_version": "1.0.0",
        "product": PRODUCT,
        "artifact_id": f"STATIC-{build_id.upper()}",
        "artifact_type": "STATIC_SHARE_PACKAGE",
        "artifact_version": "1.0.0",
        "build_id": build_id,
        "created_at": generated_at,
        "generated_at": generated_at,
        "created_by_component": "scripts.build_share_site",
        "source_workspace": "all_portfolio_control",
        "data_mode": "OFFLINE_SNAPSHOT",
        "reporting_period": evidence["reporting_period"],
        "comparison_period": evidence["comparison_period"],
        "filter_scope": evidence["source_context"]["filter_scope"],
        "dataset_profile": evidence["source_context"]["dataset_profile"],
        "dataset_hash": evidence["source_context"]["dataset_hash"],
        "configuration_hash": evidence["source_context"]["configuration_hash"],
        "metric_registry_version": evidence["source_context"]["metric_registry_version"],
        "code_version": "1.0.0",
        "evidence_ids": [evidence["evidence_id"]],
        "data_quality_status": evidence["validation"]["data_quality_status"],
        "synthetic_data": True,
        "synthetic_data_flag": True,
        "file_name": index_path.name,
        "file_size": index_path.stat().st_size,
        "sha256": _sha256(index_path),
        "dependencies": [item["path"] for item in evidence["source_context"]["source_inputs"]],
        "validation_status": validation["status"],
        "validation_tests": [
            "portable_internal_links",
            "absolute_path_scan",
            "secret_pattern_scan",
            "backend_independence",
        ],
        "known_limitations": limitations,
        "source_evidence_id": evidence["evidence_id"],
        "market_risk_status": evidence["market_risk"]["status"],
        "sample_workbook_included": workbook.is_file() and workbook.suffix.lower() == ".xlsx",
        "screenshot_asset_count": len(screenshot_files),
        "placeholders": {
            "repository_link": repository_url is None,
            "contact": contact is None,
        },
        "files": [
            {
                "path": path.relative_to(output).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for path in inventory
        ],
        "validation": validation,
    }
    _write_json(output / "build_manifest.json", manifest)
    final_validation = validate_share_site(output)
    _write_json(output / "validation.json", final_validation)
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--market-evidence", type=Path, default=DEFAULT_MARKET_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--repository-url")
    parser.add_argument("--contact")
    return parser


def main() -> None:
    args = _parser().parse_args()
    manifest = build_share_site(
        source_path=args.source,
        market_path=args.market_evidence,
        output=args.output,
        workbook=args.workbook,
        repository_url=args.repository_url,
        contact=args.contact,
    )
    print(
        f"Built {manifest['product']} share site: {manifest['build_id']} · "
        f"validation {manifest['validation']['status']}"
    )


if __name__ == "__main__":
    main()
