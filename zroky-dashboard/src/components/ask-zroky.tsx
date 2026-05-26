"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { Send, Sparkles, X } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { askZroky, listCalls, listAlerts, submitAskFeedback } from "@/lib/api";
import { useCreateReplayRunFromCall, useCreateReplayRunFromIssue } from "@/lib/hooks";
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

function buildWorkflowActions(turn: ChatTurn): AskWorkflowAction[] {
  const evidence = turn.evidence ?? [];
  if (evidence.length === 0) return [];
  const context = turn.context ?? null;
  const callEvidence = evidenceFor(evidence, ["call"]);
  const issueEvidence = evidenceFor(evidence, ["issue", "anomaly"]);
  const traceEvidence = evidenceFor(evidence, ["trace"]);
  const replayEvidence = evidenceFor(evidence, ["replay"]);
  const callId = context?.call_id ?? callEvidence?.id ?? idFromHref(callEvidence?.href, "/calls");
  const issueId = context?.issue_id ?? context?.anomaly_id ?? issueEvidence?.id ?? idFromHref(issueEvidence?.href, "/issues");
  const traceId = context?.trace_id ?? traceEvidence?.id ?? idFromHref(traceEvidence?.href, "/trace");
  const replayId = replayEvidence?.id ?? idFromHref(replayEvidence?.href, "/replay");
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
    if (kind === "promote_golden") actions.push({ kind, label: "Promote Golden", href: replayId ? `/replay/${encodeURIComponent(replayId)}` : "/goldens" });
  }

  return actions;
}

export function AskZroky() {
  const router = useRouter();
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
    if (action.kind !== "create_replay") return;
    const evidence = turn.evidence ?? [];
    const callEvidence = evidenceFor(evidence, ["call"]);
    const issueEvidence = evidenceFor(evidence, ["issue", "anomaly"]);
    const callId = turn.context?.call_id ?? callEvidence?.id ?? idFromHref(callEvidence?.href, "/calls");
    const issueId = turn.context?.issue_id ?? turn.context?.anomaly_id ?? issueEvidence?.id ?? idFromHref(issueEvidence?.href, "/issues");
    setActionStatus((prev) => ({ ...prev, [`${turn.id}-${action.kind}`]: "Creating replay..." }));
    try {
      const run = issueId
        ? await createReplayFromIssue.mutateAsync({ issueId, payload: { replay_mode: "real_llm" } })
        : callId
        ? await createReplayFromCall.mutateAsync({ callId, payload: { replay_mode: "real_llm" } })
        : null;
      if (!run) {
        setActionStatus((prev) => ({ ...prev, [`${turn.id}-${action.kind}`]: "No call or issue evidence available." }));
        return;
      }
      setOpen(false);
      router.push(`/replay/${run.id}`);
    } catch (error) {
      setActionStatus((prev) => ({
        ...prev,
        [`${turn.id}-${action.kind}`]: error instanceof Error ? error.message : "Create replay failed.",
      }));
    }
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
    <div className="ask-backdrop" role="dialog" aria-modal="true" aria-label="Ask Zroky">
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
                <p className="ask-empty-title">No data yet</p>
                <p className="ask-empty-sub">
                  Install the Zroky SDK to start analyzing your LLM calls.
                </p>
                <ol
                  style={{
                    paddingLeft: "1.25rem",
                    fontSize: "0.8rem",
                    lineHeight: 1.7,
                    color: "var(--text-muted, #8b90a3)",
                    margin: "0.75rem 0 1rem",
                  }}
                >
                  <li>
                    <Link
                      href="/settings/keys"
                      className="ask-evidence-link"
                      onClick={() => setOpen(false)}
                    >
                      Settings → API Keys
                    </Link>{" "}
                    — copy your project key
                  </li>
                  <li>
                    <code
                      style={{
                        fontFamily: "ui-monospace, monospace",
                        fontSize: "0.78rem",
                        background: "var(--surface-2, rgba(255,255,255,.06))",
                        padding: "0 0.25rem",
                        borderRadius: "3px",
                      }}
                    >
                      npm i zroky-sdk
                    </code>{" "}
                    — install the SDK
                  </li>
                  <li>Instrument one LLM call — live data appears in seconds</li>
                </ol>
              </div>
            ) : (
              // Guided empty state with dynamic suggestions
              <div className="ask-empty">
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
                          return (
                            <div key={`${turn.id}-${action.kind}`} className="ask-action-item">
                              {action.href ? (
                                <Link href={action.href} className="ask-action-button" onClick={() => setOpen(false)}>
                                  {action.label}
                                </Link>
                              ) : (
                                <button type="button" className="ask-action-button" onClick={() => void runWorkflowAction(turn, action)}>
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
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "0.4rem",
                          marginTop: "0.6rem",
                          fontSize: "0.72rem",
                        }}
                      >
                        {turnFeedback[turn.id] ? (
                          <span style={{ color: "var(--text-muted, #8b90a3)" }}>
                            Thanks for the feedback!
                          </span>
                        ) : (
                          <>
                            <span style={{ color: "var(--text-muted, #8b90a3)" }}>
                              Helpful?
                            </span>
                            <button
                              type="button"
                              className="ask-reset-btn"
                              onClick={() => void handleFeedback(turn.id, "up")}
                              aria-label="Mark as helpful"
                            >
                              👍
                            </button>
                            <button
                              type="button"
                              className="ask-reset-btn"
                              onClick={() => void handleFeedback(turn.id, "down")}
                              aria-label="Mark as not helpful"
                            >
                              👎
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
