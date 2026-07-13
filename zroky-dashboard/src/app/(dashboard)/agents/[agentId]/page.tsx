"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  Bot,
  Cpu,
  RefreshCw,
  Settings,
} from "lucide-react";

import { DashboardButton, DashboardButtonLink } from "@/components/dashboard-button";
import {
  DashboardMetricStrip,
  DashboardVerdictHero,
} from "@/components/dashboard-scaffold";
import { ProofChainStepper } from "@/components/proof-chain-stepper";
import { StatusPill } from "@/components/status-pill";
import { loadActionsLifecycleFeed } from "@/lib/actions-lifecycle-feed";
import { buildAgentDetail, type AgentDetailView } from "@/lib/agent-detail";
import { dashboardWindowDays } from "@/lib/dashboard-window";
import { formatCount, formatDateTime, humanize, timeSince } from "@/lib/format";
import {
  useActionRunners,
  useAgentProfile,
} from "@/lib/hooks";
import { useDashboardStore } from "@/lib/store";

function AgentDetailHero({
  detail,
  error,
  loading,
  onRefresh,
  windowDays,
}: {
  detail: AgentDetailView | null;
  error: boolean;
  loading: boolean;
  onRefresh: () => void;
  windowDays: number;
}) {
  const title = error
    ? "Agent detail unavailable"
    : detail
      ? detail.profile.display_name
      : loading
        ? "Loading agent"
        : "Agent not found";
  const body = detail
    ? `${detail.config.runtimePath} / ${detail.config.environment || "environment unknown"} / ${formatCount(detail.row.actionRollup.total)} protected actions in the selected ${windowDays}-day window.`
    : error
      ? "One or more agent detail feeds did not refresh cleanly."
      : "Fetching managed profile, proof state, and runner context.";

  return (
    <>
      <DashboardVerdictHero
        eyebrow="Managed agent"
        icon={<Bot aria-hidden="true" size={18} />}
        title={title}
        copy={body}
        tone={error ? "danger" : detail?.row.tone ?? "setup"}
        notices={(
          <Link href="/agents" className="agents-text-link">
            <ArrowLeft aria-hidden="true" />
            Back to fleet
          </Link>
        )}
        actions={(
          <>
            {detail ? <StatusPill value={detail.row.status} label={detail.row.statusLabel} tone={detail.row.tone} /> : null}
            <DashboardButton icon={<RefreshCw />} onClick={onRefresh} variant="soft">
              Refresh
            </DashboardButton>
          </>
        )}
      />
      {detail ? (
        <DashboardMetricStrip
          ariaLabel="Agent detail summary"
          columns={4}
          metrics={[
            {
              helper: "Actions currently held before execution.",
              label: "Held actions",
              tone: detail.row.actionRollup.held > 0 ? "warning" : "success",
              value: formatCount(detail.row.actionRollup.held),
            },
            {
              helper: "Proof mismatches for this managed agent.",
              label: "Mismatched proof",
              tone: detail.row.actionRollup.mismatched > 0 ? "danger" : "success",
              value: formatCount(detail.row.actionRollup.mismatched),
            },
            {
              helper: "Online runners among registered runners compatible with this agent's observed operations.",
              label: "Compatible runners",
              tone: detail.row.onlineRunnerCount > 0 ? "success" : detail.runners.length > 0 ? "warning" : "neutral",
              value: `${formatCount(detail.row.onlineRunnerCount)} / ${formatCount(detail.runners.length)}`,
            },
            {
              helper: "Signed receipts generated for this managed agent.",
              label: "Signed receipts",
              tone: detail.row.actionRollup.receiptsGenerated > 0 ? "success" : "neutral",
              value: formatCount(detail.row.actionRollup.receiptsGenerated),
            },
          ]}
        />
      ) : null}
    </>
  );
}

function ConfigSummaryPanel({ detail }: { detail: AgentDetailView }) {
  const profile = detail.profile;
  const setupHref = `/agents/setup?agentId=${encodeURIComponent(profile.id)}`;
  return (
    <article className="agents-table-panel agent-detail-config" aria-label="Agent control configuration summary">
      <div className="agents-panel-head">
        <div>
          <span>Control configuration</span>
          <strong>Managed by setup wizard</strong>
        </div>
        <DashboardButtonLink href={setupHref} icon={<Settings />} variant="primary">
          Configure
        </DashboardButtonLink>
      </div>
      <p className="agents-detail-message">
        Policy-affecting fields are edited only through setup, so profile config and enforced runtime mandate stay in sync.
      </p>
      <div className="agents-inspector-control-grid">
        <div>
          <span>Runtime</span>
          <strong>{profile.runtime_path}</strong>
        </div>
        <div>
          <span>Environment</span>
          <strong>{profile.environment || "environment unknown"}</strong>
        </div>
        <div>
          <span>Framework</span>
          <strong>{profile.framework || "not set"}</strong>
        </div>
        <div>
          <span>Model</span>
          <strong>{[profile.model_provider, profile.model_name].filter(Boolean).join(" / ") || "not set"}</strong>
        </div>
        <div>
          <span>Allowed actions</span>
          <strong>{profile.allowed_action_types.join(", ") || "not set"}</strong>
        </div>
        <div>
          <span>Blocked actions</span>
          <strong>{profile.blocked_action_types.join(", ") || "none"}</strong>
        </div>
        <div>
          <span>Tools</span>
          <strong>{profile.tool_names.join(", ") || "not set"}</strong>
        </div>
        <div>
          <span>Verifiers</span>
          <strong>{profile.verification_connectors.join(", ") || "not set"}</strong>
        </div>
      </div>
    </article>
  );
}

