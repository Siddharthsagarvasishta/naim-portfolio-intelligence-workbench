import {
  formatMetricNumber,
  formatMetricValue,
  normalizeMetricUnit,
  scaleMetricValue,
} from "./metric-format";
import type {
  ClientRequestDiagnostics,
  DataMode,
  DiagnosticDisplayStatus,
  EvidenceItem,
  EvidenceTab,
  KpiMetric,
  RetryState,
  ServerDataDiagnostics,
} from "../workbench-types";

const UNAVAILABLE = "UNAVAILABLE";
const LINEAGE_UNAVAILABLE = "LINEAGE UNAVAILABLE";

function text(value: string | null | undefined): string {
  return value?.trim() || UNAVAILABLE;
}

function list(values: string[] | undefined): string {
  return values && values.length > 0 ? values.join(" · ") : UNAVAILABLE;
}

function number(value: number | null | undefined): string {
  return value === null || value === undefined
    ? UNAVAILABLE
    : value.toLocaleString("en-US", { maximumFractionDigits: 6 });
}

function yesNo(value: boolean | null | undefined): string {
  if (value === null || value === undefined) return UNAVAILABLE;
  return value ? "Yes" : "No";
}

function governedRuleValue(
  value: number | null | undefined,
  unit: string | null | undefined,
): string {
  if (value === null || value === undefined || !unit) return UNAVAILABLE;
  if (unit === "accounts" || unit === "account") {
    return `${Math.round(value).toLocaleString("en-US")} accounts`;
  }
  if (unit === "cases" || unit === "case") {
    return `${Math.round(value).toLocaleString("en-US")} cases`;
  }
  return formatMetricNumber(
    scaleMetricValue(value, unit),
    normalizeMetricUnit(unit),
  );
}

function operatorLabel(operator: string): string {
  return {
    gt: ">",
    gte: "≥",
    lt: "<",
    lte: "≤",
    absolute_lte: "absolute change ≤",
  }[operator] ?? operator;
}

function thresholdList(metric: KpiMetric): string {
  const thresholds = metric.guardrailRule?.thresholds ?? [];
  if (thresholds.length > 0) {
    return thresholds
      .map((threshold) =>
        `${threshold.status}: ${operatorLabel(threshold.operator)}${
          threshold.value === null
            ? ""
            : ` ${governedRuleValue(threshold.value, threshold.unit)}`
        }`.trim(),
      )
      .join(" · ");
  }
  const applied = metric.guardrail?.thresholdApplied;
  if (!applied) return UNAVAILABLE;
  const operator = typeof applied.operator === "string" ? applied.operator : "";
  const value = typeof applied.value === "number" ? applied.value : null;
  const unit = typeof applied.unit === "string" ? applied.unit : null;
  if (!operator || value === null || !unit) return UNAVAILABLE;
  return `Applied threshold: ${operatorLabel(operator)} ${governedRuleValue(value, unit)}`;
}

function supportingSources(metric: KpiMetric): string {
  const sources = metric.lineage?.supportingSources ?? [];
  if (sources.length === 0) return "None declared by the metric registry";
  return sources
    .map((source) => {
      const join = source.joinRule ? `; join ${source.joinRule}` : "";
      return `${source.source} [${source.sourceFields.join(", ")}] at ${source.sourceGrain}${join}`;
    })
    .join(" · ");
}

function relativeChange(metric: KpiMetric): string {
  return metric.relativeChange === null
    ? UNAVAILABLE
    : `${(metric.relativeChange * 100).toFixed(2)}%`;
}

export function metricLineageAvailable(metric: KpiMetric): boolean {
  return Boolean(
    metric.lineage?.status === "AVAILABLE" &&
      metric.lineage.source &&
      metric.lineage.sourceFields.length > 0 &&
      metric.lineage.sourceGrain &&
      metric.lineage.transformation.module &&
      metric.lineage.transformation.callable &&
      metric.lineage.transformation.calculationVersion &&
      metric.lineage.refreshFacts.cadence &&
      metric.lineage.refreshFacts.watermarkField &&
      metric.lineage.refreshFacts.runtimeWatermarkSource &&
      metric.lineage.refreshFacts.refreshTimeSource &&
      metric.lineage.refreshFacts.publicationGate,
  );
}

