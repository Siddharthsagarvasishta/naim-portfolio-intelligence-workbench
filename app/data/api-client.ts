import { DEFAULT_FILTERS, deriveDemoData } from "./demo-data";
import { publicApiUrl } from "./api-environment";
import { normalizeApiOrigin } from "./api-origin.mjs";
import { normalizeMetricUnit, scaleMetricValue } from "./metric-format";
import { contributionDimensionMatches } from "./p0-contract";
import {
  ALERT_AUDIT_EVENT_TYPES,
  isAlertLifecycleStatus,
  isAlertLifecycleTransition,
} from "./alert-lifecycle";
import type {
  AlertAuditEvent,
  AlertAuditIntegrity,
  AlertAuditTrail,
  AlertLifecycleStatus,
  AlertLifecycleTransition,
  AlertRecord,
  BasketRecord,
  CapabilityRecord,
  CapabilityStatus,
  ClientRequestDiagnostics,
  DataMode,
  DataQualityCheck,
  EntityScore,
  GlobalFilters,
  InvestigationRecord,
  KpiMetric,
  ExecutivePackResult,
  MarketRiskRunResult,
  MarketRiskStatus,
  MetricDirectionality,
  RootCauseLens,
  ScenarioRecord,
  ServerDataDiagnostics,
  SignalStatus,
  SourceContext,
  PortfolioStoryRun,
  StrategyResult,
  ViewKey,
  VintageCell,
  WorkbenchData,
  AdvancedStatisticsStatus,
} from "../workbench-types";

export interface WorkbenchLoadResult {
  data: WorkbenchData;
  unavailableReason?: string;
  availableEndpoints: string[];
  requestDiagnostics: ClientRequestDiagnostics;
}

export interface GeneratedExport {
  artifactId: string;
  filename: string;
  sizeBytes: number;
  downloadUrl: string;
}

export { normalizeApiOrigin } from "./api-origin.mjs";

const API_BASE = normalizeApiOrigin(publicApiUrl());

const DATA_MODES = new Set<DataMode>([
  "LIVE",
  "DEMO",
  "OFFLINE_SNAPSHOT",
  "UNAVAILABLE",
]);

const CAPABILITY_STATUSES = new Set<CapabilityStatus>([
  "LIVE",
  "INTEGRATION_ONLY",
  "DOCUMENTED",
  "DISABLED",
  "NOT_IMPLEMENTED",
]);

const EMPTY_SOURCE_CONTEXT: SourceContext = {
  activeMode: "UNAVAILABLE",
  configuredMode: "UNAVAILABLE",
  snapshotDate: null,
  configurationHash: null,
  datasetHash: null,
  datasetHashBasis: null,
  runId: null,
  synthetic: null,
  reason: "The portfolio data source has not been verified.",
};

export const EMPTY_SERVER_DIAGNOSTICS: ServerDataDiagnostics = {
  diagnosticStatus: "UNKNOWN",
  serverObservedAt: null,
  activeMode: null,
  configuredMode: null,
  snapshot: {
    createdAt: null,
    maximumDataDate: null,
    ageSeconds: null,
    staleAfterSeconds: null,
    freshnessStatus: "UNKNOWN",
  },
  provenance: {
    datasetHash: null,
    datasetHashBasis: null,
    configurationHash: null,
    runId: null,
  },
};

export const EMPTY_CLIENT_REQUEST_DIAGNOSTICS: ClientRequestDiagnostics = {
  lastSuccessfulRequest: null,
  endpoint: null,
  clientRequestId: null,
  serverRequestId: null,
  responseTimeMs: null,
  lastError: null,
  failedEndpoints: [],
};

function emptySourceContext(
  dataMode: DataMode,
  reason: string,
): SourceContext {
  return {
    ...EMPTY_SOURCE_CONTEXT,
    activeMode: dataMode,
    configuredMode: dataMode,
    reason,
  };
}

