"""Supported command-line interface for local nAIM workflows."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from naim_risk.auth import AuthMode, AuthService, AuthSettings, Role
from naim_risk.compat import configured_legacy_environment
from naim_risk.config import CONFIG_ROOT, REPOSITORY_ROOT, load_config
from naim_risk.pipeline import run_pipeline
from naim_risk.runtime_modes import DataMode, data_mode_from_environment
from naim_risk.workflow import WorkflowStore
from naim_risk.workflow.migrations import (
    DatabaseMigrationError,
    inspect_database,
    repair_database,
    upgrade_database,
)
from naim_risk.workflow.store import database_url_from_environment

PROFILE_CHOICES = ("test", "small", "default", "medium", "large")


def _doctor_report() -> dict[str, Any]:
    dependency_names = ("fastapi", "pandas", "pyarrow", "duckdb", "uvicorn")
    dependencies = {name: importlib.util.find_spec(name) is not None for name in dependency_names}
    checks = {
        "python_3_12_or_newer": sys.version_info >= (3, 12),
        "governed_configuration": (CONFIG_ROOT / "dataset_profiles.json").is_file(),
        "backend_dependencies": all(dependencies.values()),
    }
    return {
        "product": "nAIM Portfolio Intelligence Workbench",
        "ok": all(checks.values()),
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "repository_root": str(REPOSITORY_ROOT),
        "configuration_root": str(CONFIG_ROOT),
        "node": shutil.which("node"),
        "docker": shutil.which("docker"),
        "checks": checks,
        "dependencies": dependencies,
        "deprecated_environment": [
            {"configured": legacy, "replacement": canonical}
            for legacy, canonical in configured_legacy_environment()
        ],
    }


def _run_doctor(_: argparse.Namespace) -> int:
    report = _doctor_report()
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


def _run_pipeline(args: argparse.Namespace) -> int:
    result = run_pipeline(
        load_config(args.profile, seed=args.seed, data_root=args.data_root),
        persist=not args.no_persist,
    )
    print(
        json.dumps(
            {
                "run_id": result.run_id,
                "profile": args.profile,
                "validation_status": result.validation.status,
                "publication_allowed": result.validation.publication_allowed,
                "row_counts": result.manifest["row_counts"],
                "storage_engine": result.manifest["storage_engine"],
                "manifest": str(result.paths.get("manifest", "")),
            },
            indent=2,
        )
    )
    return 0


def _run_api(args: argparse.Namespace) -> int:
    import uvicorn

    os.environ["NAIM_DATASET_PROFILE"] = args.profile
    os.environ["NAIM_DATA_DIR"] = str(args.data_root)
    if args.seed is not None:
        os.environ["NAIM_RANDOM_SEED"] = str(args.seed)
    os.environ["NAIM_AUTH_MODE"] = args.auth_mode
    os.environ["NAIM_DATA_MODE"] = args.data_mode
    uvicorn.run(
        "naim_risk.api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


def _resolved_database_url(explicit: str | None) -> str:
    return explicit or database_url_from_environment(REPOSITORY_ROOT)


def _run_db_upgrade(args: argparse.Namespace) -> int:
    database_url = _resolved_database_url(args.database_url)
    report = upgrade_database(database_url)
    if report.get("result") != "UPGRADED":
        print(json.dumps(report, indent=2))
        return 2
    print(
        json.dumps(
            {
                "status": "upgraded",
                "revision": "head",
                "database_status": report["status"],
                "database_path": report.get("database_path"),
                "current_revisions": report["current_revisions"],
            },
            indent=2,
        )
    )
    return 0


def _run_db_status(args: argparse.Namespace) -> int:
    database_url = _resolved_database_url(args.database_url)
    report = inspect_database(database_url)
    revisions = report["current_revisions"]
    report["current_revision"] = revisions[0] if len(revisions) == 1 else None
    report["up_to_date"] = report["status"] == "CURRENT"
    print(json.dumps(report, indent=2))
    return 0 if report["up_to_date"] else 1


def _run_db_repair(args: argparse.Namespace) -> int:
    database_url = _resolved_database_url(args.database_url)
    try:
        report = repair_database(database_url)
    except DatabaseMigrationError as exc:
        report = {"status": "REFUSED", "message": str(exc), "details": exc.report}
    print(json.dumps(report, indent=2))
    return 0 if report.get("status") == "REPAIRED" else 2


def _run_auth_setup_demo(args: argparse.Namespace) -> int:
    password = os.getenv(args.password_env)
    if password is None:
        raise SystemExit(f"Required environment variable {args.password_env} is not set")
    settings = AuthSettings.from_environment()
    if settings.mode is not AuthMode.DEMO:
        raise SystemExit("Set NAIM_AUTH_MODE=demo before creating a demo account")
    store = WorkflowStore(_resolved_database_url(args.database_url))
    try:
        auth = AuthService(settings, store)
        auth.setup_demo_account(
            args.username,
            password,
            Role(args.role),
            replace=args.replace,
        )
    finally:
        store.close()
    print(
        json.dumps(
            {
                "status": "demo_account_ready",
                "username": args.username,
                "role": args.role,
                "password_source": args.password_env,
            },
            indent=2,
        )
    )
    return 0


def _run_auth_status(_: argparse.Namespace) -> int:
    settings = AuthSettings.from_environment()
    print(
        json.dumps(
            {
                "mode": settings.mode.value,
                "token_ttl_seconds": settings.token_ttl_seconds,
                "oidc_adapter_configured": settings.mode is AuthMode.OIDC,
                "data_mode": data_mode_from_environment().value,
            },
            indent=2,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="naim",
        description=(
            "nAIM Portfolio Intelligence Workbench — Name the movement. Own the evidence."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_parser = subparsers.add_parser(
        "doctor", help="Check the local Python runtime, configuration and backend dependencies."
    )
    doctor_parser.set_defaults(handler=_run_doctor)

    pipeline_parser = subparsers.add_parser(
        "pipeline", help="Generate, validate and optionally persist a governed dataset."
    )
    pipeline_parser.add_argument("--profile", choices=PROFILE_CHOICES, default="default")
    pipeline_parser.add_argument("--seed", type=int)
    pipeline_parser.add_argument("--data-root", type=Path, default=REPOSITORY_ROOT / "data")
    pipeline_parser.add_argument("--no-persist", action="store_true")
    pipeline_parser.set_defaults(handler=_run_pipeline)

    api_parser = subparsers.add_parser("api", help="Start the local versioned FastAPI service.")
    api_parser.add_argument("--profile", choices=PROFILE_CHOICES, default="default")
    api_parser.add_argument("--seed", type=int)
    api_parser.add_argument("--data-root", type=Path, default=REPOSITORY_ROOT / "data")
    api_parser.add_argument("--host", default="127.0.0.1")
    api_parser.add_argument("--port", type=int, default=8000)
    api_parser.add_argument("--reload", action="store_true")
    api_parser.add_argument(
        "--auth-mode",
        choices=[mode.value for mode in AuthMode],
        default=os.getenv("NAIM_AUTH_MODE", os.getenv("AUTH_MODE", "disabled")),
    )
    api_parser.add_argument(
        "--data-mode",
        choices=[mode.value for mode in DataMode],
        default=os.getenv("NAIM_DATA_MODE", DataMode.OFFLINE_SNAPSHOT.value).upper(),
    )
    api_parser.set_defaults(handler=_run_api)

    db_parser = subparsers.add_parser("db", help="Manage durable workflow-state migrations.")
    db_subparsers = db_parser.add_subparsers(dest="db_command", required=True)
    db_upgrade_parser = db_subparsers.add_parser("upgrade", help="Apply all database migrations.")
    db_upgrade_parser.add_argument("--database-url")
    db_upgrade_parser.set_defaults(handler=_run_db_upgrade)
    db_status_parser = db_subparsers.add_parser(
        "status", help="Report the current migration revision."
    )
    db_status_parser.add_argument("--database-url")
    db_status_parser.set_defaults(handler=_run_db_status)
    db_repair_parser = db_subparsers.add_parser(
        "repair",
        help=(
            "Back up and safely reconcile a compatible unstamped SQLite database before upgrade."
        ),
    )
    db_repair_parser.add_argument("--database-url")
    db_repair_parser.set_defaults(handler=_run_db_repair)

    auth_parser = subparsers.add_parser("auth", help="Configure local demonstration identity.")
    auth_subparsers = auth_parser.add_subparsers(dest="auth_command", required=True)
    auth_setup_parser = auth_subparsers.add_parser(
        "setup-demo", help="Create or replace a password-hashed demo account."
    )
    auth_setup_parser.add_argument("--username", required=True)
    auth_setup_parser.add_argument("--role", choices=[role.value for role in Role], required=True)
    auth_setup_parser.add_argument("--password-env", default="NAIM_DEMO_BOOTSTRAP_PASSWORD")
    auth_setup_parser.add_argument("--database-url")
    auth_setup_parser.add_argument("--replace", action="store_true")
    auth_setup_parser.set_defaults(handler=_run_auth_setup_demo)
    auth_status_parser = auth_subparsers.add_parser(
        "status", help="Report configured authentication and data modes."
    )
    auth_status_parser.set_defaults(handler=_run_auth_status)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
