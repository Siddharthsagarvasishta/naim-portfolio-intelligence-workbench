"""Deterministic alert evaluation and governed cross-run condition identity."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _normalise_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _normalise_value(nested)
            for key, nested in sorted(value.items(), key=lambda item: str(item[0]))
            if nested is not None and nested != [] and nested != {}
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        normalised = [_normalise_value(item) for item in value]
        return sorted(normalised, key=_canonical_json)
    if isinstance(value, str):
        return value.strip()
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def normalise_selected_scope(scope: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return order-independent selected filters for condition identity."""

    normalised = _normalise_value(dict(scope or {}))
    return dict(normalised) if isinstance(normalised, Mapping) else {}


def alert_fingerprint(
    *,
    alert_rule_id: str,
    metric_id: str,
    selected_scope: Mapping[str, Any] | None,
    segment_or_basket: str,
    comparison_method: str,
) -> tuple[str, str]:
    """Return full condition fingerprint and stable ALERT identifier.

    Period, run, values, severity, and timestamps are deliberately excluded so the
    same governed condition survives recurrence across analytical runs.
    """

    payload = {
        "alert_rule_id": str(alert_rule_id),
        "metric_id": str(metric_id),
        "selected_scope": normalise_selected_scope(selected_scope),
        "segment_or_basket": str(segment_or_basket).strip(),
        "comparison_method": str(comparison_method),
    }
    fingerprint = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return fingerprint, f"ALERT-{fingerprint[:20].upper()}"


def _governed_severity(raw: Any) -> str:
    value = str(raw or "Watch").strip()
    compatibility = {
        "critical": "Critical",
        "high": "Adverse",
        "adverse": "Adverse",
        "medium": "Watch",
        "watch": "Watch",
        "low": "Watch",
    }
    try:
        return compatibility[value.lower()]
    except KeyError as exc:
        raise ValueError(f"Unsupported governed alert severity: {value}") from exc


def build_alert_candidate(
    rule: Mapping[str, Any],
    *,
    current_value: float | None,
    baseline_value: float | None,
    denominator: float,
    period: str,
    comparison_period: str | None,
    quality_status: str,
    selected_scope: Mapping[str, Any] | None,
    rule_version: str,
    segment_or_basket: str = "Portfolio",
    recommended_investigation: Any = None,
) -> dict[str, Any]:
    """Build one governed breached-condition candidate with compatibility fields."""

    fingerprint, alert_id = alert_fingerprint(
        alert_rule_id=str(rule["alert_rule_id"]),
        metric_id=str(rule["metric_id"]),
        selected_scope=selected_scope,
        segment_or_basket=segment_or_basket,
        comparison_method=str(rule["comparison_method"]),
    )
    absolute_movement = (
        None
        if current_value is None or baseline_value is None
        else float(current_value) - float(baseline_value)
    )
    relative_movement = (
        None
        if absolute_movement is None or float(baseline_value) == 0
        else absolute_movement / abs(float(baseline_value))
    )
    normalised_scope = normalise_selected_scope(selected_scope)
    return {
        "alert_id": alert_id,
        "fingerprint": fingerprint,
        "alert_rule_id": str(rule["alert_rule_id"]),
        "alert_name": str(rule["alert_name"]),
        "metric_id": str(rule["metric_id"]),
        "comparison_method": str(rule["comparison_method"]),
        "current_value": current_value,
        "baseline_value": baseline_value,
        "absolute_movement": absolute_movement,
        "relative_movement": relative_movement,
        "threshold": rule.get("absolute_threshold", rule.get("relative_threshold")),
        "segment": segment_or_basket,
        "segment_or_basket": segment_or_basket,
        "selected_scope": normalised_scope,
        "denominator": float(denominator),
        "severity": _governed_severity(rule.get("severity")),
        "status": "NEW",
        "data_quality_status": quality_status,
        "generation_timestamp": period,
        "comparison_period": comparison_period,
        "rule_version": rule_version,
        "owner": rule.get("owner_role"),
        "recommended_investigation": (
            rule.get("recommended_investigation")
            if recommended_investigation is None
            else recommended_investigation
        ),
        "sla_hours": rule.get("sla_hours"),
        "cooldown_periods": int(rule.get("cooldown_period", 0)),
        "condition_active": True,
        "noise_controls": {
            "minimum_denominator": rule.get("minimum_denominator"),
            "consecutive_periods": rule.get("consecutive_periods"),
            "cooldown_period": int(rule.get("cooldown_period", 0)),
            "duplicate_suppression_key": fingerprint,
        },
    }