export function createEmptyWorkbenchData(
  dataMode: DataMode = "UNAVAILABLE",
  reason = "The requested portfolio data is unavailable.",
  sourceContext: SourceContext = emptySourceContext(dataMode, reason),
): WorkbenchData {
  return {
    metadata: {
      asOf: "N/A",
      comparisonPeriod: "N/A",
      refreshedAt: "N/A",
      synthetic: sourceContext.synthetic === true,
      qualityStatus: "UNAVAILABLE",
      dataMode,
      sourceContext,
      availableViews: [],
      viewErrors: {},
      rowCount: 0,
      runId: sourceContext.runId ?? "N/A",
      calculationVersion: "N/A",
      serverDiagnostics: EMPTY_SERVER_DIAGNOSTICS,
    },
    filterOptions: {
      reportingMonths: [],
      comparisons: [],
      products: [],
      segments: [],
      channels: [],
      geographies: [],
      riskBands: [],
      strategies: [],
      vintages: [],
      modelVersions: [],
    },
    kpis: [],
    trends: [],
    riskDistribution: [],
    rollRates: { labels: [], values: [] },
    contributors: [],
    alerts: [],
    interpretation: {
      adverse: [],
      favourable: "N/A",
      caveat: "N/A",
      priority: "N/A",
    },
    rootCause: {
      finding: {
        metricId: "N/A",
        comparisonPeriod: "N/A",
        observedChangeBps: 0,
        dataQualityStatus: "UNAVAILABLE",
        primaryDimension: "N/A",
        primaryDriver: "N/A",
        contributionShare: 0,
        mixContributionBps: 0,
        withinSegmentContributionBps: 0,
        supportingDrivers: [],
        causalStatus: "UNAVAILABLE",
        recommendedInvestigation: [],
      },
      lenses: [],
      hierarchy: [],
      behaviouralDrivers: [],
    },
    vintages: [],
    strategies: [],
    strategyValidity: [],
    partners: [],
    vendors: [],
    memberships: [],
    baskets: [],
    finance: {
      bridge: [],
      unitEconomics: [],
      concentration: [],
      driverTree: [],
    },
    dataQuality: {
      score: 0,
      status: "UNAVAILABLE",
      checks: [],
      manifest: [],
      lineage: [],
    },
    scenarios: [],
    investigations: [],
    modelMonitoring: [],
    commentary: {
      sections: [],
      provider: "N/A",
      promptVersion: "N/A",
      status: "UNAVAILABLE",
    },
    marketRiskStatus: null,
    advancedStatisticsStatus: null,
    capabilities: [],
    capabilityRegistry: {
      registryVersion: "N/A",
      schemaVersion: "N/A",
      product: "nAIM Portfolio Intelligence Workbench",
      allowedStatuses: [],
      statusDefinitions: {},
      statusCounts: {},
    },
  };
}

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function asNumber(value: unknown, fallback = 0): number {
  if (value === null || value === undefined || value === "") return fallback;
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function optionalNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function asBoolean(value: unknown, fallback = false): boolean {
  return typeof value === "boolean" ? value : fallback;
}

function dataMode(value: unknown): DataMode | null {
  const candidate = asString(value).toUpperCase() as DataMode;
  return DATA_MODES.has(candidate) ? candidate : null;
}

function capabilityStatus(value: unknown): CapabilityStatus | null {
  const candidate = asString(value).toUpperCase() as CapabilityStatus;
  return CAPABILITY_STATUSES.has(candidate) ? candidate : null;
}

function normalizeSourceContext(
  payload: unknown,
  fallbackMode: DataMode,
): SourceContext {
  const root = asRecord(payload);
  const raw = asRecord(root.source_context ?? root.context);
  const activeMode =
    dataMode(raw.active_mode ?? root.data_mode ?? root.mode) ?? fallbackMode;
  const configuredMode = dataMode(raw.configured_mode) ?? activeMode;
  return {
    activeMode,
    configuredMode,
    snapshotDate: asString(raw.snapshot_date) || null,
    configurationHash: asString(raw.configuration_hash) || null,
    datasetHash: asString(raw.dataset_hash) || null,
    datasetHashBasis: asString(raw.dataset_hash_basis) || null,
    runId: asString(raw.run_id) || null,
    synthetic:
      typeof raw.synthetic === "boolean" ? raw.synthetic : null,
    reason: asString(raw.reason) || null,
  };
}

function normalizeServerDiagnostics(
  payload: unknown,
): ServerDataDiagnostics {
  const root = asRecord(payload);
  const diagnostics = asRecord(root.diagnostics);
  const rawStatus = asString(diagnostics.diagnostic_status).toUpperCase();
  const diagnosticStatus: ServerDataDiagnostics["diagnosticStatus"] =
    rawStatus === "CURRENT" || rawStatus === "STALE" || rawStatus === "UNAVAILABLE"
      ? rawStatus
      : "UNKNOWN";
  const snapshot = asRecord(diagnostics.snapshot);
  const rawFreshness = asString(snapshot.freshness_status).toUpperCase();
  const freshnessStatus: ServerDataDiagnostics["snapshot"]["freshnessStatus"] =
    rawFreshness === "CURRENT" || rawFreshness === "STALE"
      ? rawFreshness
      : "UNKNOWN";
  const provenance = asRecord(diagnostics.provenance);
  return {
    diagnosticStatus,
    serverObservedAt: asString(diagnostics.server_observed_at) || null,
    activeMode: dataMode(diagnostics.active_mode),
    configuredMode: dataMode(diagnostics.configured_mode),
    snapshot: {
      createdAt: asString(snapshot.created_at) || null,
      maximumDataDate: asString(snapshot.maximum_data_date) || null,
      ageSeconds: optionalNumber(snapshot.age_seconds),
      staleAfterSeconds: optionalNumber(snapshot.stale_after_seconds),
      freshnessStatus,
    },
    provenance: {
      datasetHash: asString(provenance.dataset_hash) || null,
      datasetHashBasis: asString(provenance.dataset_hash_basis) || null,
      configurationHash: asString(provenance.configuration_hash) || null,
      runId: asString(provenance.run_id) || null,
    },
  };
}

function configuredFrontendMode(): DataMode | null {
  const raw = process.env.NEXT_PUBLIC_NAIM_DATA_MODE;
  return raw ? dataMode(raw) : null;
}

function status(value: unknown, fallback: SignalStatus = "Stable"): SignalStatus {
  const normalized = asString(value).toLowerCase().replaceAll("_", " ");
  if (normalized.includes("critical") || normalized.includes("fail")) {
    return "Critical";
  }
  if (normalized.includes("adverse") || normalized.includes("breach")) {
    return "Adverse";
  }
  if (normalized.includes("watch") || normalized.includes("warning")) {
    return "Watch";
  }
  if (normalized.includes("favourable") || normalized.includes("pass")) {
    return "Favourable";
  }
  if (
    normalized.includes("neutral") ||
    normalized.includes("stable") ||
    normalized.includes("unchanged")
  ) {
    return "Stable";
  }
  return fallback;
}

const API_METRIC_ID_ALIASES: Record<string, string> = {
  ANNUALISED_NET_LOSS_RATE: "ANNUALISED_LOSS_RATE",
  DELINQUENCY_30_ACCOUNT_RATE: "DELINQUENCY_30_RATE",
  CUSTOMER_FRICTION_RATE: "FRICTION_RATE",
};

function displayMetricId(value: unknown): string {
  const raw = asString(value);
  return API_METRIC_ID_ALIASES[raw] ?? raw;
}

function numericString(value: unknown, fallback = "Not supplied"): string {
  if (typeof value === "string" && value.trim()) return value;
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed.toLocaleString() : fallback;
}

function formatKpiDenominator(metricId: string, value: unknown): string {
  if (typeof value === "string" && value.trim()) return value;
  const parsed = asNumber(value, Number.NaN);
  if (!Number.isFinite(parsed)) return "See governed metric registry";
  const formatted = parsed.toLocaleString(undefined, {
    maximumFractionDigits: 2,
  });
  if (metricId === "ACTIVE_ACCOUNTS") return `${formatted} active accounts`;
  if (metricId === "TRANSACTION_VALUE" || metricId === "FRAUD_BPS") {
    return `${formatted} currency units of eligible purchase volume`;
  }
  if (metricId === "ANNUALISED_LOSS_RATE") {
    return `${formatted} currency units of average receivables`;
  }
  if (
    metricId === "DELINQUENCY_30_RATE" ||
    metricId === "FRICTION_RATE" ||
    metricId === "ATTRITION_RATE"
  ) {
    return `${formatted} eligible active accounts`;
  }
  if (metricId === "MANUAL_REVIEW_RATE") {
    return `${formatted} eligible transactions`;
  }
  if (metricId === "FALSE_POSITIVE_RATE") {
    return `${formatted} reviewed alerts`;
  }
  if (metricId === "EXPECTED_PROFIT") {
    return "Portfolio-level planning measure";
  }
  return `${formatted} governed denominator units`;
}

function filtersToQuery(filters: GlobalFilters): string {
  const parameters = new URLSearchParams();
  const entries: Array<[string, string]> = [
    ["reporting_month", filters.reportingMonth],
    ["product", filters.product],
    ["customer_segment", filters.segment],
    ["acquisition_channel", filters.channel],
    ["geography", filters.geography],
    ["risk_band", filters.riskBand],
    ["strategy", filters.strategy],
    ["model_version", filters.modelVersion],
  ];
  entries.forEach(([key, value]) => {
    if (value && !value.startsWith("All ")) parameters.set(key, value);
  });
  return parameters.toString();
}

interface FetchEnvelope {
  payload: unknown;
  headerMode: DataMode | null;
  request?: RequestTrace;
}

interface RequestTrace {
  endpoint: string;
  clientRequestId: string;
  serverRequestId: string | null;
  completedAt: string;
  completedAtEpoch: number;
  responseTimeMs: number;
  error: string | null;
}

class TrackedRequestError extends Error {
  request: RequestTrace;

  constructor(message: string, request: RequestTrace) {
    super(message);
    this.name = "TrackedRequestError";
    this.request = request;
  }
}

function createClientRequestId(): string {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return `NAIM-WEB-${globalThis.crypto.randomUUID()}`;
  }
  return `NAIM-WEB-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

async function fetchJson(
  endpoint: string,
  query: string,
  outerSignal?: AbortSignal,
): Promise<FetchEnvelope> {
  const clientRequestId = createClientRequestId();
  const startedAt = performance.now();
  let serverRequestId: string | null = null;
  const timeout = AbortSignal.timeout(12000);
  const signal = outerSignal
    ? AbortSignal.any([outerSignal, timeout])
    : timeout;
  try {
    const response = await fetch(
      `${API_BASE}/api/v1/${endpoint}${query ? `?${query}` : ""}`,
      {
        headers: { Accept: "application/json" },
        signal,
        cache: "no-store",
      },
    );
    serverRequestId = response.headers.get("X-Request-ID");
    if (!response.ok) {
      throw new Error(`${endpoint} returned ${response.status}`);
    }
    const contentType = response.headers.get("content-type") ?? "";
    if (!contentType.includes("application/json")) {
      throw new Error(`${endpoint} did not return JSON`);
    }
    const payload: unknown = await response.json();
    const headerMode = dataMode(response.headers.get("X-nAIM-Data-Mode"));
    const bodyMode = dataMode(asRecord(payload).data_mode);
    if (headerMode && bodyMode && headerMode !== bodyMode) {
      throw new Error(`${endpoint} returned conflicting data-mode provenance`);
    }
    const completedAtEpoch = performance.timeOrigin + performance.now();
    return {
      payload,
      headerMode,
      request: {
        endpoint,
        clientRequestId,
        serverRequestId,
        completedAt: new Date(completedAtEpoch).toISOString(),
        completedAtEpoch,
        responseTimeMs: Math.max(0, performance.now() - startedAt),
        error: null,
      },
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : `${endpoint} failed`;
    const completedAtEpoch = performance.timeOrigin + performance.now();
    throw new TrackedRequestError(message, {
      endpoint,
      clientRequestId,
      serverRequestId,
      completedAt: new Date(completedAtEpoch).toISOString(),
      completedAtEpoch,
      responseTimeMs: Math.max(0, performance.now() - startedAt),
      error: message,
    });
  }
}

function summarizeRequestDiagnostics(
  results: Array<PromiseSettledResult<FetchEnvelope>>,
): ClientRequestDiagnostics {
  const successes = results.flatMap((result) =>
    result.status === "fulfilled" && result.value.request
      ? [result.value.request]
      : [],
  );
  const failures = results.flatMap((result) =>
    result.status === "rejected" && result.reason instanceof TrackedRequestError
      ? [result.reason.request]
      : [],
  );
  const latestSuccess = [...successes].sort(
    (left, right) => right.completedAtEpoch - left.completedAtEpoch,
  )[0];
  const latestFailure = [...failures].sort(
    (left, right) => right.completedAtEpoch - left.completedAtEpoch,
  )[0];
  const latestAttempt = [...successes, ...failures].sort(
    (left, right) => right.completedAtEpoch - left.completedAtEpoch,
  )[0];
  return {
    lastSuccessfulRequest: latestSuccess?.completedAt ?? null,
    endpoint: latestAttempt?.endpoint ?? null,
    clientRequestId: latestAttempt?.clientRequestId ?? null,
    serverRequestId: latestAttempt?.serverRequestId ?? null,
    responseTimeMs: latestAttempt?.responseTimeMs ?? null,
    lastError: latestFailure?.error ?? null,
    failedEndpoints: [...new Set(failures.map((item) => item.endpoint))],
  };
}

function mergeValidationFailures(
  diagnostics: ClientRequestDiagnostics,
  failures: Map<string, string>,
): ClientRequestDiagnostics {
  const failedEndpoints = [
    ...new Set([...diagnostics.failedEndpoints, ...failures.keys()]),
  ];
  const validationError = [...failures.values()].at(-1) ?? null;
  return {
    ...diagnostics,
    lastError: validationError ?? diagnostics.lastError,
    failedEndpoints,
  };
}

async function postJson(
  endpoint: string,
  payload: Record<string, unknown>,
  expectedMode: DataMode,
  query = "",
): Promise<FetchEnvelope> {
  const response = await fetch(
    `${API_BASE}/api/v1/${endpoint}${query ? `?${query}` : ""}`,
    {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(60000),
    cache: "no-store",
    },
  );
  if (!response.ok) {
    let detail = "";
    try {
      const errorPayload = asRecord(await response.json());
      detail = asString(errorPayload.detail);
    } catch {
      // The status code still provides a portable failure when no JSON body exists.
    }
    throw new Error(
      detail
        ? `${endpoint} returned ${response.status}: ${detail}`
        : `${endpoint} returned ${response.status}`,
    );
  }
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    throw new Error(`${endpoint} did not return JSON`);
  }
  const responsePayload: unknown = await response.json();
  const headerMode = dataMode(response.headers.get("X-nAIM-Data-Mode"));
  const bodyMode = dataMode(asRecord(responsePayload).data_mode);
  const returnedMode = bodyMode ?? headerMode;
  if (!returnedMode || returnedMode !== expectedMode) {
    throw new Error(
      `${endpoint} returned ${returnedMode ?? "no mode"} while ${expectedMode} is active`,
    );
  }
  if (!hasDeclaredSourceContext(responsePayload)) {
    throw new Error(`${endpoint} did not supply source context`);
  }
  return { payload: responsePayload, headerMode };
}

function normalizeMarketRiskStatus(payload: unknown): MarketRiskStatus | null {
  const root = asRecord(payload);
  const externalProvider = capabilityStatus(root.external_provider);
  const instruments = stringArray(root.instruments);
  const methods = stringArray(root.methods);
  if (
    !asBoolean(root.available) ||
    asString(root.status).toUpperCase() !== "LIVE" ||
    !externalProvider ||
    instruments.length === 0 ||
    methods.length === 0
  ) {
    return null;
  }
  return {
    available: true,
    status: "LIVE",
    providerMode: asString(root.provider_mode, "Not supplied"),
    instruments,
    externalProvider,
    methods,
    tradingRecommendation: asBoolean(root.trading_recommendation),
    approvalRequired: asBoolean(root.approval_required, true),
  };
}

const ADVANCED_METHOD_LABELS: Record<string, string> = {
  kaplan_meier_and_log_rank: "Kaplan–Meier and log-rank",
  behavioural_model_and_fallback_contributions:
    "Behavioural model and fallback contributions",
  shap: "SHAP explanations",
  single_change_point: "Single change-point detection",
  propensity_weighting: "Propensity weighting",
  synthetic_policy_difference_in_differences:
    "Synthetic-policy difference-in-differences",
  cox_proportional_hazards: "Cox proportional hazards",
};

function normalizeAdvancedStatisticsStatus(
  payload: unknown,
): AdvancedStatisticsStatus | null {
  const root = asRecord(payload);
  const rawMethods = asRecord(root.methods);
  const methods = Object.entries(rawMethods).flatMap(([id, value]) => {
    const methodStatus = capabilityStatus(value);
    if (!methodStatus) return [];
    return [{
      id,
      name: ADVANCED_METHOD_LABELS[id] ?? id.replaceAll("_", " "),
      status: methodStatus,
    }];
  });
  if (
    !asBoolean(root.available) ||
    asString(root.status).toUpperCase() !== "LIVE" ||
    methods.length === 0
  ) {
    return null;
  }
  return {
    available: true,
    status: "LIVE",
    methods,
    causalClaim: asBoolean(root.causal_claim),
    approvalRequired: asBoolean(root.approval_required, true),
  };
}

async function loadStatusEnvelope(
  endpoint: "market-risk/status" | "advanced-statistics/status",
  expectedMode: DataMode,
): Promise<unknown> {
  const envelope = await fetchJson(endpoint, "");
  const returnedMode = declaredPayloadMode(envelope);
  if (!returnedMode || returnedMode !== expectedMode) {
    throw new Error(
      `${endpoint} returned ${returnedMode ?? "no mode"} while ${expectedMode} is active`,
    );
  }
  if (!hasDeclaredSourceContext(envelope.payload)) {
    throw new Error(`${endpoint} did not supply source context`);
  }
  return envelope.payload;
}

export async function loadMarketRiskStatus(
  expectedMode: DataMode,
): Promise<MarketRiskStatus> {
  const status = normalizeMarketRiskStatus(
    await loadStatusEnvelope("market-risk/status", expectedMode),
  );
  if (!status) throw new Error("Market-risk status response was incomplete");
  return status;
}

export async function loadAdvancedStatisticsStatus(
  expectedMode: DataMode,
): Promise<AdvancedStatisticsStatus> {
  const status = normalizeAdvancedStatisticsStatus(
    await loadStatusEnvelope("advanced-statistics/status", expectedMode),
  );
  if (!status) {
    throw new Error("Advanced-statistics status response was incomplete");
  }
  return status;
}

export interface MarketRiskRunRequest {
  instrument: "NAIM-DEMO-INDEX" | "NAIM-DEMO-EQUITY";
  period: "one_year" | "three_years" | "five_years";
  frequency: "daily" | "weekly" | "monthly";
  returnType: "simple" | "log";
  confidence: number;
}

export async function runMarketRiskLab(
  request: MarketRiskRunRequest,
  expectedMode: DataMode,
): Promise<MarketRiskRunResult> {
  const envelope = await postJson(
    "market-risk/run",
    {
      instrument: request.instrument,
      period: request.period,
      end_date: "2025-12-31",
      frequency: request.frequency,
      return_type: request.returnType,
      confidence: request.confidence,
    },
    expectedMode,
  );
  const root = asRecord(envelope.payload);
  const source = asRecord(root.source);
  const returns = asRecord(root.returns);
  const returnSummary = asRecord(returns.summary);
  const ewma = asRecord(root.ewma);
  const conditional = asRecord(root.conditional_volatility);
  const arch = asRecord(conditional.arch);
  const garch = asRecord(conditional.garch);
  const comparison = asRecord(root.model_comparison);
  const ranking = stringArray(comparison.qlike_ranking);
  const models = asArray(comparison.models).map((raw) => {
    const row = asRecord(raw);
    const model = asString(row.model, "unnamed");
    const rank = ranking.indexOf(model);
    return {
      model,
      oneStepForecast: optionalNumber(row.one_step_forecast),
      qlike: optionalNumber(row.out_of_sample_qlike),
      rmseVariance: optionalNumber(row.out_of_sample_rmse_variance),
      persistence: optionalNumber(row.parameter_persistence),
      diagnosticStatus: asString(row.diagnostic_status, "Not supplied"),
      rank: rank >= 0 ? rank + 1 : null,
    };
  });
  const tailRoot = asRecord(root.var_expected_shortfall);
  const tailRisk = Object.entries(asRecord(tailRoot.methods)).map(
    ([method, raw]) => {
      const row = asRecord(raw);
      return {
        method,
        valueAtRisk: optionalNumber(row.var),
        expectedShortfall: optionalNumber(row.expected_shortfall),
        tailObservations: optionalNumber(row.tail_observations),
        status: asString(row.status, "implemented"),
      };
    },
  );
  const backtest = asRecord(root.var_backtesting);
  const trafficLight = asRecord(backtest.traffic_light);
  const kupiec = asRecord(backtest.kupiec_unconditional_coverage);
  const christoffersen = asRecord(backtest.christoffersen_independence);
  const regimeRoot = asRecord(root.regimes);
  const regimes = asArray(regimeRoot.series)
    .slice(-120)
    .map((raw) => {
      const row = asRecord(raw);
      return {
        date: asString(row.date, "N/A"),
        volatility: optionalNumber(row.annualised_volatility),
        regime: asString(row.regime, "unclassified"),
        changePoint: asBoolean(row.change_point_indicator),
      };
    });
  const regimeCounts = Object.entries(asRecord(regimeRoot.observation_counts)).map(
    ([regime, observations]) => ({
      regime,
      observations: asNumber(observations),
    }),
  );
  const validation = asRecord(root.validation);
  const responseMode =
    dataMode(root.data_mode ?? envelope.headerMode) ?? expectedMode;
  const sourceContext = normalizeSourceContext(root, responseMode);
  return {
    evidenceId: asString(root.evidence_id, "Not supplied"),
    purpose: asString(root.purpose, "Quantitative risk diagnostics only."),
    dataMode: responseMode,
    sourceContext,
    source: {
      instrument: asString(source.instrument, request.instrument),
      provider: asString(source.provider, "Not supplied"),
      requestedStartDate: asString(source.requested_start_date, "N/A"),
      requestedEndDate: asString(source.requested_end_date, "N/A"),
      priceBasis: asString(source.price_basis, "Not supplied"),
      sourceHash: asString(source.raw_source_sha256, "Not supplied"),
      synthetic: asBoolean(source.source_is_synthetic),
      redistributionPermitted: asBoolean(source.redistribution_permitted),
      terms: asString(source.provider_terms, "Not supplied"),
    },
    observations: asNumber(returnSummary.observations),
    annualisedVolatility: optionalNumber(
      returnSummary.annualised_standard_deviation,
    ),
    ewmaLatest: optionalNumber(ewma.latest_annualised_volatility),
    ewmaForecast: optionalNumber(
      ewma.one_step_annualised_volatility_forecast,
    ),
    archForecast: optionalNumber(asArray(arch.annualised_volatility_forecast)[0]),
    garchForecast: optionalNumber(asArray(garch.annualised_volatility_forecast)[0]),
    models,
    tailRisk,
    backtest: {
      breachCount: optionalNumber(backtest.breach_count),
      observedBreachRate: optionalNumber(backtest.observed_breach_rate),
      trafficLight: asString(trafficLight.status, "Not supplied"),
      kupiecPValue: optionalNumber(kupiec.p_value),
      christoffersenPValue: optionalNumber(christoffersen.p_value),
    },
    regimes,
    regimeCounts,
    validation: {
      status: asString(validation.status, "UNAVAILABLE"),
      publicationAllowed: asBoolean(validation.publication_allowed),
      publicationBasis: asString(
        validation.publication_basis,
        "Publication basis was not supplied.",
      ),
    },
    approvalRequired: asBoolean(root.approval_required, true),
    synthetic: asBoolean(root.synthetic, asBoolean(source.source_is_synthetic)),
  };
}

export async function generateExport(
  kind: "excel" | "powerbi",
): Promise<GeneratedExport> {
  const response = await fetch(`${API_BASE}/api/v1/exports/${kind}`, {
    method: "POST",
    headers: { Accept: "application/json" },
    signal: AbortSignal.timeout(60000),
  });
  if (!response.ok) {
    throw new Error(`Export service returned ${response.status}`);
  }
  const payload = asRecord(await response.json());
  const relativeUrl = asString(payload.download_url);
  const origin =
    API_BASE || (typeof window === "undefined" ? "http://127.0.0.1" : window.location.origin);
  return {
    artifactId: asString(payload.artifact_id),
    filename: asString(payload.filename, `${kind}-export`),
    sizeBytes: asNumber(payload.size_bytes),
    downloadUrl: relativeUrl
      ? new URL(relativeUrl, `${origin}/`).toString()
      : "",
  };
}

export class GovernedWorkflowError extends Error {
  stage: string;

  constructor(message: string, stage: string) {
    super(message);
    this.name = "GovernedWorkflowError";
    this.stage = stage;
  }
}

function publicWorkflowUrl(relativeUrl: string): string {
  if (!relativeUrl) return "";
  const origin =
    API_BASE ||
    (typeof window === "undefined" ? "http://127.0.0.1" : window.location.origin);
  return new URL(relativeUrl, `${origin}/`).toString();
}

function textList(value: unknown): string[] {
  if (typeof value === "string" && value.trim()) return [value.trim()];
  return asArray(value).map((item) => asString(item)).filter(Boolean);
}

function textRecord(value: unknown): Record<string, string> {
  return Object.fromEntries(
    Object.entries(asRecord(value)).flatMap(([key, item]) => {
      const normalized = asString(item);
      return normalized ? [[key, normalized]] : [];
    }),
  );
}

async function governedWorkflowJson(
  endpoint: string,
  init: RequestInit,
  initialStage: string,
): Promise<Record<string, unknown>> {
  const response = await fetch(`${API_BASE}/api/v1/${endpoint}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
    signal: AbortSignal.timeout(60000),
    cache: "no-store",
  });
  let payload: Record<string, unknown> = {};
  try {
    payload = asRecord(await response.json());
  } catch {
    // The status remains a truthful fallback when a proxy strips the JSON body.
  }
  if (!response.ok) {
    const detail = asRecord(payload.detail);
    throw new GovernedWorkflowError(
      asString(
        detail.error ?? detail.message ?? payload.detail,
        `${endpoint} returned ${response.status}`,
      ),
      asString(payload.stage ?? detail.stage, initialStage),
    );
  }
  return payload;
}

export async function runPortfolioStory(
  expectedMode: "DEMO" | "OFFLINE_SNAPSHOT",
): Promise<PortfolioStoryRun> {
  const root = await governedWorkflowJson(
    "demo/run",
    { method: "POST" },
    "create_or_reuse_demo_run",
  );
  const activeMode = dataMode(root.active_mode ?? root.data_mode);
  if (activeMode !== expectedMode) {
    throw new GovernedWorkflowError(
      `The governed story returned ${activeMode ?? "no active mode"} while ${expectedMode} is active.`,
      "confirm_data_mode",
    );
  }
  const runId = asString(root.demo_run_id ?? root.run_id);
  if (!runId) {
    throw new GovernedWorkflowError(
      "The governed story did not return a demo run ID.",
      "create_or_reuse_demo_run",
    );
  }
  const workspace = asRecord(root.workspace);
  const scope = asRecord(root.scope);
  const quality = asRecord(root.data_quality);
  const story = asRecord(root.story);
  const completeness = quality.completeness_percentage;
  const run: PortfolioStoryRun = {
    runId,
    reused: asBoolean(root.reused),
    status: asString(root.status, "completed"),
    activeMode,
    sourceContext: normalizeSourceContext(root, activeMode),
    workspace: {
      id: asString(workspace.workspace_id),
      name: asString(workspace.workspace_name, "Approved portfolio story workspace"),
      reportingPeriod: asString(workspace.reporting_period),
      comparisonPeriod: asString(workspace.comparison_period),
      approvalState: asString(workspace.approval_state, "APPROVED"),
    },
    scope: {
      reportingPeriod: asString(scope.reporting_period ?? workspace.reporting_period),
      comparisonPeriod: asString(scope.comparison_period ?? workspace.comparison_period),
      filters: textRecord(scope.filters ?? workspace.filter_configuration),
    },
    dataQuality: {
      status: asString(quality.status, "UNAVAILABLE"),
      publicationAllowed: asBoolean(quality.publication_allowed),
      latestAvailableMonth: asString(quality.latest_available_month),
      completenessPercentage:
        completeness === null || completeness === undefined
          ? null
          : asNumber(completeness),
    },
    story: {
      whatChanged: asString(story.what_changed, "No governed movement was returned."),
      why: asString(story.why, "No governed explanation was returned."),
      uncertainties: textList(story.uncertainties),
      supportedAction: asString(
        story.supported_action,
        "Continue governed monitoring; no automated policy action is supported.",
      ),
      evidenceProduced: textList(story.evidence_produced),
      outputsAvailable: textList(story.outputs_available),
    },
    evidence: asRecord(root.evidence),
    investigation: asRecord(root.investigation),
    commentary: asRecord(root.commentary),
    outputs: asArray(root.outputs).map(asRecord),
    steps: asArray(root.steps).map(asRecord),
  };
  if (!run.workspace.id || run.workspace.approvalState.toUpperCase() !== "APPROVED") {
    throw new GovernedWorkflowError(
      "The governed story did not return an approved workspace.",
      "load_approved_workspace",
    );
  }
  if (!run.scope.reportingPeriod || !run.scope.comparisonPeriod) {
    throw new GovernedWorkflowError(
      "The governed story did not return reporting and comparison scope.",
      "set_reporting_scope",
    );
  }
  if (!run.dataQuality.publicationAllowed) {
    throw new GovernedWorkflowError(
      `The governed story data-quality gate returned ${run.dataQuality.status}.`,
      "confirm_data_quality",
    );
  }
  if (
    !run.story.whatChanged ||
    !run.story.why ||
    run.story.evidenceProduced.length === 0 ||
    run.story.outputsAvailable.length === 0
  ) {
    throw new GovernedWorkflowError(
      "The governed story result was incomplete.",
      "assemble_story_result",
    );
  }
  return run;
}

