from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.generate_frontend_api_types import (
    DEFAULT_CONTRACT,
    DEFAULT_OUTPUT,
    check,
    generate,
    render_contract,
    schema_to_typescript,
)


def test_checked_in_frontend_contract_matches_authoritative_openapi() -> None:
    rendered = check()

    assert rendered == DEFAULT_OUTPUT.read_text(encoding="utf-8")
    assert "export interface paths" in rendered
    assert '"/api/v1/data-source"' in rendered
    assert '"data_mode": components["schemas"]["DataMode"]' in rendered
    assert '"evidence_id": components["schemas"]["EvidenceId"]' in rendered
    assert '"feature_status": components["schemas"]["FeatureStatus"]' in rendered


def test_generation_is_deterministic_and_check_detects_drift(tmp_path: Path) -> None:
    output = tmp_path / "generated-api-types.ts"

    first = generate(DEFAULT_CONTRACT, output)
    second = generate(DEFAULT_CONTRACT, output)

    assert first == second
    assert check(DEFAULT_CONTRACT, output) == first
    output.write_text(first + "// manual edit\n", encoding="utf-8")
    with pytest.raises(ValueError, match="contract drift"):
        check(DEFAULT_CONTRACT, output)


def test_renderer_preserves_required_optional_and_nullable_fields() -> None:
    rendered = schema_to_typescript(
        {
            "type": "object",
            "additionalProperties": False,
            "required": ["required_value", "nullable_value"],
            "properties": {
                "optional_value": {"type": "number"},
                "required_value": {"type": "string"},
                "nullable_value": {
                    "anyOf": [{"type": "string"}, {"type": "null"}]
                },
            },
        }
    )

    assert '"optional_value"?: number;' in rendered
    assert '"required_value": string;' in rendered
    assert '"nullable_value": string | null;' in rendered


def test_renderer_hash_and_counts_come_from_contract() -> None:
    contract = json.loads(DEFAULT_CONTRACT.read_text(encoding="utf-8"))
    rendered = render_contract(contract)

    assert f"export const OPENAPI_PATH_COUNT = {len(contract['paths'])} as const;" in rendered
    assert "OpenAPI SHA-256:" in rendered
    assert "export type RequestBodyFor<" in rendered
    assert "export type ResponseBodyFor<" in rendered
