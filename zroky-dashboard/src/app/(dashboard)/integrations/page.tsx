"use client";

import type { FormEvent } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ClipboardCheck,
  Copy,
  Database,
  RefreshCw,
  Save,
  Search,
} from "lucide-react";

import { DashboardButton, DashboardButtonLink } from "@/components/dashboard-button";
import {
  DashboardVerdictHero,
  DashboardWorkspace,
} from "@/components/dashboard-scaffold";
import { StatusPill } from "@/components/status-pill";
import {
  getCustomerRecordConnectorStatus,
  getGenericRestConnectorStatus,
  getGithubConnectionStatus,
  getHubSpotCrmConnectorStatus,
  getJiraIssueConnectorStatus,
  getLedgerRefundConnectorStatus,
  getNetSuiteFinanceConnectorStatus,
  getPostgresReadConnectorStatus,
  getRazorpayRefundConnectorStatus,
  getSalesforceCrmConnectorStatus,
  getShopifyConnectorStatus,
  getZendeskTicketConnectorStatus,
  getZohoCrmConnectorStatus,
  getSlackInstallStatus,
  getStripePaymentConnectorStatus,
  getStripeRefundConnectorStatus,
  getToolRegistry,
  listOutcomeReconciliations,
  saveGenericRestConnectorConfig,
  saveHubSpotCrmConnectorConfig,
  saveJiraIssueConnectorConfig,
  saveNetSuiteFinanceConnectorConfig,
  saveRazorpayRefundConnectorConfig,
  saveSalesforceCrmConnectorConfig,
  saveShopifyConnectorConfig,
  saveStripePaymentConnectorConfig,
  saveStripeRefundConnectorConfig,
  saveZendeskTicketConnectorConfig,
  saveZohoCrmConnectorConfig,
  startJiraIssueOAuth,
  startZohoCrmOAuth,
  testGenericRestConnector,
  testHubSpotCrmConnector,
  testJiraIssueConnector,
  testNetSuiteFinanceConnector,
  testRazorpayRefundConnector,
  testSalesforceCrmConnector,
  testShopifyConnector,
  testStripePaymentConnector,
  testStripeRefundConnector,
  testZendeskTicketConnector,
  testZohoCrmConnector,
  type CustomerRecordConnectorStatusResponse,
  type GenericRestConnectorStatusResponse,
  type HubSpotCrmConnectorStatusResponse,
  type JiraIssueConnectorStatusResponse,
  type LedgerRefundConnectorStatusResponse,
  type NetSuiteFinanceConnectorStatusResponse,
  type OutcomeReconciliationView,
  type PostgresReadConnectorStatusResponse,
  type RazorpayRefundConnectorStatusResponse,
  type SalesforceCrmConnectorStatusResponse,
  type ShopifyConnectorStatusResponse,
  type StripePaymentConnectorStatusResponse,
  type StripeRefundConnectorStatusResponse,
  type ToolRegistryResponse,
  type ZendeskTicketConnectorStatusResponse,
  type ZohoCrmConnectorStatusResponse,
} from "@/lib/api";
import {
  buildConnectorInventory,
  connectorStateLabel,
  connectorUpdatedLabel,
  type ConnectorCategoryGroup,
  type ConnectorCoverageRow,
  type ConnectorInventory,
  type ConnectorInventoryId,
  type ConnectorInventoryRow,
} from "@/lib/connector-inventory";
import { ConnectorLogo } from "@/lib/connector-logo";
import { externalNavigator } from "@/lib/external-navigation";
import { compactJson, formatCount, humanize } from "@/lib/format";
import type {
  GithubConnectionStatusResponse,
  SlackInstallStatusResponse,
} from "@/lib/types";

type ConnectorsOverviewState = {
  github: GithubConnectionStatusResponse | null;
  slack: SlackInstallStatusResponse | null;
  ledger: LedgerRefundConnectorStatusResponse | null;
  stripe: StripeRefundConnectorStatusResponse | null;
  stripePayment: StripePaymentConnectorStatusResponse | null;
  razorpay: RazorpayRefundConnectorStatusResponse | null;
  customer: CustomerRecordConnectorStatusResponse | null;
  generic: GenericRestConnectorStatusResponse | null;
  hubspot: HubSpotCrmConnectorStatusResponse | null;
  salesforce: SalesforceCrmConnectorStatusResponse | null;
  zendesk: ZendeskTicketConnectorStatusResponse | null;
  jira: JiraIssueConnectorStatusResponse | null;
  netsuite: NetSuiteFinanceConnectorStatusResponse | null;
  shopify: ShopifyConnectorStatusResponse | null;
  zoho: ZohoCrmConnectorStatusResponse | null;
  postgres: PostgresReadConnectorStatusResponse | null;
  checks: OutcomeReconciliationView[];
  registry: ToolRegistryResponse | null;
};

type GenericRestFormState = {
  baseUrl: string;
  pathTemplate: string;
  recordPath: string;
  bearerToken: string;
  recordRef: string;
  actionType: string;
  claimedJson: string;
  matchFieldsText: string;
};

type StripeRefundFormState = {
  bearerToken: string;
  refundId: string;
  claimedJson: string;
  matchFieldsText: string;
};

type StripePaymentFormState = {
  bearerToken: string;
  paymentId: string;
  claimedJson: string;
  matchFieldsText: string;
};

type RazorpayRefundFormState = {
  keyId: string;
  keySecret: string;
  refundId: string;
  claimedJson: string;
  matchFieldsText: string;
};

type HubSpotFormState = {
  bearerToken: string;
  recordRef: string;
  idProperty: string;
  propertiesText: string;
  claimedJson: string;
  matchFieldsText: string;
};

type SalesforceFormState = {
  baseUrl: string;
  bearerToken: string;
  objectType: string;
  recordRef: string;
  fieldsText: string;
  claimedJson: string;
  matchFieldsText: string;
};

type ZohoFormState = {
  baseUrl: string;
  bearerToken: string;
  moduleName: string;
  recordRef: string;
  fieldsText: string;
  claimedJson: string;
  matchFieldsText: string;
};

type ZendeskFormState = {
  baseUrl: string;
  authUsername: string;
  bearerToken: string;
  recordRef: string;
  claimedJson: string;
  matchFieldsText: string;
};

type JiraFormState = {
  baseUrl: string;
  authUsername: string;
  bearerToken: string;
  recordRef: string;
  claimedJson: string;
  matchFieldsText: string;
};

type NetSuiteFormState = {
  baseUrl: string;
  bearerToken: string;
  recordType: string;
  recordRef: string;
  claimedJson: string;
  matchFieldsText: string;
};

type ShopifyFormState = {
  baseUrl: string;
  bearerToken: string;
  recordRef: string;
  claimedJson: string;
  matchFieldsText: string;
};

const initialOverview: ConnectorsOverviewState = {
  github: null,
  slack: null,
  ledger: null,
  stripe: null,
  stripePayment: null,
  razorpay: null,
  customer: null,
  generic: null,
  hubspot: null,
  salesforce: null,
  zendesk: null,
  jira: null,
  netsuite: null,
  shopify: null,
  zoho: null,
  postgres: null,
  checks: [],
  registry: null,
};

const defaultGenericRestForm: GenericRestFormState = {
  baseUrl: "",
  pathTemplate: "/records/{record_ref}",
  recordPath: "data",
  bearerToken: "",
  recordRef: "record_1001",
  actionType: "internal_api_mutation",
  claimedJson: JSON.stringify(
    {
      record_ref: "record_1001",
      status: "approved",
    },
    null,
    2,
  ),
  matchFieldsText: "status",
};

const defaultStripeRefundForm: StripeRefundFormState = {
  bearerToken: "",
  refundId: "re_123",
  claimedJson: JSON.stringify(
    {
      refund_id: "re_123",
      amount_minor: 4250,
      amount_major: "42.5",
      currency: "USD",
      status: "succeeded",
    },
    null,
    2,
  ),
  matchFieldsText: "refund_id,amount_minor,currency,status",
};

const defaultStripePaymentForm: StripePaymentFormState = {
  bearerToken: "",
  paymentId: "pi_123",
  claimedJson: JSON.stringify(
    {
      payment_id: "pi_123",
      amount_minor: 4250,
      amount_major: "42.5",
      currency: "USD",
      status: "succeeded",
    },
    null,
    2,
  ),
  matchFieldsText: "payment_id,amount_minor,currency,status",
};

const defaultRazorpayRefundForm: RazorpayRefundFormState = {
  keyId: "rzp_live_xxxxx",
  keySecret: "",
  refundId: "rfnd_123",
  claimedJson: JSON.stringify(
    {
      refund_id: "rfnd_123",
      amount_minor: 4250,
      amount_major: "42.5",
      currency: "INR",
      status: "processed",
    },
    null,
    2,
  ),
  matchFieldsText: "refund_id,amount_minor,currency,status",
};

const defaultHubSpotForm: HubSpotFormState = {
  bearerToken: "",
  recordRef: "owner@example.com",
  idProperty: "email",
  propertiesText: "email,firstname,lastname,lifecyclestage,hs_lead_status,hs_object_id",
  claimedJson: JSON.stringify(
    {
      email: "owner@example.com",
      lifecyclestage: "customer",
    },
    null,
    2,
  ),
  matchFieldsText: "email,lifecyclestage",
};

const defaultSalesforceForm: SalesforceFormState = {
  baseUrl: "https://example.my.salesforce.com",
  bearerToken: "",
  objectType: "Account",
  recordRef: "001000000000000AAA",
  fieldsText: "Id,Name,Status,StageName,Amount",
  claimedJson: JSON.stringify(
    {
      salesforce_id: "001000000000000AAA",
      object_type: "Account",
      Name: "Acme",
    },
    null,
    2,
  ),
  matchFieldsText: "salesforce_id,Name",
};

const defaultZohoForm: ZohoFormState = {
  baseUrl: "https://www.zohoapis.com",
  bearerToken: "",
  moduleName: "Contacts",
  recordRef: "1234567890000000001",
  fieldsText: "id,Full_Name,Email,Phone,Company,Stage,Amount,Lead_Status,Owner,Modified_Time",
  claimedJson: JSON.stringify(
    {
      zoho_record_id: "1234567890000000001",
      module_name: "Contacts",
      Email: "owner@example.com",
    },
    null,
    2,
  ),
  matchFieldsText: "zoho_record_id,Email",
};

const defaultZendeskForm: ZendeskFormState = {
  baseUrl: "https://example.zendesk.com",
  authUsername: "",
  bearerToken: "",
  recordRef: "12345",
  claimedJson: JSON.stringify(
    {
      ticket_id: "12345",
      status: "solved",
    },
    null,
    2,
  ),
  matchFieldsText: "ticket_id,status",
};

const defaultJiraForm: JiraFormState = {
  baseUrl: "https://example.atlassian.net",
  authUsername: "",
  bearerToken: "",
  recordRef: "JSM-123",
  claimedJson: JSON.stringify(
    {
      jira_issue_key: "JSM-123",
      status: "Done",
    },
    null,
    2,
  ),
  matchFieldsText: "jira_issue_key,status",
};

const defaultNetSuiteForm: NetSuiteFormState = {
  baseUrl: "https://example.suitetalk.api.netsuite.com",
  bearerToken: "",
  recordType: "vendorBill",
  recordRef: "12345",
  claimedJson: JSON.stringify(
    {
      netsuite_record_id: "12345",
      record_type: "vendorBill",
      tran_id: "VB1001",
      amount_minor: 125000,
      amount_major: "1250",
      currency: "USD",
      status: "approved",
    },
    null,
    2,
  ),
  matchFieldsText: "netsuite_record_id,record_type,tran_id,amount_minor,currency,status",
};

const defaultShopifyForm: ShopifyFormState = {
  baseUrl: "https://example.myshopify.com",
  bearerToken: "",
  recordRef: "1001",
  claimedJson: JSON.stringify(
    {
      order_id: "1001",
      amount_major: "42.5",
      currency: "USD",
      financial_status: "paid",
      fulfillment_status: "fulfilled",
    },
    null,
    2,
  ),
  matchFieldsText: "order_id,amount_major,currency,financial_status",
};

const ADVANCED_CONNECTOR_IDS = new Set<ConnectorInventoryId>([
  "generic_rest",
  "ledger_template",
  "customer_template",
  "postgres_read",
]);

const SETUP_PANEL_CONNECTOR_IDS = new Set<ConnectorInventoryId>([
  "generic_rest",
  "stripe_refund",
  "stripe_payment",
  "razorpay_refund",
  "shopify_admin",
  "hubspot_crm",
  "salesforce_crm",
  "zoho_crm",
  "zendesk_ticket",
  "jira_issue",
  "netsuite_finance",
]);

