from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine

from naim_risk.auth import AuthMode, AuthService, AuthSettings, Role
from naim_risk.cli import main
from naim_risk.workflow import WorkflowStore
from naim_risk.workflow.models import Base

SECRET = "test-only-cli-signing-secret-that-is-long-enough"


def test_database_migration_commands_report_revision(
    tmp_path: Path,
    capsys,
) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'state' / 'workflow.sqlite3').resolve()}"
    assert main(["db", "upgrade", "--database-url", database_url]) == 0
    upgrade = json.loads(capsys.readouterr().out)
    assert upgrade["status"] == "upgraded"
    assert upgrade["revision"] == "head"
    assert upgrade["database_status"] == "CURRENT"
    assert upgrade["current_revisions"] == ["20260801_0001"]

    assert main(["db", "status", "--database-url", database_url]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["current_revision"] == "20260801_0001"
    assert status["up_to_date"] is True
    assert status["schema_compatible_with_head"] is True


def test_database_repair_command_backs_up_and_stamps_exact_legacy_schema(
    tmp_path: Path,
    capsys,
) -> None:
    database = (tmp_path / "legacy.sqlite3").resolve()
    database_url = f"sqlite+pysqlite:///{database}"
    engine = create_engine(database_url, future=True)
    try:
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()

    assert main(["db", "repair", "--database-url", database_url]) == 0

    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "REPAIRED"
    assert report["before"]["status"] == "COMPATIBLE_UNSTAMPED"
    assert report["after"]["status"] == "CURRENT"
    assert Path(report["backup"]["path"]).is_file()


def test_demo_setup_command_reads_password_only_from_environment(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'workflow.sqlite3').resolve()}"
    password = "a secure bootstrap password phrase"
    monkeypatch.setenv("NAIM_AUTH_MODE", "demo")
    monkeypatch.setenv("NAIM_TOKEN_SECRET", SECRET)
    monkeypatch.setenv("TEST_BOOTSTRAP_PASSWORD", password)

    assert (
        main(
            [
                "auth",
                "setup-demo",
                "--username",
                "model.validator",
                "--role",
                Role.MODEL_VALIDATOR.value,
                "--password-env",
                "TEST_BOOTSTRAP_PASSWORD",
                "--database-url",
                database_url,
            ]
        )
        == 0
    )
    output_text = capsys.readouterr().out
    output = json.loads(output_text)
    assert output["status"] == "demo_account_ready"
    assert output["password_source"] == "TEST_BOOTSTRAP_PASSWORD"
    assert password not in output_text

    store = WorkflowStore(database_url)
    try:
        auth = AuthService(AuthSettings(mode=AuthMode.DEMO, token_secret=SECRET), store)
        token = auth.authenticate_demo("model.validator", password)
        assert auth.principal(token).role is Role.MODEL_VALIDATOR
    finally:
        store.close()
