"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";

import { DashboardButtonLink } from "@/components/dashboard-button";
import { getCaptureHealth, listAgentProfiles } from "@/lib/api";
import type { AgentProfileResponse } from "@/lib/api";
import { loadActionsLifecycleFeed } from "@/lib/actions-lifecycle-feed";
import {
  useActionRunners,
} from "@/lib/hooks";
import { buildFleetView } from "@/lib/agent-fleet";
import { dashboardWindowDays } from "@/lib/dashboard-window";
import { useDashboardStore } from "@/lib/store";
import {
  getAgentControlSetupStatus,
  type AgentControlSetupStatus,
} from "@/lib/agent-control-setup-status";

import { AgentsFleetHero } from "./AgentsFleetHero";
import { AgentsFleetWorkspace } from "./AgentsFleetWorkspace";

function EmptyFirstRun() {
  return (
    <section className="agents-empty-card">
      <div className="agents-eyebrow">First protected agent</div>
      <h2>Protect one real agent action first.</h2>
      <p>
        Create a managed agent profile, route one risky action through Zroky, connect a protected runner, and verify the source-of-record proof.
      </p>
      <div className="agents-empty-path" aria-label="First protected action path">
        <div>
          <span>01</span>
          <strong>Create agent</strong>
          <small>Name the managed agent profile.</small>
        </div>
        <div>
          <span>02</span>
          <strong>Run action</strong>
          <small>Use the verified-action path.</small>
        </div>
        <div>
          <span>03</span>
          <strong>Runner executes</strong>
          <small>Isolated credentials stay with the runner.</small>
        </div>
        <div>
          <span>04</span>
          <strong>Receipt proves it</strong>
          <small>Verifier resolves matched, mismatched, or not verified.</small>
        </div>
      </div>
    </section>
  );
}

