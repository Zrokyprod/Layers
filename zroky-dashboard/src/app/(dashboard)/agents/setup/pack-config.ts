import type { ActionPackResponse } from "@/lib/api";

export const PRIMARY_PACK_IDS = ["support-ops-v1", "finance-ops-v1", "devops-release-v1", "ecommerce-ops-v1"];
export const LAUNCH_READY_PACK_IDS = new Set(["support-ops-v1", "devops-release-v1"]);
export const DEFAULT_PACK_ID = "support-ops-v1";

export const PACK_SHORT_COPY: Record<string, string> = {
  "support-ops-v1": "Refunds, CRM updates, access changes, and support messages.",
  "finance-ops-v1": "Invoice approvals, vendor payouts, journal entries, and finance records.",
  "devops-release-v1": "Deploy changes, CI gates, approval, and release proof.",
  "ecommerce-ops-v1": "Order changes, inventory updates, discounts, refunds, and fulfillment state.",
};

export const CONNECTOR_LABELS: Record<string, string> = {
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

export const SUPPORT_ENGINES = [
  {
    id: "zendesk",
    label: "Zendesk",
    summary: "Tickets, escalations, customer messages.",
    connectors: ["zendesk_ticket"],
  },
  {
    id: "intercom",
    label: "Intercom",
    summary: "Conversations, support handoff, customer messages.",
    connectors: ["intercom", "ticket_status", "email_delivery"],
  },
  {
    id: "freshdesk",
    label: "Freshdesk",
    summary: "Ticket status and support workflow proof.",
    connectors: ["freshdesk_ticket", "ticket_status"],
  },
  {
    id: "hubspot",
    label: "HubSpot Service Hub",
    summary: "Tickets plus CRM/customer record updates.",
    connectors: ["crm_record", "ticket_status"],
  },
  {
    id: "salesforce",
    label: "Salesforce Service Cloud",
    summary: "Cases, accounts, contacts, escalation workflows.",
    connectors: ["crm_record", "ticket_status"],
  },
  {
    id: "custom",
    label: "Custom support engine",
    summary: "Use Generic REST for internal support tools.",
    connectors: ["generic_rest"],
  },
] as const;
export const DEFAULT_SUPPORT_ENGINE_ID = "zendesk";

export const SUPPORT_CAPABILITIES = [
  {
    id: "tickets",
    label: "Resolve tickets",
    summary: "Close, escalate, or update support tickets.",
    contractVersions: ["support.ticket.close/1.0", "support.ticket.escalate/1.0"],
    connectors: ["ticket_status"],
  },
  {
    id: "messages",
    label: "Send customer messages",
    summary: "External replies, notices, and delivery proof.",
    contractVersions: ["customer.message.send/1.0"],
    connectors: ["email_delivery"],
  },
  {
    id: "refunds",
    label: "Issue refunds or credits",
    summary: "Refunds, refund cancellation, coupons, credits.",
    contractVersions: [
      "customer.refund.transfer/1.0",
      "customer.refund.create/1.0",
      "customer.refund.cancel/1.0",
      "customer.coupon.issue/1.0",
      "customer.credit.issue/1.0",
    ],
    connectors: ["ledger_refund", "subscription_billing"],
  },
  {
    id: "crm",
    label: "Update customer records",
    summary: "CRM fields, account status, lifecycle state.",
    contractVersions: ["customer.record.update/1.0", "customer.account.status.change/1.0"],
    connectors: ["crm_record"],
  },
  {
    id: "subscriptions",
    label: "Change subscriptions",
    summary: "Pause, cancel, or reactivate subscriptions.",
    contractVersions: [
      "customer.subscription.pause/1.0",
      "customer.subscription.cancel/1.0",
      "customer.subscription.reactivate/1.0",
    ],
    connectors: ["subscription_billing"],
  },
  {
    id: "access",
    label: "Grant or revoke access",
    summary: "Roles, account access, support-assisted permissions.",
    contractVersions: ["customer.access.grant/1.0", "customer.access.revoke/1.0"],
    connectors: ["customer_identity"],
  },
  {
    id: "identity",
    label: "Change identity details",
    summary: "Email or phone changes with account-takeover controls.",
    contractVersions: ["customer.identity.email.change/1.0", "customer.identity.phone.change/1.0"],
    connectors: ["customer_identity"],
  },
  {
    id: "privacy",
    label: "Export customer data",
    summary: "Data export and sensitive bulk-read sequence risk.",
    contractVersions: ["customer.data.export/1.0", "customer.bulk.read/1.0"],
    connectors: ["generic_rest", "crm_record"],
  },
] as const;
export type SupportCapabilityId = (typeof SUPPORT_CAPABILITIES)[number]["id"];
export const DEFAULT_SUPPORT_CAPABILITIES: SupportCapabilityId[] = ["tickets", "refunds", "crm"];

export const FINANCE_SYSTEMS = [
  {
    id: "netsuite",
    label: "NetSuite",
    summary: "ERP finance records, vendor bills, approvals.",
    connectors: ["netsuite_finance", "erp_finance"],
  },
  {
    id: "stripe",
    label: "Stripe Payments",
    summary: "Payment status and settlement proof.",
    connectors: ["stripe_payment", "payments_ledger"],
  },
  {
    id: "generic",
    label: "Generic Finance API",
    summary: "Internal ERP, ledger, or finance service.",
    connectors: ["generic_finance", "erp_finance", "accounting_system"],
  },
  {
    id: "postgres",
    label: "Postgres Read",
    summary: "Read-only checks against finance tables.",
    connectors: ["postgres_read", "accounting_system"],
  },
  {
    id: "quickbooks",
    label: "QuickBooks template",
    summary: "Use the generic finance path until native setup ships.",
    connectors: ["quickbooks_ledger", "generic_finance"],
  },
] as const;
export const DEFAULT_FINANCE_SYSTEM_ID = "netsuite";

export const FINANCE_CAPABILITIES = [
  {
    id: "invoice",
    label: "Approve invoices",
    summary: "Confirm invoice, vendor, PO, amount.",
    contractVersions: ["finance.invoice.approve/1.0"],
    connectors: ["erp_finance", "netsuite_finance", "slack_approval_alert"],
  },
  {
    id: "journal",
    label: "Create journal entries",
    summary: "Check account, direction, period, amount.",
    contractVersions: ["finance.journal.entry/1.0"],
    connectors: ["accounting_system", "netsuite_finance", "postgres_read"],
  },
  {
    id: "payout",
    label: "Send vendor payouts",
    summary: "Hold transfers until approval and ledger proof.",
    contractVersions: ["finance.vendor.payout/1.0"],
    connectors: ["payments_ledger", "stripe_payment", "slack_approval_alert"],
  },
] as const;
export type FinanceCapabilityId = (typeof FINANCE_CAPABILITIES)[number]["id"];
export const DEFAULT_FINANCE_CAPABILITIES: FinanceCapabilityId[] = ["invoice", "journal", "payout"];

export const DEVOPS_SYSTEMS = [
  {
    id: "github",
    label: "GitHub CI / deploy",
    summary: "PR, check-run, SHA, and deployment proof.",
    connectors: ["github_ci"],
  },
  {
    id: "generic",
    label: "Generic deploy API",
    summary: "Internal deploy service or release API.",
    connectors: ["generic_rest"],
  },
  {
    id: "slack",
    label: "Slack approval path",
    summary: "Human approval before release execution.",
    connectors: ["slack_approval_alert"],
  },
] as const;
export const DEFAULT_DEVOPS_SYSTEM_ID = "github";

export const DEVOPS_CAPABILITIES = [
  {
    id: "deploy",
    label: "Deploy a change",
    summary: "Guard a release by repository, environment, and SHA.",
    contractVersions: ["devops.deploy.change/1.0"],
    connectors: ["github_ci", "slack_approval_alert"],
  },
  {
    id: "promote",
    label: "Promote a PR or revision",
    summary: "Move a checked revision toward production.",
    contractVersions: ["devops.deploy.change/1.0"],
    connectors: ["github_ci"],
  },
  {
    id: "production",
    label: "Change production environment",
    summary: "Require approval and environment match before release.",
    contractVersions: ["devops.deploy.change/1.0"],
    connectors: ["generic_rest", "slack_approval_alert"],
  },
] as const;
export type DevopsCapabilityId = (typeof DEVOPS_CAPABILITIES)[number]["id"];
export const DEFAULT_DEVOPS_CAPABILITIES: DevopsCapabilityId[] = ["deploy", "promote", "production"];

export const ECOMMERCE_SYSTEMS = [
  {
    id: "shopify",
    label: "Shopify Admin",
    summary: "Order, customer, discount, and inventory proof.",
    connectors: ["shopify_admin", "commerce_platform"],
  },
  {
    id: "order",
    label: "Order management",
    summary: "Order status and cancellation source of record.",
    connectors: ["order_management"],
  },
  {
    id: "inventory",
    label: "Inventory system",
    summary: "SKU, warehouse, and stock-level verification.",
    connectors: ["inventory_system"],
  },
  {
    id: "generic",
    label: "Generic commerce API",
    summary: "Custom store, OMS, or fulfillment service.",
    connectors: ["generic_rest", "commerce_platform"],
  },
] as const;
export const DEFAULT_ECOMMERCE_SYSTEM_ID = "shopify";

export const ECOMMERCE_CAPABILITIES = [
  {
    id: "cancel",
    label: "Cancel orders",
    summary: "Verify order state, reason, and restock behavior.",
    contractVersions: ["commerce.order.cancel/1.0"],
    connectors: ["order_management", "shopify_admin", "slack_approval_alert"],
  },
  {
    id: "inventory",
    label: "Adjust inventory",
    summary: "Check SKU, location, and quantity delta.",
    contractVersions: ["commerce.inventory.adjust/1.0"],
    connectors: ["inventory_system", "shopify_admin"],
  },
  {
    id: "discount",
    label: "Issue discounts",
    summary: "Control customer credits, codes, amount, and currency.",
    contractVersions: ["commerce.discount.issue/1.0"],
    connectors: ["commerce_platform", "shopify_admin", "slack_approval_alert"],
  },
] as const;
export type EcommerceCapabilityId = (typeof ECOMMERCE_CAPABILITIES)[number]["id"];
export const DEFAULT_ECOMMERCE_CAPABILITIES: EcommerceCapabilityId[] = ["cancel", "inventory", "discount"];

export function uniqueItems(items: readonly string[]) {
  return Array.from(new Set(items.filter(Boolean)));
}

function contractIdentifiers(contract: ActionPackResponse["contract_templates"][number]) {
  return [
    contract.contract_version,
    contract.contract_key && contract.version ? `${contract.contract_key}/${contract.version}` : "",
    contract.contract_key,
  ]
    .filter(Boolean)
    .map((value) => value.toLowerCase());
}

function contractsFor(pack: ActionPackResponse, contractVersions: readonly string[]) {
  const requested = new Set(contractVersions.map((version) => version.toLowerCase()));
  return pack.contract_templates.filter((contract) =>
    contractIdentifiers(contract).some((identifier) => requested.has(identifier)),
  );
}

export function supportCapabilityById(id: SupportCapabilityId) {
  return SUPPORT_CAPABILITIES.find((item) => item.id === id) ?? SUPPORT_CAPABILITIES[0];
}

export function supportEngineById(id: string) {
  return SUPPORT_ENGINES.find((item) => item.id === id) ?? SUPPORT_ENGINES[0];
}

export function supportContractsFor(pack: ActionPackResponse, capabilityIds: readonly SupportCapabilityId[]) {
  return contractsFor(pack, capabilityIds.flatMap((id) => supportCapabilityById(id).contractVersions));
}

export function supportConnectorsFor(engineId: string, capabilityIds: readonly SupportCapabilityId[]) {
  return uniqueItems([
    ...supportEngineById(engineId).connectors,
    ...capabilityIds.flatMap((id) => supportCapabilityById(id).connectors),
    "slack_approval_alert",
  ]);
}

export function financeCapabilityById(id: FinanceCapabilityId) {
  return FINANCE_CAPABILITIES.find((item) => item.id === id) ?? FINANCE_CAPABILITIES[0];
}

export function financeSystemById(id: string) {
  return FINANCE_SYSTEMS.find((item) => item.id === id) ?? FINANCE_SYSTEMS[0];
}

export function financeContractsFor(pack: ActionPackResponse, capabilityIds: readonly FinanceCapabilityId[]) {
  return contractsFor(pack, capabilityIds.flatMap((id) => financeCapabilityById(id).contractVersions));
}

export function financeConnectorsFor(systemId: string, capabilityIds: readonly FinanceCapabilityId[]) {
  return uniqueItems([
    ...financeSystemById(systemId).connectors,
    ...capabilityIds.flatMap((id) => financeCapabilityById(id).connectors),
    "slack_approval_alert",
  ]);
}

export function devopsCapabilityById(id: DevopsCapabilityId) {
  return DEVOPS_CAPABILITIES.find((item) => item.id === id) ?? DEVOPS_CAPABILITIES[0];
}

export function devopsSystemById(id: string) {
  return DEVOPS_SYSTEMS.find((item) => item.id === id) ?? DEVOPS_SYSTEMS[0];
}

export function devopsContractsFor(pack: ActionPackResponse, capabilityIds: readonly DevopsCapabilityId[]) {
  return contractsFor(pack, capabilityIds.flatMap((id) => devopsCapabilityById(id).contractVersions));
}

export function devopsConnectorsFor(systemId: string, capabilityIds: readonly DevopsCapabilityId[]) {
  return uniqueItems([
    ...devopsSystemById(systemId).connectors,
    ...capabilityIds.flatMap((id) => devopsCapabilityById(id).connectors),
    "slack_approval_alert",
  ]);
}

export function ecommerceCapabilityById(id: EcommerceCapabilityId) {
  return ECOMMERCE_CAPABILITIES.find((item) => item.id === id) ?? ECOMMERCE_CAPABILITIES[0];
}

export function ecommerceSystemById(id: string) {
  return ECOMMERCE_SYSTEMS.find((item) => item.id === id) ?? ECOMMERCE_SYSTEMS[0];
}

export function ecommerceContractsFor(pack: ActionPackResponse, capabilityIds: readonly EcommerceCapabilityId[]) {
  return contractsFor(pack, capabilityIds.flatMap((id) => ecommerceCapabilityById(id).contractVersions));
}

export function ecommerceConnectorsFor(systemId: string, capabilityIds: readonly EcommerceCapabilityId[]) {
  return uniqueItems([
    ...ecommerceSystemById(systemId).connectors,
    ...capabilityIds.flatMap((id) => ecommerceCapabilityById(id).connectors),
    "slack_approval_alert",
  ]);
}

export function packSort(a: ActionPackResponse, b: ActionPackResponse) {
  const ai = PRIMARY_PACK_IDS.indexOf(a.id);
  const bi = PRIMARY_PACK_IDS.indexOf(b.id);
  return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
}
