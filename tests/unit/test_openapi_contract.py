from __future__ import annotations

import json
from pathlib import Path

from naim_risk.api import app
from scripts.generate_openapi import check, enrich_contract, generate, validate_contract


def test_openapi_contract_has_unique_versioned_operations_and_no_501() -> None:
    result = validate_contract(enrich_contract(app.openapi()))

    assert result["status"] == "PASS"
    assert result["api_v1_operation_count"] > 0
    assert result["operation_count"] == result["operation_id_count"]
    assert result["declared_http_501_count"] == 0


def test_openapi_contract_generation_is_repeatable(tmp_path: Path) -> None:
    contract = tmp_path / "openapi.json"
    evidence = tmp_path / "validation.json"

    first = generate(contract, evidence)
    first_bytes = contract.read_bytes()
    second = generate(contract, evidence)

    assert first == second
    assert contract.read_bytes() == first_bytes
    assert json.loads(evidence.read_text(encoding="utf-8"))["sha256"] == first["sha256"]
    assert check(contract, evidence) == first


def test_openapi_contract_declares_strict_response_metadata() -> None:
    schema = enrich_contract(app.openapi())
    components = schema["components"]["schemas"]

    assert components["DataMode"]["enum"] == [
        "LIVE",
        "DEMO",
        "OFFLINE_SNAPSHOT",
        "UNAVAILABLE",
    ]
    assert components["FeatureStatus"]["enum"] == [
        "LIVE",
        "INTEGRATION_ONLY",
        "DOCUMENTED",
        "DISABLED",
        "NOT_IMPLEMENTED",
    ]
    assert set(components["SourceContext"]["required"]) == set(
        components["SourceContext"]["properties"]
    )
    response_schema = schema["paths"]["/api/v1/data-source"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    assert {"$ref": "#/components/schemas/ApiResponseMetadata"} in response_schema["allOf"]


def test_contract_validation_rejects_missing_strict_metadata() -> None:
    schema = enrich_contract(app.openapi())
    response_schema = schema["paths"]["/api/v1/data-source"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    response_schema["allOf"] = response_schema["allOf"][:-1]

    result = validate_contract(schema)

    assert result["status"] == "FAIL"
    assert any("omits strict API metadata" in error for error in result["errors"])
