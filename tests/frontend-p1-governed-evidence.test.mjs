import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { after, before, test } from "node:test";
import { build } from "vite";

const filters = {
  reportingMonth: "",
  comparison: "",
  product: "",
  segment: "",
  channel: "",
  geography: "",
  riskBand: "",
  strategy: "",
  vintage: "",
  modelVersion: "",
};

let outputDirectory;
let client;
let evidence;
let originalFetch;

before(async () => {
  outputDirectory = await mkdtemp(join(tmpdir(), "naim-p1-evidence-"));
  const compile = async (name, source, define = {}) => {
    const outDir = join(outputDirectory, name);
    await build({
      configFile: false,
      logLevel: "silent",
      define,
      build: {
        ssr: fileURLToPath(new URL(source, import.meta.url)),
        outDir,
        emptyOutDir: true,
        target: "node22",
        rollupOptions: { output: { entryFileNames: "entry.mjs" } },
      },
    });
    return import(`${pathToFileURL(join(outDir, "entry.mjs")).href}?test=${Date.now()}`);
  };
  [client, evidence] = await Promise.all([
    compile("client", "../app/data/api-client.ts", {
      "process.env.NEXT_PUBLIC_NAIM_API_URL": JSON.stringify("http://api.test"),
      "process.env.NEXT_PUBLIC_NAIM_DATA_MODE": "undefined",
    }),
    compile("evidence", "../app/data/governed-evidence.ts"),
  ]);
  originalFetch = globalThis.fetch;
});

after(async () => {
  globalThis.fetch = originalFetch;
  if (outputDirectory) await rm(outputDirectory, { recursive: true, force: true });
});

function context(mode) {
  return {
    active_mode: mode,
    configured_mode: mode,
    snapshot_date: mode === "OFFLINE_SNAPSHOT" ? "2025-12-31" : null,
    configuration_hash: "CONFIG-P1",
    dataset_hash: "DATASET-P1",
    dataset_hash_basis: "canonical-fixture",
    run_id: "RUN-P1",
    synthetic: mode !== "LIVE",
    reason: null,
  };
}

function envelope(payload, mode) {
  return { ...payload, data_mode: mode, source_context: context(mode) };
}

function response(payload, mode, status = 200, requestId = "REQ-P1") {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "content-type": "application/json",
      "X-nAIM-Data-Mode": mode,
      "X-Request-ID": requestId,
    },
  });
}

