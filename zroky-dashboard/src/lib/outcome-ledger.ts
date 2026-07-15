import type {
  OutcomeReconciliationVerdict,
  OutcomeReconciliationView,
  SourceMutationView,
} from "@/lib/api";
import { field, humanize } from "@/lib/format";
import { sourceMutationTone, statusTone, type StatusTone } from "@/lib/action-status";

export type OutcomeLedgerFilter = OutcomeReconciliationVerdict | "all";

export type OutcomeDiffStatus = "matched" | "mismatched" | "missing" | "not_compared";

export type OutcomeDiffRow = {
  actual: string;
  claimed: string;
  field: string;
  status: OutcomeDiffStatus;
  tone: StatusTone;
};

export type OutcomeLedgerRow = {
  actionHref: string | null;
  actionType: string;
  agentLabel: string;
  amountLabel: string;
  checkedAt: string;
  check: OutcomeReconciliationView;
  connectorLabel: string;
  detail: string;
  evidenceHref: string | null;
  id: string;
  mismatchCount: number;
  priority: 0 | 1 | 2;
  reasonLabel: string;
  systemRef: string;
  title: string;
  tone: StatusTone;
  verdict: OutcomeReconciliationVerdict;
};

export type OutcomeBypassRow = {
  actorLabel: string;
  classification: string;
  detail: string;
  id: string;
  mutation: SourceMutationView;
  occurredAt: string;
  systemLabel: string;
  title: string;
  tone: StatusTone;
};

export type OutcomeLedgerCounts = {
  bypass: number;
  matched: number;
  mismatched: number;
  notVerified: number;
  total: number;
  verifiedRate: number;
};

export type OutcomeLedger = {
  bypassRows: OutcomeBypassRow[];
  counts: OutcomeLedgerCounts;
  rows: OutcomeLedgerRow[];
};

function valueAtPath(source: Record<string, unknown> | null | undefined, path: string): unknown {
  if (!source) return undefined;
  const parts = path.split(".");
  let current: unknown = source;
  for (const part of parts) {
    if (current == null || typeof current !== "object" || Array.isArray(current)) {
      return undefined;
    }
    current = (current as Record<string, unknown>)[part];
  }
  return current;
}

function keysFromRecord(source: Record<string, unknown> | null | undefined): string[] {
  if (!source || typeof source !== "object") return [];
  return Object.keys(source);
}

function mismatchFields(comparison: Record<string, unknown>): Set<string> {
  const fields = new Set<string>();
  const mismatches = comparison.mismatches;
  if (Array.isArray(mismatches)) {
    for (const item of mismatches) {
      if (typeof item === "string") {
        fields.add(item);
      } else if (item && typeof item === "object") {
        const fieldName = (item as Record<string, unknown>).field;
        if (typeof fieldName === "string" && fieldName.trim()) fields.add(fieldName);
      }
    }
  }
  return fields;
}

function comparedRows(comparison: Record<string, unknown>): OutcomeDiffRow[] {
  const compared = comparison.compared_fields;
  if (!Array.isArray(compared)) return [];
  return compared.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const record = item as Record<string, unknown>;
    const fieldName = typeof record.field === "string" && record.field.trim() ? record.field : null;
    if (!fieldName) return [];
    const matched = record.matched === true;
    const status: OutcomeDiffStatus = matched ? "matched" : "mismatched";
    return [{
      actual: field(record.actual),
      claimed: field(record.claimed),
      field: fieldName,
      status,
      tone: matched ? "success" : "danger",
    }];
  });
}

export function buildClaimedActualDiff(check: OutcomeReconciliationView): OutcomeDiffRow[] {
  const compared = comparedRows(check.comparison ?? {});
  if (compared.length > 0) return compared;

  const mismatchSet = mismatchFields(check.comparison ?? {});
  const fields = new Set([
    ...keysFromRecord(check.claimed),
    ...keysFromRecord(check.actual),
    ...Array.from(mismatchSet),
  ]);

  return Array.from(fields).sort().map((fieldName) => {
    const claimed = valueAtPath(check.claimed, fieldName);
    const actual = valueAtPath(check.actual, fieldName);
    const status: OutcomeDiffStatus =
      mismatchSet.has(fieldName)
        ? "mismatched"
        : claimed == null || actual == null
          ? "missing"
          : JSON.stringify(claimed) === JSON.stringify(actual)
            ? "matched"
            : "not_compared";
    return {
      actual: field(actual),
      claimed: field(claimed),
      field: fieldName,
      status,
      tone: status === "mismatched" ? "danger" : status === "missing" || status === "not_compared" ? "warning" : "success",
    };
  });
}

export function outcomeTitle(check: OutcomeReconciliationView): string {
  const claimed = check.claimed;
  for (const key of ["summary", "refund_id", "payment_id", "email", "customer_id", "ticket_id", "record_id"]) {
    const value = claimed[key];
    if (typeof value === "string" && value.trim()) {
      return key === "summary" ? value : `${humanize(key)} ${value}`;
    }
  }
  return check.system_ref ?? humanize(check.action_type, "Outcome check");
}

export function amountLabel(amountUsd: number | null, currency: string | null): string {
  if (amountUsd == null) return "-";
  if (!currency || currency.toUpperCase() === "USD") {
    return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(amountUsd);
  }
  return `${amountUsd.toLocaleString("en-US", { maximumFractionDigits: 2 })} ${currency.toUpperCase()}`;
}