function firstSelectedId(inventory: ConnectorInventory): ConnectorInventoryId | null {
  const primaryProofRows = inventory.categoryGroups
    .flatMap((group) => group.rows)
    .filter((row) => row.kind === "proof" && !ADVANCED_CONNECTOR_IDS.has(row.id));

  return (
    primaryProofRows.find((row) => row.state === "failing" || row.state === "mismatched")?.id
    ?? inventory.rows.find((row) => row.state === "failing" || row.state === "mismatched")?.id
    ?? primaryProofRows.find((row) => row.state === "not_tested")?.id
    ?? primaryProofRows.find((row) => row.state === "missing")?.id
    ?? primaryProofRows[0]?.id
    ?? inventory.rows[0]?.id
    ?? null
  );
}

function initialConnectorFromUrl(): ConnectorInventoryId | null {
  if (typeof window === "undefined") return null;
  const value = new URLSearchParams(window.location.search).get("connector");
  return value as ConnectorInventoryId | null;
}

function parseClaimedJson(value: string): Record<string, unknown> {
  const parsed = JSON.parse(value) as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Claimed JSON must be an object.");
  }
  return parsed as Record<string, unknown>;
}

function matchFieldsFromText(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function hubSpotQueryFromForm(form: HubSpotFormState): Record<string, string> {
  const query: Record<string, string> = {};
  if (form.propertiesText.trim()) {
    query.properties = form.propertiesText
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean)
      .join(",");
  }
  if (form.idProperty.trim()) {
    query.idProperty = form.idProperty.trim();
  }
  return query;
}

function salesforceQueryFromForm(form: SalesforceFormState): Record<string, string> {
  const query: Record<string, string> = {};
  if (form.fieldsText.trim()) {
    query.fields = form.fieldsText
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean)
      .join(",");
  }
  return query;
}

function zohoQueryFromForm(form: ZohoFormState): Record<string, string> {
  const query: Record<string, string> = {};
  if (form.fieldsText.trim()) {
    query.fields = form.fieldsText
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean)
      .join(",");
  }
  return query;
}

function safeClaimedJson(value: string, recordRef: string): Record<string, unknown> {
  try {
    return parseClaimedJson(value);
  } catch {
    return {
      record_ref: recordRef,
      status: "approved",
    };
  }
}

function buildBridgeCurl(form: GenericRestFormState) {
  const payload = {
    connector: "generic_rest",
    record_ref: form.recordRef,
    action_type: form.actionType || null,
    claimed: safeClaimedJson(form.claimedJson, form.recordRef),
    match_fields: matchFieldsFromText(form.matchFieldsText),
  };

  return [
    "curl -X POST https://api.zroky.local/v1/outcomes/reconciliation/saved \\",
    "  -H 'content-type: application/json' \\",
    "  -H 'x-api-key: $ZROKY_API_KEY' \\",
    `  -d '${JSON.stringify(payload, null, 2).replace(/'/g, "'\\''")}'`,
  ].join("\n");
}

function statusValue(row: ConnectorInventoryRow | ConnectorCoverageRow) {
  if ("state" in row) return row.state;
  return row.status;
}