export interface ExecutivePackRequest {
  workspaceId?: string;
  reportingPeriod?: string;
  comparisonPeriod?: string;
  filterScope?: Record<string, unknown>;
}

function normalizeExecutivePack(
  root: Record<string, unknown>,
  expectedMode: DataMode,
  fallback?: ExecutivePackResult,
): ExecutivePackResult {
  const returnedMode = dataMode(root.data_mode) ?? fallback?.dataMode ?? null;
  if (returnedMode !== expectedMode) {
    throw new GovernedWorkflowError(
      `The executive pack returned ${returnedMode ?? "no active mode"} while ${expectedMode} is active.`,
      asString(root.stage, "validating_scope"),
    );
  }
  const format = asString(root.format, fallback?.format ?? "").toLowerCase();
  if (format !== "pptx") {
    throw new GovernedWorkflowError(
      `The governed export returned ${format || "no format"}; an editable PowerPoint was required.`,
      asString(root.stage, "validating_file"),
    );
  }
  return {
    jobId: asString(root.job_id, fallback?.jobId ?? ""),
    artifactId: asString(root.artifact_id, fallback?.artifactId ?? ""),
    status: asString(root.status, fallback?.status ?? "unknown"),
    reused: asBoolean(root.reused, fallback?.reused ?? false),
    stage: asString(root.stage, fallback?.stage ?? "unknown"),
    lastCompletedStage: asString(
      root.last_completed_stage,
      fallback?.lastCompletedStage ?? "",
    ),
    filename: asString(root.filename, fallback?.filename ?? "executive-pack.pptx"),
    format: "pptx",
    slideCount: asNumber(root.slide_count, fallback?.slideCount ?? 0),
    fileSha256: asString(root.file_sha256, fallback?.fileSha256 ?? ""),
    sizeBytes: asNumber(root.size_bytes, fallback?.sizeBytes ?? 0),
    scope: Object.keys(asRecord(root.scope)).length > 0
      ? asRecord(root.scope)
      : fallback?.scope ?? {},
    dataMode: returnedMode,
    evidenceId: asString(root.evidence_id, fallback?.evidenceId ?? ""),
    metricRegistryVersion: asString(
      root.metric_registry_version,
      fallback?.metricRegistryVersion ?? "",
    ),
    syntheticStatement: asString(
      root.synthetic_statement,
      fallback?.syntheticStatement ?? "",
    ),
    refreshedAt: asString(root.refreshed_at, fallback?.refreshedAt ?? ""),
    validation: Object.keys(asRecord(root.validation)).length > 0
      ? asRecord(root.validation)
      : fallback?.validation ?? {},
    reconciliation: Object.keys(asRecord(root.reconciliation)).length > 0
      ? asRecord(root.reconciliation)
      : fallback?.reconciliation ?? {},
    downloadUrl: publicWorkflowUrl(
      asString(root.download_url, fallback?.downloadUrl ?? ""),
    ),
    manifestUrl: publicWorkflowUrl(
      asString(root.manifest_url, fallback?.manifestUrl ?? ""),
    ),
  };
}

export async function generateExecutivePack(
  request: ExecutivePackRequest,
  expectedMode: DataMode,
): Promise<ExecutivePackResult> {
  const createdPayload = await governedWorkflowJson(
    "executive-packs/generate",
    {
      method: "POST",
      body: JSON.stringify({
        workspace_id: request.workspaceId || undefined,
        reporting_period: request.reportingPeriod || undefined,
        comparison_period: request.comparisonPeriod || undefined,
        filter_scope: request.filterScope ?? {},
        include_pdf: false,
      }),
    },
    "validating_scope",
  );
  const created = normalizeExecutivePack(createdPayload, expectedMode);
  if (!created.jobId) {
    throw new GovernedWorkflowError(
      "The executive-pack workflow did not return a job ID.",
      created.stage,
    );
  }
  const statusPayload = await governedWorkflowJson(
    `executive-packs/${encodeURIComponent(created.jobId)}`,
    { method: "GET" },
    "reading_job_status",
  );
  const completed = normalizeExecutivePack(statusPayload, expectedMode, created);
  const validationStatus = asString(completed.validation.status).toUpperCase();
  const reconciliationStatus = asString(
    completed.reconciliation.status,
  ).toUpperCase();
  if (completed.status.toLowerCase() !== "completed") {
    throw new GovernedWorkflowError(
      `Executive-pack job ${completed.jobId} returned ${completed.status}.`,
      completed.stage,
    );
  }
  if (validationStatus !== "PASS") {
    throw new GovernedWorkflowError(
      `Executive-pack validation returned ${validationStatus || "no status"}.`,
      "validating_file",
    );
  }
  if (reconciliationStatus !== "PASS") {
    throw new GovernedWorkflowError(
      `Executive-pack reconciliation returned ${reconciliationStatus || "no status"}.`,
      "reconciling",
    );
  }
  if (
    !completed.filename.toLowerCase().endsWith(".pptx") ||
    !completed.downloadUrl ||
    !completed.manifestUrl
  ) {
    throw new GovernedWorkflowError(
      "The validated PowerPoint, manifest, or download link was missing.",
      "presenting_download",
    );
  }
  return completed;
}

export async function createInvestigation(
  payload: {
    alertId?: string;
    businessQuestion: string;
    affectedMetric?: string;
    hypothesis?: string;
    owner?: string;
  },
): Promise<Record<string, unknown>> {
  const response = await fetch(`${API_BASE}/api/v1/investigations`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      alert_id: payload.alertId,
      business_question: payload.businessQuestion,
      affected_metric: payload.affectedMetric,
      hypothesis: payload.hypothesis,
      owner: payload.owner ?? "Portfolio Analytics",
    }),
    signal: AbortSignal.timeout(12000),
  });
  if (!response.ok) {
    throw new Error(`Investigation service returned ${response.status}`);
  }
  return asRecord(await response.json());
}

async function readGovernedAlertEndpoint(
  endpoint: string,
  expectedMode: DataMode,
  filters?: GlobalFilters,
): Promise<unknown> {
  const envelope = await fetchJson(
    endpoint,
    filters ? filtersToQuery(filters) : "",
  );
  const returnedMode = declaredPayloadMode(envelope);
  if (!returnedMode || returnedMode !== expectedMode) {
    throw new Error(
      `${endpoint} returned ${returnedMode ?? "no mode"} while ${expectedMode} is active`,
    );
  }
  if (!hasDeclaredSourceContext(envelope.payload)) {
    throw new Error(`${endpoint} did not supply source context`);
  }
  return envelope.payload;
}

function requireNewerDurableAlert(
  payload: unknown,
  expectedVersion: number,
): AlertRecord {
  const alert = normalizeDurableAlertPayload(payload);
  if (!alert?.lifecycle) {
    throw new Error("The alert service returned an incomplete durable alert.");
  }
  if (alert.lifecycle.version <= expectedVersion) {
    throw new Error(
      `The alert service did not advance version ${expectedVersion}.`,
    );
  }
  return alert;
}

export async function loadDurableAlert(
  alertId: string,
  expectedMode: DataMode,
  filters?: GlobalFilters,
): Promise<AlertRecord> {
  const payload = await readGovernedAlertEndpoint(
    `alerts/${encodeURIComponent(alertId)}`,
    expectedMode,
    filters,
  );
  const alert = normalizeDurableAlertPayload(payload);
  if (!alert) {
    throw new Error("The alert detail response was incomplete or malformed.");
  }
  return alert;
}

export async function loadDurableAlertAudit(
  alertId: string,
  expectedMode: DataMode,
  filters?: GlobalFilters,
): Promise<AlertAuditTrail> {
  const payload = await readGovernedAlertEndpoint(
    `alerts/${encodeURIComponent(alertId)}/audit`,
    expectedMode,
    filters,
  );
  const root = asRecord(payload);
  const returnedAlertId = strictString(root.alert_id);
  const fingerprint = strictString(root.fingerprint);
  const version = strictInteger(root.version, 1);
  if (!Array.isArray(root.audit_events)) {
    throw new Error("The alert audit response did not return an event list.");
  }
  const auditEvents = root.audit_events.map(normalizeAlertAuditEvent);
  const auditIntegrity = normalizeAlertAuditIntegrity(root.audit_integrity);
  if (
    !returnedAlertId ||
    !fingerprint ||
    version === null ||
    auditEvents.some((event) => event === null) ||
    !auditIntegrity ||
    auditIntegrity.eventCount !== auditEvents.length
  ) {
    throw new Error("The alert audit response was incomplete or malformed.");
  }
  return {
    alertId: returnedAlertId,
    fingerprint,
    version,
    auditEvents: auditEvents as AlertAuditEvent[],
    auditIntegrity,
  };
}

export async function acknowledgeDurableAlert(
  alertId: string,
  expectedVersion: number,
  note: string,
  expectedMode: DataMode,
  filters?: GlobalFilters,
): Promise<AlertRecord> {
  const trimmedNote = note.trim();
  if (!trimmedNote) {
    throw new Error("Acknowledgement requires a non-empty note.");
  }
  const envelope = await postJson(
    `alerts/${encodeURIComponent(alertId)}/acknowledge`,
    { expected_version: expectedVersion, note: trimmedNote },
    expectedMode,
    filters ? filtersToQuery(filters) : "",
  );
  return requireNewerDurableAlert(envelope.payload, expectedVersion);
}

export interface AlertTransitionRequest {
  expectedVersion: number;
  targetStatus: AlertLifecycleTransition;
  reason: string;
  owner?: string;
  relatedInvestigation?: string;
  suppressionUntilPeriod?: string;
}

export async function transitionDurableAlert(
  alertId: string,
  request: AlertTransitionRequest,
  expectedMode: DataMode,
  filters?: GlobalFilters,
): Promise<AlertRecord> {
  if (!isAlertLifecycleTransition(request.targetStatus)) {
    throw new Error("The requested alert transition is not governed.");
  }
  const reason = request.reason.trim();
  if (!reason) {
    throw new Error("Every alert transition requires a non-empty reason.");
  }
  const payload: Record<string, unknown> = {
    expected_version: request.expectedVersion,
    target_status: request.targetStatus,
    reason,
  };
  if (request.owner?.trim()) payload.owner = request.owner.trim();
  if (request.relatedInvestigation?.trim()) {
    payload.related_investigation = request.relatedInvestigation.trim();
  }
  if (request.suppressionUntilPeriod?.trim()) {
    payload.suppression_until_period = request.suppressionUntilPeriod.trim();
  }
  const envelope = await postJson(
    `alerts/${encodeURIComponent(alertId)}/transition`,
    payload,
    expectedMode,
    filters ? filtersToQuery(filters) : "",
  );
  return requireNewerDurableAlert(envelope.payload, request.expectedVersion);
}

export async function createAndLinkAlertInvestigation(
  request: {
    alertId: string;
    expectedVersion: number;
    reason: string;
    owner: string;
  },
  expectedMode: DataMode,
  filters?: GlobalFilters,
): Promise<{ alert: AlertRecord; investigationId: string }> {
  const reason = request.reason.trim();
  if (!reason) {
    throw new Error("Starting an investigation requires a transition reason.");
  }
  const envelope = await postJson(
    `alerts/${encodeURIComponent(request.alertId)}/investigation`,
    {
      expected_version: request.expectedVersion,
      reason,
      owner: request.owner.trim(),
    },
    expectedMode,
    filters ? filtersToQuery(filters) : "",
  );
  const root = asRecord(envelope.payload);
  const investigation = asRecord(root.investigation);
  const investigationId = strictString(investigation.investigation_id);
  const linkedAlertId = strictString(investigation.alert_id);
  if (!investigationId || linkedAlertId !== request.alertId) {
    throw new Error(
      "The investigation service did not return a durable investigation linked to this alert.",
    );
  }
  const alert = normalizeDurableAlertPayload(root.alert);
  if (
    !alert?.lifecycle ||
    alert.lifecycle.version < request.expectedVersion ||
    alert.lifecycle.relatedInvestigation !== investigationId ||
    alert.lifecycle.status !== "INVESTIGATING"
  ) {
    throw new Error(
      "The alert service did not return the governed investigation linkage.",
    );
  }
  return { alert, investigationId };
}

function normalizedDirectionality(
  value: unknown,
): MetricDirectionality {
  const candidate = asString(value);
  if (
    candidate === "higher_is_better" ||
    candidate === "lower_is_better" ||
    candidate === "contextual"
  ) {
    return candidate;
  }
  return "UNAVAILABLE";
}

function metricRegistryRows(value: unknown): Map<string, Record<string, unknown>> {
  const rows = asArray(asRecord(value).data ?? value);
  return new Map(
    rows.flatMap((raw) => {
      const row = asRecord(raw);
      const id = displayMetricId(row.metric_id ?? row.id);
      return id ? [[id, row] as const] : [];
    }),
  );
}

