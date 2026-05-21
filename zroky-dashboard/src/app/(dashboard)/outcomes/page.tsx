"use client";

import { useState } from "react";
import {
  AlertCircle,
  ArrowRight,
  BadgeDollarSign,
  BarChart3,
  ChevronDown,
  CircleDollarSign,
  Layers,
  Link2,
  RefreshCw,
  TrendingDown,
  Unlink,
} from "lucide-react";
import { useOutcomeSummary } from "@/lib/hooks";
import type { AttributionClusterRow, OutcomeTypeRow } from "@/lib/api";

// ── Helpers ───────────────────────────────────────────────────────────────────

function usd(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);
}

function outcomeLabel(type: string): string {
  const map: Record<string, string> = {
    refund_issued: "Refunds",
    ticket_escalated: "Escalations",
    human_handoff: "Human Hand-offs",
    churn: "Churn",
    compliance_fine: "Compliance Fines",
    retry_cost: "Retry Costs",
    custom: "Custom",
  };
  return map[type] ?? type;
}

const OUTCOME_COLORS: Record<string, string> = {
  refund_issued: "bg-red-500",
  ticket_escalated: "bg-orange-500",
  human_handoff: "bg-yellow-500",
  churn: "bg-purple-500",
  compliance_fine: "bg-rose-600",
  retry_cost: "bg-blue-500",
  custom: "bg-slate-500",
};

function outcomeColor(type: string): string {
  return OUTCOME_COLORS[type] ?? "bg-slate-500";
}

// ── Sub-components ────────────────────────────────────────────────────────────

function KpiCard({
  icon,
  label,
  value,
  sub,
  highlight,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub?: string;
  highlight?: "red" | "green" | "neutral";
}) {
  const ring =
    highlight === "red"
      ? "border-red-500/40"
      : highlight === "green"
        ? "border-emerald-500/40"
        : "border-border";
  return (
    <div
      className={`rounded-xl border ${ring} bg-card p-5 flex flex-col gap-2 shadow-sm`}
    >
      <div className="flex items-center gap-2 text-muted-foreground text-sm">
        {icon}
        {label}
      </div>
      <div className="text-2xl font-bold tracking-tight">{value}</div>
      {sub && <div className="text-xs text-muted-foreground">{sub}</div>}
    </div>
  );
}

function TypeBar({ row, total }: { row: OutcomeTypeRow; total: number }) {
  const pct = total > 0 ? (row.total_usd / total) * 100 : 0;
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between text-sm">
        <span className="flex items-center gap-2">
          <span
            className={`h-2.5 w-2.5 rounded-full ${outcomeColor(row.outcome_type)}`}
          />
          {outcomeLabel(row.outcome_type)}
          <span className="text-muted-foreground">×{row.count}</span>
        </span>
        <span className="font-medium tabular-nums">{usd(row.total_usd)}</span>
      </div>
      <div className="h-1.5 rounded-full bg-muted overflow-hidden">
        <div
          className={`h-full rounded-full ${outcomeColor(row.outcome_type)}`}
          style={{ width: `${Math.min(pct, 100).toFixed(1)}%` }}
        />
      </div>
    </div>
  );
}

