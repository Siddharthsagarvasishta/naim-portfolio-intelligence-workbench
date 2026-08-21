from __future__ import annotations

import json
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from scripts import run_release_tests as release_tests


def _result(
    command: Sequence[str],
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
    duration: float = 0.1,
) -> release_tests.CommandResult:
    return release_tests.CommandResult(
        command=tuple(command),
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        duration_seconds=duration,
    )


def _json_http(url: str, payload: Mapping[str, object]) -> release_tests.HttpResult:
    return release_tests.HttpResult(
        url=url,
        status_code=200,
        headers={"content-type": "application/json"},
        body=json.dumps(payload),
        duration_seconds=0.01,
    )


def _write_required_bindings(root: Path) -> None:
    files = {
        "package-lock.json": "{}\n",
        "config/feature_status.yaml": "{}\n",
        "exports/validation/interop_evidence_snapshot.json": json.dumps(
            {"metadata": {"run_id": "fixture-run"}}
        ),
        "data/manifests/fixture-run/run_manifest.json": "{}\n",
        "outputs/contracts/openapi.json": "{}\n",
        "outputs/contracts/openapi_validation.json": "{}\n",
        "outputs/validation/cross_artifact_reconciliation.json": "{}\n",
    }
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def test_full_injected_run_persists_exact_release_suites_and_same_run_coverage(
    tmp_path: Path,
) -> None:
    _write_required_bindings(tmp_path)
    running = {"value": False}
    commands: list[tuple[str, ...]] = []

    def run_command(
        command: Sequence[str], _cwd: Path, _environment: Mapping[str, str] | None
    ) -> release_tests.CommandResult:
        commands.append(tuple(command))
        if "pytest" in command:
            junit_path = Path(command[command.index("--junitxml") + 1])
            coverage_argument = next(
                item for item in command if item.startswith("--cov-report=json:")
            )
            coverage_path = Path(coverage_argument.split(":", 1)[1])
            junit_path.write_text(
                '<testsuites tests="4" failures="0" errors="0" skipped="1" time="1.2"/>',
                encoding="utf-8",
            )
            coverage_path.write_text(
                json.dumps({"totals": {"percent_covered": 91.25}}), encoding="utf-8"
            )
            return _result(command, stdout="3 passed, 1 skipped, 2 warnings", duration=2.0)
        if tuple(command[:2]) == ("npm", "test"):
            return _result(
                command,
                stdout=("TAP version 13\n1..3\n# tests 3\n# pass 3\n# fail 0\n# skipped 0\n"),
                duration=3.0,
            )
        if tuple(command[:2]) == ("make", "start"):
            running["value"] = True
            return _result(command, stdout='{"status":"RUNNING"}')
        if tuple(command[:2]) == ("make", "status"):
            return _result(
                command,
                stdout=(
                    "PYTHONPATH=src python scripts/local_lifecycle.py status\n"
                    '{"status":"RUNNING","services":{'
                    '"api":{"running":true,"health":{"ok":true}},'
                    '"frontend":{"running":true,"health":{"ok":true}}}}'
                ),
            )
        if tuple(command[:2]) == ("make", "stop"):
            running["value"] = False
            return _result(command, stdout='{"status":"STOPPED"}')
        raise AssertionError(f"unexpected command: {command}")

    def http_get(url: str, _timeout: float) -> release_tests.HttpResult:
        if url.endswith("/api/v1/health"):
            return _json_http(
                url,
                {
                    "status": "healthy",
                    "publication_allowed": True,
                    "quality_status": "PASS",
                },
            )
        if url.endswith("/api/v1/data-source"):
            return _json_http(url, {"available": True})
        if "/api/v1/" in url:
            return _json_http(url, {"status": "ok"})
        return release_tests.HttpResult(
            url=url,
            status_code=200,
            headers={"content-type": "text/html; charset=utf-8"},
            body="<html><title>nAIM</title></html>",
            duration_seconds=0.01,
        )

    dependencies = release_tests.RuntimeDependencies(
        run_command=run_command,
        http_get=http_get,
        port_is_open=lambda _host, _port: running["value"],
        monotonic=time.monotonic,
        sleep=lambda _seconds: None,
    )
    output = tmp_path / "outputs" / "validation" / "test_results.json"
    runner = release_tests.ReleaseTestRunner(
        root=tmp_path,
        output_path=output,
        dependencies=dependencies,
        python_executable="python-test",
        port_release_timeout=0.01,
    )

    report = runner.run(release_tests.SUITE_CATEGORIES)

    assert report["status"] == "PASS"
    assert report["release_gate_passed"] is True
    assert [suite["name"] for suite in report["suites"]] == ["backend", "frontend", "e2e"]
    assert [suite["category"] for suite in report["suites"]] == [
        "backend",
        "frontend",
        "e2e",
    ]
    assert report["suites"][0]["passed"] == 3
    assert report["suites"][0]["warnings"] == 2
    assert report["suites"][1]["passed"] == 3
    assert report["coverage"]["status"] == "AVAILABLE"
    assert report["coverage"]["percent"] == 91.25
    assert report["coverage"]["source"] == "outputs/validation/backend_coverage.json"
    assert report["coverage"]["artifact"]["sha256"]
    assert report["coverage"]["artifact"]["invocation_id"] == report["invocation_id"]
    assert report["bindings"]["status"] == "PASS"
    assert report["bindings"]["source_tree"]["sha256"]
    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert any(command[:2] == ("make", "start") and "NO_OPEN=1" in command for command in commands)
    assert any(command[:2] == ("make", "stop") for command in commands)
    assert "browser hydration" in report["suites"][2]["limitations"][0]


