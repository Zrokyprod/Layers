"use client";

import { useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleDot,
  DollarSign,
  EyeOff,
  Lightbulb,
  Loader2,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  TrendingDown,
  Wrench,
} from "lucide-react";

import {
  useGenerateRecommendations,
  useRecommendations,
  useRecSummary,
  useUpdateRecStatus,
} from "@/lib/hooks";
import type { RecView } from "@/lib/api";
import { formatCount, formatDateTime, formatPercent, formatUsd } from "@/lib/format";

const STATUS_TABS = [
  { value: "open", label: "Open" },
  { value: "acknowledged", label: "Acknowledged" },
  { value: "resolved", label: "Resolved" },
  { value: "dismissed", label: "Dismissed" },
] as const;

function PriorityBadge({ priority }: { priority: RecView["priority"] }) {
  return <span className={`fix-priority priority-${priority}`}>{priority}</span>;
}

function TypeIcon({ type }: { type: string }) {
  const className = "fix-type-icon";
  if (type === "axis_causal") return <ShieldAlert className={className} aria-hidden="true" />;
  if (type === "determinism_high") return <AlertTriangle className={className} aria-hidden="true" />;
  if (type === "score_drop") return <TrendingDown className={className} aria-hidden="true" />;
  if (type === "cost_spike") return <DollarSign className={className} aria-hidden="true" />;
  return <CircleDot className={className} aria-hidden="true" />;
}

function difficultyLabel(difficulty: RecView["fix_difficulty"]) {
  if (!difficulty) return "Not sized";
  return difficulty;
}

function statusActionLabel(status: string): string {
  if (status === "acknowledged") return "Acknowledge";
  if (status === "resolved") return "Resolve";
  if (status === "dismissed") return "Dismiss";
  return status;
}

function StatusActions({
  rec,
  onAction,
  loading,
}: {
  rec: RecView;
  onAction: (recId: string, status: string) => void;
  loading: boolean;
}) {
  if (rec.status !== "open" && rec.status !== "acknowledged") return null;

  const actions = rec.status === "open"
    ? [
        { status: "acknowledged", icon: CheckCircle2 },
        { status: "dismissed", icon: EyeOff },
      ]
    : [
        { status: "resolved", icon: CheckCircle2 },
        { status: "dismissed", icon: EyeOff },
      ];

  return (
    <div className="fix-action-row">
      {actions.map((action) => {
        const Icon = action.icon;
        return (
          <button
            key={action.status}
            type="button"
            className={action.status === "resolved" || action.status === "acknowledged" ? "btn btn-primary" : "btn btn-soft"}
            disabled={loading}
            onClick={() => onAction(rec.id, action.status)}
          >
            <Icon aria-hidden="true" />
            {statusActionLabel(action.status)}
          </button>
        );
      })}
    </div>
  );
}

function RecCard({
  rec,
  expanded,
  onToggle,
  onAction,
  actionLoading,
}: {
  rec: RecView;
  expanded: boolean;
  onToggle: () => void;
  onAction: (recId: string, status: string) => void;
  actionLoading: boolean;
}) {
  const isClosed = rec.status === "dismissed" || rec.status === "resolved";
  const confidence = rec.axis_confidence == null ? null : rec.axis_confidence * 100;
  const failRate = rec.fail_rate_at_generation == null ? null : rec.fail_rate_at_generation * 100;

  return (
    <article className={`fix-card-row${isClosed ? " is-closed" : ""}`}>
      <button type="button" className="fix-card-summary" onClick={onToggle}>
        <span className="fix-card-icon">
          <TypeIcon type={rec.recommendation_type} />
        </span>
        <span className="fix-card-main">
          <span className="fix-card-meta">
            <PriorityBadge priority={rec.priority} />
            <span className="mono">{rec.agent_name || "unknown-agent"}</span>
            {rec.top_axis ? <span className="fix-axis-chip">{rec.top_axis}</span> : null}
            {rec.estimated_monthly_impact_usd != null && rec.estimated_monthly_impact_usd > 0 ? (
              <span className="fix-saving-chip">{formatUsd(rec.estimated_monthly_impact_usd)}/mo</span>
            ) : null}
          </span>
          <strong>{rec.title}</strong>
          <span className="fix-card-sub">
            Generated {formatDateTime(rec.created_at)} · status {rec.status}
          </span>
        </span>
        <span className="fix-card-toggle" aria-hidden="true">
          {expanded ? <ChevronDown /> : <ChevronRight />}
        </span>
      </button>

      {expanded ? (
        <div className="fix-card-detail">
          {rec.detail ? <p className="fix-detail-copy">{rec.detail}</p> : null}

          <div className="fix-evidence-grid">
            <div>
              <span>Impact score</span>
              <strong>{formatCount(rec.impact_score)}</strong>
            </div>
            <div>
              <span>Confidence</span>
              <strong>{confidence == null ? "-" : formatPercent(confidence)}</strong>
            </div>
            <div>
              <span>Health at generation</span>
              <strong>{rec.health_score_at_generation == null ? "-" : formatCount(rec.health_score_at_generation)}</strong>
            </div>
            <div>
              <span>Fail rate</span>
              <strong>{failRate == null ? "-" : formatPercent(failRate)}</strong>
            </div>
            <div>
              <span>Calls in window</span>
              <strong>{formatCount(rec.call_count_window)}</strong>
            </div>
            <div>
              <span>Fix size</span>
              <strong>{difficultyLabel(rec.fix_difficulty)}</strong>
            </div>
          </div>

          {rec.fix_suggestion ? (
            <div className="fix-suggestion-box">
              <span className="module-eyebrow">
                <Lightbulb aria-hidden="true" />
                Candidate fix
              </span>
              <p>{rec.fix_suggestion}</p>
              {rec.fix_difficulty ? (
                <span className={`fix-difficulty difficulty-${rec.fix_difficulty}`}>
                  <Wrench aria-hidden="true" />
                  {rec.fix_difficulty}
                </span>
              ) : null}
            </div>
          ) : null}

          {rec.ablation_job_id ? (
            <p className="fix-detail-note">Ablation job: <span className="mono">{rec.ablation_job_id}</span></p>
          ) : null}
          {rec.actioned_by || rec.actioned_at ? (
            <p className="fix-detail-note">
              Last action {rec.actioned_at ? formatDateTime(rec.actioned_at) : "-"}
              {rec.actioned_by ? ` by ${rec.actioned_by}` : ""}
            </p>
          ) : null}

          <StatusActions rec={rec} onAction={onAction} loading={actionLoading} />
        </div>
      ) : null}
    </article>
  );
}

