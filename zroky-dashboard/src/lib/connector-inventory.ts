import type {
  CustomerRecordConnectorStatusResponse,
  GenericRestConnectorStatusResponse,
  HubSpotCrmConnectorStatusResponse,
  JiraIssueConnectorStatusResponse,
  LedgerRefundConnectorStatusResponse,
  NetSuiteFinanceConnectorStatusResponse,
  OutcomeReconciliationView,
  PostgresReadConnectorStatusResponse,
  RazorpayRefundConnectorStatusResponse,
  SalesforceCrmConnectorStatusResponse,
  ShopifyConnectorStatusResponse,
  StripePaymentConnectorStatusResponse,
  StripeRefundConnectorStatusResponse,
  ZendeskTicketConnectorStatusResponse,
  ZohoCrmConnectorStatusResponse,
  ToolRegistryResponse,
} from "@/lib/api";
import type { GithubConnectionStatusResponse, SlackInstallStatusResponse } from "@/lib/types";
import { statusLabel, statusTone, type StatusTone } from "@/lib/action-status";
import { formatDateTime, humanize } from "@/lib/format";

export type ProofConnectorId =
  | "generic_rest"
  | "hubspot_crm"
  | "salesforce_crm"
  | "zoho_crm"
  | "zendesk_ticket"
  | "intercom"
  | "freshdesk_ticket"
  | "jira_issue"
  | "stripe_refund"
  | "stripe_payment"
  | "razorpay_refund"
  | "netsuite_finance"
  | "quickbooks_ledger"
  | "generic_finance"
  | "shopify_admin"
  | "ledger_template"
  | "customer_template"
  | "postgres_read";
export type SupportConnectorId = "github" | "slack";
export type ConnectorInventoryId = ProofConnectorId | SupportConnectorId;

export const LAUNCH_VISIBLE_CONNECTOR_IDS = new Set<ConnectorInventoryId>([
  "generic_rest",
  "stripe_refund",
  "postgres_read",
  "github",
  "slack",
]);

export const CONNECTOR_DISPLAY_LABELS: Record<string, string> = {
  accounting_system: "Accounting system",
  commerce_platform: "Commerce platform",
  crm_record: "CRM record",
  customer_identity: "Customer identity",
  erp_finance: "ERP finance",
  email_delivery: "Email/messages",
  freshdesk_ticket: "Freshdesk tickets",
  generic_finance: "Generic Finance API",
  generic_rest: "Generic REST",
  github_ci: "GitHub CI",
  inventory_system: "Inventory system",
  intercom: "Intercom",
  ledger_refund: "Refund ledger",
  netsuite_finance: "NetSuite finance",
  order_management: "Order management",
  payments_ledger: "Payments ledger",
  postgres_read: "Postgres Read",
  quickbooks_ledger: "QuickBooks template",
  razorpay_refund: "Razorpay refund",
  shopify_admin: "Shopify Admin",
  slack_approval_alert: "Slack approval",
  subscription_billing: "Subscription billing",
  stripe_payment: "Stripe payment",
  stripe_refund: "Stripe refund",
  ticket_status: "Support tickets",
  zendesk_ticket: "Zendesk tickets",
};

export type ConnectorTransport = "rest_http" | "sql_read" | "webhook_bridge" | "workflow";
export type ConnectorTemplateKind =
  | "custom"
  | "hubspot_crm"
  | "salesforce_crm"
  | "zoho_crm"
  | "zendesk_ticket"
  | "intercom"
  | "freshdesk_ticket"
  | "jira_issue"
  | "stripe_refund"
  | "stripe_payment"
  | "razorpay_refund"
  | "netsuite_finance"
  | "quickbooks_ledger"
  | "generic_finance"
  | "shopify_admin"
  | "refund_ledger"
  | "customer_record"
  | null;
export type ConnectorInventoryKind = "proof" | "support";

export type ConnectorInventoryState =
  | "missing"
  | "not_tested"
  | "ready"
  | "failing"
  | "mismatched";

export type ConnectorCoverageStatus =
  | "healthy"
  | "generic_fallback"
  | "not_tested"
  | "failing"
  | "unverifiable";

export type ConnectorInventoryVerdict = {
  tone: StatusTone;
  title: string;
  copy: string;
  pill: string;
  ctaLabel: string;
  ctaHref: string;
};

export type ConnectorInventoryCounts = {
  proofTotal: number;
  healthyVerifiers: number;
  failingVerifiers: number;
  notConfigured: number;
  notTested: number;
  supportTotal: number;
  supportConnected: number;
  matchedChecks: number;
  coveragePercent: number;
  actionTypesTotal: number;
  unverifiableActionTypes: number;
};

export type ConnectorCoverageRow = {
  actionType: string;
  status: ConnectorCoverageStatus;
  tone: StatusTone;
  label: string;
  detail: string;
  connectorId: ProofConnectorId | null;
  transport: ConnectorTransport | null;
};

export type ConnectorInventoryRow = {
  id: ConnectorInventoryId;
  kind: ConnectorInventoryKind;
  transport: ConnectorTransport;
  templateKind: ConnectorTemplateKind;
  title: string;
  category: string;
  description: string;
  href: string;
  ctaLabel: string;
  state: ConnectorInventoryState;
  tone: StatusTone;
  statusLabel: string;
  detail: string;
  connected: boolean;
  healthStatus: string | null;
  readinessStatus: string | null;
  lastVerdict: string | null;
  lastErrorCode: string | null;
  latestCheck: OutcomeReconciliationView | null;
  updatedAt: string | null;
  supportedActionTypes: string[];
  metadata: {
    connectorType: string | null;
    manifestId: string | null;
    maskedEndpoint: string | null;
    credentialSaved: boolean | null;
    supportAccount: string | null;
  };
};

