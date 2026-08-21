from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import select

import naim_risk.onboarding as onboarding_module
from naim_risk.exports.packages import _neutralise_formula_injection
from naim_risk.onboarding import OnboardingStudio, SourceReadError, SourceSafetyError
from naim_risk.workflow import WorkflowStore
from naim_risk.workflow.models import AuditEvent
from scripts.security_scan import scan_repository


def test_secret_scan_redacts_detected_values(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    secret_value = "AKIA" + "ABCDEFGHIJKLMNOP"
    (source / "unsafe.py").write_text(
        f'credential = "{secret_value}"\n',
        encoding="utf-8",
    )

    report = scan_repository(tmp_path)

    assert report["status"] == "FAIL"
    assert report["summary"]["errors"] == 1
    assert report["findings"][0]["rule_id"] == "SECRET_AWS_ACCESS_KEY"
    assert secret_value not in json.dumps(report)
    assert len(report["findings"][0]["fingerprint"]) == 20


def test_secret_scan_distinguishes_config_warnings_from_failures(tmp_path: Path) -> None:
    disabled_default = "${NAIM_AUTH_MODE:-" + "disabled}"
    empty_secret_default = "${NAIM_TOKEN_SECRET:-" + "}"
    (tmp_path / "docker-compose.yml").write_text(
        "\n".join(
            [
                "services:",
                "  api:",
                "    environment:",
                f"      NAIM_AUTH_MODE: {disabled_default}",
                f"      NAIM_TOKEN_SECRET: {empty_secret_default}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / ".env.example").write_text(
        "NAIM_TOKEN_SECRET=replace-with-at-least-32-random-characters\n",
        encoding="utf-8",
    )

    report = scan_repository(tmp_path)

    assert report["status"] == "PASS_WITH_WARNINGS"
    assert report["summary"] == {"errors": 0, "warnings": 2, "unreadable_files": 0}
    assert {finding["rule_id"] for finding in report["findings"]} == {
        "CONFIG_AUTH_DISABLED_DEFAULT",
        "CONFIG_EMPTY_TOKEN_SECRET_DEFAULT",
    }


@pytest.mark.parametrize(
    "table",
    [
        "accounts; DROP TABLE accounts",
        'accounts" UNION SELECT password FROM users --',
        "public.accounts.extra",
        "../accounts",
    ],
)
def test_database_table_identifier_rejects_sql_injection(table: str, tmp_path: Path) -> None:
    studio = OnboardingStudio(tmp_path / "onboarding")

    with pytest.raises(SourceSafetyError):
        studio.configure_postgresql_source(
            url_env="NAIM_ONBOARDING_WAREHOUSE_URL",
            table=table,
        )


def test_xlsx_decompression_bomb_metadata_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    oversized_member = zipfile.ZipInfo("xl/worksheets/sheet1.xml")
    oversized_member.file_size = 101 * 1024 * 1024

    class BombArchive:
        def __init__(self, _path: Path) -> None:
            pass

        def __enter__(self) -> BombArchive:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def infolist(self) -> list[zipfile.ZipInfo]:
            return [oversized_member]

    monkeypatch.setattr(onboarding_module.zipfile, "ZipFile", BombArchive)
    studio = OnboardingStudio(tmp_path / "onboarding", max_upload_bytes=1024)

    with pytest.raises(SourceSafetyError, match="expanded content"):
        studio._inspect_xlsx(tmp_path / "compressed.xlsx", sheet=None)


def test_rejected_upload_removes_generated_staging_directory(tmp_path: Path) -> None:
    studio = OnboardingStudio(tmp_path / "onboarding")

    with pytest.raises(SourceReadError):
        studio.upload_source("malformed.json", b"[{not-json}]")

    assert list(studio.sources_root.iterdir()) == []


def test_spreadsheet_export_neutralises_formula_injection() -> None:
    unsafe = pd.DataFrame(
        {
            "value": ["=1+1", "+SUM(A1:A2)", "-2+3", "@HYPERLINK('x')", "ordinary"],
            "number": [1, 2, 3, 4, 5],
        }
    )

    safe = _neutralise_formula_injection(unsafe)

    assert safe["value"].tolist() == [
        "'=1+1",
        "'+SUM(A1:A2)",
        "'-2+3",
        "'@HYPERLINK('x')",
        "ordinary",
    ]
    assert safe["number"].tolist() == [1, 2, 3, 4, 5]


def test_audit_chain_verification_detects_database_tampering(tmp_path: Path) -> None:
    store = WorkflowStore(f"sqlite+pysqlite:///{(tmp_path / 'audit.sqlite3').resolve()}")
    store.create(
        "investigation",
        "INV-SECURITY-1",
        {"status": "DRAFT"},
        actor="portfolio.analyst",
    )
    store.update(
        "investigation",
        "INV-SECURITY-1",
        {"status": "UNDER_REVIEW"},
        expected_version=1,
        actor="portfolio.analyst",
    )
    assert store.verify_audit_chain("investigation", "INV-SECURITY-1") is True

    with store.session_factory.begin() as session:
        first = session.scalars(select(AuditEvent).order_by(AuditEvent.occurred_at)).first()
        assert first is not None
        first.payload = {"tampered": True}

    assert store.verify_audit_chain("investigation", "INV-SECURITY-1") is False
    store.close()
