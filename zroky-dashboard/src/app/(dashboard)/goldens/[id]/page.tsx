"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Edit3,
  Eye,
  Loader2,
  Plus,
  Save,
  ShieldCheck,
  Trash2,
} from "lucide-react";

import { hasCiBlockingAccess, hasGoldensAccess } from "@/components/feature-gate";
import {
  addGoldenTrace,
  deleteGoldenSet,
  deleteGoldenTrace,
  getBillingMe,
  getGoldenSet,
  getReplayRun,
  listGoldenHistory,
  listGoldenTraces,
  listReplayRuns,
  runGoldenSet,
  updateGoldenSet,
  type GoldenTraceView,
  type GoldenHistoryItem,
  type ReplayRunTraceItem,
} from "@/lib/api";
import { formatDateTime, formatUsd } from "@/lib/format";
import {
  canBlockCi,
  ciBadgeClass,
  ciBlockingLabel,
  expectedBehaviorSummary,
  healthBadgeClass,
  healthForSet,
  lastRunLabel,
  parseJsonObject,
  passRateForRuns,
  replayTraceSummary,
  sourceEvidenceSummary,
  statusBadgeClass,
  statusLabel,
} from "../golden-utils";

function JsonDisclosure({ label, raw }: { label: string; raw: string | null | undefined }) {
  const parsed = parseJsonObject(raw);
  if (Object.keys(parsed).length === 0) return null;
  return (
    <details className="gd-json-disclosure">
      <summary>{label}</summary>
      <pre className="struct-pre">{JSON.stringify(parsed, null, 2)}</pre>
    </details>
  );
}

function MetadataCard({ label, value, helper }: { label: string; value: string | number; helper?: string }) {
  return (
    <article className="gd-meta-card">
      <span>{label}</span>
      <strong>{value}</strong>
      {helper ? <p>{helper}</p> : null}
    </article>
  );
}

function validateJsonText(raw: string, label: string): string | undefined {
  const trimmed = raw.trim();
  if (!trimmed) return undefined;
  try {
    JSON.parse(trimmed);
  } catch {
    throw new Error(`${label} must be valid JSON.`);
  }
  return trimmed;
}

function TraceResultFor({
  trace,
  latestReplayTrace,
}: {
  trace: GoldenTraceView;
  latestReplayTrace: ReplayRunTraceItem | null;
}) {
  const result = replayTraceSummary(latestReplayTrace);
  return (
    <div className="gd-result-card">
      <span className={`alert-cat-badge ${statusBadgeClass(latestReplayTrace?.status)}`}>{result.status}</span>
      <p>{result.output}</p>
      <p>{result.tool}</p>
      <div>
        <span>Cost delta {result.cost}</span>
        <span>Latency {result.latency}</span>
      </div>
      {trace.call_id ? (
        <Link href={`/calls/${trace.call_id}`} className="btn btn-soft btn-sm">
          <Eye aria-hidden="true" />
          View call
        </Link>
      ) : null}
    </div>
  );
}

function ContractPreview({ trace }: { trace: GoldenTraceView | null }) {
  const criteria = parseJsonObject(trace?.criteria_json);
  const contract = criteria.golden_contract_v1 && typeof criteria.golden_contract_v1 === "object" && !Array.isArray(criteria.golden_contract_v1)
    ? criteria.golden_contract_v1 as Record<string, unknown>
    : null;
  if (!contract) {
    return <p className="notif-meta">No structured Golden contract captured yet. Use criteria JSON to add golden_contract_v1.</p>;
  }
  const linkedProof = contract.linked_proof && typeof contract.linked_proof === "object" && !Array.isArray(contract.linked_proof)
    ? contract.linked_proof as Record<string, unknown>
    : null;
  const budgets = contract.budgets && typeof contract.budgets === "object" && !Array.isArray(contract.budgets)
    ? contract.budgets as Record<string, unknown>
    : null;
  return (
    <div className="gd-behavior-grid">
      <div><span>Final output</span><p>{JSON.stringify(contract.final_output ?? "not asserted")}</p></div>
      <div><span>Tool sequence</span><p>{JSON.stringify(contract.tool_sequence ?? "not asserted")}</p></div>
      <div><span>Policy checks</span><p>{JSON.stringify(contract.policy_checks ?? "not asserted")}</p></div>
      <div><span>RAG grounding</span><p>{JSON.stringify(contract.rag_grounding ?? "not asserted")}</p></div>
      <div><span>Budgets</span><p>{budgets ? JSON.stringify(budgets) : "not set"}</p></div>
      <div><span>Linked proof</span><p>{linkedProof ? JSON.stringify(linkedProof) : "not linked"}</p></div>
    </div>
  );
}

