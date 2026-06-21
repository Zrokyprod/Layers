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
    { id: "home", label: "Go to Home", description: "Protected agents, risky actions, outcome proof, approvals, and evidence gaps", shortcut: "Ctrl+H", action: () => router.push("/home") },
    { id: "agents", label: "Go to Agents", description: "Protected agents, mandates, safety coverage, and proof readiness", action: () => router.push("/agents") },
    { id: "approvals", label: "Go to Approvals", description: "Held risky actions, runtime policy decisions, and approval audit", action: () => router.push("/approvals") },
    { id: "outcomes", label: "Go to Outcomes", description: "System-of-record matches, mismatches, and not-verified actions", action: () => router.push("/outcomes") },
    { id: "evidence", label: "Go to Evidence", description: "Evidence packs, audit hashes, linked decisions, and export proof", action: () => router.push("/evidence") },
    { id: "connectors", label: "Go to Connectors", description: "System-of-record connectors, preflight runs, and pilot handoff status", action: () => router.push("/integrations") },
    { id: "issues", label: "Go to Incidents", description: "Unsafe actions, wrong outcomes, connector failures, and proof gaps", shortcut: "Ctrl+I", action: () => router.push("/issues") },
    { id: "policies", label: "Go to Policies", description: "Agent mandates, runtime limits, approval rules, and kill switch", action: () => router.push("/policies") },
    { id: "replay", label: "Go to Replays", description: "Verify fixes against production-derived traces before deploying", action: () => router.push("/replay") },
    { id: "contracts", label: "Engineering - Contracts", description: "Regression contracts, fixtures, approval proof, and blocking coverage", action: () => router.push("/contracts") },
    { id: "ci-gates", label: "Engineering - CI", description: "Deploy safety verdicts, contract failures, and protected-flow gates", action: () => router.push("/ci-gates") },
    { id: "settings-evaluation", label: "Settings → Evaluation", description: "Calibration and judge controls live in settings", action: () => router.push("/settings/evaluation") },
    { id: "settings-evaluation-calibration", label: "Settings → Evaluation → Calibration", description: "Open calibration controls in settings", action: () => router.push("/settings/evaluation?workspace=calibration") },
    { id: "settings-evaluation-judge", label: "Settings → Evaluation → Judge", description: "Open judge controls in settings", action: () => router.push("/settings/evaluation?workspace=judge") },
    { id: "projects", label: "Go to Projects", description: "Project list, active context, plan limit, and deletion controls", action: () => router.push("/projects") },
    { id: "settings", label: "Go to Settings", description: "API keys, members, connectors, plan, and billing", shortcut: "Ctrl+S", action: () => router.push("/settings/keys") },
    { id: "settings-keys", label: "Settings → API Keys", description: "Create and revoke API keys", action: () => router.push("/settings/keys") },
    { id: "settings-billing", label: "Settings → Plan & Billing", description: "Plan, usage, payments", action: () => router.push("/settings/billing") },
    { id: "settings-team", label: "Settings → Members", description: "Invite and remove members", action: () => router.push("/settings/team") },
    { id: "settings-connectors", label: "Settings → Connectors", description: "Configure system-of-record, GitHub, and Slack connectors", action: () => router.push("/settings/integrations") },
    { id: "integrations-slack", label: "Connectors → Slack", description: "Connect Slack reliability events", action: () => router.push("/settings/integrations/slack") },
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
