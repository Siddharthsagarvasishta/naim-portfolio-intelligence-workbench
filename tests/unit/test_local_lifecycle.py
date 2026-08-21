from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import local_lifecycle as lifecycle


class _HealthResponse:
    def __init__(self, *, content_type: str, body: bytes, status: int = 200) -> None:
        self.headers = {"Content-Type": content_type}
        self.body = body
        self.status = status
        self.read_calls = 0

    def __enter__(self) -> _HealthResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, limit: int) -> bytes:
        self.read_calls += 1
        return self.body[:limit]


def test_frontend_health_accepts_large_html_without_reading_the_page_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _HealthResponse(content_type="text/html; charset=utf-8", body=b"x" * 50_000)
    monkeypatch.setattr(lifecycle.urllib.request, "urlopen", lambda *_args, **_kwargs: response)

    result = lifecycle._fetch_health("http://localhost:3000/")

    assert result == {"ok": True, "status_code": 200, "body": None}
    assert response.read_calls == 0


def test_json_health_still_fails_closed_when_response_exceeds_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _HealthResponse(content_type="application/json", body=b"x" * 9_000)
    monkeypatch.setattr(lifecycle.urllib.request, "urlopen", lambda *_args, **_kwargs: response)

    result = lifecycle._fetch_health("http://127.0.0.1:8000/api/v1/health")

    assert result["ok"] is False
    assert result["status_code"] == 200
    assert "8192-byte" in result["error"]
    assert response.read_calls == 1


def test_restart_parser_has_complete_start_configuration() -> None:
    parsed = lifecycle._parser().parse_args(["restart", "--no-open", "--profile", "small"])

    assert parsed.action == "restart"
    assert parsed.profile == "small"
    assert parsed.api_port == 8000
    assert parsed.frontend_port == 3000
    assert parsed.timeout == 300
    assert parsed.no_open is True


def test_local_vite_config_disables_unneeded_worker_inspector() -> None:
    config = (lifecycle.ROOT / "vite.config.ts").read_text(encoding="utf-8")

    assert "inspectorPort: false" in config


def test_local_vite_config_ignores_generated_runtime_trees() -> None:
    config = (lifecycle.ROOT / "vite.config.ts").read_text(encoding="utf-8")

    for path in (".venv", ".wrangler", "data", "outputs", "work"):
        assert f'"**/{path}/**"' in config


def test_core_api_startup_defers_optional_feature_stacks() -> None:
    optional_modules = [
        "naim_risk.advanced",
        "naim_risk.market_risk",
        "naim_risk.onboarding",
        "naim_risk.optimisation",
        "naim_risk.presentations",
        "naim_risk.tableau",
    ]
    probe = (
        "import json, sys; import naim_risk.api; "
        f"print(json.dumps({{name: name in sys.modules for name in {optional_modules!r}}}))"
    )

    completed = lifecycle.subprocess.run(
        [lifecycle.sys.executable, "-c", probe],
        cwd=lifecycle.ROOT,
        env={**lifecycle.os.environ, "PYTHONPATH": "src"},
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert json.loads(completed.stdout) == dict.fromkeys(optional_modules, False)


def test_status_reports_pids_ports_health_profile_database_and_last_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("NAIM_RUNTIME_DIR", str(tmp_path / "runtime"))
    state = lifecycle._empty_state()
    state.update(
        {
            "profile": "default",
            "last_successful_pipeline": {"run_id": "default-test"},
            "last_error": "previous controlled failure",
            "services": {
                "api": {"pid": 1001, "host": "127.0.0.1", "port": 8000},
                "frontend": {"pid": 1002, "host": "127.0.0.1", "port": 3000},
            },
        }
    )
    lifecycle._write_state(state)
    monkeypatch.setattr(lifecycle, "_owned_process", lambda _record: False)
    monkeypatch.setattr(lifecycle, "_port_is_open", lambda _host, _port: False)
    monkeypatch.setattr(
        lifecycle,
        "inspect_database",
        lambda _url: {"database_path": "/safe/workflow.sqlite3", "status": "CURRENT"},
    )

    assert lifecycle.status_services() == 0

    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "STOPPED_OR_DEGRADED"
    assert report["services"]["api"]["pid"] is None
    assert report["services"]["frontend"]["port"] == 3000
    assert report["dataset_profile"] == "default"
    assert report["database_status"] == "CURRENT"
    assert report["last_successful_pipeline"]["run_id"] == "default-test"
    assert report["last_error"] == "previous controlled failure"


def test_stop_refuses_stale_or_unowned_pid_without_sending_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lifecycle, "_owned_process", lambda _record: False)
    monkeypatch.setattr(
        lifecycle.os,
        "killpg",
        lambda *_args: pytest.fail("killpg must not run for an unowned PID"),
    )

    result = lifecycle._stop_record({"pid": 4567, "ownership_token": "npm run dev"})

    assert result["stopped"] is True
    assert result["previous_pid"] == 4567
    assert "stale PID" in result["detail"]


def test_stop_targets_only_the_recorded_owned_process_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands = iter(["npm run dev -- --host 127.0.0.1", None, None, None])
    signals: list[tuple[int, int]] = []
    monkeypatch.setattr(lifecycle, "_process_command", lambda _pid: next(commands))
    monkeypatch.setattr(lifecycle.os, "getpgid", lambda pid: pid)
    monkeypatch.setattr(lifecycle.os, "killpg", lambda group, sig: signals.append((group, sig)))

    result = lifecycle._stop_record(
        {
            "pid": 7654,
            "process_group": 7654,
            "ownership_token": "npm run dev",
        }
    )

    assert result["stopped"] is True
    assert signals == [(7654, lifecycle.signal.SIGTERM)]