function agentLabel(check: OutcomeReconciliationView): string {
  const metadata = check.metadata ?? {};
  for (const key of ["agent_name", "agent_id", "agent", "actor_id"]) {
    const value = metadata[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  const claimedAgent = check.claimed.agent_name ?? check.claimed.agent_id;
  return typeof claimedAgent === "string" && claimedAgent.trim() ? claimedAgent : "Unidentified runtime";
}

function mismatchCount(check: OutcomeReconciliationView): number {
  const mismatches = check.comparison?.mismatches;
  if (Array.isArray(mismatches) && mismatches.length > 0) return mismatches.length;
  if (check.verdict !== "mismatched") return 0;
  const diffCount = buildClaimedActualDiff(check)
    .filter((row) => row.status !== "matched")
    .length;
  return Math.max(diffCount, 1);
}

function reasonLabel(check: OutcomeReconciliationView): string {
  return humanize(check.reason, "No reason supplied")
    .replace(/\brecord record\b/gi, "record");
}

function priorityFor(verdict: OutcomeReconciliationVerdict): 0 | 1 | 2 {
  if (verdict === "mismatched") return 0;
  if (verdict === "not_verified") return 1;
  return 2;
}

function checkedTime(check: OutcomeReconciliationView): number {
  const parsed = new Date(check.checked_at).getTime();
  return Number.isFinite(parsed) ? parsed : 0;
}

function evidenceHref(check: OutcomeReconciliationView): string | null {
  return check.runtime_policy_decision_id
    ? `/evidence?decision_id=${encodeURIComponent(check.runtime_policy_decision_id)}`
    : null;
}

function actionHref(check: OutcomeReconciliationView): string | null {
  const actionId = check.metadata?.action_id ?? check.metadata?.zroky_action_id;
  return typeof actionId === "string" && actionId.trim()
    ? `/actions?action_id=${encodeURIComponent(actionId)}`
    : null;
}

export function buildOutcomeLedger({
  checks,
  filter = "all",
  mutations = [],
  search = "",
}: {
  checks: OutcomeReconciliationView[];
  filter?: OutcomeLedgerFilter;
  mutations?: SourceMutationView[];
  search?: string;
}): OutcomeLedger {
  const counts: OutcomeLedgerCounts = {
    bypass: mutations.length,
    matched: checks.filter((item) => item.verdict === "matched").length,
    mismatched: checks.filter((item) => item.verdict === "mismatched").length,
    notVerified: checks.filter((item) => item.verdict === "not_verified").length,
    total: checks.length,
    verifiedRate: 0,
  };
  counts.verifiedRate = counts.total > 0 ? Math.round((counts.matched / counts.total) * 100) : 0;

  const needle = search.trim().toLowerCase();
  const rows = checks
    .filter((check) => filter === "all" || check.verdict === filter)
    .map((check): OutcomeLedgerRow => {
      const mismatches = mismatchCount(check);
      const row: OutcomeLedgerRow = {
        actionHref: actionHref(check),
        actionType: humanize(check.action_type, "Unknown action"),
        agentLabel: agentLabel(check),
        amountLabel: amountLabel(check.amount_usd, check.currency),
        checkedAt: check.checked_at,
        check,
        connectorLabel: humanize(check.connector_type, "Unknown connector"),
        detail:
          check.verdict === "mismatched"
            ? `${mismatches} field difference${mismatches === 1 ? "" : "s"}`
            : check.verdict === "not_verified"
              ? humanize(check.reason, "Proof missing")
              : "Claim matched actual record",
        evidenceHref: evidenceHref(check),
        id: check.id,
        mismatchCount: mismatches,
        priority: priorityFor(check.verdict),
        reasonLabel: reasonLabel(check),
        systemRef: check.system_ref ?? check.id,
        title: outcomeTitle(check),
        tone: statusTone(check.verdict, "proof"),
        verdict: check.verdict,
      };
      return row;
    })
    .filter((row) => {
      if (!needle) return true;
      return [
        row.id,
        row.title,
        row.agentLabel,
        row.actionType,
        row.connectorLabel,
        row.systemRef,
        row.reasonLabel,
        row.check.call_id,
        row.check.trace_id,
        JSON.stringify(row.check.claimed),
        JSON.stringify(row.check.actual),
      ].filter(Boolean).join(" ").toLowerCase().includes(needle);
    })
    .sort((a, b) => {
      const priority = a.priority - b.priority;
      if (priority !== 0) return priority;
      return checkedTime(b.check) - checkedTime(a.check);
    });

  const bypassRows = mutations.map((mutation): OutcomeBypassRow => ({
    actorLabel: mutation.actor_id ?? humanize(mutation.actor_type, "Unknown actor"),
    classification: mutation.classification,
    detail: `${humanize(mutation.source_system)} / ${humanize(mutation.action_type ?? mutation.resource_type, "Unknown mutation")}`,
    id: mutation.id,
    mutation,
    occurredAt: mutation.occurred_at,
    systemLabel: humanize(mutation.source_system, "Unknown system"),
    title: mutation.system_ref ?? mutation.resource_id ?? mutation.mutation_id,
    tone: sourceMutationTone(mutation.classification),
  }));

  return { bypassRows, counts, rows };
}
