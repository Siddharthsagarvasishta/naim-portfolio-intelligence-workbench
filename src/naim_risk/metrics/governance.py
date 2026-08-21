"""Governed metric lineage, status evaluation, and runtime evidence bindings."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any

from naim_risk.runtime_modes import DataMode, SourceContext


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _context_payload(context: SourceContext | Mapping[str, Any] | None) -> dict[str, Any]:
    if isinstance(context, SourceContext):
        return context.public()
    return dict(context or {})


def _operator_matches(operator: str, observed: float, threshold: float | None) -> bool:
    if threshold is None:
        return False
    if operator == "gt":
        return observed > threshold
    if operator == "gte":
        return observed >= threshold
    if operator == "lt":
        return observed < threshold
    if operator == "lte":
        return observed <= threshold
    if operator == "absolute_lte":
        return abs(observed) <= abs(threshold)
    raise ValueError(f"Unsupported governed threshold operator: {operator}")


def governed_metric_fields(
    metadata: Mapping[str, Any],
    *,
    value: float | None,
    absolute_change: float | None,
    denominator: float,
) -> dict[str, Any]:
    """Evaluate configured lineage, adequacy, materiality, and guardrail contracts."""

    required = {
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
    missing = sorted(required - metadata.keys())
    if missing:
        raise ValueError(
            f"Metric {metadata.get('metric_id', '<unknown>')} is missing governed fields: "
            + ", ".join(missing)
        )

    adequacy_rule = dict(metadata["adequacy_rule"])
    minimum_required = float(adequacy_rule["minimum_sample"])
    adequate = denominator >= minimum_required
    sample_adequacy = {
        "status": (
            str(adequacy_rule["status_when_met"])
            if adequate
            else str(adequacy_rule["status_when_unmet"])
        ),
        "observed_denominator": float(denominator),
        "minimum_required": minimum_required,
        "denominator_rule": str(adequacy_rule["denominator_rule"]),
    }

    statistical_rule = dict(metadata["statistical_rule"])
    statistical_assessment = {
        "inference_performed": bool(statistical_rule["inference_performed"]),
        "status": str(statistical_rule["status"]),
        "method": str(statistical_rule["method"]),
        "explanation": (
            "Minimum-sample adequacy is a data sufficiency check; no confidence interval, "
            "hypothesis test, or causal inference was run for this KPI response."
        ),
    }

    materiality_rule = dict(metadata["practical_materiality_rule"])
    materiality_threshold = float(materiality_rule["threshold"])
    if absolute_change is None:
        materiality_status = "NOT_ASSESSABLE"
    elif abs(float(absolute_change)) >= materiality_threshold:
        materiality_status = str(materiality_rule["status_when_material"])
    else:
        materiality_status = str(materiality_rule["status_when_immaterial"])
    practical_materiality = {
        "status": materiality_status,
        "observed_absolute_change": (
            None if absolute_change is None else abs(float(absolute_change))
        ),
        "threshold": materiality_threshold,
        "unit": str(materiality_rule["unit"]),
    }

    guardrail_rule = dict(metadata["guardrail_rule"])
    threshold_applied: dict[str, Any] | None = None
    if not adequate or value is None or absolute_change is None:
        guardrail_status = "INSUFFICIENT_DATA"
    else:
        observed_change = float(absolute_change)
        guardrail_status = "NEUTRAL"
        for raw_threshold in guardrail_rule["thresholds"]:
            threshold = dict(raw_threshold)
            if _operator_matches(
                str(threshold["operator"]),
                observed_change,
                None if threshold.get("value") is None else float(threshold["value"]),
            ):
                guardrail_status = str(threshold["status"])
                threshold_applied = threshold
                break
    if guardrail_status == "INSUFFICIENT_DATA":
        explanation = (
            f"{metadata['name']} has insufficient governed comparison evidence: "
            f"denominator {denominator:g}, minimum {minimum_required:g}, "
            f"comparison change {absolute_change!r}."
        )
    else:
        explanation = str(guardrail_rule["explanation_template"]).format(
            metric_name=metadata["name"],
            status=guardrail_status,
            observed_value=value,
            observed_change=absolute_change,
            threshold=(threshold_applied or {}).get("value"),
            unit=metadata["unit"],
        )
    guardrail = {
        "rule_id": str(guardrail_rule["rule_id"]),
        "rule_version": str(guardrail_rule["rule_version"]),
        "status": guardrail_status,
        "observed_value": value,
        "observed_change": absolute_change,
        "threshold_applied": threshold_applied,
        "denominator_rule": str(guardrail_rule["denominator_rule"]),
        "directionality": str(guardrail_rule["directionality"]),
        "explanation": explanation,
    }

    lineage = {
        "source": str(metadata["source"]),
        "source_fields": list(metadata["source_fields"]),
        "source_grain": str(metadata["source_grain"]),
        "supporting_sources": [dict(item) for item in metadata["supporting_sources"]],
        "transformation": dict(metadata["transformation"]),
        "refresh_facts": dict(metadata["refresh_facts"]),
    }
    return {
        "source": lineage["source"],
        "source_fields": lineage["source_fields"],
        "source_grain": lineage["source_grain"],
        "lineage": lineage,
        "guardrail": guardrail,
        "sample_adequacy": sample_adequacy,
        "statistical_assessment": statistical_assessment,
        "practical_materiality": practical_materiality,
        "interpretation_boundary": dict(metadata["interpretation_boundary"]),
        "reconciliation": {
            "status": "NOT_RUN",
            "scope": "cross_artifact",
            "checked_at": None,
            "detail": (
                "This API response was calculated from governed source tables; no "
                "cross-artifact reconciliation was executed for this request."
            ),
        },
    }


def bind_runtime_evidence(
    rows: Iterable[Mapping[str, Any]],
    *,
    context: SourceContext | Mapping[str, Any] | None,
    manifest: Mapping[str, Any],
    configuration_hash: str,
    run_id: str,
    filters: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """Bind every KPI row to deterministic dataset, configuration, and run facts."""

    context_data = _context_payload(context)
    portable_manifest = {
        key: manifest.get(key)
        for key in (
            "run_id",
            "configuration_hash",
            "row_counts",
            "mart_row_counts",
            "minimum_data_date",
            "maximum_data_date",
            "validation_status",
            "publication_allowed",
            "synthetic_data",
        )
    }
    context_configuration_hash = context_data.get("configuration_hash")
    context_run_id = context_data.get("run_id")
    if context_configuration_hash and str(context_configuration_hash) != configuration_hash:
        raise ValueError(
            "Runtime evidence context configuration_hash does not match the analytical run"
        )
    if context_run_id and str(context_run_id) != run_id:
        raise ValueError("Runtime evidence context run_id does not match the analytical run")
    dataset_hash = str(
        context_data.get("dataset_hash") or _canonical_hash(portable_manifest)
    )
    dataset_hash_basis = str(
        context_data.get("dataset_hash_basis") or "portable-run-manifest"
    )
    bound_configuration_hash = configuration_hash
    bound_run_id = run_id
    refreshed_at = str(
        manifest.get("completion_timestamp")
        or manifest.get("generation_timestamp")
        or f"{manifest.get('maximum_data_date')}T00:00:00+00:00"
    )
    filter_scope = dict(filters or {})
    output: list[dict[str, Any]] = []
    for raw_row in rows:
        row = dict(raw_row)
        binding = {
            "metric_id": row.get("metric_id"),
            "metric_version": row.get("metric_version"),
            "calculation_version": row.get("calculation_version"),
            "dataset_hash": dataset_hash,
            "dataset_hash_basis": dataset_hash_basis,
            "configuration_hash": bound_configuration_hash,
            "run_id": bound_run_id,
            "reporting_period": row.get("reporting_period"),
            "comparison_period": row.get("comparison_period"),
            "filter_scope": filter_scope,
            "value": row.get("value"),
            "prior_value": row.get("prior_value"),
            "denominator": row.get("denominator"),
        }
        binding_hash = _canonical_hash(binding)
        row["runtime_evidence"] = {
            "evidence_id": f"KPI-EVIDENCE-{binding_hash[:20].upper()}",
            "dataset_hash": dataset_hash,
            "dataset_hash_basis": dataset_hash_basis,
            "configuration_hash": bound_configuration_hash,
            "run_id": bound_run_id,
            "binding_sha256": binding_hash,
            "reporting_period": row.get("reporting_period"),
            "comparison_period": row.get("comparison_period"),
            "refreshed_at": refreshed_at,
        }
        output.append(row)
    return output


def data_source_diagnostics(
    *,
    context: SourceContext | Mapping[str, Any],
    manifest: Mapping[str, Any],
    stale_after_seconds: int,
    current_governed_configuration_hash: str | None = None,
    observed_at: datetime | None = None,
) -> dict[str, Any]:
    """Return server-observable snapshot facts without claiming client request history."""

    if stale_after_seconds <= 0:
        raise ValueError("Snapshot stale threshold must be positive")
    context_data = _context_payload(context)
    now = observed_at or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    active_mode = str(context_data.get("active_mode") or DataMode.UNAVAILABLE.value)
    created_at_raw = (
        None
        if active_mode == DataMode.DEMO.value
        else manifest.get("completion_timestamp") or manifest.get("generation_timestamp")
    )
    created_at: datetime | None = None
    if created_at_raw:
        try:
            created_at = datetime.fromisoformat(str(created_at_raw).replace("Z", "+00:00"))
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)
        except ValueError:
            created_at = None
    age_seconds = (
        None if created_at is None else max(0.0, (now - created_at).total_seconds())
    )
    if age_seconds is None:
        freshness_status = "UNKNOWN"
    elif age_seconds > stale_after_seconds:
        freshness_status = "STALE"
    else:
        freshness_status = "CURRENT"
    if active_mode == DataMode.UNAVAILABLE.value:
        diagnostic_status = "UNAVAILABLE"
    elif freshness_status == "STALE":
        diagnostic_status = "STALE"
    elif freshness_status == "UNKNOWN":
        diagnostic_status = "UNKNOWN"
    else:
        diagnostic_status = "CURRENT"
    portable_manifest = {
        key: manifest.get(key)
        for key in (
            "run_id",
            "configuration_hash",
            "row_counts",
            "mart_row_counts",
            "minimum_data_date",
            "maximum_data_date",
            "validation_status",
            "publication_allowed",
            "synthetic_data",
        )
    }
    dataset_hash = context_data.get("dataset_hash") or _canonical_hash(portable_manifest)
    dataset_hash_basis = context_data.get("dataset_hash_basis") or "portable-run-manifest"
    snapshot_configuration_hash = (
        context_data.get("configuration_hash") or manifest.get("configuration_hash")
    )
    configuration_match = (
        None
        if not snapshot_configuration_hash or not current_governed_configuration_hash
        else str(snapshot_configuration_hash) == current_governed_configuration_hash
    )
    return {
        "diagnostic_status": diagnostic_status,
        "server_observed_at": now.isoformat(),
        "active_mode": active_mode,
        "configured_mode": str(
            context_data.get("configured_mode") or DataMode.UNAVAILABLE.value
        ),
        "snapshot": {
            "created_at": None if created_at is None else created_at.isoformat(),
            "maximum_data_date": manifest.get("maximum_data_date"),
            "age_seconds": age_seconds,
            "stale_after_seconds": int(stale_after_seconds),
            "freshness_status": freshness_status,
        },
        "provenance": {
            "dataset_hash": dataset_hash,
            "dataset_hash_basis": dataset_hash_basis,
            "configuration_hash": snapshot_configuration_hash,
            "current_governed_configuration_hash": current_governed_configuration_hash,
            "configuration_match": configuration_match,
            "run_id": context_data.get("run_id") or manifest.get("run_id"),
        },
    }
