from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import naim_risk.api as api_main
from naim_risk.api import app


@pytest.fixture(autouse=True)
def isolated_security_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("NAIM_AUTH_MODE", "disabled")
    monkeypatch.setenv("NAIM_DATA_MODE", "DEMO")
    monkeypatch.setenv("NAIM_DATASET_PROFILE", "test")
    monkeypatch.setenv("NAIM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv(
        "NAIM_DATABASE_URL",
        f"sqlite+pysqlite:///{(tmp_path / 'workflow.sqlite3').resolve()}",
    )
    api_main.reset_application_state()
    yield
    app.dependency_overrides.clear()
    api_main.reset_application_state()


@pytest.mark.integration
def test_request_body_limit_and_rate_limit_are_enforced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NAIM_MAX_REQUEST_BYTES", "1024")
    oversized = TestClient(app).post(
        "/api/v1/auth/login",
        content=b"x" * 1025,
        headers={"Content-Type": "application/json"},
    )
    assert oversized.status_code == 413
    assert oversized.json()["error"]["code"] == "REQUEST_TOO_LARGE"
    assert oversized.headers["X-Content-Type-Options"] == "nosniff"

    monkeypatch.setenv("NAIM_RATE_LIMIT_REQUESTS", "2")
    monkeypatch.setenv("NAIM_RATE_LIMIT_WINDOW_SECONDS", "60")
    api_main.reset_application_state()
    client = TestClient(app)
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/health").status_code == 200
    denied = client.get("/api/v1/health")
    assert denied.status_code == 429
    assert denied.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"
    assert denied.headers["Retry-After"]
    assert denied.headers["X-RateLimit-Remaining"] == "0"


@pytest.mark.integration
def test_artifact_download_requires_an_expiring_scoped_token() -> None:
    client = TestClient(app)

    missing = client.get("/api/v1/exports/not-an-artifact/download")
    assert missing.status_code == 422
    invalid = client.get(
        "/api/v1/exports/not-an-artifact/download",
        params={"download_token": "x" * 32},
    )
    assert invalid.status_code == 403
    assert "token" in invalid.json()["detail"].lower()


@pytest.mark.integration
def test_interactive_api_docs_receive_a_usable_restricted_csp() -> None:
    response = TestClient(app).get("/api/docs")

    assert response.status_code == 200
    csp = response.headers["Content-Security-Policy"]
    assert "https://cdn.jsdelivr.net" in csp
    assert "frame-ancestors 'none'" in csp
