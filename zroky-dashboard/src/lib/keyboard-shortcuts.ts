"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { isDashboardPrimaryPath } from "./dashboard-route-contract";
import { useDashboardStore } from "./store";

interface ShortcutConfig {
  key: string;
  ctrl?: boolean;
  alt?: boolean;
  shift?: boolean;
  description: string;
  action: () => void;
}

export const DASHBOARD_KEYBOARD_ROUTES = {
  home: "/home",
  settings: "/settings/keys",
} as const;

export function useKeyboardShortcuts() {
  const router = useRouter();
  const { keyboardShortcutsEnabled, toggleSidebar, lastVisitedPage } = useDashboardStore();

  useEffect(() => {
    if (!keyboardShortcutsEnabled) return;

    const pushPrimaryRoute = (href: string) => {
      if (isDashboardPrimaryPath(href)) {
        router.push(href);
      }
    };

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
        key: "b",
        ctrl: true,
        description: "Toggle sidebar",
        action: toggleSidebar,
      },
      {
        key: "a",
        ctrl: true,
        description: "Go to Command Center",
        action: () => pushPrimaryRoute(DASHBOARD_KEYBOARD_ROUTES.home),
      },
      {
        key: "h",
        ctrl: true,
        description: "Open Command Center",
        action: () => pushPrimaryRoute(DASHBOARD_KEYBOARD_ROUTES.home),
      },
      {
        key: "s",
        ctrl: true,
        description: "Go to Settings",
        action: () => pushPrimaryRoute(DASHBOARD_KEYBOARD_ROUTES.settings),
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
  { keys: ["Ctrl", "K"], description: "Open command palette" },
  { keys: ["Ctrl", "B"], description: "Toggle sidebar" },
  { keys: ["Ctrl", "A"], description: "Go to Command Center" },
  { keys: ["Ctrl", "H"], description: "Open Command Center" },
  { keys: ["Ctrl", "S"], description: "Go to Settings" },
  { keys: ["Ctrl", "Shift", "R"], description: "Refresh data" },
  { keys: ["Shift", "?"], description: "Show this help" },
  { keys: ["Esc"], description: "Close modals / go back" },
];
