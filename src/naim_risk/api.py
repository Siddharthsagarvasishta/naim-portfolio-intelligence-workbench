"""Versioned FastAPI surface for validated nAIM analytics."""

from __future__ import annotations

import base64
import binascii
import json
import logging
import os
import secrets
import tempfile
import threading
import time
import uuid
import zipfile
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from naim_risk.auth import (
    AuthenticationError,
    AuthMode,
    AuthorizationError,
    AuthService,
    AuthSettings,
    Permission,
    Principal,
    Role,
)
from naim_risk.capabilities import capability_registry
from naim_risk.compat import environment_value
from naim_risk.config import (
    MODEL_ROOT,
    REPOSITORY_ROOT,
    NaimConfig,
    load_config,
    metric_display_contract,
    metric_lookup,
)
from naim_risk.executive_packs import (
    ExecutivePackError,
    executive_pack_record,
    generate_executive_pack,
    register_executive_pack_download,
    resolve_executive_pack_file,
)
from naim_risk.metrics.governance import data_source_diagnostics
from naim_risk.onboarding_errors import (
    FormulaSafetyError,
    OnboardingError,
    ProfileApprovalError,
    SourceSafetyError,
)
from naim_risk.pipeline import load_pipeline_data
from naim_risk.ratings import calculate_rating
from naim_risk.runtime_modes import DataMode, SourceContext, source_context
from naim_risk.security import (
    DownloadTokenError,
    DownloadTokenService,
    SlidingWindowRateLimiter,
    opaque_rate_limit_key,
)
from naim_risk.service import WorkbenchService, json_safe
from naim_risk.storage import latest_manifest
from naim_risk.types import PipelineData
from naim_risk.workflow import (
    ConcurrencyConflict,
    DuplicateObject,
    ObjectNotFound,
    WorkflowStore,
)

load_dotenv(REPOSITORY_ROOT / ".env", override=False)

logger = logging.getLogger("naim.api")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
logger.setLevel(
    getattr(logging, (environment_value("NAIM_LOG_LEVEL", "INFO") or "INFO").upper(), logging.INFO)
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScenarioRunRequest(StrictModel):
    scenario_name: str = "Baseline"
    custom_assumptions: dict[str, float] | None = None
    horizon_months: int = Field(default=12, ge=1, le=24)
    reporting_month: str | None = None


class CommentaryRequest(StrictModel):
    period: str | None = None
    commentary_type: str = "monthly executive commentary"


class AlertAcknowledgeRequest(StrictModel):
    expected_version: int = Field(ge=1)
    note: str = Field(min_length=1, max_length=2000)


class AlertTransitionRequest(StrictModel):
    expected_version: int = Field(ge=1)
    target_status: Literal[
        "ACKNOWLEDGED",
        "INVESTIGATING",
        "ACTION_PROPOSED",
        "MONITORING",
        "RESOLVED",
        "SUPPRESSED",
        "CLOSED_AS_NOISE",
    ]
    reason: str = Field(min_length=1, max_length=2000)
    owner: str | None = Field(default=None, min_length=1, max_length=200)
    related_investigation: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )
    suppression_until_period: str | None = Field(
        default=None,
        pattern=r"^\d{4}-\d{2}(?:-\d{2})?$",
    )


class AlertInvestigationRequest(StrictModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2000)
    owner: str | None = Field(default=None, min_length=1, max_length=200)


class InvestigationCreate(StrictModel):
    alert_id: str | None = None
    business_question: str
    affected_metric: str | None = None
    hypothesis: str | None = None
    owner: str = "Unassigned"


class InvestigationUpdate(StrictModel):
    expected_version: int | None = Field(default=None, ge=1)
    owner: str | None = None
    status: str | None = None
    hypothesis: str | None = None
    supporting_evidence: str | None = None
    action_taken: str | None = None
    resolution: str | None = None
    reviewer: str | None = None
    decision: str | None = None


class BasketCreate(StrictModel):
    basket_name: str
    basket_type: str = "account"
    entity_type: str = "account"
    basket_description: str = ""
    basket_expression: str = ""
    members: list[str] = Field(default_factory=list)
    locked_flag: bool = False


class BasketUpdate(StrictModel):
    expected_version: int | None = Field(default=None, ge=1)
    basket_name: str | None = None
    basket_description: str | None = None
    basket_expression: str | None = None
    members: list[str] | None = None
    locked_flag: bool | None = None


class BasketCombineRequest(StrictModel):
    left_members: list[str]
    right_members: list[str]
    operation: str = Field(pattern="^(union|intersection|subtract)$")


class BasketImpactRequest(StrictModel):
    original_members: list[str]
    revised_members: list[str]


class CapacityScenarioRequest(StrictModel):
    volume_multiplier: float = Field(default=1.0, ge=0.5, le=3.0)
    capacity_multiplier: float = Field(default=1.0, ge=0.1, le=2.0)
    handling_time_multiplier: float = Field(default=1.0, ge=0.5, le=3.0)
    review_threshold_change: float = Field(default=0.0, ge=-0.5, le=0.5)


class NetworkImpactRequest(StrictModel):
    node_id: str


class RatingRequest(StrictModel):
    rating_type: str = Field(pattern="^(partner|vendor|membership)$")
    components: dict[str, float | None]


class RatingSensitivityRequest(RatingRequest):
    weight_overrides: dict[str, float] = Field(default_factory=dict)


class PartnerScenarioRequest(StrictModel):
    partner_id: str
    volume_multiplier: float = Field(default=1.0, ge=0.1, le=3.0)
    fraud_loss_multiplier: float = Field(default=1.0, ge=0.0, le=5.0)
    credit_loss_multiplier: float = Field(default=1.0, ge=0.0, le=5.0)
    attrition_multiplier: float = Field(default=1.0, ge=0.0, le=5.0)
    reporting_month: str | None = None


class VendorReallocationRequest(StrictModel):
    source_vendor_id: str
    target_vendor_id: str
    reallocation_share: float = Field(default=0.1, gt=0.0, le=1.0)
    reporting_month: str | None = None


class WorkspaceCreate(StrictModel):
    workspace_name: str
    business_question: str
    owner: str = "Unassigned"
    workspace_type: str = "Ad hoc analysis"
    reporting_period: str | None = None
    comparison_period: str | None = None
    selected_metrics: list[str] = Field(default_factory=list)
    selected_dimensions: list[str] = Field(default_factory=list)
    selected_baskets: list[str] = Field(default_factory=list)
    selected_scenarios: list[str] = Field(default_factory=lambda: ["Baseline"])
    selected_templates: list[str] = Field(default_factory=lambda: ["MONTHLY_KPI_MOVEMENT"])
    filter_configuration: dict[str, Any] = Field(default_factory=dict)
    visual_configuration: dict[str, Any] = Field(default_factory=dict)
    commentary_configuration: dict[str, Any] = Field(
        default_factory=lambda: {"provider": "template"}
    )
    export_configuration: dict[str, Any] = Field(default_factory=dict)


class WorkspaceUpdate(StrictModel):
    expected_version: int | None = Field(default=None, ge=1)
    workspace_name: str | None = None
    business_question: str | None = None
    owner: str | None = None
    workspace_type: str | None = None
    reporting_period: str | None = None
    comparison_period: str | None = None
    selected_metrics: list[str] | None = None
    selected_dimensions: list[str] | None = None
    selected_baskets: list[str] | None = None
    selected_scenarios: list[str] | None = None
    selected_templates: list[str] | None = None
    filter_configuration: dict[str, Any] | None = None
    visual_configuration: dict[str, Any] | None = None
    commentary_configuration: dict[str, Any] | None = None
    export_configuration: dict[str, Any] | None = None


class PeerMatchRequest(StrictModel):
    entity_type: str = Field(pattern="^(partner|vendor|membership)$")
    entity_id: str
    peer_count: int = Field(default=3, ge=1, le=20)
    comparison_metric: str | None = None


class AnalysisTemplateRunRequest(StrictModel):
    template_id: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class LoginRequest(StrictModel):
    username: str = Field(min_length=3, max_length=128)
    password: str = Field(min_length=1, max_length=1024)


class OptimisationItem(StrictModel):
    name: str = Field(min_length=1, max_length=128)
    baseline: float = Field(ge=0)
    minimum: float = Field(default=0, ge=0)
    maximum: float = Field(default=1, ge=0)
    eligible: bool = True
    expected_profit: float = 0
    expected_loss: float = 0
    fraud_bps: float = 0
    customer_friction: float = 0
    vendor_cost: float = 0
    review_load: float = 0
    customer_coverage: float = 0
    regional_service: float = 0


class OptimisationConstraints(StrictModel):
    allocation_total: float = Field(default=1, gt=0)
    loss_rate_max: float | None = None
    fraud_bps_max: float | None = None
    friction_max: float | None = None
    review_capacity_max: float | None = None
    vendor_cost_max: float | None = None
    concentration_limit: float | None = Field(default=None, gt=0)
    minimum_customer_coverage: float | None = None
    regional_service_min: float | None = None


class OptimisationRunRequest(StrictModel):
    decision_dimension: str
    objective: str
    items: list[OptimisationItem] = Field(min_length=2)
    constraints: OptimisationConstraints = Field(default_factory=OptimisationConstraints)
    weights: dict[str, float] = Field(default_factory=dict)
    save_scenario: bool = False


class MarketRiskRunRequest(StrictModel):
    instrument: Literal["NAIM-DEMO-INDEX", "NAIM-DEMO-EQUITY"] = "NAIM-DEMO-INDEX"
    period: Literal["one_year", "three_years", "five_years", "custom"] = "three_years"
    start_date: date | None = None
    end_date: date = date(2025, 12, 31)
    frequency: Literal["daily", "weekly", "monthly"] = "daily"
    return_type: Literal["simple", "log"] = "log"
    windows: tuple[int, ...] = (21, 63, 126, 252)
    ewma_decay: float = Field(default=0.94, gt=0, lt=1)
    confidence: float = Field(default=0.99, gt=0.5, lt=1)
    option_inputs: dict[str, Any] | None = None


class MarketRiskExportRequest(MarketRiskRunRequest):
    include_excel: bool = True
    include_presentation: bool = True


class SurvivalRunRequest(StrictModel):
    records: list[dict[str, Any]] | None = None
    group_column: str | None = "risk_group"
    outcomes: dict[str, tuple[str, str]] | None = None
    confidence: float = Field(default=0.95, gt=0.5, lt=1)


class BehaviouralRunRequest(StrictModel):
    records: list[dict[str, Any]] | None = None
    account_column: str = "account_id"
    time_column: str = "month"
    target_column: str = "next_month_delinquent"
    current_delinquency_column: str = "days_past_due"
    feature_columns: list[str] | None = None
    segment_column: str | None = "risk_group"
    seed: int = 73421


class ChangePointRunRequest(StrictModel):
    series: list[float] | None = None
    metric_id: str = "ANNUALISED_NET_LOSS_RATE"
    min_segment: int = Field(default=12, ge=6, le=120)
    seasonal_period: int | None = Field(default=None, ge=2, le=60)
    significance: float = Field(default=0.05, ge=0.001, le=0.20)
    minimum_robust_effect: float = Field(default=1.5, gt=0)


