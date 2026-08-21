from __future__ import annotations

from pathlib import Path

import pytest

from naim_risk.optimisation import optimise_allocation
from naim_risk.workflow import WorkflowStore


def _payload() -> dict:
    return {
        "decision_dimension": "acquisition_channel",
        "objective": "maximise_expected_profit",
        "items": [
            {
                "name": "Direct",
                "baseline": 0.5,
                "minimum": 0.1,
                "maximum": 0.9,
                "expected_profit": 10.0,
                "expected_loss": 0.10,
                "review_load": 0.3,
            },
            {
                "name": "Partner",
                "baseline": 0.5,
                "minimum": 0.1,
                "maximum": 0.9,
                "expected_profit": 5.0,
                "expected_loss": 0.02,
                "review_load": 0.1,
            },
        ],
        "constraints": {
            "allocation_total": 1.0,
            "loss_rate_max": 0.084,
            "concentration_limit": 0.85,
        },
    }


def test_hand_calculated_profit_maximum_respects_loss_guardrail() -> None:
    result = optimise_allocation(_payload())
    assert result["feasible"] is True
    assert result["applied"] is False
    assert result["approval_required"] is True
    assert result["optimised_allocation"]["Direct"] == pytest.approx(0.8)
    assert result["optimised_allocation"]["Partner"] == pytest.approx(0.2)
    assert "loss_rate_max" in result["binding_constraints"]
    assert result["expected_financial_effect"]["expected_profit"] == pytest.approx(1.5)
    assert result["expected_risk_effect"]["expected_loss"] == pytest.approx(0.024)


def test_conflicting_minimum_allocations_explain_infeasibility() -> None:
    payload = _payload()
    payload["items"][0]["minimum"] = 0.7
    payload["items"][1]["minimum"] = 0.6
    result = optimise_allocation(payload)
    assert result["feasible"] is False
    assert any("minima total" in reason for reason in result["infeasibility_explanation"])
    assert result["saved"] is False


def test_saved_scenario_is_durable_and_stays_draft(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'workflow.sqlite3').resolve()}"
    store = WorkflowStore(database_url)
    payload = {**_payload(), "save_scenario": True}
    output = optimise_allocation(payload, store=store, actor="strategy.analyst")
    store.close()

    restarted = WorkflowStore(database_url)
    try:
        record = restarted.get("scenario_run", output["scenario_id"])
        assert record["approval_state"] == "DRAFT"
        assert record["created_by"] == "strategy.analyst"
        assert record["state"]["applied"] is False
    finally:
        restarted.close()


def test_invalid_baseline_and_unknown_objective_are_rejected() -> None:
    payload = _payload()
    payload["items"][0]["baseline"] = 0.8
    with pytest.raises(ValueError, match="Baseline allocations"):
        optimise_allocation(payload)
    payload = _payload()
    payload["objective"] = "magical_return"
    with pytest.raises(ValueError, match="Unsupported objective"):
        optimise_allocation(payload)
