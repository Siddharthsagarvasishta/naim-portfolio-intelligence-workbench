#!/usr/bin/env python3
"""Build immutable core release evidence and the one-way final release envelope."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

PRODUCT = "nAIM Portfolio Intelligence Workbench"
SCHEMA_VERSION = "2.0.0"
DEFAULT_ROOT = Path(__file__).resolve().parents[1]
CORE_EVIDENCE_NAME = "nAIM_Release_Core_Evidence.json"
FINAL_EVIDENCE_NAME = "nAIM_Release_Evidence.json"
READINESS_JSON_NAME = "nAIM_Release_Readiness_Matrix.json"
VALIDATION_NAME = "nAIM_Release_Validation.md"

MANIFEST_FIELDS = {
    "artifact_id",
    "artifact_type",
    "artifact_version",
    "created_at",
    "created_by_component",
    "source_workspace",
    "reporting_period",
    "comparison_period",
    "filter_scope",
    "dataset_profile",
    "dataset_hash",
    "configuration_hash",
    "metric_registry_version",
    "code_version",
    "evidence_ids",
    "data_quality_status",
    "synthetic_data_flag",
    "file_name",
    "file_size",
    "sha256",
    "dependencies",
    "validation_status",
    "validation_tests",
    "known_limitations",
}
ALLOWED_CLASSIFICATIONS = {
    "LOCAL_LIVE",
    "LOCAL_OPTIONAL",
    "DESKTOP_EXPORT",
    "DOCUMENTED",
    "NOT_IMPLEMENTED",
    "BLOCKED",
}
CORE_RELEASE_ARTIFACTS = (
    "nAIM_Portfolio_Intelligence_Workbench_Source.zip",
    "nAIM_Portfolio_Intelligence_Workbench.xlsx",
    "nAIM_Portfolio_Intelligence_Review.pptx",
    "nAIM_Tableau_Desktop_Package.zip",
    "nAIM_PowerBI_Desktop_Package.zip",
    "nAIM_SAS_Compatibility_Package.zip",
    "nAIM_LinkedIn_Showcase.zip",
)
POST_DECISION_RELEASE_ARTIFACTS = (
    "nAIM_Release_Readiness_Matrix.xlsx",
    "nAIM_Research_Package.zip",
    "nAIM_GitHub_Release_Package.zip",
    "nAIM_Screenshots.zip",
)
EXPECTED_RELEASE_ARTIFACTS = CORE_RELEASE_ARTIFACTS + POST_DECISION_RELEASE_ARTIFACTS
FINAL_VERIFICATION_ORDER = ("core_evidence", *EXPECTED_RELEASE_ARTIFACTS)

STRICT_VALIDATION_STATUSES = {
    **{name: {"PASS"} for name in EXPECTED_RELEASE_ARTIFACTS},
    "nAIM_PowerBI_Desktop_Package.zip": {"STATIC_VALIDATION_PASS"},
    "nAIM_SAS_Compatibility_Package.zip": {"STATIC_VALIDATION_PASS"},
}
RECONCILIATION_CHANNEL_ORDER = (
    "api_service_evidence",
    "ui_snapshot",
    "excel_workbook",
    "powerpoint_review",
    "tableau_hyper",
    "power_bi_validation",
    "streamlit_snapshot",
    "static_share_site",
    "linkedin_carousel",
)
CORE_RECONCILIATION_CHANNELS = {
    "api_service_evidence",
    "excel_workbook",
    "powerpoint_review",
    "tableau_hyper",
    "power_bi_validation",
    "static_share_site",
    "linkedin_carousel",
}
# These are the only reconciliation channels that may remain non-blocking at the
# core-decision phase. They are still required and verified in their declared state.
NON_CORE_RECONCILIATION_ALLOWLIST = {
    "ui_snapshot": {
        "allowed_statuses": {"PASS", "INCOMPLETE"},
        "boundary": "POST_DECISION_SCREENSHOT_EVIDENCE",
    },
    "streamlit_snapshot": {
        "allowed_statuses": {"PASS", "INCOMPLETE"},
        "boundary": "OPTIONAL_EXTERNAL_RUNTIME_EVIDENCE",
    },
}
ALLOWED_EXTERNAL_PERFORMANCE_OPERATIONS = {
    "fast/hyper_generation",
    "default/hyper_generation",
    "medium/hyper_generation",
}
REQUIRED_TEST_BINDINGS = {
    "package_lock",
    "configuration",
    "canonical_evidence",
    "run_manifest",
    "openapi_contract",
    "openapi_validation",
    "reconciliation",
}
AUTHORED_SOURCE_ROOTS = (
    "alembic",
    "app",
    "apps",
    "config",
    "docs",
    "scripts",
    "src",
    "tests",
    ".openai",
)
AUTHORED_SOURCE_FILES = (
    "Makefile",
    "pyproject.toml",
    "package.json",
    "package-lock.json",
    "vite.config.ts",
)
EXTERNAL_BOUNDARIES = (
    {
        "capability": "Power BI Desktop open/refresh validation",
        "status": "EXTERNAL_DESKTOP_RUNTIME_BOUNDARY",
        "required_for_core_local_release": False,
        "truth": "Static package validation does not claim Power BI Desktop execution on this macOS host.",
    },
    {
        "capability": "Tableau Desktop publication validation",
        "status": "EXTERNAL_DESKTOP_RUNTIME_BOUNDARY",
        "required_for_core_local_release": False,
        "truth": "Local Hyper/package validation does not claim Tableau Desktop or Cloud publication.",
    },
    {
        "capability": "SAS execution validation",
        "status": "EXTERNAL_DESKTOP_RUNTIME_BOUNDARY",
        "required_for_core_local_release": False,
        "truth": "SAS-compatible files do not prove execution in a licensed SAS runtime.",
    },
    {
        "capability": "External AI API",
        "status": "NOT_REQUIRED",
        "required_for_core_local_release": False,
        "truth": "Core localhost operation does not require an external AI API or paid AI service.",
    },
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _portable(path: Path, root: Path) -> str:
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"Path is outside repository: {path}")
    return resolved.relative_to(root.resolve()).as_posix()


def _repository_file(root: Path, raw_path: Any) -> Path | None:
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    candidate = (root / raw_path).resolve()
    if not candidate.is_relative_to(root.resolve()) or not candidate.is_file():
        return None
    return candidate


def _read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, "MISSING"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if not isinstance(payload, dict):
        return None, "Top-level JSON value is not an object"
    return payload, None


def _source(path: Path, root: Path, error: str | None = None) -> dict[str, Any]:
    return {
        "path": _portable(path, root),
        "status": "AVAILABLE" if path.is_file() and error is None else "UNAVAILABLE",
        "bytes": path.stat().st_size if path.is_file() else None,
        "sha256": _sha256(path) if path.is_file() else None,
        "error": error,
    }


def _nested(payload: dict[str, Any] | None, dotted: str, default: Any = None) -> Any:
    current: Any = payload
    for key in dotted.split("."):
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def _integer(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _authored_source_binding(root: Path) -> dict[str, Any]:
    files: list[Path] = []
    for name in AUTHORED_SOURCE_ROOTS:
        candidate = root / name
        if candidate.is_dir():
            files.extend(path for path in candidate.rglob("*") if path.is_file())
    files.extend(path for name in AUTHORED_SOURCE_FILES if (path := root / name).is_file())
    digest = hashlib.sha256()
    file_count = 0
    for path in sorted(set(files)):
        if any(part in {"__pycache__", ".pytest_cache", ".ruff_cache"} for part in path.parts):
            continue
        if path.suffix.lower() in {".pyc", ".pyo"}:
            continue
        digest.update(_portable(path, root).encode("utf-8"))
        digest.update(b"\0")
        digest.update(_sha256(path).encode("ascii"))
        digest.update(b"\n")
        file_count += 1
    return {
        "basis": "portable-authored-tree-v1",
        "sha256": digest.hexdigest(),
        "file_count": file_count,
    }


def _git_state(root: Path) -> dict[str, Any]:
    source = _authored_source_binding(root)
    if not (root / ".git").exists():
        return {
            "git_commit": None,
            "working_tree_hash": source["sha256"],
            "git_commit_or_working_tree_hash": source["sha256"],
            "dirty_working_tree": None,
            "dirty_working_tree_status": "UNAVAILABLE_NO_GIT_METADATA",
        }
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            check=True,
            text=True,
            timeout=10,
        ).stdout.strip()
        porcelain = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            capture_output=True,
            check=True,
            text=True,
            timeout=10,
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "git_commit": None,
            "working_tree_hash": source["sha256"],
            "git_commit_or_working_tree_hash": source["sha256"],
            "dirty_working_tree": None,
            "dirty_working_tree_status": f"UNAVAILABLE: {type(exc).__name__}",
        }
    dirty = bool(porcelain.strip())
    return {
        "git_commit": commit,
        "working_tree_hash": source["sha256"],
        "git_commit_or_working_tree_hash": commit,
        "dirty_working_tree": dirty,
        "dirty_working_tree_status": "DIRTY" if dirty else "CLEAN",
    }


def _environment() -> dict[str, Any]:
    try:
        node = (
            subprocess.run(
                ["node", "--version"], capture_output=True, check=True, text=True, timeout=10
            )
            .stdout.strip()
            .lstrip("v")
        )
    except (OSError, subprocess.SubprocessError):
        node = None
    try:
        physical_memory = round(
            int(os.sysconf("SC_PAGE_SIZE")) * int(os.sysconf("SC_PHYS_PAGES")) / (1024 * 1024),
            2,
        )
    except (AttributeError, OSError, TypeError, ValueError):
        physical_memory = None
    return {
        "python_version": platform.python_version(),
        "node_version": node,
        "operating_system": platform.platform(),
        "processor": platform.processor() or platform.machine() or None,
        "architecture": platform.machine() or None,
        "logical_cpu_count": os.cpu_count(),
        "physical_memory_mib": physical_memory,
    }


def _manifest_path(root: Path, canonical: dict[str, Any] | None) -> Path:
    run_id = str(_nested(canonical, "metadata.run_id", "") or "")
    if run_id:
        candidate = root / "data" / "manifests" / run_id / "run_manifest.json"
        if candidate.is_file():
            return candidate
    latest = root / "data" / "manifests" / "latest.json"
    payload, _ = _read_json(latest)
    latest_run = str((payload or {}).get("run_id") or "")
    if latest_run:
        return root / "data" / "manifests" / latest_run / "run_manifest.json"
    candidates = sorted((root / "data" / "manifests").glob("*/run_manifest.json"))
    return candidates[-1] if candidates else root / "data" / "manifests" / "UNAVAILABLE.json"


def _dataset_hash(
    manifest_path: Path, manifest: dict[str, Any] | None, root: Path
) -> tuple[str | None, str | None]:
    if manifest is None or not manifest_path.is_file():
        return None, None
    components: list[tuple[str, int, str]] = []
    data_root = (root / "data").resolve()
    for logical_name, raw_path in sorted((manifest.get("paths") or {}).items()):
        if not str(logical_name).startswith(("validated.", "mart.")):
            continue
        path = Path(str(raw_path))
        if not path.is_absolute():
            path = manifest_path.parent / path
        path = path.resolve()
        if path.is_relative_to(data_root) and path.is_file():
            components.append((str(logical_name), path.stat().st_size, _sha256(path)))
    if components:
        encoded = json.dumps(components, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest(), "validated-and-mart-files"
    excluded = {"paths", "generation_timestamp", "completion_timestamp", "duration_seconds"}
    portable = {key: value for key, value in manifest.items() if key not in excluded}
    encoded = json.dumps(portable, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest(), "portable-run-manifest"


def _latest_json(directory: Path, pattern: str) -> tuple[Path, dict[str, Any] | None, str | None]:
    candidates = sorted(directory.glob(pattern)) if directory.is_dir() else []
    if not candidates:
        return directory / pattern.replace("*", "UNAVAILABLE"), None, "MISSING"
    dated: list[tuple[str, int, Path, dict[str, Any] | None, str | None]] = []
    for path in candidates:
        payload, error = _read_json(path)
        generated = str(
            (payload or {}).get("generated_at_utc")
            or (payload or {}).get("executed_at_utc")
            or (payload or {}).get("generated_at")
            or ""
        )
        dated.append((generated, path.stat().st_mtime_ns, path, payload, error))
    _, _, path, payload, error = max(dated, key=lambda item: (item[0], item[1], item[2].name))
    return path, payload, error


def _validate_file_record(
    root: Path,
    record: Any,
    *,
    label: str,
    expected_path: str | None = None,
    invocation_id: str | None = None,
    invocation_started_at: datetime | None = None,
    invocation_completed_at: datetime | None = None,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(record, dict):
        return [f"{label}: file binding is missing or not an object"]
    raw_path = record.get("path")
    if expected_path is not None and raw_path != expected_path:
        errors.append(f"{label}: expected path {expected_path!r}, received {raw_path!r}")
    path = _repository_file(root, raw_path)
    if path is None:
        errors.append(f"{label}: referenced file is missing or outside the repository")
        return errors
    if record.get("status") not in {None, "AVAILABLE"}:
        errors.append(f"{label}: binding status is not AVAILABLE")
    if record.get("bytes") != path.stat().st_size:
        errors.append(f"{label}: recorded byte size does not match current file")
    if record.get("sha256") != _sha256(path):
        errors.append(f"{label}: recorded SHA-256 does not match current file")
    actual_modified = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    declared_modified = _parse_timestamp(record.get("modified_at"))
    if record.get("modified_at") is not None and declared_modified != actual_modified:
        errors.append(f"{label}: recorded modification timestamp does not match current file")
    if invocation_id is not None:
        if record.get("invocation_id") != invocation_id:
            errors.append(f"{label}: invocation ID does not match the test report")
        if record.get("generated_in_invocation") is not True:
            errors.append(f"{label}: file was not declared generated in this invocation")
        if declared_modified is None:
            errors.append(f"{label}: invocation-generated file lacks modified_at")
        elif (
            invocation_started_at is None
            or invocation_completed_at is None
            or declared_modified < invocation_started_at - timedelta(seconds=2)
            or declared_modified > invocation_completed_at + timedelta(seconds=2)
        ):
            errors.append(f"{label}: file timestamp is outside the invocation window")
    return errors


def _test_summary(
    root: Path,
    security: dict[str, Any] | None = None,
    reference_time: datetime | None = None,
) -> dict[str, Any]:
    path = root / "outputs" / "validation" / "test_results.json"
    payload, parse_error = _read_json(path)
    errors: list[str] = []
    if parse_error:
        errors.append(f"test results: {parse_error}")
    invocation_id = str((payload or {}).get("invocation_id") or "")
    started_at = _parse_timestamp((payload or {}).get("started_at"))
    completed_at = _parse_timestamp((payload or {}).get("generated_at"))
    if not invocation_id:
        errors.append("test results: invocation_id is missing")
    if started_at is None or completed_at is None or completed_at < started_at:
        errors.append("test results: invocation time window is missing or invalid")
    if (
        reference_time is not None
        and completed_at is not None
        and reference_time - completed_at > timedelta(hours=24)
    ):
        errors.append("test results: invocation is older than 24 hours")
    if (payload or {}).get("status") != "PASS":
        errors.append("test results: top-level status is not PASS")
    if (payload or {}).get("release_gate_passed") is not True:
        errors.append("test results: release_gate_passed is not true")
    selected = (payload or {}).get("selected_suites")
    if selected != ["backend", "frontend", "e2e"]:
        errors.append("test results: selected_suites must be exactly backend, frontend, e2e")

    raw_suites = (payload or {}).get("suites")
    suites = raw_suites if isinstance(raw_suites, list) else []
    if len(suites) != 3:
        errors.append("test results: suites must contain exactly three entries")
    observed_categories: list[str] = []
    for index, expected in enumerate(("backend", "frontend", "e2e")):
        item = suites[index] if index < len(suites) and isinstance(suites[index], dict) else {}
        category = str(item.get("category") or "").lower()
        name = str(item.get("name") or "").lower()
        observed_categories.append(category)
        if category != expected or name != expected:
            errors.append(f"test results: suite {index} must be uniquely named {expected}")
        if item.get("status") != "PASS":
            errors.append(f"test results: {expected} status is not PASS")
        if item.get("exit_code") != 0:
            errors.append(f"test results: {expected} exit_code is not zero")
        if item.get("failed") != 0:
            errors.append(f"test results: {expected} failed count is not zero")
        if (_integer(item.get("passed")) or 0) <= 0:
            errors.append(f"test results: {expected} passed count is not positive")
    if len(set(observed_categories)) != len(observed_categories):
        errors.append("test results: duplicate suite categories are not allowed")

    backend = suites[0] if suites and isinstance(suites[0], dict) else {}
    backend_evidence = backend.get("evidence") if isinstance(backend.get("evidence"), dict) else {}
    junit_summary = backend_evidence.get("junit_summary") or {}
    if (
        not isinstance(junit_summary, dict)
        or junit_summary.get("status") != "AVAILABLE"
        or (_integer(junit_summary.get("tests")) or 0) <= 0
        or _integer(junit_summary.get("failed")) != 0
    ):
        errors.append("test results: same-invocation JUnit summary is unavailable or failed")
    errors.extend(
        _validate_file_record(
            root,
            backend_evidence.get("junit_artifact"),
            label="backend JUnit",
            expected_path="outputs/validation/backend_junit.xml",
            invocation_id=invocation_id or None,
            invocation_started_at=started_at,
            invocation_completed_at=completed_at,
        )
    )

    coverage = (payload or {}).get("coverage")
    coverage = coverage if isinstance(coverage, dict) else {}
    if (
        coverage.get("status") != "AVAILABLE"
        or not isinstance(coverage.get("percent"), (int, float))
        or not 0 <= float(coverage.get("percent") or -1) <= 100
        or coverage.get("invocation_id") != invocation_id
    ):
        errors.append("test results: same-invocation JSON coverage is unavailable or invalid")
    errors.extend(
        _validate_file_record(
            root,
            coverage.get("artifact"),
            label="backend coverage JSON",
            expected_path="outputs/validation/backend_coverage.json",
            invocation_id=invocation_id or None,
            invocation_started_at=started_at,
            invocation_completed_at=completed_at,
        )
    )

    bindings = (payload or {}).get("bindings")
    bindings = bindings if isinstance(bindings, dict) else {}
    if bindings.get("status") != "PASS":
        errors.append("test results: binding status is not PASS")
    if not REQUIRED_TEST_BINDINGS.issubset(bindings):
        errors.append("test results: one or more required current-file bindings are missing")
    source_tree = bindings.get("source_tree")
    source_tree = source_tree if isinstance(source_tree, dict) else {}
    current_tree = _authored_source_binding(root)
    if (
        source_tree.get("basis") != "portable-authored-tree-v1"
        or source_tree.get("sha256") != current_tree["sha256"]
        or source_tree.get("file_count") != current_tree["file_count"]
    ):
        errors.append("test results: authored source-tree binding is stale")
    expected_binding_paths = {
        "package_lock": "package-lock.json",
        "configuration": "config/feature_status.yaml",
        "canonical_evidence": "exports/validation/interop_evidence_snapshot.json",
        "openapi_contract": "outputs/contracts/openapi.json",
        "openapi_validation": "outputs/contracts/openapi_validation.json",
        "reconciliation": "outputs/validation/cross_artifact_reconciliation.json",
    }
    for name in sorted(REQUIRED_TEST_BINDINGS):
        errors.extend(
            _validate_file_record(
                root,
                bindings.get(name),
                label=f"test binding {name}",
                expected_path=expected_binding_paths.get(name),
            )
        )

    totals = {
        key: sum((_integer(item.get(key)) or 0) for item in suites if isinstance(item, dict))
        for key in ("passed", "failed", "skipped", "warnings")
    }
    focused = (security or {}).get("focused_test_suite")
    return {
        "source": _source(path, root, parse_error),
        "invocation_id": invocation_id or None,
        "selected_suites": selected,
        "suites": suites,
        "security_focused_suite": focused if isinstance(focused, dict) else None,
        "test_counts": totals,
        "coverage": coverage,
        "bindings": bindings,
        "validation_errors": errors,
        "status": "PASS" if not errors else "INCOMPLETE",
    }


def _performance_summary(
    path: Path,
    payload: dict[str, Any] | None,
    root: Path,
    error: str | None,
    reference_time: datetime,
) -> dict[str, Any]:
    errors: list[str] = []
    if error:
        errors.append(f"performance report: {error}")
    generated = _parse_timestamp((payload or {}).get("generated_at_utc"))
    if generated is None:
        errors.append("performance report: generated_at_utc is missing or invalid")
    elif generated > reference_time + timedelta(minutes=5):
        errors.append("performance report: timestamp is in the future")
    elif reference_time - generated > timedelta(days=14):
        errors.append("performance report: evidence is older than 14 days")
    if (payload or {}).get("schema_version") != "1.0.0":
        errors.append("performance report: unsupported schema_version")
    if (payload or {}).get("fresh_run") is not True:
        errors.append("performance report: fresh_run is not true")
    repetitions = (payload or {}).get("repetitions_per_profile")
    if not isinstance(repetitions, int) or repetitions <= 0:
        errors.append("performance report: repetitions_per_profile must be positive")
    if not isinstance((payload or {}).get("machine"), dict) or not (payload or {}).get("machine"):
        errors.append("performance report: machine record is missing")
    validation = (payload or {}).get("validation") or {}
    if validation.get("status") != "PASS" or validation.get("errors") not in ([], None):
        errors.append("performance report: validation did not pass cleanly")

    raw_profiles = (payload or {}).get("profiles")
    raw_profiles = raw_profiles if isinstance(raw_profiles, dict) else {}
    requested_profiles = (payload or {}).get("requested_profiles")
    requested_profiles_valid = isinstance(requested_profiles, list) and all(
        isinstance(item, str) for item in requested_profiles
    )
    if (
        not raw_profiles
        or not requested_profiles_valid
        or set(requested_profiles) != set(raw_profiles)
    ):
        errors.append("performance report: requested_profiles must exactly match profiles")
    if "default" not in raw_profiles:
        errors.append("performance report: default profile is required")

    profiles: dict[str, Any] = {}
    external_operations: list[str] = []
    blocking_operations: list[str] = []
    for profile, values in sorted(raw_profiles.items()):
        if not isinstance(values, dict):
            errors.append(f"performance report: profile {profile} is not an object")
            continue
        dataset = values.get("dataset") or {}
        if (
            not isinstance(dataset.get("account_month_rows"), int)
            or int(dataset.get("account_month_rows") or 0) <= 0
        ):
            errors.append(f"performance report: profile {profile} has no dataset row count")
        raw_operations = values.get("operations")
        raw_operations = raw_operations if isinstance(raw_operations, dict) else {}
        if not raw_operations:
            errors.append(f"performance report: profile {profile} has no operations")
        operations: dict[str, Any] = {}
        for name, operation in sorted(raw_operations.items()):
            operation = operation if isinstance(operation, dict) else {}
            status = str(operation.get("status") or "UNKNOWN")
            qualified = f"{profile}/{name}"
            if status == "EXTERNAL_EXECUTION_REQUIRED":
                external_operations.append(qualified)
                if qualified not in ALLOWED_EXTERNAL_PERFORMANCE_OPERATIONS:
                    errors.append(
                        f"performance report: {qualified} is not an allowed external boundary"
                    )
                if not operation.get("reason") or not operation.get("rerun_requirement"):
                    errors.append(f"performance report: {qualified} lacks reason/rerun_requirement")
            elif status == "MEASURED":
                timing = operation.get("timing_ms") or {}
                samples = timing.get("samples")
                if (
                    not isinstance(timing.get("median"), (int, float))
                    or not isinstance(timing.get("p95"), (int, float))
                    or not isinstance(samples, list)
                    or not samples
                    or operation.get("repetitions") != len(samples)
                ):
                    errors.append(
                        f"performance report: {qualified} lacks complete measured timing evidence"
                    )
            else:
                blocking_operations.append(qualified)
                errors.append(f"performance report: {qualified} has unsupported status {status}")
            operations[name] = {
                "status": status,
                "median_ms": _nested(operation, "timing_ms.median"),
                "p95_ms": _nested(operation, "timing_ms.p95"),
                "repetitions": operation.get("repetitions"),
                "reason": operation.get("reason"),
                "rerun_requirement": operation.get("rerun_requirement"),
            }
        profiles[str(profile)] = {"dataset": dataset, "operations": operations}

    completeness = (payload or {}).get("completeness") or {}
    declared_unmeasured = sorted(
        str(item) for item in completeness.get("unmeasured_operations") or []
    )
    if declared_unmeasured != sorted(external_operations):
        errors.append(
            "performance report: completeness.unmeasured_operations does not match external operations"
        )
    expected_completeness = "PARTIAL" if external_operations else "COMPLETE"
    if completeness.get("status") != expected_completeness:
        errors.append(f"performance report: completeness.status must be {expected_completeness}")
    status = (
        "PASS_WITH_EXTERNAL_BOUNDARIES"
        if not errors and external_operations
        else "PASS"
        if not errors
        else "FAIL"
    )
    return {
        "source": _source(path, root, error),
        "status": status,
        "generated_at": (payload or {}).get("generated_at_utc"),
        "elapsed_seconds": (payload or {}).get("elapsed_seconds"),
        "completeness": completeness,
        "machine": (payload or {}).get("machine"),
        "profiles": profiles,
        "external_execution_operations": external_operations,
        "allowed_external_operations": sorted(ALLOWED_EXTERNAL_PERFORMANCE_OPERATIONS),
        "blocking_operations": blocking_operations,
        "validation_errors": errors,
    }


def _openapi_summary(
    root: Path, path: Path, payload: dict[str, Any] | None, error: str | None
) -> dict[str, Any]:
    errors: list[str] = []
    if error:
        errors.append(f"OpenAPI validation: {error}")
    contract_path = str((payload or {}).get("contract") or "")
    contract = _repository_file(root, contract_path)
    if contract_path != "outputs/contracts/openapi.json" or contract is None:
        errors.append("OpenAPI validation: canonical contract path is missing or invalid")
    elif (payload or {}).get("sha256") != _sha256(contract):
        errors.append("OpenAPI validation: recorded contract SHA-256 is stale")
    if (payload or {}).get("status") != "PASS" or (payload or {}).get("errors") != []:
        errors.append("OpenAPI validation: status/errors do not represent a clean pass")
    for key in ("operation_count", "operation_id_count", "api_v1_operation_count", "path_count"):
        if not isinstance((payload or {}).get(key), int) or int((payload or {}).get(key) or 0) <= 0:
            errors.append(f"OpenAPI validation: {key} must be a positive integer")
    if (payload or {}).get("operation_count") != (payload or {}).get("operation_id_count"):
        errors.append("OpenAPI validation: operation and operation-id counts differ")
    if (payload or {}).get("declared_http_501_count") != 0:
        errors.append("OpenAPI validation: declared HTTP 501 count is not zero")
    return {
        "source": _source(path, root, error),
        "contract": _source(
            contract if contract is not None else root / "outputs" / "contracts" / "openapi.json",
            root,
            None if contract is not None else "MISSING",
        ),
        "status": "PASS" if not errors else "FAIL",
        "operation_count": (payload or {}).get("operation_count"),
        "api_v1_operation_count": (payload or {}).get("api_v1_operation_count"),
        "path_count": (payload or {}).get("path_count"),
        "declared_http_501_count": (payload or {}).get("declared_http_501_count"),
        "sha256": (payload or {}).get("sha256"),
        "validation_errors": errors,
    }


def _security_summary(
    root: Path,
    security_path: Path,
    security: dict[str, Any] | None,
    security_error: str | None,
    scan_path: Path,
    scan: dict[str, Any] | None,
    scan_error: str | None,
    reference_time: datetime,
) -> dict[str, Any]:
    audit_path = root / "outputs" / "validation" / "npm_audit_after_summary.json"
    audit, audit_error = _read_json(audit_path)
    errors: list[str] = []
    if security_error:
        errors.append(f"security controls: {security_error}")
    if scan_error:
        errors.append(f"security scanner: {scan_error}")
    if audit_error:
        errors.append(f"npm audit summary: {audit_error}")
    focused = (security or {}).get("focused_test_suite")
    focused = focused if isinstance(focused, dict) else {}
    if (
        focused.get("status") != "PASS"
        or focused.get("failed") != 0
        or (_integer(focused.get("passed")) or 0) <= 0
    ):
        errors.append("security controls: focused test suite did not pass")
    overall = (security or {}).get("overall_status")
    incomplete_external = (security or {}).get("uncompleted_security_validation")
    incomplete_external = incomplete_external if isinstance(incomplete_external, list) else []
    if overall not in {"PASS", "PARTIAL"}:
        errors.append("security controls: overall_status must be PASS or honest PARTIAL")
    if overall == "PARTIAL" and not incomplete_external:
        errors.append("security controls: PARTIAL lacks explicit external boundaries")
    if (
        (scan or {}).get("status") not in {"PASS", "PASS_WITH_WARNINGS"}
        or _integer(_nested(scan, "summary.errors")) != 0
        or _integer(_nested(scan, "summary.unreadable_files")) != 0
    ):
        errors.append("security scanner: authored-surface scan did not pass")
    counts = (audit or {}).get("vulnerability_counts")
    counts = counts if isinstance(counts, dict) else {}
    if (
        (audit or {}).get("status") != "PASS"
        or (audit or {}).get("release_decision") != "PASS"
        or any(
            _integer(counts.get(key)) != 0
            for key in ("low", "moderate", "high", "critical", "total")
        )
    ):
        errors.append("npm audit summary: vulnerability counts are not a zero-advisory pass")
    lock = root / "package-lock.json"
    declared_lock = (audit or {}).get("package_lock")
    if isinstance(declared_lock, dict):
        errors.extend(
            _validate_file_record(
                root,
                declared_lock,
                label="npm audit package-lock binding",
                expected_path="package-lock.json",
            )
        )
    elif not lock.is_file() or (audit or {}).get("package_lock_sha256") != _sha256(lock):
        errors.append("npm audit summary: current package-lock SHA-256 binding is missing or stale")
    refreshed = _parse_timestamp(
        (security or {}).get("dependency_audit_refreshed_at_utc")
        or (audit or {}).get("executed_at_utc")
    )
    if refreshed is None:
        errors.append("npm audit summary: refresh timestamp is invalid")
    elif refreshed > reference_time + timedelta(minutes=5):
        errors.append("npm audit summary: refresh timestamp is in the future")
    elif reference_time - refreshed > timedelta(days=2):
        errors.append("npm audit summary: dependency evidence is older than two days")
    status = (
        "PASS_WITH_EXTERNAL_BOUNDARIES"
        if not errors and overall == "PARTIAL"
        else "PASS"
        if not errors
        else "FAIL"
    )
    return {
        "status": status,
        "overall_status": overall,
        "overall_reason": (security or {}).get("overall_reason"),
        "focused_test_suite": focused,
        "scan_status": (scan or {}).get("status"),
        "scan_summary": (scan or {}).get("summary"),
        "npm_audit_status": (audit or {}).get("status"),
        "npm_vulnerability_counts": counts,
        "uncompleted_validation": incomplete_external,
        "known_residual_risks": (
            (security or {}).get("known_residual_risks")
            if isinstance((security or {}).get("known_residual_risks"), list)
            else []
        ),
        "validation_errors": errors,
        "sources": {
            "security_tests": _source(security_path, root, security_error),
            "security_scan": _source(scan_path, root, scan_error),
            "npm_audit": _source(audit_path, root, audit_error),
            "package_lock": _source(lock, root, None if lock.is_file() else "MISSING"),
        },
    }


def _check_declared_outcome(check: dict[str, Any]) -> bool:
    if check.get("outcome") != "PASS":
        return False
    if "expected" not in check or check.get("expected") is None:
        return check.get("actual") is not None
    expected = check.get("expected")
    actual = check.get("actual")
    tolerance = check.get("tolerance")
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        try:
            return abs(float(actual) - float(expected)) <= float(tolerance or 0)
        except (TypeError, ValueError):
            return False
    return actual == expected


def _reconciliation_summary(
    root: Path,
    path: Path,
    payload: dict[str, Any] | None,
    error: str | None,
    reference_time: datetime,
    *,
    canonical_path: Path,
    dataset_hash: str | None,
    run_id: str | None,
    configuration_hash: str | None,
    final_phase: bool = False,
) -> dict[str, Any]:
    errors: list[str] = []
    if error:
        errors.append(f"reconciliation: {error}")
    generated = _parse_timestamp((payload or {}).get("generated_at_utc"))
    if generated is None:
        errors.append("reconciliation: generated_at_utc is missing or invalid")
    elif generated > reference_time + timedelta(minutes=5):
        errors.append("reconciliation: timestamp is in the future")
    elif reference_time - generated > timedelta(hours=24):
        errors.append("reconciliation: evidence is older than 24 hours")
    channels = (payload or {}).get("channels")
    channels = channels if isinstance(channels, list) else []
    channel_ids = [
        str(item.get("channel_id") or "") if isinstance(item, dict) else "" for item in channels
    ]
    if channel_ids != list(RECONCILIATION_CHANNEL_ORDER):
        errors.append("reconciliation: channel IDs/order do not match the required contract")
    if len(channel_ids) != len(set(channel_ids)):
        errors.append("reconciliation: duplicate channel IDs are not allowed")

    channel_results: list[dict[str, Any]] = []
    for item in channels:
        if not isinstance(item, dict):
            errors.append("reconciliation: channel entry is not an object")
            continue
        channel_id = str(item.get("channel_id") or "")
        status = str(item.get("status") or "")
        channel_errors: list[str] = []
        if item.get("required") is not True:
            channel_errors.append("channel must remain explicitly required")
        checks = item.get("checks")
        checks = checks if isinstance(checks, list) else []
        required_checks = [row for row in checks if isinstance(row, dict) and row.get("required")]
        if not required_checks:
            channel_errors.append("channel has no required checks")
        if channel_id in CORE_RECONCILIATION_CHANNELS or (
            final_phase and channel_id == "ui_snapshot"
        ):
            if status != "PASS":
                channel_errors.append("core channel status is not PASS")
            for check in required_checks:
                if not _check_declared_outcome(check):
                    channel_errors.append(
                        f"required check {check.get('check_id')} is failed or internally inconsistent"
                    )
        elif channel_id in NON_CORE_RECONCILIATION_ALLOWLIST and not (
            final_phase and channel_id == "ui_snapshot"
        ):
            allowed = NON_CORE_RECONCILIATION_ALLOWLIST[channel_id]["allowed_statuses"]
            if status not in allowed:
                channel_errors.append(f"status {status!r} is outside the explicit allowlist")
            outcomes = {str(check.get("outcome") or "") for check in required_checks}
            if status == "PASS":
                for check in required_checks:
                    if not _check_declared_outcome(check):
                        channel_errors.append(
                            f"PASS check {check.get('check_id')} is internally inconsistent"
                        )
            elif not outcomes.intersection({"MISSING", "UNVERIFIABLE"}):
                channel_errors.append(
                    "INCOMPLETE channel does not declare a missing/unverifiable required check"
                )
            if outcomes.difference({"PASS", "MISSING", "UNVERIFIABLE"}):
                channel_errors.append("non-core channel contains an unsupported outcome")
        else:
            channel_errors.append("channel is neither core nor explicitly allowlisted")

        raw_paths = item.get("artifact_paths")
        artifact_paths = raw_paths if isinstance(raw_paths, list) else []
        raw_artifacts = item.get("artifacts")
        artifacts = raw_artifacts if isinstance(raw_artifacts, list) else []
        if status == "PASS" and (not artifact_paths or not artifacts):
            channel_errors.append("PASS channel has no artifact evidence")
        artifact_record_paths: list[str] = []
        for index, record in enumerate(artifacts):
            if not isinstance(record, dict):
                channel_errors.append(f"artifact record {index} is not an object")
                continue
            artifact_record_paths.append(str(record.get("path") or ""))
            current = _repository_file(root, record.get("path"))
            if current is None:
                channel_errors.append(f"artifact record {index} path is missing or unsafe")
                continue
            if record.get("bytes") != current.stat().st_size:
                channel_errors.append(f"artifact record {index} byte size is stale")
            if record.get("sha256") != _sha256(current):
                channel_errors.append(f"artifact record {index} SHA-256 is stale")
            if generated is not None:
                modified = datetime.fromtimestamp(current.stat().st_mtime, tz=UTC)
                if modified > generated + timedelta(seconds=2):
                    channel_errors.append(
                        f"artifact record {index} was modified after reconciliation"
                    )
        if sorted(str(value) for value in artifact_paths) != sorted(artifact_record_paths):
            channel_errors.append("artifact_paths and artifacts records do not match exactly")
        errors.extend(f"reconciliation {channel_id}: {message}" for message in channel_errors)
        channel_results.append(
            {
                "channel_id": channel_id,
                "declared_status": status,
                "required_check_count": len(required_checks),
                "artifact_count": len(artifacts),
                "status": "PASS" if not channel_errors else "FAIL",
                "validation_errors": channel_errors,
                "boundary": (NON_CORE_RECONCILIATION_ALLOWLIST.get(channel_id) or {}).get(
                    "boundary"
                ),
            }
        )

    canonical = (payload or {}).get("canonical") or {}
    if canonical.get("source_path") != _portable(canonical_path, root):
        errors.append("reconciliation: canonical source path does not match current evidence")
    elif canonical_path.is_file() and canonical.get("source_file_sha256") != _sha256(
        canonical_path
    ):
        errors.append("reconciliation: canonical source file SHA-256 is stale")
    if canonical.get("dataset_hash") != dataset_hash:
        errors.append("reconciliation: canonical dataset hash does not match")
    story = canonical.get("story") or {}
    if story.get("run_id") != run_id:
        errors.append("reconciliation: canonical run ID does not match")
    if story.get("configuration_hash") != configuration_hash:
        errors.append("reconciliation: canonical configuration hash does not match")
    if story.get("dataset_hash") != dataset_hash:
        errors.append("reconciliation: story dataset hash does not match")

    incomplete_allowed = any(
        isinstance(item, dict)
        and item.get("channel_id")
        in ({"streamlit_snapshot"} if final_phase else NON_CORE_RECONCILIATION_ALLOWLIST)
        and item.get("status") == "INCOMPLETE"
        for item in channels
    )
    expected_result = "INCOMPLETE" if incomplete_allowed else "PASS"
    if (payload or {}).get("result") != expected_result:
        errors.append(
            f"reconciliation: declared result must be {expected_result} for observed channels"
        )
    if (payload or {}).get("release_allowed") is not (expected_result == "PASS"):
        errors.append("reconciliation: release_allowed is inconsistent with declared result")
    summary = (payload or {}).get("summary") or {}
    if summary.get("required_channel_count") != len(RECONCILIATION_CHANNEL_ORDER):
        errors.append("reconciliation: summary required_channel_count is inconsistent")
    status = (
        "PASS_WITH_NON_CORE_BOUNDARIES"
        if not errors and incomplete_allowed
        else ("PASS" if not errors else "FAIL")
    )
    return {
        "source": _source(path, root, error),
        "status": status,
        "generated_at": (payload or {}).get("generated_at_utc"),
        "declared_result": (payload or {}).get("result"),
        "declared_release_allowed": (payload or {}).get("release_allowed"),
        "channel_results": channel_results,
        "non_core_allowlist": {
            key: {
                "allowed_statuses": sorted(value["allowed_statuses"]),
                "boundary": value["boundary"],
            }
            for key, value in NON_CORE_RECONCILIATION_ALLOWLIST.items()
            if not final_phase or key == "streamlit_snapshot"
        },
        "validation_errors": errors,
        "summary": summary,
    }


def _path_like(value: str) -> bool:
    return "/" in value and Path(value).suffix.lower() in {
        ".json",
        ".md",
        ".html",
        ".py",
        ".zip",
        ".xlsx",
        ".pptx",
        ".pdf",
        ".hyper",
        ".dax",
        ".sas",
        ".csv",
    }


def _manifest_record(
    root: Path,
    manifest_path: Path,
    payload: dict[str, Any] | None,
    parse_error: str | None,
    *,
    filename: str,
    dataset_hash: str | None,
    configuration_hash: str | None,
    metric_registry_version: str | None,
    run_id: str | None,
    evidence_id: str | None,
    require_core_dependency: bool,
) -> dict[str, Any]:
    errors: list[str] = []
    if parse_error:
        errors.append(f"manifest parse: {parse_error}")
    payload = payload or {}
    missing = sorted(MANIFEST_FIELDS - set(payload))
    if missing:
        errors.append(f"manifest contract fields missing: {', '.join(missing)}")
    provenance_fields = (
        "artifact_id",
        "artifact_type",
        "artifact_version",
        "created_at",
        "created_by_component",
        "source_workspace",
        "reporting_period",
        "comparison_period",
        "dataset_profile",
        "dataset_hash",
        "configuration_hash",
        "metric_registry_version",
        "code_version",
        "file_name",
        "sha256",
        "validation_status",
    )
    for field in provenance_fields:
        if not isinstance(payload.get(field), str) or not str(payload.get(field)).strip():
            errors.append(f"manifest provenance field {field} is not a non-empty string")
    if _parse_timestamp(payload.get("created_at")) is None:
        errors.append("manifest created_at is invalid")
    for field in ("filter_scope",):
        if not isinstance(payload.get(field), dict) or not payload.get(field):
            errors.append(f"manifest provenance field {field} is not a non-empty object")
    for field in ("evidence_ids", "dependencies", "validation_tests"):
        if not isinstance(payload.get(field), list) or not payload.get(field):
            errors.append(f"manifest provenance field {field} is not a non-empty list")
    if not isinstance(payload.get("known_limitations"), list):
        errors.append("manifest known_limitations is not a list")
    if not isinstance(payload.get("synthetic_data_flag"), bool):
        errors.append("manifest synthetic_data_flag is not boolean")
    if payload.get("file_name") != filename:
        errors.append("manifest file_name does not match expected artifact")
    artifact = root / "outputs" / filename
    if not artifact.is_file():
        errors.append("expected artifact file is missing")
    else:
        if payload.get("file_size") != artifact.stat().st_size:
            errors.append("manifest file_size does not match artifact")
        if payload.get("sha256") != _sha256(artifact):
            errors.append("manifest SHA-256 does not match artifact")
    nested_artifact = payload.get("artifact") or {}
    if not isinstance(nested_artifact, dict):
        errors.append("manifest artifact record is missing")
    elif (
        nested_artifact.get("path") != f"outputs/{filename}"
        or nested_artifact.get("bytes") != payload.get("file_size")
        or nested_artifact.get("sha256") != payload.get("sha256")
    ):
        errors.append("manifest nested artifact record is inconsistent")
    allowed_statuses = STRICT_VALIDATION_STATUSES[filename]
    if payload.get("validation_status") not in allowed_statuses:
        errors.append(
            "manifest validation_status is outside the strict runtime-classification allowlist"
        )
    if payload.get("source_snapshot_id") != run_id:
        errors.append("manifest source_snapshot_id does not match canonical run")
    if payload.get("dataset_hash") != dataset_hash:
        errors.append("manifest dataset_hash does not match canonical dataset")
    if payload.get("configuration_hash") != configuration_hash:
        errors.append("manifest configuration_hash does not match canonical configuration")
    if payload.get("metric_registry_version") != metric_registry_version:
        errors.append("manifest metric_registry_version does not match canonical registry")
    if evidence_id not in (payload.get("evidence_ids") or []):
        errors.append("manifest evidence_ids do not contain canonical evidence ID")
    if payload.get("data_quality_status") != "PASS":
        errors.append("manifest data_quality_status is not PASS")

    dependencies = [str(value) for value in payload.get("dependencies") or []]
    for dependency in dependencies:
        if _repository_file(root, dependency) is None:
            errors.append(f"manifest dependency is missing or unsafe: {dependency}")
    source_inputs = payload.get("source_inputs")
    if not isinstance(source_inputs, list) or not source_inputs:
        errors.append("manifest source_inputs must contain hashed provenance records")
        source_inputs = []
    source_paths: list[str] = []
    for index, record in enumerate(source_inputs):
        source_paths.append(str(record.get("path") or "") if isinstance(record, dict) else "")
        errors.extend(_validate_file_record(root, record, label=f"manifest source_input {index}"))
    validation_evidence = payload.get("validation_evidence")
    if validation_evidence is not None and not isinstance(validation_evidence, list):
        errors.append("manifest validation_evidence is not a list")
        validation_evidence = []
    validation_evidence_paths: list[str] = []
    for index, value in enumerate(validation_evidence or []):
        if isinstance(value, dict):
            validation_evidence_paths.append(str(value.get("path") or ""))
            errors.extend(
                _validate_file_record(root, value, label=f"manifest validation_evidence {index}")
            )
        else:
            validation_evidence_paths.append(str(value))
            if _repository_file(root, str(value)) is None:
                errors.append(f"manifest validation evidence is missing or unsafe: {value}")
    for value in payload.get("validation_tests") or []:
        text = str(value)
        if _path_like(text) and _repository_file(root, text) is None:
            errors.append(f"manifest path-like validation test is missing: {text}")
    all_declared_paths = (
        set(dependencies)
        | set(source_paths)
        | set(validation_evidence_paths)
        | {str(value) for value in payload.get("validation_tests") or []}
    )
    if f"outputs/{FINAL_EVIDENCE_NAME}" in all_declared_paths:
        errors.append("artifact manifest consumes the final envelope, violating one-way lineage")
    if require_core_dependency:
        if f"outputs/{CORE_EVIDENCE_NAME}" not in all_declared_paths:
            errors.append("post-decision manifest is not bound to immutable core evidence")

    return {
        "manifest_path": _portable(manifest_path, root),
        "manifest_sha256": _sha256(manifest_path) if manifest_path.is_file() else None,
        "file_name": filename,
        "artifact_path": f"outputs/{filename}" if artifact.is_file() else None,
        "runtime_classification": (
            "STATIC_DESKTOP_EXPORT"
            if allowed_statuses == {"STATIC_VALIDATION_PASS"}
            else "VALIDATED_LOCAL_OR_PORTABLE_ARTIFACT"
        ),
        "allowed_validation_statuses": sorted(allowed_statuses),
        "validation_status": payload.get("validation_status"),
        "hash_matches": artifact.is_file() and payload.get("sha256") == _sha256(artifact),
        "size_matches": artifact.is_file() and payload.get("file_size") == artifact.stat().st_size,
        "validation_errors": errors,
        "status": "PASS" if not errors else "FAIL",
    }


def _artifact_inventory(
    root: Path,
    expected_artifacts: tuple[str, ...],
    *,
    dataset_hash: str | None,
    configuration_hash: str | None,
    metric_registry_version: str | None,
    run_id: str | None,
    evidence_id: str | None,
    post_decision_names: set[str] | None = None,
) -> dict[str, Any]:
    manifest_root = root / "outputs" / "manifests"
    parsed_manifests: list[tuple[Path, dict[str, Any] | None, str | None]] = []
    if manifest_root.is_dir():
        for path in sorted(manifest_root.rglob("*.json")):
            payload, error = _read_json(path)
            parsed_manifests.append((path, payload, error))
    expected: list[dict[str, Any]] = []
    for filename in expected_artifacts:
        matches = [
            item
            for item in parsed_manifests
            if str((item[1] or {}).get("file_name") or "") == filename
        ]
        artifact = root / "outputs" / filename
        if len(matches) == 1:
            manifest = _manifest_record(
                root,
                matches[0][0],
                matches[0][1],
                matches[0][2],
                filename=filename,
                dataset_hash=dataset_hash,
                configuration_hash=configuration_hash,
                metric_registry_version=metric_registry_version,
                run_id=run_id,
                evidence_id=evidence_id,
                require_core_dependency=filename in (post_decision_names or set()),
            )
        else:
            manifest = {
                "status": "FAIL",
                "manifest_path": None,
                "validation_status": None,
                "validation_errors": [
                    "canonical manifest is missing"
                    if not matches
                    else "multiple canonical manifests declare the same file_name"
                ],
            }
        expected.append(
            {
                "file_name": filename,
                "path": f"outputs/{filename}",
                "exists": artifact.is_file(),
                "bytes": artifact.stat().st_size if artifact.is_file() else None,
                "sha256": _sha256(artifact) if artifact.is_file() else None,
                "manifest": manifest,
                "manifest_path": manifest.get("manifest_path"),
                "manifest_status": manifest.get("status"),
            }
        )
    ready = all(item["exists"] and item["manifest_status"] == "PASS" for item in expected)
    return {
        "expected_release_artifacts": expected,
        "summary": {
            "expected_count": len(expected),
            "present_count": sum(bool(item["exists"]) for item in expected),
            "manifested_and_valid_count": sum(
                item["manifest_status"] == "PASS" for item in expected
            ),
            "all_expected_ready": ready,
        },
        "status": "PASS" if ready else "INCOMPLETE",
    }


def _file_evidence_status(root: Path, paths: list[Any]) -> tuple[str, list[str], list[str]]:
    declared = [str(item) for item in paths if str(item).strip()]
    present = [item for item in declared if _repository_file(root, item) is not None]
    missing = sorted(set(declared) - set(present))
    if not declared:
        return "NOT_APPLICABLE", present, missing
    return ("PASS" if not missing else "PARTIAL" if present else "MISSING"), present, missing


def _desktop_export(feature: dict[str, Any]) -> bool:
    identity = f"{feature.get('feature_id', '')} {feature.get('name', '')}".upper()
    return any(
        token in identity
        for token in (
            "POWER BI",
            "POWERBI",
            "TABLEAU",
            "SAS",
            "EXCEL",
            "POWERPOINT",
            "PRESENTATION",
            "EXPORT",
        )
    )


def _readiness_matrix(
    root: Path,
    registry_path: Path,
    registry: dict[str, Any] | None,
    release_allowed: bool,
    generated_at: str,
) -> dict[str, Any]:
    capabilities: list[dict[str, Any]] = []
    for feature in (registry or {}).get("features") or []:
        status = str(feature.get("status") or "UNKNOWN")
        test_status, _, _ = _file_evidence_status(root, list(feature.get("test_evidence") or []))
        documentation_paths = [
            item
            for item in (feature.get("artifact_evidence") or [])
            if str(item).lower().endswith((".md", ".html"))
        ]
        documentation_status, _, _ = _file_evidence_status(root, documentation_paths)
        export_paths = [
            item
            for item in (feature.get("artifact_evidence") or [])
            if not str(item).lower().endswith((".md", ".html"))
        ]
        export_status, _, _ = _file_evidence_status(root, export_paths)
        evidence_status = (
            "PASS"
            if test_status in {"PASS", "NOT_APPLICABLE"}
            and export_status in {"PASS", "NOT_APPLICABLE"}
            else "PARTIAL"
            if test_status == "PASS" or export_status == "PASS"
            else "MISSING"
        )
        if status == "LIVE":
            classification = "LOCAL_LIVE" if test_status == "PASS" else "BLOCKED"
        elif status == "INTEGRATION_ONLY":
            classification = "DESKTOP_EXPORT" if _desktop_export(feature) else "LOCAL_OPTIONAL"
        elif status == "DOCUMENTED":
            classification = "DOCUMENTED"
        elif status == "NOT_IMPLEMENTED":
            classification = "NOT_IMPLEMENTED"
        elif status == "DISABLED":
            classification = "LOCAL_OPTIONAL"
        else:
            classification = "BLOCKED"
        backend_routes = list(feature.get("backend_endpoint") or [])
        frontend_routes = list(feature.get("frontend_route") or [])
        row = {
            "capability": str(feature.get("name") or feature.get("feature_id") or "Unnamed"),
            "business_value": str(
                feature.get("business_value")
                or f"Provides {str(feature.get('name') or 'this capability').lower()} with explicit governance boundaries."
            ),
            "backend_status": (
                status if backend_routes or feature.get("calculation_module") else "NOT_APPLICABLE"
            ),
            "frontend_status": status if frontend_routes else "NOT_APPLICABLE",
            "test_status": test_status,
            "documentation_status": documentation_status,
            "export_status": export_status,
            "evidence_status": evidence_status,
            "limitation": str(
                feature.get("limitation") or "No limitation was supplied; treat as undocumented."
            ),
            "final_classification": classification,
        }
        if classification not in ALLOWED_CLASSIFICATIONS:
            raise AssertionError(f"Unsupported readiness classification: {classification}")
        capabilities.append(row)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "source_registry": {
            "path": _portable(registry_path, root),
            "registry_version": (registry or {}).get("registry_version"),
            "sha256": _sha256(registry_path) if registry_path.is_file() else None,
            "status": "AVAILABLE" if registry else "UNAVAILABLE",
        },
        "release_allowed": release_allowed,
        "capabilities": capabilities,
    }


def _principal_findings(canonical: dict[str, Any] | None) -> dict[str, Any]:
    finding = _nested(canonical, "root_cause.finding", {}) or {}
    recommendation = _nested(canonical, "strategy_comparison.recommendation", {}) or {}
    kpis = {
        str(item.get("metric_id")): item
        for item in (canonical or {}).get("kpis") or []
        if isinstance(item, dict) and item.get("metric_id")
    }
    selected = {
        metric: {
            "value": kpis.get(metric, {}).get("value"),
            "prior_value": kpis.get(metric, {}).get("prior_value"),
            "unit": kpis.get(metric, {}).get("unit"),
        }
        for metric in (
            "ACTIVE_ACCOUNTS",
            "ENDING_RECEIVABLES",
            "TRANSACTION_VALUE",
            "ANNUALISED_NET_LOSS_RATE",
            "THIRTY_PLUS_DELINQUENCY_RATE",
            "FRAUD_BPS",
            "MANUAL_REVIEW_RATE",
            "CUSTOMER_FRICTION_RATE",
            "EXPECTED_PROFIT",
        )
    }
    return {
        "reporting_period": (canonical or {}).get("selected_reporting_period"),
        "comparison_period": next(
            (
                item.get("comparison_period")
                for item in kpis.values()
                if item.get("comparison_period")
            ),
            None,
        ),
        "headline_scope": "All portfolio",
        "kpis": selected,
        "observed_loss_rate_movement_bps": finding.get("observed_change_bps"),
        "mix_contribution_bps": finding.get("mix_contribution_bps"),
        "within_segment_contribution_bps": finding.get("within_segment_contribution_bps"),
        "reconciliation_residual_bps": finding.get("reconciliation_residual_bps"),
        "primary_driver": finding.get("primary_driver"),
        "primary_dimension": finding.get("primary_dimension"),
        "causal_status": finding.get("causal_status"),
        "strategy_recommendation": recommendation.get("decision"),
        "approval_required": recommendation.get("approval_required"),
        "decision_notice": recommendation.get("notice"),
    }


def _gate(gate_id: str, required: bool, passed: bool, status: str, evidence: Any) -> dict[str, Any]:
    return {
        "gate_id": gate_id,
        "required": required,
        "passed": passed,
        "status": status,
        "evidence": evidence,
    }


def _input_fingerprint(
    sources: dict[str, dict[str, Any]], artifact_hashes: dict[str, str], invocation_id: Any
) -> str:
    payload = {
        "sources": {
            key: {
                "path": value.get("path"),
                "bytes": value.get("bytes"),
                "sha256": value.get("sha256"),
            }
            for key, value in sorted(sources.items())
        },
        "artifact_hashes": dict(sorted(artifact_hashes.items())),
        "test_invocation_id": invocation_id,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def build_release_evidence(
    root: Path, *, generated_at: str | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build the core decision evidence without consuming post-decision artifacts."""

    root = root.resolve()
    generated = generated_at or _utc_now()
    reference_time = _parse_timestamp(generated) or datetime.now(UTC)
    canonical_path = root / "exports" / "validation" / "interop_evidence_snapshot.json"
    canonical, canonical_error = _read_json(canonical_path)
    manifest_path = _manifest_path(root, canonical)
    run_manifest, manifest_error = _read_json(manifest_path)
    dataset_digest, dataset_basis = _dataset_hash(manifest_path, run_manifest, root)
    openapi_path = root / "outputs" / "contracts" / "openapi_validation.json"
    openapi, openapi_error = _read_json(openapi_path)
    openapi_summary = _openapi_summary(root, openapi_path, openapi, openapi_error)
    registry_path = root / "config" / "feature_status.yaml"
    registry, registry_error = _read_json(registry_path)
    performance_path, performance, performance_error = _latest_json(
        root / "outputs" / "performance", "performance-*.json"
    )
    security_path = root / "outputs" / "validation" / "security_test_results.json"
    security, security_error = _read_json(security_path)
    security_scan_path = root / "outputs" / "validation" / "security_scan.json"
    security_scan, security_scan_error = _read_json(security_scan_path)
    reconciliation_path = root / "outputs" / "validation" / "cross_artifact_reconciliation.json"
    reconciliation, reconciliation_error = _read_json(reconciliation_path)

    source_control = _git_state(root)
    metadata = (canonical or {}).get("metadata") or {}
    run_id = str(metadata.get("run_id") or "") or None
    manifest_run_id = str((run_manifest or {}).get("run_id") or "") or None
    configuration_hash = metadata.get("configuration_hash")
    manifest_configuration_hash = (run_manifest or {}).get("configuration_hash")
    metric_registry_version = metadata.get("metric_registry_version")
    evidence_id = str((canonical or {}).get("evidence_id") or "") or None
    row_counts = (run_manifest or {}).get("row_counts") or metadata.get("row_counts") or {}
    data_quality = (canonical or {}).get("data_quality") or {}
    tests = _test_summary(root, security, reference_time)
    benchmark = _performance_summary(
        performance_path, performance, root, performance_error, reference_time
    )
    security_summary = _security_summary(
        root,
        security_path,
        security,
        security_error,
        security_scan_path,
        security_scan,
        security_scan_error,
        reference_time,
    )
    reconciliation_summary = _reconciliation_summary(
        root,
        reconciliation_path,
        reconciliation,
        reconciliation_error,
        reference_time,
        canonical_path=canonical_path,
        dataset_hash=dataset_digest,
        run_id=run_id,
        configuration_hash=configuration_hash,
    )
    artifacts = _artifact_inventory(
        root,
        CORE_RELEASE_ARTIFACTS,
        dataset_hash=dataset_digest,
        configuration_hash=configuration_hash,
        metric_registry_version=metric_registry_version,
        run_id=run_id,
        evidence_id=evidence_id,
    )
    feature_counts = Counter(
        str(item.get("status") or "UNKNOWN")
        for item in (registry or {}).get("features") or []
        if isinstance(item, dict)
    )
    allowed_feature_statuses = set((registry or {}).get("allowed_statuses") or [])
    feature_registry_valid = (
        bool(registry)
        and bool((registry or {}).get("features"))
        and all(
            str(item.get("status")) in allowed_feature_statuses
            and (
                str(item.get("status")) != "LIVE"
                or (
                    bool(item.get("test_evidence"))
                    and all(
                        _repository_file(root, path) is not None
                        for path in item.get("test_evidence") or []
                    )
                )
            )
            for item in (registry or {}).get("features") or []
            if isinstance(item, dict)
        )
    )
    canonical_ok = bool(
        canonical
        and metadata.get("product") == PRODUCT
        and evidence_id
        and run_id
        and run_id == manifest_run_id
        and configuration_hash
        and configuration_hash == manifest_configuration_hash
        and metric_registry_version
        and dataset_digest
    )
    dq_ok = bool(
        data_quality.get("status") == "PASS"
        and data_quality.get("publication_allowed") is True
        and (run_manifest or {}).get("publication_allowed") is True
    )
    gates = [
        _gate(
            "canonical_evidence",
            True,
            canonical_ok,
            "PASS" if canonical_ok else "FAIL",
            _portable(canonical_path, root),
        ),
        _gate(
            "data_quality_publication",
            True,
            dq_ok,
            "PASS" if dq_ok else "FAIL",
            data_quality,
        ),
        _gate(
            "openapi_contract",
            True,
            openapi_summary["status"] == "PASS",
            openapi_summary["status"],
            openapi_summary["validation_errors"],
        ),
        _gate(
            "feature_truth_registry",
            True,
            feature_registry_valid,
            "PASS" if feature_registry_valid else "FAIL",
            dict(feature_counts),
        ),
        _gate(
            "backend_frontend_e2e_tests",
            True,
            tests["status"] == "PASS",
            tests["status"],
            tests["validation_errors"],
        ),
        _gate(
            "security_controls",
            True,
            security_summary["status"] in {"PASS", "PASS_WITH_EXTERNAL_BOUNDARIES"},
            security_summary["status"],
            security_summary["validation_errors"],
        ),
        _gate(
            "performance_reported",
            True,
            benchmark["status"] in {"PASS", "PASS_WITH_EXTERNAL_BOUNDARIES"},
            benchmark["status"],
            benchmark["validation_errors"],
        ),
        _gate(
            "core_artifact_manifest_contract",
            True,
            artifacts["status"] == "PASS",
            artifacts["status"],
            artifacts["summary"],
        ),
        _gate(
            "core_cross_artifact_reconciliation",
            True,
            reconciliation_summary["status"] in {"PASS", "PASS_WITH_NON_CORE_BOUNDARIES"},
            reconciliation_summary["status"],
            reconciliation_summary["validation_errors"],
        ),
    ]
    release_allowed = all(gate["passed"] for gate in gates if gate["required"])
    source_records = {
        "canonical_evidence": _source(canonical_path, root, canonical_error),
        "run_manifest": _source(manifest_path, root, manifest_error),
        "openapi_validation": _source(openapi_path, root, openapi_error),
        "openapi_contract": openapi_summary["contract"],
        "feature_registry": _source(registry_path, root, registry_error),
        "performance": _source(performance_path, root, performance_error),
        "security_tests": security_summary["sources"]["security_tests"],
        "security_scan": security_summary["sources"]["security_scan"],
        "npm_audit": security_summary["sources"]["npm_audit"],
        "package_lock": security_summary["sources"]["package_lock"],
        "test_results": tests["source"],
        "reconciliation": reconciliation_summary["source"],
    }
    artifact_hashes = {
        item["path"]: item["sha256"]
        for item in artifacts["expected_release_artifacts"]
        if item["sha256"] is not None
    }
    limitations: list[str] = [str(item) for item in (canonical or {}).get("limitations") or []]
    limitations.extend(
        f"{feature.get('name')}: {feature.get('limitation')}"
        for feature in (registry or {}).get("features") or []
        if isinstance(feature, dict)
        and feature.get("status") != "LIVE"
        and feature.get("limitation")
    )
    limitations.extend(str(item) for item in security_summary["known_residual_risks"])
    limitations.extend(
        f"Performance boundary: {item}" for item in benchmark["external_execution_operations"]
    )
    limitations.extend(
        f"Release gate {gate['gate_id']} is {gate['status']}."
        for gate in gates
        if gate["required"] and not gate["passed"]
    )
    release_id = f"NAIM-{run_id or 'UNAVAILABLE'}-{source_control['working_tree_hash'][:12]}"
    evidence = {
        "schema_version": SCHEMA_VERSION,
        "evidence_phase": "CORE_DECISION",
        "product": PRODUCT,
        "release_id": release_id,
        "build_timestamp": generated,
        "release_allowed": release_allowed,
        "release_status": "PASS" if release_allowed else "BLOCKED",
        "source_control": source_control,
        "environment": _environment(),
        "dataset": {
            "profile": (run_manifest or {}).get("profile") or metadata.get("profile"),
            "random_seed": (run_manifest or {}).get("random_seed"),
            "dataset_hash": dataset_digest,
            "dataset_hash_basis": dataset_basis,
            "configuration_hash": manifest_configuration_hash or configuration_hash,
            "metric_registry_version": metric_registry_version,
            "run_id": manifest_run_id or run_id,
            "account_count": row_counts.get("customer_account_master"),
            "account_month_count": row_counts.get("monthly_account_performance"),
            "strategy_decision_count": row_counts.get("strategy_decision_fact"),
            "related_table_counts": {
                key: row_counts.get(key)
                for key in (
                    "partner_master",
                    "partner_monthly_performance",
                    "vendor_master",
                    "vendor_monthly_performance",
                    "membership_master",
                    "customer_membership_history",
                    "benefit_master",
                    "benefit_usage_fact",
                )
            },
            "minimum_data_date": (run_manifest or {}).get("minimum_data_date")
            or metadata.get("minimum_date"),
            "maximum_data_date": (run_manifest or {}).get("maximum_data_date")
            or metadata.get("as_of"),
            "synthetic_data": (run_manifest or {}).get("synthetic_data", metadata.get("synthetic")),
        },
        "data_quality": {
            "score": data_quality.get("score"),
            "status": data_quality.get("status"),
            "publication_allowed": data_quality.get("publication_allowed"),
            "rejected_row_counts": (run_manifest or {}).get("rejected_row_counts"),
        },
        "tests": tests,
        "coverage": tests["coverage"],
        "api_contract": {
            **openapi_summary,
            "frontend_route_count": len(
                {
                    route
                    for feature in (registry or {}).get("features") or []
                    if isinstance(feature, dict)
                    for route in feature.get("frontend_route") or []
                }
            ),
        },
        "feature_status": {
            "registry_version": (registry or {}).get("registry_version"),
            "total": sum(feature_counts.values()),
            "counts": dict(sorted(feature_counts.items())),
        },
        "benchmark_summary": benchmark,
        "security_summary": security_summary,
        "principal_analytical_findings": _principal_findings(canonical),
        "artifact_scope": "CORE_PRE_DECISION",
        "artifact_inventory": artifacts,
        "artifact_hashes": artifact_hashes,
        "reconciliation_results": reconciliation_summary,
        "release_gates": gates,
        "external_runtime_boundaries": list(EXTERNAL_BOUNDARIES),
        "known_limitations": list(dict.fromkeys(item for item in limitations if item.strip())),
        "source_artifacts": source_records,
    }
    evidence["input_fingerprint"] = _input_fingerprint(
        source_records, artifact_hashes, tests.get("invocation_id")
    )
    matrix = _readiness_matrix(root, registry_path, registry, release_allowed, generated)
    return evidence, matrix


