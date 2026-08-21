export type SignalStatus =
  | "Favourable"
  | "Stable"
  | "Watch"
  | "Adverse"
  | "Critical"
  | "Unavailable";

export type WorkbenchMode = "executive" | "analyst" | "recruiter";

export type DataMode =
  | "LIVE"
  | "DEMO"
  | "OFFLINE_SNAPSHOT"
  | "UNAVAILABLE";

export type CapabilityStatus =
  | "LIVE"
  | "INTEGRATION_ONLY"
  | "DOCUMENTED"
  | "DISABLED"
  | "NOT_IMPLEMENTED";

export type ViewKey =
  | "start-here"
  | "samples"
  | "how-naim"
  | "why-naim"
  | "data-onboarding"
  | "executive"
  | "trends"
  | "root-cause"
  | "vintage"
  | "strategy"
  | "partners"
  | "vendors"
  | "membership"
  | "baskets"
  | "finance"
  | "market-risk"
  | "advanced-statistics"
  | "data-quality"
  | "forecast"
  | "alerts"
  | "investigations"
  | "model-monitoring"
  | "methodology"
  | "exports"
  | "capabilities"
  | "instant-demo";

export interface SourceContext {
  activeMode: DataMode;
  configuredMode: DataMode;
  snapshotDate: string | null;
  configurationHash: string | null;
  datasetHash: string | null;
  datasetHashBasis: string | null;
  runId: string | null;
  synthetic: boolean | null;
  reason: string | null;
}

export interface PortfolioStoryRun {
  runId: string;
  reused: boolean;
  status: string;
  activeMode: DataMode;
  sourceContext: SourceContext;
  workspace: {
    id: string;
    name: string;
    reportingPeriod: string;
    comparisonPeriod: string;
    approvalState: string;
  };
  scope: {
    reportingPeriod: string;
    comparisonPeriod: string;
    filters: Record<string, string>;
  };
  dataQuality: {
    status: string;
    publicationAllowed: boolean;
    latestAvailableMonth: string;
    completenessPercentage: number | null;
  };
  story: {
    whatChanged: string;
    why: string;
    uncertainties: string[];
    supportedAction: string;
    evidenceProduced: string[];
    outputsAvailable: string[];
  };
  evidence: Record<string, unknown>;
  investigation: Record<string, unknown>;
  commentary: Record<string, unknown>;
  outputs: Array<Record<string, unknown>>;
  steps: Array<Record<string, unknown>>;
}

export interface ExecutivePackResult {
  jobId: string;
  artifactId: string;
  status: string;
  reused: boolean;
  stage: string;
  lastCompletedStage: string;
  filename: string;
  format: "pptx";
  slideCount: number;
  fileSha256: string;
  sizeBytes: number;
  scope: Record<string, unknown>;
  dataMode: DataMode;
  evidenceId: string;
  metricRegistryVersion: string;
  syntheticStatement: string;
  refreshedAt: string;
  validation: Record<string, unknown>;
  reconciliation: Record<string, unknown>;
  downloadUrl: string;
  manifestUrl: string;
}

export interface CapabilityRecord {
  featureId: string;
  name: string;
  status: CapabilityStatus;
  backendEndpoints: string[];
  frontendRoutes: string[];
  calculationModules: string[];
  testEvidence: string[];
  artifactEvidence: string[];
  limitation: string;
  lastValidationDate: string;
  owner: string;
  version: string;
}

export interface CapabilityRegistryMetadata {
  registryVersion: string;
  schemaVersion: string;
  product: string;
  allowedStatuses: CapabilityStatus[];
  statusDefinitions: Partial<Record<CapabilityStatus, string>>;
  statusCounts: Partial<Record<CapabilityStatus, number>>;
}

export interface MarketRiskStatus {
  available: boolean;
  status: string;
  providerMode: string;
  instruments: string[];
  externalProvider: CapabilityStatus;
  methods: string[];
  tradingRecommendation: boolean;
  approvalRequired: boolean;
}

