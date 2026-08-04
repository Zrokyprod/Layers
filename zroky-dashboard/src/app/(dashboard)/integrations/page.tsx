"use client";

import type { FormEvent } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardCheck,
  Copy,
  Database,
  PlugZap,
  Power,
  PowerOff,
  Save,
  Search,
  ShieldCheck,
} from "lucide-react";

import { DashboardButton, DashboardButtonLink } from "@/components/dashboard-button";
import {
  DashboardMetricStrip,
  DashboardVerdictHero,
  DashboardWorkspace,
} from "@/components/dashboard-scaffold";
import { StatusPill } from "@/components/status-pill";
import {
  activateMcpUpstream,
  disableMcpUpstream,
  getGenericRestConnectorStatus,
  getGithubConnectionStatus,
  getHubSpotCrmConnectorStatus,
  getJiraIssueConnectorStatus,
  getMcpUpstreamBinding,
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
  listSourceConnectors,
  listOutcomeReconciliations,
  preflightMcpUpstream,
  saveGenericRestConnectorConfig,
  saveHubSpotCrmConnectorConfig,
  saveJiraIssueConnectorConfig,
  saveMcpUpstreamDraft,
  saveNetSuiteFinanceConnectorConfig,
  savePostgresReadConnectorConfig,
  saveRazorpayRefundConnectorConfig,
  saveSalesforceCrmConnectorConfig,
  saveShopifyConnectorConfig,
  saveStripePaymentConnectorConfig,
  saveStripeRefundConnectorConfig,
  saveZendeskTicketConnectorConfig,
  saveZohoCrmConnectorConfig,
  startJiraIssueOAuth,
  startZohoCrmOAuth,
  startSlackInstall,
  testGenericRestConnector,
  testHubSpotCrmConnector,
  testJiraIssueConnector,
  testNetSuiteFinanceConnector,
  testPostgresReadConnector,
  testRazorpayRefundConnector,
  testSalesforceCrmConnector,
  testShopifyConnector,
  testStripePaymentConnector,
  testStripeRefundConnector,
  testZendeskTicketConnector,
  testZohoCrmConnector,
  upsertSourceConnector,
  type GenericRestConnectorStatusResponse,
  type HubSpotCrmConnectorStatusResponse,
  type JiraIssueConnectorStatusResponse,
  type McpUpstreamBindingResponse,
  type NetSuiteFinanceConnectorStatusResponse,
  type OutcomeReconciliationView,
  type PostgresReadConnectorStatusResponse,
  type RazorpayRefundConnectorStatusResponse,
  type SalesforceCrmConnectorStatusResponse,
  type ShopifyConnectorStatusResponse,
  type StripePaymentConnectorStatusResponse,
  type StripeRefundConnectorStatusResponse,
  type SourceConnector,
  type ToolRegistryResponse,
  type ZendeskTicketConnectorStatusResponse,
  type ZohoCrmConnectorStatusResponse,
} from "@/lib/api";
import {
  buildConnectorInventory,
  connectorStateLabel,
  connectorUpdatedLabel,
  LAUNCH_VISIBLE_CONNECTOR_IDS,
  type ConnectorCategoryGroup,
  type ConnectorInventory,
  type ConnectorInventoryId,
  type ConnectorInventoryRow,
} from "@/lib/connector-inventory";
import { ConnectorLogo } from "@/lib/connector-logo";
import {
  CONFIGURABLE_CONNECTOR_IDS,
  connectorSetupProfile,
} from "@/lib/connector-setup-profile";
import { externalNavigator } from "@/lib/external-navigation";
import { compactJson, formatCount, humanize } from "@/lib/format";
import type {
  GithubConnectionStatusResponse,
  SlackInstallStatusResponse,
} from "@/lib/types";

