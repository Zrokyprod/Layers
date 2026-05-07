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
    { id: "home", label: "Go to Home", description: "Command center", shortcut: "Ctrl+H", action: () => router.push("/home") },
    { id: "calls", label: "Go to Calls", description: "Browse and filter all LLM calls", shortcut: "Ctrl+C", action: () => router.push("/calls") },
    { id: "fixes", label: "Go to Fixes", description: "Fix health, trust, and action queue", shortcut: "Ctrl+F", action: () => router.push("/fixes") },
    { id: "cost", label: "Go to Cost", description: "Spend trust, model mix, budget", action: () => router.push("/cost") },
    { id: "loops", label: "Go to Loops", description: "Agent loop incidents and waste", action: () => router.push("/loops") },
    { id: "auth-health", label: "Go to Auth Health", description: "Auth failure trend and MTTA", action: () => router.push("/auth-health") },
    { id: "trace", label: "Go to Traces", description: "Multi-agent trace tree", action: () => router.push("/trace") },
    { id: "alerts", label: "Go to Alerts", description: "Priority incidents", shortcut: "Ctrl+A", action: () => router.push("/alerts") },
    { id: "settings", label: "Go to Settings", description: "Project, policies, providers", shortcut: "Ctrl+S", action: () => router.push("/settings") },
    { id: "settings-keys", label: "Settings → API Keys", description: "Create and revoke API keys", action: () => router.push("/settings/keys") },
    { id: "settings-billing", label: "Settings → Billing", description: "Plan and spend limits", action: () => router.push("/settings/billing") },
    { id: "settings-team", label: "Settings → Team", description: "Invite and manage members", action: () => router.push("/settings/team") },
    { id: "settings-providers", label: "Settings → Providers", description: "AI provider connections", action: () => router.push("/settings/providers") },
    { id: "settings-support", label: "Settings → Support", description: "Create and manage support tickets", action: () => router.push("/settings/support") },
    { id: "notifications", label: "Go to Notifications", description: "Activity alerts and messages", action: () => router.push("/notifications") },
    { id: "account", label: "Go to Account", description: "Profile, password, login methods", action: () => router.push("/account") },
    { id: "onboarding", label: "Go to Onboarding", description: "First-time setup wizard", action: () => router.push("/onboarding") },
  ];
}

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const router = useRouter();
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
