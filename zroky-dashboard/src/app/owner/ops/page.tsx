"use client";

import Link from "next/link";
import { useMemo, type ReactNode } from "react";

import {
  useAuditLog,
  useOwnerBillingSummary,
  useOwnerHealth,
  useOwnerProjects,
  useOwnerStats,
  useOwnerSupportTickets,
  useUpdateOwnerSupportTicket,
} from "@/lib/hooks";
import type { OwnerSupportTicketItem } from "@/lib/owner-api";

function MetricCard({
  label,
  value,
  sub,
  tone = "default",
}: {
  label: string;
  value: string | number;
  sub?: string;
  tone?: "default" | "accent" | "warn" | "danger";
}) {
  return (
    <div className={`owner-stat-card owner-ops-metric owner-ops-metric-${tone}`}>
      <span className="owner-stat-label">{label}</span>
      <span className="owner-stat-value">{value}</span>
      {sub ? <span className="owner-stat-sub">{sub}</span> : null}
    </div>
  );
}

function Badge({ tone, children }: { tone: "ok" | "warn" | "danger" | "neutral" | "accent"; children: ReactNode }) {
  return <span className={`owner-ops-badge owner-ops-badge-${tone}`}>{children}</span>;
}

function PlanRow({ label, value, total }: { label: string; value: number; total: number }) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0;
  return (
    <div className="owner-ops-plan-row">
      <div className="owner-ops-plan-main">
        <span>{label}</span>
        <strong>{value.toLocaleString()}</strong>
      </div>
      <div className="owner-ops-bar-track">
        <span className="owner-ops-bar-fill" style={{ width: `${Math.max(4, pct)}%` }} />
      </div>
      <span className="hint">{pct}% of active plan tenants</span>
    </div>
  );
}

function TicketStatusBadge({ ticket }: { ticket: OwnerSupportTicketItem }) {
  const tone = ticket.status === "resolved" ? "ok" : ticket.priority === "urgent" || ticket.priority === "high" ? "danger" : "warn";
  return <Badge tone={tone}>{ticket.priority} · {ticket.status}</Badge>;
}

function formatDate(value: string) {
  return new Date(value).toLocaleString();
}

