"use client";

import { useEffect, useMemo, useState } from "react";

import { ApprovalInspector } from "./ApprovalInspector";
import { ApprovalQueue } from "./ApprovalQueue";
import { ApprovalsMetricStrip } from "./ApprovalsMetricStrip";
import { ApprovalsVerdictHero } from "./ApprovalsVerdictHero";
import { DashboardWorkspace } from "@/components/dashboard-scaffold";
import {
  approvalQueueCounts,
  buildApprovalQueue,
  filterApprovalQueue,
  filterApprovalQueueWindow,
  type ApprovalQueueFilter,
  type ApprovalQueueRow,
} from "@/lib/approval-queue";
import type { StatusTone } from "@/lib/action-status";
import {
  useActionIntents,
  useApproveRuntimePolicyDecision,
  useMyProjects,
  useRejectRuntimePolicyDecision,
  useRuntimePolicyApprovals,
  useRuntimePolicyEvidencePack,
} from "@/lib/hooks";
import { useDashboardStore } from "@/lib/store";

type HeroState = {
  title: string;
  copy: string;
  pill: string;
  tone: StatusTone;
};

function heroState({
  damageStopped,
  error,
  loading,
  pending,
  total,
}: {
  damageStopped: number;
  error: boolean;
  loading: boolean;
  pending: number;
  total: number;
}): HeroState {
  if (error) {
    return {
      title: "Approval control",
      copy: "The runtime gate did not refresh cleanly. Keep high-risk decisions conservative until it recovers.",
      pill: "refresh failed",
      tone: "danger",
    };
  }
  if (loading) {
    return {
      title: "Approval control",
      copy: "Fetching held actions, mandate hits, approval audit, linked action intents, and compact evidence.",
      pill: "loading",
      tone: "neutral",
    };
  }
  if (pending > 0) {
    const actionCopy = pending === 1 ? "1 action requires" : `${pending} actions require`;
    return {
      title: "Approval control",
      copy: `${actionCopy} a human decision before Zroky releases execution.`,
      pill: `${pending} held`,
      tone: "warning",
    };
  }
  if (damageStopped > 0) {
    return {
      title: "Approval control",
      copy: `${damageStopped} blocked, rejected, or expired decision${damageStopped === 1 ? "" : "s"} ${damageStopped === 1 ? "remains" : "remain"} preserved with audit evidence.`,
      pill: `${damageStopped} stopped`,
      tone: "danger",
    };
  }
  if (total > 0) {
    return {
      title: "Approval control",
      copy: "Resolved approval decisions remain linked to intent, mandate, audit trail, and evidence.",
      pill: `${total} audited`,
      tone: "success",
    };
  }
  return {
    title: "Approval control",
    copy: "High-risk agent actions will land here before commit when policy requires human approval.",
    pill: "clear",
    tone: "neutral",
  };
}

function initialDeepLink(rows: ApprovalQueueRow[], search: URLSearchParams): string | null {
  const decisionId = search.get("decision_id");
  if (!decisionId) return null;
  return rows.find((row) => row.decisionId === decisionId)?.id ?? null;
}

function filterForStatus(status: string): ApprovalQueueFilter {
  if (status === "pending_approval") return "pending";
  if (["blocked", "rejected", "expired"].includes(status)) return "stopped";
  if (status === "approved") return "approved";
  return "all";
}

function defaultFilterForRows(rows: ApprovalQueueRow[], search: URLSearchParams): ApprovalQueueFilter {
  const decisionId = search.get("decision_id");
  const linked = decisionId ? rows.find((row) => row.decisionId === decisionId) : null;
  if (linked) {
    return filterForStatus(linked.status);
  }
  if (rows.some((row) => row.status === "pending_approval")) return "pending";
  if (rows.some((row) => ["blocked", "rejected", "expired"].includes(row.status))) return "stopped";
  if (rows.some((row) => row.status === "approved")) return "approved";
  return "all";
}