class PropensityRunRequest(StrictModel):
    records: list[dict[str, Any]] = Field(min_length=40, max_length=100_000)
    treatment_column: str
    outcome_column: str
    covariates: list[str] = Field(min_length=1, max_length=100)
    trim_quantile: float = Field(default=0.99, ge=0.90, lt=1)
    seed: int = 73421


class DifferenceInDifferencesRunRequest(StrictModel):
    records: list[dict[str, Any]] = Field(min_length=40, max_length=100_000)
    outcome_column: str
    treatment_column: str
    time_column: str
    policy_date: str
    cluster_column: str | None = None
    synthetic_policy_use_case: bool = False


class PresentationGenerateRequest(StrictModel):
    workspace_id: str | None = None
    reporting_period: str | None = None
    comparison_period: str | None = None
    basket_id: str | None = None
    scenario_name: str = "Baseline"
    presentation_template: str = Field(
        default="executive_review",
        pattern="^(executive_review|risk_committee|portfolio_deep_dive)$",
    )
    selected_sections: list[str] = Field(
        default_factory=lambda: [
            "executive_summary",
            "kpis",
            "root_cause",
            "partners",
            "decision_log",
        ]
    )
    detail_level: str = Field(default="standard", pattern="^(summary|standard|detailed)$")
    include_appendix: bool = True
    speaker_notes: bool = True
    commentary_length: int = Field(default=450, ge=100, le=2000)


class ExecutivePackGenerateRequest(StrictModel):
    workspace_id: str | None = None
    reporting_period: str | None = None
    comparison_period: str | None = None
    filter_scope: dict[str, Any] = Field(default_factory=dict)
    include_pdf: bool = False


class OnboardingSource(StrictModel):
    source_id: str
    kind: Literal["csv", "xlsx", "parquet", "json", "sqlite", "duckdb", "postgresql"]
    display_name: str
    relative_path: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)
    sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    table: str | None = None
    sheet: str | int | None = None
    url_env: str | None = None


class OnboardingUploadRequest(StrictModel):
    filename: str = Field(min_length=1, max_length=255)
    content_base64: str = Field(min_length=1)


class OnboardingSelectRequest(StrictModel):
    relative_path: str = Field(min_length=1, max_length=1024)
    table: str | None = None
    sheet: str | int | None = None


class OnboardingPostgresRequest(StrictModel):
    url_env: str
    table: str


class OnboardingTableRequest(StrictModel):
    source: OnboardingSource
    table: str


class OnboardingPreviewRequest(StrictModel):
    source: OnboardingSource
    sample_rows: int = Field(default=50, ge=1, le=200)


class OnboardingMappingRequest(StrictModel):
    source: OnboardingSource
    contract_id: str
    mapping: dict[str, str]
    transformations: dict[str, str] = Field(default_factory=dict)


class OnboardingValidationRequest(OnboardingMappingRequest):
    max_error_rate: float = Field(default=0, ge=0, le=1)


class OnboardingProfileCreateRequest(OnboardingValidationRequest):
    profile_id: str


class OnboardingLoadRequest(StrictModel):
    profile_id: str
    source: OnboardingSource
    expected_version: int | None = Field(default=None, ge=1)


class OnboardingApprovalRequest(StrictModel):
    expected_version: int = Field(ge=1)
    rationale: str = Field(min_length=1, max_length=2000)


_service: WorkbenchService | None = None
_service_lock = threading.Lock()
_workflow_store: WorkflowStore | None = None
_workflow_store_key: str | None = None
_auth_service: AuthService | None = None
_auth_service_key: tuple[str | None, ...] | None = None
_state_lock = threading.RLock()
_source_context_cache: tuple[tuple[str | None, ...], SourceContext] | None = None
_request_limiter: SlidingWindowRateLimiter | None = None
_request_limiter_key: tuple[str | None, str | None] | None = None
_download_token_service: DownloadTokenService | None = None
_download_token_key: tuple[str | None, str | None, str | None] | None = None
_ephemeral_download_secret = secrets.token_bytes(32)
_bearer = HTTPBearer(auto_error=False)


def runtime_config_from_environment() -> NaimConfig:
    """Resolve the documented runtime profile, seed and data directory."""

    profile = environment_value("NAIM_DATASET_PROFILE", "default") or "default"
    data_root = Path(environment_value("NAIM_DATA_DIR", str(REPOSITORY_ROOT / "data")) or "data")
    if not data_root.is_absolute():
        data_root = REPOSITORY_ROOT / data_root
    seed_value = environment_value("NAIM_RANDOM_SEED")
    seed = int(seed_value) if seed_value is not None else None
    return load_config(profile, seed=seed, data_root=data_root)


def matching_persisted_pipeline(config: NaimConfig) -> PipelineData | None:
    """Load a complete, matching persisted run without trusting foreign paths."""

    manifest_path = latest_manifest(config.data_root)
    if manifest_path is None:
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected = {
            "profile": config.profile.name,
            "random_seed": config.seed,
            "configuration_hash": config.config_hash,
        }
        if any(manifest.get(key) != value for key, value in expected.items()):
            return None
        if not manifest.get("publication_allowed"):
            return None
        data_root = config.data_root.resolve()
        for key, value in manifest.get("paths", {}).items():
            if not (key.startswith("validated.") or key.startswith("mart.")):
                continue
            referenced = Path(value)
            if not referenced.is_absolute():
                referenced = manifest_path.parent / referenced
            if not referenced.resolve().is_relative_to(data_root):
                logger.warning(
                    json.dumps(
                        {
                            "level": "WARNING",
                            "event": "persisted_run_rejected",
                            "reason": "manifest_path_outside_data_root",
                            "manifest": manifest_path.name,
                        }
                    )
                )
                return None
        loaded = load_pipeline_data(manifest_path)
        required_tables = {
            "customer_account_master",
            "monthly_account_performance",
            "partner_master",
            "partner_contract",
            "partner_monthly_performance",
            "vendor_master",
            "vendor_contract",
            "vendor_monthly_performance",
            "membership_master",
            "customer_membership_history",
            "benefit_master",
            "benefit_usage_fact",
            "portfolio_basket_definition",
            "portfolio_basket_membership",
            "workspace_definition",
        }
        if not required_tables.issubset(loaded.tables):
            return None
        return loaded
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        logger.exception(
            json.dumps(
                {
                    "level": "WARNING",
                    "event": "persisted_run_rejected",
                    "reason": "manifest_load_failure",
                    "manifest": manifest_path.name,
                }
            )
        )
        return None


def get_service() -> WorkbenchService:
    """Return one process-wide service without duplicate cold-start generation."""

    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                config = runtime_config_from_environment()
                _service = WorkbenchService(
                    config,
                    matching_persisted_pipeline(config),
                    workflow_store=get_workflow_store(),
                )
    return _service


def get_workflow_store() -> WorkflowStore:
    """Return durable mutable state using SQLite or the configured PostgreSQL URL."""

    global _workflow_store, _workflow_store_key
    configured_url = os.getenv("NAIM_DATABASE_URL")
    if configured_url:
        database_url = configured_url
    else:
        database_path = (
            runtime_config_from_environment().data_root / "state" / "naim_workflow.sqlite3"
        ).resolve()
        database_url = f"sqlite+pysqlite:///{database_path}"
    if _workflow_store is None or _workflow_store_key != database_url:
        with _state_lock:
            if _workflow_store is None or _workflow_store_key != database_url:
                if _workflow_store is not None:
                    _workflow_store.close()
                _workflow_store = WorkflowStore(database_url)
                _workflow_store_key = database_url
    return _workflow_store


def _auth_environment_key() -> tuple[str | None, ...]:
    names = (
        "NAIM_AUTH_MODE",
        "AUTH_MODE",
        "NAIM_TOKEN_SECRET",
        "NAIM_TOKEN_TTL_SECONDS",
        "NAIM_TOKEN_ISSUER",
        "NAIM_TOKEN_AUDIENCE",
        "NAIM_OIDC_ISSUER",
        "NAIM_OIDC_AUDIENCE",
        "NAIM_OIDC_JWKS_URL",
        "NAIM_OIDC_ROLE_CLAIM",
        "NAIM_DATABASE_URL",
    )
    return tuple(os.getenv(name) for name in names)


def get_auth_service() -> AuthService:
    """Return the configured backend authentication and authorization service."""

    global _auth_service, _auth_service_key
    key = _auth_environment_key()
    if _auth_service is None or _auth_service_key != key:
        with _state_lock:
            if _auth_service is None or _auth_service_key != key:
                _auth_service = AuthService(AuthSettings.from_environment(), get_workflow_store())
                _auth_service_key = key
    return _auth_service


def _source_environment_key() -> tuple[str | None, ...]:
    names = (
        "NAIM_DATA_MODE",
        "NAIM_DATASET_PROFILE",
        "NAIM_RANDOM_SEED",
        "NAIM_DATA_DIR",
    )
    return tuple(os.getenv(name) for name in names)


def get_source_context() -> SourceContext:
    """Return cached, portable provenance for the active dataset selection."""

    global _source_context_cache
    key = _source_environment_key()
    if _source_context_cache is None or _source_context_cache[0] != key:
        with _state_lock:
            if _source_context_cache is None or _source_context_cache[0] != key:
                try:
                    context = source_context(runtime_config_from_environment())
                except ValueError as exc:
                    context = SourceContext(
                        active_mode=DataMode.UNAVAILABLE,
                        configured_mode=DataMode.UNAVAILABLE,
                        snapshot_date=None,
                        configuration_hash=None,
                        dataset_hash=None,
                        dataset_hash_basis=None,
                        run_id=None,
                        synthetic=None,
                        reason=str(exc),
                    )
                _source_context_cache = (key, context)
    return _source_context_cache[1]


def _server_observable_manifest(context: SourceContext) -> dict[str, Any]:
    """Read snapshot facts without forcing the analytical service to initialise."""

    if _service is not None:
        return dict(_service.data.manifest)
    try:
        config = runtime_config_from_environment()
        manifest_path = latest_manifest(config.data_root)
        if manifest_path is not None:
            return json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        logger.exception(
            json.dumps(
                {
                    "level": "WARNING",
                    "event": "snapshot_diagnostics_unavailable",
                    "reason": "manifest_read_failure",
                }
            )
        )
    return {
        "run_id": context.run_id,
        "configuration_hash": context.configuration_hash,
        "maximum_data_date": context.snapshot_date,
        "synthetic_data": context.synthetic,
    }


def get_presentation_output_root() -> Path:
    """Return the governed server-side presentation directory."""

    return (REPOSITORY_ROOT / "outputs" / "presentations").resolve()


def get_executive_pack_output_root() -> Path:
    """Return the configured governed generated-export directory."""

    return (runtime_config_from_environment().data_root / "generated_exports").resolve()


def get_tableau_output_path() -> Path:
    """Return the governed Tableau Hyper extract path."""

    return (REPOSITORY_ROOT / "outputs" / "tableau" / "nAIM_Portfolio_Intelligence.hyper").resolve()


