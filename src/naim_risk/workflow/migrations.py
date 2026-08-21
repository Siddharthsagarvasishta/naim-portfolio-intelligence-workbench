"""Fail-closed database inspection, bootstrap, backup, and migration helpers.

The local workflow database predates Alembic in some installations.  Those databases may have
the complete SQLAlchemy schema but no ``alembic_version`` row.  This module is the single place
where that legacy state is recognised: a baseline is stamped only after an exact schema check.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, UniqueConstraint, create_engine, inspect, text
from sqlalchemy.dialects import sqlite as sqlite_dialect
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import SQLAlchemyError

from alembic import command
from naim_risk.config import REPOSITORY_ROOT
from naim_risk.workflow.models import Base

BASELINE_REVISION = "20260801_0001"
VERSION_TABLE = "alembic_version"


class DatabaseMigrationError(RuntimeError):
    """Raised when migration safety cannot be proven."""

    def __init__(self, message: str, report: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.report = report or {}


def alembic_configuration(database_url: str) -> AlembicConfig:
    """Build an Alembic configuration anchored to the repository, not the caller's cwd."""

    configuration = AlembicConfig(str(REPOSITORY_ROOT / "alembic.ini"))
    configuration.set_main_option("script_location", str(REPOSITORY_ROOT / "alembic"))
    configuration.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return configuration


def _safe_url(url: URL) -> str:
    return str(url.set(password="***")) if url.password else str(url)


def sqlite_database_path(database_url: str) -> Path | None:
    """Return the resolved SQLite file path, or ``None`` for memory/non-SQLite URLs."""

    url = make_url(database_url)
    if url.get_backend_name() != "sqlite" or not url.database:
        return None
    query = {str(key): str(value).lower() for key, value in url.query.items()}
    if url.database == ":memory:" or query.get("mode") == "memory" or url.database.startswith(
        "file:"
    ):
        return None
    path = Path(url.database).expanduser()
    if not path.is_absolute():
        path = REPOSITORY_ROOT / path
    return path.resolve()


def is_sqlite_memory_url(database_url: str) -> bool:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite":
        return False
    query = {str(key): str(value).lower() for key, value in url.query.items()}
    return (
        url.database in {None, ":memory:"}
        or query.get("mode") == "memory"
        or str(url.database).startswith("file:")
    )


def _compiled_type(column_type: Any) -> str:
    return " ".join(
        str(column_type.compile(dialect=sqlite_dialect.dialect())).upper().split()
    )


def _expected_table_contract(table_name: str) -> dict[str, Any]:
    table = Base.metadata.tables[table_name]
    indexes = sorted(
        {
            (
                str(index.name),
                tuple(str(column.name) for column in index.columns),
                bool(index.unique),
            )
            for index in table.indexes
        }
    )
    unique_constraints = sorted(
        {
            (
                str(constraint.name),
                tuple(str(column.name) for column in constraint.columns),
            )
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        }
    )
    foreign_keys = sorted(
        {
            (
                tuple(str(column.parent.name) for column in constraint.elements),
                str(constraint.elements[0].column.table.name),
                tuple(str(column.column.name) for column in constraint.elements),
                str(constraint.ondelete or "").upper(),
            )
            for constraint in table.foreign_key_constraints
        }
    )
    return {
        "columns": [
            {
                "name": str(column.name),
                "type": _compiled_type(column.type),
                "nullable": bool(column.nullable),
                "primary_key": bool(column.primary_key),
            }
            for column in table.columns
        ],
        "primary_key": tuple(str(column.name) for column in table.primary_key.columns),
        "indexes": indexes,
        "unique_constraints": unique_constraints,
        "foreign_keys": foreign_keys,
    }


def _actual_table_contract(inspector: Any, table_name: str) -> dict[str, Any]:
    indexes = sorted(
        {
            (
                str(index.get("name")),
                tuple(str(column) for column in index.get("column_names") or ()),
                bool(index.get("unique")),
            )
            for index in inspector.get_indexes(table_name)
        }
    )
    unique_constraints = sorted(
        {
            (
                str(constraint.get("name")),
                tuple(str(column) for column in constraint.get("column_names") or ()),
            )
            for constraint in inspector.get_unique_constraints(table_name)
        }
    )
    foreign_keys = sorted(
        {
            (
                tuple(str(column) for column in constraint.get("constrained_columns") or ()),
                str(constraint.get("referred_table")),
                tuple(str(column) for column in constraint.get("referred_columns") or ()),
                str((constraint.get("options") or {}).get("ondelete") or "").upper(),
            )
            for constraint in inspector.get_foreign_keys(table_name)
        }
    )
    primary_key = inspector.get_pk_constraint(table_name).get("constrained_columns") or ()
    return {
        "columns": [
            {
                "name": str(column["name"]),
                "type": _compiled_type(column["type"]),
                "nullable": bool(column["nullable"]),
                "primary_key": bool(column.get("primary_key")),
            }
            for column in inspector.get_columns(table_name)
        ],
        "primary_key": tuple(str(column) for column in primary_key),
        "indexes": indexes,
        "unique_constraints": unique_constraints,
        "foreign_keys": foreign_keys,
    }