export interface AdvancedStatisticsMethod {
  id: string;
  name: string;
  status: CapabilityStatus;
}

export interface AdvancedStatisticsStatus {
  available: boolean;
  status: string;
  methods: AdvancedStatisticsMethod[];
  causalClaim: boolean;
  approvalRequired: boolean;
}

export interface MarketRiskModelResult {
  model: string;
  oneStepForecast: number | null;
  qlike: number | null;
  rmseVariance: number | null;
  persistence: number | null;
  diagnosticStatus: string;
  rank: number | null;
}

export interface MarketRiskTailMethod {
  method: string;
  valueAtRisk: number | null;
  expectedShortfall: number | null;
  tailObservations: number | null;
  status: string;
}

export interface MarketRiskRegimePoint {
  date: string;
  volatility: number | null;
  regime: string;
  changePoint: boolean;
}

export interface MarketRiskRunResult {
  evidenceId: string;
  purpose: string;
  dataMode: DataMode;
  sourceContext: SourceContext;
  source: {
    instrument: string;
    provider: string;
    requestedStartDate: string;
    requestedEndDate: string;
    priceBasis: string;
    sourceHash: string;
    synthetic: boolean;
    redistributionPermitted: boolean;
    terms: string;
  };
  observations: number;
  annualisedVolatility: number | null;
  ewmaLatest: number | null;
  ewmaForecast: number | null;
  archForecast: number | null;
  garchForecast: number | null;
  models: MarketRiskModelResult[];
  tailRisk: MarketRiskTailMethod[];
  backtest: {
    breachCount: number | null;
    observedBreachRate: number | null;
    trafficLight: string;
    kupiecPValue: number | null;
    christoffersenPValue: number | null;
  };
  regimes: MarketRiskRegimePoint[];
  regimeCounts: Array<{ regime: string; observations: number }>;
  validation: {
    status: string;
    publicationAllowed: boolean;
    publicationBasis: string;
  };
  approvalRequired: boolean;
  synthetic: boolean;
}

export interface GlobalFilters {
  reportingMonth: string;
  comparison: string;
  product: string;
  segment: string;
  channel: string;
  geography: string;
  riskBand: string;
  strategy: string;
  vintage: string;
  modelVersion: string;
}

export interface FilterOptions {
  reportingMonths: string[];
  comparisons: string[];
  products: string[];
  segments: string[];
  channels: string[];
  geographies: string[];
  riskBands: string[];
  strategies: string[];
  vintages: string[];
  modelVersions: string[];
}

export interface MetricDefinition {
  businessDefinition?: string;
  formula: string;
  denominator: string;
  exclusions: string;
  source: string;
  version: string;
}

export type MetricDirectionality =
  | "higher_is_better"
  | "lower_is_better"
  | "contextual"
  | "UNAVAILABLE";

export interface MetricLineage {
  status: "AVAILABLE" | "UNAVAILABLE";
  source: string | null;
  sourceFields: string[];
  sourceGrain: string | null;
  supportingSources: Array<{
    source: string;
    sourceFields: string[];
    sourceGrain: string;
    joinRule: string | null;
  }>;
  transformation: {
    module: string | null;
    callable: string | null;
    calculationVersion: string | null;
  };
  refreshFacts: {
    cadence: string | null;
    watermarkField: string | null;
    runtimeWatermarkSource: string | null;
    refreshTimeSource: string | null;
    publicationGate: string | null;
  };
  defect: string | null;
}

export interface MetricInterpretationBoundary {
  canConclude: string[];
  cannotConclude: string[];
  directionality: MetricDirectionality;
  caveats: string[];
  permittedNextAction: string | null;
}

