"use client";

import { useEffect, useState } from "react";
import { X } from "lucide-react";

import { KEYBOARD_SHORTCUTS_HELP } from "@/lib/keyboard-shortcuts";

export function ShortcutsHelp() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const show = () => setOpen(true);
    const onEscape = () => setOpen(false);
    window.addEventListener("show-shortcuts-help", show);
    window.addEventListener("escape-pressed", onEscape);
    return () => {
      window.removeEventListener("show-shortcuts-help", show);
      window.removeEventListener("escape-pressed", onEscape);
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open]);

  if (!open) return null;

  return (
    <div
      className="sh-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label="Keyboard shortcuts"
      onClick={(e) => { if (e.target === e.currentTarget) setOpen(false); }}
    >
      <div className="sh-shell">
        <div className="sh-header">
          <span className="sh-title">Keyboard Shortcuts</span>
          <button
            type="button"
            className="sh-close"
            aria-label="Close shortcuts help"
            onClick={() => setOpen(false)}
          >
            <X size={16} />
          </button>
        </div>
        <ul className="sh-list" role="list">
          {KEYBOARD_SHORTCUTS_HELP.map((s) => (
            <li key={s.description} className="sh-item">
              <span className="sh-desc">{s.description}</span>
              <span className="sh-keys">
                {s.keys.map((k, i) => (
                  <kbd key={i} className="sh-kbd">{k}</kbd>
                ))}
              </span>
            </li>
          ))}
        </ul>
        <div className="sh-footer">
          Press <kbd className="sh-kbd sh-kbd-sm">Shift+?</kbd> or <kbd className="sh-kbd sh-kbd-sm">Esc</kbd> to close
        </div>
      </div>
    </div>
  );
}
