from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import naim_risk.api as api_main
from naim_risk.api import app


@pytest.mark.integration
def test_onboarding_api_upload_validate_load_approve_and_restart(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    monkeypatch.setenv("NAIM_AUTH_MODE", "disabled")
    monkeypatch.setenv("NAIM_DATA_MODE", "DEMO")
    monkeypatch.setenv("NAIM_DATASET_PROFILE", "test")
    monkeypatch.setenv("NAIM_DATA_DIR", str(data_root))
    monkeypatch.setenv(
        "NAIM_DATABASE_URL",
        f"sqlite+pysqlite:///{(tmp_path / 'workflow.sqlite3').resolve()}",
    )
    api_main.reset_application_state()
    client = TestClient(app)
    csv_bytes = b"acct_id,region_raw,limit\nA-1, NORTH ,1000\nA-2,South,500\n"
    try:
        upload = client.post(
            "/api/v1/data-onboarding/sources/upload",
            json={
                "filename": "accounts.csv",
                "content_base64": base64.b64encode(csv_bytes).decode(),
            },
        )
        assert upload.status_code == 201
        source = {
            key: value
            for key, value in upload.json().items()
            if key not in {"data_mode", "source_context"}
        }
        assert source["relative_path"].startswith("sources/")
        assert str(tmp_path) not in json.dumps(source)

        preview = client.post(
            "/api/v1/data-onboarding/preview",
            json={"source": source, "sample_rows": 10},
        )
        assert preview.status_code == 200
        assert preview.json()["sample_row_count"] == 2
        assert preview.json()["data_mode"] == "DEMO"

        mapping = {
            "source": source,
            "contract_id": "account_master",
            "mapping": {"account_id": "acct_id", "credit_limit": "limit"},
            "transformations": {"region": "normalize(region_raw)"},
            "max_error_rate": 0,
        }
        mapped = client.post(
            "/api/v1/data-onboarding/map",
            json={key: value for key, value in mapping.items() if key != "max_error_rate"},
        )
        assert mapped.status_code == 200
        assert mapped.json()["valid"] is True
        validated = client.post("/api/v1/data-onboarding/validate", json=mapping)
        assert validated.status_code == 200
        assert validated.json()["validation"]["passed"] is True

        profile = client.post(
            "/api/v1/data-onboarding/profiles",
            json={**mapping, "profile_id": "account-master-v1"},
        )
        assert profile.status_code == 201
        assert profile.json()["version"] == 1
        assert profile.json()["active"] is False
        loaded = client.post(
            "/api/v1/data-onboarding/load",
            json={
                "profile_id": "account-master-v1",
                "source": source,
                "expected_version": 1,
            },
        )
        assert loaded.status_code == 200
        assert loaded.json()["loaded_to_active_analytics"] is False
        assert loaded.json()["reconciliation"]["balanced"] is True
        assert all(not value.startswith("/") for value in loaded.json()["outputs"].values())

        approved = client.post(
            "/api/v1/data-onboarding/profiles/account-master-v1/approve",
            json={
                "expected_version": 2,
                "rationale": "Validation passed and source totals reconcile.",
            },
        )
        assert approved.status_code == 200
        assert approved.json()["approval_state"] == "APPROVED"
        assert approved.json()["active"] is True

        api_main.reset_application_state()
        restarted = TestClient(app).get("/api/v1/data-onboarding/profiles/account-master-v1")
        assert restarted.status_code == 200
        assert restarted.json()["active"] is True
    finally:
        api_main.reset_application_state()


@pytest.mark.integration
def test_onboarding_api_rejects_formula_injection_and_path_traversal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("NAIM_AUTH_MODE", "disabled")
    monkeypatch.setenv("NAIM_DATA_MODE", "DEMO")
    monkeypatch.setenv("NAIM_DATASET_PROFILE", "test")
    monkeypatch.setenv("NAIM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv(
        "NAIM_DATABASE_URL",
        f"sqlite+pysqlite:///{(tmp_path / 'workflow.sqlite3').resolve()}",
    )
    api_main.reset_application_state()
    try:
        client = TestClient(app)
        traversal = client.post(
            "/api/v1/data-onboarding/sources/select",
            json={"relative_path": "../../.env"},
        )
        assert traversal.status_code == 422
        assert traversal.json()["error"]["code"] == "UNSAFE_ONBOARDING_REQUEST"

        upload = client.post(
            "/api/v1/data-onboarding/sources/upload",
            json={
                "filename": "accounts.csv",
                "content_base64": base64.b64encode(b"account_id\nA-1\n").decode(),
            },
        ).json()
        source = {
            key: value
            for key, value in upload.items()
            if key not in {"data_mode", "source_context"}
        }
        injection = client.post(
            "/api/v1/data-onboarding/map",
            json={
                "source": source,
                "contract_id": "account_master",
                "mapping": {"account_id": "account_id"},
                "transformations": {"region": "__import__('os').system('id')"},
            },
        )
        assert injection.status_code == 422
        assert injection.json()["error"]["code"] == "UNSAFE_ONBOARDING_REQUEST"
    finally:
        api_main.reset_application_state()