function connectorSearchText(row: ConnectorInventoryRow): string {
  return [
    row.title,
    row.category,
    row.description,
    row.transport,
    row.templateKind,
    row.statusLabel,
    row.detail,
    row.metadata.connectorType,
    row.metadata.maskedEndpoint,
    ...row.supportedActionTypes,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function filterCategoryGroups(
  groups: ConnectorCategoryGroup[],
  query: string,
): ConnectorCategoryGroup[] {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return groups;
  return groups
    .map((group) => ({
      ...group,
      rows: group.rows.filter((row) => connectorSearchText(row).includes(normalized)),
    }))
    .filter((group) => group.rows.length > 0);
}

function connectorPrimaryCtaLabel(row: ConnectorInventoryRow): string {
  if (row.kind === "support") return row.ctaLabel;
  if (row.id === "generic_rest") return "Set up custom REST";
  if (row.id === "postgres_read") return "Set up database";
  if (row.id === "ledger_template" || row.id === "customer_template") return "Set up template";
  return `Connect ${connectorSystemLabel(row)}`;
}

function connectorSystemLabel(row: ConnectorInventoryRow): string {
  if (row.id === "generic_rest") return "Custom REST API";
  if (row.id === "postgres_read") return "SQL database";
  if (row.id === "stripe_refund" || row.id === "stripe_payment") return "Stripe";
  if (row.id === "razorpay_refund") return "Razorpay";
  return row.title
    .replace(/\s+verifier$/i, "")
    .replace(/\s+template$/i, "");
}

function connectorCardMeta(row: ConnectorInventoryRow): string {
  if (row.kind === "support") return "Workflow";
  if (row.transport === "sql_read") return "SQL read";
  if (row.id === "generic_rest") return "Custom REST";
  if (row.id === "stripe_refund" || row.id === "razorpay_refund") return "Refunds";
  if (row.id === "stripe_payment") return "Payments";
  if (row.id === "ledger_template" || row.id === "customer_template") return "Template";
  return "Read-only verifier";
}

function connectorInspectorEyebrow(row: ConnectorInventoryRow): string {
  if (row.kind === "support") return "Workflow";
  if (row.id === "generic_rest") return "Custom connector";
  if (row.id === "postgres_read") return "Database connector";
  return "Native connector";
}

function connectorInspectorCopy(row: ConnectorInventoryRow): string {
  const system = connectorSystemLabel(row);
  if (row.kind === "support") return "Approvals and alerts for protected actions.";
  if (row.id === "generic_rest") return "Verify any read-only API.";
  if (row.id === "postgres_read") return "Verify records from a read-only database.";
  if (row.id === "stripe_refund" || row.id === "stripe_payment") return "Verify refunds and payments from Stripe.";
  if (row.id === "razorpay_refund") return "Verify refunds from Razorpay.";
  if (["hubspot_crm", "salesforce_crm", "zoho_crm"].includes(row.id)) return `Verify CRM changes from ${system}.`;
  if (["zendesk_ticket", "freshdesk_ticket", "intercom", "jira_issue"].includes(row.id)) {
    return `Verify support actions from ${system}.`;
  }
  if (["netsuite_finance", "quickbooks_ledger", "generic_finance"].includes(row.id)) {
    return `Verify finance records from ${system}.`;
  }
  if (row.id === "shopify_admin") return "Verify commerce actions from Shopify.";
  return `Verify agent actions from ${system}.`;
}

type ConnectorDisplayCard = {
  ids: ConnectorInventoryId[];
  key: string;
  logoId: ConnectorInventoryId;
  meta: string;
  row: ConnectorInventoryRow;
  title: string;
};

function connectorDisplayCards(
  rows: ConnectorInventoryRow[],
  selectedId: ConnectorInventoryId | null,
  searchQuery: string,
): ConnectorDisplayCard[] {
  const cards: ConnectorDisplayCard[] = [];
  const handled = new Set<ConnectorInventoryId>();
  const normalizedQuery = searchQuery.trim().toLowerCase();

  for (const row of rows) {
    if (handled.has(row.id)) continue;

    if (row.id === "stripe_refund" || row.id === "stripe_payment") {
      const stripeRows = rows.filter((candidate) => candidate.id === "stripe_refund" || candidate.id === "stripe_payment");
      for (const stripeRow of stripeRows) handled.add(stripeRow.id);

      const selectedStripeRow = stripeRows.find((stripeRow) => stripeRow.id === selectedId);
      const preferredStripeRow =
        selectedStripeRow
        ?? (normalizedQuery.includes("payment") ? stripeRows.find((stripeRow) => stripeRow.id === "stripe_payment") : null)
        ?? stripeRows.find((stripeRow) => stripeRow.id === "stripe_refund")
        ?? stripeRows[0];
      const hasRefunds = stripeRows.some((stripeRow) => stripeRow.id === "stripe_refund");
      const hasPayments = stripeRows.some((stripeRow) => stripeRow.id === "stripe_payment");

      cards.push({
        ids: stripeRows.map((stripeRow) => stripeRow.id),
        key: "stripe",
        logoId: "stripe_refund",
        meta: hasRefunds && hasPayments ? "Refunds + payments" : hasPayments ? "Payments" : "Refunds",
        row: preferredStripeRow,
        title: "Stripe",
      });
      continue;
    }

    handled.add(row.id);
    cards.push({
      ids: [row.id],
      key: row.id,
      logoId: row.id,
      meta: connectorCardMeta(row),
      row,
      title: connectorSystemLabel(row),
    });
  }

  return cards;
}

function connectorActionSummary(row: ConnectorInventoryRow): string {
  if (row.supportedActionTypes.includes("*")) return "custom agent actions";
  const actions = row.supportedActionTypes.slice(0, 3).map((item) => humanize(item));
  if (actions.length === 0) return row.kind === "support" ? "workflow events" : "agent actions";
  return `${actions.join(", ")}${row.supportedActionTypes.length > actions.length ? ", and more" : ""}`;
}

function connectorPreflightSummary(row: ConnectorInventoryRow) {
  if (row.state === "ready") {
    return {
      label: "Matched",
      title: "Ready",
      detail: "Proof checks can use this connector.",
      tone: "success" as const,
    };
  }
  if (row.state === "mismatched") {
    return {
      label: "Mismatched",
      title: "Mismatch",
      detail: "Last preflight did not match.",
      tone: "danger" as const,
    };
  }
  if (row.state === "failing") {
    return {
      label: "Blocked",
      title: "Needs fix",
      detail: "Connection check failed.",
      tone: "danger" as const,
    };
  }
  if (row.state === "not_tested") {
    return {
      label: "Needs check",
      title: "Connected",
      detail: "Run preflight once.",
      tone: "warning" as const,
    };
  }
  return {
    label: "Not configured",
    title: "Not connected",
    detail: "Connect read-only access to start.",
    tone: "neutral" as const,
  };
}

function Fact({
  label,
  value,
}: {
  label: string;
  value: string | number | boolean | null | undefined;
}) {
  if (value == null || value === "") return null;
  return (
    <div className="connector-fact">
      <span>{label}</span>
      <strong>{typeof value === "boolean" ? (value ? "Yes" : "No") : value}</strong>
    </div>
  );
}

function CoverageMap({ rows }: { rows: ConnectorCoverageRow[] }) {
  return (
    <section className="panel connectors-coverage-panel connectors-coverage-panel-secondary" aria-label="Verification coverage audit">
      <details className="connectors-coverage-details">
        <summary>
          <span>
            <span className="dashboard-eyebrow">Coverage audit</span>
            <strong>Which agent actions can Zroky verify?</strong>
          </span>
          <small>{rows.length > 0 ? `${formatCount(rows.length)} observed action types` : "No observed action types yet"}</small>
        </summary>

        <div className="connectors-coverage-body">
          <div className="connectors-section-head">
            <div>
              <h2>Verification coverage audit</h2>
              <p>
                Advanced view generated from observed action types and the tool registry. Actions without a healthy
                verifier resolve to not_verified until a REST, SQL, or bridge verifier is configured.
              </p>
            </div>
            <DashboardButtonLink href="/outcomes" variant="soft" size="sm">
              Open Outcomes
            </DashboardButtonLink>
          </div>

          {rows.length > 0 ? (
            <div className="connectors-coverage-grid">
              {rows.map((row) => (
                <article className="connectors-coverage-row" data-tone={row.tone} key={row.actionType}>
                  <div>
                    <strong>{row.actionType}</strong>
                    <span>{row.detail}</span>
                  </div>
                  <StatusPill value={row.status} label={row.label} tone={row.tone} />
                </article>
              ))}
            </div>
          ) : (
            <div className="connectors-empty-state">
              <strong>No action types observed yet</strong>
              <span>Run a protected action or configure an agent catalog to see verifier coverage.</span>
            </div>
          )}
        </div>
      </details>
    </section>
  );
}

function ConnectorInventoryList({
  groups,
  searchQuery,
  selectedId,
  onSearchQueryChange,
  onSelect,
}: {
  groups: ConnectorCategoryGroup[];
  searchQuery: string;
  selectedId: ConnectorInventoryId | null;
  onSearchQueryChange: (value: string) => void;
  onSelect: (id: ConnectorInventoryId) => void;
}) {
  return (
    <section className="panel connectors-inventory-panel" aria-label="Connector inventory">
      <div className="connectors-section-head">
        <div>
          <span className="dashboard-eyebrow">Connectors</span>
          <h2>Available systems</h2>
          <p>Select a source system, connect read-only access, and use it for proof.</p>
        </div>
      </div>

      <label className="connector-search-field">
        <Search aria-hidden="true" />
        <span className="sr-only">Search connectors</span>
        <input
          aria-label="Search connectors"
          placeholder="Search connectors, systems, action types..."
          type="search"
          value={searchQuery}
          onChange={(event) => onSearchQueryChange(event.target.value)}
        />
      </label>

      <div className="connector-category-list">
        {groups.map((group) => {
          const cards = connectorDisplayCards(group.rows, selectedId, searchQuery);
          return (
            <section className="connector-category-group" key={group.category} aria-label={group.label}>
              <div className="connector-category-head">
                <strong>{group.label}</strong>
                <span>{cards.length} connector{cards.length === 1 ? "" : "s"}</span>
              </div>
              <div className="connector-row-list">
                {cards.map((card) => (
                  <button
                    type="button"
                    className="connector-inventory-row"
                    data-selected={selectedId != null && card.ids.includes(selectedId)}
                    data-tone={card.row.tone}
                    key={card.key}
                    onClick={() => onSelect(card.row.id)}
                  >
                    <ConnectorLogo id={card.logoId} />
                    <span className="connector-row-main">
                      <strong>{card.title}</strong>
                      <small>{card.meta}</small>
                    </span>
                    <span className="connector-row-status">
                      <StatusPill value={statusValue(card.row)} label={card.row.statusLabel} tone={card.row.tone} />
                    </span>
                  </button>
                ))}
              </div>
            </section>
          );
        })}
      </div>

      {groups.length === 0 ? (
        <div className="connectors-empty-state">
          <strong>No connectors match this search</strong>
          <span>Try a system name, connector type, or action type such as refund, CRM, Jira, or SQL.</span>
        </div>
      ) : null}
    </section>
  );
}

function GenericRestSetupPanel({
  latestCheck,
  onStatusChange,
  status,
}: {
  latestCheck: OutcomeReconciliationView | null;
  onStatusChange: (status: GenericRestConnectorStatusResponse) => void;
  status: GenericRestConnectorStatusResponse | null;
}) {
  const [form, setForm] = useState<GenericRestFormState>(defaultGenericRestForm);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [copiedBridge, setCopiedBridge] = useState(false);

  useEffect(() => {
    if (!status) return;
    setForm((current) => ({
      ...current,
      baseUrl: status.base_url ?? current.baseUrl,
      pathTemplate: status.path_template ?? current.pathTemplate,
      recordPath: status.record_path ?? current.recordPath,
    }));
  }, [status]);

  const updateForm = (key: keyof GenericRestFormState, value: string) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const saveConfig = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const saved = await saveGenericRestConnectorConfig({
        base_url: form.baseUrl,
        path_template: form.pathTemplate,
        record_path: form.recordPath || null,
        bearer_token: form.bearerToken || null,
      });
      onStatusChange(saved);
      setMessage("REST verifier saved. Run preflight to make it evidence-ready.");
      setForm((current) => ({ ...current, bearerToken: "" }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save REST verifier.");
    } finally {
      setSaving(false);
    }
  };

  const runTest = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setTesting(true);
    setError(null);
    setMessage(null);
    try {
      const claimed = parseClaimedJson(form.claimedJson);
      const result = await testGenericRestConnector({
        record_ref: form.recordRef,
        claimed,
        action_type: form.actionType || null,
        system_ref: form.recordRef,
        match_fields: matchFieldsFromText(form.matchFieldsText),
      });
      onStatusChange(result.connector);
      setMessage(`REST verifier test recorded ${result.check.verdict}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run REST verifier test.");
    } finally {
      setTesting(false);
    }
  };

  const copyBridge = async () => {
    await navigator.clipboard?.writeText(buildBridgeCurl(form));
    setCopiedBridge(true);
    window.setTimeout(() => setCopiedBridge(false), 1500);
  };

  const connected = Boolean(status?.connected);
  const bridgeCurl = buildBridgeCurl(form);

  return (
    <section className="connectors-generic-panel connectors-rest-panel" aria-label="Generic REST verifier setup">
      <div className="connectors-section-head">
        <div>
          <span className="dashboard-eyebrow">REST / HTTP JSON verifier</span>
          <h2>Custom REST verifier setup</h2>
          <p>Use this for internal APIs, SaaS APIs, and systems where Zroky can read a JSON record by reference.</p>
        </div>
        <StatusPill
          value={status?.last_verdict ?? latestCheck?.verdict ?? "not_configured"}
          kind="proof"
          tone={connected ? "warning" : "neutral"}
        />
      </div>

      <div className="connectors-generic-layout connectors-rest-layout">
        <form className="connectors-generic-form connectors-rest-card connectors-rest-card-primary" onSubmit={saveConfig}>
          <div className="connectors-generic-form-head connectors-rest-card-head">
            <span className="connectors-rest-step">1</span>
            <div>
              <strong>Save read-only endpoint</strong>
              <span>Store a read-scoped source-of-record path. Secrets stay server-side.</span>
            </div>
          </div>
          <div className="connectors-generic-grid connectors-rest-field-grid">
            <label className="connectors-generic-wide">
              <span>Base URL</span>
              <input
                value={form.baseUrl}
                onChange={(event) => updateForm("baseUrl", event.target.value)}
                placeholder="https://api.company.com"
                required
              />
            </label>
            <label className="connectors-generic-wide">
              <span>Path template</span>
              <input
                value={form.pathTemplate}
                onChange={(event) => updateForm("pathTemplate", event.target.value)}
                placeholder="/orders/{record_ref}"
                required
              />
            </label>
            <label>
              <span>Record path</span>
              <input
                value={form.recordPath}
                onChange={(event) => updateForm("recordPath", event.target.value)}
                placeholder="data"
              />
            </label>
            <label>
              <span>Bearer token</span>
              <input
                value={form.bearerToken}
                onChange={(event) => updateForm("bearerToken", event.target.value)}
                placeholder={status?.has_bearer_token ? "Token saved" : "Read-scoped token"}
                type="password"
              />
            </label>
          </div>
          <div className="connectors-rest-actions">
            <DashboardButton icon={<Save />} loading={saving} type="submit" variant="primary">
              Save verifier
            </DashboardButton>
          </div>
        </form>

        <form className="connectors-generic-form connectors-rest-card" onSubmit={runTest}>
          <div className="connectors-generic-form-head connectors-rest-card-head">
            <span className="connectors-rest-step">2</span>
            <div>
              <strong>Run proof test</strong>
              <span>Compare claimed fields to the real source-of-record record.</span>
            </div>
          </div>
          <div className="connectors-generic-grid connectors-rest-field-grid">
            <label className="connectors-generic-wide">
              <span>Record ref</span>
              <input
                value={form.recordRef}
                onChange={(event) => updateForm("recordRef", event.target.value)}
                placeholder="ord_1001"
                required
              />
            </label>
            <label className="connectors-generic-wide">
              <span>Action type</span>
              <input
                value={form.actionType}
                onChange={(event) => updateForm("actionType", event.target.value)}
                placeholder="internal_api_mutation"
              />
            </label>
            <label className="connectors-generic-wide">
              <span>Match fields</span>
              <input
                value={form.matchFieldsText}
                onChange={(event) => updateForm("matchFieldsText", event.target.value)}
                placeholder="status, amount_minor"
              />
            </label>
            <label className="connectors-generic-wide">
              <span>Claimed JSON</span>
              <textarea
                value={form.claimedJson}
                onChange={(event) => updateForm("claimedJson", event.target.value)}
                rows={7}
              />
            </label>
          </div>
          <div className="connectors-rest-actions">
            <DashboardButton disabled={!connected} loading={testing} type="submit" variant="soft">
              Run proof test
            </DashboardButton>
          </div>
        </form>

        <details className="connectors-generic-bridge connectors-rest-advanced" aria-label="Generic REST webhook bridge request">
          <summary>
            <span>
              <strong>Advanced: webhook bridge request</strong>
              <small>For systems Zroky cannot poll directly.</small>
            </span>
          </summary>
          <div className="connectors-generic-bridge-body">
            <p>
              Call this after the agent reports success. Zroky uses the saved REST verifier to independently read the real record.
            </p>
            <pre aria-label="Generic REST saved connector bridge curl">
              <code>{bridgeCurl}</code>
            </pre>
            <DashboardButton icon={<Copy />} onClick={() => void copyBridge()} variant="soft">
              {copiedBridge ? "Copied" : "Copy bridge request"}
            </DashboardButton>
          </div>
        </details>
      </div>

      {error ? <div className="alert-strip connectors-alert">{error}</div> : null}
      {message ? <div className="connectors-success-strip">{message}</div> : null}
    </section>
  );
}

type BearerVerifierStatus = {
  connected?: boolean;
  has_bearer_token?: boolean;
  bearer_token_last4?: string | null;
  last_verdict?: string | null;
  health_status?: string | null;
};

type BearerVerifierFormState = {
  bearerToken: string;
  recordRef: string;
  claimedJson: string;
  matchFieldsText: string;
};

type BearerVerifierTestResult<TStatus extends BearerVerifierStatus> = {
  connector: TStatus;
  check: Pick<OutcomeReconciliationView, "verdict">;
};

function BearerVerifierSetupPanel<TStatus extends BearerVerifierStatus>({
  actionType,
  ariaLabel,
  claimedFieldsCopy,
  description,
  eyebrow,
  initialForm,
  latestCheck,
  recordLabel,
  onSaveConfig,
  saveError,
  saveMessage,
  secretSavedPlaceholder,
  status,
  testConfig,
  testError,
  testMessagePrefix,
  title,
  onStatusChange,
}: {
  actionType: string;
  ariaLabel: string;
  claimedFieldsCopy: string;
  description: string;
  eyebrow: string;
  initialForm: BearerVerifierFormState;
  latestCheck: OutcomeReconciliationView | null;
  recordLabel: string;
  onSaveConfig: (bearerToken: string | null) => Promise<TStatus>;
  saveError: string;
  saveMessage: string;
  secretSavedPlaceholder: string;
  status: TStatus | null;
  testConfig: (payload: {
    action_type: string;
    claimed: Record<string, unknown>;
    match_fields: string[];
    record_ref: string;
  }) => Promise<BearerVerifierTestResult<TStatus>>;
  testError: string;
  testMessagePrefix: string;
  title: string;
  onStatusChange: (status: TStatus) => void;
}) {
  const [form, setForm] = useState<BearerVerifierFormState>(initialForm);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const updateForm = (key: keyof BearerVerifierFormState, value: string) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const saveConfig = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const saved = await onSaveConfig(form.bearerToken || null);
      onStatusChange(saved);
      setMessage(saveMessage);
      setForm((current) => ({ ...current, bearerToken: "" }));
    } catch (err) {
      setError(err instanceof Error ? err.message : saveError);
    } finally {
      setSaving(false);
    }
  };

  const runTest = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setTesting(true);
    setError(null);
    setMessage(null);
    try {
      const claimed = parseClaimedJson(form.claimedJson);
      const result = await testConfig({
        record_ref: form.recordRef,
        claimed,
        action_type: actionType,
        match_fields: matchFieldsFromText(form.matchFieldsText),
      });
      onStatusChange(result.connector);
      setMessage(`${testMessagePrefix} test recorded ${result.check.verdict}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : testError);
    } finally {
      setTesting(false);
    }
  };

  return (
    <section className="connectors-generic-panel" aria-label={ariaLabel}>
      <div className="connectors-section-head">
        <div>
          <span className="dashboard-eyebrow">{eyebrow}</span>
          <h2>{title}</h2>
          <p>{description}</p>
        </div>
        <StatusPill value={status?.last_verdict ?? latestCheck?.verdict ?? "not_configured"} kind="proof" />
      </div>

      <div className="connectors-generic-layout">
        <form className="connectors-generic-form" onSubmit={saveConfig}>
          <div className="connectors-generic-form-head">
            <strong>1. Access</strong>
            <span>Use a restricted secret key with read-only access. Saved keys never render in the browser.</span>
          </div>
          <label>
            <span>Stripe secret key</span>
            <input
              autoComplete="off"
              onChange={(event) => updateForm("bearerToken", event.target.value)}
              placeholder={status?.has_bearer_token ? secretSavedPlaceholder : "sk_live_..."}
              type="password"
              value={form.bearerToken}
            />
          </label>
          <DashboardButton disabled={saving || (!form.bearerToken && !status?.has_bearer_token)} icon={<Save />} loading={saving} type="submit">
            Save access
          </DashboardButton>
        </form>

        <form className="connectors-generic-form" onSubmit={runTest}>
          <div className="connectors-generic-form-head">
            <strong>2. Preflight</strong>
            <span>{claimedFieldsCopy}</span>
          </div>
          <label>
            <span>{recordLabel}</span>
            <input onChange={(event) => updateForm("recordRef", event.target.value)} required value={form.recordRef} />
          </label>
          <label>
            <span>Claimed JSON</span>
            <textarea onChange={(event) => updateForm("claimedJson", event.target.value)} rows={5} value={form.claimedJson} />
          </label>
          <label>
            <span>Match fields</span>
            <input onChange={(event) => updateForm("matchFieldsText", event.target.value)} value={form.matchFieldsText} />
          </label>
          <DashboardButton disabled={testing || !status?.connected} icon={<ClipboardCheck />} loading={testing} type="submit">
            Run preflight
          </DashboardButton>
        </form>
      </div>

      {message ? <div className="connectors-success-strip">{message}</div> : null}
      {error ? <div className="alert-strip connectors-alert">{error}</div> : null}
      <div className="connector-fact-grid">
        <Fact label="Connected" value={status?.connected ? "yes" : "no"} />
        <Fact label="Secret" value={status?.has_bearer_token ? `saved${status.bearer_token_last4 ? ` (...${status.bearer_token_last4})` : ""}` : "missing"} />
        <Fact label="Last verdict" value={status?.last_verdict ?? latestCheck?.verdict ?? null} />
        <Fact label="Health" value={status?.health_status ?? "not configured"} />
      </div>
    </section>
  );
}

function StripeRefundSetupPanel({
  latestCheck,
  onStatusChange,
  status,
}: {
  latestCheck: OutcomeReconciliationView | null;
  onStatusChange: (status: StripeRefundConnectorStatusResponse) => void;
  status: StripeRefundConnectorStatusResponse | null;
}) {
  return (
    <BearerVerifierSetupPanel
      actionType="refund"
      ariaLabel="Stripe refund verifier setup"
      claimedFieldsCopy="Fetch one safe existing Stripe refund and compare normalized amount, currency, and status."
      description="Read one Stripe refund by ID and compare the fields your refund or payment agent claims."
      eyebrow="Stripe refund verifier"
      initialForm={{
        bearerToken: defaultStripeRefundForm.bearerToken,
        recordRef: defaultStripeRefundForm.refundId,
        claimedJson: defaultStripeRefundForm.claimedJson,
        matchFieldsText: defaultStripeRefundForm.matchFieldsText,
      }}
      latestCheck={latestCheck}
      recordLabel="Refund ID"
      onSaveConfig={(bearerToken) => saveStripeRefundConnectorConfig({ bearer_token: bearerToken })}
      saveError="Failed to save Stripe verifier."
      saveMessage="Stripe verifier saved. Run preflight to make it evidence-ready."
      secretSavedPlaceholder="Secret key saved"
      status={status}
      testConfig={(payload) =>
        testStripeRefundConnector({
          refund_id: payload.record_ref,
          action_type: payload.action_type,
          claimed: payload.claimed,
          match_fields: payload.match_fields,
        })
      }
      testError="Failed to run Stripe verifier test."
      testMessagePrefix="Stripe verifier"
      title="Native Stripe refund verification"
      onStatusChange={onStatusChange}
    />
  );
}

function StripePaymentSetupPanel({
  latestCheck,
  onStatusChange,
  status,
}: {
  latestCheck: OutcomeReconciliationView | null;
  onStatusChange: (status: StripePaymentConnectorStatusResponse) => void;
  status: StripePaymentConnectorStatusResponse | null;
}) {
  return (
    <BearerVerifierSetupPanel
      actionType="payment_adjustment"
      ariaLabel="Stripe payment verifier setup"
      claimedFieldsCopy="Fetch one safe existing PaymentIntent and compare normalized amount, currency, and status."
      description="Read one Stripe PaymentIntent by ID and compare amount, currency, customer, method, and status fields."
      eyebrow="Stripe payment verifier"
      initialForm={{
        bearerToken: defaultStripePaymentForm.bearerToken,
        recordRef: defaultStripePaymentForm.paymentId,
        claimedJson: defaultStripePaymentForm.claimedJson,
        matchFieldsText: defaultStripePaymentForm.matchFieldsText,
      }}
      latestCheck={latestCheck}
      recordLabel="PaymentIntent ID"
      onSaveConfig={(bearerToken) => saveStripePaymentConnectorConfig({ bearer_token: bearerToken })}
      saveError="Failed to save Stripe payment verifier."
      saveMessage="Stripe payment verifier saved. Run preflight to make it evidence-ready."
      secretSavedPlaceholder="Secret key saved"
      status={status}
      testConfig={(payload) =>
        testStripePaymentConnector({
          payment_id: payload.record_ref,
          action_type: payload.action_type,
          claimed: payload.claimed,
          match_fields: payload.match_fields,
        })
      }
      testError="Failed to run Stripe payment verifier test."
      testMessagePrefix="Stripe payment verifier"
      title="Native Stripe PaymentIntent verification"
      onStatusChange={onStatusChange}
    />
  );
}

function RazorpayRefundSetupPanel({
  latestCheck,
  onStatusChange,
  status,
}: {
  latestCheck: OutcomeReconciliationView | null;
  onStatusChange: (status: RazorpayRefundConnectorStatusResponse) => void;
  status: RazorpayRefundConnectorStatusResponse | null;
}) {
  const [form, setForm] = useState<RazorpayRefundFormState>(defaultRazorpayRefundForm);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!status?.query) return;
    setForm((current) => ({
      ...current,
      keyId: typeof status.query?.key_id === "string" ? status.query.key_id : current.keyId,
    }));
  }, [status]);

  const updateForm = (key: keyof RazorpayRefundFormState, value: string) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const saveConfig = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const saved = await saveRazorpayRefundConnectorConfig({
        key_id: form.keyId,
        key_secret: form.keySecret || null,
      });
      onStatusChange(saved);
      setMessage("Razorpay verifier saved. Run preflight to make it evidence-ready.");
      setForm((current) => ({ ...current, keySecret: "" }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save Razorpay verifier.");
    } finally {
      setSaving(false);
    }
  };

  const runTest = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setTesting(true);
    setError(null);
    setMessage(null);
    try {
      const claimed = parseClaimedJson(form.claimedJson);
      const result = await testRazorpayRefundConnector({
        refund_id: form.refundId,
        claimed,
        action_type: "refund",
        match_fields: matchFieldsFromText(form.matchFieldsText),
      });
      onStatusChange(result.connector);
      setMessage(`Razorpay verifier test recorded ${result.check.verdict}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run Razorpay verifier test.");
    } finally {
      setTesting(false);
    }
  };

  return (
    <section className="connectors-generic-panel" aria-label="Razorpay refund verifier setup">
      <div className="connectors-section-head">
        <div>
          <span className="dashboard-eyebrow">Razorpay refund verifier</span>
          <h2>Native Razorpay refund verification</h2>
          <p>Read one Razorpay refund by ID and compare normalized amount, currency, payment, and status fields.</p>
        </div>
        <StatusPill value={status?.last_verdict ?? latestCheck?.verdict ?? "not_configured"} kind="proof" />
      </div>

      <div className="connectors-generic-layout">
        <form className="connectors-generic-form" onSubmit={saveConfig}>
          <div className="connectors-generic-form-head">
            <strong>1. Access</strong>
            <span>Use Razorpay key id plus key secret. The key secret is encrypted and never renders in the browser.</span>
          </div>
          <label>
            <span>Razorpay key id</span>
            <input
              autoComplete="off"
              onChange={(event) => updateForm("keyId", event.target.value)}
              placeholder="rzp_live_..."
              required
              value={form.keyId}
            />
          </label>
          <label>
            <span>Razorpay key secret</span>
            <input
              autoComplete="off"
              onChange={(event) => updateForm("keySecret", event.target.value)}
              placeholder={status?.has_bearer_token ? "Key secret saved" : "Razorpay key secret"}
              type="password"
              value={form.keySecret}
            />
          </label>
          <DashboardButton disabled={saving || !form.keyId || (!form.keySecret && !status?.has_bearer_token)} icon={<Save />} loading={saving} type="submit">
            Save access
          </DashboardButton>
        </form>

        <form className="connectors-generic-form" onSubmit={runTest}>
          <div className="connectors-generic-form-head">
            <strong>2. Preflight</strong>
            <span>Fetch one safe existing Razorpay refund and compare normalized amount, currency, payment id, and status.</span>
          </div>
          <label>
            <span>Refund ID</span>
            <input onChange={(event) => updateForm("refundId", event.target.value)} required value={form.refundId} />
          </label>
          <label>
            <span>Claimed JSON</span>
            <textarea onChange={(event) => updateForm("claimedJson", event.target.value)} rows={5} value={form.claimedJson} />
          </label>
          <label>
            <span>Match fields</span>
            <input onChange={(event) => updateForm("matchFieldsText", event.target.value)} value={form.matchFieldsText} />
          </label>
          <DashboardButton disabled={testing || !status?.connected} icon={<ClipboardCheck />} loading={testing} type="submit">
            Run preflight
          </DashboardButton>
        </form>
      </div>

      {message ? <div className="connectors-success-strip">{message}</div> : null}
      {error ? <div className="alert-strip connectors-alert">{error}</div> : null}
      <div className="connector-fact-grid">
        <Fact label="Connected" value={status?.connected ? "yes" : "no"} />
        <Fact label="Key id" value={typeof status?.query?.key_id === "string" ? status.query.key_id : null} />
        <Fact label="Key secret" value={status?.has_bearer_token ? `saved${status.bearer_token_last4 ? ` (...${status.bearer_token_last4})` : ""}` : "missing"} />
        <Fact label="Last verdict" value={status?.last_verdict ?? latestCheck?.verdict ?? null} />
        <Fact label="Health" value={status?.health_status ?? "not configured"} />
      </div>
    </section>
  );
}

function HubSpotSetupPanel({
  latestCheck,
  onStatusChange,
  status,
}: {
  latestCheck: OutcomeReconciliationView | null;
  onStatusChange: (status: HubSpotCrmConnectorStatusResponse) => void;
  status: HubSpotCrmConnectorStatusResponse | null;
}) {
  const [form, setForm] = useState<HubSpotFormState>(defaultHubSpotForm);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!status?.query) return;
    setForm((current) => ({
      ...current,
      idProperty: typeof status.query?.idProperty === "string" ? status.query.idProperty : current.idProperty,
      propertiesText: typeof status.query?.properties === "string" ? status.query.properties : current.propertiesText,
    }));
  }, [status]);

  const updateForm = (key: keyof HubSpotFormState, value: string) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const saveConfig = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const saved = await saveHubSpotCrmConnectorConfig({
        query: hubSpotQueryFromForm(form),
        bearer_token: form.bearerToken || null,
      });
      onStatusChange(saved);
      setMessage("HubSpot verifier saved. Run preflight to make it evidence-ready.");
      setForm((current) => ({ ...current, bearerToken: "" }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save HubSpot verifier.");
    } finally {
      setSaving(false);
    }
  };

  const runTest = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setTesting(true);
    setError(null);
    setMessage(null);
    try {
      const claimed = parseClaimedJson(form.claimedJson);
      const result = await testHubSpotCrmConnector({
        record_ref: form.recordRef,
        claimed,
        action_type: "customer_record_update",
        match_fields: matchFieldsFromText(form.matchFieldsText),
      });
      onStatusChange(result.connector);
      setMessage(`HubSpot verifier test recorded ${result.check.verdict}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run HubSpot verifier test.");
    } finally {
      setTesting(false);
    }
  };

  const connected = Boolean(status?.connected);

  return (
    <section className="connectors-generic-panel" aria-label="HubSpot CRM verifier setup">
      <div className="connectors-section-head">
        <div>
          <span className="dashboard-eyebrow">HubSpot CRM verifier</span>
          <h2>Native HubSpot contact verification</h2>
          <p>
            Read HubSpot contacts directly for CRM agent proof. Private app token is available now; OAuth install remains planned.
          </p>
        </div>
        <StatusPill
          value={status?.last_verdict ?? latestCheck?.verdict ?? "not_configured"}
          kind="proof"
          tone={connected ? "warning" : "neutral"}
        />
      </div>

      <div className="connectors-generic-layout">
        <form className="connectors-generic-form" onSubmit={saveConfig}>
          <div className="connectors-generic-form-head">
            <strong>1. Access</strong>
            <span>Use a read-scoped HubSpot private app token. The browser never renders saved tokens.</span>
          </div>
          <div className="connectors-generic-grid">
            <label>
              <span>Private app token</span>
              <input
                value={form.bearerToken}
                onChange={(event) => updateForm("bearerToken", event.target.value)}
                placeholder={status?.has_bearer_token ? "Token saved" : "HubSpot private app token"}
                type="password"
              />
            </label>
            <label>
              <span>ID property</span>
              <input
                value={form.idProperty}
                onChange={(event) => updateForm("idProperty", event.target.value)}
                placeholder="email"
              />
            </label>
            <label className="connectors-generic-wide">
              <span>Properties</span>
              <input
                value={form.propertiesText}
                onChange={(event) => updateForm("propertiesText", event.target.value)}
                placeholder="email,firstname,lastname,lifecyclestage,hs_object_id"
              />
            </label>
          </div>
          <DashboardButton icon={<Save />} loading={saving} type="submit" variant="primary">
            Save access
          </DashboardButton>
        </form>

        <form className="connectors-generic-form" onSubmit={runTest}>
          <div className="connectors-generic-form-head">
            <strong>2. Preflight</strong>
            <span>Fetch one existing contact and match claimed CRM fields.</span>
          </div>
          <div className="connectors-generic-grid">
            <label>
              <span>Contact ref</span>
              <input
                value={form.recordRef}
                onChange={(event) => updateForm("recordRef", event.target.value)}
                placeholder="owner@example.com"
                required
              />
            </label>
            <label>
              <span>Match fields</span>
              <input
                value={form.matchFieldsText}
                onChange={(event) => updateForm("matchFieldsText", event.target.value)}
                placeholder="email,lifecyclestage"
              />
            </label>
            <label className="connectors-generic-wide">
              <span>Claimed JSON</span>
              <textarea
                value={form.claimedJson}
                onChange={(event) => updateForm("claimedJson", event.target.value)}
                rows={7}
              />
            </label>
          </div>
          <DashboardButton disabled={!connected} loading={testing} type="submit" variant="soft">
            Run preflight
          </DashboardButton>
        </form>
      </div>

      {error ? <div className="alert-strip connectors-alert">{error}</div> : null}
      {message ? <div className="connectors-success-strip">{message}</div> : null}
    </section>
  );
}