export interface MetricGuardrailRule {
  ruleId: string | null;
  ruleVersion: string | null;
  directionality: MetricDirectionality;
  denominatorRule: string | null;
  thresholds: Array<{
    status: string;
    operator: string;
    value: number | null;
    unit: string;
  }>;
  explanationTemplate: string | null;
}

export interface MetricGuardrailAssessment {
  ruleId: string | null;
  ruleVersion: string | null;
  status: string;
  observedValue: number | null;
  observedChange: number | null;
  thresholdApplied: Record<string, unknown> | null;
  denominatorRule: string | null;
  directionality: MetricDirectionality;
  explanation: string | null;
}

export interface MetricRuntimeEvidence {
  evidenceId: string | null;
  datasetHash: string | null;
  configurationHash: string | null;
  runId: string | null;
  bindingSha256: string | null;
  reportingPeriod: string | null;
  comparisonPeriod: string | null;
  refreshedAt: string | null;
}

export interface MetricSampleAdequacy {
  status: "ADEQUATE" | "INADEQUATE" | "UNAVAILABLE";
  observedDenominator: number | null;
  minimumRequired: number | null;
  denominatorRule: string | null;
}

export interface MetricStatisticalAssessment {
  inferencePerformed: boolean | null;
  status: string;
  method: string | null;
  explanation: string | null;
}

export interface MetricPracticalMateriality {
  status: "MATERIAL" | "IMMATERIAL" | "NOT_ASSESSABLE" | "UNAVAILABLE";
  observedAbsoluteChange: number | null;
  threshold: number | null;
  unit: string | null;
}

export interface MetricReconciliation {
  status: "NOT_RUN" | "PASS" | "FAIL" | "UNAVAILABLE";
  scope: string | null;
  checkedAt: string | null;
  detail: string | null;
}

export type MetricDisplayUnit =
  | "count"
  | "cases"
  | "currency"
  | "percent"
  | "bps"
  | "per_1000"
  | "ratio"
  | "days"
  | "months";

export interface KpiMetric {
  id: string;
  name: string;
  shortName: string;
  value: number | null;
  prior: number | null;
  absoluteChange: number | null;
  relativeChange: number | null;
  unit: MetricDisplayUnit;
  registryUnit?: string;
  scale?: string;
  numerator?: string;
  scalingFactor?: number;
  formatString?: string;
  currencyCode?: string;
  currencySymbol?: string;
  denominator: string;
  status: SignalStatus;
  statisticalStatus: string;
  refreshedAt: string;
  definition: MetricDefinition;
  releaseCritical?: boolean;
  reportingPeriod?: string | null;
  comparisonPeriod?: string | null;
  lineage?: MetricLineage;
  interpretationBoundary?: MetricInterpretationBoundary;
  guardrailRule?: MetricGuardrailRule;
  guardrail?: MetricGuardrailAssessment;
  runtimeEvidence?: MetricRuntimeEvidence;
  sampleAdequacy?: MetricSampleAdequacy;
  statisticalAssessment?: MetricStatisticalAssessment;
  practicalMateriality?: MetricPracticalMateriality;
  reconciliation?: MetricReconciliation;
}

export interface TrendPoint {
  month: string;
  value: number;
  comparison?: number;
  lower?: number;
  upper?: number;
}

export interface Series {
  id: string;
  label: string;
  unit: string;
  points: TrendPoint[];
}

export interface DistributionPoint {
  label: string;
  value: number;
  secondary?: number;
  status?: SignalStatus;
}

export interface ContributionPoint {
  label: string;
  contribution: number;
  mix: number;
  performance: number;
  population: number;
  persistence: number;
  status: SignalStatus;
}

export type AlertLifecycleStatus =
  | "NEW"
  | "ACKNOWLEDGED"
  | "INVESTIGATING"
  | "ACTION_PROPOSED"
  | "MONITORING"
  | "RESOLVED"
  | "SUPPRESSED"
  | "CLOSED_AS_NOISE";

export type AlertLifecycleTransition = Exclude<AlertLifecycleStatus, "NEW">;