export default function FounderOpsPage() {
  const statsQuery = useOwnerStats();
  const healthQuery = useOwnerHealth();
  const billingQuery = useOwnerBillingSummary();
  const supportQuery = useOwnerSupportTickets({ limit: 8, status: "open" });
  const projectsQuery = useOwnerProjects(8, 0);
  const auditQuery = useAuditLog({ limit: 8 });
  const updateTicket = useUpdateOwnerSupportTicket();

  const stats = statsQuery.data ?? null;
  const billing = billingQuery.data ?? null;
  const health = healthQuery.data ?? null;
  const support = supportQuery.data ?? null;
  const auditEntries = auditQuery.data?.entries ?? [];
  const error = statsQuery.error?.message ?? billingQuery.error?.message ?? supportQuery.error?.message ?? projectsQuery.error?.message ?? auditQuery.error?.message ?? healthQuery.error?.message ?? "";

  const lastUpdated = useMemo(() => {
    const timestamps = [
      statsQuery.dataUpdatedAt,
      billingQuery.dataUpdatedAt,
      supportQuery.dataUpdatedAt,
      projectsQuery.dataUpdatedAt,
      auditQuery.dataUpdatedAt,
      healthQuery.dataUpdatedAt,
    ].filter(Boolean);
    return timestamps.length ? new Date(Math.max(...timestamps)) : null;
  }, [auditQuery.dataUpdatedAt, billingQuery.dataUpdatedAt, healthQuery.dataUpdatedAt, projectsQuery.dataUpdatedAt, statsQuery.dataUpdatedAt, supportQuery.dataUpdatedAt]);

  const topProjects = useMemo(() => {
    const projects = projectsQuery.data?.projects ?? [];
    return [...projects].sort((a, b) => b.total_cost_usd - a.total_cost_usd).slice(0, 5);
  }, [projectsQuery.data?.projects]);

  const loading = statsQuery.isLoading || billingQuery.isLoading || supportQuery.isLoading;
  const overdue = billing?.overdue ?? 0;
  const canceled = billing?.canceled ?? 0;
  const openTickets = support?.total ?? 0;
  const dangerTickets = support?.items.filter((ticket) => ticket.priority === "urgent" || ticket.priority === "high").length ?? 0;
  const systemTone = health?.maintenance_mode ? "warn" : health?.overall === "ok" ? "ok" : health?.overall === "down" ? "danger" : "warn";

  const refreshAll = () => {
    void statsQuery.refetch();
    void healthQuery.refetch();
    void billingQuery.refetch();
    void supportQuery.refetch();
    void projectsQuery.refetch();
    void auditQuery.refetch();
  };

  const resolveTicket = async (ticketId: string) => {
    await updateTicket.mutateAsync({ ticketId, body: { status: "resolved" } });
  };

  return (
    <div className="owner-page owner-ops-page">
      <div className="owner-page-header">
        <div>
          <h2 className="owner-page-title">Founder Ops Console</h2>
          <p className="hint">Revenue, support, platform risk, tenant health and operating controls in one founder-grade view.</p>
        </div>
        <div className="owner-page-header-actions">
          {lastUpdated ? <span className="hint">Updated {lastUpdated.toLocaleTimeString()}</span> : null}
          <button className="btn btn-soft" onClick={refreshAll} disabled={loading}>Refresh all</button>
        </div>
      </div>

      {error ? <div className="alert-strip alert-strip-error">{error}</div> : null}

      <div className="owner-ops-hero panel">
        <div>
          <p className="owner-section-label">Operating posture</p>
          <h3 className="owner-ops-hero-title">{health?.maintenance_mode ? "Maintenance window active" : "Founder command center is live"}</h3>
          <p className="hint">Use this as the default daily console before jumping into users, projects, pricing or audit trails.</p>
        </div>
        <div className="owner-ops-hero-status">
          <Badge tone={systemTone}>{health?.overall ?? "checking"}</Badge>
          <span className="hint">{health?.services.length ?? 0} services monitored</span>
        </div>
      </div>

      <div className="owner-stat-grid">
        <MetricCard label="Active subscriptions" value={(billing?.total_subscriptions ?? 0).toLocaleString()} sub={`${overdue.toLocaleString()} overdue · ${canceled.toLocaleString()} canceled`} tone={overdue > 0 ? "warn" : "accent"} />
        <MetricCard label="Open support" value={openTickets.toLocaleString()} sub={`${dangerTickets.toLocaleString()} high-priority in current queue`} tone={dangerTickets > 0 ? "danger" : "default"} />
        <MetricCard label="7d platform cost" value={stats ? `$${stats.cost_last_7d_usd.toLocaleString(undefined, { maximumFractionDigits: 2 })}` : "—"} sub={stats ? `${stats.calls_last_7d.toLocaleString()} calls in last 7d` : "Waiting for stats"} tone="accent" />
        <MetricCard label="Active users 7d" value={(stats?.active_users_last_7d ?? 0).toLocaleString()} sub={stats ? `${stats.total_users.toLocaleString()} total users` : "Waiting for stats"} />
      </div>

      <div className="owner-ops-grid">
        <div className="panel owner-ops-panel">
          <div className="panel-header">Subscription mix <Link href="/owner/pricing" className="owner-row-link">Manage pricing →</Link></div>
          <div className="owner-ops-list">
            {(billing?.by_plan ?? []).length === 0 ? <p className="hint">No active subscription plans yet.</p> : null}
            {(billing?.by_plan ?? []).map((plan) => (
              <PlanRow key={plan.slug} label={plan.plan} value={plan.tenant_count} total={billing?.total_subscriptions ?? 0} />
            ))}
          </div>
        </div>

        <div className="panel owner-ops-panel">
          <div className="panel-header">Lifecycle risk</div>
          <div className="owner-ops-status-grid">
            {(billing?.by_status ?? []).length === 0 ? <p className="hint">No subscription statuses recorded.</p> : null}
            {(billing?.by_status ?? []).map((row) => (
              <div key={row.status} className="owner-ops-status-card">
                <span className="owner-stat-label">{row.status || "unknown"}</span>
                <strong>{row.count.toLocaleString()}</strong>
              </div>
            ))}
          </div>
          <div className="owner-ops-actions">
            <Link href="/owner/users" className="btn btn-soft">Users</Link>
            <Link href="/owner/projects" className="btn btn-soft">Projects</Link>
            <Link href="/owner/rate-limits" className="btn btn-soft">Rate limits</Link>
          </div>
        </div>
      </div>

      <div className="owner-ops-grid owner-ops-grid-wide-left">
        <div className="panel owner-ops-panel">
          <div className="panel-header">Support command queue</div>
          <div className="owner-ops-ticket-list">
            {(support?.items ?? []).length === 0 ? <p className="hint">No open support tickets.</p> : null}
            {(support?.items ?? []).map((ticket) => (
              <div key={ticket.ticket_id} className="owner-ops-ticket">
                <div className="owner-ops-ticket-main">
                  <div>
                    <strong>{ticket.title}</strong>
                    <p className="hint">{ticket.category ?? "general"} · {ticket.message_count} messages · {formatDate(ticket.created_at)}</p>
                  </div>
                  <TicketStatusBadge ticket={ticket} />
                </div>
                <div className="owner-ops-ticket-foot">
                  <span className="owner-td-mono">{ticket.tenant_id ?? "tenant:unknown"}</span>
                  <button className="btn btn-soft" onClick={() => void resolveTicket(ticket.ticket_id)} disabled={updateTicket.isPending}>Resolve</button>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="panel owner-ops-panel">
          <div className="panel-header">Top tenant spend</div>
          <div className="owner-ops-list">
            {topProjects.length === 0 ? <p className="hint">No projects found.</p> : null}
            {topProjects.map((project) => (
              <Link key={project.id} href={`/owner/projects/${project.id}`} className="owner-ops-project-row">
                <span>{project.name}</span>
                <strong>${project.total_cost_usd.toLocaleString(undefined, { maximumFractionDigits: 2 })}</strong>
              </Link>
            ))}
          </div>
        </div>
      </div>

      <div className="panel owner-ops-panel">
        <div className="panel-header">Recent owner audit trail <Link href="/owner/audit" className="owner-row-link">View all →</Link></div>
        <div className="owner-table-wrap owner-ops-audit-wrap">
          <table className="owner-table">
            <thead>
              <tr>
                {['Time', 'Action', 'Actor', 'Tenant'].map((header) => <th key={header} className="owner-th">{header}</th>)}
              </tr>
            </thead>
            <tbody>
              {auditEntries.length === 0 ? <tr><td colSpan={4} className="owner-td owner-td-empty">No audit entries found.</td></tr> : null}
              {auditEntries.map((entry) => (
                <tr key={entry.id} className="owner-tr">
                  <td className="owner-td owner-td-ts">{formatDate(entry.created_at)}</td>
                  <td className="owner-td"><code className="owner-action-code">{entry.action}</code></td>
                  <td className="owner-td owner-td-truncate">{entry.actor_subject ?? "—"}</td>
                  <td className="owner-td-mono">{entry.tenant_id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