function SalesforceSetupPanel({
  latestCheck,
  onStatusChange,
  status,
}: {
  latestCheck: OutcomeReconciliationView | null;
  onStatusChange: (status: SalesforceCrmConnectorStatusResponse) => void;
  status: SalesforceCrmConnectorStatusResponse | null;
}) {
  const [form, setForm] = useState<SalesforceFormState>(defaultSalesforceForm);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!status) return;
    setForm((current) => ({
      ...current,
      baseUrl: status.base_url ?? current.baseUrl,
      fieldsText: typeof status.query?.fields === "string" ? status.query.fields : current.fieldsText,
    }));
  }, [status]);

  const updateForm = (key: keyof SalesforceFormState, value: string) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const saveConfig = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const saved = await saveSalesforceCrmConnectorConfig({
        base_url: form.baseUrl,
        query: salesforceQueryFromForm(form),
        bearer_token: form.bearerToken || null,
      });
      onStatusChange(saved);
      setMessage("Salesforce verifier saved. Run preflight to make it evidence-ready.");
      setForm((current) => ({ ...current, bearerToken: "" }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save Salesforce verifier.");
    } finally {
      setSaving(false);
    }
  };

  const runTest = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setTesting(true);
    setError(null);
    setMessage(null);
    try {
      const claimed = parseClaimedJson(form.claimedJson);
      const result = await testSalesforceCrmConnector({
        object_type: form.objectType,
        record_ref: form.recordRef,
        claimed,
        action_type: "customer_record_update",
        match_fields: matchFieldsFromText(form.matchFieldsText),
      });
      onStatusChange(result.connector);
      setMessage(`Salesforce verifier test recorded ${result.check.verdict}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run Salesforce verifier test.");
    } finally {
      setTesting(false);
    }
  };

  const connected = Boolean(status?.connected);

  return (
    <section className="connectors-generic-panel" aria-label="Salesforce CRM verifier setup">
      <div className="connectors-section-head">
        <div>
          <span className="dashboard-eyebrow">Salesforce CRM verifier</span>
          <h2>Native Salesforce sObject verification</h2>
          <p>
            Read Accounts, Contacts, Leads, Opportunities, Cases, or custom objects for CRM and RevOps proof.
            Bearer token setup works today; one-click OAuth remains planned.
          </p>
        </div>
        <StatusPill
          value={status?.last_verdict ?? latestCheck?.verdict ?? "not_configured"}
          kind="proof"
          tone={connected ? "warning" : "neutral"}
        />
      </div>

      <div className="connectors-generic-layout">
        <form className="connectors-generic-form" onSubmit={saveConfig}>
          <div className="connectors-generic-form-head">
            <strong>1. Access</strong>
            <span>Use a read-scoped Salesforce bearer token. Saved tokens never render in the browser.</span>
          </div>
          <div className="connectors-generic-grid">
            <label>
              <span>Instance URL</span>
              <input
                value={form.baseUrl}
                onChange={(event) => updateForm("baseUrl", event.target.value)}
                placeholder="https://company.my.salesforce.com"
                required
              />
            </label>
            <label>
              <span>Fields</span>
              <input
                value={form.fieldsText}
                onChange={(event) => updateForm("fieldsText", event.target.value)}
                placeholder="Id,Name,StageName,Amount"
              />
            </label>
            <label className="connectors-generic-wide">
              <span>Bearer token</span>
              <input
                value={form.bearerToken}
                onChange={(event) => updateForm("bearerToken", event.target.value)}
                placeholder={status?.has_bearer_token ? "Token saved" : "Salesforce bearer token"}
                type="password"
              />
            </label>
          </div>
          <DashboardButton icon={<Save />} loading={saving} type="submit" variant="primary">
            Save access
          </DashboardButton>
        </form>

        <form className="connectors-generic-form" onSubmit={runTest}>
          <div className="connectors-generic-form-head">
            <strong>2. Preflight</strong>
            <span>Fetch one safe existing Salesforce record and compare the fields your CRM agent will claim.</span>
          </div>
          <div className="connectors-generic-grid">
            <label>
              <span>Object type</span>
              <input
                value={form.objectType}
                onChange={(event) => updateForm("objectType", event.target.value)}
                placeholder="Account"
                required
              />
            </label>
            <label>
              <span>Record ID</span>
              <input
                value={form.recordRef}
                onChange={(event) => updateForm("recordRef", event.target.value)}
                placeholder="001..."
                required
              />
            </label>
            <label className="connectors-generic-wide">
              <span>Match fields</span>
              <input
                value={form.matchFieldsText}
                onChange={(event) => updateForm("matchFieldsText", event.target.value)}
                placeholder="salesforce_id,Name,StageName"
              />
            </label>
            <label className="connectors-generic-wide">
              <span>Claimed JSON</span>
              <textarea
                value={form.claimedJson}
                onChange={(event) => updateForm("claimedJson", event.target.value)}
                rows={7}
              />
            </label>
          </div>
          <DashboardButton disabled={!connected} loading={testing} type="submit" variant="soft">
            Run preflight
          </DashboardButton>
        </form>
      </div>

      {error ? <div className="alert-strip connectors-alert">{error}</div> : null}
      {message ? <div className="connectors-success-strip">{message}</div> : null}
    </section>
  );
}

function ZohoSetupPanel({
  latestCheck,
  onStatusChange,
  status,
}: {
  latestCheck: OutcomeReconciliationView | null;
  onStatusChange: (status: ZohoCrmConnectorStatusResponse) => void;
  status: ZohoCrmConnectorStatusResponse | null;
}) {
  const [form, setForm] = useState<ZohoFormState>(defaultZohoForm);
  const [connecting, setConnecting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!status) return;
    setForm((current) => ({
      ...current,
      baseUrl: status.base_url ?? current.baseUrl,
      fieldsText: typeof status.query?.fields === "string" ? status.query.fields : current.fieldsText,
    }));
  }, [status]);

  const updateForm = (key: keyof ZohoFormState, value: string) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const startOAuth = async () => {
    setConnecting(true);
    setError(null);
    setMessage(null);
    try {
      const result = await startZohoCrmOAuth();
      externalNavigator.assign(result.authorization_url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start Zoho OAuth.");
      setConnecting(false);
    }
  };

  const saveConfig = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const saved = await saveZohoCrmConnectorConfig({
        base_url: form.baseUrl,
        query: zohoQueryFromForm(form),
        bearer_token: form.bearerToken || null,
      });
      onStatusChange(saved);
      setMessage("Zoho CRM verifier saved. Run preflight to make it evidence-ready.");
      setForm((current) => ({ ...current, bearerToken: "" }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save Zoho CRM verifier.");
    } finally {
      setSaving(false);
    }
  };

  const runTest = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setTesting(true);
    setError(null);
    setMessage(null);
    try {
      const claimed = parseClaimedJson(form.claimedJson);
      const result = await testZohoCrmConnector({
        module_name: form.moduleName,
        record_ref: form.recordRef,
        claimed,
        action_type: "customer_record_update",
        match_fields: matchFieldsFromText(form.matchFieldsText),
      });
      onStatusChange(result.connector);
      setMessage(`Zoho CRM verifier test recorded ${result.check.verdict}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run Zoho CRM verifier test.");
    } finally {
      setTesting(false);
    }
  };

  const connected = Boolean(status?.connected);

  return (
    <section className="connectors-generic-panel" aria-label="Zoho CRM verifier setup">
      <div className="connectors-section-head">
        <div>
          <span className="dashboard-eyebrow">Zoho CRM verifier</span>
          <h2>Native Zoho CRM record verification</h2>
          <p>
            Read Leads, Contacts, Accounts, Deals, or custom Zoho CRM modules for CRM and RevOps proof.
            Connect with Zoho OAuth or use a read-scoped access token as a manual fallback.
          </p>
        </div>
        <StatusPill
          value={status?.last_verdict ?? latestCheck?.verdict ?? "not_configured"}
          kind="proof"
          tone={connected ? "warning" : "neutral"}
        />
      </div>

      <div className="connectors-generic-layout">
        <form className="connectors-generic-form" onSubmit={saveConfig}>
          <div className="connectors-generic-form-head">
            <strong>1. Access</strong>
            <span>
              OAuth stores an encrypted refresh token. Manual access tokens remain supported for restricted tenants.
            </span>
          </div>
          <DashboardButton
            disabled={connecting}
            loading={connecting}
            onClick={startOAuth}
            type="button"
            variant="primary"
          >
            Connect with OAuth
          </DashboardButton>
          {status?.has_oauth_refresh_token ? (
            <div className="connectors-success-strip">
              OAuth connection saved
              {status.oauth_refresh_token_last4 ? ` (refresh token ...${status.oauth_refresh_token_last4})` : ""}.
            </div>
          ) : null}
          <div className="connectors-generic-grid">
            <label>
              <span>Zoho API domain</span>
              <input
                value={form.baseUrl}
                onChange={(event) => updateForm("baseUrl", event.target.value)}
                placeholder="https://www.zohoapis.com"
                required
              />
            </label>
            <label>
              <span>Fields</span>
              <input
                value={form.fieldsText}
                onChange={(event) => updateForm("fieldsText", event.target.value)}
                placeholder="id,Full_Name,Email,Stage"
              />
            </label>
            <label className="connectors-generic-wide">
              <span>Manual bearer token</span>
              <input
                value={form.bearerToken}
                onChange={(event) => updateForm("bearerToken", event.target.value)}
                placeholder={status?.has_bearer_token ? "Token saved" : "Optional read-scoped access token"}
                type="password"
              />
            </label>
          </div>
          <DashboardButton icon={<Save />} loading={saving} type="submit" variant="primary">
            Save access
          </DashboardButton>
        </form>

        <form className="connectors-generic-form" onSubmit={runTest}>
          <div className="connectors-generic-form-head">
            <strong>2. Preflight</strong>
            <span>Fetch one safe existing Zoho CRM record and compare the fields your CRM agent will claim.</span>
          </div>
          <div className="connectors-generic-grid">
            <label>
              <span>Module name</span>
              <input
                value={form.moduleName}
                onChange={(event) => updateForm("moduleName", event.target.value)}
                placeholder="Contacts"
                required
              />
            </label>
            <label>
              <span>Record ID</span>
              <input
                value={form.recordRef}
                onChange={(event) => updateForm("recordRef", event.target.value)}
                placeholder="1234567890000000001"
                required
              />
            </label>
            <label className="connectors-generic-wide">
              <span>Match fields</span>
              <input
                value={form.matchFieldsText}
                onChange={(event) => updateForm("matchFieldsText", event.target.value)}
                placeholder="zoho_record_id,Email,Stage"
              />
            </label>
            <label className="connectors-generic-wide">
              <span>Claimed JSON</span>
              <textarea
                value={form.claimedJson}
                onChange={(event) => updateForm("claimedJson", event.target.value)}
                rows={7}
              />
            </label>
          </div>
          <DashboardButton disabled={!connected} loading={testing} type="submit" variant="soft">
            Run preflight
          </DashboardButton>
        </form>
      </div>

      {error ? <div className="alert-strip connectors-alert">{error}</div> : null}
      {message ? <div className="connectors-success-strip">{message}</div> : null}
    </section>
  );
}