def get_onboarding_studio(
    store: WorkflowStore = Depends(get_workflow_store),
) -> Any:
    """Return a governed onboarding facade below the selected durable data root."""

    from naim_risk.onboarding import OnboardingStudio

    root = (runtime_config_from_environment().data_root / "onboarding").resolve()
    return OnboardingStudio(root, workflow_store=store)


def get_request_limiter() -> SlidingWindowRateLimiter:
    """Return the configured single-node sliding-window request limiter."""

    global _request_limiter, _request_limiter_key
    key = (os.getenv("NAIM_RATE_LIMIT_REQUESTS"), os.getenv("NAIM_RATE_LIMIT_WINDOW_SECONDS"))
    if _request_limiter is None or _request_limiter_key != key:
        limit = int(key[0] or "600")
        window_seconds = int(key[1] or "60")
        if not 1 <= limit <= 100_000 or not 1 <= window_seconds <= 3600:
            raise ValueError("Request rate-limit settings are outside governed bounds")
        _request_limiter = SlidingWindowRateLimiter(limit, window_seconds)
        _request_limiter_key = key
    return _request_limiter


def get_download_token_service() -> DownloadTokenService:
    """Return an expiring token service; local disabled-auth mode uses a process-only secret."""

    global _download_token_service, _download_token_key
    key = (
        os.getenv("NAIM_DOWNLOAD_TOKEN_SECRET"),
        os.getenv("NAIM_TOKEN_SECRET"),
        os.getenv("NAIM_DOWNLOAD_TOKEN_TTL_SECONDS"),
    )
    if _download_token_service is None or _download_token_key != key:
        configured_secret = key[0] or key[1]
        secret = (
            configured_secret.encode("utf-8") if configured_secret else _ephemeral_download_secret
        )
        ttl_seconds = int(key[2] or "300")
        _download_token_service = DownloadTokenService(secret, ttl_seconds=ttl_seconds)
        _download_token_key = key
    return _download_token_service


def _tokenized_url(
    path: str,
    resource: str,
    principal: Principal,
    token_service: DownloadTokenService,
) -> str:
    return f"{path}?download_token={token_service.issue(resource, principal.username)}"


def _verify_download_token(
    token: str,
    resource: str,
    principal: Principal,
    token_service: DownloadTokenService,
) -> None:
    try:
        token_service.verify(token, resource, principal.username)
    except DownloadTokenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def reset_application_state() -> None:
    """Dispose process singletons between isolated tests and controlled restarts."""

    global _service, _workflow_store, _workflow_store_key
    global _auth_service, _auth_service_key, _source_context_cache
    global _request_limiter, _request_limiter_key
    global _download_token_service, _download_token_key
    with _state_lock:
        _service = None
        _auth_service = None
        _auth_service_key = None
        _source_context_cache = None
        if _request_limiter is not None:
            _request_limiter.clear()
        _request_limiter = None
        _request_limiter_key = None
        _download_token_service = None
        _download_token_key = None
        if _workflow_store is not None:
            _workflow_store.close()
        _workflow_store = None
        _workflow_store_key = None


def get_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    auth_service: AuthService = Depends(get_auth_service),
) -> Principal:
    """Authenticate the current bearer token or explicit disabled-mode principal."""

    token = credentials.credentials if credentials is not None else None
    return auth_service.principal(token)


def require_permission(permission: Permission) -> Callable[..., Principal]:
    """Build an endpoint dependency that enforces a backend role permission."""

    def dependency(
        principal: Principal = Depends(get_principal),
        auth_service: AuthService = Depends(get_auth_service),
    ) -> Principal:
        return auth_service.require(principal, permission)

    return dependency


def common_filters(
    product: list[str] | None = Query(default=None),
    customer_segment: list[str] | None = Query(default=None),
    acquisition_channel: list[str] | None = Query(default=None),
    geography: list[str] | None = Query(default=None),
    risk_band: list[str] | None = Query(default=None),
    strategy: list[str] | None = Query(default=None),
    model_version: list[str] | None = Query(default=None),
    partner: list[str] | None = Query(default=None),
    vendor: list[str] | None = Query(default=None),
    membership_tier: list[str] | None = Query(default=None),
) -> dict[str, Any]:
    mapping = {
        "product_type": product,
        "customer_segment": customer_segment,
        "acquisition_channel": acquisition_channel,
        "geography": geography,
        "original_risk_band": risk_band,
        "strategy_version": strategy,
        "model_version": model_version,
        "partner_id": partner,
        "vendor_id": vendor,
        "membership_tier_id": membership_tier,
    }
    return {key: value for key, value in mapping.items() if value}


def paginate(payload: dict[str, Any], page: int, page_size: int) -> dict[str, Any]:
    if not isinstance(payload.get("data"), list):
        return payload
    rows = payload["data"]
    start = (page - 1) * page_size
    return {
        **payload,
        "data": rows[start : start + page_size],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": len(rows),
            "pages": (len(rows) + page_size - 1) // page_size,
        },
    }


def _records_frame(records: list[dict[str, Any]]) -> pd.DataFrame:
    if not records:
        raise ValueError("At least one analytical record is required")
    if len(records) > 100_000:
        raise ValueError("Advanced-statistics requests are limited to 100,000 records")
    frame = pd.DataFrame.from_records(records)
    if frame.empty or frame.columns.duplicated().any():
        raise ValueError("Analytical records must form a non-empty table with unique columns")
    return frame


def _market_risk_analysis(payload: MarketRiskRunRequest) -> tuple[Any, dict[str, Any]]:
    from naim_risk.market_risk.analytics import run_market_risk_lab
    from naim_risk.market_risk.providers import (
        DeterministicSampleProvider,
        InstrumentSelection,
    )

    if payload.period == "custom":
        if payload.start_date is None:
            raise ValueError("A custom market-risk period requires start_date")
        selection = InstrumentSelection(
            payload.instrument,
            "index" if payload.instrument.endswith("INDEX") else "equity",
            payload.start_date,
            payload.end_date,
            "custom",
        )
    else:
        selection = InstrumentSelection.trailing_period(
            instrument=payload.instrument,
            instrument_type="index" if payload.instrument.endswith("INDEX") else "equity",
            end_date=payload.end_date,
            period=payload.period,
        )
    market = DeterministicSampleProvider().get_prices(
        selection.instrument,
        selection.start_date,
        selection.end_date,
        ["open", "high", "low", "close", "adjusted_close", "volume"],
    )
    result = run_market_risk_lab(
        market,
        frequency=payload.frequency,
        return_type=payload.return_type,
        windows=payload.windows,
        ewma_decay=payload.ewma_decay,
        confidence=payload.confidence,
        option_inputs=payload.option_inputs,
    )
    result["evidence_id"] = f"MRISK-{market.raw_source_sha256[:20].upper()}"
    result["approval_required"] = True
    result["synthetic"] = True
    return market, result


def _portfolio_survival_frame(service: WorkbenchService) -> pd.DataFrame:
    history = service.tables["monthly_account_performance"].copy()
    master = service.tables["customer_account_master"][["account_id", "original_risk_band"]]
    history = history.merge(master, on="account_id", how="left").sort_values(
        ["account_id", "month"]
    )
    history["risk_group"] = (
        history["original_risk_band"]
        .astype(str)
        .str[:1]
        .map(lambda value: "Lower-to-moderate" if value in {"A", "B", "C"} else "Elevated")
    )
    rows: list[dict[str, Any]] = []
    for account_id, group in history.groupby("account_id", sort=True):
        maximum_duration = int(group["months_on_book"].max())
        attrition = group[group["attrition_flag"] == 1]
        delinquency = group[group["days_past_due"] >= 30]
        rows.append(
            {
                "account_id": account_id,
                "risk_group": str(group["risk_group"].iloc[0]),
                "time_to_attrition": (
                    int(attrition["months_on_book"].iloc[0])
                    if not attrition.empty
                    else maximum_duration
                ),
                "attrition_event": int(not attrition.empty),
                "time_to_first_30_plus_delinquency": (
                    int(delinquency["months_on_book"].iloc[0])
                    if not delinquency.empty
                    else maximum_duration
                ),
                "delinquency_30_event": int(not delinquency.empty),
            }
        )
    return pd.DataFrame(rows)


def _portfolio_behavioural_frame(service: WorkbenchService) -> pd.DataFrame:
    history = service.tables["monthly_account_performance"].copy()
    master = service.tables["customer_account_master"][["account_id", "original_risk_band"]]
    history = history.merge(master, on="account_id", how="left")
    history["risk_group"] = (
        history["original_risk_band"]
        .astype(str)
        .str[:1]
        .map(lambda value: "Lower-to-moderate" if value in {"A", "B", "C"} else "Elevated")
    )
    return history


app = FastAPI(
    title="nAIM Portfolio Intelligence Workbench API",
    version="1.0.0",
    description=(
        "Versioned API for synthetic, institution-neutral portfolio-risk analytics. "
        "All recommendations require human review."
    ),
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=(
        environment_value("NAIM_ALLOWED_ORIGINS", "http://localhost:3000")
        or "http://localhost:3000"
    ).split(","),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)


@app.middleware("http")
async def request_context(request: Request, call_next: Any) -> Response:
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    started = time.perf_counter()
    rate_decision = None
    response: Response | None = None
    if request.url.path.startswith("/api/"):
        client_host = request.client.host if request.client is not None else "unknown"
        rate_key = opaque_rate_limit_key(client_host, request.headers.get("Authorization"))
        rate_decision = get_request_limiter().check(rate_key)
        if not rate_decision.allowed:
            response = JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": "Request rate limit exceeded",
                    }
                },
                headers={"Retry-After": str(rate_decision.retry_after_seconds)},
            )

    if response is None and request.method in {"POST", "PUT", "PATCH"}:
        max_bytes = int(os.getenv("NAIM_MAX_REQUEST_BYTES", str(10 * 1024 * 1024)))
        if not 1024 <= max_bytes <= 100 * 1024 * 1024:
            raise ValueError("NAIM_MAX_REQUEST_BYTES is outside governed bounds")
        declared_length = request.headers.get("Content-Length")
        if declared_length is not None and int(declared_length) > max_bytes:
            response = JSONResponse(
                status_code=413,
                content={
                    "error": {
                        "code": "REQUEST_TOO_LARGE",
                        "message": f"Request body exceeds the {max_bytes}-byte limit",
                    }
                },
            )
        elif declared_length is None:
            body = await request.body()
            if len(body) > max_bytes:
                response = JSONResponse(
                    status_code=413,
                    content={
                        "error": {
                            "code": "REQUEST_TOO_LARGE",
                            "message": f"Request body exceeds the {max_bytes}-byte limit",
                        }
                    },
                )

    if response is None:
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                json.dumps(
                    {
                        "timestamp": time.time(),
                        "level": "ERROR",
                        "request_id": request_id,
                        "module": "api",
                        "event": "request_failed",
                        "path": request.url.path,
                    }
                )
            )
            raise
    context = get_source_context()
    if (
        request.url.path.startswith("/api/v1")
        and response.status_code != 204
        and "application/json" in response.headers.get("content-type", "")
    ):
        if hasattr(response, "body_iterator"):
            body = b"".join([chunk async for chunk in response.body_iterator])
        else:
            body = bytes(getattr(response, "body", b""))
        try:
            payload = json.loads(body)
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = None
        if isinstance(payload, dict):
            payload["data_mode"] = context.active_mode.value
            payload["source_context"] = context.public()
            preserved_headers = {
                key: value
                for key, value in response.headers.items()
                if key.lower() not in {"content-length", "content-type"}
            }
            response = JSONResponse(
                content=payload,
                status_code=response.status_code,
                headers=preserved_headers,
                background=response.background,
            )

    duration_ms = (time.perf_counter() - started) * 1000.0
    response.headers["X-Request-ID"] = request_id
    response.headers["X-nAIM-Data-Mode"] = context.active_mode.value
    response.headers["Cache-Control"] = "no-store"
    if request.url.path in {"/api/docs", "/api/redoc"}:
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; script-src https://cdn.jsdelivr.net; "
            "style-src 'unsafe-inline' https://cdn.jsdelivr.net; img-src data: https:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
    else:
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
    response.headers["Permissions-Policy"] = "camera=(), geolocation=(), microphone=()"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    if rate_decision is not None:
        response.headers["X-RateLimit-Limit"] = str(rate_decision.limit)
        response.headers["X-RateLimit-Remaining"] = str(rate_decision.remaining)
    logger.info(
        json.dumps(
            {
                "timestamp": time.time(),
                "level": "INFO",
                "request_id": request_id,
                "module": "api",
                "event": "request_completed",
                "path": request.url.path,
                "method": request.method,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 3),
            }
        )
    )
    return response


