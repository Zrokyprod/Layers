"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Download, FileJson, ShieldCheck } from "lucide-react";

import {
  getRuntimePolicyEvidencePack,
  listOutcomeReconciliations,
  listRuntimePolicyApprovals,
  type OutcomeReconciliationView,
  type RuntimePolicyDecisionResponse,
  type RuntimePolicyEvidencePackResponse,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";

type EvidenceRow = {
  key: string;
  decisionId: string | null;
  agentName: string | null;
  actionType: string | null;
  decisionStatus: string | null;
  decision: string | null;
  outcomeVerdict: string | null;
  systemRef: string | null;
  sourceLabel: string;
  createdAt: string | null;
};

function safeFilePart(value: string) {
  return value.replace(/[^a-zA-Z0-9_.-]+/g, "_");
}

function downloadJsonFile(payload: RuntimePolicyEvidencePackResponse, filename: string) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function statusLabel(value: string | null) {
  if (!value) return "not_verified";
  return value.replace(/_/g, " ");
}

function pillClass(value: string | null) {
  if (["allow", "allowed", "approved", "matched", "pass"].includes(value ?? "")) {
    return "pill pill-green";
  }
  if (["block", "blocked", "rejected", "mismatched", "fail"].includes(value ?? "")) {
    return "pill pill-red";
  }
  return "pill pill-yellow";
}

function decisionRow(decision: RuntimePolicyDecisionResponse): EvidenceRow {
  return {
    key: `decision:${decision.id}`,
    decisionId: decision.id,
    agentName: decision.agent_name,
    actionType: decision.action_type ?? decision.tool_name,
    decisionStatus: decision.status,
    decision: decision.decision,
    outcomeVerdict: null,
    systemRef: null,
    sourceLabel: "Runtime decision",
    createdAt: decision.created_at,
  };
}

function outcomeRow(outcome: OutcomeReconciliationView): EvidenceRow {
  return {
    key: `outcome:${outcome.id}`,
    decisionId: outcome.runtime_policy_decision_id,
    agentName: null,
    actionType: outcome.action_type,
    decisionStatus: null,
    decision: null,
    outcomeVerdict: outcome.verdict,
    systemRef: outcome.system_ref,
    sourceLabel: outcome.connector_type,
    createdAt: outcome.checked_at ?? outcome.created_at,
  };
}

function mergeEvidenceRows(
  decisions: RuntimePolicyDecisionResponse[],
  outcomes: OutcomeReconciliationView[],
) {
  const byDecision = new Map<string, EvidenceRow>();
  const rows: EvidenceRow[] = [];

  for (const decision of decisions) {
    const row = decisionRow(decision);
    byDecision.set(decision.id, row);
    rows.push(row);
  }

  for (const outcome of outcomes) {
    const decisionId = outcome.runtime_policy_decision_id;
    if (decisionId && byDecision.has(decisionId)) {
      const existing = byDecision.get(decisionId);
      if (existing) {
        existing.outcomeVerdict = outcome.verdict;
        existing.systemRef = outcome.system_ref;
        existing.sourceLabel = outcome.connector_type;
        existing.createdAt = outcome.checked_at ?? existing.createdAt;
      }
      continue;
    }
    rows.push(outcomeRow(outcome));
  }

  return rows.sort((a, b) => new Date(b.createdAt ?? 0).getTime() - new Date(a.createdAt ?? 0).getTime());
}

export default function EvidencePage() {
  const [message, setMessage] = useState("");
  const [downloadingDecisionId, setDownloadingDecisionId] = useState<string | null>(null);
  const decisionsQuery = useQuery({
    queryKey: ["runtime-policy", "evidence-index"],
    queryFn: ({ signal }) => listRuntimePolicyApprovals("all", signal),
  });
  const outcomesQuery = useQuery({
    queryKey: ["outcomes", "evidence-index"],
    queryFn: ({ signal }) => listOutcomeReconciliations({ limit: 50 }, signal),
  });

  const rows = useMemo(
    () => mergeEvidenceRows(decisionsQuery.data?.items ?? [], outcomesQuery.data?.items ?? []),
    [decisionsQuery.data?.items, outcomesQuery.data?.items],
  );
  const linkedCount = rows.filter((row) => row.decisionId).length;
  const matchedCount = rows.filter((row) => row.outcomeVerdict === "matched").length;
  const notVerifiedCount = rows.filter((row) => row.outcomeVerdict === "not_verified" || !row.outcomeVerdict).length;
  const loading = decisionsQuery.isLoading || outcomesQuery.isLoading;
  const error = decisionsQuery.error || outcomesQuery.error;

  async function downloadEvidence(decisionId: string) {
    setMessage("");
    setDownloadingDecisionId(decisionId);
    try {
      const pack = await getRuntimePolicyEvidencePack(decisionId);
      downloadJsonFile(pack, `zroky-evidence-${safeFilePart(decisionId)}.json`);
      setMessage("Evidence Pack JSON downloaded.");
    } catch (downloadError) {
      setMessage(downloadError instanceof Error ? downloadError.message : "Evidence Pack download failed.");
    } finally {
      setDownloadingDecisionId(null);
    }
  }

  return (
    <div className="dashboard-page evidence-page">
      {message ? <div className="alert-strip">{message}</div> : null}

      <section className="page-header">
        <div>
          <span className="eyebrow">Audit proof</span>
          <h1>Evidence</h1>
          <p>Runtime decisions, system-of-record outcomes, and exportable Evidence Packs for customer or auditor proof.</p>
        </div>
        <div className="actions">
          <Link href="/approvals" className="btn btn-soft">Open approvals</Link>
          <Link href="/outcomes" className="btn btn-primary">Open outcomes</Link>
        </div>
      </section>

      <section className="settings-summary-grid" aria-label="Evidence summary">
        <article className="panel settings-summary-card">
          <FileJson aria-hidden="true" />
          <span>Evidence linked</span>
          <strong>{linkedCount}</strong>
          <small>Rows with a runtime policy decision id can export a full Evidence Pack.</small>
        </article>
        <article className="panel settings-summary-card">
          <ShieldCheck aria-hidden="true" />
          <span>Matched outcomes</span>
          <strong>{matchedCount}</strong>
          <small>System-of-record checks that matched the agent claim.</small>
        </article>
        <article className="panel settings-summary-card">
          <AlertTriangle aria-hidden="true" />
          <span>Needs proof</span>
          <strong>{notVerifiedCount}</strong>
          <small>Rows without matched outcome proof stay not_verified.</small>
        </article>
      </section>

      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>Evidence library</h3>
            <p>Download proof from linked runtime decisions and review outcome status before handoff.</p>
          </div>
        </header>

        {loading ? (
          <div className="empty-state">Loading evidence...</div>
        ) : error ? (
          <div className="empty-state">Evidence could not load. Verify backend connectivity and project access.</div>
        ) : rows.length === 0 ? (
          <div className="empty-state">No evidence yet. Run a protected action, approval, or connector reconciliation first.</div>
        ) : (
          <div className="list">
            {rows.map((row) => {
              const status = row.outcomeVerdict ?? row.decisionStatus ?? row.decision;
              const title = row.agentName ?? row.systemRef ?? row.decisionId ?? "Unlinked outcome";
              const subtitle = [row.actionType, row.sourceLabel, row.systemRef].filter(Boolean).join(" - ");
              const isDownloading = Boolean(row.decisionId) && downloadingDecisionId === row.decisionId;
              return (
                <div className="list-row" key={row.key}>
                  <div className="list-main">
                    <strong>{title}</strong>
                    <span>{subtitle || "Evidence row"}</span>
                    <small>{formatDateTime(row.createdAt)}</small>
                  </div>
                  <span className={pillClass(status)}>{statusLabel(status)}</span>
                  <button
                    className="btn btn-soft btn-sm"
                    type="button"
                    disabled={!row.decisionId || isDownloading}
                    onClick={() => row.decisionId && void downloadEvidence(row.decisionId)}
                  >
                    <Download aria-hidden="true" />
                    {isDownloading ? "Downloading..." : row.decisionId ? "Download JSON" : "Not linked"}
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
