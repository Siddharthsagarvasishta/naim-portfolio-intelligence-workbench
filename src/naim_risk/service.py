"""In-process analytical service shared by FastAPI endpoints."""

from __future__ import annotations

import json
import math
import threading
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd

from naim_risk.alerts import AlertLifecycle, build_alert_candidate, generate_alerts
from naim_risk.baskets import combine_memberships, impact_preview
from naim_risk.capacity import capacity_summary, run_capacity_scenario
from naim_risk.commentary import CommentaryEvidence, DeterministicTemplateProvider
from naim_risk.config import NaimConfig, load_config
from naim_risk.cross_domain import (
    finance_analytics,
    membership_analytics,
    partner_analytics,
    vendor_analytics,
)
from naim_risk.exports import generate_excel_export, generate_powerbi_package, list_exports
from naim_risk.forecasting import list_scenarios, run_scenario
from naim_risk.governance import calculate_population_drift
from naim_risk.metrics import (
    apply_filters,
    calculate_period_kpis,
    calculate_roll_rates,
    calculate_trends,
    enrich_performance,
)
from naim_risk.metrics.governance import bind_runtime_evidence
from naim_risk.network import build_dependency_network, network_impact
from naim_risk.peer import match_peer_analogues
from naim_risk.pipeline import run_pipeline
from naim_risk.ratings import rate_memberships, rate_partners, rate_vendors
from naim_risk.root_cause import root_cause_finding
from naim_risk.runtime_modes import DataMode, SourceContext
from naim_risk.segmentation import business_rule_segments, statistical_segments
from naim_risk.strategies import compare_strategies
from naim_risk.types import PipelineData
from naim_risk.vintage import calculate_vintages
from naim_risk.workflow import (
    ConcurrencyConflict,
    DuplicateObject,
    ObjectNotFound,
    WorkflowStore,
)


