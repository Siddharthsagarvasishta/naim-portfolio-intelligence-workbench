from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from naim_risk.api import app, get_service


@pytest.fixture
def client(service):
    app.dependency_overrides[get_service] = lambda: service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.integration
def test_partner_and_vendor_scenarios_are_live(client, service):
    partner_id = str(service.tables["partner_master"]["partner_id"].iloc[0])
    partner = client.post(
        "/api/v1/partner-scenarios/run",
        json={
            "partner_id": partner_id,
            "volume_multiplier": 1.1,
            "fraud_loss_multiplier": 1.2,
        },
    )
    assert partner.status_code == 200
    assert partner.json()["partner_id"] == partner_id
    assert partner.json()["status"] == "scenario_estimate"
    assert partner.json()["approval_required"] is True

    vendor_ids = service.tables["vendor_master"]["vendor_id"].astype(str).tolist()
    vendor = client.post(
        "/api/v1/vendor-reallocation/run",
        json={
            "source_vendor_id": vendor_ids[0],
            "target_vendor_id": vendor_ids[1],
            "reallocation_share": 0.25,
        },
    )
    assert vendor.status_code == 200
    assert vendor.json()["cases_moved"] >= 0
    assert vendor.json()["source_vendor_id"] != vendor.json()["target_vendor_id"]
    assert vendor.json()["saved"] is False


@pytest.mark.integration
def test_versioned_basket_crud_clone_and_lock_control(client):
    detail = client.get("/api/v1/baskets/BASKET-001")
    assert detail.status_code == 200
    assert detail.json()["members"]
    updated = client.patch(
        "/api/v1/baskets/BASKET-001",
        json={"basket_description": "Controlled updated description"},
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == detail.json()["version"] + 1
    assert updated.json()["approved_flag"] is False
    assert client.get("/api/v1/baskets/BASKET-001").json()["version"] == updated.json()["version"]
    cloned = client.post("/api/v1/baskets/BASKET-001/clone")
    assert cloned.status_code == 201
    assert cloned.json()["source_basket_id"] == "BASKET-001"
    assert cloned.json()["approved_flag"] is False
    locked = client.patch(
        "/api/v1/baskets/BASKET-002",
        json={"basket_description": "Must not change"},
    )
    assert locked.status_code == 422
    assert client.get("/api/v1/baskets/UNKNOWN").status_code == 404


@pytest.mark.integration
def test_workspace_lifecycle_and_live_run(client):
    created = client.post(
        "/api/v1/workspaces",
        json={
            "workspace_name": "Controlled test workspace",
            "business_question": "What changed in the governed portfolio?",
            "selected_metrics": ["ANNUALISED_NET_LOSS_RATE"],
        },
    )
    assert created.status_code == 201
    workspace_id = created.json()["workspace_id"]
    updated = client.patch(
        f"/api/v1/workspaces/{workspace_id}",
        json={"owner": "Synthetic Reviewer"},
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    assert updated.json()["change_audit"]["approval_required"] is True
    run = client.post(f"/api/v1/workspaces/{workspace_id}/run")
    assert run.status_code == 200
    assert run.json()["live_calculations"] is True
    assert run.json()["data_quality_status"] == "PASS"
    refresh = client.post(f"/api/v1/workspaces/{workspace_id}/refresh")
    assert refresh.json()["refresh"] is True
    assert client.get("/api/v1/workspaces/UNKNOWN").status_code == 404


@pytest.mark.integration
def test_peer_matching_and_analysis_template_execution(client, service):
    catalogue = client.get("/api/v1/peer-analogues")
    assert catalogue.status_code == 200
    partner_id = str(service.tables["partner_master"]["partner_id"].iloc[0])
    peer = client.post(
        "/api/v1/peer-analogues/match",
        json={
            "entity_type": "partner",
            "entity_id": partner_id,
            "peer_count": 3,
        },
    )
    assert peer.status_code == 200
    assert peer.json()["peer_count"] == 3
    assert partner_id not in {row["entity_id"] for row in peer.json()["selected_peer_population"]}
    assert peer.json()["causal_status"] == "DESCRIPTIVE"

    run = client.post(
        "/api/v1/analysis-templates/run",
        json={"template_id": "MONTHLY_KPI_MOVEMENT", "parameters": {}},
    )
    assert run.status_code == 200
    run_id = run.json()["run_id"]
    status = client.get(f"/api/v1/analysis-runs/{run_id}")
    assert status.status_code == 200
    assert status.json()["template_id"] == "MONTHLY_KPI_MOVEMENT"
    unavailable = client.post(
        "/api/v1/analysis-templates/run",
        json={"template_id": "PANEL_FIXED_EFFECTS", "parameters": {}},
    )
    assert unavailable.status_code == 422


@pytest.mark.integration
@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/data-onboarding/preview",
        "/api/v1/data-onboarding/map",
        "/api/v1/data-onboarding/validate",
        "/api/v1/data-onboarding/load",
        "/api/v1/composition-scenarios/run",
        "/api/v1/optimisation/run",
    ],
)
def test_former_integration_routes_no_longer_return_501(client, path):
    response = client.post(path)
    assert response.status_code != 501
    assert response.json().get("status") != "documented_integration"
