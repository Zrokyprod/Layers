"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  BarChart3,
  BellDot,
  ExternalLink,
  LockKeyhole,
  RotateCcw,
  Search,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";

import {
  assignFinalIncident,
  approveFinalApprovalRequirement,
  compileFinalIncidentRecovery,
  containFinalIncident,
  denyFinalApprovalRequirement,
  executeFinalIncidentRecovery,
  listFinalApprovalRequirements,
  listFinalIncidents,
  listFinalRuns,
  listMyProjects,
  resolveFinalIncidentManually,
  snoozeFinalIncident,
  type FinalApprovalRequirementResponse,
  type FinalIncidentResponse,
  type FinalRunResponse,
} from "@/lib/api";
import { useDashboardStore } from "@/lib/store";

import { operationsRowsCsv } from "./csv";
import styles from "./operations.module.css";

type OpsTab = "attention" | "runs" | "incidents" | "approvals" | "unverifiable" | "recovery";
type OpsSeverity = "P1" | "P2" | "P3";
type OpsKind = "Mismatch" | "Approval" | "Unverifiable" | "Recovery" | "Run";
type UnverifiableReason =
  | "no_connector"
  | "no_sor_trace"
  | "sor_unreachable"
  | "runner_offline"
  | "missing_correlation"
  | "stale_source"
  | "evidence_signer_failed"
  | "observation_missing";
type SavedView =
  | "All"
  | "Critical"
  | "My items"
  | "Last 24h";

type OpsRow = {
  id: string;
  runId: string;
  type: OpsKind;
  severity: OpsSeverity;
  item: string;
  source: string;
  agent: string;
  state: string;
  age: string;
  owner: string;
  action: string;
  href: string;
  expected: string;
  actual: string;
  impact: string;
  digest: string;
  createdAt: string;
  timeline: string[];
  reasonCode?: UnverifiableReason;
};

type AgentStat = {
  agent: string;
  total: number;
  mismatches: number;
  unverifiable: number;
  recovery: number;
  lastSeen: string;
};
type IncidentLocalState = {
  state: "contained" | "snoozed";
  note: string;
  until?: string;
};

const DEMO_OPERATIONS_STORAGE_KEY = "zroky:demo-operations";

const TABS: Array<{ id: OpsTab; label: string }> = [
  { id: "attention", label: "Operator queue" },
  { id: "runs", label: "Runs" },
  { id: "incidents", label: "Incidents" },
  { id: "approvals", label: "Approvals" },
  { id: "unverifiable", label: "Unverifiable" },
  { id: "recovery", label: "Recovery" },
];

const EMPTY_RUNS: FinalRunResponse[] = [];
const EMPTY_INCIDENTS: FinalIncidentResponse[] = [];
const EMPTY_APPROVALS: FinalApprovalRequirementResponse[] = [];
const SAVED_VIEWS: SavedView[] = [
  "All",
  "Critical",
  "My items",
  "Last 24h",
];

function demoOperationsEnabled(): boolean {
  if (typeof window === "undefined") return false;
  const host = window.location.hostname;
  if (host !== "localhost" && host !== "127.0.0.1" && host !== "::1") return false;
  const demoParam = new URLSearchParams(window.location.search).get("demoOperations");
  if (demoParam === "1") {
    window.localStorage.setItem(DEMO_OPERATIONS_STORAGE_KEY, "1");
    return true;
  }
  if (demoParam === "0") {
    window.localStorage.removeItem(DEMO_OPERATIONS_STORAGE_KEY);
    return false;
  }
  return window.localStorage.getItem(DEMO_OPERATIONS_STORAGE_KEY) === "1";
}

function isoMinutesAgo(minutes: number): string {
  return new Date(Date.now() - minutes * 60_000).toISOString();
}

function demoOperationRuns(): FinalRunResponse[] {
  return [
    {
      id: "run_payroll_042",
      project_id: "proj_demo",
      environment: "production",
      idempotency_key: "demo-payroll-042",
      external_run_id: "payroll-export-042",
      intent_id: "intent_payroll_042",
      workflow_key: "Payroll Export WF",
      agent_ref: "payroll-agent",
      status: "mismatch",
      run_digest: "sig:9f42c1a8",
      run: {},
      started_at: isoMinutesAgo(13),
      finished_at: isoMinutesAgo(12),
      created_at: isoMinutesAgo(12),
    },
    {
      id: "run_ref_318",
      project_id: "proj_demo",
      environment: "production",
      idempotency_key: "demo-refund-318",
      external_run_id: "stripe-refund-318",
      intent_id: "intent_refund_318",
      workflow_key: "Stripe Refund WF",
      agent_ref: "refund-agent",
      status: "verified",
      run_digest: "sig:71ad03be",
      run: {},
      started_at: isoMinutesAgo(15),
      finished_at: isoMinutesAgo(14),
      created_at: isoMinutesAgo(14),
    },
    {
      id: "run_quote_117",
      project_id: "proj_demo",
      environment: "production",
      idempotency_key: "demo-quote-117",
      external_run_id: "quote-approval-117",
      intent_id: "intent_quote_117",
      workflow_key: "Quote Approval WF",
      agent_ref: "salesforce-agent",
      status: "unverifiable",
      run_digest: "sig:c03a9a91",
      run: { reason_code: "missing_correlation" },
      started_at: isoMinutesAgo(35),
      finished_at: null,
      created_at: isoMinutesAgo(34),
    },
    {
      id: "run_db_recovery_901",
      project_id: "proj_demo",
      environment: "production",
      idempotency_key: "demo-db-recovery-901",
      external_run_id: "db-recovery-901",
      intent_id: "intent_db_recovery_901",
      workflow_key: "DB Recovery WF",
      agent_ref: "postgres-recovery-agent",
      status: "recovery_failed",
      run_digest: "sig:3fb5d90c",
      run: {},
      started_at: isoMinutesAgo(64),
      finished_at: null,
      created_at: isoMinutesAgo(63),
    },
  ];
}