def _schema_differences(engine: Engine) -> tuple[list[str], list[str], list[str]]:
    inspector = inspect(engine)
    expected_tables = set(Base.metadata.tables)
    actual_tables = {
        name
        for name in inspector.get_table_names()
        if name != VERSION_TABLE and not name.startswith("sqlite_")
    }
    missing_tables = sorted(expected_tables - actual_tables)
    unexpected_tables = sorted(actual_tables - expected_tables)
    mismatches: list[str] = []
    for table_name in sorted(expected_tables & actual_tables):
        expected = _expected_table_contract(table_name)
        actual = _actual_table_contract(inspector, table_name)
        for contract_name in (
            "columns",
            "primary_key",
            "indexes",
            "unique_constraints",
            "foreign_keys",
        ):
            if actual[contract_name] != expected[contract_name]:
                mismatches.append(
                    f"{table_name}.{contract_name}: expected={expected[contract_name]!r}; "
                    f"actual={actual[contract_name]!r}"
                )
    return missing_tables, unexpected_tables, mismatches


def inspect_database(database_url: str) -> dict[str, Any]:
    """Inspect migration and schema state without modifying the database."""

    url = make_url(database_url)
    configuration = alembic_configuration(database_url)
    heads = sorted(ScriptDirectory.from_config(configuration).get_heads())
    known_revisions = sorted(
        revision.revision for revision in ScriptDirectory.from_config(configuration).walk_revisions()
    )
    path = sqlite_database_path(database_url)
    database_exists = path.is_file() if path else None
    integrity_result: str | None = None
    inspection_error: str | None = None
    revisions: list[str] = []
    tables: list[str] = []
    missing_tables: list[str] = []
    unexpected_tables: list[str] = []
    mismatches: list[str] = []
    if path is not None and not database_exists:
        missing_tables = sorted(Base.metadata.tables)
    else:
        engine = create_engine(database_url, future=True)
        try:
            with engine.connect() as connection:
                inspector = inspect(connection)
                tables = sorted(inspector.get_table_names())
                if url.get_backend_name() == "sqlite":
                    integrity_result = str(
                        connection.execute(text("PRAGMA integrity_check")).scalar()
                    )
                if VERSION_TABLE in tables:
                    revisions = sorted(
                        str(row[0])
                        for row in connection.execute(
                            text(f"SELECT version_num FROM {VERSION_TABLE}")
                        )
                        if row[0] is not None
                    )
                missing_tables, unexpected_tables, mismatches = _schema_differences(
                    connection.engine
                )
        except SQLAlchemyError as exc:
            inspection_error = f"{type(exc).__name__}: {exc}"
        finally:
            engine.dispose()

    application_tables = sorted(
        name for name in tables if name != VERSION_TABLE and not name.startswith("sqlite_")
    )
    schema_compatible = not (
        inspection_error or missing_tables or unexpected_tables or mismatches
    ) and bool(application_tables)
    version_table_present = VERSION_TABLE in tables
    if inspection_error or (integrity_result not in {None, "ok"}):
        state = "INCOMPATIBLE"
        action = "Restore a known-good backup or preserve this file and rebuild separately."
    elif not application_tables and not version_table_present:
        state = "EMPTY"
        action = "Run migrations normally."
    elif schema_compatible and (not version_table_present or not revisions):
        state = "COMPATIBLE_UNSTAMPED"
        action = "Back up, stamp the verified baseline, then upgrade to head."
    elif schema_compatible and revisions == heads:
        state = "CURRENT"
        action = "No schema change is required."
    elif schema_compatible and revisions and all(item in known_revisions for item in revisions):
        state = "VERSIONED"
        action = "Run remaining migrations to head."
    elif version_table_present and (
        not revisions or any(item not in known_revisions for item in revisions)
    ):
        state = "PARTIALLY_STAMPED"
        action = "Do not stamp or upgrade automatically; inspect the revision state."
    else:
        state = "INCOMPATIBLE"
        action = "Preserve the database, review mismatches, and rebuild from its backup if approved."

    same_as_data_root_default: bool | None = None
    data_root_database: str | None = None
    if path is not None:
        configured_data_root = Path(os.getenv("NAIM_DATA_DIR", REPOSITORY_ROOT / "data"))
        if not configured_data_root.is_absolute():
            configured_data_root = REPOSITORY_ROOT / configured_data_root
        data_root_path = (configured_data_root / "state" / "naim_workflow.sqlite3").resolve()
        data_root_database = str(data_root_path)
        same_as_data_root_default = path == data_root_path

    return {
        "status": state,
        "safe_to_stamp_baseline": state == "COMPATIBLE_UNSTAMPED",
        "schema_compatible_with_head": schema_compatible,
        "database_url": _safe_url(url),
        "database_path": str(path) if path else None,
        "database_exists": database_exists,
        "integrity_check": integrity_result,
        "application_tables": application_tables,
        "alembic_version_table_present": version_table_present,
        "migration_state": (
            "PARTIALLY_STAMPED_EMPTY_VERSION_TABLE"
            if version_table_present and not revisions
            else "UNSTAMPED"
            if not version_table_present
            else "STAMPED"
        ),
        "current_revisions": revisions,
        "head_revisions": heads,
        "known_revisions": known_revisions,
        "missing_tables": missing_tables,
        "unexpected_tables": unexpected_tables,
        "schema_mismatches": mismatches,
        "inspection_error": inspection_error,
        "environment_alignment": {
            "naim_database_url_configured": bool(os.getenv("NAIM_DATABASE_URL")),
            "naim_data_dir_database": data_root_database,
            "selected_matches_data_dir_database": same_as_data_root_default,
        },
        "recommended_action": action,
    }


