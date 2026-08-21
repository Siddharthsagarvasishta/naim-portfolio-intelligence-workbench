from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.benchmark_performance import (
    ALL_METRICS,
    EXTERNAL_EXECUTION_REQUIRED,
    MEASURED,
    SCHEMA_VERSION,
    aggregate_worker_samples,
    percentile_nearest_rank,
    validate_report,
)


def _worker_sample() -> dict:
    operations = {
        metric: {
            "status": MEASURED,
            "duration_ms": float(index + 1),
            "process_peak_rss_mib": 100.0 + index,
        }
        for index, metric in enumerate(ALL_METRICS)
    }
    return {
        "requested_profile": "fast",
        "resolved_profile": "test",
        "seed": 73421,
        "configuration_hash": "a" * 64,
        "dataset": {
            "account_month_rows": 2_312,
            "quality_status": "PASS",
        },
        "operations": operations,
    }


def test_nearest_rank_percentile_is_deterministic_for_small_samples() -> None:
    assert percentile_nearest_rank([5, 1, 3], 0.95) == 5
    assert percentile_nearest_rank([5, 1, 3], 0.5) == 3
    with pytest.raises(ValueError, match="At least one"):
        percentile_nearest_rank([], 0.95)


def test_aggregate_reports_median_p95_memory_and_external_limit() -> None:
    first = _worker_sample()
    second = deepcopy(first)
    third = deepcopy(first)
    first["operations"]["data_generation"]["duration_ms"] = 10.0
    second["operations"]["data_generation"]["duration_ms"] = 30.0
    third["operations"]["data_generation"]["duration_ms"] = 20.0
    for sample in (first, second, third):
        sample["operations"]["hyper_generation"] = {
            "status": EXTERNAL_EXECUTION_REQUIRED,
            "reason": "Local socket blocked",
            "rerun_requirement": "Run outside the restricted sandbox.",
        }

    aggregated = aggregate_worker_samples([first, second, third])

    generation = aggregated["operations"]["data_generation"]
    assert generation["repetitions"] == 3
    assert generation["timing_ms"]["median"] == 20.0
    assert generation["timing_ms"]["p95"] == 30.0
    assert len(generation["process_peak_rss_mib"]["samples"]) == 3
    hyper = aggregated["operations"]["hyper_generation"]
    assert hyper["status"] == EXTERNAL_EXECUTION_REQUIRED
    assert hyper["reason"] == "Local socket blocked"
    assert hyper["rerun_requirement"]


def test_report_validator_enforces_complete_metric_schema_and_reasons() -> None:
    profile = aggregate_worker_samples([_worker_sample()])
    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": "2026-08-01T00:00:00+00:00",
        "machine": {"python": "3.12.13", "platform": "test-machine"},
        "profiles": {"fast": profile},
    }
    assert validate_report(report) == []

    del report["profiles"]["fast"]["operations"]["vintage_response"]
    errors = validate_report(report)
    assert any("missing operations" in error for error in errors)

    report["profiles"]["fast"]["operations"]["vintage_response"] = {
        "status": EXTERNAL_EXECUTION_REQUIRED
    }
    errors = validate_report(report)
    assert any("unmeasured result has no reason" in error for error in errors)


def test_aggregate_rejects_changed_deterministic_dataset_controls() -> None:
    first = _worker_sample()
    second = deepcopy(first)
    second["dataset"]["account_month_rows"] += 1
    with pytest.raises(ValueError, match="dataset controls changed"):
        aggregate_worker_samples([first, second])
