"use client";

import Link from "next/link";
import { ArrowUpRight } from "lucide-react";

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
      {metrics.map((metric) => (
        <Link className={`mc-proof-card mc-tone-${metric.tone}`} href={metric.href} key={metric.id}>
          <div className="mc-proof-card-head">
            <span>{metric.label}</span>
            <ArrowUpRight aria-hidden="true" size={14} />
          </div>
          <strong>{metric.value}</strong>
          <p>{metric.detail}</p>
        </Link>
      ))}
    </section>
  );
}