def test_e2e_http_failure_always_stops_and_verifies_ports_free(tmp_path: Path) -> None:
    running = {"value": False}
    commands: list[tuple[str, ...]] = []

    def run_command(
        command: Sequence[str], _cwd: Path, _environment: Mapping[str, str] | None
    ) -> release_tests.CommandResult:
        commands.append(tuple(command))
        if tuple(command[:2]) == ("make", "start"):
            running["value"] = True
            return _result(command)
        if tuple(command[:2]) == ("make", "status"):
            return _result(
                command,
                stdout=(
                    '{"status":"RUNNING","services":{'
                    '"api":{"running":true,"health":{"ok":true}},'
                    '"frontend":{"running":true,"health":{"ok":true}}}}'
                ),
            )
        if tuple(command[:2]) == ("make", "stop"):
            running["value"] = False
            return _result(command)
        raise AssertionError(f"unexpected command: {command}")

    def http_get(url: str, _timeout: float) -> release_tests.HttpResult:
        if url.endswith("/strategy"):
            return release_tests.HttpResult(
                url=url,
                status_code=500,
                headers={"content-type": "text/html"},
                body="failed",
                duration_seconds=0.01,
                error="HTTPError: 500",
            )
        if url.endswith("/api/v1/health"):
            return _json_http(
                url,
                {
                    "status": "healthy",
                    "publication_allowed": True,
                    "quality_status": "PASS",
                },
            )
        if url.endswith("/api/v1/data-source"):
            return _json_http(url, {"available": True})
        if "/api/v1/" in url:
            return _json_http(url, {"status": "ok"})
        return release_tests.HttpResult(
            url=url,
            status_code=200,
            headers={"content-type": "text/html"},
            body="<html></html>",
            duration_seconds=0.01,
        )

    runner = release_tests.ReleaseTestRunner(
        root=tmp_path,
        output_path=tmp_path / "test_results.json",
        dependencies=release_tests.RuntimeDependencies(
            run_command=run_command,
            http_get=http_get,
            port_is_open=lambda _host, _port: running["value"],
            monotonic=time.monotonic,
            sleep=lambda _seconds: None,
        ),
        python_executable="python-test",
        port_release_timeout=0.01,
    )

    report = runner.run(["e2e"])

    e2e = report["suites"][2]
    checks = {check["check"]: check for check in e2e["evidence"]["checks"]}
    assert report["status"] == "FAIL"
    assert e2e["status"] == "FAIL"
    assert checks["frontend_route_strategy"]["status"] == "FAIL"
    assert checks["lifecycle_stop"]["status"] == "PASS"
    assert checks["api_port_released"]["status"] == "PASS"
    assert checks["frontend_port_released"]["status"] == "PASS"
    assert commands[-1][:2] == ("make", "stop")