function normalizeKpis(
  value: unknown,
  registryPayload?: unknown,
  existingMetrics: KpiMetric[] = [],
): KpiMetric[] {
  const rows = asArray(value);
  if (rows.length === 0) return [];
  const registryById = metricRegistryRows(registryPayload);
  const existingById = new Map(existingMetrics.map((item) => [item.id, item]));
  return rows.flatMap((raw) => {
    const row = asRecord(raw);
    const id = displayMetricId(row.metric_id ?? row.id);
    if (!id) return [];
    const registry = registryById.get(id) ?? {};
    const existing = existingById.get(id);
    const rawUnit = row.unit ?? registry.unit;
    const hasCurrent = row.value !== null && row.value !== undefined;
    const hasPrior =
      row.prior_value !== null && row.prior_value !== undefined ||
      row.prior !== null && row.prior !== undefined;
    const current = hasCurrent
      ? scaleMetricValue(asNumber(row.value), rawUnit)
      : null;
    const prior = hasPrior
      ? scaleMetricValue(asNumber(row.prior_value ?? row.prior), rawUnit)
      : null;
    const absoluteChange =
      row.absolute_change !== null && row.absolute_change !== undefined
        ? scaleMetricValue(asNumber(row.absolute_change), rawUnit)
        : current !== null && prior !== null
          ? current - prior
          : null;
    const relativeChange =
      row.relative_change !== null && row.relative_change !== undefined
        ? asNumber(row.relative_change)
        : current !== null && prior !== null && prior !== 0
          ? (current - prior) / Math.abs(prior)
          : null;
    const definition = asRecord(row.definition);
    const rawLineage = asRecord(row.lineage);
    const transformation = asRecord(
      rawLineage.transformation ?? registry.transformation,
    );
    const refreshFacts = asRecord(
      rawLineage.refresh_facts ?? registry.refresh_facts,
    );
    const source = asString(rawLineage.source ?? row.source ?? registry.source);
    const sourceFields = stringArray(
      rawLineage.source_fields ?? row.source_fields ?? registry.source_fields,
    );
    const sourceGrain = asString(
      rawLineage.source_grain ?? row.source_grain ?? registry.source_grain,
    );
    const supportingSources = asArray(
      rawLineage.supporting_sources ?? registry.supporting_sources,
    ).flatMap((rawSource) => {
      const support = asRecord(rawSource);
      const supportSource = asString(support.source);
      const supportGrain = asString(support.source_grain);
      if (!supportSource || !supportGrain) return [];
      return [{
        source: supportSource,
        sourceFields: stringArray(support.source_fields),
        sourceGrain: supportGrain,
        joinRule: asString(support.join_rule) || null,
      }];
    });
    const lineageAvailable = Boolean(
      source &&
      sourceFields.length > 0 &&
      sourceGrain &&
      asString(transformation.module) &&
      asString(transformation.callable) &&
      asString(transformation.calculation_version) &&
      asString(refreshFacts.cadence) &&
      asString(refreshFacts.watermark_field) &&
      asString(refreshFacts.runtime_watermark_source) &&
      asString(refreshFacts.refresh_time_source) &&
      asString(refreshFacts.publication_gate),
    );
    const rawBoundary = asRecord(
      row.interpretation_boundary ?? registry.interpretation_boundary,
    );
    const rawGuardrailRule = asRecord(registry.guardrail_rule);
    const rawGuardrail = asRecord(row.guardrail);
    const runtimeEvidence = asRecord(row.runtime_evidence);
    const rawAdequacy = asRecord(row.sample_adequacy);
    const rawStatistical = asRecord(row.statistical_assessment);
    const rawMateriality = asRecord(row.practical_materiality);
    const rawReconciliation = asRecord(row.reconciliation);
    const adequacyStatus = asString(rawAdequacy.status).toUpperCase();
    const materialityStatus = asString(rawMateriality.status).toUpperCase();
    const reconciliationStatus = asString(rawReconciliation.status).toUpperCase();
    const guardrailRule = Object.keys(rawGuardrailRule).length > 0
      ? {
          ruleId: asString(rawGuardrailRule.rule_id) || null,
          ruleVersion: asString(rawGuardrailRule.rule_version) || null,
          directionality: normalizedDirectionality(rawGuardrailRule.directionality),
          denominatorRule: asString(rawGuardrailRule.denominator_rule) || null,
          thresholds: asArray(rawGuardrailRule.thresholds).flatMap((rawThreshold) => {
            const threshold = asRecord(rawThreshold);
            const thresholdStatus = asString(threshold.status);
            const operator = asString(threshold.operator);
            const unit = asString(threshold.unit);
            if (!thresholdStatus || !operator || !unit) return [];
            return [{
              status: thresholdStatus,
              operator,
              value: optionalNumber(threshold.value),
              unit,
            }];
          }),
          explanationTemplate: asString(rawGuardrailRule.explanation_template) || null,
        }
      : existing?.guardrailRule;
    return [{
      id,
      name: asString(row.name, id.replaceAll("_", " ")),
      shortName: asString(row.short_name, asString(row.name, id)),
      value: current,
      prior,
      absoluteChange,
      relativeChange,
      unit: normalizeMetricUnit(rawUnit),
      registryUnit: asString(rawUnit),
      scale: asString(row.scale ?? registry.scale, "1"),
      numerator: asString(row.numerator ?? registry.numerator, "N/A"),
      scalingFactor:
        (row.scaling_factor ?? registry.scaling_factor) === null ||
        (row.scaling_factor ?? registry.scaling_factor) === undefined
          ? undefined
          : asNumber(row.scaling_factor ?? registry.scaling_factor),
      formatString: asString(row.format_string ?? registry.format_string, ""),
      currencyCode: asString(row.currency_code, ""),
      currencySymbol: asString(row.currency_symbol, ""),
      denominator: formatKpiDenominator(id, row.denominator ?? registry.denominator),
      status: status(row.status, "Unavailable"),
      statisticalStatus: asString(row.statistical_status, "Unavailable"),
      refreshedAt: asString(
        row.refreshed_at ?? runtimeEvidence.refreshed_at,
        "N/A",
      ),
      definition: {
        businessDefinition: asString(
          definition.business_definition ??
            registry.business_definition ??
            (typeof row.definition === "string" ? row.definition : undefined),
          "N/A",
        ),
        formula: asString(
          definition.formula ?? row.formula ?? registry.formula,
          asString(row.definition, "N/A"),
        ),
        denominator: asString(
          definition.denominator ?? registry.denominator,
          formatKpiDenominator(id, row.denominator ?? registry.denominator),
        ),
        exclusions: asString(
          definition.exclusions ?? row.exclusions ?? registry.exclusions,
          "N/A",
        ),
        source: lineageAvailable ? source : "N/A",
        version: asString(
          definition.version ?? row.metric_version ?? row.version ?? registry.version,
          "N/A",
        ),
      },
      releaseCritical: true,
      reportingPeriod:
        asString(row.reporting_period ?? runtimeEvidence.reporting_period) || null,
      comparisonPeriod:
        asString(row.comparison_period ?? runtimeEvidence.comparison_period) || null,
      lineage: {
        status: lineageAvailable ? "AVAILABLE" : "UNAVAILABLE",
        source: lineageAvailable ? source : null,
        sourceFields: lineageAvailable ? sourceFields : [],
        sourceGrain: lineageAvailable ? sourceGrain : null,
        supportingSources: lineageAvailable ? supportingSources : [],
        transformation: {
          module: asString(transformation.module) || null,
          callable: asString(transformation.callable) || null,
          calculationVersion: asString(transformation.calculation_version) || null,
        },
        refreshFacts: {
          cadence: asString(refreshFacts.cadence) || null,
          watermarkField: asString(refreshFacts.watermark_field) || null,
          runtimeWatermarkSource:
            asString(refreshFacts.runtime_watermark_source) || null,
          refreshTimeSource: asString(refreshFacts.refresh_time_source) || null,
          publicationGate: asString(refreshFacts.publication_gate) || null,
        },
        defect: lineageAvailable
          ? null
          : `LINEAGE UNAVAILABLE: ${id} did not return complete governed source and transformation facts.`,
      },
      interpretationBoundary: Object.keys(rawBoundary).length > 0
        ? {
            canConclude: stringArray(rawBoundary.can_conclude),
            cannotConclude: stringArray(rawBoundary.cannot_conclude),
            directionality: normalizedDirectionality(rawBoundary.directionality),
            caveats: stringArray(rawBoundary.caveats),
            permittedNextAction: asString(rawBoundary.permitted_next_action) || null,
          }
        : existing?.interpretationBoundary,
      guardrailRule,
      guardrail: Object.keys(rawGuardrail).length > 0
        ? {
            ruleId: asString(rawGuardrail.rule_id) || null,
            ruleVersion: asString(rawGuardrail.rule_version) || null,
            status: asString(rawGuardrail.status, "UNAVAILABLE"),
            observedValue: optionalNumber(rawGuardrail.observed_value),
            observedChange: optionalNumber(rawGuardrail.observed_change),
            thresholdApplied:
              rawGuardrail.threshold_applied === null ||
              rawGuardrail.threshold_applied === undefined
                ? null
                : asRecord(rawGuardrail.threshold_applied),
            denominatorRule: asString(rawGuardrail.denominator_rule) || null,
            directionality: normalizedDirectionality(rawGuardrail.directionality),
            explanation: asString(rawGuardrail.explanation) || null,
          }
        : existing?.guardrail,
      runtimeEvidence: Object.keys(runtimeEvidence).length > 0
        ? {
            evidenceId: asString(runtimeEvidence.evidence_id) || null,
            datasetHash: asString(runtimeEvidence.dataset_hash) || null,
            configurationHash: asString(runtimeEvidence.configuration_hash) || null,
            runId: asString(runtimeEvidence.run_id) || null,
            bindingSha256: asString(runtimeEvidence.binding_sha256) || null,
            reportingPeriod: asString(runtimeEvidence.reporting_period) || null,
            comparisonPeriod: asString(runtimeEvidence.comparison_period) || null,
            refreshedAt: asString(runtimeEvidence.refreshed_at) || null,
          }
        : existing?.runtimeEvidence,
      sampleAdequacy: Object.keys(rawAdequacy).length > 0
        ? {
            status:
              adequacyStatus === "ADEQUATE" || adequacyStatus === "INADEQUATE"
                ? adequacyStatus
                : "UNAVAILABLE",
            observedDenominator: optionalNumber(rawAdequacy.observed_denominator),
            minimumRequired: optionalNumber(rawAdequacy.minimum_required),
            denominatorRule: asString(rawAdequacy.denominator_rule) || null,
          }
        : existing?.sampleAdequacy,
      statisticalAssessment: Object.keys(rawStatistical).length > 0
        ? {
            inferencePerformed:
              typeof rawStatistical.inference_performed === "boolean"
                ? rawStatistical.inference_performed
                : null,
            status: asString(rawStatistical.status, "UNAVAILABLE"),
            method: asString(rawStatistical.method) || null,
            explanation: asString(rawStatistical.explanation) || null,
          }
        : existing?.statisticalAssessment,
      practicalMateriality: Object.keys(rawMateriality).length > 0
        ? {
            status:
              materialityStatus === "MATERIAL" ||
              materialityStatus === "IMMATERIAL" ||
              materialityStatus === "NOT_ASSESSABLE"
                ? materialityStatus
                : "UNAVAILABLE",
            observedAbsoluteChange: optionalNumber(
              rawMateriality.observed_absolute_change,
            ),
            threshold: optionalNumber(rawMateriality.threshold),
            unit: asString(rawMateriality.unit) || null,
          }
        : existing?.practicalMateriality,
      reconciliation: Object.keys(rawReconciliation).length > 0
        ? {
            status:
              reconciliationStatus === "NOT_RUN" ||
              reconciliationStatus === "PASS" ||
              reconciliationStatus === "FAIL"
                ? reconciliationStatus
                : "UNAVAILABLE",
            scope: asString(rawReconciliation.scope) || null,
            checkedAt: asString(rawReconciliation.checked_at) || null,
            detail: asString(rawReconciliation.detail) || null,
          }
        : existing?.reconciliation,
    }];
  });
}

function mergeCommandCentre(
  data: WorkbenchData,
  payload: unknown,
  registryPayload?: unknown,
): WorkbenchData {
  const root = asRecord(payload);
  const metadata = asRecord(root.metadata);
  const rowCounts = asRecord(metadata.row_counts);
  const rawKpis = asArray(root.kpis);
  const normalizedKpis = normalizeKpis(rawKpis, registryPayload, data.kpis);
  const firstKpi = asRecord(rawKpis[0]);
  const trends = asArray(root.trends);
  const trendByMetric = new Map<string, Array<{ month: string; value: number }>>();
  trends.forEach((item) => {
    const row = asRecord(item);
    const id = displayMetricId(row.metric_id);
    if (
      !id ||
      !asString(row.month) ||
      row.value === null ||
      row.value === undefined ||
      !Number.isFinite(Number(row.value))
    ) return;
    const current = trendByMetric.get(id) ?? [];
    current.push({
      month: asString(row.month),
      value: scaleMetricValue(asNumber(row.value), row.unit),
    });
    trendByMetric.set(id, current);
  });
  const normalizedTrends = [...trendByMetric.entries()].map(
    ([id, points]) => {
      const metric = normalizedKpis.find((item) => item.id === id);
      return {
        id,
        label: metric?.name ?? id.replaceAll("_", " "),
        unit:
          metric?.unit === "percent"
            ? "%"
            : metric?.unit === "currency"
              ? "$m"
              : metric?.unit === "count"
                ? "count"
                : metric?.unit ?? "",
        points: points.map((point, index, all) => ({
          ...point,
          comparison: index > 0 ? all[index - 1].value : undefined,
        })),
      };
    },
  );

  const rawRiskDistribution = asArray(root.risk_distribution);
  const riskCountTotal = rawRiskDistribution.reduce<number>(
    (total, raw) => total + asNumber(asRecord(raw).count),
    0,
  );
  const riskDistribution = rawRiskDistribution.map((raw) => {
    const row = asRecord(raw);
    const count = asNumber(row.count);
    return {
      label: asString(row.risk_band ?? row.label),
      value: riskCountTotal === 0 ? 0 : (count / riskCountTotal) * 100,
      secondary: count,
      status: "Stable" as SignalStatus,
    };
  });

  const alerts = normalizeAlerts(root.alerts);
  const rawInterpretation = asRecord(root.interpretation);
  const validatedMovements = asArray(rawInterpretation.top_validated_movements)
    .map((item) => asRecord(item))
    .filter((item) => Object.keys(item).length > 0);
  const adverseInterpretation = asArray(rawInterpretation.adverse)
    .map((item) => asString(item))
    .filter(Boolean);
  if (adverseInterpretation.length === 0) {
    validatedMovements
      .filter((item) => asString(item.status).toLowerCase() === "adverse")
      .forEach((item) => {
        adverseInterpretation.push(
          `${asString(item.name ?? item.metric_id, "Returned metric")} moved adversely in the selected period.`,
        );
      });
  }
  const favourableRecord = asRecord(
    rawInterpretation.largest_favourable_movement,
  );
  return {
    ...data,
    metadata: {
      ...data.metadata,
      asOf: asString(
        firstKpi.reporting_period ?? metadata.as_of,
        "N/A",
      ),
      comparisonPeriod: asString(
        firstKpi.comparison_period ?? metadata.comparison_period,
        "N/A",
      ),
      qualityStatus: asString(
        metadata.quality_status,
        "UNAVAILABLE",
      ),
      synthetic:
        typeof metadata.synthetic === "boolean"
          ? metadata.synthetic
          : data.metadata.synthetic,
      refreshedAt: asString(metadata.refreshed_at, "N/A"),
      rowCount: asNumber(rowCounts.monthly_account_performance),
      runId: asString(metadata.run_id, data.metadata.sourceContext.runId ?? "N/A"),
      calculationVersion: `nAIM analytics v${asString(
        metadata.version ?? metadata.metric_registry_version,
        "N/A",
      )}`,
    },
    kpis: normalizedKpis,
    trends: normalizedTrends,
    riskDistribution,
    alerts,
    interpretation: {
      adverse: adverseInterpretation,
      favourable: asString(
        rawInterpretation.favourable,
        Object.keys(favourableRecord).length > 0
          ? `${asString(favourableRecord.name ?? favourableRecord.metric_id, "Returned metric")} was the largest favourable movement.`
          : "N/A",
      ),
      caveat: asString(
        rawInterpretation.caveat ??
          rawInterpretation.most_important_data_quality_caveat,
        "N/A",
      ),
      priority: asString(
        rawInterpretation.priority ??
          rawInterpretation.highest_priority_investigation,
        "N/A",
      ),
    },
  };
}

function normalizeAlerts(value: unknown): AlertRecord[] {
  const rows = asArray(value);
  if (rows.length === 0) return [];
  return rows.map((raw) => {
    const row = asRecord(raw);
    const metricId = displayMetricId(row.metric_id ?? row.metric);
    const rawSeverity = asString(row.severity).toLowerCase();
    const severity: SignalStatus =
      rawSeverity === "high"
        ? "Adverse"
        : rawSeverity === "medium"
          ? "Watch"
          : rawSeverity === "low"
            ? "Stable"
            : status(row.severity, "Watch");
    const formatValue = (value: unknown) => {
      const parsed = asNumber(value, Number.NaN);
      if (!Number.isFinite(parsed)) return "Not supplied";
      if (metricId.includes("RATE") || metricId === "DATA_COMPLETENESS") {
        return `${(parsed * 100).toFixed(2)}%`;
      }
      if (metricId.includes("BPS")) return `${parsed.toFixed(2)} bps`;
      return parsed.toLocaleString(undefined, { maximumFractionDigits: 2 });
    };
    const controls = asRecord(row.noise_controls);
    const ruleId = asString(row.alert_rule_id);
    const thresholdValue = asNumber(row.threshold, Number.NaN);
    const threshold =
      !Number.isFinite(thresholdValue)
        ? "Not supplied"
        : ruleId.includes("MOVEMENT")
          ? `${thresholdValue.toFixed(1)} bps movement`
          : ruleId.includes("PERSISTENT")
            ? `${thresholdValue.toFixed(1)}% relative increase across required periods`
            : formatValue(thresholdValue);
    const evidence = [
      asString(row.recommended_investigation),
      row.data_quality_status
        ? `Data quality: ${asString(row.data_quality_status)}`
        : "",
      controls.minimum_denominator !== undefined
        ? `Minimum denominator: ${numericString(controls.minimum_denominator)}`
        : "",
      controls.consecutive_periods !== undefined
        ? `Persistence rule: ${numericString(controls.consecutive_periods)} period(s)`
        : "",
    ].filter(Boolean);
    return {
      id: asString(row.alert_id ?? row.id, "Unidentified alert"),
      severity,
      title: asString(row.alert_name ?? row.title, "Governed evidence alert"),
      metric: metricId || "Metric not supplied",
      current: formatValue(row.current_value ?? row.current),
      baseline: formatValue(row.baseline_value ?? row.baseline),
      threshold,
      segment: asString(row.segment, "Portfolio"),
      owner: asString(row.owner ?? row.owner_role, "Unassigned"),
      state: asString(row.status ?? row.state, "New"),
      age: asString(
        row.age,
        row.generation_timestamp
          ? `Generated ${asString(row.generation_timestamp)}`
          : "Generation time not supplied",
      ),
      evidence,
      durable: false,
    };
  });
}

function strictString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function strictNullableString(value: unknown): string | null | undefined {
  if (value === null) return null;
  return strictString(value) ?? undefined;
}

function strictNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function strictNullableNumber(value: unknown): number | null | undefined {
  if (value === null) return null;
  return strictNumber(value) ?? undefined;
}

function strictInteger(value: unknown, minimum = 0): number | null {
  return typeof value === "number" &&
      Number.isInteger(value) &&
      value >= minimum
    ? value
    : null;
}

function normalizeAlertAuditEvent(value: unknown): AlertAuditEvent | null {
  const row = asRecord(value);
  const eventType = strictString(row.event_type);
  const actor = strictString(row.actor);
  const occurredAt = strictString(row.occurred_at);
  const previousHash = strictNullableString(row.previous_hash);
  const eventHash = strictString(row.event_hash);
  const payloadIsObject =
    row.payload !== null &&
    typeof row.payload === "object" &&
    !Array.isArray(row.payload);
  if (
    !eventType ||
    !ALERT_AUDIT_EVENT_TYPES.includes(
      eventType as (typeof ALERT_AUDIT_EVENT_TYPES)[number],
    ) ||
    !actor ||
    !occurredAt ||
    Number.isNaN(Date.parse(occurredAt)) ||
    previousHash === undefined ||
    !eventHash ||
    !payloadIsObject
  ) {
    return null;
  }
  return {
    eventType: eventType as AlertAuditEvent["eventType"],
    actor,
    occurredAt,
    payload: asRecord(row.payload),
    previousHash,
    eventHash,
  };
}

