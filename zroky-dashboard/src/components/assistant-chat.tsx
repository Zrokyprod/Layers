"use client";

import { useEffect, useRef, useState } from "react";

import { clearAssistantSession, sendAssistantMessage, type ToolSource } from "@/lib/assistant-api";

type Role = "user" | "assistant" | "error";

interface Message {
  id: string;
  role: Role;
  text: string;
  sources?: ToolSource[];
}

function generateSessionId(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`;
}

function getOrCreateSessionId(): string {
  if (typeof window === "undefined") return generateSessionId();
  const key = "zroky_assistant_session";
  const existing = window.sessionStorage.getItem(key);
  if (existing) return existing;
  const id = generateSessionId();
  window.sessionStorage.setItem(key, id);
  return id;
}

function msgId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

const SUGGESTIONS = [
  "What failed in the last 24 hours?",
  "Which model is costing the most?",
  "Are there any open alerts?",
  "Show me diagnosis summary for last 7 days",
];

function SourcePills({ sources }: { sources: ToolSource[] }) {
  if (!sources.length) return null;
  return (
    <div className="chat-source-pills">
      {sources.map((s, i) => (
        <span key={i} className="chat-source-pill" title={s.summary}>{s.tool}</span>
      ))}
    </div>
  );
}

function MessageBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === "user";
  const isError = msg.role === "error";
  return (
    <div className={`chat-bubble-row${isUser ? " chat-bubble-row-user" : " chat-bubble-row-assistant"}`}>
      <div className={`chat-bubble${isUser ? " chat-bubble-user" : isError ? " chat-bubble-error" : " chat-bubble-assistant"}`}>
        <p className="chat-bubble-text">{msg.text}</p>
        {!isUser && msg.sources && <SourcePills sources={msg.sources} />}
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="chat-bubble-row chat-bubble-row-assistant">
      <div className="chat-bubble chat-bubble-assistant chat-typing">
        <span className="chat-dot" />
        <span className="chat-dot" />
        <span className="chat-dot" />
      </div>
    </div>
  );
}

export function AssistantChat() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId] = useState<string>(() => getOrCreateSessionId());
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading, open]);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 50);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open]);

  const send = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || loading) return;
    setMessages((prev) => [...prev, { id: msgId(), role: "user", text: trimmed }]);
    setInput("");
    setLoading(true);
    abortRef.current = new AbortController();
    try {
      const data = await sendAssistantMessage(trimmed, sessionId, abortRef.current.signal);
      setMessages((prev) => [...prev, { id: msgId(), role: "assistant", text: data.reply, sources: data.sources }]);
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") return;
      setMessages((prev) => [...prev, { id: msgId(), role: "error", text: "Failed to reach assistant. Please try again." }]);
    } finally {
      setLoading(false);
      abortRef.current = null;
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(input); }
  };

  const handleClear = async () => {
    setMessages([]);
    await clearAssistantSession(sessionId).catch(() => {});
  };

  const isEmpty = messages.length === 0;

  return (
    <>
      {/* FAB trigger */}
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label="Open Zroky assistant"
        className={`chat-fab${open ? " chat-fab-hidden" : ""}`}
      >
        Γ£ª
      </button>

      {/* Panel */}
      <div className={`chat-panel${open ? " chat-panel-open" : ""}`}>
        {/* Header */}
        <div className="chat-panel-header">
          <div className="chat-panel-title">
            <span className="chat-panel-icon">Γ£ª</span>
            <span>Zroky Assistant</span>
            <span className="chat-beta-badge">BETA</span>
          </div>
          <div className="chat-panel-controls">
            {messages.length > 0 && (
              <button onClick={() => void handleClear()} aria-label="Clear conversation" className="chat-ctrl-btn">
                Clear
              </button>
            )}
            <button onClick={() => setOpen(false)} aria-label="Close assistant" className="chat-ctrl-btn">
              Γ£ò
            </button>
          </div>
        </div>

        {/* Messages */}
        <div className="chat-messages">
          {isEmpty && !loading && (
            <div className="chat-empty">
              <p className="chat-empty-hint">
                Ask anything about your project&apos;s AI costs, errors, or alerts.
              </p>
              <div className="chat-suggestions">
                {SUGGESTIONS.map((s) => (
                  <button key={s} onClick={() => void send(s)} className="chat-suggestion-btn">{s}</button>
                ))}
              </div>
            </div>
          )}
          {messages.map((msg) => <MessageBubble key={msg.id} msg={msg} />)}
          {loading && <TypingIndicator />}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className="chat-input-area">
          <div className="chat-input-row">
            <textarea
              ref={inputRef}
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about costs, errors, alertsΓÇª"
              disabled={loading}
              className="chat-textarea"
            />
            <button
              onClick={() => void send(input)}
              disabled={!input.trim() || loading}
              aria-label="Send message"
              className="chat-send-btn"
            >
              Γåæ
            </button>
          </div>
          <p className="chat-disclaimer">Only answers questions about this project&apos;s monitoring data.</p>
        </div>
      </div>
    </>
  );
}