export function buildMetricEvidenceTabs(metric: KpiMetric): EvidenceTab[] {
  const lineageAvailable = metricLineageAvailable(metric);
  const lineage = metric.lineage;
  const boundary = metric.interpretationBoundary;
  const guardrail = metric.guardrail;
  const runtime = metric.runtimeEvidence;
  const adequacy = metric.sampleAdequacy;
  const statistical = metric.statisticalAssessment;
  const materiality = metric.practicalMateriality;
  const reconciliation = metric.reconciliation;

  return [
    {
      id: "definition",
      label: "Definition",
      facts: [
        { label: "Metric ID", value: metric.id },
        { label: "Name", value: metric.name },
        { label: "Business definition", value: text(metric.definition.businessDefinition) },
        { label: "Registry version", value: text(metric.definition.version) },
        { label: "Unit", value: text(metric.registryUnit ?? metric.unit) },
        { label: "Exclusions", value: text(metric.definition.exclusions) },
      ],
    },
    {
      id: "calculation",
      label: "Calculation",
      facts: [
        { label: "Formula", value: text(metric.definition.formula) },
        { label: "Numerator", value: text(metric.numerator) },
        { label: "Denominator", value: text(metric.denominator) },
        {
          label: "Scaling factor",
          value: number(metric.scalingFactor),
        },
        { label: "Display scale", value: text(metric.scale) },
        {
          label: "Transformation module",
          value: text(lineage?.transformation.module),
        },
        {
          label: "Callable",
          value: text(lineage?.transformation.callable),
        },
        {
          label: "Calculation version",
          value: text(lineage?.transformation.calculationVersion),
        },
      ],
      defect: lineageAvailable ? undefined : LINEAGE_UNAVAILABLE,
    },
    {
      id: "source",
      label: "Source",
      facts: [
        {
          label: "Lineage state",
          value: lineageAvailable ? "AVAILABLE" : LINEAGE_UNAVAILABLE,
        },
        {
          label: "Controlling source",
          value: lineageAvailable ? text(lineage?.source) : LINEAGE_UNAVAILABLE,
        },
        {
          label: "Source fields",
          value: lineageAvailable ? list(lineage?.sourceFields) : LINEAGE_UNAVAILABLE,
        },
        {
          label: "Source grain",
          value: lineageAvailable ? text(lineage?.sourceGrain) : LINEAGE_UNAVAILABLE,
        },
        { label: "Supporting sources", value: supportingSources(metric) },
      ],
      defect: lineageAvailable ? undefined : text(lineage?.defect),
    },
    {
      id: "scope",
      label: "Scope",
      facts: [
        { label: "Reporting period", value: text(runtime?.reportingPeriod ?? metric.reportingPeriod) },
        { label: "Comparison period", value: text(runtime?.comparisonPeriod ?? metric.comparisonPeriod) },
        { label: "Source grain", value: lineageAvailable ? text(lineage?.sourceGrain) : LINEAGE_UNAVAILABLE },
        { label: "Denominator rule", value: text(guardrail?.denominatorRule ?? metric.guardrailRule?.denominatorRule) },
        { label: "Observed denominator", value: number(adequacy?.observedDenominator) },
      ],
    },
    {
      id: "interpretation",
      label: "Interpretation",
      facts: [
        { label: "Can conclude", value: list(boundary?.canConclude) },
        { label: "Cannot conclude", value: list(boundary?.cannotConclude) },
        { label: "Directionality", value: text(boundary?.directionality) },
        { label: "Configured guardrail", value: `${text(metric.guardrailRule?.ruleId ?? guardrail?.ruleId)} · version ${text(metric.guardrailRule?.ruleVersion ?? guardrail?.ruleVersion)}` },
        { label: "Configured thresholds", value: thresholdList(metric) },
        { label: "Guardrail rule template", value: text(metric.guardrailRule?.explanationTemplate) },
        { label: "Runtime guardrail status", value: text(guardrail?.status) },
        { label: "Guardrail explanation", value: text(guardrail?.explanation) },
        { label: "Caveats", value: list(boundary?.caveats) },
        { label: "Permitted next action", value: text(boundary?.permittedNextAction) },
      ],
    },
    {
      id: "statistics",
      label: "Statistics",
      facts: [
        { label: "Sample adequacy", value: text(adequacy?.status) },
        { label: "Observed denominator", value: number(adequacy?.observedDenominator) },
        { label: "Minimum required", value: number(adequacy?.minimumRequired) },
        { label: "Adequacy rule", value: text(adequacy?.denominatorRule) },
        { label: "Statistical inference performed", value: yesNo(statistical?.inferencePerformed) },
        { label: "Statistical significance", value: text(statistical?.status) },
        { label: "Statistical method", value: text(statistical?.method) },
        { label: "Statistical explanation", value: text(statistical?.explanation) },
        { label: "Practical materiality", value: text(materiality?.status) },
        { label: "Observed absolute change", value: governedRuleValue(materiality?.observedAbsoluteChange, materiality?.unit) },
        { label: "Materiality threshold", value: governedRuleValue(materiality?.threshold, materiality?.unit) },
      ],
    },
    {
      id: "history",
      label: "History",
      facts: [
        { label: "Current", value: formatMetricValue(metric) },
        { label: "Prior", value: formatMetricValue(metric, metric.prior) },
        { label: "Absolute change", value: formatMetricValue(metric, metric.absoluteChange) },
        { label: "Relative change", value: relativeChange(metric) },
        { label: "Reporting period", value: text(runtime?.reportingPeriod ?? metric.reportingPeriod) },
        { label: "Comparison period", value: text(runtime?.comparisonPeriod ?? metric.comparisonPeriod) },
        { label: "Refreshed at", value: text(runtime?.refreshedAt ?? metric.refreshedAt) },
        { label: "Refresh cadence", value: text(lineage?.refreshFacts.cadence) },
        { label: "Watermark field", value: text(lineage?.refreshFacts.watermarkField) },
        { label: "Runtime watermark source", value: text(lineage?.refreshFacts.runtimeWatermarkSource) },
        { label: "Refresh time source", value: text(lineage?.refreshFacts.refreshTimeSource) },
        { label: "Publication gate", value: text(lineage?.refreshFacts.publicationGate) },
      ],
    },
    {
      id: "artifacts",
      label: "Artifacts",
      facts: [
        { label: "Evidence ID", value: text(runtime?.evidenceId) },
        { label: "Run ID", value: text(runtime?.runId) },
        { label: "Dataset hash", value: text(runtime?.datasetHash) },
        { label: "Configuration hash", value: text(runtime?.configurationHash) },
        { label: "Runtime binding SHA-256", value: text(runtime?.bindingSha256) },
        { label: "Reconciliation", value: text(reconciliation?.status) },
        { label: "Reconciliation scope", value: text(reconciliation?.scope) },
        { label: "Checked at", value: text(reconciliation?.checkedAt) },
        { label: "Reconciliation detail", value: text(reconciliation?.detail) },
      ],
    },
  ];
}

