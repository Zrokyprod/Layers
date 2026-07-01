"use client";

import { AlertTriangle, CheckCircle2, RefreshCw, ShieldCheck } from "lucide-react";

import { DashboardButton, DashboardButtonLink } from "@/components/dashboard-button";
import type { StatusTone } from "@/lib/action-status";

type Verdict = {
  title: string;
  detail: string;
  tone: StatusTone;
  ctaLabel: string;
  ctaHref: string;
};

type VerdictHeroProps = {
  verdict: Verdict;
  updatedLabel: string;
  loading: boolean;
  errorCount: number;
  quotaWarning: string | null;
  onRefresh: () => void;
};

function IconForTone({ tone }: { tone: StatusTone }) {
  if (tone === "danger" || tone === "warning") {
    return <AlertTriangle aria-hidden="true" size={18} />;
  }
  if (tone === "success") {
    return <CheckCircle2 aria-hidden="true" size={18} />;
  }
  return <ShieldCheck aria-hidden="true" size={18} />;
}

export function VerdictHero({
  verdict,
  updatedLabel,
  loading,
  errorCount,
  quotaWarning,
  onRefresh,
}: VerdictHeroProps) {
  return (
    <section className={`mc-hero mc-tone-${verdict.tone}`} aria-label="Fleet verdict">
      <div className="mc-hero-main">
        <div className="mc-verdict-icon">
          <IconForTone tone={verdict.tone} />
        </div>
        <div>
          <p className="mc-eyebrow">Mission control</p>
          <h1>{verdict.title}</h1>
          <p className="mc-hero-detail">{verdict.detail}</p>
          <div className="mc-hero-badges" aria-label="Operational notices">
            {quotaWarning ? <span className="mc-inline-warning">{quotaWarning}</span> : null}
            {errorCount > 0 ? (
              <span className="mc-inline-warning">{errorCount} data source{errorCount === 1 ? "" : "s"} unavailable</span>
            ) : null}
          </div>
        </div>
      </div>
      <div className="mc-hero-actions">
        <div className="mc-live-status" aria-label={updatedLabel}>
          <span className="mc-live-dot" aria-hidden="true" />
          <span>{updatedLabel}</span>
        </div>
        <div className="mc-hero-buttons">
          <DashboardButton icon={<RefreshCw />} onClick={onRefresh} disabled={loading} variant="soft">
            Refresh
          </DashboardButton>
          <DashboardButtonLink href={verdict.ctaHref} variant="primary">
            {verdict.ctaLabel}
          </DashboardButtonLink>
        </div>
      </div>
    </section>
  );
}
