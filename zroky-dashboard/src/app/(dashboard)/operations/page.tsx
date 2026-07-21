"use client";

import { AlertTriangle, CheckCircle2, Clock3, ShieldCheck } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import {
  DashboardMetricStrip,
  DashboardVerdictHero,
  DashboardWorkspace,
  type DashboardMetric,
} from "@/components/dashboard-scaffold";
import { StatusPill } from "@/components/status-pill";
import {
  listFinalApprovalRequirements,
  listFinalIncidents,
  listFinalRuns,
  type FinalApprovalRequirementResponse,
  type FinalIncidentResponse,
  type FinalRunResponse,
} from "@/lib/api";

function countOpenIncidents(items: FinalIncidentResponse[]): number {
  return items.filter((item) => item.status !== "resolved").length;
}

function countPendingApprovals(items: FinalApprovalRequirementResponse[]): number {
  return items.filter((item) => item.status === "pending").length;
}

function formatWhen(value: string | null | undefined): string {
  if (!value) return "-";
  return new Date(value).toISOString().slice(0, 19).replace("T", " ");
}

function latestRunLabel(runs: FinalRunResponse[]): string {
  return runs[0]?.status ?? "none";
}

function errorText(value: unknown): string {
  if (value instanceof Error && value.message.trim()) return value.message;
  if (typeof value === "string" && value.trim()) return value;
  return "API request failed.";
}

function isPermissionError(value: unknown): boolean {
  return /401|403|forbidden|permission|unauthorized/i.test(errorText(value));
}

export default function OperationsPage() {
  const runs = useQuery({ queryKey: ["final-runs"], queryFn: ({ signal }) => listFinalRuns(signal) });
  const incidents = useQuery({ queryKey: ["final-incidents"], queryFn: ({ signal }) => listFinalIncidents(signal) });
  const approvals = useQuery({
    queryKey: ["final-approval-requirements"],
    queryFn: ({ signal }) => listFinalApprovalRequirements(signal),
  });

  const runItems = runs.data?.items ?? [];
  const incidentItems = incidents.data ?? [];
  const approvalItems = approvals.data?.items ?? [];
  const hasError = runs.isError || incidents.isError || approvals.isError;
  const hasPermissionError = isPermissionError(runs.error) || isPermissionError(incidents.error) || isPermissionError(approvals.error);
  const isLoading = runs.isLoading || incidents.isLoading || approvals.isLoading;
  const openIncidents = countOpenIncidents(incidentItems);
  const pendingApprovals = countPendingApprovals(approvalItems);

  const metrics: DashboardMetric[] = [
    {
      id: "runs",
      label: "Runs",
      value: isLoading ? "Loading" : hasError ? "-" : String(runItems.length),
      helper: `Latest status: ${latestRunLabel(runItems)}.`,
      tone: runItems.length > 0 ? "success" : "setup",
    },
    {
      id: "incidents",
      label: "Open incidents",
      value: isLoading ? "Loading" : hasError ? "-" : String(openIncidents),
      helper: "Non-verified outcome snapshots needing operator action.",
      tone: openIncidents > 0 ? "danger" : "success",
    },
    {
      id: "approvals",
      label: "Pending approvals",
      value: isLoading ? "Loading" : hasError ? "-" : String(pendingApprovals),
      helper: "Digest-bound policy approvals waiting for action.",
      tone: pendingApprovals > 0 ? "warning" : "success",
    },
  ];

  return (
    <main className="policies-page operations-page">
      <DashboardVerdictHero
        eyebrow="Operations"
        title={
          hasPermissionError
            ? "Operations access unavailable"
            : hasError
              ? "Operations data unavailable"
              : isLoading
                ? "Loading operations"
                : openIncidents > 0
                  ? "Outcome incidents need review"
                  : "Operations are clear"
        }
        copy="Final runs, incidents, and approval requirements from the live Zroky APIs."
        tone={hasError ? "danger" : openIncidents > 0 ? "danger" : pendingApprovals > 0 ? "warning" : "success"}
        icon={hasError ? <AlertTriangle size={22} /> : <ShieldCheck size={22} />}
        pill={isLoading ? "loading" : hasError ? "error" : "live"}
      />

      <DashboardMetricStrip ariaLabel="Operations metrics" columns={3} metrics={metrics} />

      <DashboardWorkspace
        left={
          <section className="agent-setup-card" aria-labelledby="operations-incidents-title">
            <div>
              <span className="dashboard-eyebrow">Incidents</span>
              <h2 id="operations-incidents-title">Outcome incidents</h2>
            </div>
            {isLoading ? <p>Loading incidents...</p> : null}
            {hasError ? <p>Unable to load incidents from the live API.</p> : null}
            {!isLoading && !hasError && incidentItems.length === 0 ? <p>No incidents found.</p> : null}
            {incidentItems.map((incident) => (
              <article key={incident.id} className="policy-boundary-card">
                <StatusPill value={incident.status} tone={incident.status === "resolved" ? "success" : "danger"} />
                <strong>{String(incident.incident.deviation_type ?? "unknown")}</strong>
                <p>{String(incident.incident.reason ?? "No reason recorded.")}</p>
                <small>{incident.severity} · {formatWhen(incident.created_at)}</small>
              </article>
            ))}
          </section>
        }
        right={
          <aside className="agent-setup-card" aria-labelledby="operations-queue-title">
            <div>
              <span className="dashboard-eyebrow">Queues</span>
              <h2 id="operations-queue-title">Runs, approvals, and recovery</h2>
              <p>Recovery dispatch stays approval-controlled and tied to fresh outcome evidence.</p>
            </div>
            <section aria-label="Runs queue">
              <h3><Clock3 size={16} /> Recent runs</h3>
              {isLoading ? <p>Loading runs...</p> : null}
              {runs.isError ? <p>Unable to load runs from the live API.</p> : null}
              {!isLoading && !runs.isError && runItems.length === 0 ? <p>No runs found.</p> : null}
              {runItems.slice(0, 5).map((run) => (
                <p key={run.id}>{run.workflow_key ?? run.id}: {run.status}</p>
              ))}
            </section>
            <section aria-label="Approvals queue">
              <h3><CheckCircle2 size={16} /> Approval requirements</h3>
              {isLoading ? <p>Loading approval requirements...</p> : null}
              {approvals.isError ? <p>Unable to load approval requirements from the live API.</p> : null}
              {!isLoading && !approvals.isError && approvalItems.length === 0 ? <p>No approval requirements found.</p> : null}
              {approvalItems.slice(0, 5).map((approval) => (
                <p key={approval.id}>{approval.required_role}: {approval.status}</p>
              ))}
            </section>
          </aside>
        }
      />
    </main>
  );
}
