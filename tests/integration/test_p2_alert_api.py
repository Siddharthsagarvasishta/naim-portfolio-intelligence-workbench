from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import naim_risk.api as api_main
from naim_risk.alerts import build_alert_candidate
from naim_risk.api import app, get_service, get_source_context
from naim_risk.auth import Role
from naim_risk.runtime_modes import DataMode, SourceContext
from naim_risk.service import WorkbenchService
from naim_risk.workflow import WorkflowStore

SECRET = "test-only-alert-signing-secret-that-is-long-enough"


@pytest.mark.integration
def test_alert_api_durable_mutations_permissions_audit_and_idempotent_get(
    test_config,
    pipeline_data,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service_store = WorkflowStore(
        f"sqlite+pysqlite:///{(tmp_path / 'service-alerts.sqlite3').resolve()}"
    )
    service = WorkbenchService(test_config, pipeline_data, workflow_store=service_store)
    context = SourceContext(
        active_mode=DataMode.DEMO,
        configured_mode=DataMode.DEMO,
        snapshot_date=str(service.data.manifest.get("maximum_data_date")),
        configuration_hash=service.config.config_hash,
        dataset_hash="d" * 64,
        dataset_hash_basis="test-governed-dataset",
        run_id=service.data.run_id,
        synthetic=True,
        reason=None,
    )
    monkeypatch.setenv("NAIM_DATA_MODE", "DEMO")
    monkeypatch.setenv("NAIM_DATASET_PROFILE", "test")
    monkeypatch.setenv("NAIM_DATA_DIR", str(test_config.data_root))
    monkeypatch.setenv("NAIM_AUTH_MODE", "demo")
    monkeypatch.setenv("NAIM_TOKEN_SECRET", SECRET)
    monkeypatch.setenv(
        "NAIM_DATABASE_URL",
        f"sqlite+pysqlite:///{(tmp_path / 'api-auth.sqlite3').resolve()}",
    )
    api_main.reset_application_state()
    app.dependency_overrides[get_service] = lambda: service
    app.dependency_overrides[get_source_context] = lambda: context
    try:
        auth = api_main.get_auth_service()
        auth.setup_demo_account(
            "executive",
            "secure executive phrase",
            Role.EXECUTIVE_VIEWER,
        )
        auth.setup_demo_account(
            "validator",
            "secure validator phrase",
            Role.MODEL_VALIDATOR,
        )
        auth.setup_demo_account(
            "portfolio.analyst",
            "secure portfolio phrase",
            Role.PORTFOLIO_ANALYST,
        )
        client = TestClient(app)

        first = client.get("/api/v1/alerts")
        assert first.status_code == 200
        assert first.json()["data"]
        alert = first.json()["data"][0]
        required = {
            "alert_id",
            "fingerprint",
            "alert_rule_id",
            "rule_version",
            "metric_id",
            "severity",
            "owner",
            "status",
            "sla_hours",
            "sla_due_at",
            "recurrence_count",
            "first_observed",
            "last_observed",
            "observation_key",
            "latest_evidence",
            "allowed_transitions",
            "can_acknowledge",
            "condition_active",
            "workflow_active",
            "version",
            "audit_events",
            "audit_integrity",
        }
        assert required.issubset(alert)
        assert alert["alert_fingerprint"] == alert["fingerprint"]
        assert alert["alert_rule_name"] == alert["alert_name"]
        assert alert["acknowledgement"]["acknowledged"] is False
        assert alert["sla"]["hours"] == alert["sla_hours"]
        assert alert["first_observed_period"] == alert["first_observed"]
        assert alert["last_observation_key"] == alert["observation_key"]
        assert alert["recurrence_count"] == 0
        assert alert["latest_evidence"]["run_id"] == service.data.run_id
        assert alert["latest_evidence"]["configuration_hash"] == service.config.config_hash
        assert alert["latest_evidence"]["dataset_hash"] == "d" * 64

        second = client.get("/api/v1/alerts")
        repeated = second.json()["data"][0]
        assert repeated["alert_id"] == alert["alert_id"]
        assert repeated["version"] == alert["version"]
        assert len(service.workflow_store.list("alert")) == 1

        detail = client.get(f"/api/v1/alerts/{alert['alert_id']}")
        assert detail.status_code == 200
        assert detail.json()["allowed_transitions"] == alert["allowed_transitions"]
        audit = client.get(f"/api/v1/alerts/{alert['alert_id']}/audit")
        assert audit.status_code == 200
        assert audit.json()["audit_integrity"]["status"] == "PASS"
        assert audit.json()["audit_events"][0]["event_type"] == "ALERT_CREATED"

        def login(username: str, password: str) -> dict[str, str]:
            response = client.post(
                "/api/v1/auth/login",
                json={"username": username, "password": password},
            )
            assert response.status_code == 200
            return {"Authorization": f"Bearer {response.json()['access_token']}"}

        viewer_headers = login("executive", "secure executive phrase")
        validator_headers = login("validator", "secure validator phrase")
        for headers in (viewer_headers, validator_headers):
            forbidden = client.post(
                f"/api/v1/alerts/{alert['alert_id']}/acknowledge",
                headers=headers,
                json={"expected_version": alert["version"], "note": "I own this."},
            )
            assert forbidden.status_code == 403
            assert forbidden.json()["error"]["code"] == "PERMISSION_DENIED"

        analyst_headers = login("portfolio.analyst", "secure portfolio phrase")
        scoped_filters = {"product_type": ["Scoped Card"]}
        scoped_candidate = build_alert_candidate(
            service.config.alert_rules[0],
            current_value=0.09,
            baseline_value=0.07,
            denominator=1_000,
            period="2025-08-01",
            comparison_period="2025-07-01",
            quality_status="PASS",
            selected_scope=scoped_filters,
            rule_version=service.config.alert_rule_version,
        )
        scoped_alert = service.alert_lifecycle.reconcile(
            [scoped_candidate],
            run_id=service.data.run_id,
            configuration_hash=service.config.config_hash,
            dataset_hash="d" * 64,
            evaluation_period="2025-08-01",
            selected_scope=scoped_filters,
        )[0]
        wrong_scope_detail = client.get(
            f"/api/v1/alerts/{scoped_alert['alert_id']}"
        )
        assert wrong_scope_detail.status_code == 404
        correct_scope_detail = client.get(
            f"/api/v1/alerts/{scoped_alert['alert_id']}",
            params={"product": "Scoped Card"},
        )
        assert correct_scope_detail.status_code == 200
        wrong_scope_acknowledgement = client.post(
            f"/api/v1/alerts/{scoped_alert['alert_id']}/acknowledge",
            headers=analyst_headers,
            json={
                "expected_version": scoped_alert["version"],
                "note": "Wrong scope must not mutate.",
            },
        )
        assert wrong_scope_acknowledgement.status_code == 404
        assert service.alert_lifecycle.get(
            scoped_alert["alert_id"],
            selected_scope=scoped_filters,
        )["version"] == scoped_alert["version"]

        acknowledged = client.post(
            f"/api/v1/alerts/{alert['alert_id']}/acknowledge",
            headers=analyst_headers,
            json={
                "expected_version": alert["version"],
                "note": "Accepted for governed investigation.",
            },
        )
        assert acknowledged.status_code == 200
        acknowledged_row = acknowledged.json()
        assert acknowledged_row["status"] == "ACKNOWLEDGED"
        assert acknowledged_row["acknowledged_by"] == "portfolio.analyst"
        assert acknowledged_row["can_acknowledge"] is False
        assert acknowledged_row["workflow_active"] is True

        stale = client.post(
            f"/api/v1/alerts/{alert['alert_id']}/acknowledge",
            headers=analyst_headers,
            json={"expected_version": alert["version"], "note": "Stale repeat."},
        )
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "STALE_VERSION"

        started = client.post(
            f"/api/v1/alerts/{alert['alert_id']}/investigation",
            headers=analyst_headers,
            json={
                "expected_version": acknowledged_row["version"],
                "reason": "Evidence owner assigned.",
                "owner": "Portfolio Risk Analytics",
            },
        )
        assert started.status_code == 200
        started_row = started.json()
        investigating_row = started_row["alert"]
        investigation = started_row["investigation"]
        assert investigating_row["status"] == "INVESTIGATING"
        assert investigating_row["owner"] == "Portfolio Risk Analytics"
        assert investigating_row["related_investigation"] == investigation["investigation_id"]
        assert investigation["alert_id"] == alert["alert_id"]
        assert investigation["affected_metric"] == alert["metric_id"]
        assert investigation["evidence_id"] == alert["observation_key"]
        assert investigation["selected_scope"] == {}
        assert investigating_row["audit_integrity"]["chain_valid"] is True

        repeated_start = client.post(
            f"/api/v1/alerts/{alert['alert_id']}/investigation",
            headers=analyst_headers,
            json={
                "expected_version": investigating_row["version"],
                "reason": "Evidence owner assigned.",
                "owner": "Portfolio Risk Analytics",
            },
        )
        assert repeated_start.status_code == 200
        repeated_start_row = repeated_start.json()
        assert repeated_start_row["reused"] is True
        assert repeated_start_row["investigation"]["investigation_id"] == investigation["investigation_id"]
        assert repeated_start_row["alert"]["version"] == investigating_row["version"]
        assert len(service.workflow_store.list("investigation")) == 1

        action_proposed = client.post(
            f"/api/v1/alerts/{alert['alert_id']}/transition",
            headers=analyst_headers,
            json={
                "expected_version": investigating_row["version"],
                "target_status": "ACTION_PROPOSED",
                "reason": "Evidence-backed action is ready for review.",
            },
        )
        assert action_proposed.status_code == 200
        action_row = action_proposed.json()
        assert action_row["status"] == "ACTION_PROPOSED"

        invalid_extra = client.post(
            f"/api/v1/alerts/{alert['alert_id']}/transition",
            headers=analyst_headers,
            json={
                "expected_version": action_row["version"],
                "target_status": "RESOLVED",
                "reason": "Complete.",
                "fabricated": True,
            },
        )
        assert invalid_extra.status_code == 422
    finally:
        app.dependency_overrides.clear()
        api_main.reset_application_state()
        service_store.close()
