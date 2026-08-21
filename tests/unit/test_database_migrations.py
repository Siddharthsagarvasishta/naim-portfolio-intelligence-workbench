from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy import create_engine, text

from naim_risk.workflow import WorkflowStore
from naim_risk.workflow.migrations import (
    BASELINE_REVISION,
    inspect_database,
    repair_database,
    upgrade_database,
)
from naim_risk.workflow.models import Base


def sqlite_url(path: Path) -> str:
    return f"sqlite+pysqlite:///{path.resolve()}"


def create_unstamped_schema(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    database_url = sqlite_url(path)
    engine = create_engine(database_url, future=True)
    try:
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()
    return database_url


def test_empty_database_upgrades_normally_and_repeated_upgrade_is_safe(tmp_path: Path) -> None:
    database_url = sqlite_url(tmp_path / "empty.sqlite3")

    first = upgrade_database(database_url)
    second = upgrade_database(database_url)

    assert first["result"] == "UPGRADED"
    assert second["result"] == "UPGRADED"
    assert inspect_database(database_url)["status"] == "CURRENT"
    assert inspect_database(database_url)["current_revisions"] == [BASELINE_REVISION]


def test_compatible_unstamped_database_is_backed_up_verified_and_stamped(
    tmp_path: Path,
) -> None:
    database = tmp_path / "legacy.sqlite3"
    database_url = create_unstamped_schema(database)
    before_hash = hashlib.sha256(database.read_bytes()).hexdigest()
    assert inspect_database(database_url)["status"] == "COMPATIBLE_UNSTAMPED"

    result = repair_database(database_url)

    assert result["status"] == "REPAIRED"
    assert result["baseline_stamped"] == BASELINE_REVISION
    assert result["before"]["safe_to_stamp_baseline"] is True
    assert result["after"]["status"] == "CURRENT"
    backup = Path(result["backup"]["path"])
    assert backup.is_file()
    assert result["backup"]["source_sha256"] == before_hash
    assert inspect_database(sqlite_url(backup))["schema_compatible_with_head"] is True


def test_exact_schema_with_empty_version_table_recovers_failed_first_migration(
    tmp_path: Path,
) -> None:
    database_url = create_unstamped_schema(tmp_path / "failed-first-upgrade.sqlite3")
    engine = create_engine(database_url, future=True)
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
    finally:
        engine.dispose()
    before = inspect_database(database_url)
    assert before["migration_state"] == "PARTIALLY_STAMPED_EMPTY_VERSION_TABLE"
    assert before["status"] == "COMPATIBLE_UNSTAMPED"

    result = repair_database(database_url)

    assert result["status"] == "REPAIRED"
    assert result["after"]["current_revisions"] == [BASELINE_REVISION]


def test_partially_migrated_database_is_backed_up_and_refused(tmp_path: Path) -> None:
    database = tmp_path / "partial.sqlite3"
    database_url = sqlite_url(database)
    engine = create_engine(database_url, future=True)
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
            connection.execute(text("CREATE TABLE workflow_object (id VARCHAR(36) PRIMARY KEY)"))
    finally:
        engine.dispose()
    before_hash = hashlib.sha256(database.read_bytes()).hexdigest()

    result = repair_database(database_url)

    assert result["status"] == "REFUSED"
    assert result["before"]["status"] == "PARTIALLY_STAMPED"
    assert result["before"]["missing_tables"]
    assert Path(result["backup"]["path"]).is_file()
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before_hash


def test_incompatible_database_is_never_stamped_or_modified(tmp_path: Path) -> None:
    database = tmp_path / "incompatible.sqlite3"
    database_url = create_unstamped_schema(database)
    engine = create_engine(database_url, future=True)
    try:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE workflow_object ADD COLUMN unsafe_guess TEXT"))
    finally:
        engine.dispose()
    before_hash = hashlib.sha256(database.read_bytes()).hexdigest()

    result = repair_database(database_url)

    assert result["status"] == "REFUSED"
    assert result["before"]["status"] == "INCOMPATIBLE"
    assert result["before"]["schema_mismatches"]
    assert result.get("baseline_stamped") is None
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before_hash


def test_unknown_revision_is_refused_even_when_tables_match(tmp_path: Path) -> None:
    database = tmp_path / "unknown-revision.sqlite3"
    database_url = create_unstamped_schema(database)
    engine = create_engine(database_url, future=True)
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
            connection.execute(
                text("INSERT INTO alembic_version (version_num) VALUES ('unknown_revision')")
            )
    finally:
        engine.dispose()

    result = repair_database(database_url)

    assert result["status"] == "REFUSED"
    assert result["before"]["status"] == "PARTIALLY_STAMPED"
    assert result["before"]["current_revisions"] == ["unknown_revision"]


def test_status_exposes_cli_api_data_root_database_mismatch(
    monkeypatch,
    tmp_path: Path,
) -> None:
    selected_url = create_unstamped_schema(tmp_path / "selected" / "workflow.sqlite3")
    monkeypatch.setenv("NAIM_DATA_DIR", str(tmp_path / "different-data-root"))

    report = inspect_database(selected_url)

    assert report["environment_alignment"]["selected_matches_data_dir_database"] is False
    assert report["environment_alignment"]["naim_data_dir_database"].endswith(
        "different-data-root/state/naim_workflow.sqlite3"
    )


def test_workflow_store_bootstrap_uses_migrations_and_persists_after_restart(
    tmp_path: Path,
) -> None:
    database_url = sqlite_url(tmp_path / "runtime.sqlite3")
    store = WorkflowStore(database_url)
    store.create("workspace", "WS-MIGRATION", {"name": "Durable"}, actor="test")
    store.close()

    status = inspect_database(database_url)
    assert status["status"] == "CURRENT"
    restarted = WorkflowStore(database_url)
    try:
        assert restarted.get("workspace", "WS-MIGRATION")["state"]["name"] == "Durable"
    finally:
        restarted.close()
