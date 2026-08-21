#!/usr/bin/env python3
"""Reproducible scale benchmark for the nAIM analytical workbench.

Each timing sample runs in a fresh Python process.  This avoids warmed global
state leaking between repetitions and makes the recorded process memory
high-water mark comparable across samples.  The analytical response timings
include strict JSON serialisation but exclude HTTP transport and middleware.
"""

from __future__ import annotations

import argparse
import gc
import importlib.metadata
import json
import math
import os
import platform
import resource
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from naim_risk.config import REPOSITORY_ROOT, NaimConfig, load_config
from naim_risk.data_generation import generate_synthetic_portfolio
from naim_risk.exports import generate_excel_export
from naim_risk.presentations import DEFAULT_SECTIONS, generate_presentation
from naim_risk.runtime_modes import DataMode, SourceContext
from naim_risk.segmentation import statistical_segments
from naim_risk.service import WorkbenchService
from naim_risk.tableau import generate_hyper_extract
from naim_risk.transformations import build_marts
from naim_risk.types import PipelineData, ValidationResult
from naim_risk.validation import validate_tables

SCHEMA_VERSION = "1.0.0"
HARNESS_VERSION = "1.0.0"
PROFILE_ALIASES = {"fast": "test"}
DEFAULT_PROFILES = ("fast", "default", "medium")
PIPELINE_METRICS = (
    "data_generation",
    "validation",
    "mart_build",
    "model_training",
)
RESPONSE_METRICS = (
    "command_centre_response",
    "root_cause_response",
    "vintage_response",
    "basket_comparison",
    "scenario_run",
    "presentation_generation",
    "excel_generation",
    "hyper_generation",
)
ALL_METRICS = PIPELINE_METRICS + RESPONSE_METRICS
MEASURED = "MEASURED"
SKIPPED = "SKIPPED"
EXTERNAL_EXECUTION_REQUIRED = "EXTERNAL_EXECUTION_REQUIRED"


def _iso_slug(timestamp: datetime) -> str:
    return timestamp.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _peak_rss_mib() -> float:
    """Return the process peak resident set in MiB on macOS or Linux."""

    raw = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    bytes_used = raw if sys.platform == "darwin" else raw * 1024.0
    return bytes_used / (1024.0 * 1024.0)


def _physical_memory_mib() -> float | None:
    try:
        pages = int(os.sysconf("SC_PHYS_PAGES"))
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
    except (AttributeError, OSError, TypeError, ValueError):
        return None
    return round((pages * page_size) / (1024.0 * 1024.0), 3)


def machine_details() -> dict[str, Any]:
    packages = {}
    for package in ("numpy", "pandas", "scikit-learn", "openpyxl", "python-pptx"):
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = None
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or None,
        "logical_cpu_count": os.cpu_count(),
        "physical_memory_mib": _physical_memory_mib(),
        "packages": packages,
        "thread_environment": {
            key: os.environ.get(key)
            for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
            if os.environ.get(key) is not None
        },
    }


def _dataframe_mib(frames: dict[str, pd.DataFrame]) -> float:
    total = sum(int(frame.memory_usage(index=True, deep=True).sum()) for frame in frames.values())
    return total / (1024.0 * 1024.0)


def _timed(operation: Callable[[], Any]) -> tuple[Any, dict[str, float]]:
    gc.collect()
    started = time.perf_counter_ns()
    value = operation()
    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000.0
    return value, {
        "duration_ms": round(elapsed_ms, 6),
        "process_peak_rss_mib": round(_peak_rss_mib(), 6),
    }