function demoOperationIncidents(): FinalIncidentResponse[] {
  return [
    {
      id: "inc_payroll_042",
      project_id: "proj_demo",
      environment: "production",
      outcome_graph_id: "run_payroll_042",
      severity: "critical",
      status: "open",
      incident: {
        reason: "Payroll export row count did not match Workday source-of-truth.",
        deviation_type: "Mismatch in payroll export",
        source_system: "Workday Payroll",
        agent_ref: "Payroll Export WF",
        expected: "Agent claimed 1,204 payroll rows exported.",
        impact: "Payroll data may be incomplete until contained and re-verified.",
      },
      created_at: isoMinutesAgo(12),
      resolved_at: null,
    },
  ];
}

function demoOperationApprovals(): FinalApprovalRequirementResponse[] {
  return [
    {
      id: "apr_vendor_118",
      project_id: "proj_demo",
      environment: "production",
      intent_id: "Vendor Payments WF",
      policy_decision_id: "pol_vendor_exception",
      required_role: "finance_owner",
      binding_digest: "sig:e2019c4d",
      status: "pending",
      created_at: isoMinutesAgo(18),
      resolved_at: null,
    },
  ];
}

function text(value: unknown, fallback = "Unknown"): string {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof fallback === "string" && fallback.trim()) return fallback;
  return "Unknown";
}

function recordText(record: Record<string, unknown>, key: string, fallback = "Unknown"): string {
  return text(record[key], fallback);
}

function recordOptionalText(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  return typeof value === "string" ? value : "";
}

