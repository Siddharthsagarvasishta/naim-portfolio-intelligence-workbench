import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { after, before, test } from "node:test";
import { build } from "vite";

let outputDirectory;
let client;
let lifecycle;
let p0;
let originalFetch;

before(async () => {
  outputDirectory = await mkdtemp(join(tmpdir(), "naim-p2-alerts-"));
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
  [client, lifecycle, p0] = await Promise.all([
    compile("client", "../app/data/api-client.ts", {
      "process.env.NEXT_PUBLIC_NAIM_API_URL": JSON.stringify("http://api.test"),
      "process.env.NEXT_PUBLIC_NAIM_DATA_MODE": "undefined",
    }),
    compile("lifecycle", "../app/data/alert-lifecycle.ts"),
    compile("p0", "../app/data/p0-contract.ts"),
  ]);
  originalFetch = globalThis.fetch;
});

after(async () => {
  globalThis.fetch = originalFetch;
  if (outputDirectory) await rm(outputDirectory, { recursive: true, force: true });
});

function sourceContext(mode = "LIVE") {
  return {
    active_mode: mode,
    configured_mode: mode,
    snapshot_date: null,
    configuration_hash: "CONFIG-P2",
    dataset_hash: "DATASET-P2",
    dataset_hash_basis: "governed-alert-evaluation",
    run_id: "RUN-P2",
    synthetic: false,
    reason: null,
  };
}

function withProvenance(payload, mode = "LIVE") {
  return {
    ...payload,
    data_mode: mode,
    source_context: sourceContext(mode),
  };
}

function auditEvent(overrides = {}) {
  return {
    event_type: "ALERT_CREATED",
    actor: "alert.engine",
    occurred_at: "2026-08-11T12:00:00+00:00",
    payload: { period: "2025-12-31", observation_key: "OBS-1" },
    previous_hash: null,
    event_hash: "EVENT-HASH-1",
    ...overrides,
  };
}

function durableAlert(overrides = {}) {
  return {
    alert_id: "ALERT-LOSS-AFFILIATE",
    alert_fingerprint: "FINGERPRINT-LOSS-AFFILIATE",
    alert_rule_id: "LOSS_MOVEMENT",
    alert_rule_name: "Loss movement guardrail",
    alert_name: "Loss rate increased materially",
    rule_version: "2.1.0",
    metric_id: "ANNUALISED_NET_LOSS_RATE",
    severity: "Adverse",
    owner: "Portfolio Risk Analytics",
    status: "NEW",
    acknowledgement: {
      acknowledged: false,
      by: null,
      at: null,
      note: null,
    },
    sla: { hours: 24, due_at: "2026-08-12T12:00:00+00:00" },
    recurrence_count: 0,
    first_observed_at: "2026-08-11T12:00:00+00:00",
    first_observed_period: "2025-12-31",
    last_observed_at: "2026-08-11T12:00:00+00:00",
    last_observed_period: "2025-12-31",
    last_observation_key: "OBS-1",
    cooldown: { periods: 1, until_period: null },
    suppression: {
      active: false,
      reason: null,
      by: null,
      at: null,
      until_period: null,
    },
    resolution: { reason: null, by: null, at: null },
    reopen_history: [],
    latest_evidence: {
      run_id: "RUN-P2",
      configuration_hash: "CONFIG-P2",
      dataset_hash: "DATASET-P2",
      period: "2025-12-31",
      comparison_period: "2025-11-30",
      data_quality_status: "PASS_WITH_WARNINGS",
      current_value: 0.0428,
      baseline_value: 0.0385,
      absolute_movement: 0.0043,
      relative_movement: 0.1117,
      denominator: 428600000,
      observation_key: "OBS-1",
    },
    related_investigation: null,
    version: 1,
    audit_integrity: {
      status: "PASS",
      chain_valid: true,
      event_count: 1,
      head_hash: "EVENT-HASH-1",
    },
    audit_events: [auditEvent()],
    allowed_transitions: [
      "ACKNOWLEDGED",
      "INVESTIGATING",
      "RESOLVED",
      "SUPPRESSED",
      "CLOSED_AS_NOISE",
    ],
    can_acknowledge: true,
    condition_active: true,
    workflow_active: true,
    current_value: 0.0428,
    baseline_value: 0.0385,
    threshold: 20,
    segment: "Affiliate",
    recommended_investigation: "Review governed loss decomposition.",
    noise_controls: { minimum_denominator: 100 },
    ...overrides,
  };
}

