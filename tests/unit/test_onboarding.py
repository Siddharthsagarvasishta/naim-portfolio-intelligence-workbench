from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import duckdb
import pandas as pd
import pytest
from openpyxl import Workbook

from naim_risk.onboarding import (
    FormulaSafetyError,
    OnboardingError,
    OnboardingStudio,
    ProfileApprovalError,
    SafeFormula,
    SourceReadError,
    SourceSafetyError,
    list_contracts,
)
from naim_risk.workflow import WorkflowStore


def _studio(tmp_path: Path, *, store: WorkflowStore | None = None) -> OnboardingStudio:
    return OnboardingStudio(
        tmp_path / "onboarding",
        workflow_store=store,
        max_upload_bytes=2 * 1024 * 1024,
        max_rows=1_000,
        max_preview_rows=20,
    )


def _account_source(studio: OnboardingStudio, *, invalid: bool = False) -> dict[str, object]:
    second_limit = "-50" if invalid else "200"
    payload = (
        "acct,opened,limit,region\n"
        "A-1,2025-01-01,100, North \n"
        f"A-2,2025-02-01,{second_limit},SOUTH\n"
    ).encode()
    return studio.upload_source("accounts.csv", payload)


def _account_mapping() -> dict[str, str]:
    return {
        "account_id": "acct",
        "opened_date": "opened",
        "credit_limit": "limit",
    }


def test_eight_canonical_contracts_are_exposed() -> None:
    contracts = list_contracts()

    assert {contract["contract_id"] for contract in contracts} == {
        "account_master",
        "account_month_performance",
        "strategy_decision",
        "partner_performance",
        "vendor_performance",
        "membership_history",
        "benefit_usage",
        "economic_assumptions",
    }
    assert all(contract["version"] == "1.0.0" for contract in contracts)
    assert all(contract["fields"] and contract["unique_key"] for contract in contracts)


def test_safe_formula_supports_governed_operations() -> None:
    row = {
        "loss": 20,
        "exposure": 0,
        "region": "  NÖRTH  WEST ",
        "start": "2024-01-01",
        "end": "2025-01-01",
        "missing": None,
    }

    assert SafeFormula("loss / exposure", allowed_fields=row).evaluate(row) is None
    assert SafeFormula("coalesce(missing, loss)", allowed_fields=row).evaluate(row) == 20
    assert SafeFormula("clip(loss, 0, 10)", allowed_fields=row).evaluate(row) == 10
    assert SafeFormula("normalize(region)", allowed_fields=row).evaluate(row) == "nörth west"
    assert SafeFormula("date_diff('months', start, end)", allowed_fields=row).evaluate(row) == 12
    assert (
        SafeFormula(
            "if_else(loss > 10, category_map('N', {'N': 'high'}, 'low'), 'low')",
            allowed_fields=row,
        ).evaluate(row)
        == "high"
    )

    with pytest.raises(FormulaSafetyError, match="Exponentiation"):
        SafeFormula("10 ** 1000", allowed_fields=[]).evaluate({})


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('id')",
        "open('/etc/passwd').read()",
        "value.__class__",
        "[item for item in value]",
        "globals()",
        "(lambda: 1)()",
    ],
)
def test_formula_injection_is_rejected(expression: str) -> None:
    with pytest.raises(FormulaSafetyError):
        SafeFormula(expression, allowed_fields=["value"])


def test_path_traversal_and_oversized_upload_are_rejected(tmp_path: Path) -> None:
    studio = OnboardingStudio(tmp_path / "onboarding", max_upload_bytes=16)

    with pytest.raises(SourceSafetyError):
        studio.upload_source("../escape.csv", b"a\n1\n")
    with pytest.raises(SourceSafetyError):
        studio.select_source("../escape.csv")
    with pytest.raises(SourceSafetyError):
        studio.upload_source("large.csv", b"a" * 17)


@pytest.mark.parametrize(
    ("filename", "payload"),
    [
        ("broken.json", b"[{not-json}]"),
        ("broken.csv", b'a,b\n"unterminated,2\n'),
        ("empty.csv", b""),
        ("header-only.csv", b"a,b\n"),
        ("duplicate.csv", b"a,a\n1,2\n"),
    ],
)
def test_malformed_upload_is_rejected(
    tmp_path: Path,
    filename: str,
    payload: bytes,
) -> None:
    with pytest.raises(SourceReadError):
        _studio(tmp_path).upload_source(filename, payload)


