"""Durable alert recurrence, lifecycle, cooldown, and audit governance."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Any

from naim_risk.alerts.engine import normalise_selected_scope
from naim_risk.workflow import ConcurrencyConflict, DuplicateObject, ObjectNotFound, WorkflowStore

ALERT_STATUSES = (
    "NEW",
    "ACKNOWLEDGED",
    "INVESTIGATING",
    "ACTION_PROPOSED",
    "MONITORING",
    "RESOLVED",
    "SUPPRESSED",
    "CLOSED_AS_NOISE",
)
WORKFLOW_ACTIVE_STATUSES = frozenset(ALERT_STATUSES[:5])
SEVERITY_ORDER = {"Watch": 1, "Adverse": 2, "Critical": 3}
ALLOWED_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "NEW": (
        "ACKNOWLEDGED",
        "INVESTIGATING",
        "RESOLVED",
        "SUPPRESSED",
        "CLOSED_AS_NOISE",
    ),
    "ACKNOWLEDGED": (
        "INVESTIGATING",
        "ACTION_PROPOSED",
        "MONITORING",
        "RESOLVED",
        "SUPPRESSED",
        "CLOSED_AS_NOISE",
    ),
    "INVESTIGATING": (
        "ACTION_PROPOSED",
        "MONITORING",
        "RESOLVED",
        "SUPPRESSED",
        "CLOSED_AS_NOISE",
    ),
    "ACTION_PROPOSED": (
        "INVESTIGATING",
        "MONITORING",
        "RESOLVED",
        "SUPPRESSED",
        "CLOSED_AS_NOISE",
    ),
    "MONITORING": (
        "INVESTIGATING",
        "ACTION_PROPOSED",
        "RESOLVED",
        "SUPPRESSED",
        "CLOSED_AS_NOISE",
    ),
    "RESOLVED": (),
    "SUPPRESSED": ("INVESTIGATING", "RESOLVED", "CLOSED_AS_NOISE"),
    "CLOSED_AS_NOISE": (),
}


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def alert_observation_key(fingerprint: str, run_id: str, period: str) -> str:
    """Bind one observation without changing the cross-run condition identity."""

    return _canonical_hash(
        {"fingerprint": fingerprint, "run_id": run_id, "period": period}
    )


def _period_key(value: str) -> tuple[int, int]:
    text = str(value).strip()
    month_match = re.fullmatch(r"(\d{4})-(\d{2})", text)
    if month_match is not None:
        year, month = (int(part) for part in month_match.groups())
    else:
        try:
            parsed = (
                datetime.fromisoformat(text.replace("Z", "+00:00")).date()
                if "T" in text or " " in text
                else date.fromisoformat(text)
            )
        except ValueError as exc:
            raise ValueError(
                f"Alert period must be a governed YYYY-MM or ISO date: {value!r}"
            ) from exc
        year, month = parsed.year, parsed.month
    if not 1 <= month <= 12:
        raise ValueError(f"Alert period must be a governed YYYY-MM value: {value!r}")
    return year, month


def _add_months(value: str, months: int) -> str:
    year, month = _period_key(value)
    ordinal = year * 12 + month - 1 + max(0, int(months))
    return f"{ordinal // 12:04d}-{ordinal % 12 + 1:02d}-01"


class AlertLifecycle:
    """Persist one durable workflow object for every governed alert fingerprint."""

    def __init__(
        self,
        store: WorkflowStore,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self.clock = clock or (lambda: datetime.now(UTC))

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _latest_evidence(
        candidate: Mapping[str, Any],
        *,
        run_id: str,
        configuration_hash: str,
        dataset_hash: str | None,
        observation_key: str,
    ) -> dict[str, Any]:
        return {
            "run_id": run_id,
            "configuration_hash": configuration_hash,
            "dataset_hash": dataset_hash,
            "period": str(candidate["generation_timestamp"]),
            "comparison_period": candidate.get("comparison_period"),
            "data_quality_status": str(candidate["data_quality_status"]),
            "current_value": candidate.get("current_value"),
            "baseline_value": candidate.get("baseline_value"),
            "absolute_movement": candidate.get("absolute_movement"),
            "relative_movement": candidate.get("relative_movement"),
            "denominator": float(candidate.get("denominator") or 0),
            "observation_key": observation_key,
        }

    def _initial_state(
        self,
        candidate: Mapping[str, Any],
        *,
        run_id: str,
        configuration_hash: str,
        dataset_hash: str | None,
        evaluation_period: str,
    ) -> dict[str, Any]:
        now = self._now()
        period = str(candidate["generation_timestamp"])
        observation_key = alert_observation_key(
            str(candidate["fingerprint"]), run_id, period
        )
        sla_hours = int(candidate.get("sla_hours") or 0)
        if sla_hours <= 0:
            raise ValueError(f"Alert {candidate['alert_rule_id']} has no governed SLA")
        return {
            **dict(candidate),
            "status": "NEW",
            "acknowledged_by": None,
            "acknowledged_at": None,
            "acknowledgement_note": None,
            "sla_hours": sla_hours,
            "sla_due_at": (now + timedelta(hours=sla_hours)).isoformat(),
            "recurrence_count": 0,
            "first_observed": period,
            "last_observed": period,
            "first_observed_at": now.isoformat(),
            "last_observed_at": now.isoformat(),
            "last_evaluated_period": evaluation_period,
            "observation_key": observation_key,
            "observation_keys": [observation_key],
            "cooldown_periods": int(candidate.get("cooldown_periods") or 0),
            "cooldown_until_period": None,
            "suppression_active": False,
            "suppression_reason": None,
            "suppressed_by": None,
            "suppressed_at": None,
            "suppression_until_period": None,
            "resolution_reason": None,
            "resolved_by": None,
            "resolved_at": None,
            "reopen_history": [],
            "related_investigation": None,
            "latest_evidence": self._latest_evidence(
                candidate,
                run_id=run_id,
                configuration_hash=configuration_hash,
                dataset_hash=dataset_hash,
                observation_key=observation_key,
            ),
            "condition_active": True,
        }

    @staticmethod
    def _require_scope(
        record: Mapping[str, Any],
        selected_scope: Mapping[str, Any] | None,
    ) -> None:
        if selected_scope is None:
            return
        state = dict(record["state"])
        if state.get("selected_scope") != normalise_selected_scope(selected_scope):
            raise ObjectNotFound(
                f"alert/{record['external_id']} not found in the selected scope"
            )

    def _view(self, record: Mapping[str, Any]) -> dict[str, Any]:
        alert_id = str(record["external_id"])
        state = dict(record["state"])
        events = self.store.audit_events("alert", alert_id)
        chain_valid = self.store.verify_audit_chain("alert", alert_id)
        status = str(state["status"])
        return {
            **state,
            "alert_fingerprint": state["fingerprint"],
            "alert_rule_name": state["alert_name"],
            "acknowledgement": {
                "acknowledged": state.get("acknowledged_at") is not None,
                "by": state.get("acknowledged_by"),
                "at": state.get("acknowledged_at"),
                "note": state.get("acknowledgement_note"),
            },
            "sla": {
                "hours": state["sla_hours"],
                "due_at": state["sla_due_at"],
            },
            "first_observed_period": state["first_observed"],
            "last_observed_period": state["last_observed"],
            "last_observation_key": state["observation_key"],
            "cooldown": {
                "periods": state.get("cooldown_periods", 0),
                "until_period": state.get("cooldown_until_period"),
            },
            "suppression": {
                "active": bool(state.get("suppression_active")),
                "reason": state.get("suppression_reason"),
                "by": state.get("suppressed_by"),
                "at": state.get("suppressed_at"),
                "until_period": state.get("suppression_until_period"),
            },
            "resolution": {
                "reason": state.get("resolution_reason"),
                "by": state.get("resolved_by"),
                "at": state.get("resolved_at"),
            },
            "version": int(record["version"]),
            "created_at": record.get("created_at"),
            "modified_at": record.get("modified_at"),
            "allowed_transitions": list(ALLOWED_TRANSITIONS[status]),
            "can_acknowledge": status == "NEW",
            "condition_active": bool(state.get("condition_active")),
            "workflow_active": status in WORKFLOW_ACTIVE_STATUSES,
            "audit_events": events,
            "audit_integrity": {
                "status": "PASS" if chain_valid else "FAIL",
                "chain_valid": chain_valid,
                "event_count": len(events),
                "head_hash": events[-1]["event_hash"] if events else None,
            },
        }

    def get(
        self,
        alert_id: str,
        *,
        selected_scope: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        record = self.store.get("alert", alert_id)
        self._require_scope(record, selected_scope)
        return self._view(record)

    def audit(
        self,
        alert_id: str,
        *,
        selected_scope: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        alert = self.get(alert_id, selected_scope=selected_scope)
        return {
            "alert_id": alert_id,
            "fingerprint": alert["fingerprint"],
            "version": alert["version"],
            "audit_events": alert["audit_events"],
            "audit_integrity": alert["audit_integrity"],
        }

    def list(self) -> list[dict[str, Any]]:
        rows = [self._view(record) for record in self.store.list("alert")]
        return sorted(
            rows,
            key=lambda row: (
                not bool(row["workflow_active"]),
                -SEVERITY_ORDER[str(row["severity"])],
                str(row["last_observed"]),
                str(row["alert_id"]),
            ),
        )

    @staticmethod
    def _candidate_updates(candidate: Mapping[str, Any]) -> dict[str, Any]:
        return {
            key: candidate.get(key)
            for key in (
                "alert_name",
                "metric_id",
                "comparison_method",
                "current_value",
                "baseline_value",
                "absolute_movement",
                "relative_movement",
                "threshold",
                "segment",
                "segment_or_basket",
                "selected_scope",
                "denominator",
                "generation_timestamp",
                "comparison_period",
                "data_quality_status",
                "rule_version",
                "recommended_investigation",
                "noise_controls",
            )
        }

    def _reconcile_candidate(
        self,
        candidate: Mapping[str, Any],
        *,
        run_id: str,
        configuration_hash: str,
        dataset_hash: str | None,
        evaluation_period: str,
        actor: str,
    ) -> dict[str, Any]:
        alert_id = str(candidate["alert_id"])
        period = str(candidate["generation_timestamp"])
        observation_key = alert_observation_key(
            str(candidate["fingerprint"]), run_id, period
        )
        for _ in range(4):
            try:
                record = self.store.get("alert", alert_id)
            except ObjectNotFound:
                state = self._initial_state(
                    candidate,
                    run_id=run_id,
                    configuration_hash=configuration_hash,
                    dataset_hash=dataset_hash,
                    evaluation_period=evaluation_period,
                )
                try:
                    created = self.store.create(
                        "alert",
                        alert_id,
                        state,
                        actor=actor,
                        domain_events=[
                            {
                                "event_type": "ALERT_CREATED",
                                "payload": {
                                    "fingerprint": candidate["fingerprint"],
                                    "observation_key": observation_key,
                                    "period": period,
                                },
                            }
                        ],
                    )
                    return self._view(created)
                except DuplicateObject:
                    continue

            state = dict(record["state"])
            if state.get("fingerprint") != candidate.get("fingerprint"):
                raise RuntimeError(f"Alert ID collision for {alert_id}")
            if observation_key in state.get("observation_keys", []):
                return self._view(record)
            if _period_key(period) < _period_key(str(state["last_observed"])):
                return self._view(record)

            now = self._now()
            current_severity = str(state["severity"])
            candidate_severity = str(candidate["severity"])
            if current_severity not in SEVERITY_ORDER or candidate_severity not in SEVERITY_ORDER:
                raise ValueError("Alert severity must be Critical, Adverse, or Watch")
            severity = (
                candidate_severity
                if SEVERITY_ORDER[candidate_severity] > SEVERITY_ORDER[current_severity]
                else current_severity
            )
            events: list[dict[str, Any]] = [
                {
                    "event_type": "ALERT_REPEATED",
                    "payload": {
                        "observation_key": observation_key,
                        "period": period,
                        "run_id": run_id,
                    },
                }
            ]
            if severity != current_severity:
                events.append(
                    {
                        "event_type": "ALERT_ESCALATED",
                        "payload": {
                            "from_severity": current_severity,
                            "to_severity": severity,
                        },
                    }
                )

            status = str(state["status"])
            changes: dict[str, Any] = {
                **self._candidate_updates(candidate),
                "severity": severity,
                "recurrence_count": int(state.get("recurrence_count", 0)) + 1,
                "last_observed": period,
                "last_observed_at": now.isoformat(),
                "last_evaluated_period": evaluation_period,
                "observation_key": observation_key,
                "observation_keys": [*state.get("observation_keys", []), observation_key],
                "latest_evidence": self._latest_evidence(
                    candidate,
                    run_id=run_id,
                    configuration_hash=configuration_hash,
                    dataset_hash=dataset_hash,
                    observation_key=observation_key,
                ),
                "condition_active": True,
            }
            if status == "RESOLVED":
                cooldown_until = state.get("cooldown_until_period")
                if cooldown_until and _period_key(period) <= _period_key(str(cooldown_until)):
                    changes.update(
                        {
                            "status": "SUPPRESSED",
                            "suppression_active": True,
                            "suppression_reason": "Configured post-resolution cooldown",
                            "suppressed_by": "alert.engine",
                            "suppressed_at": now.isoformat(),
                            "suppression_until_period": cooldown_until,
                        }
                    )
                    events.append(
                        {
                            "event_type": "ALERT_SUPPRESSED",
                            "payload": {
                                "reason": "configured_post_resolution_cooldown",
                                "until_period": cooldown_until,
                            },
                        }
                    )
                else:
                    self._apply_reopen(changes, state, period, run_id, observation_key, now)
                    events.append(
                        {
                            "event_type": "ALERT_REOPENED",
                            "payload": {"prior_status": status, "period": period},
                        }
                    )
            elif status in {"SUPPRESSED", "CLOSED_AS_NOISE"}:
                suppression_until = state.get("suppression_until_period")
                if suppression_until is not None and _period_key(period) > _period_key(
                    str(suppression_until)
                ):
                    self._apply_reopen(changes, state, period, run_id, observation_key, now)
                    events.append(
                        {
                            "event_type": "ALERT_REOPENED",
                            "payload": {"prior_status": status, "period": period},
                        }
                    )
            try:
                updated = self.store.update(
                    "alert",
                    alert_id,
                    changes,
                    expected_version=int(record["version"]),
                    actor=actor,
                    domain_events=events,
                )
                return self._view(updated)
            except ConcurrencyConflict:
                continue
        raise ConcurrencyConflict(f"Could not reconcile alert {alert_id} after retries")

    @staticmethod
    def _apply_reopen(
        changes: dict[str, Any],
        state: Mapping[str, Any],
        period: str,
        run_id: str,
        observation_key: str,
        now: datetime,
    ) -> None:
        prior_status = str(state["status"])
        changes.update(
            {
                "status": "NEW",
                "acknowledged_by": None,
                "acknowledged_at": None,
                "acknowledgement_note": None,
                "suppression_active": False,
                "suppression_reason": None,
                "suppressed_by": None,
                "suppressed_at": None,
                "suppression_until_period": None,
                "cooldown_until_period": None,
                "reopen_history": [
                    *state.get("reopen_history", []),
                    {
                        "reopened_at": now.isoformat(),
                        "run_id": run_id,
                        "period": period,
                        "prior_status": prior_status,
                        "cooldown_until_period": state.get("cooldown_until_period"),
                        "reason": "Matching condition recurred after the governed suppression window",
                        "observation_key": observation_key,
                    },
                ],
                "sla_due_at": (
                    now + timedelta(hours=int(state.get("sla_hours") or 0))
                ).isoformat(),
            }
        )

    def reconcile(
        self,
        candidates: Iterable[Mapping[str, Any]],
        *,
        run_id: str,
        configuration_hash: str,
        dataset_hash: str | None,
        evaluation_period: str,
        selected_scope: Mapping[str, Any] | None,
        actor: str = "alert.engine",
    ) -> list[dict[str, Any]]:
        """Create/recur breached conditions and retain non-breached lifecycle history."""

        candidate_rows = [dict(candidate) for candidate in candidates]
        normalised_scope = normalise_selected_scope(selected_scope)
        _period_key(evaluation_period)
        for candidate in candidate_rows:
            if normalise_selected_scope(candidate.get("selected_scope")) != normalised_scope:
                raise ValueError(
                    "Alert candidate scope does not match the requested analytical scope"
                )
            _period_key(str(candidate.get("generation_timestamp") or ""))
            comparison_period = candidate.get("comparison_period")
            if comparison_period is not None:
                _period_key(str(comparison_period))
        observed_ids: set[str] = set()
        for candidate in candidate_rows:
            observed_ids.add(str(candidate["alert_id"]))
            self._reconcile_candidate(
                candidate,
                run_id=run_id,
                configuration_hash=configuration_hash,
                dataset_hash=dataset_hash,
                evaluation_period=evaluation_period,
                actor=actor,
            )

        for record in self.store.list("alert"):
            state = dict(record["state"])
            if state.get("selected_scope") != normalised_scope:
                continue
            if str(record["external_id"]) in observed_ids or not state.get("condition_active"):
                continue
            if _period_key(evaluation_period) < _period_key(
                str(state.get("last_evaluated_period") or state["last_observed"])
            ):
                continue
            try:
                self.store.update(
                    "alert",
                    str(record["external_id"]),
                    {
                        "condition_active": False,
                        "last_evaluated_period": evaluation_period,
                    },
                    expected_version=int(record["version"]),
                    actor=actor,
                    domain_events=[
                        {
                            "event_type": "ALERT_CONDITION_CLEARED",
                            "payload": {"evaluation_period": evaluation_period},
                        }
                    ],
                )
            except ConcurrencyConflict:
                continue
        return [
            row
            for row in self.list()
            if row.get("selected_scope") == normalised_scope
        ]

    def acknowledge(
        self,
        alert_id: str,
        *,
        expected_version: int,
        note: str,
        actor: str,
        selected_scope: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not note.strip():
            raise ValueError("Alert acknowledgement requires a note")
        current = self.store.get("alert", alert_id)
        self._require_scope(current, selected_scope)
        state = dict(current["state"])
        if int(current["version"]) != expected_version:
            raise ConcurrencyConflict(f"Expected alert/{alert_id} version {expected_version}")
        if "ACKNOWLEDGED" not in ALLOWED_TRANSITIONS[str(state["status"])]:
            raise ValueError(f"Alert status {state['status']} cannot be acknowledged")
        now = self._now().isoformat()
        updated = self.store.update(
            "alert",
            alert_id,
            {
                "status": "ACKNOWLEDGED",
                "acknowledged_by": actor,
                "acknowledged_at": now,
                "acknowledgement_note": note.strip(),
            },
            expected_version=expected_version,
            actor=actor,
            domain_events=[
                {
                    "event_type": "ALERT_ACKNOWLEDGED",
                    "payload": {"note": note.strip()},
                }
            ],
        )
        return self._view(updated)

    def link_investigation(
        self,
        alert_id: str,
        *,
        expected_version: int,
        investigation_id: str,
        actor: str,
        selected_scope: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Link an existing governed investigation without inventing a status change."""

        if not investigation_id.strip():
            raise ValueError("A governed investigation identifier is required")
        current = self.store.get("alert", alert_id)
        self._require_scope(current, selected_scope)
        if int(current["version"]) != expected_version:
            raise ConcurrencyConflict(f"Expected alert/{alert_id} version {expected_version}")
        state = dict(current["state"])
        if state.get("related_investigation") == investigation_id.strip():
            return self._view(current)
        if str(state["status"]) not in WORKFLOW_ACTIVE_STATUSES:
            raise ValueError("Only a workflow-active alert can link an investigation")
        updated = self.store.update(
            "alert",
            alert_id,
            {"related_investigation": investigation_id.strip()},
            expected_version=expected_version,
            actor=actor,
            domain_events=[
                {
                    "event_type": "ALERT_INVESTIGATION_LINKED",
                    "payload": {"investigation_id": investigation_id.strip()},
                }
            ],
        )
        return self._view(updated)

    def transition(
        self,
        alert_id: str,
        *,
        expected_version: int,
        target_status: str,
        reason: str,
        actor: str,
        owner: str | None = None,
        related_investigation: str | None = None,
        suppression_until_period: str | None = None,
        selected_scope: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if target_status not in ALERT_STATUSES or target_status == "NEW":
            raise ValueError(f"Unsupported alert target status: {target_status}")
        if not reason.strip():
            raise ValueError("Alert transition requires a reason")
        if target_status == "ACKNOWLEDGED":
            return self.acknowledge(
                alert_id,
                expected_version=expected_version,
                note=reason,
                actor=actor,
                selected_scope=selected_scope,
            )
        current = self.store.get("alert", alert_id)
        self._require_scope(current, selected_scope)
        state = dict(current["state"])
        if int(current["version"]) != expected_version:
            raise ConcurrencyConflict(f"Expected alert/{alert_id} version {expected_version}")
        status = str(state["status"])
        if target_status not in ALLOWED_TRANSITIONS[status]:
            raise ValueError(f"Alert transition {status} -> {target_status} is not allowed")
        if suppression_until_period is not None and _period_key(
            suppression_until_period
        ) < _period_key(str(state["last_observed"])):
            raise ValueError("suppression_until_period cannot precede the latest observation")

        now = self._now()
        changes: dict[str, Any] = {"status": target_status}
        if owner is not None:
            changes["owner"] = owner.strip()
        if related_investigation is not None:
            changes["related_investigation"] = related_investigation.strip()
        event_type = "ALERT_STATUS_TRANSITIONED"
        if target_status == "RESOLVED":
            cooldown_until = _add_months(
                str(state["last_observed"]), int(state.get("cooldown_periods") or 0)
            )
            changes.update(
                {
                    "resolution_reason": reason.strip(),
                    "resolved_by": actor,
                    "resolved_at": now.isoformat(),
                    "cooldown_until_period": cooldown_until,
                    "suppression_active": False,
                }
            )
            event_type = "ALERT_RESOLVED"
        elif target_status in {"SUPPRESSED", "CLOSED_AS_NOISE"}:
            changes.update(
                {
                    "suppression_active": True,
                    "suppression_reason": reason.strip(),
                    "suppressed_by": actor,
                    "suppressed_at": now.isoformat(),
                    "suppression_until_period": suppression_until_period,
                }
            )
            event_type = "ALERT_SUPPRESSED"
        updated = self.store.update(
            "alert",
            alert_id,
            changes,
            expected_version=expected_version,
            actor=actor,
            domain_events=[
                {
                    "event_type": event_type,
                    "payload": {
                        "from_status": status,
                        "to_status": target_status,
                        "reason": reason.strip(),
                        "owner": owner,
                        "related_investigation": related_investigation,
                        "suppression_until_period": suppression_until_period,
                    },
                }
            ],
        )
        return self._view(updated)