function ZendeskSetupPanel({
  latestCheck,
  onStatusChange,
  status,
}: {
  latestCheck: OutcomeReconciliationView | null;
  onStatusChange: (status: ZendeskTicketConnectorStatusResponse) => void;
  status: ZendeskTicketConnectorStatusResponse | null;
}) {
  const [form, setForm] = useState<ZendeskFormState>(defaultZendeskForm);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!status) return;
    setForm((current) => ({
      ...current,
      baseUrl: status.base_url ?? current.baseUrl,
      authUsername: typeof status.query?.auth_username === "string" ? status.query.auth_username : current.authUsername,
    }));
  }, [status]);

  const updateForm = (key: keyof ZendeskFormState, value: string) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const saveConfig = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const saved = await saveZendeskTicketConnectorConfig({
        base_url: form.baseUrl,
        auth_username: form.authUsername || null,
        bearer_token: form.bearerToken || null,
      });
      onStatusChange(saved);
      setMessage("Zendesk verifier saved. Run preflight to make it evidence-ready.");
      setForm((current) => ({ ...current, bearerToken: "" }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save Zendesk verifier.");
    } finally {
      setSaving(false);
    }
  };

  const runTest = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setTesting(true);
    setError(null);
    setMessage(null);
    try {
      const claimed = parseClaimedJson(form.claimedJson);
      const result = await testZendeskTicketConnector({
        record_ref: form.recordRef,
        claimed,
        action_type: "ticket_close",
        match_fields: matchFieldsFromText(form.matchFieldsText),
      });
      onStatusChange(result.connector);
      setMessage(`Zendesk verifier test recorded ${result.check.verdict}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run Zendesk verifier test.");
    } finally {
      setTesting(false);
    }
  };

  const connected = Boolean(status?.connected);

  return (
    <section className="connectors-generic-panel" aria-label="Zendesk ticket verifier setup">
      <div className="connectors-section-head">
        <div>
          <span className="dashboard-eyebrow">Zendesk ticket verifier</span>
          <h2>Native Zendesk ticket verification</h2>
          <p>
            Read Zendesk Support tickets directly for support agent proof. OAuth bearer tokens or API token basic auth work today; one-click OAuth remains planned.
          </p>
        </div>
        <StatusPill
          value={status?.last_verdict ?? latestCheck?.verdict ?? "not_configured"}
          kind="proof"
          tone={connected ? "warning" : "neutral"}
        />
      </div>

      <div className="connectors-generic-layout">
        <form className="connectors-generic-form" onSubmit={saveConfig}>
          <div className="connectors-generic-form-head">
            <strong>1. Access</strong>
            <span>Use an OAuth bearer token, or provide email for Zendesk API token basic auth. Saved tokens never render in the browser.</span>
          </div>
          <div className="connectors-generic-grid">
            <label>
              <span>Zendesk URL</span>
              <input
                value={form.baseUrl}
                onChange={(event) => updateForm("baseUrl", event.target.value)}
                placeholder="https://company.zendesk.com"
                required
              />
            </label>
            <label>
              <span>Auth email (optional)</span>
              <input
                value={form.authUsername}
                onChange={(event) => updateForm("authUsername", event.target.value)}
                placeholder="agent@example.com"
              />
            </label>
            <label className="connectors-generic-wide">
              <span>Token</span>
              <input
                value={form.bearerToken}
                onChange={(event) => updateForm("bearerToken", event.target.value)}
                placeholder={status?.has_bearer_token ? "Token saved" : "Read-scoped Zendesk token"}
                type="password"
              />
            </label>
          </div>
          <DashboardButton icon={<Save />} loading={saving} type="submit" variant="primary">
            Save access
          </DashboardButton>
        </form>

        <form className="connectors-generic-form" onSubmit={runTest}>
          <div className="connectors-generic-form-head">
            <strong>2. Preflight</strong>
            <span>Fetch one safe existing ticket and compare the fields your support agent will claim.</span>
          </div>
          <div className="connectors-generic-grid">
            <label>
              <span>Ticket ID</span>
              <input
                value={form.recordRef}
                onChange={(event) => updateForm("recordRef", event.target.value)}
                placeholder="12345"
                required
              />
            </label>
            <label>
              <span>Match fields</span>
              <input
                value={form.matchFieldsText}
                onChange={(event) => updateForm("matchFieldsText", event.target.value)}
                placeholder="ticket_id,status"
              />
            </label>
            <label className="connectors-generic-wide">
              <span>Claimed JSON</span>
              <textarea
                value={form.claimedJson}
                onChange={(event) => updateForm("claimedJson", event.target.value)}
                rows={7}
              />
            </label>
          </div>
          <DashboardButton disabled={!connected} loading={testing} type="submit" variant="soft">
            Run preflight
          </DashboardButton>
        </form>
      </div>

      {error ? <div className="alert-strip connectors-alert">{error}</div> : null}
      {message ? <div className="connectors-success-strip">{message}</div> : null}
    </section>
  );
}

function JiraSetupPanel({
  latestCheck,
  onStatusChange,
  status,
}: {
  latestCheck: OutcomeReconciliationView | null;
  onStatusChange: (status: JiraIssueConnectorStatusResponse) => void;
  status: JiraIssueConnectorStatusResponse | null;
}) {
  const [form, setForm] = useState<JiraFormState>(defaultJiraForm);
  const [saving, setSaving] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!status) return;
    const siteUrl =
      typeof status.query?.atlassian_site_url === "string"
        ? status.query.atlassian_site_url
        : null;
    setForm((current) => ({
      ...current,
      baseUrl: siteUrl ?? status.base_url ?? current.baseUrl,
      authUsername:
        typeof status.query?.auth_username === "string"
          ? status.query.auth_username
          : current.authUsername,
    }));
  }, [status]);

  const updateForm = (key: keyof JiraFormState, value: string) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const saveConfig = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const saved = await saveJiraIssueConnectorConfig({
        base_url: form.baseUrl,
        auth_username: form.authUsername || null,
        bearer_token: form.bearerToken || null,
      });
      onStatusChange(saved);
      setMessage("Jira verifier saved. Run preflight to make it evidence-ready.");
      setForm((current) => ({ ...current, bearerToken: "" }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save Jira verifier.");
    } finally {
      setSaving(false);
    }
  };

  const connectWithOAuth = async () => {
    setConnecting(true);
    setError(null);
    setMessage(null);
    try {
      const result = await startJiraIssueOAuth();
      window.location.assign(result.authorization_url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start Jira OAuth.");
      setConnecting(false);
    }
  };

  const runTest = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setTesting(true);
    setError(null);
    setMessage(null);
    try {
      const claimed = parseClaimedJson(form.claimedJson);
      const result = await testJiraIssueConnector({
        record_ref: form.recordRef,
        claimed,
        action_type: "ticket_close",
        match_fields: matchFieldsFromText(form.matchFieldsText),
      });
      onStatusChange(result.connector);
      setMessage(`Jira verifier test recorded ${result.check.verdict}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run Jira verifier test.");
    } finally {
      setTesting(false);
    }
  };

  const connected = Boolean(status?.connected);

  return (
    <section className="connectors-generic-panel" aria-label="Jira issue verifier setup">
      <div className="connectors-section-head">
        <div>
          <span className="dashboard-eyebrow">Jira / JSM verifier</span>
          <h2>Native Jira issue verification</h2>
          <p>
            Read Jira or Jira Service Management issues for support, access, incident, and change proof. Connect Jira with OAuth, or use an API token as a fallback.
          </p>
        </div>
        <StatusPill
          value={status?.last_verdict ?? latestCheck?.verdict ?? "not_configured"}
          kind="proof"
          tone={connected ? "warning" : "neutral"}
        />
      </div>

      <div className="connectors-generic-layout">
        <form className="connectors-generic-form" onSubmit={saveConfig}>
          <div className="connectors-generic-form-head">
            <strong>1. Access</strong>
            <span>
              OAuth is the fastest path. API token setup remains available for manual access.
            </span>
          </div>
          <DashboardButton loading={connecting} onClick={connectWithOAuth} type="button" variant="primary">
            Connect Jira
          </DashboardButton>
          {status?.has_oauth_refresh_token ? (
            <div className="connectors-success-strip">
              Jira OAuth connected{status.query?.atlassian_site_url ? ` to ${status.query.atlassian_site_url}` : ""}.
            </div>
          ) : null}
          <div className="connectors-generic-grid">
            <label>
              <span>Atlassian site URL</span>
              <input
                value={form.baseUrl}
                onChange={(event) => updateForm("baseUrl", event.target.value)}
                placeholder="https://company.atlassian.net"
                required
              />
            </label>
            <label>
              <span>Atlassian email</span>
              <input
                value={form.authUsername}
                onChange={(event) => updateForm("authUsername", event.target.value)}
                placeholder="agent@example.com"
              />
            </label>
            <label className="connectors-generic-wide">
              <span>API token or bearer token</span>
              <input
                value={form.bearerToken}
                onChange={(event) => updateForm("bearerToken", event.target.value)}
                placeholder={status?.has_bearer_token ? "Token saved" : "Read-scoped Jira token"}
                type="password"
              />
            </label>
          </div>
          <DashboardButton icon={<Save />} loading={saving} type="submit" variant="primary">
            Save access
          </DashboardButton>
        </form>

        <form className="connectors-generic-form" onSubmit={runTest}>
          <div className="connectors-generic-form-head">
            <strong>2. Preflight</strong>
            <span>Fetch one safe existing issue and compare the fields your agent will claim.</span>
          </div>
          <div className="connectors-generic-grid">
            <label>
              <span>Issue key</span>
              <input
                value={form.recordRef}
                onChange={(event) => updateForm("recordRef", event.target.value)}
                placeholder="JSM-123"
                required
              />
            </label>
            <label>
              <span>Match fields</span>
              <input
                value={form.matchFieldsText}
                onChange={(event) => updateForm("matchFieldsText", event.target.value)}
                placeholder="jira_issue_key,status"
              />
            </label>
            <label className="connectors-generic-wide">
              <span>Claimed JSON</span>
              <textarea
                value={form.claimedJson}
                onChange={(event) => updateForm("claimedJson", event.target.value)}
                rows={7}
              />
            </label>
          </div>
          <DashboardButton disabled={!connected} loading={testing} type="submit" variant="soft">
            Run preflight
          </DashboardButton>
        </form>
      </div>

      {error ? <div className="alert-strip connectors-alert">{error}</div> : null}
      {message ? <div className="connectors-success-strip">{message}</div> : null}
    </section>
  );
}

