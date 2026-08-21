"use client";

import { useEffect, useMemo, useState } from "react";
import {
  approveOnboardingProfile,
  createOnboardingProfile,
  loadOnboardingContracts,
  OnboardingClientError,
  previewOnboardingSource,
  runOnboardingProfile,
  uploadOnboardingSource,
  validateOnboardingSource,
} from "../data/onboarding-client";
import type {
  OnboardingContract,
  OnboardingPreview,
  OnboardingProfile,
  OnboardingRun,
  OnboardingSourceDescriptor,
  OnboardingValidation,
} from "../data/onboarding-client";
import type { ViewKey, WorkbenchData } from "../workbench-types";
import { StatusChip, TableShell } from "./ui";

type OnboardingPhase =
  | "idle"
  | "loading_contracts"
  | "uploading_source"
  | "previewing_source"
  | "ready_to_map"
  | "validating_source"
  | "validated"
  | "creating_governed_namespace"
  | "namespace_created"
  | "approving_profile"
  | "approved"
  | "error";

const GUIDE_STEPS = [
  "Choose local data",
  "Preview",
  "Select data contract",
  "Map fields",
  "Validate",
  "Review issues",
  "Create governed snapshot",
  "Select analysis",
  "Run",
  "Review evidence",
  "Export",
];

const ANALYSIS_OPTIONS: Array<{ value: ViewKey; label: string; detail: string }> = [
  { value: "executive", label: "Command Centre", detail: "Review governed KPI movement" },
  { value: "root-cause", label: "Root Cause", detail: "Decompose a validated rate movement" },
  { value: "vintage", label: "Vintage Explorer", detail: "Compare cohorts at common maturity" },
  { value: "strategy", label: "Strategy Impact", detail: "Compare strategy outcomes and guardrails" },
  { value: "forecast", label: "Scenario", detail: "Review versioned planning assumptions" },
];

function phaseStep(
  phase: OnboardingPhase,
  validation: OnboardingValidation | null,
  run: OnboardingRun | null,
): number {
  if (run) return 8;
  if (phase === "creating_governed_namespace") return 7;
  if (validation) return validation.validation.passed ? 7 : 6;
  if (phase === "validating_source") return 5;
  if (phase === "ready_to_map") return 4;
  if (phase === "previewing_source") return 2;
  return 1;
}

function stageLabel(phase: OnboardingPhase): string {
  return phase.replaceAll("_", " ");
}

function objectFacts(value: Record<string, unknown> | undefined): Array<[string, string]> {
  if (!value) return [];
  return Object.entries(value).map(([key, item]) => [
    key.replaceAll("_", " "),
    typeof item === "string" ? item : JSON.stringify(item),
  ]);
}

function normalizedProfileId(filename: string): string {
  const stem = filename.replace(/\.[^.]+$/, "").replace(/[^A-Za-z0-9._-]+/g, "-").slice(0, 34);
  return `local-${stem || "portfolio"}-${Date.now().toString(36)}`.slice(0, 64);
}

function bestContract(
  contracts: OnboardingContract[],
  preview: OnboardingPreview,
): OnboardingContract | undefined {
  return [...contracts].sort((left, right) => {
    const leftCount = Object.keys(preview.suggested_mappings[left.contract_id] ?? {}).length;
    const rightCount = Object.keys(preview.suggested_mappings[right.contract_id] ?? {}).length;
    return rightCount - leftCount;
  })[0];
}

