import type { LucideIcon } from "lucide-react";
import { CheckCircle2, Database, GitBranch, Globe2, Headphones, Landmark, Mail, ShoppingBag } from "lucide-react";

export type ToolCatalogStatus = "available" | "needs_config" | "coming_next" | "fallback";

export interface ToolCatalogItem {
  name: string;
  connectorId: string;
  category: string;
  status: ToolCatalogStatus;
  useCase: string;
  proof: string;
}

export const TOOL_CATALOG: ToolCatalogItem[] = [
  {
    name: "Stripe Refund",
    connectorId: "stripe_refund",
    category: "Payments",
    status: "available",
    useCase: "Refund verification for SaaS and support agents.",
    proof: "Saved connector test plus outcome reconciliation.",
  },
  {
    name: "Stripe Payment",
    connectorId: "stripe_payment",
    category: "Payments",
    status: "available",
    useCase: "Payment, PaymentIntent, or Charge status verification.",
    proof: "Read-only Stripe payment lookup and reconciliation.",
  },
  {
    name: "Razorpay Refund",
    connectorId: "razorpay_refund",
    category: "Payments",
    status: "available",
    useCase: "India-first refund and payment confirmation evidence.",
    proof: "Signed webhook, payment recovery, and refund lookup.",
  },
  {
    name: "Ledger Refund",
    connectorId: "ledger_refund_api",
    category: "Payments",
    status: "available",
    useCase: "Internal ledger or finance API refund evidence.",
    proof: "HTTP record fetch with saved secret isolation.",
  },
  {
    name: "Shopify Admin",
    connectorId: "shopify_admin",
    category: "Commerce",
    status: "available",
    useCase: "Order, refund, fulfillment, and customer evidence.",
    proof: "Read-only Shopify Admin record lookup and reconciliation.",
  },
  {
    name: "HubSpot CRM",
    connectorId: "hubspot_crm",
    category: "CRM",
    status: "available",
    useCase: "Customer/account field verification.",
    proof: "CRM record reconciliation.",
  },
  {
    name: "Salesforce CRM",
    connectorId: "salesforce_crm",
    category: "CRM",
    status: "available",
    useCase: "Enterprise account, case, and opportunity verification.",
    proof: "CRM record reconciliation.",
  },
  {
    name: "Zoho CRM",
    connectorId: "zoho_crm",
    category: "CRM",
    status: "available",
    useCase: "SMB CRM record verification.",
    proof: "CRM record reconciliation.",
  },
  {
    name: "Zendesk Ticket",
    connectorId: "zendesk_ticket",
    category: "Support",
    status: "available",
    useCase: "Support ticket status and customer-message evidence.",
    proof: "Ticket record reconciliation.",
  },
  {
    name: "Jira Issue",
    connectorId: "jira_issue",
    category: "Support",
    status: "available",
    useCase: "Engineering/support issue state evidence.",
    proof: "Issue record reconciliation.",
  },
  {
    name: "NetSuite Finance",
    connectorId: "netsuite_finance",
    category: "Finance",
    status: "available",
    useCase: "Finance record verification for billing ops.",
    proof: "Finance record reconciliation.",
  },
  {
    name: "Postgres Read",
    connectorId: "postgres_read",
    category: "Data",
    status: "available",
    useCase: "Read-only source-of-record evidence from customer DB.",
    proof: "Parameterized read verification.",
  },
  {
    name: "Generic REST",
    connectorId: "generic_rest_api",
    category: "Custom fallback",
    status: "fallback",
    useCase: "Only when a native connector does not exist yet.",
    proof: "Custom endpoint record reconciliation.",
  },
];

export const TOOL_CATEGORY_ICONS: Record<string, LucideIcon> = {
  Payments: Landmark,
  Commerce: ShoppingBag,
  CRM: Database,
  Support: Headphones,
  Finance: Landmark,
  Data: Database,
  "Custom fallback": Globe2,
};

export const TOOL_STATUS_LABELS: Record<ToolCatalogStatus, string> = {
  available: "Available",
  needs_config: "Needs config",
  coming_next: "Coming next",
  fallback: "Custom fallback",
};

export const TOOL_SUMMARY_ICONS = {
  available: CheckCircle2,
  roadmap: GitBranch,
  fallback: Globe2,
  default: Mail,
} as const;
