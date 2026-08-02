import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import WorkflowsPage from "./page";

const api = vi.hoisted(() => ({
  listAssurancePacks: vi.fn(),
  publishAssurancePack: vi.fn(),
  validateAssurancePack: vi.fn(),
}));

vi.mock("@/lib/api", () => api);

describe("WorkflowsPage", () => {
  beforeEach(() => {
    api.listAssurancePacks.mockReset();
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
    });
    api.listAssurancePacks.mockResolvedValue([]);
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

  it("lists and selects only persisted workflow packs", async () => {
    api.listAssurancePacks.mockResolvedValue([
      {
        id: "pack_vendor",
        project_id: "proj_1",
        environment: "production",
        workflow_key: "vendor_payment",
        version: "1.2.0",
        pack_digest: "digest_vendor",
        status: "active",
        pack: {
          schema_version: "zroky.workflow_assurance_pack.v1",
          workflow_key: "vendor_payment",
          version: "1.2.0",
          intent_schema: { required: ["vendor_id"] },
          object_types: [{ key: "payment", schema: {} }],
          effects: [{ key: "payment_settled", object_type: "payment", predicate: "payment.status == 'posted'" }],
          source_bindings: [{ key: "payment_read", connector_capability: "stripe_payment.read", object_type: "payment", freshness_seconds: 300 }],
          recovery_playbooks: [],
        },
      },
    ]);
    render(<WorkflowsPage />);

    fireEvent.click(await screen.findByRole("button", { name: /vendor_payment/i }));

    expect(screen.getByRole("heading", { name: "vendor_payment" })).toBeInTheDocument();
    expect(screen.getAllByText("stripe_payment.read").length).toBeGreaterThan(0);
    expect((screen.getByLabelText("Assurance Pack JSON") as HTMLTextAreaElement).value).toContain('"workflow_key":"vendor_payment"');
  });

  it("does not invent workflow rows when no packs are published", async () => {
    render(<WorkflowsPage />);

    expect(await screen.findByText("No Assurance Packs published in production.")).toBeInTheDocument();
    expect(screen.queryByText("payroll_export")).not.toBeInTheDocument();
    expect(screen.queryByText("vendor_payment")).not.toBeInTheDocument();
  });
});
