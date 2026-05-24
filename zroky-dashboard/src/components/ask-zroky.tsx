"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { Send, Sparkles, X } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { askZroky, listCalls, listAlerts, submitAskFeedback } from "@/lib/api";
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
}

function uid(): string {
  return Math.random().toString(36).slice(2, 11);
}

export function AskZroky() {
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [pending, setPending] = useState(false);
  const [context, setContext] = useState<AskContext | null>(null);
  const [turnFeedback, setTurnFeedback] = useState<Record<string, "up" | "down">>({});
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

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
      const assistantTurn: ChatTurn = {
        id: uid(),
        role: "assistant",
        text: result.answer,
        evidence: result.evidence,
        suggested_actions: result.suggested_actions,
        used_llm: result.used_llm,
        fallback_reason: result.fallback_reason,
        intent: result.intent,
        confidence: result.confidence,
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

  function reset() {
    setTurns([]);
    setContext(null);
    setQuestion("");
    setTurnFeedback({});
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
              {context.anomaly_id ? `anomaly ${context.anomaly_id.slice(0, 8)}` : null}
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

                    {turn.role === "assistant" &&
                      turn.suggested_actions &&
                      turn.suggested_actions.length > 0 && (
                        <ul className="ask-actions">
                          {turn.suggested_actions.map((action, idx) => (
                            <li
                              // eslint-disable-next-line react/no-array-index-key
                              key={`${turn.id}-action-${idx}`}
                              className="ask-action-item"
                            >
                              <span className="ask-action-arrow" aria-hidden="true">
                                →
                              </span>
                              <span>{action}</span>
                            </li>
                          ))}
                        </ul>
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
                                    {ev.kind}
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