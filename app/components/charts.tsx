"use client";

import { useMemo, useState } from "react";

import type {
  ContributionPoint,
  DistributionPoint,
  FinanceBridgeItem,
  SignalStatus,
  StrategyResult,
  TrendPoint,
  VintageCell,
} from "../workbench-types";

export type ChartDataRow = Record<
  string,
  string | number | boolean | null | undefined
>;

export interface ChartInteractionState {
  activeSeries: ReadonlySet<string>;
  range: string;
}

function csvCell(value: ChartDataRow[string]): string {
  if (value === null || value === undefined) return "";
  let text = String(value);
  if (typeof value === "string" && /^[=+\-@]/.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}

export function chartRowsToCsv(rows: ChartDataRow[]): string {
  const headers = [...new Set(rows.flatMap((row) => Object.keys(row)))];
  if (headers.length === 0) return "";
  return [
    headers.map(csvCell).join(","),
    ...rows.map((row) => headers.map((header) => csvCell(row[header])).join(",")),
  ].join("\n");
}

export function ChartInteractionFrame({
  label,
  filename,
  rows,
  series = [],
  rangeOptions = [],
  defaultRange,
  onOpenEvidence,
  onDrillThrough,
  children,
}: {
  label: string;
  filename: string;
  rows: ChartDataRow[] | ((state: ChartInteractionState) => ChartDataRow[]);
  series?: Array<{ id: string; label: string }>;
  rangeOptions?: Array<{ value: string; label: string }>;
  defaultRange?: string;
  onOpenEvidence?: () => void;
  onDrillThrough?: () => void;
  children: (state: ChartInteractionState) => React.ReactNode;
}) {
  const [activeSeries, setActiveSeries] = useState(
    () => new Set(series.map((item) => item.id)),
  );
  const [range, setRange] = useState(
    defaultRange ?? rangeOptions[0]?.value ?? "all",
  );
  const [downloadState, setDownloadState] = useState("");
  const interactionState = useMemo<ChartInteractionState>(
    () => ({ activeSeries, range }),
    [activeSeries, range],
  );
  const resolvedRows = typeof rows === "function" ? rows(interactionState) : rows;

  const toggleSeries = (id: string) => {
    setActiveSeries((current) => {
      const next = new Set(current);
      if (next.has(id)) {
        if (next.size > 1) next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const download = () => {
    const csv = chartRowsToCsv(resolvedRows);
    if (!csv) {
      setDownloadState("No rows are available for this chart scope.");
      return;
    }
    const url = URL.createObjectURL(
      new Blob(["\uFEFF", csv], { type: "text/csv;charset=utf-8" }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename.endsWith(".csv") ? filename : `${filename}.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
    setDownloadState(`${resolvedRows.length.toLocaleString()} chart rows downloaded.`);
  };

  return (
    <div className="interactive-chart" aria-label={`${label} interactive chart`}>
      <div className="chart-interaction-bar">
        <div className="chart-interaction-label"><span aria-hidden="true">◎</span><strong>Chart tools</strong></div>
        {series.length > 0 ? (
          <div className="chart-series-controls" role="group" aria-label={`${label} legend`}>
            {series.map((item) => (
              <button
                type="button"
                key={item.id}
                aria-pressed={activeSeries.has(item.id)}
                className={activeSeries.has(item.id) ? "is-active" : ""}
                onClick={() => toggleSeries(item.id)}
              >
                <i aria-hidden="true" /> {item.label}
              </button>
            ))}
          </div>
        ) : null}
        {rangeOptions.length > 0 ? (
          <div className="chart-range-controls" role="group" aria-label={`${label} range`}>
            {rangeOptions.map((option) => (
              <button
                type="button"
                key={option.value}
                aria-pressed={range === option.value}
                className={range === option.value ? "is-active" : ""}
                onClick={() => setRange(option.value)}
              >
                {option.label}
              </button>
            ))}
          </div>
        ) : null}
        <div className="chart-action-controls">
          {onDrillThrough ? <button type="button" onClick={onDrillThrough}>Drill through</button> : null}
          {onOpenEvidence ? <button type="button" onClick={onOpenEvidence}>Open evidence</button> : null}
          <button type="button" onClick={download}>Download chart data</button>
        </div>
      </div>
      <div className="interactive-chart-stage">{children(interactionState)}</div>
      <span className="sr-only" role="status" aria-live="polite">{downloadState}</span>
    </div>
  );
}

export function formatCompact(
  value: number | null | undefined,
  unit = "",
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "N/A";
  if (unit === "$m") return `$${value.toFixed(value >= 10 ? 1 : 2)}m`;
  if (unit === "$") return `$${value.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
  if (unit === "%") return `${value.toFixed(2)}%`;
  if (unit === "bps") return `${value.toFixed(1)} bps`;
  if (unit === "count") return Math.round(value).toLocaleString("en-US");
  return `${value.toLocaleString("en-US", { maximumFractionDigits: 2 })}${unit}`;
}

export function SparkBars({
  values,
  status = "Stable",
  label,
}: {
  values: number[];
  status?: SignalStatus;
  label: string;
}) {
  const max = Math.max(...values);
  const min = Math.min(...values);
  const span = Math.max(max - min, max * 0.08, 0.01);
  return (
    <div
      className={`spark-bars tone-${status.toLowerCase()}`}
      role="img"
      aria-label={`${label}. Values ${values.map((value) => value.toFixed(2)).join(", ")}.`}
    >
      {values.map((value, index) => (
        <span
          key={`${value}-${index}`}
          className="spark-bar"
          style={{ height: `${18 + ((value - min) / span) * 82}%` }}
          title={`${value.toFixed(2)}`}
        />
      ))}
    </div>
  );
}

export function TrendBars({
  points,
  unit,
  label,
  threshold,
}: {
  points: TrendPoint[];
  unit: string;
  label: string;
  threshold?: number;
}) {
  if (points.length === 0) {
    return <ChartEmpty label={label} />;
  }
  const values = points.flatMap((point) =>
    [point.value, point.lower, point.upper].filter(
      (value): value is number => typeof value === "number",
    ),
  );
  const max = Math.max(...values);
  const min = Math.min(...values);
  const baseline = Math.min(0, min);
  const span = Math.max(max - baseline, 0.01);
  return (
    <div className="trend-chart">
      <div
        className="trend-bars"
        role="img"
        aria-label={`${label} from ${points[0].month} to ${points[points.length - 1].month}. Latest ${formatCompact(points.at(-1)?.value, unit)}.`}
      >
        {threshold !== undefined ? (
          <div
            className="chart-threshold"
            style={{
              bottom: `${Math.min(96, ((threshold - baseline) / span) * 100)}%`,
            }}
          >
            <span>Guardrail {formatCompact(threshold, unit)}</span>
          </div>
        ) : null}
        {points.map((point, index) => {
          const barHeight = Math.max(
            4,
            ((point.value - baseline) / span) * 100,
          );
          return (
            <div className="trend-bar-column" key={`${point.month}-${index}`}>
              <div className="trend-value">{formatCompact(point.value, unit)}</div>
              <div
                className={`trend-bar ${index === points.length - 1 ? "is-latest" : ""}`}
                style={{ height: `${barHeight}%` }}
                title={`${point.month}: ${formatCompact(point.value, unit)}`}
              />
              {(points.length <= 12 ||
                index % Math.max(1, Math.ceil(points.length / 8)) === 0 ||
                index === points.length - 1) && (
                <div className="trend-label">{point.month}</div>
              )}
            </div>
          );
        })}
      </div>
      <div className="chart-foot">
        <span>Source: governed monthly metric mart</span>
        <span>{points.length} reporting periods</span>
      </div>
    </div>
  );
}

export function HorizontalBars({
  data,
  unit = "%",
  max,
  onSelect,
  valueLabel,
}: {
  data: DistributionPoint[];
  unit?: string;
  max?: number;
  onSelect?: (item: DistributionPoint) => void;
  valueLabel?: string;
}) {
  if (data.length === 0) return <ChartEmpty label="distribution" />;
  const resolvedMax = max ?? Math.max(...data.map((item) => item.value), 1);
  return (
    <div className="horizontal-bars">
      {data.map((item) => {
        const content = (
          <>
            <span className="hbar-label">
              <span>{item.label}</span>
              {item.status ? (
                <span
                  className={`status-dot tone-${item.status.toLowerCase()}`}
                  aria-label={item.status}
                />
              ) : null}
            </span>
            <span className="hbar-track" aria-hidden="true">
              <span
                className={`hbar-fill ${item.status ? `tone-${item.status.toLowerCase()}` : ""}`}
                style={{
                  width: `${Math.max(1, (Math.abs(item.value) / resolvedMax) * 100)}%`,
                }}
              />
            </span>
            <span className="hbar-value">
              {formatCompact(item.value, unit)}
              {item.secondary !== undefined ? (
                <small>
                  {valueLabel ?? "n"} {formatCompact(item.secondary, "count")}
                </small>
              ) : null}
            </span>
          </>
        );
        return onSelect ? (
          <button
            type="button"
            className="hbar-row is-clickable"
            key={item.label}
            onClick={() => onSelect(item)}
            aria-label={`Inspect ${item.label}: ${formatCompact(item.value, unit)}`}
          >
            {content}
          </button>
        ) : (
          <div className="hbar-row" key={item.label}>
            {content}
          </div>
        );
      })}
    </div>
  );
}

export function ContributionBars({
  data,
  onSelect,
  showMix = true,
  showPerformance = true,
}: {
  data: ContributionPoint[];
  onSelect?: (item: ContributionPoint) => void;
  showMix?: boolean;
  showPerformance?: boolean;
}) {
  if (data.length === 0) return <ChartEmpty label="contribution analysis" />;
  const max = Math.max(...data.map((item) => Math.abs(item.contribution)), 1);
  return (
    <div className="contribution-bars">
      <div className="contribution-legend">
        {showMix ? <span><i className="legend-mix" /> Mix</span> : null}
        {showPerformance ? <span><i className="legend-performance" /> Within-segment</span> : null}
      </div>
      {data.map((item) => (
        <button
          type="button"
          className="contribution-row"
          key={item.label}
          onClick={() => onSelect?.(item)}
          aria-label={`${item.label}: ${item.contribution.toFixed(1)} basis points total, ${item.mix.toFixed(1)} mix and ${item.performance.toFixed(1)} performance`}
        >
          <span className="contribution-label">
            <strong>{item.label}</strong>
            <small>
              n = {item.population.toLocaleString()} · {item.persistence} period
              {item.persistence === 1 ? "" : "s"}
            </small>
          </span>
          <span className="stack-track">
            <span
              className="stack-mix"
              style={{ width: showMix ? `${(Math.abs(item.mix) / max) * 100}%` : "0%" }}
            />
            <span
              className="stack-performance"
              style={{ width: showPerformance ? `${(Math.abs(item.performance) / max) * 100}%` : "0%" }}
            />
          </span>
          <strong className="contribution-value">
            {item.contribution > 0 ? "+" : ""}
            {item.contribution.toFixed(1)} bps
          </strong>
        </button>
      ))}
    </div>
  );
}

export function RollRateMatrix({
  labels,
  values,
}: {
  labels: string[];
  values: number[][];
}) {
  const flat = values.flat();
  const max = Math.max(...flat, 1);
  return (
    <div className="matrix-wrap">
      <table className="matrix-table">
        <caption className="sr-only">
          Adjacent-period delinquency transition matrix. Rows show prior state
          and columns show current state.
        </caption>
        <thead>
          <tr>
            <th scope="col">From / to</th>
            {labels.map((label) => (
              <th scope="col" key={label}>{label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {values.map((row, rowIndex) => (
            <tr key={labels[rowIndex]}>
              <th scope="row">{labels[rowIndex]}</th>
              {row.map((value, columnIndex) => (
                <td
                  key={`${rowIndex}-${columnIndex}`}
                  className={`heat-${Math.max(1, Math.ceil((value / max) * 5))}`}
                  title={`${labels[rowIndex]} to ${labels[columnIndex]}: ${value.toFixed(1)}%`}
                >
                  {value.toFixed(1)}%
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="chart-foot">
        <span>Unit: % of matched adjacent-period accounts</span>
        <span>Excludes quarantined observations</span>
      </div>
    </div>
  );
}

export function VintageHeatmap({
  cells,
  metric = "delinquency30",
  onSelect,
}: {
  cells: VintageCell[];
  metric?: "delinquency30" | "cumulativeLoss";
  onSelect?: (cell: VintageCell) => void;
}) {
  if (cells.length === 0) return <ChartEmpty label="vintage heatmap" />;
  const vintages = [...new Set(cells.map((cell) => cell.vintage))];
  const mobs = [...new Set(cells.map((cell) => cell.mob))].sort((a, b) => a - b);
  const values = cells.map((cell) => cell[metric]);
  const max = Math.max(...values, 0.01);
  return (
    <div className="vintage-grid-wrap">
      <table className="vintage-grid">
        <caption className="sr-only">
          {metric === "delinquency30"
            ? "30 plus delinquency"
            : "cumulative net loss"}{" "}
          by vintage and months on book.
        </caption>
        <thead>
          <tr>
            <th scope="col">Vintage</th>
            {mobs.map((mob) => (
              <th scope="col" key={mob}>M{mob}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {vintages.map((vintage) => (
            <tr key={vintage}>
              <th scope="row">
                <span>{vintage}</span>
                <small>
                  n ={" "}
                  {cells
                    .find((cell) => cell.vintage === vintage)
                    ?.cohortSize.toLocaleString()}
                </small>
              </th>
              {mobs.map((mob) => {
                const cell = cells.find(
                  (candidate) =>
                    candidate.vintage === vintage && candidate.mob === mob,
                );
                if (!cell) {
                  return (
                    <td className="vintage-empty" key={mob} aria-label="Not mature">
                      —
                    </td>
                  );
                }
                const value = cell[metric];
                const level = Math.max(1, Math.ceil((value / max) * 5));
                return (
                  <td key={mob}>
                    <button
                      type="button"
                      className={`vintage-cell heat-${level}`}
                      onClick={() => onSelect?.(cell)}
                      title={`${vintage}, month ${mob}: ${value.toFixed(2)}%. 95% interval ${cell.confidenceLow.toFixed(2)}%–${cell.confidenceHigh.toFixed(2)}%.`}
                    >
                      {value.toFixed(2)}
                      {cell.maturityWarning ? <sup>†</sup> : null}
                    </button>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="chart-foot">
        <span>Unit: % · original booked cohort denominator</span>
        <span>† Incomplete maturity; interpret against aligned months only</span>
      </div>
    </div>
  );
}

export function CohortCurves({
  cells,
  metric = "delinquency30",
}: {
  cells: VintageCell[];
  metric?: "delinquency30" | "cumulativeLoss";
}) {
  if (cells.length === 0) return <ChartEmpty label="vintage curves" />;
  const vintages = [...new Set(cells.map((cell) => cell.vintage))];
  const max = Math.max(...cells.map((cell) => cell[metric]), 1);
  return (
    <div className="cohort-curves">
      {vintages.map((vintage, seriesIndex) => {
        const series = cells
          .filter((cell) => cell.vintage === vintage)
          .sort((a, b) => a.mob - b.mob);
        return (
          <div className="cohort-row" key={vintage}>
            <span className="cohort-label">
              <i className={`series-swatch series-${seriesIndex + 1}`} />
              <span>
                <strong>{vintage}</strong>
                <small>
                  n = {series[0]?.cohortSize.toLocaleString()} ·{" "}
                  {series[0]?.channel}
                </small>
              </span>
            </span>
            <span
              className="cohort-spark"
              role="img"
              aria-label={`${vintage}: ${series.map((cell) => `${cell.mob} months ${cell[metric].toFixed(2)}%`).join(", ")}`}
            >
              {series.map((cell) => (
                <span className="cohort-point-wrap" key={cell.mob}>
                  <span
                    className={`cohort-point series-${seriesIndex + 1}`}
                    style={{
                      height: `${Math.max(8, (cell[metric] / max) * 100)}%`,
                    }}
                    title={`MOB ${cell.mob}: ${cell[metric].toFixed(2)}%`}
                  />
                  <small>M{cell.mob}</small>
                </span>
              ))}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export function StrategyComparison({
  rows,
  selectedMetric,
  visibleStrategies,
}: {
  rows: StrategyResult[];
  selectedMetric:
    | "expectedProfit"
    | "fraudBps"
    | "reviewRate"
    | "frictionRate"
    | "lossRate";
  visibleStrategies?: ReadonlySet<string>;
}) {
  const visibleRows = visibleStrategies
    ? rows.filter((row) => visibleStrategies.has(row.strategy))
    : rows;
  if (visibleRows.length === 0) return <ChartEmpty label="strategy comparison" />;
  const max = Math.max(...visibleRows.map((row) => Math.abs(row[selectedMetric])), 1);
  const unit = selectedMetric === "expectedProfit" ? "$m" : selectedMetric === "fraudBps" ? "bps" : "%";
  return (
    <div className="strategy-bars">
      {visibleRows.map((row) => {
        const index = rows.findIndex((candidate) => candidate.strategy === row.strategy);
        return (
        <div className="strategy-bar-row" key={row.strategy}>
          <span className="strategy-name">
            <i className={`series-swatch series-${index + 1}`} />
            <span>
              <strong>{row.strategy}</strong>
              <small>{row.status} · n = {row.eligibleAccounts.toLocaleString()}</small>
            </span>
          </span>
          <span className="strategy-track">
            <span
              className={`strategy-fill series-${index + 1}`}
              style={{ width: `${(Math.abs(row[selectedMetric]) / max) * 100}%` }}
            />
          </span>
          <strong>{formatCompact(row[selectedMetric], unit)}</strong>
        </div>
        );
      })}
    </div>
  );
}

export function WaterfallChart({
  items,
}: {
  items: FinanceBridgeItem[];
}) {
  if (items.length === 0) return <ChartEmpty label="profitability bridge" />;
  const max = Math.max(...items.map((item) => Math.abs(item.value)), 1);
  return (
    <div className="waterfall-chart" role="img" aria-label="Expected profit bridge">
      {items.map((item, index) => {
        const isTotal = item.group === "opening" || item.group === "closing";
        const height = isTotal
          ? Math.max(10, (Math.abs(item.value) / max) * 100)
          : Math.max(8, (Math.abs(item.value) / max) * 74);
        return (
          <div className="waterfall-column" key={`${item.label}-${index}`}>
            <strong>
              {item.value > 0 && !isTotal ? "+" : ""}
              {formatCompact(item.value, "$m")}
            </strong>
            <span
              className={`waterfall-bar is-${item.group}`}
              style={{ height: `${height}%` }}
              title={`${item.label}: ${formatCompact(item.value, "$m")}`}
            />
            <small>{item.label}</small>
          </div>
        );
      })}
    </div>
  );
}

export function QuadrantChart({
  items,
  xLabel,
  yLabel,
  xValue,
  yValue,
  onSelect,
}: {
  items: Array<{ id: string; name: string; trend: SignalStatus }>;
  xLabel: string;
  yLabel: string;
  xValue: (item: { id: string; name: string; trend: SignalStatus }) => number;
  yValue: (item: { id: string; name: string; trend: SignalStatus }) => number;
  onSelect?: (item: { id: string; name: string; trend: SignalStatus }) => void;
}) {
  if (items.length === 0) return <ChartEmpty label="quadrant" />;
  const xValues = items.map(xValue);
  const yValues = items.map(yValue);
  const xMin = Math.min(...xValues);
  const xMax = Math.max(...xValues);
  const yMin = Math.min(...yValues);
  const yMax = Math.max(...yValues);
  const xSpan = Math.max(xMax - xMin, 1);
  const ySpan = Math.max(yMax - yMin, 1);
  return (
    <div
      className="quadrant-chart"
      role="img"
      aria-label={`${yLabel} versus ${xLabel}.`}
    >
      <div className="quadrant-line is-vertical" />
      <div className="quadrant-line is-horizontal" />
      <span className="quadrant-axis x-axis">{xLabel}</span>
      <span className="quadrant-axis y-axis">{yLabel}</span>
      <span className="quadrant-zone zone-a">Higher / higher</span>
      <span className="quadrant-zone zone-b">Lower / higher</span>
      <span className="quadrant-zone zone-c">Lower / lower</span>
      <span className="quadrant-zone zone-d">Higher / lower</span>
      {items.map((item) => (
        <button
          type="button"
          className={`quadrant-dot tone-${item.trend.toLowerCase()}`}
          style={{
            left: `${8 + ((xValue(item) - xMin) / xSpan) * 82}%`,
            bottom: `${9 + ((yValue(item) - yMin) / ySpan) * 78}%`,
          }}
          key={item.id}
          title={`${item.name}: ${xLabel} ${xValue(item).toFixed(1)}, ${yLabel} ${yValue(item).toFixed(1)}`}
          onClick={() => onSelect?.(item)}
        >
          <span>{item.name.split(" ")[0]}</span>
        </button>
      ))}
    </div>
  );
}

export function ChartEmpty({ label }: { label: string }) {
  return (
    <div className="chart-empty" role="status">
      <span>∅</span>
      <strong>No {label} data in this scope</strong>
      <small>Adjust the global filters or reset the view.</small>
    </div>
  );
}
