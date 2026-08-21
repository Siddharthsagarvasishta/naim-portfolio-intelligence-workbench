from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.generate_release_evidence import (
    ALLOWED_CLASSIFICATIONS,
    CORE_EVIDENCE_NAME,
    CORE_RELEASE_ARTIFACTS,
    FINAL_EVIDENCE_NAME,
    FINAL_VERIFICATION_ORDER,
    MANIFEST_FIELDS,
    POST_DECISION_RELEASE_ARTIFACTS,
    _authored_source_binding,
    _dataset_hash,
    build_final_release_envelope,
    build_release_evidence,
    write_release_outputs,
)


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_record(path: Path, root: Path, **extra: object) -> dict[str, object]:
    return {
        "path": path.relative_to(root).as_posix(),
        "status": "AVAILABLE",
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "modified_at": datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat(),
        **extra,
    }


def _manifest_payload(
    root: Path,
    *,
    filename: str,
    index: int,
    dataset_hash: str,
    core_dependency: bool = False,
) -> dict[str, object]:
    run_id = "default-73421-fixture"
    artifact = root / "outputs" / filename
    canonical = root / "exports/validation/interop_evidence_snapshot.json"
    run_manifest = root / f"data/manifests/{run_id}/run_manifest.json"
    dependencies = [
        canonical.relative_to(root).as_posix(),
        run_manifest.relative_to(root).as_posix(),
    ]
    source_inputs = [file_record(canonical, root)]
    if core_dependency:
        core = root / "outputs" / CORE_EVIDENCE_NAME
        dependencies.append(core.relative_to(root).as_posix())
        source_inputs.append(file_record(core, root))
    validation_status = (
        "STATIC_VALIDATION_PASS"
        if filename
        in {
            "nAIM_PowerBI_Desktop_Package.zip",
            "nAIM_SAS_Compatibility_Package.zip",
        }
        else "PASS"
    )
    payload: dict[str, object] = {
        "schema_version": "2.0.0",
        "artifact_id": f"ART-{index:03d}",
        "artifact_type": "TEST_ARTIFACT",
        "artifact_version": "1.0.0",
        "created_at": datetime.now(UTC).isoformat(),
        "created_by_component": "fixture",
        "source_workspace": "all_portfolio_control",
        "source_snapshot_id": run_id,
        "reporting_period": "2025-08-01",
        "comparison_period": "2025-07-01",
        "filter_scope": {"scope": "All portfolio"},
        "dataset_profile": "default",
        "dataset_hash": dataset_hash,
        "configuration_hash": "config-hash",
        "metric_registry_version": "2.0.0",
        "code_version": "fixture-code",
        "evidence_ids": [f"NAIM-{run_id}"],
        "data_quality_status": "PASS",
        "synthetic_data_flag": True,
        "file_name": filename,
        "file_size": artifact.stat().st_size,
        "sha256": sha256(artifact),
        "dependencies": dependencies,
        "validation_status": validation_status,
        "validation_tests": ["fixture validation"],
        "known_limitations": ["Synthetic fixture."],
        "artifact": {
            "path": f"outputs/{filename}",
            "bytes": artifact.stat().st_size,
            "sha256": sha256(artifact),
        },
        "source_inputs": source_inputs,
        "validation_evidence": [],
    }
    assert MANIFEST_FIELDS <= set(payload)
    return payload


def _write_artifacts_and_manifests(
    root: Path,
    names: tuple[str, ...],
    dataset_hash: str,
    *,
    core_dependency: bool = False,
) -> None:
    for index, filename in enumerate(names):
        artifact = root / "outputs" / filename
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(f"artifact-{filename}-{index}\n".encode())
        write_json(
            root / "outputs/manifests" / f"{filename}.manifest.json",
            _manifest_payload(
                root,
                filename=filename,
                index=index,
                dataset_hash=dataset_hash,
                core_dependency=core_dependency,
            ),
        )


