import Link from "next/link";
import type { CSSProperties, ReactNode } from "react";

import { cn } from "@/lib/utils";
import type { StatusTone } from "@/lib/action-status";

export type DashboardScaffoldTone = StatusTone | "setup";

export type DashboardVerdictHeroProps = {
  actions?: ReactNode;
  ariaLabel?: string;
  className?: string;
  copy: string;
  eyebrow: string;
  icon?: ReactNode;
  notices?: ReactNode;
  pill?: string;
  tone: DashboardScaffoldTone;
  title: string;
  updatedLabel?: string;
};

export function DashboardVerdictHero({
  actions,
  ariaLabel,
  className,
  copy,
  eyebrow,
  icon,
  notices,
  pill,
  tone,
  title,
  updatedLabel,
}: DashboardVerdictHeroProps) {
  return (
    <section
      className={cn("dashboard-verdict-hero", className)}
      data-tone={tone}
      aria-label={ariaLabel}
    >
      <div className="dashboard-verdict-main">
        {icon ? <div className="dashboard-verdict-icon">{icon}</div> : null}
        <div className="dashboard-verdict-copy">
          <span className="dashboard-eyebrow">{eyebrow}</span>
          <h1>{title}</h1>
          <p>{copy}</p>
          {notices ? <div className="dashboard-verdict-notices">{notices}</div> : null}
        </div>
      </div>
      <div className="dashboard-verdict-actions">
        {updatedLabel ? (
          <span className="dashboard-live-status">
            <span className="dashboard-live-dot" aria-hidden="true" />
            {updatedLabel}
          </span>
        ) : null}
        {pill ? <span className="dashboard-verdict-pill">{pill}</span> : null}
        {actions ? <div className="dashboard-verdict-buttons">{actions}</div> : null}
      </div>
    </section>
  );
}

export type DashboardMetric = {
  helper: string;
  href?: string;
  icon?: ReactNode;
  id?: string;
  label: string;
  tone: DashboardScaffoldTone;
  value: string;
};

export type DashboardMetricStripProps = {
  ariaLabel: string;
  className?: string;
  columns?: number;
  metrics: DashboardMetric[];
  onMetricClick?: (metric: DashboardMetric) => void;
};

export function DashboardMetricStrip({
  ariaLabel,
  className,
  columns,
  metrics,
  onMetricClick,
}: DashboardMetricStripProps) {
  const style = columns
    ? ({ "--dashboard-metric-columns": columns } as CSSProperties)
    : undefined;

  return (
    <section
      className={cn("dashboard-metric-strip", className)}
      aria-label={ariaLabel}
      style={style}
    >
      {metrics.map((metric) => {
        const content = (
          <>
            <span className="dashboard-metric-head">
              {metric.icon ? <span className="dashboard-metric-icon">{metric.icon}</span> : null}
              {metric.label}
            </span>
            <strong>{metric.value}</strong>
            <p>{metric.helper}</p>
          </>
        );
        const key = metric.id ?? metric.label;

        if (metric.href) {
          return (
            <Link
              key={key}
              href={metric.href}
              className="dashboard-metric-card"
              data-tone={metric.tone}
              onClick={(event) => {
                if (!onMetricClick) return;
                event.preventDefault();
                onMetricClick(metric);
              }}
            >
              {content}
            </Link>
          );
        }

        return (
          <article key={key} className="dashboard-metric-card" data-tone={metric.tone}>
            {content}
          </article>
        );
      })}
    </section>
  );
}

export type DashboardWorkspaceProps = {
  className?: string;
  left: ReactNode;
  leftClassName?: string;
  right: ReactNode;
  rightClassName?: string;
};

export function DashboardWorkspace({
  className,
  left,
  leftClassName,
  right,
  rightClassName,
}: DashboardWorkspaceProps) {
  return (
    <div className={cn("dashboard-workspace", className)}>
      <div className={cn("dashboard-workspace-primary", leftClassName)}>{left}</div>
      <div className={cn("dashboard-workspace-secondary", rightClassName)}>{right}</div>
    </div>
  );
}
