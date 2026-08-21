from __future__ import annotations

import io
import zipfile
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

import naim_risk.api as api_main
from naim_risk.api import app, get_service


@pytest.fixture
def quant_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    service,
):
    monkeypatch.setenv("NAIM_AUTH_MODE", "disabled")
    monkeypatch.setenv("NAIM_DATA_MODE", "DEMO")
    monkeypatch.setenv("NAIM_DATASET_PROFILE", "test")
    monkeypatch.setenv("NAIM_DATA_DIR", str(service.config.data_root))
    monkeypatch.setenv(
        "NAIM_DATABASE_URL",
        f"sqlite+pysqlite:///{(tmp_path / 'workflow.sqlite3').resolve()}",
    )
    api_main.reset_application_state()
    app.dependency_overrides[get_service] = lambda: service
    client = TestClient(app)
    try:
        yield client
    finally:
        client.close()
        app.dependency_overrides.clear()
        api_main.reset_application_state()


@pytest.mark.integration
def test_market_risk_lab_and_downloadable_export_are_live(quant_client: TestClient) -> None:
    status = quant_client.get("/api/v1/market-risk/status")
    assert status.status_code == 200
    assert status.json()["status"] == "LIVE"
    assert status.json()["trading_recommendation"] is False

    request = {
        "instrument": "NAIM-DEMO-INDEX",
        "period": "one_year",
        "end_date": "2025-12-31",
        "windows": [21, 63],
    }
    analysis = quant_client.post("/api/v1/market-risk/run", json=request)
    assert analysis.status_code == 200
    payload = analysis.json()
    assert payload["status"] == "implemented"
    assert payload["conditional_volatility"]["garch"]["status"] == "implemented"
    assert payload["var_backtesting"]["status"] == "implemented"
    assert payload["governance"]["trading_recommendation"] is False

    exported = quant_client.post(
        "/api/v1/market-risk/export",
        json={**request, "include_excel": False, "include_presentation": False},
    )
    assert exported.status_code == 201
    export_payload = exported.json()
    assert export_payload["status"] == "completed"
    assert export_payload["approval_state"] == "DRAFT"
    download = quant_client.get(export_payload["download_url"])
    assert download.status_code == 200
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        assert {
            "market_risk_evidence.json",
            "prepared_returns.csv",
            "prepared_returns.parquet",
            "export_manifest.json",
        }.issubset(archive.namelist())


def _behavioural_records() -> list[dict[str, object]]:
    records = []
    for account in range(60):
        for month in range(12):
            records.append(
                {
                    "account_id": f"A-{account:03d}",
                    "month": f"2024-{month + 1:02d}-01",
                    "days_past_due": 30 if (account + month) % 7 == 0 else 0,
                    "utilization": ((account * 3 + month) % 20) / 20,
                    "account_balance": 500 + account * 10 + month * 5,
                    "risk_group": "Elevated" if account % 2 else "Lower-to-moderate",
                }
            )
    return records


@pytest.mark.integration
def test_survival_behavioural_and_change_point_endpoints_execute(
    quant_client: TestClient,
) -> None:
    survival = quant_client.post("/api/v1/advanced-statistics/survival", json={})
    assert survival.status_code == 200
    assert survival.json()["status"] == "implemented"
    assert survival.json()["cox_proportional_hazards"]["status"] == "not_implemented"

    behavioural = quant_client.post(
        "/api/v1/advanced-statistics/behavioural",
        json={
            "records": _behavioural_records(),
            "feature_columns": ["utilization", "account_balance"],
        },
    )
    assert behavioural.status_code == 200
    assert behavioural.json()["status"] == "implemented"
    assert behavioural.json()["contribution_diagnostics"]["local_synthetic_record"]["features"]
    assert behavioural.json()["governance"]["causal_status"] == "predictive association only"

    rng = np.random.default_rng(73421)
    series = [*rng.normal(0, 0.2, 60), *rng.normal(2, 0.2, 60)]
    change = quant_client.post(
        "/api/v1/advanced-statistics/change-points",
        json={"series": series, "min_segment": 12},
    )
    assert change.status_code == 200
    assert change.json()["classification"] == "structural_level_shift"
    assert change.json()["method_validation"]["status"] == "passed"


@pytest.mark.integration
def test_propensity_and_synthetic_policy_did_execute_with_diagnostics(
    quant_client: TestClient,
) -> None:
    propensity_records = []
    for index in range(200):
        treatment = index % 2
        first = ((index * 7) % 23 - 11) / 5
        second = ((index * 11) % 19 - 9) / 4
        propensity_records.append(
            {
                "treatment": treatment,
                "outcome": 1.5 * treatment + 0.4 * first - 0.2 * second,
                "first": first,
                "second": second,
            }
        )
    propensity = quant_client.post(
        "/api/v1/advanced-statistics/propensity",
        json={
            "records": propensity_records,
            "treatment_column": "treatment",
            "outcome_column": "outcome",
            "covariates": ["first", "second"],
        },
    )
    assert propensity.status_code == 200
    assert propensity.json()["status"] in {"implemented", "review_required"}
    assert propensity.json()["balance"]
    assert "not a randomised result" in propensity.json()["sensitivity_warning"]

    did_records = []
    for entity in range(30):
        treated = int(entity < 15)
        for period in range(8):
            did_records.append(
                {
                    "entity": entity,
                    "date": f"2024-{period + 1:02d}-01",
                    "treated": treated,
                    "outcome": entity / 30 + 0.1 * period + (1.2 * treated if period >= 4 else 0),
                }
            )
    did = quant_client.post(
        "/api/v1/advanced-statistics/difference-in-differences",
        json={
            "records": did_records,
            "outcome_column": "outcome",
            "treatment_column": "treated",
            "time_column": "date",
            "policy_date": "2024-05-01",
            "cluster_column": "entity",
            "synthetic_policy_use_case": True,
        },
    )
    assert did.status_code == 200
    assert did.json()["status"] in {"implemented", "not_interpretable"}
    assert did.json()["estimate"]["difference_in_differences"] == pytest.approx(1.2, abs=0.1)