type ConnectorsOverviewState = {
  mcp: McpUpstreamBindingResponse | null;
  github: GithubConnectionStatusResponse | null;
  slack: SlackInstallStatusResponse | null;
  stripe: StripeRefundConnectorStatusResponse | null;
  stripePayment: StripePaymentConnectorStatusResponse | null;
  razorpay: RazorpayRefundConnectorStatusResponse | null;
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

type McpUpstreamFormState = {
  endpointUrl: string;
  credentialId: string;
  allowedToolsText: string;
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

type PostgresFormState = {
  databaseUrl: string;
  readQuery: string;
  systemRef: string;
  paramsJson: string;
  actionType: string;
  claimedJson: string;
  matchFieldsText: string;
};

const initialOverview: ConnectorsOverviewState = {
  mcp: null,
  github: null,
  slack: null,
  stripe: null,
  stripePayment: null,
  razorpay: null,
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

const defaultMcpUpstreamForm: McpUpstreamFormState = {
  endpointUrl: "",
  credentialId: "",
  allowedToolsText: "",
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

const defaultPostgresForm: PostgresFormState = {
  databaseUrl: "",
  readQuery: "",
  systemRef: "record_1001",
  paramsJson: JSON.stringify({ record_id: "record_1001" }, null, 2),
  actionType: "database_record_update",
  claimedJson: JSON.stringify(
    {
      record_id: "record_1001",
      status: "approved",
    },
    null,
    2,
  ),
  matchFieldsText: "record_id,status",
};

const ADVANCED_CONNECTOR_IDS = new Set<ConnectorInventoryId>([
  "generic_rest",
  "ledger_template",
  "customer_template",
  "postgres_read",
]);

const SETUP_PANEL_CONNECTOR_IDS = new Set<ConnectorInventoryId>([
  "mcp_upstream",
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
  "postgres_read",
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

function parseSqlParams(value: string): Record<string, string | number | boolean | null> {
  const parsed = parseClaimedJson(value);
  const entries = Object.entries(parsed);
  if (entries.some(([, item]) => item !== null && !["string", "number", "boolean"].includes(typeof item))) {
    throw new Error("Query params must contain only strings, numbers, booleans, or null.");
  }
  return parsed as Record<string, string | number | boolean | null>;
}

function matchFieldsFromText(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function mcpToolsFromText(value: string): string[] {
  return [...new Set(value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean))];
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

function statusValue(row: ConnectorInventoryRow) {
  return row.state;
}

function connectorSearchText(row: ConnectorInventoryRow): string {
  const setupProfile = connectorSetupProfile(row.id);
  return [
    row.title,
    row.category,
    row.description,
    row.transport,
    row.templateKind,
    row.statusLabel,
    row.detail,
    row.metadata.connectorType,
    row.metadata.manifestId,
    row.metadata.maskedEndpoint,
    setupProfile.methodLabel,
    setupProfile.requirement,
    setupProfile.detail,
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
  if (row.id === "generic_rest") return "Connect custom REST";
  if (row.id === "postgres_read") return "Connect database";
  if (row.id === "ledger_template" || row.id === "customer_template") return "Connect template";
  return `${row.connected ? "Manage" : "Connect"} ${connectorSystemLabel(row)}`;
}

function stripeStatusFromSourceConnector(connector: SourceConnector | undefined): StripeRefundConnectorStatusResponse | null {
  if (!connector || connector.status !== "active") return null;
  return {
    connected: true,
    connector_type: "stripe_refund",
    base_url: null,
    path_template: null,
    record_path: null,
    query: null,
    has_bearer_token: true,
    bearer_token_last4: null,
    last_tested_at: null,
    health_status: "",
    last_verdict: null,
    last_error: null,
    last_error_code: null,
    last_http_status: null,
    last_attempts: null,
    last_retryable: null,
    last_checked_at: null,
    readiness: { status: "not_ready" },
    created_at: connector.created_at,
    updated_at: connector.updated_at,
  };
}

function connectorSystemLabel(row: ConnectorInventoryRow): string {
  if (row.id === "mcp_upstream") return "MCP Upstream";
  if (row.id === "generic_rest") return "Custom REST API";
  if (row.id === "postgres_read") return "SQL database";
  if (row.id === "stripe_refund" || row.id === "stripe_payment") return "Stripe";
  if (row.id === "razorpay_refund") return "Razorpay";
  return row.title
    .replace(/\s+verifier$/i, "")
    .replace(/\s+template$/i, "");
}

function connectorCardMeta(row: ConnectorInventoryRow): string {
  return connectorSetupProfile(row.id).cardLabel;
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
        meta: hasRefunds && hasPayments
          ? "Restricted key / Refunds + payments"
          : hasPayments
            ? "Restricted key / Payments"
            : "Restricted key / Refunds",
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

function ConnectorOneClickFlow() {
  const steps = [
    ["Authorize read-only", "Grant read-only access"],
    ["Validate manifest", "Verify schema & permissions"],
    ["Run test-read", "Execute safe dry-run"],
    ["Bind workflow", "Attach to workflows"],
  ];

  return (
    <ol className="connectors-one-click-flow" aria-label="One-click connector setup flow">
      {steps.map(([step, detail], index) => (
        <li key={step}>
          <span>{index + 1}</span>
          <strong>{step}</strong>
          <small>{detail}</small>
        </li>
      ))}
    </ol>
  );
}

function ConnectorReadinessStrip({ inventory }: { inventory: ConnectorInventory }) {
  const counts = inventory.counts;
  const connectedSources = Math.max(
    0,
    counts.proofTotal - counts.notConfigured,
  );
  const coverageTone =
    counts.actionTypesTotal === 0
      ? "neutral"
      : counts.unverifiableActionTypes > 0
        ? "warning"
        : "success";

  return (
    <DashboardMetricStrip
      ariaLabel="Connector readiness"
      className="connectors-readiness-strip"
      columns={6}
      metrics={[
        {
          id: "connected",
          label: "Connected sources",
          value: formatCount(connectedSources),
          helper: "read-only proof access saved",
          icon: <PlugZap aria-hidden="true" />,
          tone: connectedSources > 0 ? "success" : "warning",
        },
        {
          id: "ready",
          label: "Test-read ready",
          value: formatCount(counts.healthyVerifiers),
          helper: "source reads passing",
          icon: <CheckCircle2 aria-hidden="true" />,
          tone: counts.healthyVerifiers > 0 ? "success" : "neutral",
        },
        {
          id: "needs-test",
          label: "Needs test-read",
          value: formatCount(counts.notTested),
          helper: "connected but not proven",
          icon: <ClipboardCheck aria-hidden="true" />,
          tone: counts.notTested > 0 ? "warning" : "neutral",
        },
        {
          id: "blocked",
          label: "Blocked",
          value: formatCount(counts.failingVerifiers),
          helper: "mismatch or source failure",
          icon: <AlertTriangle aria-hidden="true" />,
          tone: counts.failingVerifiers > 0 ? "danger" : "neutral",
        },
        {
          id: "coverage",
          label: "Coverage",
          value: `${counts.coveragePercent}%`,
          helper: `${formatCount(counts.actionTypesTotal)} action types observed`,
          icon: <ShieldCheck aria-hidden="true" />,
          tone: coverageTone,
        },
        {
          id: "unconfigured",
          label: "Unconfigured",
          value: formatCount(counts.notConfigured),
          helper: "available proof presets",
          icon: <Database aria-hidden="true" />,
          tone: counts.notConfigured > 0 ? "warning" : "success",
        },
      ]}
    />
  );
}

function connectorScopeLabel(row: ConnectorInventoryRow): string {
  if (row.id === "stripe_refund" || row.id === "stripe_payment") return "Payments · Transactions · Refunds";
  if (row.id === "razorpay_refund") return "Payments · Payouts · Refunds";
  if (row.id === "shopify_admin") return "Orders · Refunds · Discounts";
  if (row.id === "hubspot_crm") return "Deals · Contacts · Activities";
  if (row.id === "salesforce_crm") return "Accounts · Opportunities · Cases";
  if (row.id === "zendesk_ticket") return "Tickets · Comments · Status";
  if (row.id === "jira_issue") return "Issues · Transitions · Fields";
  if (row.id === "postgres_read") return "Tables · Records · Audit fields";
  return row.supportedActionTypes.slice(0, 3).map((item) => humanize(item)).join(" · ") || connectorCardMeta(row);
}

function connectorPrimitiveLabel(row: ConnectorInventoryRow): string {
  if (row.id === "stripe_refund") return "refunds.retrieve";
  if (row.id === "stripe_payment") return "payments.retrieve";
  if (row.id === "razorpay_refund") return "refunds.fetch";
  if (row.id === "shopify_admin") return "orders.get";
  if (row.id === "hubspot_crm") return "crm.objects.get";
  if (row.id === "salesforce_crm") return "sobjects.retrieve";
  if (row.id === "zendesk_ticket") return "tickets.show";
  if (row.id === "jira_issue") return "issues.get";
  if (row.id === "postgres_read") return "select.read";
  return row.id === "generic_rest" ? "generic_rest.read" : humanize(row.transport);
}

function connectorInspectorStatus(row: ConnectorInventoryRow) {
  if (row.state === "missing") return { label: "Missing / Not connected", tone: "danger" as const };
  return { label: connectorStateLabel(row.state), tone: row.tone };
}

function ConnectorSetupMatrix({
  onConnect,
  row,
}: {
  onConnect: () => void;
  row: ConnectorInventoryRow;
}) {
  const manifestLoaded = row.metadata.manifestId != null && row.metadata.manifestId !== "";
  const canConfigure = row.kind === "proof" && row.connected;
  const canRunTestRead = canConfigure;
  const canBindWorkflow = canConfigure && row.state === "ready";
  const cards = [
    {
      action: "Edit",
      disabled: !canConfigure,
      detail: row.supportedActionTypes.length > 0 ? connectorScopeLabel(row) : "Read-only verifier scope",
      icon: <ShieldCheck aria-hidden="true" />,
      title: "Read-only scope",
      reason: "Connect source first",
      onClick: onConnect,
    },
    {
      action: "Run test-read",
      disabled: !canRunTestRead,
      detail: row.connected ? (row.lastVerdict ? humanize(row.lastVerdict) : "Ready to execute") : "Not executed",
      icon: <Search aria-hidden="true" />,
      title: "Test-read",
      reason: "Connect source first",
      onClick: onConnect,
    },
    {
      action: "Bind",
      disabled: !canBindWorkflow,
      detail: row.readinessStatus ? humanize(row.readinessStatus) : "Not bound to any workflow",
      icon: <PlugZap aria-hidden="true" />,
      title: "Workflow binding",
      reason: row.connected ? "Run a passing test-read first" : "Connect source first",
      onClick: onConnect,
    },
    {
      action: manifestLoaded ? "View manifest" : "Upload manifest",
      disabled: !manifestLoaded,
      detail: manifestLoaded ? String(row.metadata.manifestId) : "No manifest loaded",
      icon: <ClipboardCheck aria-hidden="true" />,
      title: "Manifest",
      reason: "Manifest upload is not wired yet",
      onClick: onConnect,
    },
  ];

  return (
    <div className="connector-setup-matrix" aria-label="Selected verifier setup status">
      {cards.map((card) => (
        <article className="connector-setup-card" key={card.title}>
          <span className="connector-setup-icon">{card.icon}</span>
          <div>
            <strong>{card.title}</strong>
            <small>{card.detail}</small>
          </div>
          <DashboardButton
            disabled={card.disabled}
            onClick={card.onClick}
            size="sm"
            title={card.disabled ? card.reason : undefined}
            variant="soft"
          >
            {card.action}
          </DashboardButton>
        </article>
      ))}
    </div>
  );
}

function SourceAudit({
  rows,
}: {
  rows: ConnectorInventoryRow[];
}) {
  const auditRows = rows
    .filter((row) => row.latestCheck)
    .sort((left, right) => Date.parse(right.latestCheck?.checked_at ?? "") - Date.parse(left.latestCheck?.checked_at ?? ""))
    .slice(0, 8)
    .map((row) => ({ ...row, updatedAt: row.latestCheck?.checked_at ?? row.updatedAt }));

  return (
    <section className="panel connectors-source-audit-panel" aria-label="Recent test-reads">
      <div className="connectors-source-audit-head">
        <div>
          <h2>Recent test-reads</h2>
          <p>Recent connector activity and test-read attempts</p>
        </div>
      </div>

      <div className="connectors-source-audit-table">
        <div className="connectors-source-audit-row connectors-source-audit-row-head">
          <span>System</span>
          <span>Primitive</span>
          <span>Status</span>
          <span>Last read</span>
        </div>
        {auditRows.length === 0 ? <div className="connectors-source-audit-empty">No test-reads yet.</div> : null}
        {auditRows.map((row) => (
          <div className="connectors-source-audit-row" key={row.id}>
            <strong>{connectorSystemLabel(row)}</strong>
            <span>{connectorPrimitiveLabel(row)}</span>
            <StatusPill value={row.lastVerdict ?? row.state} label={row.lastVerdict ? humanize(row.lastVerdict) : connectorStateLabel(row.state)} tone={row.tone} />
            <span>{row.updatedAt ? connectorUpdatedLabel(row) : "—"}</span>
          </div>
        ))}
      </div>
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
    <section className="panel connectors-inventory-panel" aria-label="Connector inventory" id="connector-catalog">
      <div className="connectors-section-head">
        <div>
          <span className="dashboard-eyebrow">Connectors</span>
          <h2>Available systems</h2>
        </div>
      </div>

      <label className="connector-search-field">
        <Search aria-hidden="true" />
        <span className="sr-only">Search connectors</span>
        <input
          aria-label="Search connectors"
          placeholder="Search systems, OAuth, API keys, or action types..."
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
                {cards.map((card) => {
                  const selected = selectedId != null && card.ids.includes(selectedId);
                  return (
                    <button
                      type="button"
                      className="connector-inventory-row"
                      data-selected={selected}
                      data-tone={card.row.tone}
                      key={card.key}
                      onClick={() => onSelect(card.row.id)}
                    >
                      <ConnectorLogo id={card.logoId} />
                      <span className="connector-row-main">
                        <strong>{card.title}</strong>
                        <small>{connectorScopeLabel(card.row)}</small>
                      </span>
                      <span className="connector-row-status">
                        <span className="connector-availability-pill" data-selected={selected}>
                          {selected ? "Selected" : "Available"}
                        </span>
                      </span>
                    </button>
                  );
                })}
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

const STRIPE_REFUND_READ_CAPABILITY = "stripe_refund.read";

function StripeRefundPullSetupPanel() {
  const [environment, setEnvironment] = useState("production");
  const [connector, setConnector] = useState<SourceConnector | null>(null);
  const [secretRef, setSecretRef] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setMessage(null);
    void listSourceConnectors(
      { environment, capability: STRIPE_REFUND_READ_CAPABILITY },
      controller.signal,
    )
      .then(({ items }) => {
        const current = items[0] ?? null;
        setConnector(current);
        setSecretRef(current?.secret_ref ?? "");
      })
      .catch((err) => {
        if (!controller.signal.aborted) {
          setError(err instanceof Error ? err.message : "Failed to load automatic source check.");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [environment]);

  const save = async (status: "active" | "disabled") => {
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const saved = await upsertSourceConnector({
        environment,
        capability: STRIPE_REFUND_READ_CAPABILITY,
        connector_kind: "stripe",
        secret_ref: status === "disabled" ? connector?.secret_ref ?? secretRef : secretRef,
        config: {},
        status,
      });
      setConnector(saved);
      setMessage(status === "active" ? "Automatic source checks enabled." : "Automatic source checks disabled.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update automatic source check.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="connectors-generic-panel" aria-label="Stripe refund automatic source check">
      <div className="connectors-section-head">
        <div>
          <span className="dashboard-eyebrow">Automatic source check</span>
          <h2>Pull Stripe refund proof</h2>
          <p>Let Zroky read Stripe when an outcome needs fresh proof.</p>
        </div>
        <StatusPill value={connector?.status ?? "not_configured"} />
      </div>
      <form
        className="connectors-generic-form"
        onSubmit={(event) => {
          event.preventDefault();
          void save("active");
        }}
      >
        <div className="connectors-generic-form-head">
          <strong>3. Automatic source check</strong>
          <span>Zroky stores the variable name, never the Stripe key.</span>
        </div>
        <label>
          <span>Environment</span>
          <select disabled={loading || saving} onChange={(event) => setEnvironment(event.target.value)} value={environment}>
            <option value="production">production</option>
            <option value="staging">staging</option>
            <option value="development">development</option>
          </select>
        </label>
        <label>
          <span>Credential environment variable</span>
          <input
            autoComplete="off"
            disabled={loading || saving}
            onChange={(event) => setSecretRef(event.target.value)}
            pattern="[A-Z_][A-Z0-9_]*"
            placeholder="STRIPE_KEY_PROJ_ABC"
            required
            title="Use an uppercase environment variable name, not a Stripe key."
            value={secretRef}
          />
        </label>
        <DashboardButton disabled={loading || saving || !secretRef} icon={<Power />} loading={saving} type="submit">
          {connector?.status === "active" ? "Save automatic checks" : "Enable automatic checks"}
        </DashboardButton>
        {connector?.status === "active" ? (
          <DashboardButton disabled={saving} icon={<PowerOff />} onClick={() => void save("disabled")} type="button" variant="soft">
            Disable automatic checks
          </DashboardButton>
        ) : null}
      </form>
      {message ? <div className="connectors-success-strip">{message}</div> : null}
      {error ? <div className="alert-strip connectors-alert">{error}</div> : null}
    </section>
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

function PostgresReadSetupPanel({
  onStatusChange,
  status,
}: {
  onStatusChange: (status: PostgresReadConnectorStatusResponse) => void;
  status: PostgresReadConnectorStatusResponse | null;
}) {
  const [form, setForm] = useState<PostgresFormState>(defaultPostgresForm);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const updateForm = (key: keyof PostgresFormState, value: string) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const saveConfig = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const result = await savePostgresReadConnectorConfig({
        database_url: form.databaseUrl.trim() || undefined,
        read_query: form.readQuery.trim(),
      });
      onStatusChange(result);
      setForm((current) => ({ ...current, databaseUrl: "" }));
      setMessage("Read-only database access saved. Run preflight with a real record.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save database access.");
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
      const result = await testPostgresReadConnector({
        action_type: form.actionType.trim() || null,
        claimed: parseClaimedJson(form.claimedJson),
        match_fields: matchFieldsFromText(form.matchFieldsText),
        params: parseSqlParams(form.paramsJson),
        system_ref: form.systemRef.trim() || null,
      });
      onStatusChange(result.connector);
      setMessage(result.ok ? "Database preflight matched the claimed record." : "Database preflight completed without a match.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Database preflight failed.");
    } finally {
      setTesting(false);
    }
  };

  const canSave = Boolean(
    form.readQuery.trim()
      && (form.databaseUrl.trim() || status?.has_database_url),
  );

  return (
    <section className="connectors-generic-panel" aria-label="Postgres read verifier setup">
      <div className="connectors-section-head">
        <div>
          <h2>SQL database</h2>
          <p>Read one business record through a dedicated read-only database role.</p>
        </div>
      </div>

      <div className="connectors-generic-layout">
        <form className="connectors-generic-form" onSubmit={saveConfig}>
          <div className="connectors-generic-form-head">
            <strong>1. Read-only access</strong>
            <span>Database credentials are encrypted and never rendered again.</span>
          </div>
          <div className="connectors-generic-grid">
            <label className="connectors-generic-wide">
              <span>Database URL</span>
              <input
                aria-label="Read-only database URL"
                autoComplete="off"
                onChange={(event) => updateForm("databaseUrl", event.target.value)}
                placeholder={status?.has_database_url ? "Database URL saved" : "postgresql://readonly_user:..."}
                type="password"
                value={form.databaseUrl}
              />
            </label>
            <label className="connectors-generic-wide">
              <span>Parameterized SELECT query</span>
              <textarea
                aria-label="Parameterized SELECT query"
                onChange={(event) => updateForm("readQuery", event.target.value)}
                placeholder={status?.has_read_query ? "Enter a replacement SELECT query" : "SELECT id, status FROM records WHERE id = :record_id"}
                rows={4}
                value={form.readQuery}
              />
            </label>
          </div>
          <DashboardButton disabled={!canSave} loading={saving} type="submit" variant="primary">
            Save database access
          </DashboardButton>
        </form>

        <form className="connectors-generic-form" onSubmit={runTest}>
          <div className="connectors-generic-form-head">
            <strong>2. Preflight</strong>
            <span>Use a real record reference and compare only stable fields.</span>
          </div>
          <div className="connectors-generic-grid">
            <label>
              <span>System reference</span>
              <input value={form.systemRef} onChange={(event) => updateForm("systemRef", event.target.value)} />
            </label>
            <label>
              <span>Action type</span>
              <input value={form.actionType} onChange={(event) => updateForm("actionType", event.target.value)} />
            </label>
            <label className="connectors-generic-wide">
              <span>Query params JSON</span>
              <textarea
                aria-label="Query params JSON"
                rows={3}
                value={form.paramsJson}
                onChange={(event) => updateForm("paramsJson", event.target.value)}
              />
            </label>
            <label className="connectors-generic-wide">
              <span>Claimed JSON</span>
              <textarea
                aria-label="Database claimed JSON"
                rows={4}
                value={form.claimedJson}
                onChange={(event) => updateForm("claimedJson", event.target.value)}
              />
            </label>
            <label className="connectors-generic-wide">
              <span>Match fields</span>
              <input
                aria-label="Database match fields"
                value={form.matchFieldsText}
                onChange={(event) => updateForm("matchFieldsText", event.target.value)}
              />
            </label>
          </div>
          <DashboardButton disabled={!status?.connected} loading={testing} type="submit" variant="soft">
            Run database preflight
          </DashboardButton>
        </form>
      </div>

      {message ? <div className="connectors-success-strip">{message}</div> : null}
      {error ? <div className="alert-strip connectors-alert">{error}</div> : null}
    </section>
  );
}

function McpUpstreamSetupPanel({
  onStatusChange,
  status,
}: {
  onStatusChange: (status: McpUpstreamBindingResponse) => void;
  status: McpUpstreamBindingResponse | null;
}) {
  const [form, setForm] = useState<McpUpstreamFormState>(defaultMcpUpstreamForm);
  const [discoveredTools, setDiscoveredTools] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [activating, setActivating] = useState(false);
  const [disabling, setDisabling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!status) return;
    setForm((current) => ({
      ...current,
      endpointUrl: status.endpoint_url,
      allowedToolsText: status.allowed_tools.join("\n"),
    }));
  }, [status]);

  const runAction = async (
    action: () => Promise<McpUpstreamBindingResponse>,
    setLoading: (value: boolean) => void,
    successMessage: string,
  ) => {
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      const nextStatus = await action();
      onStatusChange(nextStatus);
      setMessage(successMessage);
    } catch (err) {
      setError(err instanceof Error ? err.message : "MCP upstream operation failed.");
    } finally {
      setLoading(false);
    }
  };

  const saveDraft = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const allowedTools = mcpToolsFromText(form.allowedToolsText);
    await runAction(
      () => saveMcpUpstreamDraft({
        endpoint_url: form.endpointUrl.trim(),
        protocol_version: "2025-06-18",
        bearer_credential_id: form.credentialId.trim() || null,
        allowed_tools: allowedTools,
      }),
      setSaving,
      "Draft saved. Run preflight before activation.",
    );
    setForm((current) => ({ ...current, credentialId: "" }));
  };

  const runPreflight = async () => {
    setTesting(true);
    setError(null);
    setMessage(null);
    try {
      const result = await preflightMcpUpstream();
      onStatusChange(result.binding);
      setDiscoveredTools(result.discovered_tools);
      if (result.binding.test_status === "succeeded") {
        setMessage(`Preflight passed. ${result.discovered_tools.length} upstream tools discovered.`);
      } else {
        setError(result.binding.last_test_error ?? "Upstream preflight failed.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "MCP upstream preflight failed.");
    } finally {
      setTesting(false);
    }
  };

  const isActive = status?.status === "active";
  const canActivate = status?.test_status === "succeeded" && !isActive;

  return (
    <section className="connectors-generic-panel" aria-label="MCP upstream setup">
      <div className="connectors-section-head">
        <div>
          <span className="dashboard-eyebrow">MCP upstream</span>
          <h2>Put Zroky in the agent tool path</h2>
          <p>Connect one MCP server, verify its tool inventory, then activate the tenant-scoped gateway.</p>
        </div>
        <StatusPill value={status?.status ?? "not_configured"} tone={isActive ? "success" : "neutral"} />
      </div>

      <form className="connectors-generic-form" onSubmit={saveDraft}>
        <div className="connectors-generic-form-head">
          <strong>1. Draft configuration</strong>
          <span>Only a managed credential reference is accepted here. Secret values never render in this form.</span>
        </div>
        <div className="connectors-generic-grid">
          <label className="connectors-generic-wide">
            <span>Upstream endpoint</span>
            <input
              type="url"
              value={form.endpointUrl}
              onChange={(event) => setForm((current) => ({ ...current, endpointUrl: event.target.value }))}
              placeholder="https://mcp.example.com/mcp"
              required
            />
          </label>
          <label>
            <span>Managed credential ID</span>
            <input
              value={form.credentialId}
              onChange={(event) => setForm((current) => ({ ...current, credentialId: event.target.value }))}
              placeholder={status?.credential_configured ? "Credential configured" : "Optional credential reference"}
            />
          </label>
          <label className="connectors-generic-wide">
            <span>Allowed tools</span>
            <textarea
              value={form.allowedToolsText}
              onChange={(event) => setForm((current) => ({ ...current, allowedToolsText: event.target.value }))}
              placeholder={"refund.create\naccount.disable"}
              rows={5}
              required
            />
          </label>
        </div>
        <DashboardButton icon={<Save />} loading={saving} type="submit" variant="primary">
          Save draft
        </DashboardButton>
      </form>

      <div className="connectors-generic-form">
        <div className="connectors-generic-form-head">
          <strong>2. Verify and activate</strong>
          <span>Preflight initializes the MCP session and checks that every allowed tool exists upstream.</span>
        </div>
        <div className="connectors-rest-actions">
          <DashboardButton disabled={!status || isActive} icon={<ShieldCheck />} loading={testing} onClick={() => void runPreflight()} variant="soft">
            Run preflight
          </DashboardButton>
          <DashboardButton
            disabled={!canActivate}
            icon={<Power />}
            loading={activating}
            onClick={() => void runAction(activateMcpUpstream, setActivating, "MCP upstream activated.")}
            variant="primary"
          >
            Activate
          </DashboardButton>
          <DashboardButton
            disabled={!isActive}
            icon={<PowerOff />}
            loading={disabling}
            onClick={() => void runAction(disableMcpUpstream, setDisabling, "MCP upstream disabled.")}
            variant="soft"
          >
            Disable
          </DashboardButton>
        </div>
        <div className="connector-fact-grid">
          <Fact label="Preflight" value={status ? humanize(status.test_status) : null} />
          <Fact label="Protocol" value={status?.protocol_version ?? null} />
          <Fact label="Credential" value={status?.credential_configured ? "Managed reference saved" : "None"} />
          <Fact label="Version" value={status ? String(status.version) : null} />
        </div>
        {discoveredTools.length > 0 ? (
          <div className="connector-action-tags" aria-label="Discovered MCP tools">
            {discoveredTools.map((tool) => <span key={tool}>{tool}</span>)}
          </div>
        ) : null}
      </div>

      {error ? <div className="alert-strip connectors-alert">{error}</div> : null}
      {message ? <div className="connectors-success-strip">{message}</div> : null}
    </section>
  );
}

function ConnectorInspector({
  mcpStatus,
  genericStatus,
  hubspotStatus,
  jiraStatus,
  netsuiteStatus,
  postgresStatus,
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
  onPostgresStatusChange,
  onRazorpayStatusChange,
  onSalesforceStatusChange,
  onShopifyStatusChange,
  onStripePaymentStatusChange,
  onStripeStatusChange,
  onZendeskStatusChange,
  onZohoStatusChange,
  onMcpStatusChange,
  row,
  setupRequest,
}: {
  mcpStatus: McpUpstreamBindingResponse | null;
  genericStatus: GenericRestConnectorStatusResponse | null;
  hubspotStatus: HubSpotCrmConnectorStatusResponse | null;
  jiraStatus: JiraIssueConnectorStatusResponse | null;
  netsuiteStatus: NetSuiteFinanceConnectorStatusResponse | null;
  postgresStatus: PostgresReadConnectorStatusResponse | null;
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
  onPostgresStatusChange: (status: PostgresReadConnectorStatusResponse) => void;
  onRazorpayStatusChange: (status: RazorpayRefundConnectorStatusResponse) => void;
  onSalesforceStatusChange: (status: SalesforceCrmConnectorStatusResponse) => void;
  onShopifyStatusChange: (status: ShopifyConnectorStatusResponse) => void;
  onStripePaymentStatusChange: (status: StripePaymentConnectorStatusResponse) => void;
  onStripeStatusChange: (status: StripeRefundConnectorStatusResponse) => void;
  onZendeskStatusChange: (status: ZendeskTicketConnectorStatusResponse) => void;
  onZohoStatusChange: (status: ZohoCrmConnectorStatusResponse) => void;
  onMcpStatusChange: (status: McpUpstreamBindingResponse) => void;
  row: ConnectorInventoryRow | null;
  setupRequest: number;
}) {
  const [setupOpen, setSetupOpen] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  useEffect(() => {
    setSetupOpen(false);
    setConnectionError(null);
  }, [row?.id]);

  useEffect(() => {
    if (setupRequest > 0 && row?.kind === "proof") setSetupOpen(true);
  }, [row?.kind, setupRequest]);

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

  const status = connectorInspectorStatus(row);
  const setupProfile = connectorSetupProfile(row.id);
  const accessStatus = row.connected ? "Saved" : setupProfile.oneClick ? "Authorization required" : "Credential required";
  const accessScope =
    row.id === "mcp_upstream"
      ? "Policy-gated execution"
      : row.kind === "support"
        ? "Workflow delivery"
        : "Read-only proof";
  const needsOneClickAuthorization =
    setupProfile.oneClick && (!row.connected || (row.id === "jira_issue" && !jiraStatus?.has_oauth_refresh_token));

  const startOneClickConnect = async () => {
    setConnecting(true);
    setConnectionError(null);
    try {
      if (row.id === "github") {
        externalNavigator.assign("/api/zroky/v1/settings/github/connect/start");
        return;
      }
      if (row.id === "slack") {
        externalNavigator.assign("/api/zroky/v1/settings/slack/connect/start");
        return;
      }
      if (row.id === "zoho_crm" || row.id === "jira_issue") {
        setSetupOpen(true);
        return;
      }
      if (row.href) externalNavigator.assign(row.href);
    } finally {
      setConnecting(false);
    }
  };

  return (
    <section className="panel connector-inspector-panel" aria-label="Selected connector">
      <div className="connector-inspector-head">
        <div className="connector-inspector-title">
          <ConnectorLogo id={row.id} size={26} />
          <div>
            <h2>{connectorSystemLabel(row)}</h2>
            <p>{connectorScopeLabel(row)}</p>
          </div>
        </div>
        <StatusPill value={row.state} label={status.label} tone={status.tone} />
      </div>

      <div className="connector-launch-grid" aria-label="Connector access requirements">
        <article>
          <span>Setup method</span>
          <strong>{setupProfile.methodLabel}</strong>
          <span>{setupProfile.oneClick ? "No credential copy and paste." : "Secure form setup."}</span>
        </article>
        <article>
          <span>Access needed</span>
          <strong>{setupProfile.requirement}</strong>
          <span>{setupProfile.detail}</span>
        </article>
        <article>
          <span>Current access</span>
          <strong>{accessStatus}</strong>
          <span>{accessScope}</span>
        </article>
      </div>

      <div className="connector-inspector-actions">
        {needsOneClickAuthorization ? (
          <>
            <DashboardButton loading={connecting} onClick={() => void startOneClickConnect()} variant="primary">
              {connectorPrimaryCtaLabel(row)}
            </DashboardButton>
            {row.id === "zoho_crm" || row.id === "jira_issue" ? (
              <DashboardButton onClick={() => setSetupOpen(true)} variant="soft">
                Use manual access
              </DashboardButton>
            ) : null}
          </>
        ) : row.kind === "proof" || row.id === "mcp_upstream" ? (
          <DashboardButton onClick={() => setSetupOpen(true)} variant="primary">
            {connectorPrimaryCtaLabel(row)}
          </DashboardButton>
        ) : (
          <DashboardButtonLink
            href={row.id === "github" ? "/api/zroky/v1/settings/github/connect/start" : row.href}
            variant="primary"
          >
            {connectorPrimaryCtaLabel(row)}
          </DashboardButtonLink>
        )}
      </div>

      <ConnectorSetupMatrix onConnect={() => setSetupOpen(true)} row={row} />

      <details className="connector-advanced-details" open>
        <summary>
          <span>Details</span>
          <small>Status and fields</small>
        </summary>

        <div className="connector-fact-grid">
          <Fact label="Transport" value={humanize(row.transport)} />
          <Fact label="Template" value={row.templateKind ? humanize(row.templateKind) : "Custom"} />
          <Fact label="Auth method" value={row.metadata.connectorType ?? "API key"} />
          <Fact label="Connector type" value={row.metadata.connectorType} />
          <Fact label="Base URL" value={row.metadata.maskedEndpoint} />
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

      {row.kind === "proof" || row.id === "mcp_upstream" ? (
        <details
          className="connector-setup-details"
          open={setupOpen}
          onToggle={(event) => setSetupOpen(event.currentTarget.open)}
        >
          <summary>
            <span>One-click setup</span>
            <small>Read-only access · test-read · workflow binding</small>
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
                <>
                  <StripeRefundSetupPanel
                    latestCheck={row.latestCheck}
                    onStatusChange={onStripeStatusChange}
                    status={stripeStatus}
                  />
                  <StripeRefundPullSetupPanel />
                </>
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
              {row.id === "postgres_read" ? (
                <PostgresReadSetupPanel
                  onStatusChange={onPostgresStatusChange}
                  status={postgresStatus}
                />
              ) : null}
              {row.id === "mcp_upstream" ? (
                <McpUpstreamSetupPanel onStatusChange={onMcpStatusChange} status={mcpStatus} />
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
  const [setupRequest, setSetupRequest] = useState(0);

  const loadOverview = useCallback(async () => {
    setLoading(true);
    const [
      mcpResult,
      githubResult,
      slackResult,
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
      sourceConnectorsResult,
    ] = await Promise.allSettled([
      getMcpUpstreamBinding(),
      getGithubConnectionStatus(),
      getSlackInstallStatus(),
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
      listSourceConnectors({ environment: "production", capability: STRIPE_REFUND_READ_CAPABILITY }),
    ]);

    const nativeStripeStatus = stripeResult.status === "fulfilled" ? stripeResult.value : null;
    const sourceStripeStatus = sourceConnectorsResult.status === "fulfilled"
      ? stripeStatusFromSourceConnector(sourceConnectorsResult.value.items[0])
      : null;

    setOverview({
      mcp: mcpResult.status === "fulfilled" ? mcpResult.value : null,
      github: githubResult.status === "fulfilled" ? githubResult.value : null,
      slack: slackResult.status === "fulfilled" ? slackResult.value : null,
      generic: genericResult.status === "fulfilled" ? genericResult.value : null,
      stripe: nativeStripeStatus?.connected ? nativeStripeStatus : sourceStripeStatus ?? nativeStripeStatus,
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
      mcpResult,
      githubResult,
      slackResult,
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
    () =>
      buildConnectorInventory({
        ...overview,
        customer: null,
        ledger: null,
        partialFailure,
        visibleConnectorIds: LAUNCH_VISIBLE_CONNECTOR_IDS,
      }),
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
  const openSelectedConnectorSetup = () => {
    const targetId = selectedRow?.kind === "proof" ? selectedRow.id : firstSelectedId(visibleInventory);
    if (targetId) setSelectedId(targetId);
    setSetupRequest((current) => current + 1);
  };
  return (
    <div className="dashboard-page integrations-page connectors-page">
      <DashboardVerdictHero
        actions={
          <>
            <DashboardButton loading={loading} onClick={() => void loadOverview()} variant="soft">
              Refresh
            </DashboardButton>
            {selectedRow?.kind === "support" ? (
              <DashboardButtonLink href={selectedRow.href} variant="primary">
                {connectorPrimaryCtaLabel(selectedRow)}
              </DashboardButtonLink>
            ) : (
              <DashboardButton loading={loading} onClick={openSelectedConnectorSetup} variant="primary">
                {selectedRow ? connectorPrimaryCtaLabel(selectedRow) : "Connect verifier"}
              </DashboardButton>
            )}
          </>
        }
        copy={`${visibleInventory.verdict.copy} One-click means read-only access, manifest validation, test-read, then Assurance Pack binding.`}
        eyebrow="Connectors"
        pill="One-click · read-only"
        tone={visibleInventory.verdict.tone}
        title="Connectors"
        updatedLabel={loading ? "Refreshing" : "Updated now"}
      />

      <section className="connectors-flow-strip" aria-label="One-click connector setup">
        <ConnectorOneClickFlow />
      </section>

      <ConnectorReadinessStrip inventory={visibleInventory} />

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
            mcpStatus={overview.mcp}
            genericStatus={overview.generic}
            hubspotStatus={overview.hubspot}
            jiraStatus={overview.jira}
            netsuiteStatus={overview.netsuite}
            postgresStatus={overview.postgres}
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
            onPostgresStatusChange={(postgres) => setOverview((current) => ({ ...current, postgres }))}
            onRazorpayStatusChange={(razorpay) => setOverview((current) => ({ ...current, razorpay }))}
            onSalesforceStatusChange={(salesforce) => setOverview((current) => ({ ...current, salesforce }))}
            onShopifyStatusChange={(shopify) => setOverview((current) => ({ ...current, shopify }))}
            onStripePaymentStatusChange={(stripePayment) => setOverview((current) => ({ ...current, stripePayment }))}
            onStripeStatusChange={(stripe) => setOverview((current) => ({ ...current, stripe }))}
            onZendeskStatusChange={(zendesk) => setOverview((current) => ({ ...current, zendesk }))}
            onZohoStatusChange={(zoho) => setOverview((current) => ({ ...current, zoho }))}
            onMcpStatusChange={(mcp) => setOverview((current) => ({ ...current, mcp }))}
            row={selectedRow}
            setupRequest={setupRequest}
          />
        }
      />

      <SourceAudit rows={visibleInventory.proofRows} />

      {partialFailure ? (
        <div className="alert-strip connectors-alert">
          <AlertTriangle aria-hidden="true" />
          Some connector status checks could not load. Coverage is shown from the sources that responded.
        </div>
      ) : null}
    </div>
  );
}