function NetSuiteSetupPanel({
  latestCheck,
  onStatusChange,
  status,
}: {
  latestCheck: OutcomeReconciliationView | null;
  onStatusChange: (status: NetSuiteFinanceConnectorStatusResponse) => void;
  status: NetSuiteFinanceConnectorStatusResponse | null;
}) {
  const [form, setForm] = useState<NetSuiteFormState>(defaultNetSuiteForm);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!status) return;
    setForm((current) => ({
      ...current,
      baseUrl: status.base_url ?? current.baseUrl,
    }));
  }, [status]);

  const updateForm = (key: keyof NetSuiteFormState, value: string) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const saveConfig = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const saved = await saveNetSuiteFinanceConnectorConfig({
        base_url: form.baseUrl,
        bearer_token: form.bearerToken || null,
      });
      onStatusChange(saved);
      setMessage("NetSuite verifier saved. Run preflight to make it evidence-ready.");
      setForm((current) => ({ ...current, bearerToken: "" }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save NetSuite verifier.");
    } finally {
      setSaving(false);
    }
  };

  const runTest = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setTesting(true);
    setError(null);
    setMessage(null);
    try {
      const claimed = parseClaimedJson(form.claimedJson);
      const result = await testNetSuiteFinanceConnector({
        record_type: form.recordType,
        record_ref: form.recordRef,
        claimed,
        action_type: "invoice_spend_approval",
        match_fields: matchFieldsFromText(form.matchFieldsText),
      });
      onStatusChange(result.connector);
      setMessage(`NetSuite verifier test recorded ${result.check.verdict}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run NetSuite verifier test.");
    } finally {
      setTesting(false);
    }
  };

  const connected = Boolean(status?.connected);

  return (
    <section className="connectors-generic-panel" aria-label="NetSuite finance verifier setup">
      <div className="connectors-section-head">
        <div>
          <span className="dashboard-eyebrow">NetSuite finance verifier</span>
          <h2>Native NetSuite record verification</h2>
          <p>
            Read one NetSuite finance or procurement record for vendor-bill, purchase-order, invoice, and payment-approval proof.
          </p>
        </div>
        <StatusPill
          value={status?.last_verdict ?? latestCheck?.verdict ?? "not_configured"}
          kind="proof"
          tone={connected ? "warning" : "neutral"}
        />
      </div>

      <div className="connectors-generic-layout">
        <form className="connectors-generic-form" onSubmit={saveConfig}>
          <div className="connectors-generic-form-head">
            <strong>1. Access</strong>
            <span>Use a read-scoped NetSuite bearer token. Saved tokens never render in the browser.</span>
          </div>
          <div className="connectors-generic-grid">
            <label className="connectors-generic-wide">
              <span>NetSuite REST base URL</span>
              <input
                value={form.baseUrl}
                onChange={(event) => updateForm("baseUrl", event.target.value)}
                placeholder="https://ACCOUNT.suitetalk.api.netsuite.com"
                required
              />
            </label>
            <label className="connectors-generic-wide">
              <span>Bearer token</span>
              <input
                value={form.bearerToken}
                onChange={(event) => updateForm("bearerToken", event.target.value)}
                placeholder={status?.has_bearer_token ? "Token saved" : "Read-scoped NetSuite token"}
                type="password"
              />
            </label>
          </div>
          <DashboardButton icon={<Save />} loading={saving} type="submit" variant="primary">
            Save access
          </DashboardButton>
        </form>

        <form className="connectors-generic-form" onSubmit={runTest}>
          <div className="connectors-generic-form-head">
            <strong>2. Preflight</strong>
            <span>Fetch one safe existing NetSuite record and compare the fields your finance agent will claim.</span>
          </div>
          <div className="connectors-generic-grid">
            <label>
              <span>Record type</span>
              <input
                value={form.recordType}
                onChange={(event) => updateForm("recordType", event.target.value)}
                placeholder="vendorBill"
                required
              />
            </label>
            <label>
              <span>Record ID</span>
              <input
                value={form.recordRef}
                onChange={(event) => updateForm("recordRef", event.target.value)}
                placeholder="12345"
                required
              />
            </label>
            <label>
              <span>Match fields</span>
              <input
                value={form.matchFieldsText}
                onChange={(event) => updateForm("matchFieldsText", event.target.value)}
                placeholder="netsuite_record_id,status,amount_minor"
              />
            </label>
            <label className="connectors-generic-wide">
              <span>Claimed JSON</span>
              <textarea
                value={form.claimedJson}
                onChange={(event) => updateForm("claimedJson", event.target.value)}
                rows={7}
              />
            </label>
          </div>
          <DashboardButton disabled={!connected} loading={testing} type="submit" variant="soft">
            Run preflight
          </DashboardButton>
        </form>
      </div>

      {error ? <div className="alert-strip connectors-alert">{error}</div> : null}
      {message ? <div className="connectors-success-strip">{message}</div> : null}
    </section>
  );
}

function ShopifySetupPanel({
  latestCheck,
  onStatusChange,
  status,
}: {
  latestCheck: OutcomeReconciliationView | null;
  onStatusChange: (status: ShopifyConnectorStatusResponse) => void;
  status: ShopifyConnectorStatusResponse | null;
}) {
  const [form, setForm] = useState<ShopifyFormState>(defaultShopifyForm);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!status) return;
    setForm((current) => ({
      ...current,
      baseUrl: status.base_url ?? current.baseUrl,
    }));
  }, [status]);

  const updateForm = (key: keyof ShopifyFormState, value: string) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const saveConfig = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const saved = await saveShopifyConnectorConfig({
        base_url: form.baseUrl,
        bearer_token: form.bearerToken || null,
      });
      onStatusChange(saved);
      setMessage("Shopify verifier saved. Run preflight to make it evidence-ready.");
      setForm((current) => ({ ...current, bearerToken: "" }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save Shopify verifier.");
    } finally {
      setSaving(false);
    }
  };

  const runTest = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setTesting(true);
    setError(null);
    setMessage(null);
    try {
      const claimed = parseClaimedJson(form.claimedJson);
      const result = await testShopifyConnector({
        record_ref: form.recordRef,
        claimed,
        action_type: "shopify_record",
        match_fields: matchFieldsFromText(form.matchFieldsText),
      });
      onStatusChange(result.connector);
      setMessage(`Shopify verifier test recorded ${result.check.verdict}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run Shopify verifier test.");
    } finally {
      setTesting(false);
    }
  };

  const connected = Boolean(status?.connected);

  return (
    <section className="connectors-generic-panel" aria-label="Shopify Admin verifier setup">
      <div className="connectors-section-head">
        <div>
          <span className="dashboard-eyebrow">Shopify Admin verifier</span>
          <h2>Native Shopify order verification</h2>
          <p>Read one Shopify Admin order by ID and compare total, currency, financial status, fulfillment, and cancellation fields.</p>
        </div>
        <StatusPill
          value={status?.last_verdict ?? latestCheck?.verdict ?? "not_configured"}
          kind="proof"
          tone={connected ? "warning" : "neutral"}
        />
      </div>

      <div className="connectors-generic-layout">
        <form className="connectors-generic-form" onSubmit={saveConfig}>
          <div className="connectors-generic-form-head">
            <strong>1. Access</strong>
            <span>Use a read-scoped Shopify Admin API access token. Saved tokens never render in the browser.</span>
          </div>
          <div className="connectors-generic-grid">
            <label className="connectors-generic-wide">
              <span>Shop Admin base URL</span>
              <input
                value={form.baseUrl}
                onChange={(event) => updateForm("baseUrl", event.target.value)}
                placeholder="https://example.myshopify.com"
                required
              />
            </label>
            <label className="connectors-generic-wide">
              <span>Admin API access token</span>
              <input
                value={form.bearerToken}
                onChange={(event) => updateForm("bearerToken", event.target.value)}
                placeholder={status?.has_bearer_token ? "Token saved" : "Read-scoped Shopify Admin token"}
                type="password"
              />
            </label>
          </div>
          <DashboardButton icon={<Save />} loading={saving} type="submit" variant="primary">
            Save access
          </DashboardButton>
        </form>

        <form className="connectors-generic-form" onSubmit={runTest}>
          <div className="connectors-generic-form-head">
            <strong>2. Preflight</strong>
            <span>Fetch one safe existing order and compare the fields your commerce agent will claim.</span>
          </div>
          <div className="connectors-generic-grid">
            <label>
              <span>Order ID</span>
              <input
                value={form.recordRef}
                onChange={(event) => updateForm("recordRef", event.target.value)}
                placeholder="1001"
                required
              />
            </label>
            <label>
              <span>Match fields</span>
              <input
                value={form.matchFieldsText}
                onChange={(event) => updateForm("matchFieldsText", event.target.value)}
                placeholder="order_id,amount_major,currency,financial_status"
              />
            </label>
            <label className="connectors-generic-wide">
              <span>Claimed JSON</span>
              <textarea
                value={form.claimedJson}
                onChange={(event) => updateForm("claimedJson", event.target.value)}
                rows={7}
              />
            </label>
          </div>
          <DashboardButton disabled={!connected} loading={testing} type="submit" variant="soft">
            Run preflight
          </DashboardButton>
        </form>
      </div>

      {error ? <div className="alert-strip connectors-alert">{error}</div> : null}
      {message ? <div className="connectors-success-strip">{message}</div> : null}
    </section>
  );
}

