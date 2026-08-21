"use client";

import { useEffect, useMemo, useState } from "react";
import {
  loadAdvancedStatisticsStatus,
  loadMarketRiskStatus,
  runMarketRiskLab,
  type MarketRiskRunRequest,
} from "../data/api-client";
import type {
  AdvancedStatisticsMethod,
  AdvancedStatisticsStatus,
  CapabilityStatus,
  MarketRiskRunResult,
  MarketRiskStatus,
  PageProps,
} from "../workbench-types";
import {
  DataState,
  ModeNote,
  PageHeader,
  Panel,
  SourceFooter,
  StatusChip,
  TableShell,
} from "./ui";

const DEFAULT_RUN: MarketRiskRunRequest = {
  instrument: "NAIM-DEMO-INDEX",
  period: "three_years",
  frequency: "daily",
  returnType: "log",
  confidence: 0.99,
};

function displayName(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function percentage(value: number | null, digits = 1): string {
  return value === null ? "Not returned" : `${(value * 100).toFixed(digits)}%`;
}

function decimal(value: number | null, digits = 4): string {
  return value === null ? "Not returned" : value.toFixed(digits);
}

function statusTone(status: string): string {
  const normalised = status.toLowerCase();
  if (normalised === "pass" || normalised === "green" || normalised === "live") {
    return "Favourable";
  }
  if (normalised.includes("fail") || normalised === "red") return "Critical";
  if (normalised.includes("integration") || normalised === "amber") return "Watch";
  return "Stable";
}

function useMarketRiskStatus(
  initial: MarketRiskStatus | null,
  dataMode: PageProps["data"]["metadata"]["dataMode"],
) {
  const [status, setStatus] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (initial || dataMode === "UNAVAILABLE") return;
    let current = true;
    void loadMarketRiskStatus(dataMode)
      .then((response) => {
        if (current) setStatus(response);
      })
      .catch((reason: unknown) => {
        if (current) {
          setError(
            reason instanceof Error
              ? reason.message
              : "Market-risk status could not be verified.",
          );
        }
      });
    return () => {
      current = false;
    };
  }, [dataMode, initial]);
  return { status, error };
}

function useAdvancedStatus(
  initial: AdvancedStatisticsStatus | null,
  dataMode: PageProps["data"]["metadata"]["dataMode"],
) {
  const [status, setStatus] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (initial || dataMode === "UNAVAILABLE") return;
    let current = true;
    void loadAdvancedStatisticsStatus(dataMode)
      .then((response) => {
        if (current) setStatus(response);
      })
      .catch((reason: unknown) => {
        if (current) {
          setError(
            reason instanceof Error
              ? reason.message
              : "Advanced-statistics status could not be verified.",
          );
        }
      });
    return () => {
      current = false;
    };
  }, [dataMode, initial]);
  return { status, error };
}

