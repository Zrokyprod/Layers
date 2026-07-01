"use client";

import { ArrowRight, Bot, Lock, RefreshCw } from "lucide-react";

import { DashboardButton, DashboardButtonLink } from "@/components/dashboard-button";
import {
  type DashboardScaffoldTone,
  DashboardMetricStrip,
  DashboardVerdictHero,
} from "@/components/dashboard-scaffold";
import type { AgentFleetView } from "@/lib/agent-fleet";
import { formatCount } from "@/lib/format";

type AgentsFleetHeroProps = {
  fleet: AgentFleetView;
  loading: boolean;
  error: boolean;
  degradedFeeds?: string[];
  onRefresh: () => void;
};

function heroCopy(fleet: AgentFleetView, error: boolean): {
  tone: DashboardScaffoldTone;
  title: string;
  body: string;
  cta: string;
} {
  if (error) {
    return {
      tone: "danger",
      title: "Agent visibility unavailable",
      body: "One or more agent fleet feeds did not refresh cleanly.",
      cta: "Retry refresh",
    };
  }
  if (fleet.totals.mismatched > 0) {
    return {
      tone: "danger",
      title: "Agent proof mismatch",
      body: `${formatCount(fleet.totals.mismatched)} managed action path has source-of-record proof that does not match.`,
      cta: "Review exceptions",
    };
  }
  if (fleet.totals.held > 0) {
    return {
      tone: "warning",
      title: "Agents need decisions",
      body: `${formatCount(fleet.totals.held)} action is held before execution. Review approvals before letting the fleet continue.`,
      cta: "Review holds",
    };
  }
  if (fleet.totals.notVerified > 0) {
    return {
      tone: "warning",
      title: "Agents need proof",
      body: `${formatCount(fleet.totals.notVerified)} action path is controlled but not verified yet.`,
      cta: "Review proof",
    };
  }
  if (fleet.rows.length === 0) {
    return {
      tone: "setup",
      title: "Setup required",
      body: "Create one managed agent profile, run one protected action, and attach a runner plus verifier.",
      cta: "Add agent",
    };
  }
  return {
    tone: "success",
    title: "Agents controlled",
    body: "Managed profiles, runner attempts, and proof states are visible through the verified-action loop.",
    cta: "Add agent",
  };
}

export function AgentsFleetHero({
  degradedFeeds = [],
  error,
  fleet,
  loading,
  onRefresh,
}: AgentsFleetHeroProps) {
  const copy = heroCopy(fleet, error);
  const capLabel = fleet.meter.cap === -1
    ? `${formatCount(fleet.meter.active)} managed \u00b7 unlimited`
    : `${formatCount(fleet.meter.active)} / ${formatCount(fleet.meter.cap)}`;
  const addDisabled = fleet.meter.reached || loading;

  return (
    <>
      <DashboardVerdictHero
        eyebrow="Agent fleet"
        icon={<Bot aria-hidden="true" size={18} />}
        title={copy.title}
        copy={copy.body}
        tone={copy.tone}
        notices={!error && degradedFeeds.length > 0 ? (
          <span className="dashboard-inline-warning">
            {degradedFeeds.join(" / ")} degraded - core agent data is live.
          </span>
        ) : null}
        actions={(
          <>
            {fleet.meter.reached ? (
              <DashboardButton disabled icon={<Lock />} title="Plan cap reached" variant="soft">
                Upgrade to add agents
              </DashboardButton>
            ) : (
              <DashboardButtonLink
                aria-disabled={addDisabled || undefined}
                href="/agents/setup"
                icon={<ArrowRight />}
                iconPosition="right"
                variant="primary"
              >
                {copy.cta}
              </DashboardButtonLink>
            )}
            <DashboardButton icon={<RefreshCw />} onClick={onRefresh} variant="soft">
              Refresh
            </DashboardButton>
          </>
        )}
      />
      <DashboardMetricStrip
        ariaLabel="Agent fleet summary"
        columns={4}
        metrics={[
          {
            helper: fleet.meter.reached ? "Plan cap reached." : "Managed AgentProfile capacity.",
            label: "Managed agents",
            tone: fleet.meter.reached ? "warning" : fleet.meter.active > 0 ? "success" : "neutral",
            value: capLabel,
          },
          {
            helper: "Actions waiting at the policy gate.",
            label: "Held actions",
            tone: fleet.totals.held > 0 ? "warning" : "success",
            value: formatCount(fleet.totals.held),
          },
          {
            helper: "Protected runners with active heartbeat.",
            label: "Runners online",
            tone: fleet.runners.online > 0 ? "success" : fleet.runners.total > 0 ? "warning" : "neutral",
            value: `${formatCount(fleet.runners.online)} / ${formatCount(fleet.runners.total)}`,
          },
          {
            helper: "Signed receipts linked to managed actions.",
            label: "Receipts generated",
            tone: fleet.totals.receiptReady > 0 ? "success" : "neutral",
            value: formatCount(fleet.totals.receiptReady),
          },
        ]}
      />
    </>
  );
}
