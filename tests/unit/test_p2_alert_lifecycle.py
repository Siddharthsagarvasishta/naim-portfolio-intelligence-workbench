from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from naim_risk.alerts import (
    AlertLifecycle,
    alert_fingerprint,
    build_alert_candidate,
    generate_alerts,
)
from naim_risk.auth import Permission, Role
from naim_risk.auth.service import ROLE_PERMISSIONS
from naim_risk.config import load_config
from naim_risk.workflow import ConcurrencyConflict, ObjectNotFound, WorkflowStore

NOW = datetime(2026, 8, 11, 8, 0, tzinfo=UTC)


def _rule(*, severity: str = "Adverse", cooldown: int = 1) -> dict[str, Any]:
    return {
        "alert_rule_id": "LOSS_MOVEMENT",
        "metric_id": "ANNUALISED_NET_LOSS_RATE",
        "alert_name": "Loss rate increased materially",
        "comparison_method": "basis_point_movement",
        "relative_threshold": 20,
        "minimum_denominator": 100,
        "consecutive_periods": 1,
        "severity": severity,
        "cooldown_period": cooldown,
        "sla_hours": 24,
        "owner_role": "Portfolio Risk Analytics",
        "recommended_investigation": "Review the reconciled loss movement.",
    }


def _candidate(
    period: str,
    *,
    severity: str = "Adverse",
    scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return build_alert_candidate(
        _rule(severity=severity),
        current_value=0.08,
        baseline_value=0.07,
        denominator=1_000,
        period=period,
        comparison_period="2024-12-01",
        quality_status="PASS",
        selected_scope=scope or {"product_type": ["Card"]},
        rule_version="2.0.0",
    )


def _lifecycle(store: WorkflowStore) -> AlertLifecycle:
    return AlertLifecycle(store, clock=lambda: NOW)


def _reconcile(
    lifecycle: AlertLifecycle,
    candidate: dict[str, Any],
    *,
    run_id: str,
) -> dict[str, Any]:
    return lifecycle.reconcile(
        [candidate],
        run_id=run_id,
        configuration_hash="c" * 64,
        dataset_hash="d" * 64,
        evaluation_period=str(candidate["generation_timestamp"]),
        selected_scope=candidate["selected_scope"],
    )[0]


def test_fingerprint_is_invariant_to_scope_order_and_dynamic_observation_facts() -> None:
    kwargs = {
        "alert_rule_id": "LOSS_MOVEMENT",
        "metric_id": "ANNUALISED_NET_LOSS_RATE",
        "segment_or_basket": "Portfolio",
        "comparison_method": "basis_point_movement",
    }
    first = alert_fingerprint(
        **kwargs,
        selected_scope={"product_type": ["Card", "Loan"], "geography": ["US"]},
    )
    second = alert_fingerprint(
        **kwargs,
        selected_scope={"geography": ["US"], "product_type": ["Loan", "Card"]},
    )
    assert first == second
    assert first[1] == f"ALERT-{first[0][:20].upper()}"

    candidate_one = _candidate("2025-01-01", severity="Adverse")
    candidate_two = _candidate("2025-02-01", severity="Critical")
    assert candidate_one["fingerprint"] == candidate_two["fingerprint"]
    assert candidate_one["alert_id"] == candidate_two["alert_id"]


def test_fingerprint_distinguishes_selected_scope() -> None:
    first = _candidate("2025-01-01", scope={"product_type": ["Card"]})
    second = _candidate("2025-01-01", scope={"product_type": ["Loan"]})
    assert first["fingerprint"] != second["fingerprint"]
    assert first["alert_id"] != second["alert_id"]


def test_data_quality_alert_uses_governed_trend_period_and_fails_without_one() -> None:
    rule = {
        **_rule(severity="Critical", cooldown=0),
        "alert_rule_id": "COMPLETENESS",
        "metric_id": "DATA_COMPLETENESS",
        "comparison_method": "data_quality",
        "absolute_threshold": 0.995,
    }
    rule.pop("relative_threshold")
    trends = [
        {"metric_id": "ACTIVE_ACCOUNTS", "month": "2025-01-01", "value": 10},
        {"metric_id": "ACTIVE_ACCOUNTS", "month": "2025-02-01", "value": 11},
    ]
    alerts = generate_alerts(
        trends,
        [rule],
        quality_status="BLOCKED",
        completeness=0.9,
        rule_version="2.0.0",
    )
    assert alerts[0]["generation_timestamp"] == "2025-02-01"
    assert alerts[0]["comparison_period"] == "2025-01-01"
    with pytest.raises(ValueError, match="governed reporting period"):
        generate_alerts(
            [],
            [rule],
            quality_status="BLOCKED",
            completeness=0.9,
            rule_version="2.0.0",
        )


def test_idempotency_recurrence_escalation_ack_cooldown_and_reopen(tmp_path: Path) -> None:
    database = tmp_path / "alerts.sqlite3"
    store = WorkflowStore(f"sqlite+pysqlite:///{database}")
    lifecycle = _lifecycle(store)
    january = _reconcile(lifecycle, _candidate("2025-01-01"), run_id="RUN-1")
    assert january["recurrence_count"] == 0
    assert january["version"] == 1
    assert january["condition_active"] is True
    assert january["workflow_active"] is True

    repeated_get = _reconcile(lifecycle, _candidate("2025-01-01"), run_id="RUN-1")
    assert repeated_get["version"] == 1
    assert repeated_get["recurrence_count"] == 0

    february = _reconcile(
        lifecycle,
        _candidate("2025-02-01", severity="Critical"),
        run_id="RUN-2",
    )
    assert february["alert_id"] == january["alert_id"]
    assert february["recurrence_count"] == 1
    assert february["severity"] == "Critical"
    assert february["latest_evidence"]["run_id"] == "RUN-2"
    assert february["latest_evidence"]["configuration_hash"] == "c" * 64
    assert february["latest_evidence"]["dataset_hash"] == "d" * 64

    acknowledged = lifecycle.acknowledge(
        january["alert_id"],
        expected_version=february["version"],
        note="Owned by the portfolio analyst.",
        actor="analyst",
    )
    assert acknowledged["status"] == "ACKNOWLEDGED"
    assert acknowledged["acknowledged_by"] == "analyst"

    store.close()
    restarted_store = WorkflowStore(f"sqlite+pysqlite:///{database}")
    restarted = _lifecycle(restarted_store)
    persisted = restarted.get(january["alert_id"])
    assert persisted["status"] == "ACKNOWLEDGED"
    assert persisted["acknowledgement_note"] == "Owned by the portfolio analyst."

    resolved = restarted.transition(
        january["alert_id"],
        expected_version=persisted["version"],
        target_status="RESOLVED",
        reason="Verified mitigating action completed.",
        actor="analyst",
    )
    assert resolved["cooldown_until_period"] == "2025-03-01"
    during_cooldown = _reconcile(
        restarted,
        _candidate("2025-03-01", severity="Adverse"),
        run_id="RUN-3",
    )
    assert during_cooldown["status"] == "SUPPRESSED"
    assert during_cooldown["workflow_active"] is False
    assert during_cooldown["condition_active"] is True

    reopened = _reconcile(
        restarted,
        _candidate("2025-04-01", severity="Adverse"),
        run_id="RUN-4",
    )
    assert reopened["status"] == "NEW"
    assert reopened["alert_id"] == january["alert_id"]
    assert reopened["recurrence_count"] == 3
    assert reopened["can_acknowledge"] is True
    assert reopened["acknowledged_by"] is None
    assert reopened["reopen_history"][0]["prior_status"] == "SUPPRESSED"
    event_types = [event["event_type"] for event in reopened["audit_events"]]
    assert {
        "ALERT_CREATED",
        "ALERT_REPEATED",
        "ALERT_ESCALATED",
        "ALERT_ACKNOWLEDGED",
        "ALERT_RESOLVED",
        "ALERT_SUPPRESSED",
        "ALERT_REOPENED",
    }.issubset(event_types)
    assert reopened["audit_integrity"]["status"] == "PASS"
    assert reopened["audit_integrity"]["chain_valid"] is True


def test_manual_suppression_reason_resolution_and_optimistic_concurrency() -> None:
    lifecycle = _lifecycle(WorkflowStore("sqlite+pysqlite:///:memory:"))
    alert = _reconcile(lifecycle, _candidate("2025-01-01"), run_id="RUN-1")
    with pytest.raises(ValueError, match="requires a reason"):
        lifecycle.transition(
            alert["alert_id"],
            expected_version=alert["version"],
            target_status="SUPPRESSED",
            reason=" ",
            actor="analyst",
        )
    suppressed = lifecycle.transition(
        alert["alert_id"],
        expected_version=alert["version"],
        target_status="SUPPRESSED",
        reason="Known synthetic test account cohort.",
        actor="analyst",
        suppression_until_period="2025-02-01",
    )
    assert suppressed["suppression_reason"] == "Known synthetic test account cohort."
    assert suppressed["workflow_active"] is False
    with pytest.raises(ConcurrencyConflict):
        lifecycle.transition(
            alert["alert_id"],
            expected_version=alert["version"],
            target_status="RESOLVED",
            reason="Stale mutation must not win.",
            actor="analyst",
        )


def test_reconcile_is_scope_bound_and_malformed_period_fails_closed() -> None:
    lifecycle = _lifecycle(WorkflowStore("sqlite+pysqlite:///:memory:"))
    card = _candidate("2025-01-01", scope={"product_type": ["Card"]})
    loan = _candidate("2025-01-01", scope={"product_type": ["Loan"]})
    card_row = _reconcile(lifecycle, card, run_id="RUN-1")
    assert len(card_row) > 0
    loan_rows = lifecycle.reconcile(
        [loan],
        run_id="RUN-1",
        configuration_hash="c" * 64,
        dataset_hash="d" * 64,
        evaluation_period="2025-01-01",
        selected_scope={"product_type": ["Loan"]},
    )
    assert [row["selected_scope"] for row in loan_rows] == [
        {"product_type": ["Loan"]}
    ]
    with pytest.raises(ObjectNotFound):
        lifecycle.get(
            card_row["alert_id"],
            selected_scope={"product_type": ["Loan"]},
        )
    with pytest.raises(ObjectNotFound):
        lifecycle.acknowledge(
            card_row["alert_id"],
            expected_version=card_row["version"],
            note="Wrong-scope mutation must not win.",
            actor="analyst",
            selected_scope={"product_type": ["Loan"]},
        )

    before = len(lifecycle.store.list("alert"))
    malformed = _candidate(
        "2025-01-01",
        scope={"product_type": ["Malformed period cohort"]},
    )
    malformed["generation_timestamp"] = "current"
    with pytest.raises(ValueError, match="YYYY-MM"):
        _reconcile(lifecycle, malformed, run_id="RUN-2")
    assert len(lifecycle.store.list("alert")) == before

    with pytest.raises(ValueError, match="YYYY-MM"):
        lifecycle.reconcile(
            [_candidate("2025-02-01", scope={"product_type": ["New"]})],
            run_id="RUN-3",
            configuration_hash="c" * 64,
            dataset_hash="d" * 64,
            evaluation_period="2025-99-99",
            selected_scope={"product_type": ["New"]},
        )
    assert len(lifecycle.store.list("alert")) == before


def test_governed_alert_config_is_versioned_complete_and_byte_identical() -> None:
    root = Path("config/alert_rules.json")
    bundled = Path("src/naim_risk/resources/config/alert_rules.json")
    assert root.read_bytes() == bundled.read_bytes()
    payload = json.loads(root.read_text(encoding="utf-8"))
    assert payload["rule_version"] == "2.0.0"
    assert {rule["severity"] for rule in payload["rules"]} == {
        "Critical",
        "Adverse",
        "Watch",
    }
    assert all(int(rule["sla_hours"]) > 0 for rule in payload["rules"])
    hierarchy = {rule["alert_rule_id"]: rule["severity"] for rule in payload["rules"]}
    assert hierarchy["COMPLETENESS"] == "Critical"
    assert hierarchy["LOSS_MOVEMENT"] == "Adverse"
    assert hierarchy["FALSE_POSITIVE_GUARDRAIL"] == "Watch"
    assert load_config("test").alert_rule_version == "2.0.0"


def test_manage_alerts_permission_is_role_bound() -> None:
    assert Permission.MANAGE_ALERTS in ROLE_PERMISSIONS[Role.PORTFOLIO_ANALYST]
    assert Permission.MANAGE_ALERTS in ROLE_PERMISSIONS[Role.STRATEGY_ANALYST]
    assert Permission.MANAGE_ALERTS in ROLE_PERMISSIONS[Role.ADMINISTRATOR]
    assert Permission.MANAGE_ALERTS not in ROLE_PERMISSIONS[Role.EXECUTIVE_VIEWER]
    assert Permission.MANAGE_ALERTS not in ROLE_PERMISSIONS[Role.MODEL_VALIDATOR]