export interface AlertAcknowledgement {
  acknowledged: boolean;
  by: string | null;
  at: string | null;
  note: string | null;
}

export interface AlertSla {
  hours: number;
  dueAt: string;
}

export interface AlertCooldown {
  periods: number;
  untilPeriod: string | null;
}

export interface AlertSuppression {
  active: boolean;
  reason: string | null;
  by: string | null;
  at: string | null;
  untilPeriod: string | null;
}

export interface AlertResolution {
  reason: string | null;
  by: string | null;
  at: string | null;
}

export interface AlertReopenEvent {
  reopenedAt: string;
  runId: string;
  period: string;
  priorStatus: "RESOLVED" | "SUPPRESSED" | "CLOSED_AS_NOISE";
  cooldownUntilPeriod: string | null;
  reason: string;
  observationKey: string;
}

export interface AlertRuntimeEvidence {
  runId: string;
  configurationHash: string;
  datasetHash: string | null;
  period: string;
  comparisonPeriod: string | null;
  dataQualityStatus: string;
  currentValue: number | null;
  baselineValue: number | null;
  absoluteMovement: number | null;
  relativeMovement: number | null;
  denominator: number;
  observationKey: string;
}

export interface AlertAuditEvent {
  eventType:
    | "ALERT_CREATED"
    | "ALERT_REPEATED"
    | "ALERT_ESCALATED"
    | "ALERT_ACKNOWLEDGED"
    | "ALERT_SUPPRESSED"
    | "ALERT_RESOLVED"
    | "ALERT_REOPENED"
    | "ALERT_CONDITION_CLEARED"
    | "ALERT_INVESTIGATION_LINKED"
    | "ALERT_STATUS_TRANSITIONED";
  actor: string;
  occurredAt: string;
  payload: Record<string, unknown>;
  previousHash: string | null;
  eventHash: string;
}

export interface AlertAuditIntegrity {
  status: "PASS" | "FAIL";
  chainValid: boolean;
  eventCount: number;
  headHash: string | null;
}

export interface AlertAuditTrail {
  alertId: string;
  fingerprint: string;
  version: number;
  auditEvents: AlertAuditEvent[];
  auditIntegrity: AlertAuditIntegrity;
}

export interface DurableAlertLifecycle {
  fingerprint: string;
  ruleId: string;
  ruleName: string;
  ruleVersion: string;
  status: AlertLifecycleStatus;
  acknowledgement: AlertAcknowledgement;
  sla: AlertSla;
  recurrenceCount: number;
  firstObservedAt: string;
  firstObservedPeriod: string;
  lastObservedAt: string;
  lastObservedPeriod: string;
  lastObservationKey: string;
  cooldown: AlertCooldown;
  suppression: AlertSuppression;
  resolution: AlertResolution;
  reopenHistory: AlertReopenEvent[];
  latestEvidence: AlertRuntimeEvidence;
  relatedInvestigation: string | null;
  version: number;
  auditIntegrity: AlertAuditIntegrity;
  auditEvents: AlertAuditEvent[];
  allowedTransitions: AlertLifecycleTransition[];
  canAcknowledge: boolean;
  conditionActive: boolean;
  workflowActive: boolean;
}

export interface AlertRecord {
  id: string;
  severity: SignalStatus;
  title: string;
  metric: string;
  current: string;
  baseline: string;
  threshold: string;
  segment: string;
  owner: string;
  state: string;
  age: string;
  evidence: string[];
  durable?: boolean;
  lifecycle?: DurableAlertLifecycle;
}

export interface RootCauseFinding {
  metricId: string;
  comparisonPeriod: string;
  observedChangeBps: number;
  dataQualityStatus: string;
  primaryDimension: string;
  primaryDriver: string;
  contributionShare: number;
  mixContributionBps: number;
  withinSegmentContributionBps: number;
  supportingDrivers: string[];
  causalStatus: string;
  recommendedInvestigation: string[];
}

