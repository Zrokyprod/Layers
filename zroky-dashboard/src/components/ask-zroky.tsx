"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  CheckCircle2,
  ExternalLink,
  FilePlus2,
  Loader2,
  MessageSquarePlus,
  Send,
  ShieldCheck,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  X,
  type LucideIcon,
} from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
  addGoldenTrace,
  askZroky,
  createGoldenSet,
  getReplayRun,
  listAlerts,
  listCalls,
  listGoldenSets,
  submitAskFeedback,
  type GoldenSetView,
  type ReplayRunDetailItem,
  type ReplayRunTraceItem,
} from "@/lib/api";
import { useCreateReplayRunFromCall, useCreateReplayRunFromIssue } from "@/lib/hooks";
import { DEFAULT_VERIFICATION_REPLAY_MODE, replayVerifiedFix } from "@/lib/replay-mode";
import type { AskContext, AskEvidence, AskFeedbackRequest, AskResponse } from "@/lib/types";

interface ChatTurn {
  id: string;
  role: "user" | "assistant";
  text: string;
  evidence?: AskEvidence[];
  suggested_actions?: string[];
  used_llm?: boolean;
  fallback_reason?: string | null;
  intent?: string;
  confidence?: number;
  context?: AskContext | null;
}

function uid(): string {
  return Math.random().toString(36).slice(2, 11);
}

type AskActionKind = "create_replay" | "open_issue" | "open_call" | "open_trace" | "promote_golden";

interface AskWorkflowAction {
  kind: AskActionKind;
  label: string;
  href?: string;
}

interface AskTurnRefs {
  callId: string | null;
  issueId: string | null;
  traceId: string | null;
  replayId: string | null;
}

const ASK_GOLDEN_SET_NAME = "Ask Zroky verified fixes";

function actionKind(action: string): AskActionKind | null {
  const normalized = action.toLowerCase().replace(/[_-]/g, " ");
  if (normalized.includes("create") && normalized.includes("replay")) return "create_replay";
  if (normalized.includes("open") && normalized.includes("issue")) return "open_issue";
  if (normalized.includes("open") && normalized.includes("call")) return "open_call";
  if (normalized.includes("open") && normalized.includes("trace")) return "open_trace";
  if (normalized.includes("promote") && normalized.includes("golden")) return "promote_golden";
  return null;
}

function evidenceFor(evidence: AskEvidence[], kinds: string[]): AskEvidence | null {
  return evidence.find((ev) => kinds.includes(ev.kind.toLowerCase())) ?? null;
}