function endpointFrom(input) {
  return new URL(typeof input === "string" ? input : input.url).pathname
    .replace(/^\/api\/v1\//, "");
}

function installApi(responses, mode) {
  globalThis.fetch = async (input) => {
    const endpoint = endpointFrom(input);
    if (responses[endpoint] !== undefined) {
      return response(
        envelope(responses[endpoint], mode),
        mode,
        200,
        `REQ-${endpoint.toUpperCase()}`,
      );
    }
    return response(
      envelope({ detail: `${endpoint} unavailable in focused fixture` }, mode),
      mode,
      503,
      `REQ-${endpoint.toUpperCase()}`,
    );
  };
}

function metricRegistry() {
  return {
    version: "registry-3.0",
    registry_version: "registry-3.0",
    data: [
      {
        metric_id: "ANNUALISED_NET_LOSS_RATE",
        name: "Annualised net loss rate",
        business_definition: "Annualised portfolio net credit loss as a share of average receivables.",
        source: "analytics.vw_portfolio_loss_monthly",
        source_fields: ["net_credit_loss", "average_receivables"],
        source_grain: "portfolio-month",
        supporting_sources: [
          {
            source: "governance.metric_exclusions",
            source_fields: ["account_id", "exclusion_reason"],
            source_grain: "account-exclusion",
            join_rule: "account_id",
          },
        ],
        transformation: {
          module: "naim.analytics.credit_loss",
          callable: "annualised_net_loss_rate",
          calculation_version: "3.0.1",
        },
        refresh_facts: {
          cadence: "monthly",
          watermark_field: "month",
          runtime_watermark_source: "run_manifest.maximum_data_date",
          refresh_time_source: "run_manifest.completion_timestamp",
          publication_gate: "run_manifest.publication_allowed must be true",
        },
        unit: "annualised_rate",
        scale: "rate",
        numerator: "net credit loss",
        denominator: "average receivables",
        scaling_factor: 12,
        format_string: "0.00%",
        version: "metric-3.0",
        formula: "Portfolio net credit loss divided by average receivables, annualised.",
        exclusions: "Quarantined observations",
        interpretation_boundary: {
          can_conclude: ["Observed portfolio loss increased month over month."],
          cannot_conclude: ["The movement was caused by a single strategy."],
          directionality: "lower_is_better",
          caveats: ["Late recoveries can revise the most recent period."],
          permitted_next_action: "Open a scoped driver investigation.",
        },
        adequacy_rule: {
          denominator_rule: "average receivables must be positive",
          minimum_sample: 1000000,
          status_when_met: "ADEQUATE",
          status_when_unmet: "INADEQUATE",
        },
        statistical_rule: {
          inference_performed: false,
          status: "NOT_RUN",
          method: "descriptive_only",
        },
        practical_materiality_rule: {
          comparison_basis: "absolute_change",
          threshold: 0.0005,
          unit: "rate",
          status_when_material: "MATERIAL",
          status_when_immaterial: "IMMATERIAL",
        },
        guardrail_rule: {
          rule_id: "LOSS-RULE",
          rule_version: "4.2",
          directionality: "lower_is_better",
          denominator_rule: "average receivables must be positive",
          thresholds: [
            { status: "CRITICAL", operator: ">=", value: 0.0015, unit: "rate" },
            { status: "ADVERSE", operator: ">=", value: 0.001, unit: "rate" },
            { status: "WATCH", operator: ">=", value: 0.0005, unit: "rate" },
            { status: "NEUTRAL", operator: "<", value: 0.0005, unit: "rate" },
          ],
          explanation_template: "Compare the observed rate with configured loss thresholds.",
        },
      },
    ],
  };
}

function governedKpi(overrides = {}) {
  const registry = metricRegistry().data[0];
  return {
    metric_id: "ANNUALISED_NET_LOSS_RATE",
    name: "Annualised net loss rate",
    short_name: "Loss rate",
    value: 0.041,
    prior_value: 0.039,
    absolute_change: 0.002,
    relative_change: 0.051282,
    unit: "annualised_rate",
    scale: "rate",
    numerator: "net credit loss",
    denominator: 420000000,
    scaling_factor: 12,
    format_string: "0.00%",
    status: "critical",
    statistical_status: "descriptive_only",
    reporting_period: "2025-12-31",
    comparison_period: "2025-11-30",
    refreshed_at: "2026-08-11T14:00:00Z",
    definition: registry.business_definition,
    source: registry.source,
    source_fields: registry.source_fields,
    source_grain: registry.source_grain,
    lineage: {
      source: registry.source,
      source_fields: registry.source_fields,
      source_grain: registry.source_grain,
      supporting_sources: registry.supporting_sources,
      transformation: registry.transformation,
      refresh_facts: registry.refresh_facts,
    },
    runtime_evidence: {
      evidence_id: "EVIDENCE-LOSS-202512",
      dataset_hash: "DATASET-P1",
      configuration_hash: "CONFIG-P1",
      run_id: "RUN-P1",
      binding_sha256: "BINDING-P1",
      reporting_period: "2025-12-31",
      comparison_period: "2025-11-30",
      refreshed_at: "2026-08-11T14:00:00Z",
    },
    guardrail: {
      rule_id: "LOSS-RULE",
      rule_version: "4.2",
      status: "CRITICAL",
      observed_value: 0.041,
      observed_change: 0.002,
      threshold_applied: { operator: ">=", value: 0.0015, unit: "rate" },
      denominator_rule: "average receivables must be positive",
      directionality: "lower_is_better",
      explanation: "The observed rate exceeds the configured critical threshold.",
    },
    sample_adequacy: {
      status: "ADEQUATE",
      observed_denominator: 420000000,
      minimum_required: 1000000,
      denominator_rule: "average receivables must be positive",
    },
    statistical_assessment: {
      inference_performed: false,
      status: "NOT_RUN",
      method: "descriptive_only",
      explanation: "No inferential significance test was run.",
    },
    practical_materiality: {
      status: "MATERIAL",
      observed_absolute_change: 0.002,
      threshold: 0.0005,
      unit: "rate",
    },
    interpretation_boundary: registry.interpretation_boundary,
    reconciliation: {
      status: "NOT_RUN",
      scope: "cross_artifact",
      checked_at: null,
      detail: "Ordinary API response; cross-artifact reconciliation was not run.",
    },
    ...overrides,
  };
}

function commandCentre(kpi = governedKpi()) {
  return {
    metadata: {
      as_of: "2025-12-31",
      comparison_period: "2025-11-30",
      quality_status: "PASS",
      row_counts: { monthly_account_performance: 12 },
      run_id: "RUN-P1",
      metric_registry_version: "registry-3.0",
      refreshed_at: "2026-08-11T14:00:00Z",
    },
    kpis: [kpi],
    trends: [],
    risk_distribution: [],
    alerts: [],
    interpretation: {},
  };
}

function dataSource(mode, diagnosticStatus = "CURRENT") {
  return {
    mode,
    configured_mode: mode,
    available: true,
    context: context(mode),
    diagnostics: {
      diagnostic_status: diagnosticStatus,
      server_observed_at: "2026-08-11T14:00:01Z",
      active_mode: mode,
      configured_mode: mode,
      snapshot: {
        created_at: mode === "OFFLINE_SNAPSHOT" ? "2026-08-11T13:00:00Z" : null,
        maximum_data_date: "2025-12-31",
        age_seconds: diagnosticStatus === "STALE" ? 90000 : 10,
        stale_after_seconds: 86400,
        freshness_status: diagnosticStatus === "STALE" ? "STALE" : "CURRENT",
      },
      provenance: {
        dataset_hash: "DATASET-P1",
        dataset_hash_basis: "canonical-fixture",
        configuration_hash: "CONFIG-P1",
        run_id: "RUN-P1",
      },
    },
  };
}

test("release-critical KPI consumes complete governed lineage and metric-specific boundaries", async () => {
  installApi(
    {
      "data-source": dataSource("LIVE"),
      "metric-registry": metricRegistry(),
      "command-centre": commandCentre(),
    },
    "LIVE",
  );
  const result = await client.loadWorkbenchData(filters, undefined, "LIVE");
  const metric = result.data.kpis[0];
  assert.equal(metric.releaseCritical, true);
  assert.equal(metric.status, "Critical");
  assert.equal(metric.lineage.status, "AVAILABLE");
  assert.equal(metric.definition.source, "analytics.vw_portfolio_loss_monthly");
  assert.notEqual(metric.definition.source, "N/A");
  assert.match(metric.definition.businessDefinition, /Annualised portfolio net credit loss/);
  assert.equal(metric.definition.exclusions, "Quarantined observations");
  assert.equal(metric.guardrailRule.ruleVersion, "4.2");
  assert.equal(metric.guardrailRule.thresholds.length, 4);
  assert.equal(metric.guardrail.status, "CRITICAL");
  assert.equal(metric.interpretationBoundary.directionality, "lower_is_better");
  assert.equal(metric.sampleAdequacy.status, "ADEQUATE");
  assert.equal(metric.statisticalAssessment.status, "NOT_RUN");
  assert.equal(metric.practicalMateriality.status, "MATERIAL");
  assert.equal(metric.reconciliation.status, "NOT_RUN");

  const drawer = evidence.buildMetricEvidence(metric);
  assert.deepEqual(
    drawer.tabs.map((tab) => tab.label),
    ["Definition", "Calculation", "Source", "Scope", "Interpretation", "Statistics", "History", "Artifacts"],
  );
  const serialized = JSON.stringify(drawer);
  assert.match(serialized, /analytics\.vw_portfolio_loss_monthly/);
  assert.match(serialized, /The movement was caused by a single strategy/);
  assert.match(serialized, /LOSS-RULE/);
  assert.match(serialized, /Configured thresholds/);
  assert.match(serialized, /observed rate exceeds the configured critical threshold/);
  assert.match(serialized, /No inferential significance test was run/);
  assert.match(serialized, /run_manifest\.maximum_data_date/);
  assert.match(serialized, /publication_allowed must be true/);
  assert.match(serialized, /MATERIAL/);
  assert.match(serialized, /NOT_RUN/);
  assert.doesNotMatch(serialized, /Source[^}]{0,60}N\/A/);
});