function AgentsSetupActivationBanner({
  runnerNeedsRecovery,
  status,
}: {
  runnerNeedsRecovery: boolean;
  status: AgentControlSetupStatus;
}) {
  const operationalChecks = runnerNeedsRecovery ? [{
    id: "runner_health",
    label: "Restore protected runner",
    done: false,
    detail: "Runner configuration is saved, but no configured runner has an active heartbeat.",
  }] : [];
  const visibleChecks = [
    ...operationalChecks,
    ...status.checks.filter((check) => !check.done),
  ].slice(0, 4);
  const completionLabel = runnerNeedsRecovery
    ? `${status.completedCount}/${status.totalCount} configured; runner offline`
    : `${status.completedCount}/${status.totalCount} complete`;
  const setupHref = status.setupAgentId
    ? `/agents/setup?agentId=${encodeURIComponent(status.setupAgentId)}`
    : "/agents/setup";
  const primaryHref = status.ctaHref === "/agents/setup" ? setupHref : status.ctaHref;
  return (
    <section className="agents-setup-banner" aria-label="Agent control setup status">
      <div className="agents-panel-head">
        <div>
          <span>Setup activation</span>
          <strong>{status.title}</strong>
        </div>
        <span className="agents-table-count">{completionLabel}</span>
      </div>
      <div className="agents-setup-banner-body">
        <div className="agents-setup-banner-copy">
          <p>{status.body}</p>
          <div className="agents-setup-banner-progress" aria-label="Agent setup completion">
            <span>{status.progressPct}% ready</span>
            <div>
              <i style={{ width: `${status.progressPct}%` }} />
            </div>
          </div>
          <div className="agents-setup-banner-actions">
            <DashboardButtonLink href={primaryHref} icon={<ArrowRight />} iconPosition="right" variant="primary">
              {status.ctaLabel}
            </DashboardButtonLink>
            <DashboardButtonLink href={runnerNeedsRecovery ? setupHref : "/integrations"} variant="soft">
              {runnerNeedsRecovery ? "Open runner setup" : "Check connectors"}
            </DashboardButtonLink>
          </div>
        </div>
        <div className="agents-setup-banner-checks">
          {(visibleChecks.length > 0 ? visibleChecks : status.checks.slice(-4)).map((check) => (
            <div key={check.id} data-done={check.done ? "true" : "false"}>
              <strong>{check.label}</strong>
              <span>{check.done ? "Ready" : check.detail}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function UnmanagedAgentsNotice({
  count,
  locked,
  promoteHref,
}: {
  count: number;
  locked: boolean;
  promoteHref: string;
}) {
  if (count <= 0) return null;
  return (
    <section className="agents-warning-panel" aria-label="Unmanaged agents observed">
      <div>
        <strong>{count} unmanaged agent{count === 1 ? "" : "s"} observed</strong>
        <span>Actions are happening through telemetry, but these agents are not managed by AgentProfile yet.</span>
      </div>
      <DashboardButtonLink aria-disabled={locked || undefined} href={promoteHref} variant="soft">
        {locked ? "Upgrade to manage" : "Promote first agent"}
      </DashboardButtonLink>
    </section>
  );
}

function setupHrefForAgent(agentName?: string) {
  const trimmed = agentName?.trim();
  return trimmed ? `/agents/setup?agentName=${encodeURIComponent(trimmed)}` : "/agents/setup";
}

export default function AgentsPage() {
  const dateRange = useDashboardStore((state) => state.dateRange);
  const windowDays = useMemo(() => dashboardWindowDays(dateRange), [dateRange]);
  const profilesQuery = useQuery({
    queryKey: ["agents", "profiles"],
    queryFn: ({ signal }) => listAgentProfiles({ limit: 200 }, signal),
    staleTime: 15_000,
    refetchInterval: 30_000,
  });
  const lifecycleQuery = useQuery({
    queryKey: ["agents", "lifecycle-summary", windowDays, 200],
    queryFn: ({ signal }) => loadActionsLifecycleFeed({ days: windowDays, limit: 200 }, signal),
    staleTime: 15_000,
    refetchInterval: 30_000,
  });
  const runnersQuery = useActionRunners();
  const captureHealthQuery = useQuery({
    queryKey: ["agents", "capture-health"],
    queryFn: ({ signal }) => getCaptureHealth(signal),
    staleTime: 15_000,
    refetchInterval: 30_000,
  });

  const profiles = useMemo(() => profilesQuery.data?.items ?? [], [profilesQuery.data?.items]);
  const lifecycleSummary = lifecycleQuery.data?.summary ?? null;
  const lifecycleData = lifecycleSummary?.data;
  const attempts = useMemo(
    () => lifecycleData?.attempts ?? lifecycleData?.stale_attempts ?? [],
    [lifecycleData?.attempts, lifecycleData?.stale_attempts],
  );
  const staleAttemptIds = useMemo(
    () => (lifecycleData?.stale_attempts ?? []).map((attempt) => attempt.attempt_id),
    [lifecycleData?.stale_attempts],
  );
  const sourceSummary = lifecycleData?.source_summary;
  const bypassCoverageAvailable = Boolean(
    (sourceSummary?.successful_pollers ?? 0) > 0,
  );
  const fleet = useMemo(() => buildFleetView({
    profiles,
    profileMeta: profilesQuery.data ?? null,
    intents: lifecycleData?.intents ?? [],
    decisions: lifecycleData?.approvals ?? [],
    outcomes: lifecycleData?.outcomes ?? [],
    runners: runnersQuery.data?.items ?? [],
    attempts,
    staleAttemptIds,
    mutations: lifecycleData?.mutations ?? [],
    bypassCoverageAvailable,
  }), [
    profiles,
    profilesQuery.data,
    lifecycleData?.intents,
    lifecycleData?.approvals,
    lifecycleData?.outcomes,
    runnersQuery.data?.items,
    attempts,
    staleAttemptIds,
    lifecycleData?.mutations,
    bypassCoverageAvailable,
  ]);

  const loading = profilesQuery.isLoading;
  const error = Boolean(profilesQuery.error);
  const degradedFeeds = [
    lifecycleQuery.error && "Action lifecycle",
    lifecycleSummary?.sources.outcomes === false && "Proof feed",
    lifecycleSummary?.sources.source_summary === false && "Bypass feed",
    runnersQuery.error && "Runner feed",
    captureHealthQuery.error && "Capture health",
  ].filter(Boolean) as string[];
  const setupStatus = getAgentControlSetupStatus(
    profiles as AgentProfileResponse[],
    captureHealthQuery.data ?? null,
  );
  const setupPrimaryActive = !setupStatus.complete && setupStatus.ctaHref === "/agents/setup";
  const firstTelemetryRow = fleet.rows.find((row) => row.kind === "telemetry") ?? null;

  function refresh() {
    profilesQuery.refetch();
    lifecycleQuery.refetch();
    runnersQuery.refetch();
    captureHealthQuery.refetch();
  }

  return (
    <main className="agents-screen" aria-label="Agents control cockpit">
      <AgentsFleetHero
        fleet={fleet}
        loading={loading}
        error={error}
        degradedFeeds={degradedFeeds}
        setupIncomplete={setupPrimaryActive}
        windowDays={windowDays}
        onRefresh={refresh}
      />

      {!setupStatus.complete ? (
        <AgentsSetupActivationBanner
          status={setupStatus}
          runnerNeedsRecovery={fleet.totals.awaitingRunner > 0 && fleet.runners.online === 0}
        />
      ) : null}
      <UnmanagedAgentsNotice
        count={fleet.totals.telemetryOnly}
        locked={fleet.meter.reached}
        promoteHref={setupHrefForAgent(firstTelemetryRow?.agentName)}
      />

      {fleet.rows.length === 0 ? (
        <EmptyFirstRun />
      ) : (
        <AgentsFleetWorkspace
          fleet={fleet}
          promoteLocked={fleet.meter.reached}
        />
      )}
    </main>
  );
}