function HistoryList({ items }: { items: GoldenHistoryItem[] }) {
  if (items.length === 0) return <p className="notif-meta">No Golden history captured yet.</p>;
  return (
    <div className="gd-run-list">
      {items.slice(0, 8).map((item) => (
        <div key={item.id}>
          <span className="alert-cat-badge badge-gray">{item.action}</span>
          <strong>{item.reason ?? item.golden_trace_id ?? item.golden_set_id ?? "Golden change"}</strong>
          <span>{formatDateTime(item.created_at)}</span>
        </div>
      ))}
    </div>
  );
}

export default function GoldenDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [selectedTraceId, setSelectedTraceId] = useState("");
  const [editOpen, setEditOpen] = useState(false);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editJudgeConfig, setEditJudgeConfig] = useState("");
  const [deleteSetConfirm, setDeleteSetConfirm] = useState(false);
  const [addTraceOpen, setAddTraceOpen] = useState(false);
  const [newTraceCallId, setNewTraceCallId] = useState("");
  const [newTraceStatus, setNewTraceStatus] = useState<"draft" | "active">("draft");
  const [newTraceExpected, setNewTraceExpected] = useState("");
  const [newTraceSource, setNewTraceSource] = useState("");
  const [newTraceCriteria, setNewTraceCriteria] = useState("");
  const billingQuery = useQuery({
    queryKey: ["billing-me"],
    queryFn: ({ signal }) => getBillingMe(signal),
  });
  const setQuery = useQuery({
    queryKey: ["golden-set", id],
    queryFn: ({ signal }) => getGoldenSet(id, signal),
  });
  const tracesQuery = useQuery({
    queryKey: ["golden-traces", id],
    queryFn: ({ signal }) => listGoldenTraces(id, { limit: 100 }, signal),
  });
  const runsQuery = useQuery({
    queryKey: ["replay-runs", { golden_set_id: id, limit: 20 }],
    queryFn: ({ signal }) => listReplayRuns({ golden_set_id: id, limit: 20 }, signal),
  });
  const historyQuery = useQuery({
    queryKey: ["golden-history", id],
    queryFn: ({ signal }) => listGoldenHistory(id, signal),
  });

  const set = setQuery.data ?? null;
  const traces = useMemo(() => tracesQuery.data?.items ?? [], [tracesQuery.data?.items]);
  const runs = useMemo(() => runsQuery.data?.items ?? [], [runsQuery.data?.items]);
  const latestRun = runs[0] ?? null;
  const latestRunDetailQuery = useQuery({
    queryKey: ["replay-run", latestRun?.id],
    queryFn: ({ signal }) => getReplayRun(latestRun!.id, signal),
    enabled: Boolean(latestRun?.id),
  });
  const latestRunDetail = latestRunDetailQuery.data ?? null;
  const planTemplate = billingQuery.data?.plan_template;
  const planCode = billingQuery.data?.plan_code;
  const canUseGoldens = hasGoldensAccess(planTemplate, planCode);
  const canToggleCi = hasCiBlockingAccess(planTemplate, planCode);
  const selectedTrace = traces.find((trace) => trace.id === selectedTraceId) ?? traces[0] ?? null;
  const latestReplayTraceByGoldenId = useMemo(() => {
    const map = new Map<string, ReplayRunTraceItem>();
    for (const trace of latestRunDetail?.traces ?? []) {
      if (trace.golden_trace_id) map.set(trace.golden_trace_id, trace);
    }
    return map;
  }, [latestRunDetail?.traces]);

  useEffect(() => {
    if (!set) return;
    setEditName(set.name);
    setEditDescription(set.description ?? "");
    setEditJudgeConfig(set.judge_config_json ?? "");
  }, [set?.id, set?.name, set?.description, set?.judge_config_json, set]);

  useEffect(() => {
    if (!selectedTraceId && traces[0]) {
      setSelectedTraceId(traces[0].id);
      return;
    }
    if (selectedTraceId && !traces.some((trace) => trace.id === selectedTraceId)) {
      setSelectedTraceId(traces[0]?.id ?? "");
    }
  }, [selectedTraceId, traces]);

  const runMutation = useMutation({
    mutationFn: () => runGoldenSet(id, { trigger: "manual" }),
    onSuccess: (created) => {
      void queryClient.invalidateQueries({ queryKey: ["replay-runs"] });
      void queryClient.invalidateQueries({ queryKey: ["replay-run"] });
      router.push(`/replay/${created.id}`);
    },
  });
  const ciMutation = useMutation({
    mutationFn: (blocks_ci: boolean) => updateGoldenSet(id, { blocks_ci }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["golden-set", id] });
      void queryClient.invalidateQueries({ queryKey: ["golden-sets"] });
      void queryClient.invalidateQueries({ queryKey: ["golden-history", id] });
    },
  });
  const editMutation = useMutation({
    mutationFn: () => updateGoldenSet(id, {
      name: editName.trim(),
      ...(editDescription.trim() ? { description: editDescription.trim() } : { clear_description: true }),
      ...(editJudgeConfig.trim() ? { judge_config_json: validateJsonText(editJudgeConfig, "Judge config") } : { clear_judge_config: true }),
    }),
    onSuccess: () => {
      setEditOpen(false);
      void queryClient.invalidateQueries({ queryKey: ["golden-set", id] });
      void queryClient.invalidateQueries({ queryKey: ["golden-sets"] });
    },
  });
  const addTraceMutation = useMutation({
    mutationFn: () => addGoldenTrace(id, {
      ...(newTraceCallId.trim() ? { call_id: newTraceCallId.trim() } : {}),
      status: newTraceStatus,
      ...(newTraceExpected.trim() ? { expected_output_text: newTraceExpected.trim() } : {}),
      ...(newTraceSource.trim() ? { source_output_text: newTraceSource.trim() } : {}),
      ...(newTraceCriteria.trim() ? { criteria_json: validateJsonText(newTraceCriteria, "Criteria JSON") } : {}),
      weight: 1,
    }),
    onSuccess: (trace) => {
      setAddTraceOpen(false);
      setNewTraceCallId("");
      setNewTraceStatus("draft");
      setNewTraceExpected("");
      setNewTraceSource("");
      setNewTraceCriteria("");
      setSelectedTraceId(trace.id);
      void queryClient.invalidateQueries({ queryKey: ["golden-traces", id] });
      void queryClient.invalidateQueries({ queryKey: ["golden-set", id] });
      void queryClient.invalidateQueries({ queryKey: ["golden-sets"] });
      void queryClient.invalidateQueries({ queryKey: ["golden-history", id] });
    },
  });
  const deleteTraceMutation = useMutation({
    mutationFn: (traceId: string) => deleteGoldenTrace(id, traceId),
    onSuccess: (_data, traceId) => {
      if (selectedTraceId === traceId) setSelectedTraceId("");
      void queryClient.invalidateQueries({ queryKey: ["golden-traces", id] });
      void queryClient.invalidateQueries({ queryKey: ["golden-set", id] });
      void queryClient.invalidateQueries({ queryKey: ["golden-sets"] });
      void queryClient.invalidateQueries({ queryKey: ["golden-history", id] });
    },
  });
  const deleteSetMutation = useMutation({
    mutationFn: () => deleteGoldenSet(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["golden-sets"] });
      router.replace("/goldens");
    },
  });

  if (setQuery.isLoading) {
    return (
      <section className="panel">
        <div className="loading" />
      </section>
    );
  }

  if (!set || setQuery.error) {
    return (
      <section className="panel">
        <p className="notif-error">{setQuery.error?.message ?? "Golden set unavailable."}</p>
        <Link href="/goldens" className="btn btn-soft">
          <ArrowLeft aria-hidden="true" />
          Back to Goldens
        </Link>
      </section>
    );
  }

  const health = healthForSet(set, runs);
  const ciLabel = ciBlockingLabel(set, runs);
  const blocksCiEligible = canBlockCi(set);
  const needsReviewCount = health === "Healthy" ? 0 : 1;
  const passRate = passRateForRuns(runs);
  const selectedReplayTrace = selectedTrace ? latestReplayTraceByGoldenId.get(selectedTrace.id) ?? null : null;
  const selectedReplaySummary = replayTraceSummary(selectedReplayTrace);
  const canEnableBlocking = canUseGoldens && canToggleCi && health === "Healthy" && set.trace_count > 0 && !set.blocks_ci;
  const canDisableBlocking = canUseGoldens && canToggleCi && set.blocks_ci;
  const canChangeBlocking = set.blocks_ci ? canDisableBlocking : canEnableBlocking;

  return (
    <div className="goldens-mvp golden-detail-mvp">
      <Link href="/goldens" className="detail-back-link">
        <ArrowLeft aria-hidden="true" />
        Back to Goldens
      </Link>

      <section className="gm-hero gd-hero">
        <div>
          <div className="gm-eyebrow">
            <ShieldCheck aria-hidden="true" />
            Protected flow
          </div>
          <h1>{set.name}</h1>
          <p>{set.description ?? `${set.trace_count} verified traces protecting production behavior.`}</p>
          <div className="detail-badge-row">
            <span className={`alert-cat-badge ${healthBadgeClass(health)}`}>{health === "Healthy" ? "Active" : health}</span>
            <span className={`alert-cat-badge ${ciBadgeClass(ciLabel)}`}>{ciLabel}</span>
            <span className={`alert-cat-badge ${statusBadgeClass(latestRun?.status)}`}>{statusLabel(latestRun?.status)}</span>
          </div>
        </div>
        <aside className="gd-hero-side">
          <strong>{set.trace_count}</strong>
          <span>protected traces</span>
        </aside>
      </section>

      <section className="gm-kpi-grid" aria-label="Golden set metadata">
        <MetadataCard label="Trace count" value={set.trace_count} helper="Protected traces" />
        <MetadataCard label="Last pass rate" value={passRate} helper="Recent runs" />
        <MetadataCard label="Blocks CI" value={blocksCiEligible ? "Yes" : "No"} helper={ciLabel} />
        <MetadataCard label="Needs review" value={needsReviewCount} helper={health} />
      </section>

      <section className="gd-proof-ladder" aria-label="Golden proof ladder">
        <div className={selectedTrace?.call_id ? "is-ready" : ""}>
          <span>Source</span>
          <strong>{selectedTrace?.call_id ? "Call linked" : "Manual trace"}</strong>
        </div>
        <div className={selectedTrace?.status === "active" ? "is-ready" : "is-warn"}>
          <span>Expected behavior</span>
          <strong>{selectedTrace?.status === "active" ? "Active" : "Draft"}</strong>
        </div>
        <div className={selectedReplayTrace?.status === "pass" ? "is-ready" : "is-warn"}>
          <span>Latest replay</span>
          <strong>{selectedReplaySummary.status}</strong>
        </div>
        <div className={canBlockCi(set) ? "is-ready" : "is-warn"}>
          <span>CI gate</span>
          <strong>{ciLabel}</strong>
        </div>
      </section>

      <div className="gd-layout">
        <div className="gd-main">
          <section className="gm-table-section">
            <header className="gm-section-header">
              <div>
                <h2>Protected traces</h2>
                <p>Expected behavior and latest replay proof for this Golden set.</p>
              </div>
              <button type="button" className="btn btn-soft btn-sm" onClick={() => setAddTraceOpen((value) => !value)}>
                <Plus aria-hidden="true" />
                Add trace
              </button>
            </header>
            {addTraceOpen ? (
              <div className="gd-inline-form" aria-label="Add Golden trace">
                <label>
                  <span>Call ID</span>
                  <input
                    aria-label="Trace call ID"
                    className="input"
                    value={newTraceCallId}
                    onChange={(event) => setNewTraceCallId(event.target.value)}
                    placeholder="optional source call"
                  />
                </label>
                <label>
                  <span>Status</span>
                  <select
                    aria-label="Trace status"
                    className="input"
                    value={newTraceStatus}
                    onChange={(event) => setNewTraceStatus(event.target.value as "draft" | "active")}
                  >
                    <option value="draft">Draft</option>
                    <option value="active">Active</option>
                  </select>
                </label>
                <label>
                  <span>Expected behavior</span>
                  <textarea
                    aria-label="Trace expected behavior"
                    className="input"
                    value={newTraceExpected}
                    onChange={(event) => setNewTraceExpected(event.target.value)}
                    placeholder="Expected output or behavior"
                  />
                </label>
                <label>
                  <span>Source evidence</span>
                  <textarea
                    aria-label="Trace source evidence"
                    className="input"
                    value={newTraceSource}
                    onChange={(event) => setNewTraceSource(event.target.value)}
                    placeholder="Why this trace is trusted"
                  />
                </label>
                <label className="gd-form-wide">
                  <span>Criteria JSON</span>
                  <textarea
                    aria-label="Trace criteria JSON"
                    className="input"
                    value={newTraceCriteria}
                    onChange={(event) => setNewTraceCriteria(event.target.value)}
                    placeholder='{"required_tool_behavior":"..."}'
                  />
                </label>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={!canUseGoldens}
                  onClick={() => addTraceMutation.mutate()}
                >
                  {addTraceMutation.isPending ? <Loader2 aria-hidden="true" /> : <Plus aria-hidden="true" />}
                  Add trace
                </button>
                {addTraceMutation.error ? <p className="notif-error">{addTraceMutation.error.message}</p> : null}
              </div>
            ) : null}
            {tracesQuery.isLoading ? (
              <div className="gm-empty">
                <Loader2 aria-hidden="true" />
                <strong>Loading traces...</strong>
              </div>
            ) : traces.length === 0 ? (
              <div className="gm-empty">
                <BookOpenIcon />
                <strong>This set has no protected traces yet.</strong>
                <p>Create a Golden from a verified replay.</p>
              </div>
            ) : (
              <div className="gm-table-wrap">
                <table className="gm-table gd-trace-table">
                  <thead>
                    <tr>
                      <th>Trace</th>
                      <th>Expected behavior</th>
                      <th>Last result</th>
                      <th>Cost bound</th>
                      <th>Latency bound</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {traces.map((trace) => {
                      const replayTrace = latestReplayTraceByGoldenId.get(trace.id) ?? null;
                      return (
                        <tr key={trace.id} className={selectedTrace?.id === trace.id ? "is-selected" : ""}>
                          <td>
                            <div className="gm-set-cell">
                              <strong>{trace.call_id ?? trace.id}</strong>
                              <span>{trace.status}</span>
                            </div>
                          </td>
                          <td>{expectedBehaviorSummary(trace)}</td>
                          <td>{statusLabel(replayTrace?.status)}</td>
                          <td>{trace.expected_cost_usd == null ? "Not set" : formatUsd(trace.expected_cost_usd)}</td>
                          <td>{trace.expected_latency_ms == null ? "Not set" : `${trace.expected_latency_ms} ms`}</td>
                          <td>
                            <div className="gm-row-actions">
                              <button type="button" className="btn btn-soft btn-sm" onClick={() => setSelectedTraceId(trace.id)}>
                                Select
                              </button>
                              {trace.call_id ? (
                                <Link href={`/calls/${trace.call_id}`} className="btn btn-soft btn-sm">View call</Link>
                              ) : null}
                              <button
                                type="button"
                                className="btn btn-soft btn-sm"
                                disabled={!canUseGoldens || deleteTraceMutation.isPending}
                                onClick={() => deleteTraceMutation.mutate(trace.id)}
                              >
                                <Trash2 aria-hidden="true" />
                                Remove
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="gd-card">
            <header className="gm-section-header">
              <div>
                <h2>Expected behavior</h2>
                <p>Human-readable criteria for the selected protected trace.</p>
              </div>
            </header>
            <div className="gd-behavior-grid">
              <div>
                <span>Expected</span>
                <p>{expectedBehaviorSummary(selectedTrace)}</p>
              </div>
              <div>
                <span>Source evidence</span>
                <p>{sourceEvidenceSummary(selectedTrace)}</p>
              </div>
            </div>
            <JsonDisclosure label="View criteria JSON" raw={selectedTrace?.criteria_json} />
            <JsonDisclosure label="View source evidence JSON" raw={selectedTrace?.source_evidence_json} />
          </section>

          <section className="gd-card">
            <header className="gm-section-header">
              <div>
                <h2>Golden contract</h2>
                <p>Structured assertions used by replay and CI gates.</p>
              </div>
            </header>
            <ContractPreview trace={selectedTrace} />
          </section>

          <section className="gd-card">
            <header className="gm-section-header">
              <div>
                <h2>Last replay result</h2>
                <p>{lastRunLabel(latestRun)}</p>
              </div>
              <span className={`alert-cat-badge ${statusBadgeClass(selectedReplayTrace?.status ?? latestRun?.status)}`}>
                {selectedReplaySummary.status}
              </span>
            </header>
            {selectedTrace ? (
              <TraceResultFor trace={selectedTrace} latestReplayTrace={selectedReplayTrace} />
            ) : (
              <p className="notif-meta">No protected trace has replay proof yet.</p>
            )}
          </section>

          <section className="gd-card">
            <header className="gm-section-header">
              <div>
                <h2>Run history</h2>
                <p>Recent Golden set replay runs.</p>
              </div>
            </header>
            {runs.length === 0 ? (
              <p className="notif-meta">No Golden set runs yet.</p>
            ) : (
              <div className="gd-run-list">
                {runs.map((run) => (
                  <Link key={run.id} href={`/replay/${run.id}`}>
                    <span className={`alert-cat-badge ${statusBadgeClass(run.status)}`}>{statusLabel(run.status)}</span>
                    <strong>{run.summary.verification_status}</strong>
                    <span>{formatDateTime(run.created_at)}</span>
                  </Link>
                ))}
              </div>
            )}
          </section>

          <section className="gd-card">
            <header className="gm-section-header">
              <div>
                <h2>Change history</h2>
                <p>Audit trail for Golden contract and blocking changes.</p>
              </div>
            </header>
            {historyQuery.isLoading ? <p className="notif-meta">Loading history...</p> : <HistoryList items={historyQuery.data?.items ?? []} />}
          </section>
        </div>

        <aside className="gd-side-panel">
          <section className="gd-card">
            <header className="gm-section-header">
              <div>
                <h2>Set controls</h2>
                <p>Edit metadata or remove this Golden set.</p>
              </div>
              <button type="button" className="btn btn-soft btn-sm" onClick={() => setEditOpen((value) => !value)}>
                <Edit3 aria-hidden="true" />
                Edit
              </button>
            </header>
            {editOpen ? (
              <div className="gd-side-stack" aria-label="Edit Golden set">
                <label className="gd-control-field">
                  <span>Name</span>
                  <input className="input" value={editName} onChange={(event) => setEditName(event.target.value)} />
                </label>
                <label className="gd-control-field">
                  <span>Description</span>
                  <textarea className="input" value={editDescription} onChange={(event) => setEditDescription(event.target.value)} />
                </label>
                <label className="gd-control-field">
                  <span>Judge config JSON</span>
                  <textarea className="input" value={editJudgeConfig} onChange={(event) => setEditJudgeConfig(event.target.value)} />
                </label>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={!canUseGoldens || !editName.trim() || editMutation.isPending}
                  onClick={() => editMutation.mutate()}
                >
                  {editMutation.isPending ? <Loader2 aria-hidden="true" /> : <Save aria-hidden="true" />}
                  Save set
                </button>
                {editMutation.error ? <p className="notif-error">{editMutation.error.message}</p> : null}
              </div>
            ) : null}
            <div className="gd-danger-zone">
              <button type="button" className="btn btn-soft" onClick={() => setDeleteSetConfirm((value) => !value)}>
                <Trash2 aria-hidden="true" />
                Delete set
              </button>
              {deleteSetConfirm ? (
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={!canUseGoldens || deleteSetMutation.isPending}
                  onClick={() => deleteSetMutation.mutate()}
                >
                  {deleteSetMutation.isPending ? "Deleting..." : "Confirm delete"}
                </button>
              ) : null}
              {deleteSetMutation.error ? <p className="notif-error">{deleteSetMutation.error.message}</p> : null}
            </div>
          </section>

          <section className="gd-card">
            <header className="gm-section-header">
              <div>
                <h2>Golden health</h2>
                <p>Current protection state for this flow.</p>
              </div>
            </header>
            <div className="gd-side-stack">
              <div>
                <span>Status</span>
                <strong>{health}</strong>
              </div>
              <div>
                <span>CI blocking</span>
                <strong>{ciLabel}</strong>
              </div>
              {health !== "Healthy" ? (
                <div className="gd-warning">
                  <AlertTriangle aria-hidden="true" />
                  <span>Draft, flaky, drift-suspected, or empty Goldens should be reviewed before blocking CI.</span>
                </div>
              ) : null}
              <button
                type="button"
                className="btn btn-primary"
                disabled={!canUseGoldens || set.trace_count === 0 || runMutation.isPending}
                onClick={() => runMutation.mutate()}
              >
                {runMutation.isPending ? <Loader2 aria-hidden="true" /> : <ShieldCheck aria-hidden="true" />}
                {runMutation.isPending ? "Running..." : "Run Golden set"}
              </button>
              <button
                type="button"
                className="btn btn-soft"
                disabled={!canChangeBlocking || ciMutation.isPending}
                onClick={() => ciMutation.mutate(!set.blocks_ci)}
              >
                {set.blocks_ci ? "Disable CI blocking" : "Enable CI blocking"}
              </button>
              {!canChangeBlocking ? (
                <p className="notif-meta">CI blocking requires a healthy active set and CI blocking entitlement.</p>
              ) : null}
              {runMutation.error ? <p className="notif-error">{runMutation.error.message}</p> : null}
              {ciMutation.error ? <p className="notif-error">{ciMutation.error.message}</p> : null}
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}

function BookOpenIcon() {
  return <CheckCircle2 aria-hidden="true" />;
}
