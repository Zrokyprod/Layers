"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, GitPullRequest, Loader2, ShieldAlert, ShieldCheck } from "lucide-react";

import {
  getRegressionCIRun,
  listReplayRuns,
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

type PageState = {
  runs: ReplayRunItem[];
  details: Record<string, RegressionCIRunDetailResponse>;
};

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

export default function CiGatesPage() {
  const [state, setState] = useState<PageState>({ runs: [], details: {} });
  const [loading, setLoading] = useState(true);
  const [replayContextWarning, setReplayContextWarning] = useState<string | null>(null);
  const [detailWarning, setDetailWarning] = useState<string | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    async function load() {
      setLoading(true);
      setReplayContextWarning(null);
      setDetailWarning(null);
      try {
        const runsResponse = await listReplayRuns({ limit: 50 }, ctrl.signal);
        const ciRuns = runsResponse.items.filter(isCiRun).slice(0, 30);
        const detailResults = await Promise.allSettled(
          ciRuns.slice(0, 20).map((run) => getRegressionCIRun(run.id, ctrl.signal)),
        );
        if (ctrl.signal.aborted) return;
        const details: Record<string, RegressionCIRunDetailResponse> = {};
        for (const result of detailResults) {
          if (result.status === "fulfilled") details[result.value.run_id] = result.value;
        }
        if (detailResults.some((result) => result.status === "rejected")) {
          setDetailWarning("Regression CI details unavailable for some runs.");
        }
        setState({ runs: ciRuns, details });
      } catch (loadError) {
        if ((loadError as { name?: string }).name === "AbortError") return;
        setState({ runs: [], details: {} });
        setReplayContextWarning("Replay run context unavailable. CI gate results are still shown when available.");
      } finally {
        if (!ctrl.signal.aborted) setLoading(false);
      }
    }
    void load();
    return () => ctrl.abort();
  }, []);

  const metrics = useMemo(() => {
    let failed = 0;
    let notVerified = 0;
    let passed = 0;
    let protectedFlows = 0;
    for (const run of state.runs) {
      const detail = state.details[run.id];
      const status = normalizeStatus(run, detail);
      if (status === "fail" || status === "error") failed += 1;
      if (status === "not_verified") notVerified += 1;
      if (status === "pass") passed += 1;
      protectedFlows += protectedFlowCount(run, detail);
    }
    return { failed, notVerified, passed, protectedFlows };
  }, [state.details, state.runs]);

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
      </section>

      <section className="ci-kpi-grid" aria-label="CI gate summary">
        <article className="ci-kpi-card">
          <span>Failed / blocked</span>
          <strong>{metrics.failed}</strong>
          <p>Requires protected-flow review</p>
        </article>
        <article className="ci-kpi-card">
          <span>Not verified</span>
          <strong>{metrics.notVerified}</strong>
          <p>Never counted as pass</p>
        </article>
        <article className="ci-kpi-card">
          <span>Passed</span>
          <strong>{metrics.passed}</strong>
          <p>Trusted replay under threshold</p>
        </article>
        <article className="ci-kpi-card">
          <span>Protected flows</span>
          <strong>{metrics.protectedFlows}</strong>
          <p>Checked in loaded runs</p>
        </article>
      </section>

      <section className="ci-table-section">
        <header className="ci-section-header">
          <div>
            <h2>Regression CI runs</h2>
            <p>PR verdicts, replay proof, failed flow counts, and commit metadata.</p>
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
                {state.runs.map((run) => {
                  const detail = state.details[run.id];
                  const status = normalizeStatus(run, detail);
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
