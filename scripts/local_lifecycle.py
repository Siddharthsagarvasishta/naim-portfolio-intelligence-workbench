#!/usr/bin/env python3
"""Own the two-process, Docker-optional localhost lifecycle for nAIM."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from naim_risk.workflow.migrations import inspect_database, repair_database, upgrade_database
from naim_risk.workflow.store import database_url_from_environment

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FRONTEND_URL = "http://localhost:3000"
DEFAULT_API_URL = "http://127.0.0.1:8000"


class LifecycleError(RuntimeError):
    """Raised for a local lifecycle failure that is safe to show to the operator."""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _runtime_root() -> Path:
    configured = os.getenv("NAIM_RUNTIME_DIR")
    path = Path(configured).expanduser() if configured else ROOT / "work" / "local"
    return path.resolve()


def _state_path() -> Path:
    return _runtime_root() / "lifecycle.json"


def _log_root() -> Path:
    return _runtime_root() / "logs"


def _empty_state() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "product": "nAIM Portfolio Intelligence Workbench",
        "repository": str(ROOT),
        "updated_at": _utc_now(),
        "profile": os.getenv("PROFILE", "default"),
        "services": {},
        "last_successful_pipeline": None,
        "last_error": None,
    }


def _read_state() -> dict[str, Any]:
    path = _state_path()
    if not path.is_file():
        return _empty_state()
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LifecycleError(f"Lifecycle state is unreadable: {path}: {exc}") from exc
    return loaded if isinstance(loaded, dict) else _empty_state()


def _write_state(state: dict[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = _utc_now()
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _version_tuple(raw: str) -> tuple[int, int, int]:
    values = raw.strip().lstrip("v").split(".")
    return tuple(int(value) for value in (values + ["0", "0"])[:3])


def _verify_runtime() -> dict[str, str]:
    if sys.version_info < (3, 12):  # noqa: UP036 - lifecycle reports a user-facing preflight
        raise LifecycleError(f"Python 3.12+ is required; selected {sys.version.split()[0]}")
    node = shutil.which("node")
    npm = shutil.which("npm")
    if not node or not npm:
        raise LifecycleError("Node.js and npm are required. Run `make doctor` for details.")
    node_result = subprocess.run(
        [node, "--version"], capture_output=True, check=False, text=True, cwd=ROOT
    )
    node_version = node_result.stdout.strip() or node_result.stderr.strip()
    try:
        node_ok = node_result.returncode == 0 and _version_tuple(node_version) >= (22, 13, 0)
    except ValueError:
        node_ok = False
    if not node_ok:
        raise LifecycleError(f"Node.js 22.13+ is required; selected {node_version or 'unknown'}")
    return {"python": sys.version.split()[0], "node": node_version, "npm": npm}


def _port_is_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.25):
            return True
    except OSError:
        return False


def _process_command(pid: int) -> str | None:
    if pid <= 1:
        return None
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        capture_output=True,
        check=False,
        text=True,
    )
    command = result.stdout.strip()
    return command if result.returncode == 0 and command else None


def _owned_process(record: dict[str, Any]) -> bool:
    try:
        pid = int(record.get("pid", 0))
    except (TypeError, ValueError):
        return False
    expected = str(record.get("ownership_token", ""))
    command = _process_command(pid)
    return bool(command and expected and expected in command)


def _fetch_health(
    url: str,
    *,
    timeout: float = 1.0,
    max_body_bytes: int = 8192,
) -> dict[str, Any]:
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "nAIM-local-lifecycle/1.0"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = str(response.headers.get("Content-Type", ""))
            if "application/json" not in content_type:
                return {
                    "ok": 200 <= response.status < 400,
                    "status_code": response.status,
                    "body": None,
                }
            body = response.read(max_body_bytes + 1)
            if len(body) > max_body_bytes:
                return {
                    "ok": False,
                    "status_code": response.status,
                    "error": f"Response exceeded the {max_body_bytes}-byte lifecycle limit",
                }
            payload: Any = None
            payload = json.loads(body.decode("utf-8"))
            return {"ok": 200 <= response.status < 400, "status_code": response.status, "body": payload}
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _latest_pipeline(profile: str) -> dict[str, Any] | None:
    latest_path = ROOT / "data" / "manifests" / "latest.json"
    if not latest_path.is_file():
        return None
    try:
        latest = json.loads(latest_path.read_text(encoding="utf-8"))
        run_id = str(latest["run_id"])
        manifest_path = ROOT / "data" / "manifests" / run_id / "run_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return None
    run_profile = str(manifest.get("profile", run_id.split("-", 1)[0]))
    if run_profile != profile:
        return None
    return {
        "run_id": run_id,
        "profile": run_profile,
        "manifest": str(manifest_path),
        "validation_status": manifest.get("validation_status"),
    }


def _ensure_pipeline(profile: str) -> dict[str, Any]:
    existing = _latest_pipeline(profile)
    if existing is not None:
        return existing
    command = [
        sys.executable,
        "-m",
        "naim_risk.cli",
        "pipeline",
        "--profile",
        profile,
        "--data-root",
        str(ROOT / "data"),
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=_process_environment(),
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-2000:]
        raise LifecycleError(f"Dataset generation failed: {detail}")
    current = _latest_pipeline(profile)
    if current is None:
        raise LifecycleError("Dataset command completed but no validated run manifest was found")
    return current


def _process_environment() -> dict[str, str]:
    environment = dict(os.environ)
    current_pythonpath = environment.get("PYTHONPATH")
    source = str(ROOT / "src")
    environment["PYTHONPATH"] = (
        source if not current_pythonpath else os.pathsep.join((source, current_pythonpath))
    )
    return environment


def _ensure_database() -> dict[str, Any]:
    database_url = database_url_from_environment(ROOT)
    before = inspect_database(database_url)
    if before["status"] == "CURRENT":
        return before
    if before["status"] in {"EMPTY", "VERSIONED"}:
        result = upgrade_database(database_url)
        if result.get("result") != "UPGRADED":
            raise LifecycleError(f"Database upgrade refused: {result.get('message')}")
        return result
    result = repair_database(database_url)
    if result.get("status") != "REPAIRED":
        backup = (result.get("backup") or {}).get("path")
        raise LifecycleError(
            "Database repair refused an incompatible state. "
            f"Backup: {backup or 'not available'}. Review `make db-status`."
        )
    return result["after"]


def _service_records(
    profile: str,
    api_host: str,
    api_port: int,
    frontend_host: str,
    frontend_port: int,
    npm: str,
) -> dict[str, dict[str, Any]]:
    log_root = _log_root()
    log_root.mkdir(parents=True, exist_ok=True)
    return {
        "api": {
            "command": [
                sys.executable,
                "-m",
                "naim_risk.cli",
                "api",
                "--profile",
                profile,
                "--data-root",
                str(ROOT / "data"),
                "--host",
                api_host,
                "--port",
                str(api_port),
            ],
            "ownership_token": "naim_risk.cli api",
            "host": api_host,
            "port": api_port,
            "url": f"http://{api_host}:{api_port}",
            "health_url": f"http://{api_host}:{api_port}/api/v1/health",
            "log": str(log_root / "api.log"),
        },
        "frontend": {
            "command": [
                npm,
                "run",
                "dev",
                "--",
                "--host",
                frontend_host,
                "--port",
                str(frontend_port),
            ],
            "ownership_token": "npm run dev",
            "host": frontend_host,
            "port": frontend_port,
            "url": f"http://{frontend_host}:{frontend_port}",
            "health_url": f"http://{frontend_host}:{frontend_port}/",
            "log": str(log_root / "frontend.log"),
        },
    }


def _spawn(record: dict[str, Any]) -> None:
    log_path = Path(record["log"])
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log_handle:
        log_handle.write(f"\n[{_utc_now()}] starting: {' '.join(record['command'])}\n")
        log_handle.flush()
        process = subprocess.Popen(
            record["command"],
            cwd=ROOT,
            env=_process_environment(),
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    record["pid"] = process.pid
    record["process_group"] = process.pid
    record["started_at"] = _utc_now()


def _wait_for_health(services: dict[str, dict[str, Any]], timeout: float) -> None:
    deadline = time.monotonic() + timeout
    pending = set(services)
    while pending and time.monotonic() < deadline:
        for name in tuple(pending):
            record = services[name]
            if not _owned_process(record):
                raise LifecycleError(f"{name} stopped during startup; inspect {record['log']}")
            health = _fetch_health(record["health_url"])
            record["health"] = health
            if health.get("ok"):
                pending.remove(name)
        if pending:
            time.sleep(0.5)
    if pending:
        names = ", ".join(sorted(pending))
        raise LifecycleError(f"Timed out waiting for healthy local services: {names}")


def _warm_api_readiness(api: dict[str, Any], timeout: float) -> dict[str, Any]:
    """Initialize and validate the first analytical response before exposing the UI."""

    readiness_url = f"{str(api['url']).rstrip('/')}/api/v1/command-centre"
    source_url = f"{str(api['url']).rstrip('/')}/api/v1/data-source"
    result = _fetch_health(
        readiness_url,
        timeout=max(1.0, min(timeout, 90.0)),
        max_body_bytes=8 * 1024 * 1024,
    )
    payload = result.get("body")
    if not result.get("ok") or not isinstance(payload, dict):
        detail = result.get("error") or f"HTTP {result.get('status_code', 'unknown')}"
        raise LifecycleError(f"API analytical readiness failed: {detail}")

    source_result = _fetch_health(
        source_url,
        timeout=max(1.0, min(timeout, 30.0)),
        max_body_bytes=1024 * 1024,
    )
    source_payload = source_result.get("body")
    if not source_result.get("ok") or not isinstance(source_payload, dict):
        detail = source_result.get("error") or (
            f"HTTP {source_result.get('status_code', 'unknown')}"
        )
        raise LifecycleError(f"API data-source readiness failed: {detail}")

    metadata = payload.get("metadata")
    source_context = source_payload.get("context")
    kpis = payload.get("kpis")
    if not isinstance(metadata, dict) or not isinstance(source_context, dict):
        raise LifecycleError("API analytical readiness response omitted governed provenance")
    if not isinstance(kpis, list) or not kpis:
        raise LifecycleError("API analytical readiness response contained no KPI results")
    evidence = [
        row.get("runtime_evidence") if isinstance(row, dict) else None
        for row in kpis
    ]
    if any(not isinstance(item, dict) for item in evidence):
        raise LifecycleError("API analytical readiness KPI omitted runtime evidence")
    evidence_rows = [item for item in evidence if isinstance(item, dict)]
    data_mode = source_payload.get("mode")
    run_id = metadata.get("run_id")
    configuration_hash = metadata.get("configuration_hash")
    dataset_hash = source_context.get("dataset_hash")
    if (
        data_mode not in {"LIVE", "DEMO", "OFFLINE_SNAPSHOT"}
        or source_context.get("active_mode") != data_mode
        or not run_id
        or source_context.get("run_id") != run_id
        or not configuration_hash
        or source_context.get("configuration_hash") != configuration_hash
        or not dataset_hash
        or metadata.get("quality_status") != "PASS"
        or metadata.get("publication_allowed") is not True
        or any(
            item.get("run_id") != run_id
            or item.get("configuration_hash") != configuration_hash
            or item.get("dataset_hash") != dataset_hash
            or not item.get("binding_sha256")
            for item in evidence_rows
        )
    ):
        raise LifecycleError("API analytical readiness response failed provenance or quality checks")

    readiness = {
        "ok": True,
        "url": readiness_url,
        "source_url": source_url,
        "data_mode": data_mode,
        "run_id": run_id,
        "configuration_hash": configuration_hash,
        "dataset_hash": dataset_hash,
        "kpi_count": len(kpis),
        "warmed_at": _utc_now(),
    }
    api["analytical_readiness"] = readiness
    return readiness


def _stop_record(record: dict[str, Any], *, timeout: float = 12.0) -> dict[str, Any]:
    pid = int(record.get("pid") or 0)
    if not _owned_process(record):
        return {"stopped": True, "previous_pid": pid or None, "detail": "not running or stale PID"}
    group = int(record.get("process_group") or 0)
    try:
        actual_group = os.getpgid(pid)
    except ProcessLookupError:
        return {"stopped": True, "previous_pid": pid, "detail": "already stopped"}
    if group != pid or actual_group != group:
        raise LifecycleError(f"Refusing to stop PID {pid}: recorded process-group ownership is invalid")
    os.killpg(group, signal.SIGTERM)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and _process_command(pid) is not None:
        time.sleep(0.2)
    if _process_command(pid) is not None:
        os.killpg(group, signal.SIGKILL)
        time.sleep(0.2)
    return {
        "stopped": _process_command(pid) is None,
        "previous_pid": pid,
        "detail": "nAIM-owned process group stopped",
    }


def stop_services(*, quiet: bool = False) -> dict[str, Any]:
    state = _read_state()
    stopped: dict[str, Any] = {}
    errors: list[str] = []
    for name, record in (state.get("services") or {}).items():
        try:
            stopped[name] = _stop_record(record)
            if not stopped[name]["stopped"]:
                errors.append(f"{name}: recorded process did not stop")
            else:
                record["pid"] = None
                record["process_group"] = None
                record["stopped_at"] = _utc_now()
        except (LifecycleError, OSError) as exc:
            errors.append(f"{name}: {exc}")
        host = str(record.get("host") or ("127.0.0.1" if name == "api" else "localhost"))
        port = int(record.get("port") or 0)
        if port and _port_is_open(host, port):
            errors.append(f"{name}: port {host}:{port} was not released")
    if errors:
        state["last_error"] = "; ".join(errors)
    _write_state(state)
    report = {"status": "STOPPED" if not errors else "PARTIAL", "services": stopped, "errors": errors}
    if not quiet:
        print(json.dumps(report, indent=2))
    return report


def start_services(args: argparse.Namespace) -> dict[str, Any]:
    runtime = _verify_runtime()
    previous = _read_state()
    existing = previous.get("services") or {}
    if any(_owned_process(record) for record in existing.values()):
        stop_services(quiet=True)
    for host, port, label in (
        (args.api_host, args.api_port, "API"),
        (args.frontend_host, args.frontend_port, "frontend"),
    ):
        if _port_is_open(host, port):
            raise LifecycleError(
                f"{label} port {host}:{port} is already in use by an unrecorded process"
            )
    database = _ensure_database()
    pipeline = _ensure_pipeline(args.profile)
    services = _service_records(
        args.profile,
        args.api_host,
        args.api_port,
        args.frontend_host,
        args.frontend_port,
        runtime["npm"],
    )
    state = _empty_state()
    state.update(
        {
            "profile": args.profile,
            "runtime": {"python": runtime["python"], "node": runtime["node"]},
            "database_path": database.get("database_path"),
            "database_status": database.get("status"),
            "last_successful_pipeline": pipeline,
            "services": services,
            "last_error": None,
        }
    )
    try:
        for record in services.values():
            _spawn(record)
            _write_state(state)
        _wait_for_health(services, args.timeout)
        _warm_api_readiness(services["api"], args.timeout)
    except Exception as exc:
        state["last_error"] = str(exc)
        _write_state(state)
        stop_services(quiet=True)
        raise
    _write_state(state)
    frontend_url = services["frontend"]["url"]
    opened = False
    if not args.no_open:
        opened = bool(webbrowser.open(frontend_url))
    report = {
        "status": "RUNNING",
        "frontend": {
            "url": frontend_url,
            "pid": services["frontend"]["pid"],
            "health": services["frontend"]["health"],
        },
        "api": {
            "url": services["api"]["url"],
            "docs": f"{services['api']['url']}/api/docs",
            "pid": services["api"]["pid"],
            "health": services["api"]["health"],
            "analytical_readiness": services["api"]["analytical_readiness"],
        },
        "profile": args.profile,
        "database_path": database.get("database_path"),
        "last_successful_pipeline": pipeline,
        "logs": str(_log_root()),
        "browser_open_requested": not args.no_open,
        "browser_opened": opened,
    }
    print(json.dumps(report, indent=2))
    return report


def status_services(*, require_running: bool = False) -> int:
    state = _read_state()
    services: dict[str, Any] = {}
    all_running = True
    for name in ("api", "frontend"):
        record = (state.get("services") or {}).get(name) or {}
        running = _owned_process(record)
        port = int(record.get("port") or (8000 if name == "api" else 3000))
        host = str(record.get("host") or ("127.0.0.1" if name == "api" else "localhost"))
        port_open = _port_is_open(host, port)
        health = _fetch_health(str(record.get("health_url"))) if running else {"ok": False}
        services[name] = {
            "running": running,
            "pid": record.get("pid") if running else None,
            "host": host,
            "port": port,
            "port_state": "OWNED" if running and port_open else "IN_USE_UNRECORDED" if port_open else "FREE",
            "health": health,
            "log": record.get("log"),
        }
        all_running = all_running and running and bool(health.get("ok"))
    database_url = database_url_from_environment(ROOT)
    database = inspect_database(database_url)
    report = {
        "status": "RUNNING" if all_running else "STOPPED_OR_DEGRADED",
        "services": services,
        "dataset_profile": state.get("profile", os.getenv("PROFILE", "default")),
        "database_path": database.get("database_path"),
        "database_status": database.get("status"),
        "last_successful_pipeline": state.get("last_successful_pipeline"),
        "last_error": state.get("last_error"),
        "state_file": str(_state_path()),
    }
    print(json.dumps(report, indent=2))
    return 0 if all_running or not require_running else 1


def show_logs(lines: int) -> int:
    state = _read_state()
    output: dict[str, Any] = {}
    for name in ("api", "frontend"):
        record = (state.get("services") or {}).get(name) or {}
        path_value = record.get("log")
        path = Path(path_value) if path_value else _log_root() / f"{name}.log"
        if path.is_file():
            output[name] = {"path": str(path), "tail": path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]}
        else:
            output[name] = {"path": str(path), "tail": [], "message": "log not created yet"}
    print(json.dumps(output, indent=2))
    return 0


def open_frontend() -> int:
    state = _read_state()
    record = (state.get("services") or {}).get("frontend") or {}
    if not _owned_process(record) or not _fetch_health(str(record.get("health_url"))).get("ok"):
        raise LifecycleError("Frontend is not healthy. Run `make start`, then try `make open`.")
    url = str(record.get("url") or DEFAULT_FRONTEND_URL)
    if not webbrowser.open(url):
        raise LifecycleError(f"The browser did not accept {url}; open it manually.")
    print(json.dumps({"status": "OPENED", "url": url}, indent=2))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    for start_action in ("start", "restart"):
        start = subparsers.add_parser(start_action)
        start.add_argument("--profile", default=os.getenv("PROFILE", "default"))
        start.add_argument("--api-host", default=os.getenv("API_HOST", "127.0.0.1"))
        start.add_argument("--api-port", type=int, default=int(os.getenv("API_PORT", "8000")))
        start.add_argument(
            "--frontend-host", default=os.getenv("FRONTEND_HOST", "localhost")
        )
        start.add_argument(
            "--frontend-port", type=int, default=int(os.getenv("FRONTEND_PORT", "3000"))
        )
        start.add_argument(
            "--timeout",
            type=float,
            default=float(os.getenv("NAIM_START_TIMEOUT_SECONDS", "300")),
        )
        start.add_argument(
            "--no-open",
            action="store_true",
            default=os.getenv("NAIM_NO_OPEN", "0").strip().lower()
            in {"1", "true", "yes"},
        )
    subparsers.add_parser("stop")
    status = subparsers.add_parser("status")
    status.add_argument("--require-running", action="store_true")
    subparsers.add_parser("open")
    logs = subparsers.add_parser("logs")
    logs.add_argument("--lines", type=int, default=80)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.action == "start":
            start_services(args)
            return 0
        if args.action == "stop":
            return 0 if stop_services()["status"] == "STOPPED" else 1
        if args.action == "restart":
            stop_services(quiet=True)
            start_services(args)
            return 0
        if args.action == "status":
            return status_services(require_running=args.require_running)
        if args.action == "open":
            return open_frontend()
        if args.action == "logs":
            return show_logs(args.lines)
    except (LifecycleError, OSError, subprocess.SubprocessError) as exc:
        state = _read_state()
        state["last_error"] = str(exc)
        _write_state(state)
        print(json.dumps({"status": "ERROR", "message": str(exc)}, indent=2), file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
