"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Copy,
  ExternalLink,
  GitPullRequest,
  Loader2,
  Play,
  RefreshCw,
  RotateCcw,
  ShieldAlert,
} from "lucide-react";

import {
  getRegressionCIRun,
  getReplayRun,
  runRegressionCI,
  type RegressionCIRunDetailResponse,
  type ReplayRunDetailItem,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import {
  actionLabel,
  failedFlowCount,
  failedProtectedFlows,
  formatRate,
  goldenSetId,
  isRecord,
  normalizeStatus,
  numericField,
  prCommentPreview,
  prUrl,
  regressionRate,
  replayProofBadgeClass,
  replayProofLabel,
  runMeta,
  runNotes,
  runTitle,
  shortSha,
  statusBadgeClass,
  statusLabel,
  stringField,
  summaryUrl,
  thresholdRate,
  verdictSubtitle,
} from "../ci-utils";

type DetailState = {
  run: ReplayRunDetailItem | null;
  detail: RegressionCIRunDetailResponse | null;
};

const ACTIVE_STATUSES = new Set(["running", "pending", "queued"]);

function StatusBadge({ status }: { status: string }) {
  return <span className={`alert-cat-badge ${statusBadgeClass(status)}`}>{statusLabel(status)}</span>;
}

function MetadataCard({ label, value, helper }: { label: string; value: string; helper?: string }) {
  return (
    <article className="ci-meta-card">
      <span>{label}</span>
      <strong>{value}</strong>
      {helper ? <p>{helper}</p> : null}
    </article>
  );
}

function FlowList({ flows }: { flows: string[] }) {
  if (flows.length === 0) {
    return (
      <div className="ci-compact-empty">
        <span>No failed protected flows reported.</span>
      </div>
    );
  }
  return (
    <div className="ci-flow-list">
      {flows.map((flow) => (
        <div key={flow}>
          <strong>{flow.split(":")[0]}</strong>
          <span>{flow.includes(":") ? flow.slice(flow.indexOf(":") + 1).trim() : "Regression evidence captured for this protected flow."}</span>
        </div>
      ))}
    </div>
  );
}

function reportRecord(detail: RegressionCIRunDetailResponse | null | undefined, key: string): Record<string, unknown> | null {
  const value = detail?.report?.[key];
  return isRecord(value) ? value : null;
}

function formatMoney(value: number | null): string {
  if (value == null) return "-";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: value >= 100 ? 0 : 2 }).format(value);
}

function blastRadiusLabel(detail: RegressionCIRunDetailResponse | null): string {
  const blast = reportRecord(detail, "blast_radius");
  const category = stringField(blast, "category") ?? "Not captured";
  const source = stringField(blast, "source");
  const target = stringField(blast, "target");
  return [category.replaceAll("_", " "), target, source ? `via ${source}` : null].filter(Boolean).join(" - ");
}

function samplePlanLabel(detail: RegressionCIRunDetailResponse | null): string {
  const sample = reportRecord(detail, "sample_spec");
  const target = numericField(sample, "target_total");
  const traceCount = numericField(detail?.report, "trace_count");
  if (target != null && traceCount != null) return `${traceCount} / ${target} traces`;
  if (traceCount != null) return `${traceCount} traces`;
  return "-";
}

function outcomeRisk(detail: RegressionCIRunDetailResponse | null): number | null {
  return numericField(reportRecord(detail, "outcome_attribution"), "estimated_monthly_risk_usd");
}

