import { describe, expect, it } from "vitest";

import { CONFIGURABLE_CONNECTOR_IDS, connectorSetupProfile } from "@/lib/connector-setup-profile";

describe("connector setup profiles", () => {
  it("only marks real OAuth entry points as one click", () => {
    expect(connectorSetupProfile("github").oneClick).toBe(true);
    expect(connectorSetupProfile("slack").oneClick).toBe(true);
    expect(connectorSetupProfile("zoho_crm").oneClick).toBe(true);
    expect(connectorSetupProfile("jira_issue").oneClick).toBe(true);
    expect(connectorSetupProfile("stripe_refund").oneClick).toBe(false);
  });

  it("keeps unsupported native and duplicate template entries out of the configurable catalog", () => {
    expect(CONFIGURABLE_CONNECTOR_IDS.has("intercom")).toBe(false);
    expect(CONFIGURABLE_CONNECTOR_IDS.has("freshdesk_ticket")).toBe(false);
    expect(CONFIGURABLE_CONNECTOR_IDS.has("quickbooks_ledger")).toBe(false);
    expect(CONFIGURABLE_CONNECTOR_IDS.has("ledger_template")).toBe(false);
    expect(CONFIGURABLE_CONNECTOR_IDS.has("customer_template")).toBe(false);
    expect(CONFIGURABLE_CONNECTOR_IDS.has("generic_finance")).toBe(false);
  });

  it("describes the actual credential required by manual native connectors", () => {
    expect(connectorSetupProfile("stripe_refund").requirement).toMatch(/restricted Stripe secret key/i);
    expect(connectorSetupProfile("razorpay_refund").requirement).toMatch(/key ID and key secret/i);
    expect(connectorSetupProfile("postgres_read").requirement).toMatch(/read-only database URL/i);
  });
});