def backup_sqlite_database(database_url: str) -> dict[str, Any] | None:
    """Create a timestamped, consistent backup of an existing SQLite file."""

    source = sqlite_database_path(database_url)
    if source is None:
        raise DatabaseMigrationError("Database repair supports file-backed SQLite only")
    if not source.is_file():
        return None
    source_bytes = source.stat().st_size
    source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    target = source.with_name(f"{source.name}.backup-{stamp}")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(str(source)) as source_connection:
            with sqlite3.connect(str(target)) as target_connection:
                source_connection.backup(target_connection)
    except sqlite3.DatabaseError:
        # Preserve even a malformed SQLite candidate byte-for-byte for manual recovery.
        shutil.copy2(source, target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    return {
        "path": str(target),
        "bytes": target.stat().st_size,
        "sha256": digest,
        "source_bytes": source_bytes,
        "source_sha256": source_digest,
    }


def upgrade_database(database_url: str) -> dict[str, Any]:
    """Upgrade only states that Alembic can safely advance without guessing."""

    path = sqlite_database_path(database_url)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        report = inspect_database(database_url)
        if report["status"] not in {"EMPTY", "CURRENT", "VERSIONED"}:
            report["result"] = "REFUSED"
            report["message"] = (
                "Migration upgrade refused because schema safety is not proven. "
                "Run `naim db repair` for a backed-up compatibility check."
            )
            return report
    command.upgrade(alembic_configuration(database_url), "head")
    report = inspect_database(database_url)
    report["result"] = "UPGRADED" if report["status"] == "CURRENT" else "REFUSED"
    return report


def repair_database(database_url: str) -> dict[str, Any]:
    """Back up and repair a compatible SQLite database; refuse all ambiguous states."""

    path = sqlite_database_path(database_url)
    if path is None:
        raise DatabaseMigrationError("`db repair` supports file-backed SQLite databases only")
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = backup_sqlite_database(database_url)
    before = inspect_database(database_url)
    result: dict[str, Any] = {"backup": backup, "before": before}
    if before["status"] == "COMPATIBLE_UNSTAMPED":
        command.stamp(alembic_configuration(database_url), BASELINE_REVISION)
        result["baseline_stamped"] = BASELINE_REVISION
    elif before["status"] not in {"EMPTY", "CURRENT", "VERSIONED"}:
        result.update(
            {
                "status": "REFUSED",
                "message": (
                    "Database was backed up but not modified because exact compatibility "
                    "could not be proven. Preserve the original, move it aside only after "
                    "review, then run `naim db upgrade` to create a clean replacement."
                ),
                "manual_rebuild_steps": [
                    f"Preserve the backup: {backup['path'] if backup else 'no source file existed'}",
                    f"Move the incompatible database aside manually: {path}",
                    "Run: make db-upgrade",
                ],
            }
        )
        return result
    command.upgrade(alembic_configuration(database_url), "head")
    after = inspect_database(database_url)
    result.update(
        {
            "status": "REPAIRED" if after["status"] == "CURRENT" else "REFUSED",
            "after": after,
        }
    )
    return result


def ensure_database_ready(database_url: str, *, engine: Engine | None = None) -> None:
    """Safely initialise file databases used directly by application services."""

    if is_sqlite_memory_url(database_url):
        if engine is None:
            raise DatabaseMigrationError("An existing engine is required for SQLite memory mode")
        Base.metadata.create_all(engine)
        return
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite":
        command.upgrade(alembic_configuration(database_url), "head")
        return
    report = inspect_database(database_url)
    if report["status"] == "CURRENT":
        return
    if report["status"] == "EMPTY":
        result = upgrade_database(database_url)
    elif report["status"] == "COMPATIBLE_UNSTAMPED":
        result = repair_database(database_url)
    elif report["status"] == "VERSIONED":
        result = upgrade_database(database_url)
    else:
        raise DatabaseMigrationError(
            "Workflow database is incompatible or ambiguously stamped; run `naim db repair`.",
            report,
        )
    if result.get("status") not in {"CURRENT", "REPAIRED"} and result.get("result") != "UPGRADED":
        raise DatabaseMigrationError("Workflow database bootstrap failed closed.", result)
