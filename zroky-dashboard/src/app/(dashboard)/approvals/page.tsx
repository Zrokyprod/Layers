"use client";

import { useEffect, useMemo, useState } from "react";

import { ApprovalInspector } from "./ApprovalInspector";
import { ApprovalQueue, type ApprovalFilter } from "./ApprovalQueue";
import { ApprovalsMetricStrip } from "./ApprovalsMetricStrip";
import { ApprovalsVerdictHero } from "./ApprovalsVerdictHero";
import { KillSwitchPanel } from "./KillSwitchPanel";
import { DashboardWorkspace } from "@/components/dashboard-scaffold";
import {
  approvalQueueCounts,
  buildApprovalQueue,
  filterApprovalQueue,
  type ApprovalQueueRow,
} from "@/lib/approval-queue";
import type { StatusTone } from "@/lib/action-status";
import {
  useActionIntents,
  useApproveRuntimePolicyDecision,
  useRejectRuntimePolicyDecision,
  useRuntimePolicyApprovals,
  useRuntimePolicyEvidencePack,
  useSetRuntimePolicyKillSwitch,
} from "@/lib/hooks";

type HeroState = {
  title: string;
  copy: string;
  pill: string;
  tone: StatusTone;
};

function heroState({
  damageStopped,
  error,
  killSwitchArmed,
  loading,
  pending,
  total,
}: {
  damageStopped: number;
  error: boolean;
  killSwitchArmed: boolean;
  loading: boolean;
  pending: number;
  total: number;
}): HeroState {
  if (killSwitchArmed) {
    return {
      title: "Kill switch confirmation armed",
      copy: "No global hold is enabled until you confirm. Use it only when proof or mandate boundaries are unsafe.",
      pill: "confirmation armed",
      tone: "danger",
    };
  }
  if (error) {
    return {
      title: "Approval state unavailable",
      copy: "The runtime gate did not refresh cleanly. Keep high-risk decisions conservative until it recovers.",
      pill: "refresh failed",
      tone: "danger",
    };
  }
  if (loading) {
    return {
      title: "Loading runtime gate",
      copy: "Fetching held actions, mandate hits, approval audit, linked action intents, and compact evidence.",
      pill: "loading",
      tone: "neutral",
    };
  }
  if (pending > 0) {
    const actionCopy = pending === 1 ? "1 action requires" : `${pending} actions require`;
    return {
      title: "Risky actions held before commit",
      copy: `${actionCopy} a human decision before Zroky releases execution.`,
      pill: `${pending} held`,
      tone: "warning",
    };
  }
  if (damageStopped > 0) {
    return {
      title: "Unsafe action stopped",
      copy: `${damageStopped} blocked or rejected decision${damageStopped === 1 ? "" : "s"} ${damageStopped === 1 ? "remains" : "remain"} preserved with audit evidence.`,
      pill: `${damageStopped} stopped`,
      tone: "danger",
    };
  }
  if (total > 0) {
    return {
      title: "Actions controlled and proved",
      copy: "Resolved approval decisions remain linked to intent, mandate, audit trail, and evidence.",
      pill: `${total} audited`,
      tone: "success",
    };
  }
  return {
    title: "Approval gate clear",
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

function filterForStatus(status: string): ApprovalFilter {
  if (
    status === "pending_approval" ||
    status === "blocked" ||
    status === "approved" ||
    status === "rejected"
  ) {
    return status;
  }
  return "all";
}

function defaultFilterForRows(rows: ApprovalQueueRow[], search: URLSearchParams): ApprovalFilter {
  const decisionId = search.get("decision_id");
  const linked = decisionId ? rows.find((row) => row.decisionId === decisionId) : null;
  if (linked) {
    return filterForStatus(linked.status);
  }
  if (rows.some((row) => row.status === "pending_approval")) return "pending_approval";
  if (rows.some((row) => row.status === "blocked")) return "blocked";
  if (rows.some((row) => row.status === "rejected")) return "rejected";
  if (rows.some((row) => row.status === "approved")) return "approved";
  return "all";
}

export default function RuntimeApprovalsPage() {
  const [filter, setFilter] = useState<ApprovalFilter>("pending_approval");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [initialFilterSettled, setInitialFilterSettled] = useState(false);
  const [decisionReason, setDecisionReason] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [killSwitchArmed, setKillSwitchArmed] = useState(false);
  const search = useMemo(
    () => new URLSearchParams(typeof window === "undefined" ? "" : window.location.search),
    [],
  );

  const approvalsQuery = useRuntimePolicyApprovals("all", { refetchInterval: 15_000 });
  const actionIntentsQuery = useActionIntents({ status: "all", limit: 100 }, { refetchInterval: 15_000 });
  const approveMutation = useApproveRuntimePolicyDecision();
  const rejectMutation = useRejectRuntimePolicyDecision();
  const killSwitchMutation = useSetRuntimePolicyKillSwitch();

  const decisions = useMemo(() => approvalsQuery.data?.items ?? [], [approvalsQuery.data?.items]);
  const actionIntents = useMemo(() => actionIntentsQuery.data?.items ?? [], [actionIntentsQuery.data?.items]);
  const rows = useMemo(
    () => buildApprovalQueue({ decisions, intents: actionIntents }),
    [actionIntents, decisions],
  );
  const filteredRows = useMemo(() => filterApprovalQueue(rows, filter), [filter, rows]);
  const counts = useMemo(() => approvalQueueCounts(rows), [rows]);
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
    damageStopped: counts.damageStopped,
    error,
    killSwitchArmed,
    loading,
    pending: counts.pending,
    total: counts.total,
  });
  const busy = approveMutation.isPending || rejectMutation.isPending;
  const killSwitchPanel = (
    <KillSwitchPanel
      armed={killSwitchArmed}
      setArmed={setKillSwitchArmed}
      isPending={killSwitchMutation.isPending}
      onConfirm={async () => {
        setMessage(null);
        try {
          await killSwitchMutation.mutateAsync(true);
          setKillSwitchArmed(false);
          setMessage("Kill switch enabled.");
        } catch (caught) {
          setMessage(caught instanceof Error ? caught.message : "Kill switch update failed.");
        }
      }}
    />
  );

  useEffect(() => {
    if (rows.length === 0) {
      setSelectedId(null);
      return;
    }
    if (!initialFilterSettled) {
      const nextFilter = defaultFilterForRows(rows, search);
      setInitialFilterSettled(true);
      if (nextFilter !== filter) {
        setFilter(nextFilter);
        return;
      }
    }
    const linked = initialDeepLink(rows, search);
    if (linked && selectedId == null) {
      setSelectedId(linked);
      return;
    }
    if (filteredRows.length > 0 && (!selectedId || !filteredRows.some((row) => row.id === selectedId))) {
      setSelectedId(filteredRows[0].id);
      return;
    }
    if (!selectedId || !rows.some((row) => row.id === selectedId)) {
      setSelectedId(filteredRows[0]?.id ?? null);
      return;
    }
    if (filteredRows.length === 0 && selectedId != null) {
      setSelectedId(null);
    }
  }, [filter, filteredRows, initialFilterSettled, rows, search, selectedId]);

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
        await approveMutation.mutateAsync({ decisionId, reason });
        setMessage("Approval recorded.");
      } else {
        await rejectMutation.mutateAsync({ decisionId, reason });
        setMessage("Rejection recorded.");
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
        damageStopped={counts.damageStopped}
        expiringSoon={counts.expiringSoon}
        sequenceRisk={counts.sequenceRisk}
      />

      {message ? <div className="approval-v2-notice">{message}</div> : null}

      {error ? (
        <section className="approval-v2-alert approval-v2-tone-danger" role="status">
          <div>
            <span className="approval-v2-eyebrow">Refresh status</span>
            <strong>{degradedFeeds.join(", ")} unavailable</strong>
            <p>Showing the last usable approval state. Keep decisions conservative until the feed refreshes cleanly.</p>
          </div>
        </section>
      ) : null}

      {killSwitchPanel}

      {loading ? (
        <section className="approval-v2-empty-state">
          <h2>Loading runtime approvals</h2>
          <p>Fetching action holds and linked intent context.</p>
        </section>
      ) : rows.length === 0 ? (
        <section className="approval-v2-empty-state">
          <h2>No held actions in this view</h2>
          <p>When an agent attempts a high-risk action, Zroky will hold it here before commit.</p>
        </section>
      ) : (
        <>
          <DashboardWorkspace
            left={(
              <ApprovalQueue
                rows={filteredRows}
                selectedId={selectedRow?.id ?? null}
                filter={filter}
                onFilterChange={setFilter}
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
