"use client";

import { useState } from "react";
import Link from "next/link";
import { useReplayRuns, useReplayQuota } from "@/lib/hooks";
import type { ReplayRunItem } from "@/lib/api";
import { replayModeLabel, replayModeProof, replayVerificationLabel, replayVerifiedFix } from "@/lib/replay-mode";

// ── helpers ───────────────────────────────────────────────────────────────────

function timeAgo(iso: string) {
  const secs = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (secs < 60) return `${secs}s ago`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
}

const STATUS_COLOURS: Record<string, string> = {
  pending: "bg-slate-700 text-slate-300",
  running: "bg-blue-900/60 text-blue-300 animate-pulse",
  pass: "bg-emerald-900/60 text-emerald-300",
  fail: "bg-red-900/60 text-red-300",
  error: "bg-amber-900/60 text-amber-300",
};

const STATUSES = ["", "pending", "running", "pass", "fail", "error"] as const;

function StatusBadge({ status }: { status: string }) {
  const cls = STATUS_COLOURS[status] ?? "bg-slate-700 text-slate-300";
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${cls}`}>
      {status}
    </span>
  );
}


function proofLabel(value: boolean | null | undefined) {
  if (value === true) return "yes";
  if (value === false) return "no";
  return "unknown";
}

function deltaLabel(value: number | null | undefined, suffix = "") {
  if (value == null) return null;
  const sign = value > 0 ? "+" : "";
  return `${sign}${value}${suffix}`;
}

function moneyDeltaLabel(value: number | null | undefined) {
  if (value == null) return null;
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  return `${sign}$${Math.abs(value).toFixed(4)}`;
}

function RunRow({ run }: { run: ReplayRunItem }) {
  const total = run.summary.trace_count_at_dispatch;
  const executed = run.summary.trace_count_executed;
  const passRate = total > 0 ? Math.round((run.summary.pass_count / total) * 100) : null;
  const isVerifiedFix = replayVerifiedFix(run.replay_mode, run.summary.verified_fix);
  const verificationLabel = replayVerificationLabel(run.replay_mode, run.summary.verified_fix, run.summary.verification_status);
  const verificationTone = isVerifiedFix
    ? "text-emerald-400"
    : run.replay_mode === "stub" || run.summary.verification_status === "sanity_check_only"
    ? "text-amber-400"
    : "text-slate-400";
  const costDelta = moneyDeltaLabel(run.summary.cost_delta_usd);
  const latencyDelta = deltaLabel(run.summary.latency_delta_ms, "ms");

  return (
    <Link
      href={`/replay/${run.id}`}
      className="group flex flex-col gap-3 rounded-lg border border-white/[0.06] bg-white/[0.02] p-4 hover:border-white/[0.12] hover:bg-white/[0.04] transition-colors"
    >
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex items-center gap-2 flex-wrap">
            <code className="text-xs font-mono text-slate-400">{run.id.slice(0, 16)}...</code>
            <StatusBadge status={run.status} />
            <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-300">{replayModeLabel(run.replay_mode)}</span>
            <span className={`rounded bg-slate-900 px-1.5 py-0.5 text-[10px] ${verificationTone}`}>
              {verificationLabel}
            </span>
          </div>
          <div className="flex items-center gap-3 text-xs text-slate-500 flex-wrap">
            <span>trigger: <span className="text-slate-400">{run.trigger}</span></span>
            {run.git_sha && (
              <span>sha: <code className="font-mono text-slate-400">{run.git_sha.slice(0, 8)}</code></span>
            )}
            <span>golden set: <code className="font-mono text-slate-400">{run.golden_set_id.slice(0, 12)}...</code></span>
            <span>{timeAgo(run.created_at)}</span>
          </div>
          <p className="text-xs text-slate-500">proof: <span className="text-slate-300">{replayModeProof(run.replay_mode)}</span></p>
          {(run.replay_mode_warning || run.replay_mode === "stub") && (
            <p className="text-xs text-amber-300">{run.replay_mode === "stub" ? "Stub replay is a sanity check, not a verified fix." : run.replay_mode_warning}</p>
          )}
        </div>

        <div className="flex items-center gap-4 text-xs shrink-0">
          {total > 0 ? (
            <>
              <span className="text-emerald-400">{run.summary.pass_count} pass</span>
              <span className="text-red-400">{run.summary.fail_count} fail</span>
              {run.summary.error_count > 0 && (
                <span className="text-amber-400">{run.summary.error_count} err</span>
              )}
              {passRate !== null && (
                <span className="text-slate-400">{passRate}%</span>
              )}
            </>
          ) : (
            <span className="text-slate-600">{total} traces</span>
          )}
          <span className="text-slate-600 group-hover:text-slate-400 transition-colors">Open</span>
        </div>
      </div>

      <div className="grid gap-2 text-xs text-slate-500 sm:grid-cols-2 lg:grid-cols-4">
        <span>executed: <span className="text-slate-300">{executed}/{total}</span></span>
        <span>original failure: <span className="text-slate-300">{proofLabel(run.summary.reproduced_original_failure)}</span></span>
        <span>fix passed: <span className="text-slate-300">{proofLabel(run.summary.fix_passed)}</span></span>
        <span>
          deltas:{" "}
          <span className="text-slate-300">
            {costDelta ?? "cost n/a"} / {latencyDelta ?? "latency n/a"}
          </span>
        </span>
      </div>
    </Link>
  );
}

// ── main page ─────────────────────────────────────────────────────────────────

export default function ReplayPage() {
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [goldenSetId, setGoldenSetId] = useState("");
  const [cursor, setCursor] = useState<string | undefined>(undefined);
  const [pages, setPages] = useState<string[]>([]); // cursor stack

  const quotaQuery = useReplayQuota();
  const quota = quotaQuery.data;
  const isPlanEnabled = quota?.enabled ?? null;

  const params = {
    ...(statusFilter ? { status: statusFilter } : {}),
    ...(goldenSetId.trim() ? { golden_set_id: goldenSetId.trim() } : {}),
    ...(cursor ? { cursor } : {}),
    limit: 20,
  };

  const query = useReplayRuns(params, { enabled: isPlanEnabled === true });
  const runs = query.data?.items ?? [];
  const nextCursor = query.data?.next_cursor;

  function handleFilterChange() {
    setCursor(undefined);
    setPages([]);
  }

  function loadMore() {
    if (!nextCursor) return;
    setPages((p) => [...p, cursor ?? ""]);
    setCursor(nextCursor);
  }

  function loadPrev() {
    const prev = pages[pages.length - 1];
    setPages((p) => p.slice(0, -1));
    setCursor(prev || undefined);
  }

  // ── plan gate ──────────────────────────────────────────────────────────────
  if (quotaQuery.isLoading) {
    return (
      <div className="py-20 text-center text-sm text-slate-500">
        Loading…
      </div>
    );
  }

  if (isPlanEnabled === false) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-lg font-semibold text-white">Replay Runs</h1>
          <p className="mt-0.5 text-xs text-slate-500">
            Golden-set replay results — regression checks against pinned traces.
          </p>
        </div>
        <div className="rounded-xl border border-indigo-900/40 bg-indigo-950/30 p-8 text-center space-y-4">
          <div className="text-2xl">🔒</div>
          <h2 className="text-base font-semibold text-white">
            Replay requires Pro or higher
          </h2>
          <p className="text-sm text-slate-400 max-w-md mx-auto">
            The Replay module runs your golden traces against your current
            prompt and model configuration to catch regressions before they
            reach production.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-3 text-xs text-slate-500">
            <span className="rounded-full bg-slate-800 px-3 py-1">Starter — 100 runs/mo (legacy only)</span>
            <span className="rounded-full bg-indigo-900/60 text-indigo-300 px-3 py-1 font-semibold">Pro — 5,000 runs/mo</span>
            <span className="rounded-full bg-slate-800 px-3 py-1">Team — 50,000 runs/mo</span>
            <span className="rounded-full bg-slate-800 px-3 py-1">Enterprise — unlimited</span>
          </div>
          <Link
            href="/settings/billing?upgrade_hint=pilot.autopilot_enabled"
            className="inline-flex items-center rounded-lg bg-indigo-600 px-5 py-2 text-sm font-semibold text-white hover:bg-indigo-500 transition-colors"
          >
            Upgrade to Pro →
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold text-white">Replay Runs</h1>
          <p className="mt-0.5 text-xs text-slate-500">
            Golden-set replay results — regression checks against pinned traces.
          </p>
        </div>
        <Link
          href="/goldens"
          className="rounded-lg bg-indigo-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500 transition-colors"
        >
          + Run a Golden Set
        </Link>
      </div>

      {/* Quota banner */}
      {quota && quota.limit !== -1 && (
        <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-4 py-3 flex flex-wrap items-center justify-between gap-2">
          <div className="space-y-1 flex-1 min-w-0">
            <div className="flex items-center gap-2 text-xs text-slate-400">
              <span className="font-medium text-slate-200">
                {quota.used.toLocaleString()} / {quota.limit.toLocaleString()}
              </span>
              replay runs used this month
              <span className="text-slate-600">· resets {quota.resets_at}</span>
            </div>
            <div className="h-1 w-full max-w-xs rounded-full bg-white/[0.06] overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${
                  quota.used / quota.limit >= 0.9
                    ? "bg-red-500"
                    : quota.used / quota.limit >= 0.75
                    ? "bg-amber-500"
                    : "bg-indigo-500"
                }`}
                style={{ width: `${Math.min(100, (quota.used / quota.limit) * 100)}%` }}
              />
            </div>
          </div>
          {quota.used / quota.limit >= 0.9 && (
            <Link
              href="/settings/billing?upgrade_hint=replay.monthly_runs"
              className="shrink-0 text-xs text-indigo-400 hover:underline"
            >
              Upgrade plan →
            </Link>
          )}
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1 rounded-lg border border-white/[0.08] bg-white/[0.03] p-1">
          {STATUSES.map((s) => (
            <button
              key={s || "all"}
              type="button"
              onClick={() => { setStatusFilter(s); handleFilterChange(); }}
              className={`rounded px-3 py-1 text-xs font-medium transition-colors ${
                statusFilter === s
                  ? "bg-indigo-600 text-white"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {s || "All"}
            </button>
          ))}
        </div>
        <input
          type="text"
          placeholder="Filter by Golden Set ID…"
          value={goldenSetId}
          onChange={(e) => { setGoldenSetId(e.target.value); handleFilterChange(); }}
          className="rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-xs text-slate-200 placeholder:text-slate-600 outline-none focus:border-indigo-500/50 transition-colors w-64"
        />
      </div>

      {/* List */}
      {query.isLoading && (
        <p className="py-12 text-center text-sm text-slate-500">Loading replay runs…</p>
      )}

      {!query.isLoading && runs.length === 0 && (
        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-12 text-center">
          <p className="text-sm text-slate-400">No replay runs found.</p>
          <p className="mt-1 text-xs text-slate-600">
            Trigger a run from the{" "}
            <Link href="/goldens" className="text-indigo-400 hover:underline">Golden Sets</Link> page.
          </p>
        </div>
      )}

      {runs.length > 0 && (
        <div className="space-y-2">
          {runs.map((run) => (
            <RunRow key={run.id} run={run} />
          ))}
        </div>
      )}

      {/* Pagination */}
      {(pages.length > 0 || nextCursor) && (
        <div className="flex items-center justify-between pt-2">
          <button
            type="button"
            onClick={loadPrev}
            disabled={pages.length === 0}
            className="rounded-lg border border-white/[0.08] px-4 py-1.5 text-xs text-slate-400 hover:text-slate-200 disabled:opacity-40 transition-colors"
          >
            ← Previous
          </button>
          <button
            type="button"
            onClick={loadMore}
            disabled={!nextCursor}
            className="rounded-lg border border-white/[0.08] px-4 py-1.5 text-xs text-slate-400 hover:text-slate-200 disabled:opacity-40 transition-colors"
          >
            Load more →
          </button>
        </div>
      )}
    </div>
  );
}
