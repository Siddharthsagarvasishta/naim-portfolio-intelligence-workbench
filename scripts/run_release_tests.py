#!/usr/bin/env python3
"""Run and persist the backend, frontend, and real-local-lifecycle release gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "outputs" / "validation" / "test_results.json"
SUITE_CATEGORIES = ("backend", "frontend", "e2e")
AUTHORED_SOURCE_ROOTS = (
    "alembic",
    "app",
    "apps",
    "config",
    "docs",
    "scripts",
    "src",
    "tests",
    ".openai",
)
AUTHORED_SOURCE_FILES = (
    "Makefile",
    "pyproject.toml",
    "package.json",
    "package-lock.json",
    "vite.config.ts",
)
REQUIRED_FILE_BINDINGS = (
    "package_lock",
    "configuration",
    "canonical_evidence",
    "run_manifest",
    "openapi_contract",
    "openapi_validation",
    "reconciliation",
)
REPRESENTATIVE_FRONTEND_ROUTES = (
    "/root-cause",
    "/vintage",
    "/strategy",
    "/alerts",
    "/model-monitoring",
    "/market-risk",
    "/advanced-statistics",
    "/exports",
    "/capabilities",
    "/instant-demo",
)


@dataclass(frozen=True)
class CommandResult:
    """Captured command result with a runner-measured wall-clock duration."""

    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float


@dataclass(frozen=True)
class HttpResult:
    """Small HTTP result used by the real runner and focused injected tests."""

    url: str
    status_code: int | None
    headers: Mapping[str, str]
    body: str
    duration_seconds: float
    error: str | None = None


CommandRunner = Callable[[Sequence[str], Path, Mapping[str, str] | None], CommandResult]
HttpGetter = Callable[[str, float], HttpResult]
PortProbe = Callable[[str, int], bool]


@dataclass(frozen=True)
class RuntimeDependencies:
    """Replaceable side-effect boundary for deterministic focused tests."""

    run_command: CommandRunner
    http_get: HttpGetter
    port_is_open: PortProbe
    monotonic: Callable[[], float]
    sleep: Callable[[float], None]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _portable(path: Path, root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _file_binding(path: Path, root: Path, *, invocation_id: str | None = None) -> dict[str, Any]:
    modified_at = (
        datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat() if path.is_file() else None
    )
    record: dict[str, Any] = {
        "path": _portable(path, root),
        "status": "AVAILABLE" if path.is_file() else "MISSING",
        "bytes": path.stat().st_size if path.is_file() else None,
        "sha256": _sha256(path) if path.is_file() else None,
        "modified_at": modified_at,
    }
    if invocation_id is not None:
        record["invocation_id"] = invocation_id
        record["generated_in_invocation"] = path.is_file()
    return record


def _authored_source_binding(root: Path) -> dict[str, Any]:
    files: list[Path] = []
    for name in AUTHORED_SOURCE_ROOTS:
        candidate = root / name
        if candidate.is_dir():
            files.extend(path for path in candidate.rglob("*") if path.is_file())
    files.extend(path for name in AUTHORED_SOURCE_FILES if (path := root / name).is_file())
    digest = hashlib.sha256()
    included = 0
    for path in sorted(set(files)):
        if any(part in {"__pycache__", ".pytest_cache", ".ruff_cache"} for part in path.parts):
            continue
        if path.suffix.lower() in {".pyc", ".pyo"}:
            continue
        digest.update(_portable(path, root).encode("utf-8"))
        digest.update(b"\0")
        digest.update(_sha256(path).encode("ascii"))
        digest.update(b"\n")
        included += 1
    return {
        "basis": "portable-authored-tree-v1",
        "sha256": digest.hexdigest(),
        "file_count": included,
        "roots": list(AUTHORED_SOURCE_ROOTS),
        "top_level_files": list(AUTHORED_SOURCE_FILES),
    }


def _duration(value: float) -> float:
    return round(max(0.0, float(value)), 3)


def _tail(value: str, limit: int = 2000) -> str | None:
    text = value.strip()
    return text[-limit:] if text else None


def _run_command(
    command: Sequence[str], cwd: Path, extra_environment: Mapping[str, str] | None
) -> CommandResult:
    started = time.monotonic()
    environment = dict(os.environ)
    if extra_environment:
        environment.update(extra_environment)
    try:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            env=environment,
            capture_output=True,
            check=False,
            text=True,
        )
        returncode = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except OSError as exc:
        returncode = 127
        stdout = ""
        stderr = f"{type(exc).__name__}: {exc}"
    return CommandResult(
        command=tuple(str(item) for item in command),
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        duration_seconds=_duration(time.monotonic() - started),
    )


def _http_get(url: str, timeout: float) -> HttpResult:
    started = time.monotonic()
    request = urllib.request.Request(url, headers={"User-Agent": "nAIM-release-tests/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(1_048_576).decode("utf-8", errors="replace")
            headers = {key.lower(): value for key, value in response.headers.items()}
            return HttpResult(
                url=url,
                status_code=response.status,
                headers=headers,
                body=body,
                duration_seconds=_duration(time.monotonic() - started),
            )
    except urllib.error.HTTPError as exc:
        body = exc.read(1_048_576).decode("utf-8", errors="replace")
        headers = {key.lower(): value for key, value in exc.headers.items()}
        return HttpResult(
            url=url,
            status_code=exc.code,
            headers=headers,
            body=body,
            duration_seconds=_duration(time.monotonic() - started),
            error=f"HTTPError: {exc}",
        )
    except (OSError, urllib.error.URLError) as exc:
        return HttpResult(
            url=url,
            status_code=None,
            headers={},
            body="",
            duration_seconds=_duration(time.monotonic() - started),
            error=f"{type(exc).__name__}: {exc}",
        )


def _port_is_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.25):
            return True
    except OSError:
        return False


def default_dependencies() -> RuntimeDependencies:
    return RuntimeDependencies(
        run_command=_run_command,
        http_get=_http_get,
        port_is_open=_port_is_open,
        monotonic=time.monotonic,
        sleep=time.sleep,
    )


def _empty_suite(category: str) -> dict[str, Any]:
    return {
        "name": category,
        "category": category,
        "status": "NOT_RUN",
        "passed": None,
        "failed": None,
        "skipped": None,
        "warnings": None,
        "duration_seconds": None,
        "command": None,
        "evidence": {},
        "limitations": ["This suite was not selected in this invocation."],
    }


def _parse_junit(path: Path) -> dict[str, Any]:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        return {"status": "UNAVAILABLE", "error": f"{type(exc).__name__}: {exc}"}

    def attributes(element: ET.Element) -> dict[str, float]:
        values: dict[str, float] = {}
        for key in ("tests", "failures", "errors", "skipped", "time"):
            try:
                values[key] = float(element.attrib.get(key, "0"))
            except ValueError:
                values[key] = 0.0
        return values

    if root.attrib.get("tests") is not None:
        totals = attributes(root)
    elif root.tag.rsplit("}", 1)[-1] == "testsuite":
        totals = attributes(root)
    else:
        direct_suites = [child for child in root if child.tag.rsplit("}", 1)[-1] == "testsuite"]
        totals = {
            key: sum(attributes(suite)[key] for suite in direct_suites)
            for key in ("tests", "failures", "errors", "skipped", "time")
        }
    tests = int(totals["tests"])
    failures = int(totals["failures"])
    errors = int(totals["errors"])
    skipped = int(totals["skipped"])
    passed = max(0, tests - failures - errors - skipped)
    return {
        "status": "AVAILABLE",
        "tests": tests,
        "passed": passed,
        "failures": failures,
        "errors": errors,
        "failed": failures + errors,
        "skipped": skipped,
        "reported_duration_seconds": _duration(totals["time"]),
    }


def _parse_coverage(path: Path, source: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        percent = float(payload["totals"]["percent_covered"])
        if not 0.0 <= percent <= 100.0:
            raise ValueError("coverage percent is outside 0..100")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {
            "status": "UNAVAILABLE",
            "percent": None,
            "source": source,
            "scope": "Full backend pytest suite over naim_risk.",
            "error": f"{type(exc).__name__}: {exc}",
        }
    return {
        "status": "AVAILABLE",
        "percent": percent,
        "source": source,
        "scope": "Full backend pytest suite over naim_risk.",
    }


def _parse_warning_count(output: str) -> int:
    matches = re.findall(r"(?im)(\d+)\s+warnings?\b", output)
    return max((int(value) for value in matches), default=0)


def _parse_tap(output: str) -> dict[str, Any]:
    summary: dict[str, int] = {}
    for key, value in re.findall(
        r"(?im)^\s*#\s*(tests|pass|fail|cancelled|skipped|todo)\s+(\d+)\s*$", output
    ):
        summary[key.lower()] = int(value)
    required = {"tests", "pass", "fail"}
    if not required.issubset(summary):
        return {
            "status": "UNAVAILABLE",
            "error": "Node TAP summary is missing one or more required count fields.",
        }
    cancelled = summary.get("cancelled", 0)
    skipped = summary.get("skipped", 0)
    todo = summary.get("todo", 0)
    failed = summary["fail"] + cancelled
    counts_consistent = summary["tests"] == summary["pass"] + failed + skipped + todo
    return {
        "status": "AVAILABLE",
        "tests": summary["tests"],
        "passed": summary["pass"],
        "failed": failed,
        "skipped": skipped + todo,
        "cancelled": cancelled,
        "todo": todo,
        "counts_consistent": counts_consistent,
    }


def _extract_last_json_object(text: str) -> dict[str, Any] | None:
    decoder = json.JSONDecoder()
    found: dict[str, Any] | None = None
    longest = -1
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, consumed = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and consumed > longest:
            found = value
            longest = consumed
    return found


class ReleaseTestRunner:
    """Orchestrate release suites while keeping all side effects injectable."""

    def __init__(
        self,
        *,
        root: Path = ROOT,
        output_path: Path | None = None,
        dependencies: RuntimeDependencies | None = None,
        profile: str = "default",
        api_host: str = "127.0.0.1",
        api_port: int = 8000,
        frontend_host: str = "localhost",
        frontend_port: int = 3000,
        http_timeout: float = 10.0,
        port_release_timeout: float = 10.0,
        python_executable: str = sys.executable,
        npm_executable: str = "npm",
        make_executable: str = "make",
        runtime_directory: Path | None = None,
    ) -> None:
        self.root = root.resolve()
        self.output_path = (output_path or self.root / DEFAULT_OUTPUT.relative_to(ROOT)).resolve()
        self.dependencies = dependencies or default_dependencies()
        self.profile = profile
        self.api_host = api_host
        self.api_port = api_port
        self.frontend_host = frontend_host
        self.frontend_port = frontend_port
        self.http_timeout = http_timeout
        self.port_release_timeout = port_release_timeout
        self.python_executable = python_executable
        self.npm_executable = npm_executable
        self.make_executable = make_executable
        self.runtime_directory = (
            runtime_directory or self.root / "work" / "release-tests" / "lifecycle"
        ).resolve()
        self._invocation_id: str | None = None

    @property
    def validation_directory(self) -> Path:
        return self.output_path.parent

    def _portable(self, path: Path) -> str:
        return _portable(path, self.root)

    def _run_manifest_path(self) -> Path:
        canonical_path = self.root / "exports" / "validation" / "interop_evidence_snapshot.json"
        try:
            canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
            run_id = str((canonical.get("metadata") or {}).get("run_id") or "")
        except (OSError, json.JSONDecodeError, AttributeError):
            run_id = ""
        if run_id:
            return self.root / "data" / "manifests" / run_id / "run_manifest.json"
        return self.root / "data" / "manifests" / "UNAVAILABLE" / "run_manifest.json"

    def _release_bindings(self) -> dict[str, Any]:
        paths = {
            "package_lock": self.root / "package-lock.json",
            "configuration": self.root / "config" / "feature_status.yaml",
            "canonical_evidence": (
                self.root / "exports" / "validation" / "interop_evidence_snapshot.json"
            ),
            "run_manifest": self._run_manifest_path(),
            "openapi_contract": self.root / "outputs" / "contracts" / "openapi.json",
            "openapi_validation": (self.root / "outputs" / "contracts" / "openapi_validation.json"),
            "reconciliation": (
                self.root / "outputs" / "validation" / "cross_artifact_reconciliation.json"
            ),
        }
        bindings = {
            "source_tree": _authored_source_binding(self.root),
            **{name: _file_binding(path, self.root) for name, path in paths.items()},
        }
        bindings["status"] = (
            "PASS"
            if all(bindings[name]["status"] == "AVAILABLE" for name in REQUIRED_FILE_BINDINGS)
            else "INCOMPLETE"
        )
        return bindings

    def _pythonpath_environment(self) -> dict[str, str]:
        existing = os.environ.get("PYTHONPATH")
        source = str(self.root / "src")
        return {"PYTHONPATH": source if not existing else os.pathsep.join((source, existing))}

    def _backend_environment(self) -> dict[str, str]:
        return {**self._pythonpath_environment(), "NAIM_DATASET_PROFILE": "test"}

    def _lifecycle_environment(self) -> dict[str, str]:
        return {
            **self._pythonpath_environment(),
            "NAIM_RUNTIME_DIR": str(self.runtime_directory),
            "NO_OPEN": "1",
        }

    def _display_python(self) -> str:
        executable = Path(self.python_executable)
        if not executable.is_absolute():
            return self.python_executable
        try:
            return executable.relative_to(self.root).as_posix()
        except ValueError:
            return self.python_executable

    def _command(
        self, command: Sequence[str], environment: Mapping[str, str] | None = None
    ) -> CommandResult:
        try:
            return self.dependencies.run_command(command, self.root, environment)
        except Exception as exc:  # pragma: no cover - defensive boundary for injected executors
            return CommandResult(
                command=tuple(command),
                returncode=127,
                stdout="",
                stderr=f"{type(exc).__name__}: {exc}",
                duration_seconds=0.0,
            )

    def plan(self, selected: Sequence[str]) -> dict[str, Any]:
        selected_set = set(selected)
        return {
            "schema_version": "1.0.0",
            "dry_run": True,
            "selected_suites": [name for name in SUITE_CATEGORIES if name in selected_set],
            "output": self._portable(self.output_path),
            "commands": {
                "backend": [
                    self._display_python(),
                    "-m",
                    "pytest",
                    "-o",
                    "addopts=",
                    "-q",
                    "--strict-markers",
                    "--junitxml=outputs/validation/backend_junit.xml",
                    "--cov=src/naim_risk",
                    "--cov-report=json:outputs/validation/backend_coverage.json",
                    "--cov-report=term-missing",
                ],
                "frontend": [self.npm_executable, "test"],
                "e2e_start": self._make_start_command(),
                "e2e_status": [
                    self.make_executable,
                    "status",
                    f"PYTHON={self._display_python()}",
                ],
                "e2e_stop": [
                    self.make_executable,
                    "stop",
                    f"PYTHON={self._display_python()}",
                ],
            },
            "e2e_urls": self._e2e_urls(),
            "note": "Dry-run does not execute commands, issue HTTP requests, or write evidence.",
        }

    def _run_backend(self) -> tuple[dict[str, Any], dict[str, Any]]:
        self.validation_directory.mkdir(parents=True, exist_ok=True)
        canonical_junit = self.validation_directory / "backend_junit.xml"
        canonical_coverage = self.validation_directory / "backend_coverage.json"
        with tempfile.TemporaryDirectory(
            prefix=".release-tests-", dir=self.validation_directory
        ) as temporary_directory:
            temporary = Path(temporary_directory)
            junit_path = temporary / "backend_junit.xml"
            coverage_path = temporary / "backend_coverage.json"
            command = [
                self.python_executable,
                "-m",
                "pytest",
                "-o",
                "addopts=",
                "-q",
                "--strict-markers",
                "--junitxml",
                str(junit_path),
                "--cov=src/naim_risk",
                f"--cov-report=json:{coverage_path}",
                "--cov-report=term-missing",
            ]
            result = self._command(command, self._backend_environment())
            junit = _parse_junit(junit_path)
            coverage = _parse_coverage(coverage_path, self._portable(canonical_coverage))
            junit_generated = junit_path.is_file()
            coverage_generated = coverage_path.is_file()
            if junit_generated:
                os.replace(junit_path, canonical_junit)
            if coverage_generated:
                os.replace(coverage_path, canonical_coverage)

        invocation_id = self._invocation_id or "UNAVAILABLE"
        junit_artifact = (
            _file_binding(canonical_junit, self.root, invocation_id=invocation_id)
            if junit_generated
            else None
        )
        coverage_artifact = (
            _file_binding(canonical_coverage, self.root, invocation_id=invocation_id)
            if coverage_generated
            else None
        )
        if coverage_artifact is not None:
            coverage["artifact"] = coverage_artifact
            coverage["invocation_id"] = invocation_id

        output = "\n".join((result.stdout, result.stderr))
        warnings = _parse_warning_count(output)
        passed = junit.get("passed") if junit.get("status") == "AVAILABLE" else None
        failed = junit.get("failed") if junit.get("status") == "AVAILABLE" else None
        skipped = junit.get("skipped") if junit.get("status") == "AVAILABLE" else None
        valid = (
            result.returncode == 0
            and junit.get("status") == "AVAILABLE"
            and int(junit.get("tests") or 0) > 0
            and int(failed or 0) == 0
            and coverage.get("percent") is not None
        )
        suite = {
            "name": "backend",
            "category": "backend",
            "status": "PASS" if valid else "FAIL",
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "warnings": warnings,
            "duration_seconds": _duration(result.duration_seconds),
            "command": self.plan(["backend"])["commands"]["backend"],
            "exit_code": result.returncode,
            "evidence": {
                "junit": self._portable(canonical_junit) if junit_generated else None,
                "coverage": coverage.get("source") if coverage.get("percent") is not None else None,
                "junit_summary": junit,
                "junit_artifact": junit_artifact,
                "coverage_artifact": coverage_artifact,
            },
            "limitations": [] if valid else ["Backend evidence is incomplete or failed."],
        }
        if not valid:
            suite["error"] = _tail(result.stderr or result.stdout) or junit.get("error")
        return suite, coverage

    def _run_frontend(self) -> dict[str, Any]:
        result = self._command([self.npm_executable, "test"])
        output = "\n".join((result.stdout, result.stderr))
        tap = _parse_tap(output)
        passed = tap.get("passed") if tap.get("status") == "AVAILABLE" else None
        failed = tap.get("failed") if tap.get("status") == "AVAILABLE" else None
        skipped = tap.get("skipped") if tap.get("status") == "AVAILABLE" else None
        valid = (
            result.returncode == 0
            and tap.get("status") == "AVAILABLE"
            and int(tap.get("tests") or 0) > 0
            and int(failed or 0) == 0
            and tap.get("counts_consistent") is True
        )
        suite = {
            "name": "frontend",
            "category": "frontend",
            "status": "PASS" if valid else "FAIL",
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "warnings": _parse_warning_count(output),
            "duration_seconds": _duration(result.duration_seconds),
            "command": [self.npm_executable, "test"],
            "exit_code": result.returncode,
            "evidence": {"source": "npm test TAP output", "tap_summary": tap},
            "limitations": [] if valid else ["Frontend TAP evidence is incomplete or failed."],
        }
        if not valid:
            suite["error"] = _tail(result.stderr or result.stdout) or tap.get("error")
        return suite

    def _make_start_command(self) -> list[str]:
        return [
            self.make_executable,
            "start",
            "NO_OPEN=1",
            f"PROFILE={self.profile}",
            f"API_HOST={self.api_host}",
            f"API_PORT={self.api_port}",
            f"FRONTEND_HOST={self.frontend_host}",
            f"FRONTEND_PORT={self.frontend_port}",
            f"PYTHON={self._display_python()}",
        ]

    def _e2e_urls(self) -> dict[str, str]:
        api = f"http://{self.api_host}:{self.api_port}"
        frontend = f"http://{self.frontend_host}:{self.frontend_port}"
        urls = {
            "api_health": f"{api}/api/v1/health",
            "frontend_root": f"{frontend}/",
            "api_docs": f"{api}/api/docs",
            "api_data_source": f"{api}/api/v1/data-source",
            "api_capabilities": f"{api}/api/v1/capabilities",
            "api_command_centre": f"{api}/api/v1/command-centre",
        }
        for route in REPRESENTATIVE_FRONTEND_ROUTES:
            urls[f"frontend_route_{route.removeprefix('/').replace('-', '_')}"] = frontend + route
        return urls

    def _check_command(
        self,
        name: str,
        command: Sequence[str],
        *,
        require_running_status: bool = False,
        environment: Mapping[str, str] | None = None,
    ) -> tuple[dict[str, Any], CommandResult]:
        result = self._command(command, environment)
        valid = result.returncode == 0
        parsed: dict[str, Any] | None = None
        if require_running_status:
            parsed = _extract_last_json_object(result.stdout)
            services = (parsed or {}).get("services") or {}
            valid = bool(
                valid
                and (parsed or {}).get("status") == "RUNNING"
                and all(
                    bool((services.get(service) or {}).get("running"))
                    and bool(((services.get(service) or {}).get("health") or {}).get("ok"))
                    for service in ("api", "frontend")
                )
            )
        check = {
            "check": name,
            "status": "PASS" if valid else "FAIL",
            "duration_seconds": _duration(result.duration_seconds),
            "exit_code": result.returncode,
        }
        if parsed is not None:
            check["observed_status"] = parsed.get("status")
        if not valid:
            check["detail"] = _tail(result.stderr or result.stdout) or "Command failed validation."
        return check, result

    def _check_http(self, name: str, url: str, expectation: str) -> dict[str, Any]:
        try:
            result = self.dependencies.http_get(url, self.http_timeout)
        except Exception as exc:  # pragma: no cover - defensive boundary
            result = HttpResult(url, None, {}, "", 0.0, f"{type(exc).__name__}: {exc}")
        valid = result.error is None and result.status_code == 200
        detail: str | None = result.error
        if valid and expectation in {"healthy_json", "available_json", "json"}:
            try:
                payload = json.loads(result.body)
            except json.JSONDecodeError as exc:
                valid = False
                detail = f"JSONDecodeError: {exc}"
            else:
                if expectation == "healthy_json":
                    valid = bool(
                        isinstance(payload, dict)
                        and payload.get("status") == "healthy"
                        and payload.get("publication_allowed") is True
                        and payload.get("quality_status") == "PASS"
                    )
                    if not valid:
                        detail = "Health payload did not report healthy publication-ready state."
                elif expectation == "available_json":
                    valid = bool(isinstance(payload, dict) and payload.get("available") is True)
                    if not valid:
                        detail = "Data-source payload did not report available=true."
                elif not isinstance(payload, dict):
                    valid = False
                    detail = "Expected a JSON object."
        if valid and expectation == "html":
            content_type = str(result.headers.get("content-type", "")).lower()
            valid = "text/html" in content_type
            if not valid:
                detail = f"Expected text/html, received {content_type or 'no content type'}."
        return {
            "check": name,
            "status": "PASS" if valid else "FAIL",
            "duration_seconds": _duration(result.duration_seconds),
            "url": url,
            "status_code": result.status_code,
            **({"detail": detail or "HTTP validation failed."} if not valid else {}),
        }

    def _wait_for_port_release(self, host: str, port: int) -> bool:
        deadline = self.dependencies.monotonic() + self.port_release_timeout
        while self.dependencies.port_is_open(host, port):
            if self.dependencies.monotonic() >= deadline:
                return False
            self.dependencies.sleep(min(0.1, self.port_release_timeout))
        return True

    @staticmethod
    def _skipped_check(name: str, detail: str) -> dict[str, Any]:
        return {
            "check": name,
            "status": "SKIPPED",
            "duration_seconds": 0.0,
            "detail": detail,
        }

    def _run_e2e(self) -> dict[str, Any]:
        started_at = self.dependencies.monotonic()
        checks: list[dict[str, Any]] = []
        api_initially_open = self.dependencies.port_is_open(self.api_host, self.api_port)
        frontend_initially_open = self.dependencies.port_is_open(
            self.frontend_host, self.frontend_port
        )
        checks.extend(
            [
                {
                    "check": "preflight_api_port_free",
                    "status": "FAIL" if api_initially_open else "PASS",
                    "duration_seconds": 0.0,
                    **(
                        {
                            "detail": "API port is already in use; refusing to stop an unowned process."
                        }
                        if api_initially_open
                        else {}
                    ),
                },
                {
                    "check": "preflight_frontend_port_free",
                    "status": "FAIL" if frontend_initially_open else "PASS",
                    "duration_seconds": 0.0,
                    **(
                        {
                            "detail": (
                                "Frontend port is already in use; refusing to stop an unowned process."
                            )
                        }
                        if frontend_initially_open
                        else {}
                    ),
                },
            ]
        )
        urls = self._e2e_urls()
        after_start_checks = ["lifecycle_status", *urls]
        start_attempted = False
        if api_initially_open or frontend_initially_open:
            reason = "Lifecycle start was not attempted because a requested port was occupied."
            checks.append(self._skipped_check("lifecycle_start", reason))
            checks.extend(self._skipped_check(name, reason) for name in after_start_checks)
            checks.append(self._skipped_check("lifecycle_stop", reason))
            checks.append(self._skipped_check("api_port_released", reason))
            checks.append(self._skipped_check("frontend_port_released", reason))
        else:
            start_attempted = True
            start_check, start_result = self._check_command(
                "lifecycle_start",
                self._make_start_command(),
                environment=self._lifecycle_environment(),
            )
            checks.append(start_check)
            try:
                if start_result.returncode == 0:
                    status_check, _ = self._check_command(
                        "lifecycle_status",
                        [
                            self.make_executable,
                            "status",
                            f"PYTHON={self._display_python()}",
                        ],
                        require_running_status=True,
                        environment=self._lifecycle_environment(),
                    )
                    checks.append(status_check)
                    expectations = {
                        "api_health": "healthy_json",
                        "frontend_root": "html",
                        "api_docs": "html",
                        "api_data_source": "available_json",
                        "api_capabilities": "json",
                        "api_command_centre": "json",
                    }
                    for name, url in urls.items():
                        expectation = expectations.get(name, "html")
                        checks.append(self._check_http(name, url, expectation))
                else:
                    reason = "Lifecycle start failed; live HTTP checks were not run."
                    checks.extend(self._skipped_check(name, reason) for name in after_start_checks)
            finally:
                stop_check, _ = self._check_command(
                    "lifecycle_stop",
                    [
                        self.make_executable,
                        "stop",
                        f"PYTHON={self._display_python()}",
                    ],
                    environment=self._lifecycle_environment(),
                )
                checks.append(stop_check)
                api_released = self._wait_for_port_release(self.api_host, self.api_port)
                frontend_released = self._wait_for_port_release(
                    self.frontend_host, self.frontend_port
                )
                checks.extend(
                    [
                        {
                            "check": "api_port_released",
                            "status": "PASS" if api_released else "FAIL",
                            "duration_seconds": 0.0,
                            **(
                                {}
                                if api_released
                                else {"detail": "API port remained open after lifecycle stop."}
                            ),
                        },
                        {
                            "check": "frontend_port_released",
                            "status": "PASS" if frontend_released else "FAIL",
                            "duration_seconds": 0.0,
                            **(
                                {}
                                if frontend_released
                                else {"detail": "Frontend port remained open after lifecycle stop."}
                            ),
                        },
                    ]
                )
        counts = {
            "passed": sum(check["status"] == "PASS" for check in checks),
            "failed": sum(check["status"] == "FAIL" for check in checks),
            "skipped": sum(check["status"] == "SKIPPED" for check in checks),
        }
        valid = bool(start_attempted and counts["failed"] == 0 and counts["skipped"] == 0)
        return {
            "name": "e2e",
            "category": "e2e",
            "status": "PASS" if valid else "FAIL",
            **counts,
            "warnings": 0,
            "duration_seconds": _duration(self.dependencies.monotonic() - started_at),
            "command": self._make_start_command(),
            "exit_code": 0 if valid else 1,
            "evidence": {
                "method": "real make start/status/stop lifecycle plus live HTTP and port checks",
                "no_open": True,
                "runtime_directory": self._portable(self.runtime_directory),
                "checks": checks,
            },
            "limitations": [
                "This is a real two-service HTTP lifecycle smoke; browser hydration, interaction, "
                "and accessibility automation are not claimed."
            ]
            + ([] if valid else ["Real localhost lifecycle E2E did not fully pass."]),
        }

    def run(self, selected: Sequence[str]) -> dict[str, Any]:
        selected_set = set(selected)
        invalid = selected_set.difference(SUITE_CATEGORIES)
        if invalid:
            raise ValueError(f"Unknown release-test suites: {', '.join(sorted(invalid))}")
        started = self.dependencies.monotonic()
        started_at = _utc_now()
        self._invocation_id = hashlib.sha256(
            f"{started_at}|{self.root}|{os.getpid()}".encode()
        ).hexdigest()
        suites = {category: _empty_suite(category) for category in SUITE_CATEGORIES}
        coverage = {
            "status": "UNAVAILABLE",
            "percent": None,
            "source": None,
            "scope": "Backend suite was not selected in this invocation.",
        }
        if "backend" in selected_set:
            suites["backend"], coverage = self._run_backend()
        if "frontend" in selected_set:
            suites["frontend"] = self._run_frontend()
        if "e2e" in selected_set:
            suites["e2e"] = self._run_e2e()
        ordered_suites = [suites[category] for category in SUITE_CATEGORIES]
        all_release_suites_pass = all(item["status"] == "PASS" for item in ordered_suites)
        any_selected_failed = any(suites[category]["status"] != "PASS" for category in selected_set)
        bindings = self._release_bindings()
        status = (
            "PASS"
            if (
                all_release_suites_pass
                and coverage.get("percent") is not None
                and bindings["status"] == "PASS"
            )
            else "FAIL"
            if any_selected_failed
            else "INCOMPLETE"
        )
        totals = {
            key: sum(int(item.get(key) or 0) for item in ordered_suites)
            for key in ("passed", "failed", "skipped", "warnings")
        }
        report = {
            "schema_version": "1.0.0",
            "invocation_id": self._invocation_id,
            "started_at": started_at,
            "generated_at": _utc_now(),
            "status": status,
            "release_gate_passed": status == "PASS",
            "selected_suites": [name for name in SUITE_CATEGORIES if name in selected_set],
            "duration_seconds": _duration(self.dependencies.monotonic() - started),
            "suites": ordered_suites,
            "totals": totals,
            "coverage": coverage,
            "bindings": bindings,
            "source": {
                "runner": "scripts/run_release_tests.py",
                "repository": ".",
            },
            "limitations": (
                []
                if status == "PASS"
                else [
                    "Release test evidence is not complete until backend, frontend, and real "
                    "lifecycle E2E all pass in the same invocation with all current-source "
                    "bindings available."
                ]
            ),
        }
        self._write(report)
        return report

    def _write(self, report: Mapping[str, Any]) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.output_path.with_suffix(self.output_path.suffix + ".tmp")
        temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, self.output_path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite",
        action="append",
        choices=SUITE_CATEGORIES,
        help="Run one suite; repeat for multiple suites. Default: all three.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--profile", default="default")
    parser.add_argument("--api-host", default="127.0.0.1")
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--frontend-host", default="localhost")
    parser.add_argument("--frontend-port", type=int, default=3000)
    parser.add_argument("--http-timeout", type=float, default=10.0)
    parser.add_argument("--port-release-timeout", type=float, default=10.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    selected = tuple(dict.fromkeys(args.suite or SUITE_CATEGORIES))
    runner = ReleaseTestRunner(
        output_path=args.output,
        profile=args.profile,
        api_host=args.api_host,
        api_port=args.api_port,
        frontend_host=args.frontend_host,
        frontend_port=args.frontend_port,
        http_timeout=args.http_timeout,
        port_release_timeout=args.port_release_timeout,
    )
    if args.dry_run:
        print(json.dumps(runner.plan(selected), indent=2))
        return 0
    report = runner.run(selected)
    print(
        json.dumps(
            {
                "status": report["status"],
                "release_gate_passed": report["release_gate_passed"],
                "output": runner._portable(runner.output_path),
            },
            indent=2,
        )
    )
    return 0 if report["release_gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
