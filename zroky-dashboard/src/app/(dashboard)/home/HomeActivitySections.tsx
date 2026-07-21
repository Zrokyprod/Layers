"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { ArrowUpRight, CheckCircle2, ClipboardCheck, ShieldCheck } from "lucide-react";

import { StatusPill } from "@/components/status-pill";
import { buildActionView } from "@/lib/action-view";
import type { StatusTone } from "@/lib/action-status";
import { field, formatDateTime, humanize } from "@/lib/format";
import type {
  ActionIntentResponse,
  OutcomeReconciliationView,
  RuntimePolicyDecisionResponse,
} from "@/lib/api";

type HomeActivitySectionsProps = {
  intents: ActionIntentResponse[];
  approvals: RuntimePolicyDecisionResponse[];
  outcomes: OutcomeReconciliationView[];
  loading: boolean;
};

type ActivityRow = {
  id: string;
  title: string;
  meta: string;
  status: string;
  tone: StatusTone;
  href: string;
  createdAt: string | null;
};

function byRecent<T extends { created_at?: string | null; checked_at?: string | null }>(items: T[]): T[] {
  return [...items].sort((a, b) => {
    const aTime = new Date(a.checked_at ?? a.created_at ?? 0).getTime();
    const bTime = new Date(b.checked_at ?? b.created_at ?? 0).getTime();
    return bTime - aTime;
  });
}

function approvalTitle(approval: RuntimePolicyDecisionResponse): string {
  return (
    field(approval.intended_action.summary) ??
    field(approval.tool_name) ??
    field(approval.action_type) ??
    approval.id
  );
}

function approvalTone(approval: RuntimePolicyDecisionResponse): StatusTone {
  if (approval.status === "allowed" || approval.allowed) return "success";
  if (approval.status === "blocked" || approval.status === "rejected" || approval.status === "expired") return "danger";
  return "warning";
}

function outcomeTone(outcome: OutcomeReconciliationView): StatusTone {
  if (outcome.verdict === "matched" || outcome.verification_status === "matched") return "success";
  if (outcome.verdict === "mismatched" || outcome.verification_status === "mismatched") return "danger";
  return "warning";
}

function EmptyActivity({ label }: { label: string }) {
  return (
    <div className="mc-activity-empty">
      <CheckCircle2 aria-hidden="true" size={16} />
      <span>{label}</span>
    </div>
  );
}

function ActivityList({
  title,
  eyebrow,
  href,
  icon,
  rows,
  empty,
  loading,
}: {
  title: string;
  eyebrow: string;
  href: string;
  icon: ReactNode;
  rows: ActivityRow[];
  empty: string;
  loading: boolean;
}) {
  return (
    <section className="mc-activity-card" aria-label={title}>
      <div className="mc-activity-head">
        <span className="mc-activity-icon" aria-hidden="true">{icon}</span>
        <div>
          <p className="mc-eyebrow">{eyebrow}</p>
          <h2>{title}</h2>
        </div>
        <Link href={href} aria-label={`Open ${title}`}>
          <ArrowUpRight aria-hidden="true" size={15} />
        </Link>
      </div>

      {loading ? (
        <div className="mc-activity-list" aria-label={`Loading ${title}`}>
          {Array.from({ length: 3 }).map((_, index) => (
            <div className="mc-activity-row mc-skeleton-row" key={index}>
              <span className="mc-skeleton mc-skeleton-label" />
              <span className="mc-skeleton mc-skeleton-line" />
            </div>
          ))}
        </div>
      ) : rows.length > 0 ? (
        <div className="mc-activity-list">
          {rows.map((row) => (
            <Link className={`mc-activity-row mc-tone-${row.tone}`} href={row.href} key={row.id}>
              <span>
                <strong>{row.title}</strong>
                <small>{row.meta}</small>
              </span>
              <span>
                <StatusPill value={row.status} tone={row.tone} />
                <em>{formatDateTime(row.createdAt)}</em>
              </span>
            </Link>
          ))}
        </div>
      ) : (
        <EmptyActivity label={empty} />
      )}
    </section>
  );
}

export function HomeActivitySections({
  intents,
  approvals,
  outcomes,
  loading,
}: HomeActivitySectionsProps) {
  const protectedActions = byRecent(intents).slice(0, 4).map((intent): ActivityRow => {
    const view = buildActionView(intent);
    return {
      id: intent.action_id,
      title: view.title,
      meta: view.agentName,
      status: view.statusLabel,
      tone: view.statusTone,
      href: `/operations?action_id=${encodeURIComponent(intent.action_id)}`,
      createdAt: intent.created_at,
    };
  });
  const recentApprovals = byRecent(approvals).slice(0, 4).map((approval): ActivityRow => ({
    id: approval.id,
    title: approvalTitle(approval),
    meta: approval.agent_name ?? humanize(approval.action_type) ?? "Approval",
    status: approval.status,
    tone: approvalTone(approval),
    href: `/approvals?decision_id=${encodeURIComponent(approval.id)}`,
    createdAt: approval.created_at,
  }));
  const proofChecks = byRecent(outcomes).slice(0, 4).map((outcome): ActivityRow => ({
    id: outcome.id,
    title: outcome.system_ref ?? humanize(outcome.action_type) ?? "Outcome check",
    meta: outcome.reason ? humanize(outcome.reason) : humanize(outcome.connector_type),
    status: outcome.verdict ?? outcome.verification_status ?? "not_verified",
    tone: outcomeTone(outcome),
    href: "/outcomes",
    createdAt: outcome.checked_at ?? outcome.created_at,
  }));

  return (
    <div className="mc-activity-grid" aria-label="Recent Home activity">
      <ActivityList
        title="Recent protected actions"
        eyebrow="Actions"
        href="/operations"
        icon={<ShieldCheck size={16} />}
        rows={protectedActions}
        empty="No protected actions yet."
        loading={loading}
      />
      <ActivityList
        title="Recent approvals"
        eyebrow="Approvals"
        href="/approvals"
        icon={<ClipboardCheck size={16} />}
        rows={recentApprovals}
        empty="No approval activity yet."
        loading={loading}
      />
      <ActivityList
        title="Recent proof checks"
        eyebrow="Proof"
        href="/outcomes"
        icon={<CheckCircle2 size={16} />}
        rows={proofChecks}
        empty="No proof checks yet."
        loading={loading}
      />
    </div>
  );
}
