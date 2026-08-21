from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import naim_risk.api as api_main
from naim_risk.api import app, get_service
from naim_risk.auth import Role

SECRET = "test-only-api-signing-secret-that-is-long-enough"


@pytest.fixture(autouse=True)
def isolated_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
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
def test_every_versioned_json_response_exposes_strict_mode_and_security_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NAIM_AUTH_MODE", "disabled")
    client = TestClient(app)
    for path in ("/api/v1/health", "/api/v1/data-source", "/api/v1/capabilities"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.json()["data_mode"] == "DEMO"
        assert response.json()["source_context"]["active_mode"] == "DEMO"
        assert response.headers["X-nAIM-Data-Mode"] == "DEMO"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
    assert api_main._service is None


@pytest.mark.integration
def test_disabled_auth_mode_is_visibly_limited_to_local_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NAIM_AUTH_MODE", "disabled")
    with pytest.warns(RuntimeWarning, match="private local development"):
        response = TestClient(app).get("/api/v1/auth/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "disabled"
    assert payload["authentication_required"] is False
    assert "private local" in payload["local_development_warning"]


@pytest.mark.integration
def test_demo_login_endpoint_roles_and_logout_are_enforced(
    monkeypatch: pytest.MonkeyPatch,
    service,
) -> None:
    monkeypatch.setenv("NAIM_AUTH_MODE", "demo")
    monkeypatch.setenv("NAIM_TOKEN_SECRET", SECRET)
    auth = api_main.get_auth_service()
    auth.setup_demo_account("executive", "secure executive phrase", Role.EXECUTIVE_VIEWER)
    auth.setup_demo_account(
        "portfolio.analyst",
        "secure portfolio phrase",
        Role.PORTFOLIO_ANALYST,
    )
    app.dependency_overrides[get_service] = lambda: service
    client = TestClient(app)

    missing = client.post(
        "/api/v1/investigations",
        json={"business_question": "Why did validated loss move?"},
    )
    assert missing.status_code == 401

    viewer_login = client.post(
        "/api/v1/auth/login",
        json={"username": "executive", "password": "secure executive phrase"},
    )
    assert viewer_login.status_code == 200
    viewer_token = viewer_login.json()["access_token"]
    forbidden = client.post(
        "/api/v1/investigations",
        headers={"Authorization": f"Bearer {viewer_token}"},
        json={"business_question": "Why did validated loss move?"},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "PERMISSION_DENIED"

    analyst_login = client.post(
        "/api/v1/auth/login",
        json={
            "username": "portfolio.analyst",
            "password": "secure portfolio phrase",
        },
    )
    analyst_token = analyst_login.json()["access_token"]
    headers = {"Authorization": f"Bearer {analyst_token}"}
    created = client.post(
        "/api/v1/investigations",
        headers=headers,
        json={"business_question": "Why did validated loss move?"},
    )
    assert created.status_code == 201
    created_record = service.workflow_store.get("investigation", created.json()["investigation_id"])
    assert created_record["created_by"] == "portfolio.analyst"

    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["role"] == "Portfolio Analyst"
    logged_out = client.post("/api/v1/auth/logout", headers=headers)
    assert logged_out.status_code == 200
    assert logged_out.json()["logged_out"] is True
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
