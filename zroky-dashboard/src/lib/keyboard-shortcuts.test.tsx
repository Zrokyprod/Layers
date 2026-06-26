import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  DASHBOARD_RETIRED_ROUTES,
  DASHBOARD_SUPPORT_ROUTES,
  isDashboardPrimaryPath,
} from "./dashboard-route-contract";
import {
  DASHBOARD_KEYBOARD_ROUTES,
  KEYBOARD_SHORTCUTS_HELP,
  useKeyboardShortcuts,
} from "./keyboard-shortcuts";

const routerState = vi.hoisted(() => ({
  push: vi.fn(),
}));

const storeState = vi.hoisted(() => ({
  keyboardShortcutsEnabled: true,
  lastVisitedPage: "/home",
  toggleSidebar: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: routerState.push,
  }),
}));

vi.mock("./store", () => ({
  useDashboardStore: () => storeState,
}));

function KeyboardShortcutHarness() {
  useKeyboardShortcuts();
  return null;
}

describe("useKeyboardShortcuts", () => {
  beforeEach(() => {
    routerState.push.mockClear();
    storeState.toggleSidebar.mockClear();
    storeState.keyboardShortcutsEnabled = true;
  });

  it("opens canonical primary settings instead of the settings redirect", () => {
    render(<KeyboardShortcutHarness />);

    fireEvent.keyDown(window, { key: "s", ctrlKey: true });

    expect(routerState.push).toHaveBeenCalledWith("/settings/keys");
  });

  it("does not keep the old failures shortcut wired to incidents", () => {
    render(<KeyboardShortcutHarness />);

    fireEvent.keyDown(window, { key: "i", ctrlKey: true });

    expect(routerState.push).not.toHaveBeenCalled();
  });

  it("keeps advertised shortcut destinations inside the primary route contract", () => {
    const shortcutRoutes: string[] = Object.values(DASHBOARD_KEYBOARD_ROUTES);
    const hiddenPrefixes: string[] = [...DASHBOARD_SUPPORT_ROUTES, ...DASHBOARD_RETIRED_ROUTES].map(
      (route) => route.href,
    );

    for (const href of shortcutRoutes) {
      expect(isDashboardPrimaryPath(href), href).toBe(true);
      expect(
        hiddenPrefixes.some((prefix) => href === prefix || href.startsWith(`${prefix}/`)),
        href,
      ).toBe(false);
    }

    expect(KEYBOARD_SHORTCUTS_HELP).not.toContainEqual(
      expect.objectContaining({ keys: ["Ctrl", "I"] }),
    );
    expect(KEYBOARD_SHORTCUTS_HELP).not.toContainEqual(
      expect.objectContaining({ description: "Go to Failures" }),
    );
  });

  it("does not route while the user is typing in a form field", () => {
    render(
      <>
        <KeyboardShortcutHarness />
        <input aria-label="Search input" />
      </>,
    );

    fireEvent.keyDown(screen.getByLabelText("Search input"), { key: "s", ctrlKey: true });

    expect(routerState.push).not.toHaveBeenCalled();
  });
});