function refreshedAlert(overrides = {}) {
  const secondEvent = auditEvent({
    event_type: "ALERT_ACKNOWLEDGED",
    actor: "portfolio.analyst",
    occurred_at: "2026-08-11T12:15:00+00:00",
    payload: { note: "Evidence reviewed" },
    previous_hash: "EVENT-HASH-1",
    event_hash: "EVENT-HASH-2",
  });
  return durableAlert({
    status: "ACKNOWLEDGED",
    acknowledgement: {
      acknowledged: true,
      by: "portfolio.analyst",
      at: "2026-08-11T12:15:00+00:00",
      note: "Evidence reviewed",
    },
    version: 2,
    audit_integrity: {
      status: "PASS",
      chain_valid: true,
      event_count: 2,
      head_hash: "EVENT-HASH-2",
    },
    audit_events: [auditEvent(), secondEvent],
    allowed_transitions: [
      "INVESTIGATING",
      "ACTION_PROPOSED",
      "MONITORING",
      "RESOLVED",
      "SUPPRESSED",
      "CLOSED_AS_NOISE",
    ],
    can_acknowledge: false,
    ...overrides,
  });
}

function response(payload, status = 200, mode = "LIVE") {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "content-type": "application/json",
      "X-nAIM-Data-Mode": mode,
      "X-Request-ID": "REQ-P2",
    },
  });
}