def test_xlsx_formula_cells_and_external_execution_are_rejected(tmp_path: Path) -> None:
    workbook_path = tmp_path / "formula.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(["account_id", "credit_limit"])
    worksheet.append(["A-1", '=WEBSERVICE("https://example.invalid")'])
    workbook.save(workbook_path)
    workbook.close()

    with pytest.raises(SourceSafetyError, match="formulas"):
        _studio(tmp_path).upload_source("formula.xlsx", workbook_path.read_bytes())


def test_preview_infers_types_and_mapping_suggestions(tmp_path: Path) -> None:
    studio = _studio(tmp_path)
    source = _account_source(studio)

    preview = studio.preview_source(source)

    assert preview["sample_row_count"] == 2
    assert [column["inferred_type"] for column in preview["columns"]] == [
        "string",
        "datetime",
        "integer",
        "string",
    ]
    assert preview["suggested_mappings"]["account_master"] == {"region": "region"}
    assert preview["source"]["relative_path"].startswith("sources/")


def test_mapping_and_transformations_validate_without_eval(tmp_path: Path) -> None:
    studio = _studio(tmp_path)
    source = _account_source(studio)

    mapping = studio.validate_mapping(
        source,
        contract_id="account_master",
        mapping=_account_mapping(),
        transformations={"region": "normalize(region)"},
    )
    result = studio.validate_source(
        source,
        contract_id="account_master",
        mapping=_account_mapping(),
        transformations={"region": "normalize(region)"},
    )

    assert mapping["valid"] is True
    assert mapping["derived_fields"] == ["region"]
    assert result["validation"]["passed"] is True
    assert [row["region"] for row in result["valid_row_preview"]] == ["north", "south"]


def test_validation_quarantine_reconciliation_and_approval(tmp_path: Path) -> None:
    store = WorkflowStore(f"sqlite+pysqlite:///{tmp_path / 'workflow.sqlite3'}")
    studio = _studio(tmp_path, store=store)
    source = _account_source(studio, invalid=True)

    profile = studio.save_import_profile(
        "accounts-v1",
        source,
        contract_id="account_master",
        mapping=_account_mapping(),
        max_error_rate=0.5,
        actor="analyst",
    )
    with pytest.raises(ProfileApprovalError):
        studio.approve_profile(
            "accounts-v1",
            expected_version=profile["version"],
            actor="validator",
            rationale="Too early",
        )

    run = studio.load_into_onboarding_namespace(
        "accounts-v1",
        source,
        actor="analyst",
        expected_version=1,
    )

    assert run["validation"]["passed"] is True
    assert run["validation"]["valid_rows"] == 1
    assert run["validation"]["invalid_rows"] == 1
    assert run["reconciliation"]["balanced"] is True
    assert run["reconciliation"]["row_balance_delta"] == 0
    assert run["loaded_to_active_analytics"] is False
    namespace = studio.root / run["outputs"]["onboarding_namespace"]
    quarantine = studio.root / run["outputs"]["quarantine"]
    preview_mart = studio.root / run["outputs"]["preview_mart"]
    assert len(pd.read_parquet(namespace)) == 1
    quarantined = pd.read_parquet(quarantine)
    assert len(quarantined) == 1
    assert "credit_limit:NEGATIVE_VALUE" in quarantined.loc[0, "_error_codes"]
    assert preview_mart.is_file()

    approved = studio.approve_profile(
        "accounts-v1",
        expected_version=2,
        actor="validator",
        rationale="Validation passed and source totals reconcile.",
    )

    assert approved["active"] is True
    assert approved["approval_state"] == "APPROVED"
    assert approved["version"] == 3
    assert store.verify_audit_chain("configuration_change", "onboarding-profile:accounts-v1")
    store.close()


def test_failed_validation_cannot_be_approved(tmp_path: Path) -> None:
    studio = _studio(tmp_path)
    source = _account_source(studio, invalid=True)
    studio.save_import_profile(
        "strict",
        source,
        contract_id="account_master",
        mapping=_account_mapping(),
        max_error_rate=0.0,
        actor="analyst",
    )
    run = studio.run_import_profile("strict", source, actor="analyst", expected_version=1)

    assert run["validation"]["passed"] is False
    with pytest.raises(ProfileApprovalError, match="did not pass"):
        studio.approve_profile(
            "strict",
            expected_version=2,
            actor="validator",
            rationale="Cannot approve",
        )


