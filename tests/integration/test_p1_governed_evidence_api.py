from __future__ import annotations

from fastapi.testclient import TestClient

import naim_risk.api as api_main
from naim_risk.api import app, get_service, get_source_context
from naim_risk.config import CORE_METRIC_IDS
from naim_risk.runtime_modes import DataMode, SourceContext


def test_governed_kpi_registry_and_diagnostics_api_contracts(
    service,
    monkeypatch,
) -> None:
    monkeypatch.setenv("NAIM_DATA_MODE", "DEMO")
    monkeypatch.setenv("NAIM_DATASET_PROFILE", "test")
    monkeypatch.setenv("NAIM_RANDOM_SEED", str(service.config.seed))
    monkeypatch.setenv("NAIM_DATA_DIR", str(service.config.data_root))
    monkeypatch.setenv("NAIM_SNAPSHOT_STALE_AFTER_SECONDS", "86400")
    api_main.reset_application_state()
    app.dependency_overrides[get_service] = lambda: service
    try:
        client = TestClient(app)
        request_id = "p1-governed-evidence-contract"
        kpi_response = client.get(
            "/api/v1/kpis",
            headers={"X-Request-ID": request_id},
        )
        assert kpi_response.status_code == 200
        assert kpi_response.headers["X-Request-ID"] == request_id
        assert kpi_response.headers["X-nAIM-Data-Mode"] == "DEMO"
        kpi_payload = kpi_response.json()
        assert "request_id" not in kpi_payload
        assert kpi_payload["data_mode"] == "DEMO"
        assert kpi_payload["source_context"]["active_mode"] == "DEMO"
        assert len(kpi_payload["data"]) == len(CORE_METRIC_IDS)
        for row in kpi_payload["data"]:
            assert row["source"] == "validated.monthly_account_performance"
            assert row["source_fields"]
            assert row["lineage"]["source"] == row["source"]
            assert row["lineage"]["refresh_facts"]["watermark_field"] == "month"
            assert row["runtime_evidence"]["dataset_hash"] == (
                kpi_payload["source_context"]["dataset_hash"]
            )
            assert row["runtime_evidence"]["configuration_hash"] == (
                kpi_payload["source_context"]["configuration_hash"]
            )
            assert row["runtime_evidence"]["run_id"] == service.data.run_id
            assert row["reconciliation"]["status"] == "NOT_RUN"
            assert row["statistical_status"] == "NOT_RUN"
            assert row["statistical_assessment"]["status"] == "NOT_RUN"
            assert isinstance(row["interpretation_boundary"]["can_conclude"], list)
            assert isinstance(row["interpretation_boundary"]["cannot_conclude"], list)

        command_response = client.get("/api/v1/command-centre")
        assert command_response.status_code == 200
        command_payload = command_response.json()
        by_metric = {
            row["metric_id"]: row["runtime_evidence"]
            for row in command_payload["kpis"]
        }
        assert by_metric == {
            row["metric_id"]: row["runtime_evidence"] for row in kpi_payload["data"]
        }

        registry_response = client.get("/api/v1/metric-registry")
        assert registry_response.status_code == 200
        registry_payload = registry_response.json()
        assert registry_payload["version"] == "2.0.0"
        assert registry_payload["registry_version"] == "2.0.0"
        assert {row["metric_id"] for row in registry_payload["data"]} == set(
            CORE_METRIC_IDS
        )
        for definition in registry_payload["data"]:
            assert definition["source"] != "N/A"
            assert isinstance(definition["interpretation_boundary"]["can_conclude"], list)
            assert isinstance(definition["interpretation_boundary"]["cannot_conclude"], list)
            assert definition["statistical_rule"]["status"] == "NOT_RUN"
            assert definition["adequacy_rule"]["status_when_unmet"] == "INADEQUATE"
            assert definition["runtime_evidence"]["evidence_id"]

        data_source_response = client.get("/api/v1/data-source")
        assert data_source_response.status_code == 200
        source_payload = data_source_response.json()
        assert source_payload["mode"] == "DEMO"
        assert source_payload["diagnostics"]["active_mode"] == "DEMO"
        assert source_payload["diagnostics"]["diagnostic_status"] == "UNKNOWN"
        assert source_payload["diagnostics"]["snapshot"]["freshness_status"] == "UNKNOWN"
        assert source_payload["diagnostics"]["provenance"]["dataset_hash"] == (
            source_payload["source_context"]["dataset_hash"]
        )
        assert source_payload["diagnostics"]["provenance"]["configuration_hash"] == (
            service.config.config_hash
        )
        assert source_payload["diagnostics"]["provenance"][
            "current_governed_configuration_hash"
        ] == service.config.config_hash
        assert source_payload["diagnostics"]["provenance"]["configuration_match"] is True
        lowered = str(source_payload).lower()
        assert "request_history" not in lowered
        assert "last_request" not in lowered
    finally:
        app.dependency_overrides.clear()
        api_main.reset_application_state()


def test_kpi_api_rejects_conflicting_envelope_provenance(service, monkeypatch) -> None:
    monkeypatch.setenv("NAIM_DATA_MODE", "DEMO")
    monkeypatch.setenv("NAIM_DATASET_PROFILE", "test")
    monkeypatch.setenv("NAIM_RANDOM_SEED", str(service.config.seed))
    monkeypatch.setenv("NAIM_DATA_DIR", str(service.config.data_root))
    api_main.reset_application_state()
    conflicting = SourceContext(
        active_mode=DataMode.DEMO,
        configured_mode=DataMode.DEMO,
        snapshot_date=None,
        configuration_hash="foreign-configuration",
        dataset_hash="foreign-dataset",
        dataset_hash_basis="foreign-basis",
        run_id="foreign-run",
        synthetic=True,
        reason=None,
    )
    app.dependency_overrides[get_service] = lambda: service
    app.dependency_overrides[get_source_context] = lambda: conflicting
    try:
        response = TestClient(app).get("/api/v1/kpis")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "INVALID_ANALYTICAL_REQUEST"
        assert "configuration_hash does not match" in response.json()["error"]["message"]
        assert "data" not in response.json()
    finally:
        app.dependency_overrides.clear()
        api_main.reset_application_state()
