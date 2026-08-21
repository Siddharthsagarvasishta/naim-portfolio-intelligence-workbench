"use client";

import { useId, useState } from "react";
import type {
  EvidenceItem,
  EvidenceTabId,
  KpiMetric,
  SignalStatus,
  WorkbenchMode,
} from "../workbench-types";
import { formatMetricDelta, formatMetricValue } from "../data/metric-format";
import { metricLineageAvailable } from "../data/governed-evidence";
import { SparkBars } from "./charts";

export function StatusChip({
  status,
  compact = false,
}: {
  status: SignalStatus | string;
  compact?: boolean;
}) {
  const normalized = status.toLowerCase().replaceAll(" ", "-");
  return (
    <span className={`status-chip tone-${normalized} ${compact ? "is-compact" : ""}`}>
      <i aria-hidden="true" />
      {status}
    </span>
  );
}

export function Panel({
  title,
  eyebrow,
  subtitle,
  action,
  children,
  className = "",
  flush = false,
  id,
}: {
  title?: string;
  eyebrow?: string;
  subtitle?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  flush?: boolean;
  id?: string;
}) {
  return (
    <section
      className={`panel ${flush ? "is-flush" : ""} ${className}`}
      id={id}
    >
      {title || eyebrow || subtitle || action ? (
        <header className="panel-header">
          <div>
            {eyebrow ? <div className="eyebrow">{eyebrow}</div> : null}
            {title ? <h2>{title}</h2> : null}
            {subtitle ? <p>{subtitle}</p> : null}
          </div>
          {action ? <div className="panel-actions">{action}</div> : null}
        </header>
      ) : null}
      <div className={flush ? "panel-body is-flush" : "panel-body"}>
        {children}
      </div>
    </section>
  );
}

