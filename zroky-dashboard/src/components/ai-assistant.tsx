"use client";

import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import { usePathname } from "next/navigation";

function generateSessionId(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

type Source = { tool: string; summary: string };
type Msg = { role: "user" | "assistant"; text: string; sources?: Source[]; ts: number };

function getQuickPrompts(pathname: string): string[] {
  if (/^\/calls\/[^/]+/.test(pathname))
    return [
      "Explain this failure",
      "What's the likely root cause?",
      "How do I prevent this?",
    ];
  if (pathname === "/calls")
    return [
      "Which calls had the highest cost today?",
      "Show me recurring failure patterns",
      "Why is my error rate high?",
    ];
  if (pathname.startsWith("/cost"))
    return [
      "What's driving my cost spike?",
      "Which model is cheapest for my use case?",
      "How can I cut spend by 20%?",
    ];
  if (pathname.startsWith("/alerts"))
    return [
      "Which alert fired the most this week?",
      "How do I reduce alert noise?",
      "Summarise open incidents",
    ];
  if (pathname.startsWith("/traces"))
    return [
      "What does this trace tell me?",
      "Show slowest tool calls",
      "Are there any loops in this trace?",
    ];
  return [
    "Summarise today's incidents",
    "What should I investigate first?",
    "Any anomalies right now?",
  ];
}

export function AiAssistant() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Stable session ID for conversation memory — resets when chat is cleared
  const sessionId = useMemo(() => generateSessionId(), []);

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Focus input when panel opens
  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 120);
    }
  }, [open]);

  // Close on Escape
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && open) setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const send = useCallback(async (text: string) => {
    const msg = text.trim();
    if (!msg || loading) return;

    setMessages((m) => [...m, { role: "user", text: msg, ts: Date.now() }]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch("/api/zroky/v1/assistant/chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          message: msg,
          session_id: sessionId,
        }),
      });

      if (res.ok) {
        const data = (await res.json()) as {
          reply: string;
          sources: Source[];
          off_topic: boolean;
        };
        setMessages((m) => [
          ...m,
          {
            role: "assistant",
            text: data.reply,
            sources: data.sources ?? [],
            ts: Date.now(),
          },
        ]);
      } else {
        throw new Error(`${res.status}`);
      }
    } catch {
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          text: "Sorry, I couldn't process that. Check your connection and try again.",
          ts: Date.now(),
        },
      ]);
    } finally {
      setLoading(false);
    }
  }, [loading, sessionId]);

  const quickPrompts = getQuickPrompts(pathname);

  return (
    <>
      {/* Floating Action Button */}
      <button
        type="button"
        className={`ai-fab${open ? " ai-fab-open" : ""}`}
        onClick={() => setOpen((o) => !o)}
        aria-label={open ? "Close AI Assistant" : "Open AI Assistant"}
        title="Zroky AI Assistant"
      >
        {open ? "✕" : "✦"}
      </button>

      {/* Backdrop — mobile only */}
      {open && (
        <div
          className="ai-backdrop"
          aria-hidden="true"
          onClick={() => setOpen(false)}
        />
      )}

      {/* Slide-in panel */}
      <aside
        className={`ai-panel${open ? " ai-panel-open" : ""}`}
        aria-label="AI Assistant"
        role="complementary"
      >
        <div className="ai-panel-header">
          <div className="ai-panel-title">
            <span className="ai-panel-icon">✦</span>
            <span>Zroky AI</span>
          </div>
          <div className="ai-panel-actions">
            {messages.length > 0 && (
              <button
                type="button"
                className="ai-clear-btn"
                onClick={() => {
                  setMessages([]);
                  // Clear server-side session history
                  fetch(`/api/zroky/v1/assistant/chat/${encodeURIComponent(sessionId)}`, {
                    method: "DELETE",
                    credentials: "include",
                  }).catch(() => undefined);
                }}
                title="Clear chat"
              >
                Clear
              </button>
            )}
            <button
              type="button"
              className="ai-close-btn"
              onClick={() => setOpen(false)}
              aria-label="Close AI Assistant"
            >
              ✕
            </button>
          </div>
        </div>

        <div className="ai-context-bar">
          <span className="ai-context-label">Context:</span>
          <code className="ai-context-path">{pathname}</code>
        </div>

        <div className="ai-messages" role="log" aria-live="polite">
          {messages.length === 0 && (
            <div className="ai-empty">
              <p className="ai-empty-heading">Ask me anything about your AI usage.</p>
              <div className="ai-quick-prompts">
                {quickPrompts.map((p) => (
                  <button
                    key={p}
                    type="button"
                    className="ai-quick-prompt"
                    onClick={() => send(p)}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m) => (
            <div key={m.ts} className={`ai-msg ai-msg-${m.role}`}>
              {m.role === "assistant" && (
                <span className="ai-msg-icon">✦</span>
              )}
              <div className="ai-msg-body">
                <p className="ai-msg-text">{m.text}</p>
                {m.role === "assistant" && m.sources && m.sources.length > 0 && (
                  <ul className="ai-sources">
                    {m.sources.map((s) => (
                      <li key={s.tool} className="ai-source-item">
                        <span className="ai-source-tool">{s.tool}</span>
                        <span className="ai-source-summary">{s.summary}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          ))}

          {loading && (
            <div className="ai-msg ai-msg-assistant ai-msg-thinking">
              <span className="ai-msg-icon">✦</span>
              <span className="ai-thinking-dots">
                <span />
                <span />
                <span />
              </span>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        <div className="ai-input-row">
          <input
            ref={inputRef}
            className="ai-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(input);
              }
            }}
            placeholder="Ask Zroky AI…"
            disabled={loading}
            autoComplete="off"
            aria-label="Message input"
          />
          <button
            type="button"
            className="ai-send-btn"
            onClick={() => send(input)}
            disabled={loading || !input.trim()}
            aria-label="Send message"
          >
            ↑
          </button>
        </div>
      </aside>
    </>
  );
}