function ProofPanel({ detail }: { detail: AgentDetailView }) {
  const action = detail.latestAction;
  return (
    <aside className="agents-inspector-panel agent-detail-proof" aria-label="Agent proof and runner context">
      <div className="agents-panel-head">
        <div>
          <span>Control loop</span>
          <strong>{action?.title ?? "No protected action yet"}</strong>
        </div>
        <StatusPill value={detail.row.status} label={detail.row.statusLabel} tone={detail.row.tone} />
      </div>

      <div className="agents-inspector-score">
        <div>
          <span>Actions</span>
          <strong>{formatCount(detail.row.actionRollup.total)}</strong>
        </div>
        <div>
          <span>Runners</span>
          <strong>{formatCount(detail.runners.length)}</strong>
        </div>
        <div>
          <span>Attempts</span>
          <strong>{formatCount(detail.attemptSummary.total)}</strong>
        </div>
        <div>
          <span>Stalled</span>
          <strong>{formatCount(detail.attemptSummary.stalled)}</strong>
        </div>
      </div>

      {action ? (
        <>
          <ProofChainStepper steps={detail.proofChain} />
          <div className="agents-inspector-control-grid">
            <div>
              <span>Action id</span>
              <strong>{action.actionId}</strong>
            </div>
            <div>
              <span>Digest</span>
              <strong>{action.digest ?? "-"}</strong>
            </div>
            <div>
              <span>Proof</span>
              <strong>{action.proofLabel}</strong>
            </div>
            <div>
              <span>Receipt</span>
              <strong>{action.receiptLabel}</strong>
            </div>
          </div>
          <div className="agents-inspector-actions">
            <DashboardButtonLink href={action.hrefs.action ?? "/actions"} variant="soft">
              Open action
            </DashboardButtonLink>
            {action.hrefs.approvals ? (
              <DashboardButtonLink href={action.hrefs.approvals} variant="soft">
                Open approval
              </DashboardButtonLink>
            ) : null}
            <DashboardButtonLink href={action.hrefs.evidence ?? "/evidence"} variant="primary">
              Open evidence
            </DashboardButtonLink>
          </div>
        </>
      ) : (
        <div className="agents-empty-filter">
          <strong>No protected action yet</strong>
          <span>Run this agent through zroky.protect() or the Action Intent API to populate proof and runner context.</span>
        </div>
      )}
    </aside>
  );
}

function ActionHistoryPanel({ detail }: { detail: AgentDetailView }) {
  return (
    <article className="agents-table-panel" aria-label="Agent protected actions">
      <div className="agents-panel-head">
        <div>
          <span>Protected actions</span>
          <strong>{formatCount(detail.row.actionRows.length)} linked rows</strong>
        </div>
      </div>
      <div className="agents-card-list">
        {detail.row.actionRows.length > 0 ? detail.row.actionRows.map((row) => (
          <Link key={row.id} className="agent-detail-action-card" href={row.hrefs.action ?? "/actions"}>
            <div>
              <strong>{row.title}</strong>
              <span>{row.actionType} / {row.stage.label}</span>
              <small>{formatDateTime(row.updatedAt ?? row.createdAt)} / {timeSince(row.updatedAt ?? row.createdAt)}</small>
            </div>
            <div>
              <StatusPill value={row.proofStatus} label={row.proofLabel} tone={row.proofTone} />
              <StatusPill value={row.receiptStatus} label={row.receiptLabel} tone={row.receiptTone} />
            </div>
          </Link>
        )) : (
          <div className="agents-empty-filter">
            <strong>No action history</strong>
            <span>This managed profile has not produced a verified-action lifecycle row yet.</span>
          </div>
        )}
      </div>
    </article>
  );
}

