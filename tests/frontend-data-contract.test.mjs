import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
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
let contract;
let originalFetch;

before(async () => {
  outputDirectory = await mkdtemp(join(tmpdir(), "naim-frontend-contract-"));
  await build({
    configFile: false,
    logLevel: "silent",
    define: {
      "process.env.NEXT_PUBLIC_NAIM_API_URL": JSON.stringify("http://api.test"),
      "process.env.NEXT_PUBLIC_NAIM_DATA_MODE": "undefined",
    },
    build: {
      ssr: fileURLToPath(new URL("../app/data/api-client.ts", import.meta.url)),
      outDir: outputDirectory,
      emptyOutDir: true,
      target: "node22",
      rollupOptions: { output: { entryFileNames: "contract-client.mjs" } },
    },
  });
  contract = await import(
    `${pathToFileURL(join(outputDirectory, "contract-client.mjs")).href}?test=${Date.now()}`
  );
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
    configuration_hash: "config-contract-hash",
    dataset_hash: "dataset-contract-hash",
    dataset_hash_basis: "contract-test",
    run_id: "RUN-CONTRACT-ONLY",
    synthetic: mode !== "LIVE",
    reason: null,
  };
}

function withProvenance(payload, mode = "LIVE") {
  return { ...payload, data_mode: mode, source_context: context(mode) };
}

function jsonResponse(payload, mode = "LIVE", status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "content-type": "application/json",
      "X-nAIM-Data-Mode": mode,
    },
  });
}