export function PageHeader({
  eyebrow,
  title,
  summary,
  facts,
  actions,
}: {
  eyebrow: string;
  title: string;
  summary: string;
  facts: Array<{ label: string; value: string; status?: SignalStatus }>;
  actions?: React.ReactNode;
}) {
  return (
    <header className="page-header">
      <div className="page-heading-copy">
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{summary}</p>
      </div>
      <div className="page-heading-side">
        {actions ? <div className="page-actions">{actions}</div> : null}
        <dl className="page-facts">
          {facts.map((fact) => (
            <div key={fact.label}>
              <dt>{fact.label}</dt>
              <dd>
                {fact.status ? <StatusChip status={fact.status} compact /> : null}
                {fact.value}
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </header>
  );
}

export function MetricCard({
  metric,
  trend,
  onInspect,
  compact = false,
}: {
  metric: KpiMetric;
  trend?: number[];
  onInspect: (metric: KpiMetric) => void;
  compact?: boolean;
}) {
  const tooltipId = useId();
  const lineageAvailable = metricLineageAvailable(metric);
  return (
    <button
      type="button"
      className={`metric-card ${compact ? "is-compact" : ""} ${lineageAvailable ? "" : "is-lineage-defect"}`}
      onClick={() => onInspect(metric)}
      aria-describedby={tooltipId}
    >
      <div className="metric-card-top">
        <span>{metric.shortName}</span>
        <StatusChip status={metric.status} compact />
      </div>
      <div className="metric-card-value">{formatMetricValue(metric)}</div>
      <div className="metric-card-change">
        <strong>{formatMetricDelta(metric)}</strong>
        <span>
          vs {formatMetricValue(metric, metric.prior)}
        </span>
      </div>
      {trend ? (
        <SparkBars
          values={trend}
          status={metric.status}
          label={`${metric.name} recent trend`}
        />
      ) : null}
      <div className="metric-card-foot">
        <span>{lineageAvailable ? metric.statisticalStatus : "LINEAGE UNAVAILABLE"}</span>
        <span aria-hidden="true">↗</span>
      </div>
      <span className="sr-only" id={tooltipId}>
        {metric.definition.formula}. Denominator: {metric.denominator}. Open
        metric evidence. {lineageAvailable ? "Governed lineage available." : "Lineage defect: governed source evidence is unavailable."}
      </span>
    </button>
  );
}

export function SegmentedControl<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: Array<{ value: T; label: string }>;
  onChange: (value: T) => void;
}) {
  return (
    <div className="segmented-control" role="group" aria-label={label}>
      {options.map((option) => (
        <button
          type="button"
          key={option.value}
          className={value === option.value ? "is-active" : ""}
          onClick={() => onChange(option.value)}
          aria-pressed={value === option.value}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function EvidenceDrawer({
  evidence,
  onClose,
}: {
  evidence: EvidenceItem | null;
  onClose: () => void;
}) {
  const drawerTitleId = useId();
  const tabsId = useId();
  const [activeTab, setActiveTab] = useState<EvidenceTabId>("definition");
  const tabs = evidence?.tabs ?? [];
  const selectedTab =
    tabs.find((tab) => tab.id === activeTab) ?? tabs[0];

  return (
    <>
      <button
        type="button"
        className={`drawer-scrim ${evidence ? "is-open" : ""}`}
        onClick={onClose}
        aria-label="Close evidence drawer"
        tabIndex={evidence ? 0 : -1}
      />
      <aside
        className={`evidence-drawer ${evidence ? "is-open" : ""}`}
        aria-hidden={!evidence}
        aria-labelledby={drawerTitleId}
        aria-modal={Boolean(evidence)}
        role="dialog"
      >
        <header>
          <div>
            <div className="eyebrow">{evidence?.eyebrow ?? "Evidence"}</div>
            <h2 id={drawerTitleId}>{evidence?.title ?? "Evidence"}</h2>
          </div>
          <button type="button" className="icon-button" onClick={onClose}>
            <span aria-hidden="true">×</span>
            <span className="sr-only">Close</span>
          </button>
        </header>
        {evidence ? (
          <div className="drawer-content">
            <p className="drawer-summary">{evidence.summary}</p>
            <dl className="evidence-facts">
              {evidence.facts.map((fact) => (
                <div key={fact.label}>
                  <dt>{fact.label}</dt>
                  <dd>{fact.value}</dd>
                </div>
              ))}
            </dl>
            {evidence.defect ? (
              <div className="drawer-defect" role="alert">
                <strong>Evidence defect</strong>
                <p>{evidence.defect}</p>
              </div>
            ) : null}
            {tabs.length > 0 && selectedTab ? (
              <div className="evidence-tabs">
                <div
                  className="evidence-tab-list"
                  role="tablist"
                  aria-label="Metric evidence sections"
                  onKeyDown={(event) => {
                    const current = Math.max(
                      0,
                      tabs.findIndex((tab) => tab.id === selectedTab.id),
                    );
                    let next = current;
                    if (event.key === "ArrowRight") {
                      event.preventDefault();
                      next = (current + 1) % tabs.length;
                    } else if (event.key === "ArrowLeft") {
                      event.preventDefault();
                      next = (current - 1 + tabs.length) % tabs.length;
                    } else if (event.key === "Home") {
                      event.preventDefault();
                      next = 0;
                    } else if (event.key === "End") {
                      event.preventDefault();
                      next = tabs.length - 1;
                    } else {
                      return;
                    }
                    setActiveTab(tabs[next].id);
                    event.currentTarget
                      .querySelectorAll<HTMLButtonElement>('[role="tab"]')
                      [next]?.focus();
                  }}
                >
                  {tabs.map((tab) => (
                    <button
                      type="button"
                      role="tab"
                      id={`${tabsId}-${tab.id}-tab`}
                      aria-controls={`${tabsId}-${tab.id}-panel`}
                      aria-selected={selectedTab.id === tab.id}
                      tabIndex={selectedTab.id === tab.id ? 0 : -1}
                      className={selectedTab.id === tab.id ? "is-active" : ""}
                      key={tab.id}
                      onClick={() => setActiveTab(tab.id)}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>
                <section
                  className="evidence-tab-panel"
                  role="tabpanel"
                  id={`${tabsId}-${selectedTab.id}-panel`}
                  aria-labelledby={`${tabsId}-${selectedTab.id}-tab`}
                  tabIndex={0}
                >
                  {selectedTab.defect ? (
                    <div className="drawer-defect" role="alert">
                      <strong>Evidence defect</strong>
                      <p>{selectedTab.defect}</p>
                    </div>
                  ) : null}
                  <dl className="evidence-facts">
                    {selectedTab.facts.map((fact) => (
                      <div key={fact.label}>
                        <dt>{fact.label}</dt>
                        <dd>{fact.value}</dd>
                      </div>
                    ))}
                  </dl>
                  {selectedTab.note ? <p className="evidence-tab-note">{selectedTab.note}</p> : null}
                </section>
              </div>
            ) : null}
            {evidence.caveat ? (
              <div className="drawer-note">
                <strong>Interpretation boundary</strong>
                <p>{evidence.caveat}</p>
              </div>
            ) : null}
            {evidence.action ? (
              <div className="drawer-action">
                <strong>Controlled next step</strong>
                <p>{evidence.action}</p>
              </div>
            ) : null}
          </div>
        ) : null}
      </aside>
    </>
  );
}

export function MethodologyPopover({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="methodology-popover">
      <button
        type="button"
        className="ghost-button"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
      >
        <span aria-hidden="true">ⓘ</span> Methodology
      </button>
      {open ? (
        <div className="methodology-card" role="dialog" aria-label={title}>
          <header>
            <strong>{title}</strong>
            <button
              type="button"
              className="icon-button"
              onClick={() => setOpen(false)}
            >
              <span aria-hidden="true">×</span>
              <span className="sr-only">Close</span>
            </button>
          </header>
          <div>{children}</div>
        </div>
      ) : null}
    </div>
  );
}

export function AnalystOnly({
  mode,
  children,
}: {
  mode: WorkbenchMode;
  children: React.ReactNode;
}) {
  if (mode === "executive") return null;
  return <>{children}</>;
}

export function DataState({
  type,
  title,
  detail,
  action,
}: {
  type: "loading" | "empty" | "error";
  title: string;
  detail: string;
  action?: React.ReactNode;
}) {
  return (
    <div className={`data-state is-${type}`} role={type === "error" ? "alert" : "status"}>
      {type === "loading" ? (
        <div className="loading-mark" aria-hidden="true">
          <i />
          <i />
          <i />
        </div>
      ) : (
        <div className="data-state-mark" aria-hidden="true">
          {type === "empty" ? "∅" : "!"}
        </div>
      )}
      <strong>{title}</strong>
      <p>{detail}</p>
      {action}
    </div>
  );
}

export function SourceFooter({
  source,
  denominator,
  period,
}: {
  source: string;
  denominator: string;
  period: string;
}) {
  return (
    <div className="source-footer">
      <span>Source: {source}</span>
      <span>Denominator: {denominator}</span>
      <span>Period: {period}</span>
    </div>
  );
}

export function TableShell({
  children,
  label,
}: {
  children: React.ReactNode;
  label: string;
}) {
  return (
    <div className="table-shell" role="region" aria-label={label} tabIndex={0}>
      {children}
    </div>
  );
}

export function ModeNote({ mode }: { mode: WorkbenchMode }) {
  if (mode === "analyst") {
    return (
      <div className="mode-note">
        <span>Analyst mode</span>
        Confidence, sample and diagnostic detail is visible.
      </div>
    );
  }
  if (mode === "recruiter") {
    return (
      <div className="mode-note">
        <span>Showcase mode</span>
        The seeded deterioration story and governed workflow are foregrounded.
      </div>
    );
  }
  return null;
}