export type ConnectorTransportGroup = {
  transport: ConnectorTransport;
  label: string;
  description: string;
  rows: ConnectorInventoryRow[];
};

export type ConnectorBusinessCategory =
  | "payments"
  | "commerce"
  | "crm"
  | "support_itsm"
  | "finance_erp"
  | "database_custom"
  | "workflow";

export type ConnectorCategoryGroup = {
  category: ConnectorBusinessCategory;
  label: string;
  description: string;
  rows: ConnectorInventoryRow[];
};

export type ConnectorInventory = {
  rows: ConnectorInventoryRow[];
  proofRows: ConnectorInventoryRow[];
  supportRows: ConnectorInventoryRow[];
  transportGroups: ConnectorTransportGroup[];
  categoryGroups: ConnectorCategoryGroup[];
  coverageRows: ConnectorCoverageRow[];
  counts: ConnectorInventoryCounts;
  verdict: ConnectorInventoryVerdict;
  registry: {
    available: number;
    template: number;
    planned: number;
  };
};

type ProofConnectorStatus =
  | LedgerRefundConnectorStatusResponse
  | CustomerRecordConnectorStatusResponse
  | GenericRestConnectorStatusResponse
  | HubSpotCrmConnectorStatusResponse
  | SalesforceCrmConnectorStatusResponse
  | ZendeskTicketConnectorStatusResponse
  | JiraIssueConnectorStatusResponse
  | StripeRefundConnectorStatusResponse
  | StripePaymentConnectorStatusResponse
  | RazorpayRefundConnectorStatusResponse
  | NetSuiteFinanceConnectorStatusResponse
  | ShopifyConnectorStatusResponse
  | ZohoCrmConnectorStatusResponse
  | PostgresReadConnectorStatusResponse;

export type BuildConnectorInventoryInput = {
  ledger: LedgerRefundConnectorStatusResponse | null;
  customer: CustomerRecordConnectorStatusResponse | null;
  generic: GenericRestConnectorStatusResponse | null;
  hubspot?: HubSpotCrmConnectorStatusResponse | null;
  salesforce?: SalesforceCrmConnectorStatusResponse | null;
  zendesk?: ZendeskTicketConnectorStatusResponse | null;
  jira?: JiraIssueConnectorStatusResponse | null;
  stripe?: StripeRefundConnectorStatusResponse | null;
  stripePayment?: StripePaymentConnectorStatusResponse | null;
  razorpay?: RazorpayRefundConnectorStatusResponse | null;
  netsuite?: NetSuiteFinanceConnectorStatusResponse | null;
  shopify?: ShopifyConnectorStatusResponse | null;
  zoho?: ZohoCrmConnectorStatusResponse | null;
  postgres: PostgresReadConnectorStatusResponse | null;
  github: GithubConnectionStatusResponse | null;
  slack: SlackInstallStatusResponse | null;
  checks?: OutcomeReconciliationView[];
  registry?: ToolRegistryResponse | null;
  actionTypes?: string[];
  partialFailure?: boolean;
  visibleConnectorIds?: ReadonlySet<ConnectorInventoryId>;
};

type ProofConnectorDefinition = {
  id: ProofConnectorId;
  transport: ConnectorTransport;
  templateKind: ConnectorTemplateKind;
  title: string;
  category: string;
  description: string;
  href: string;
  ctaLabel: string;
  connectorTypes: string[];
  supportedActionTypes: string[];
  status: ProofConnectorStatus | null;
};

type ActionConnectorHints = Map<string, ProofConnectorId[]>;

const TRANSPORT_ORDER: ConnectorTransport[] = ["rest_http", "sql_read", "webhook_bridge", "workflow"];

const TRANSPORT_COPY: Record<ConnectorTransport, { label: string; description: string }> = {
  rest_http: {
    label: "REST / HTTP JSON verifier",
    description: "Read-only JSON endpoints for SaaS, internal APIs, and template-based source-of-record checks.",
  },
  sql_read: {
    label: "SQL / database read verifier",
    description: "Read-only database checks for database-backed business state.",
  },
  webhook_bridge: {
    label: "Webhook / bridge verifier",
    description: "For systems that cannot be polled directly. Planned as a first-class transport.",
  },
  workflow: {
    label: "Workflow integrations",
    description: "Slack and GitHub support approvals, alerts, and change workflows. They are not proof verifiers.",
  },
};

const CATEGORY_ORDER: ConnectorBusinessCategory[] = [
  "payments",
  "commerce",
  "crm",
  "support_itsm",
  "finance_erp",
  "workflow",
  "database_custom",
];

const CATEGORY_COPY: Record<ConnectorBusinessCategory, { label: string; description: string }> = {
  payments: {
    label: "Payments",
    description: "Refund, payout, invoice, and payment-adjustment systems that prove money movement.",
  },
  commerce: {
    label: "Commerce",
    description: "Order, fulfillment, inventory, and storefront systems that prove commerce operations.",
  },
  crm: {
    label: "CRM",
    description: "Customer, lead, deal, account, and contact records used by sales and support agents.",
  },
  support_itsm: {
    label: "Support & ITSM",
    description: "Ticket, incident, access, and change-management systems for service operations.",
  },
  finance_erp: {
    label: "Finance & ERP",
    description: "Procurement, vendor bill, purchase-order, and finance source-of-record checks.",
  },
  database_custom: {
    label: "Developer / Custom APIs",
    description: "Advanced read-only SQL and custom REST paths for internal systems or unsupported SaaS products.",
  },
  workflow: {
    label: "Workflow",
    description: "Approval, alerting, change, and collaboration channels. These do not produce evidence by themselves.",
  },
};

