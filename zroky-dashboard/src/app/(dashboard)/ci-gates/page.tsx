"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  GitPullRequest,
  Loader2,
  Play,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";

import {
  getRegressionCIRun,
  listReplayRuns,
  runRegressionCI,
  type RegressionCIChangedFilePayload,
  type RegressionCIRunDetailResponse,
  type ReplayRunItem,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import {
  actionLabel,
  failedFlowCount,
  formatRate,
  isCiRun,
  normalizeStatus,
  protectedFlowCount,
  regressionRate,
  replayProofBadgeClass,
  replayProofLabel,
  runMeta,
  runTitle,
  shortSha,
  statusBadgeClass,
  statusLabel,
} from "./ci-utils";

type CiStatusFilter = "all" | "blocked" | "not_verified" | "running" | "pass";
type CiSort = "completed_desc" | "completed_asc" | "regression_desc" | "failed_desc";

type PageState = {
  runs: ReplayRunItem[];
  details: Record<string, RegressionCIRunDetailResponse>;
};

type DecoratedRun = {
  run: ReplayRunItem;
  detail?: RegressionCIRunDetailResponse;
  status: string;
};

const ACTIVE_STATUSES = new Set(["running", "pending", "queued"]);
const BLOCKED_STATUSES = new Set(["fail", "error"]);

function StatusBadge({ status }: { status: string }) {
  return <span className={`alert-cat-badge ${statusBadgeClass(status)}`}>{statusLabel(status)}</span>;
}

function ReplayProofBadge({ run, detail }: { run: ReplayRunItem; detail?: RegressionCIRunDetailResponse }) {
  return (
    <span className={`alert-cat-badge ${replayProofBadgeClass(run, detail)}`}>
      {replayProofLabel(run, detail)}
    </span>
  );
}

function failedFlowDisplay(run: ReplayRunItem, detail?: RegressionCIRunDetailResponse): string {
  const status = normalizeStatus(run, detail);
  if (status === "not_verified") return "-";
  const count = failedFlowCount(run, detail);
  return count == null ? "-" : String(count);
}

function completedTimestamp(run: ReplayRunItem): number {
  const value = run.completed_at ?? run.started_at ?? run.created_at;
  const timestamp = value ? Date.parse(value) : 0;
  return Number.isFinite(timestamp) ? timestamp : 0;
}

function matchesStatusFilter(status: string, filter: CiStatusFilter): boolean {
  if (filter === "all") return true;
  if (filter === "blocked") return BLOCKED_STATUSES.has(status);
  if (filter === "running") return ACTIVE_STATUSES.has(status);
  return status === filter;
}

function searchableText(run: ReplayRunItem, detail: RegressionCIRunDetailResponse | undefined, status: string): string {
  return [
    run.id,
    run.git_sha,
    run.golden_set_id,
    status,
    statusLabel(status),
    runTitle(run, detail),
    runMeta(run, detail),
    replayProofLabel(run, detail),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function parseChangedFiles(value: string): RegressionCIChangedFilePayload[] {
  return value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean)
    .map((path) => ({ path }));
}

export default function CiGatesPage() {
  const router = useRouter();
  const [state, setState] = useState<PageState>({ runs: [], details: {} });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [replayContextWarning, setReplayContextWarning] = useState<string | null>(null);
  const [detailWarning, setDetailWarning] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<CiStatusFilter>("all");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<CiSort>("completed_desc");
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [gitSha, setGitSha] = useState("");
  const [threshold, setThreshold] = useState("0.02");
  const [changedFiles, setChangedFiles] = useState("");
  const [runError, setRunError] = useState<string | null>(null);
  const [runMessage, setRunMessage] = useState<string | null>(null);
  const [runningGate, setRunningGate] = useState(false);

  const loadRuns = useCallback(async (signal?: AbortSignal, mode: "initial" | "refresh" = "refresh") => {
    if (mode === "initial") setLoading(true);
    else setRefreshing(true);
      setReplayContextWarning(null);
      setDetailWarning(null);
      try {
        const runsResponse = await listReplayRuns({ limit: 50 }, signal);
        const ciRuns = runsResponse.items.filter(isCiRun).slice(0, 30);
        const detailResults = await Promise.allSettled(
          ciRuns.slice(0, 20).map((run) => getRegressionCIRun(run.id, signal)),
        );
        if (signal?.aborted) return;
        const details: Record<string, RegressionCIRunDetailResponse> = {};
        for (const result of detailResults) {
          if (result.status === "fulfilled") details[result.value.run_id] = result.value;
        }
        if (detailResults.some((result) => result.status === "rejected")) {
          setDetailWarning("Regression CI details unavailable for some runs.");
        }
        setState({ runs: ciRuns, details });
        setLastUpdated(new Date().toISOString());
      } catch (loadError) {
        if ((loadError as { name?: string }).name === "AbortError") return;
        if (mode === "initial") setState({ runs: [], details: {} });
        setReplayContextWarning("Replay run context unavailable. CI gate results are still shown when available.");
      } finally {
        if (!signal?.aborted) {
          if (mode === "initial") setLoading(false);
          else setRefreshing(false);
        }
      }
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    void loadRuns(ctrl.signal, "initial");
    return () => ctrl.abort();
  }, [loadRuns]);

  const decoratedRuns = useMemo<DecoratedRun[]>(
    () =>
      state.runs.map((run) => {
        const detail = state.details[run.id];
        return { run, detail, status: normalizeStatus(run, detail) };
      }),
    [state.details, state.runs],
  );

  const hasActiveRuns = useMemo(
    () => decoratedRuns.some((item) => ACTIVE_STATUSES.has(item.status)),
    [decoratedRuns],
  );

  useEffect(() => {
    if (!autoRefresh || !hasActiveRuns) return;
    const timer = window.setInterval(() => {
      void loadRuns(undefined, "refresh");
    }, 10_000);
    return () => window.clearInterval(timer);
  }, [autoRefresh, hasActiveRuns, loadRuns]);

  async function onRunGate() {
    const sha = gitSha.trim();
    setRunError(null);
    setRunMessage(null);
    if (sha.length < 4) {
      setRunError("Enter a commit SHA with at least 4 characters.");
      return;
    }
    const thresholdValue = threshold.trim() ? Number(threshold) : undefined;
    if (thresholdValue != null && (!Number.isFinite(thresholdValue) || thresholdValue < 0 || thresholdValue > 1)) {
      setRunError("Threshold must be a number between 0 and 1.");
      return;
    }
    setRunningGate(true);
    try {
      const created = await runRegressionCI({
        git_sha: sha,
        threshold: thresholdValue,
        changed_files: parseChangedFiles(changedFiles),
      });
      setRunMessage(`CI gate queued: ${created.run_id}`);
      setCreateOpen(false);
      router.push(`/ci-gates/${created.run_id}`);
    } catch (error) {
      setRunError(error instanceof Error ? error.message : "Failed to run CI gate.");
    } finally {
      setRunningGate(false);
    }
  }

  const metrics = useMemo(() => {
    let failed = 0;
    let notVerified = 0;
    let passed = 0;
    let running = 0;
    let protectedFlows = 0;
    for (const { run, detail, status } of decoratedRuns) {
      if (status === "fail" || status === "error") failed += 1;
      if (status === "not_verified") notVerified += 1;
      if (status === "pass") passed += 1;
      if (ACTIVE_STATUSES.has(status)) running += 1;
      protectedFlows += protectedFlowCount(run, detail);
    }
    return { failed, notVerified, passed, running, protectedFlows };
  }, [decoratedRuns]);

  const filteredRuns = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return decoratedRuns
      .filter(({ run, detail, status }) => matchesStatusFilter(status, statusFilter) && (!needle || searchableText(run, detail, status).includes(needle)))
      .sort((left, right) => {
        if (sort === "completed_asc") return completedTimestamp(left.run) - completedTimestamp(right.run);
        if (sort === "regression_desc") return (regressionRate(right.run, right.detail) ?? -1) - (regressionRate(left.run, left.detail) ?? -1);
        if (sort === "failed_desc") return (failedFlowCount(right.run, right.detail) ?? -1) - (failedFlowCount(left.run, left.detail) ?? -1);
        return completedTimestamp(right.run) - completedTimestamp(left.run);
      });
  }, [decoratedRuns, query, sort, statusFilter]);

  const clearFilters = () => {
    setStatusFilter("all");
    setQuery("");
    setSort("completed_desc");
  };

  return (
    <div className="ci-gates-mvp">
      <section className="ci-hero">
        <div>
          <div className="ci-eyebrow">
            <GitPullRequest aria-hidden="true" />
            Release safety
          </div>
          <h1>CI Gates</h1>
          <p>Replay-backed PR safety checks for protected agent flows.</p>
          <span>Review failed, not verified, and blocking regression runs before merge.</span>
        </div>
        <div className="ci-hero-actions">
          <button type="button" className="btn btn-soft" onClick={() => void loadRuns(undefined, "refresh")} disabled={loading || refreshing}>
            <RefreshCw aria-hidden="true" className={refreshing ? "ci-spin" : undefined} />
            {refreshing ? "Refreshing" : "Refresh"}
          </button>
          <button type="button" className="btn btn-primary" onClick={() => setCreateOpen((value) => !value)}>
            <Play aria-hidden="true" />
            Run gate
          </button>
        </div>
      </section>

      <section className="ci-kpi-grid" aria-label="CI gate summary">
        <button type="button" className={`ci-kpi-card ci-kpi-button${statusFilter === "blocked" ? " is-active" : ""}`} onClick={() => setStatusFilter("blocked")}>
          <span>Failed / blocked</span>
          <strong>{metrics.failed}</strong>
          <p>Requires protected-flow review</p>
        </button>
        <button type="button" className={`ci-kpi-card ci-kpi-button${statusFilter === "not_verified" ? " is-active" : ""}`} onClick={() => setStatusFilter("not_verified")}>
          <span>Not verified</span>
          <strong>{metrics.notVerified}</strong>
          <p>Never counted as pass</p>
        </button>
        <button type="button" className={`ci-kpi-card ci-kpi-button${statusFilter === "running" ? " is-active" : ""}`} onClick={() => setStatusFilter("running")}>
          <span>Running / pending</span>
          <strong>{metrics.running}</strong>
          <p>Auto-refresh watches these</p>
        </button>
        <button type="button" className={`ci-kpi-card ci-kpi-button${statusFilter === "pass" ? " is-active" : ""}`} onClick={() => setStatusFilter("pass")}>
          <span>Passed</span>
          <strong>{metrics.passed}</strong>
          <p>Trusted replay under threshold</p>
        </button>
        <button type="button" className={`ci-kpi-card ci-kpi-button${statusFilter === "all" && !query ? " is-active" : ""}`} onClick={clearFilters}>
          <span>Protected flows</span>
          <strong>{metrics.protectedFlows}</strong>
          <p>Checked in loaded runs</p>
        </button>
      </section>

      <section className="ci-toolbar" aria-label="CI gate controls">
        <label className="ci-search-box">
          <Search aria-hidden="true" />
          <input
            aria-label="Search CI gates"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search PR, branch, SHA, run ID"
          />
        </label>
        <label className="ci-field">
          <span>Status</span>
          <select aria-label="Status filter" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as CiStatusFilter)}>
            <option value="all">All gates</option>
            <option value="blocked">Failed / error</option>
            <option value="not_verified">Not verified</option>
            <option value="running">Running / pending</option>
            <option value="pass">Passed</option>
          </select>
        </label>
        <label className="ci-field">
          <span>Sort</span>
          <select aria-label="Sort CI gates" value={sort} onChange={(event) => setSort(event.target.value as CiSort)}>
            <option value="completed_desc">Newest first</option>
            <option value="completed_asc">Oldest first</option>
            <option value="regression_desc">Highest regression</option>
            <option value="failed_desc">Most failed flows</option>
          </select>
        </label>
        <label className="ci-toggle">
          <input type="checkbox" checked={autoRefresh} onChange={(event) => setAutoRefresh(event.target.checked)} />
          <span>Auto-refresh active gates</span>
        </label>
        <span className="ci-last-updated">{lastUpdated ? `Updated ${formatDateTime(lastUpdated)}` : "Not refreshed yet"}</span>
      </section>

      {createOpen ? (
        <section className="ci-run-card" aria-label="Run a CI gate">
          <form
            className="ci-run-form"
            onSubmit={(event) => {
              event.preventDefault();
              void onRunGate();
            }}
          >
            <label className="ci-field">
              <span>Commit SHA</span>
              <input aria-label="Commit SHA" value={gitSha} onChange={(event) => setGitSha(event.target.value)} placeholder="abc1234" />
            </label>
            <label className="ci-field">
              <span>Regression threshold</span>
              <input aria-label="Regression threshold" value={threshold} onChange={(event) => setThreshold(event.target.value)} inputMode="decimal" />
            </label>
            <label className="ci-field ci-field-wide">
              <span>Changed files</span>
              <textarea
                aria-label="Changed files"
                value={changedFiles}
                onChange={(event) => setChangedFiles(event.target.value)}
                placeholder="src/agent/refund.ts&#10;prompts/refund.md"
              />
            </label>
            <div className="ci-run-actions">
              <button type="submit" className="btn btn-primary" disabled={runningGate}>
                <Play aria-hidden="true" />
                {runningGate ? "Queueing..." : "Queue CI gate"}
              </button>
              <button type="button" className="btn btn-soft" onClick={() => setCreateOpen(false)}>
                Cancel
              </button>
            </div>
          </form>
          {runError ? <div className="ci-context-warning ci-context-error" role="alert"><AlertTriangle aria-hidden="true" /> <span>{runError}</span></div> : null}
          {runMessage ? <div className="ci-context-warning" role="status"><CheckCircle2 aria-hidden="true" /> <span>{runMessage}</span></div> : null}
        </section>
      ) : null}

      <section className="ci-table-section">
        <header className="ci-section-header">
          <div>
            <h2>Regression CI runs</h2>
            <p>{filteredRuns.length} visible of {state.runs.length} loaded runs. PR verdicts, replay proof, failed flow counts, and commit metadata.</p>
          </div>
          <span className="ci-trust-copy">
            <ShieldAlert aria-hidden="true" />
            Not verified is never treated as pass.
          </span>
        </header>

        {replayContextWarning ? (
          <div className="ci-context-warning" role="status">
            <AlertTriangle aria-hidden="true" />
            <span>{replayContextWarning}</span>
          </div>
        ) : null}

        {detailWarning ? (
          <div className="ci-context-warning" role="status">
            <AlertTriangle aria-hidden="true" />
            <span>{detailWarning}</span>
          </div>
        ) : null}

        {loading ? (
          <div className="ci-empty">
            <Loader2 aria-hidden="true" />
            <strong>Loading CI gate runs...</strong>
          </div>
        ) : state.runs.length === 0 ? (
          <div className="ci-empty">
            <ShieldCheck aria-hidden="true" />
            <strong>No CI gate runs yet</strong>
            <p>Run Goldens from GitHub CI to block regressions before merge.</p>
            <Link href="/goldens" className="btn btn-primary">View Goldens</Link>
          </div>
        ) : filteredRuns.length === 0 ? (
          <div className="ci-empty">
            <Search aria-hidden="true" />
            <strong>No CI gates match filters</strong>
            <p>Clear filters or search for another PR, branch, SHA, or status.</p>
            <button type="button" className="btn btn-soft" onClick={clearFilters}>Clear filters</button>
          </div>
        ) : (
          <div className="ci-table-wrap">
            <table className="ci-runs-table">
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Status</th>
                  <th>Regression</th>
                  <th>Failed flows</th>
                  <th>Replay proof</th>
                  <th>Git SHA</th>
                  <th>Completed</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {filteredRuns.map(({ run, detail, status }) => {
                  return (
                    <tr key={run.id}>
                      <td>
                        <div className="ci-run-cell">
                          <Link href={`/ci-gates/${run.id}`}>{runTitle(run, detail)}</Link>
                          <span>{runMeta(run, detail)}</span>
                        </div>
                      </td>
                      <td><StatusBadge status={status} /></td>
                      <td>{status === "not_verified" ? "-" : formatRate(regressionRate(run, detail))}</td>
                      <td>{failedFlowDisplay(run, detail)}</td>
                      <td><ReplayProofBadge run={run} detail={detail} /></td>
                      <td><span className="ci-sha">{shortSha(run.git_sha)}</span></td>
                      <td>{formatDateTime(run.completed_at ?? run.started_at ?? run.created_at)}</td>
                      <td>
                        <Link href={`/ci-gates/${run.id}`} className="btn btn-soft btn-sm">
                          {actionLabel(status)}
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="ci-footnote-card">
        <CheckCircle2 aria-hidden="true" />
        <span>Passed means trusted replay completed under threshold. Not verified cannot prove PR safety.</span>
      </section>
    </div>
  );
}
