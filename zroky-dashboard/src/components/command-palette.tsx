"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import {
  DASHBOARD_PRIMARY_ROUTES,
  type DashboardPrimaryRoute,
} from "@/lib/dashboard-route-contract";

interface CommandItem {
  id: string;
  label: string;
  description: string;
  shortcut?: string;
  action: () => void;
}

type PrimaryCommandCopy = {
  href?: string;
  description: string;
  shortcut?: string;
};

const PRIMARY_COMMAND_COPY: Record<DashboardPrimaryRoute["id"], PrimaryCommandCopy> = {
  home: {
    description: "Protected agents, risky actions, outcome proof, approvals, and evidence gaps",
    shortcut: "Ctrl+H",
  },
  operations: {
    description: "Live runs, outcome incidents, approval queues, and recovery state",
  },
  workflows: {
    description: "Workflow Assurance Packs, validation, and immutable workflow versions",
  },
  systems: {
    description: "System-of-record connectors, preflight runs, and proof coverage",
  },
  evidence: {
    description: "Evidence bundles, audit hashes, linked decisions, and export proof",
  },
  settings: {
    href: "/settings/keys",
    description: "API keys, members, billing, and workspace controls",
    shortcut: "Ctrl+S",
  },
};

function useCommandItems(): CommandItem[] {
  const router = useRouter();

  const primaryCommands = DASHBOARD_PRIMARY_ROUTES.map((route) => {
    const commandCopy = PRIMARY_COMMAND_COPY[route.id];
    const href = commandCopy.href ?? route.href;
    return {
      id: route.id,
      label: `Go to ${route.label}`,
      description: commandCopy.description,
      shortcut: commandCopy.shortcut,
      action: () => router.push(href),
    } satisfies CommandItem;
  });

  return [
    ...primaryCommands,
    { id: "settings-keys", label: "Settings → API keys", description: "Create and revoke API keys", action: () => router.push("/settings/keys") },
    { id: "settings-billing", label: "Settings → Plan & Billing", description: "Plan, usage, payments", action: () => router.push("/settings/billing") },
    { id: "settings-team", label: "Settings → Members", description: "Invite and remove members", action: () => router.push("/settings/team") },
    { id: "settings-workspace", label: "Settings → Workspace", description: "Project identity and workspace metadata", action: () => router.push("/settings/workspace") },
    { id: "integrations-slack", label: "Connectors → Slack", description: "Connect Slack reliability events", action: () => router.push("/integrations/slack") },
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
