"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";

import { DashboardButtonLink } from "@/components/dashboard-button";
import { listAgentProfiles, listUnreceiptedSourceMutations } from "@/lib/api";
import type { AgentProfileResponse } from "@/lib/api";
import {
  useActionIntents,
  useActionRunners,
  useOutcomeReconciliations,
  useProjectActionExecutionAttempts,
  useReliabilityLeaderboard,
  useRuntimePolicyApprovals,
} from "@/lib/hooks";
import { buildFleetView } from "@/lib/agent-fleet";
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
      <div className="agents-empty-actions">
        <DashboardButtonLink href="/agents/setup" icon={<ArrowRight />} iconPosition="right" variant="primary">
          Add agent
        </DashboardButtonLink>
        <DashboardButtonLink href="/agents/setup" variant="soft">
          Open setup
        </DashboardButtonLink>
      </div>
    </section>
  );
}

function AgentsSetupActivationBanner({ status }: { status: AgentControlSetupStatus }) {
  const visibleChecks = status.checks.filter((check) => !check.done).slice(0, 4);
  return (
    <section className="agents-setup-banner" aria-label="Agent control setup status">
      <div className="agents-panel-head">
        <div>
          <span>Setup activation</span>
          <strong>{status.title}</strong>
        </div>
        <span className="agents-table-count">{status.completedCount}/{status.totalCount} complete</span>
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
            <DashboardButtonLink href={status.ctaHref} icon={<ArrowRight />} iconPosition="right" variant="primary">
              {status.ctaLabel}
            </DashboardButtonLink>
            <DashboardButtonLink href="/integrations" variant="soft">
              Check connectors
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
  const profilesQuery = useQuery({
    queryKey: ["agents", "profiles"],
    queryFn: ({ signal }) => listAgentProfiles({ limit: 200 }, signal),
    staleTime: 15_000,
    refetchInterval: 30_000,
  });
  const leaderboardQuery = useReliabilityLeaderboard(100);
  const intentsQuery = useActionIntents({ limit: 200 });
  const approvalsQuery = useRuntimePolicyApprovals("all");
  const outcomesQuery = useOutcomeReconciliations("all", 200);
  const runnersQuery = useActionRunners();
  const attemptsQuery = useProjectActionExecutionAttempts({ limit: 200 });
  const sourceMutationsQuery = useQuery({
    queryKey: ["agents", "source-mutations", "unreceipted"],
    queryFn: ({ signal }) => listUnreceiptedSourceMutations(200, signal),
    staleTime: 15_000,
    refetchInterval: 30_000,
  });
  const staleAttemptsQuery = useProjectActionExecutionAttempts({
    status: ["planned", "claimed", "dispatched", "running"],
    stale: true,
    stale_after_seconds: 600,
    limit: 200,
  });

  const profiles = useMemo(() => profilesQuery.data?.items ?? [], [profilesQuery.data?.items]);
  const attempts = useMemo(() => attemptsQuery.data?.items ?? [], [attemptsQuery.data?.items]);
  const sourceMutations = useMemo(
    () => sourceMutationsQuery.data?.items ?? [],
    [sourceMutationsQuery.data?.items],
  );
  const staleAttemptIds = useMemo(
    () => (staleAttemptsQuery.data?.items ?? []).map((attempt) => attempt.attempt_id),
    [staleAttemptsQuery.data?.items],
  );
  const fleet = useMemo(() => buildFleetView({
    profiles,
    profileMeta: profilesQuery.data ?? null,
    scores: leaderboardQuery.data ?? [],
    intents: intentsQuery.data?.items ?? [],
    decisions: approvalsQuery.data?.items ?? [],
    outcomes: outcomesQuery.data?.items ?? [],
    runners: runnersQuery.data?.items ?? [],
    attempts,
    staleAttemptIds,
    mutations: sourceMutations,
  }), [
    profiles,
    profilesQuery.data,
    leaderboardQuery.data,
    intentsQuery.data?.items,
    approvalsQuery.data?.items,
    outcomesQuery.data?.items,
    runnersQuery.data?.items,
    attempts,
    staleAttemptIds,
    sourceMutations,
  ]);

  const loading = profilesQuery.isLoading;
  const error = Boolean(profilesQuery.error);
  const degradedFeeds = [
    (outcomesQuery.error || leaderboardQuery.error) && "Proof feed",
    runnersQuery.error && "Runner feed",
    attemptsQuery.error && "Attempt feed",
    sourceMutationsQuery.error && "Bypass feed",
    (intentsQuery.error || approvalsQuery.error) && "Action feed",
  ].filter(Boolean) as string[];
  const setupStatus = getAgentControlSetupStatus(profiles as AgentProfileResponse[], null);
  const firstTelemetryRow = fleet.rows.find((row) => row.kind === "telemetry") ?? null;

  function refresh() {
    profilesQuery.refetch();
    leaderboardQuery.refetch();
    intentsQuery.refetch();
    approvalsQuery.refetch();
    outcomesQuery.refetch();
    runnersQuery.refetch();
    attemptsQuery.refetch();
    sourceMutationsQuery.refetch();
    staleAttemptsQuery.refetch();
  }

  return (
    <main className="agents-screen" aria-label="Agents control cockpit">
      <AgentsFleetHero
        fleet={fleet}
        loading={loading}
        error={error}
        degradedFeeds={degradedFeeds}
        onRefresh={refresh}
      />

      {!setupStatus.complete ? <AgentsSetupActivationBanner status={setupStatus} /> : null}
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
          runners={runnersQuery.data?.items ?? []}
          attempts={attempts}
          staleAttemptIds={staleAttemptIds}
          promoteLocked={fleet.meter.reached}
        />
      )}
    </main>
  );
}
