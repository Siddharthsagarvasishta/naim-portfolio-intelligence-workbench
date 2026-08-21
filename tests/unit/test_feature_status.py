from __future__ import annotations

from copy import deepcopy

from scripts.validate_feature_status import (
    DEFAULT_DOCUMENTATION,
    REPOSITORY_ROOT,
    load_registry,
    status_counts,
    validate_document_sync,
    validate_registry,
)


def test_repository_registry_and_documentation_validate() -> None:
    registry = load_registry()
    registry_errors = validate_registry(registry, REPOSITORY_ROOT)
    documentation_errors = validate_document_sync(
        registry,
        DEFAULT_DOCUMENTATION.read_text(encoding="utf-8"),
    )

    assert registry_errors == []
    assert documentation_errors == []
    assert sum(status_counts(registry).values()) == len(registry["features"])


def test_unknown_status_is_rejected() -> None:
    registry = deepcopy(load_registry())
    registry["features"][0]["status"] = "PARTIAL"

    errors = validate_registry(registry, REPOSITORY_ROOT)

    assert any("status is not allowed" in error for error in errors)


def test_duplicate_feature_id_is_rejected() -> None:
    registry = deepcopy(load_registry())
    registry["features"][1]["feature_id"] = registry["features"][0]["feature_id"]

    errors = validate_registry(registry, REPOSITORY_ROOT)

    assert any("Duplicate feature_id" in error for error in errors)


def test_missing_evidence_path_is_rejected() -> None:
    registry = deepcopy(load_registry())
    registry["features"][0]["calculation_module"] = ["scripts/not-present.py"]

    errors = validate_registry(registry, REPOSITORY_ROOT)

    assert any("evidence path does not exist" in error for error in errors)


def test_live_claim_requires_focused_test_evidence() -> None:
    registry = deepcopy(load_registry())
    registry["features"][0]["test_evidence"] = []

    errors = validate_registry(registry, REPOSITORY_ROOT)

    assert any("LIVE but has no focused test evidence" in error for error in errors)


def test_documented_claim_cannot_expose_an_executable_surface() -> None:
    registry = deepcopy(load_registry())
    documented = next(
        feature for feature in registry["features"] if feature["status"] == "DOCUMENTED"
    )
    documented["backend_endpoint"] = ["/api/v1/unsupported"]

    errors = validate_registry(registry, REPOSITORY_ROOT)

    assert any("DOCUMENTED but makes an executable or tested claim" in error for error in errors)


def test_not_implemented_claim_cannot_carry_execution_evidence() -> None:
    registry = deepcopy(load_registry())
    missing = next(
        feature for feature in registry["features"] if feature["status"] == "NOT_IMPLEMENTED"
    )
    missing["test_evidence"] = ["tests/unit/test_feature_status.py"]

    errors = validate_registry(registry, REPOSITORY_ROOT)

    assert any("NOT_IMPLEMENTED but claims evidence" in error for error in errors)


def test_documentation_status_drift_is_rejected() -> None:
    registry = load_registry()
    documentation = DEFAULT_DOCUMENTATION.read_text(encoding="utf-8").replace(
        "| `CAPABILITY_STATUS_REGISTRY` | `LIVE` |",
        "| `CAPABILITY_STATUS_REGISTRY` | `DOCUMENTED` |",
        1,
    )

    errors = validate_document_sync(registry, documentation)

    assert any("out of sync for CAPABILITY_STATUS_REGISTRY" in error for error in errors)