function VolatilityTrace({ result }: { result: MarketRiskRunResult }) {
  const points = result.regimes.filter(
    (point): point is typeof point & { volatility: number } =>
      point.volatility !== null,
  );
  if (points.length < 2) {
    return (
      <DataState
        type="empty"
        title="No volatility trace returned"
        detail="The run completed without enough regime observations to draw a trace."
      />
    );
  }
  const width = 760;
  const height = 220;
  const padding = 18;
  const values = points.map((point) => point.volatility);
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const spread = Math.max(maximum - minimum, 0.0001);
  const coordinate = (value: number, index: number) => ({
    x: padding + (index / Math.max(points.length - 1, 1)) * (width - padding * 2),
    y: height - padding - ((value - minimum) / spread) * (height - padding * 2),
  });
  const polyline = points
    .map((point, index) => {
      const location = coordinate(point.volatility, index);
      return `${location.x.toFixed(1)},${location.y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <div className="volatility-trace">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Recent annualised volatility coloured by empirical regime"
      >
        <defs>
          <linearGradient id="riskTraceFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#337894" stopOpacity="0.22" />
            <stop offset="100%" stopColor="#337894" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0.25, 0.5, 0.75].map((position) => (
          <line
            key={position}
            x1={padding}
            x2={width - padding}
            y1={padding + position * (height - padding * 2)}
            y2={padding + position * (height - padding * 2)}
            className="risk-grid-line"
          />
        ))}
        <polygon
          points={`${padding},${height - padding} ${polyline} ${width - padding},${height - padding}`}
          fill="url(#riskTraceFill)"
        />
        <polyline points={polyline} className="risk-trace-line" />
        {points.map((point, index) => {
          if (!point.changePoint && index !== points.length - 1) return null;
          const location = coordinate(point.volatility, index);
          return (
            <circle
              key={`${point.date}-${index}`}
              cx={location.x}
              cy={location.y}
              r={point.changePoint ? 4.5 : 3.5}
              className={point.changePoint ? "risk-change-point" : "risk-last-point"}
            />
          );
        })}
      </svg>
      <div className="risk-trace-axis">
        <span>{points[0]?.date}</span>
        <span>{percentage(maximum)} peak</span>
        <span>{points.at(-1)?.date}</span>
      </div>
    </div>
  );
}

function RunControls({
  request,
  instruments,
  running,
  disabled,
  onChange,
  onRun,
}: {
  request: MarketRiskRunRequest;
  instruments: string[];
  running: boolean;
  disabled: boolean;
  onChange: (request: MarketRiskRunRequest) => void;
  onRun: () => void;
}) {
  return (
    <div className="risk-run-controls">
      <label>
        <span>Instrument</span>
        <select
          value={request.instrument}
          onChange={(event) =>
            onChange({
              ...request,
              instrument: event.target.value as MarketRiskRunRequest["instrument"],
            })
          }
        >
          {(instruments.length > 0
            ? instruments
            : ["NAIM-DEMO-INDEX", "NAIM-DEMO-EQUITY"]
          ).map((instrument) => (
            <option key={instrument} value={instrument}>{instrument}</option>
          ))}
        </select>
      </label>
      <label>
        <span>Evidence period</span>
        <select
          value={request.period}
          onChange={(event) =>
            onChange({
              ...request,
              period: event.target.value as MarketRiskRunRequest["period"],
            })
          }
        >
          <option value="one_year">One year</option>
          <option value="three_years">Three years</option>
          <option value="five_years">Five years</option>
        </select>
      </label>
      <label>
        <span>Frequency</span>
        <select
          value={request.frequency}
          onChange={(event) =>
            onChange({
              ...request,
              frequency: event.target.value as MarketRiskRunRequest["frequency"],
            })
          }
        >
          <option value="daily">Daily</option>
          <option value="weekly">Weekly</option>
          <option value="monthly">Monthly</option>
        </select>
      </label>
      <label>
        <span>Return basis</span>
        <select
          value={request.returnType}
          onChange={(event) =>
            onChange({
              ...request,
              returnType: event.target.value as MarketRiskRunRequest["returnType"],
            })
          }
        >
          <option value="log">Log return</option>
          <option value="simple">Simple return</option>
        </select>
      </label>
      <label>
        <span>Tail confidence</span>
        <select
          value={request.confidence}
          onChange={(event) =>
            onChange({ ...request, confidence: Number(event.target.value) })
          }
        >
          <option value={0.95}>95%</option>
          <option value={0.975}>97.5%</option>
          <option value={0.99}>99%</option>
        </select>
      </label>
      <button
        type="button"
        className="primary-button risk-run-button"
        disabled={disabled || running}
        onClick={onRun}
      >
        <span aria-hidden="true">{running ? "◌" : "▶"}</span>
        {running ? "Running governed models…" : "Run selected analysis"}
      </button>
    </div>
  );
}

export function MarketRiskPage({ data, mode, onNavigate }: PageProps) {
  const { status, error: statusError } = useMarketRiskStatus(
    data.marketRiskStatus,
    data.metadata.dataMode,
  );
  const [request, setRequest] = useState(DEFAULT_RUN);
  const [result, setResult] = useState<MarketRiskRunResult | null>(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const latestRegime = result?.regimes.at(-1)?.regime ?? "Not run";
  const topModel = useMemo(
    () => result?.models.find((model) => model.rank === 1) ?? null,
    [result],
  );

  const run = async () => {
    setRunning(true);
    setRunError(null);
    setResult(null);
    try {
      const response = await runMarketRiskLab(
        request,
        data.metadata.dataMode,
      );
      setResult(response);
    } catch (reason) {
      setRunError(
        reason instanceof Error
          ? reason.message
          : "The selected market-risk analysis could not be completed.",
      );
    } finally {
      setRunning(false);
    }
  };

  return (
    <>
      <PageHeader
        eyebrow="Quantitative decision lab"
        title="Market Risk & Volatility Lab"
        summary="Compare transparent volatility and tail-risk methods on a governed deterministic sample. Results are diagnostics—not a trade signal, investment recommendation or maximum-loss estimate."
        facts={[
          {
            label: "Runtime status",
            value: status?.status ?? "Awaiting verified status",
            status: status ? "Favourable" : "Watch",
          },
          {
            label: "Provider",
            value: status?.providerMode
              ? displayName(status.providerMode)
              : "Not verified",
          },
          { label: "Latest run", value: result?.evidenceId ?? "Not run" },
        ]}
        actions={
          <button
            type="button"
            className="secondary-button"
            onClick={() => onNavigate("advanced-statistics")}
          >
            Advanced statistics status →
          </button>
        }
      />
      <ModeNote mode={mode} />

      <section className="quant-governance-strip" aria-label="Market-risk governance">
        <div className="quant-governance-mark" aria-hidden="true">≋</div>
        <div>
          <strong>
            {data.metadata.dataMode === "OFFLINE_SNAPSHOT"
              ? "Verified offline portfolio context"
              : data.metadata.dataMode === "DEMO"
                ? "Demonstration mode; analysis still requires a verified API response"
                : "Live API control plane with bundled synthetic market prices"}
          </strong>
          <p>
            External data is {status?.externalProvider ?? "not verified"}. The bundled
            provider is deterministic, synthetic and redistribution-permitted; every run
            remains draft and approval-required.
          </p>
        </div>
        <StatusChip status={status?.externalProvider ?? "Not verified"} compact />
      </section>

      <Panel
        eyebrow="Explicit run controls"
        title="Select the evidence basis"
        subtitle="No model runs on page load; changing controls never fabricates a result"
      >
        <RunControls
          request={request}
          instruments={status?.instruments ?? []}
          running={running}
          disabled={!status?.available}
          onChange={setRequest}
          onRun={() => void run()}
        />
        {statusError ? (
          <div className="quant-inline-warning" role="alert">
            <strong>Status unavailable.</strong> {statusError} No demo result was substituted.
          </div>
        ) : null}
      </Panel>

      {running ? (
        <DataState
          type="loading"
          title="Running volatility, diagnostics and tail-risk models"
          detail="The deterministic sample is being transformed, fitted, backtested and validated."
        />
      ) : runError ? (
        <DataState
          type="error"
          title="Market-risk run did not complete"
          detail={`${runError} No prior or demonstration result has been substituted.`}
          action={<button type="button" className="primary-button" onClick={() => void run()}>Retry selected run</button>}
        />
      ) : result ? (
        <>
          <section className="risk-kpi-grid" aria-label="Market-risk result summary">
            {[
              ["Annualised volatility", percentage(result.annualisedVolatility), `${result.observations.toLocaleString()} returns`],
              ["EWMA one-step forecast", percentage(result.ewmaForecast), "λ 0.94"],
              ["Top held-out QLIKE", topModel ? displayName(topModel.model) : "Not returned", topModel ? decimal(topModel.qlike, 3) : "No rank"],
              ["Current regime", displayName(latestRegime), `${result.regimeCounts.length} empirical states`],
              ["VaR backtest", displayName(result.backtest.trafficLight), `${result.backtest.breachCount ?? "Not returned"} breaches`],
              ["Validation", result.validation.status, result.validation.publicationAllowed ? "Publication checks passed" : "Publication blocked"],
            ].map(([label, value, note]) => (
              <article key={label}>
                <span>{label}</span>
                <strong>{value}</strong>
                <small>{note}</small>
              </article>
            ))}
          </section>

          <div className="content-grid cols-8-4">
            <Panel
              eyebrow="Recent volatility path"
              title="Empirical regime trace"
              subtitle="Last 120 eligible observations · annualised rolling volatility"
            >
              <VolatilityTrace result={result} />
            </Panel>
            <Panel
              eyebrow="Regime distribution"
              title="Time spent by state"
              subtitle="Empirical percentile bands; associational scenario input only"
            >
              <div className="regime-count-list">
                {result.regimeCounts.map((item) => {
                  const total = result.regimeCounts.reduce(
                    (sum, candidate) => sum + candidate.observations,
                    0,
                  );
                  const share = total === 0 ? 0 : item.observations / total;
                  return (
                    <div key={item.regime}>
                      <span><i className={`regime-${item.regime}`} />{displayName(item.regime)}</span>
                      <strong>{item.observations.toLocaleString()}</strong>
                      <small>{(share * 100).toFixed(1)}%</small>
                      <em><b style={{ width: `${share * 100}%` }} /></em>
                    </div>
                  );
                })}
              </div>
              <div className="quant-boundary-note">
                A volatility state is not asserted to cause portfolio credit or fraud movement.
              </div>
            </Panel>
          </div>

          <Panel
            eyebrow="Held-out comparison"
            title="Volatility model evidence"
            subtitle="Chronological test tail · ranking is descriptive for this sample, never automatic model selection"
          >
            <TableShell label="Volatility model comparison">
              <table className="data-table quant-model-table">
                <thead>
                  <tr>
                    <th>Model</th>
                    <th>QLIKE rank</th>
                    <th>One-step forecast</th>
                    <th>QLIKE</th>
                    <th>Variance RMSE</th>
                    <th>Persistence</th>
                    <th>Diagnostic</th>
                  </tr>
                </thead>
                <tbody>
                  {result.models
                    .slice()
                    .sort((left, right) => (left.rank ?? 99) - (right.rank ?? 99))
                    .map((model) => (
                      <tr key={model.model}>
                        <th scope="row">{displayName(model.model)}</th>
                        <td>{model.rank ?? "Not ranked"}</td>
                        <td>{percentage(model.oneStepForecast)}</td>
                        <td>{decimal(model.qlike, 4)}</td>
                        <td>{decimal(model.rmseVariance, 6)}</td>
                        <td>{decimal(model.persistence, 3)}</td>
                        <td><StatusChip status={statusTone(model.diagnosticStatus)} compact /> {displayName(model.diagnosticStatus)}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </TableShell>
          </Panel>

          <div className="content-grid cols-7-5">
            <Panel
              eyebrow={`${(request.confidence * 100).toFixed(1)}% tail confidence`}
              title="Value at Risk and Expected Shortfall"
              subtitle="Positive numbers denote loss magnitude for one selected return period"
            >
              <TableShell label="Tail-risk method comparison">
                <table className="data-table">
                  <thead><tr><th>Method</th><th>VaR</th><th>Expected shortfall</th><th>Tail observations</th></tr></thead>
                  <tbody>
                    {result.tailRisk.map((row) => (
                      <tr key={row.method}>
                        <th scope="row">{displayName(row.method)}</th>
                        <td>{percentage(row.valueAtRisk, 2)}</td>
                        <td>{percentage(row.expectedShortfall, 2)}</td>
                        <td>{row.tailObservations ?? "Method-derived"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableShell>
            </Panel>
            <Panel
              eyebrow="Coverage diagnostics"
              title="VaR backtest"
              subtitle="Kupiec coverage and Christoffersen independence evidence"
            >
              <dl className="risk-backtest-list">
                <div><dt>Traffic light</dt><dd><StatusChip status={statusTone(result.backtest.trafficLight)} compact /> {displayName(result.backtest.trafficLight)}</dd></div>
                <div><dt>Observed breach rate</dt><dd>{percentage(result.backtest.observedBreachRate, 2)}</dd></div>
                <div><dt>Kupiec p-value</dt><dd>{decimal(result.backtest.kupiecPValue, 3)}</dd></div>
                <div><dt>Christoffersen p-value</dt><dd>{decimal(result.backtest.christoffersenPValue, 3)}</dd></div>
              </dl>
              <div className="quant-boundary-note">
                VaR is a quantile estimate, not the maximum possible loss. A green analytical traffic light is not a regulatory classification.
              </div>
            </Panel>
          </div>

          <section className="risk-provenance-card" aria-label="Market-risk evidence provenance">
            <div>
              <span>Evidence</span><strong>{result.evidenceId}</strong>
            </div>
            <div>
              <span>Instrument / period</span><strong>{result.source.instrument} · {result.source.requestedStartDate} to {result.source.requestedEndDate}</strong>
            </div>
            <div>
              <span>Source</span><strong>{displayName(result.source.provider)} · synthetic {result.source.synthetic ? "yes" : "no"}</strong>
            </div>
            <div>
              <span>Source hash</span><strong>{result.source.sourceHash}</strong>
            </div>
            <div>
              <span>Price basis</span><strong>{result.source.priceBasis}</strong>
            </div>
            <div>
              <span>Publication gate</span><strong>{result.validation.publicationBasis}</strong>
            </div>
          </section>
        </>
      ) : (
        <DataState
          type="empty"
          title="No market-risk analysis has been run"
          detail="Choose an instrument and evidence basis, then run the governed analysis. The page does not preload, cache or substitute analytical results."
        />
      )}

      <SourceFooter
        source={result ? displayName(result.source.provider) : "status endpoint only; no analytical result yet"}
        denominator={result ? `${result.observations.toLocaleString()} eligible returns` : "Not established until run"}
        period={result ? `${result.source.requestedStartDate} to ${result.source.requestedEndDate}` : "User-selected at run time"}
      />
    </>
  );
}

const UNVERIFIED_SHAP: AdvancedStatisticsMethod = {
  id: "shap",
  name: "SHAP explanations",
  status: "INTEGRATION_ONLY",
};

function governedAdvancedMethods(
  status: AdvancedStatisticsStatus | null,
): AdvancedStatisticsMethod[] {
  if (!status) return [UNVERIFIED_SHAP];
  const methods = status.methods.map((method) =>
    method.id === "shap" && method.status !== "LIVE"
      ? { ...method, status: "INTEGRATION_ONLY" as CapabilityStatus }
      : method,
  );
  if (!methods.some((method) => method.id === "shap")) {
    methods.push(UNVERIFIED_SHAP);
  }
  return methods;
}

export function AdvancedStatisticsPage({ data, mode, onNavigate }: PageProps) {
  const { status, error } = useAdvancedStatus(
    data.advancedStatisticsStatus,
    data.metadata.dataMode,
  );
  const methods = governedAdvancedMethods(status);
  const liveCount = methods.filter((method) => method.status === "LIVE").length;
  const limitedCount = methods.length - liveCount;
  return (
    <>
      <PageHeader
        eyebrow="Advanced analytical methods"
        title="Advanced Statistics Status"
        summary="A compact truth view of executable methods and integration boundaries. Status reflects the live API contract; availability never turns an associational method into causal proof."
        facts={[
          { label: "Status endpoint", value: status?.status ?? "Not verified", status: status ? "Favourable" : "Watch" },
          { label: "Live methods", value: status ? liveCount.toString() : "Not verified" },
          { label: "Limited / planned", value: limitedCount.toString(), status: limitedCount > 0 ? "Watch" : "Stable" },
        ]}
        actions={
          <button type="button" className="secondary-button" onClick={() => onNavigate("market-risk")}>
            Open Market Risk Lab →
          </button>
        }
      />
      <ModeNote mode={mode} />
      {error ? (
        <div className="quant-inline-warning" role="alert">
          <strong>Status unavailable.</strong> {error} Only the conservative SHAP integration boundary is shown; no method was promoted to LIVE.
        </div>
      ) : null}
      <section className="advanced-status-grid" aria-label="Advanced-statistics capability status">
        {methods.map((method) => (
          <article key={method.id}>
            <div>
              <span>{method.id.replaceAll("_", " · ")}</span>
              <StatusChip status={method.status} compact />
            </div>
            <strong>{method.name}</strong>
            <p>
              {method.id === "shap"
                ? method.status === "LIVE"
                  ? "The API explicitly reports executable SHAP evidence for this runtime."
                  : "Optional SHAP execution is not claimed live; governed fallback contributions remain a separate method."
                : method.status === "LIVE"
                  ? "Executable endpoint and method evidence are available for governed analytical use."
                  : method.status === "NOT_IMPLEMENTED"
                    ? "The named method is not implemented in this release."
                    : "The interface or documentation exists, but full runtime evidence is limited."}
            </p>
          </article>
        ))}
      </section>
      <div className="content-grid cols-7-5">
        <Panel
          eyebrow="Interpretation boundary"
          title="What LIVE means here"
          subtitle="Executable and tested does not mean causal or decision-automating"
        >
          <div className="advanced-boundary-list">
            <div><span>01</span><p><strong>Survival</strong> compares time-to-event curves and log-rank evidence; it does not prove why curves differ.</p></div>
            <div><span>02</span><p><strong>Behavioural diagnostics</strong> use time-split prediction and contribution evidence; fallback perturbations are not SHAP values.</p></div>
            <div><span>03</span><p><strong>Change points</strong> flag a bounded structural-shift candidate and preserve validation cases for no-change, trend and seasonality.</p></div>
            <div><span>04</span><p><strong>Propensity and DiD</strong> require overlap, timing and design assumptions; results remain analytical evidence for human review.</p></div>
          </div>
        </Panel>
        <Panel
          eyebrow="Governance"
          title="Controlled use"
          subtitle="Runtime declarations from the advanced-statistics status endpoint"
        >
          <dl className="risk-backtest-list">
            <div><dt>Causal claim</dt><dd>{status ? (status.causalClaim ? "Declared" : "No") : "Not verified"}</dd></div>
            <div><dt>Approval required</dt><dd>{status ? (status.approvalRequired ? "Yes" : "No") : "Not verified"}</dd></div>
            <div><dt>Data mode</dt><dd>{data.metadata.dataMode}</dd></div>
            <div><dt>Dataset hash</dt><dd className="quant-hash">{data.metadata.sourceContext.datasetHash ?? "Not returned"}</dd></div>
          </dl>
          <div className="quant-boundary-note">
            No customer policy, adverse action, pricing action or investment decision is automated from this page.
          </div>
        </Panel>
      </div>
      <SourceFooter
        source="advanced-statistics status endpoint"
        denominator="Method-level runtime declarations"
        period={data.metadata.sourceContext.snapshotDate ?? data.metadata.asOf}
      />
    </>
  );
}