def test_approved_profile_reuses_future_compatible_file(tmp_path: Path) -> None:
    studio = _studio(tmp_path)
    original = _account_source(studio)
    studio.save_import_profile(
        "reusable",
        original,
        contract_id="account_master",
        mapping=_account_mapping(),
        actor="analyst",
    )
    studio.run_import_profile("reusable", original, actor="analyst", expected_version=1)
    studio.approve_profile(
        "reusable",
        expected_version=2,
        actor="validator",
        rationale="Balanced",
    )
    future = studio.upload_source(
        "next-period.csv",
        b"acct,opened,limit,region\nA-3,2025-03-01,300,EAST\n",
    )

    rerun = studio.run_import_profile("reusable", future, actor="analyst", expected_version=3)

    assert rerun["validation"]["valid_rows"] == 1
    assert rerun["profile_active"] is True
    assert rerun["profile_approval_state"] == "APPROVED"


def test_profile_rejects_future_file_with_missing_structure(tmp_path: Path) -> None:
    studio = _studio(tmp_path)
    source = _account_source(studio)
    studio.save_import_profile(
        "shape",
        source,
        contract_id="account_master",
        mapping=_account_mapping(),
        actor="analyst",
    )
    incompatible = studio.upload_source("missing.csv", b"acct,opened\nA-3,2025-03-01\n")

    with pytest.raises(OnboardingError, match="missing: limit"):
        studio.run_import_profile("shape", incompatible, actor="analyst", expected_version=1)


def test_sqlite_and_duckdb_are_read_as_base_tables_only(tmp_path: Path) -> None:
    studio = _studio(tmp_path)
    sqlite_path = tmp_path / "source.sqlite"
    sqlite_connection = sqlite3.connect(sqlite_path)
    sqlite_connection.execute("CREATE TABLE accounts (account_id TEXT, credit_limit REAL)")
    sqlite_connection.execute("INSERT INTO accounts VALUES ('A-1', 100)")
    sqlite_connection.execute("CREATE VIEW account_view AS SELECT * FROM accounts")
    sqlite_connection.commit()
    sqlite_connection.close()
    duckdb_path = tmp_path / "source.duckdb"
    duckdb_connection = duckdb.connect(str(duckdb_path))
    duckdb_connection.execute("CREATE TABLE accounts AS SELECT 'A-2' account_id, 200 credit_limit")
    duckdb_connection.execute("CREATE VIEW account_view AS SELECT * FROM accounts")
    duckdb_connection.close()

    sqlite_source = studio.upload_source("source.sqlite", sqlite_path.read_bytes())
    duckdb_source = studio.upload_source("source.duckdb", duckdb_path.read_bytes())

    assert studio.list_database_tables(sqlite_source) == ["accounts"]
    assert studio.list_database_tables(duckdb_source) == ["accounts"]
    assert studio.preview_source(studio.with_table(sqlite_source, "accounts"))["rows"] == [
        {"account_id": "A-1", "credit_limit": 100.0}
    ]
    assert studio.preview_source(studio.with_table(duckdb_source, "accounts"))["rows"] == [
        {"account_id": "A-2", "credit_limit": 200}
    ]
    with pytest.raises(SourceSafetyError):
        studio.with_table(sqlite_source, "accounts; DROP TABLE accounts")


def test_json_parquet_and_xlsx_sources_preview(tmp_path: Path) -> None:
    studio = _studio(tmp_path)
    json_source = studio.upload_source(
        "accounts.json",
        json.dumps([{"account_id": "A-1", "credit_limit": 100}]).encode(),
    )
    parquet_path = tmp_path / "accounts.parquet"
    pd.DataFrame([{"account_id": "A-2", "credit_limit": 200}]).to_parquet(parquet_path)
    parquet_source = studio.upload_source("accounts.parquet", parquet_path.read_bytes())
    workbook_path = tmp_path / "accounts.xlsx"
    pd.DataFrame([{"account_id": "A-3", "credit_limit": 300}]).to_excel(workbook_path, index=False)
    xlsx_source = studio.upload_source("accounts.xlsx", workbook_path.read_bytes())

    assert studio.preview_source(json_source)["rows"][0]["account_id"] == "A-1"
    assert studio.preview_source(parquet_source)["rows"][0]["account_id"] == "A-2"
    assert studio.preview_source(xlsx_source)["rows"][0]["account_id"] == "A-3"