function endpointFrom(input) {
  const pathname = new URL(typeof input === "string" ? input : input.url).pathname;
  return pathname.replace(/^\/api\/v1\//, "");
}

function installApi(responses, mode = "LIVE") {
  globalThis.fetch = async (input) => {
    const endpoint = endpointFrom(input);
    const configured = responses[endpoint];
    if (configured instanceof Response) return configured;
    if (configured !== undefined) {
      return jsonResponse(withProvenance(configured, mode), mode);
    }
    return jsonResponse(
      withProvenance({ detail: `${endpoint} deliberately unavailable` }, mode),
      mode,
      503,
    );
  };
}

function dataSource(mode = "LIVE") {
  return {
    mode,
    configured_mode: mode,
    available: mode !== "UNAVAILABLE",
    context: context(mode),
    data_mode: mode,
    source_context: context(mode),
  };
}

function capabilities(status = "INTEGRATION_ONLY", mode = "LIVE") {
  return withProvenance(
    {
      schema_version: "1.0.0",
      registry_version: "contract-registry",
      product: "nAIM Portfolio Intelligence Workbench",
      allowed_statuses: [
        "LIVE",
        "INTEGRATION_ONLY",
        "DOCUMENTED",
        "DISABLED",
        "NOT_IMPLEMENTED",
      ],
      status_definitions: {
        LIVE: "Executable evidence exists.",
        INTEGRATION_ONLY: "Interface only.",
        DOCUMENTED: "Documentation only.",
        DISABLED: "Disabled by configuration.",
        NOT_IMPLEMENTED: "No implementation.",
      },
      data: [
        {
          feature_id: "CONTRACT_ONLY_FEATURE",
          name: "Contract-only feature",
          status,
          backend_endpoint: [],
          frontend_route: [],
          calculation_module: [],
          test_evidence: [],
          artifact_evidence: [],
          limitation: "This limitation must remain visible.",
          last_validation_date: "2026-08-01",
          owner: "Contract test",
          version: "1.0.0",
        },
      ],
      status_counts: { [status]: 1 },
    },
    mode,
  );
}

function partialCommand(mode = "LIVE") {
  return withProvenance(
    {
      metadata: {
        as_of: "2025-12-31",
        comparison_period: "2025-11-30",
        quality_status: "PASS",
        row_counts: { monthly_account_performance: 17 },
        run_id: "RUN-CONTRACT-ONLY",
        metric_registry_version: "contract",
      },
      kpis: [
        {
          metric_id: "ACTIVE_ACCOUNTS",
          name: "API contract accounts",
          value: 17,
          // Deliberately omit prior_value and definition subfields.
          unit: "count",
          denominator: 17,
          status: "neutral",
          reporting_period: "2025-12-31",
          comparison_period: "2025-11-30",
        },
      ],
      trends: [
        {
          month: "2025-12-01",
          metric_id: "ACTIVE_ACCOUNTS",
          value: 17,
          unit: "count",
        },
      ],
      risk_distribution: [],
      alerts: [],
      interpretation: {},
    },
    mode,
  );
}

const demoSentinels = [
  "42.7",
  "Affiliate acquisition",
  "Champion A",
  "SYN-202512-017",
  "548216",
];

function assertNoDemoSentinels(value) {
  const serialized = JSON.stringify(value);
  for (const sentinel of demoSentinels) {
    assert.doesNotMatch(serialized, new RegExp(sentinel, "i"), sentinel);
  }
}

test("partial LIVE payloads preserve N/A/null and never borrow demo facts", async () => {
  installApi({
    "data-source": dataSource("LIVE"),
    capabilities: capabilities("INTEGRATION_ONLY", "LIVE"),
    "command-centre": partialCommand("LIVE"),
  });

  const result = await contract.loadWorkbenchData(filters, undefined, "LIVE");
  assert.equal(result.data.metadata.dataMode, "LIVE");
  assert.equal(result.data.kpis.length, 1);
  assert.equal(result.data.kpis[0].value, 17);
  assert.equal(result.data.kpis[0].prior, null);
  assert.equal(result.data.kpis[0].definition.source, "N/A");
  assert.equal(result.data.rootCause.lenses.length, 0);
  assert.equal(result.data.metadata.availableViews.includes("root-cause"), false);
  assert.match(result.data.metadata.viewErrors["root-cause"], /unavailable|no complete|503/i);
  assert.equal(result.data.capabilities[0].status, "INTEGRATION_ONLY");
  assert.equal(
    result.data.capabilities[0].limitation,
    "This limitation must remain visible.",
  );
  assertNoDemoSentinels(result.data);
});

test("failed API produces UNAVAILABLE, not an implicit demo", async () => {
  globalThis.fetch = async () => {
    throw new Error("deliberate network failure");
  };
  const result = await contract.loadWorkbenchData(filters, undefined, null);
  assert.equal(result.data.metadata.dataMode, "UNAVAILABLE");
  assert.deepEqual(result.data.kpis, []);
  assert.deepEqual(result.data.scenarios, []);
  assert.deepEqual(result.availableEndpoints, []);
  assertNoDemoSentinels(result.data);
});

test("malformed optional capability status is not promoted or rendered", async () => {
  installApi({
    "data-source": dataSource("LIVE"),
    capabilities: capabilities("SECRETLY_LIVE", "LIVE"),
    "command-centre": partialCommand("LIVE"),
  });
  const result = await contract.loadWorkbenchData(filters, undefined, "LIVE");
  assert.deepEqual(result.data.capabilities, []);
  assert.equal(result.data.metadata.availableViews.includes("capabilities"), false);
  assert.match(result.data.metadata.viewErrors.capabilities, /no complete/i);
  assertNoDemoSentinels(result.data);
});

test("quant status routes require complete live contracts and preserve SHAP boundary", async () => {
  installApi({
    "data-source": dataSource("LIVE"),
    capabilities: capabilities("INTEGRATION_ONLY", "LIVE"),
    "market-risk/status": {
      available: true,
      status: "LIVE",
      provider_mode: "bundled_deterministic_sample",
      instruments: ["NAIM-DEMO-INDEX"],
      external_provider: "INTEGRATION_ONLY",
      methods: ["historical volatility", "GARCH(1,1)", "VaR"],
      trading_recommendation: false,
      approval_required: true,
    },
    "advanced-statistics/status": {
      available: true,
      status: "LIVE",
      methods: {
        kaplan_meier_and_log_rank: "LIVE",
        behavioural_model_and_fallback_contributions: "LIVE",
        shap: "INTEGRATION_ONLY",
        single_change_point: "LIVE",
        propensity_weighting: "LIVE",
        synthetic_policy_difference_in_differences: "LIVE",
        cox_proportional_hazards: "NOT_IMPLEMENTED",
      },
      causal_claim: false,
      approval_required: true,
    },
  });

  const result = await contract.loadWorkbenchData(filters, undefined, "LIVE");
  assert.equal(result.data.metadata.availableViews.includes("market-risk"), true);
  assert.equal(
    result.data.metadata.availableViews.includes("advanced-statistics"),
    true,
  );
  assert.equal(result.data.marketRiskStatus.providerMode, "bundled_deterministic_sample");
  assert.equal(result.data.marketRiskStatus.externalProvider, "INTEGRATION_ONLY");
  assert.equal(
    result.data.advancedStatisticsStatus.methods.find((method) => method.id === "shap").status,
    "INTEGRATION_ONLY",
  );
  assert.equal(result.data.advancedStatisticsStatus.causalClaim, false);
});

test("market-risk execution normalizes governed evidence only after an explicit call", async () => {
  let calls = 0;
  globalThis.fetch = async (input, init) => {
    assert.equal(endpointFrom(input), "market-risk/run");
    assert.equal(init.method, "POST");
    calls += 1;
    return jsonResponse(
      withProvenance({
        evidence_id: "MRISK-CONTRACT",
        purpose: "Risk diagnostics; not a trading recommendation.",
        approval_required: true,
        synthetic: true,
        source: {
          instrument: "NAIM-DEMO-INDEX",
          provider: "bundled_deterministic_sample",
          requested_start_date: "2022-12-31",
          requested_end_date: "2025-12-31",
          price_basis: "adjusted close",
          raw_source_sha256: "contract-market-source-hash",
          source_is_synthetic: true,
          redistribution_permitted: true,
          provider_terms: "Bundled synthetic data.",
        },
        returns: {
          summary: {
            observations: 782,
            annualised_standard_deviation: 0.1571,
          },
        },
        ewma: {
          latest_annualised_volatility: 0.1401,
          one_step_annualised_volatility_forecast: 0.1378,
        },
        conditional_volatility: {
          arch: { annualised_volatility_forecast: [0.157] },
          garch: { annualised_volatility_forecast: [0.158] },
        },
        model_comparison: {
          qlike_ranking: ["garch", "historical"],
          models: [
            {
              model: "historical",
              one_step_forecast: 0.159,
              out_of_sample_qlike: -8.2,
              out_of_sample_rmse_variance: 0.00016,
              parameter_persistence: null,
              diagnostic_status: "non_parametric",
            },
            {
              model: "garch",
              one_step_forecast: 0.158,
              out_of_sample_qlike: -8.3,
              out_of_sample_rmse_variance: 0.00015,
              parameter_persistence: 0.84,
              diagnostic_status: "implemented",
            },
          ],
        },
        var_expected_shortfall: {
          methods: {
            historical: {
              var: 0.026,
              expected_shortfall: 0.035,
              tail_observations: 8,
            },
          },
        },
        var_backtesting: {
          breach_count: 7,
          observed_breach_rate: 0.0119,
          traffic_light: { status: "green" },
          kupiec_unconditional_coverage: { p_value: 0.65 },
          christoffersen_independence: { p_value: 0.68 },
        },
        regimes: {
          series: [
            {
              date: "2025-12-31",
              annualised_volatility: 0.14,
              regime: "calm",
              change_point_indicator: false,
            },
          ],
          observation_counts: { calm: 381, elevated: 266, stressed: 115 },
        },
        validation: {
          status: "PASS",
          publication_allowed: true,
          publication_basis: "Executable checks passed.",
        },
      }),
    );
  };

  const result = await contract.runMarketRiskLab(
    {
      instrument: "NAIM-DEMO-INDEX",
      period: "three_years",
      frequency: "daily",
      returnType: "log",
      confidence: 0.99,
    },
    "LIVE",
  );
  assert.equal(calls, 1);
  assert.equal(result.dataMode, "LIVE");
  assert.equal(result.evidenceId, "MRISK-CONTRACT");
  assert.equal(result.models.find((model) => model.model === "garch").rank, 1);
  assert.equal(result.tailRisk[0].valueAtRisk, 0.026);
  assert.equal(result.source.sourceHash, "contract-market-source-hash");
  assert.equal(result.validation.publicationAllowed, true);
});

test("market-risk execution rejects provenance mismatch without substituting results", async () => {
  globalThis.fetch = async () =>
    jsonResponse(withProvenance({ status: "implemented" }, "DEMO"), "DEMO");
  await assert.rejects(
    contract.runMarketRiskLab(
      {
        instrument: "NAIM-DEMO-INDEX",
        period: "one_year",
        frequency: "daily",
        returnType: "log",
        confidence: 0.99,
      },
      "LIVE",
    ),
    /while LIVE is active/,
  );
});

test("OFFLINE_SNAPSHOT exposes exact snapshot provenance and keeps missing KPI fields null", async () => {
  installApi(
    {
      "data-source": dataSource("OFFLINE_SNAPSHOT"),
      "command-centre": partialCommand("OFFLINE_SNAPSHOT"),
    },
    "OFFLINE_SNAPSHOT",
  );
  const result = await contract.loadWorkbenchData(
    filters,
    undefined,
    "OFFLINE_SNAPSHOT",
  );
  assert.equal(result.data.metadata.dataMode, "OFFLINE_SNAPSHOT");
  assert.equal(result.data.metadata.sourceContext.snapshotDate, "2025-12-31");
  assert.equal(
    result.data.metadata.sourceContext.configurationHash,
    "config-contract-hash",
  );
  assert.equal(
    result.data.metadata.sourceContext.datasetHash,
    "dataset-contract-hash",
  );
  assert.equal(result.data.kpis[0].prior, null);
  assertNoDemoSentinels(result.data);
});

test("DEMO is explicit, deterministic, and does not call analytical APIs", async () => {
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    throw new Error("DEMO must not fetch");
  };
  const first = await contract.loadWorkbenchData(filters, undefined, "DEMO");
  const second = await contract.loadWorkbenchData(filters, undefined, "DEMO");
  assert.equal(first.data.metadata.dataMode, "DEMO");
  assert.equal(calls, 0);
  assert.deepEqual(first.data, second.data);
});

