import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import type { ActionContractResponse, OutcomeMismatchResponseView } from "@/lib/api";
import { CorrectiveActionComposer } from "./CorrectiveActionComposer";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: ReactNode }) => <a href={href}>{children}</a>,
}));

const responseCase = {
  id: "case_1",
  project_id: "proj_1",
  reconciliation_check_id: "check_1",
  action_intent_id: "action_original",
  action_receipt_id: "receipt_1",
  receipt_digest: "sha256:receipt",
  alert_id: "alert_1",
  status: "OPEN",
  resolution_code: null,
  resolution_note: null,
  remediation: {},
  evidence: {
    action_type: "refund",
    system_ref: "rf_123",
    claimed: { refund_id: "rf_123", amount_minor: 5000, currency: "USD" },
    actual: { refund_id: "rf_123", amount_minor: 0, currency: "USD" },
  },
  acknowledged_by_subject: null,
  acknowledged_at: null,
  resolved_by_subject: null,
  resolved_at: null,
  created_at: "2026-07-14T10:00:00Z",
  updated_at: "2026-07-14T10:00:00Z",
} satisfies OutcomeMismatchResponseView;

const contract = {
  id: "contract_1",
  project_id: "proj_1",
  contract_key: "customer.refund.transfer",
  version: "1.0",
  contract_version: "customer.refund.transfer/1.0",
  action_type: "refund",
  operation_kind: "TRANSFER",
  domain_family: "customer_operations",
  schema_digest: "sha256:schema",
  schema: {
    type: "object",
    properties: {
      resource: {
        type: "object",
        required: ["refund_id"],
        properties: { refund_id: { type: "string" } },
      },
      parameters: {
        type: "object",
        required: ["amount_minor", "currency"],
        properties: {
          amount_minor: { type: "integer" },
          currency: { type: "string" },
          reason: { type: "string" },
        },
      },
    },
  },
  risk_class: "R3",
  verification_profile: {},
  connector_family: "ledger_refund",
  status: "active",
  created_at: "2026-07-14T09:00:00Z",
} satisfies ActionContractResponse;

describe("CorrectiveActionComposer", () => {
  it("prefills contract fields from mismatch evidence and submits an immutable protected intent", async () => {
    const onSubmit = vi.fn();
    render(
      <CorrectiveActionComposer
        busy={false}
        canCreate
        contracts={[contract]}
        error={null}
        loading={false}
        onClose={vi.fn()}
        onSubmit={onSubmit}
        responseCase={responseCase}
      />,
    );

    await waitFor(() => expect((screen.getByLabelText(/Refund id/) as HTMLInputElement).value).toBe("rf_123"));
    expect((screen.getByLabelText(/Amount minor/) as HTMLInputElement).value).toBe("5000");
    expect((screen.getByLabelText(/Currency/) as HTMLInputElement).value).toBe("USD");

    fireEvent.click(screen.getByRole("button", { name: "Submit to policy" }));

    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      idempotencyKey: expect.stringContaining("outcome-correction:case_1:"),
      payload: expect.objectContaining({
        contract_version: "customer.refund.transfer/1.0",
        action_type: "refund",
        operation_kind: "TRANSFER",
        purpose: expect.objectContaining({ mismatch_response_id: "case_1" }),
        resource: { refund_id: "rf_123" },
        parameters: expect.objectContaining({ amount_minor: 5000, currency: "USD" }),
      }),
    }));
  });

  it("keeps viewers read-only", () => {
    render(
      <CorrectiveActionComposer
        busy={false}
        canCreate={false}
        contracts={[contract]}
        error={null}
        loading={false}
        onClose={vi.fn()}
        onSubmit={vi.fn()}
        responseCase={responseCase}
      />,
    );

    expect(screen.getByText("Viewer access is read-only. A project member can propose corrections.")).toBeInTheDocument();
    expect((screen.getByRole("button", { name: "Submit to policy" }) as HTMLButtonElement).disabled).toBe(true);
  });
});
