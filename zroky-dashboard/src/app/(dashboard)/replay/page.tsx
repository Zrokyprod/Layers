"use client";

import { Suspense, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  ArrowRight,
  CheckCircle2,
  History,
  Loader2,
  PlayCircle,
  ShieldCheck,
  TriangleAlert,
  XCircle,
} from "lucide-react";

import type { ReplayRunItem } from "@/lib/api";
import { useReplayQuota, useReplayRuns } from "@/lib/hooks";
import { replayModeLabel, replayModeProof, replayVerificationLabel, replayVerifiedFix } from "@/lib/replay-mode";

const STATUSES = ["", "pending", "running", "pass", "fail", "error"] as const;

function timeAgo(iso: string) {
  const secs = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (secs < 60) return `${secs}s ago`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
}

function statusClass(status: string) {
  if (status === "pass") return "badge-green";
  if (status === "fail" || status === "error") return "badge-red";
  if (status === "running" || status === "pending") return "badge-yellow";
  return "badge-gray";
}

function statusLabel(status: string) {
  if (!status) return "All";
  return status.charAt(0).toUpperCase() + status.slice(1);
}

function proofLabel(value: boolean | null | undefined) {
  if (value === true) return "yes";
  if (value === false) return "no";
  return "unknown";
}

function deltaLabel(value: number | null | undefined, suffix = "") {
  if (value == null) return "n/a";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value}${suffix}`;
}

function moneyDeltaLabel(value: number | null | undefined) {
  if (value == null) return "n/a";
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  return `${sign}$${Math.abs(value).toFixed(4)}`;
}

function quotaPercent(used: number, limit: number) {
  if (limit <= 0) return 0;
  return Math.min(100, Math.round((used / limit) * 100));
}

function ReplayMetric({ label, value, helper }: { label: string; value: string; helper: string }) {
  return (
    <div className="metric-card replay-metric-card">
      <div className="notif-meta">{label}</div>
      <strong>{value}</strong>
      <span>{helper}</span>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  return <span className={`alert-cat-badge ${statusClass(status)}`}>{statusLabel(status)}</span>;
}

function RunRow({ run }: { run: ReplayRunItem }) {
  const total = run.summary.trace_count_at_dispatch;
  const executed = run.summary.trace_count_executed;
  const passRate = total > 0 ? Math.round((run.summary.pass_count / total) * 100) : null;
  const isVerifiedFix = replayVerifiedFix(run.replay_mode, run.summary.verified_fix);
  const verificationLabel = replayVerificationLabel(run.replay_mode, run.summary.verified_fix, run.summary.verification_status);
  const isStub = run.replay_mode === "stub";
  const costDelta = moneyDeltaLabel(run.summary.cost_delta_usd);
  const latencyDelta = deltaLabel(run.summary.latency_delta_ms, "ms");

  return (
    <Link href={`/replay/${run.id}`} className="replay-run-card">
      <div className="replay-run-main">
        <div className="replay-run-badges">
          <StatusBadge status={run.status} />
          <span className="alert-cat-badge badge-gray">{replayModeLabel(run.replay_mode)}</span>
          <span className={`alert-cat-badge ${isVerifiedFix ? "badge-green" : isStub ? "badge-yellow" : "badge-gray"}`}>
            {verificationLabel}
          </span>
        </div>

        <h2>
          Run {run.id.slice(0, 16)}
          <span>...</span>
        </h2>

        <div className="replay-run-meta">
          <span>trigger: {run.trigger}</span>
          {run.git_sha && <span>sha: {run.git_sha.slice(0, 8)}</span>}
          <span>golden set: {run.golden_set_id.slice(0, 12)}...</span>
          <span>{timeAgo(run.created_at)}</span>
        </div>

        <p className="replay-proof-copy">proof: {replayModeProof(run.replay_mode)}</p>
        {(run.replay_mode_warning || isStub) && (
          <p className="replay-warning">
            <TriangleAlert aria-hidden="true" />
            {isStub ? "Stub replay is a sanity check, not a verified fix." : run.replay_mode_warning}
          </p>
        )}
      </div>

      <div className="replay-run-proof">
        <div>
          <strong>{executed}/{total}</strong>
          <span>executed</span>
        </div>
        <div>
          <strong>{run.summary.pass_count} / {run.summary.fail_count}</strong>
          <span>pass / fail</span>
        </div>
        <div>
          <strong>{passRate == null ? "-" : `${passRate}%`}</strong>
          <span>pass rate</span>
        </div>
        <div>
          <strong>{proofLabel(run.summary.reproduced_original_failure)}</strong>
          <span>reproduced failure</span>
        </div>
        <div>
          <strong>{proofLabel(run.summary.fix_passed)}</strong>
          <span>fix passed</span>
        </div>
        <div>
          <strong>{costDelta} / {latencyDelta}</strong>
          <span>cost / latency delta</span>
        </div>
      </div>

      <div className="replay-run-open">
        Open
        <ArrowRight aria-hidden="true" />
      </div>
    </Link>
  );
}

export default function ReplayPage() {
  return (
    <Suspense fallback={<p className="hint">Loading replay runs...</p>}>
      <ReplayPageContent />
    </Suspense>
  );
}

function ReplayPageContent() {
  const searchParams = useSearchParams();
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [goldenSetId, setGoldenSetId] = useState(searchParams.get("golden_set_id") ?? "");
  const [cursor, setCursor] = useState<string | undefined>(undefined);
  const [pages, setPages] = useState<string[]>([]);

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
  const runs = useMemo(() => query.data?.items ?? [], [query.data?.items]);
  const nextCursor = query.data?.next_cursor;

  const runStats = useMemo(() => {
    const verified = runs.filter((run) => replayVerifiedFix(run.replay_mode, run.summary.verified_fix)).length;
    const sanityOnly = runs.filter((run) => run.replay_mode === "stub" || run.summary.verification_status === "sanity_check_only").length;
    const failed = runs.filter((run) => run.status === "fail" || run.status === "error").length;
    const passingTraces = runs.reduce((sum, run) => sum + run.summary.pass_count, 0);
    return { verified, sanityOnly, failed, passingTraces };
  }, [runs]);

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

  if (quotaQuery.isLoading) {
    return (
      <section className="panel issue-loading-panel" aria-label="Loading replay quota">
        <Loader2 aria-hidden="true" />
        <div>
          <strong>Loading replay proof engine</strong>
          <p className="notif-meta">Checking plan quota and recent replay runs.</p>
        </div>
      </section>
    );
  }

  if (isPlanEnabled === false) {
    return (
      <div className="replay-workspace">
        <section className="module-hero">
          <div className="module-hero-header">
            <div>
              <div className="module-eyebrow">
                <ShieldCheck aria-hidden="true" />
                Replay proof engine
              </div>
              <h1>Replay Runs</h1>
              <p>Replay needs Pro or higher so fixes can be tested against pinned production traces before release.</p>
            </div>
            <Link href="/settings/billing?upgrade_hint=replay.monthly_runs" className="btn btn-primary">
              Upgrade plan
              <ArrowRight aria-hidden="true" />
            </Link>
          </div>
        </section>
        <section className="panel replay-plan-gate">
          <ShieldCheck aria-hidden="true" />
          <h2>Replay requires Pro or higher</h2>
          <p>The Replay module runs golden traces against current prompt and model configuration to catch regressions before they reach production.</p>
        </section>
      </div>
    );
  }

  return (
    <div className="replay-workspace">
      <section className="module-hero replay-hero">
        <div className="module-hero-header">
          <div>
            <div className="module-eyebrow">
              <PlayCircle aria-hidden="true" />
              Replay proof engine
            </div>
            <h1>Replay Runs</h1>
            <p>Compare candidate fixes against production memory. Stub runs stay sanity-only; verified means a non-stub replay passed real comparison.</p>
          </div>
          <Link href="/goldens" className="btn btn-primary">
            Run a golden set
            <ArrowRight aria-hidden="true" />
          </Link>
        </div>
      </section>

      <section className="metric-strip" aria-label="Replay summary">
        <ReplayMetric label="Visible runs" value={runs.length.toLocaleString()} helper="Current filtered queue" />
        <ReplayMetric label="Verified fixes" value={runStats.verified.toLocaleString()} helper="Non-stub runs with proof" />
        <ReplayMetric label="Sanity only" value={runStats.sanityOnly.toLocaleString()} helper="Stub or unverified checks" />
        <ReplayMetric label="Failing runs" value={runStats.failed.toLocaleString()} helper={`${runStats.passingTraces.toLocaleString()} passing traces visible`} />
      </section>

      {quota && quota.limit !== -1 && (
        <section className="replay-quota-panel">
          <div>
            <strong>{quota.used.toLocaleString()} / {quota.limit.toLocaleString()}</strong>
            <span>replay runs used this month - resets {quota.resets_at}</span>
          </div>
          <div className="replay-quota-track" aria-hidden="true">
            <span style={{ width: `${quotaPercent(quota.used, quota.limit)}%` }} />
          </div>
          {quotaPercent(quota.used, quota.limit) >= 90 && (
            <Link href="/settings/billing?upgrade_hint=replay.monthly_runs" className="notif-action-link">
              Upgrade plan
            </Link>
          )}
        </section>
      )}

      <section className="replay-filter-bar" aria-label="Replay filters">
        <div className="replay-status-tabs">
          {STATUSES.map((status) => (
            <button
              key={status || "all"}
              type="button"
              onClick={() => {
                setStatusFilter(status);
                handleFilterChange();
              }}
              className={statusFilter === status ? "is-active" : ""}
            >
              {statusLabel(status)}
            </button>
          ))}
        </div>
        <input
          type="text"
          placeholder="Filter by Golden Set ID..."
          value={goldenSetId}
          onChange={(event) => {
            setGoldenSetId(event.target.value);
            handleFilterChange();
          }}
          className="input input-sm replay-golden-filter"
        />
      </section>

      {query.isLoading ? (
        <section className="panel issue-loading-panel" aria-label="Loading replay runs">
          <Loader2 aria-hidden="true" />
          <div>
            <strong>Loading replay runs</strong>
            <p className="notif-meta">Reading recent proof results.</p>
          </div>
        </section>
      ) : runs.length === 0 ? (
        <section className="empty replay-empty">
          <History aria-hidden="true" />
          <strong>No replay runs found.</strong>
          <span>
            Trigger a run from the <Link href="/goldens" className="notif-action-link">Goldens</Link> page.
          </span>
        </section>
      ) : (
        <section className="replay-run-list" aria-label="Replay runs">
          {runs.map((run) => (
            <RunRow key={run.id} run={run} />
          ))}
        </section>
      )}

      {(pages.length > 0 || nextCursor) && (
        <div className="replay-pagination">
          <button type="button" onClick={loadPrev} disabled={pages.length === 0} className="btn btn-soft">
            Previous
          </button>
          <button type="button" onClick={loadMore} disabled={!nextCursor} className="btn btn-soft">
            Load more
          </button>
        </div>
      )}

      <section className="panel panel-muted replay-honesty-panel">
        <div>
          <TriangleAlert aria-hidden="true" />
          <strong>Replay honesty rule</strong>
        </div>
        <p>Stub replay is a cheap sanity check. A fix is only verified when a non-stub replay proves original failure reproduction and candidate fix pass.</p>
        <div className="replay-honesty-grid">
          <span><CheckCircle2 aria-hidden="true" /> real_llm: real comparison</span>
          <span><XCircle aria-hidden="true" /> stub: sanity only</span>
        </div>
      </section>
    </div>
  );
}