const CATEGORY_BY_CONNECTOR: Record<ConnectorInventoryId, ConnectorBusinessCategory> = {
  generic_rest: "database_custom",
  hubspot_crm: "crm",
  salesforce_crm: "crm",
  zoho_crm: "crm",
  zendesk_ticket: "support_itsm",
  intercom: "support_itsm",
  freshdesk_ticket: "support_itsm",
  jira_issue: "support_itsm",
  stripe_refund: "payments",
  stripe_payment: "payments",
  razorpay_refund: "payments",
  netsuite_finance: "finance_erp",
  quickbooks_ledger: "finance_erp",
  generic_finance: "finance_erp",
  shopify_admin: "commerce",
  ledger_template: "payments",
  customer_template: "crm",
  postgres_read: "database_custom",
  github: "workflow",
  slack: "workflow",
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function textValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function normalize(value: string | null | undefined): string {
  return (value ?? "").trim().toLowerCase();
}

function connectorMetadata(check: OutcomeReconciliationView): Record<string, unknown> {
  const metadata = isRecord(check.metadata) ? check.metadata : {};
  const nested = metadata.connector;
  return isRecord(nested) ? { ...metadata, ...nested } : metadata;
}

function checkConnectorKind(check: OutcomeReconciliationView): string | null {
  const metadata = connectorMetadata(check);
  return textValue(metadata.connector_kind)
    ?? textValue(metadata.connector_type)
    ?? textValue(metadata.system_of_record)
    ?? textValue(check.connector_type);
}

function latestCheckForConnector(checks: OutcomeReconciliationView[], connectorTypes: string[]): OutcomeReconciliationView | null {
  const normalized = new Set(connectorTypes.map((item) => item.toLowerCase()));
  return checks
    .filter((check) => {
      const kind = checkConnectorKind(check)?.toLowerCase();
      return Boolean(kind && normalized.has(kind));
    })
    .sort((a, b) => new Date(b.checked_at).getTime() - new Date(a.checked_at).getTime())[0] ?? null;
}

function credentialSaved(status: ProofConnectorStatus | null): boolean | null {
  if (!status) return null;
  if ("has_database_url" in status) {
    return Boolean(status.has_database_url && status.has_read_query);
  }
  return Boolean(status.has_bearer_token);
}

function maskedEndpoint(status: ProofConnectorStatus | null): string | null {
  if (!status) return null;
  if ("has_database_url" in status) {
    return status.read_query_digest ? `query:${status.read_query_digest}` : null;
  }
  if (!status.base_url) return null;
  return status.path_template ? `${status.base_url}${status.path_template}` : status.base_url;
}

function statusHealthy(value: string | null | undefined): boolean {
  return normalize(value) === "healthy";
}

function readinessReady(value: string | null | undefined): boolean {
  return normalize(value) === "ready";
}

function connectedStatus(status: ProofConnectorStatus | null): boolean {
  return Boolean(status?.connected);
}

function connectorReady(status: ProofConnectorStatus | null, latestCheck: OutcomeReconciliationView | null): boolean {
  return Boolean(
    status?.connected
      && statusHealthy(status.health_status)
      && (status.last_verdict ?? latestCheck?.verdict) === "matched"
      && readinessReady(status.readiness?.status)
      && !status.last_error_code,
  );
}

function proofState(status: ProofConnectorStatus | null, latestCheck: OutcomeReconciliationView | null): ConnectorInventoryState {
  if (!connectedStatus(status)) return "missing";
  const verdict = status?.last_verdict ?? latestCheck?.verdict ?? null;
  if (verdict === "mismatched") return "mismatched";
  if (status?.last_error_code || (status?.health_status && !statusHealthy(status.health_status))) return "failing";
  if (connectorReady(status, latestCheck)) return "ready";
  return "not_tested";
}

function proofStatusLabel(state: ConnectorInventoryState, status: ProofConnectorStatus | null): string {
  if (state === "missing") return "Not configured";
  if (state === "ready") return "Healthy";
  if (state === "mismatched") return "Mismatched";
  if (state === "failing") return status?.last_error_code ? humanize(status.last_error_code, "Failing") : "Failing";
  return "Needs preflight";
}

function proofDetail(state: ConnectorInventoryState, status: ProofConnectorStatus | null, latestCheck: OutcomeReconciliationView | null): string {
  if (state === "missing") {
    return "Save a read-scoped system-of-record verifier before this proof path can verify outcomes.";
  }
  if (state === "ready") {
    return `Healthy / ${statusLabel(status?.last_verdict ?? latestCheck?.verdict, "proof")} / evidence exportable.`;
  }
  if (state === "mismatched") {
    return latestCheck?.reason ? `Latest proof mismatched: ${latestCheck.reason}.` : "Latest proof mismatched the source of record.";
  }
  if (state === "failing") {
    return status?.last_error_code
      ? `${humanize(status.last_error_code)} is blocking preflight.`
      : `${humanize(status?.health_status, "Connector health")} is blocking preflight.`;
  }
  return `${humanize(status?.readiness?.status, "Not ready")} / ${statusLabel(status?.last_verdict ?? latestCheck?.verdict, "proof", "No proof run")}. Run preflight before handoff.`;
}

function proofRow(definition: ProofConnectorDefinition, checks: OutcomeReconciliationView[]): ConnectorInventoryRow {
  const latestCheck = latestCheckForConnector(checks, definition.connectorTypes);
  const state = proofState(definition.status, latestCheck);
  return {
    id: definition.id,
    kind: "proof",
    transport: definition.transport,
    templateKind: definition.templateKind,
    title: definition.title,
    category: definition.category,
    description: definition.description,
    href: definition.href,
    ctaLabel: definition.ctaLabel,
    state,
    tone: connectorStateTone(state),
    statusLabel: proofStatusLabel(state, definition.status),
    detail: proofDetail(state, definition.status, latestCheck),
    connected: connectedStatus(definition.status),
    healthStatus: definition.status?.health_status ?? null,
    readinessStatus: definition.status?.readiness?.status ?? null,
    lastVerdict: definition.status?.last_verdict ?? latestCheck?.verdict ?? null,
    lastErrorCode: definition.status?.last_error_code ?? null,
    latestCheck,
    updatedAt: definition.status?.last_checked_at ?? definition.status?.updated_at ?? latestCheck?.checked_at ?? null,
    supportedActionTypes: definition.supportedActionTypes,
    metadata: {
      connectorType: definition.status?.connector_type ?? null,
      manifestId: null,
      maskedEndpoint: maskedEndpoint(definition.status),
      credentialSaved: credentialSaved(definition.status),
      supportAccount: null,
    },
  };
}

function supportRow(
  id: SupportConnectorId,
  status: GithubConnectionStatusResponse | SlackInstallStatusResponse | null,
): ConnectorInventoryRow {
  const isGithub = id === "github";
  const connected = Boolean(status?.connected);
  const account = isGithub
    ? textValue((status as GithubConnectionStatusResponse | null)?.github_login)
    : textValue((status as SlackInstallStatusResponse | null)?.channel_name)
      ?? textValue((status as SlackInstallStatusResponse | null)?.team_name);
  return {
    id,
    kind: "support",
    transport: "workflow",
    templateKind: null,
    title: isGithub ? "GitHub" : "Slack",
    category: isGithub ? "Change workflow" : "Ops delivery",
    description: isGithub
      ? "Repository access for generated fix pull requests and source-linked reliability work."
      : "Approval, alert, and incident delivery for operators.",
    href: isGithub ? "/integrations#github-connector" : "/integrations/slack",
    ctaLabel: isGithub ? "Connect GitHub" : "Manage Slack",
    state: connected ? "ready" : "missing",
    tone: connected ? "success" : "neutral",
    statusLabel: connected ? "Connected" : "Not connected",
    detail: connected && account
      ? isGithub ? `@${account} is connected.` : `Routing through ${account.startsWith("#") ? account : `#${account}`}.`
      : isGithub ? "Connect repository access before generated fix proof can gate changes." : "Connect the operating channel for approval and failure events.",
    connected,
    healthStatus: null,
    readinessStatus: null,
    lastVerdict: null,
    lastErrorCode: null,
    latestCheck: null,
    updatedAt: status?.updated_at ?? (isGithub ? (status as GithubConnectionStatusResponse | null)?.connected_at : (status as SlackInstallStatusResponse | null)?.installed_at) ?? null,
    supportedActionTypes: [],
    metadata: {
      connectorType: id,
      manifestId: null,
      maskedEndpoint: null,
      credentialSaved: null,
      supportAccount: account,
    },
  };
}

function registryCounts(registry: ToolRegistryResponse | null | undefined) {
  const items = registry
    ? [...registry.runtime_paths, ...registry.verification_connectors, ...registry.native_tool_families]
    : [];
  return {
    available: items.filter((item) => item.implementation_status === "available").length,
    template: items.filter((item) => item.implementation_status === "template").length,
    planned: items.filter((item) => item.implementation_status === "planned").length,
  };
}

function registryActionTypes(registry: ToolRegistryResponse | null | undefined): string[] {
  if (!registry) return [];
  return [
    ...registry.recommended.action_types,
    ...registry.verification_connectors.flatMap((item) => item.supported_action_types),
    ...registry.verification_connectors.flatMap((item) => item.recommended_for_action_types),
    ...registry.native_tool_families.flatMap((item) => item.supported_action_types),
    ...registry.native_tool_families.flatMap((item) => item.recommended_for_action_types),
  ];
}

function uniqueSorted(values: string[]): string[] {
  return [...new Set(values.map((item) => item.trim()).filter(Boolean))].sort((a, b) => a.localeCompare(b));
}

function actionTypesForCoverage(input: BuildConnectorInventoryInput): string[] {
  return uniqueSorted([
    ...(input.actionTypes ?? []),
    ...registryActionTypes(input.registry),
    ...(input.checks ?? []).map((check) => check.action_type ?? ""),
  ]);
}

function registryConnectorIds(item: ToolRegistryResponse["verification_connectors"][number]): ProofConnectorId[] {
  const haystack = normalize([
    item.id,
    item.label,
    item.backend_capability,
    item.category,
  ].filter(Boolean).join(" "));
  const ids: ProofConnectorId[] = [];
  if (
    haystack.includes("stripe_payment")
    || haystack.includes("stripe payments")
    || haystack.includes("paymentintent")
    || haystack.includes("payment_intent")
  ) ids.push("stripe_payment");
  if (haystack.includes("stripe_refund") || (haystack.includes("stripe") && haystack.includes("refund"))) ids.push("stripe_refund");
  if (haystack.includes("shopify")) ids.push("shopify_admin");
  if (haystack.includes("razorpay")) ids.push("razorpay_refund");
  if (haystack.includes("quickbooks")) ids.push("quickbooks_ledger");
  if (haystack.includes("generic_finance") || haystack.includes("finance_api") || haystack.includes("accounting_system")) ids.push("generic_finance");
  if (haystack.includes("netsuite") || haystack.includes("procurement") || haystack.includes("finance")) ids.push("netsuite_finance");
  if (haystack.includes("hubspot")) ids.push("hubspot_crm");
  if (haystack.includes("salesforce")) ids.push("salesforce_crm");
  if (haystack.includes("zoho")) ids.push("zoho_crm");
  if (haystack.includes("intercom")) ids.push("intercom");
  if (haystack.includes("freshdesk")) ids.push("freshdesk_ticket");
  if (haystack.includes("zendesk") || haystack.includes("ticket")) ids.push("zendesk_ticket");
  if (
    haystack.includes("jira")
    || haystack.includes("jsm")
    || haystack.includes("atlassian")
    || haystack.includes("incident")
    || haystack.includes("access")
    || haystack.includes("change")
  ) ids.push("jira_issue");
  if (haystack.includes("generic") || haystack.includes("rest")) ids.push("generic_rest");
  if ((haystack.includes("ledger") || haystack.includes("refund")) && !haystack.includes("stripe")) ids.push("ledger_template");
  if (haystack.includes("customer") || haystack.includes("crm")) ids.push("customer_template");
  if (haystack.includes("postgres") || haystack.includes("sql") || haystack.includes("database")) ids.push("postgres_read");
  return [...new Set(ids)];
}

function registryConnectorHints(registry: ToolRegistryResponse | null | undefined): ActionConnectorHints {
  const hints: ActionConnectorHints = new Map();
  if (!registry) return hints;

  for (const item of registry.verification_connectors) {
    const connectorIds = registryConnectorIds(item);
    if (connectorIds.length === 0) continue;

    for (const actionType of [...item.supported_action_types, ...item.recommended_for_action_types]) {
      const key = normalize(actionType);
      if (!key) continue;
      hints.set(key, [...new Set([...(hints.get(key) ?? []), ...connectorIds])]);
    }
  }

  return hints;
}

function registryManifestIds(registry: ToolRegistryResponse | null | undefined): Map<string, string> {
  const out = new Map<string, string>();
  for (const item of registry?.verification_connectors ?? []) {
    if (!item.manifest_id) continue;
    out.set(item.id, item.manifest_id);
    if (item.id === "database_read") {
      out.set("postgres_read", item.manifest_id);
    }
  }
  return out;
}

function connectorForAction(
  actionType: string,
  proofRows: ConnectorInventoryRow[],
  connectorHints: ActionConnectorHints,
): ConnectorCoverageRow {
  const hints = connectorHints.get(normalize(actionType)) ?? [];
  const exactRows = hints
    .map((id) => proofRows.find((row) => row.id === id))
    .filter((row): row is ConnectorInventoryRow => Boolean(row));

  const healthyExact = exactRows.find((row) => row.state === "ready");
  if (healthyExact) {
    return {
      actionType,
      status: "healthy",
      tone: "success",
      label: "Verifier healthy",
      detail: `${healthyExact.title} can verify this action type.`,
      connectorId: healthyExact.id as ProofConnectorId,
      transport: healthyExact.transport,
    };
  }

  const problemExact = exactRows.find((row) => row.state === "failing" || row.state === "mismatched");
  if (problemExact) {
    return {
      actionType,
      status: "failing",
      tone: "danger",
      label: "Verifier failing",
      detail: `${problemExact.title} is configured but not trustworthy right now.`,
      connectorId: problemExact.id as ProofConnectorId,
      transport: problemExact.transport,
    };
  }

  const notTestedExact = exactRows.find((row) => row.connected);
  if (notTestedExact) {
    return {
      actionType,
      status: "not_tested",
      tone: "warning",
      label: "Needs preflight",
      detail: `${notTestedExact.title} is saved but still needs matched proof.`,
      connectorId: notTestedExact.id as ProofConnectorId,
      transport: notTestedExact.transport,
    };
  }

  const generic = proofRows.find((row) => row.id === "generic_rest");
  if (generic?.state === "ready") {
    return {
      actionType,
      status: "generic_fallback",
      tone: "success",
      label: "Generic REST fallback",
      detail: "Generic REST verifier is healthy; map this action type to a readable JSON record.",
      connectorId: "generic_rest",
      transport: "rest_http",
    };
  }

  if (generic?.connected && generic.state !== "missing") {
    return {
      actionType,
      status: generic.state === "failing" || generic.state === "mismatched" ? "failing" : "not_tested",
      tone: generic.state === "failing" || generic.state === "mismatched" ? "danger" : "warning",
      label: generic.state === "failing" || generic.state === "mismatched" ? "Fallback failing" : "Fallback needs preflight",
      detail: "Generic REST is the fallback path, but it is not ready yet.",
      connectorId: "generic_rest",
      transport: "rest_http",
    };
  }

  return {
    actionType,
    status: "unverifiable",
    tone: "warning",
    label: "No verifier",
    detail: "Actions of this type will resolve not_verified until a REST, SQL, or webhook verifier is configured.",
    connectorId: null,
    transport: null,
  };
}

function buildCoverageRows(
  actionTypes: string[],
  proofRows: ConnectorInventoryRow[],
  connectorHints: ActionConnectorHints,
): ConnectorCoverageRow[] {
  return actionTypes.map((actionType) => connectorForAction(actionType, proofRows, connectorHints));
}

function buildTransportGroups(rows: ConnectorInventoryRow[]): ConnectorTransportGroup[] {
  return TRANSPORT_ORDER
    .map((transport) => ({
      transport,
      ...TRANSPORT_COPY[transport],
      rows: rows.filter((row) => row.transport === transport),
    }))
    .filter((group) => group.rows.length > 0 || group.transport === "webhook_bridge");
}

function buildCategoryGroups(rows: ConnectorInventoryRow[]): ConnectorCategoryGroup[] {
  return CATEGORY_ORDER
    .map((category) => ({
      category,
      ...CATEGORY_COPY[category],
      rows: rows.filter((row) => CATEGORY_BY_CONNECTOR[row.id] === category),
    }))
    .filter((group) => group.rows.length > 0);
}

function coveragePercent(rows: ConnectorCoverageRow[]): number {
  if (rows.length === 0) return 0;
  const covered = rows.filter((row) => row.status === "healthy" || row.status === "generic_fallback").length;
  return Math.round((covered / rows.length) * 100);
}

function inventoryVerdict(counts: ConnectorInventoryCounts, partialFailure: boolean): ConnectorInventoryVerdict {
  if (partialFailure) {
    return {
      tone: "danger",
      title: "Connector status unavailable",
      copy: "One or more connector feeds did not refresh cleanly. Core proof configuration may still be visible.",
      pill: "Degraded",
      ctaLabel: "Retry refresh",
      ctaHref: "/integrations",
    };
  }
  if (counts.failingVerifiers > 0) {
    return {
      tone: "danger",
      title: "Verification connector blocked",
      copy: "A system-of-record verifier is failing or mismatched. Fix it before trusting new evidence exports.",
      pill: "Blocked",
      ctaLabel: "Fix connector",
      ctaHref: "/integrations",
    };
  }
  if (counts.actionTypesTotal > 0 && counts.unverifiableActionTypes > 0) {
    return {
      tone: "warning",
      title: "Some agent actions are unverifiable",
      copy: "Configure a REST, SQL, or webhook verifier for action types that would otherwise resolve not_verified.",
      pill: "Coverage gap",
      ctaLabel: "Review coverage",
      ctaHref: "/integrations",
    };
  }
  if (counts.healthyVerifiers > 0 && counts.notTested > 0) {
    return {
      tone: "warning",
      title: "Verification connectors need preflight",
      copy: "Some source systems are saved but still need a matched preflight before evidence can be trusted.",
      pill: "Needs preflight",
      ctaLabel: "Run preflight",
      ctaHref: "/integrations",
    };
  }
  if (counts.healthyVerifiers > 0 && (counts.actionTypesTotal === 0 || counts.coveragePercent === 100)) {
    return {
      tone: "success",
      title: "Systems of record ready",
      copy: "Healthy read-only verifiers can independently check real outcomes for configured agent actions.",
      pill: "Ready",
      ctaLabel: "Open Outcomes",
      ctaHref: "/outcomes",
    };
  }
  return {
    tone: "neutral",
    title: "Connect read-only verifiers",
    copy: "Connect REST, SQL, or webhook verifier paths so Zroky can prove what autonomous agents actually changed.",
    pill: "Setup required",
    ctaLabel: "Configure first verifier",
    ctaHref: "/integrations",
  };
}

export function buildConnectorInventory(input: BuildConnectorInventoryInput): ConnectorInventory {
  const checks = input.checks ?? [];
  const proofDefinitions: ProofConnectorDefinition[] = [
    {
      id: "generic_rest",
      transport: "rest_http",
      templateKind: "custom",
      title: "REST / HTTP JSON verifier",
      category: "Custom REST verifier",
      description: "Primary general verifier for internal APIs, SaaS APIs, and any readable JSON source of record.",
      href: "/integrations#generic-rest-connector",
      ctaLabel: "Configure REST verifier",
      connectorTypes: ["generic_rest_api", "generic_rest"],
      supportedActionTypes: ["*"],
      status: input.generic,
    },
    {
      id: "hubspot_crm",
      transport: "rest_http",
      templateKind: "hubspot_crm",
      title: "HubSpot CRM verifier",
      category: "Native REST verifier",
      description: "Native HubSpot contact reader for CRM agent proof. Uses a private app token today; OAuth is planned.",
      href: "/integrations?connector=hubspot_crm",
      ctaLabel: "Configure HubSpot",
      connectorTypes: ["hubspot_crm", "hubspot_customer", "system_of_record.hubspot_crm"],
      supportedActionTypes: ["customer_record_update", "crm", "lead", "deal", "contact"],
      status: input.hubspot ?? null,
    },
    {
      id: "salesforce_crm",
      transport: "rest_http",
      templateKind: "salesforce_crm",
      title: "Salesforce CRM verifier",
      category: "Native REST verifier",
      description: "Salesforce sObject reader for CRM and RevOps proof when a working access token is available. OAuth refresh still needs launch hardening.",
      href: "/integrations?connector=salesforce_crm",
      ctaLabel: "Configure Salesforce",
      connectorTypes: ["salesforce_crm", "salesforce_customer", "system_of_record.salesforce_crm"],
      supportedActionTypes: [
        "customer_record_update",
        "crm",
        "lead",
        "deal",
        "opportunity",
        "account",
        "contact",
        "case",
      ],
      status: input.salesforce ?? null,
    },
    {
      id: "zoho_crm",
      transport: "rest_http",
      templateKind: "zoho_crm",
      title: "Zoho CRM verifier",
      category: "Native REST verifier",
      description: "Zoho CRM module reader for CRM and RevOps proof. OAuth connect exists, but refresh-token verification still needs launch hardening.",
      href: "/integrations?connector=zoho_crm",
      ctaLabel: "Configure Zoho",
      connectorTypes: ["zoho_crm", "zoho_customer", "system_of_record.zoho_crm"],
      supportedActionTypes: [
        "customer_record_update",
        "crm",
        "lead",
        "deal",
        "account",
        "contact",
        "zoho",
      ],
      status: input.zoho ?? null,
    },
    {
      id: "zendesk_ticket",
      transport: "rest_http",
      templateKind: "zendesk_ticket",
      title: "Zendesk ticket verifier",
      category: "Native REST verifier",
      description: "Native Zendesk Support ticket reader for support agent proof. Uses a read-scoped token today; OAuth is planned.",
      href: "/integrations?connector=zendesk_ticket",
      ctaLabel: "Configure Zendesk",
      connectorTypes: ["zendesk_ticket", "ticket_status", "system_of_record.zendesk_ticket"],
      supportedActionTypes: ["ticket_close", "support", "ticket", "zendesk", "case"],
      status: input.zendesk ?? null,
    },
    {
      id: "intercom",
      transport: "rest_http",
      templateKind: "intercom",
      title: "Intercom verifier",
      category: "Native REST verifier",
      description: "Intercom conversation and customer-message proof for support agents. Native credential setup is not enabled yet; use Custom REST until launch.",
      href: "/integrations?connector=intercom",
      ctaLabel: "Configure Intercom",
      connectorTypes: ["intercom", "intercom_conversation", "intercom_ticket", "system_of_record.intercom"],
      supportedActionTypes: ["ticket_close", "support", "ticket", "message", "email_send", "customer_message", "intercom"],
      status: null,
    },
    {
      id: "freshdesk_ticket",
      transport: "rest_http",
      templateKind: "freshdesk_ticket",
      title: "Freshdesk ticket verifier",
      category: "Native REST verifier",
      description: "Freshdesk ticket and workflow proof for support agents. Native credential setup is not enabled yet; use Custom REST until launch.",
      href: "/integrations?connector=freshdesk_ticket",
      ctaLabel: "Configure Freshdesk",
      connectorTypes: ["freshdesk_ticket", "freshdesk", "ticket_status", "system_of_record.freshdesk_ticket"],
      supportedActionTypes: ["ticket_close", "support", "ticket", "freshdesk", "case", "customer_message"],
      status: null,
    },
    {
      id: "jira_issue",
      transport: "rest_http",
      templateKind: "jira_issue",
      title: "Jira / JSM verifier",
      category: "Native REST verifier",
      description: "Native Jira issue reader for support, ITSM, access, incident, and change proof. Uses Atlassian API-token setup today; OAuth is planned.",
      href: "/integrations?connector=jira_issue",
      ctaLabel: "Configure Jira",
      connectorTypes: ["jira_issue", "jira", "jira_ticket", "jsm", "system_of_record.jira_issue"],
      supportedActionTypes: [
        "ticket_close",
        "support",
        "ticket",
        "jira",
        "jsm",
        "incident",
        "access",
        "change",
        "deploy_change",
        "internal_api_mutation",
      ],
      status: input.jira ?? null,
    },
    {
      id: "stripe_refund",
      transport: "rest_http",
      templateKind: "stripe_refund",
      title: "Stripe refund verifier",
      category: "Native REST verifier",
      description: "Native Stripe refund reader for refund, credit, and payment-adjustment proof. Uses a restricted Stripe secret key.",
      href: "/integrations?connector=stripe_refund",
      ctaLabel: "Configure Stripe",
      connectorTypes: ["stripe_refund", "stripe", "stripe_refunds", "system_of_record.stripe_refund"],
      supportedActionTypes: ["refund", "credit", "payment", "payment_adjustment", "payout", "invoice"],
      status: input.stripe ?? null,
    },
    {
      id: "stripe_payment",
      transport: "rest_http",
      templateKind: "stripe_payment",
      title: "Stripe payment verifier",
      category: "Native REST verifier",
      description: "Native Stripe PaymentIntent reader for payment, payout, invoice, and charge-status proof. Uses a restricted Stripe secret key.",
      href: "/integrations?connector=stripe_payment",
      ctaLabel: "Configure Stripe Payment",
      connectorTypes: ["stripe_payment", "stripe_payments", "payment_intent", "paymentintent", "system_of_record.stripe_payment"],
      supportedActionTypes: ["payment_adjustment", "vendor_payout", "invoice_spend_approval", "payment", "payout", "invoice", "charge"],
      status: input.stripePayment ?? null,
    },
    {
      id: "razorpay_refund",
      transport: "rest_http",
      templateKind: "razorpay_refund",
      title: "Razorpay refund verifier",
      category: "Native REST verifier",
      description: "Native Razorpay refund reader for refund and payment-adjustment proof. Uses Razorpay key-id plus key-secret basic auth.",
      href: "/integrations?connector=razorpay_refund",
      ctaLabel: "Configure Razorpay",
      connectorTypes: ["razorpay_refund", "razorpay", "razorpay_refunds", "system_of_record.razorpay_refund"],
      supportedActionTypes: ["refund", "credit", "payment", "payment_adjustment", "payout", "invoice"],
      status: input.razorpay ?? null,
    },
    {
      id: "netsuite_finance",
      transport: "rest_http",
      templateKind: "netsuite_finance",
      title: "NetSuite finance verifier",
      category: "Native REST verifier",
      description: "NetSuite finance/procurement record reader for teams that can supply a working read token today. Native TBA/OAuth hardening is still required for launch-grade NetSuite.",
      href: "/integrations?connector=netsuite_finance",
      ctaLabel: "Configure NetSuite",
      connectorTypes: ["netsuite_finance", "netsuite", "netsuite_record", "system_of_record.netsuite_finance"],
      supportedActionTypes: [
        "invoice_spend_approval",
        "payment_adjustment",
        "finance",
        "procurement",
        "vendor_bill",
        "purchase_order",
        "invoice",
        "spend",
        "internal_api_mutation",
      ],
      status: input.netsuite ?? null,
    },
    {
      id: "quickbooks_ledger",
      transport: "rest_http",
      templateKind: "quickbooks_ledger",
      title: "QuickBooks ledger verifier",
      category: "Native REST verifier",
      description: "QuickBooks invoice, payment, and ledger proof for finance agents. Native OAuth setup is not enabled yet; use the finance template until launch.",
      href: "/integrations?connector=quickbooks_ledger",
      ctaLabel: "Configure QuickBooks",
      connectorTypes: ["quickbooks_ledger", "quickbooks", "quickbooks_online", "accounting_system", "system_of_record.quickbooks_ledger"],
      supportedActionTypes: [
        "invoice_spend_approval",
        "payment_adjustment",
        "vendor_payout",
        "journal_entry",
        "finance",
        "invoice",
        "ledger",
        "accounting",
      ],
      status: null,
    },
    {
      id: "generic_finance",
      transport: "rest_http",
      templateKind: "generic_finance",
      title: "Generic Finance API verifier",
      category: "Finance REST verifier",
      description: "Internal ERP, ledger, accounting, and finance-service proof through a read-only REST API.",
      href: "/integrations?connector=generic_finance",
      ctaLabel: "Configure Finance API",
      connectorTypes: ["generic_finance", "finance_api", "erp_finance", "accounting_system", "system_of_record.generic_finance"],
      supportedActionTypes: [
        "invoice_spend_approval",
        "payment_adjustment",
        "vendor_payout",
        "journal_entry",
        "finance",
        "procurement",
        "vendor_bill",
        "purchase_order",
        "invoice",
        "ledger",
        "accounting",
      ],
      status: input.generic,
    },
    {
      id: "shopify_admin",
      transport: "rest_http",
      templateKind: "shopify_admin",
      title: "Shopify Admin verifier",
      category: "Native REST verifier",
      description: "Shopify Admin order reader for order, fulfillment, cancellation, discount, and inventory proof.",
      href: "/integrations?connector=shopify_admin",
      ctaLabel: "Configure Shopify",
      connectorTypes: ["shopify_admin", "shopify", "shopify_order", "system_of_record.shopify_admin"],
      supportedActionTypes: ["order_cancel", "inventory_adjust", "discount_issue", "fulfillment", "refund", "commerce", "order"],
      status: input.shopify ?? null,
    },
    {
      id: "ledger_template",
      transport: "rest_http",
      templateKind: "refund_ledger",
      title: "Refund ledger template",
      category: "REST template",
      description: "Template for reading refund or payment-ledger records through the REST verifier path.",
      href: "/integrations#ledger-refund-connector",
      ctaLabel: "Configure template",
      connectorTypes: ["ledger_refund_api", "ledger_refund"],
      supportedActionTypes: ["refund", "credit", "payment", "payout", "invoice", "spend", "procurement"],
      status: input.ledger,
    },
    {
      id: "customer_template",
      transport: "rest_http",
      templateKind: "customer_record",
      title: "Customer / CRM record template",
      category: "REST template",
      description: "Template for verifying support, CRM, ticket, and customer-account updates.",
      href: "/integrations#customer-record-connector",
      ctaLabel: "Configure template",
      connectorTypes: ["customer_record_api", "customer_record"],
      supportedActionTypes: ["customer", "crm", "account", "ticket", "support", "lead", "deal"],
      status: input.customer,
    },
    {
      id: "postgres_read",
      transport: "sql_read",
      templateKind: null,
      title: "SQL / Postgres read verifier",
      category: "Database read verifier",
      description: "Read-only SQL verifier for database-backed business changes.",
      href: "/integrations#postgres-read-connector",
      ctaLabel: "Configure SQL verifier",
      connectorTypes: ["postgres_read", "postgres_read_model"],
      supportedActionTypes: [
        "database",
        "sql",
        "record",
        "internal_api",
        "finance",
        "journal_entry",
        "invoice_spend_approval",
        "ledger",
        "accounting",
      ],
      status: input.postgres,
    },
  ];

  const visibleConnectorIds = input.visibleConnectorIds ?? null;
  const manifestIds = registryManifestIds(input.registry);
  const visibleProofDefinitions = visibleConnectorIds
    ? proofDefinitions.filter((definition) => visibleConnectorIds.has(definition.id))
    : proofDefinitions;
  const proofRows = visibleProofDefinitions.map((definition) => {
    const row = proofRow(definition, checks);
    return {
      ...row,
      metadata: {
        ...row.metadata,
        manifestId: manifestIds.get(definition.id) ?? null,
      },
    };
  });
  const supportRows = [
    supportRow("github", input.github),
    supportRow("slack", input.slack),
  ].filter((row) => !visibleConnectorIds || visibleConnectorIds.has(row.id));
  const actionTypes = actionTypesForCoverage(input);
  const coverageRows = buildCoverageRows(actionTypes, proofRows, registryConnectorHints(input.registry));
  const counts: ConnectorInventoryCounts = {
    proofTotal: proofRows.length,
    healthyVerifiers: proofRows.filter((row) => row.state === "ready").length,
    failingVerifiers: proofRows.filter((row) => row.state === "failing" || row.state === "mismatched").length,
    notConfigured: proofRows.filter((row) => row.state === "missing").length,
    notTested: proofRows.filter((row) => row.state === "not_tested").length,
    supportTotal: supportRows.length,
    supportConnected: supportRows.filter((row) => row.connected).length,
    matchedChecks: checks.filter((check) => check.verdict === "matched").length,
    coveragePercent: coveragePercent(coverageRows),
    actionTypesTotal: coverageRows.length,
    unverifiableActionTypes: coverageRows.filter((row) => row.status === "unverifiable").length,
  };
  const rows = [...proofRows, ...supportRows];

  return {
    rows,
    proofRows,
    supportRows,
    transportGroups: buildTransportGroups(rows),
    categoryGroups: buildCategoryGroups(rows),
    coverageRows,
    counts,
    verdict: inventoryVerdict(counts, Boolean(input.partialFailure)),
    registry: registryCounts(input.registry),
  };
}

export function connectorUpdatedLabel(row: Pick<ConnectorInventoryRow, "updatedAt">): string {
  return row.updatedAt ? formatDateTime(row.updatedAt) : "Not checked";
}

export function connectorStateTone(state: ConnectorInventoryState): StatusTone {
  return state === "ready" ? "success" : state === "missing" || state === "not_tested" ? "warning" : statusTone(state);
}

export function connectorStateLabel(state: ConnectorInventoryState): string {
  if (state === "not_tested") return "Needs preflight";
  if (state === "ready") return "Healthy";
  return statusLabel(state);
}
