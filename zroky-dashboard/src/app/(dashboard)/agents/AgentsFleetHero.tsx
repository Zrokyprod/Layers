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
  windowDays: number;
  onRefresh: () => void;
};

function heroCopy(fleet: AgentFleetView, error: boolean, setupIncomplete: boolean): {
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
      ctaHref: "/actions?filter=needs_action",
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
  if (fleet.totals.awaitingRunner > 0) {
    return {
      tone: "warning",
      title: "Agents waiting for runner",
      body: `${formatCount(fleet.totals.awaitingRunner)} authorized action${fleet.totals.awaitingRunner === 1 ? " has" : "s have"} no healthy protected runner attempt yet.`,
      cta: "Restore runner",
      ctaHref: "/agents/setup",
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
      ctaHref: "/actions?filter=needs_action",
    };
  }
  if (setupIncomplete) {
    return {
      tone: "warning",
      title: "Agent control incomplete",
      body: "Managed profiles exist, but policy, execution, verification, or first-action proof still needs activation.",
      cta: "Continue setup",
      ctaHref: "/agents/setup",
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
  windowDays,
}: AgentsFleetHeroProps) {
  const copy = heroCopy(fleet, error, setupIncomplete);
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
  const showPrimaryAction = fleet.meter.reached || !setupIncomplete || [
    fleet.totals.bypassed,
    fleet.totals.mismatched,
    fleet.totals.held,
    fleet.totals.awaitingRunner,
    fleet.totals.sequenceRisk,
    fleet.totals.notVerified,
  ].some((count) => count > 0);
  const coverageLabel = fleet.totals.coveragePercent == null
    ? fleet.totals.coverageAvailable ? "No activity" : "Not covered"
    : `${fleet.totals.coveragePercent}%`;
  const riskSignalCount = fleet.totals.bypassed + fleet.totals.sequenceRisk;
  const riskSignalLabel = riskSignalCount > 0
    ? formatCount(riskSignalCount)
    : fleet.totals.coverageAvailable
      ? "0"
      : "Not covered";

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
                <DashboardButtonLink href="/settings/billing" icon={<Lock />} variant="soft">
                  Review plan
                </DashboardButtonLink>
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
            helper: fleet.totals.coverageAvailable
              ? `Protected versus bypassed actions in the selected ${windowDays}-day window.`
              : "No source mutation feed is connected; protected-action observations alone do not prove coverage.",
            label: "Coverage",
            tone: !fleet.totals.coverageAvailable
              ? "warning"
              : fleet.totals.bypassed > 0
                ? "danger"
                : fleet.totals.coveragePercent === 100
                  ? "success"
                  : "warning",
            value: coverageLabel,
          },
          {
            helper: fleet.totals.coverageAvailable
              ? `${formatCount(fleet.totals.bypassed)} bypass / ${formatCount(fleet.totals.sequenceRisk)} sequence-risk in ${windowDays} days.`
              : "Sequence checks are visible; bypass detection needs a connected source mutation feed.",
            label: "Risk signals",
            tone: fleet.totals.bypassed > 0
              ? "danger"
              : fleet.totals.sequenceRisk > 0 || !fleet.totals.coverageAvailable
                ? "warning"
                : "success",
            value: riskSignalLabel,
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