def test_start_refuses_unrecorded_port_before_mutating_database_or_spawning(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("NAIM_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setattr(
        lifecycle,
        "_verify_runtime",
        lambda: {"python": "3.12.0", "node": "v22.13.0", "npm": "/usr/bin/npm"},
    )
    monkeypatch.setattr(lifecycle, "_port_is_open", lambda _host, port: port == 8000)
    monkeypatch.setattr(
        lifecycle,
        "_ensure_database",
        lambda: pytest.fail("database must not be touched when a port is occupied"),
    )
    args = lifecycle._parser().parse_args(["start", "--no-open"])

    with pytest.raises(lifecycle.LifecycleError, match="unrecorded process"):
        lifecycle.start_services(args)


def test_open_uses_only_the_recorded_healthy_frontend(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("NAIM_RUNTIME_DIR", str(tmp_path / "runtime"))
    state = lifecycle._empty_state()
    state["services"] = {
        "frontend": {
            "pid": 3001,
            "url": "http://localhost:3000",
            "health_url": "http://localhost:3000/",
        }
    }
    lifecycle._write_state(state)
    opened: list[str] = []
    monkeypatch.setattr(lifecycle, "_owned_process", lambda _record: True)
    monkeypatch.setattr(lifecycle, "_fetch_health", lambda _url: {"ok": True})
    monkeypatch.setattr(lifecycle.webbrowser, "open", lambda url: opened.append(url) or True)

    assert lifecycle.open_frontend() == 0

    assert opened == ["http://localhost:3000"]
    assert json.loads(capsys.readouterr().out)["status"] == "OPENED"


def test_latest_pipeline_resolves_manifest_from_run_id_not_stale_absolute_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "relocated-repository"
    manifest_root = root / "data" / "manifests"
    run_id = "default-1234-abcd"
    (manifest_root / run_id).mkdir(parents=True)
    (manifest_root / "latest.json").write_text(
        json.dumps({"run_id": run_id, "manifest": "/old/machine/run_manifest.json"}),
        encoding="utf-8",
    )
    (manifest_root / run_id / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "profile": "default",
                "validation_status": "PASS",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(lifecycle, "ROOT", root)

    report = lifecycle._latest_pipeline("default")

    assert report is not None
    assert report["run_id"] == run_id
    assert report["validation_status"] == "PASS"
    assert report["manifest"].startswith(str(root))


def test_api_warmup_requires_governed_analytical_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = {
        "active_mode": "OFFLINE_SNAPSHOT",
        "run_id": "default-test",
        "configuration_hash": "c" * 64,
        "dataset_hash": "d" * 64,
    }
    payload = {
        "metadata": {
            "run_id": "default-test",
            "configuration_hash": "c" * 64,
            "quality_status": "PASS",
            "publication_allowed": True,
        },
        "kpis": [
            {
                "metric_id": "loss_rate",
                "value": 0.01,
                "runtime_evidence": {
                    "run_id": "default-test",
                    "configuration_hash": "c" * 64,
                    "dataset_hash": "d" * 64,
                    "binding_sha256": "b" * 64,
                },
            }
        ],
    }

    def readiness_response(url: str, **_kwargs: object) -> dict[str, object]:
        body = {"mode": "OFFLINE_SNAPSHOT", "context": context} if url.endswith(
            "/data-source"
        ) else payload
        return {"ok": True, "status_code": 200, "body": body}

    monkeypatch.setattr(
        lifecycle,
        "_fetch_health",
        readiness_response,
    )
    record = {"url": "http://127.0.0.1:8000"}

    readiness = lifecycle._warm_api_readiness(record, 120)

    assert readiness["ok"] is True
    assert readiness["data_mode"] == "OFFLINE_SNAPSHOT"
    assert readiness["run_id"] == "default-test"
    assert readiness["kpi_count"] == 1
    assert record["analytical_readiness"] == readiness


@pytest.mark.parametrize(
    ("payload", "source_payload"),
    [
        (
            {
                "metadata": {
                    "run_id": None,
                    "configuration_hash": None,
                    "quality_status": "UNAVAILABLE",
                    "publication_allowed": False,
                },
                "kpis": [],
            },
            {
                "mode": "UNAVAILABLE",
                "context": {
                    "active_mode": "UNAVAILABLE",
                    "run_id": None,
                    "configuration_hash": None,
                    "dataset_hash": None,
                },
            },
        ),
        (
            {
                "metadata": {
                    "run_id": "default-test",
                    "configuration_hash": "c" * 64,
                    "quality_status": "PASS",
                    "publication_allowed": True,
                },
                "kpis": [
                    {
                        "runtime_evidence": {
                            "run_id": "different-run",
                            "configuration_hash": "c" * 64,
                            "dataset_hash": "d" * 64,
                            "binding_sha256": "b" * 64,
                        }
                    }
                ],
            },
            {
                "mode": "OFFLINE_SNAPSHOT",
                "context": {
                    "active_mode": "OFFLINE_SNAPSHOT",
                    "run_id": "default-test",
                    "configuration_hash": "c" * 64,
                    "dataset_hash": "d" * 64,
                },
            },
        ),
    ],
)
def test_api_warmup_fails_closed_without_ready_results(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, object],
    source_payload: dict[str, object],
) -> None:
    def readiness_response(url: str, **_kwargs: object) -> dict[str, object]:
        body = source_payload if url.endswith("/data-source") else payload
        return {"ok": True, "status_code": 200, "body": body}

    monkeypatch.setattr(
        lifecycle,
        "_fetch_health",
        readiness_response,
    )

    with pytest.raises(lifecycle.LifecycleError, match="readiness response"):
        lifecycle._warm_api_readiness({"url": "http://127.0.0.1:8000"}, 120)