function normalizeAlertAuditIntegrity(
  value: unknown,
): AlertAuditIntegrity | null {
  const row = asRecord(value);
  const integrityStatus = strictString(row.status);
  const eventCount = strictInteger(row.event_count);
  const headHash = strictNullableString(row.head_hash);
  if (
    (integrityStatus !== "PASS" && integrityStatus !== "FAIL") ||
    typeof row.chain_valid !== "boolean" ||
    eventCount === null ||
    headHash === undefined
  ) {
    return null;
  }
  return {
    status: integrityStatus,
    chainValid: row.chain_valid,
    eventCount,
    headHash,
  };
}

function formatDurableAlertValue(metricId: string, value: unknown): string {
  const parsed = strictNumber(value);
  if (parsed === null) return "Not supplied";
  if (metricId.includes("RATE") || metricId === "DATA_COMPLETENESS") {
    return `${(parsed * 100).toFixed(2)}%`;
  }
  if (metricId.includes("BPS")) return `${parsed.toFixed(2)} bps`;
  return parsed.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

export function normalizeDurableAlertPayload(
  value: unknown,
): AlertRecord | null {
  const row = asRecord(value);
  const alertId = strictString(row.alert_id);
  const fingerprint = strictString(row.alert_fingerprint);
  const ruleId = strictString(row.alert_rule_id);
  const ruleName = strictString(row.alert_rule_name);
  const ruleVersion = strictString(row.rule_version);
  const metricId = strictString(row.metric_id);
  const owner = strictString(row.owner);
  const lifecycleStatus = strictString(row.status);
  const severity = row.severity;
  const normalizedSeverity: SignalStatus | null =
    severity === "Critical" || severity === "Adverse" || severity === "Watch"
      ? severity
      : null;
  const version = strictInteger(row.version, 1);
  const firstObservedAt = strictString(row.first_observed_at);
  const firstObservedPeriod = strictString(row.first_observed_period);
  const lastObservedAt = strictString(row.last_observed_at);
  const lastObservedPeriod = strictString(row.last_observed_period);
  const lastObservationKey = strictString(row.last_observation_key);
  const recurrenceCount = strictInteger(row.recurrence_count);
  const relatedInvestigation = strictNullableString(row.related_investigation);
  if (
    !alertId ||
    !fingerprint ||
    !ruleId ||
    !ruleName ||
    !ruleVersion ||
    !metricId ||
    !owner ||
    !isAlertLifecycleStatus(lifecycleStatus) ||
    !normalizedSeverity ||
    version === null ||
    !firstObservedAt ||
    !firstObservedPeriod ||
    !lastObservedAt ||
    !lastObservedPeriod ||
    !lastObservationKey ||
    recurrenceCount === null ||
    relatedInvestigation === undefined ||
    typeof row.can_acknowledge !== "boolean" ||
    typeof row.condition_active !== "boolean" ||
    typeof row.workflow_active !== "boolean" ||
    !Array.isArray(row.allowed_transitions)
  ) {
    return null;
  }
  const allowedTransitions = row.allowed_transitions.filter(
    isAlertLifecycleTransition,
  );
  if (allowedTransitions.length !== row.allowed_transitions.length) return null;

  const acknowledgement = asRecord(row.acknowledgement);
  const acknowledgedBy = strictNullableString(acknowledgement.by);
  const acknowledgedAt = strictNullableString(acknowledgement.at);
  const acknowledgementNote = strictNullableString(acknowledgement.note);
  if (
    typeof acknowledgement.acknowledged !== "boolean" ||
    acknowledgedBy === undefined ||
    acknowledgedAt === undefined ||
    acknowledgementNote === undefined
  ) {
    return null;
  }

  const sla = asRecord(row.sla);
  const slaHours = strictNumber(sla.hours);
  const slaDueAt = strictString(sla.due_at);
  if (slaHours === null || slaHours < 0 || !slaDueAt) return null;

  const cooldown = asRecord(row.cooldown);
  const cooldownPeriods = strictInteger(cooldown.periods);
  const cooldownUntilPeriod = strictNullableString(cooldown.until_period);
  if (cooldownPeriods === null || cooldownUntilPeriod === undefined) return null;

  const suppression = asRecord(row.suppression);
  const suppressionReason = strictNullableString(suppression.reason);
  const suppressionBy = strictNullableString(suppression.by);
  const suppressionAt = strictNullableString(suppression.at);
  const suppressionUntilPeriod = strictNullableString(
    suppression.until_period,
  );
  if (
    typeof suppression.active !== "boolean" ||
    suppressionReason === undefined ||
    suppressionBy === undefined ||
    suppressionAt === undefined ||
    suppressionUntilPeriod === undefined
  ) {
    return null;
  }

  const resolution = asRecord(row.resolution);
  const resolutionReason = strictNullableString(resolution.reason);
  const resolutionBy = strictNullableString(resolution.by);
  const resolutionAt = strictNullableString(resolution.at);
  if (
    resolutionReason === undefined ||
    resolutionBy === undefined ||
    resolutionAt === undefined
  ) {
    return null;
  }

  if (!Array.isArray(row.reopen_history)) return null;
  const reopenHistory = row.reopen_history.map((value) => {
    const item = asRecord(value);
    const reopenedAt = strictString(item.reopened_at);
    const runId = strictString(item.run_id);
    const period = strictString(item.period);
    const priorStatus = strictString(item.prior_status);
    const untilPeriod = strictNullableString(item.cooldown_until_period);
    const reason = strictString(item.reason);
    const observationKey = strictString(item.observation_key);
    if (
      !reopenedAt ||
      !runId ||
      !period ||
      (priorStatus !== "RESOLVED" &&
        priorStatus !== "SUPPRESSED" &&
        priorStatus !== "CLOSED_AS_NOISE") ||
      untilPeriod === undefined ||
      !reason ||
      !observationKey
    ) {
      return null;
    }
    return {
      reopenedAt,
      runId,
      period,
      priorStatus,
      cooldownUntilPeriod: untilPeriod,
      reason,
      observationKey,
    };
  });
  if (reopenHistory.some((item) => item === null)) return null;

  const latestEvidence = asRecord(row.latest_evidence);
  const evidenceRunId = strictString(latestEvidence.run_id);
  const configurationHash = strictString(latestEvidence.configuration_hash);
  const datasetHash = strictNullableString(latestEvidence.dataset_hash);
  const evidencePeriod = strictString(latestEvidence.period);
  const comparisonPeriod = strictNullableString(latestEvidence.comparison_period);
  const dataQualityStatus = strictString(latestEvidence.data_quality_status);
  const currentValue = strictNullableNumber(latestEvidence.current_value);
  const baselineValue = strictNullableNumber(latestEvidence.baseline_value);
  const absoluteMovement = strictNullableNumber(latestEvidence.absolute_movement);
  const relativeMovement = strictNullableNumber(latestEvidence.relative_movement);
  const denominator = strictNumber(latestEvidence.denominator);
  const observationKey = strictString(latestEvidence.observation_key);
  if (
    !evidenceRunId ||
    !configurationHash ||
    datasetHash === undefined ||
    !evidencePeriod ||
    comparisonPeriod === undefined ||
    !dataQualityStatus ||
    currentValue === undefined ||
    baselineValue === undefined ||
    absoluteMovement === undefined ||
    relativeMovement === undefined ||
    denominator === null ||
    !observationKey
  ) {
    return null;
  }

  if (!Array.isArray(row.audit_events)) return null;
  const auditEvents = row.audit_events.map(normalizeAlertAuditEvent);
  const auditIntegrity = normalizeAlertAuditIntegrity(row.audit_integrity);
  if (
    auditEvents.some((event) => event === null) ||
    !auditIntegrity ||
    auditIntegrity.eventCount !== auditEvents.length
  ) {
    return null;
  }

  const controls = asRecord(row.noise_controls);
  const thresholdValue = strictNumber(row.threshold);
  const threshold = thresholdValue === null
    ? "Not supplied"
    : ruleId.includes("MOVEMENT")
      ? `${thresholdValue.toFixed(1)} bps movement`
      : ruleId.includes("PERSISTENT")
        ? `${thresholdValue.toFixed(1)}% relative increase across required periods`
        : formatDurableAlertValue(metricId, thresholdValue);
  const recommended = Array.isArray(row.recommended_investigation)
    ? row.recommended_investigation.map(strictString).filter(Boolean)
    : [strictString(row.recommended_investigation)].filter(Boolean);
  const evidence = [
    ...recommended,
    `Data quality: ${dataQualityStatus}`,
    `Evidence run: ${evidenceRunId}`,
    `Observation: ${observationKey}`,
    controls.minimum_denominator !== undefined
      ? `Minimum denominator: ${numericString(controls.minimum_denominator)}`
      : "",
  ].filter(Boolean) as string[];
  const statusLabel = lifecycleStatus
    .toLowerCase()
    .replaceAll("_", " ")
    .replace(/^./, (letter) => letter.toUpperCase());
  return {
    id: alertId,
    severity: normalizedSeverity,
    title: strictString(row.alert_name) ?? ruleName,
    metric: displayMetricId(metricId),
    current: formatDurableAlertValue(metricId, currentValue),
    baseline: formatDurableAlertValue(metricId, baselineValue),
    threshold,
    segment: strictString(row.segment) ?? "Portfolio",
    owner,
    state: statusLabel,
    age: `Last observed ${lastObservedAt}`,
    evidence,
    durable: true,
    lifecycle: {
      fingerprint,
      ruleId,
      ruleName,
      ruleVersion,
      status: lifecycleStatus as AlertLifecycleStatus,
      acknowledgement: {
        acknowledged: acknowledgement.acknowledged,
        by: acknowledgedBy,
        at: acknowledgedAt,
        note: acknowledgementNote,
      },
      sla: { hours: slaHours, dueAt: slaDueAt },
      recurrenceCount,
      firstObservedAt,
      firstObservedPeriod,
      lastObservedAt,
      lastObservedPeriod,
      lastObservationKey,
      cooldown: {
        periods: cooldownPeriods,
        untilPeriod: cooldownUntilPeriod,
      },
      suppression: {
        active: suppression.active,
        reason: suppressionReason,
        by: suppressionBy,
        at: suppressionAt,
        untilPeriod: suppressionUntilPeriod,
      },
      resolution: {
        reason: resolutionReason,
        by: resolutionBy,
        at: resolutionAt,
      },
      reopenHistory: reopenHistory as NonNullable<
        AlertRecord["lifecycle"]
      >["reopenHistory"],
      latestEvidence: {
        runId: evidenceRunId,
        configurationHash,
        datasetHash,
        period: evidencePeriod,
        comparisonPeriod,
        dataQualityStatus,
        currentValue,
        baselineValue,
        absoluteMovement,
        relativeMovement,
        denominator,
        observationKey,
      },
      relatedInvestigation,
      version,
      auditIntegrity,
      auditEvents: auditEvents as AlertAuditEvent[],
      allowedTransitions,
      canAcknowledge: row.can_acknowledge,
      conditionActive: row.condition_active,
      workflowActive: row.workflow_active,
    },
  };
}

function normalizeDurableAlertListPayload(
  value: unknown,
): AlertRecord[] | null {
  const root = asRecord(value);
  if (!Array.isArray(root.data)) return null;
  const rows = root.data.map(normalizeDurableAlertPayload);
  return rows.some((row) => row === null) ? null : (rows as AlertRecord[]);
}

function mergeRootCause(
  data: WorkbenchData,
  payload: unknown,
): WorkbenchData {
  const root = asRecord(payload);
  const finding = asRecord(root.finding);
  const lenses: RootCauseLens[] = asArray(root.lenses).map((rawLens) => {
    const lens = asRecord(rawLens);
    const lensDimension = asString(lens.dimension);
    const rawSegments = asArray(
      lens.items ?? lens.contributions ?? lens.segments,
    );
    rawSegments.forEach((rawItem) => {
      const itemDimension = asString(asRecord(rawItem).dimension);
      if (
        itemDimension &&
        !contributionDimensionMatches(lensDimension, itemDimension)
      ) {
        throw new Error(
          `Root-cause lens ${lensDimension || "without dimension"} returned a ${itemDimension} member.`,
        );
      }
    });
    const rateScale = 1;
    return {
      dimension: lensDimension,
      total:
        asNumber(lens.total ?? lens.observed_change) * rateScale,
      items: rawSegments.map((rawItem) => {
        const item = asRecord(rawItem);
        const contribution =
          asNumber(
            item.contribution ??
              item.contribution_bps ??
              item.total_contribution,
          ) * rateScale;
        return {
          label: asString(item.label ?? item.segment),
          contribution,
          mix:
            asNumber(item.mix ?? item.mix_contribution_bps ?? item.mix_contribution) *
            rateScale,
          performance:
            asNumber(
              item.performance ??
                item.performance_contribution_bps ??
                item.within_segment_contribution,
            ) * rateScale,
          population: asNumber(
            item.population ??
              item.denominator ??
              item.current_denominator,
          ),
          persistence: asNumber(item.persistence),
          status: status(
            item.status,
            contribution > 0
              ? "Adverse"
              : contribution < 0
                ? "Favourable"
                : "Stable",
          ),
        };
      }),
    };
  });
  const recommendedInvestigation = asArray(
    finding.recommended_investigation,
  )
    .map((item) => asString(item))
    .filter(Boolean);
  const supportingDrivers = asArray(finding.supporting_drivers)
    .map((item) => asString(item))
    .filter(Boolean);
  const normalizedFinding = {
    metricId: asString(finding.metric_id, "N/A"),
    comparisonPeriod: asString(finding.comparison_period, "N/A"),
    observedChangeBps: asNumber(finding.observed_change_bps),
    dataQualityStatus: asString(
      finding.data_quality_status,
      "UNAVAILABLE",
    ),
    primaryDimension: asString(
      finding.primary_dimension,
      "N/A",
    ),
    primaryDriver: asString(
      finding.primary_driver,
      "N/A",
    ),
    contributionShare: asNumber(finding.contribution_share),
    mixContributionBps: asNumber(finding.mix_contribution_bps),
    withinSegmentContributionBps: asNumber(
      finding.within_segment_contribution_bps,
    ),
    supportingDrivers,
    causalStatus: asString(finding.causal_status, "UNAVAILABLE"),
    recommendedInvestigation,
  };
  const primaryLens =
    lenses.find(
      (item) => item.dimension === normalizedFinding.primaryDimension,
    ) ?? lenses[0];
  const contributors = primaryLens?.items ?? [];
  const hierarchy = [...contributors]
    .sort(
      (left, right) =>
        Math.abs(right.contribution) - Math.abs(left.contribution),
    )
    .slice(0, 5)
    .map((item, index) => ({
      level: `${primaryLens?.dimension ?? "driver"} rank ${index + 1}`,
      value: item.label,
      contribution: item.contribution,
      share:
        normalizedFinding.observedChangeBps === 0
          ? 0
          : item.contribution / normalizedFinding.observedChangeBps,
      population: item.population,
    }));
  const favourableMetric = data.kpis.find(
    (metric) => metric.status === "Favourable",
  );
  const movement = normalizedFinding.observedChangeBps;
  return {
    ...data,
    contributors,
    interpretation: {
      adverse:
        movement > 0
          ? [
              `Annualised net loss rate increased ${movement.toFixed(1)} bps.`,
              `${normalizedFinding.primaryDriver} is the largest driver in the ${normalizedFinding.primaryDimension.replaceAll("_", " ")} lens.`,
            ]
          : [
              `Annualised net loss rate moved ${Math.abs(movement).toFixed(1)} bps favourably.`,
            ],
      favourable: favourableMetric
        ? `${favourableMetric.name} is classified ${favourableMetric.status.toLowerCase()} in the selected period.`
        : "No separately favourable governed KPI was returned.",
      caveat: `${normalizedFinding.causalStatus}: decomposition explains the observed rate movement but does not establish causality.`,
      priority:
        recommendedInvestigation[0] ??
        "Continue governed monitoring for the selected scope.",
    },
    rootCause: {
      ...data.rootCause,
      finding: normalizedFinding,
      lenses,
      hierarchy,
      behaviouralDrivers: [],
    },
  };
}

function mergeVintages(data: WorkbenchData, payload: unknown): WorkbenchData {
  const root = asRecord(payload);
  const rows = asArray(root.data ?? payload);
  const vintages: VintageCell[] = rows.map((raw) => {
    const row = asRecord(raw);
    const delinquency = asNumber(
      row.delinquency_30_rate ?? row.delinquency30,
    ) * 100;
    return {
      vintage: asString(row.vintage),
      mob: asNumber(row.months_on_book ?? row.mob),
      cohortSize: asNumber(row.cohort_size),
      delinquency30: delinquency,
      cumulativeLoss:
        asNumber(row.cumulative_net_loss_rate ?? row.cumulativeLoss) * 100,
      confidenceLow:
        asNumber(
          row.delinquency_30_ci_lower ?? row.confidence_low,
          delinquency / 100 * 0.9,
        ) * 100,
      confidenceHigh:
        asNumber(
          row.delinquency_30_ci_upper ?? row.confidence_high,
          delinquency / 100 * 1.1,
        ) * 100,
      maturityWarning: Boolean(row.maturity_warning),
      channel: asString(row.channel, "Portfolio scope"),
    };
  });
  return {
    ...data,
    vintages,
  };
}

function mergeStrategies(data: WorkbenchData, payload: unknown): WorkbenchData {
  const root = asRecord(payload);
  const validity = asRecord(root.validity);
  const recommendation = asRecord(root.recommendation);
  const strategies: StrategyResult[] = asArray(root.strategies).map((raw) => {
    const row = asRecord(raw);
    return {
      strategy: asString(row.strategy),
      status: asString(
        row.status,
        asString(row.strategy) === "Champion A" ? "Champion" : "Comparison",
      ),
      eligibleAccounts: asNumber(row.eligible_accounts),
      assignmentShare: asNumber(row.assignment_share) * 100,
      lossRate: asNumber(row.loss_rate) * 100,
      fraudBps: asNumber(row.fraud_bps),
      reviewRate:
        asNumber(row.review_rate ?? row.manual_review_rate) * 100,
      falsePositiveRate: asNumber(row.false_positive_rate) * 100,
      frictionRate: asNumber(
        row.friction_rate ?? row.customer_friction_rate,
      ) * 100,
      complaintsPerThousand: asNumber(
        row.complaint_rate ?? row.complaint_rate_per_1000,
      ),
      expectedProfit: asNumber(row.expected_profit) / 1_000_000,
    };
  });
  const validityRows: WorkbenchData["strategyValidity"] = [];
  const randomisedObservations = asNumber(validity.randomised_observations);
  if (randomisedObservations > 0) {
    validityRows.push({
      test: "Randomised observations",
      result: randomisedObservations.toLocaleString(),
      status: "Favourable",
      detail: asString(
        validity.assignment_type,
        "Randomised and rule-based populations are labelled separately.",
      ),
    });
  }
  if (validity.sample_ratio_mismatch_p_value !== undefined) {
    const mismatch = Boolean(validity.sample_ratio_mismatch_flag);
    validityRows.push({
      test: "Sample-ratio mismatch",
      result: `p = ${asNumber(validity.sample_ratio_mismatch_p_value).toPrecision(3)}`,
      status: mismatch ? "Critical" : "Favourable",
      detail: mismatch
        ? "Observed assignment shares differ materially from the configured allocation."
        : "Observed assignment shares are consistent with the configured allocation.",
    });
  }
  asArray(validity.outcomes).forEach((rawOutcome) => {
    const outcome = asRecord(rawOutcome);
    validityRows.push({
      test: asString(outcome.metric).replaceAll("_", " "),
      result: `adjusted p = ${asNumber(outcome.adjusted_p_value).toPrecision(3)}`,
      status: Boolean(outcome.statistically_significant)
        ? "Watch"
        : "Stable",
      detail: `Observed effect ${asNumber(outcome.effect).toFixed(4)}; multiple-comparison adjustment applied.`,
    });
  });
  return {
    ...data,
    strategies,
    strategyValidity: validityRows,
    strategyRecommendation: {
      decision: asString(recommendation.decision, "Review"),
      rulePath: asArray(recommendation.rule_path)
        .map((item) => asString(item))
        .filter(Boolean),
      approvalRequired:
        typeof recommendation.approval_required === "boolean"
          ? recommendation.approval_required
          : true,
      notice: asString(
        recommendation.notice,
        "Analytical output requires human review.",
      ),
    },
  };
}

function mergeEntities(
  data: WorkbenchData,
  key: "partners" | "vendors" | "memberships",
  payload: unknown,
): WorkbenchData {
  const root = asRecord(payload);
  const sourceRows = asArray(root.data ?? payload);
  const scaleField =
    key === "partners"
      ? "transaction_value"
      : key === "vendors"
        ? "process_volume"
        : "active_members";
  const scaleTotal = sourceRows.reduce<number>(
    (sum, raw) => sum + asNumber(asRecord(raw)[scaleField]),
    0,
  );
  const rows: EntityScore[] = sourceRows.map((raw, index) => {
    const row = asRecord(raw);
    const rating = asRecord(row.rating);
    const serviceMetric =
      row.sla_rate !== undefined
        ? asNumber(row.sla_rate) * 100
        : key === "vendors"
          ? asNumber(
              row.first_time_right_rate,
              asNumber(row.quality_score) / 100,
            ) * 100
          : key === "memberships"
            ? asNumber(row.benefit_utilisation) * 100
            : asNumber(row.service_metric);
    const rawProfit =
      row.partner_contribution ??
      row.expected_contribution ??
      row.expected_profit ??
      (row.total_vendor_cost === undefined
        ? undefined
        : -asNumber(row.total_vendor_cost));
    const scale =
      key === "partners"
        ? asNumber(row.transaction_value) / 1_000_000
        : key === "vendors"
          ? asNumber(row.process_volume) / 1_000
          : asNumber(row.active_members);
    const explicitConcentration =
      row.concentration ?? row.concentration_exposure;
    const concentrationRaw =
      explicitConcentration === undefined
        ? scaleTotal === 0
          ? 0
          : asNumber(row[scaleField]) / scaleTotal
        : asNumber(explicitConcentration);
    const riskMetric =
      row.risk_metric !== undefined || row.risk_score !== undefined
        ? asNumber(row.risk_metric ?? row.risk_score)
        : key === "partners"
          ? (asNumber(row.confirmed_fraud_loss) /
              Math.max(asNumber(row.transaction_value), 1)) *
            10_000
          : key === "memberships"
            ? (asNumber(row.fraud_loss) /
                Math.max(asNumber(row.transaction_value), 1)) *
              10_000
            : asNumber(row.fraud_bps);
    return {
      id: asString(
        row.id ?? row.partner_id ?? row.vendor_id ?? row.membership_tier_id,
        `${key}-${index + 1}`,
      ),
      name: asString(
        row.name ??
          row.partner_name ??
          row.vendor_name ??
          row.membership_tier_name,
        "Unnamed entity",
      ),
      category: asString(
        row.category ??
          row.partner_type ??
          row.vendor_category ??
          row.service_type ??
          row.membership_tier_name,
        "Not supplied",
      ),
      region: asString(row.region ?? row.primary_region, "Portfolio"),
      scale,
      growth:
        row.growth_rate === undefined
          ? asNumber(row.growth, 0)
          : asNumber(row.growth_rate) * 100,
      profit:
        rawProfit === undefined
          ? 0
          : asNumber(rawProfit) / 1_000_000,
      riskMetric,
      serviceMetric,
      concentration: asNumber(
        concentrationRaw <= 1 ? concentrationRaw * 100 : concentrationRaw,
        0,
      ),
      score: asNumber(
        row.score ?? row.rating_score ?? rating.rating_score ?? rating.score,
        0,
      ),
      grade: asString(row.grade ?? rating.grade, "Not rated"),
      trend: status(row.trend, "Stable"),
      status: asString(
        row.status ?? row.partner_status ?? row.vendor_status,
        "Current API snapshot",
      ),
    };
  });
  return { ...data, [key]: rows };
}

function mergeBaskets(data: WorkbenchData, payload: unknown): WorkbenchData {
  const root = asRecord(payload);
  const rows: BasketRecord[] = asArray(root.data ?? payload).map((raw) => {
    const row = asRecord(raw);
    return {
      id: asString(row.basket_id ?? row.id, "Unidentified basket"),
      name: asString(row.name ?? row.basket_name, "Unnamed basket"),
      type: asString(row.type ?? row.basket_type, "account"),
      memberCount: asNumber(row.member_count),
      version: numericString(row.version, "1"),
      status: asString(row.status, "Draft"),
      approved:
        typeof row.approved === "boolean"
          ? row.approved
          : typeof row.approved_flag === "boolean"
            ? row.approved_flag
            : false,
      owner: asString(row.owner, "Unassigned"),
      updated: asString(row.valid_from, "Current version"),
      definition: asString(
        row.basket_expression ?? row.basket_description,
        "Definition not supplied",
      ),
      weightBasis: asString(row.entity_type, "entity"),
      metrics: {
        balance: null,
        transactionValue: null,
        lossRate: null,
        expectedProfit: null,
      },
    };
  });
  return { ...data, baskets: rows };
}

function mergeFinance(data: WorkbenchData, payload: unknown): WorkbenchData {
  const root = asRecord(payload);
  const bridge = asArray(root.bridge).map((raw) => {
    const row = asRecord(raw);
    const value = asNumber(row.value) / 1_000_000;
    const rawGroup = asString(row.group).toLowerCase();
    return {
      label: asString(row.component ?? row.label),
      value,
      group:
        rawGroup === "opening"
          ? ("opening" as const)
          : rawGroup === "closing"
            ? ("closing" as const)
            : rawGroup === "favourable" || value >= 0
              ? ("favourable" as const)
              : ("adverse" as const),
    };
  });
  const unitEconomicsRecord = asRecord(root.unit_economics);
  const unitEconomics = Object.entries(unitEconomicsRecord).map(
    ([label, value]) => ({
      label: label.replaceAll("_", " "),
      value: asNumber(value),
      status: "Stable" as SignalStatus,
    }),
  );
  const concentrationRecord = asRecord(root.concentration);
  const concentration = Object.entries(concentrationRecord).map(
    ([label, value]) => ({
      label: label.replaceAll("_", " "),
      value: label.includes("hhi")
        ? asNumber(value) * 10_000
        : asNumber(value) * 100,
      status: "Stable" as SignalStatus,
    }),
  );
  const driverTree = bridge
    .filter((item) => item.group !== "opening" && item.group !== "closing")
    .map((item) => ({
      parent: "Expected profit",
      child: item.label,
      value: item.value,
    }));
  return {
    ...data,
    finance: {
      ...data.finance,
      bridge,
      unitEconomics,
      concentration,
      driverTree,
    },
  };
}

function mergeDataQuality(
  data: WorkbenchData,
  payload: unknown,
): WorkbenchData {
  const root = asRecord(payload);
  const checks: DataQualityCheck[] = asArray(root.checks).map((raw) => {
    const row = asRecord(raw);
    const rawSeverity = asString(row.severity, "Warning");
    const rawStatus = asString(row.status, "Warning");
    return {
      id: asString(row.check_id),
      name: asString(row.name ?? row.check_id),
      severity: (
        ["Critical", "High", "Medium", "Warning"].includes(rawSeverity)
          ? rawSeverity
          : "Warning"
      ) as DataQualityCheck["severity"],
      status: (
        ["Pass", "Warning", "Fail"].includes(rawStatus)
          ? rawStatus
          : rawStatus.toLowerCase().includes("pass")
            ? "Pass"
            : "Warning"
      ) as DataQualityCheck["status"],
      affectedRows: asNumber(row.affected_rows),
      businessImpact: asString(row.business_impact),
      quarantine: asString(row.quarantine_location, "No rows quarantined"),
      recommendation: asString(row.recommendation),
    };
  });
  const manifestRecord = asRecord(root.manifest);
  const manifest = Object.entries(manifestRecord)
    .filter(([, value]) => value === null || typeof value !== "object")
    .map(([label, value]) => ({
      label: label.replaceAll("_", " "),
      value: String(value),
    }));
  return {
    ...data,
    dataQuality: {
      ...data.dataQuality,
      score: asNumber(root.score, data.dataQuality.score),
      status: asString(root.status, data.dataQuality.status),
      checks,
      manifest,
    },
  };
}

function mergeScenarios(data: WorkbenchData, payload: unknown): WorkbenchData {
  const root = asRecord(payload);
  const rows = asArray(root.data ?? payload);
  if (rows.length === 0) return { ...data, scenarios: [] };
  const scenarios: ScenarioRecord[] = rows.map((raw) => {
    const row = asRecord(raw);
    const assumptions = asRecord(row.assumptions);
    const projections = asArray(row.projections).map((rawProjection) => {
      const projection = asRecord(rawProjection);
      return {
        month: asString(projection.month),
        delinquency30: asNumber(projection.delinquency_30_rate) * 100,
        annualisedLossRate:
          asNumber(projection.annualised_net_loss_rate) * 100,
        fraudLoss:
          asNumber(projection.confirmed_fraud_loss) / 1_000_000,
        reviews: asNumber(projection.manual_reviews),
        expectedProfit: asNumber(projection.expected_profit) / 1_000_000,
        lower:
          asNumber(projection.net_credit_loss_interval_lower) / 1_000_000,
        upper:
          asNumber(projection.net_credit_loss_interval_upper) / 1_000_000,
      };
    });
    return {
      id: asString(row.id ?? row.scenario_id, "N/A"),
      name: asString(row.name ?? row.scenario_name, "N/A"),
      description: asString(row.description, "N/A"),
      assumptions: {
        consumerStress:
          asNumber(assumptions.consumer_stress_index) * 100,
        unemployment:
          asNumber(assumptions.unemployment_rate) * 100,
        interestRate: asNumber(assumptions.interest_rate) * 100,
        fraudPressure:
          asNumber(assumptions.fraud_pressure_index) * 100,
      },
      projections,
      cumulativeLoss:
        asNumber(row.cumulative_loss) / 1_000_000,
      cumulativeFraud:
        asNumber(row.cumulative_fraud) / 1_000_000,
      expectedProfit:
        asNumber(row.expected_profit) / 1_000_000,
      deltaFromBaseline: asNumber(
        row.delta_from_baseline,
      ) / 1_000_000,
    };
  });
  return { ...data, scenarios };
}

function mergeInvestigations(
  data: WorkbenchData,
  payload: unknown,
): WorkbenchData {
  const root = asRecord(payload);
  const rows: InvestigationRecord[] = asArray(root.data ?? payload).map(
    (raw) => {
      const row = asRecord(raw);
      return {
        id: asString(row.investigation_id ?? row.id, "Unidentified"),
        alertId: asString(row.alert_id, "No linked alert"),
        title: asString(
          row.business_question ?? row.title ?? row.hypothesis,
          "Untitled investigation",
        ),
        status: asString(row.status, "New"),
        severity: status(row.severity, "Watch"),
        owner: asString(row.owner, "Unassigned"),
        opened: asString(row.opened_timestamp, "Not supplied"),
        sla: asString(row.sla, "SLA not assigned"),
        hypothesis: asString(row.hypothesis, "No hypothesis recorded"),
        evidenceCount: asArray(row.supporting_evidence).length,
        nextAction: asString(
          row.action_taken,
          "Record the next analytical action",
        ),
      };
    },
  );
  return {
    ...data,
    investigations: rows,
  };
}

function mergeFilters(data: WorkbenchData, payload: unknown): WorkbenchData {
  const root = asRecord(payload);
  const values = asRecord(root.data);
  const strings = (key: string) =>
    asArray(values[key]).map((item) => asString(item)).filter(Boolean);
  const months = strings("month")
    .map((value) => {
      const parsed = new Date(`${value.slice(0, 10)}T00:00:00Z`);
      return Number.isNaN(parsed.getTime())
        ? value
        : parsed.toLocaleDateString("en-US", {
            month: "short",
            year: "numeric",
            timeZone: "UTC",
          });
    })
    .reverse();
  return {
    ...data,
    filterOptions: {
      reportingMonths: months,
      comparisons: ["Prior month"],
      products: ["All products", ...strings("product_type")],
      segments: ["All segments", ...strings("customer_segment")],
      channels: ["All channels", ...strings("acquisition_channel")],
      geographies: ["All geographies", ...strings("geography")],
      riskBands: ["All risk bands", ...strings("original_risk_band")],
      strategies: ["All strategies", ...strings("strategy_version")],
      vintages: ["All vintages"],
      modelVersions: ["All models", ...strings("model_version")],
    },
  };
}

function mergeRollRates(data: WorkbenchData, payload: unknown): WorkbenchData {
  const root = asRecord(payload);
  const rows = asArray(root.matrix)
    .map((raw) => asRecord(raw))
    .filter(
      (row) =>
        Boolean(asString(row.from_status)) &&
        Boolean(asString(row.to_status)) &&
        Number.isFinite(Number(row.rate)),
    );
  const labels = [...new Set(rows.flatMap((row) => [
    asString(row.from_status),
    asString(row.to_status),
  ]))];
  const values = labels.map((fromStatus) =>
    labels.map((toStatus) => {
      const row = rows.find(
        (candidate) =>
          asString(candidate.from_status) === fromStatus &&
          asString(candidate.to_status) === toStatus,
      );
      return row ? asNumber(row.rate) * 100 : 0;
    }),
  );
  return { ...data, rollRates: { labels, values } };
}

function stringArray(value: unknown): string[] {
  return asArray(value).map((item) => asString(item)).filter(Boolean);
}

function mergeCapabilities(
  data: WorkbenchData,
  payload: unknown,
): WorkbenchData {
  const root = asRecord(payload);
  const capabilities: CapabilityRecord[] = asArray(root.data).flatMap((raw) => {
    const row = asRecord(raw);
    const recordStatus = capabilityStatus(row.status);
    const featureId = asString(row.feature_id);
    if (!recordStatus || !featureId) return [];
    return [{
      featureId,
      name: asString(row.name, featureId.replaceAll("_", " ")),
      status: recordStatus,
      backendEndpoints: stringArray(row.backend_endpoint),
      frontendRoutes: stringArray(row.frontend_route),
      calculationModules: stringArray(row.calculation_module),
      testEvidence: stringArray(row.test_evidence),
      artifactEvidence: stringArray(row.artifact_evidence),
      limitation: asString(row.limitation, "No limitation was supplied."),
      lastValidationDate: asString(row.last_validation_date, "N/A"),
      owner: asString(row.owner, "N/A"),
      version: asString(row.version, "N/A"),
    }];
  });
  const statusDefinitions: WorkbenchData["capabilityRegistry"]["statusDefinitions"] = {};
  Object.entries(asRecord(root.status_definitions)).forEach(([key, value]) => {
    const keyStatus = capabilityStatus(key);
    if (keyStatus) statusDefinitions[keyStatus] = asString(value);
  });
  const statusCounts: WorkbenchData["capabilityRegistry"]["statusCounts"] = {};
  Object.entries(asRecord(root.status_counts)).forEach(([key, value]) => {
    const keyStatus = capabilityStatus(key);
    if (keyStatus) statusCounts[keyStatus] = asNumber(value);
  });
  return {
    ...data,
    capabilities,
    capabilityRegistry: {
      registryVersion: asString(root.registry_version, "N/A"),
      schemaVersion: asString(root.schema_version, "N/A"),
      product: asString(root.product, "nAIM Portfolio Intelligence Workbench"),
      allowedStatuses: stringArray(root.allowed_statuses)
        .map((item) => capabilityStatus(item))
        .filter((item): item is CapabilityStatus => item !== null),
      statusDefinitions,
      statusCounts,
    },
  };
}

function mergeMarketRiskStatus(
  data: WorkbenchData,
  payload: unknown,
): WorkbenchData {
  return {
    ...data,
    marketRiskStatus: normalizeMarketRiskStatus(payload),
  };
}

function mergeAdvancedStatisticsStatus(
  data: WorkbenchData,
  payload: unknown,
): WorkbenchData {
  return {
    ...data,
    advancedStatisticsStatus: normalizeAdvancedStatisticsStatus(payload),
  };
}

function mergeDrift(data: WorkbenchData, payload: unknown): WorkbenchData {
  const root = asRecord(payload);
  const thresholds = asRecord(root.thresholds);
  const watch = asNumber(thresholds.watch, 0.1);
  const rows = asArray(root.features).map((raw) => {
    const row = asRecord(raw);
    const psi = asNumber(row.psi);
    return {
      metric: `${asString(row.feature).replaceAll("_", " ")} PSI`,
      current: psi,
      reference: watch,
      unit: "",
      status: status(row.status, psi >= watch ? "Watch" : "Stable"),
      note: `Jensen–Shannon distance ${asNumber(
        row.jensen_shannon_distance,
      ).toFixed(4)} · baseline ${numericString(
        row.baseline_sample,
      )} / current ${numericString(row.current_sample)}`,
    };
  });
  return {
    ...data,
    modelMonitoring: rows,
  };
}

const WORKBENCH_ENDPOINTS = [
  "data-source",
  "capabilities",
  "metric-registry",
  "command-centre",
  "alerts",
  "filters",
  "root-cause",
  "vintages",
  "roll-rates",
  "strategy-comparison",
  "partners",
  "vendors",
  "memberships",
  "baskets",
  "finance",
  "data-quality",
  "scenarios",
  "investigations",
  "drift",
  "market-risk/status",
  "advanced-statistics/status",
] as const;

type WorkbenchEndpoint = (typeof WORKBENCH_ENDPOINTS)[number];

function declaredPayloadMode(envelope: FetchEnvelope): DataMode | null {
  const root = asRecord(envelope.payload);
  const context = asRecord(root.source_context ?? root.context);
  return dataMode(
    root.data_mode ?? root.mode ?? context.active_mode ?? envelope.headerMode,
  );
}

function hasDeclaredSourceContext(payload: unknown): boolean {
  const root = asRecord(payload);
  const context = asRecord(root.source_context ?? root.context);
  return Object.keys(context).length > 0;
}

function rootCausePayloadUsable(payload: unknown): boolean {
  const root = asRecord(payload);
  const finding = asRecord(root.finding);
  return Boolean(
    asString(finding.metric_id) &&
    asString(finding.primary_dimension) &&
    asString(finding.primary_driver) &&
    Number.isFinite(Number(finding.observed_change_bps)) &&
    Number.isFinite(Number(finding.mix_contribution_bps)) &&
    Number.isFinite(Number(finding.within_segment_contribution_bps)) &&
    asArray(root.lenses).length > 0,
  );
}

function scenariosPayloadUsable(payload: unknown): boolean {
  const rows = asArray(asRecord(payload).data ?? payload);
  return rows.length > 0 && rows.every((raw) => {
    const row = asRecord(raw);
    const assumptions = asRecord(row.assumptions);
    const projections = asArray(row.projections);
    return Boolean(
      asString(row.id ?? row.scenario_id) &&
      asString(row.name ?? row.scenario_name) &&
      Number.isFinite(Number(assumptions.consumer_stress_index)) &&
      Number.isFinite(Number(assumptions.unemployment_rate)) &&
      Number.isFinite(Number(assumptions.interest_rate)) &&
      Number.isFinite(Number(assumptions.fraud_pressure_index)) &&
      projections.length > 0 &&
      projections.every((rawProjection) => {
        const projection = asRecord(rawProjection);
        return Boolean(
          asString(projection.month) &&
          Number.isFinite(Number(projection.delinquency_30_rate)) &&
          Number.isFinite(Number(projection.annualised_net_loss_rate)) &&
          Number.isFinite(Number(projection.expected_profit)),
        );
      }),
    );
  });
}

function metricRegistryPayloadUsable(payload: unknown): boolean {
  const root = asRecord(payload);
  const rows = asArray(root.data);
  return Boolean(
    asString(root.version ?? root.registry_version) &&
    rows.length > 0 &&
    rows.every((raw) => {
      const row = asRecord(raw);
      const transformation = asRecord(row.transformation);
      const refreshFacts = asRecord(row.refresh_facts);
      const boundary = asRecord(row.interpretation_boundary);
      const adequacy = asRecord(row.adequacy_rule);
      const statistical = asRecord(row.statistical_rule);
      const materiality = asRecord(row.practical_materiality_rule);
      const guardrail = asRecord(row.guardrail_rule);
      const directionality = asString(boundary.directionality);
      return Boolean(
        asString(row.metric_id) &&
        asString(row.source) &&
        stringArray(row.source_fields).length > 0 &&
        asString(row.source_grain) &&
        Array.isArray(row.supporting_sources) &&
        asString(transformation.module) &&
        asString(transformation.callable) &&
        asString(transformation.calculation_version) &&
        asString(refreshFacts.cadence) &&
        asString(refreshFacts.watermark_field) &&
        asString(refreshFacts.runtime_watermark_source) &&
        asString(refreshFacts.refresh_time_source) &&
        asString(refreshFacts.publication_gate) &&
        stringArray(boundary.can_conclude).length > 0 &&
        stringArray(boundary.cannot_conclude).length > 0 &&
        ["higher_is_better", "lower_is_better", "contextual"].includes(
          directionality,
        ) &&
        stringArray(boundary.caveats).length > 0 &&
        asString(boundary.permitted_next_action) &&
        asString(adequacy.denominator_rule) &&
        Number.isFinite(Number(adequacy.minimum_sample)) &&
        asString(adequacy.status_when_met) === "ADEQUATE" &&
        asString(adequacy.status_when_unmet) === "INADEQUATE" &&
        statistical.inference_performed === false &&
        asString(statistical.status) === "NOT_RUN" &&
        asString(statistical.method) === "descriptive_only" &&
        asString(materiality.comparison_basis) &&
        Number.isFinite(Number(materiality.threshold)) &&
        asString(materiality.unit) &&
        asString(guardrail.rule_id) &&
        asString(guardrail.rule_version) &&
        asArray(guardrail.thresholds).length > 0 &&
        asString(guardrail.explanation_template)
      );
    }),
  );
}

function dataSourceDiagnosticsPayloadUsable(payload: unknown): boolean {
  const diagnostics = asRecord(asRecord(payload).diagnostics);
  const snapshot = asRecord(diagnostics.snapshot);
  const provenance = asRecord(diagnostics.provenance);
  const status = asString(diagnostics.diagnostic_status).toUpperCase();
  const freshness = asString(snapshot.freshness_status).toUpperCase();
  return Boolean(
    ["CURRENT", "STALE", "UNAVAILABLE", "UNKNOWN"].includes(status) &&
    asString(diagnostics.server_observed_at) &&
    dataMode(diagnostics.active_mode) &&
    dataMode(diagnostics.configured_mode) &&
    ["CURRENT", "STALE", "UNKNOWN"].includes(freshness) &&
    Number.isFinite(Number(snapshot.stale_after_seconds)) &&
    Object.keys(provenance).length > 0,
  );
}

function kpiGovernanceComplete(metric: KpiMetric): boolean {
  const runtime = metric.runtimeEvidence;
  const boundary = metric.interpretationBoundary;
  const guardrailRule = metric.guardrailRule;
  const guardrail = metric.guardrail;
  const adequacy = metric.sampleAdequacy;
  const statistical = metric.statisticalAssessment;
  const materiality = metric.practicalMateriality;
  const reconciliation = metric.reconciliation;
  return Boolean(
    metric.lineage?.status === "AVAILABLE" &&
    runtime?.evidenceId &&
    runtime.datasetHash &&
    runtime.configurationHash &&
    runtime.runId &&
    runtime.bindingSha256 &&
    runtime.reportingPeriod &&
    runtime.refreshedAt &&
    boundary &&
    boundary.canConclude.length > 0 &&
    boundary.cannotConclude.length > 0 &&
    boundary.directionality !== "UNAVAILABLE" &&
    boundary.caveats.length > 0 &&
    boundary.permittedNextAction &&
    guardrailRule?.ruleId &&
    guardrailRule.ruleVersion &&
    guardrailRule.thresholds.length > 0 &&
    guardrail?.ruleId &&
    guardrail.ruleVersion &&
    guardrail.status !== "UNAVAILABLE" &&
    adequacy &&
    adequacy.status !== "UNAVAILABLE" &&
    adequacy.observedDenominator !== null &&
    adequacy.minimumRequired !== null &&
    statistical &&
    statistical.inferencePerformed === false &&
    statistical.status === "NOT_RUN" &&
    statistical.method === "descriptive_only" &&
    materiality &&
    materiality.status !== "UNAVAILABLE" &&
    materiality.threshold !== null &&
    materiality.unit &&
    reconciliation &&
    ["NOT_RUN", "PASS", "FAIL"].includes(reconciliation.status)
  );
}

function capabilitiesPayloadUsable(payload: unknown): boolean {
  const root = asRecord(payload);
  const allowed = stringArray(root.allowed_statuses);
  const rows = asArray(root.data);
  const identifiers = rows.map((raw) => asString(asRecord(raw).feature_id));
  const returnedCounts = asRecord(root.status_counts);
  const countsMatch = allowed.every((item) => {
    const expected = rows.filter(
      (raw) => asString(asRecord(raw).status).toUpperCase() === item,
    ).length;
    return asNumber(returnedCounts[item]) === expected;
  });
  return (
    rows.length > 0 &&
    allowed.length === CAPABILITY_STATUSES.size &&
    allowed.every((item) => capabilityStatus(item) !== null) &&
    new Set(allowed).size === CAPABILITY_STATUSES.size &&
    identifiers.every(Boolean) &&
    new Set(identifiers).size === identifiers.length &&
    countsMatch &&
    rows.every((raw) => {
      const row = asRecord(raw);
      return Boolean(asString(row.feature_id) && capabilityStatus(row.status));
    })
  );
}

function endpointError(
  failures: Map<string, string>,
  endpoint: WorkbenchEndpoint,
  fallback: string,
): string {
  return failures.get(endpoint) ?? fallback;
}

export async function loadWorkbenchData(
  filters: GlobalFilters,
  outerSignal?: AbortSignal,
  requestedMode: DataMode | null = configuredFrontendMode(),
): Promise<WorkbenchLoadResult> {
  if (requestedMode === "DEMO") {
    const demoFilters = filters.reportingMonth ? filters : DEFAULT_FILTERS;
    return {
      data: deriveDemoData(demoFilters),
      unavailableReason: undefined,
      availableEndpoints: ["deterministic-demo"],
      requestDiagnostics: EMPTY_CLIENT_REQUEST_DIAGNOSTICS,
    };
  }
  if (requestedMode === "UNAVAILABLE") {
    const reason = "The frontend data source is explicitly disabled.";
    return {
      data: createEmptyWorkbenchData("UNAVAILABLE", reason),
      unavailableReason: reason,
      availableEndpoints: [],
      requestDiagnostics: EMPTY_CLIENT_REQUEST_DIAGNOSTICS,
    };
  }

  const query = filtersToQuery(filters);
  const responses = await Promise.allSettled(
    WORKBENCH_ENDPOINTS.map((endpoint) =>
      fetchJson(
        endpoint,
        endpoint === "data-source" ||
          endpoint === "capabilities" ||
          endpoint === "metric-registry"
          ? ""
          : query,
        outerSignal,
      ),
    ),
  );
  const requestDiagnostics = summarizeRequestDiagnostics(responses);
  const failures = new Map<string, string>();
  const candidates = new Map<WorkbenchEndpoint, FetchEnvelope>();
  responses.forEach((result, index) => {
    const endpoint = WORKBENCH_ENDPOINTS[index];
    if (result.status === "rejected") {
      failures.set(
        endpoint,
        result.reason instanceof Error
          ? result.reason.message
          : `${endpoint} is unavailable`,
      );
      return;
    }
    const declaredMode = declaredPayloadMode(result.value);
    if (!declaredMode) {
      failures.set(endpoint, `${endpoint} did not declare a valid data mode`);
      return;
    }
    if (!hasDeclaredSourceContext(result.value.payload)) {
      failures.set(endpoint, `${endpoint} did not supply source context`);
      return;
    }
    candidates.set(endpoint, result.value);
  });

  const candidateModes = new Set(
    [...candidates.values()].map((envelope) => declaredPayloadMode(envelope)),
  );
  candidateModes.delete(null);
  let activeMode: DataMode | null = requestedMode as DataMode | null;
  if (!activeMode) {
    const authoritativeMode = candidates.has("data-source")
      ? declaredPayloadMode(candidates.get("data-source") as FetchEnvelope)
      : null;
    if (authoritativeMode) {
      activeMode = authoritativeMode;
    } else if (candidateModes.size !== 1) {
      const reason = candidateModes.size === 0
        ? "No API response supplied valid data-mode provenance."
        : "API services returned inconsistent data modes.";
      return {
        data: createEmptyWorkbenchData("UNAVAILABLE", reason),
        unavailableReason: reason,
        availableEndpoints: [],
        requestDiagnostics: mergeValidationFailures(requestDiagnostics, failures),
      };
    } else {
      activeMode = [...candidateModes][0] as DataMode;
    }
  }

  const succeeded = new Map<WorkbenchEndpoint, unknown>();
  const authoritativeContext = candidates.has("data-source")
    ? normalizeSourceContext(
        candidates.get("data-source")?.payload,
        activeMode,
      )
    : null;
  candidates.forEach((envelope, endpoint) => {
    if (declaredPayloadMode(envelope) !== activeMode) {
      failures.set(
        endpoint,
        `${endpoint} returned ${declaredPayloadMode(envelope) ?? "no mode"} while ${activeMode} is active`,
      );
      return;
    }
    const endpointContext = normalizeSourceContext(envelope.payload, activeMode);
    const runMismatch = Boolean(
      authoritativeContext?.runId &&
      endpointContext.runId &&
      authoritativeContext.runId !== endpointContext.runId,
    );
    const datasetMismatch = Boolean(
      authoritativeContext?.datasetHash &&
      endpointContext.datasetHash &&
      authoritativeContext.datasetHash !== endpointContext.datasetHash,
    );
    if (runMismatch || datasetMismatch) {
      failures.set(endpoint, `${endpoint} returned inconsistent dataset provenance`);
      return;
    }
    succeeded.set(endpoint, envelope.payload);
  });
  if (
    succeeded.has("data-source") &&
    !dataSourceDiagnosticsPayloadUsable(succeeded.get("data-source"))
  ) {
    failures.set(
      "data-source",
      "data-source did not return complete server diagnostics",
    );
  }

  const contextPayload =
    succeeded.get("data-source") ??
    succeeded.get("command-centre") ??
    succeeded.get("capabilities");
  const sourceContext = contextPayload
    ? normalizeSourceContext(contextPayload, activeMode)
    : emptySourceContext(activeMode, "No verified source context was returned.");
  const serverDiagnostics = succeeded.has("data-source")
    ? normalizeServerDiagnostics(succeeded.get("data-source"))
    : {
        ...EMPTY_SERVER_DIAGNOSTICS,
        activeMode,
        configuredMode: sourceContext.configuredMode,
        provenance: {
          datasetHash: sourceContext.datasetHash,
          datasetHashBasis: sourceContext.datasetHashBasis,
          configurationHash: sourceContext.configurationHash,
          runId: sourceContext.runId,
        },
      };

  if (activeMode === "DEMO") {
    let demo = deriveDemoData(
      filters.reportingMonth ? filters : DEFAULT_FILTERS,
    );
    if (
      succeeded.has("capabilities") &&
      capabilitiesPayloadUsable(succeeded.get("capabilities"))
    ) {
      demo = mergeCapabilities(demo, succeeded.get("capabilities"));
      demo = {
        ...demo,
        metadata: {
          ...demo.metadata,
          availableViews: [...demo.metadata.availableViews, "capabilities"],
          viewErrors: { ...demo.metadata.viewErrors, capabilities: undefined },
        },
      };
    }
    return {
      data: demo,
      unavailableReason: undefined,
      availableEndpoints: [...succeeded.keys()],
      requestDiagnostics: mergeValidationFailures(requestDiagnostics, failures),
    };
  }

  let data = createEmptyWorkbenchData(
    activeMode,
    sourceContext.reason ?? "Some analytical services may be unavailable.",
    sourceContext,
  );
  data = {
    ...data,
    metadata: {
      ...data.metadata,
      dataMode: activeMode,
      sourceContext,
      synthetic: sourceContext.synthetic === true,
      runId: sourceContext.runId ?? "N/A",
      serverDiagnostics,
    },
  };

  const valid = new Set<WorkbenchEndpoint>();
  if (
    succeeded.has("capabilities") &&
    capabilitiesPayloadUsable(succeeded.get("capabilities"))
  ) {
    data = mergeCapabilities(data, succeeded.get("capabilities"));
    valid.add("capabilities");
  }
  if (
    succeeded.has("metric-registry") &&
    metricRegistryPayloadUsable(succeeded.get("metric-registry"))
  ) {
    valid.add("metric-registry");
  } else if (succeeded.has("metric-registry")) {
    failures.set(
      "metric-registry",
      "metric-registry returned no complete governed definitions",
    );
  }

  // An UNAVAILABLE backend may still publish capability truth, but its
  // analytical bodies are deliberately ignored.
  if (activeMode !== "UNAVAILABLE") {
    if (succeeded.has("command-centre")) {
      data = mergeCommandCentre(
        data,
        succeeded.get("command-centre"),
        succeeded.get("metric-registry"),
      );
      if (data.kpis.length > 0) {
        valid.add("command-centre");
        if (!data.kpis.every(kpiGovernanceComplete)) {
          failures.set(
            "command-centre",
            "command-centre returned release-critical KPIs with incomplete governed evidence",
          );
        }
      } else {
        failures.set(
          "command-centre",
          "command-centre returned no complete KPI records",
        );
      }
    }
    if (succeeded.has("alerts")) {
      const durableAlerts = normalizeDurableAlertListPayload(
        succeeded.get("alerts"),
      );
      const historicalRoot = asRecord(succeeded.get("alerts"));
      const historicalRows = asArray(historicalRoot.data);
      const historicalAlerts =
        durableAlerts === null &&
        historicalRows.length > 0 &&
        historicalRows.every((row) => asRecord(row).durable === false)
          ? normalizeAlerts(historicalRows)
          : null;
      if (durableAlerts || historicalAlerts) {
        data = { ...data, alerts: durableAlerts ?? historicalAlerts ?? [] };
        valid.add("alerts");
      } else {
        failures.set(
          "alerts",
          "alerts returned malformed or incomplete durable lifecycle facts",
        );
      }
    }
    if (succeeded.has("filters")) {
      data = mergeFilters(data, succeeded.get("filters"));
      valid.add("filters");
    }
    if (
      succeeded.has("root-cause") &&
      rootCausePayloadUsable(succeeded.get("root-cause"))
    ) {
      data = mergeRootCause(data, succeeded.get("root-cause"));
      valid.add("root-cause");
    }
    if (succeeded.has("vintages")) {
      data = mergeVintages(data, succeeded.get("vintages"));
      if (data.vintages.length > 0) valid.add("vintages");
    }
    if (succeeded.has("roll-rates")) {
      data = mergeRollRates(data, succeeded.get("roll-rates"));
      if (data.rollRates.labels.length > 0) valid.add("roll-rates");
    }
    if (succeeded.has("strategy-comparison")) {
      data = mergeStrategies(data, succeeded.get("strategy-comparison"));
      if (data.strategies.length > 0) valid.add("strategy-comparison");
    }
    if (succeeded.has("partners")) {
      data = mergeEntities(data, "partners", succeeded.get("partners"));
      if (data.partners.length > 0) valid.add("partners");
    }
    if (succeeded.has("vendors")) {
      data = mergeEntities(data, "vendors", succeeded.get("vendors"));
      if (data.vendors.length > 0) valid.add("vendors");
    }
    if (succeeded.has("memberships")) {
      data = mergeEntities(data, "memberships", succeeded.get("memberships"));
      if (data.memberships.length > 0) valid.add("memberships");
    }
    if (succeeded.has("baskets")) {
      data = mergeBaskets(data, succeeded.get("baskets"));
      valid.add("baskets");
    }
    if (succeeded.has("finance")) {
      data = mergeFinance(data, succeeded.get("finance"));
      if (data.finance.bridge.length > 0) valid.add("finance");
    }
    if (succeeded.has("data-quality")) {
      data = mergeDataQuality(data, succeeded.get("data-quality"));
      if (Number.isFinite(Number(asRecord(succeeded.get("data-quality")).score))) {
        valid.add("data-quality");
      }
    }
    if (
      succeeded.has("scenarios") &&
      scenariosPayloadUsable(succeeded.get("scenarios"))
    ) {
      data = mergeScenarios(data, succeeded.get("scenarios"));
      if (data.scenarios.length > 0) valid.add("scenarios");
    }
    if (succeeded.has("investigations")) {
      data = mergeInvestigations(data, succeeded.get("investigations"));
      valid.add("investigations");
    }
    if (succeeded.has("drift")) {
      data = mergeDrift(data, succeeded.get("drift"));
      if (data.modelMonitoring.length > 0) valid.add("drift");
    }
    if (succeeded.has("market-risk/status")) {
      data = mergeMarketRiskStatus(data, succeeded.get("market-risk/status"));
      if (data.marketRiskStatus) valid.add("market-risk/status");
    }
    if (succeeded.has("advanced-statistics/status")) {
      data = mergeAdvancedStatisticsStatus(
        data,
        succeeded.get("advanced-statistics/status"),
      );
      if (data.advancedStatisticsStatus) {
        valid.add("advanced-statistics/status");
      }
    }
  }

  const availableViews: ViewKey[] = [];
  const addView = (view: ViewKey, available: boolean) => {
    if (available) availableViews.push(view);
  };
  const commandReady = valid.has("command-centre");
  const trendReady = commandReady && data.trends.length > 0;
  const rootReady = valid.has("root-cause");
  const qualityReady = valid.has("data-quality");
  addView("executive", trendReady && rootReady);
  addView("trends", trendReady);
  addView("root-cause", rootReady && qualityReady);
  addView("vintage", valid.has("vintages"));
  addView("strategy", valid.has("strategy-comparison"));
  addView("partners", valid.has("partners"));
  addView("vendors", valid.has("vendors"));
  addView("membership", valid.has("memberships"));
  addView("baskets", valid.has("baskets"));
  addView("finance", valid.has("finance"));
  addView("market-risk", valid.has("market-risk/status"));
  addView(
    "advanced-statistics",
    valid.has("advanced-statistics/status"),
  );
  addView("data-quality", qualityReady);
  addView("forecast", valid.has("scenarios"));
  addView("alerts", valid.has("alerts"));
  addView("investigations", valid.has("investigations"));
  addView("model-monitoring", valid.has("drift"));
  addView("methodology", commandReady && rootReady && qualityReady);
  addView("exports", commandReady);
  addView("capabilities", valid.has("capabilities"));
  const storyReady =
    activeMode === "OFFLINE_SNAPSHOT" &&
    commandReady &&
    rootReady &&
    valid.has("vintages") &&
    valid.has("strategy-comparison") &&
    valid.has("scenarios") &&
    data.alerts.length > 0;
  addView("instant-demo", storyReady);

  const viewEndpoint: Partial<Record<ViewKey, WorkbenchEndpoint>> = {
    executive: "command-centre",
    trends: "command-centre",
    "root-cause": "root-cause",
    vintage: "vintages",
    strategy: "strategy-comparison",
    partners: "partners",
    vendors: "vendors",
    membership: "memberships",
    baskets: "baskets",
    finance: "finance",
    "market-risk": "market-risk/status",
    "advanced-statistics": "advanced-statistics/status",
    "data-quality": "data-quality",
    forecast: "scenarios",
    alerts: "alerts",
    investigations: "investigations",
    "model-monitoring": "drift",
    methodology: "command-centre",
    exports: "command-centre",
    capabilities: "capabilities",
  };
  const viewErrors: Partial<Record<ViewKey, string>> = {};
  (Object.keys(viewEndpoint) as ViewKey[]).forEach((view) => {
    if (availableViews.includes(view)) return;
    const endpoint = viewEndpoint[view];
    if (!endpoint) return;
    viewErrors[view] = endpointError(
      failures,
      endpoint,
      `${endpoint} returned no complete records for this view`,
    );
  });
  if (!storyReady) {
    viewErrors["instant-demo"] =
      "The governed portfolio story requires DEMO or OFFLINE_SNAPSHOT mode with complete KPI, root-cause, vintage, strategy, alert and scenario evidence.";
  }
  data = {
    ...data,
    metadata: {
      ...data.metadata,
      availableViews,
      viewErrors,
    },
  };

  const unavailableCount = Object.keys(viewErrors).length;
  const unavailableReason =
    activeMode === "UNAVAILABLE"
      ? sourceContext.reason ?? "The backend data source is unavailable."
      : unavailableCount > 0
        ? `${unavailableCount} workbench views are unavailable because their API data is missing, incomplete, or failed.`
        : undefined;
  return {
    data,
    unavailableReason,
    availableEndpoints: [...valid],
    requestDiagnostics: mergeValidationFailures(requestDiagnostics, failures),
  };
}

function storyInvestigation(
  value: unknown,
  data: WorkbenchData,
): InvestigationRecord | null {
  const row = asRecord(value);
  const id = asString(row.investigation_id ?? row.id);
  if (!id) return null;
  return {
    id,
    alertId: asString(row.alert_id, data.alerts[0]?.id ?? "No linked alert"),
    title: asString(
      row.title ?? row.business_question,
      "Governed portfolio-story investigation",
    ),
    status: asString(row.status, "New"),
    severity: status(row.severity, "Adverse"),
    owner: asString(row.owner, "Portfolio Analytics"),
    opened: asString(
      row.opened_timestamp ?? row.created_at,
      "Created by governed portfolio story",
    ),
    sla: asString(row.sla, "SLA not assigned"),
    hypothesis: asString(
      row.hypothesis,
      "Review the governed portfolio-story evidence.",
    ),
    evidenceCount: asArray(
      row.supporting_evidence ?? row.evidence_ids ?? row.evidence,
    ).length,
    nextAction: asString(
      row.action_taken ?? row.next_action,
      "Review the supported action and record a human decision.",
    ),
  };
}

export function applyPortfolioStoryEvidence(
  current: WorkbenchData,
  run: PortfolioStoryRun,
): WorkbenchData {
  let data = current;
  const evidence = run.evidence;
  if (evidence.command_centre) {
    const command = asRecord(evidence.command_centre);
    const returnedAlerts = asArray(asRecord(evidence.alerts).data);
    data = mergeCommandCentre(
      data,
      returnedAlerts.length > 0 ? { ...command, alerts: returnedAlerts } : command,
    );
    const durableAlerts = normalizeDurableAlertListPayload({ data: returnedAlerts });
    if (durableAlerts !== null && durableAlerts.length > 0) {
      data = { ...data, alerts: durableAlerts };
    }
  }
  if (evidence.root_cause) data = mergeRootCause(data, evidence.root_cause);
  if (evidence.vintages) data = mergeVintages(data, evidence.vintages);
  if (evidence.strategy_comparison) {
    data = mergeStrategies(data, evidence.strategy_comparison);
  }
  if (
    Array.isArray(evidence.scenario) ||
    asArray(asRecord(evidence.scenario).data).length > 0
  ) {
    data = mergeScenarios(data, evidence.scenario);
  }
  const investigation = storyInvestigation(run.investigation, data);
  if (
    investigation &&
    !data.investigations.some((item) => item.id === investigation.id)
  ) {
    data = {
      ...data,
      investigations: [investigation, ...data.investigations],
    };
  }
  const commentarySections = asArray(run.commentary.sections).flatMap((raw) => {
    const row = asRecord(raw);
    const title = asString(row.title);
    const body = asString(row.body);
    return title && body
      ? [{ title, body, metricIds: stringArray(row.metric_ids) }]
      : [];
  });
  if (commentarySections.length > 0) {
    data = {
      ...data,
      commentary: {
        sections: commentarySections,
        provider: asString(run.commentary.provider, data.commentary.provider),
        promptVersion: asString(
          run.commentary.prompt_version,
          data.commentary.promptVersion,
        ),
        status: asString(run.commentary.status, "Draft · human review required"),
      },
    };
  }
  const storyMonth = reportingMonthLabel(run.scope.reportingPeriod);
  const storyFilters = run.scope.filters;
  const withOption = (values: string[], value: string | undefined): string[] =>
    value && !values.includes(value) ? [value, ...values] : values;
  return {
    ...data,
    filterOptions: {
      ...data.filterOptions,
      reportingMonths: withOption(data.filterOptions.reportingMonths, storyMonth),
      products: withOption(
        data.filterOptions.products,
        storyFilters.product ?? storyFilters.product_type,
      ),
      segments: withOption(
        data.filterOptions.segments,
        storyFilters.segment ?? storyFilters.customer_segment,
      ),
      channels: withOption(
        data.filterOptions.channels,
        storyFilters.channel ?? storyFilters.acquisition_channel,
      ),
      geographies: withOption(
        data.filterOptions.geographies,
        storyFilters.geography,
      ),
      riskBands: withOption(
        data.filterOptions.riskBands,
        storyFilters.risk_band ?? storyFilters.original_risk_band,
      ),
      strategies: withOption(
        data.filterOptions.strategies,
        storyFilters.strategy ?? storyFilters.strategy_version,
      ),
      vintages: withOption(data.filterOptions.vintages, storyFilters.vintage),
      modelVersions: withOption(
        data.filterOptions.modelVersions,
        storyFilters.model_version,
      ),
    },
    metadata: {
      ...data.metadata,
      asOf: run.scope.reportingPeriod || data.metadata.asOf,
      comparisonPeriod:
        run.scope.comparisonPeriod || data.metadata.comparisonPeriod,
      dataMode: run.activeMode,
      sourceContext: run.sourceContext,
      qualityStatus: run.dataQuality.status,
      runId: run.sourceContext.runId ?? data.metadata.runId,
      availableViews: data.metadata.availableViews.includes("instant-demo")
        ? data.metadata.availableViews
        : [...data.metadata.availableViews, "instant-demo"],
      viewErrors: { ...data.metadata.viewErrors, "instant-demo": undefined },
    },
  };
}

function reportingMonthLabel(value: string): string {
  const parsed = new Date(`${value.slice(0, 10)}T00:00:00Z`);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleDateString("en-US", {
        month: "short",
        year: "numeric",
        timeZone: "UTC",
      });
}

export function filtersForPortfolioStory(
  run: PortfolioStoryRun,
  current: GlobalFilters,
  options: WorkbenchData["filterOptions"],
): GlobalFilters {
  const source = run.scope.filters;
  const choice = (
    keys: string[],
    available: string[],
    fallback: string,
  ): string => {
    const requested = keys.map((key) => source[key]).find(Boolean);
    if (requested) return requested;
    return available.find((value) => value.startsWith("All ")) ?? fallback;
  };
  const month = reportingMonthLabel(run.scope.reportingPeriod);
  return {
    reportingMonth: month || current.reportingMonth,
    comparison: options.comparisons.includes("Prior month")
      ? "Prior month"
      : current.comparison,
    product: choice(["product", "product_type"], options.products, current.product),
    segment: choice(
      ["segment", "customer_segment"],
      options.segments,
      current.segment,
    ),
    channel: choice(
      ["channel", "acquisition_channel"],
      options.channels,
      current.channel,
    ),
    geography: choice(["geography"], options.geographies, current.geography),
    riskBand: choice(
      ["risk_band", "original_risk_band"],
      options.riskBands,
      current.riskBand,
    ),
    strategy: choice(
      ["strategy", "strategy_version"],
      options.strategies,
      current.strategy,
    ),
    vintage: choice(["vintage"], options.vintages, current.vintage),
    modelVersion: choice(
      ["model_version"],
      options.modelVersions,
      current.modelVersion,
    ),
  };
}

export function getInitialWorkbenchData(): WorkbenchData {
  const configuredMode = configuredFrontendMode();
  if (configuredMode === "DEMO") return deriveDemoData(DEFAULT_FILTERS);
  const reason = configuredMode === "UNAVAILABLE"
    ? "The frontend data source is explicitly disabled."
    : "Waiting for verified API provenance.";
  return createEmptyWorkbenchData("UNAVAILABLE", reason);
}
