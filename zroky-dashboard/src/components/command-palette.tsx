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
    // Watch
    { id: "home", label: "Go to Home", description: "Health, activity, and pilot impact", shortcut: "Ctrl+H", action: () => router.push("/home") },
    { id: "calls", label: "Go to Calls", description: "Search and inspect captured calls", shortcut: "Ctrl+C", action: () => router.push("/calls") },
    { id: "trace", label: "Go to Traces", description: "Multi-agent trace tree", action: () => router.push("/trace") },
    { id: "anomalies", label: "Go to Anomalies", description: "Detector-driven anomalies and diagnoses", shortcut: "Ctrl+I", action: () => router.push("/anomalies") },
    { id: "alerts", label: "Go to Alerts", description: "Priority incidents", shortcut: "Ctrl+A", action: () => router.push("/alerts") },
    // Pilot (paid)
    { id: "pilot", label: "Go to Pilot", description: "Autopilot policy and action feed", action: () => router.push("/pilot") },
    { id: "goldens", label: "Go to Goldens", description: "Production-trace canonicals", action: () => router.push("/goldens") },
    { id: "replay", label: "Go to Replay Runs", description: "Replay run history", action: () => router.push("/replay") },
    { id: "judge", label: "Go to Judge Calibration", description: "Accuracy scoreboard, confusion matrix, mode control", action: () => router.push("/judge") },
    { id: "calibration", label: "Go to Calibration Score", description: "Public per-model accuracy, F1 per class, blocking/advisory mode", action: () => router.push("/calibration") },
    { id: "outcomes", label: "Go to Cost Attribution", description: "Dollar cost of every bad AI outcome — by type, cluster, and replay savings", action: () => router.push("/outcomes") },
    { id: "root-cause", label: "Go to Root Cause", description: "Statistical causal ablation — identify which axis explains each AI failure", action: () => router.push("/root-cause") },
    { id: "reliability", label: "Go to Reliability", description: "Composite 0-100 health score per agent — fail rate, cost, determinism, trend", action: () => router.push("/reliability") },
    { id: "recommendations", label: "Go to Fix Queue", description: "Ranked actionable fix items — causal axis failures, determinism spikes, cost overruns", action: () => router.push("/recommendations") },
    { id: "digest", label: "Go to Digest", description: "Weekly impact summaries", action: () => router.push("/digest") },
    { id: "drift", label: "Go to Provider Drift", description: "Silent-update alerts for major LLM providers", action: () => router.push("/drift") },
    { id: "notifications", label: "Go to Notifications", description: "Account inbox for alerts and product updates", action: () => router.push("/notifications") },
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
