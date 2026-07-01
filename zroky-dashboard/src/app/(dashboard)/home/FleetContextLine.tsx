"use client";

import Link from "next/link";
import { Bot, CheckCircle2, ShieldCheck } from "lucide-react";

import type { AgentFleetView } from "@/lib/agent-fleet";
import { formatCount } from "@/lib/format";

type FleetContextLineProps = {
  fleet: AgentFleetView;
  loading: boolean;
};

export function FleetContextLine({ fleet, loading }: FleetContextLineProps) {
  if (loading || fleet.mode !== "fleet") {
    return null;
  }

  return (
    <section className="mc-fleet-line" aria-label="Agent fleet context">
      <Link href="/agents" className="mc-fleet-link">
        <Bot aria-hidden="true" size={15} />
        <strong>{formatCount(fleet.totals.managedProfiles)}</strong>
        <span>managed agents</span>
      </Link>
      <Link href="/approvals" className="mc-fleet-link" data-tone={fleet.totals.held > 0 ? "warning" : "success"}>
        <ShieldCheck aria-hidden="true" size={15} />
        <strong>{formatCount(fleet.totals.held)}</strong>
        <span>held actions</span>
      </Link>
      <Link href="/agents" className="mc-fleet-link" data-tone={fleet.runners.online > 0 ? "success" : "warning"}>
        <CheckCircle2 aria-hidden="true" size={15} />
        <strong>{formatCount(fleet.runners.online)} / {formatCount(fleet.runners.total)}</strong>
        <span>runners online</span>
      </Link>
    </section>
  );
}