def _json_response(operation: Callable[[], Any]) -> bytes:
    value = operation()
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _pipeline_data(
    config: NaimConfig,
    validation: ValidationResult,
    marts: dict[str, pd.DataFrame],
) -> PipelineData:
    performance = validation.accepted["monthly_account_performance"]
    row_counts = {
        name: int(len(frame))
        for name, frame in validation.accepted.items()
        if not name.startswith("_")
    }
    manifest = {
        "run_id": f"benchmark-{config.profile.name}-{config.seed}-{config.config_hash[:12]}",
        "random_seed": config.seed,
        "profile": config.profile.name,
        "configuration_hash": config.config_hash,
        "synthetic_data": True,
        "synthetic_label": config.synthetic_label,
        "row_counts": row_counts,
        "mart_row_counts": {name: int(len(frame)) for name, frame in marts.items()},
        "minimum_data_date": str(pd.Timestamp(performance["month"].min()).date()),
        "maximum_data_date": str(pd.Timestamp(performance["month"].max()).date()),
        "validation_status": validation.status,
        "publication_allowed": validation.publication_allowed,
        "quality_score": validation.quality_score,
        "rejected_row_counts": {
            name: int(len(frame)) for name, frame in validation.quarantined.items()
        },
        "storage_engine": "in-memory benchmark",
        "paths": {},
    }
    return PipelineData(
        run_id=str(manifest["run_id"]),
        tables=validation.accepted,
        marts=marts,
        manifest=manifest,
        validation=validation,
    )


def _bounded_model_input(performance: pd.DataFrame, account_limit: int = 2_000) -> pd.DataFrame:
    """Bound exact silhouette diagnostics to a deterministic operational sample."""

    account_ids = sorted(performance["account_id"].astype(str).unique())[:account_limit]
    return performance[performance["account_id"].astype(str).isin(account_ids)].copy()


def _source_context(service: WorkbenchService) -> SourceContext:
    return SourceContext(
        active_mode=DataMode.DEMO,
        configured_mode=DataMode.DEMO,
        snapshot_date=service.metadata()["as_of"],
        configuration_hash=service.config.config_hash,
        dataset_hash=service.config.config_hash,
        dataset_hash_basis="benchmark-configuration-hash",
        run_id=service.data.run_id,
        synthetic=True,
        reason="Isolated deterministic benchmark process.",
    )


def _measure_hyper(
    service: WorkbenchService,
    output_root: Path,
    hyper_mode: str,
) -> dict[str, Any]:
    if hyper_mode == "skip":
        return {
            "status": SKIPPED,
            "reason": "Hyper was explicitly skipped for this run.",
        }
    target = output_root / "benchmark.hyper"
    try:
        result, measurement = _timed(
            lambda: generate_hyper_extract(service, output_path=target)
        )
    except Exception as exc:  # the Hyper engine can be blocked by a local socket sandbox
        failure = {
            "status": EXTERNAL_EXECUTION_REQUIRED,
            "reason": f"{type(exc).__name__}: {str(exc)[:500]}",
            "rerun_requirement": (
                "Run the same harness with --hyper required in an environment that permits "
                "the Tableau Hyper local process and Unix-domain socket."
            ),
        }
        if hyper_mode == "required":
            raise RuntimeError(failure["reason"]) from exc
        return failure
    return {
        "status": MEASURED,
        **measurement,
        "output_bytes": int(target.stat().st_size),
        "validation_status": result["status"],
    }


