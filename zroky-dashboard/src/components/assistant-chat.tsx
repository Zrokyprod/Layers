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
        ✦
      </button>

      {/* Panel */}
      <div className={`chat-panel${open ? " chat-panel-open" : ""}`}>
        {/* Header */}
        <div className="chat-panel-header">
          <div className="chat-panel-title">
            <span className="chat-panel-icon">✦</span>
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
              ✕
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
              placeholder="Ask about costs, errors, alerts…"
              disabled={loading}
              className="chat-textarea"
            />
            <button
              onClick={() => void send(input)}
              disabled={!input.trim() || loading}
              aria-label="Send message"
              className="chat-send-btn"
            >
              ↑
            </button>
          </div>
          <p className="chat-disclaimer">Only answers questions about this project&apos;s monitoring data.</p>
        </div>
      </div>
    </>
  );
}


// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Role = "user" | "assistant" | "error";

interface Message {
  id: string;
  role: Role;
  text: string;
  sources?: ToolSource[];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Suggestion chips — starter questions for new users
// ---------------------------------------------------------------------------

const SUGGESTIONS = [
  "What failed in the last 24 hours?",
  "Which model is costing the most?",
  "Are there any open alerts?",
  "Show me diagnosis summary for last 7 days",
];

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SourcePills({ sources }: { sources: ToolSource[] }) {
  if (!sources.length) return null;
  return (
    <div className="mt-1.5 flex flex-wrap gap-1">
      {sources.map((s, i) => (
        <span
          key={i}
          className="inline-flex items-center rounded-full border border-border bg-muted/50 px-2 py-0.5 text-[10px] text-muted-foreground"
          title={s.summary}
        >
          {s.tool}
        </span>
      ))}
    </div>
  );
}

function MessageBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === "user";
  const isError = msg.role === "error";

  return (
    <div className={cn("flex w-full", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[85%] rounded-xl px-3 py-2 text-sm leading-relaxed",
          isUser && "bg-primary text-primary-foreground",
          !isUser && !isError && "bg-muted text-foreground",
          isError && "border border-destructive/40 bg-destructive/10 text-destructive",
        )}
      >
        <p className="whitespace-pre-wrap break-words">{msg.text}</p>
        {!isUser && msg.sources && <SourcePills sources={msg.sources} />}
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="flex items-center gap-1 rounded-xl bg-muted px-3 py-2">
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:-0.3s]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:-0.15s]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground" />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function AssistantChat() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId] = useState<string>(() => getOrCreateSessionId());
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Scroll to bottom on new messages
  useEffect(() => {
    if (open) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, loading, open]);

  // Focus input when panel opens
  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open]);

  const send = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || loading) return;

    const userMsg: Message = { id: msgId(), role: "user", text: trimmed };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    abortRef.current = new AbortController();

    try {
      const data = await sendAssistantMessage(trimmed, sessionId, abortRef.current.signal);
      const assistantMsg: Message = {
        id: msgId(),
        role: "assistant",
        text: data.reply,
        sources: data.sources,
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") return;
      const errorMsg: Message = {
        id: msgId(),
        role: "error",
        text: "Failed to reach assistant. Please try again.",
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setLoading(false);
      abortRef.current = null;
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void send(input);
    }
  };

  const handleClear = async () => {
    setMessages([]);
    await clearAssistantSession(sessionId).catch(() => {});
  };

  const isEmpty = messages.length === 0;

  return (
    <>
      {/* Floating trigger button */}
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label="Open Zroky assistant"
        className={cn(
          "fixed bottom-6 right-6 z-50 flex h-12 w-12 items-center justify-center",
          "rounded-full bg-primary text-primary-foreground shadow-lg",
          "transition-transform hover:scale-105 active:scale-95",
          open && "opacity-0 pointer-events-none",
        )}
      >
        <Bot className="h-5 w-5" />
      </button>

      {/* Chat panel */}
      <div
        className={cn(
          "fixed bottom-6 right-6 z-50 flex flex-col",
          "w-[360px] max-h-[560px] rounded-2xl border border-border bg-background shadow-2xl",
          "transition-all duration-200",
          open ? "opacity-100 scale-100" : "opacity-0 scale-95 pointer-events-none",
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div className="flex items-center gap-2">
            <Bot className="h-4 w-4 text-primary" />
            <span className="text-sm font-semibold">Zroky Assistant</span>
            <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] text-primary font-medium">
              BETA
            </span>
          </div>
          <div className="flex items-center gap-1">
            {messages.length > 0 && (
              <button
                onClick={handleClear}
                aria-label="Clear conversation"
                className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            )}
            <button
              onClick={() => setOpen(false)}
              aria-label="Close assistant"
              className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3 min-h-0">
          {isEmpty && !loading && (
            <div className="space-y-3">
              <p className="text-center text-xs text-muted-foreground pt-2">
                Ask anything about your project&apos;s AI costs, errors, or alerts.
                <br />
                Answers are grounded in real data — no guessing.
              </p>
              <div className="space-y-1.5">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => void send(s)}
                    className={cn(
                      "w-full rounded-lg border border-border bg-muted/40 px-3 py-2",
                      "text-left text-xs text-muted-foreground",
                      "hover:bg-muted hover:text-foreground transition-colors",
                    )}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((msg) => (
            <MessageBubble key={msg.id} msg={msg} />
          ))}
          {loading && <TypingIndicator />}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className="border-t border-border px-3 py-2.5">
          <div className="flex items-end gap-2">
            <textarea
              ref={inputRef}
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about costs, errors, alerts…"
              disabled={loading}
              className={cn(
                "flex-1 resize-none rounded-lg border border-input bg-background",
                "px-3 py-2 text-sm placeholder:text-muted-foreground",
                "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
                "disabled:opacity-50 max-h-24 overflow-y-auto",
              )}
              style={{ minHeight: "36px" }}
            />
            <button
              onClick={() => void send(input)}
              disabled={!input.trim() || loading}
              aria-label="Send message"
              className={cn(
                "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg",
                "bg-primary text-primary-foreground",
                "disabled:opacity-40 disabled:cursor-not-allowed",
                "hover:bg-primary/90 transition-colors",
              )}
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
          <p className="mt-1.5 text-[10px] text-muted-foreground">
            Only answers questions about this project&apos;s monitoring data.
          </p>
        </div>
      </div>
    </>
  );
}