function endpointFrom(input) {
  return new URL(typeof input === "string" ? input : input.url).pathname
    .replace(/^\/api\/v1\//, "");
}

test("strict durable alert normalization preserves governed severity and server activity facts", () => {
  const adverse = client.normalizeDurableAlertPayload(durableAlert());
  const watch = client.normalizeDurableAlertPayload(
    durableAlert({ alert_id: "ALERT-WATCH", severity: "Watch" }),
  );
  assert.equal(adverse.severity, "Adverse");
  assert.equal(adverse.lifecycle.recurrenceCount, 0);
  assert.equal(adverse.lifecycle.workflowActive, true);
  assert.equal(adverse.lifecycle.conditionActive, true);
  assert.deepEqual(adverse.lifecycle.allowedTransitions, [
    "ACKNOWLEDGED",
    "INVESTIGATING",
    "RESOLVED",
    "SUPPRESSED",
    "CLOSED_AS_NOISE",
  ]);
  assert.equal(client.normalizeDurableAlertPayload(durableAlert({ severity: "High" })), null);
  assert.equal(
    p0.earlyWarningHeadline([
      watch,
      client.normalizeDurableAlertPayload(
        durableAlert({ alert_id: "ALERT-WATCH-2", severity: "Watch" }),
      ),
    ]),
    "0 Adverse | 2 Watch",
  );
  assert.equal(p0.earlyWarningHeadline([adverse, watch]), "1 Adverse | 1 Watch");
});

test("normalization fails closed on malformed lifecycle or audit facts and accepts condition-cleared audit", () => {
  assert.equal(
    client.normalizeDurableAlertPayload(durableAlert({ audit_integrity: undefined })),
    null,
  );
  assert.equal(
    client.normalizeDurableAlertPayload(
      durableAlert({ allowed_transitions: ["INVESTIGATING", "REOPENED"] }),
    ),
    null,
  );
  assert.equal(
    client.normalizeDurableAlertPayload(durableAlert({ workflow_active: "true" })),
    null,
  );
  const conditionCleared = client.normalizeDurableAlertPayload(
    durableAlert({
      condition_active: false,
      audit_events: [
        auditEvent({ event_type: "ALERT_CONDITION_CLEARED" }),
      ],
    }),
  );
  assert.equal(conditionCleared.lifecycle.auditEvents[0].eventType, "ALERT_CONDITION_CLEARED");
  assert.equal(conditionCleared.lifecycle.conditionActive, false);
});

test("active queue and retained history use server workflow_active without local status inference", () => {
  const active = client.normalizeDurableAlertPayload(durableAlert());
  const history = client.normalizeDurableAlertPayload(
    durableAlert({
      alert_id: "ALERT-RESOLVED",
      status: "RESOLVED",
      workflow_active: false,
      condition_active: false,
      allowed_transitions: [],
      can_acknowledge: false,
    }),
  );
  assert.deepEqual(lifecycle.activeAlertQueue([active, history]).map((row) => row.id), [
    "ALERT-LOSS-AFFILIATE",
  ]);
  assert.deepEqual(lifecycle.alertHistory([active, history]).map((row) => row.id), [
    "ALERT-RESOLVED",
  ]);
});

test("mutation reducer clears prior errors and never promotes a failed or stale response", () => {
  const failed = lifecycle.alertMutationReducer(
    { phase: "idle" },
    {
      type: "failed",
      alertId: "ALERT-LOSS-AFFILIATE",
      mutation: "RESOLVED",
      message: "Conflict",
    },
  );
  const retrying = lifecycle.alertMutationReducer(failed, {
    type: "begin",
    alertId: "ALERT-LOSS-AFFILIATE",
    mutation: "RESOLVED",
    expectedVersion: 1,
  });
  assert.deepEqual(retrying, {
    phase: "pending",
    alertId: "ALERT-LOSS-AFFILIATE",
    mutation: "RESOLVED",
    expectedVersion: 1,
  });
  const current = [client.normalizeDurableAlertPayload(durableAlert())];
  assert.throws(
    () => lifecycle.replaceWithRefreshedAlert(current, current[0], 1),
    /newer durable alert version/,
  );
  assert.equal(current[0].lifecycle.version, 1);
  const refreshed = client.normalizeDurableAlertPayload(refreshedAlert());
  const replaced = lifecycle.replaceWithRefreshedAlert(current, refreshed, 1);
  assert.equal(replaced[0].lifecycle.version, 2);
});

test("acknowledge and transition clients send exact governed bodies and require a refreshed version", async () => {
  const calls = [];
  globalThis.fetch = async (input, init = {}) => {
    calls.push({ endpoint: endpointFrom(input), init });
    if (endpointFrom(input).endsWith("/acknowledge")) {
      return response(withProvenance(refreshedAlert()));
    }
    return response(
      withProvenance(
        refreshedAlert({
          status: "INVESTIGATING",
          allowed_transitions: [
            "ACTION_PROPOSED",
            "MONITORING",
            "RESOLVED",
            "SUPPRESSED",
            "CLOSED_AS_NOISE",
          ],
        }),
      ),
    );
  };
  const acknowledged = await client.acknowledgeDurableAlert(
    "ALERT-LOSS-AFFILIATE",
    1,
    "  Evidence reviewed  ",
    "LIVE",
  );
  assert.equal(acknowledged.lifecycle.version, 2);
  assert.equal(calls[0].endpoint, "alerts/ALERT-LOSS-AFFILIATE/acknowledge");
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    expected_version: 1,
    note: "Evidence reviewed",
  });

  const transitioned = await client.transitionDurableAlert(
    "ALERT-LOSS-AFFILIATE",
    {
      expectedVersion: 1,
      targetStatus: "INVESTIGATING",
      reason: "  Driver review opened  ",
      owner: "Portfolio Risk Analytics",
      relatedInvestigation: "INV-101",
    },
    "LIVE",
  );
  assert.equal(transitioned.lifecycle.status, "INVESTIGATING");
  assert.equal(calls[1].endpoint, "alerts/ALERT-LOSS-AFFILIATE/transition");
  assert.deepEqual(JSON.parse(calls[1].init.body), {
    expected_version: 1,
    target_status: "INVESTIGATING",
    reason: "Driver review opened",
    owner: "Portfolio Risk Analytics",
    related_investigation: "INV-101",
  });

  globalThis.fetch = async () => response(withProvenance(durableAlert()));
  await assert.rejects(
    client.acknowledgeDurableAlert(
      "ALERT-LOSS-AFFILIATE",
      1,
      "Evidence reviewed",
      "LIVE",
    ),
    /did not advance version 1/,
  );
});