def _validate_core_snapshot(root: Path, core: dict[str, Any] | None) -> list[str]:
    errors: list[str] = []
    if not core:
        return ["immutable core evidence is missing or malformed"]
    if core.get("schema_version") != SCHEMA_VERSION:
        errors.append("immutable core evidence has an unsupported schema_version")
    if core.get("evidence_phase") != "CORE_DECISION":
        errors.append("immutable core evidence has the wrong evidence_phase")
    if core.get("release_allowed") is not True or core.get("release_status") != "PASS":
        errors.append("immutable core evidence did not record a passing core decision")
    gates = core.get("release_gates")
    if (
        not isinstance(gates, list)
        or not gates
        or any(
            not isinstance(gate, dict)
            or gate.get("required") is not True
            or gate.get("passed") is not True
            for gate in gates
        )
    ):
        errors.append("immutable core evidence contains a non-passing required gate")
    sources = core.get("source_artifacts")
    sources = sources if isinstance(sources, dict) else {}
    if not sources:
        errors.append("immutable core evidence has no source-artifact bindings")
    for name, record in sorted(sources.items()):
        errors.extend(_validate_file_record(root, record, label=f"core source {name}"))
    hashes = core.get("artifact_hashes")
    hashes = hashes if isinstance(hashes, dict) else {}
    if set(hashes) != {f"outputs/{name}" for name in CORE_RELEASE_ARTIFACTS}:
        errors.append("immutable core evidence does not hash exactly the core artifact set")
    for raw_path, expected_hash in sorted(hashes.items()):
        artifact = _repository_file(root, raw_path)
        if artifact is None or expected_hash != _sha256(artifact):
            errors.append(f"immutable core artifact is missing or changed: {raw_path}")
    expected_fingerprint = _input_fingerprint(
        sources,
        hashes,
        _nested(core, "tests.invocation_id"),
    )
    if core.get("input_fingerprint") != expected_fingerprint:
        errors.append("immutable core evidence input_fingerprint is inconsistent")
    return errors