export function buildMetricEvidence(metric: KpiMetric): EvidenceItem {
  const lineageAvailable = metricLineageAvailable(metric);
  return {
    eyebrow: "Governed metric evidence",
    title: metric.name,
    summary: text(metric.definition.businessDefinition ?? metric.definition.formula),
    facts: [
      { label: "Current", value: formatMetricValue(metric) },
      {
        label: "Lineage state",
        value: lineageAvailable ? "AVAILABLE" : LINEAGE_UNAVAILABLE,
      },
      { label: "Guardrail", value: text(metric.guardrail?.status) },
      { label: "Reconciliation", value: text(metric.reconciliation?.status) },
    ],
    caveat: list(metric.interpretationBoundary?.caveats),
    action: text(metric.interpretationBoundary?.permittedNextAction),
    defect: lineageAvailable ? undefined : text(metric.lineage?.defect),
    tabs: buildMetricEvidenceTabs(metric),
  };
}

export type RetryAction =
  | { type: "begin" }
  | { type: "connected" }
  | { type: "unavailable" }
  | { type: "reset" };

export function retryStateReducer(
  state: RetryState,
  action: RetryAction,
): RetryState {
  if (action.type === "begin") return "RETRYING";
  if (action.type === "connected") return "CONNECTED";
  if (action.type === "unavailable") return "STILL_UNAVAILABLE";
  if (action.type === "reset") return "IDLE";
  return state;
}

export function hasCriticalRequestFailure(
  client: ClientRequestDiagnostics,
): boolean {
  return client.failedEndpoints.some((endpoint) =>
    endpoint === "data-source" ||
    endpoint === "metric-registry" ||
    endpoint === "command-centre",
  );
}

export function diagnosticDisplayStatus(
  activeMode: DataMode,
  server: ServerDataDiagnostics,
  client: ClientRequestDiagnostics,
  retryState: RetryState,
): DiagnosticDisplayStatus {
  if (activeMode === "DEMO") return "DEMO";
  const criticalRequestFailed = hasCriticalRequestFailure(client);
  if (
    (retryState === "STILL_UNAVAILABLE" ||
      activeMode === "UNAVAILABLE" ||
      criticalRequestFailed) &&
    client.lastError
  ) {
    return "API_ERROR";
  }
  if (server.diagnosticStatus === "STALE" || server.snapshot.freshnessStatus === "STALE") {
    return "STALE";
  }
  if (server.diagnosticStatus === "UNAVAILABLE") return "UNAVAILABLE";
  if (
    server.diagnosticStatus === "UNKNOWN" ||
    server.snapshot.freshnessStatus === "UNKNOWN"
  ) {
    return "UNAVAILABLE";
  }
  if (activeMode === "LIVE") return "LIVE";
  if (activeMode === "OFFLINE_SNAPSHOT") return "OFFLINE_SNAPSHOT";
  return "UNAVAILABLE";
}