export default function CiGateDetailPage() {
  const params = useParams<{ runId: string }>();
  const router = useRouter();
  const runId = params.runId;
  const [state, setState] = useState<DetailState>({ run: null, detail: null });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [rerunning, setRerunning] = useState(false);
  const [copying, setCopying] = useState(false);

  const loadGate = useCallback(async (signal?: AbortSignal, mode: "initial" | "refresh" = "refresh") => {
    if (!runId) return;
    if (mode === "initial") setLoading(true);
    else setRefreshing(true);
      setError(null);
      try {
        const [run, detailResult] = await Promise.all([
          getReplayRun(runId, signal),
          getRegressionCIRun(runId, signal).catch(() => null),
        ]);
        if (signal?.aborted) return;
        setState({ run, detail: detailResult });
        setLastUpdated(new Date().toISOString());
      } catch (loadError) {
        if ((loadError as { name?: string }).name === "AbortError") return;
        setError(loadError instanceof Error ? loadError.message : "Failed to load CI gate run.");
      } finally {
        if (!signal?.aborted) {
          if (mode === "initial") setLoading(false);
          else setRefreshing(false);
        }
      }
  }, [runId]);

  useEffect(() => {
    const ctrl = new AbortController();
    void loadGate(ctrl.signal, "initial");
    return () => ctrl.abort();
  }, [loadGate]);

  const run = state.run;
  const detail = state.detail;
  const status = run ? normalizeStatus(run, detail) : "pending";
  const flows = useMemo(() => (run ? failedProtectedFlows(run, detail) : []), [detail, run]);
  const setId = run ? goldenSetId(run, detail) : null;
  const externalPrUrl = prUrl(detail);
  const failedCount = run ? failedFlowCount(run, detail) : null;
  const isActive = ACTIVE_STATUSES.has(status);

  useEffect(() => {
    if (!autoRefresh || !isActive) return;
    const timer = window.setInterval(() => {
      void loadGate(undefined, "refresh");
    }, 8_000);
    return () => window.clearInterval(timer);
  }, [autoRefresh, isActive, loadGate]);

  async function onRerunGate() {
    if (!run?.git_sha) {
      setActionError("This CI gate has no commit SHA to rerun.");
      return;
    }
    setActionError(null);
    setActionMessage(null);
    setRerunning(true);
    try {
      const threshold = thresholdRate(detail) ?? undefined;
      const created = await runRegressionCI({ git_sha: run.git_sha, threshold });
      setActionMessage(`Rerun queued: ${created.run_id}`);
      router.push(`/ci-gates/${created.run_id}`);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Failed to rerun CI gate.");
    } finally {
      setRerunning(false);
    }
  }

  async function onCopyComment() {
    if (!run) return;
    setActionError(null);
    setActionMessage(null);
    setCopying(true);
    try {
      await navigator.clipboard.writeText(prCommentPreview(run, detail));
      setActionMessage("PR comment copied.");
    } catch {
      setActionError("Unable to copy PR comment in this browser.");
    } finally {
      setCopying(false);
    }
  }

  if (loading) {
    return (
      <div className="ci-gates-mvp">
        <section className="ci-empty">
          <Loader2 aria-hidden="true" />
          <strong>Loading CI gate run...</strong>
        </section>
      </div>
    );
  }

  if (!run || error) {
    return (
      <div className="ci-gates-mvp">
        <section className="ci-empty">
          <AlertTriangle aria-hidden="true" />
          <strong>CI gate run unavailable</strong>
          <p>{error ?? "The selected CI gate run could not be loaded."}</p>
          <Link href="/ci-gates" className="btn btn-soft">
            <ArrowLeft aria-hidden="true" />
            Back to CI Gates
          </Link>
        </section>
      </div>
    );
  }

  return (
    <div className="ci-gates-mvp ci-detail-mvp">
      <Link href="/ci-gates" className="detail-back-link">
        <ArrowLeft aria-hidden="true" />
        Back to CI Gates
      </Link>

      <section className="ci-hero ci-detail-hero">
        <div>
          <div className="ci-eyebrow">
            <GitPullRequest aria-hidden="true" />
            Regression CI verdict
          </div>
          <h1>{runTitle(run, detail)}</h1>
          <p>{verdictSubtitle(status)}</p>
          <div className="ci-badge-row">
            <StatusBadge status={status} />
            <span className={`alert-cat-badge ${replayProofBadgeClass(run, detail)}`}>{replayProofLabel(run, detail)}</span>
            <span className="alert-cat-badge badge-gray">{runMeta(run, detail)}</span>
          </div>
        </div>
        <div className="ci-hero-actions">
          <button type="button" className="btn btn-soft" onClick={() => void loadGate(undefined, "refresh")} disabled={refreshing}>
            <RefreshCw aria-hidden="true" className={refreshing ? "ci-spin" : undefined} />
            {refreshing ? "Refreshing" : "Refresh"}
          </button>
          <button type="button" className="btn btn-primary" onClick={() => void onRerunGate()} disabled={rerunning || !run.git_sha}>
            <Play aria-hidden="true" />
            {rerunning ? "Queueing..." : "Rerun gate"}
          </button>
          <label className="ci-toggle ci-toggle-compact">
            <input type="checkbox" checked={autoRefresh} onChange={(event) => setAutoRefresh(event.target.checked)} />
            <span>Auto-refresh</span>
          </label>
        </div>
      </section>

      {actionError ? <div className="ci-context-warning ci-context-error" role="alert"><AlertTriangle aria-hidden="true" /> <span>{actionError}</span></div> : null}
      {actionMessage ? <div className="ci-context-warning" role="status"><CheckCircle2 aria-hidden="true" /> <span>{actionMessage}</span></div> : null}

      <section className="ci-meta-grid" aria-label="CI gate run metadata">
        <MetadataCard label="Regression rate" value={status === "not_verified" ? "-" : formatRate(regressionRate(run, detail))} />
        <MetadataCard label="Failed flows" value={status === "not_verified" ? "-" : failedCount == null ? "-" : String(failedCount)} />
        <MetadataCard label="Threshold" value={formatRate(thresholdRate(detail))} />
        <MetadataCard label="Git SHA" value={shortSha(run.git_sha)} />
        <MetadataCard label="Summary URL" value={summaryUrl(run, detail)} helper="Backend detail endpoint for this gate." />
        <MetadataCard label="Completed at" value={formatDateTime(run.completed_at ?? run.started_at ?? run.created_at)} />
      </section>

      <div className="ci-detail-layout">
        <main className="ci-detail-main">
          <section className="ci-card">
            <header className="ci-section-header">
              <div>
                <h2>Verdict summary</h2>
                <p>{statusLabel(status)}</p>
              </div>
              <StatusBadge status={status} />
            </header>
            {status === "not_verified" ? (
              <div className="ci-warning-card">
                <ShieldAlert aria-hidden="true" />
                <div>
                  <strong>This CI run did not execute trusted replay. Do not treat this PR as safe.</strong>
                  <p>{verdictSubtitle(status)}</p>
                </div>
              </div>
            ) : (
              <p className="ci-body-copy">{verdictSubtitle(status)}</p>
            )}
          </section>

          <section className="ci-card">
            <header className="ci-section-header">
              <div>
                <h2>Failed protected flows</h2>
                <p>Protected Golden flows that regressed or need review.</p>
              </div>
            </header>
            <FlowList flows={flows} />
          </section>

          <section className="ci-card">
            <header className="ci-section-header">
              <div>
                <h2>Replay evidence</h2>
                <p>Replay proof used for this CI verdict.</p>
              </div>
              <span className={`alert-cat-badge ${replayProofBadgeClass(run, detail)}`}>{replayProofLabel(run, detail)}</span>
            </header>
            <div className="ci-evidence-grid">
              <div><span>Status</span><strong>{statusLabel(status)}</strong></div>
              <div><span>Replay mode</span><strong>{replayProofLabel(run, detail)}</strong></div>
              <div><span>Executed traces</span><strong>{run.summary.trace_count_executed || "-"}</strong></div>
              <div><span>Git SHA</span><strong>{shortSha(run.git_sha)}</strong></div>
              <div><span>Summary URL</span><strong>{summaryUrl(run, detail)}</strong></div>
              <div><span>Last refreshed</span><strong>{lastUpdated ? formatDateTime(lastUpdated) : "-"}</strong></div>
            </div>
          </section>

          <section className="ci-card">
            <header className="ci-section-header">
              <div>
                <h2>Gate proof</h2>
                <p>Why this verdict should or should not block a release.</p>
              </div>
            </header>
            <div className="ci-evidence-grid">
              <div><span>Blast radius</span><strong>{blastRadiusLabel(detail)}</strong></div>
              <div><span>Sample plan</span><strong>{samplePlanLabel(detail)}</strong></div>
              <div><span>Judge checks</span><strong>{numericField(detail?.report, "judge_used_count") ?? "-"}</strong></div>
              <div><span>Replay cost</span><strong>{formatMoney(numericField(detail?.report, "cost_usd"))}</strong></div>
              <div><span>Duration</span><strong>{numericField(detail?.report, "duration_seconds") != null ? `${numericField(detail?.report, "duration_seconds")}s` : "-"}</strong></div>
              <div><span>Estimated risk</span><strong>{formatMoney(outcomeRisk(detail))}</strong></div>
            </div>
          </section>

          <section className="ci-card">
            <header className="ci-section-header">
              <div>
                <h2>PR comment preview</h2>
                <p>Reviewer-facing CI summary.</p>
              </div>
              <button type="button" className="btn btn-soft btn-sm" onClick={() => void onCopyComment()} disabled={copying}>
                <Copy aria-hidden="true" />
                {copying ? "Copying" : "Copy comment"}
              </button>
            </header>
            <pre className="struct-pre ci-comment-preview">{prCommentPreview(run, detail)}</pre>
          </section>

          <section className="ci-card">
            <header className="ci-section-header">
              <div>
                <h2>Run notes</h2>
                <p>Additional context captured by the CI report.</p>
              </div>
            </header>
            <p className="ci-body-copy">{runNotes(detail)}</p>
          </section>
        </main>

        <aside className="ci-action-panel">
          <section className="ci-card">
            <header className="ci-section-header">
              <div>
                <h2>Recommended action</h2>
                <p>{actionLabel(status)}</p>
              </div>
            </header>
            <p className="ci-body-copy">
              {status === "fail"
                ? "Review failed flows before merging this PR."
                : status === "not_verified"
                  ? "Run with trusted replay before treating this PR as safe."
                  : status === "pass"
                    ? "No blocking action is required from this CI verdict."
                    : "Inspect this run before making a release decision."}
            </p>
            <div className="ci-panel-actions">
              <Link href={`/replay/${run.id}`} className="btn btn-primary">
                <RotateCcw aria-hidden="true" />
                View replay
              </Link>
              {setId ? <Link href={`/goldens/${setId}`} className="btn btn-soft">View Golden set</Link> : null}
              {externalPrUrl ? (
                <a href={externalPrUrl} className="btn btn-soft" target="_blank" rel="noreferrer">
                  <ExternalLink aria-hidden="true" />
                  Open PR
                </a>
              ) : null}
            </div>
          </section>

          <section className="ci-card">
            <header className="ci-section-header">
              <div>
                <h2>Replay proof status</h2>
                <p>{replayProofLabel(run, detail)}</p>
              </div>
            </header>
            <span className={`alert-cat-badge ${replayProofBadgeClass(run, detail)}`}>{replayProofLabel(run, detail)}</span>
          </section>
        </aside>
      </div>
    </div>
  );
}
