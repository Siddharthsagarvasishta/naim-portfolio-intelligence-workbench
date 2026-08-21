"""Configuration loading for deterministic nAIM analytics."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CORE_METRIC_IDS = (
    "ACTIVE_ACCOUNTS",
    "ACCOUNT_GROWTH",
    "ENDING_RECEIVABLES",
    "TRANSACTION_VALUE",
    "UTILIZATION",
    "DELINQUENCY_30_ACCOUNT_RATE",
    "ANNUALISED_NET_LOSS_RATE",
    "FRAUD_BPS",
    "FRAUD_ALERT_TRANSACTION_RATE",
    "MANUAL_REVIEW_RATE",
    "FALSE_POSITIVE_RATE",
    "CUSTOMER_FRICTION_RATE",
    "COMPLAINT_RATE_PER_1000",
    "ATTRITION_RATE",
    "EXPECTED_PROFIT",
)

_REQUIRED_GOVERNANCE_FIELDS = {
    "source",
    "source_fields",
    "source_grain",
    "supporting_sources",
    "transformation",
    "refresh_facts",
    "interpretation_boundary",
    "adequacy_rule",
    "statistical_rule",
    "practical_materiality_rule",
    "guardrail_rule",
}
_PLACEHOLDER_SOURCE_VALUES = {"", "n/a", "na", "none", "null", "tbd", "unknown"}
_ALERT_SEVERITIES = {"Critical", "Adverse", "Watch"}
_ALERT_COMPARISON_METHODS = {
    "absolute_threshold",
    "basis_point_movement",
    "persistent_increase",
    "data_quality",
    "contribution_share_threshold",
}
_REQUIRED_ALERT_FIELDS = {
    "alert_rule_id",
    "metric_id",
    "alert_name",
    "comparison_method",
    "minimum_denominator",
    "consecutive_periods",
    "severity",
    "cooldown_period",
    "sla_hours",
    "owner_role",
    "recommended_investigation",
}

PACKAGE_ROOT = Path(__file__).resolve().parent
_SOURCE_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if (_SOURCE_REPOSITORY_ROOT / "config" / "dataset_profiles.json").is_file():
    REPOSITORY_ROOT = _SOURCE_REPOSITORY_ROOT
    CONFIG_ROOT = REPOSITORY_ROOT / "config"
    MODEL_ROOT = REPOSITORY_ROOT / "models"
else:
    # A wheel has no repository checkout. Use bundled governed defaults while
    # keeping generated data relative to the operator's current directory.
    REPOSITORY_ROOT = Path.cwd().resolve()
    CONFIG_ROOT = PACKAGE_ROOT / "resources" / "config"
    MODEL_ROOT = PACKAGE_ROOT / "resources" / "models"


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@dataclass(frozen=True)
class DatasetProfile:
    """Account count and observation window for one generation profile."""

    name: str
    accounts: int
    months: int
    description: str


@dataclass(frozen=True)
class NaimConfig:
    """Resolved immutable configuration used by a pipeline run."""

    profile: DatasetProfile
    seed: int
    start_month: str
    data_root: Path
    synthetic_label: str
    deterioration: Mapping[str, Any]
    scenarios: Mapping[str, Any]
    elasticities: Mapping[str, float]
    metrics: tuple[Mapping[str, Any], ...]
    alert_rules: tuple[Mapping[str, Any], ...]
    ratings: Mapping[str, Any]
    metric_registry_version: str
    metric_calculation_version: str
    assumption_version: str
    alert_rule_version: str
    config_hash: str


def _validate_metric_registry(registry: Mapping[str, Any]) -> None:
    """Fail closed when a core KPI lacks governed executable metadata."""

    metrics = [dict(item) for item in registry.get("metrics", [])]
    identifiers = [str(item.get("metric_id") or "") for item in metrics]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Metric registry contains duplicate metric IDs")
    missing_ids = sorted(set(CORE_METRIC_IDS) - set(identifiers))
    unexpected_ids = sorted(set(identifiers) - set(CORE_METRIC_IDS))
    if missing_ids or unexpected_ids:
        raise ValueError(
            "Metric registry must exactly cover the executable core KPI set; "
            f"missing={missing_ids}, unexpected={unexpected_ids}"
        )
    for metric in metrics:
        metric_id = str(metric["metric_id"])
        missing = sorted(_REQUIRED_GOVERNANCE_FIELDS - metric.keys())
        if missing:
            raise ValueError(
                f"Metric {metric_id} is missing governed registry fields: {', '.join(missing)}"
            )
        source = str(metric["source"]).strip().lower()
        if source in _PLACEHOLDER_SOURCE_VALUES:
            raise ValueError(f"Metric {metric_id} has a placeholder source")
        if not metric["source_fields"] or not str(metric["source_grain"]).strip():
            raise ValueError(f"Metric {metric_id} has incomplete source lineage")
        if any(
            str(field).strip().lower() in _PLACEHOLDER_SOURCE_VALUES
            for field in metric["source_fields"]
        ):
            raise ValueError(f"Metric {metric_id} has placeholder source fields")
        for supporting in metric["supporting_sources"]:
            supporting_source = dict(supporting)
            if not all(
                supporting_source.get(field)
                for field in ("source", "source_fields", "source_grain", "join_rule")
            ):
                raise ValueError(f"Metric {metric_id} has incomplete supporting lineage")
        transformation = dict(metric["transformation"])
        if not all(
            str(transformation.get(field) or "").strip()
            for field in ("module", "callable", "calculation_version")
        ):
            raise ValueError(f"Metric {metric_id} has incomplete transformation lineage")
        if transformation["calculation_version"] != registry.get("calculation_version"):
            raise ValueError(f"Metric {metric_id} calculation version is not registry-aligned")
        refresh_facts = dict(metric["refresh_facts"])
        if not all(
            refresh_facts.get(field)
            for field in (
                "cadence",
                "watermark_field",
                "runtime_watermark_source",
                "refresh_time_source",
                "publication_gate",
            )
        ):
            raise ValueError(f"Metric {metric_id} has incomplete refresh facts")
        interpretation = dict(metric["interpretation_boundary"])
        if not (
            isinstance(interpretation.get("can_conclude"), list)
            and interpretation["can_conclude"]
            and isinstance(interpretation.get("cannot_conclude"), list)
            and interpretation["cannot_conclude"]
            and isinstance(interpretation.get("caveats"), list)
            and interpretation["caveats"]
            and interpretation.get("permitted_next_action")
        ):
            raise ValueError(f"Metric {metric_id} has incomplete interpretation boundaries")
        statistical = dict(metric["statistical_rule"])
        if statistical.get("inference_performed") is not False or statistical.get(
            "status"
        ) != "NOT_RUN" or statistical.get("method") != "descriptive_only":
            raise ValueError(f"Metric {metric_id} overclaims statistical evidence")
        guardrail = dict(metric["guardrail_rule"])
        if guardrail.get("directionality") != interpretation.get("directionality"):
            raise ValueError(f"Metric {metric_id} has conflicting directionality contracts")
        statuses = {str(item.get("status")) for item in guardrail.get("thresholds", [])}
        if statuses != {"CRITICAL", "ADVERSE", "WATCH", "FAVOURABLE", "NEUTRAL"}:
            raise ValueError(f"Metric {metric_id} has an incomplete guardrail hierarchy")


def _validate_alert_rules(alerts: Mapping[str, Any]) -> None:
    """Fail closed when alert lifecycle or threshold governance is incomplete."""

    version = str(alerts.get("rule_version") or "").strip()
    if not version:
        raise ValueError("Alert rules require a rule_version")
    rules = [dict(item) for item in alerts.get("rules", [])]
    identifiers = [str(item.get("alert_rule_id") or "") for item in rules]
    if not rules or len(identifiers) != len(set(identifiers)) or any(not item for item in identifiers):
        raise ValueError("Alert rules must contain unique, non-empty identifiers")
    for rule in rules:
        rule_id = str(rule["alert_rule_id"])
        missing = sorted(_REQUIRED_ALERT_FIELDS - rule.keys())
        if missing:
            raise ValueError(
                f"Alert rule {rule_id} is missing governed fields: {', '.join(missing)}"
            )
        method = str(rule["comparison_method"])
        if method not in _ALERT_COMPARISON_METHODS:
            raise ValueError(f"Alert rule {rule_id} has unsupported comparison method")
        if rule["severity"] not in _ALERT_SEVERITIES:
            raise ValueError(f"Alert rule {rule_id} has unsupported severity")
        if int(rule["sla_hours"]) <= 0:
            raise ValueError(f"Alert rule {rule_id} requires a positive SLA")
        if int(rule["cooldown_period"]) < 0:
            raise ValueError(f"Alert rule {rule_id} has a negative cooldown")
        threshold_field = (
            "relative_threshold"
            if method in {"basis_point_movement", "persistent_increase"}
            else "absolute_threshold"
        )
        if threshold_field not in rule:
            raise ValueError(f"Alert rule {rule_id} has no governed threshold")


def load_config(
    profile: str = "default",
    *,
    seed: int | None = None,
    data_root: str | Path | None = None,
) -> NaimConfig:
    """Load governed JSON configuration and calculate an audit hash."""

    dataset_config = _read_json(CONFIG_ROOT / "dataset_profiles.json")
    profile_config = dataset_config["dataset_profiles"].get(profile)
    if profile_config is None:
        valid = ", ".join(sorted(dataset_config["dataset_profiles"]))
        raise ValueError(f"Unknown profile {profile!r}; choose one of: {valid}")
    scenarios = _read_json(CONFIG_ROOT / "economic_scenarios.json")
    metric_registry = _read_json(CONFIG_ROOT / "metric_registry.json")
    _validate_metric_registry(metric_registry)
    alerts = _read_json(CONFIG_ROOT / "alert_rules.json")
    _validate_alert_rules(alerts)
    ratings = _read_json(CONFIG_ROOT / "rating_methodologies.json")
    resolved_seed = int(dataset_config["default_seed"] if seed is None else seed)
    hash_payload = {
        "profile": profile,
        "profile_config": profile_config,
        "seed": resolved_seed,
        "start_month": dataset_config["start_month"],
        "deterioration": dataset_config["deterioration"],
        "scenario_version": scenarios["assumption_version"],
        "metric_version": metric_registry["registry_version"],
        "alert_version": alerts["rule_version"],
        "rating_version": ratings["methodology_version"],
    }
    config_hash = hashlib.sha256(
        json.dumps(hash_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    root = Path(data_root) if data_root is not None else REPOSITORY_ROOT / "data"
    return NaimConfig(
        profile=DatasetProfile(
            name=profile,
            accounts=int(profile_config["accounts"]),
            months=int(profile_config["months"]),
            description=str(profile_config["description"]),
        ),
        seed=resolved_seed,
        start_month=str(dataset_config["start_month"]),
        data_root=root,
        synthetic_label=str(dataset_config["synthetic_label"]),
        deterioration=dict(dataset_config["deterioration"]),
        scenarios=dict(scenarios["scenarios"]),
        elasticities=dict(scenarios["elasticities"]),
        metrics=tuple(metric_registry["metrics"]),
        alert_rules=tuple(alerts["rules"]),
        ratings=ratings,
        metric_registry_version=str(metric_registry["registry_version"]),
        metric_calculation_version=str(metric_registry["calculation_version"]),
        assumption_version=str(scenarios["assumption_version"]),
        alert_rule_version=str(alerts["rule_version"]),
        config_hash=config_hash,
    )


def metric_lookup(config: NaimConfig) -> dict[str, Mapping[str, Any]]:
    """Return metric metadata keyed by governed metric ID."""

    return {str(item["metric_id"]): item for item in config.metrics}


_DISPLAY_CONTRACT_BY_UNIT: dict[str, dict[str, Any]] = {
    "accounts": {
        "scale": "whole_count",
        "scaling_factor": 1.0,
        "format_string": "#,##0",
    },
    "annualised_rate": {
        "scale": "fraction",
        "scaling_factor": 100.0,
        "format_string": "0.00%",
    },
    "basis_points": {
        "scale": "basis_points",
        "scaling_factor": 1.0,
        "format_string": '#,##0.0 "bps"',
    },
    "currency": {
        "scale": "adaptive_currency",
        "scaling_factor": 1.0,
        "format_string": "$0.0a;[Red]($0.0a)",
        "currency_code": "USD",
        "currency_symbol": "$",
    },
    "per_1000": {
        "scale": "per_1000_accounts",
        "scaling_factor": 1.0,
        "format_string": '#,##0.0 "per 1,000"',
    },
    "rate": {
        "scale": "fraction",
        "scaling_factor": 100.0,
        "format_string": "0.00%",
    },
}


def metric_display_contract(metric: Mapping[str, Any]) -> dict[str, Any]:
    """Derive one explicit display contract from a governed metric unit.

    The calculation registry remains authoritative for metric meaning.  This
    function only makes the already-implied storage scale and display format
    explicit, so the API and all clients can use the same formatter.
    """

    unit = str(metric.get("unit") or "")
    try:
        display = _DISPLAY_CONTRACT_BY_UNIT[unit]
    except KeyError as exc:
        raise ValueError(f"Unsupported governed metric unit: {unit or '<missing>'}") from exc
    return {
        **dict(metric),
        "unit": unit,
        "scale": display["scale"],
        "scaling_factor": display["scaling_factor"],
        "format_string": display["format_string"],
        **(
            {
                "currency_code": display["currency_code"],
                "currency_symbol": display["currency_symbol"],
            }
            if unit == "currency"
            else {}
        ),
    }


def format_metric_value(
    value: Any,
    unit: str,
    *,
    signed: bool = False,
) -> str:
    """Format a governed metric value from the same unit contract exposed by the API."""

    if value is None:
        return "N/A"
    numeric = float(value)
    sign = "+" if signed and numeric > 0 else ""
    if unit in {"rate", "annualised_rate"}:
        return f"{sign}{numeric:.2%}"
    if unit == "basis_points":
        return f"{sign}{numeric:,.1f} bps"
    if unit == "per_1000":
        return f"{sign}{numeric:,.1f} per 1,000"
    if unit == "accounts":
        return f"{sign}{numeric:,.0f} accounts"
    if unit == "currency":
        magnitude = abs(numeric)
        if magnitude >= 1_000_000_000:
            return f"{sign}${numeric / 1_000_000_000:,.1f}bn"
        if magnitude >= 1_000_000:
            return f"{sign}${numeric / 1_000_000:,.1f}m"
        if magnitude >= 1_000:
            return f"{sign}${numeric / 1_000:,.1f}k"
        return f"{sign}${numeric:,.0f}"
    raise ValueError(f"Unsupported governed metric unit: {unit}")