export default function RecommendationsPage() {
  const [activeStatus, setActiveStatus] = useState("open");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const { data: recs, isLoading, refetch } = useRecommendations({ status: activeStatus, limit: 100 });
  const { data: summary } = useRecSummary();
  const { mutate: updateStatus, isPending: updating } = useUpdateRecStatus();
  const { mutate: generate, isPending: generating } = useGenerateRecommendations();

  const openImpact = summary?.total_estimated_saving_usd ?? 0;
  const activeItems = recs ?? [];
  const focusText = useMemo(() => {
    const agents = summary?.top_agents ?? [];
    return agents.length > 0 ? agents.join(", ") : "No dominant agent yet";
  }, [summary?.top_agents]);

  function handleAction(recId: string, status: string) {
    updateStatus({ recId, status, actioned_by: "dashboard" });
  }

  return (
    <div className="fix-queue-workspace">
      <section className="module-hero fix-queue-hero">
        <div className="module-hero-header">
          <div>
            <span className="module-eyebrow">
              <Sparkles aria-hidden="true" />
              Fix queue
            </span>
            <h1>What to fix next</h1>
            <p>
              Ranked production recommendations from reliability, cost, determinism,
              and causal-axis evidence. Every item stays a candidate until replay or goldens verify it.
            </p>
          </div>
          <div className="fix-hero-actions">
            <button type="button" className="btn btn-primary" disabled={generating} onClick={() => generate()}>
              {generating ? <Loader2 aria-hidden="true" className="spin-icon" /> : <Sparkles aria-hidden="true" />}
              Generate
            </button>
            <button type="button" className="btn btn-soft" onClick={() => void refetch()}>
              <RefreshCw aria-hidden="true" />
              Refresh
            </button>
          </div>
        </div>
      </section>

      <section className="fix-summary-strip" aria-label="Fix queue summary">
        <article>
          <span>Open</span>
          <strong>{formatCount(summary?.total_open)}</strong>
        </article>
        <article className={summary?.critical_count ? "tone-danger" : ""}>
          <span>Critical</span>
          <strong>{formatCount(summary?.critical_count)}</strong>
        </article>
        <article className={summary?.high_count ? "tone-warning" : ""}>
          <span>High</span>
          <strong>{formatCount(summary?.high_count)}</strong>
        </article>
        <article className={openImpact > 0 ? "tone-success" : ""}>
          <span>Potential monthly saving</span>
          <strong>{formatUsd(openImpact)}</strong>
        </article>
        <article>
          <span>Focus</span>
          <strong>{focusText}</strong>
        </article>
      </section>

      <section className="fix-queue-panel">
        <header className="fix-panel-header">
          <div>
            <span className="module-eyebrow">Queue</span>
            <h2>{activeItems.length} {activeStatus} items</h2>
          </div>
          <div className="fix-status-tabs" role="tablist" aria-label="Recommendation status">
            {STATUS_TABS.map((tab) => (
              <button
                key={tab.value}
                type="button"
                role="tab"
                aria-selected={activeStatus === tab.value}
                className={activeStatus === tab.value ? "active" : ""}
                onClick={() => {
                  setActiveStatus(tab.value);
                  setExpandedId(null);
                }}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </header>

        {isLoading ? (
          <div className="fix-loading">
            <Loader2 aria-hidden="true" className="spin-icon" />
            Loading recommendations
          </div>
        ) : activeItems.length === 0 ? (
          <div className="fix-empty-state">
            <CheckCircle2 aria-hidden="true" />
            <strong>No {activeStatus} recommendations</strong>
            {activeStatus === "open" ? <span>Generate after new reliability data arrives.</span> : null}
          </div>
        ) : (
          <div className="fix-card-stack">
            {activeItems.map((rec) => (
              <RecCard
                key={rec.id}
                rec={rec}
                expanded={expandedId === rec.id}
                onToggle={() => setExpandedId(expandedId === rec.id ? null : rec.id)}
                onAction={handleAction}
                actionLoading={updating}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
