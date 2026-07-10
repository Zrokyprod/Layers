"use client";

import Link from "next/link";
import { AlertTriangle, CheckCircle2, CircleDashed, ExternalLink } from "lucide-react";

import type { HomeSummaryResponse, OutcomeReconciliationSummaryResponse } from "@/lib/api";
import { formatCount } from "@/lib/format";

export type ControlReadiness = {
  ready: boolean;
  detail: string;
  href: string;
};

type Health = NonNullable<NonNullable<HomeSummaryResponse["data"]>["control_health"]>;

export function buildControlReadiness(health: Health | null, receipts: number): Record<string, ControlReadiness> {
  if (!health) {
    return {
      agents: { ready: false, detail: "Control health unavailable", href: "/agents" },
      policy: { ready: false, detail: "Control health unavailable", href: "/policies" },
      path: { ready: false, detail: "Control health unavailable", href: "/integrations" },
      proof: { ready: false, detail: "Control health unavailable", href: "/integrations" },
      receipt: { ready: false, detail: "Control health unavailable", href: "/evidence" },
    };
  }
  const policyReady = health.active_agents > 0
    && health.policy_enforced_agents >= health.active_agents
    && health.runtime_enabled
    && !health.kill_switch_enabled;
  const mcpReady = health.mcp_gateway_status === "active" && health.mcp_gateway_test_status === "succeeded";
  return {
    agents: {
      ready: health.active_agents > 0 && health.configured_action_packs > 0,
      detail: `${formatCount(health.active_agents)} active / ${formatCount(health.configured_action_packs)} action packs`,
      href: "/agents",
    },
    policy: {
      ready: policyReady,
      detail: health.kill_switch_enabled
        ? "Kill switch is enabled"
        : `${formatCount(health.policy_enforced_agents)} of ${formatCount(health.active_agents)} agents enforced`,
      href: "/policies",
    },
    path: {
      ready: mcpReady || health.online_runners > 0,
      detail: mcpReady ? "MCP gateway active and tested" : `${formatCount(health.online_runners)} runners online`,
      href: mcpReady ? "/integrations?connector=mcp_upstream" : "/agents",
    },
    proof: {
      ready: health.tested_sor_connectors > 0,
      detail: `${formatCount(health.tested_sor_connectors)} of ${formatCount(health.active_sor_connectors)} SOR connectors tested`,
      href: "/integrations",
    },
    receipt: {
      ready: receipts > 0,
      detail: receipts > 0 ? `${formatCount(receipts)} signed receipts generated` : "No signed receipt yet",
      href: "/evidence",
    },
  };
}

export function firstMissingControl(readiness: Record<string, ControlReadiness>): ControlReadiness | null {
  return Object.values(readiness).find((item) => !item.ready) ?? null;
}

export function ControlHealthPanel({
  health,
  receipts,
  proof,
}: {
  health: Health | null;
  receipts: number;
  proof: OutcomeReconciliationSummaryResponse | null;
}) {
  const readiness = buildControlReadiness(health, receipts);
  const checks = [
    ["Agent control", readiness.agents],
    ["Policy enforcement", readiness.policy],
    ["Execution path", readiness.path],
    ["Proof source", readiness.proof],
    ["Signed receipt", readiness.receipt],
  ] as const;
  const proofStates = [
    ["Matched", proof?.matched ?? 0, "success"],
    ["Mismatch", proof?.mismatched ?? 0, "danger"],
    ["Pending", proof?.pending ?? 0, "warning"],
    ["Partial", proof?.partial ?? 0, "warning"],
    ["Unverifiable", proof?.unverifiable ?? 0, "neutral"],
  ] as const;

  return (
    <section className="mc-control-health" aria-label="Pilot control health">
      <div className="mc-section-head">
        <div>
          <p className="mc-eyebrow">Pilot readiness</p>
          <h2>Control health</h2>
        </div>
        <span className="mc-muted">Durable project state</span>
      </div>
      <div className="mc-control-health-grid">
        <div className="mc-readiness-list">
          {checks.map(([label, item]) => (
            <Link key={label} href={item.href} className="mc-readiness-row" data-state={item.ready ? "ready" : "missing"}>
              {item.ready ? <CheckCircle2 aria-hidden="true" /> : health ? <AlertTriangle aria-hidden="true" /> : <CircleDashed aria-hidden="true" />}
              <span><strong>{label}</strong><small>{item.detail}</small></span>
              <ExternalLink aria-hidden="true" />
            </Link>
          ))}
        </div>
        <div className="mc-proof-health" aria-label="Proof state summary">
          <div>
            <p className="mc-eyebrow">Proof outcomes</p>
            <strong>{formatCount(proof?.total ?? 0)} checks</strong>
          </div>
          <div className="mc-proof-state-grid">
            {proofStates.map(([label, count, tone]) => (
              <Link href="/outcomes" key={label} data-tone={tone}>
                <strong>{formatCount(count)}</strong>
                <span>{label}</span>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
