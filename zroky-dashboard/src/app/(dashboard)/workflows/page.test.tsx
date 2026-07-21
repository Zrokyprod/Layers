import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import WorkflowsPage from "./page";

const api = vi.hoisted(() => ({
  publishAssurancePack: vi.fn(),
  validateAssurancePack: vi.fn(),
}));

vi.mock("@/lib/api", () => api);

describe("WorkflowsPage", () => {
  beforeEach(() => {
    api.publishAssurancePack.mockReset();
    api.validateAssurancePack.mockReset();
    api.validateAssurancePack.mockResolvedValue({
      valid: true,
      schema_version: "zroky.workflow_assurance_pack.v1",
      workflow_key: "refund_resolution",
      version: "1.0.0",
    });
    api.publishAssurancePack.mockResolvedValue({
      id: "pack_1",
      project_id: "proj_1",
      environment: "production",
      workflow_key: "refund_resolution",
      version: "1.0.0",
      pack_digest: "sha256:abc",
      status: "active",
      pack: {},
      created_at: "2026-07-21T00:00:00Z",
    });
  });

  it("drafts and validates a workflow assurance pack", async () => {
    render(<WorkflowsPage />);

    fireEvent.click(screen.getByRole("button", { name: /Validate/ }));

    await waitFor(() => expect(api.validateAssurancePack).toHaveBeenCalledTimes(1));
    expect(screen.getByText("refund_resolution@1.0.0 is valid.")).toBeInTheDocument();
  });

  it("validates before publishing an immutable pack", async () => {
    render(<WorkflowsPage />);

    fireEvent.click(screen.getByRole("button", { name: /Publish/ }));

    await waitFor(() => expect(api.publishAssurancePack).toHaveBeenCalledTimes(1));
    expect(api.validateAssurancePack).toHaveBeenCalledTimes(1);
    expect(api.publishAssurancePack).toHaveBeenCalledWith(expect.objectContaining({ workflow_key: "refund_resolution" }), "production");
    expect(screen.getByText("refund_resolution@1.0.0 published to production.")).toBeInTheDocument();
  });

  it("blocks invalid JSON locally before API calls", async () => {
    render(<WorkflowsPage />);

    fireEvent.change(screen.getByLabelText("Assurance Pack JSON"), { target: { value: "{" } });
    fireEvent.click(screen.getByRole("button", { name: /Validate/ }));

    await waitFor(() => {
      expect(screen.getByLabelText("Workflow API result").textContent).toMatch(
        /JSON|Expected property name|Unexpected end/,
      );
    });
    expect(api.validateAssurancePack).not.toHaveBeenCalled();
  });
});
