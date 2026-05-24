"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { useDashboardStore } from "./store";

interface ShortcutConfig {
  key: string;
  ctrl?: boolean;
  alt?: boolean;
  shift?: boolean;
  description: string;
  action: () => void;
}

export function useKeyboardShortcuts() {
  const router = useRouter();
  const { keyboardShortcutsEnabled, toggleSidebar, lastVisitedPage } = useDashboardStore();

  useEffect(() => {
    if (!keyboardShortcutsEnabled) return;

    const shortcuts: ShortcutConfig[] = [
      {
        key: "k",
        ctrl: true,
        description: "Open command palette / search",
        action: () => {
          // Dispatch custom event for command palette
          window.dispatchEvent(new CustomEvent("open-command-palette"));
        },
      },
      {
        key: "j",
        ctrl: true,
        description: "Open Ask Zroky",
        action: () => {
          window.dispatchEvent(new CustomEvent("open-ask-zroky"));
        },
      },
      {
        key: "b",
        ctrl: true,
        description: "Toggle sidebar",
        action: toggleSidebar,
      },
      {
        key: "h",
        ctrl: true,
        description: "Go to home",
        action: () => router.push("/home"),
      },
      {
        key: "c",
        ctrl: true,
        description: "Go to calls",
        action: () => router.push("/calls"),
      },
      {
        key: "i",
        ctrl: true,
        description: "Go to anomalies",
        action: () => router.push("/anomalies"),
      },
      {
        key: "f",
        ctrl: true,
        description: "Go to fix queue",
        action: () => router.push("/recommendations"),
      },
      {
        key: "s",
        ctrl: true,
        description: "Go to settings",
        action: () => router.push("/settings"),
      },
      {
        key: "r",
        ctrl: true,
        shift: true,
        description: "Refresh data",
        action: () => {
          window.dispatchEvent(new CustomEvent("refresh-dashboard-data"));
        },
      },
      {
        key: "?",
        shift: true,
        description: "Show keyboard shortcuts help",
        action: () => {
          window.dispatchEvent(new CustomEvent("show-shortcuts-help"));
        },
      },
      {
        key: "Escape",
        description: "Close modals / go back",
        action: () => {
          window.dispatchEvent(new CustomEvent("escape-pressed"));
        },
      },
    ];

    const handleKeyDown = (event: KeyboardEvent) => {
      // Don't trigger shortcuts when typing in input fields
      if (
        event.target instanceof HTMLInputElement ||
        event.target instanceof HTMLTextAreaElement ||
        event.target instanceof HTMLSelectElement
      ) {
        return;
      }

      const shortcut = shortcuts.find(
        (s) =>
          s.key.toLowerCase() === event.key.toLowerCase() &&
          !!s.ctrl === event.ctrlKey &&
          !!s.alt === event.altKey &&
          !!s.shift === event.shiftKey
      );

      if (shortcut) {
        event.preventDefault();
        shortcut.action();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [keyboardShortcutsEnabled, router, toggleSidebar, lastVisitedPage]);

  return { shortcutsEnabled: keyboardShortcutsEnabled };
}

export const KEYBOARD_SHORTCUTS_HELP = [
  { keys: ["Ctrl", "J"], description: "Ask Zroky (natural-language Q&A)" },
  { keys: ["Ctrl", "K"], description: "Open command palette" },
  { keys: ["Ctrl", "B"], description: "Toggle sidebar" },
  { keys: ["Ctrl", "H"], description: "Go to home" },
  { keys: ["Ctrl", "C"], description: "Go to calls" },
  { keys: ["Ctrl", "I"], description: "Go to anomalies" },
  { keys: ["Ctrl", "F"], description: "Go to fix queue" },
  { keys: ["Ctrl", "S"], description: "Go to settings" },
  { keys: ["Ctrl", "Shift", "R"], description: "Refresh data" },
  { keys: ["Shift", "?"], description: "Show this help" },
  { keys: ["Esc"], description: "Close modals / go back" },
];