export function DataOnboardingPage({
  data,
  onNavigate,
}: {
  data: WorkbenchData;
  onNavigate: (view: ViewKey) => void;
}) {
  const [phase, setPhase] = useState<OnboardingPhase>("loading_contracts");
  const [contracts, setContracts] = useState<OnboardingContract[]>([]);
  const [source, setSource] = useState<OnboardingSourceDescriptor | null>(null);
  const [preview, setPreview] = useState<OnboardingPreview | null>(null);
  const [contractId, setContractId] = useState("");
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [validation, setValidation] = useState<OnboardingValidation | null>(null);
  const [profile, setProfile] = useState<OnboardingProfile | null>(null);
  const [run, setRun] = useState<OnboardingRun | null>(null);
  const [selectedAnalysis, setSelectedAnalysis] = useState<ViewKey>("executive");
  const [approvalRationale, setApprovalRationale] = useState(
    "Validated local source and balanced onboarding reconciliation reviewed for governed reuse.",
  );
  const [error, setError] = useState<OnboardingClientError | null>(null);

  useEffect(() => {
    let active = true;
    void loadOnboardingContracts()
      .then((rows) => {
        if (!active) return;
        setContracts(rows);
        setContractId(rows[0]?.contract_id ?? "");
        setPhase("idle");
      })
      .catch((reason: unknown) => {
        if (!active) return;
        setError(
          reason instanceof OnboardingClientError
            ? reason
            : new OnboardingClientError("The governed contract registry could not be loaded.", "loading_contracts", "not-returned"),
        );
        setPhase("error");
      });
    return () => { active = false; };
  }, []);

  const contract = useMemo(
    () => contracts.find((item) => item.contract_id === contractId),
    [contractId, contracts],
  );
  const requiredMapped = useMemo(
    () => contract?.fields.filter((field) => field.required).every((field) => Boolean(mapping[field.name])) ?? false,
    [contract, mapping],
  );
  const activeStep = phaseStep(phase, validation, run);
  const busy = [
    "loading_contracts",
    "uploading_source",
    "previewing_source",
    "validating_source",
    "creating_governed_namespace",
    "approving_profile",
  ].includes(phase);

  const resetAfterSource = () => {
    setPreview(null);
    setValidation(null);
    setProfile(null);
    setRun(null);
    setMapping({});
  };

  const chooseFile = async (file: File | undefined) => {
    if (!file || busy) return;
    resetAfterSource();
    setError(null);
    setPhase("uploading_source");
    try {
      const uploaded = await uploadOnboardingSource(file);
      setSource(uploaded);
      setPhase("previewing_source");
      const inspected = await previewOnboardingSource(uploaded);
      setPreview(inspected);
      const selected = bestContract(contracts, inspected) ?? contracts[0];
      if (selected) {
        setContractId(selected.contract_id);
        setMapping(inspected.suggested_mappings[selected.contract_id] ?? {});
      }
      setPhase("ready_to_map");
    } catch (reason) {
      setError(
        reason instanceof OnboardingClientError
          ? reason
          : new OnboardingClientError("The local source could not be uploaded and previewed.", "previewing_source", "not-returned"),
      );
      setPhase("error");
    }
  };

  const selectContract = (nextContractId: string) => {
    setContractId(nextContractId);
    setMapping(preview?.suggested_mappings[nextContractId] ?? {});
    setValidation(null);
    setProfile(null);
    setRun(null);
    setPhase("ready_to_map");
  };

  const validate = async () => {
    if (!source || !contract || !requiredMapped || busy) return;
    setError(null);
    setPhase("validating_source");
    try {
      const result = await validateOnboardingSource(source, contract.contract_id, mapping);
      setValidation(result);
      setPhase("validated");
    } catch (reason) {
      setError(
        reason instanceof OnboardingClientError
          ? reason
          : new OnboardingClientError("The source could not be validated.", "validating_source", "not-returned"),
      );
      setPhase("error");
    }
  };

  const createNamespace = async () => {
    if (!source || !contract || !validation?.validation.passed || busy) return;
    setError(null);
    setPhase("creating_governed_namespace");
    try {
      const created = await createOnboardingProfile(
        normalizedProfileId(source.display_name),
        source,
        contract.contract_id,
        mapping,
      );
      setProfile(created);
      const result = await runOnboardingProfile(created.profile_id, source, created.version);
      setRun(result);
      setProfile((current) => current ? { ...current, version: result.profile_version } : current);
      setPhase("namespace_created");
    } catch (reason) {
      setError(
        reason instanceof OnboardingClientError
          ? reason
          : new OnboardingClientError("The governed onboarding namespace could not be created.", "creating_governed_namespace", "not-returned"),
      );
      setPhase("error");
    }
  };

  const approve = async () => {
    if (!profile || !run || !approvalRationale.trim() || busy) return;
    setError(null);
    setPhase("approving_profile");
    try {
      const approved = await approveOnboardingProfile(
        profile.profile_id,
        run.profile_version,
        approvalRationale.trim(),
      );
      setProfile(approved);
      setPhase("approved");
    } catch (reason) {
      setError(
        reason instanceof OnboardingClientError
          ? reason
          : new OnboardingClientError("The import profile could not be approved.", "approving_profile", "not-returned"),
      );
      setPhase("error");
    }
  };

  return (
    <div className="onboarding-experience">
      <header className="experience-page-header onboarding-header">
        <div>
          <div className="eyebrow">Governed local data onboarding</div>
          <h1>Use Your Own Local Data</h1>
          <p>
            Preview a bounded local file, map it to a canonical contract,
            validate every row and create a quarantine-isolated governed
            namespace. The active workbench source never changes silently.
          </p>
        </div>
        <div className="experience-status">
          <small>Current workbench source</small>
          <StatusChip status={data.metadata.dataMode} compact />
          <strong>{data.metadata.sourceContext.reason ?? "Current source remains unchanged during onboarding"}</strong>
        </div>
      </header>

      <section className="source-kind-grid" aria-label="Data source distinctions">
        {[
          ["Prepared Sample", "Built-in deterministic data for guided questions", "DEMO"],
          ["Uploaded Local Data", "A file selected in this browser and copied to the governed onboarding namespace", source ? "SELECTED" : "NOT SELECTED"],
          ["Offline Snapshot", "A verified persisted API snapshot with dataset/configuration binding", data.metadata.dataMode === "OFFLINE_SNAPSHOT" ? "ACTIVE" : "NOT ACTIVE"],
          ["Repository Data", "Versioned source/config assets used by controlled pipeline runs", "CONTROLLED"],
        ].map(([title, detail, status]) => (
          <article key={title} className={title === "Uploaded Local Data" ? "is-primary" : ""}>
            <span>{status}</span><strong>{title}</strong><p>{detail}</p>
          </article>
        ))}
      </section>

      <ol className="onboarding-stepper" aria-label="Local data onboarding steps">
        {GUIDE_STEPS.map((step, index) => {
          const number = index + 1;
          return (
            <li className={number < activeStep ? "is-complete" : number === activeStep ? "is-active" : ""} key={step}>
              <span>{number < activeStep ? "✓" : number}</span><strong>{step}</strong>
            </li>
          );
        })}
      </ol>

      {busy ? (
        <section className="onboarding-progress" role="status" aria-live="polite">
          <div><span className="loading-orbit" aria-hidden="true" /><div><strong>Preparing analysis</strong><p>{stageLabel(phase)}</p></div></div>
          <ul>
            <li className={source ? "is-done" : "is-current"}>{source ? "✓" : "●"} Validated file boundary</li>
            <li className={preview ? "is-done" : source ? "is-current" : ""}>{preview ? "✓" : source ? "●" : "○"} Inspected source schema</li>
            <li className={validation?.validation.passed ? "is-done" : phase === "validating_source" ? "is-current" : ""}>{validation?.validation.passed ? "✓" : phase === "validating_source" ? "●" : "○"} Applied canonical contract</li>
            <li className={run ? "is-done" : phase === "creating_governed_namespace" ? "is-current" : ""}>{run ? "✓" : phase === "creating_governed_namespace" ? "●" : "○"} Built evidence and reconciliation</li>
          </ul>
        </section>
      ) : null}

      {error ? (
        <section className="onboarding-error" role="alert">
          <div><span aria-hidden="true">!</span><div><strong>What failed</strong><p>{error.stage.replaceAll("_", " ")}: {error.message}</p></div></div>
          <dl>
            <div><dt>Existing data safety</dt><dd>The active workbench source and prior validated results remain unchanged.</dd></div>
            <div><dt>What you can do</dt><dd>Correct the file, mapping or approval input, then retry only this onboarding stage.</dd></div>
            <div><dt>Request ID</dt><dd><code>{error.requestId}</code></dd></div>
          </dl>
          <button type="button" onClick={() => { setError(null); setPhase(preview ? "ready_to_map" : "idle"); }}>Return to safe state</button>
        </section>
      ) : null}

      <section className="onboarding-workspace">
        <header><div className="eyebrow">Steps 1–2</div><h2>Choose and preview local data</h2><p>CSV, XLSX, Parquet, JSON, SQLite and DuckDB files are accepted up to 50 MB. Source bytes are validated server-side.</p></header>
        <div className="file-drop-zone">
          <input
            type="file"
            id="local-data-file"
            accept=".csv,.xlsx,.parquet,.json,.sqlite,.db,.duckdb"
            disabled={busy}
            onChange={(event) => void chooseFile(event.target.files?.[0])}
          />
          <label htmlFor="local-data-file">
            <span aria-hidden="true">⇧</span>
            <strong>{source ? "Choose a different local file" : "Choose local data"}</strong>
            <small>The browser sends only the selected file to the localhost onboarding service.</small>
          </label>
          {source ? (
            <dl className="selected-source-facts">
              <div><dt>File</dt><dd>{source.display_name}</dd></div>
              <div><dt>Type</dt><dd>{source.kind.toUpperCase()}</dd></div>
              <div><dt>Size</dt><dd>{(source.size_bytes ?? 0).toLocaleString()} bytes</dd></div>
              <div><dt>SHA-256</dt><dd><code>{source.sha256 ?? "Not returned"}</code></dd></div>
            </dl>
          ) : null}
        </div>
        {preview ? (
          <div className="onboarding-preview">
            <div className="preview-summary">
              <span><small>Sample rows</small><strong>{preview.sample_row_count}</strong></span>
              <span><small>Columns</small><strong>{preview.columns.length}</strong></span>
              <span><small>Preview limit</small><strong>{preview.sample_limit}</strong></span>
            </div>
            <TableShell label="Uploaded local data preview">
              <table className="data-table compact-preview-table">
                <thead><tr>{preview.columns.slice(0, 8).map((column) => <th key={column.name}>{column.name}<small>{column.inferred_type}</small></th>)}</tr></thead>
                <tbody>
                  {preview.rows.slice(0, 8).map((row, rowIndex) => (
                    <tr key={rowIndex}>{preview.columns.slice(0, 8).map((column) => <td key={column.name}>{String(row[column.name] ?? "")}</td>)}</tr>
                  ))}
                </tbody>
              </table>
            </TableShell>
          </div>
        ) : null}
      </section>

      {preview ? (
        <section className="onboarding-workspace">
          <header><div className="eyebrow">Steps 3–6</div><h2>Select a contract, map fields and validate</h2><p>Required target fields must be mapped to real source columns. Suggested exact-name mappings remain editable.</p></header>
          <label className="onboarding-contract-select">
            <span>Canonical data contract</span>
            <select value={contractId} onChange={(event) => selectContract(event.target.value)}>
              {contracts.map((item) => <option value={item.contract_id} key={item.contract_id}>{item.contract_id} · v{item.version}</option>)}
            </select>
            <small>{contract?.description}</small>
          </label>
          {contract ? (
            <div className="mapping-table-wrap">
              <table className="mapping-table">
                <thead><tr><th>Canonical field</th><th>Requirement</th><th>Type</th><th>Source column</th></tr></thead>
                <tbody>
                  {contract.fields.map((field) => (
                    <tr key={field.name} className={field.required && !mapping[field.name] ? "is-missing" : ""}>
                      <th scope="row">{field.name}<small>{field.description}</small></th>
                      <td>{field.required ? "Required" : "Optional"}</td>
                      <td>{field.data_type}{field.non_negative ? " · non-negative" : ""}</td>
                      <td>
                        <select
                          aria-label={`Map ${field.name}`}
                          value={mapping[field.name] ?? ""}
                          onChange={(event) => setMapping((current) => {
                            const next = { ...current };
                            if (event.target.value) next[field.name] = event.target.value;
                            else delete next[field.name];
                            return next;
                          })}
                        >
                          <option value="">Not mapped</option>
                          {preview.columns.map((column) => <option value={column.name} key={column.name}>{column.name} · {column.inferred_type}</option>)}
                        </select>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
          <div className="onboarding-actions">
            <button type="button" className="primary-button" disabled={!requiredMapped || busy} onClick={() => void validate()}>
              Validate mapped source
            </button>
            <span>{requiredMapped ? `${Object.keys(mapping).length} fields mapped` : "Map every required field to continue"}</span>
          </div>
          {validation ? (
            <div className={`validation-result ${validation.validation.passed ? "is-pass" : "is-fail"}`}>
              <header><StatusChip status={validation.validation.passed ? "PASS" : "FAIL"} compact /><div><strong>{validation.validation.passed ? "Source validation passed" : "Source validation failed"}</strong><p>Review row counts and issues before creating any governed namespace.</p></div></header>
              <dl>
                <div><dt>Source rows</dt><dd>{validation.validation.source_rows.toLocaleString()}</dd></div>
                <div><dt>Valid rows</dt><dd>{validation.validation.valid_rows.toLocaleString()}</dd></div>
                <div><dt>Invalid rows</dt><dd>{validation.validation.invalid_rows.toLocaleString()}</dd></div>
                <div><dt>Error rate</dt><dd>{(validation.validation.error_rate * 100).toFixed(3)}%</dd></div>
              </dl>
              {validation.error_preview.length > 0 ? <details><summary>Review validation issues ({validation.validation.validation_error_count})</summary><pre>{JSON.stringify(validation.error_preview, null, 2)}</pre></details> : <p className="no-validation-issues">✓ No validation issues were returned.</p>}
            </div>
          ) : null}
        </section>
      ) : null}

      {validation?.validation.passed ? (
        <section className="onboarding-workspace">
          <header><div className="eyebrow">Step 7</div><h2>Create a governed onboarding snapshot</h2><p>This writes only to a quarantine-isolated onboarding namespace and records row-balance reconciliation. It does not silently replace the active workbench source.</p></header>
          <button type="button" className="primary-button" disabled={busy || Boolean(run)} onClick={() => void createNamespace()}>
            {run ? "Governed namespace created" : "Create governed snapshot"}
          </button>
          {run ? (
            <div className="namespace-result">
              <header><StatusChip status={run.reconciliation.balanced ? "PASS" : "FAIL"} compact /><div><strong>Onboarding run {run.run_id}</strong><p>{run.loaded_to_active_analytics ? "The service reports activation into analytics." : "Not loaded into active analytics; controlled promotion remains separate."}</p></div></header>
              <dl>
                <div><dt>Source rows</dt><dd>{run.reconciliation.source_rows.toLocaleString()}</dd></div>
                <div><dt>Loaded rows</dt><dd>{run.reconciliation.loaded_rows.toLocaleString()}</dd></div>
                <div><dt>Quarantined</dt><dd>{run.reconciliation.quarantined_rows.toLocaleString()}</dd></div>
                <div><dt>Row balance</dt><dd>{run.reconciliation.row_balance_delta}</dd></div>
              </dl>
              <details><summary>Outputs and hashes</summary><dl>{objectFacts(run.outputs).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}{objectFacts(run.output_hashes).map(([key, value]) => <div key={`hash-${key}`}><dt>{key} hash</dt><dd><code>{value}</code></dd></div>)}</dl></details>
              {profile?.approval_state !== "APPROVED" ? (
                <div className="profile-approval">
                  <label><span>Approval rationale</span><textarea value={approvalRationale} onChange={(event) => setApprovalRationale(event.target.value)} /></label>
                  <button type="button" disabled={busy || !approvalRationale.trim()} onClick={() => void approve()}>Approve reusable import profile</button>
                  <small>Approval is permission-controlled and still does not switch the active analytical snapshot automatically.</small>
                </div>
              ) : <p className="profile-approved">✓ Import profile approved for governed reuse.</p>}
            </div>
          ) : null}
        </section>
      ) : null}

      {run ? (
        <section className="onboarding-workspace analysis-handoff">
          <header><div className="eyebrow">Steps 8–11</div><h2>Select the next governed analysis</h2><p>The current workbench will continue to show its declared active source. Promote a new analytical snapshot through the controlled pipeline before treating uploaded rows as analysis input.</p></header>
          <div className="analysis-choice-grid">
            {ANALYSIS_OPTIONS.map((item) => (
              <button type="button" className={selectedAnalysis === item.value ? "is-selected" : ""} aria-pressed={selectedAnalysis === item.value} onClick={() => setSelectedAnalysis(item.value)} key={item.value}>
                <strong>{item.label}</strong><span>{item.detail}</span>
              </button>
            ))}
          </div>
          <div className="analysis-handoff-actions">
            <button type="button" className="primary-button" onClick={() => onNavigate(selectedAnalysis)}>Open selected analysis</button>
            <button type="button" className="secondary-button" onClick={() => onNavigate("data-quality")}>Review evidence and lineage</button>
            <button type="button" className="secondary-button" onClick={() => onNavigate("exports")}>Open Download Centre</button>
          </div>
        </section>
      ) : null}
    </div>
  );
}