function ConnectorInspector({
  genericStatus,
  hubspotStatus,
  jiraStatus,
  netsuiteStatus,
  razorpayStatus,
  salesforceStatus,
  shopifyStatus,
  stripePaymentStatus,
  stripeStatus,
  zendeskStatus,
  zohoStatus,
  onGenericStatusChange,
  onHubSpotStatusChange,
  onJiraStatusChange,
  onNetSuiteStatusChange,
  onRazorpayStatusChange,
  onSalesforceStatusChange,
  onShopifyStatusChange,
  onStripePaymentStatusChange,
  onStripeStatusChange,
  onZendeskStatusChange,
  onZohoStatusChange,
  row,
}: {
  genericStatus: GenericRestConnectorStatusResponse | null;
  hubspotStatus: HubSpotCrmConnectorStatusResponse | null;
  jiraStatus: JiraIssueConnectorStatusResponse | null;
  netsuiteStatus: NetSuiteFinanceConnectorStatusResponse | null;
  razorpayStatus: RazorpayRefundConnectorStatusResponse | null;
  salesforceStatus: SalesforceCrmConnectorStatusResponse | null;
  shopifyStatus: ShopifyConnectorStatusResponse | null;
  stripePaymentStatus: StripePaymentConnectorStatusResponse | null;
  stripeStatus: StripeRefundConnectorStatusResponse | null;
  zendeskStatus: ZendeskTicketConnectorStatusResponse | null;
  zohoStatus: ZohoCrmConnectorStatusResponse | null;
  onGenericStatusChange: (status: GenericRestConnectorStatusResponse) => void;
  onHubSpotStatusChange: (status: HubSpotCrmConnectorStatusResponse) => void;
  onJiraStatusChange: (status: JiraIssueConnectorStatusResponse) => void;
  onNetSuiteStatusChange: (status: NetSuiteFinanceConnectorStatusResponse) => void;
  onRazorpayStatusChange: (status: RazorpayRefundConnectorStatusResponse) => void;
  onSalesforceStatusChange: (status: SalesforceCrmConnectorStatusResponse) => void;
  onShopifyStatusChange: (status: ShopifyConnectorStatusResponse) => void;
  onStripePaymentStatusChange: (status: StripePaymentConnectorStatusResponse) => void;
  onStripeStatusChange: (status: StripeRefundConnectorStatusResponse) => void;
  onZendeskStatusChange: (status: ZendeskTicketConnectorStatusResponse) => void;
  onZohoStatusChange: (status: ZohoCrmConnectorStatusResponse) => void;
  row: ConnectorInventoryRow | null;
}) {
  const [setupOpen, setSetupOpen] = useState(false);

  useEffect(() => {
    setSetupOpen(false);
  }, [row?.id]);

  if (!row) {
    return (
      <section className="panel connector-inspector-panel" aria-label="Selected connector">
        <div className="connectors-empty-state">
          <strong>No connector selected</strong>
          <span>Select a verifier or workflow integration to inspect its coverage.</span>
        </div>
      </section>
    );
  }

  const preflight = connectorPreflightSummary(row);

  return (
    <section className="panel connector-inspector-panel" aria-label="Selected connector">
      <div className="connector-inspector-head">
        <div className="connector-inspector-title">
          <ConnectorLogo id={row.id} size={26} />
          <div>
            <span className="dashboard-eyebrow">{connectorInspectorEyebrow(row)}</span>
            <h2>{connectorSystemLabel(row)}</h2>
            <p>{connectorInspectorCopy(row)}</p>
          </div>
        </div>
        <StatusPill value={row.state} label={connectorStateLabel(row.state)} tone={row.tone} />
      </div>

      <div className="connector-simple-status" data-tone={preflight.tone}>
        <div>
          <strong>{preflight.title}</strong>
          <span>{preflight.detail}</span>
        </div>
        <div className="connector-simple-meta">
          <span>
            Updated <strong>{connectorUpdatedLabel(row)}</strong>
          </span>
          <span>
            Verdict <strong>{row.lastVerdict ? humanize(row.lastVerdict) : "None"}</strong>
          </span>
        </div>
      </div>

      <div className="connector-inspector-actions">
        {row.kind === "proof" ? (
          <DashboardButton onClick={() => setSetupOpen(true)} variant="primary">
            {connectorPrimaryCtaLabel(row)}
          </DashboardButton>
        ) : (
          <DashboardButtonLink href={row.href} variant="primary">
            {connectorPrimaryCtaLabel(row)}
          </DashboardButtonLink>
        )}
      </div>

      <details className="connector-advanced-details">
        <summary>
          <span>Details</span>
          <small>Status and fields</small>
        </summary>

        <div className="connector-fact-grid">
          <Fact label="Transport" value={humanize(row.transport)} />
          <Fact label="Template" value={row.templateKind ? humanize(row.templateKind) : "Custom"} />
          <Fact label="Connector type" value={row.metadata.connectorType} />
          <Fact label="Endpoint" value={row.metadata.maskedEndpoint} />
          <Fact label="Credential saved" value={row.metadata.credentialSaved} />
          <Fact label="Health" value={row.healthStatus ? humanize(row.healthStatus) : null} />
          <Fact label="Readiness" value={row.readinessStatus ? humanize(row.readinessStatus) : null} />
          <Fact label="Last verdict" value={row.lastVerdict ? humanize(row.lastVerdict) : null} />
          <Fact label="Updated" value={connectorUpdatedLabel(row)} />
        </div>

        {row.supportedActionTypes.length > 0 ? (
          <div className="connector-action-tags" aria-label="Supported action types">
            {row.supportedActionTypes.map((item) => (
              <span key={item}>{item}</span>
            ))}
          </div>
        ) : null}

        {row.latestCheck ? (
          <div className="connector-details-json">
            <strong>Latest verification check</strong>
            <pre>
              <code>{compactJson(row.latestCheck)}</code>
            </pre>
          </div>
        ) : null}
      </details>

      {row.kind === "proof" ? (
        <details
          className="connector-setup-details"
          open={setupOpen}
          onToggle={(event) => setSetupOpen(event.currentTarget.open)}
        >
          <summary>
            <span>{row.id === "generic_rest" || row.id === "postgres_read" ? "Developer setup" : "Connect access"}</span>
            <small>{row.id === "generic_rest" || row.id === "postgres_read" ? "Manual config" : "Secure setup"}</small>
          </summary>
          {setupOpen ? (
            <div className="connector-setup-body">
              {!SETUP_PANEL_CONNECTOR_IDS.has(row.id) ? (
                <div className="connectors-empty-state">
                  <strong>Advanced setup required</strong>
                  <span>Use Custom REST or request a native connector.</span>
                </div>
              ) : null}
              {row.id === "generic_rest" ? (
                <GenericRestSetupPanel
                  latestCheck={row.latestCheck}
                  onStatusChange={onGenericStatusChange}
                  status={genericStatus}
                />
              ) : null}
              {row.id === "stripe_refund" ? (
                <StripeRefundSetupPanel
                  latestCheck={row.latestCheck}
                  onStatusChange={onStripeStatusChange}
                  status={stripeStatus}
                />
              ) : null}
              {row.id === "stripe_payment" ? (
                <StripePaymentSetupPanel
                  latestCheck={row.latestCheck}
                  onStatusChange={onStripePaymentStatusChange}
                  status={stripePaymentStatus}
                />
              ) : null}
              {row.id === "razorpay_refund" ? (
                <RazorpayRefundSetupPanel
                  latestCheck={row.latestCheck}
                  onStatusChange={onRazorpayStatusChange}
                  status={razorpayStatus}
                />
              ) : null}
              {row.id === "hubspot_crm" ? (
                <HubSpotSetupPanel
                  latestCheck={row.latestCheck}
                  onStatusChange={onHubSpotStatusChange}
                  status={hubspotStatus}
                />
              ) : null}
              {row.id === "salesforce_crm" ? (
                <SalesforceSetupPanel
                  latestCheck={row.latestCheck}
                  onStatusChange={onSalesforceStatusChange}
                  status={salesforceStatus}
                />
              ) : null}
              {row.id === "zoho_crm" ? (
                <ZohoSetupPanel
                  latestCheck={row.latestCheck}
                  onStatusChange={onZohoStatusChange}
                  status={zohoStatus}
                />
              ) : null}
              {row.id === "zendesk_ticket" ? (
                <ZendeskSetupPanel
                  latestCheck={row.latestCheck}
                  onStatusChange={onZendeskStatusChange}
                  status={zendeskStatus}
                />
              ) : null}
              {row.id === "jira_issue" ? (
                <JiraSetupPanel
                  latestCheck={row.latestCheck}
                  onStatusChange={onJiraStatusChange}
                  status={jiraStatus}
                />
              ) : null}
              {row.id === "netsuite_finance" ? (
                <NetSuiteSetupPanel
                  latestCheck={row.latestCheck}
                  onStatusChange={onNetSuiteStatusChange}
                  status={netsuiteStatus}
                />
              ) : null}
              {row.id === "shopify_admin" ? (
                <ShopifySetupPanel
                  latestCheck={row.latestCheck}
                  onStatusChange={onShopifyStatusChange}
                  status={shopifyStatus}
                />
              ) : null}
            </div>
          ) : null}
        </details>
      ) : null}
    </section>
  );
}