export default function RuntimeApprovalsPage() {
  const [filter, setFilter] = useState<ApprovalQueueFilter>("pending");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [initialFilterSettled, setInitialFilterSettled] = useState(false);
  const [decisionReason, setDecisionReason] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const dateRange = useDashboardStore((state) => state.dateRange);
  const selectedProject = useDashboardStore((state) => state.selectedProject);
  const search = useMemo(
    () => new URLSearchParams(typeof window === "undefined" ? "" : window.location.search),
    [],
  );

  const approvalsQuery = useRuntimePolicyApprovals("all", { refetchInterval: 15_000 });
  const actionIntentsQuery = useActionIntents({ status: "all", limit: 100 }, { refetchInterval: 15_000 });
  const projectsQuery = useMyProjects();
  const approveMutation = useApproveRuntimePolicyDecision();
  const rejectMutation = useRejectRuntimePolicyDecision();

  const decisions = useMemo(() => approvalsQuery.data?.items ?? [], [approvalsQuery.data?.items]);
  const actionIntents = useMemo(() => actionIntentsQuery.data?.items ?? [], [actionIntentsQuery.data?.items]);
  const rows = useMemo(
    () => buildApprovalQueue({ decisions, intents: actionIntents }),
    [actionIntents, decisions],
  );
  const preservedDecisionId = search.get("decision_id");
  const windowRows = useMemo(
    () => filterApprovalQueueWindow(rows, dateRange, preservedDecisionId),
    [dateRange, preservedDecisionId, rows],
  );
  const filteredRows = useMemo(() => filterApprovalQueue(windowRows, filter), [filter, windowRows]);
  const counts = useMemo(() => approvalQueueCounts(windowRows), [windowRows]);
  const selectedRow =
    filteredRows.find((row) => row.id === selectedId) ??
    filteredRows[0] ??
    null;
  const evidencePackQuery = useRuntimePolicyEvidencePack(selectedRow?.decisionId ?? null);
  const loading = approvalsQuery.isLoading || actionIntentsQuery.isLoading;
  const degradedFeeds = [
    approvalsQuery.isError ? "approval gate" : null,
    actionIntentsQuery.isError ? "action intent context" : null,
  ].filter((feed): feed is string => Boolean(feed));
  const error = degradedFeeds.length > 0;
  const hero = heroState({
    damageStopped: counts.stopped,
    error,
    loading,
    pending: counts.pending,
    total: counts.total,
  });
  const busy = approveMutation.isPending || rejectMutation.isPending;
  const selectedMembership = projectsQuery.data?.find((project) => project.project_id === selectedProject);
  const canDecide = selectedMembership
    ? ["admin", "owner"].includes(selectedMembership.role.toLowerCase())
    : projectsQuery.data?.length === 1
      ? ["admin", "owner"].includes(projectsQuery.data[0].role.toLowerCase())
      : false;

  useEffect(() => {
    if (windowRows.length === 0) {
      setSelectedId(null);
      return;
    }
    if (!initialFilterSettled) {
      const nextFilter = defaultFilterForRows(windowRows, search);
      setInitialFilterSettled(true);
      if (nextFilter !== filter) {
        setFilter(nextFilter);
        return;
      }
    }
    const linked = initialDeepLink(windowRows, search);
    if (linked && selectedId == null) {
      setSelectedId(linked);
      return;
    }
    if (filteredRows.length > 0 && (!selectedId || !filteredRows.some((row) => row.id === selectedId))) {
      setSelectedId(filteredRows[0].id);
      return;
    }
    if (!selectedId || !windowRows.some((row) => row.id === selectedId)) {
      setSelectedId(filteredRows[0]?.id ?? null);
      return;
    }
    if (filteredRows.length === 0 && selectedId != null) {
      setSelectedId(null);
    }
  }, [filter, filteredRows, initialFilterSettled, search, selectedId, windowRows]);

  useEffect(() => {
    setDecisionReason("");
  }, [selectedRow?.id]);

  async function refreshAll() {
    await Promise.all([
      approvalsQuery.refetch(),
      actionIntentsQuery.refetch(),
      evidencePackQuery.refetch(),
    ]);
  }

  async function resolve(kind: "approve" | "reject", decisionId: string, reason: string) {
    setMessage(null);
    try {
      if (kind === "approve") {
        const result = await approveMutation.mutateAsync({ decisionId, reason: reason.trim() });
        if (result?.status === "pending_approval") {
          setMessage(`${result.approval_count ?? 0}/${result.required_approval_count ?? 1} approvals recorded. Action remains held.`);
        } else {
          setMessage("Action approved and released to the protected execution flow.");
        }
      } else {
        await rejectMutation.mutateAsync({ decisionId, reason: reason.trim() });
        setMessage("Action rejected and kept from execution.");
      }
      setDecisionReason("");
      await Promise.all([approvalsQuery.refetch(), actionIntentsQuery.refetch()]);
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Decision failed.");
    }
  }

  return (
    <main className="approvals-v2-page">
      <ApprovalsVerdictHero
        title={hero.title}
        copy={hero.copy}
        pill={hero.pill}
        tone={hero.tone}
        refreshing={approvalsQuery.isFetching || actionIntentsQuery.isFetching}
        onRefresh={() => {
          void refreshAll();
        }}
      />

      <ApprovalsMetricStrip
        pending={counts.pending}
        approved={counts.approved}
        expiringSoon={counts.expiringSoon}
        stopped={counts.stopped}
        total={counts.total}
        activeFilter={filter}
        onFilterChange={setFilter}
      />

      {message ? <div className="approval-v2-notice" role="status" aria-live="polite">{message}</div> : null}

      {error ? (
        <section className="approval-v2-alert approval-v2-tone-danger" role="status">
          <div>
            <span className="approval-v2-eyebrow">Refresh status</span>
            <strong>{degradedFeeds.join(", ")} unavailable</strong>
            <p>Showing the last usable approval state. Keep decisions conservative until the feed refreshes cleanly.</p>
          </div>
        </section>
      ) : null}

      {loading ? (
        <section className="approval-v2-empty-state">
          <h2>Loading runtime approvals</h2>
          <p>Fetching action holds and linked intent context.</p>
        </section>
      ) : windowRows.length === 0 ? (
        <section className="approval-v2-empty-state">
          <h2>No approval decisions in this window</h2>
          <p>Pending actions always remain visible. Resolved approval history follows the dashboard time window.</p>
        </section>
      ) : (
        <>
          <DashboardWorkspace
            left={(
              <ApprovalQueue
                rows={filteredRows}
                selectedId={selectedRow?.id ?? null}
                filter={filter}
                onSelect={setSelectedId}
              />
            )}
            right={(
              <ApprovalInspector
                row={selectedRow}
                pack={evidencePackQuery.data}
                packLoading={evidencePackQuery.isLoading}
                packError={evidencePackQuery.error instanceof Error ? evidencePackQuery.error : null}
                reason={decisionReason}
                setReason={setDecisionReason}
                busy={busy}
                canDecide={canDecide}
                onApprove={(decisionId, reason) => {
                  void resolve("approve", decisionId, reason);
                }}
                onReject={(decisionId, reason) => {
                  void resolve("reject", decisionId, reason);
                }}
              />
            )}
          />
        </>
      )}

    </main>
  );
}