export interface RootCauseLens {
  dimension: string;
  total: number;
  items: ContributionPoint[];
}

export interface VintageCell {
  vintage: string;
  mob: number;
  cohortSize: number;
  delinquency30: number;
  cumulativeLoss: number;
  confidenceLow: number;
  confidenceHigh: number;
  maturityWarning: boolean;
  channel: string;
}

export interface StrategyResult {
  strategy: string;
  status: string;
  eligibleAccounts: number;
  assignmentShare: number;
  lossRate: number;
  fraudBps: number;
  reviewRate: number;
  falsePositiveRate: number;
  frictionRate: number;
  complaintsPerThousand: number;
  expectedProfit: number;
}

export interface EntityScore {
  id: string;
  name: string;
  category: string;
  region: string;
  scale: number;
  growth: number;
  profit: number;
  riskMetric: number;
  serviceMetric: number;
  concentration: number;
  score: number;
  grade: string;
  trend: SignalStatus;
  status?: string;
}

export interface BasketRecord {
  id: string;
  name: string;
  type: string;
  memberCount: number;
  version: string;
  status: string;
  approved: boolean;
  owner: string;
  updated: string;
  definition: string;
  weightBasis: string;
  metrics: {
    balance: number | null;
    transactionValue: number | null;
    lossRate: number | null;
    expectedProfit: number | null;
  };
}

export interface FinanceBridgeItem {
  label: string;
  value: number;
  group: "opening" | "favourable" | "adverse" | "closing";
}

export interface DataQualityCheck {
  id: string;
  name: string;
  severity: "Critical" | "High" | "Medium" | "Warning";
  status: "Pass" | "Warning" | "Fail";
  affectedRows: number;
  businessImpact: string;
  quarantine: string;
  recommendation: string;
}

export interface ScenarioProjection {
  month: string;
  delinquency30: number;
  annualisedLossRate: number;
  fraudLoss: number;
  reviews: number;
  expectedProfit: number;
  lower: number;
  upper: number;
}

export interface ScenarioRecord {
  id: string;
  name: string;
  description: string;
  assumptions: {
    consumerStress: number;
    unemployment: number;
    interestRate: number;
    fraudPressure: number;
  };
  projections: ScenarioProjection[];
  cumulativeLoss: number;
  cumulativeFraud: number;
  expectedProfit: number;
  deltaFromBaseline: number;
}

export interface InvestigationRecord {
  id: string;
  alertId: string;
  title: string;
  status: string;
  severity: SignalStatus;
  owner: string;
  opened: string;
  sla: string;
  hypothesis: string;
  evidenceCount: number;
  nextAction: string;
}

export interface ModelMonitor {
  metric: string;
  current: number;
  reference: number;
  unit: string;
  status: SignalStatus;
  note: string;
}

export type ServerDiagnosticStatus =
  | "CURRENT"
  | "STALE"
  | "UNAVAILABLE"
  | "UNKNOWN";

export interface ServerDataDiagnostics {
  diagnosticStatus: ServerDiagnosticStatus;
  serverObservedAt: string | null;
  activeMode: DataMode | null;
  configuredMode: DataMode | null;
  snapshot: {
    createdAt: string | null;
    maximumDataDate: string | null;
    ageSeconds: number | null;
    staleAfterSeconds: number | null;
    freshnessStatus: "CURRENT" | "STALE" | "UNKNOWN";
  };
  provenance: {
    datasetHash: string | null;
    datasetHashBasis: string | null;
    configurationHash: string | null;
    runId: string | null;
  };
}

export interface ClientRequestDiagnostics {
  lastSuccessfulRequest: string | null;
  endpoint: string | null;
  clientRequestId: string | null;
  serverRequestId: string | null;
  responseTimeMs: number | null;
  lastError: string | null;
  failedEndpoints: string[];
}