function portfolioStoryPayload(reused = false) {
  return withProvenance({
    run_id: "DEMO-CONTRACT-1",
    demo_run_id: "DEMO-CONTRACT-1",
    status: "completed",
    reused,
    active_mode: "OFFLINE_SNAPSHOT",
    workspace: {
      workspace_id: "WS-APPROVED",
      workspace_name: "Approved deterioration story",
      reporting_period: "2025-12-31",
      comparison_period: "2025-11-30",
      filter_configuration: { acquisition_channel: "Affiliate" },
      approval_state: "APPROVED",
    },
    scope: {
      reporting_period: "2025-12-31",
      comparison_period: "2025-11-30",
      filters: { acquisition_channel: "Affiliate" },
    },
    data_quality: {
      status: "PASS_WITH_WARNINGS",
      publication_allowed: true,
      latest_available_month: "2025-12-31",
      completeness_percentage: 99.8,
    },
    story: {
      what_changed: "Loss increased.",
      why: "Affiliate mix and performance.",
      uncertainties: ["Associational evidence only."],
      supported_action: "Open a targeted review.",
      evidence_produced: ["KPI", "Root cause", "Vintage"],
      outputs_available: ["Executive PowerPoint"],
    },
    evidence: {},
    investigation: {
      investigation_id: "INV-DEMO-STABLE",
      alert_id: "ALT-1",
      status: "New",
      owner: "Portfolio Analytics",
    },
    commentary: { status: "draft" },
    outputs: [{ format: "pptx" }],
    steps: [{ step: "confirm_data_mode", status: "completed" }],
  }, "OFFLINE_SNAPSHOT");
}