function idFromHref(href: string | undefined, prefix: string): string | null {
  if (!href) return null;
  const match = href.match(new RegExp(`${prefix}/([^/?#]+)`));
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

function turnRefs(turn: ChatTurn): AskTurnRefs {
  const evidence = turn.evidence ?? [];
  const context = turn.context ?? null;
  const callEvidence = evidenceFor(evidence, ["call"]);
  const issueEvidence = evidenceFor(evidence, ["issue", "anomaly"]);
  const traceEvidence = evidenceFor(evidence, ["trace"]);
  const replayEvidence = evidenceFor(evidence, ["replay"]);

  return {
    callId: context?.call_id ?? callEvidence?.id ?? idFromHref(callEvidence?.href, "/calls"),
    issueId: context?.issue_id ?? context?.anomaly_id ?? issueEvidence?.id ?? idFromHref(issueEvidence?.href, "/issues"),
    traceId: context?.trace_id ?? traceEvidence?.id ?? idFromHref(traceEvidence?.href, "/trace"),
    replayId: replayEvidence?.id ?? idFromHref(replayEvidence?.href, "/replay"),
  };
}

function buildWorkflowActions(turn: ChatTurn): AskWorkflowAction[] {
  const evidence = turn.evidence ?? [];
  if (evidence.length === 0) return [];
  const { callId, issueId, traceId, replayId } = turnRefs(turn);
  const seen = new Set<AskActionKind>();
  const actions: AskWorkflowAction[] = [];

  for (const suggestedAction of turn.suggested_actions ?? []) {
    const kind = actionKind(suggestedAction);
    if (!kind || seen.has(kind)) continue;
    seen.add(kind);
    if (kind === "create_replay" && (issueId || callId)) actions.push({ kind, label: "Create Replay" });
    if (kind === "open_issue" && issueId) actions.push({ kind, label: "Open Issue", href: `/issues/${encodeURIComponent(issueId)}` });
    if (kind === "open_call" && callId) actions.push({ kind, label: "Open Call", href: `/calls/${encodeURIComponent(callId)}` });
    if (kind === "open_trace" && traceId) actions.push({ kind, label: "Open Trace", href: `/trace/${encodeURIComponent(traceId)}` });
    if (kind === "promote_golden" && replayId) actions.push({ kind, label: "Promote Contract" });
    if (kind === "promote_golden" && !replayId && !seen.has("create_replay") && (issueId || callId)) {
      seen.add("create_replay");
      actions.push({ kind: "create_replay", label: "Create Replay First" });
    }
  }

  return actions;
}

function actionIcon(kind: AskActionKind): LucideIcon {
  if (kind === "create_replay") return FilePlus2;
  if (kind === "promote_golden") return ShieldCheck;
  return ExternalLink;
}

function actionTone(kind: AskActionKind): "primary" | "secondary" {
  return kind === "create_replay" || kind === "promote_golden" ? "primary" : "secondary";
}

function promotionCriteria(run: ReplayRunDetailItem, trace: ReplayRunTraceItem): string {
  return JSON.stringify({
    source: "ask_zroky_verified_promotion",
    source_replay_run_id: run.id,
    source_replay_trace_id: trace.id,
    source_golden_trace_id: trace.golden_trace_id,
    replay_mode: run.replay_mode,
    executor_replay_mode: run.executor_replay_mode,
    replay_status: run.status,
    replay_trace_status: trace.status,
    verification_status: run.summary.verification_status,
    verified_fix: replayVerifiedFix(run.replay_mode, run.summary.verified_fix),
    diff_metric: trace.diff_metric,
    cost_delta_usd: trace.cost_delta_usd,
    latency_delta_ms: trace.latency_delta_ms,
    output_diff: trace.output_diff,
    tool_behavior_diff: trace.tool_behavior_diff,
    promoted_at: new Date().toISOString(),
  });
}

export function AskZroky() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [pending, setPending] = useState(false);
  const [context, setContext] = useState<AskContext | null>(null);
  const [turnFeedback, setTurnFeedback] = useState<Record<string, "up" | "down">>({});
  const [actionStatus, setActionStatus] = useState<Record<string, string>>({});
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const createReplayFromCall = useCreateReplayRunFromCall();
  const createReplayFromIssue = useCreateReplayRunFromIssue();

  // Dynamic suggestion data — only fetched when drawer is open
  const callsQuery = useQuery({
    queryKey: ["calls", "list", { limit: 1 }],
    queryFn: () => listCalls({ limit: 1 }),
    enabled: open,
    staleTime: 120_000,
  });
  const alertsQuery = useQuery({
    queryKey: ["alerts", { status: "OPEN", limit: 5 }],
    queryFn: () => listAlerts({ status: "OPEN", limit: 5 }),
    enabled: open,
    staleTime: 60_000,
  });

  const hasData = !callsQuery.isLoading && (callsQuery.data?.total ?? 0) > 0;
  const openAlertCount = alertsQuery.data?.items?.length ?? 0;

  const suggestions = useMemo(() => {
    const s: string[] = [];
    if (openAlertCount > 0) {
      s.push(
        `You have ${openAlertCount} open alert${openAlertCount !== 1 ? "s" : ""}. What's most urgent?`,
      );
    }
    s.push("Which calls cost the most today?");
    s.push("What should I fix first?");
    s.push("Show me recent agent failures.");
    return s.slice(0, 4);
  }, [openAlertCount]);

  // Listen for global open/close events from topbar button, command palette, and contextual buttons.
  useEffect(() => {
    const onOpen = (event: Event) => {
      setOpen(true);
      const detail = (event as CustomEvent<{ context?: AskContext; prefill?: string }>).detail;
      if (detail?.context) {
        setContext(detail.context);
      }
      if (detail?.prefill) {
        setQuestion(detail.prefill);
      }
    };
    const onClose = () => setOpen(false);
    window.addEventListener("open-ask-zroky", onOpen);
    window.addEventListener("close-ask-zroky", onClose);
    return () => {
      window.removeEventListener("open-ask-zroky", onOpen);
      window.removeEventListener("close-ask-zroky", onClose);
    };
  }, []);

  // Focus input when drawer opens.
  useEffect(() => {
    if (open) {
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  // Auto-scroll the conversation as new turns arrive.
  useEffect(() => {
    const el = listRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [turns, pending]);

  // Close on Escape.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || pending) return;

    const userTurn: ChatTurn = { id: uid(), role: "user", text: trimmed };
    setTurns((prev) => [...prev, userTurn]);
    setQuestion("");
    setPending(true);

    try {
      const payload: { question: string; context?: AskContext } = { question: trimmed };
      if (context) {
        payload.context = context;
      }
      const result: AskResponse = await askZroky(payload);
      const hasEvidence = result.evidence.length > 0;
      const assistantTurn: ChatTurn = {
        id: uid(),
        role: "assistant",
        text: hasEvidence ? result.answer : "Not enough data to answer this yet.",
        evidence: result.evidence,
        suggested_actions: hasEvidence ? result.suggested_actions : [],
        used_llm: result.used_llm,
        fallback_reason: result.fallback_reason,
        intent: result.intent,
        confidence: result.confidence,
        context,
      };
      setTurns((prev) => [...prev, assistantTurn]);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Something went wrong.";
      setTurns((prev) => [
        ...prev,
        {
          id: uid(),
          role: "assistant",
          text: `Sorry — I could not answer that. (${message})`,
          used_llm: false,
        },
      ]);
    } finally {
      setPending(false);
    }
  }

  async function handleFeedback(turnId: string, vote: "up" | "down") {
    setTurnFeedback((prev) => ({ ...prev, [turnId]: vote }));
    const turnIdx = turns.findIndex((t) => t.id === turnId);
    const questionText = turnIdx > 0 ? turns[turnIdx - 1].text : "";
    const turn = turns[turnIdx];
    if (!turn) return;
    const body: AskFeedbackRequest = {
      question: questionText,
      answer: turn.text,
      helpful: vote === "up",
      intent: turn.intent ?? "",
      confidence: turn.confidence ?? 0,
    };
    try {
      await submitAskFeedback(body);
    } catch {
      // non-critical — UI already updated optimistically
    }
  }

  async function runWorkflowAction(turn: ChatTurn, action: AskWorkflowAction) {
    const { callId, issueId, replayId } = turnRefs(turn);
    const key = `${turn.id}-${action.kind}`;
    const verb = action.kind === "promote_golden" ? "Promoting" : "Creating";
    setActionStatus((prev) => ({ ...prev, [key]: `${verb}...` }));

    try {
      if (action.kind === "create_replay") {
        const run = issueId
          ? await createReplayFromIssue.mutateAsync({ issueId, payload: { replay_mode: DEFAULT_VERIFICATION_REPLAY_MODE } })
          : callId
            ? await createReplayFromCall.mutateAsync({ callId, payload: { replay_mode: DEFAULT_VERIFICATION_REPLAY_MODE } })
            : null;
        if (!run) {
          setActionStatus((prev) => ({ ...prev, [key]: "No call or issue evidence available." }));
          return;
        }
        setOpen(false);
        router.push(`/replay/${run.id}`);
        return;
      }

      if (action.kind === "promote_golden") {
        if (!replayId) {
          setActionStatus((prev) => ({ ...prev, [key]: "No replay evidence available." }));
          return;
        }
        const { targetSet, createdCount } = await promoteReplayToGolden(replayId);
        setActionStatus((prev) => ({
          ...prev,
          [key]: `${createdCount} trace${createdCount === 1 ? "" : "s"} added to ${targetSet.name}.`,
        }));
        void queryClient.invalidateQueries({ queryKey: ["golden-sets"] });
        void queryClient.invalidateQueries({ queryKey: ["golden-traces", targetSet.id] });
        setOpen(false);
        router.push("/goldens");
      }
    } catch (error) {
      setActionStatus((prev) => ({
        ...prev,
        [key]: error instanceof Error ? error.message : "Action failed.",
      }));
    }
  }

  async function promoteReplayToGolden(replayId: string): Promise<{ targetSet: GoldenSetView; createdCount: number }> {
    const run = await getReplayRun(replayId);
    const verifiedFix = replayVerifiedFix(run.replay_mode, run.summary.verified_fix);
    const promotableTraces = run.traces.filter((trace) => trace.status === "pass" && Boolean(trace.call_id_replayed));

    if (run.status !== "pass" || run.replay_mode_warning || !verifiedFix || promotableTraces.length === 0) {
      throw new Error("Only verified, non-stub passing replays can be promoted to goldens.");
    }

    const sets = await listGoldenSets({ limit: 100 });
    let targetSet = sets.items.find((set) => set.name === ASK_GOLDEN_SET_NAME) ?? null;
    if (!targetSet) {
      targetSet = await createGoldenSet({
        name: ASK_GOLDEN_SET_NAME,
        description: "Verified replay traces promoted from Ask Zroky.",
      });
    }

    let createdCount = 0;
    for (const trace of promotableTraces) {
      if (!trace.call_id_replayed) continue;
      await addGoldenTrace(targetSet.id, {
        call_id: trace.call_id_replayed,
        expected_output_text: trace.output_text ?? undefined,
        criteria_json: promotionCriteria(run, trace),
        weight: 1,
      });
      createdCount += 1;
    }

    return { targetSet, createdCount };
  }

  function reset() {
    setTurns([]);
    setContext(null);
    setQuestion("");
    setTurnFeedback({});
    setActionStatus({});
  }

  if (!open) {
    return null;
  }

  const isIdle = turns.length === 0 && !pending;

  return (
    <div
      className="ask-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label="Ask Zroky"
      onClick={() => setOpen(false)}
    >
      <div className="ask-drawer" onClick={(e) => e.stopPropagation()}>
        <header className="ask-head">
          <div className="ask-head-title">
            <Sparkles className="ask-head-icon" aria-hidden="true" />
            <div>
              <h3>Ask Zroky</h3>
              <p>Natural-language Q&amp;A over your agent telemetry.</p>
            </div>
          </div>
          <div className="ask-head-actions">
            {turns.length > 0 && (
              <button type="button" className="ask-reset-btn" onClick={reset}>
                New chat
              </button>
            )}
            <button
              type="button"
              className="ask-close-btn"
              aria-label="Close Ask Zroky"
              onClick={() => setOpen(false)}
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </header>

        {context && (
          <div className="ask-context-pill">
            Scoped to{" "}
            <span className="mono">
              {context.call_id ? `call ${context.call_id.slice(0, 8)}` : null}
              {context.issue_id ? `issue ${context.issue_id.slice(0, 8)}` : null}
              {context.anomaly_id ? `issue ${context.anomaly_id.slice(0, 8)}` : null}
              {context.trace_id ? `trace ${context.trace_id.slice(0, 8)}` : null}
            </span>
            <button
              type="button"
              className="ask-context-clear"
              onClick={() => setContext(null)}
              aria-label="Clear context"
            >
              clear
            </button>
          </div>
        )}

        <div className="ask-body" ref={listRef}>
          {isIdle ? (
            // Cold-start: no data yet
            !hasData && !callsQuery.isLoading ? (
              <div className="ask-empty">
                <div className="ask-empty-mark" aria-hidden="true">
                  <MessageSquarePlus className="h-5 w-5" />
                </div>
                <p className="ask-empty-title">No data yet</p>
                <p className="ask-empty-sub">
                  Install the Zroky SDK to start analyzing your LLM calls.
                </p>
                <ol className="ask-setup-list">
                  <li>
                    <Link
                      href="/settings/keys"
                      className="ask-evidence-link"
                      onClick={() => setOpen(false)}
                    >
                      Settings - API Keys
                    </Link>{" "}
                    - copy your project key
                  </li>
                  <li>
                    <code className="ask-inline-code">npm i @zroky-ai/sdk</code> - install the SDK
                  </li>
                  <li>Instrument one LLM call - live data appears in seconds</li>
                </ol>
              </div>
            ) : (
              // Guided empty state with dynamic suggestions
              <div className="ask-empty">
                <div className="ask-empty-mark" aria-hidden="true">
                  <Sparkles className="h-5 w-5" />
                </div>
                <p className="ask-empty-title">Ask anything about your AI agent.</p>
                <p className="ask-empty-sub">Try one of these:</p>
                <div className="ask-suggestions">
                  {suggestions.map((q) => (
                    <button
                      key={q}
                      type="button"
                      className="ask-suggestion-btn"
                      onClick={() => void send(q)}
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            )
          ) : (
            <ol className="ask-turns">
              {turns.map((turn) => (
                <li key={turn.id} className={`ask-turn ask-turn-${turn.role}`}>
                  <div className="ask-bubble">
                    <p className="ask-bubble-text">{turn.text}</p>

                    {turn.role === "assistant" && buildWorkflowActions(turn).length > 0 && (
                      <div className="ask-actions">
                        {buildWorkflowActions(turn).map((action) => {
                          const status = actionStatus[`${turn.id}-${action.kind}`];
                          const busy = status === "Creating..." || status === "Promoting...";
                          const Icon = busy ? Loader2 : actionIcon(action.kind);
                          const className = `ask-action-button ask-action-${actionTone(action.kind)}`;
                          return (
                            <div key={`${turn.id}-${action.kind}`} className="ask-action-item">
                              {action.href ? (
                                <Link href={action.href} className={className} onClick={() => setOpen(false)}>
                                  <Icon className="ask-action-icon" aria-hidden="true" />
                                  {action.label}
                                </Link>
                              ) : (
                                <button
                                  type="button"
                                  className={className}
                                  onClick={() => void runWorkflowAction(turn, action)}
                                  disabled={busy}
                                >
                                  <Icon className={`ask-action-icon${busy ? " spin-icon" : ""}`} aria-hidden="true" />
                                  {status ?? action.label}
                                </button>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}

                    {turn.role === "assistant" &&
                      turn.evidence &&
                      turn.evidence.length > 0 && (
                        <div className="ask-evidence">
                          <p className="ask-evidence-label">Evidence</p>
                          <ul className="ask-evidence-list">
                            {turn.evidence.map((ev) => (
                              <li key={`${turn.id}-${ev.kind}-${ev.id}`}>
                                <Link
                                  href={ev.href}
                                  className="ask-evidence-link"
                                  onClick={() => setOpen(false)}
                                >
                                  <span
                                    className={`ask-evidence-kind ask-evidence-kind-${ev.kind}`}
                                  >
                                    {ev.kind.toLowerCase() === "anomaly" ? "issue" : ev.kind}
                                  </span>
                                  <span className="ask-evidence-label-text">{ev.label}</span>
                                </Link>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                    {turn.role === "assistant" && turn.fallback_reason && (
                      <p className="ask-fallback-note">
                        Heuristic answer (LLM unavailable: {turn.fallback_reason}).
                      </p>
                    )}

                    {turn.role === "assistant" && (
                      <div className="ask-feedback">
                        {turnFeedback[turn.id] ? (
                          <span className="ask-feedback-saved">
                            <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                            Thanks for the feedback!
                          </span>
                        ) : (
                          <>
                            <span className="ask-feedback-label">Helpful?</span>
                            <button
                              type="button"
                              className="ask-feedback-btn"
                              onClick={() => void handleFeedback(turn.id, "up")}
                              aria-label="Mark as helpful"
                              title="Helpful"
                            >
                              <ThumbsUp className="h-3.5 w-3.5" aria-hidden="true" />
                            </button>
                            <button
                              type="button"
                              className="ask-feedback-btn"
                              onClick={() => void handleFeedback(turn.id, "down")}
                              aria-label="Mark as not helpful"
                              title="Not helpful"
                            >
                              <ThumbsDown className="h-3.5 w-3.5" aria-hidden="true" />
                            </button>
                          </>
                        )}
                      </div>
                    )}
                  </div>
                </li>
              ))}
              {pending && (
                <li className="ask-turn ask-turn-assistant">
                  <div className="ask-bubble ask-bubble-pending">
                    <span className="ask-typing-dot" />
                    <span className="ask-typing-dot" />
                    <span className="ask-typing-dot" />
                  </div>
                </li>
              )}
            </ol>
          )}
        </div>

        <form
          className="ask-input-row"
          onSubmit={(e) => {
            e.preventDefault();
            void send(question);
          }}
        >
          <input
            ref={inputRef}
            type="text"
            className="ask-input"
            placeholder="Ask anything about your agent…"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            disabled={pending}
            autoComplete="off"
            spellCheck={false}
          />
          <button
            type="submit"
            className="ask-send-btn"
            disabled={pending || !question.trim()}
            aria-label="Send"
          >
            <Send className="h-4 w-4" />
          </button>
        </form>
      </div>
    </div>
  );
}