test("Start Investigation uses one idempotent governed alert endpoint and returns the persisted link", async () => {
  const calls = [];
  const linked = refreshedAlert({
    status: "INVESTIGATING",
    related_investigation: "INV-P2-1",
    allowed_transitions: [
      "ACTION_PROPOSED",
      "MONITORING",
      "RESOLVED",
      "SUPPRESSED",
      "CLOSED_AS_NOISE",
    ],
  });
  globalThis.fetch = async (input, init = {}) => {
    calls.push({ endpoint: endpointFrom(input), init });
    return response(
      withProvenance({
        alert: linked,
        investigation: {
          investigation_id: "INV-P2-1",
          alert_id: "ALERT-LOSS-AFFILIATE",
        },
        reused: false,
      }),
    );
  };
  const result = await client.createAndLinkAlertInvestigation(
    {
      alertId: "ALERT-LOSS-AFFILIATE",
      expectedVersion: 1,
      reason: "  Governed driver review  ",
      owner: "Portfolio Risk Analytics",
    },
    "LIVE",
  );
  assert.equal(result.investigationId, "INV-P2-1");
  assert.equal(result.alert.lifecycle.status, "INVESTIGATING");
  assert.equal(result.alert.lifecycle.relatedInvestigation, "INV-P2-1");
  assert.equal(
    calls[0].endpoint,
    "alerts/ALERT-LOSS-AFFILIATE/investigation",
  );
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    expected_version: 1,
    reason: "Governed driver review",
    owner: "Portfolio Risk Analytics",
  });
});

test("detail and audit clients use locked endpoints and reject failed mutations without promotion", async () => {
  const endpoints = [];
  globalThis.fetch = async (input, init = {}) => {
    const endpoint = endpointFrom(input);
    endpoints.push(endpoint);
    if (init.method === "POST") {
      return response({ detail: "Expected version conflict" }, 409);
    }
    if (endpoint.endsWith("/audit")) {
      return response(
        withProvenance({
          alert_id: "ALERT-LOSS-AFFILIATE",
          fingerprint: "FINGERPRINT-LOSS-AFFILIATE",
          version: 1,
          audit_events: [auditEvent()],
          audit_integrity: {
            status: "PASS",
            chain_valid: true,
            event_count: 1,
            head_hash: "EVENT-HASH-1",
          },
        }),
      );
    }
    return response(withProvenance(durableAlert()));
  };
  const detail = await client.loadDurableAlert("ALERT-LOSS-AFFILIATE", "LIVE");
  const audit = await client.loadDurableAlertAudit("ALERT-LOSS-AFFILIATE", "LIVE");
  assert.equal(detail.id, "ALERT-LOSS-AFFILIATE");
  assert.equal(audit.auditIntegrity.status, "PASS");
  assert.deepEqual(endpoints.slice(0, 2), [
    "alerts/ALERT-LOSS-AFFILIATE",
    "alerts/ALERT-LOSS-AFFILIATE/audit",
  ]);

  const current = detail;
  await assert.rejects(
    client.transitionDurableAlert(
      detail.id,
      { expectedVersion: 1, targetStatus: "RESOLVED", reason: "Reviewed" },
      "LIVE",
    ),
    /Expected version conflict/,
  );
  assert.equal(current.lifecycle.status, "NEW");
  assert.equal(current.lifecycle.version, 1);
});

test("Early Warning source renders only server-authorized actions and labels demo fixtures non-durable", async () => {
  const [pagesSource, clientSource, workbenchSource] = await Promise.all([
    readFile(new URL("../app/components/pages.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/data/api-client.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/workbench.tsx", import.meta.url), "utf8"),
  ]);
  assert.match(pagesSource, /lifecycle\?\.allowedTransitions\.filter/);
  assert.match(pagesSource, /lifecycle\.canAcknowledge/);
  assert.match(pagesSource, /Durable lifecycle controls unavailable/);
  assert.match(pagesSource, /No acknowledgement, transition, audit, or persistence claim is made/);
  assert.match(pagesSource, /The visible durable record was not promoted/);
  assert.match(pagesSource, /Resolved and suppressed history/);
  assert.match(pagesSource, /createAndLinkAlertInvestigation/);
  assert.match(pagesSource, /Investigation .* is linked and the alert is investigating/);
  assert.match(clientSource, /"alerts",/);
  assert.match(clientSource, /rawSeverity === "high"\s*\? "Adverse"/);
  assert.match(clientSource, /alerts\/\$\{encodeURIComponent\(alertId\)\}\/acknowledge/);
  assert.match(clientSource, /expected_version: expectedVersion, note: trimmedNote/);
  assert.match(workbenchSource, /activeAlertQueue\(data\.alerts\)\.length/);
});