def test_e2e_refuses_occupied_ports_without_stopping_unowned_service(tmp_path: Path) -> None:
    commands: list[tuple[str, ...]] = []

    def run_command(
        command: Sequence[str], _cwd: Path, _environment: Mapping[str, str] | None
    ) -> release_tests.CommandResult:
        commands.append(tuple(command))
        return _result(command)

    runner = release_tests.ReleaseTestRunner(
        root=tmp_path,
        output_path=tmp_path / "test_results.json",
        dependencies=release_tests.RuntimeDependencies(
            run_command=run_command,
            http_get=lambda _url, _timeout: (_ for _ in ()).throw(
                AssertionError("HTTP must not run")
            ),
            port_is_open=lambda _host, _port: True,
            monotonic=time.monotonic,
            sleep=lambda _seconds: None,
        ),
    )

    report = runner.run(["e2e"])

    checks = {check["check"]: check for check in report["suites"][2]["evidence"]["checks"]}
    assert report["status"] == "FAIL"
    assert checks["preflight_api_port_free"]["status"] == "FAIL"
    assert checks["lifecycle_start"]["status"] == "SKIPPED"
    assert checks["lifecycle_stop"]["status"] == "SKIPPED"
    assert commands == []


def test_backend_failure_never_reuses_stale_junit_or_coverage(tmp_path: Path) -> None:
    validation = tmp_path / "outputs" / "validation"
    validation.mkdir(parents=True)
    (validation / "backend_junit.xml").write_text(
        '<testsuites tests="999" failures="0" errors="0" skipped="0"/>', encoding="utf-8"
    )
    (validation / "backend_coverage.json").write_text(
        json.dumps({"totals": {"percent_covered": 100.0}}), encoding="utf-8"
    )

    runner = release_tests.ReleaseTestRunner(
        root=tmp_path,
        output_path=validation / "test_results.json",
        dependencies=release_tests.RuntimeDependencies(
            run_command=lambda command, _cwd, _environment: _result(
                command, returncode=2, stderr="collection failed"
            ),
            http_get=lambda _url, _timeout: (_ for _ in ()).throw(
                AssertionError("HTTP must not run")
            ),
            port_is_open=lambda _host, _port: False,
            monotonic=time.monotonic,
            sleep=lambda _seconds: None,
        ),
    )

    report = runner.run(["backend"])

    backend = report["suites"][0]
    assert report["status"] == "FAIL"
    assert backend["status"] == "FAIL"
    assert backend["passed"] is None
    assert backend["evidence"]["junit"] is None
    assert backend["evidence"]["coverage"] is None
    assert report["coverage"]["percent"] is None
    assert backend["error"] == "collection failed"


def test_dry_run_prints_plan_without_execution_or_evidence_write(tmp_path: Path, capsys) -> None:
    output = tmp_path / "test_results.json"

    assert (
        release_tests.main(
            ["--dry-run", "--suite", "backend", "--suite", "e2e", "--output", str(output)]
        )
        == 0
    )

    plan = json.loads(capsys.readouterr().out)
    assert plan["dry_run"] is True
    assert plan["selected_suites"] == ["backend", "e2e"]
    assert (
        "--cov-report=json:outputs/validation/backend_coverage.json" in plan["commands"]["backend"]
    )
    assert "NO_OPEN=1" in plan["commands"]["e2e_start"]
    assert not output.exists()


def test_current_file_bindings_fail_closed_when_required_evidence_is_missing(
    tmp_path: Path,
) -> None:
    runner = release_tests.ReleaseTestRunner(
        root=tmp_path,
        output_path=tmp_path / "outputs/validation/test_results.json",
        dependencies=release_tests.RuntimeDependencies(
            run_command=lambda command, _cwd, _environment: _result(
                command, returncode=1, stderr="not run"
            ),
            http_get=lambda _url, _timeout: (_ for _ in ()).throw(
                AssertionError("HTTP must not run")
            ),
            port_is_open=lambda _host, _port: False,
            monotonic=time.monotonic,
            sleep=lambda _seconds: None,
        ),
    )

    report = runner.run(["backend"])

    assert report["release_gate_passed"] is False
    assert report["bindings"]["status"] == "INCOMPLETE"
    assert all(
        report["bindings"][name]["status"] == "MISSING"
        for name in release_tests.REQUIRED_FILE_BINDINGS
    )