test("governed portfolio story launches in OFFLINE_SNAPSHOT and reuses backend objects", async () => {
  let calls = 0;
  globalThis.fetch = async (input, init) => {
    assert.equal(endpointFrom(input), "demo/run");
    assert.equal(init.method, "POST");
    calls += 1;
    return jsonResponse(portfolioStoryPayload(calls > 1), "OFFLINE_SNAPSHOT");
  };

  const first = await contract.runPortfolioStory("OFFLINE_SNAPSHOT");
  const repeated = await contract.runPortfolioStory("OFFLINE_SNAPSHOT");
  assert.equal(first.runId, "DEMO-CONTRACT-1");
  assert.equal(first.activeMode, "OFFLINE_SNAPSHOT");
  assert.equal(first.workspace.id, "WS-APPROVED");
  assert.equal(first.scope.filters.acquisition_channel, "Affiliate");
  assert.equal(first.dataQuality.publicationAllowed, true);
  assert.deepEqual(first.story.evidenceProduced, ["KPI", "Root cause", "Vintage"]);
  assert.equal(repeated.runId, first.runId);
  assert.equal(repeated.reused, true);

  const demo = await contract.loadWorkbenchData(filters, undefined, "DEMO");
  const governedFilters = contract.filtersForPortfolioStory(
    first,
    demo.data.filterOptions.reportingMonths.length > 0
      ? { ...filters, reportingMonth: "Aug 2025" }
      : filters,
    demo.data.filterOptions,
  );
  assert.equal(governedFilters.reportingMonth, "Dec 2025");
  assert.equal(governedFilters.comparison, "Prior month");
  assert.equal(governedFilters.channel, "Affiliate");
  assert.equal(governedFilters.product, "All products");
  const appliedOnce = contract.applyPortfolioStoryEvidence(demo.data, first);
  const appliedTwice = contract.applyPortfolioStoryEvidence(appliedOnce, repeated);
  assert.equal(
    appliedTwice.investigations.filter((item) => item.id === "INV-DEMO-STABLE").length,
    1,
  );
});