@app.exception_handler(AuthenticationError)
async def authentication_error_handler(_: Request, exc: AuthenticationError) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={"error": {"code": "AUTHENTICATION_REQUIRED", "message": str(exc)}},
        headers={"WWW-Authenticate": "Bearer"},
    )


@app.exception_handler(AuthorizationError)
async def authorization_error_handler(_: Request, exc: AuthorizationError) -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={"error": {"code": "PERMISSION_DENIED", "message": str(exc)}},
    )


@app.exception_handler(ConcurrencyConflict)
async def concurrency_conflict_handler(_: Request, exc: ConcurrencyConflict) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={"error": {"code": "STALE_VERSION", "message": str(exc)}},
    )


@app.exception_handler(DuplicateObject)
async def duplicate_object_handler(_: Request, exc: DuplicateObject) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={"error": {"code": "DUPLICATE_OBJECT", "message": str(exc)}},
    )


@app.exception_handler(ObjectNotFound)
async def object_not_found_handler(_: Request, exc: ObjectNotFound) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"error": {"code": "OBJECT_NOT_FOUND", "message": str(exc)}},
    )


@app.exception_handler(ProfileApprovalError)
async def profile_approval_error_handler(_: Request, exc: ProfileApprovalError) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={"error": {"code": "PROFILE_NOT_APPROVABLE", "message": str(exc)}},
    )


@app.exception_handler(OnboardingError)
async def onboarding_error_handler(_: Request, exc: OnboardingError) -> JSONResponse:
    code = (
        "UNSAFE_ONBOARDING_REQUEST"
        if isinstance(exc, (SourceSafetyError, FormulaSafetyError))
        else "ONBOARDING_VALIDATION_FAILED"
    )
    return JSONResponse(
        status_code=422,
        content={"error": {"code": code, "message": str(exc)}},
    )


@app.exception_handler(ValueError)
async def value_error_handler(_: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "INVALID_ANALYTICAL_REQUEST", "message": str(exc)}},
    )


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "name": "nAIM Portfolio Intelligence Workbench",
        "pronunciation": "name",
        "aim_expansion": "All Is Mine",
        "tagline": "Name the movement. Own the evidence.",
        "synthetic": True,
        "documentation": "/api/docs",
        "health": "/api/v1/health",
    }


@app.get("/api/v1/health")
def health() -> dict[str, Any]:
    context = get_source_context()
    available = context.active_mode is not DataMode.UNAVAILABLE
    return {
        "status": "healthy" if available else "degraded",
        "publication_allowed": available and context.reason is None,
        "quality_status": "PASS" if available and context.reason is None else "UNAVAILABLE",
        "run_id": context.run_id,
        "service_initialised": _service is not None,
    }


@app.get("/api/v1/data-source")
def data_source(context: SourceContext = Depends(get_source_context)) -> dict[str, Any]:
    stale_after_seconds = int(os.getenv("NAIM_SNAPSHOT_STALE_AFTER_SECONDS", "86400"))
    current_configuration_hash = runtime_config_from_environment().config_hash
    diagnostics = data_source_diagnostics(
        context=context,
        manifest=_server_observable_manifest(context),
        stale_after_seconds=stale_after_seconds,
        current_governed_configuration_hash=current_configuration_hash,
    )
    return {
        "mode": context.active_mode.value,
        "configured_mode": context.configured_mode.value,
        "available": context.active_mode is not DataMode.UNAVAILABLE,
        "context": context.public(),
        "diagnostics": diagnostics,
    }


@app.get("/api/v1/capabilities")
def capabilities() -> dict[str, Any]:
    return capability_registry()


@app.get("/api/v1/auth/status")
def auth_status(auth_service: AuthService = Depends(get_auth_service)) -> dict[str, Any]:
    mode = auth_service.settings.mode
    return {
        "mode": mode.value,
        "authentication_required": mode is not AuthMode.DISABLED,
        "local_development_warning": (
            "Authentication is disabled. Use only on a private local machine."
            if mode is AuthMode.DISABLED
            else None
        ),
        "available_roles": [role.value for role in Role],
        "oidc_validation_status": (
            "adapter_configured_not_provider-validated"
            if mode is AuthMode.OIDC
            else "not_applicable"
        ),
    }


@app.post("/api/v1/auth/login")
def login(
    payload: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, Any]:
    token = auth_service.authenticate_demo(payload.username, payload.password)
    principal = auth_service.principal(token)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": auth_service.settings.token_ttl_seconds,
        "principal": {
            "username": principal.username,
            "role": principal.role.value,
            "permissions": sorted(permission.value for permission in principal.permissions),
        },
    }


@app.post("/api/v1/auth/logout")
def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    principal: Principal = Depends(get_principal),
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, Any]:
    if credentials is not None:
        auth_service.logout(credentials.credentials)
    return {"logged_out": True, "username": principal.username}


@app.get("/api/v1/auth/me")
def auth_me(principal: Principal = Depends(get_principal)) -> dict[str, Any]:
    return {
        "username": principal.username,
        "role": principal.role.value,
        "permissions": sorted(permission.value for permission in principal.permissions),
        "auth_mode": principal.auth_mode.value,
    }


@app.get("/api/v1/metadata")
def metadata(service: WorkbenchService = Depends(get_service)) -> dict[str, Any]:
    return service.metadata()


@app.get("/api/v1/filters")
def filters(service: WorkbenchService = Depends(get_service)) -> dict[str, Any]:
    return service.filters()


@app.get("/api/v1/command-centre")
def command_centre(
    reporting_month: str | None = Query(default=None),
    selected_filters: dict[str, Any] = Depends(common_filters),
    service: WorkbenchService = Depends(get_service),
    context: SourceContext = Depends(get_source_context),
) -> dict[str, Any]:
    return service.command_centre(
        period=reporting_month,
        filters=selected_filters,
        source_context=context,
    )


@app.get("/api/v1/kpis")
def kpis(
    reporting_month: str | None = Query(default=None),
    selected_filters: dict[str, Any] = Depends(common_filters),
    service: WorkbenchService = Depends(get_service),
    context: SourceContext = Depends(get_source_context),
) -> dict[str, Any]:
    return service.kpis(
        period=reporting_month,
        filters=selected_filters,
        source_context=context,
    )


