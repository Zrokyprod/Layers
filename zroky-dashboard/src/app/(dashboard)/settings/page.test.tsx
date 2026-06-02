import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SettingsPage from "./page";

const api = vi.hoisted(() => ({
  disconnectGithubRepoConnection: vi.fn(),
  eraseRetentionData: vi.fn(),
  exportProjectData: vi.fn(),
  getGithubConnectionStatus: vi.fn(),
  getNotifications: vi.fn(),
  getPiiPolicy: vi.fn(),
  getProjectSettings: vi.fn(),
  getRetention: vi.fn(),
  testPiiDetector: vi.fn(),
  updateNotifications: vi.fn(),
  updatePiiPolicy: vi.fn(),
  updateRetention: vi.fn(),
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: {
    href: string;
    children: ReactNode;
    [key: string]: unknown;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    ...api,
  };
});

describe("SettingsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows a retryable error panel when project settings cannot load", async () => {
    api.getProjectSettings.mockRejectedValue(new Error("Backend API is unavailable."));

    render(<SettingsPage />);

    expect(await screen.findByText("Settings could not load")).toBeInTheDocument();
    expect(screen.getByText("Backend API is unavailable.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save retention" })).not.toBeInTheDocument();
  });
});
