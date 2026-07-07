import { describe, expect, it } from "vitest";

import type { ActionPackResponse } from "@/lib/api";
import { supportContractsFor } from "./pack-config";

function contract(contractKey: string, actionType = contractKey) {
  return {
    contract_key: contractKey,
    version: "1.0",
    contract_version: `${contractKey}/1.0`,
    action_type: actionType,
    operation_kind: "UPDATE",
    domain_family: "customer_operations",
    risk_class: "R2",
    connector_family: "crm_record",
    schema: {},
    verification_profile: {},
  };
}

function pack(contracts: ReturnType<typeof contract>[]): ActionPackResponse {
  return {
    id: "support-ops-v1",
    display_name: "Support operations",
    summary: "Guard support actions.",
    primary_runtime_path: "sdk",
    recommended_connectors: [],
    native_tool_families: [],
    quickstart_steps: [],
    dashboard_href: "/agents/setup",
    contract_templates: contracts,
  };
}

describe("agent setup pack config", () => {
  it("selects protected actions by exact contract identity, not substring markers", () => {
    const selected = supportContractsFor(
      pack([
        contract("support.ticket.close"),
        contract("support.ticket.internal_note"),
        contract("customer.refund.transfer"),
        contract("customer.refund.note"),
      ]),
      ["tickets", "refunds"],
    );

    expect(selected.map((item) => item.contract_version)).toEqual([
      "support.ticket.close/1.0",
      "customer.refund.transfer/1.0",
    ]);
  });
});