def _reconciliation_payload(
    root: Path,
    *,
    generated_at: str,
    final: bool = False,
) -> dict[str, object]:
    canonical = root / "exports/validation/interop_evidence_snapshot.json"
    ui = root / "outputs/validation/ui_evidence_snapshot.json"
    channel_order = (
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
    channels: list[dict[str, object]] = []
    for channel_id in channel_order:
        if channel_id == "streamlit_snapshot" or (channel_id == "ui_snapshot" and not final):
            channels.append(
                {
                    "channel_id": channel_id,
                    "required": True,
                    "status": "INCOMPLETE",
                    "artifact_paths": [],
                    "artifacts": [],
                    "checks": [
                        {
                            "check_id": f"{channel_id}.artifact_present",
                            "required": True,
                            "outcome": "MISSING",
                            "expected": "runtime evidence",
                            "actual": None,
                        }
                    ],
                }
            )
            continue
        artifact = ui if channel_id == "ui_snapshot" else canonical
        channels.append(
            {
                "channel_id": channel_id,
                "required": True,
                "status": "PASS",
                "artifact_paths": [artifact.relative_to(root).as_posix()],
                "artifacts": [
                    {
                        "path": artifact.relative_to(root).as_posix(),
                        "bytes": artifact.stat().st_size,
                        "sha256": sha256(artifact),
                    }
                ],
                "checks": [
                    {
                        "check_id": f"{channel_id}.fixture",
                        "required": True,
                        "outcome": "PASS",
                        "expected": "fixture",
                        "actual": "fixture",
                    }
                ],
            }
        )
    incomplete = ["streamlit_snapshot"] if final else ["ui_snapshot", "streamlit_snapshot"]
    return {
        "schema_version": "1.0.0",
        "generated_at_utc": generated_at,
        "result": "INCOMPLETE",
        "release_allowed": False,
        "canonical": {
            "source_path": canonical.relative_to(root).as_posix(),
            "source_file_sha256": sha256(canonical),
            "dataset_hash": "fixture-dataset-hash-placeholder",
            "story": {
                "run_id": "default-73421-fixture",
                "configuration_hash": "config-hash",
                "dataset_hash": "fixture-dataset-hash-placeholder",
            },
        },
        "channels": channels,
        "summary": {
            "required_channel_count": len(channel_order),
            "missing_or_incomplete_channels": incomplete,
        },
    }


def _write_release_test_results(root: Path) -> None:
    invocation = "fixture-invocation"
    started_at = datetime.now(UTC).isoformat()
    junit = root / "outputs/validation/backend_junit.xml"
    coverage = root / "outputs/validation/backend_coverage.json"
    junit.write_text(
        '<testsuites tests="4" failures="0" errors="0" skipped="1"/>',
        encoding="utf-8",
    )
    write_json(coverage, {"totals": {"percent_covered": 91.2}})
    canonical = root / "exports/validation/interop_evidence_snapshot.json"
    run_manifest = root / "data/manifests/default-73421-fixture/run_manifest.json"
    bindings = {
        "status": "PASS",
        "source_tree": _authored_source_binding(root),
        "package_lock": file_record(root / "package-lock.json", root),
        "configuration": file_record(root / "config/feature_status.yaml", root),
        "canonical_evidence": file_record(canonical, root),
        "run_manifest": file_record(run_manifest, root),
        "openapi_contract": file_record(root / "outputs/contracts/openapi.json", root),
        "openapi_validation": file_record(root / "outputs/contracts/openapi_validation.json", root),
        "reconciliation": file_record(
            root / "outputs/validation/cross_artifact_reconciliation.json", root
        ),
    }
    invocation_fields = {
        "invocation_id": invocation,
        "generated_in_invocation": True,
    }
    suites = [
        {
            "name": "backend",
            "category": "backend",
            "status": "PASS",
            "passed": 300,
            "failed": 0,
            "skipped": 1,
            "warnings": 2,
            "duration_seconds": 2.0,
            "exit_code": 0,
            "evidence": {
                "junit_summary": {
                    "status": "AVAILABLE",
                    "tests": 301,
                    "passed": 300,
                    "failed": 0,
                    "skipped": 1,
                },
                "junit_artifact": file_record(junit, root, **invocation_fields),
            },
        },
        {
            "name": "frontend",
            "category": "frontend",
            "status": "PASS",
            "passed": 30,
            "failed": 0,
            "skipped": 0,
            "warnings": 0,
            "duration_seconds": 3.0,
            "exit_code": 0,
            "evidence": {},
        },
        {
            "name": "e2e",
            "category": "e2e",
            "status": "PASS",
            "passed": 10,
            "failed": 0,
            "skipped": 0,
            "warnings": 0,
            "duration_seconds": 1.0,
            "exit_code": 0,
            "evidence": {},
        },
    ]
    write_json(
        root / "outputs/validation/test_results.json",
        {
            "schema_version": "1.0.0",
            "invocation_id": invocation,
            "started_at": started_at,
            "generated_at": datetime.now(UTC).isoformat(),
            "status": "PASS",
            "release_gate_passed": True,
            "selected_suites": ["backend", "frontend", "e2e"],
            "suites": suites,
            "coverage": {
                "status": "AVAILABLE",
                "percent": 91.2,
                "scope": "full backend suite",
                "source": "outputs/validation/backend_coverage.json",
                "invocation_id": invocation,
                "artifact": file_record(coverage, root, **invocation_fields),
            },
            "bindings": bindings,
        },
    )


def build_complete_fixture(root: Path) -> str:
    now = datetime.now(UTC)
    generated_at = now.isoformat()
    run_id = "default-73421-fixture"
    canonical = {
        "schema_version": "1.0.0",
        "evidence_id": f"NAIM-{run_id}",
        "selected_reporting_period": "2025-08-01",
        "synthetic_data_flag": True,
        "metadata": {
            "product": "nAIM Portfolio Intelligence Workbench",
            "run_id": run_id,
            "profile": "default",
            "configuration_hash": "config-hash",
            "metric_registry_version": "2.0.0",
            "synthetic": True,
            "row_counts": {
                "customer_account_master": 25_000,
                "monthly_account_performance": 513_923,
                "strategy_decision_fact": 513_573,
            },
        },
        "data_quality": {"status": "PASS", "score": 100.0, "publication_allowed": True},
        "kpis": [
            {
                "metric_id": "ACTIVE_ACCOUNTS",
                "value": 22_531,
                "prior_value": 22_761,
                "unit": "accounts",
                "comparison_period": "2025-07-01",
            }
        ],
        "root_cause": {
            "finding": {
                "observed_change_bps": 311.415,
                "mix_contribution_bps": 4.4335,
                "within_segment_contribution_bps": 306.9815,
                "reconciliation_residual_bps": 0.0,
                "primary_driver": "Affiliate",
                "primary_dimension": "acquisition_channel",
                "causal_status": "ASSOCIATIONAL",
            }
        },
        "strategy_comparison": {
            "recommendation": {
                "decision": "Investigate",
                "approval_required": True,
                "notice": "Human approval required.",
            }
        },
        "limitations": ["Synthetic data only."],
    }
    write_json(root / "exports/validation/interop_evidence_snapshot.json", canonical)
    run_manifest_path = root / f"data/manifests/{run_id}/run_manifest.json"
    write_json(
        run_manifest_path,
        {
            "run_id": run_id,
            "profile": "default",
            "random_seed": 73421,
            "configuration_hash": "config-hash",
            "publication_allowed": True,
            "validation_status": "PASS",
            "synthetic_data": True,
            "minimum_data_date": "2024-01-01",
            "maximum_data_date": "2025-12-01",
            "rejected_row_counts": {},
            "row_counts": canonical["metadata"]["row_counts"],
            "paths": {},
        },
    )
    dataset_hash, _ = _dataset_hash(
        run_manifest_path, json.loads(run_manifest_path.read_text()), root
    )
    assert dataset_hash

    package_lock = root / "package-lock.json"
    package_lock.write_text('{"lockfileVersion": 3}\n', encoding="utf-8")
    for relative in ("tests/unit/test_live.py", "src/naim_risk/live.py", "docs/live.md"):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("fixture\n", encoding="utf-8")
    registry = {
        "schema_version": "1.1.0",
        "registry_version": "2.0.0",
        "allowed_statuses": ["LIVE", "INTEGRATION_ONLY", "NOT_IMPLEMENTED"],
        "features": [
            {
                "feature_id": "CORE",
                "name": "Core portfolio analytics",
                "business_value": "Provides reproducible local portfolio decisions.",
                "status": "LIVE",
                "backend_endpoint": ["/api/v1/kpis"],
                "frontend_route": ["/"],
                "calculation_module": ["src/naim_risk/live.py"],
                "test_evidence": ["tests/unit/test_live.py"],
                "artifact_evidence": ["docs/live.md"],
                "limitation": "Synthetic data.",
            },
            {
                "feature_id": "POWERBI_DESKTOP_EXPORT",
                "name": "Power BI Desktop export",
                "status": "INTEGRATION_ONLY",
                "test_evidence": [],
                "artifact_evidence": [],
                "limitation": "Desktop runtime not executed here.",
            },
            {
                "feature_id": "COX_MODEL",
                "name": "Cox proportional-hazards model",
                "status": "NOT_IMPLEMENTED",
                "test_evidence": [],
                "artifact_evidence": [],
                "limitation": "No implementation exists.",
            },
        ],
    }
    write_json(root / "config/feature_status.yaml", registry)
    contract = root / "outputs/contracts/openapi.json"
    write_json(contract, {"openapi": "3.1.0", "paths": {"/api/v1/health": {}}})
    write_json(
        root / "outputs/contracts/openapi_validation.json",
        {
            "status": "PASS",
            "errors": [],
            "contract": "outputs/contracts/openapi.json",
            "operation_count": 110,
            "operation_id_count": 110,
            "api_v1_operation_count": 109,
            "path_count": 104,
            "declared_http_501_count": 0,
            "sha256": sha256(contract),
        },
    )
    measured = {
        "status": "MEASURED",
        "repetitions": 3,
        "timing_ms": {"median": 10.0, "p95": 12.0, "samples": [9.0, 10.0, 12.0]},
    }
    external = {
        "status": "EXTERNAL_EXECUTION_REQUIRED",
        "repetitions": 3,
        "reason": "Local process unavailable.",
        "rerun_requirement": "Run on a host that permits Hyper.",
    }
    write_json(
        root / "outputs/performance/performance-fixture.json",
        {
            "schema_version": "1.0.0",
            "generated_at_utc": generated_at,
            "fresh_run": True,
            "elapsed_seconds": 12.5,
            "repetitions_per_profile": 3,
            "requested_profiles": ["default"],
            "completeness": {
                "status": "PARTIAL",
                "unmeasured_operations": ["default/hyper_generation"],
            },
            "machine": {"python": "3.12.0"},
            "profiles": {
                "default": {
                    "dataset": {"account_month_rows": 513_923},
                    "operations": {
                        "command_centre_response": measured,
                        "hyper_generation": external,
                    },
                }
            },
            "validation": {"status": "PASS", "errors": []},
        },
    )
    write_json(
        root / "outputs/validation/security_test_results.json",
        {
            "overall_status": "PARTIAL",
            "overall_reason": "Licensed/external validation was unavailable.",
            "dependency_audit_refreshed_at_utc": generated_at,
            "focused_test_suite": {"status": "PASS", "passed": 20, "failed": 0},
            "uncompleted_security_validation": ["Licensed external scanner"],
            "known_residual_risks": ["External scanner was not run."],
        },
    )
    write_json(
        root / "outputs/validation/security_scan.json",
        {
            "status": "PASS_WITH_WARNINGS",
            "summary": {"errors": 0, "warnings": 1, "unreadable_files": 0},
        },
    )
    write_json(
        root / "outputs/validation/npm_audit_after_summary.json",
        {
            "executed_at_utc": generated_at,
            "status": "PASS",
            "release_decision": "PASS",
            "package_lock_sha256": sha256(package_lock),
            "vulnerability_counts": {
                "low": 0,
                "moderate": 0,
                "high": 0,
                "critical": 0,
                "total": 0,
            },
        },
    )
    _write_artifacts_and_manifests(root, CORE_RELEASE_ARTIFACTS, dataset_hash)
    reconciliation = _reconciliation_payload(root, generated_at=datetime.now(UTC).isoformat())
    reconciliation["canonical"]["dataset_hash"] = dataset_hash
    reconciliation["canonical"]["story"]["dataset_hash"] = dataset_hash
    write_json(root / "outputs/validation/cross_artifact_reconciliation.json", reconciliation)
    _write_release_test_results(root)
    return datetime.now(UTC).isoformat()


def test_complete_core_evidence_passes_with_explicit_non_core_boundaries(
    tmp_path: Path,
) -> None:
    generated_at = build_complete_fixture(tmp_path)

    evidence, matrix = build_release_evidence(tmp_path, generated_at=generated_at)

    assert evidence["evidence_phase"] == "CORE_DECISION"
    assert evidence["release_allowed"] is True
    assert all(gate["passed"] for gate in evidence["release_gates"])
    assert evidence["tests"]["status"] == "PASS"
    assert evidence["tests"]["selected_suites"] == ["backend", "frontend", "e2e"]
    assert evidence["coverage"]["percent"] == 91.2
    assert evidence["api_contract"]["status"] == "PASS"
    assert evidence["security_summary"]["status"] == "PASS_WITH_EXTERNAL_BOUNDARIES"
    assert evidence["benchmark_summary"]["status"] == "PASS_WITH_EXTERNAL_BOUNDARIES"
    assert evidence["reconciliation_results"]["status"] == ("PASS_WITH_NON_CORE_BOUNDARIES")
    assert evidence["artifact_inventory"]["summary"]["expected_count"] == len(
        CORE_RELEASE_ARTIFACTS
    )
    assert evidence["artifact_inventory"]["status"] == "PASS"
    assert set(evidence["artifact_hashes"]) == {
        f"outputs/{name}" for name in CORE_RELEASE_ARTIFACTS
    }
    assert len(evidence["input_fingerprint"]) == 64

    rows = {row["capability"]: row for row in matrix["capabilities"]}
    assert rows["Core portfolio analytics"]["final_classification"] == "LOCAL_LIVE"
    assert rows["Power BI Desktop export"]["final_classification"] == "DESKTOP_EXPORT"
    assert rows["Cox proportional-hazards model"]["final_classification"] == ("NOT_IMPLEMENTED")
    assert all(
        row["final_classification"] in ALLOWED_CLASSIFICATIONS for row in matrix["capabilities"]
    )


def test_missing_evidence_blocks_without_coverage_fallback(tmp_path: Path) -> None:
    (tmp_path / ".coverage").write_bytes(b"stale")

    evidence, matrix = build_release_evidence(tmp_path)

    assert evidence["release_allowed"] is False
    assert evidence["coverage"].get("percent") is None
    assert evidence["tests"]["status"] == "INCOMPLETE"
    assert evidence["artifact_inventory"]["status"] == "INCOMPLETE"
    assert matrix["release_allowed"] is False


def test_test_consumer_rejects_duplicate_suite_and_tampered_same_run_files(
    tmp_path: Path,
) -> None:
    generated_at = build_complete_fixture(tmp_path)
    path = tmp_path / "outputs/validation/test_results.json"
    payload = json.loads(path.read_text())
    payload["suites"][2]["name"] = "frontend"
    payload["suites"][2]["category"] = "frontend"
    write_json(path, payload)
    (tmp_path / "outputs/validation/backend_coverage.json").write_text(
        '{"totals":{"percent_covered":100}}\n', encoding="utf-8"
    )

    evidence, _ = build_release_evidence(tmp_path, generated_at=generated_at)

    assert evidence["release_allowed"] is False
    errors = evidence["tests"]["validation_errors"]
    assert any("uniquely named e2e" in item for item in errors)
    assert any("duplicate suite categories" in item for item in errors)
    assert any("coverage JSON: recorded SHA-256" in item for item in errors)


def test_test_consumer_rejects_stale_source_and_reconciliation_bindings(
    tmp_path: Path,
) -> None:
    generated_at = build_complete_fixture(tmp_path)
    (tmp_path / "src/naim_risk/live.py").write_text("changed\n", encoding="utf-8")
    reconciliation = tmp_path / "outputs/validation/cross_artifact_reconciliation.json"
    payload = json.loads(reconciliation.read_text())
    payload["channels"] = []
    payload["result"] = "PASS"
    payload["release_allowed"] = True
    write_json(reconciliation, payload)

    evidence, _ = build_release_evidence(tmp_path, generated_at=generated_at)

    assert evidence["release_allowed"] is False
    assert any(
        "source-tree binding is stale" in item for item in evidence["tests"]["validation_errors"]
    )
    assert evidence["reconciliation_results"]["status"] == "FAIL"
    assert any(
        "channel IDs/order" in item
        for item in evidence["reconciliation_results"]["validation_errors"]
    )


@pytest.mark.parametrize(
    ("field", "bad_value", "expected_error"),
    [
        ("created_by_component", None, "created_by_component is not a non-empty string"),
        ("validation_status", "PARTIAL", "strict runtime-classification allowlist"),
        ("dataset_hash", "forged", "dataset_hash does not match"),
    ],
)
def test_manifest_contract_rejects_null_partial_and_forged_provenance(
    tmp_path: Path,
    field: str,
    bad_value: object,
    expected_error: str,
) -> None:
    generated_at = build_complete_fixture(tmp_path)
    name = CORE_RELEASE_ARTIFACTS[0]
    manifest = tmp_path / "outputs/manifests" / f"{name}.manifest.json"
    payload = json.loads(manifest.read_text())
    payload[field] = bad_value
    write_json(manifest, payload)

    evidence, _ = build_release_evidence(tmp_path, generated_at=generated_at)

    row = next(
        item
        for item in evidence["artifact_inventory"]["expected_release_artifacts"]
        if item["file_name"] == name
    )
    assert row["manifest_status"] == "FAIL"
    assert any(expected_error in item for item in row["manifest"]["validation_errors"])
    assert evidence["release_allowed"] is False


def test_current_openapi_contract_and_package_lock_are_rehashed(
    tmp_path: Path,
) -> None:
    generated_at = build_complete_fixture(tmp_path)
    (tmp_path / "outputs/contracts/openapi.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "package-lock.json").write_text('{"changed":true}\n', encoding="utf-8")

    evidence, _ = build_release_evidence(tmp_path, generated_at=generated_at)

    assert evidence["api_contract"]["status"] == "FAIL"
    assert any(
        "recorded contract SHA-256 is stale" in item
        for item in evidence["api_contract"]["validation_errors"]
    )
    assert evidence["security_summary"]["status"] == "FAIL"
    assert any(
        "package-lock SHA-256" in item for item in evidence["security_summary"]["validation_errors"]
    )
    assert evidence["release_allowed"] is False


def test_performance_rejects_stale_report_and_invented_external_boundary(
    tmp_path: Path,
) -> None:
    generated_at = build_complete_fixture(tmp_path)
    path = tmp_path / "outputs/performance/performance-fixture.json"
    payload = json.loads(path.read_text())
    payload["generated_at_utc"] = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    payload["profiles"]["default"]["operations"]["cloud_publish"] = {
        "status": "EXTERNAL_EXECUTION_REQUIRED",
        "reason": "not run",
        "rerun_requirement": "run elsewhere",
    }
    payload["completeness"]["unmeasured_operations"].append("default/cloud_publish")
    write_json(path, payload)

    evidence, _ = build_release_evidence(tmp_path, generated_at=generated_at)

    assert evidence["benchmark_summary"]["status"] == "FAIL"
    errors = evidence["benchmark_summary"]["validation_errors"]
    assert any("older than 14 days" in item for item in errors)
    assert any("not an allowed external boundary" in item for item in errors)


def test_core_output_is_immutable_after_passing_decision(tmp_path: Path) -> None:
    build_complete_fixture(tmp_path)
    first = write_release_outputs(tmp_path)
    core = tmp_path / "outputs" / CORE_EVIDENCE_NAME
    first_hash = sha256(core)

    second = write_release_outputs(tmp_path)

    assert first["release_allowed"] is True
    assert second["release_allowed"] is False
    assert second["release_status"] == "IMMUTABLE_CORE_EXISTS"
    assert second["immutable_conflict"] is True
    assert sha256(core) == first_hash


def test_final_envelope_requires_real_ui_evidence_and_one_way_post_manifests(
    tmp_path: Path,
) -> None:
    generated_at = build_complete_fixture(tmp_path)
    assert write_release_outputs(tmp_path)["release_allowed"] is True
    core = json.loads((tmp_path / "outputs" / CORE_EVIDENCE_NAME).read_text())
    dataset_hash = core["dataset"]["dataset_hash"]
    _write_artifacts_and_manifests(
        tmp_path,
        POST_DECISION_RELEASE_ARTIFACTS,
        dataset_hash,
        core_dependency=True,
    )

    blocked = build_final_release_envelope(tmp_path, generated_at=generated_at)
    assert blocked["release_allowed"] is False
    assert (
        next(
            gate
            for gate in blocked["release_gates"]
            if gate["gate_id"] == "browser_validated_ui_evidence"
        )["passed"]
        is False
    )

    ui = tmp_path / "outputs/validation/ui_evidence_snapshot.json"
    write_json(ui, {"source": "rendered browser", "status": "PASS"})
    final_reconciliation = _reconciliation_payload(
        tmp_path, generated_at=datetime.now(UTC).isoformat(), final=True
    )
    final_reconciliation["canonical"]["dataset_hash"] = dataset_hash
    final_reconciliation["canonical"]["story"]["dataset_hash"] = dataset_hash
    write_json(
        tmp_path / "outputs/validation/final_cross_artifact_reconciliation.json",
        final_reconciliation,
    )

    envelope = build_final_release_envelope(tmp_path)

    assert envelope["release_allowed"] is True
    assert envelope["verification_order"] == list(FINAL_VERIFICATION_ORDER)
    assert envelope["final_reconciliation"]["status"] == ("PASS_WITH_NON_CORE_BOUNDARIES")
    streamlit = next(
        item
        for item in envelope["final_reconciliation"]["channel_results"]
        if item["channel_id"] == "streamlit_snapshot"
    )
    assert streamlit["declared_status"] == "INCOMPLETE"
    ui_result = next(
        item
        for item in envelope["final_reconciliation"]["channel_results"]
        if item["channel_id"] == "ui_snapshot"
    )
    assert ui_result["declared_status"] == "PASS"

    result = write_release_outputs(tmp_path, phase="final")
    assert result["release_allowed"] is True
    assert (tmp_path / "outputs" / FINAL_EVIDENCE_NAME).is_file()
    assert result["outputs"] == [str(tmp_path / "outputs" / FINAL_EVIDENCE_NAME)]


def test_post_decision_manifest_without_core_dependency_fails_final_envelope(
    tmp_path: Path,
) -> None:
    build_complete_fixture(tmp_path)
    assert write_release_outputs(tmp_path)["release_allowed"] is True
    core = json.loads((tmp_path / "outputs" / CORE_EVIDENCE_NAME).read_text())
    _write_artifacts_and_manifests(
        tmp_path,
        POST_DECISION_RELEASE_ARTIFACTS,
        core["dataset"]["dataset_hash"],
        core_dependency=True,
    )
    name = POST_DECISION_RELEASE_ARTIFACTS[0]
    manifest = tmp_path / "outputs/manifests" / f"{name}.manifest.json"
    payload = json.loads(manifest.read_text())
    payload["dependencies"] = [
        item for item in payload["dependencies"] if CORE_EVIDENCE_NAME not in item
    ]
    payload["source_inputs"] = [
        item for item in payload["source_inputs"] if CORE_EVIDENCE_NAME not in item["path"]
    ]
    write_json(manifest, payload)

    envelope = build_final_release_envelope(tmp_path)

    row = next(
        item
        for item in envelope["final_artifact_inventory"]["expected_release_artifacts"]
        if item["file_name"] == name
    )
    assert row["manifest_status"] == "FAIL"
    assert any(
        "not bound to immutable core evidence" in item
        for item in row["manifest"]["validation_errors"]
    )


def test_manifest_may_not_consume_final_envelope(tmp_path: Path) -> None:
    generated_at = build_complete_fixture(tmp_path)
    name = CORE_RELEASE_ARTIFACTS[0]
    manifest = tmp_path / "outputs/manifests" / f"{name}.manifest.json"
    payload = json.loads(manifest.read_text())
    forbidden = tmp_path / "outputs" / FINAL_EVIDENCE_NAME
    write_json(forbidden, {"not": "an allowed input"})
    payload["dependencies"].append(f"outputs/{FINAL_EVIDENCE_NAME}")
    write_json(manifest, payload)

    evidence, _ = build_release_evidence(tmp_path, generated_at=generated_at)

    row = next(
        item
        for item in evidence["artifact_inventory"]["expected_release_artifacts"]
        if item["file_name"] == name
    )
    assert any(
        "consumes the final envelope" in item for item in row["manifest"]["validation_errors"]
    )


def test_malformed_nested_types_block_instead_of_crashing(tmp_path: Path) -> None:
    generated_at = build_complete_fixture(tmp_path)
    audit_path = tmp_path / "outputs/validation/npm_audit_after_summary.json"
    audit = json.loads(audit_path.read_text())
    audit["vulnerability_counts"] = [0]
    write_json(audit_path, audit)
    performance_path = tmp_path / "outputs/performance/performance-fixture.json"
    performance = json.loads(performance_path.read_text())
    performance["requested_profiles"] = {"default": True}
    write_json(performance_path, performance)
    name = CORE_RELEASE_ARTIFACTS[0]
    manifest_path = tmp_path / "outputs/manifests" / f"{name}.manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["created_by_component"] = ["not", "a", "string"]
    write_json(manifest_path, manifest)

    evidence, _ = build_release_evidence(tmp_path, generated_at=generated_at)

    assert evidence["release_allowed"] is False
    assert evidence["security_summary"]["status"] == "FAIL"
    assert evidence["benchmark_summary"]["status"] == "FAIL"
    assert evidence["artifact_inventory"]["status"] == "INCOMPLETE"