function RunnerPanel({ detail }: { detail: AgentDetailView }) {
  return (
    <article className="agents-table-panel" aria-label="Agent compatible runners and attempts">
      <div className="agents-panel-head">
        <div>
          <span>Compatible runners</span>
          <strong>{formatCount(detail.row.onlineRunnerCount)} online / {formatCount(detail.runners.length)} compatible</strong>
        </div>
      </div>
      <div className="agents-card-list">
        {detail.runners.length > 0 ? detail.runners.map((runner) => (
          <div key={runner.runner_id} className="agents-runner-card">
            <div>
              <Cpu aria-hidden="true" />
              <strong>{runner.name}</strong>
              <span>{runner.runner_type} / {runner.environment}</span>
            </div>
            <StatusPill value={runner.status} />
            <small>{runner.supported_operation_kinds.map((kind) => humanize(kind)).join(" / ") || "all operations"}</small>
            <small>Heartbeat {formatDateTime(runner.last_heartbeat_at)}</small>
          </div>
        )) : (
          <div className="agents-empty-filter">
            <strong>No compatible runner yet</strong>
            <span>No registered runner matches this agent&apos;s observed environment and operation kinds.</span>
          </div>
        )}
        {detail.attempts.slice(0, 5).map((attempt) => {
          const stalled = detail.stalledAttemptIds.includes(attempt.attempt_id);
          return (
            <div key={attempt.attempt_id} className="agents-attempt-card" data-stale={stalled ? "true" : "false"}>
              <div>
                <strong>{attempt.action_id}</strong>
                <span>{attempt.runner_id ?? "runner pending"}</span>
              </div>
              <StatusPill value={attempt.status} tone={stalled ? "danger" : undefined} label={stalled ? "Stalled" : undefined} />
              <small>Attempt {attempt.attempt_number} / updated {formatDateTime(attempt.updated_at)}</small>
            </div>
          );
        })}
      </div>
    </article>
  );
}

export default function AgentDetailPage() {
  const params = useParams<{ agentId?: string }>();
  const agentId = typeof params.agentId === "string" ? params.agentId : null;
  const dateRange = useDashboardStore((state) => state.dateRange);
  const windowDays = useMemo(() => dashboardWindowDays(dateRange), [dateRange]);
  const profileQuery = useAgentProfile(agentId);
  const lifecycleQuery = useQuery({
    queryKey: ["agents", "detail", agentId, "lifecycle-summary", windowDays, 200],
    queryFn: ({ signal }) => loadActionsLifecycleFeed({ days: windowDays, limit: 200 }, signal),
    enabled: Boolean(agentId),
    staleTime: 15_000,
    refetchInterval: 30_000,
  });
  const runnersQuery = useActionRunners({ enabled: Boolean(agentId) });

  const lifecycleData = lifecycleQuery.data?.summary.data;
  const attempts = useMemo(
    () => lifecycleData?.attempts ?? lifecycleData?.stale_attempts ?? [],
    [lifecycleData?.attempts, lifecycleData?.stale_attempts],
  );
  const staleAttemptIds = useMemo(
    () => (lifecycleData?.stale_attempts ?? []).map((attempt) => attempt.attempt_id),
    [lifecycleData?.stale_attempts],
  );
  const profile = profileQuery.data ?? null;
  const sourceSummary = lifecycleData?.source_summary;
  const bypassCoverageAvailable = Boolean(
    (sourceSummary?.connected_feeds ?? 0) > 0 || (sourceSummary?.successful_pollers ?? 0) > 0,
  );

  const detail = useMemo(() => (
    profile ? buildAgentDetail({
      profile,
      intents: lifecycleData?.intents ?? [],
      decisions: lifecycleData?.approvals ?? [],
      outcomes: lifecycleData?.outcomes ?? [],
      runners: runnersQuery.data?.items ?? [],
      attempts,
      staleAttemptIds,
      bypassCoverageAvailable,
    }) : null
  ), [
    profile,
    lifecycleData?.intents,
    lifecycleData?.approvals,
    lifecycleData?.outcomes,
    runnersQuery.data?.items,
    attempts,
    staleAttemptIds,
    bypassCoverageAvailable,
  ]);

  const loading = profileQuery.isLoading;
  const error = Boolean(
    profileQuery.error ||
    lifecycleQuery.error ||
    runnersQuery.error,
  );

  function refresh() {
    profileQuery.refetch();
    lifecycleQuery.refetch();
    runnersQuery.refetch();
  }

  return (
    <main className="agents-screen agent-detail-screen" aria-label="Agent detail control">
      <AgentDetailHero
        detail={detail}
        error={error}
        loading={loading}
        windowDays={windowDays}
        onRefresh={refresh}
      />

      {loading ? (
        <section className="agents-empty-card">
          <div className="agents-eyebrow">Loading</div>
          <h2>Fetching managed profile.</h2>
          <p>Profile config, proof state, and runner attempts are loading.</p>
        </section>
      ) : null}

      {!loading && !detail ? (
        <section className="agents-empty-card">
          <div className="agents-eyebrow">Unavailable</div>
          <h2>Agent profile could not be opened.</h2>
          <p>Return to the fleet and confirm the managed profile still exists in this project.</p>
          <DashboardButtonLink href="/agents" variant="primary">
            Back to agents
          </DashboardButtonLink>
        </section>
      ) : null}

      {detail ? (
        <section className="agent-detail-layout">
          <div className="agent-detail-main">
            <ConfigSummaryPanel detail={detail} />
            <ActionHistoryPanel detail={detail} />
          </div>
          <div className="agent-detail-side">
            <ProofPanel detail={detail} />
            <RunnerPanel detail={detail} />
          </div>
        </section>
      ) : null}
    </main>
  );
}