test("missing governed lineage fails closed as a visible defect", async () => {
  const missing = governedKpi({
    source: undefined,
    source_fields: undefined,
    source_grain: undefined,
    lineage: undefined,
    status: "insufficient_data",
    guardrail: {
      rule_id: "LOSS-RULE",
      rule_version: "4.2",
      status: "INSUFFICIENT_DATA",
      observed_value: 0.041,
      observed_change: null,
      threshold_applied: null,
      denominator_rule: "average receivables must be positive",
      directionality: "lower_is_better",
      explanation: "The governed denominator is below the configured minimum.",
    },
    sample_adequacy: {
      status: "INADEQUATE",
      observed_denominator: 10,
      minimum_required: 1000000,
      denominator_rule: "average receivables must be positive",
    },
  });
  installApi(
    {
      "data-source": dataSource("LIVE"),
      "metric-registry": { ...metricRegistry(), data: [] },
      "command-centre": commandCentre(missing),
    },
    "LIVE",
  );
  const result = await client.loadWorkbenchData(filters, undefined, "LIVE");
  const metric = result.data.kpis[0];
  assert.equal(metric.lineage.status, "UNAVAILABLE");
  assert.match(metric.lineage.defect, /^LINEAGE UNAVAILABLE/);
  assert.equal(metric.status, "Unavailable");
  assert.equal(metric.guardrail.status, "INSUFFICIENT_DATA");
  assert.equal(metric.sampleAdequacy.status, "INADEQUATE");
  assert.ok(result.requestDiagnostics.failedEndpoints.includes("metric-registry"));
  assert.match(result.requestDiagnostics.lastError, /incomplete governed evidence/);
  assert.equal(
    evidence.diagnosticDisplayStatus(
      result.data.metadata.dataMode,
      result.data.metadata.serverDiagnostics,
      result.requestDiagnostics,
      "CONNECTED",
    ),
    "API_ERROR",
  );
  const drawer = evidence.buildMetricEvidence(metric);
  assert.match(JSON.stringify(drawer), /LINEAGE UNAVAILABLE/);
  assert.ok(drawer.defect);
});

