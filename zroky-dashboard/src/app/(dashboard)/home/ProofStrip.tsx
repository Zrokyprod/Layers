"use client";

import Link from "next/link";
import { Activity, ArrowUpRight, Clock3, FileCheck2, UsersRound } from "lucide-react";

import type { StatusTone } from "@/lib/action-status";

export type ProofMetric = {
  id: string;
  label: string;
  value: string;
  detail: string;
  href: string;
  tone: StatusTone;
};

type ProofStripProps = {
  metrics: ProofMetric[];
  loading: boolean;
};

const metricIcons = {
  "agents-protected": UsersRound,
  "controlled-actions": Activity,
  "pending-approvals": Clock3,
  "proof-generated": FileCheck2,
} as const;

export function ProofStrip({ metrics, loading }: ProofStripProps) {
  if (loading) {
    return (
      <section className="mc-proof-strip" aria-label="Proof metrics">
        {Array.from({ length: 4 }).map((_, index) => (
          <div className="mc-proof-card mc-skeleton-card" key={index}>
            <span className="mc-skeleton mc-skeleton-label" />
            <span className="mc-skeleton mc-skeleton-value" />
            <span className="mc-skeleton mc-skeleton-line" />
          </div>
        ))}
      </section>
    );
  }

  return (
    <section className="mc-proof-strip" aria-label="Proof metrics">
      {metrics.map((metric) => {
        const MetricIcon = metricIcons[metric.id as keyof typeof metricIcons] ?? Activity;

        return (
          <Link
            className={`mc-proof-card mc-tone-${metric.tone}`}
            data-metric={metric.id}
            href={metric.href}
            key={metric.id}
          >
            <span className="mc-proof-card-icon" aria-hidden="true">
              <MetricIcon size={19} />
            </span>
            <div className="mc-proof-card-copy">
              <div className="mc-proof-card-head">
                <span>{metric.label}</span>
                <ArrowUpRight aria-hidden="true" size={14} />
              </div>
              <strong>{metric.value}</strong>
              <p>{metric.detail}</p>
            </div>
          </Link>
        );
      })}
    </section>
  );
}