def build_final_release_envelope(root: Path, *, generated_at: str | None = None) -> dict[str, Any]:
    """Verify immutable core evidence plus every post-decision release artifact."""

    root = root.resolve()
    generated = generated_at or _utc_now()
    reference_time = _parse_timestamp(generated) or datetime.now(UTC)
    core_path = root / "outputs" / CORE_EVIDENCE_NAME
    core, core_error = _read_json(core_path)
    core_errors = _validate_core_snapshot(root, core)
    if core_error:
        core_errors.insert(0, f"immutable core evidence: {core_error}")

    canonical_path = root / "exports" / "validation" / "interop_evidence_snapshot.json"
    canonical, canonical_error = _read_json(canonical_path)
    manifest_path = _manifest_path(root, canonical)
    run_manifest, manifest_error = _read_json(manifest_path)
    dataset_digest, _ = _dataset_hash(manifest_path, run_manifest, root)
    metadata = (canonical or {}).get("metadata") or {}
    run_id = str(metadata.get("run_id") or "") or None
    configuration_hash = metadata.get("configuration_hash")
    metric_registry_version = metadata.get("metric_registry_version")
    evidence_id = str((canonical or {}).get("evidence_id") or "") or None
    inventory = _artifact_inventory(
        root,
        EXPECTED_RELEASE_ARTIFACTS,
        dataset_hash=dataset_digest,
        configuration_hash=configuration_hash,
        metric_registry_version=metric_registry_version,
        run_id=run_id,
        evidence_id=evidence_id,
        post_decision_names=set(POST_DECISION_RELEASE_ARTIFACTS),
    )

    final_reconciliation_path = (
        root / "outputs" / "validation" / "final_cross_artifact_reconciliation.json"
    )
    final_reconciliation, final_reconciliation_error = _read_json(final_reconciliation_path)
    final_reconciliation_summary = _reconciliation_summary(
        root,
        final_reconciliation_path,
        final_reconciliation,
        final_reconciliation_error,
        reference_time,
        canonical_path=canonical_path,
        dataset_hash=dataset_digest,
        run_id=run_id,
        configuration_hash=configuration_hash,
        final_phase=True,
    )
    ui_channel = next(
        (
            item
            for item in final_reconciliation_summary["channel_results"]
            if item.get("channel_id") == "ui_snapshot"
        ),
        None,
    )
    ui_evidence_ok = bool(
        ui_channel
        and ui_channel.get("declared_status") == "PASS"
        and ui_channel.get("status") == "PASS"
        and int(ui_channel.get("artifact_count") or 0) > 0
    )
    reconciliation_ok = final_reconciliation_summary["status"] in {
        "PASS",
        "PASS_WITH_NON_CORE_BOUNDARIES",
    }
    gates = [
        _gate(
            "immutable_core_decision",
            True,
            not core_errors,
            "PASS" if not core_errors else "FAIL",
            core_errors,
        ),
        _gate(
            "final_artifact_manifest_contract",
            True,
            inventory["status"] == "PASS",
            inventory["status"],
            inventory["summary"],
        ),
        _gate(
            "final_cross_artifact_reconciliation",
            True,
            reconciliation_ok,
            final_reconciliation_summary["status"],
            final_reconciliation_summary["validation_errors"],
        ),
        _gate(
            "browser_validated_ui_evidence",
            True,
            ui_evidence_ok,
            "PASS" if ui_evidence_ok else "FAIL",
            ui_channel,
        ),
    ]
    release_allowed = all(gate["passed"] for gate in gates)
    limitations = list((core or {}).get("known_limitations") or [])
    limitations.extend(
        f"Final gate {gate['gate_id']} is {gate['status']}." for gate in gates if not gate["passed"]
    )
    artifact_hashes = {
        item["path"]: item["sha256"]
        for item in inventory["expected_release_artifacts"]
        if item["sha256"] is not None
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "evidence_phase": "FINAL_ENVELOPE",
        "product": PRODUCT,
        "release_id": (core or {}).get("release_id"),
        "generated_at": generated,
        "release_allowed": release_allowed,
        "release_status": "PASS" if release_allowed else "BLOCKED",
        "verification_order": list(FINAL_VERIFICATION_ORDER),
        "core_evidence": {
            **_source(core_path, root, core_error),
            "release_allowed": (core or {}).get("release_allowed"),
            "input_fingerprint": (core or {}).get("input_fingerprint"),
            "validation_errors": core_errors,
        },
        "final_artifact_inventory": inventory,
        "artifact_hashes": artifact_hashes,
        "final_reconciliation": final_reconciliation_summary,
        "release_gates": gates,
        "external_runtime_boundaries": (core or {}).get(
            "external_runtime_boundaries", list(EXTERNAL_BOUNDARIES)
        ),
        "known_limitations": list(dict.fromkeys(item for item in limitations if item)),
        "source_artifacts": {
            "core_evidence": _source(core_path, root, core_error),
            "canonical_evidence": _source(canonical_path, root, canonical_error),
            "run_manifest": _source(manifest_path, root, manifest_error),
            "final_reconciliation": final_reconciliation_summary["source"],
        },
    }