export default function IntegrationsPage() {
  const [overview, setOverview] = useState<ConnectorsOverviewState>(initialOverview);
  const [loading, setLoading] = useState(true);
  const [partialFailure, setPartialFailure] = useState(false);
  const [selectedId, setSelectedId] = useState<ConnectorInventoryId | null>(initialConnectorFromUrl);
  const [connectorSearch, setConnectorSearch] = useState("");

  const loadOverview = useCallback(async () => {
    setLoading(true);
    const [
      githubResult,
      slackResult,
      ledgerResult,
      customerResult,
      genericResult,
      stripeResult,
      stripePaymentResult,
      razorpayResult,
      hubspotResult,
      salesforceResult,
      zendeskResult,
      jiraResult,
      netsuiteResult,
      shopifyResult,
      zohoResult,
      postgresResult,
      checksResult,
      registryResult,
    ] = await Promise.allSettled([
      getGithubConnectionStatus(),
      getSlackInstallStatus(),
      getLedgerRefundConnectorStatus(),
      getCustomerRecordConnectorStatus(),
      getGenericRestConnectorStatus(),
      getStripeRefundConnectorStatus(),
      getStripePaymentConnectorStatus(),
      getRazorpayRefundConnectorStatus(),
      getHubSpotCrmConnectorStatus(),
      getSalesforceCrmConnectorStatus(),
      getZendeskTicketConnectorStatus(),
      getJiraIssueConnectorStatus(),
      getNetSuiteFinanceConnectorStatus(),
      getShopifyConnectorStatus(),
      getZohoCrmConnectorStatus(),
      getPostgresReadConnectorStatus(),
      listOutcomeReconciliations({ limit: 50 }),
      getToolRegistry(),
    ]);

    setOverview({
      github: githubResult.status === "fulfilled" ? githubResult.value : null,
      slack: slackResult.status === "fulfilled" ? slackResult.value : null,
      ledger: ledgerResult.status === "fulfilled" ? ledgerResult.value : null,
      customer: customerResult.status === "fulfilled" ? customerResult.value : null,
      generic: genericResult.status === "fulfilled" ? genericResult.value : null,
      stripe: stripeResult.status === "fulfilled" ? stripeResult.value : null,
      stripePayment: stripePaymentResult.status === "fulfilled" ? stripePaymentResult.value : null,
      razorpay: razorpayResult.status === "fulfilled" ? razorpayResult.value : null,
      hubspot: hubspotResult.status === "fulfilled" ? hubspotResult.value : null,
      salesforce: salesforceResult.status === "fulfilled" ? salesforceResult.value : null,
      zendesk: zendeskResult.status === "fulfilled" ? zendeskResult.value : null,
      jira: jiraResult.status === "fulfilled" ? jiraResult.value : null,
      netsuite: netsuiteResult.status === "fulfilled" ? netsuiteResult.value : null,
      shopify: shopifyResult.status === "fulfilled" ? shopifyResult.value : null,
      zoho: zohoResult.status === "fulfilled" ? zohoResult.value : null,
      postgres: postgresResult.status === "fulfilled" ? postgresResult.value : null,
      checks: checksResult.status === "fulfilled" ? checksResult.value.items : [],
      registry: registryResult.status === "fulfilled" ? registryResult.value : null,
    });
    setPartialFailure([
      githubResult,
      slackResult,
      ledgerResult,
      customerResult,
      genericResult,
      stripeResult,
      stripePaymentResult,
      razorpayResult,
      hubspotResult,
      salesforceResult,
      zendeskResult,
      jiraResult,
      netsuiteResult,
      shopifyResult,
      zohoResult,
      postgresResult,
      checksResult,
      registryResult,
    ].some((result) => result.status === "rejected"));
    setLoading(false);
  }, []);

  useEffect(() => {
    void loadOverview();
  }, [loadOverview]);

  const inventory = useMemo(
    () => buildConnectorInventory({ ...overview, partialFailure }),
    [overview, partialFailure],
  );
  const visibleInventory = inventory;

  useEffect(() => {
    if (selectedId && inventory.rows.some((row) => row.id === selectedId)) return;
    setSelectedId(firstSelectedId(visibleInventory));
  }, [inventory, selectedId, visibleInventory]);

  const selectedRow = inventory.rows.find((row) => row.id === selectedId) ?? null;
  const filteredCategoryGroups = useMemo(
    () => filterCategoryGroups(visibleInventory.categoryGroups, connectorSearch),
    [connectorSearch, visibleInventory.categoryGroups],
  );

  return (
    <div className="dashboard-page integrations-page connectors-page">
      <DashboardVerdictHero
        actions={
          <>
            <DashboardButton icon={<RefreshCw />} loading={loading} onClick={() => void loadOverview()} variant="soft">
              Refresh
            </DashboardButton>
            <DashboardButtonLink href={visibleInventory.verdict.ctaHref} variant="primary">
              {visibleInventory.verdict.ctaLabel}
            </DashboardButtonLink>
          </>
        }
        copy="Connect the systems Zroky can read for proof. Keep setup focused: choose a connector, save read-only access, run preflight."
        eyebrow="Connectors"
        icon={<Database />}
        pill="Read-only proof"
        tone="neutral"
        title="Connectors"
        updatedLabel={loading ? "Refreshing" : "Updated live"}
      />

      <DashboardWorkspace
        className="connectors-workspace"
        left={
          <ConnectorInventoryList
            groups={filteredCategoryGroups}
            onSearchQueryChange={setConnectorSearch}
            onSelect={setSelectedId}
            searchQuery={connectorSearch}
            selectedId={selectedId}
          />
        }
        right={
          <ConnectorInspector
            genericStatus={overview.generic}
            hubspotStatus={overview.hubspot}
            jiraStatus={overview.jira}
            netsuiteStatus={overview.netsuite}
            razorpayStatus={overview.razorpay}
            salesforceStatus={overview.salesforce}
            shopifyStatus={overview.shopify}
            stripePaymentStatus={overview.stripePayment}
            stripeStatus={overview.stripe}
            zendeskStatus={overview.zendesk}
            zohoStatus={overview.zoho}
            onGenericStatusChange={(generic) => setOverview((current) => ({ ...current, generic }))}
            onHubSpotStatusChange={(hubspot) => setOverview((current) => ({ ...current, hubspot }))}
            onJiraStatusChange={(jira) => setOverview((current) => ({ ...current, jira }))}
            onNetSuiteStatusChange={(netsuite) => setOverview((current) => ({ ...current, netsuite }))}
            onRazorpayStatusChange={(razorpay) => setOverview((current) => ({ ...current, razorpay }))}
            onSalesforceStatusChange={(salesforce) => setOverview((current) => ({ ...current, salesforce }))}
            onShopifyStatusChange={(shopify) => setOverview((current) => ({ ...current, shopify }))}
            onStripePaymentStatusChange={(stripePayment) => setOverview((current) => ({ ...current, stripePayment }))}
            onStripeStatusChange={(stripe) => setOverview((current) => ({ ...current, stripe }))}
            onZendeskStatusChange={(zendesk) => setOverview((current) => ({ ...current, zendesk }))}
            onZohoStatusChange={(zoho) => setOverview((current) => ({ ...current, zoho }))}
            row={selectedRow}
          />
        }
      />

      <CoverageMap rows={inventory.coverageRows} />

      {partialFailure ? (
        <div className="alert-strip connectors-alert">
          <AlertTriangle aria-hidden="true" />
          Some connector status checks could not load. Coverage is shown from the sources that responded.
        </div>
      ) : null}
    </div>
  );
}
