import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import PilotPage from "./page";

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

vi.mock("next/image", () => ({
  default: ({
    alt,
    ...props
  }: {
    alt: string;
    [key: string]: unknown;
  }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img alt={alt} {...props} />
  ),
}));

describe("PilotPage", () => {
  it("renders a design-partner handoff path with install proof and protected setup", () => {
    render(<PilotPage />);

    expect(screen.getByRole("heading", { name: "Start with one protected agent and end with proof." })).toBeInTheDocument();
    expect(screen.getByText("Paid-launch proof, not a generic demo.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Start protected setup" }).getAttribute("href")).toBe(
      "/signup?source=pilot&intent=protect-agent&plan=pro"
    );
    expect(screen.getByRole("link", { name: "Open dashboard runbook" }).getAttribute("href")).toBe(
      "/settings/keys?intent=protect-agent&source=pilot&plan=pro"
    );
    expect(screen.getByText("Pre-action stop")).toBeInTheDocument();
    expect(screen.getByText("System-of-record match")).toBeInTheDocument();
    expect(screen.getByText("Exportable evidence")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open key setup" }).getAttribute("href")).toBe(
      "/settings/keys?intent=protect-agent&source=pilot&plan=pro"
    );
    expect(screen.getByRole("link", { name: "Open connector setup" }).getAttribute("href")).toBe(
      "/settings/integrations#ledger-refund-connector"
    );
    expect(screen.getByRole("link", { name: "View test endpoints" }).getAttribute("href")).toBe(
      "#saved-connector-tests"
    );
    expect(screen.getByText(/--scenario refund/)).toBeInTheDocument();
    expect(screen.getByText(/--scenario customer-record/)).toBeInTheDocument();
    expect(screen.getByText(/\/v1\/integrations\/system-of-record\/ledger-refund\/test/)).toBeInTheDocument();
    expect(screen.getByText(/\/v1\/integrations\/system-of-record\/customer-record\/test/)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Configure connector" }).some((link) => link.getAttribute("href") === "/settings/integrations#customer-record-connector")).toBe(true);
    expect(screen.getByText("unsafe_action_stopped")).toBeInTheDocument();
    expect(screen.getByText("connector_configured")).toBeInTheDocument();
    expect(screen.getByText("connector_health_verified")).toBeInTheDocument();
    expect(screen.getByText("real_connector_ready")).toBeInTheDocument();
    expect(screen.getByText("saved_test_endpoint_used")).toBeInTheDocument();
    expect(screen.getByText("matched_outcome_shown")).toBeInTheDocument();
    expect(screen.getByText("evidence_hash_visible")).toBeInTheDocument();
    expect(screen.getByText("evidence_json_exported")).toBeInTheDocument();
    expect(screen.getByText("not_verified_when_missing")).toBeInTheDocument();
    expect(screen.getByText("secrets_redacted")).toBeInTheDocument();
    expect(screen.getByText("not_verified")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("bearer_token");
    expect(document.body.textContent).not.toContain("ledger-secret-token");
  });
});