def generate_alerts(
    trends: Iterable[Mapping[str, Any]],
    rules: Iterable[Mapping[str, Any]],
    *,
    quality_status: str,
    completeness: float = 1.0,
    selected_scope: Mapping[str, Any] | None = None,
    rule_version: str = "1.0.0",
    reporting_period: str | None = None,
    reporting_comparison_period: str | None = None,
) -> list[dict[str, Any]]:
    """Evaluate governed early-warning rules against long-form KPI trends."""

    by_metric: dict[str, list[Mapping[str, Any]]] = {}
    for row in trends:
        by_metric.setdefault(str(row["metric_id"]), []).append(row)
    for rows in by_metric.values():
        rows.sort(key=lambda item: str(item["month"]))
    governed_periods = sorted(
        {str(row["month"]) for rows in by_metric.values() for row in rows}
    )
    alerts: list[dict[str, Any]] = []
    for rule in rules:
        metric_id = str(rule["metric_id"])
        rows = by_metric.get(metric_id, [])
        method = str(rule["comparison_method"])
        comparison_period: str | None = None
        if method == "data_quality":
            breached = quality_status == "BLOCKED" or completeness < float(
                rule.get("absolute_threshold", 1.0)
            )
            current_value = completeness
            baseline_value = 1.0
            period = reporting_period or (
                governed_periods[-1] if governed_periods else None
            )
            if period is None:
                raise ValueError(
                    "Data-quality alert evaluation requires a governed reporting period"
                )
            comparison_period = reporting_comparison_period or (
                governed_periods[-2] if len(governed_periods) > 1 else None
            )
            denominator = 1.0
        elif not rows:
            continue
        else:
            current = rows[-1]
            previous = rows[-2] if len(rows) > 1 else current
            current_value = current.get("value")
            baseline_value = previous.get("value")
            denominator = float(current.get("denominator") or 0)
            period = str(current["month"])
            comparison_period = str(previous["month"]) if len(rows) > 1 else None
            if current_value is None or denominator < float(rule.get("minimum_denominator", 0)):
                breached = False
            elif method == "absolute_threshold":
                breached = float(current_value) > float(rule["absolute_threshold"])
            elif method == "basis_point_movement":
                breached = baseline_value is not None and (
                    float(current_value) - float(baseline_value)
                ) * 10_000 > float(rule["relative_threshold"])
            elif method == "persistent_increase":
                required = int(rule.get("consecutive_periods", 2))
                relative_threshold = float(rule.get("relative_threshold", 0)) / 100
                recent = rows[-(required + 1) :]
                breached = len(recent) == required + 1 and all(
                    recent[index]["value"] is not None
                    and recent[index - 1]["value"] is not None
                    and float(recent[index]["value"]) > float(recent[index - 1]["value"])
                    and float(recent[index - 1]["value"]) != 0
                    and (float(recent[index]["value"]) - float(recent[index - 1]["value"]))
                    / abs(float(recent[index - 1]["value"]))
                    >= relative_threshold
                    for index in range(1, len(recent))
                )
            else:
                breached = False
        if breached:
            alerts.append(
                build_alert_candidate(
                    rule,
                    current_value=(
                        None if current_value is None else float(current_value)
                    ),
                    baseline_value=(
                        None if baseline_value is None else float(baseline_value)
                    ),
                    denominator=denominator,
                    period=period,
                    comparison_period=comparison_period,
                    quality_status=quality_status,
                    selected_scope=selected_scope,
                    rule_version=rule_version,
                )
            )
    return alerts