def json_safe(value: Any) -> Any:
    """Convert NumPy/Pandas values to strict JSON-compatible Python values."""

    if value is None:
        return None
    if isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): json_safe(nested) for key, nested in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(nested) for nested in value]
    if pd.isna(value):
        return None
    return str(value)


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class WorkbenchService:
    """Governed analytical facade; no endpoint recalculates formulas independently."""

    def __init__(
        self,
        config: NaimConfig | None = None,
        data: PipelineData | None = None,
        workflow_store: WorkflowStore | None = None,
    ) -> None:
        self.config = config or load_config("test")
        self.data = data or run_pipeline(
            self.config,
            persist=self.config.profile.name != "test",
        )
        if not self.data.validation.publication_allowed:
            raise RuntimeError("Critical data-quality failures block analytical publication")
        self.tables = self.data.tables
        self._cache: dict[str, Any] = {}
        self._lock = threading.RLock()
        self.workflow_store = workflow_store or self._default_workflow_store()
        self.alert_lifecycle = AlertLifecycle(self.workflow_store)

    def _default_workflow_store(self) -> WorkflowStore:
        if self.config.profile.name == "test":
            token = uuid4().hex
            database_url = (
                f"sqlite+pysqlite:///file:naim-workflow-{token}?mode=memory&cache=shared&uri=true"
            )
        else:
            database = (self.config.data_root / "state" / "naim_workflow.sqlite3").resolve()
            database_url = f"sqlite+pysqlite:///{database}"
        return WorkflowStore(database_url)

    @staticmethod
    def _workflow_actor(
        payload: Mapping[str, Any] | None = None,
        explicit: str | None = None,
    ) -> str:
        payload = payload or {}
        return str(explicit or payload.get("actor") or "workbench.service")

    @staticmethod
    def _expected_version(
        payload: Mapping[str, Any],
        current_version: int,
        explicit: int | None,
    ) -> int:
        embedded = payload.get("expected_version")
        if embedded is not None and explicit is not None and int(embedded) != int(explicit):
            raise ValueError("Conflicting expected_version values")
        selected = explicit if explicit is not None else embedded
        return int(current_version if selected is None else selected)

    @staticmethod
    def _workflow_view(record: Mapping[str, Any]) -> dict[str, Any]:
        state = dict(record["state"])
        state["version"] = int(record["version"])
        state["approval_state"] = str(record["approval_state"])
        state["approved_flag"] = record["approval_state"] == "APPROVED"
        state.setdefault("created_timestamp", record.get("created_at"))
        state["modified_timestamp"] = record.get("modified_at")
        return json_safe(state)

    def _create_unique_workflow(
        self,
        object_type: str,
        prefix: str,
        state: Mapping[str, Any],
        *,
        actor: str,
        approval_state: str = "DRAFT",
        id_field: str | None = None,
    ) -> dict[str, Any]:
        for _ in range(10):
            external_id = f"{prefix}-{uuid4().hex[:16].upper()}"
            persisted_state = dict(state)
            if id_field is not None:
                persisted_state[id_field] = external_id
            try:
                return self.workflow_store.create(
                    object_type,
                    external_id,
                    persisted_state,
                    actor=actor,
                    approval_state=approval_state,
                )
            except DuplicateObject:
                continue
        raise RuntimeError(f"Unable to allocate a unique {object_type} identifier")

    def _create_or_get_workflow(
        self,
        object_type: str,
        external_id: str,
        state: Mapping[str, Any],
        *,
        actor: str,
        approval_state: str = "DRAFT",
        id_field: str | None = None,
    ) -> dict[str, Any]:
        persisted_state = dict(state)
        if id_field is not None:
            persisted_state[id_field] = external_id
        try:
            return self.workflow_store.create(
                object_type,
                external_id,
                persisted_state,
                actor=actor,
                approval_state=approval_state,
            )
        except DuplicateObject:
            try:
                return self.workflow_store.get(object_type, external_id)
            except ObjectNotFound:
                return self._create_unique_workflow(
                    object_type,
                    external_id,
                    persisted_state,
                    actor=actor,
                    approval_state=approval_state,
                    id_field=id_field,
                )

    def _persist_baseline_override(
        self,
        object_type: str,
        external_id: str,
        state: Mapping[str, Any],
        *,
        actor: str,
    ) -> dict[str, Any]:
        try:
            return self.workflow_store.get(object_type, external_id)
        except ObjectNotFound:
            clean = json_safe(
                {
                    key: value
                    for key, value in state.items()
                    if key
                    not in {
                        "version",
                        "approval_state",
                        "approved_flag",
                        "audit",
                        "scope_metadata",
                    }
                }
            )
            approval_state = "APPROVED" if state.get("approved_flag") else "DRAFT"
            return self._create_or_get_workflow(
                object_type,
                external_id,
                clean,
                actor=actor,
                approval_state=approval_state,
            )

    def _stable_record_id(self, prefix: str, payload: Mapping[str, Any]) -> str:
        canonical = json.dumps(
            json_safe(
                {
                    "pipeline_run_id": self.data.run_id,
                    "configuration_hash": self.config.config_hash,
                    "payload": dict(payload),
                }
            ),
            sort_keys=True,
            separators=(",", ":"),
        )
        return f"{prefix}-{sha256(canonical.encode()).hexdigest()[:20].upper()}"

    @property
    def performance(self) -> pd.DataFrame:
        return self.tables["monthly_account_performance"]

    @property
    def master(self) -> pd.DataFrame:
        return self.tables["customer_account_master"]

    def _cached(self, key: str, builder: Any) -> Any:
        with self._lock:
            if key not in self._cache:
                self._cache[key] = builder()
            return self._cache[key]

    def metadata(self) -> dict[str, Any]:
        return json_safe(
            {
                "product": "nAIM Portfolio Intelligence Workbench",
                "pronunciation": "name",
                "aim_expansion": "All Is Mine",
                "tagline": "Name the movement. Own the evidence.",
                "version": "0.1.0",
                "run_id": self.data.run_id,
                "configuration_hash": self.config.config_hash,
                "profile": self.config.profile.name,
                "synthetic": True,
                "synthetic_label": self.config.synthetic_label,
                "as_of": self.data.manifest["maximum_data_date"],
                "minimum_date": self.data.manifest["minimum_data_date"],
                "quality_status": self.data.validation.status,
                "publication_allowed": self.data.validation.publication_allowed,
                "row_counts": self.data.manifest["row_counts"],
                "metric_registry_version": self.config.metric_registry_version,
                "metric_calculation_version": self.config.metric_calculation_version,
                "assumption_version": self.config.assumption_version,
                "alert_rule_version": self.config.alert_rule_version,
                "causal_notice": "Observational findings are associational unless a valid randomised design is explicitly identified.",
                "decision_notice": "Analytical recommendations require human review and approval.",
            }
        )

    def _bounded_metadata(self, period: str | None = None) -> dict[str, Any]:
        metadata = self.metadata()
        maximum = pd.Timestamp(self.performance["month"].max()).to_period("M").to_timestamp()
        analytical_period = (
            maximum if period is None else pd.Timestamp(period).to_period("M").to_timestamp()
        )
        metadata["analytical_as_of"] = str(analytical_period.date())
        metadata["maximum_source_month_used"] = str(min(analytical_period, maximum).date())
        metadata["future_periods_excluded"] = bool(analytical_period < maximum)
        metadata["source_period_scope"] = "through_reporting_month"
        return metadata

    @staticmethod
    def _bound_frame(
        frame: pd.DataFrame,
        period: str | None,
        *,
        date_column: str = "month",
    ) -> pd.DataFrame:
        if period is None or date_column not in frame:
            return frame
        cutoff = pd.Timestamp(period).to_period("M").to_timestamp()
        dates = pd.to_datetime(frame[date_column]).dt.to_period("M").dt.to_timestamp()
        return frame[dates <= cutoff].copy()

    def _master_as_of(self, period: str | None) -> pd.DataFrame:
        master = self.master.copy()
        if period is None:
            return master
        cutoff = pd.Timestamp(period).normalize()
        history = self.tables["customer_membership_history"].copy()
        starts = pd.to_datetime(history["effective_start_date"])
        ends = pd.to_datetime(history["effective_end_date"])
        active = history[(starts <= cutoff) & (ends.isna() | (ends >= cutoff))].copy()
        if active.empty:
            return master
        active["_effective_start"] = pd.to_datetime(active["effective_start_date"])
        membership = (
            active.sort_values(["account_id", "_effective_start"])
            .drop_duplicates("account_id", keep="last")
            .set_index("account_id")["membership_tier_id"]
        )
        master["membership_tier_id"] = (
            master["account_id"].map(membership).fillna(master["membership_tier_id"])
        )
        return master

    def filters(self) -> dict[str, Any]:
        enriched = enrich_performance(self.performance, self.master)
        fields = [
            "month",
            "product_type",
            "customer_segment",
            "acquisition_channel",
            "geography",
            "original_risk_band",
            "strategy_version",
            "model_version",
            "partner_id",
            "vendor_id",
            "membership_tier_id",
        ]
        values = {}
        for field in fields:
            entries = enriched[field].dropna().unique().tolist()
            if field == "month":
                entries = [str(pd.Timestamp(item).date()) for item in sorted(entries)]
            else:
                entries = sorted(str(item) for item in entries)
            values[field] = entries
        return {
            "data": values,
            "filter_syntax": "Exact scalar or repeated multi-select values",
            "supported_filter_metadata": [
                {
                    "filter": "reporting_month",
                    "supported": True,
                    "endpoints": [
                        "command-centre",
                        "kpis",
                        "roll-rates",
                        "root-cause",
                    ],
                },
                *[
                    {
                        "filter": field,
                        "supported": True,
                        "endpoints": [
                            "command-centre",
                            "kpis",
                            "trends",
                            "vintages",
                            "roll-rates",
                            "strategy-comparison",
                            "segments",
                            "root-cause",
                            "alerts",
                        ],
                    }
                    for field in fields
                    if field != "month"
                ],
                {
                    "filter": "comparison",
                    "supported": False,
                    "reason": (
                        "The analytical API currently uses the immediately prior "
                        "available month as the governed comparison."
                    ),
                },
                {
                    "filter": "vintage",
                    "supported": False,
                    "reason": (
                        "Vintage is an analytical output dimension in this slice, "
                        "not an API query filter."
                    ),
                },
            ],
        }

    def kpis(
        self,
        *,
        period: str | None = None,
        filters: Mapping[str, Any] | None = None,
        source_context: SourceContext | Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        key = f"kpis:{period}:{json.dumps(filters or {}, sort_keys=True)}"
        rows = self._cached(
            key,
            lambda: calculate_period_kpis(
                self.performance,
                self.master,
                period=period,
                assumptions=self.config.scenarios["Baseline"],
                metric_registry=self.config.metrics,
                filters=filters,
            ),
        )
        evidenced_rows = bind_runtime_evidence(
            rows,
            context=source_context,
            manifest=self.data.manifest,
            configuration_hash=self.config.config_hash,
            run_id=self.data.run_id,
            filters=filters,
        )
        return json_safe({"data": evidenced_rows, "metadata": self._bounded_metadata(period)})

    def trends(
        self,
        *,
        period: str | None = None,
        filters: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        key = f"trends:{period}:{json.dumps(filters or {}, sort_keys=True)}"
        rows = self._cached(
            key,
            lambda: calculate_trends(
                self.performance,
                self.master,
                assumptions=self.config.scenarios["Baseline"],
                metric_registry=self.config.metrics,
                filters=filters,
                through_period=period,
            ),
        )
        return json_safe({"data": rows, "metadata": self._bounded_metadata(period)})

    def alerts(
        self,
        *,
        period: str | None = None,
        filters: Mapping[str, Any] | None = None,
        source_context: SourceContext | Mapping[str, Any] | None = None,
        persist: bool = True,
        persist_historical: bool = False,
    ) -> dict[str, Any]:
        metadata = self._bounded_metadata(period)
        evaluation_period = str(metadata["maximum_source_month_used"])
        latest_period = str(self._bounded_metadata(None)["maximum_source_month_used"])
        persist_durable_workflow = persist and (
            evaluation_period == latest_period or persist_historical
        )
        trend_rows = self.trends(period=period, filters=filters)["data"]
        governed_periods = sorted({str(row["month"]) for row in trend_rows})
        comparison_period = (
            governed_periods[-2] if len(governed_periods) > 1 else None
        )
        candidates = generate_alerts(
            trend_rows,
            self.config.alert_rules,
            quality_status=self.data.validation.status,
            completeness=1.0
            - sum(self.data.manifest["rejected_row_counts"].values())
            / max(sum(self.data.manifest["row_counts"].values()), 1),
            selected_scope=filters,
            rule_version=self.config.alert_rule_version,
            reporting_period=evaluation_period,
            reporting_comparison_period=comparison_period,
        )
        kpi_rows = self.kpis(
            period=period,
            filters=filters,
            source_context=source_context,
        )["data"]
        runtime_evidence = dict(kpi_rows[0]["runtime_evidence"] if kpi_rows else {})
        root = self.root_cause(period=period, filters=filters).get("finding")
        if (
            root
            and root.get("contribution_share") is not None
            and root["contribution_share"] > 0.40
            and root["observed_change_bps"] > 0
        ):
            concentration_rule = next(
                rule
                for rule in self.config.alert_rules
                if rule["alert_rule_id"] == "LOSS_CONCENTRATION"
            )
            loss_kpi = next(
                (
                    row
                    for row in kpi_rows
                    if row["metric_id"] == "ANNUALISED_NET_LOSS_RATE"
                ),
                {},
            )
            candidates.append(
                build_alert_candidate(
                    concentration_rule,
                    current_value=float(root["contribution_share"]),
                    baseline_value=float(concentration_rule["absolute_threshold"]),
                    denominator=float(loss_kpi.get("denominator") or 0),
                    period=evaluation_period,
                    comparison_period=comparison_period,
                    quality_status=self.data.validation.status,
                    selected_scope=filters,
                    rule_version=self.config.alert_rule_version,
                    segment_or_basket=(
                        f"{root.get('primary_dimension')}={root.get('primary_driver')}"
                    ),
                    recommended_investigation=root["recommended_investigation"],
                )
            )
        if persist_durable_workflow:
            rows = self.alert_lifecycle.reconcile(
                candidates,
                run_id=str(runtime_evidence.get("run_id") or self.data.run_id),
                configuration_hash=str(
                    runtime_evidence.get("configuration_hash") or self.config.config_hash
                ),
                dataset_hash=runtime_evidence.get("dataset_hash"),
                evaluation_period=evaluation_period,
                selected_scope=filters,
            )
        else:
            rows = [
                {
                    **candidate,
                    "durable": False,
                    "workflow_scope": "historical_evaluation_not_persisted",
                }
                for candidate in candidates
            ]
        return json_safe(
            {
                "data": rows,
                "metadata": {
                    **metadata,
                    "alert_workflow_scope": (
                        "current_durable_workflow"
                        if evaluation_period == latest_period
                        else "approved_demo_historical_durable_workflow"
                        if persist_durable_workflow
                        else "historical_evaluation_not_persisted"
                    ),
                },
            }
        )

    def alert_detail(
        self,
        alert_id: str,
        *,
        filters: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return one durable alert with server-computed workflow controls."""

        return json_safe(
            self.alert_lifecycle.get(alert_id, selected_scope=filters)
        )

    def alert_audit(
        self,
        alert_id: str,
        *,
        filters: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return the independently verifiable hash-chained alert audit."""

        return json_safe(
            self.alert_lifecycle.audit(alert_id, selected_scope=filters)
        )

    def acknowledge_alert(
        self,
        alert_id: str,
        *,
        expected_version: int,
        note: str,
        actor: str,
        filters: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return json_safe(
            self.alert_lifecycle.acknowledge(
                alert_id,
                expected_version=expected_version,
                note=note,
                actor=actor,
                selected_scope=filters,
            )
        )

    def transition_alert(
        self,
        alert_id: str,
        payload: Mapping[str, Any],
        *,
        actor: str,
        filters: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return json_safe(
            self.alert_lifecycle.transition(
                alert_id,
                expected_version=int(payload["expected_version"]),
                target_status=str(payload["target_status"]),
                reason=str(payload["reason"]),
                actor=actor,
                owner=payload.get("owner"),
                related_investigation=payload.get("related_investigation"),
                suppression_until_period=payload.get("suppression_until_period"),
                selected_scope=filters,
            )
        )

    def start_alert_investigation(
        self,
        alert_id: str,
        payload: Mapping[str, Any],
        *,
        actor: str,
        filters: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create or reuse one open investigation and bind it to the alert."""

        reason = str(payload.get("reason") or "").strip()
        if not reason:
            raise ValueError("Starting an investigation requires a reason")
        expected_version = int(payload["expected_version"])
        alert = self.alert_lifecycle.get(alert_id, selected_scope=filters)
        if int(alert["version"]) != expected_version:
            raise ConcurrencyConflict(
                f"Expected alert/{alert_id} version {expected_version}"
            )
        owner = str(payload.get("owner") or alert.get("owner") or "Unassigned").strip()
        terminal_statuses = {"resolved", "closed", "closed as noise", "closed_as_noise"}
        matching: list[dict[str, Any]] = []
        for record in self.workflow_store.list("investigation"):
            state = dict(record["state"])
            if state.get("alert_id") != alert_id:
                continue
            if str(state.get("status") or "").strip().lower() in terminal_statuses:
                continue
            matching.append(record)

        reused = bool(matching)
        if matching:
            investigation_record = matching[0]
            investigation = self._workflow_view(investigation_record)
        else:
            recommended = alert.get("recommended_investigation")
            if isinstance(recommended, list):
                business_question = " ".join(str(item) for item in recommended if item)
            else:
                business_question = str(recommended or "").strip()
            if not business_question:
                business_question = (
                    f"Investigate {alert['alert_name']} for {alert.get('segment') or 'Portfolio'}."
                )
            evidence = dict(alert["latest_evidence"])
            investigation = self.create_investigation(
                {
                    "alert_id": alert_id,
                    "business_question": business_question,
                    "affected_metric": alert["metric_id"],
                    "hypothesis": reason,
                    "owner": owner,
                    "selected_scope": dict(alert.get("selected_scope") or {}),
                    "alert_fingerprint": alert["fingerprint"],
                    "evidence_id": evidence.get("observation_key"),
                    "evidence_run_id": evidence.get("run_id"),
                    "configuration_hash": evidence.get("configuration_hash"),
                    "dataset_hash": evidence.get("dataset_hash"),
                },
                actor=actor,
            )

        investigation_id = str(investigation["investigation_id"])
        if (
            alert.get("related_investigation") == investigation_id
            and alert.get("status") == "INVESTIGATING"
        ):
            refreshed_alert = alert
        elif alert.get("status") == "INVESTIGATING":
            refreshed_alert = self.alert_lifecycle.link_investigation(
                alert_id,
                expected_version=expected_version,
                investigation_id=investigation_id,
                actor=actor,
                selected_scope=filters,
            )
        else:
            refreshed_alert = self.alert_lifecycle.transition(
                alert_id,
                expected_version=expected_version,
                target_status="INVESTIGATING",
                reason=reason,
                actor=actor,
                owner=owner,
                related_investigation=investigation_id,
                selected_scope=filters,
            )
        return json_safe(
            {
                "alert": refreshed_alert,
                "investigation": investigation,
                "reused": reused,
            }
        )

    def command_centre(
        self,
        *,
        period: str | None = None,
        filters: Mapping[str, Any] | None = None,
        source_context: SourceContext | Mapping[str, Any] | None = None,
        persist_alerts: bool = True,
    ) -> dict[str, Any]:
        kpis = self.kpis(
            period=period,
            filters=filters,
            source_context=source_context,
        )["data"]
        trends = self.trends(period=period, filters=filters)["data"]
        enriched = apply_filters(enrich_performance(self.performance, self.master), filters)
        target = (
            pd.Timestamp(period).to_period("M").to_timestamp()
            if period
            else enriched["month"].max()
        )
        current = enriched[enriched["month"] == target]
        risk_distribution = (
            current.groupby("original_risk_band", as_index=False)
            .agg(count=("account_id", "nunique"), balance=("account_balance", "sum"))
            .rename(columns={"original_risk_band": "risk_band"})
            .to_dict(orient="records")
        )
        movements = [
            item
            for item in kpis
            if item["absolute_change"] is not None and item["value"] is not None
        ]
        adverse = sorted(
            [item for item in movements if item["status"] == "adverse"],
            key=lambda item: abs(item["relative_change"] or 0),
            reverse=True,
        )
        favourable = sorted(
            [item for item in movements if item["status"] == "favourable"],
            key=lambda item: abs(item["relative_change"] or 0),
            reverse=True,
        )
        alert_rows = self.alerts(
            period=period,
            filters=filters,
            source_context=source_context,
            persist=persist_alerts,
        )["data"]
        return json_safe(
            {
                "metadata": self._bounded_metadata(period),
                "kpis": kpis,
                "trends": trends,
                "risk_distribution": risk_distribution,
                "alerts": alert_rows,
                "interpretation": {
                    "top_validated_movements": movements[:3],
                    "largest_favourable_movement": favourable[0] if favourable else None,
                    "largest_adverse_movement": adverse[0] if adverse else None,
                    "most_important_data_quality_caveat": (
                        "No failed critical checks."
                        if self.data.validation.status == "PASS"
                        else "Review the Data Quality gate before interpretation."
                    ),
                    "highest_priority_investigation": (
                        alert_rows[0]["recommended_investigation"] if alert_rows else None
                    ),
                },
            }
        )

    def vintages(
        self,
        *,
        period: str | None = None,
        filters: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        rows = calculate_vintages(
            self.performance,
            self.master,
            filters=filters,
            through_period=period,
        )
        return json_safe(
            {
                "data": rows,
                "metadata": {
                    **self._bounded_metadata(period),
                    "normalisation": "Original booked accounts and cumulative transaction value",
                },
            }
        )

    def roll_rates(
        self, *, period: str | None = None, filters: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        return json_safe(
            calculate_roll_rates(
                self.performance,
                self.master,
                period=period,
                filters=filters,
            )
        )

    def strategy_comparison(
        self,
        *,
        period: str | None = None,
        filters: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = compare_strategies(
            self._bound_frame(self.performance, period),
            self.master,
            assumptions=self.config.scenarios["Baseline"],
            filters=filters,
            seed=self.config.seed,
        )
        return json_safe({**result, "metadata": self._bounded_metadata(period)})

    def segments(self, *, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        key = f"segments:{json.dumps(filters or {}, sort_keys=True)}"
        return json_safe(
            self._cached(
                key,
                lambda: {
                    "data": business_rule_segments(self.performance, self.master, filters=filters),
                    "statistical": statistical_segments(self.performance, seed=self.config.seed),
                    "methodology": {
                        "methods": [
                            "Business-rule segmentation",
                            "StandardScaler plus K-Means",
                            "Shallow decision-tree surrogate",
                        ],
                        "protected_attributes_used": False,
                        "causal_status": "DESCRIPTIVE",
                    },
                },
            )
        )

    def root_cause(
        self,
        *,
        period: str | None = None,
        filters: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        key = f"root:{period}:{json.dumps(filters or {}, sort_keys=True)}"
        result = self._cached(
            key,
            lambda: root_cause_finding(
                self.performance,
                self.master,
                period=period,
                filters=filters,
                quality_status=self.data.validation.status,
            ),
        )
        return json_safe({**result, "metadata": self._bounded_metadata(period)})

    def drift(self) -> dict[str, Any]:
        return json_safe(calculate_population_drift(self.performance, self.master))

    def scenarios(self, *, period: str | None = None) -> dict[str, Any]:
        def build() -> dict[str, Any]:
            definitions = {row["scenario_name"]: row for row in list_scenarios(self.config)}
            source_performance = self._bound_frame(self.performance, period)
            results = {
                name: run_scenario(
                    source_performance,
                    self.master,
                    self.config,
                    scenario_name=name,
                    horizon_months=12,
                )
                for name in self.config.scenarios
            }
            baseline_profit = float(results["Baseline"]["summary"]["total_expected_profit"])
            rows = []
            for name, result in results.items():
                summary = result["summary"]
                expected_profit = float(summary["total_expected_profit"])
                rows.append(
                    {
                        "id": name.lower().replace(" ", "-"),
                        "scenario_id": name.lower().replace(" ", "-"),
                        "name": name,
                        "scenario_name": name,
                        "description": definitions[name]["notice"],
                        "assumptions": result["assumptions"],
                        "elasticities": result["elasticities"],
                        "projections": result["projections"],
                        "cumulative_loss": summary["cumulative_net_credit_loss"],
                        "cumulative_fraud": summary["cumulative_fraud_loss"],
                        "expected_profit": expected_profit,
                        "delta_from_baseline": expected_profit - baseline_profit,
                        "loss_delta_from_baseline": summary["loss_difference_from_baseline"],
                        "summary": summary,
                        "validation": result["validation"],
                        "notice": result["notice"],
                    }
                )
            return {
                "data": rows,
                "horizon_months": 12,
                "units": {
                    "cumulative_loss": "currency units",
                    "cumulative_fraud": "currency units",
                    "expected_profit": "currency units",
                    "delta_from_baseline": "currency units of expected profit",
                    "projection_rates": "ratio",
                },
                "metadata": {
                    **self._bounded_metadata(period),
                    "projection_scope": (
                        "Forward-looking planning estimates begin after the "
                        "bounded source reporting month."
                    ),
                },
            }

        return json_safe(self._cached(f"scenario-catalogue:12:{period}", build))

    def scenario_run(
        self,
        payload: Mapping[str, Any],
        *,
        actor: str | None = None,
    ) -> dict[str, Any]:
        period = payload.get("reporting_month")
        result = run_scenario(
            self._bound_frame(self.performance, period),
            self.master,
            self.config,
            scenario_name=str(payload.get("scenario_name", "Baseline")),
            custom_assumptions=payload.get("custom_assumptions"),
            horizon_months=int(payload.get("horizon_months", 12)),
        )
        identity_payload = {key: value for key, value in payload.items() if key != "actor"}
        run_id = self._stable_record_id("SCENARIO", identity_payload)
        state = {
            **result,
            "run_id": run_id,
            "record_kind": "scenario_run",
            "saved": True,
            "approval_required": True,
            "metadata": {
                **self._bounded_metadata(str(period) if period is not None else None),
                "projection_scope": (
                    "Forward-looking planning estimate from the bounded source reporting month."
                ),
            },
        }
        record = self._create_or_get_workflow(
            "scenario_run",
            run_id,
            state,
            actor=self._workflow_actor(payload, actor),
            id_field="run_id",
        )
        return self._workflow_view(record)

    def scenario_run_record(self, run_id: str) -> dict[str, Any]:
        try:
            record = self.workflow_store.get("scenario_run", run_id)
        except ObjectNotFound as exc:
            raise KeyError(run_id) from exc
        return self._workflow_view(record)

    def peak_deterioration_period(self) -> dict[str, Any]:
        loss_rows = sorted(
            [
                row
                for row in self.trends()["data"]
                if row["metric_id"] == "ANNUALISED_NET_LOSS_RATE" and row["value"] is not None
            ],
            key=lambda row: row["month"],
        )
        if not loss_rows:
            return {
                "period": self.data.manifest["maximum_data_date"],
                "comparison_period": None,
                "movement": None,
                "selection_method": "Latest available month because no loss-rate trend exists",
            }
        candidates = [
            {
                "period": current["month"],
                "comparison_period": prior["month"],
                "movement": float(current["value"] - prior["value"]),
                "current_value": current["value"],
                "prior_value": prior["value"],
            }
            for prior, current in zip(loss_rows, loss_rows[1:], strict=False)
        ]
        positive = [row for row in candidates if row["movement"] > 0]
        if positive:
            selected = max(
                positive,
                key=lambda row: (row["movement"], row["period"]),
            )
        elif candidates:
            selected = max(candidates, key=lambda row: row["period"])
        else:
            selected = {
                "period": loss_rows[0]["month"],
                "comparison_period": None,
                "movement": None,
                "current_value": loss_rows[0]["value"],
                "prior_value": None,
            }
        return {
            **selected,
            "metric_id": "ANNUALISED_NET_LOSS_RATE",
            "selection_method": (
                "Largest adverse adjacent-month movement in the governed "
                "annualised net loss-rate trend; latest month only if no "
                "adverse movement exists."
            ),
        }

    def commentary(
        self,
        payload: Mapping[str, Any] | None = None,
        *,
        actor: str | None = None,
        persist_alerts: bool = True,
    ) -> dict[str, Any]:
        payload = payload or {}
        kpis = self.kpis(period=payload.get("period"))["data"]
        metric_values = {item["metric_id"]: item["value"] for item in kpis}
        movements = {item["metric_id"]: item["absolute_change"] for item in kpis}
        root = self.root_cause(period=payload.get("period")).get("finding") or {}
        alerts = self.alerts(
            period=payload.get("period"),
            persist=persist_alerts,
        )["data"]
        evidence = CommentaryEvidence(
            reporting_period=str(kpis[0]["reporting_period"] if kpis else "N/A"),
            comparison_period=str(kpis[0]["comparison_period"] if kpis else "N/A"),
            metric_values=metric_values,
            validated_movements=movements,
            root_cause_contributions={
                "primary_driver": root.get("primary_driver"),
                "contribution_share": root.get("contribution_share"),
                "mix_contribution_bps": root.get("mix_contribution_bps"),
                "within_segment_contribution_bps": root.get("within_segment_contribution_bps"),
            },
            alert_status=alerts,
            statistical_confidence={item["metric_id"]: item["statistical_status"] for item in kpis},
            caveats=[
                "All data and thresholds are synthetic and institution-neutral.",
                "Root-cause contributions are associational, not causal.",
            ],
            recommended_investigation_steps=root.get(
                "recommended_investigation", ["Continue governed monitoring."]
            ),
            data_quality_status=self.data.validation.status,
        )
        result = DeterministicTemplateProvider().generate(evidence)
        identity_payload = {key: value for key, value in payload.items() if key != "actor"}
        commentary_id = self._stable_record_id("COMMENTARY", identity_payload)
        state = {
            **result.as_dict(),
            "commentary_id": commentary_id,
            "record_kind": "commentary",
            "evidence_contract": evidence.allowlisted_dict(),
            "raw_account_records_sent": False,
            "approval_required": True,
        }
        record = self._create_or_get_workflow(
            "commentary",
            commentary_id,
            state,
            actor=self._workflow_actor(payload, actor),
            id_field="commentary_id",
        )
        return self._workflow_view(record)

    def commentary_record(self, commentary_id: str) -> dict[str, Any]:
        try:
            record = self.workflow_store.get("commentary", commentary_id)
        except ObjectNotFound as exc:
            raise KeyError(commentary_id) from exc
        return self._workflow_view(record)

    def partners(self, *, period: str | None = None) -> dict[str, Any]:
        performance = self._bound_frame(self.tables["partner_monthly_performance"], period)
        output = partner_analytics(
            performance,
            self.tables["partner_master"],
            self.tables["partner_contract"],
        )
        ratings = {
            row["partner_id"]: row for row in rate_partners(performance, self.config.ratings)
        }
        for row in output["data"]:
            row["rating"] = ratings.get(row["partner_id"])
        output["metadata"] = self._bounded_metadata(period)
        return json_safe(output)

    def partner_scenario(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        partner_id = str(payload["partner_id"])
        period = payload.get("reporting_month")
        latest = self._bound_frame(
            self.tables["partner_monthly_performance"],
            str(period) if period is not None else None,
        )
        latest = latest[latest["month"] == latest["month"].max()]
        matched = latest[latest["partner_id"] == partner_id]
        if matched.empty:
            raise ValueError(f"Unknown partner_id: {partner_id}")
        row = matched.iloc[0]
        volume_multiplier = float(payload.get("volume_multiplier", 1.0))
        fraud_multiplier = float(payload.get("fraud_loss_multiplier", 1.0))
        credit_multiplier = float(payload.get("credit_loss_multiplier", 1.0))
        attrition_multiplier = float(payload.get("attrition_multiplier", 1.0))
        projected_fraud = float(row["confirmed_fraud_loss"]) * volume_multiplier * fraud_multiplier
        projected_credit = float(row["credit_loss"]) * volume_multiplier * credit_multiplier
        projected_attrition = (
            float(row["attrition_count"]) * volume_multiplier * attrition_multiplier
        )
        scaled_profit = float(row["expected_profit"]) * volume_multiplier
        excess_loss = (
            projected_fraud
            + projected_credit
            - (float(row["confirmed_fraud_loss"]) + float(row["credit_loss"])) * volume_multiplier
        )
        attrition_cost = (
            max(
                projected_attrition - float(row["attrition_count"]) * volume_multiplier,
                0,
            )
            * 25.0
        )
        projected_profit = scaled_profit - excess_loss - attrition_cost
        baseline = {
            "active_accounts": float(row["active_accounts"]),
            "transaction_value": float(row["transaction_value"]),
            "confirmed_fraud_loss": float(row["confirmed_fraud_loss"]),
            "credit_loss": float(row["credit_loss"]),
            "attrition_count": float(row["attrition_count"]),
            "expected_profit": float(row["expected_profit"]),
        }
        scenario = {
            "active_accounts": baseline["active_accounts"] * volume_multiplier,
            "transaction_value": baseline["transaction_value"] * volume_multiplier,
            "confirmed_fraud_loss": projected_fraud,
            "credit_loss": projected_credit,
            "attrition_count": projected_attrition,
            "expected_profit": projected_profit,
        }
        return json_safe(
            {
                "partner_id": partner_id,
                "baseline": baseline,
                "scenario": scenario,
                "delta": {key: scenario[key] - baseline[key] for key in scenario},
                "assumptions": {
                    "volume_multiplier": volume_multiplier,
                    "fraud_loss_multiplier": fraud_multiplier,
                    "credit_loss_multiplier": credit_multiplier,
                    "attrition_multiplier": attrition_multiplier,
                    "incremental_attrition_cost_per_account": 25.0,
                },
                "formula": (
                    "Scaled baseline profit less incremental credit/fraud losses "
                    "and incremental attrition cost."
                ),
                "status": "scenario_estimate",
                "saved": False,
                "approval_required": True,
                "notice": "Synthetic planning estimate; not a committed partner decision.",
                "metadata": self._bounded_metadata(str(period) if period is not None else None),
            }
        )

    def vendors(self, *, period: str | None = None) -> dict[str, Any]:
        performance = self._bound_frame(self.tables["vendor_monthly_performance"], period)
        output = vendor_analytics(
            performance,
            self.tables["vendor_master"],
            self.tables["vendor_contract"],
        )
        ratings = {row["vendor_id"]: row for row in rate_vendors(performance, self.config.ratings)}
        for row in output["data"]:
            row["rating"] = ratings.get(row["vendor_id"])
        output["metadata"] = self._bounded_metadata(period)
        return json_safe(output)

    def vendor_reallocation(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        source_id = str(payload["source_vendor_id"])
        target_id = str(payload["target_vendor_id"])
        if source_id == target_id:
            raise ValueError("Source and target vendors must differ")
        period = payload.get("reporting_month")
        latest = self._bound_frame(
            self.tables["vendor_monthly_performance"],
            str(period) if period is not None else None,
        )
        latest = latest[latest["month"] == latest["month"].max()].copy()
        indexed = latest.set_index("vendor_id", drop=False)
        missing = [
            vendor_id for vendor_id in [source_id, target_id] if vendor_id not in indexed.index
        ]
        if missing:
            raise ValueError(f"Unknown vendor_id values: {missing}")
        source = indexed.loc[source_id]
        target = indexed.loc[target_id]
        share = float(payload.get("reallocation_share", 0.1))
        cases_moved = float(source["cases_received"]) * share

        def projection(row: pd.Series, case_delta: float) -> dict[str, float]:
            base_cases = float(row["cases_received"])
            projected_cases = max(base_cases + case_delta, 0)
            ratio = projected_cases / base_cases if base_cases else 1.0
            projected_cost = (
                float(row["fixed_cost"])
                + float(row["variable_cost"]) * ratio
                + float(row["penalty_value"])
                - float(row["incentive_value"])
            )
            return {
                "cases_received": projected_cases,
                "total_vendor_cost": projected_cost,
                "capacity_utilisation": float(row["capacity_utilisation"]) * ratio,
                "quality_score": float(row["quality_score"]),
                "risk_score": float(row["risk_score"]),
            }

        source_projection = projection(source, -cases_moved)
        target_projection = projection(target, cases_moved)
        baseline_cost = float(source["total_vendor_cost"]) + float(target["total_vendor_cost"])
        projected_cost = (
            source_projection["total_vendor_cost"] + target_projection["total_vendor_cost"]
        )
        target_capacity = target_projection["capacity_utilisation"]
        return json_safe(
            {
                "source_vendor_id": source_id,
                "target_vendor_id": target_id,
                "cases_moved": cases_moved,
                "reallocation_share": share,
                "source_projection": source_projection,
                "target_projection": target_projection,
                "total_cost_delta": projected_cost - baseline_cost,
                "guardrails": {
                    "target_capacity_within_limit": target_capacity <= 1.0,
                    "target_capacity_utilisation": target_capacity,
                    "quality_held_constant": True,
                    "customer_impact_review_required": True,
                },
                "status": "scenario_estimate",
                "saved": False,
                "approval_required": True,
                "notice": "Synthetic planning estimate; not a committed vendor allocation.",
                "metadata": self._bounded_metadata(str(period) if period is not None else None),
            }
        )

    def memberships(self, *, period: str | None = None) -> dict[str, Any]:
        output = membership_analytics(
            self._bound_frame(self.performance, period),
            self._master_as_of(period),
            self.tables["membership_master"],
            self._bound_frame(self.tables["benefit_usage_fact"], period),
        )
        ratings = {
            row["membership_tier_id"]: row
            for row in rate_memberships(pd.DataFrame(output["data"]), self.config.ratings)
        }
        for row in output["data"]:
            row["rating"] = ratings.get(row["membership_tier_id"])
        output["metadata"] = self._bounded_metadata(period)
        return json_safe(output)

    def membership_transitions(self, *, period: str | None = None) -> dict[str, Any]:
        history = self.tables["customer_membership_history"]
        if period is not None:
            cutoff = pd.Timestamp(period).normalize()
            history = history[pd.to_datetime(history["effective_start_date"]) <= cutoff]
        changed = history[history["change_type"].isin(["Upgrade", "Downgrade"])]
        matrix = (
            changed.groupby(["prior_membership_tier", "new_membership_tier"], as_index=False)
            .agg(count=("account_id", "nunique"))
            .to_dict(orient="records")
        )
        return json_safe(
            {
                "data": matrix,
                "upgrades": int(changed["upgrade_flag"].sum()),
                "downgrades": int(changed["downgrade_flag"].sum()),
                "analytical_grain": "customer-account membership transition",
                "metadata": self._bounded_metadata(period),
            }
        )

    def benefits(self, *, period: str | None = None) -> dict[str, Any]:
        master = self.tables["benefit_master"]
        usage = self._bound_frame(self.tables["benefit_usage_fact"], period)
        if len(usage):
            grouped = usage.groupby("benefit_id", as_index=False).agg(
                users=("account_id", "nunique"),
                usage_count=("usage_count", "sum"),
                customer_value=("customer_value", "sum"),
                issuer_cost=("issuer_cost", "sum"),
                partner_funded_value=("partner_funded_value", "sum"),
                fraud_events=("fraud_confirmed_flag", "sum"),
                disputes=("dispute_flag", "sum"),
            )
            output = master.merge(grouped, on="benefit_id", how="left").fillna(0)
        else:
            output = master.copy()
        return json_safe(
            {
                "data": output.to_dict(orient="records"),
                "metadata": self._bounded_metadata(period),
            }
        )

    def baskets(self, *, requested_period: str | None = None) -> dict[str, Any]:
        definitions = self.tables["portfolio_basket_definition"].copy()
        membership = self.tables["portfolio_basket_membership"]
        counts = membership.groupby("basket_id")["entity_id"].nunique().to_dict()
        rows_by_id: dict[str, dict[str, Any]] = {}
        for row in definitions.to_dict(orient="records"):
            row["member_count"] = int(counts.get(row["basket_id"], 0))
            row.setdefault("version", 1)
            row.setdefault("approval_state", "APPROVED" if row.get("approved_flag") else "DRAFT")
            rows_by_id[row["basket_id"]] = row
        for record in self.workflow_store.list("basket"):
            row = self._workflow_view(record)
            rows_by_id[str(row["basket_id"])] = row
        return json_safe(
            {
                "data": list(rows_by_id.values()),
                "metadata": {
                    "versioning": True,
                    "approval_required": True,
                    "scope": "current_definition_state",
                    "requested_reporting_month": requested_period,
                    "reporting_month_applied": False,
                    "scope_notice": (
                        "Basket definitions are current workflow objects; the "
                        "reporting-month filter is not applied to definition state."
                    ),
                },
            }
        )

    def basket_detail(
        self, basket_id: str, *, requested_period: str | None = None
    ) -> dict[str, Any]:
        rows = [
            row
            for row in self.baskets(requested_period=requested_period)["data"]
            if row["basket_id"] == basket_id
        ]
        if not rows:
            raise KeyError(basket_id)
        row = dict(rows[0])
        if "members" in row:
            members = list(row["members"])
        else:
            membership = self.tables["portfolio_basket_membership"]
            members = sorted(
                str(value)
                for value in membership.loc[
                    membership["basket_id"] == basket_id, "entity_id"
                ].unique()
            )
        row["members"] = members
        row["member_count"] = len(members)
        row["audit"] = {
            "version": row.get("version", 1),
            "status": row.get("status"),
            "approved_flag": bool(row.get("approved_flag", False)),
            "locked_flag": bool(row.get("locked_flag", False)),
        }
        row["scope_metadata"] = {
            "scope": "current_definition_state",
            "requested_reporting_month": requested_period,
            "reporting_month_applied": False,
        }
        return json_safe(row)

    def create_basket(
        self,
        payload: Mapping[str, Any],
        *,
        actor: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            workflow_actor = self._workflow_actor(payload, actor)
            members = sorted({str(member) for member in payload.get("members", [])})
            state = {
                "basket_name": str(payload["basket_name"]),
                "basket_type": str(payload.get("basket_type", "account")),
                "entity_type": str(payload.get("entity_type", "account")),
                "basket_description": str(payload.get("basket_description", "")),
                "basket_expression": str(payload.get("basket_expression", "")),
                "member_count": len(members),
                "members": members,
                "status": "Draft",
                "locked_flag": bool(payload.get("locked_flag", False)),
                "source_basket_id": payload.get("source_basket_id"),
                "approval_required": True,
            }
            record = self._create_unique_workflow(
                "basket",
                "BASKET",
                state,
                actor=workflow_actor,
                id_field="basket_id",
            )
            basket_id = str(record["external_id"])
            self.workflow_store.create(
                "basket_membership",
                f"{basket_id}:members",
                {
                    "basket_id": basket_id,
                    "members": members,
                    "member_count": len(members),
                    "basket_version": 1,
                },
                actor=workflow_actor,
            )
            return self._workflow_view(record)

    def update_basket(
        self,
        basket_id: str,
        payload: Mapping[str, Any],
        *,
        expected_version: int | None = None,
        actor: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            existing = self.basket_detail(basket_id)
            if existing.get("locked_flag"):
                raise ValueError("Locked baskets must be cloned before editing")
            workflow_actor = self._workflow_actor(payload, actor)
            current = self._persist_baseline_override(
                "basket",
                basket_id,
                existing,
                actor=workflow_actor,
            )
            resolved_version = self._expected_version(
                payload,
                int(current["version"]),
                expected_version,
            )
            allowed = {
                "basket_name",
                "basket_description",
                "basket_expression",
                "members",
                "locked_flag",
            }
            now = datetime.now(UTC).isoformat()
            updated = {
                key: value
                for key, value in existing.items()
                if key
                not in {
                    "audit",
                    "scope_metadata",
                    "version",
                    "approval_state",
                    "approved_flag",
                    "created_timestamp",
                    "modified_timestamp",
                }
            }
            changed_fields = []
            for key, value in payload.items():
                if key in allowed and value is not None and updated.get(key) != value:
                    updated[key] = value
                    changed_fields.append(key)
            updated["members"] = sorted({str(member) for member in updated.get("members", [])})
            updated["member_count"] = len(updated["members"])
            updated["status"] = "Draft"
            updated["approval_required"] = True
            updated["change_audit"] = {
                "changed_fields": changed_fields,
                "prior_version": resolved_version,
                "new_version": resolved_version + 1,
                "timestamp": now,
                "approval_required": True,
            }
            record = self.workflow_store.update(
                "basket",
                basket_id,
                updated,
                expected_version=resolved_version,
                actor=workflow_actor,
                approval_state="DRAFT",
                replace=True,
            )
            membership_id = f"{basket_id}:members"
            membership_state = {
                "basket_id": basket_id,
                "members": updated["members"],
                "member_count": updated["member_count"],
                "basket_version": int(record["version"]),
            }
            try:
                membership_record = self.workflow_store.get(
                    "basket_membership",
                    membership_id,
                )
            except ObjectNotFound:
                self.workflow_store.create(
                    "basket_membership",
                    membership_id,
                    membership_state,
                    actor=workflow_actor,
                )
            else:
                self.workflow_store.update(
                    "basket_membership",
                    membership_id,
                    membership_state,
                    expected_version=int(membership_record["version"]),
                    actor=workflow_actor,
                    replace=True,
                )
            return self._workflow_view(record)

    def clone_basket(self, basket_id: str, *, actor: str | None = None) -> dict[str, Any]:
        existing = self.basket_detail(basket_id)
        return self.create_basket(
            {
                "basket_name": f"{existing['basket_name']} — clone",
                "basket_type": existing.get("basket_type", "account"),
                "entity_type": existing.get("entity_type", "account"),
                "basket_description": existing.get("basket_description", ""),
                "basket_expression": existing.get("basket_expression", ""),
                "members": existing.get("members", []),
                "locked_flag": False,
                "source_basket_id": basket_id,
            },
            actor=actor,
        )

    def combine_baskets(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        members = combine_memberships(
            payload.get("left_members", []),
            payload.get("right_members", []),
            str(payload.get("operation", "union")),
        )
        return {
            "operation": payload.get("operation", "union"),
            "members": members,
            "member_count": len(members),
            "frozen_reproducibility_hash": sha256(
                json.dumps(members, separators=(",", ":")).encode()
            ).hexdigest(),
        }

    def basket_impact(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        latest = self.tables["partner_monthly_performance"]
        latest = latest[latest["month"] == latest["month"].max()]
        return json_safe(
            impact_preview(
                latest,
                entity_id_column="partner_id",
                original_members=payload.get("original_members", []),
                revised_members=payload.get("revised_members", []),
                metric_columns=["transaction_value", "expected_profit", "confirmed_fraud_loss"],
            )
        )

    def workspaces(self) -> dict[str, Any]:
        base = {
            row["workspace_id"]: row
            for row in self.tables["workspace_definition"].to_dict(orient="records")
        }
        for row in base.values():
            row.setdefault("version", 1)
            row.setdefault("approval_state", "APPROVED" if row.get("approved_flag") else "DRAFT")
        for record in self.workflow_store.list("workspace"):
            row = self._workflow_view(record)
            base[str(row["workspace_id"])] = row
        return json_safe({"data": list(base.values())})

    def workspace_detail(self, workspace_id: str) -> dict[str, Any]:
        rows = [row for row in self.workspaces()["data"] if row["workspace_id"] == workspace_id]
        if not rows:
            raise KeyError(workspace_id)
        return rows[0]

    def create_workspace(
        self,
        payload: Mapping[str, Any],
        *,
        actor: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            state = {
                "workspace_name": str(payload["workspace_name"]),
                "owner": str(payload.get("owner", "Unassigned")),
                "workspace_type": str(payload.get("workspace_type", "Ad hoc analysis")),
                "business_question": str(payload["business_question"]),
                "reporting_period": payload.get("reporting_period")
                or self.data.manifest["maximum_data_date"],
                "comparison_period": payload.get("comparison_period"),
                "selected_metrics": payload.get("selected_metrics", []),
                "selected_dimensions": payload.get("selected_dimensions", []),
                "selected_baskets": payload.get("selected_baskets", []),
                "selected_scenarios": payload.get("selected_scenarios", ["Baseline"]),
                "selected_templates": payload.get("selected_templates", ["MONTHLY_KPI_MOVEMENT"]),
                "filter_configuration": payload.get("filter_configuration", {}),
                "visual_configuration": payload.get("visual_configuration", {}),
                "commentary_configuration": payload.get(
                    "commentary_configuration", {"provider": "template"}
                ),
                "export_configuration": payload.get("export_configuration", {}),
                "status": "Draft",
                "approval_required": True,
            }
            record = self._create_unique_workflow(
                "workspace",
                "WORKSPACE",
                state,
                actor=self._workflow_actor(payload, actor),
                id_field="workspace_id",
            )
            return self._workflow_view(record)

    def update_workspace(
        self,
        workspace_id: str,
        payload: Mapping[str, Any],
        *,
        expected_version: int | None = None,
        actor: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            existing = self.workspace_detail(workspace_id)
            workflow_actor = self._workflow_actor(payload, actor)
            current = self._persist_baseline_override(
                "workspace",
                workspace_id,
                existing,
                actor=workflow_actor,
            )
            resolved_version = self._expected_version(
                payload,
                int(current["version"]),
                expected_version,
            )
            allowed = {
                "workspace_name",
                "owner",
                "workspace_type",
                "business_question",
                "reporting_period",
                "comparison_period",
                "selected_metrics",
                "selected_dimensions",
                "selected_baskets",
                "selected_scenarios",
                "selected_templates",
                "filter_configuration",
                "visual_configuration",
                "commentary_configuration",
                "export_configuration",
            }
            updated = {
                key: value
                for key, value in existing.items()
                if key
                not in {
                    "version",
                    "approval_state",
                    "approved_flag",
                    "created_timestamp",
                    "modified_timestamp",
                }
            }
            changed_fields = []
            for key, value in payload.items():
                if key in allowed and value is not None and updated.get(key) != value:
                    updated[key] = value
                    changed_fields.append(key)
            now = datetime.now(UTC).isoformat()
            updated["status"] = "Draft"
            updated["approval_required"] = True
            updated["change_audit"] = {
                "changed_fields": changed_fields,
                "prior_version": resolved_version,
                "new_version": resolved_version + 1,
                "timestamp": now,
                "approval_required": True,
            }
            record = self.workflow_store.update(
                "workspace",
                workspace_id,
                updated,
                expected_version=resolved_version,
                actor=workflow_actor,
                approval_state="DRAFT",
                replace=True,
            )
            return self._workflow_view(record)

    def run_workspace(self, workspace_id: str, *, refresh: bool = False) -> dict[str, Any]:
        workspace = self.workspace_detail(workspace_id)
        result = {
            "workspace_id": workspace_id,
            "workspace_version": workspace.get("version", 1),
            "status": "completed",
            "refresh": refresh,
            "run_timestamp": datetime.now(UTC).isoformat(),
            "business_question": workspace.get("business_question"),
            "command_centre": self.command_centre(period=workspace.get("reporting_period")),
            "root_cause": self.root_cause(period=workspace.get("reporting_period")),
            "data_quality_status": self.data.validation.status,
            "live_calculations": True,
        }
        return json_safe(result)

    def export_workspace(self, workspace_id: str) -> dict[str, Any]:
        self.workspace_detail(workspace_id)
        exported = self.export_excel()
        return {
            **exported,
            "workspace_id": workspace_id,
            "workspace_version": self.workspace_detail(workspace_id).get("version", 1),
        }

    def peer_catalogue(self) -> dict[str, Any]:
        return {
            "data": [
                {
                    "entity_type": "partner",
                    "entity_ids": sorted(
                        str(value) for value in self.tables["partner_master"]["partner_id"].unique()
                    ),
                    "default_comparison_metric": "expected_profit",
                },
                {
                    "entity_type": "vendor",
                    "entity_ids": sorted(
                        str(value) for value in self.tables["vendor_master"]["vendor_id"].unique()
                    ),
                    "default_comparison_metric": "quality_score",
                },
                {
                    "entity_type": "membership",
                    "entity_ids": sorted(
                        str(value)
                        for value in self.tables["membership_master"]["membership_tier_id"].unique()
                    ),
                    "default_comparison_metric": "expected_contribution",
                },
            ],
            "methods": [
                "nearest-neighbour matching on standardised numeric features",
                "deterministic tie-breaking",
            ],
            "causal_status": "DESCRIPTIVE",
        }

    def peer_analogues(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        entity_type = str(payload.get("entity_type", "partner"))
        if entity_type == "partner":
            frame = pd.DataFrame(self.partners()["data"])
            identifier = "partner_id"
            features = [
                "active_accounts",
                "transaction_value",
                "average_balance",
                "confirmed_fraud_loss",
                "credit_loss",
                "complaints",
                "partner_contribution",
            ]
            default_metric = "expected_profit"
        elif entity_type == "vendor":
            frame = pd.DataFrame(self.vendors()["data"])
            identifier = "vendor_id"
            features = [
                "process_volume",
                "average_processing_minutes",
                "first_time_right_rate",
                "unit_cost",
                "capacity_utilisation",
                "quality_score",
                "risk_score",
            ]
            default_metric = "quality_score"
        elif entity_type == "membership":
            frame = pd.DataFrame(self.memberships()["data"])
            identifier = "membership_tier_id"
            features = [
                "active_members",
                "transaction_value",
                "balance",
                "credit_loss",
                "fraud_loss",
                "attrition_rate",
                "benefit_utilisation",
            ]
            default_metric = "expected_contribution"
        else:
            raise ValueError("entity_type must be partner, vendor, or membership")
        return json_safe(
            match_peer_analogues(
                frame,
                entity_id_column=identifier,
                entity_id=str(payload["entity_id"]),
                feature_columns=features,
                comparison_metric=str(payload.get("comparison_metric") or default_metric),
                peer_count=int(payload.get("peer_count", 3)),
            )
        )

    def run_analysis_template(
        self,
        template_id: str,
        parameters: Mapping[str, Any] | None = None,
        *,
        actor: str | None = None,
    ) -> dict[str, Any]:
        parameters = parameters or {}
        template_id = template_id.upper()
        if template_id == "MONTHLY_KPI_MOVEMENT":
            result = {
                "kpis": self.kpis(period=parameters.get("period")),
                "root_cause": self.root_cause(period=parameters.get("period")),
            }
        elif template_id == "VINTAGE_DETERIORATION":
            result = self.vintages()
        elif template_id == "STRATEGY_EXPERIMENT":
            result = self.strategy_comparison()
        elif template_id == "CONCENTRATION_DEPENDENCY":
            result = {
                "finance": self.finance(),
                "network": self.network(),
            }
        else:
            raise ValueError(f"Template {template_id} is not executable in this implementation")
        with self._lock:
            state = {
                "record_kind": "analysis_run",
                "template_id": template_id,
                "status": "completed",
                "parameters": dict(parameters),
                "result": result,
                "run_timestamp": datetime.now(UTC).isoformat(),
                "data_quality_status": self.data.validation.status,
                "causal_status": "Design-dependent",
                "live_calculations": True,
                "approval_required": True,
            }
            record = self._create_unique_workflow(
                "workspace_version",
                "ANALYSIS",
                state,
                actor=self._workflow_actor(parameters, actor),
                id_field="run_id",
            )
            return self._workflow_view(record)

    def analysis_run(self, run_id: str) -> dict[str, Any]:
        try:
            record = self.workflow_store.get("workspace_version", run_id)
        except ObjectNotFound as exc:
            raise KeyError(run_id) from exc
        if record["state"].get("record_kind") != "analysis_run":
            raise KeyError(run_id)
        return self._workflow_view(record)

    def finance(self, *, period: str | None = None) -> dict[str, Any]:
        result = finance_analytics(
            self._bound_frame(self.performance, period),
            self._bound_frame(self.tables["partner_monthly_performance"], period),
            self._bound_frame(self.tables["vendor_monthly_performance"], period),
            self.config.scenarios["Baseline"],
        )
        return json_safe({**result, "metadata": self._bounded_metadata(period)})

    def data_quality(self) -> dict[str, Any]:
        validation = self.data.validation.as_dict()
        for check in validation["checks"]:
            location = check.get("quarantine_location")
            if location:
                check["quarantine_location"] = Path(str(location)).name
        manifest = dict(self.data.manifest)
        manifest["paths"] = {
            name: Path(str(path)).name for name, path in manifest.get("paths", {}).items()
        }
        return json_safe(
            {
                **validation,
                "manifest": manifest,
                "latest_available_month": self.data.manifest["maximum_data_date"],
                "completeness_percentage": 100.0
                * (
                    1
                    - sum(self.data.manifest["rejected_row_counts"].values())
                    / max(sum(self.data.manifest["row_counts"].values()), 1)
                ),
            }
        )

    def network(self) -> dict[str, Any]:
        return json_safe(
            build_dependency_network(
                self.master,
                self.tables["benefit_usage_fact"],
                self.tables["service_incident_fact"],
            )
        )

    def network_impact(self, node_id: str) -> dict[str, Any]:
        return json_safe(network_impact(node_id, self.master, self.performance))

    def capacity(self) -> dict[str, Any]:
        return json_safe(capacity_summary(self.tables["vendor_monthly_performance"]))

    def capacity_scenario(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return json_safe(
            run_capacity_scenario(
                self.tables["vendor_monthly_performance"],
                volume_multiplier=float(payload.get("volume_multiplier", 1.0)),
                capacity_multiplier=float(payload.get("capacity_multiplier", 1.0)),
                handling_time_multiplier=float(payload.get("handling_time_multiplier", 1.0)),
                review_threshold_change=float(payload.get("review_threshold_change", 0.0)),
            )
        )

    def investigations(self, *, requested_period: str | None = None) -> dict[str, Any]:
        rows = sorted(
            (self._workflow_view(record) for record in self.workflow_store.list("investigation")),
            key=lambda item: item["opened_timestamp"],
        )
        return json_safe(
            {
                "data": rows,
                "total": len(rows),
                "metadata": {
                    "scope": "current_workflow_state",
                    "requested_reporting_month": requested_period,
                    "reporting_month_applied": False,
                    "scope_notice": (
                        "Investigation status is a current workflow state and is "
                        "not reconstructed as-of a historical reporting month."
                    ),
                },
            }
        )

    def create_investigation(
        self,
        payload: Mapping[str, Any],
        *,
        actor: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            now = datetime.now(UTC).isoformat()
            state = {
                "alert_id": payload.get("alert_id"),
                "business_question": payload.get("business_question"),
                "affected_metric": payload.get("affected_metric"),
                "hypothesis": payload.get("hypothesis"),
                "owner": payload.get("owner", "Unassigned"),
                "status": "New",
                "opened_timestamp": now,
                "audit_timestamp": now,
                "decision": None,
                "approval_required": True,
                "selected_scope": dict(payload.get("selected_scope") or {}),
                "alert_fingerprint": payload.get("alert_fingerprint"),
                "evidence_id": payload.get("evidence_id"),
                "evidence_run_id": payload.get("evidence_run_id"),
                "configuration_hash": payload.get("configuration_hash"),
                "dataset_hash": payload.get("dataset_hash"),
            }
            record = self._create_unique_workflow(
                "investigation",
                "INV",
                state,
                actor=self._workflow_actor(payload, actor),
                id_field="investigation_id",
            )
            return self._workflow_view(record)

    def update_investigation(
        self,
        investigation_id: str,
        payload: Mapping[str, Any],
        *,
        expected_version: int | None = None,
        actor: str | None = None,
    ) -> dict[str, Any]:
        allowed = {
            "owner",
            "status",
            "hypothesis",
            "supporting_evidence",
            "action_taken",
            "resolution",
            "reviewer",
            "decision",
        }
        with self._lock:
            try:
                current = self.workflow_store.get("investigation", investigation_id)
            except ObjectNotFound as exc:
                raise KeyError(investigation_id) from exc
            resolved_version = self._expected_version(
                payload,
                int(current["version"]),
                expected_version,
            )
            row = dict(current["state"])
            changed_fields = []
            for key, value in payload.items():
                if key in allowed and row.get(key) != value:
                    row[key] = value
                    changed_fields.append(key)
            row["audit_timestamp"] = datetime.now(UTC).isoformat()
            row["change_audit"] = {
                "changed_fields": changed_fields,
                "prior_version": resolved_version,
                "new_version": resolved_version + 1,
                "timestamp": row["audit_timestamp"],
                "approval_required": True,
            }
            record = self.workflow_store.update(
                "investigation",
                investigation_id,
                row,
                expected_version=resolved_version,
                actor=self._workflow_actor(payload, actor),
                approval_state="DRAFT",
                replace=True,
            )
            return self._workflow_view(record)

    def exports(self) -> dict[str, Any]:
        for discovered in list_exports(self):
            filename = Path(str(discovered["filename"])).name
            self._register_export(
                self.config.data_root / "generated_exports" / filename,
                actor="workbench.service.discovery",
            )
        rows = []
        for record in self.workflow_store.list("export_job"):
            row = self._workflow_view(record)
            artifact_id = str(row["artifact_id"])
            filename = str(row["filename"])
            row["download_url"] = f"/api/v1/exports/{artifact_id}/download"
            row["available"] = (
                Path(filename).name == filename
                and (self.config.data_root / "generated_exports" / filename).is_file()
            )
            rows.append(row)
        return json_safe({"data": rows})

    def _register_export(
        self,
        path: Path,
        format_name: str | None = None,
        *,
        actor: str | None = None,
    ) -> dict[str, Any]:
        filename = Path(path.name).name
        if filename != path.name or not path.is_file():
            raise ValueError("Export artifact must be an existing path-safe file")
        workflow_actor = actor or "workbench.service"
        now = datetime.now(UTC)
        existing = next(
            (
                record
                for record in self.workflow_store.list("export_job")
                if record["state"].get("filename") == filename
            ),
            None,
        )
        file_hash = _sha256_file(path)
        existing_state = existing["state"] if existing is not None else {}
        unchanged_file = bool(
            existing is not None
            and existing_state.get("file_sha256") == file_hash
            and int(existing_state.get("size_bytes", -1)) == path.stat().st_size
        )
        state = {
            "record_kind": "export_job",
            "filename": filename,
            "size_bytes": path.stat().st_size,
            "file_sha256": file_hash,
            "status": "completed",
            "format": format_name
            or (existing["state"].get("format") if existing is not None else None)
            or path.suffix.lstrip(".").lower(),
            "synthetic": True,
            "approval_required": True,
            "requested_by": existing_state.get("requested_by", workflow_actor),
            "workspace_id": None,
            "filters": {},
            "created_at": (
                existing_state.get("created_at") if existing is not None else now.isoformat()
            ),
            "completed_at": (
                existing_state.get("completed_at") if unchanged_file else now.isoformat()
            ),
            "expires_at": (
                existing_state.get("expires_at")
                if unchanged_file
                else (now + timedelta(hours=24)).isoformat()
            ),
            "error": None,
            "download_count": (
                int(existing_state.get("download_count", 0)) if existing is not None else 0
            ),
        }
        if existing is None:
            record = self._create_unique_workflow(
                "export_job",
                "EXPORT",
                state,
                actor=workflow_actor,
                id_field="artifact_id",
            )
        elif all(existing["state"].get(key) == value for key, value in state.items()):
            record = existing
        else:
            record = self.workflow_store.update(
                "export_job",
                str(existing["external_id"]),
                {**existing["state"], **state},
                expected_version=int(existing["version"]),
                actor=workflow_actor,
                replace=True,
            )
        result = self._workflow_view(record)
        result["download_url"] = f"/api/v1/exports/{result['artifact_id']}/download"
        return json_safe(result)

    def register_export_artifact(
        self,
        path: Path,
        format_name: str,
        *,
        actor: str,
    ) -> dict[str, Any]:
        """Register a governed artifact produced by a live extension module."""

        root = (self.config.data_root / "generated_exports").resolve()
        candidate = path.resolve()
        if candidate.parent != root:
            raise ValueError("Extension exports must be written to the governed export directory")
        return self._register_export(candidate, format_name, actor=actor)

    def resolve_export_artifact(
        self,
        artifact_id: str,
        *,
        actor: str | None = None,
    ) -> Path:
        try:
            record = self.workflow_store.get("export_job", artifact_id)
        except ObjectNotFound:
            for discovered in list_exports(self):
                if discovered["artifact_id"] != artifact_id:
                    continue
                filename = Path(str(discovered["filename"])).name
                candidate = self.config.data_root / "generated_exports" / filename
                if candidate.is_file():
                    return candidate
            raise KeyError(artifact_id) from None
        filename = str(record["state"].get("filename", ""))
        expires_at = record["state"].get("expires_at")
        if expires_at and datetime.fromisoformat(str(expires_at)) <= datetime.now(UTC):
            self.workflow_store.update(
                "export_job",
                artifact_id,
                {**record["state"], "status": "expired"},
                expected_version=int(record["version"]),
                actor=actor or "workbench.service",
                replace=True,
            )
            raise KeyError(artifact_id)
        if record["state"].get("status") != "completed":
            raise KeyError(artifact_id)
        if not filename or Path(filename).name != filename:
            raise KeyError(artifact_id)
        root = (self.config.data_root / "generated_exports").resolve()
        candidate = (root / filename).resolve()
        if candidate.parent != root or not candidate.is_file():
            raise KeyError(artifact_id)
        expected_hash = str(record["state"].get("file_sha256", ""))
        expected_size = record["state"].get("size_bytes")
        try:
            actual_size = candidate.stat().st_size
            actual_hash = _sha256_file(candidate)
        except OSError:
            actual_size = -1
            actual_hash = ""
        if (
            not expected_hash
            or expected_size is None
            or actual_size != int(expected_size)
            or actual_hash != expected_hash
        ):
            self.workflow_store.update(
                "export_job",
                artifact_id,
                {
                    **record["state"],
                    "status": "integrity_failed",
                    "error": "Registered artifact failed size or SHA-256 verification.",
                    "integrity_checked_at": datetime.now(UTC).isoformat(),
                },
                expected_version=int(record["version"]),
                actor=actor or "workbench.service",
                replace=True,
            )
            raise KeyError(artifact_id)
        return candidate

    def register_export_download(self, artifact_id: str, *, actor: str) -> dict[str, Any]:
        """Persist a successful authorized download against the export job audit chain."""

        record = self.workflow_store.get("export_job", artifact_id)
        state = {
            **record["state"],
            "download_count": int(record["state"].get("download_count", 0)) + 1,
            "last_downloaded_at": datetime.now(UTC).isoformat(),
            "last_downloaded_by": actor,
        }
        updated = self.workflow_store.update(
            "export_job",
            artifact_id,
            state,
            expected_version=int(record["version"]),
            actor=actor,
            replace=True,
        )
        return self._workflow_view(updated)

    def export_excel(self, *, actor: str | None = None) -> dict[str, Any]:
        path = generate_excel_export(self)
        return {
            "status": "completed",
            "format": "xlsx",
            **self._register_export(path, "xlsx", actor=actor),
            "synthetic": True,
            "detail_exported": False,
        }

    def export_powerbi(self, *, actor: str | None = None) -> dict[str, Any]:
        path = generate_powerbi_package(self)
        return {
            "status": "completed",
            "format": "powerbi-ready-zip",
            **self._register_export(path, "powerbi-ready-zip", actor=actor),
            "synthetic": True,
            "reconciliation_included": True,
        }

    def _refresh_demo_alert_evidence(
        self,
        response: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Overlay current durable lifecycle state on an immutable demo record."""

        refreshed = json_safe(response)
        evidence = dict(refreshed.get("evidence") or {})
        alert_envelope = dict(evidence.get("alerts") or {})
        stored_rows = list(alert_envelope.get("data") or [])
        current_rows: list[dict[str, Any]] = []
        for stored_row in stored_rows:
            row = dict(stored_row)
            alert_id = str(row.get("alert_id") or "").strip()
            if not alert_id:
                current_rows.append(row)
                continue
            try:
                current_rows.append(
                    self.alert_lifecycle.get(
                        alert_id,
                        selected_scope=row.get("selected_scope"),
                    )
                )
            except ObjectNotFound:
                current_rows.append(row)
        if not current_rows:
            return refreshed

        alert_envelope["data"] = current_rows
        evidence["alerts"] = alert_envelope
        refreshed["evidence"] = evidence
        refreshed["steps"] = [
            {
                **dict(step),
                "result": alert_envelope,
            }
            if int(dict(step).get("step_id") or 0) == 11
            else dict(step)
            for step in list(refreshed.get("steps") or [])
        ]
        return json_safe(refreshed)

    def run_demo(
        self,
        *,
        actor: str | None = None,
        source_context: SourceContext | Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run or reuse the deterministic governed 60-second portfolio story."""

        workflow_actor = actor or "workbench.service"
        if isinstance(source_context, SourceContext):
            context = source_context.public()
        elif source_context is not None:
            context = dict(source_context)
        else:
            assumed_mode = (
                DataMode.DEMO.value
                if self.config.profile.name == "test"
                else DataMode.OFFLINE_SNAPSHOT.value
            )
            context = {
                "active_mode": assumed_mode,
                "configured_mode": assumed_mode,
                "snapshot_date": self.data.manifest.get("maximum_data_date"),
                "configuration_hash": self.config.config_hash,
                "dataset_hash": sha256(self.data.run_id.encode()).hexdigest(),
                "dataset_hash_basis": "pipeline-run-id",
                "run_id": self.data.run_id,
                "synthetic": True,
                "reason": None,
            }
        active_mode = str(context.get("active_mode") or "")
        allowed_modes = {DataMode.DEMO.value, DataMode.OFFLINE_SNAPSHOT.value}
        if active_mode not in allowed_modes:
            raise ValueError(
                "Instant Demo requires approved DEMO or OFFLINE_SNAPSHOT evidence"
            )
        quality = self.data_quality()
        if not quality.get("publication_allowed"):
            raise ValueError("Instant Demo is blocked by the data-quality publication gate")

        selected_period = self.peak_deterioration_period()
        period = str(selected_period["period"])
        comparison_period = selected_period.get("comparison_period")
        unfiltered_root = self.root_cause(period=period)
        initial_finding = dict(unfiltered_root.get("finding") or {})
        primary_dimension = initial_finding.get("primary_dimension")
        # The governed headline remains an all-portfolio comparison. The leading
        # segment is explanatory evidence, not a filter to reapply to the result.
        story_filters: dict[str, str] = {}
        scope = {
            "reporting_period": period,
            "comparison_period": comparison_period,
            "filters": story_filters,
        }
        identity = {
            "mode": active_mode,
            "source_run_id": context.get("run_id") or self.data.run_id,
            "dataset_hash": context.get("dataset_hash"),
            "scope": scope,
        }
        demo_run_id = self._stable_record_id("DEMO", identity)
        workspace_id = self._stable_record_id("DEMO-WORKSPACE", identity)
        investigation_id = self._stable_record_id("DEMO-INV", identity)
        evidence_id = self._stable_record_id("EVIDENCE", identity)
        refresh_time = f"{period[:10]}T00:00:00+00:00"

        try:
            existing_demo = self.workflow_store.get(
                "configuration_change", demo_run_id
            )
        except ObjectNotFound:
            existing_demo = None
        if existing_demo is not None:
            if existing_demo["state"].get("record_kind") != "demo_run":
                raise DuplicateObject(
                    f"configuration_change/{demo_run_id} is not a demo run"
                )
            return self._refresh_demo_alert_evidence(
                {**self._workflow_view(existing_demo), "reused": True}
            )

        workspace_state = {
            "record_kind": "demo_workspace",
            "workspace_id": workspace_id,
            "workspace_name": "Approved 60-Second Portfolio Story",
            "owner": "Portfolio Risk Analytics",
            "workspace_type": "Approved deterministic sample",
            "business_question": "What changed, why, and what action is supported?",
            "reporting_period": period,
            "comparison_period": comparison_period,
            "selected_metrics": [
                row["metric_id"]
                for row in self.kpis(
                    period=period,
                    filters=story_filters,
                    source_context=context,
                )["data"]
            ],
            "selected_dimensions": (
                [str(primary_dimension)] if primary_dimension else []
            ),
            "selected_baskets": [],
            "selected_scenarios": ["Baseline", "Mild Downturn"],
            "selected_templates": ["MONTHLY_KPI_MOVEMENT"],
            "filter_configuration": story_filters,
            "visual_configuration": {"story_mode": "60_second_portfolio_story"},
            "commentary_configuration": {"provider": "deterministic_template"},
            "export_configuration": {"executive_pack": True},
            "status": "Approved sample",
            "approval_required": False,
            "evidence_id": evidence_id,
        }
        workspace_record = self._create_or_get_workflow(
            "workspace",
            workspace_id,
            workspace_state,
            actor=workflow_actor,
            approval_state="APPROVED",
            id_field="workspace_id",
        )
        workspace = self._workflow_view(workspace_record)

        command = self.command_centre(
            period=period,
            filters=story_filters,
            source_context=context,
            persist_alerts=False,
        )
        root = self.root_cause(period=period, filters=story_filters)
        vintages = self.vintages(period=period, filters=story_filters)
        strategy = self.strategy_comparison(period=period, filters=story_filters)
        alert_filters = {
            key: [value] if isinstance(value, str) else value
            for key, value in story_filters.items()
        }
        alerts = self.alerts(
            period=period,
            filters=alert_filters,
            source_context=context,
            persist_historical=True,
        )
        scenario_rows = self.scenarios(period=period)["data"]
        scenario = next(
            (row for row in scenario_rows if row.get("scenario_name") == "Mild Downturn"),
            scenario_rows[0] if scenario_rows else None,
        )

        root_finding = dict(root.get("finding") or initial_finding)
        investigation_state = {
            "record_kind": "demo_investigation",
            "investigation_id": investigation_id,
            "alert_id": alerts["data"][0]["alert_id"] if alerts.get("data") else None,
            "business_question": "What evidence explains the largest governed adverse movement?",
            "affected_metric": root_finding.get("metric_id")
            or selected_period.get("metric_id"),
            "hypothesis": (
                f"Investigate {root_finding.get('primary_driver')} within "
                f"{root_finding.get('primary_dimension')}."
                if root_finding.get("primary_driver")
                else "No single segment driver is asserted."
            ),
            "owner": "Portfolio Risk Analytics",
            "status": "New",
            "opened_timestamp": refresh_time,
            "audit_timestamp": refresh_time,
            "decision": None,
            "approval_required": True,
            "evidence_id": evidence_id,
            "demo_run_id": demo_run_id,
        }
        investigation_record = self._create_or_get_workflow(
            "investigation",
            investigation_id,
            investigation_state,
            actor=workflow_actor,
            id_field="investigation_id",
        )
        investigation = self._workflow_view(investigation_record)
        commentary = self.commentary(
            {"period": period},
            actor=workflow_actor,
            persist_alerts=False,
        )

        kpi_movements = [
            row
            for row in command.get("kpis", [])
            if row.get("absolute_change") is not None
        ]
        adverse = sorted(
            (row for row in kpi_movements if row.get("status") == "adverse"),
            key=lambda row: abs(float(row.get("relative_change") or 0.0)),
            reverse=True,
        )
        largest = adverse[0] if adverse else (kpi_movements[0] if kpi_movements else None)
        story = {
            "what_changed": (
                f"{largest['name']} moved by {largest['absolute_change']:+.6g} "
                f"{largest['unit']}."
                if largest
                else "No validated KPI movement is available for the selected scope."
            ),
            "why": (
                f"The largest descriptive contribution is {root_finding.get('primary_driver')} "
                f"within {root_finding.get('primary_dimension')}."
                if root_finding.get("primary_driver")
                else "No single descriptive driver passed the evidence contract."
            ),
            "uncertainties": [
                "Root-cause decomposition is associational, not causal.",
                "Scenario projections are planning estimates with synthetic assumptions.",
                "Human review and approval remain required before action.",
            ],
            "supported_action": investigation["business_question"],
            "evidence_produced": [
                "KPI movement",
                "root-cause decomposition",
                "vintage evidence",
                "strategy trade-off",
                "Early Warning signals",
                "scenario implication",
                "controlled commentary",
            ],
            "outputs_available": ["Executive Pack (PPTX)", "Excel", "Power BI-ready ZIP"],
        }
        outputs = [
            {
                "type": "executive_pack",
                "label": "Export Executive Pack",
                "status": "available",
                "request_url": "/api/v1/executive-packs/generate",
            },
            {
                "type": "excel",
                "label": "Export governed Excel evidence",
                "status": "available",
                "request_url": "/api/v1/exports/excel",
            },
            {
                "type": "powerbi",
                "label": "Export Power BI-ready evidence",
                "status": "available",
                "request_url": "/api/v1/exports/powerbi",
            },
        ]
        steps = [
            {"step_id": 1, "step": "Confirm current data mode", "result": context},
            {"step_id": 2, "step": "Load approved sample workspace", "result": workspace},
            {"step_id": 3, "step": "Set reporting period", "result": period},
            {"step_id": 4, "step": "Set comparison period", "result": comparison_period},
            {"step_id": 5, "step": "Retain governed all-portfolio scope", "result": story_filters},
            {"step_id": 6, "step": "Display data-quality status", "result": quality},
            {"step_id": 7, "step": "Reveal KPI movement", "result": command},
            {"step_id": 8, "step": "Reveal root-cause decomposition", "result": root},
            {"step_id": 9, "step": "Reveal vintage evidence", "result": vintages},
            {"step_id": 10, "step": "Reveal strategy trade-off", "result": strategy},
            {"step_id": 11, "step": "Reveal Early Warning signals", "result": alerts},
            {"step_id": 12, "step": "Show controlled scenario implication", "result": scenario},
            {"step_id": 13, "step": "Create or reuse governed investigation", "result": investigation},
            {"step_id": 14, "step": "Generate deterministic commentary", "result": commentary},
            {"step_id": 15, "step": "Offer validated outputs", "result": outputs},
        ]
        state = {
            "record_kind": "demo_run",
            "run_id": demo_run_id,
            "demo_run_id": demo_run_id,
            "status": "completed",
            "active_mode": active_mode,
            "source_context": context,
            "workspace": workspace,
            "scope": scope,
            "selected_period": selected_period,
            "data_quality": {
                "status": quality.get("status"),
                "publication_allowed": quality.get("publication_allowed"),
                "latest_available_month": quality.get("latest_available_month"),
                "completeness_percentage": quality.get("completeness_percentage"),
            },
            "story": story,
            "evidence": {
                "evidence_id": evidence_id,
                "command_centre": command,
                "root_cause": root,
                "vintages": vintages,
                "strategy_comparison": strategy,
                "alerts": alerts,
                "scenario": scenario,
            },
            "investigation": investigation,
            "commentary": commentary,
            "outputs": outputs,
            "steps": steps,
            "live_calculations": True,
            "hidden_hard_coded_results": False,
            "approval_required": True,
        }
        record = self.workflow_store.create(
            "configuration_change",
            demo_run_id,
            state,
            actor=workflow_actor,
            approval_state="DRAFT",
        )
        return {**self._workflow_view(record), "reused": False}

    def demo_status(self, run_id: str) -> dict[str, Any]:
        try:
            record = self.workflow_store.get("configuration_change", run_id)
        except ObjectNotFound as exc:
            raise KeyError(run_id) from exc
        if record["state"].get("record_kind") != "demo_run":
            raise KeyError(run_id)
        return self._refresh_demo_alert_evidence(
            {**self._workflow_view(record), "reused": True}
        )
