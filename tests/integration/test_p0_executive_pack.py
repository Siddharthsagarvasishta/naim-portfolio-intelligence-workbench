from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import naim_risk.api as api_main
from naim_risk.api import (
    app,
    get_executive_pack_output_root,
    get_service,
    get_source_context,
    get_workflow_store,
)
from naim_risk.runtime_modes import DataMode, source_context
from naim_risk.service import WorkbenchService
from naim_risk.workflow import WorkflowStore


@pytest.mark.integration
def test_governed_executive_pack_api_reuses_validated_file_and_manifest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    test_config,
    pipeline_data,
) -> None:
    output_root = tmp_path / "generated_exports"
    store = WorkflowStore(
        f"sqlite+pysqlite:///{(tmp_path / 'executive-pack.sqlite3').resolve()}"
    )
    service = WorkbenchService(test_config, pipeline_data, workflow_store=store)
    context = source_context(test_config, DataMode.DEMO)
    monkeypatch.setenv("NAIM_AUTH_MODE", "disabled")
    monkeypatch.setenv("NAIM_DATA_MODE", "DEMO")
    monkeypatch.setenv("NAIM_DATASET_PROFILE", "test")
    monkeypatch.setenv("NAIM_DATA_DIR", str(test_config.data_root))
    api_main.reset_application_state()
    app.dependency_overrides[get_service] = lambda: service
    app.dependency_overrides[get_workflow_store] = lambda: store
    app.dependency_overrides[get_source_context] = lambda: context
    app.dependency_overrides[get_executive_pack_output_root] = lambda: output_root
    try:
        client = TestClient(app)
        request = {
            "reporting_period": service.metadata()["as_of"],
            "comparison_period": "2024-07-01",
            "filter_scope": {},
            "include_pdf": False,
        }
        created_response = client.post("/api/v1/executive-packs/generate", json=request)
        assert created_response.status_code == 201
        created = created_response.json()
        assert created["status"] == "completed"
        assert created["stage"] == "completed"
        assert created["last_completed_stage"] == "registering_manifest"
        assert created["format"] == "pptx"
        assert created["data_mode"] == context.active_mode.value
        assert created["validation_status"] == "PASS"
        assert created["reconciliation_status"] == "PASS"
        assert created["filename"] == "nAIM_Executive_Portfolio_Review_2024_08.pptx"
        assert created["download_url"].startswith(
            f"/api/v1/executive-packs/{created['job_id']}/download?download_token="
        )
        assert created["manifest_url"].startswith(
            f"/api/v1/executive-packs/{created['job_id']}/manifest?download_token="
        )

        status_response = client.get(f"/api/v1/executive-packs/{created['job_id']}")
        assert status_response.status_code == 200
        status = status_response.json()
        assert status["stage"] == "completed"
        assert status["validation_status"] == "PASS"
        assert status["reconciliation_status"] == "PASS"

        download = client.get(created["download_url"])
        assert download.status_code == 200
        assert download.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        )
        downloaded_path = tmp_path / "downloaded-executive-pack.pptx"
        downloaded_path.write_bytes(download.content)
        with zipfile.ZipFile(downloaded_path) as archive:
            slides = [
                name
                for name in archive.namelist()
                if name.startswith("ppt/slides/slide") and name.endswith(".xml")
            ]
        assert len(slides) == 14

        manifest_response = client.get(created["manifest_url"])
        assert manifest_response.status_code == 200
        manifest = manifest_response.json()
        assert manifest["job_id"] == created["job_id"]
        assert manifest["artifact"]["sha256"] == created["file_sha256"]
        assert manifest["scope"] == created["scope"]
        assert manifest["evidence_id"] == created["evidence_id"]
        assert manifest["metric_version"] == created["metric_registry_version"]
        assert manifest["synthetic"] is True
        assert manifest["synthetic_data"] is True
        assert manifest["validation_status"] == "PASS"
        assert manifest["reconciliation_status"] == "PASS"
        assert manifest["validation"]["status"] == "PASS"
        assert manifest["reconciliation"]["status"] == "PASS"
        assert not Path(manifest["render_evidence"]["qa_root"]).is_absolute()
        assert manifest["render_evidence"]["qa_root"].startswith("work/p0-")

        reused_response = client.post("/api/v1/executive-packs/generate", json=request)
        assert reused_response.status_code == 201
        reused = reused_response.json()
        assert reused["job_id"] == created["job_id"]
        assert reused["reused"] is True
        assert reused["file_sha256"] == created["file_sha256"]
        assert client.get(f"/api/v1/executive-packs/{created['job_id']}").json()[
            "download_count"
        ] == 1

        manifest_path = output_root / created["manifest_filename"]
        persisted_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert persisted_manifest == manifest
    finally:
        app.dependency_overrides.clear()
        api_main.reset_application_state()
        store.close()
