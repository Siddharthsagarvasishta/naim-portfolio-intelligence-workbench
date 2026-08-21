from __future__ import annotations

import io
import json
import zipfile

import openpyxl
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import naim_risk.api as api_main
from naim_risk.api import app, get_service
from naim_risk.config import load_config
from naim_risk.pipeline import run_pipeline


def _configure_matching_demo_mode(
    monkeypatch: pytest.MonkeyPatch,
    service,
) -> None:
    monkeypatch.setenv("NAIM_DATA_MODE", "DEMO")
    monkeypatch.setenv("NAIM_DATASET_PROFILE", "test")
    monkeypatch.setenv("NAIM_RANDOM_SEED", str(service.config.seed))
    monkeypatch.setenv("NAIM_DATA_DIR", str(service.config.data_root))
    api_main.reset_application_state()
    app.dependency_overrides[get_service] = lambda: service


@pytest.mark.integration
def test_pipeline_persists_manifest_parquet_and_catalogue(test_config):
    result = run_pipeline(test_config, persist=True)
    assert result.validation.status == "PASS"
    assert result.paths["manifest"].exists()
    manifest = json.loads(result.paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["random_seed"] == test_config.seed
    assert manifest["configuration_hash"] == test_config.config_hash
    assert manifest["row_counts"]["monthly_account_performance"] > 2000
    assert result.paths["catalogue"].exists()


@pytest.mark.integration
def test_client_facing_api_shapes(service, monkeypatch: pytest.MonkeyPatch):
    _configure_matching_demo_mode(monkeypatch, service)
    try:
        client = TestClient(app)
        command = client.get("/api/v1/command-centre")
        assert command.status_code == 200
        command_json = command.json()
        assert command_json["metadata"]["synthetic"] is True
        assert command_json["kpis"]
        assert {"metric_id", "value", "prior_value", "unit", "denominator"}.issubset(
            command_json["kpis"][0]
        )
        root = client.get("/api/v1/root-cause").json()
        assert {"finding", "lenses"}.issubset(root)
        assert root["finding"]["causal_status"] == "ASSOCIATIONAL"
        for path, id_field in [
            ("/api/v1/partners", "partner_id"),
            ("/api/v1/vendors", "vendor_id"),
            ("/api/v1/memberships", "membership_tier_id"),
        ]:
            response = client.get(path)
            assert response.status_code == 200
            assert response.json()["data"]
            assert id_field in response.json()["data"][0]
        assert client.get("/api/v1/data-quality").json()["publication_allowed"] is True
        assert client.get("/api/v1/analysis-templates").json()["live_count"] == 4
        filter_metadata = client.get("/api/v1/filters").json()["supported_filter_metadata"]
        support = {row["filter"]: row["supported"] for row in filter_metadata}
        assert support["comparison"] is False
        assert support["vintage"] is False
    finally:
        app.dependency_overrides.clear()
        api_main.reset_application_state()


@pytest.mark.integration
def test_api_mutations_scenarios_commentary_and_exports(
    service,
    monkeypatch: pytest.MonkeyPatch,
):
    _configure_matching_demo_mode(monkeypatch, service)
    try:
        client = TestClient(app)
        scenario = client.post(
            "/api/v1/scenarios/run",
            json={"scenario_name": "Fraud Shock", "horizon_months": 3},
        )
        assert scenario.status_code == 200
        assert len(scenario.json()["projections"]) == 3
        commentary = client.post("/api/v1/commentary/generate", json={}).json()
        assert commentary["verification_status"] == "PASS"
        assert commentary["draft_requires_human_review"] is True
        investigation = client.post(
            "/api/v1/investigations",
            json={"business_question": "Why did validated loss move?"},
        )
        assert investigation.status_code == 201
        updated = client.patch(
            f"/api/v1/investigations/{investigation.json()['investigation_id']}",
            json={"status": "Investigating", "owner": "Synthetic Analyst"},
        )
        assert updated.json()["status"] == "Investigating"
        powerbi = client.post("/api/v1/exports/powerbi").json()
        assert "path" not in powerbi
        assert not powerbi["filename"].startswith("/")
        powerbi_download = client.get(powerbi["download_url"])
        assert powerbi_download.status_code == 200
        download_state = service.workflow_store.get("export_job", powerbi["artifact_id"])["state"]
        assert download_state["download_count"] == 1
        assert download_state["last_downloaded_by"] == "local-development"
        with zipfile.ZipFile(io.BytesIO(powerbi_download.content)) as archive:
            names = set(archive.namelist())
            assert "relationships.json" in names
            assert "metric_registry.json" in names
        excel = client.post("/api/v1/exports/excel").json()
        assert "path" not in excel
        assert not excel["filename"].startswith("/")
        excel_download = client.get(excel["download_url"])
        assert excel_download.status_code == 200
        workbook = openpyxl.load_workbook(io.BytesIO(excel_download.content), read_only=True)
        assert {"KPI Summary", "Metric Registry", "Provenance"}.issubset(workbook.sheetnames)
        demo = client.post("/api/v1/demo/run").json()
        selected = demo["selected_period"]
        assert selected["metric_id"] == "ANNUALISED_NET_LOSS_RATE"
        command_step = next(row for row in demo["steps"] if row["step_id"] == 7)
        assert command_step["result"]["kpis"][0]["reporting_period"] == selected["period"]
        assert len(demo["steps"]) == 15
    finally:
        app.dependency_overrides.clear()
        api_main.reset_application_state()


@pytest.mark.integration
def test_api_sanitises_manifest_and_quarantine_paths(service):
    original_paths = service.data.manifest.get("paths", {})
    check = service.data.validation.checks[0]
    original_quarantine = check.quarantine_location
    service.data.manifest["paths"] = {"raw.example": "/private/sensitive/raw/example.parquet"}
    check.quarantine_location = "/private/sensitive/quarantine/rejected.parquet"
    app.dependency_overrides[get_service] = lambda: service
    try:
        response = TestClient(app).get("/api/v1/data-quality")
        assert response.status_code == 200
        payload = response.json()
        assert payload["manifest"]["paths"]["raw.example"] == "example.parquet"
        assert payload["checks"][0]["quarantine_location"] == "rejected.parquet"
        assert "/private/" not in json.dumps(payload)
    finally:
        service.data.manifest["paths"] = original_paths
        check.quarantine_location = original_quarantine
        app.dependency_overrides.clear()


@pytest.mark.integration
def test_historical_analytics_exclude_all_future_periods(
    service,
    monkeypatch: pytest.MonkeyPatch,
):
    months = service.filters()["data"]["month"]
    selected = months[-4]
    assert months[-1] > selected
    _configure_matching_demo_mode(monkeypatch, service)
    try:
        client = TestClient(app)
        command = client.get(
            "/api/v1/command-centre",
            params={"reporting_month": selected},
        )
        assert command.status_code == 200
        command_payload = command.json()
        assert command_payload["metadata"]["maximum_source_month_used"] == selected
        assert command_payload["metadata"]["future_periods_excluded"] is True
        assert command_payload["trends"]
        assert max(row["month"] for row in command_payload["trends"]) <= selected
        assert command_payload["alerts"]
        assert all(row["generation_timestamp"] <= selected for row in command_payload["alerts"])

        trends = client.get(
            "/api/v1/trends",
            params={"reporting_month": selected},
        ).json()
        assert max(row["month"] for row in trends["data"]) <= selected
        alerts = client.get(
            "/api/v1/alerts",
            params={"reporting_month": selected},
        ).json()
        assert alerts["data"]
        assert all(row["generation_timestamp"] <= selected for row in alerts["data"])
        root = client.get(
            "/api/v1/root-cause",
            params={"reporting_month": selected},
        ).json()
        assert root["metadata"]["maximum_source_month_used"] == selected
        if root["finding"]:
            assert root["finding"]["comparison_period"].startswith(selected[:7])

        commentary = client.post(
            "/api/v1/commentary/generate",
            json={"period": selected},
        ).json()
        evidence_alerts = commentary["evidence_contract"]["alert_status"]
        assert all(row["generation_timestamp"] <= selected for row in evidence_alerts)

        for endpoint in [
            "vintages",
            "strategy-comparison",
            "memberships",
            "benefits",
            "finance",
            "scenarios",
        ]:
            payload = client.get(
                f"/api/v1/{endpoint}",
                params={"reporting_month": selected},
            ).json()
            assert payload["metadata"]["maximum_source_month_used"] == selected
            assert payload["metadata"]["future_periods_excluded"] is True

        partners = client.get(
            "/api/v1/partners",
            params={"reporting_month": selected},
        ).json()
        vendors = client.get(
            "/api/v1/vendors",
            params={"reporting_month": selected},
        ).json()
        assert partners["metadata"]["maximum_source_month_used"] == selected
        assert vendors["metadata"]["maximum_source_month_used"] == selected
        assert all(row["month"][:10] <= selected for row in partners["data"])
        assert all(row["month"][:10] <= selected for row in vendors["data"])

        bounded_strategy = client.get(
            "/api/v1/strategy-comparison",
            params={"reporting_month": selected},
        ).json()
        source = service.performance[service.performance["month"] <= pd.Timestamp(selected)]
        expected_assignments = int((source["strategy_assignment_type"] != "Recovery-only").sum())
        assert (
            sum(row["assignment_count"] for row in bounded_strategy["strategies"])
            == expected_assignments
        )

        finance = client.get(
            "/api/v1/finance",
            params={"reporting_month": selected},
        ).json()
        expected_profit = next(
            row["value"]
            for row in service.kpis(period=selected)["data"]
            if row["metric_id"] == "EXPECTED_PROFIT"
        )
        assert finance["bridge"][-1]["value"] == pytest.approx(expected_profit)

        scenarios = client.get(
            "/api/v1/scenarios",
            params={"reporting_month": selected},
        ).json()
        first_projection_month = scenarios["data"][0]["projections"][0]["month"]
        assert pd.Timestamp(first_projection_month) == pd.Timestamp(selected) + pd.DateOffset(
            months=1
        )

        baskets = client.get(
            "/api/v1/baskets",
            params={"reporting_month": selected},
        ).json()
        investigations = client.get(
            "/api/v1/investigations",
            params={"reporting_month": selected},
        ).json()
        assert baskets["metadata"]["scope"] == "current_definition_state"
        assert baskets["metadata"]["reporting_month_applied"] is False
        assert baskets["metadata"]["requested_reporting_month"] == selected
        assert investigations["metadata"]["scope"] == "current_workflow_state"
        assert investigations["metadata"]["reporting_month_applied"] is False
    finally:
        app.dependency_overrides.clear()
        api_main.reset_application_state()


@pytest.mark.integration
def test_runtime_environment_honours_profile_seed_and_data_directory(monkeypatch, tmp_path):
    data_root = tmp_path / "runtime-data"
    monkeypatch.setenv("NAIM_DATASET_PROFILE", "test")
    monkeypatch.setenv("NAIM_RANDOM_SEED", "918273")
    monkeypatch.setenv("NAIM_DATA_DIR", str(data_root))
    resolved = api_main.runtime_config_from_environment()

    assert resolved.profile.name == "test"
    assert resolved.seed == 918273
    assert resolved.data_root == data_root

    original_service = api_main._service
    api_main._service = None
    try:
        runtime_service = api_main.get_service()
        assert runtime_service.config.profile.name == "test"
        assert runtime_service.config.seed == 918273
        assert runtime_service.config.data_root == data_root
    finally:
        api_main._service = original_service


@pytest.mark.integration
def test_api_startup_reuses_only_matching_persisted_pipeline(monkeypatch, tmp_path):
    config = load_config("test", seed=662211, data_root=tmp_path / "persisted")
    persisted = run_pipeline(config, persist=True)
    original_loader = api_main.load_pipeline_data
    loaded_paths = []

    def tracked_loader(path):
        loaded_paths.append(path)
        return original_loader(path)

    monkeypatch.setattr(api_main, "runtime_config_from_environment", lambda: config)
    monkeypatch.setattr(api_main, "load_pipeline_data", tracked_loader)
    original_service = api_main._service
    api_main._service = None
    try:
        runtime_service = api_main.get_service()
        assert runtime_service.data.run_id == persisted.run_id
        assert runtime_service.data.manifest["configuration_hash"] == config.config_hash
        assert runtime_service.data.validation.checks[0].check_id == "persisted_manifest"
        assert loaded_paths
    finally:
        api_main._service = original_service
