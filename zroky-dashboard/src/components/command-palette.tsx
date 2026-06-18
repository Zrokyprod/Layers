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
    { id: "command-center", label: "Go to Command Center", description: "Open capture health, failures, replay gaps, Goldens, CI gates, and policy status", shortcut: "Ctrl+A", action: () => router.push("/home") },
    { id: "agents", label: "Go to Agents", description: "Agent safety coverage, replay proof, and open failure status", action: () => router.push("/agents") },
    { id: "traces", label: "Go to Traces", description: "Execution evidence across inputs, tools, RAG, memory, policy, outcome, and versions", action: () => router.push("/trace") },
    { id: "issues", label: "Go to Failures", description: "Grouped production failures with root cause and action context", shortcut: "Ctrl+I", action: () => router.push("/issues") },
    { id: "replay", label: "Go to Replay", description: "Verify fixes against production-derived traces before deploying", action: () => router.push("/replay") },
    { id: "goldens", label: "Go to Goldens", description: "Production-derived regression contracts and CI blocking coverage", action: () => router.push("/goldens") },
    { id: "ci-gates", label: "Go to CI Gates", description: "Deploy safety verdicts, failed Goldens, and protected-flow gates", action: () => router.push("/ci-gates") },
    { id: "policies", label: "Go to Policies", description: "Runtime limits, approval rules, allowed tools, and kill switch state", action: () => router.push("/policies") },
    { id: "approvals", label: "Go to Approvals", description: "Paused risky actions, policy hits, and approval audit trail", action: () => router.push("/approvals") },
    { id: "integrations", label: "Go to Integrations", description: "Provider, GitHub, Slack, and capture connection health", action: () => router.push("/integrations") },
    { id: "home", label: "Open Command Center", description: "Default dashboard home", shortcut: "Ctrl+H", action: () => router.push("/home") },
    { id: "settings-evaluation", label: "Settings → Evaluation", description: "Calibration and judge controls live in settings", action: () => router.push("/settings/evaluation") },
    { id: "settings-evaluation-calibration", label: "Settings → Evaluation → Calibration", description: "Open calibration controls in settings", action: () => router.push("/settings/evaluation?workspace=calibration") },
    { id: "settings-evaluation-judge", label: "Settings → Evaluation → Judge", description: "Open judge controls in settings", action: () => router.push("/settings/evaluation?workspace=judge") },
    { id: "settings", label: "Go to Settings", description: "Project, members, providers, plan & billing", shortcut: "Ctrl+S", action: () => router.push("/settings") },
    { id: "settings-keys", label: "Settings → API Keys", description: "Create and revoke API keys", action: () => router.push("/settings/keys") },
    { id: "settings-billing", label: "Settings → Plan & Billing", description: "Plan, usage, payments", action: () => router.push("/settings/billing") },
    { id: "settings-team", label: "Settings → Members", description: "Invite and remove members", action: () => router.push("/settings/team") },
    { id: "settings-providers", label: "Settings → Providers", description: "Provider keys vault for replay", action: () => router.push("/settings/providers") },
    { id: "integrations-slack", label: "Integrations → Slack", description: "Connect Slack reliability events", action: () => router.push("/settings/integrations/slack") },
    { id: "account-profile", label: "Account → Profile", description: "Identity, password, sessions, and account deletion", action: () => router.push("/account") },
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