export type RetryState = "IDLE" | "RETRYING" | "CONNECTED" | "STILL_UNAVAILABLE";

export type DiagnosticDisplayStatus =
  | "LIVE"
  | "OFFLINE_SNAPSHOT"
  | "STALE"
  | "API_ERROR"
  | "DEMO"
  | "UNAVAILABLE";

export interface WorkbenchData {
  metadata: {
    asOf: string;
    comparisonPeriod: string;
    refreshedAt: string;
    synthetic: boolean;
    qualityStatus: string;
    dataMode: DataMode;
    sourceContext: SourceContext;
    availableViews: ViewKey[];
    viewErrors: Partial<Record<ViewKey, string>>;
    rowCount: number;
    runId: string;
    calculationVersion: string;
    serverDiagnostics: ServerDataDiagnostics;
  };
  filterOptions: FilterOptions;
  kpis: KpiMetric[];
  trends: Series[];
  riskDistribution: DistributionPoint[];
  rollRates: {
    labels: string[];
    values: number[][];
  };
  contributors: ContributionPoint[];
  alerts: AlertRecord[];
  interpretation: {
    adverse: string[];
    favourable: string;
    caveat: string;
    priority: string;
  };
  rootCause: {
    finding: RootCauseFinding;
    lenses: RootCauseLens[];
    hierarchy: Array<{
      level: string;
      value: string;
      contribution: number;
      share: number;
      population: number;
    }>;
    behaviouralDrivers: DistributionPoint[];
  };
  vintages: VintageCell[];
  strategies: StrategyResult[];
  strategyRecommendation?: {
    decision: string;
    rulePath: string[];
    approvalRequired: boolean;
    notice: string;
  };
  strategyValidity: Array<{
    test: string;
    result: string;
    status: SignalStatus;
    detail: string;
  }>;
  partners: EntityScore[];
  vendors: EntityScore[];
  memberships: EntityScore[];
  baskets: BasketRecord[];
  finance: {
    bridge: FinanceBridgeItem[];
    unitEconomics: DistributionPoint[];
    concentration: DistributionPoint[];
    driverTree: Array<{ parent: string; child: string; value: number }>;
  };
  dataQuality: {
    score: number;
    status: string;
    checks: DataQualityCheck[];
    manifest: Array<{ label: string; value: string }>;
    lineage: string[];
  };
  scenarios: ScenarioRecord[];
  investigations: InvestigationRecord[];
  modelMonitoring: ModelMonitor[];
  commentary: {
    sections: Array<{ title: string; body: string; metricIds: string[] }>;
    provider: string;
    promptVersion: string;
    status: string;
  };
  marketRiskStatus: MarketRiskStatus | null;
  advancedStatisticsStatus: AdvancedStatisticsStatus | null;
  capabilities: CapabilityRecord[];
  capabilityRegistry: CapabilityRegistryMetadata;
}

export interface EvidenceItem {
  eyebrow: string;
  title: string;
  summary: string;
  facts: Array<{ label: string; value: string }>;
  caveat?: string;
  action?: string;
  defect?: string;
  tabs?: EvidenceTab[];
}

export type EvidenceTabId =
  | "definition"
  | "calculation"
  | "source"
  | "scope"
  | "interpretation"
  | "statistics"
  | "history"
  | "artifacts";

export interface EvidenceTab {
  id: EvidenceTabId;
  label: string;
  facts: Array<{ label: string; value: string }>;
  note?: string;
  defect?: string;
}

export interface PageProps {
  data: WorkbenchData;
  mode: WorkbenchMode;
  filters: GlobalFilters;
  portfolioStory: PortfolioStoryRun | null;
  onOpenEvidence: (evidence: EvidenceItem) => void;
  onNavigate: (view: ViewKey) => void;
  onAlertUpdated: (alert: AlertRecord) => void;
  onRefreshData: () => void;
}