test("stale server status remains separate from governed OFFLINE_SNAPSHOT mode", async () => {
  installApi(
    {
      "data-source": dataSource("OFFLINE_SNAPSHOT", "STALE"),
      "metric-registry": metricRegistry(),
      "command-centre": commandCentre(),
    },
    "OFFLINE_SNAPSHOT",
  );
  const result = await client.loadWorkbenchData(filters, undefined, "OFFLINE_SNAPSHOT");
  assert.equal(result.data.metadata.dataMode, "OFFLINE_SNAPSHOT");
  assert.equal(result.data.metadata.serverDiagnostics.diagnosticStatus, "STALE");
  assert.equal(result.data.metadata.serverDiagnostics.snapshot.freshnessStatus, "STALE");
  assert.equal(
    evidence.diagnosticDisplayStatus(
      result.data.metadata.dataMode,
      result.data.metadata.serverDiagnostics,
      result.requestDiagnostics,
      "CONNECTED",
    ),
    "STALE",
  );
  assert.match(result.requestDiagnostics.clientRequestId, /^NAIM-WEB-/);
  assert.match(result.requestDiagnostics.serverRequestId, /^REQ-/);
  assert.ok(result.requestDiagnostics.responseTimeMs >= 0);
  assert.ok(result.requestDiagnostics.lastSuccessfulRequest);
  assert.ok(result.requestDiagnostics.endpoint);
});

