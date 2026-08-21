from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import naim_risk.api as api_main
import naim_risk.exports.packages as export_packages
from naim_risk.api import app


@pytest.fixture(autouse=True)
def isolated_security_release_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
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
def test_cors_allows_configured_local_origin_and_rejects_untrusted_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NAIM_AUTH_MODE", "disabled")
    client = TestClient(app)
    allowed = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    untrusted = client.options(
        "/api/v1/health",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert allowed.status_code == 200
    assert allowed.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
    assert untrusted.status_code == 400
    assert "Access-Control-Allow-Origin" not in untrusted.headers


@pytest.mark.integration
def test_download_endpoint_requires_authentication_before_artifact_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NAIM_AUTH_MODE", "demo")
    monkeypatch.setenv(
        "NAIM_TOKEN_SECRET",
        "test-only-release-signing-secret-that-is-long-enough",
    )
    api_main.reset_application_state()

    response = TestClient(app).get(
        "/api/v1/exports/EXPORT-DOES-NOT-EXIST/download",
        params={"download_token": "x" * 32},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.integration
def test_export_staging_directory_is_removed_after_package_generation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    service,
) -> None:
    original_temporary_directory = tempfile.TemporaryDirectory
    created: list[Path] = []

    class TrackedTemporaryDirectory:
        def __init__(self, *args: object, **kwargs: object) -> None:
            kwargs["dir"] = tmp_path
            self._directory = original_temporary_directory(*args, **kwargs)

        def __enter__(self) -> str:
            name = self._directory.__enter__()
            created.append(Path(name))
            return name

        def __exit__(self, *args: object) -> object:
            return self._directory.__exit__(*args)

    monkeypatch.setattr(export_packages.tempfile, "TemporaryDirectory", TrackedTemporaryDirectory)

    artifact = export_packages.generate_powerbi_package(service)

    assert artifact.is_file()
    assert created
    assert all(not directory.exists() for directory in created)
