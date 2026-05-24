"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

interface CommandItem {
  id: string;
  label: string;
  description: string;
  shortcut?: string;
  action: () => void;
}

function useCommandItems(): CommandItem[] {
  const router = useRouter();
  return [
    // Watch (Observability)
    { id: "home", label: "Go to Home", description: "Health check + live agent activity", shortcut: "Ctrl+H", action: () => router.push("/home") },
    { id: "calls", label: "Go to Calls", description: "What your agent said — prompts, responses, latency", shortcut: "Ctrl+C", action: () => router.push("/calls") },
    { id: "alerts", label: "Go to Alerts", description: "Triage open alerts — acknowledge, resolve, reopen", shortcut: "Ctrl+I", action: () => router.push("/alerts") },
    { id: "cost", label: "Go to Cost", description: "Spend, waste, and cost of failures", action: () => router.push("/cost") },
    { id: "outcomes", label: "Go to Outcomes", description: "Business cost of failures — refunds, escalations, churn attributed by agent", action: () => router.push("/outcomes") },
    // Pilot (Actionable)
    { id: "recommendations", label: "Go to Fix Queue", description: "What to fix next, ranked by impact ($)", action: () => router.push("/recommendations") },
    { id: "replay", label: "Go to Replay", description: "Test a fix against past data before deploying", action: () => router.push("/replay") },
    { id: "calibration", label: "Go to Calibration", description: "LLM judge calibration — golden sets, accuracy, run history", action: () => router.push("/calibration") },
    { id: "calibration-goldens", label: "Calibration → Golden Sets", description: "Add production traces and label pass/fail/inconclusive", action: () => router.push("/calibration?tab=goldens") },
    { id: "calibration-judge", label: "Calibration → Judge Results", description: "Run calibration, check accuracy gauge and confusion matrix", action: () => router.push("/calibration?tab=judge") },
    { id: "calibration-score", label: "Calibration → Score Overview", description: "Per-model accuracy rings and blocking/advisory mode", action: () => router.push("/calibration?tab=score") },
    // Ask Zroky
    { id: "ask", label: "Ask Zroky", description: "Ask anything about your agent — natural language Q&A", shortcut: "Ctrl+K", action: () => window.dispatchEvent(new CustomEvent("open-ask-zroky")) },
    // Settings
    { id: "settings", label: "Go to Settings", description: "Project, members, providers, plan & billing", shortcut: "Ctrl+S", action: () => router.push("/settings") },
    { id: "settings-keys", label: "Settings → API Keys", description: "Create and revoke API keys", action: () => router.push("/settings/keys") },
    { id: "settings-billing", label: "Settings → Plan & Billing", description: "Plan, usage, Stripe portal", action: () => router.push("/settings/billing") },
    { id: "settings-team", label: "Settings → Members", description: "Invite and remove members", action: () => router.push("/settings/team") },
    { id: "settings-providers", label: "Settings → Providers", description: "Provider keys vault for replay", action: () => router.push("/settings/providers") },
    { id: "settings-slack", label: "Settings → Slack", description: "Connect Slack alerts and reliability events", action: () => router.push("/settings/integrations/slack") },
    { id: "settings-teams", label: "Settings → Microsoft Teams", description: "Connect Teams alerts and reliability events", action: () => router.push("/settings/integrations/teams") },
    { id: "settings-profile", label: "Settings → Profile", description: "Identity, password, 2FA, account deletion", action: () => router.push("/settings/profile") },
  ];
}

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const allItems = useCommandItems();

  const filtered = query.trim()
    ? allItems.filter(
        (item) =>
          item.label.toLowerCase().includes(query.toLowerCase()) ||
          item.description.toLowerCase().includes(query.toLowerCase()),
      )
    : allItems;

  // Reset active index when filtered list changes
  useEffect(() => {
    setActiveIndex(0);
  }, [query]);

  // Listen for the open event dispatched by keyboard-shortcuts.ts
  useEffect(() => {
    const onOpen = () => {
      setOpen(true);
      setQuery("");
      setActiveIndex(0);
    };
    const onEscape = () => setOpen(false);
    window.addEventListener("open-command-palette", onOpen);
    window.addEventListener("escape-pressed", onEscape);
    return () => {
      window.removeEventListener("open-command-palette", onOpen);
      window.removeEventListener("escape-pressed", onEscape);
    };
  }, []);

  // Focus input when opened
  useEffect(() => {
    if (open) {
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  function close() {
    setOpen(false);
    setQuery("");
  }

  function runItem(item: CommandItem) {
    item.action();
    close();
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") {
      close();
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const item = filtered[activeIndex];
      if (item) runItem(item);
    }
  }

  // Scroll active item into view
  useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    const active = list.querySelector<HTMLLIElement>("[data-active='true']");
    if (active) active.scrollIntoView({ block: "nearest" });
  }, [activeIndex]);

  if (!open) return null;

  return (
    <div className="cp-backdrop" role="dialog" aria-modal="true" aria-label="Command palette" onClick={close}>
      <div className="cp-shell" onClick={(e) => e.stopPropagation()}>
        <div className="cp-search-row">
          <span className="cp-icon" aria-hidden="true">⌕</span>
          <input
            ref={inputRef}
            className="cp-input"
            type="text"
            placeholder="Search pages and actions…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            autoComplete="off"
            spellCheck={false}
          />
          <kbd className="cp-esc-hint" onClick={close}>Esc</kbd>
        </div>

        {filtered.length === 0 ? (
          <div className="cp-empty">No results for &ldquo;{query}&rdquo;</div>
        ) : (
          <ul className="cp-list" ref={listRef} role="listbox">
            {filtered.map((item, idx) => (
              <li
                key={item.id}
                className={`cp-item ${idx === activeIndex ? "cp-item-active" : ""}`}
                data-active={idx === activeIndex ? "true" : "false"}
                role="option"
                aria-selected={idx === activeIndex}
                onClick={() => runItem(item)}
                onMouseEnter={() => setActiveIndex(idx)}
              >
                <div className="cp-item-main">
                  <span className="cp-item-label">{item.label}</span>
                  <span className="cp-item-desc">{item.description}</span>
                </div>
                {item.shortcut ? <kbd className="cp-kbd">{item.shortcut}</kbd> : null}
              </li>
            ))}
          </ul>
        )}

        <div className="cp-footer">
          <span><kbd className="cp-kbd-sm">↑↓</kbd> navigate</span>
          <span><kbd className="cp-kbd-sm">↵</kbd> open</span>
          <span><kbd className="cp-kbd-sm">Esc</kbd> close</span>
        </div>
      </div>
    </div>
  );
}