function ClusterRow({ cluster }: { cluster: AttributionClusterRow }) {
  const [open, setOpen] = useState(false);
  const agent = cluster.agent_name ?? "unattributed";
  const detector = cluster.detector ?? "—";
  return (
    <div className="rounded-lg border border-border bg-card overflow-hidden">
      <button
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-muted/50 transition-colors"
        onClick={() => setOpen((v) => !v)}
      >
        <Layers className="h-4 w-4 text-muted-foreground shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="font-medium truncate">{agent}</div>
          <div className="text-xs text-muted-foreground truncate">
            {detector !== "—" ? `Detector: ${detector}` : "No failure match"}
          </div>
        </div>
        <div className="text-right shrink-0 ml-3">
          <div className="font-semibold text-red-500 tabular-nums">
            {usd(cluster.outcome_cost_usd)}
          </div>
          <div className="text-xs text-muted-foreground">
            {cluster.outcome_count} events
          </div>
        </div>
        <ChevronDown
          className={`h-4 w-4 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div className="border-t border-border px-4 py-3 grid grid-cols-2 gap-x-6 gap-y-2 text-sm bg-muted/20">
          <div>
            <span className="text-muted-foreground">Linked failures</span>
            <div className="font-medium">{cluster.failure_count}</div>
          </div>
          <div>
            <span className="text-muted-foreground">Top outcome</span>
            <div className="font-medium">
              {cluster.top_outcome_type
                ? outcomeLabel(cluster.top_outcome_type)
                : "—"}
            </div>
          </div>
          <div>
            <span className="text-muted-foreground">Avg cost / event</span>
            <div className="font-medium">
              {cluster.outcome_count > 0
                ? usd(cluster.outcome_cost_usd / cluster.outcome_count)
                : "—"}
            </div>
          </div>
          <div>
            <span className="text-muted-foreground">Est. monthly savings</span>
            <div className="font-semibold text-emerald-500">
              {usd(cluster.estimated_monthly_savings_usd)}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

const WINDOWS = [7, 14, 30, 90];

export default function OutcomesPage() {
  const [days, setDays] = useState(30);
  const { data, isLoading, isError, refetch, isFetching } =
    useOutcomeSummary(days);

  const total = data?.total_outcome_usd ?? 0;
  const avgPerLinked = data?.avg_cost_per_linked ?? 0;
  const linkedCount = data?.linked_outcome_count ?? 0;
  const unlinkedCount = data?.unlinked_outcome_count ?? 0;
  const totalCount = linkedCount + unlinkedCount;
  const linkedPct =
    totalCount > 0 ? Math.round((linkedCount / totalCount) * 100) : 0;

  const topCluster = data?.by_cluster?.[0];
  const topSavings = topCluster?.estimated_monthly_savings_usd ?? 0;
  const topAgent = topCluster?.agent_name ?? "—";
  const topDetector = topCluster?.detector;

  return (
    <div className="flex flex-col gap-8 p-6 max-w-5xl mx-auto w-full">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <CircleDollarSign className="h-6 w-6 text-red-500" />
            Cost-of-Failure Attribution
          </h1>
          <p className="text-muted-foreground text-sm mt-1">
            Every bad outcome has a price. This is it.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <div className="flex rounded-lg border border-border overflow-hidden text-sm">
            {WINDOWS.map((d) => (
              <button
                key={d}
                onClick={() => setDays(d)}
                className={`px-3 py-1.5 transition-colors ${
                  days === d
                    ? "bg-primary text-primary-foreground font-medium"
                    : "hover:bg-muted text-muted-foreground"
                }`}
              >
                {d}d
              </button>
            ))}
          </div>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="rounded-lg border border-border p-1.5 hover:bg-muted transition-colors disabled:opacity-50"
            title="Refresh"
          >
            <RefreshCw
              className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`}
            />
          </button>
        </div>
      </div>

      {/* Error */}
      {isError && (
        <div className="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-500">
          <AlertCircle className="h-4 w-4 shrink-0" />
          Failed to load outcome data. Check your API connection.
        </div>
      )}

      {/* KPI strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <KpiCard
          icon={<BadgeDollarSign className="h-4 w-4" />}
          label="Total outcome cost"
          value={isLoading ? "—" : usd(total)}
          sub={`Last ${days} days`}
          highlight="red"
        />
        <KpiCard
          icon={<BarChart3 className="h-4 w-4" />}
          label="Avg cost / event"
          value={isLoading ? "—" : usd(avgPerLinked)}
          sub={`${linkedCount} linked events`}
        />
        <KpiCard
          icon={<Link2 className="h-4 w-4" />}
          label="Attribution rate"
          value={isLoading ? "—" : `${linkedPct}%`}
          sub={`${unlinkedCount} unlinked`}
          highlight={linkedPct >= 70 ? "green" : "neutral"}
        />
        <KpiCard
          icon={<TrendingDown className="h-4 w-4 text-emerald-500" />}
          label="Top cluster savings"
          value={isLoading ? "—" : `${usd(topSavings)}/mo`}
          sub={topAgent !== "—" ? `Fix ${topAgent}` : "No clusters yet"}
          highlight="green"
        />
      </div>

      {/* Top insight banner */}
      {!isLoading && topCluster && (
        <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 px-5 py-4 flex flex-col sm:flex-row sm:items-center gap-3">
          <div className="flex-1">
            <div className="font-semibold text-emerald-600 dark:text-emerald-400 text-sm mb-0.5">
              Highest-impact fix
            </div>
            <div className="text-sm">
              <span className="font-medium">{topAgent}</span>
              {topDetector ? (
                <>
                  {" "}
                  — <span className="text-muted-foreground">{topDetector}</span>
                </>
              ) : null}{" "}
              caused{" "}
              <span className="font-medium text-red-500">
                {usd(topCluster.outcome_cost_usd)}
              </span>{" "}
              in {topCluster.outcome_count} outcome
              {topCluster.outcome_count !== 1 ? "s" : ""}. Fixing this prompt →{" "}
              <span className="font-medium text-emerald-500">
                {usd(topSavings)}/mo
              </span>{" "}
              estimated savings.
            </div>
          </div>
          <ArrowRight className="h-4 w-4 text-emerald-500 shrink-0" />
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* By-type breakdown */}
        <div className="rounded-xl border border-border bg-card p-5 flex flex-col gap-4">
          <h2 className="font-semibold flex items-center gap-2">
            <BadgeDollarSign className="h-4 w-4 text-muted-foreground" />
            Cost by outcome type
          </h2>
          {isLoading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-8 rounded bg-muted animate-pulse" />
              ))}
            </div>
          ) : data?.by_type.length ? (
            <div className="flex flex-col gap-3">
              {data.by_type.map((row) => (
                <TypeBar key={row.outcome_type} row={row} total={total} />
              ))}
            </div>
          ) : (
            <div className="text-sm text-muted-foreground">
              No outcome events in this window.
            </div>
          )}
        </div>

        {/* Attribution rate donut-ish */}
        <div className="rounded-xl border border-border bg-card p-5 flex flex-col gap-4">
          <h2 className="font-semibold flex items-center gap-2">
            <Link2 className="h-4 w-4 text-muted-foreground" />
            Attribution coverage
          </h2>
          {isLoading ? (
            <div className="h-32 rounded bg-muted animate-pulse" />
          ) : (
            <div className="flex flex-col gap-4">
              <div className="flex items-center gap-4">
                <div className="relative w-24 h-24 shrink-0">
                  <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
                    <circle
                      cx="18"
                      cy="18"
                      r="15.9"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="3.2"
                      className="text-muted"
                    />
                    <circle
                      cx="18"
                      cy="18"
                      r="15.9"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="3.2"
                      strokeDasharray={`${linkedPct} ${100 - linkedPct}`}
                      strokeLinecap="round"
                      className="text-emerald-500"
                    />
                  </svg>
                  <div className="absolute inset-0 flex items-center justify-center text-sm font-bold">
                    {linkedPct}%
                  </div>
                </div>
                <div className="flex flex-col gap-2 text-sm">
                  <div className="flex items-center gap-2">
                    <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />
                    <span className="text-muted-foreground">Linked</span>
                    <span className="font-medium ml-auto">{linkedCount}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="h-2.5 w-2.5 rounded-full bg-muted-foreground" />
                    <span className="text-muted-foreground">Unlinked</span>
                    <span className="font-medium ml-auto">{unlinkedCount}</span>
                  </div>
                </div>
              </div>
              {unlinkedCount > 0 && (
                <div className="flex items-start gap-2 rounded-lg bg-yellow-500/10 border border-yellow-500/20 px-3 py-2 text-xs text-yellow-600 dark:text-yellow-400">
                  <Unlink className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                  {unlinkedCount} events have no{" "}
                  <code className="mx-0.5 font-mono">call_id</code> — pass it
                  via{" "}
                  <code className="mx-0.5 font-mono">
                    zroky.outcome(call_id=...)
                  </code>{" "}
                  to unlock attribution.
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Cluster table */}
      <div className="flex flex-col gap-3">
        <h2 className="font-semibold flex items-center gap-2">
          <Layers className="h-4 w-4 text-muted-foreground" />
          Clusters — agent × detector
        </h2>
        {isLoading ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-14 rounded-lg bg-muted animate-pulse" />
            ))}
          </div>
        ) : data?.by_cluster.length ? (
          <div className="flex flex-col gap-2">
            {data.by_cluster.map((c, i) => (
              <ClusterRow key={`${c.agent_name}-${c.detector}-${i}`} cluster={c} />
            ))}
          </div>
        ) : (
          <div className="rounded-xl border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
            No attributed clusters yet. Start sending outcomes via
            <code className="mx-1 font-mono text-xs bg-muted px-1.5 py-0.5 rounded">
              zroky.outcome(call_id=..., type=&quot;refund_issued&quot;, amount_usd=49)
            </code>
            to see attribution data here.
          </div>
        )}
      </div>

      {/* SDK quick-start */}
      <div className="rounded-xl border border-border bg-muted/30 p-5 flex flex-col gap-3">
        <h2 className="font-semibold text-sm">SDK quick-start</h2>
        <pre className="text-xs bg-card border border-border rounded-lg px-4 py-3 overflow-x-auto leading-relaxed">
          <code>{`import zroky

result = zroky.call(client.chat.completions.create, ...)

# When a bad outcome occurs downstream:
zroky.outcome(
    call_id=result._zroky_call_id,
    type="refund_issued",
    amount_usd=49.00,
    metadata={"order_id": "ORD-9182"},
)`}</code>
        </pre>
        <p className="text-xs text-muted-foreground">
          Outcomes are fire-and-forget — non-blocking, retries once, never
          throws. Webhook receivers for Stripe, Zendesk, and Salesforce are
          available at{" "}
          <code className="font-mono text-xs">/v1/outcomes/webhooks/*</code>.
        </p>
      </div>
    </div>
  );
}