def run_worker(requested_profile: str, hyper_mode: str) -> dict[str, Any]:
    resolved_profile = PROFILE_ALIASES.get(requested_profile, requested_profile)
    with tempfile.TemporaryDirectory(prefix=f"naim-benchmark-{requested_profile}-") as temporary:
        temporary_root = Path(temporary)
        config = load_config(resolved_profile, data_root=temporary_root / "data")
        operations: dict[str, dict[str, Any]] = {}

        raw_tables, operations["data_generation"] = _timed(
            lambda: generate_synthetic_portfolio(config)
        )
        ground_truth = raw_tables.pop("_ground_truth_deterioration")
        validation_input = {**raw_tables, "_ground_truth_deterioration": ground_truth}
        validation, operations["validation"] = _timed(
            lambda: validate_tables(validation_input)
        )
        if not validation.publication_allowed:
            raise RuntimeError("Benchmark dataset failed its publication gate")
        marts, operations["mart_build"] = _timed(
            lambda: build_marts(validation.accepted)
        )
        model_input = _bounded_model_input(
            validation.accepted["monthly_account_performance"]
        )
        model_result, operations["model_training"] = _timed(
            lambda: statistical_segments(
                model_input,
                seed=config.seed,
                candidate_clusters=(3, 4),
            )
        )
        operations["model_training"].update(
            {
                "training_accounts": int(model_input["account_id"].nunique()),
                "training_rows": int(len(model_input)),
                "model_status": model_result.get("status"),
                "workload_note": (
                    "Deterministic first-2,000-account cap; exact silhouette diagnostics "
                    "are quadratic in account count."
                ),
            }
        )

        pipeline_data = _pipeline_data(config, validation, marts)
        service = WorkbenchService(config, pipeline_data)

        # Prime only read-only analytical caches. Mutating and file-generation
        # operations remain unprimed and are measured exactly once per process.
        _json_response(service.command_centre)
        _json_response(service.root_cause)
        _json_response(service.vintages)
        partners = sorted(service.tables["partner_master"]["partner_id"].astype(str).tolist())
        split = max(1, len(partners) // 2)
        basket_payload = {
            "original_members": partners[:split],
            "revised_members": partners[max(0, split - 1) :],
        }
        _json_response(lambda: service.basket_impact(basket_payload))

        for name, operation in (
            ("command_centre_response", service.command_centre),
            ("root_cause_response", service.root_cause),
            ("vintage_response", service.vintages),
            ("basket_comparison", lambda: service.basket_impact(basket_payload)),
        ):
            payload, measurement = _timed(lambda operation=operation: _json_response(operation))
            operations[name] = {
                **measurement,
                "response_bytes": len(payload),
                "cache_state": "warmed_once",
                "transport_scope": "analytical call plus strict JSON serialisation",
            }

        scenario_payload = {
            "scenario_name": "Baseline",
            "horizon_months": 12,
            "reporting_month": service.metadata()["as_of"],
        }
        scenario_bytes, scenario_measurement = _timed(
            lambda: _json_response(lambda: service.scenario_run(scenario_payload))
        )
        operations["scenario_run"] = {
            **scenario_measurement,
            "response_bytes": len(scenario_bytes),
            "cache_state": "unprimed_persistent_workflow",
            "transport_scope": "analytical call plus strict JSON serialisation",
        }

        presentation_root = temporary_root / "presentations"
        presentation_payload = {
            "reporting_period": service.metadata()["as_of"],
            "selected_sections": list(DEFAULT_SECTIONS),
            "include_appendix": True,
            "speaker_notes": True,
        }
        presentation, presentation_measurement = _timed(
            lambda: generate_presentation(
                service,
                presentation_payload,
                store=service.workflow_store,
                source_context=_source_context(service),
                actor="performance.harness",
                output_root=presentation_root,
            )
        )
        presentation_path = presentation_root / presentation["filename"]
        operations["presentation_generation"] = {
            **presentation_measurement,
            "output_bytes": int(presentation_path.stat().st_size),
            "slide_count": int(presentation["slide_count"]),
            "validation_status": presentation["validation_status"],
        }

        excel_path, excel_measurement = _timed(lambda: generate_excel_export(service))
        operations["excel_generation"] = {
            **excel_measurement,
            "output_bytes": int(excel_path.stat().st_size),
            "sheet_count": 9,
        }
        operations["hyper_generation"] = _measure_hyper(
            service,
            temporary_root / "hyper",
            hyper_mode,
        )

        raw_row_counts = {name: int(len(frame)) for name, frame in raw_tables.items()}
        mart_row_counts = {name: int(len(frame)) for name, frame in marts.items()}
        for operation in operations.values():
            operation.setdefault("status", MEASURED)
        return {
            "requested_profile": requested_profile,
            "resolved_profile": resolved_profile,
            "seed": config.seed,
            "configuration_hash": config.config_hash,
            "dataset": {
                "configured_accounts": config.profile.accounts,
                "configured_months": config.profile.months,
                "account_month_rows": raw_row_counts["monthly_account_performance"],
                "raw_rows_total": sum(raw_row_counts.values()),
                "mart_rows_total": sum(mart_row_counts.values()),
                "raw_in_memory_mib": round(_dataframe_mib(raw_tables), 6),
                "mart_in_memory_mib": round(_dataframe_mib(marts), 6),
                "raw_row_counts": raw_row_counts,
                "mart_row_counts": mart_row_counts,
                "quality_status": validation.status,
                "quality_score": validation.quality_score,
            },
            "operations": operations,
        }


def percentile_nearest_rank(values: list[float], percentile: float) -> float:
    if not values:
        raise ValueError("At least one value is required")
    if not 0 < percentile <= 1:
        raise ValueError("Percentile must be in (0, 1]")
    ordered = sorted(float(value) for value in values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def _summarise(values: list[float]) -> dict[str, Any]:
    return {
        "median": round(statistics.median(values), 6),
        "p95": round(percentile_nearest_rank(values, 0.95), 6),
        "minimum": round(min(values), 6),
        "maximum": round(max(values), 6),
        "samples": [round(value, 6) for value in values],
    }


def aggregate_worker_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    if not samples:
        raise ValueError("At least one worker sample is required")
    identity = samples[0]
    for sample in samples[1:]:
        if sample["requested_profile"] != identity["requested_profile"]:
            raise ValueError("Worker samples have different requested profiles")
        if sample["configuration_hash"] != identity["configuration_hash"]:
            raise ValueError("Worker samples have different configuration hashes")
        if sample["dataset"] != identity["dataset"]:
            raise ValueError("Deterministic dataset controls changed between repetitions")

    operations: dict[str, Any] = {}
    for metric in ALL_METRICS:
        rows = [sample["operations"][metric] for sample in samples]
        statuses = {row["status"] for row in rows}
        if statuses == {MEASURED}:
            timings = [float(row["duration_ms"]) for row in rows]
            memory = [float(row["process_peak_rss_mib"]) for row in rows]
            detail_keys = sorted(
                set.intersection(*(set(row) for row in rows))
                - {"status", "duration_ms", "process_peak_rss_mib"}
            )
            stable_details = {
                key: rows[0][key]
                for key in detail_keys
                if all(row[key] == rows[0][key] for row in rows[1:])
            }
            operations[metric] = {
                "status": MEASURED,
                "repetitions": len(rows),
                "timing_ms": _summarise(timings),
                "process_peak_rss_mib": {
                    **_summarise(memory),
                    "interpretation": (
                        "Whole-process high-water mark observed by completion of the operation; "
                        "it is not incremental memory attributable only to this operation."
                    ),
                },
                **stable_details,
            }
        else:
            reasons = sorted({str(row.get("reason", "unspecified")) for row in rows})
            status = (
                EXTERNAL_EXECUTION_REQUIRED
                if EXTERNAL_EXECUTION_REQUIRED in statuses
                else SKIPPED
            )
            operations[metric] = {
                "status": status,
                "repetitions": len(rows),
                "reason": " | ".join(reasons),
            }
            rerun = next((row.get("rerun_requirement") for row in rows if row.get("rerun_requirement")), None)
            if rerun:
                operations[metric]["rerun_requirement"] = rerun
    return {
        "status": "MEASURED",
        "requested_profile": identity["requested_profile"],
        "resolved_profile": identity["resolved_profile"],
        "seed": identity["seed"],
        "configuration_hash": identity["configuration_hash"],
        "dataset": identity["dataset"],
        "operations": operations,
    }


def validate_report(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if report.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version is not supported")
    if not report.get("generated_at_utc"):
        errors.append("generated_at_utc is missing")
    machine = report.get("machine")
    if not isinstance(machine, dict) or not machine.get("python") or not machine.get("platform"):
        errors.append("machine details are incomplete")
    profiles = report.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        errors.append("profiles are missing")
        return errors
    for profile_name, profile in profiles.items():
        if profile.get("status") != "MEASURED":
            errors.append(f"{profile_name}: profile was not measured")
            continue
        dataset = profile.get("dataset", {})
        if int(dataset.get("account_month_rows", 0)) <= 0:
            errors.append(f"{profile_name}: dataset size is missing")
        operations = profile.get("operations", {})
        missing = sorted(set(ALL_METRICS).difference(operations))
        if missing:
            errors.append(f"{profile_name}: missing operations {missing}")
        for metric, result in operations.items():
            if result.get("status") != MEASURED:
                if not result.get("reason"):
                    errors.append(f"{profile_name}/{metric}: unmeasured result has no reason")
                continue
            repetitions = int(result.get("repetitions", 0))
            timing = result.get("timing_ms", {})
            memory = result.get("process_peak_rss_mib", {})
            if repetitions <= 0 or len(timing.get("samples", [])) != repetitions:
                errors.append(f"{profile_name}/{metric}: timing sample count mismatch")
            if len(memory.get("samples", [])) != repetitions:
                errors.append(f"{profile_name}/{metric}: memory sample count mismatch")
            if float(timing.get("median", -1)) < 0:
                errors.append(f"{profile_name}/{metric}: invalid median")
            if float(timing.get("p95", -1)) < float(timing.get("median", 0)):
                errors.append(f"{profile_name}/{metric}: p95 is below median")
            if float(memory.get("median", 0)) <= 0:
                errors.append(f"{profile_name}/{metric}: invalid process memory")
    return errors


def _run_worker_process(
    profile: str,
    hyper_mode: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        "--profile",
        profile,
        "--hyper",
        hyper_mode,
    ]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        env={**os.environ, "PYTHONPATH": str(REPOSITORY_ROOT / "src")},
    )
    if completed.returncode != 0:
        stderr = completed.stderr.strip()[-2_000:]
        raise RuntimeError(
            f"Benchmark worker failed for {profile} with exit {completed.returncode}: {stderr}"
        )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError(f"Benchmark worker for {profile} returned no result")
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Benchmark worker for {profile} returned invalid JSON: {lines[-1][-500:]}"
        ) from exc


def run_benchmark(
    profiles: list[str],
    repetitions: int,
    hyper_mode: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    if repetitions < 1:
        raise ValueError("repetitions must be at least one")
    started = datetime.now(UTC)
    results: dict[str, Any] = {}
    for profile in profiles:
        samples = [
            _run_worker_process(profile, hyper_mode, timeout_seconds)
            for _ in range(repetitions)
        ]
        results[profile] = aggregate_worker_samples(samples)
    report = {
        "schema_version": SCHEMA_VERSION,
        "harness_version": HARNESS_VERSION,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "fresh_run": True,
        "requested_profiles": profiles,
        "repetitions_per_profile": repetitions,
        "percentile_method": "nearest-rank",
        "timing_scope": {
            "pipeline_stages": "in-process stage wall time without persistence",
            "responses": "analytical call plus strict JSON serialisation; no HTTP transport",
            "artifacts": "in-process validated file generation to an isolated temporary root",
        },
        "memory_scope": (
            "ru_maxrss whole-process high-water mark sampled after each operation; retained "
            "dataset and prior-operation memory are included"
        ),
        "machine": machine_details(),
        "profiles": results,
        "elapsed_seconds": round((datetime.now(UTC) - started).total_seconds(), 6),
    }
    errors = validate_report(report)
    unmeasured = [
        f"{profile_name}/{metric}"
        for profile_name, profile in results.items()
        for metric, result in profile["operations"].items()
        if result["status"] != MEASURED
    ]
    report["validation"] = {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
    }
    report["completeness"] = {
        "status": "COMPLETE" if not unmeasured else "PARTIAL",
        "unmeasured_operations": unmeasured,
    }
    return report


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles", nargs="+", default=list(DEFAULT_PROFILES))
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument(
        "--hyper",
        choices=("skip", "auto", "required"),
        default="auto",
        help="auto records a sandbox limitation; required fails if Hyper cannot execute",
    )
    parser.add_argument("--timeout-seconds", type=int, default=1_200)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPOSITORY_ROOT / "outputs" / "performance",
    )
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--profile", help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    valid_profiles = {"fast", "test", "small", "default", "medium", "large"}
    if args.worker:
        if args.profile not in valid_profiles:
            raise SystemExit(f"Worker profile must be one of {sorted(valid_profiles)}")
        print(json.dumps(run_worker(args.profile, args.hyper), separators=(",", ":")))
        return
    unknown = sorted(set(args.profiles).difference(valid_profiles))
    if unknown:
        raise SystemExit(f"Unknown profiles: {', '.join(unknown)}")
    report = run_benchmark(
        list(dict.fromkeys(args.profiles)),
        args.repetitions,
        args.hyper,
        args.timeout_seconds,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    generated = datetime.fromisoformat(report["generated_at_utc"])
    path = args.output_dir / f"performance-{_iso_slug(generated)}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "path": str(path),
                "validation": report["validation"],
                "completeness": report["completeness"],
                "elapsed_seconds": report["elapsed_seconds"],
            },
            indent=2,
        )
    )
    if report["validation"]["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