test("retry transitions report Retrying, Connected, and Still unavailable truthfully", () => {
  let state = evidence.retryStateReducer("IDLE", { type: "begin" });
  assert.equal(state, "RETRYING");
  state = evidence.retryStateReducer(state, { type: "connected" });
  assert.equal(state, "CONNECTED");
  state = evidence.retryStateReducer(state, { type: "begin" });
  state = evidence.retryStateReducer(state, { type: "unavailable" });
  assert.equal(state, "STILL_UNAVAILABLE");
  assert.equal(
    evidence.diagnosticDisplayStatus(
      "UNAVAILABLE",
      client.EMPTY_SERVER_DIAGNOSTICS,
      { ...client.EMPTY_CLIENT_REQUEST_DIAGNOSTICS, lastError: "API failed" },
      state,
    ),
    "API_ERROR",
  );
});

test("diagnostic resolver exposes every status without rewriting active mode", () => {
  const current = {
    ...client.EMPTY_SERVER_DIAGNOSTICS,
    diagnosticStatus: "CURRENT",
    snapshot: {
      ...client.EMPTY_SERVER_DIAGNOSTICS.snapshot,
      freshnessStatus: "CURRENT",
    },
  };
  const emptyClient = client.EMPTY_CLIENT_REQUEST_DIAGNOSTICS;
  assert.equal(evidence.diagnosticDisplayStatus("LIVE", current, emptyClient, "CONNECTED"), "LIVE");
  assert.equal(
    evidence.diagnosticDisplayStatus("OFFLINE_SNAPSHOT", current, emptyClient, "CONNECTED"),
    "OFFLINE_SNAPSHOT",
  );
  assert.equal(evidence.diagnosticDisplayStatus("DEMO", current, emptyClient, "IDLE"), "DEMO");
  assert.equal(
    evidence.diagnosticDisplayStatus(
      "LIVE",
      { ...current, diagnosticStatus: "STALE" },
      emptyClient,
      "CONNECTED",
    ),
    "STALE",
  );
  assert.equal(
    evidence.diagnosticDisplayStatus(
      "UNAVAILABLE",
      current,
      { ...emptyClient, lastError: "network error" },
      "STILL_UNAVAILABLE",
    ),
    "API_ERROR",
  );
  assert.equal(
    evidence.diagnosticDisplayStatus(
      "LIVE",
      current,
      {
        ...emptyClient,
        lastError: "command-centre returned 503",
        failedEndpoints: ["command-centre"],
      },
      "CONNECTED",
    ),
    "API_ERROR",
  );
  assert.equal(
    evidence.diagnosticDisplayStatus("UNAVAILABLE", current, emptyClient, "IDLE"),
    "UNAVAILABLE",
  );
  assert.equal(
    evidence.diagnosticDisplayStatus(
      "LIVE",
      {
        ...current,
        diagnosticStatus: "UNKNOWN",
        snapshot: { ...current.snapshot, freshnessStatus: "UNKNOWN" },
      },
      emptyClient,
      "CONNECTED",
    ),
    "UNAVAILABLE",
  );
  assert.equal(
    evidence.diagnosticDisplayStatus(
      "UNAVAILABLE",
      current,
      emptyClient,
      "STILL_UNAVAILABLE",
    ),
    "UNAVAILABLE",
  );
});

test("evidence tabs and retry diagnostics expose accessible UI semantics", async () => {
  const [ui, workbench, pages] = await Promise.all([
    readFile(new URL("../app/components/ui.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/workbench.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/pages.tsx", import.meta.url), "utf8"),
  ]);
  for (const semantic of [
    'role="dialog"',
    'role="tablist"',
    'role="tab"',
    'role="tabpanel"',
    "aria-selected",
    "aria-controls",
    "ArrowRight",
    "ArrowLeft",
  ]) {
    assert.match(ui, new RegExp(semantic.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }
  assert.match(ui, /LINEAGE UNAVAILABLE/);
  assert.doesNotMatch(ui, /Validated synthetic result/);
  assert.doesNotMatch(ui, /nAIM analytics v2\.4\.0/);
  assert.match(workbench, /Governed data diagnostics/);
  assert.match(workbench, /Last successful request/);
  assert.match(workbench, /Client request ID/);
  assert.match(workbench, /Server request ID/);
  assert.match(workbench, /Retrying API/);
  assert.match(workbench, /Still unavailable/);
  assert.doesNotMatch(pages, /definition\.source/);
});
