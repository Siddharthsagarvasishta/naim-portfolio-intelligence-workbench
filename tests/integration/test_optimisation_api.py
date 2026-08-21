from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import naim_risk.api as api_main
from naim_risk.api import app


def _payload(*, save: bool) -> dict:
    return {
        "decision_dimension": "partner_allocation",
        "objective": "maximise_expected_profit",
        "items": [
            {
                "name": "Partner A",
                "baseline": 0.5,
                "minimum": 0.2,
                "maximum": 0.8,
                "expected_profit": 10,
                "expected_loss": 0.08,
            },
            {
                "name": "Partner B",
                "baseline": 0.5,
                "minimum": 0.2,
                "maximum": 0.8,
                "expected_profit": 6,
                "expected_loss": 0.02,
            },
        ],
        "constraints": {"allocation_total": 1, "loss_rate_max": 0.065},
        "save_scenario": save,
    }


@pytest.mark.integration
def test_live_optimisation_and_composition_endpoints_never_apply_result(
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
        optimisation = client.post("/api/v1/optimisation/run", json=_payload(save=True))
        assert optimisation.status_code == 200
        result = optimisation.json()
        assert result["feasible"] is True
        assert result["saved"] is True
        assert result["applied"] is False
        assert result["approval_state"] == "DRAFT"
        assert result["data_mode"] == "DEMO"

        composition = client.post("/api/v1/composition-scenarios/run", json=_payload(save=False))
        assert composition.status_code == 200
        assert composition.json()["saved"] is False
        assert composition.json()["applied"] is False
    finally:
        api_main.reset_application_state()