@app.get("/api/v1/trends")
def trends(
    reporting_month: str | None = Query(default=None),
    selected_filters: dict[str, Any] = Depends(common_filters),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    return service.trends(period=reporting_month, filters=selected_filters)


@app.get("/api/v1/vintages")
def vintages(
    reporting_month: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    selected_filters: dict[str, Any] = Depends(common_filters),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    return paginate(
        service.vintages(period=reporting_month, filters=selected_filters),
        page,
        page_size,
    )


@app.get("/api/v1/roll-rates")
def roll_rates(
    reporting_month: str | None = Query(default=None),
    selected_filters: dict[str, Any] = Depends(common_filters),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    return service.roll_rates(period=reporting_month, filters=selected_filters)


@app.get("/api/v1/strategy-comparison")
def strategy_comparison(
    reporting_month: str | None = Query(default=None),
    selected_filters: dict[str, Any] = Depends(common_filters),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    return service.strategy_comparison(period=reporting_month, filters=selected_filters)


@app.get("/api/v1/segments")
def segments(
    selected_filters: dict[str, Any] = Depends(common_filters),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    return service.segments(filters=selected_filters)


@app.get("/api/v1/root-cause")
def root_cause(
    reporting_month: str | None = Query(default=None),
    selected_filters: dict[str, Any] = Depends(common_filters),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    return service.root_cause(period=reporting_month, filters=selected_filters)


@app.get("/api/v1/alerts")
def alerts(
    reporting_month: str | None = Query(default=None),
    selected_filters: dict[str, Any] = Depends(common_filters),
    service: WorkbenchService = Depends(get_service),
    context: SourceContext = Depends(get_source_context),
) -> dict[str, Any]:
    return service.alerts(
        period=reporting_month,
        filters=selected_filters,
        source_context=context,
    )


@app.get("/api/v1/alerts/{alert_id}/audit")
def alert_audit(
    alert_id: str,
    selected_filters: dict[str, Any] = Depends(common_filters),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    return service.alert_audit(alert_id, filters=selected_filters)


@app.get("/api/v1/alerts/{alert_id}")
def alert_detail(
    alert_id: str,
    selected_filters: dict[str, Any] = Depends(common_filters),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    return service.alert_detail(alert_id, filters=selected_filters)


@app.post("/api/v1/alerts/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: str,
    payload: AlertAcknowledgeRequest,
    principal: Principal = Depends(require_permission(Permission.MANAGE_ALERTS)),
    selected_filters: dict[str, Any] = Depends(common_filters),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    return service.acknowledge_alert(
        alert_id,
        expected_version=payload.expected_version,
        note=payload.note,
        actor=principal.username,
        filters=selected_filters,
    )


@app.post("/api/v1/alerts/{alert_id}/transition")
def transition_alert(
    alert_id: str,
    payload: AlertTransitionRequest,
    principal: Principal = Depends(require_permission(Permission.MANAGE_ALERTS)),
    selected_filters: dict[str, Any] = Depends(common_filters),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    return service.transition_alert(
        alert_id,
        payload.model_dump(),
        actor=principal.username,
        filters=selected_filters,
    )


@app.post("/api/v1/alerts/{alert_id}/investigation")
def start_alert_investigation(
    alert_id: str,
    payload: AlertInvestigationRequest,
    principal: Principal = Depends(require_permission(Permission.MANAGE_ALERTS)),
    selected_filters: dict[str, Any] = Depends(common_filters),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    return service.start_alert_investigation(
        alert_id,
        payload.model_dump(exclude_none=True),
        actor=principal.username,
        filters=selected_filters,
    )


@app.get("/api/v1/investigations")
def investigations(
    reporting_month: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    return paginate(
        service.investigations(requested_period=reporting_month),
        page,
        page_size,
    )


@app.post("/api/v1/investigations", status_code=201)
def create_investigation(
    payload: InvestigationCreate,
    principal: Principal = Depends(require_permission(Permission.CREATE_INVESTIGATIONS)),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    return service.create_investigation(payload.model_dump(), actor=principal.username)


@app.patch("/api/v1/investigations/{investigation_id}")
def update_investigation(
    investigation_id: str,
    payload: InvestigationUpdate,
    principal: Principal = Depends(require_permission(Permission.CREATE_INVESTIGATIONS)),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    try:
        changes = payload.model_dump(exclude_none=True)
        expected_version = changes.pop("expected_version", None)
        return service.update_investigation(
            investigation_id,
            changes,
            expected_version=expected_version,
            actor=principal.username,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Investigation not found") from exc


@app.get("/api/v1/drift")
def drift(service: WorkbenchService = Depends(get_service)) -> dict[str, Any]:
    return service.drift()


@app.get("/api/v1/scenarios")
def scenarios(
    reporting_month: str | None = Query(default=None),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    return service.scenarios(period=reporting_month)


@app.post("/api/v1/scenarios/run")
def scenario_run(
    payload: ScenarioRunRequest,
    principal: Principal = Depends(require_permission(Permission.RUN_STRATEGY_SCENARIOS)),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    return service.scenario_run(payload.model_dump(), actor=principal.username)


@app.post("/api/v1/commentary/generate")
def commentary(
    payload: CommentaryRequest,
    principal: Principal = Depends(require_permission(Permission.CREATE_WORKSPACES)),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    return service.commentary(payload.model_dump(), actor=principal.username)


@app.get("/api/v1/partners")
@app.get("/api/v1/partner-performance")
def partners(
    reporting_month: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    return paginate(service.partners(period=reporting_month), page, page_size)


@app.get("/api/v1/partners/{partner_id}")
def partner_detail(
    partner_id: str,
    reporting_month: str | None = Query(default=None),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    rows = [
        row
        for row in service.partners(period=reporting_month)["data"]
        if row["partner_id"] == partner_id
    ]
    if not rows:
        raise HTTPException(status_code=404, detail="Partner not found")
    return rows[0]


@app.get("/api/v1/partner-ratings")
def partner_ratings(
    reporting_month: str | None = Query(default=None),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    output = service.partners(period=reporting_month)
    return {
        "data": [
            {"partner_id": row["partner_id"], **(row.get("rating") or {})} for row in output["data"]
        ],
        "metadata": output["metadata"],
    }


@app.post("/api/v1/partner-scenarios/run")
def partner_scenario(
    payload: PartnerScenarioRequest,
    _: Principal = Depends(require_permission(Permission.RUN_STRATEGY_SCENARIOS)),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    return service.partner_scenario(payload.model_dump())


@app.get("/api/v1/vendors")
@app.get("/api/v1/vendor-performance")
def vendors(
    reporting_month: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    return paginate(service.vendors(period=reporting_month), page, page_size)


@app.get("/api/v1/vendors/{vendor_id}")
def vendor_detail(
    vendor_id: str,
    reporting_month: str | None = Query(default=None),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    rows = [
        row
        for row in service.vendors(period=reporting_month)["data"]
        if row["vendor_id"] == vendor_id
    ]
    if not rows:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return rows[0]


@app.get("/api/v1/vendor-ratings")
def vendor_ratings(
    reporting_month: str | None = Query(default=None),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    output = service.vendors(period=reporting_month)
    return {
        "data": [
            {"vendor_id": row["vendor_id"], **(row.get("rating") or {})} for row in output["data"]
        ],
        "metadata": output["metadata"],
    }


@app.post("/api/v1/vendor-reallocation/run")
def vendor_reallocation(
    payload: VendorReallocationRequest,
    _: Principal = Depends(require_permission(Permission.RUN_STRATEGY_SCENARIOS)),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    return service.vendor_reallocation(payload.model_dump())


@app.get("/api/v1/memberships")
@app.get("/api/v1/membership-performance")
def memberships(
    reporting_month: str | None = Query(default=None),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    return service.memberships(period=reporting_month)


@app.get("/api/v1/membership-transitions")
def membership_transitions(
    reporting_month: str | None = Query(default=None),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    return service.membership_transitions(period=reporting_month)


@app.get("/api/v1/benefits")
@app.get("/api/v1/benefit-performance")
def benefits(
    reporting_month: str | None = Query(default=None),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    return service.benefits(period=reporting_month)


@app.get("/api/v1/baskets")
def baskets(
    reporting_month: str | None = Query(default=None),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    return service.baskets(requested_period=reporting_month)


@app.post("/api/v1/baskets", status_code=201)
def create_basket(
    payload: BasketCreate,
    principal: Principal = Depends(require_permission(Permission.CREATE_WORKSPACES)),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    return service.create_basket(payload.model_dump(), actor=principal.username)


@app.post("/api/v1/baskets/combine")
def combine_baskets(
    payload: BasketCombineRequest,
    _: Principal = Depends(require_permission(Permission.CREATE_WORKSPACES)),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    return service.combine_baskets(payload.model_dump())


@app.post("/api/v1/baskets/compare")
@app.post("/api/v1/baskets/impact-preview")
def basket_impact(
    payload: BasketImpactRequest,
    _: Principal = Depends(require_permission(Permission.CREATE_WORKSPACES)),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    return service.basket_impact(payload.model_dump())


@app.get("/api/v1/baskets/{basket_id}")
def basket_detail(
    basket_id: str,
    reporting_month: str | None = Query(default=None),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    try:
        return service.basket_detail(basket_id, requested_period=reporting_month)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Basket not found") from exc


@app.patch("/api/v1/baskets/{basket_id}")
def update_basket(
    basket_id: str,
    payload: BasketUpdate,
    principal: Principal = Depends(require_permission(Permission.CREATE_WORKSPACES)),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    try:
        changes = payload.model_dump(exclude_none=True)
        expected_version = changes.pop("expected_version", None)
        return service.update_basket(
            basket_id,
            changes,
            expected_version=expected_version,
            actor=principal.username,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Basket not found") from exc


@app.post("/api/v1/baskets/{basket_id}/clone", status_code=201)
def clone_basket(
    basket_id: str,
    principal: Principal = Depends(require_permission(Permission.CREATE_WORKSPACES)),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    try:
        return service.clone_basket(basket_id, actor=principal.username)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Basket not found") from exc


@app.get("/api/v1/workspaces")
def workspaces(service: WorkbenchService = Depends(get_service)) -> dict[str, Any]:
    return service.workspaces()


@app.post("/api/v1/workspaces", status_code=201)
def create_workspace(
    payload: WorkspaceCreate,
    principal: Principal = Depends(require_permission(Permission.CREATE_WORKSPACES)),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    return service.create_workspace(payload.model_dump(), actor=principal.username)


@app.get("/api/v1/workspaces/{workspace_id}")
def workspace_detail(
    workspace_id: str,
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    try:
        return service.workspace_detail(workspace_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Workspace not found") from exc


@app.patch("/api/v1/workspaces/{workspace_id}")
def update_workspace(
    workspace_id: str,
    payload: WorkspaceUpdate,
    principal: Principal = Depends(require_permission(Permission.CREATE_WORKSPACES)),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    try:
        changes = payload.model_dump(exclude_none=True)
        expected_version = changes.pop("expected_version", None)
        return service.update_workspace(
            workspace_id,
            changes,
            expected_version=expected_version,
            actor=principal.username,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Workspace not found") from exc


@app.post("/api/v1/workspaces/{workspace_id}/run")
def run_workspace(
    workspace_id: str,
    _: Principal = Depends(require_permission(Permission.CREATE_WORKSPACES)),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    try:
        return service.run_workspace(workspace_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Workspace not found") from exc


@app.post("/api/v1/workspaces/{workspace_id}/refresh")
def refresh_workspace(
    workspace_id: str,
    _: Principal = Depends(require_permission(Permission.CREATE_WORKSPACES)),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    try:
        return service.run_workspace(workspace_id, refresh=True)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Workspace not found") from exc


@app.post("/api/v1/workspaces/{workspace_id}/export")
def export_workspace(
    workspace_id: str,
    _: Principal = Depends(require_permission(Permission.DOWNLOAD_ARTIFACTS)),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    try:
        return service.export_workspace(workspace_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Workspace not found") from exc


@app.get("/api/v1/peer-analogues")
def peer_analogue_catalogue(
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    return service.peer_catalogue()


@app.post("/api/v1/peer-analogues/match")
def peer_analogue_match(
    payload: PeerMatchRequest,
    _: Principal = Depends(require_permission(Permission.VIEW_ANALYTICS)),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    return service.peer_analogues(payload.model_dump())


@app.get("/api/v1/ratings")
def ratings(service: WorkbenchService = Depends(get_service)) -> dict[str, Any]:
    return {
        "methodology_version": service.config.ratings["methodology_version"],
        "methodologies": {
            key: value
            for key, value in service.config.ratings.items()
            if key not in {"methodology_version", "grade_thresholds"}
        },
        "grade_thresholds": service.config.ratings["grade_thresholds"],
    }


@app.post("/api/v1/ratings/calculate")
def rating_calculate(
    payload: RatingRequest,
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    return calculate_rating(
        payload.components,
        service.config.ratings[payload.rating_type],
        service.config.ratings["grade_thresholds"],
        methodology_version=service.config.ratings["methodology_version"],
    )


@app.post("/api/v1/ratings/sensitivity")
def rating_sensitivity(
    payload: RatingSensitivityRequest,
    _: Principal = Depends(require_permission(Permission.APPROVE_MODELS)),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    base = service.config.ratings[payload.rating_type]
    revised = {
        name: {**spec, "weight": payload.weight_overrides.get(name, spec["weight"])}
        for name, spec in base.items()
    }
    total = sum(float(spec["weight"]) for spec in revised.values())
    if total <= 0:
        raise ValueError("Sensitivity weights must have a positive total")
    revised = {
        name: {**spec, "weight": float(spec["weight"]) / total} for name, spec in revised.items()
    }
    return {
        "baseline": calculate_rating(
            payload.components,
            base,
            service.config.ratings["grade_thresholds"],
            methodology_version=service.config.ratings["methodology_version"],
        ),
        "sensitivity": calculate_rating(
            payload.components,
            revised,
            service.config.ratings["grade_thresholds"],
            methodology_version=f"{service.config.ratings['methodology_version']}-preview",
        ),
        "saved": False,
        "approval_required": True,
    }


@app.get("/api/v1/finance")
def finance(
    reporting_month: str | None = Query(default=None),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    return service.finance(period=reporting_month)


@app.get("/api/v1/data-quality")
def data_quality(service: WorkbenchService = Depends(get_service)) -> dict[str, Any]:
    return service.data_quality()


@app.get("/api/v1/network")
def network(service: WorkbenchService = Depends(get_service)) -> dict[str, Any]:
    return service.network()


@app.post("/api/v1/network/impact")
def network_node_impact(
    payload: NetworkImpactRequest,
    _: Principal = Depends(require_permission(Permission.RUN_STRATEGY_SCENARIOS)),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    return service.network_impact(payload.node_id)


@app.get("/api/v1/capacity")
def capacity(service: WorkbenchService = Depends(get_service)) -> dict[str, Any]:
    return service.capacity()


@app.post("/api/v1/capacity/scenario")
def capacity_scenario(
    payload: CapacityScenarioRequest,
    _: Principal = Depends(require_permission(Permission.RUN_STRATEGY_SCENARIOS)),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    return service.capacity_scenario(payload.model_dump())


@app.get("/api/v1/metric-registry")
def metric_registry(
    service: WorkbenchService = Depends(get_service),
    context: SourceContext = Depends(get_source_context),
) -> dict[str, Any]:
    evidence_by_metric = {
        row["metric_id"]: row["runtime_evidence"]
        for row in service.kpis(source_context=context)["data"]
    }
    return {
        "data": [
            {
                **metric_display_contract(metric),
                "runtime_evidence": evidence_by_metric[str(metric["metric_id"])],
            }
            for metric in metric_lookup(service.config).values()
        ],
        "version": service.config.metric_registry_version,
        "registry_version": service.config.metric_registry_version,
    }


@app.get("/api/v1/analysis-templates")
def analysis_templates() -> dict[str, Any]:
    registry_path = MODEL_ROOT / "analysis_template_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    live = [
        {**template, "status": "live", "causal_status": "Design-dependent"}
        for template in registry["live_templates"]
    ]
    documented = [
        {
            "template_id": name.upper().replace(" ", "_").replace("-", "_"),
            "methodology": name,
            "status": "documented_integration",
            "causal_status": "Not executable in this slice",
        }
        for name in registry["documented_integrations"]
    ]
    return {
        "registry_version": registry["registry_version"],
        "data": live + documented,
        "live_count": len(live),
        "documented_integration_count": len(documented),
    }


@app.post("/api/v1/analysis-templates/run")
def run_analysis_template(
    payload: AnalysisTemplateRunRequest,
    principal: Principal = Depends(require_permission(Permission.VIEW_ANALYTICS)),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    return service.run_analysis_template(
        payload.template_id,
        payload.parameters,
        actor=principal.username,
    )


@app.get("/api/v1/analysis-runs/{run_id}")
def analysis_run(
    run_id: str,
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    try:
        return service.analysis_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Analysis run not found") from exc


@app.get("/api/v1/data-onboarding/contracts")
def onboarding_contracts(
    _: Principal = Depends(require_permission(Permission.VIEW_ANALYTICS)),
    studio: Any = Depends(get_onboarding_studio),
) -> dict[str, Any]:
    contracts = studio.contracts()
    return {"data": contracts, "total": len(contracts), "available": True}


@app.post("/api/v1/data-onboarding/sources/upload", status_code=201)
def onboarding_upload_source(
    payload: OnboardingUploadRequest,
    _: Principal = Depends(require_permission(Permission.CREATE_WORKSPACES)),
    studio: Any = Depends(get_onboarding_studio),
) -> dict[str, Any]:
    try:
        content = base64.b64decode(payload.content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail="content_base64 is invalid") from exc
    return studio.upload_source(payload.filename, content)


@app.post("/api/v1/data-onboarding/sources/select")
def onboarding_select_source(
    payload: OnboardingSelectRequest,
    _: Principal = Depends(require_permission(Permission.CREATE_WORKSPACES)),
    studio: Any = Depends(get_onboarding_studio),
) -> dict[str, Any]:
    return studio.select_source(
        payload.relative_path,
        table=payload.table,
        sheet=payload.sheet,
    )


@app.post("/api/v1/data-onboarding/sources/postgresql")
def onboarding_postgresql_source(
    payload: OnboardingPostgresRequest,
    _: Principal = Depends(require_permission(Permission.PUBLISH_CONFIGURATION)),
    studio: Any = Depends(get_onboarding_studio),
) -> dict[str, Any]:
    return studio.configure_postgresql_source(url_env=payload.url_env, table=payload.table)


@app.post("/api/v1/data-onboarding/sources/table")
def onboarding_bind_table(
    payload: OnboardingTableRequest,
    _: Principal = Depends(require_permission(Permission.CREATE_WORKSPACES)),
    studio: Any = Depends(get_onboarding_studio),
) -> dict[str, Any]:
    return studio.with_table(payload.source.model_dump(exclude_none=True), payload.table)


@app.post("/api/v1/data-onboarding/sources/tables")
def onboarding_database_tables(
    source: OnboardingSource,
    _: Principal = Depends(require_permission(Permission.CREATE_WORKSPACES)),
    studio: Any = Depends(get_onboarding_studio),
) -> dict[str, Any]:
    tables = studio.list_database_tables(source.model_dump(exclude_none=True))
    return {"data": tables, "total": len(tables)}


@app.post("/api/v1/data-onboarding/preview")
def onboarding_preview(
    payload: OnboardingPreviewRequest,
    _: Principal = Depends(require_permission(Permission.CREATE_WORKSPACES)),
    studio: Any = Depends(get_onboarding_studio),
) -> dict[str, Any]:
    return studio.preview_source(
        payload.source.model_dump(exclude_none=True),
        sample_rows=payload.sample_rows,
    )


@app.post("/api/v1/data-onboarding/map")
def onboarding_map(
    payload: OnboardingMappingRequest,
    _: Principal = Depends(require_permission(Permission.CREATE_WORKSPACES)),
    studio: Any = Depends(get_onboarding_studio),
) -> dict[str, Any]:
    return studio.validate_mapping(
        payload.source.model_dump(exclude_none=True),
        contract_id=payload.contract_id,
        mapping=payload.mapping,
        transformations=payload.transformations,
    )


@app.post("/api/v1/data-onboarding/validate")
def onboarding_validate(
    payload: OnboardingValidationRequest,
    _: Principal = Depends(require_permission(Permission.CREATE_WORKSPACES)),
    studio: Any = Depends(get_onboarding_studio),
) -> dict[str, Any]:
    return studio.validate_source(
        payload.source.model_dump(exclude_none=True),
        contract_id=payload.contract_id,
        mapping=payload.mapping,
        transformations=payload.transformations,
        max_error_rate=payload.max_error_rate,
    )


@app.get("/api/v1/data-onboarding/profiles")
def onboarding_profiles(
    _: Principal = Depends(require_permission(Permission.VIEW_ANALYTICS)),
    studio: Any = Depends(get_onboarding_studio),
) -> dict[str, Any]:
    rows = studio.list_profiles()
    return {"data": rows, "total": len(rows)}


@app.post("/api/v1/data-onboarding/profiles", status_code=201)
def onboarding_create_profile(
    payload: OnboardingProfileCreateRequest,
    principal: Principal = Depends(require_permission(Permission.CREATE_WORKSPACES)),
    studio: Any = Depends(get_onboarding_studio),
) -> dict[str, Any]:
    return studio.save_import_profile(
        payload.profile_id,
        payload.source.model_dump(exclude_none=True),
        contract_id=payload.contract_id,
        mapping=payload.mapping,
        transformations=payload.transformations,
        max_error_rate=payload.max_error_rate,
        actor=principal.username,
    )


@app.get("/api/v1/data-onboarding/profiles/{profile_id}")
def onboarding_profile(
    profile_id: str,
    _: Principal = Depends(require_permission(Permission.VIEW_ANALYTICS)),
    studio: Any = Depends(get_onboarding_studio),
) -> dict[str, Any]:
    return studio.get_profile(profile_id)


@app.post("/api/v1/data-onboarding/load")
def onboarding_load(
    payload: OnboardingLoadRequest,
    principal: Principal = Depends(require_permission(Permission.CREATE_WORKSPACES)),
    studio: Any = Depends(get_onboarding_studio),
) -> dict[str, Any]:
    return studio.load_into_onboarding_namespace(
        payload.profile_id,
        payload.source.model_dump(exclude_none=True),
        actor=principal.username,
        expected_version=payload.expected_version,
    )


@app.post("/api/v1/data-onboarding/profiles/{profile_id}/approve")
def onboarding_approve_profile(
    profile_id: str,
    payload: OnboardingApprovalRequest,
    principal: Principal = Depends(require_permission(Permission.PUBLISH_CONFIGURATION)),
    studio: Any = Depends(get_onboarding_studio),
) -> dict[str, Any]:
    return studio.approve_profile(
        profile_id,
        expected_version=payload.expected_version,
        actor=principal.username,
        rationale=payload.rationale,
    )


@app.post("/api/v1/composition-scenarios/run")
def composition_scenario(
    payload: OptimisationRunRequest,
    principal: Principal = Depends(require_permission(Permission.RUN_STRATEGY_SCENARIOS)),
    store: WorkflowStore = Depends(get_workflow_store),
) -> dict[str, Any]:
    from naim_risk.optimisation import optimise_allocation

    return optimise_allocation(
        payload.model_dump(),
        store=store,
        actor=principal.username,
    )


@app.post("/api/v1/optimisation/run")
def optimisation_run(
    payload: OptimisationRunRequest,
    principal: Principal = Depends(require_permission(Permission.RUN_STRATEGY_SCENARIOS)),
    store: WorkflowStore = Depends(get_workflow_store),
) -> dict[str, Any]:
    from naim_risk.optimisation import optimise_allocation

    return optimise_allocation(
        payload.model_dump(),
        store=store,
        actor=principal.username,
    )


@app.get("/api/v1/market-risk/status")
def market_risk_status(
    _: Principal = Depends(require_permission(Permission.VIEW_ANALYTICS)),
) -> dict[str, Any]:
    return {
        "available": True,
        "status": "LIVE",
        "provider_mode": "bundled_deterministic_sample",
        "instruments": ["NAIM-DEMO-INDEX", "NAIM-DEMO-EQUITY"],
        "external_provider": "INTEGRATION_ONLY",
        "methods": [
            "historical volatility",
            "EWMA",
            "ARCH",
            "GARCH(1,1)",
            "implied volatility from user inputs",
            "VaR and expected shortfall",
            "VaR backtesting",
            "volatility regimes",
        ],
        "trading_recommendation": False,
        "approval_required": True,
    }


@app.post("/api/v1/market-risk/run")
def market_risk_run(
    payload: MarketRiskRunRequest,
    _: Principal = Depends(require_permission(Permission.VIEW_ANALYTICS)),
) -> dict[str, Any]:
    from naim_risk.market_risk.providers import MarketDataError

    try:
        _, result = _market_risk_analysis(payload)
    except MarketDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result


@app.post("/api/v1/market-risk/export", status_code=201)
def market_risk_export(
    payload: MarketRiskExportRequest,
    principal: Principal = Depends(require_permission(Permission.DOWNLOAD_ARTIFACTS)),
    service: WorkbenchService = Depends(get_service),
    token_service: DownloadTokenService = Depends(get_download_token_service),
) -> dict[str, Any]:
    from naim_risk.market_risk.exports import export_market_risk_bundle
    from naim_risk.market_risk.providers import MarketDataError

    try:
        market, analysis = _market_risk_analysis(payload)
    except MarketDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    export_root = (service.config.data_root / "generated_exports").resolve()
    export_root.mkdir(parents=True, exist_ok=True)
    export_token = uuid.uuid4().hex[:16].upper()
    filename = f"nAIM_Market_Risk_Volatility_Lab_{export_token}.zip"
    archive_path = export_root / filename
    with tempfile.TemporaryDirectory(prefix="naim-market-risk-", dir=export_root) as temporary:
        temporary_root = Path(temporary)
        manifest = export_market_risk_bundle(
            analysis,
            temporary_root,
            market=market,
            include_excel=payload.include_excel,
            include_presentation=payload.include_presentation,
        )
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for item in sorted(temporary_root.rglob("*")):
                if item.is_file() and not item.is_symlink():
                    archive.write(item, item.relative_to(temporary_root).as_posix())
    record = service.register_export_artifact(
        archive_path,
        "social-and-market-risk-zip",
        actor=principal.username,
    )
    artifact_id = str(record["artifact_id"])
    return {
        **record,
        "status": "completed",
        "manifest": manifest,
        "download_url": _tokenized_url(
            f"/api/v1/exports/{artifact_id}/download",
            f"export:{artifact_id}",
            principal,
            token_service,
        ),
        "approval_state": "DRAFT",
        "trading_recommendation": False,
    }


@app.get("/api/v1/advanced-statistics/status")
def advanced_statistics_status(
    _: Principal = Depends(require_permission(Permission.VIEW_ANALYTICS)),
) -> dict[str, Any]:
    return {
        "available": True,
        "status": "LIVE",
        "methods": {
            "kaplan_meier_and_log_rank": "LIVE",
            "behavioural_model_and_fallback_contributions": "LIVE",
            "shap": "INTEGRATION_ONLY",
            "single_change_point": "LIVE",
            "propensity_weighting": "LIVE",
            "synthetic_policy_difference_in_differences": "LIVE",
            "cox_proportional_hazards": "NOT_IMPLEMENTED",
        },
        "causal_claim": False,
        "approval_required": True,
    }


@app.post("/api/v1/advanced-statistics/survival")
def advanced_survival(
    payload: SurvivalRunRequest,
    _: Principal = Depends(require_permission(Permission.VIEW_ANALYTICS)),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    from naim_risk.advanced.survival import run_survival_analysis

    frame = (
        _records_frame(payload.records)
        if payload.records is not None
        else _portfolio_survival_frame(service)
    )
    result = run_survival_analysis(
        frame,
        group_column=payload.group_column,
        outcomes=payload.outcomes,
        confidence=payload.confidence,
    )
    result["source"] = "request_records" if payload.records is not None else "governed_portfolio"
    result["approval_required"] = True
    return result


@app.post("/api/v1/advanced-statistics/behavioural")
def advanced_behavioural(
    payload: BehaviouralRunRequest,
    _: Principal = Depends(require_permission(Permission.VIEW_ANALYTICS)),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    from naim_risk.advanced.behavioural import run_behavioural_diagnostics

    frame = (
        _records_frame(payload.records)
        if payload.records is not None
        else _portfolio_behavioural_frame(service)
    )
    default_features = [
        "months_on_book",
        "account_balance",
        "utilization",
        "payment_amount",
        "minimum_payment_due",
        "missed_payment_flag",
        "fraud_alert_count",
        "manual_review_count",
        "risk_score",
        "expected_probability_of_default",
    ]
    result = run_behavioural_diagnostics(
        frame,
        account_column=payload.account_column,
        time_column=payload.time_column,
        target_column=payload.target_column,
        current_delinquency_column=payload.current_delinquency_column,
        feature_columns=payload.feature_columns or default_features,
        segment_column=payload.segment_column,
        seed=payload.seed,
    )
    result["source"] = "request_records" if payload.records is not None else "governed_portfolio"
    result["approval_required"] = True
    return result


@app.post("/api/v1/advanced-statistics/change-points")
def advanced_change_points(
    payload: ChangePointRunRequest,
    _: Principal = Depends(require_permission(Permission.VIEW_ANALYTICS)),
    service: WorkbenchService = Depends(get_service),
) -> dict[str, Any]:
    from naim_risk.advanced.changepoint import (
        detect_change_points,
        validate_change_point_method,
    )

    if payload.series is None:
        trend_rows = [
            row for row in service.trends()["data"] if row["metric_id"] == payload.metric_id
        ]
        series = [float(row["value"]) for row in trend_rows]
        source = {
            "kind": "governed_portfolio_metric",
            "metric_id": payload.metric_id,
            "periods": [row["month"] for row in trend_rows],
            "unit": trend_rows[0]["unit"] if trend_rows else None,
        }
    else:
        series = payload.series
        source = {"kind": "request_series", "metric_id": None}
    result = detect_change_points(
        series,
        min_segment=payload.min_segment,
        seasonal_period=payload.seasonal_period,
        significance=payload.significance,
        minimum_robust_effect=payload.minimum_robust_effect,
    )
    result["source"] = source
    result["method_validation"] = validate_change_point_method()
    result["causal_status"] = "associational diagnostic"
    return result


@app.post("/api/v1/advanced-statistics/propensity")
def advanced_propensity(
    payload: PropensityRunRequest,
    _: Principal = Depends(require_permission(Permission.RUN_STRATEGY_SCENARIOS)),
) -> dict[str, Any]:
    from naim_risk.advanced.causal import propensity_weighted_comparison

    return json_safe(
        propensity_weighted_comparison(
            _records_frame(payload.records),
            treatment_column=payload.treatment_column,
            outcome_column=payload.outcome_column,
            covariates=payload.covariates,
            trim_quantile=payload.trim_quantile,
            seed=payload.seed,
        )
    )


@app.post("/api/v1/advanced-statistics/difference-in-differences")
def advanced_difference_in_differences(
    payload: DifferenceInDifferencesRunRequest,
    _: Principal = Depends(require_permission(Permission.RUN_STRATEGY_SCENARIOS)),
) -> dict[str, Any]:
    from naim_risk.advanced.causal import difference_in_differences

    return json_safe(
        difference_in_differences(
            _records_frame(payload.records),
            outcome_column=payload.outcome_column,
            treatment_column=payload.treatment_column,
            time_column=payload.time_column,
            policy_date=payload.policy_date,
            cluster_column=payload.cluster_column,
            synthetic_policy_use_case=payload.synthetic_policy_use_case,
        )
    )


@app.post("/api/v1/tableau/extract", status_code=201)
def tableau_extract(
    principal: Principal = Depends(require_permission(Permission.DOWNLOAD_ARTIFACTS)),
    service: WorkbenchService = Depends(get_service),
    store: WorkflowStore = Depends(get_workflow_store),
    output_path: Path = Depends(get_tableau_output_path),
    token_service: DownloadTokenService = Depends(get_download_token_service),
) -> dict[str, Any]:
    from naim_risk.tableau import HyperUnavailable, generate_hyper_extract

    context = get_source_context()
    if context.active_mode is DataMode.UNAVAILABLE:
        raise HTTPException(status_code=503, detail=context.reason or "Data source unavailable")
    try:
        result = generate_hyper_extract(service, output_path=output_path)
    except HyperUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    state = {
        "record_kind": "tableau_hyper_export",
        "filename": result["filename"],
        "sha256": result["sha256"],
        "status": result["status"],
        "validation_tables": len(result["tables"]),
        "publishing_status": result["publishing"]["status"],
        "approval_required": True,
    }
    external_id = "TABLEAU-HYPER-LATEST"
    try:
        store.create(
            "configuration_change",
            external_id,
            state,
            actor=principal.username,
            approval_state="DRAFT",
        )
    except DuplicateObject:
        current = store.get("configuration_change", external_id)
        store.update(
            "configuration_change",
            external_id,
            state,
            expected_version=int(current["version"]),
            actor=principal.username,
            approval_state="DRAFT",
            replace=True,
        )
    return {
        **result,
        "download_url": _tokenized_url(
            "/api/v1/tableau/extract/download",
            "tableau:latest:artifact",
            principal,
            token_service,
        ),
        "manifest_url": _tokenized_url(
            "/api/v1/tableau/extract/manifest",
            "tableau:latest:manifest",
            principal,
            token_service,
        ),
        "approval_state": "DRAFT",
    }


@app.get("/api/v1/tableau/extract/download")
def tableau_extract_download(
    download_token: str = Query(min_length=20, max_length=4096),
    principal: Principal = Depends(require_permission(Permission.DOWNLOAD_ARTIFACTS)),
    output_path: Path = Depends(get_tableau_output_path),
    token_service: DownloadTokenService = Depends(get_download_token_service),
) -> FileResponse:
    _verify_download_token(
        download_token,
        "tableau:latest:artifact",
        principal,
        token_service,
    )
    root = (REPOSITORY_ROOT / "outputs" / "tableau").resolve()
    path = output_path.resolve()
    if path.parent != root or not path.is_file():
        raise HTTPException(status_code=404, detail="Tableau extract not found")
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")


@app.get("/api/v1/tableau/extract/manifest")
def tableau_extract_manifest(
    download_token: str = Query(min_length=20, max_length=4096),
    principal: Principal = Depends(require_permission(Permission.DOWNLOAD_ARTIFACTS)),
    output_path: Path = Depends(get_tableau_output_path),
    token_service: DownloadTokenService = Depends(get_download_token_service),
) -> FileResponse:
    _verify_download_token(
        download_token,
        "tableau:latest:manifest",
        principal,
        token_service,
    )
    root = (REPOSITORY_ROOT / "outputs" / "tableau").resolve()
    path = output_path.with_suffix(".manifest.json").resolve()
    if path.parent != root or not path.is_file():
        raise HTTPException(status_code=404, detail="Tableau manifest not found")
    return FileResponse(path, filename=path.name, media_type="application/json")


@app.get("/api/v1/exports")
def exports(
    principal: Principal = Depends(require_permission(Permission.DOWNLOAD_ARTIFACTS)),
    service: WorkbenchService = Depends(get_service),
    token_service: DownloadTokenService = Depends(get_download_token_service),
) -> dict[str, Any]:
    result = service.exports()
    for row in result.get("data", []):
        artifact_id = str(row["artifact_id"])
        row["download_url"] = _tokenized_url(
            f"/api/v1/exports/{artifact_id}/download",
            f"export:{artifact_id}",
            principal,
            token_service,
        )
    return result


@app.get("/api/v1/exports/{artifact_id}/download")
def download_export(
    artifact_id: str,
    download_token: str = Query(min_length=20, max_length=4096),
    principal: Principal = Depends(require_permission(Permission.DOWNLOAD_ARTIFACTS)),
    service: WorkbenchService = Depends(get_service),
    token_service: DownloadTokenService = Depends(get_download_token_service),
) -> FileResponse:
    _verify_download_token(download_token, f"export:{artifact_id}", principal, token_service)
    try:
        path = service.resolve_export_artifact(artifact_id, actor=principal.username)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Export artifact not found") from exc
    service.register_export_download(artifact_id, actor=principal.username)
    return FileResponse(path, filename=path.name)


@app.post("/api/v1/exports/excel")
def export_excel(
    principal: Principal = Depends(require_permission(Permission.DOWNLOAD_ARTIFACTS)),
    service: WorkbenchService = Depends(get_service),
    token_service: DownloadTokenService = Depends(get_download_token_service),
) -> dict[str, Any]:
    result = service.export_excel(actor=principal.username)
    artifact_id = str(result["artifact_id"])
    result["download_url"] = _tokenized_url(
        f"/api/v1/exports/{artifact_id}/download",
        f"export:{artifact_id}",
        principal,
        token_service,
    )
    return result


@app.post("/api/v1/exports/powerbi")
def export_powerbi(
    principal: Principal = Depends(require_permission(Permission.DOWNLOAD_ARTIFACTS)),
    service: WorkbenchService = Depends(get_service),
    token_service: DownloadTokenService = Depends(get_download_token_service),
) -> dict[str, Any]:
    result = service.export_powerbi(actor=principal.username)
    artifact_id = str(result["artifact_id"])
    result["download_url"] = _tokenized_url(
        f"/api/v1/exports/{artifact_id}/download",
        f"export:{artifact_id}",
        principal,
        token_service,
    )
    return result


@app.post("/api/v1/demo/run")
def demo_run(
    principal: Principal = Depends(require_permission(Permission.VIEW_ANALYTICS)),
    service: WorkbenchService = Depends(get_service),
    context: SourceContext = Depends(get_source_context),
) -> dict[str, Any]:
    if context.active_mode not in {DataMode.DEMO, DataMode.OFFLINE_SNAPSHOT}:
        raise HTTPException(
            status_code=503,
            detail=(
                context.reason
                or "Instant Demo requires approved DEMO or OFFLINE_SNAPSHOT evidence"
            ),
        )
    try:
        return service.run_demo(actor=principal.username, source_context=context)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/v1/demo/status/{run_id}")
def demo_status(run_id: str, service: WorkbenchService = Depends(get_service)) -> dict[str, Any]:
    try:
        return service.demo_status(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Demo run not found") from exc


@app.post("/api/v1/executive-packs/generate", status_code=201)
def executive_pack_generate(
    payload: ExecutivePackGenerateRequest,
    principal: Principal = Depends(require_permission(Permission.DOWNLOAD_ARTIFACTS)),
    service: WorkbenchService = Depends(get_service),
    store: WorkflowStore = Depends(get_workflow_store),
    context: SourceContext = Depends(get_source_context),
    output_root: Path = Depends(get_executive_pack_output_root),
    token_service: DownloadTokenService = Depends(get_download_token_service),
) -> dict[str, Any]:
    try:
        result = generate_executive_pack(
            service,
            payload.model_dump(),
            store=store,
            source_context=context,
            actor=principal.username,
            output_root=output_root,
        )
    except ExecutivePackError as exc:
        status_code = 422 if exc.stage == "validating_scope" else 500
        raise HTTPException(
            status_code=status_code,
            detail={"stage": exc.stage, "error": str(exc)},
        ) from exc
    job_id = str(result["job_id"])
    result["download_url"] = _tokenized_url(
        f"/api/v1/executive-packs/{job_id}/download",
        f"executive-pack:{job_id}:artifact",
        principal,
        token_service,
    )
    result["manifest_url"] = _tokenized_url(
        f"/api/v1/executive-packs/{job_id}/manifest",
        f"executive-pack:{job_id}:manifest",
        principal,
        token_service,
    )
    return result


@app.get("/api/v1/executive-packs/{job_id}")
def executive_pack_status(
    job_id: str,
    principal: Principal = Depends(require_permission(Permission.DOWNLOAD_ARTIFACTS)),
    store: WorkflowStore = Depends(get_workflow_store),
    token_service: DownloadTokenService = Depends(get_download_token_service),
) -> dict[str, Any]:
    try:
        result = executive_pack_record(store, job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Executive Pack job not found") from exc
    if result.get("status") == "completed":
        result["download_url"] = _tokenized_url(
            f"/api/v1/executive-packs/{job_id}/download",
            f"executive-pack:{job_id}:artifact",
            principal,
            token_service,
        )
        result["manifest_url"] = _tokenized_url(
            f"/api/v1/executive-packs/{job_id}/manifest",
            f"executive-pack:{job_id}:manifest",
            principal,
            token_service,
        )
    return result


@app.get("/api/v1/executive-packs/{job_id}/download")
def executive_pack_download(
    job_id: str,
    download_token: str = Query(min_length=20, max_length=4096),
    principal: Principal = Depends(require_permission(Permission.DOWNLOAD_ARTIFACTS)),
    store: WorkflowStore = Depends(get_workflow_store),
    output_root: Path = Depends(get_executive_pack_output_root),
    token_service: DownloadTokenService = Depends(get_download_token_service),
) -> FileResponse:
    _verify_download_token(
        download_token,
        f"executive-pack:{job_id}:artifact",
        principal,
        token_service,
    )
    try:
        path = resolve_executive_pack_file(store, job_id, output_root=output_root)
        register_executive_pack_download(store, job_id, actor=principal.username)
    except (KeyError, ObjectNotFound) as exc:
        raise HTTPException(status_code=404, detail="Executive Pack artifact not found") from exc
    return FileResponse(
        path,
        filename=path.name,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )


@app.get("/api/v1/executive-packs/{job_id}/manifest")
def executive_pack_manifest(
    job_id: str,
    download_token: str = Query(min_length=20, max_length=4096),
    principal: Principal = Depends(require_permission(Permission.DOWNLOAD_ARTIFACTS)),
    store: WorkflowStore = Depends(get_workflow_store),
    output_root: Path = Depends(get_executive_pack_output_root),
    token_service: DownloadTokenService = Depends(get_download_token_service),
) -> FileResponse:
    _verify_download_token(
        download_token,
        f"executive-pack:{job_id}:manifest",
        principal,
        token_service,
    )
    try:
        path = resolve_executive_pack_file(
            store,
            job_id,
            output_root=output_root,
            manifest=True,
        )
    except (KeyError, ObjectNotFound) as exc:
        raise HTTPException(status_code=404, detail="Executive Pack manifest not found") from exc
    return FileResponse(path, filename=path.name, media_type="application/json")


@app.get("/api/v1/presentations")
def presentations(
    _: Principal = Depends(require_permission(Permission.DOWNLOAD_ARTIFACTS)),
    store: WorkflowStore = Depends(get_workflow_store),
) -> dict[str, Any]:
    from naim_risk.presentations import list_presentations

    rows = list_presentations(store)
    return {"data": rows, "total": len(rows), "available": True}


@app.post("/api/v1/presentations/generate", status_code=201)
def presentation_generate(
    payload: PresentationGenerateRequest,
    principal: Principal = Depends(require_permission(Permission.CREATE_WORKSPACES)),
    service: WorkbenchService = Depends(get_service),
    store: WorkflowStore = Depends(get_workflow_store),
    output_root: Path = Depends(get_presentation_output_root),
    token_service: DownloadTokenService = Depends(get_download_token_service),
) -> dict[str, Any]:
    from naim_risk.presentations import generate_presentation

    context = get_source_context()
    if context.active_mode is DataMode.UNAVAILABLE:
        raise HTTPException(status_code=503, detail=context.reason or "Data source unavailable")
    try:
        result = generate_presentation(
            service,
            payload.model_dump(),
            store=store,
            source_context=context,
            actor=principal.username,
            output_root=output_root,
        )
        presentation_id = str(result["presentation_id"])
        result["download_url"] = _tokenized_url(
            f"/api/v1/presentations/{presentation_id}/download",
            f"presentation:{presentation_id}:artifact",
            principal,
            token_service,
        )
        result["manifest_url"] = _tokenized_url(
            f"/api/v1/presentations/{presentation_id}/manifest",
            f"presentation:{presentation_id}:manifest",
            principal,
            token_service,
        )
        return result
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Workspace or basket not found") from exc


@app.get("/api/v1/presentations/{presentation_id}")
def presentation_status(
    presentation_id: str,
    _: Principal = Depends(require_permission(Permission.DOWNLOAD_ARTIFACTS)),
    store: WorkflowStore = Depends(get_workflow_store),
) -> dict[str, Any]:
    from naim_risk.presentations import presentation_record

    try:
        return presentation_record(store, presentation_id)
    except (KeyError, ObjectNotFound) as exc:
        raise HTTPException(status_code=404, detail="Presentation not found") from exc


@app.get("/api/v1/presentations/{presentation_id}/download")
def presentation_download(
    presentation_id: str,
    download_token: str = Query(min_length=20, max_length=4096),
    principal: Principal = Depends(require_permission(Permission.DOWNLOAD_ARTIFACTS)),
    store: WorkflowStore = Depends(get_workflow_store),
    output_root: Path = Depends(get_presentation_output_root),
    token_service: DownloadTokenService = Depends(get_download_token_service),
) -> FileResponse:
    from naim_risk.presentations import resolve_presentation_file

    _verify_download_token(
        download_token,
        f"presentation:{presentation_id}:artifact",
        principal,
        token_service,
    )
    try:
        path = resolve_presentation_file(store, presentation_id, output_root=output_root)
    except (KeyError, ObjectNotFound) as exc:
        raise HTTPException(status_code=404, detail="Presentation not found") from exc
    return FileResponse(
        path,
        filename=path.name,
        media_type=("application/vnd.openxmlformats-officedocument.presentationml.presentation"),
    )


@app.get("/api/v1/presentations/{presentation_id}/manifest")
def presentation_manifest(
    presentation_id: str,
    download_token: str = Query(min_length=20, max_length=4096),
    principal: Principal = Depends(require_permission(Permission.DOWNLOAD_ARTIFACTS)),
    store: WorkflowStore = Depends(get_workflow_store),
    output_root: Path = Depends(get_presentation_output_root),
    token_service: DownloadTokenService = Depends(get_download_token_service),
) -> FileResponse:
    from naim_risk.presentations import resolve_presentation_file

    _verify_download_token(
        download_token,
        f"presentation:{presentation_id}:manifest",
        principal,
        token_service,
    )
    try:
        path = resolve_presentation_file(
            store, presentation_id, manifest=True, output_root=output_root
        )
    except (KeyError, ObjectNotFound) as exc:
        raise HTTPException(status_code=404, detail="Presentation manifest not found") from exc
    return FileResponse(path, filename=path.name, media_type="application/json")