def test_postgresql_descriptor_is_environment_referenced_and_secret_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    studio = _studio(tmp_path)
    descriptor = studio.configure_postgresql_source(
        url_env="NAIM_ONBOARDING_POSTGRES_URL",
        table="public.accounts",
    )

    assert descriptor["kind"] == "postgresql"
    assert descriptor["url_env"] == "NAIM_ONBOARDING_POSTGRES_URL"
    assert "url" not in descriptor
    with pytest.raises(SourceSafetyError):
        studio.configure_postgresql_source(url_env="DATABASE_URL", table="accounts")
    monkeypatch.setenv("NAIM_ONBOARDING_POSTGRES_URL", "sqlite:///not-postgres.sqlite3")
    with pytest.raises(SourceSafetyError, match="PostgreSQL driver"):
        studio.list_database_tables(descriptor)


def test_registered_source_hash_detects_tampering(tmp_path: Path) -> None:
    studio = _studio(tmp_path)
    source = _account_source(studio)
    path = studio.root / str(source["relative_path"])
    path.write_text("acct\nchanged\n", encoding="utf-8")

    with pytest.raises(SourceSafetyError, match="registered hash"):
        studio.preview_source(source)


def test_unregistered_hash_and_symbolic_link_are_rejected(tmp_path: Path) -> None:
    studio = _studio(tmp_path)
    source = _account_source(studio)
    without_hash = dict(source)
    without_hash.pop("sha256")

    with pytest.raises(SourceSafetyError, match="registered SHA-256"):
        studio.preview_source(without_hash)

    source_path = studio.root / str(source["relative_path"])
    link_path = studio.sources_root / "linked.csv"
    link_path.symlink_to(source_path)
    with pytest.raises(SourceSafetyError, match="Symbolic-link"):
        studio.select_source("linked.csv")


def test_json_row_limit_is_checked_before_sampling(tmp_path: Path) -> None:
    studio = OnboardingStudio(tmp_path / "onboarding", max_rows=2)
    payload = json.dumps([{"id": 1}, {"id": 2}, {"id": 3}]).encode()

    with pytest.raises(SourceSafetyError, match="row safety limit"):
        studio.upload_source("too-many.json", payload)


def test_chained_derived_fields_do_not_become_future_source_requirements(
    tmp_path: Path,
) -> None:
    studio = _studio(tmp_path)
    source = studio.upload_source(
        "derived.csv",
        b"acct,raw_region\nA-1, NORTH \n",
    )
    profile = studio.save_import_profile(
        "derived",
        source,
        contract_id="account_master",
        mapping={"account_id": "acct"},
        transformations={
            "region": "normalize(raw_region)",
            "product": "normalize(region)",
        },
        actor="analyst",
    )

    assert profile["required_source_columns"] == ["acct", "raw_region"]
    run = studio.run_import_profile("derived", source, actor="analyst", expected_version=1)
    assert run["validation"]["passed"] is True


def test_non_finite_numeric_values_are_quarantined_not_crashed(tmp_path: Path) -> None:
    studio = _studio(tmp_path)
    source = studio.upload_source("nonfinite.csv", b"acct,limit\nA-1,inf\n")

    result = studio.validate_source(
        source,
        contract_id="account_master",
        mapping={"account_id": "acct", "credit_limit": "limit"},
    )

    assert result["validation"]["invalid_rows"] == 1
    assert result["error_preview"][0]["code"] == "INVALID_TYPE"


def test_mapping_requires_contract_fields_and_known_sources(tmp_path: Path) -> None:
    studio = _studio(tmp_path)
    source = _account_source(studio)

    with pytest.raises(ValueError, match="Required contract mappings"):
        studio.validate_mapping(source, contract_id="account_master", mapping={})
    with pytest.raises(ValueError, match="does not exist"):
        studio.validate_mapping(
            source,
            contract_id="account_master",
            mapping={"account_id": "missing"},
        )
