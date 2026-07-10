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
  setupIncomplete?: boolean;
  onRefresh: () => void;
};

function heroCopy(fleet: AgentFleetView, error: boolean): {
  tone: DashboardScaffoldTone;
  title: string;
  body: string;
  cta: string;
  ctaHref: string;
} {
  if (error) {
    return {
      tone: "danger",
      title: "Agent visibility unavailable",
      body: "One or more agent fleet feeds did not refresh cleanly.",
      cta: "Retry refresh",
      ctaHref: "/agents",
    };
  }
  if (fleet.totals.bypassed > 0) {
    return {
      tone: "danger",
      title: "Agent control bypass detected",
      body: `${formatCount(fleet.totals.bypassed)} connected source mutation${fleet.totals.bypassed === 1 ? "" : "s"} happened without a matching protected action receipt.`,
      cta: "Review bypass",
      ctaHref: "/actions?filter=bypassed",
    };
  }
  if (fleet.totals.mismatched > 0) {
    return {
      tone: "danger",
      title: "Agent proof mismatch",
      body: `${formatCount(fleet.totals.mismatched)} managed action path has source-of-record proof that does not match.`,
      cta: "Review exceptions",
      ctaHref: "/actions?filter=mismatched",
    };
  }
  if (fleet.totals.held > 0) {
    return {
      tone: "warning",
      title: "Agents need decisions",
      body: `${formatCount(fleet.totals.held)} action is held before execution. Review approvals before letting the fleet continue.`,
      cta: "Review holds",
      ctaHref: "/approvals",
    };
  }
  if (fleet.totals.sequenceRisk > 0) {
    return {
      tone: "warning",
      title: "Sequence risk caught",
      body: `${formatCount(fleet.totals.sequenceRisk)} agent action sequence matched a cross-action risk pattern before execution.`,
      cta: "Review signals",
      ctaHref: "/approvals",
    };
  }
  if (fleet.totals.notVerified > 0) {
    return {
      tone: "warning",
      title: "Agents need proof",
      body: `${formatCount(fleet.totals.notVerified)} action path is controlled but not verified yet.`,
      cta: "Review proof",
      ctaHref: "/actions?filter=not_verified",
    };
  }
  if (fleet.rows.length === 0) {
    return {
      tone: "setup",
      title: "Setup required",
      body: "Create one managed agent profile, run one protected action, and attach a runner plus verifier.",
      cta: "Add agent",
      ctaHref: "/agents/setup",
    };
  }
  return {
    tone: "success",
    title: "Agents controlled",
    body: "Managed profiles, runner attempts, and proof states are visible through the verified-action loop.",
    cta: "Add agent",
    ctaHref: "/agents/setup",
  };
}

export function AgentsFleetHero({
  degradedFeeds = [],
  error,
  fleet,
  loading,
  onRefresh,
  setupIncomplete = false,
}: AgentsFleetHeroProps) {
  const copy = heroCopy(fleet, error);
  const capLabel = fleet.meter.cap === -1
    ? `${formatCount(fleet.meter.active)} managed \u00b7 unlimited`
    : fleet.meter.active > fleet.meter.cap
      ? `${formatCount(fleet.meter.active)} managed \u00b7 limit ${formatCount(fleet.meter.cap)}`
      : `${formatCount(fleet.meter.active)} / ${formatCount(fleet.meter.cap)}`;
  const capHelper = fleet.meter.cap !== -1 && fleet.meter.active > fleet.meter.cap
    ? "Existing profiles exceed the current plan limit; new agents are blocked."
    : fleet.meter.reached
      ? "Plan cap reached."
      : "Managed AgentProfile capacity.";
  const addDisabled = fleet.meter.reached || loading;
  const showPrimaryAction = !setupIncomplete;
  const coverageLabel = fleet.totals.coveragePercent == null
    ? "No coverage"
    : `${fleet.totals.coveragePercent}%`;
  const riskSignalCount = fleet.totals.bypassed + fleet.totals.sequenceRisk;

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
            {showPrimaryAction ? (
              fleet.meter.reached ? (
                <DashboardButton disabled icon={<Lock />} title="Plan cap reached" variant="soft">
                  Upgrade to add agents
                </DashboardButton>
              ) : (
                <DashboardButtonLink
                  aria-disabled={addDisabled || undefined}
                  href={copy.ctaHref}
                  icon={<ArrowRight />}
                  iconPosition="right"
                  variant="primary"
                >
                  {copy.cta}
                </DashboardButtonLink>
              )
            ) : null}
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
            helper: capHelper,
            label: "Managed agents",
            tone: fleet.meter.reached ? "warning" : fleet.meter.active > 0 ? "success" : "neutral",
            value: capLabel,
          },
          {
            helper: "Observed high-risk paths protected by Zroky versus connected bypass feeds.",
            label: "Coverage",
            tone: fleet.totals.bypassed > 0 ? "danger" : fleet.totals.coveragePercent === 100 ? "success" : "warning",
            value: coverageLabel,
          },
          {
            helper: `${formatCount(fleet.totals.bypassed)} bypass / ${formatCount(fleet.totals.sequenceRisk)} sequence-risk.`,
            label: "Risk signals",
            tone: fleet.totals.bypassed > 0 ? "danger" : fleet.totals.sequenceRisk > 0 ? "warning" : "success",
            value: formatCount(riskSignalCount),
          },
          {
            helper: "Protected runners with active heartbeat.",
            label: "Runners online",
            tone: fleet.runners.online > 0 ? "success" : fleet.runners.total > 0 ? "warning" : "neutral",
            value: `${formatCount(fleet.runners.online)} / ${formatCount(fleet.runners.total)}`,
          },
        ]}
      />
    </>
  );
}