function formatAge(value: string | null | undefined): string {
  if (!value) return "-";
  const then = new Date(value).getTime();
  if (!Number.isFinite(then)) return "-";
  const minutes = Math.max(1, Math.round((Date.now() - then) / 60_000));
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours}h ${String(rest).padStart(2, "0")}m` : `${hours}h`;
}

function errorText(value: unknown): string {
  if (value instanceof Error && value.message.trim()) return value.message;
  if (typeof value === "string" && value.trim()) return value;
  return "API request failed.";
}

function isPermissionError(value: unknown): boolean {
  return /401|403|forbidden|permission|unauthorized/i.test(errorText(value));
}

function severityFor(value: string | null | undefined): OpsSeverity {
  const normalized = value?.toLowerCase() ?? "";
  if (["critical", "high", "p1"].some((token) => normalized.includes(token))) return "P1";
  if (["medium", "warning", "p2"].some((token) => normalized.includes(token))) return "P2";
  return "P3";
}

function unverifiableReason(value: string): UnverifiableReason {
  if (value === "no_connector") return value;
  if (value === "sor_unreachable") return value;
  if (value === "runner_offline") return value;
  if (value === "missing_correlation") return value;
  if (value === "stale_source") return value;
  if (value === "evidence_signer_failed") return value;
  if (value === "observation_missing") return value;
  return "no_sor_trace";
}

function runUnverifiableReason(run: FinalRunResponse): UnverifiableReason {
  const candidate =
    recordOptionalText(run.run, "reason_code") ||
    recordOptionalText(run.run, "unverifiable_reason") ||
    recordOptionalText(run.run, "verification_reason") ||
    recordOptionalText(run.run, "failure_reason") ||
    recordOptionalText(run.run, "reason");
  return unverifiableReason(candidate.trim().toLowerCase());
}

function actionForReason(reason: UnverifiableReason): string {
  if (reason === "no_connector") return "Connect source";
  if (reason === "missing_correlation" || reason === "no_sor_trace" || reason === "observation_missing") return "Fix correlation";
  if (reason === "sor_unreachable" || reason === "stale_source") return "Retry read";
  if (reason === "runner_offline") return "Open runner";
  if (reason === "evidence_signer_failed") return "Inspect signer";
  return "Analyze";
}

function detailForReason(reason: UnverifiableReason): string {
  if (reason === "no_connector") return "No read-only source connector is configured for this action.";
  if (reason === "missing_correlation") return "ZROKY could not map the agent claim to a source-of-truth object.";
  if (reason === "sor_unreachable") return "The source-of-truth system could not be reached for an authoritative read.";
  if (reason === "runner_offline") return "The customer runner is offline, so local proof or recovery cannot complete.";
  if (reason === "stale_source") return "The latest source read is stale and cannot prove this outcome.";
  if (reason === "evidence_signer_failed") return "The evidence signer failed before a signed proof bundle could be produced.";
  if (reason === "observation_missing") return "No observation event is attached to this run.";
  return "No conclusive source-of-truth trace is attached to this run.";
}

function runAgent(run: FinalRunResponse): string {
  return run.agent_ref ?? run.workflow_key ?? run.intent_id ?? "Unknown agent";
}

function incidentRow(incident: FinalIncidentResponse): OpsRow {
  const reason = recordText(incident.incident, "reason", "Source-of-truth outcome did not match the agent claim.");
  const deviation = recordText(incident.incident, "deviation_type", "Outcome mismatch");
  const runId = incident.outcome_graph_id || incident.id;
  return {
    id: incident.id,
    runId,
    type: "Mismatch",
    severity: severityFor(incident.severity),
    item: deviation,
    source: recordText(incident.incident, "source_system", incident.environment),
    agent: recordText(incident.incident, "agent_ref", "linked run"),
    state: recordText(incident.incident, "lifecycle_status", incident.status),
    age: formatAge(incident.created_at),
    owner: "Unassigned",
    action: incident.status === "resolved" ? "Open evidence" : "Investigate",
    href: `/operations?incident_id=${encodeURIComponent(incident.id)}`,
    expected: recordText(incident.incident, "expected", "Agent claim should match source-of-truth state."),
    actual: reason,
    impact: recordText(incident.incident, "impact", "Potential business outcome gap until verified or contained."),
    digest: runId,
    createdAt: incident.created_at,
    timeline: ["Incident opened", "Outcome graph compared", "Operator review required"],
  };
}

function approvalRow(approval: FinalApprovalRequirementResponse): OpsRow {
  return {
    id: approval.id,
    runId: approval.intent_id,
    type: "Approval",
    severity: "P1",
    item: `Approval required: ${approval.required_role}`,
    source: approval.environment,
    agent: approval.intent_id,
    state: approval.status,
    age: formatAge(approval.created_at),
    owner: approval.required_role,
    action: approval.status === "pending" ? "Review" : "Open",
    href: `/operations?approval_id=${encodeURIComponent(approval.id)}`,
    expected: "Exact policy-bound payload must be approved before execution.",
    actual: `Waiting for ${approval.required_role} approval.`,
    impact: "Execution remains blocked until digest-bound approval resolves.",
    digest: approval.binding_digest,
    createdAt: approval.created_at,
    timeline: ["Policy required approval", "Binding digest generated", "Approval pending"],
  };
}

function runRow(run: FinalRunResponse): OpsRow {
  const status = run.status.toLowerCase();
  const isFailed = /fail|dead|error|recovery/.test(status);
  const isUnverifiable = /unver|unknown|missing|not_verified/.test(status);
  const reasonCode = isUnverifiable ? runUnverifiableReason(run) : undefined;
  const reasonAction = reasonCode ? actionForReason(reasonCode) : null;
  const reasonDetail = reasonCode ? detailForReason(reasonCode) : null;
  return {
    id: run.id,
    runId: run.id,
    type: isUnverifiable ? "Unverifiable" : isFailed ? "Recovery" : "Run",
    severity: isFailed ? "P2" : isUnverifiable ? "P2" : "P3",
    item: run.workflow_key ?? run.external_run_id ?? run.id,
    source: run.environment,
    agent: runAgent(run),
    state: run.status,
    age: formatAge(run.created_at),
    owner: "Ops",
    action: isFailed ? "Retry" : reasonAction ?? "Open",
    href: `/operations?run_id=${encodeURIComponent(run.id)}`,
    expected: "Run should produce an independently verifiable source-of-truth outcome.",
    actual: reasonDetail ?? `Run state is ${run.status}.`,
    impact: isUnverifiable
      ? "Blind spot: this outcome must stay amber until the proof gap is fixed or explicitly accepted with expiry."
      : isFailed
        ? "Recovery rail needs operator attention."
        : "Operational audit trail available.",
    digest: run.run_digest,
    createdAt: run.created_at,
    timeline: reasonCode
      ? ["Run registered", `Unverifiable reason: ${reasonCode}`, `Next action: ${reasonAction}`]
      : ["Run registered", "Policy and proof rail linked", "Awaiting final evidence state"],
    reasonCode,
  };
}

function buildRows(runs: FinalRunResponse[], incidents: FinalIncidentResponse[], approvals: FinalApprovalRequirementResponse[]): OpsRow[] {
  return [
    ...incidents.filter((item) => item.status !== "resolved").map(incidentRow),
    ...approvals.filter((item) => item.status === "pending").map(approvalRow),
    ...runs.map(runRow),
  ];
}

function applyIncidentLocalState(rows: OpsRow[], states: Record<string, IncidentLocalState>): OpsRow[] {
  return rows.map((row) => {
    const state = states[row.id];
    if (row.type !== "Mismatch" || !state) return row;
    const suffix = state.state === "snoozed" && state.until ? ` until ${state.until}` : "";
    return {
      ...row,
      state: `${state.state}${suffix}`,
      action: state.state === "contained" ? "Monitor" : "Review later",
      timeline: [...row.timeline, `${state.state}: ${state.note}`],
    };
  });
}

function tabRows(rows: OpsRow[], tab: OpsTab): OpsRow[] {
  if (tab === "runs") return rows.filter((row) => row.type === "Run" || row.type === "Unverifiable" || row.type === "Recovery");
  if (tab === "incidents") return rows.filter((row) => row.type === "Mismatch");
  if (tab === "approvals") return rows.filter((row) => row.type === "Approval");
  if (tab === "unverifiable") return rows.filter((row) => row.type === "Unverifiable");
  if (tab === "recovery") return rows.filter((row) => row.type === "Recovery");
  return rows.filter((row) => row.type !== "Run");
}

function matchesSavedView(row: OpsRow, view: SavedView): boolean {
  if (view === "Critical") return row.severity === "P1";
  if (view === "My items") return row.owner !== "Unassigned";
  if (view === "Last 24h") return Date.now() - new Date(row.createdAt).getTime() <= 86_400_000;
  return true;
}

function matchesSearch(row: OpsRow, query: string): boolean {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return true;
  return [row.item, row.source, row.agent, row.state, row.owner, row.runId, row.reasonCode ?? ""].some((value) =>
    value.toLowerCase().includes(normalized),
  );
}

function downloadCsv(filename: string, content: string) {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function canOperate(role: string | null | undefined): boolean {
  const normalized = role?.trim().toLowerCase();
  return normalized === "owner" || normalized === "admin";
}

function toneFor(row: OpsRow): string {
  if (row.severity === "P1") return "critical";
  if (row.severity === "P2") return "warning";
  return "neutral";
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.field}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function OperationsMetricStrip({
  openIncidents,
  pendingApprovals,
  queueDepth,
  recovery,
  runCount,
  unverifiable,
}: {
  openIncidents: number;
  pendingApprovals: number;
  queueDepth: number;
  recovery: number;
  runCount: number;
  unverifiable: number;
}) {
  const cells = [
    { label: "Needs attention", value: queueDepth, tone: "critical", Icon: ShieldAlert },
    { label: "Runs ledger", value: runCount, tone: "ready", Icon: ShieldCheck },
    { label: "Unverifiable", value: unverifiable, tone: "stale", Icon: AlertTriangle },
    { label: "Open incidents", value: openIncidents, tone: "critical", Icon: BellDot },
    { label: "Pending approvals", value: pendingApprovals, tone: "pending", Icon: LockKeyhole },
    { label: "Recovery rail", value: recovery, tone: "neutral", Icon: BarChart3 },
  ];
  return (
    <section className={styles.metricStrip} aria-label="Operations metrics">
      {cells.map(({ label, value, tone, Icon }) => (
        <article className={styles.metricCell} data-tone={tone} key={label}>
          <span>
            <Icon size={15} aria-hidden="true" />
            {label}
          </span>
          <strong>{value}</strong>
        </article>
      ))}
    </section>
  );
}

function buildAgentStats(rows: OpsRow[]): AgentStat[] {
  const stats = new Map<string, AgentStat>();
  for (const row of rows) {
    const stat = stats.get(row.agent) ?? {
      agent: row.agent,
      total: 0,
      mismatches: 0,
      unverifiable: 0,
      recovery: 0,
      lastSeen: row.age,
    };
    stat.total += 1;
    if (/mismatch/i.test(row.state)) stat.mismatches += 1;
    if (row.type === "Unverifiable") stat.unverifiable += 1;
    if (row.type === "Recovery") stat.recovery += 1;
    stat.lastSeen = row.age;
    stats.set(row.agent, stat);
  }
  return [...stats.values()].sort((a, b) =>
    b.mismatches - a.mismatches ||
    b.unverifiable - a.unverifiable ||
    b.recovery - a.recovery ||
    b.total - a.total ||
    a.agent.localeCompare(b.agent),
  );
}

function AgentFacet({
  activeAgent,
  onSelect,
  stats,
}: {
  activeAgent: string | null;
  onSelect: (agent: string | null) => void;
  stats: AgentStat[];
}) {
  if (stats.length === 0) return null;
  return (
    <div className={styles.agentFacet} aria-label="Agent summary">
      <button type="button" data-active={!activeAgent} onClick={() => onSelect(null)}>
        All agents
        <strong>{stats.reduce((sum, stat) => sum + stat.total, 0)}</strong>
      </button>
      {stats.map((stat) => (
        <button type="button" key={stat.agent} data-active={activeAgent === stat.agent} onClick={() => onSelect(stat.agent)}>
          <span>{stat.agent}</span>
          <small>{stat.total} runs · {stat.mismatches} mismatch · {stat.unverifiable} unverifiable · {stat.recovery} recovery</small>
          <em>{stat.lastSeen}</em>
        </button>
      ))}
    </div>
  );
}

type OperationsUrlSelection = { agentName: string | null; id: string | null; tab: OpsTab };

function selectionFromUrl(
  runs: FinalRunResponse[],
  incidents: FinalIncidentResponse[],
  approvals: FinalApprovalRequirementResponse[],
): OperationsUrlSelection | null {
  if (typeof window === "undefined") return null;
  const params = new URLSearchParams(window.location.search);
  const incidentId = params.get("incident_id");
  if (incidentId) return { agentName: null, id: incidentId, tab: "incidents" };
  const approvalId = params.get("approval_id");
  if (approvalId) return { agentName: null, id: approvalId, tab: "approvals" };
  const runId = params.get("run_id");
  if (runId) return { agentName: null, id: runId, tab: "runs" };

  const intentId = params.get("intent_id");
  if (intentId) {
    const run = runs.find((item) => item.intent_id === intentId);
    if (run) return { agentName: null, id: run.id, tab: "runs" };
    const incident = incidents.find((item) => recordOptionalText(item.incident, "intent_id") === intentId);
    if (incident) return { agentName: null, id: incident.id, tab: "incidents" };
    const approval = approvals.find((item) => item.intent_id === intentId);
    return { agentName: null, id: approval?.id ?? intentId, tab: approval ? "approvals" : "runs" };
  }

  const decisionId = params.get("decision_id");
  if (decisionId) {
    const approval = approvals.find((item) => item.policy_decision_id === decisionId || item.id === decisionId);
    return { agentName: null, id: approval?.id ?? decisionId, tab: "approvals" };
  }

  const actionId = params.get("action_id");
  if (actionId) {
    const run = runs.find((item) => {
      const metadata = item.run.metadata;
      const metadataRecord = metadata && typeof metadata === "object" ? (metadata as Record<string, unknown>) : {};
      return [
        item.external_run_id,
        recordOptionalText(item.run, "action_id"),
        recordOptionalText(item.run, "zroky_action_id"),
        recordOptionalText(metadataRecord, "action_id"),
        recordOptionalText(metadataRecord, "zroky_action_id"),
      ].includes(actionId);
    });
    return { agentName: null, id: run?.id ?? actionId, tab: "runs" };
  }

  const agentName = params.get("agent_name");
  if (agentName) return { agentName, id: null, tab: "runs" };
  const view = params.get("view");
  if (TABS.some((tab) => tab.id === view)) return { agentName: null, id: null, tab: view as OpsTab };
  return null;
}

function DetailDrawer({
  canMutate,
  isAssigning,
  isExecutingRecovery,
  isManuallyResolving,
  error,
  onAssignIncident,
  onExecuteRecovery,
  onMarkContained,
  onResolveIncidentManually,
  onSnoozeIncident,
  isResolving,
  onResolveApproval,
  row,
}: {
  canMutate: boolean;
  error: string | null;
  isAssigning: boolean;
  isExecutingRecovery: boolean;
  isManuallyResolving: boolean;
  onAssignIncident: (row: OpsRow, owner: string) => void;
  onExecuteRecovery: (row: OpsRow, executorRef: string) => void;
  onMarkContained: (row: OpsRow, note: string) => void;
  onResolveIncidentManually: (row: OpsRow, graphId: string, note: string) => void;
  onSnoozeIncident: (row: OpsRow, reason: string, until: string) => void;
  isResolving: boolean;
  onResolveApproval: (row: OpsRow, decision: "approve" | "deny", reason: string) => void;
  row: OpsRow | null;
}) {
  const [owner, setOwner] = useState("");
  const [executorRef, setExecutorRef] = useState("");
  const [verifiedGraphId, setVerifiedGraphId] = useState("");
  const [resolutionNote, setResolutionNote] = useState("");
  const [approvalReason, setApprovalReason] = useState("");
  const [containmentNote, setContainmentNote] = useState("");
  const [snoozeReason, setSnoozeReason] = useState("");
  const [snoozeUntil, setSnoozeUntil] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    setOwner(row?.owner === "Unassigned" ? "" : row?.owner ?? "");
    setExecutorRef("");
    setVerifiedGraphId("");
    setResolutionNote("");
    setApprovalReason("");
    setContainmentNote("");
    setSnoozeReason("");
    setSnoozeUntil("");
    setLocalError(null);
  }, [row?.id, row?.owner]);

  if (!row) {
    return (
      <aside className={styles.drawer} aria-label="Operation detail">
        <div className={styles.emptyDrawer}>
          <ShieldCheck size={18} aria-hidden="true" />
          <strong>Select an operation</strong>
          <span>Open a row to inspect expected vs actual, policy, approval, recovery, and evidence.</span>
        </div>
      </aside>
    );
  }

  return (
    <aside className={styles.drawer} aria-label="Operation detail">
      <div className={styles.drawerHead}>
        <span className={styles.kicker}>Expected vs actual</span>
        <h2>{row.item}</h2>
        <Link href={row.href}>
          Permalink <ExternalLink size={12} aria-hidden="true" />
        </Link>
      </div>

      <section className={styles.diffHero}>
        <div>
          <span>Expected</span>
          <p>{row.expected}</p>
        </div>
        <div>
          <span>Actual</span>
          <p>{row.actual}</p>
        </div>
        <strong data-tone={toneFor(row)}>{row.type}</strong>
      </section>

      <div className={styles.drawerGrid}>
        <Field label="Run" value={row.runId} />
        <Field label="Source" value={row.source} />
        <Field label="Agent / workflow" value={row.agent} />
        <Field label="State" value={row.state} />
        <Field label="Owner" value={row.owner} />
        <Field label="Digest" value={text(row.digest).slice(0, 18)} />
      </div>
      {row.type === "Mismatch" ? (
        <section className={styles.drawerSection}>
          <h3>Incident lifecycle</h3>
          <div className={styles.lifecycleRail} aria-label="Incident lifecycle">
            {["Open", "Investigating", "Contained", "Recovering", "Resolved", "Closed"].map((step) => (
              <span key={step} data-active={row.state.toLowerCase().includes(step.toLowerCase()) || (step === "Open" && row.state === "open")}>
                {step}
              </span>
            ))}
          </div>
          <form
            className={styles.drawerForm}
            aria-label="Contain or snooze incident"
            onSubmit={(event) => event.preventDefault()}
          >
            <label>
              Containment note
              <input
                aria-label="Containment note"
                value={containmentNote}
                onChange={(event) => setContainmentNote(event.target.value)}
                placeholder="What blast radius was stopped?"
              />
            </label>
            <div className={styles.drawerActions}>
              <button
                type="button"
                disabled={!canMutate || containmentNote.trim().length === 0}
                onClick={() => onMarkContained(row, containmentNote.trim())}
              >
                Mark contained
              </button>
            </div>
            <label>
              Snooze reason
              <input
                aria-label="Snooze reason"
                value={snoozeReason}
                onChange={(event) => setSnoozeReason(event.target.value)}
                placeholder="Accepted risk reason"
              />
            </label>
            <label>
              Snooze until
              <input
                aria-label="Snooze until"
                type="datetime-local"
                value={snoozeUntil}
                onChange={(event) => setSnoozeUntil(event.target.value)}
              />
            </label>
            <div className={styles.drawerActions}>
              <button
                type="button"
                disabled={!canMutate || snoozeReason.trim().length === 0 || snoozeUntil.length === 0}
                onClick={() => onSnoozeIncident(row, snoozeReason.trim(), snoozeUntil)}
              >
                Snooze
              </button>
            </div>
          </form>
        </section>
      ) : null}

      <section className={styles.drawerSection}>
        <h3>Policy decision</h3>
        <p>Action remains governed by policy, approval state, and exact payload binding.</p>
        {!canMutate ? <p className={styles.readOnlyNote}>Read-only role: actions are disabled.</p> : null}
        {row.type === "Approval" && row.state === "pending" ? (
          <form
            className={styles.drawerForm}
            aria-label="Resolve approval"
            onSubmit={(event) => event.preventDefault()}
          >
            <div className={styles.approvalPreview}>
              <span>Intent</span>
              <strong>{row.runId}</strong>
              <span>Binding digest</span>
              <code>{row.digest}</code>
              <span>Exact payload preview</span>
              <p>{row.expected}</p>
            </div>
            <label>
              Decision reason
              <input
                aria-label="Approval decision reason"
                value={approvalReason}
                onChange={(event) => setApprovalReason(event.target.value)}
                placeholder="Why is this exact payload safe or denied?"
              />
            </label>
            <div className={styles.drawerActions}>
              <button
                type="button"
                onClick={() => onResolveApproval(row, "approve", approvalReason.trim())}
                disabled={!canMutate || isResolving || approvalReason.trim().length === 0}
              >
                Approve exact payload
              </button>
              <button
                type="button"
                onClick={() => onResolveApproval(row, "deny", approvalReason.trim())}
                disabled={!canMutate || isResolving || approvalReason.trim().length === 0}
              >
                Deny
              </button>
            </div>
          </form>
        ) : null}
        {error ? <p className={styles.actionError}>{error}</p> : null}
      </section>
      <section className={styles.drawerSection}>
        <h3>Recovery attempts</h3>
        <p>{row.impact}</p>
        {row.type === "Mismatch" ? (
          <form
            className={styles.drawerForm}
            aria-label="Execute recovery"
            onSubmit={(event) => {
              event.preventDefault();
              if (!canMutate) return;
              const value = executorRef.trim();
              if (!value.startsWith("customer-recovery-executor://")) {
                setLocalError("Executor ref must start with customer-recovery-executor://");
                return;
              }
              setLocalError(null);
              onExecuteRecovery(row, value);
            }}
          >
            <label>
              Executor ref
              <input
                aria-label="Recovery executor ref"
                value={executorRef}
                onChange={(event) => setExecutorRef(event.target.value)}
                placeholder="customer-recovery-executor://..."
              />
            </label>
            <button type="submit" disabled={!canMutate || isExecutingRecovery}>Execute recovery</button>
          </form>
        ) : null}
      </section>
      {row.type === "Mismatch" ? (
        <section className={styles.drawerSection}>
          <h3>Owner</h3>
          <form
            className={styles.drawerForm}
            aria-label="Assign incident"
            onSubmit={(event) => {
              event.preventDefault();
              if (!canMutate) return;
              const value = owner.trim();
              if (!value) {
                setLocalError("Owner is required.");
                return;
              }
              setLocalError(null);
              onAssignIncident(row, value);
            }}
          >
            <label>
              Incident owner
              <input aria-label="Incident owner" value={owner} onChange={(event) => setOwner(event.target.value)} />
            </label>
            <button type="submit" disabled={!canMutate || isAssigning}>Assign owner</button>
          </form>
        </section>
      ) : null}
      {row.type === "Mismatch" ? (
        <section className={styles.drawerSection}>
          <h3>Manual resolution</h3>
          <p>Requires a fresh verified outcome graph. Backend rejects stale or unrelated graph IDs.</p>
          <form
            className={styles.drawerForm}
            aria-label="Resolve incident manually"
            onSubmit={(event) => {
              event.preventDefault();
              if (!canMutate) return;
              const graphId = verifiedGraphId.trim();
              if (!graphId) {
                setLocalError("Verified outcome graph ID is required.");
                return;
              }
              setLocalError(null);
              onResolveIncidentManually(row, graphId, resolutionNote.trim());
            }}
          >
            <label>
              Verified outcome graph ID
              <input
                aria-label="Verified outcome graph ID"
                value={verifiedGraphId}
                onChange={(event) => setVerifiedGraphId(event.target.value)}
              />
            </label>
            <label>
              Resolution note
              <input
                aria-label="Resolution note"
                value={resolutionNote}
                onChange={(event) => setResolutionNote(event.target.value)}
              />
            </label>
            <button type="submit" disabled={!canMutate || isManuallyResolving}>Resolve manually</button>
          </form>
        </section>
      ) : null}
      <section className={styles.drawerSection}>
        <h3>Evidence bundle</h3>
        <p>View, generate, verify, copy link, or export audit bundle from the linked evidence record.</p>
      </section>
      <section className={styles.drawerSection}>
        <h3>Audit timeline</h3>
        <ol>
          {row.timeline.map((item) => <li key={item}>{item}</li>)}
        </ol>
      </section>
      {localError ? <p className={styles.actionError}>{localError}</p> : null}
    </aside>
  );
}

function recoveryIdempotencyKey(incidentId: string): string {
  const nonce = globalThis.crypto?.randomUUID?.() ?? String(Date.now());
  return `operations-recovery-${incidentId}-${nonce}`;
}

export default function OperationsPage() {
  const queryClient = useQueryClient();
  const searchInputRef = useRef<HTMLInputElement>(null);
  const deepLinkHandled = useRef(false);
  const selectedProject = useDashboardStore((state) => state.selectedProject);
  const realTimeEnabled = useDashboardStore((state) => state.realTimeEnabled);
  const liveQueryOptions = { refetchInterval: realTimeEnabled ? 30_000 : false as const };
  const [explicitDemo, setExplicitDemo] = useState(demoOperationsEnabled);
  const localPreview = explicitDemo;
  const runs = useQuery({
    queryKey: ["final-runs"],
    queryFn: ({ signal }) => listFinalRuns(signal),
    enabled: !localPreview,
    ...liveQueryOptions,
  });
  const incidents = useQuery({
    queryKey: ["final-incidents"],
    queryFn: ({ signal }) => listFinalIncidents(signal),
    enabled: !localPreview,
    ...liveQueryOptions,
  });
  const approvals = useQuery({
    queryKey: ["final-approval-requirements"],
    queryFn: ({ signal }) => listFinalApprovalRequirements(signal),
    enabled: !localPreview,
    ...liveQueryOptions,
  });
  const projects = useQuery({ queryKey: ["my-projects"], queryFn: ({ signal }) => listMyProjects(signal), enabled: !localPreview });

  const [activeTab, setActiveTab] = useState<OpsTab>("attention");
  const [activeView, setActiveView] = useState<SavedView>("All");
  const [activeAgent, setActiveAgent] = useState<string | null>(null);
  const [incidentLocalStates, setIncidentLocalStates] = useState<Record<string, IncidentLocalState>>({});
  const [searchTerm, setSearchTerm] = useState("");
  const hasError = runs.isError || incidents.isError || approvals.isError;
  const hasPermissionError = isPermissionError(runs.error) || isPermissionError(incidents.error) || isPermissionError(approvals.error);
  const useDemoData = localPreview || (process.env.NODE_ENV === "development" && hasPermissionError);
  const runItems = useDemoData ? demoOperationRuns() : runs.data?.items ?? EMPTY_RUNS;
  const incidentItems = useDemoData ? demoOperationIncidents() : incidents.data ?? EMPTY_INCIDENTS;
  const approvalItems = useDemoData ? demoOperationApprovals() : approvals.data?.items ?? EMPTY_APPROVALS;
  const isLoading = !useDemoData && (runs.isLoading || incidents.isLoading || approvals.isLoading);
  const rows = useMemo(
    () => applyIncidentLocalState(buildRows(runItems, incidentItems, approvalItems), incidentLocalStates),
    [runItems, incidentItems, approvalItems, incidentLocalStates],
  );
  const runLedgerRows = useMemo(() => tabRows(rows, "runs"), [rows]);
  const agentStats = useMemo(() => buildAgentStats(runLedgerRows), [runLedgerRows]);
  const selectedRows = tabRows(rows, activeTab);
  const scopedView = activeTab === "attention" ? activeView : "All";
  const displayedRows = selectedRows.filter((row) =>
    matchesSavedView(row, scopedView) &&
    matchesSearch(row, searchTerm) &&
    (activeTab !== "runs" || !activeAgent || row.agent === activeAgent),
  );
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const approvalResolution = useMutation({
    mutationFn: ({ decision, reason, row }: { decision: "approve" | "deny"; reason: string; row: OpsRow }) =>
      decision === "approve"
        ? approveFinalApprovalRequirement(row.id, row.digest, reason)
        : denyFinalApprovalRequirement(row.id, row.digest, reason),
    onSuccess: async () => {
      setActionError(null);
      await queryClient.invalidateQueries({ queryKey: ["final-approval-requirements"] });
    },
    onError: (error) => setActionError(errorText(error)),
  });
  const incidentAssignment = useMutation({
    mutationFn: ({ owner, row }: { owner: string; row: OpsRow }) => assignFinalIncident(row.id, owner),
    onSuccess: async () => {
      setActionError(null);
      await queryClient.invalidateQueries({ queryKey: ["final-incidents"] });
    },
    onError: (error) => setActionError(errorText(error)),
  });
  const recoveryExecution = useMutation({
    mutationFn: async ({ executorRef, row }: { executorRef: string; row: OpsRow }) => {
      const compiled = await compileFinalIncidentRecovery(row.id);
      return executeFinalIncidentRecovery(
        row.id,
        executorRef,
        recoveryIdempotencyKey(row.id),
        compiled.plan,
      );
    },
    onSuccess: async () => {
      setActionError(null);
      await queryClient.invalidateQueries({ queryKey: ["final-incidents"] });
    },
    onError: (error) => setActionError(errorText(error)),
  });
  const manualResolution = useMutation({
    mutationFn: ({ graphId, note, row }: { graphId: string; note: string; row: OpsRow }) =>
      resolveFinalIncidentManually(row.id, graphId, note),
    onSuccess: async () => {
      setActionError(null);
      await queryClient.invalidateQueries({ queryKey: ["final-incidents"] });
    },
    onError: (error) => setActionError(errorText(error)),
  });
  const incidentContainment = useMutation({
    mutationFn: ({ note, row }: { note: string; row: OpsRow }) => containFinalIncident(row.id, note),
    onSuccess: async () => {
      setActionError(null);
      await queryClient.invalidateQueries({ queryKey: ["final-incidents"] });
    },
    onError: (error) => setActionError(errorText(error)),
  });
  const incidentSnooze = useMutation({
    mutationFn: ({ reason, row, until }: { reason: string; row: OpsRow; until: string }) => snoozeFinalIncident(row.id, reason, until),
    onSuccess: async () => {
      setActionError(null);
      await queryClient.invalidateQueries({ queryKey: ["final-incidents"] });
    },
    onError: (error) => setActionError(errorText(error)),
  });
  const selectedRow = selectedId === null
    ? displayedRows[0] ?? null
    : displayedRows.find((row) => row.id === selectedId) ?? null;
  const openIncidents = incidentItems.filter((item) => item.status !== "resolved").length;
  const pendingApprovals = approvalItems.filter((item) => item.status === "pending").length;
  const unverifiable = rows.filter((row) => row.type === "Unverifiable").length;
  const recovery = rows.filter((row) => row.type === "Recovery").length;
  const queueDepth = tabRows(rows, "attention").length;
  const projectRole = selectedProject
    ? projects.data?.find((project) => project.project_id === selectedProject)?.role
    : projects.data?.[0]?.role;
  const userCanMutate = useDemoData || canOperate(projectRole);

  useEffect(() => {
    setExplicitDemo(demoOperationsEnabled());
  }, []);

  useEffect(() => {
    if (deepLinkHandled.current || isLoading) return;
    const selection = selectionFromUrl(runItems, incidentItems, approvalItems);
    deepLinkHandled.current = true;
    if (selection) {
      setActiveTab(selection.tab);
      setSelectedId(selection.id);
      setActiveAgent(selection.agentName);
    }
  }, [approvalItems, incidentItems, isLoading, runItems]);

  function selectRow(row: OpsRow) {
    setSelectedId(row.id);
    if (typeof window !== "undefined") {
      window.history.replaceState(null, "", row.href);
    }
  }

  function moveSelection(delta: number) {
    if (displayedRows.length === 0) return;
    const current = Math.max(0, displayedRows.findIndex((row) => row.id === selectedRow?.id));
    const next = displayedRows[(current + delta + displayedRows.length) % displayedRows.length];
    selectRow(next);
  }

  function refreshOperations() {
    void queryClient.invalidateQueries({ queryKey: ["final-runs"] });
    void queryClient.invalidateQueries({ queryKey: ["final-incidents"] });
    void queryClient.invalidateQueries({ queryKey: ["final-approval-requirements"] });
  }

  function selectSavedView(view: SavedView) {
    setActiveView(view);
    setSelectedId(null);
  }

  function exportVisibleRows() {
    downloadCsv("zroky-operations.csv", operationsRowsCsv(displayedRows));
  }

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const tag = target?.tagName?.toLowerCase() ?? "";
      if (tag === "input" || tag === "textarea" || target?.isContentEditable) return;
      if (event.key === "/") {
        event.preventDefault();
        searchInputRef.current?.focus();
      } else if (event.key === "j") {
        event.preventDefault();
        moveSelection(1);
      } else if (event.key === "k") {
        event.preventDefault();
        moveSelection(-1);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  });

  return (
    <main className={styles.operationsPage} aria-label="Operations workbench">
      <header className={styles.header}>
        <div className={styles.headerTop}>
          <div>
            <span className={styles.kicker}>Operations</span>
            <h1>
              {useDemoData
                ? "Operator action required"
                : hasPermissionError
                ? "Operations access unavailable"
                : hasError
                  ? "Operations data unavailable"
                  : isLoading
                    ? "Loading operations"
                    : queueDepth > 0
                      ? "Operator action required"
                      : "Operations are clear"}
            </h1>
            <p>
              {useDemoData
                ? "Local demo data is shown because Operations access is unavailable."
                : "Decision, investigation, recovery, and evidence handoff for AI-agent actions."}
            </p>
          </div>
          <div className={styles.heroSummary} aria-label="Operations summary">
            <strong>{queueDepth > 0 ? `${queueDepth} items need attention` : "No active operator queue"}</strong>
            <span>
              {openIncidents} incident{openIncidents === 1 ? "" : "s"} · {pendingApprovals} approval
              {pendingApprovals === 1 ? "" : "s"} · {unverifiable} unverifiable · {recovery} recovery
            </span>
          </div>
        </div>
        <div className={styles.headerActions}>
          <label className={styles.searchBox}>
            <Search size={13} aria-hidden="true" />
            <input
              ref={searchInputRef}
              aria-label="Search operations"
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              placeholder="Search operations..."
            />
          </label>
          <button type="button" onClick={exportVisibleRows}>Export CSV</button>
          <button className={styles.iconButton} type="button" onClick={refreshOperations} aria-label="Refresh operations" title="Refresh">
            <RotateCcw size={13} aria-hidden="true" />
          </button>
        </div>
      </header>

      <OperationsMetricStrip
        openIncidents={openIncidents}
        pendingApprovals={pendingApprovals}
        queueDepth={queueDepth}
        recovery={recovery}
        runCount={runItems.length}
        unverifiable={unverifiable}
      />

      <nav className={styles.tabs} aria-label="Operations views">
        {TABS.map((tab) => {
          const count =
            tab.id === "runs" ? runItems.length :
            tab.id === "incidents" ? openIncidents :
            tab.id === "approvals" ? pendingApprovals :
            tab.id === "unverifiable" ? unverifiable :
            tab.id === "recovery" ? recovery :
            queueDepth;
          return (
            <button
              key={tab.id}
              type="button"
              className={activeTab === tab.id ? styles.activeTab : undefined}
              onClick={() => {
                setActiveTab(tab.id);
                setActiveView("All");
                if (tab.id !== "runs") setActiveAgent(null);
                setSelectedId(null);
              }}
            >
              {tab.label}
              <span>{count}</span>
            </button>
          );
        })}
      </nav>

      {activeTab === "attention" ? (
        <section className={styles.filterBar} aria-label="Operations filters">
          {SAVED_VIEWS.map((view) => (
            <button type="button" key={view} data-active={activeView === view} onClick={() => selectSavedView(view)}>
              {view}
            </button>
          ))}
        </section>
      ) : null}

      {hasError && !useDemoData ? (
        <section className={styles.stateCard} role="alert">
          <AlertTriangle size={18} aria-hidden="true" />
          <strong>{hasPermissionError ? "Permission required" : "Operations unavailable"}</strong>
          <span>{hasPermissionError ? "You do not have access to the live operations rail." : "Unable to load one or more Operations APIs."}</span>
        </section>
      ) : (
        <div className={styles.workbench}>
          <section className={styles.tableCard} aria-label={`${TABS.find((tab) => tab.id === activeTab)?.label} table`}>
            {activeTab === "runs" ? (
              <AgentFacet activeAgent={activeAgent} onSelect={setActiveAgent} stats={agentStats} />
            ) : null}
            <div className={styles.panelHeader}>
              <div>
                <h2>{TABS.find((tab) => tab.id === activeTab)?.label}</h2>
                <p>{displayedRows.length} items</p>
              </div>
              <Link href="/operations">View all <ExternalLink size={12} aria-hidden="true" /></Link>
            </div>
            {isLoading ? <p className={styles.emptyRows}>Loading operations...</p> : null}
            {!isLoading && displayedRows.length === 0 ? <p className={styles.emptyRows}>No items in this view.</p> : null}
            {displayedRows.map((row) => (
              <button
                type="button"
                key={row.id}
                className={`${styles.attentionRow} ${selectedRow?.id === row.id ? styles.selectedRow : ""}`}
                onClick={() => selectRow(row)}
              >
                <>
                    <span className={styles.severityDot} data-severity={row.severity} aria-label={row.severity} />
                    <div className={styles.attentionCopy}>
                      <div>
                        <span className={styles.severity} data-severity={row.severity}>{row.severity}</span>
                        <strong>{row.item}</strong>
                      </div>
                      {row.reasonCode ? <small>{row.reasonCode}</small> : null}
                      <small>{row.source} · {row.agent}</small>
                    </div>
                    <time>{row.age}</time>
                    <em>{row.action}</em>
                </>
              </button>
            ))}
          </section>
          <DetailDrawer
            canMutate={userCanMutate}
            error={actionError}
            isAssigning={incidentAssignment.isPending}
            isExecutingRecovery={recoveryExecution.isPending}
            isManuallyResolving={manualResolution.isPending}
            isResolving={approvalResolution.isPending}
            onAssignIncident={(row, owner) => incidentAssignment.mutate({ owner, row })}
            onExecuteRecovery={(row, executorRef) => recoveryExecution.mutate({ executorRef, row })}
            onMarkContained={(row, note) =>
              useDemoData
                ? setIncidentLocalStates((states) => ({ ...states, [row.id]: { note, state: "contained" } }))
                : incidentContainment.mutate({ note, row })
            }
            onResolveIncidentManually={(row, graphId, note) => manualResolution.mutate({ graphId, note, row })}
            onResolveApproval={(row, decision, reason) => approvalResolution.mutate({ decision, reason, row })}
            onSnoozeIncident={(row, reason, until) =>
              useDemoData
                ? setIncidentLocalStates((states) => ({ ...states, [row.id]: { note: reason, state: "snoozed", until } }))
                : incidentSnooze.mutate({ reason, row, until })
            }
            row={selectedRow}
          />
        </div>
      )}
    </main>
  );
}