def _markdown(evidence: dict[str, Any]) -> str:
    decision = (
        "PASS — core release allowed"
        if evidence["release_allowed"]
        else ("BLOCKED — core release not allowed")
    )
    dataset = evidence["dataset"]
    lines = [
        "# nAIM Core Release Validation",
        "",
        f"**Decision: {decision}.**",
        "",
        "This immutable decision is produced before the readiness workbook, research package, ",
        "GitHub package, screenshots package, and final verification envelope. Those artifacts ",
        "may consume this core evidence; this core evidence never consumes them.",
        "",
        f"Release ID: `{evidence['release_id']}`  ",
        f"Built: `{evidence['build_timestamp']}`  ",
        f"Input fingerprint: `{evidence['input_fingerprint']}`",
        "",
        "## Required core gates",
        "",
        "| Gate | Status | Passed |",
        "|---|---:|---:|",
    ]
    lines.extend(
        f"| {gate['gate_id']} | {gate['status']} | {'Yes' if gate['passed'] else 'No'} |"
        for gate in evidence["release_gates"]
    )
    lines.extend(
        [
            "",
            "## Canonical lineage",
            "",
            f"- Profile / run: `{dataset.get('profile')}` / `{dataset.get('run_id')}`",
            f"- Dataset hash: `{dataset.get('dataset_hash')}` ({dataset.get('dataset_hash_basis')})",
            f"- Configuration hash: `{dataset.get('configuration_hash')}`",
            f"- DQ: `{evidence['data_quality'].get('status')}`; publication `{evidence['data_quality'].get('publication_allowed')}`",
            f"- Tests: `{evidence['tests'].get('status')}`; invocation `{evidence['tests'].get('invocation_id')}`",
            f"- Coverage: `{evidence['coverage'].get('percent')}` percent",
            f"- Performance: `{evidence['benchmark_summary'].get('status')}`",
            f"- Security: `{evidence['security_summary'].get('status')}`",
            f"- Core artifacts: {evidence['artifact_inventory']['summary']['manifested_and_valid_count']} / {evidence['artifact_inventory']['summary']['expected_count']}",
            "",
            "## Known limitations",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in evidence["known_limitations"])
    if not evidence["known_limitations"]:
        lines.append("- None recorded.")
    lines.append("")
    return "\n".join(lines)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def write_release_outputs(
    root: Path,
    output_root: Path | None = None,
    *,
    phase: str = "core",
    replace_core: bool = False,
) -> dict[str, Any]:
    root = root.resolve()
    output = (output_root or root / "outputs").resolve()
    if not output.is_relative_to(root):
        raise ValueError("Output root must remain inside the repository")
    output.mkdir(parents=True, exist_ok=True)
    if phase == "final":
        envelope = build_final_release_envelope(root)
        final_path = output / FINAL_EVIDENCE_NAME
        _atomic_write(final_path, json.dumps(envelope, indent=2, sort_keys=True) + "\n")
        return {
            "phase": "final",
            "release_allowed": envelope["release_allowed"],
            "release_status": envelope["release_status"],
            "outputs": [str(final_path)],
        }
    if phase != "core":
        raise ValueError(f"Unknown release-evidence phase: {phase}")
    evidence, matrix = build_release_evidence(root)
    core_path = output / CORE_EVIDENCE_NAME
    if core_path.is_file() and not replace_core:
        existing, existing_error = _read_json(core_path)
        if existing_error is None and (existing or {}).get("release_allowed") is True:
            return {
                "phase": "core",
                "release_allowed": False,
                "release_status": "IMMUTABLE_CORE_EXISTS",
                "immutable_conflict": True,
                "outputs": [str(core_path)],
                "message": (
                    "A passing immutable core decision already exists. Use --phase final, or "
                    "explicitly invalidate it with --replace-core before creating a new decision."
                ),
            }
    validation_path = output / VALIDATION_NAME
    matrix_path = output / READINESS_JSON_NAME
    _atomic_write(core_path, json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    _atomic_write(validation_path, _markdown(evidence))
    _atomic_write(matrix_path, json.dumps(matrix, indent=2, sort_keys=True) + "\n")
    return {
        "phase": "core",
        "release_allowed": evidence["release_allowed"],
        "release_status": evidence["release_status"],
        "immutable_conflict": False,
        "outputs": [str(core_path), str(validation_path), str(matrix_path)],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument(
        "--phase",
        choices=("core", "final"),
        default="core",
        help="Write the immutable core decision or verify it into the final one-way envelope.",
    )
    parser.add_argument(
        "--replace-core",
        action="store_true",
        help="Explicitly invalidate and replace an existing passing core decision.",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.phase == "final" and args.replace_core:
        raise SystemExit("--replace-core is only valid with --phase core")
    result = write_release_outputs(
        args.repository_root,
        args.output_root,
        phase=args.phase,
        replace_core=args.replace_core,
    )
    print(json.dumps(result, indent=2))
    return 0 if result["release_allowed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