test("executive-pack workflow creates a job, reads status, and returns only governed PPTX links", async () => {
  const endpoints = [];
  globalThis.fetch = async (input, init) => {
    const endpoint = endpointFrom(input);
    endpoints.push(endpoint);
    if (endpoint === "executive-packs/generate") {
      assert.equal(init.method, "POST");
      const body = JSON.parse(init.body);
      assert.deepEqual(body, {
        workspace_id: "WS-APPROVED",
        reporting_period: "2025-12-31",
        comparison_period: "2025-11-30",
        filter_scope: { acquisition_channel: "Affiliate" },
        include_pdf: false,
      });
      return jsonResponse(withProvenance({
        job_id: "PACK-JOB-1",
        artifact_id: "PACK-ARTIFACT-1",
        status: "completed",
        reused: false,
        stage: "completed",
        last_completed_stage: "registering_manifest",
        filename: "nAIM_Executive_Portfolio_Review_2025_12.pptx",
        format: "pptx",
        slide_count: 14,
        file_sha256: "a".repeat(64),
        size_bytes: 123456,
        scope: { reporting_period: "2025-12-31" },
        data_mode: "OFFLINE_SNAPSHOT",
        evidence_id: "EVID-PACK-1",
        metric_registry_version: "registry-v1",
        synthetic_statement: "Synthetic data.",
        refreshed_at: "2026-08-11T00:00:00Z",
        validation: { status: "PASS" },
        reconciliation: { status: "PASS" },
        download_url: "/api/v1/executive-packs/PACK-JOB-1/download?download_token=token",
        manifest_url: "/api/v1/executive-packs/PACK-JOB-1/manifest?download_token=token",
      }, "OFFLINE_SNAPSHOT"), "OFFLINE_SNAPSHOT");
    }
    assert.equal(endpoint, "executive-packs/PACK-JOB-1");
    assert.equal(init.method, "GET");
    return jsonResponse(withProvenance({
      job_id: "PACK-JOB-1",
      artifact_id: "PACK-ARTIFACT-1",
      status: "completed",
      stage: "completed",
      last_completed_stage: "registering_manifest",
      filename: "nAIM_Executive_Portfolio_Review_2025_12.pptx",
      format: "pptx",
      slide_count: 14,
      data_mode: "OFFLINE_SNAPSHOT",
      validation: { status: "PASS" },
      reconciliation: { status: "PASS" },
    }, "OFFLINE_SNAPSHOT"), "OFFLINE_SNAPSHOT");
  };

  const pack = await contract.generateExecutivePack(
    {
      workspaceId: "WS-APPROVED",
      reportingPeriod: "2025-12-31",
      comparisonPeriod: "2025-11-30",
      filterScope: { acquisition_channel: "Affiliate" },
    },
    "OFFLINE_SNAPSHOT",
  );
  assert.deepEqual(endpoints, [
    "executive-packs/generate",
    "executive-packs/PACK-JOB-1",
  ]);
  assert.equal(pack.status, "completed");
  assert.equal(pack.format, "pptx");
  assert.equal(pack.slideCount, 14);
  assert.match(pack.downloadUrl, /PACK-JOB-1\/download/);
  assert.match(pack.manifestUrl, /PACK-JOB-1\/manifest/);
  assert.doesNotMatch(JSON.stringify(pack), /pdf/i);
});
