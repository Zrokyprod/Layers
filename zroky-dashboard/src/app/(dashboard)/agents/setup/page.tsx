"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  CheckCircle2,
  Copy,
  KeyRound,
  PlayCircle,
  ShieldCheck,
} from "lucide-react";

import { DashboardButton, DashboardButtonLink } from "@/components/dashboard-button";
import { DashboardVerdictHero } from "@/components/dashboard-scaffold";
import {
  createProjectApiKey,
  createAgentProfile,
  enforceAgentProfile,
  getProjectSettings,
  installActionPack,
  listActionIntents,
  listActionPacks,
  listAgentProfiles,
  listProjectApiKeys,
  type ActionPackResponse,
  type AgentProfileResponse,
} from "@/lib/api";
import type { ApiKeyCreateResponse, ApiKeyResponse } from "@/lib/types";

const FRAMEWORKS = [
  "OpenAI Agents SDK",
  "LangGraph",
  "CrewAI",
  "AutoGen",
  "MCP client",
  "Custom agent runtime",
];

const ENVIRONMENTS = ["production", "staging", "development"];
const DEFAULT_RUNTIME_KEY_NAME = "Protected agent runtime key";
type SetupStep = "key" | "connect" | "pack" | "run" | "next";

const PRIMARY_PACK_IDS = ["support-ops-v1", "finance-ops-v1", "devops-release-v1", "ecommerce-ops-v1"];
const DEFAULT_PACK_ID = "support-ops-v1";
const PACK_SHORT_COPY: Record<string, string> = {
  "support-ops-v1": "Refunds, CRM updates, access changes, and support messages.",
  "finance-ops-v1": "Invoice approvals, vendor payouts, journal entries, and finance records.",
  "devops-release-v1": "Deploy changes, CI gates, approval, and release proof.",
  "ecommerce-ops-v1": "Order changes, inventory updates, discounts, refunds, and fulfillment state.",
};
const CONNECTOR_LABELS: Record<string, string> = {
  accounting_system: "Accounting system",
  commerce_platform: "Commerce platform",
  crm_record: "CRM record",
  customer_identity: "Customer identity",
  erp_finance: "ERP finance",
  email_delivery: "Email/messages",
  generic_finance: "Generic Finance API",
  generic_rest: "Generic REST",
  github_ci: "GitHub CI",
  inventory_system: "Inventory system",
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
const SUPPORT_ENGINES = [
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
    connectors: ["ticket_status", "email_delivery"],
  },
  {
    id: "freshdesk",
    label: "Freshdesk",
    summary: "Ticket status and support workflow proof.",
    connectors: ["ticket_status", "generic_rest"],
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
const DEFAULT_SUPPORT_ENGINE_ID = "zendesk";
const SUPPORT_CAPABILITIES = [
  {
    id: "tickets",
    label: "Resolve tickets",
    summary: "Close, escalate, or update support tickets.",
    contractMarkers: ["support.ticket"],
    connectors: ["zendesk_ticket", "ticket_status"],
  },
  {
    id: "messages",
    label: "Send customer messages",
    summary: "External replies, notices, and delivery proof.",
    contractMarkers: ["customer.message"],
    connectors: ["email_delivery"],
  },
  {
    id: "refunds",
    label: "Issue refunds or credits",
    summary: "Refunds, refund cancellation, coupons, credits.",
    contractMarkers: ["customer.refund", "customer.coupon", "customer.credit", "refund"],
    connectors: ["ledger_refund", "subscription_billing"],
  },
  {
    id: "crm",
    label: "Update customer records",
    summary: "CRM fields, account status, lifecycle state.",
    contractMarkers: ["customer.record", "customer.account", "customer_record_update"],
    connectors: ["crm_record"],
  },
  {
    id: "subscriptions",
    label: "Change subscriptions",
    summary: "Pause, cancel, or reactivate subscriptions.",
    contractMarkers: ["customer.subscription"],
    connectors: ["subscription_billing"],
  },
  {
    id: "access",
    label: "Grant or revoke access",
    summary: "Roles, account access, support-assisted permissions.",
    contractMarkers: ["customer.access"],
    connectors: ["customer_identity"],
  },
  {
    id: "identity",
    label: "Change identity details",
    summary: "Email or phone changes with account-takeover controls.",
    contractMarkers: ["customer.identity"],
    connectors: ["customer_identity"],
  },
  {
    id: "privacy",
    label: "Export customer data",
    summary: "Data export and sensitive bulk-read sequence risk.",
    contractMarkers: ["customer.data", "customer.bulk"],
    connectors: ["generic_rest", "crm_record"],
  },
] as const;
type SupportCapabilityId = (typeof SUPPORT_CAPABILITIES)[number]["id"];
const DEFAULT_SUPPORT_CAPABILITIES: SupportCapabilityId[] = ["tickets", "refunds", "crm"];

const FINANCE_SYSTEMS = [
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
const DEFAULT_FINANCE_SYSTEM_ID = "netsuite";
const FINANCE_CAPABILITIES = [
  {
    id: "invoice",
    label: "Approve invoices",
    summary: "Confirm invoice, vendor, PO, amount.",
    contractMarkers: ["finance.invoice", "invoice_approve"],
    connectors: ["erp_finance", "netsuite_finance", "slack_approval_alert"],
  },
  {
    id: "journal",
    label: "Create journal entries",
    summary: "Check account, direction, period, amount.",
    contractMarkers: ["finance.journal", "journal_entry"],
    connectors: ["accounting_system", "netsuite_finance", "postgres_read"],
  },
  {
    id: "payout",
    label: "Send vendor payouts",
    summary: "Hold transfers until approval and ledger proof.",
    contractMarkers: ["finance.vendor", "vendor_payout"],
    connectors: ["payments_ledger", "stripe_payment", "slack_approval_alert"],
  },
] as const;
type FinanceCapabilityId = (typeof FINANCE_CAPABILITIES)[number]["id"];
const DEFAULT_FINANCE_CAPABILITIES: FinanceCapabilityId[] = ["invoice", "journal", "payout"];

const DEVOPS_SYSTEMS = [
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
const DEFAULT_DEVOPS_SYSTEM_ID = "github";
const DEVOPS_CAPABILITIES = [
  {
    id: "deploy",
    label: "Deploy a change",
    summary: "Guard a release by repository, environment, and SHA.",
    contractMarkers: ["devops.deploy", "deploy_change"],
    connectors: ["github_ci", "slack_approval_alert"],
  },
  {
    id: "promote",
    label: "Promote a PR or revision",
    summary: "Move a checked revision toward production.",
    contractMarkers: ["devops.deploy", "deploy_change"],
    connectors: ["github_ci"],
  },
  {
    id: "production",
    label: "Change production environment",
    summary: "Require approval and environment match before release.",
    contractMarkers: ["devops.deploy", "deploy_change"],
    connectors: ["generic_rest", "slack_approval_alert"],
  },
] as const;
type DevopsCapabilityId = (typeof DEVOPS_CAPABILITIES)[number]["id"];
const DEFAULT_DEVOPS_CAPABILITIES: DevopsCapabilityId[] = ["deploy", "promote", "production"];

const ECOMMERCE_SYSTEMS = [
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
const DEFAULT_ECOMMERCE_SYSTEM_ID = "shopify";
const ECOMMERCE_CAPABILITIES = [
  {
    id: "cancel",
    label: "Cancel orders",
    summary: "Verify order state, reason, and restock behavior.",
    contractMarkers: ["commerce.order", "order_cancel"],
    connectors: ["order_management", "shopify_admin", "slack_approval_alert"],
  },
  {
    id: "inventory",
    label: "Adjust inventory",
    summary: "Check SKU, location, and quantity delta.",
    contractMarkers: ["commerce.inventory", "inventory_adjust"],
    connectors: ["inventory_system", "shopify_admin"],
  },
  {
    id: "discount",
    label: "Issue discounts",
    summary: "Control customer credits, codes, amount, and currency.",
    contractMarkers: ["commerce.discount", "discount_issue"],
    connectors: ["commerce_platform", "shopify_admin", "slack_approval_alert"],
  },
] as const;
type EcommerceCapabilityId = (typeof ECOMMERCE_CAPABILITIES)[number]["id"];
const DEFAULT_ECOMMERCE_CAPABILITIES: EcommerceCapabilityId[] = ["cancel", "inventory", "discount"];

function keyIsActive(key: ApiKeyResponse) {
  return !key.revoked && !key.expired;
}

function runtimeCredentialRef(keyPrefix: string | undefined) {
  const normalized = (keyPrefix ?? "project-runtime-key")
    .trim()
    .replace(/[^a-zA-Z0-9_.-]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return `customer-runner-secret://zroky/project-key/${normalized || "project-runtime-key"}`;
}

function CopyableCode({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard can be unavailable in restricted browser contexts.
    }
  }
  return (
    <div className="agent-quickstart-code">
      <div className="agent-quickstart-code-head">
        <span>{label}</span>
        <button type="button" onClick={copy} aria-label={`Copy ${label}`}>
          <Copy size={13} aria-hidden="true" />
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre>{value}</pre>
    </div>
  );
}

function CopyableCommand({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard can be unavailable in restricted browser contexts.
    }
  }
  return (
    <div className="agent-command-row">
      <span>{label}</span>
      <code>{value}</code>
      <button type="button" onClick={copy} aria-label={`Copy ${label}`}>
        <Copy size={13} aria-hidden="true" />
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}

function stepStateLabel(activeStep: SetupStep, step: SetupStep, done: boolean) {
  if (done) return "Done";
  if (activeStep === step) return "Now";
  return "Locked";
}

function visibleStepState(activeStep: SetupStep, step: SetupStep, done: boolean) {
  if (step === "key") {
    return done ? "Ready" : "Not created";
  }
  return stepStateLabel(activeStep, step, done);
}

function actionLabel(actionType: string) {
  return actionType
    .replace(/[_.]/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function connectorLabel(connector: string) {
  return CONNECTOR_LABELS[connector] ?? actionLabel(connector);
}

function uniqueItems(items: string[]) {
  return Array.from(new Set(items.filter(Boolean)));
}

function supportCapabilityById(id: SupportCapabilityId) {
  return SUPPORT_CAPABILITIES.find((item) => item.id === id) ?? SUPPORT_CAPABILITIES[0];
}

function supportEngineById(id: string) {
  return SUPPORT_ENGINES.find((item) => item.id === id) ?? SUPPORT_ENGINES[0];
}

function supportContractsFor(pack: ActionPackResponse, capabilityIds: SupportCapabilityId[]) {
  const markers = capabilityIds.flatMap((id) => supportCapabilityById(id).contractMarkers);
  return pack.contract_templates.filter((contract) => {
    const haystack = `${contract.contract_key} ${contract.action_type}`.toLowerCase();
    return markers.some((marker) => haystack.includes(marker.toLowerCase()));
  });
}

function supportConnectorsFor(engineId: string, capabilityIds: SupportCapabilityId[]) {
  return uniqueItems([
    ...supportEngineById(engineId).connectors,
    ...capabilityIds.flatMap((id) => supportCapabilityById(id).connectors),
    "slack_approval_alert",
  ]);
}

function financeCapabilityById(id: FinanceCapabilityId) {
  return FINANCE_CAPABILITIES.find((item) => item.id === id) ?? FINANCE_CAPABILITIES[0];
}

function financeSystemById(id: string) {
  return FINANCE_SYSTEMS.find((item) => item.id === id) ?? FINANCE_SYSTEMS[0];
}

function financeContractsFor(pack: ActionPackResponse, capabilityIds: FinanceCapabilityId[]) {
  const markers = capabilityIds.flatMap((id) => financeCapabilityById(id).contractMarkers);
  return pack.contract_templates.filter((contract) => {
    const haystack = `${contract.contract_key} ${contract.action_type}`.toLowerCase();
    return markers.some((marker) => haystack.includes(marker.toLowerCase()));
  });
}

function financeConnectorsFor(systemId: string, capabilityIds: FinanceCapabilityId[]) {
  return uniqueItems([
    ...financeSystemById(systemId).connectors,
    ...capabilityIds.flatMap((id) => financeCapabilityById(id).connectors),
    "slack_approval_alert",
  ]);
}

function devopsCapabilityById(id: DevopsCapabilityId) {
  return DEVOPS_CAPABILITIES.find((item) => item.id === id) ?? DEVOPS_CAPABILITIES[0];
}

function devopsSystemById(id: string) {
  return DEVOPS_SYSTEMS.find((item) => item.id === id) ?? DEVOPS_SYSTEMS[0];
}

function devopsContractsFor(pack: ActionPackResponse, capabilityIds: DevopsCapabilityId[]) {
  const markers = capabilityIds.flatMap((id) => devopsCapabilityById(id).contractMarkers);
  return pack.contract_templates.filter((contract) => {
    const haystack = `${contract.contract_key} ${contract.action_type}`.toLowerCase();
    return markers.some((marker) => haystack.includes(marker.toLowerCase()));
  });
}

function devopsConnectorsFor(systemId: string, capabilityIds: DevopsCapabilityId[]) {
  return uniqueItems([
    ...devopsSystemById(systemId).connectors,
    ...capabilityIds.flatMap((id) => devopsCapabilityById(id).connectors),
    "slack_approval_alert",
  ]);
}

function ecommerceCapabilityById(id: EcommerceCapabilityId) {
  return ECOMMERCE_CAPABILITIES.find((item) => item.id === id) ?? ECOMMERCE_CAPABILITIES[0];
}

function ecommerceSystemById(id: string) {
  return ECOMMERCE_SYSTEMS.find((item) => item.id === id) ?? ECOMMERCE_SYSTEMS[0];
}

function ecommerceContractsFor(pack: ActionPackResponse, capabilityIds: EcommerceCapabilityId[]) {
  const markers = capabilityIds.flatMap((id) => ecommerceCapabilityById(id).contractMarkers);
  return pack.contract_templates.filter((contract) => {
    const haystack = `${contract.contract_key} ${contract.action_type}`.toLowerCase();
    return markers.some((marker) => haystack.includes(marker.toLowerCase()));
  });
}

function ecommerceConnectorsFor(systemId: string, capabilityIds: EcommerceCapabilityId[]) {
  return uniqueItems([
    ...ecommerceSystemById(systemId).connectors,
    ...capabilityIds.flatMap((id) => ecommerceCapabilityById(id).connectors),
    "slack_approval_alert",
  ]);
}

function packSort(a: ActionPackResponse, b: ActionPackResponse) {
  const ai = PRIMARY_PACK_IDS.indexOf(a.id);
  const bi = PRIMARY_PACK_IDS.indexOf(b.id);
  return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
}

export default function ProtectedAgentSetupPage() {
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();

  const [agentName, setAgentName] = useState(() => (searchParams.get("agentName") ?? "").trim());
  const [framework, setFramework] = useState(FRAMEWORKS[0]);
  const [environment, setEnvironment] = useState(ENVIRONMENTS[0]);
  const [profile, setProfile] = useState<AgentProfileResponse | null>(null);
  const [newRuntimeKey, setNewRuntimeKey] = useState<ApiKeyCreateResponse | null>(null);
  const [runtimeKeyCopied, setRuntimeKeyCopied] = useState(false);
  const [runtimeStatus, setRuntimeStatus] = useState<string | null>(null);
  const [selectedPackId, setSelectedPackId] = useState(DEFAULT_PACK_ID);
  const [supportEngineId, setSupportEngineId] = useState(DEFAULT_SUPPORT_ENGINE_ID);
  const [supportCapabilityIds, setSupportCapabilityIds] = useState<SupportCapabilityId[]>(DEFAULT_SUPPORT_CAPABILITIES);
  const [financeSystemId, setFinanceSystemId] = useState(DEFAULT_FINANCE_SYSTEM_ID);
  const [financeCapabilityIds, setFinanceCapabilityIds] = useState<FinanceCapabilityId[]>(DEFAULT_FINANCE_CAPABILITIES);
  const [devopsSystemId, setDevopsSystemId] = useState(DEFAULT_DEVOPS_SYSTEM_ID);
  const [devopsCapabilityIds, setDevopsCapabilityIds] = useState<DevopsCapabilityId[]>(DEFAULT_DEVOPS_CAPABILITIES);
  const [ecommerceSystemId, setEcommerceSystemId] = useState(DEFAULT_ECOMMERCE_SYSTEM_ID);
  const [ecommerceCapabilityIds, setEcommerceCapabilityIds] =
    useState<EcommerceCapabilityId[]>(DEFAULT_ECOMMERCE_CAPABILITIES);
  const [installedPack, setInstalledPack] = useState<ActionPackResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const projectQuery = useQuery({
    queryKey: ["agent-setup", "project"],
    queryFn: ({ signal }) => getProjectSettings(signal),
    retry: false,
  });
  const projectId = projectQuery.data?.project_id ?? "";
  const keysQuery = useQuery({
    queryKey: ["agent-setup", "project-api-keys", projectId],
    queryFn: ({ signal }) => listProjectApiKeys(projectId, signal),
    enabled: Boolean(projectId),
    retry: false,
  });
  const activeRuntimeKeys = (keysQuery.data ?? []).filter(keyIsActive);
  const hasRuntimeKey = Boolean(newRuntimeKey) || activeRuntimeKeys.length > 0;
  const runtimeKeyPrefix = newRuntimeKey?.key_prefix ?? activeRuntimeKeys[0]?.key_prefix;
  const profilesQuery = useQuery({
    queryKey: ["agent-setup", "profiles"],
    queryFn: ({ signal }) => listAgentProfiles({ limit: 50 }, signal),
    enabled: hasRuntimeKey,
    retry: false,
  });
  const existingProfile = profilesQuery.data?.items?.[0] ?? null;
  const connectedProfile = profile ?? existingProfile;
  const packsQuery = useQuery({
    queryKey: ["agent-setup", "action-packs"],
    queryFn: ({ signal }) => listActionPacks(signal),
    enabled: Boolean(connectedProfile),
    retry: false,
  });
  const packs = (packsQuery.data?.items ?? [])
    .filter((pack) => PRIMARY_PACK_IDS.includes(pack.id))
    .sort(packSort);
  const selectedPack = packs.find((pack) => pack.id === selectedPackId) ?? packs[0] ?? null;
  const isSupportPack = selectedPack?.id === "support-ops-v1";
  const isFinancePack = selectedPack?.id === "finance-ops-v1";
  const isDevopsPack = selectedPack?.id === "devops-release-v1";
  const isEcommercePack = selectedPack?.id === "ecommerce-ops-v1";
  const selectedSupportContracts = selectedPack && isSupportPack
    ? supportContractsFor(selectedPack, supportCapabilityIds)
    : [];
  const selectedSupportConnectors = selectedPack && isSupportPack
    ? supportConnectorsFor(supportEngineId, supportCapabilityIds)
    : [];
  const selectedFinanceContracts = selectedPack && isFinancePack
    ? financeContractsFor(selectedPack, financeCapabilityIds)
    : [];
  const selectedFinanceConnectors = selectedPack && isFinancePack
    ? financeConnectorsFor(financeSystemId, financeCapabilityIds)
    : [];
  const selectedDevopsContracts = selectedPack && isDevopsPack
    ? devopsContractsFor(selectedPack, devopsCapabilityIds)
    : [];
  const selectedDevopsConnectors = selectedPack && isDevopsPack
    ? devopsConnectorsFor(devopsSystemId, devopsCapabilityIds)
    : [];
  const selectedEcommerceContracts = selectedPack && isEcommercePack
    ? ecommerceContractsFor(selectedPack, ecommerceCapabilityIds)
    : [];
  const selectedEcommerceConnectors = selectedPack && isEcommercePack
    ? ecommerceConnectorsFor(ecommerceSystemId, ecommerceCapabilityIds)
    : [];
  const packInstalled = Boolean(installedPack);

  const createKeyMutation = useMutation({
    mutationFn: async () => {
      if (!projectId) {
        throw new Error("Project is still loading. Try again in a moment.");
      }
      return createProjectApiKey(projectId, {
        name: DEFAULT_RUNTIME_KEY_NAME,
        expires_in_days: 90,
        scopes: ["project:member"],
      });
    },
    onSuccess: (created) => {
      setNewRuntimeKey(created);
      setRuntimeStatus("Project key created. Copy it before leaving this page.");
      void queryClient.invalidateQueries({ queryKey: ["agent-setup", "project-api-keys", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["project-api-keys", projectId] });
    },
    onError: (err) => {
      setRuntimeStatus(err instanceof Error ? err.message : "Could not create the project key.");
    },
  });

  const createMutation = useMutation({
    mutationFn: async () => {
      const created = await createAgentProfile({
        display_name: agentName.trim(),
        description: "",
        runtime_path: "sdk",
        framework,
        environment,
        model_provider: "",
        model_name: "",
        tool_names: ["agent.protected_action"],
        allowed_action_types: ["internal_api_mutation"],
        blocked_action_types: [],
        risk_limits: {
          auto_allow_amount_usd: 0,
          approval_required_above_usd: 500,
          deny_above_usd: 5000,
          approval_ttl_minutes: 60,
        },
        verification_connectors: [],
        metadata: {
          runner_verification: {
            runner_mode: "customer_hosted",
            credential_ref: runtimeCredentialRef(runtimeKeyPrefix),
          },
        },
      });
      // Enforcing with no declared action map applies the safe fail-closed
      // default: unknown actions deny, sensitive actions hold for approval.
      return enforceAgentProfile(created.id);
    },
    onSuccess: (created) => {
      setProfile(created);
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["agents", "profiles"] });
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : "Could not create the agent.");
    },
  });

  const installPackMutation = useMutation({
    mutationFn: async () => {
      if (!selectedPack) {
        throw new Error("Protected action templates are still loading.");
      }
      return installActionPack(selectedPack.id);
    },
    onSuccess: (result) => {
      setInstalledPack(result.pack);
      setError(null);
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : "Could not install protected actions.");
    },
  });

  const firstActionQuery = useQuery({
    queryKey: ["agent-setup", "first-actions", connectedProfile?.id],
    queryFn: ({ signal }) => listActionIntents({ agent_id: connectedProfile?.id ?? null, limit: 5 }, signal),
    enabled: Boolean(connectedProfile?.id),
    refetchInterval: 5_000,
  });
  const firstReceiptQuery = useQuery({
    queryKey: ["agent-setup", "first-receipt", connectedProfile?.id],
    queryFn: ({ signal }) =>
      listActionIntents(
        { agent_id: connectedProfile?.id ?? null, proof_status: "matched", receipt_status: "generated", limit: 1 },
        signal,
      ),
    enabled: Boolean(connectedProfile?.id),
    refetchInterval: 15_000,
  });

  const created = Boolean(connectedProfile);
  const firstAction = firstActionQuery.data?.items[0] ?? null;
  const live = (firstReceiptQuery.data?.items.length ?? 0) > 0;
  const activeStep: SetupStep = !hasRuntimeKey
    ? "key"
    : !created
      ? "connect"
      : !packInstalled
        ? "pack"
        : !live
          ? "run"
          : "next";
  const policyChecked = Boolean(firstAction);
  const maskedRuntimeKey = runtimeKeyPrefix ? `${runtimeKeyPrefix}...` : "zk_live_...";
  const connectedAgentName = connectedProfile?.display_name?.trim() || agentName.trim() || "Agent runtime";
  const actionStatus = firstAction
    ? firstAction.status.replace(/_/g, " ")
    : firstActionQuery.isFetching
      ? "polling"
      : "waiting";

  const keyEnvSnippet = `ZROKY_API_KEY=${maskedRuntimeKey}
ZROKY_PROJECT_ID=${projectId || "proj_..."}`;
  const firstProtectedActionSnippet = `import zroky

zroky.init()

receipt = zroky.protect(
    action="customer.access.grant",
    operation_kind="UPDATE",
    params={"role": "viewer", "reason": "Support case verified"},
    resource={"customer_id": "cus_123"},
    raise_on_approval=False,
)

print(receipt["status"])`;

  async function copyRuntimeKey(value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setRuntimeKeyCopied(true);
      window.setTimeout(() => setRuntimeKeyCopied(false), 1500);
    } catch {
      setRuntimeStatus("Copy failed. Select the key and copy it manually.");
    }
  }

  const verdict = live
    ? {
        tone: "success" as const,
        title: "Agent is live",
        copy: "Your first protected action is captured. Review the receipt, then tune policy from real data.",
        pill: "Live",
      }
    : created
      ? {
          tone: "warning" as const,
          title: "Run a test action",
          copy: "Run one protected action locally. Zroky will capture it and unlock the dashboard.",
          pill: "Capturing",
        }
      : {
          tone: "neutral" as const,
          title: "Protect your first agent",
          copy: "Create a key, define one agent, then send one protected action.",
          pill: "Setup",
        };

  return (
    <div className="agent-setup-screen">
      <DashboardVerdictHero
        eyebrow="Agent Control Setup"
        icon={<ShieldCheck aria-hidden="true" size={18} />}
        title={verdict.title}
        copy={verdict.copy}
        tone={verdict.tone}
        pill={verdict.pill}
        updatedLabel={created ? (live ? "Live" : "Capturing") : "Not started"}
        notices={
          <Link href="/agents" className="agents-text-link">
            <ArrowLeft aria-hidden="true" />
            Agents
          </Link>
        }
        actions={
          created ? (
            <DashboardButtonLink href={`/agents/${connectedProfile?.id ?? ""}`} variant="soft">
              Agent home
            </DashboardButtonLink>
          ) : null
        }
      />

      {error ? <div className="alert-strip agent-setup-alert">{error}</div> : null}

      <section className="agent-quickstart" aria-label="Protect an agent">
        <div className="agent-quickstart-main">
          {/* 1 - Project key */}
          <div
            className="agent-quickstart-card agent-runtime-key-card"
            data-step="key"
            data-active={activeStep === "key" ? "true" : "false"}
            data-done={hasRuntimeKey ? "true" : "false"}
          >
            <div className="agent-quickstart-card-head">
              <span>{hasRuntimeKey ? <CheckCircle2 aria-hidden="true" size={16} /> : "01"}</span>
              <div>
                <strong>Project key</strong>
                <small>Authenticate SDK requests.</small>
              </div>
              <em>{visibleStepState(activeStep, "key", hasRuntimeKey)}</em>
            </div>

            {projectQuery.error ? (
              <p className="agent-setup-status is-error">Project context did not load. Refresh before creating a key.</p>
            ) : newRuntimeKey ? (
              <div className="agent-runtime-key-reveal">
                <div className="agent-runtime-secret">
                  <span className="mono">{maskedRuntimeKey}</span>
                  <button type="button" onClick={() => void copyRuntimeKey(newRuntimeKey.api_key)}>
                    <Copy size={13} aria-hidden="true" />
                    {runtimeKeyCopied ? "Copied" : "Copy key"}
                  </button>
                </div>
                <CopyableCode label=".env" value={keyEnvSnippet} />
                <p className="agent-setup-muted">Copy once. Store it in your agent runtime.</p>
              </div>
            ) : hasRuntimeKey ? (
              <div className="agent-runtime-ready">
                <CheckCircle2 aria-hidden="true" />
                <div>
                  <strong>Runtime key ready</strong>
                  <span>
                    {activeRuntimeKeys[0]?.key_prefix ? `${activeRuntimeKeys[0].key_prefix}...` : "Active project key found"}
                  </span>
                </div>
              </div>
            ) : (
              <div className="agent-runtime-create">
                <p className="agent-setup-muted">
                  Only talks to Zroky. No access to OpenAI, Stripe, Slack, or your systems.
                </p>
                <DashboardButton
                  icon={<KeyRound />}
                  type="button"
                  variant="primary"
                  loading={createKeyMutation.isPending}
                  disabled={!projectId || createKeyMutation.isPending}
                  onClick={() => createKeyMutation.mutate()}
                >
                  Create project key
                </DashboardButton>
              </div>
            )}
            {runtimeStatus ? <p className="agent-setup-status">{runtimeStatus}</p> : null}
          </div>

          {/* 2 - Connect */}
          <div
            className="agent-quickstart-card"
            data-step="connect"
            data-active={activeStep === "connect" ? "true" : "false"}
            data-done={created ? "true" : "false"}
            aria-disabled={!hasRuntimeKey || undefined}
          >
            <div className="agent-quickstart-card-head">
              <span>{created ? <CheckCircle2 aria-hidden="true" size={16} /> : "02"}</span>
              <div>
                <strong>Connect</strong>
                <small>Name one agent runtime.</small>
              </div>
              <em>{stepStateLabel(activeStep, "connect", created)}</em>
            </div>

            {created ? (
              <div className="agent-quickstart-connected">
                <strong>{connectedAgentName}</strong>
                <div className="agent-profile-summary">
                  <span>{framework}</span>
                  <span>{environment}</span>
                  <span>{packInstalled ? "Actions ready" : "Choose actions next"}</span>
                </div>
              </div>
            ) : (
              <form
                className="agent-setup-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (!agentName.trim()) {
                    setError("Give the agent a name to continue.");
                    return;
                  }
                  if (!hasRuntimeKey) {
                    setError("Create a project key before connecting the agent runtime.");
                    return;
                  }
                  setError(null);
                  createMutation.mutate();
                }}
              >
                <div className="agent-setup-form-grid">
                  <label className="agent-setup-field">
                    <span>Agent name</span>
                    <input
                      value={agentName}
                      onChange={(event) => setAgentName(event.target.value)}
                      disabled={!hasRuntimeKey}
                      placeholder="Operations Agent"
                      aria-label="Agent name"
                    />
                  </label>
                  <label className="agent-setup-field">
                    <span>Framework</span>
                    <select
                      value={framework}
                      onChange={(event) => setFramework(event.target.value)}
                      aria-label="Framework"
                      disabled={!hasRuntimeKey}
                    >
                      {FRAMEWORKS.map((item) => (
                        <option key={item} value={item}>
                          {item}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="agent-setup-field">
                    <span>Environment</span>
                    <select
                      value={environment}
                      onChange={(event) => setEnvironment(event.target.value)}
                      aria-label="Environment"
                      disabled={!hasRuntimeKey}
                    >
                      {ENVIRONMENTS.map((item) => (
                        <option key={item} value={item}>
                          {item}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <p className="agent-setup-muted">Safe default is applied automatically.</p>
                <DashboardButton
                  icon={<ShieldCheck />}
                  type="submit"
                  variant="primary"
                  loading={createMutation.isPending}
                  disabled={!hasRuntimeKey || createMutation.isPending}
                >
                  {hasRuntimeKey ? "Create agent profile" : "Create project key first"}
                </DashboardButton>
              </form>
            )}
          </div>

          {/* 3 - Protected actions */}
          <div
            className="agent-quickstart-card"
            data-step="pack"
            data-active={activeStep === "pack" ? "true" : "false"}
            data-done={packInstalled ? "true" : "false"}
            aria-disabled={!created || undefined}
          >
            <div className="agent-quickstart-card-head">
              <span>{packInstalled ? <CheckCircle2 aria-hidden="true" size={16} /> : "03"}</span>
              <div>
                <strong>Protected actions</strong>
                <small>Choose the actions and connectors Zroky should govern.</small>
              </div>
              <em>{stepStateLabel(activeStep, "pack", packInstalled)}</em>
            </div>
            {!created ? (
              <div className="agent-run-locked">
                <strong>Create the agent first.</strong>
                <span>Protected actions appear after Step 2.</span>
              </div>
            ) : (
              <div className="agent-pack-picker">
                <div className="agent-pack-options" aria-label="Protected action packs">
                  {packs.length > 0 ? packs.map((pack) => (
                    <button
                      key={pack.id}
                      type="button"
                      data-selected={selectedPack?.id === pack.id ? "true" : "false"}
                      onClick={() => setSelectedPackId(pack.id)}
                      disabled={packInstalled}
                    >
                      <strong>{pack.display_name.replace(" operations", "")}</strong>
                      <span>{PACK_SHORT_COPY[pack.id] ?? pack.summary}</span>
                    </button>
                  )) : (
                    <div className="agent-run-locked">
                      <strong>Loading protected actions.</strong>
                      <span>Templates are coming from your Zroky project.</span>
                    </div>
                  )}
                </div>

                {selectedPack ? (
                  <div className="agent-pack-detail">
                    {isSupportPack ? (
                      <div className="support-engine-builder">
                        <div>
                          <span className="dashboard-eyebrow">Support engine</span>
                          <div className="support-engine-options" aria-label="Support engine">
                            {SUPPORT_ENGINES.map((engine) => (
                              <button
                                key={engine.id}
                                type="button"
                                data-selected={supportEngineId === engine.id ? "true" : "false"}
                                onClick={() => setSupportEngineId(engine.id)}
                                disabled={packInstalled}
                              >
                                <strong>{engine.label}</strong>
                                <span>{engine.summary}</span>
                              </button>
                            ))}
                          </div>
                        </div>
                        <div>
                          <span className="dashboard-eyebrow">What can this agent do?</span>
                          <div className="support-capability-grid">
                            {SUPPORT_CAPABILITIES.map((capability) => {
                              const checked = supportCapabilityIds.includes(capability.id);
                              return (
                                <label key={capability.id} data-checked={checked ? "true" : "false"}>
                                  <input
                                    type="checkbox"
                                    checked={checked}
                                    disabled={packInstalled}
                                    onChange={() => {
                                      setSupportCapabilityIds((current) => {
                                        if (current.includes(capability.id)) {
                                          return current.length > 1
                                            ? current.filter((id) => id !== capability.id)
                                            : current;
                                        }
                                        return [...current, capability.id];
                                      });
                                    }}
                                  />
                                  <span>
                                    <strong>{capability.label}</strong>
                                    <small>{capability.summary}</small>
                                  </span>
                                </label>
                              );
                            })}
                          </div>
                        </div>
                        <div className="support-selection-summary">
                          <div>
                            <span className="dashboard-eyebrow">Guardrails Zroky will install</span>
                            <strong>{selectedSupportContracts.length} protected actions</strong>
                            <small>
                              {supportCapabilityIds.map((id) => supportCapabilityById(id).label).join(", ")}
                            </small>
                          </div>
                          <div>
                            <span className="dashboard-eyebrow">Suggested proof sources</span>
                            <div className="agent-pack-chip-row">
                              {selectedSupportConnectors.map((connector) => (
                                <span key={connector}>{connectorLabel(connector)}</span>
                              ))}
                            </div>
                          </div>
                        </div>
                      </div>
                    ) : isFinancePack ? (
                      <div className="support-engine-builder">
                        <div>
                          <span className="dashboard-eyebrow">Finance system</span>
                          <div className="support-engine-options" aria-label="Finance system">
                            {FINANCE_SYSTEMS.map((system) => (
                              <button
                                key={system.id}
                                type="button"
                                data-selected={financeSystemId === system.id ? "true" : "false"}
                                onClick={() => setFinanceSystemId(system.id)}
                                disabled={packInstalled}
                              >
                                <strong>{system.label}</strong>
                                <span>{system.summary}</span>
                              </button>
                            ))}
                          </div>
                        </div>
                        <div>
                          <span className="dashboard-eyebrow">What money risk can this agent touch?</span>
                          <div className="support-capability-grid finance-capability-grid">
                            {FINANCE_CAPABILITIES.map((capability) => {
                              const checked = financeCapabilityIds.includes(capability.id);
                              return (
                                <label key={capability.id} data-checked={checked ? "true" : "false"}>
                                  <input
                                    type="checkbox"
                                    checked={checked}
                                    disabled={packInstalled}
                                    onChange={() => {
                                      setFinanceCapabilityIds((current) => {
                                        if (current.includes(capability.id)) {
                                          return current.length > 1
                                            ? current.filter((id) => id !== capability.id)
                                            : current;
                                        }
                                        return [...current, capability.id];
                                      });
                                    }}
                                  />
                                  <span>
                                    <strong>{capability.label}</strong>
                                    <small>{capability.summary}</small>
                                  </span>
                                </label>
                              );
                            })}
                          </div>
                        </div>
                        <div className="support-selection-summary">
                          <div>
                            <span className="dashboard-eyebrow">Guardrails Zroky will install</span>
                            <strong>{selectedFinanceContracts.length} protected actions</strong>
                            <small>
                              {financeCapabilityIds.map((id) => financeCapabilityById(id).label).join(", ")}
                            </small>
                          </div>
                          <div>
                            <span className="dashboard-eyebrow">Suggested proof sources</span>
                            <div className="agent-pack-chip-row">
                              {selectedFinanceConnectors.map((connector) => (
                                <span key={connector}>{connectorLabel(connector)}</span>
                              ))}
                            </div>
                          </div>
                        </div>
                      </div>
                    ) : isDevopsPack ? (
                      <div className="support-engine-builder">
                        <div>
                          <span className="dashboard-eyebrow">Release system</span>
                          <div className="support-engine-options" aria-label="Release system">
                            {DEVOPS_SYSTEMS.map((system) => (
                              <button
                                key={system.id}
                                type="button"
                                data-selected={devopsSystemId === system.id ? "true" : "false"}
                                onClick={() => setDevopsSystemId(system.id)}
                                disabled={packInstalled}
                              >
                                <strong>{system.label}</strong>
                                <span>{system.summary}</span>
                              </button>
                            ))}
                          </div>
                        </div>
                        <div>
                          <span className="dashboard-eyebrow">What release risk should Zroky govern?</span>
                          <div className="support-capability-grid finance-capability-grid">
                            {DEVOPS_CAPABILITIES.map((capability) => {
                              const checked = devopsCapabilityIds.includes(capability.id);
                              return (
                                <label key={capability.id} data-checked={checked ? "true" : "false"}>
                                  <input
                                    type="checkbox"
                                    checked={checked}
                                    disabled={packInstalled}
                                    onChange={() => {
                                      setDevopsCapabilityIds((current) => {
                                        if (current.includes(capability.id)) {
                                          return current.length > 1
                                            ? current.filter((id) => id !== capability.id)
                                            : current;
                                        }
                                        return [...current, capability.id];
                                      });
                                    }}
                                  />
                                  <span>
                                    <strong>{capability.label}</strong>
                                    <small>{capability.summary}</small>
                                  </span>
                                </label>
                              );
                            })}
                          </div>
                        </div>
                        <div className="support-selection-summary">
                          <div>
                            <span className="dashboard-eyebrow">Guardrails Zroky will install</span>
                            <strong>{selectedDevopsContracts.length} protected action</strong>
                            <small>
                              {devopsCapabilityIds.map((id) => devopsCapabilityById(id).label).join(", ")}
                            </small>
                          </div>
                          <div>
                            <span className="dashboard-eyebrow">Suggested proof sources</span>
                            <div className="agent-pack-chip-row">
                              {selectedDevopsConnectors.map((connector) => (
                                <span key={connector}>{connectorLabel(connector)}</span>
                              ))}
                            </div>
                          </div>
                        </div>
                      </div>
                    ) : isEcommercePack ? (
                      <div className="support-engine-builder">
                        <div>
                          <span className="dashboard-eyebrow">Commerce system</span>
                          <div className="support-engine-options" aria-label="Commerce system">
                            {ECOMMERCE_SYSTEMS.map((system) => (
                              <button
                                key={system.id}
                                type="button"
                                data-selected={ecommerceSystemId === system.id ? "true" : "false"}
                                onClick={() => setEcommerceSystemId(system.id)}
                                disabled={packInstalled}
                              >
                                <strong>{system.label}</strong>
                                <span>{system.summary}</span>
                              </button>
                            ))}
                          </div>
                        </div>
                        <div>
                          <span className="dashboard-eyebrow">What commerce risk should Zroky govern?</span>
                          <div className="support-capability-grid finance-capability-grid">
                            {ECOMMERCE_CAPABILITIES.map((capability) => {
                              const checked = ecommerceCapabilityIds.includes(capability.id);
                              return (
                                <label key={capability.id} data-checked={checked ? "true" : "false"}>
                                  <input
                                    type="checkbox"
                                    checked={checked}
                                    disabled={packInstalled}
                                    onChange={() => {
                                      setEcommerceCapabilityIds((current) => {
                                        if (current.includes(capability.id)) {
                                          return current.length > 1
                                            ? current.filter((id) => id !== capability.id)
                                            : current;
                                        }
                                        return [...current, capability.id];
                                      });
                                    }}
                                  />
                                  <span>
                                    <strong>{capability.label}</strong>
                                    <small>{capability.summary}</small>
                                  </span>
                                </label>
                              );
                            })}
                          </div>
                        </div>
                        <div className="support-selection-summary">
                          <div>
                            <span className="dashboard-eyebrow">Guardrails Zroky will install</span>
                            <strong>{selectedEcommerceContracts.length} protected actions</strong>
                            <small>
                              {ecommerceCapabilityIds.map((id) => ecommerceCapabilityById(id).label).join(", ")}
                            </small>
                          </div>
                          <div>
                            <span className="dashboard-eyebrow">Suggested proof sources</span>
                            <div className="agent-pack-chip-row">
                              {selectedEcommerceConnectors.map((connector) => (
                                <span key={connector}>{connectorLabel(connector)}</span>
                              ))}
                            </div>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <>
                        <div>
                          <span className="dashboard-eyebrow">Includes</span>
                          <div className="agent-pack-chip-row">
                            {selectedPack.contract_templates.map((contract) => (
                              <span key={contract.contract_version}>{actionLabel(contract.action_type)}</span>
                            ))}
                          </div>
                        </div>
                        <div>
                          <span className="dashboard-eyebrow">Suggested connectors</span>
                          <div className="agent-pack-chip-row">
                            {selectedPack.recommended_connectors.map((connector) => (
                              <span key={connector}>{connectorLabel(connector)}</span>
                            ))}
                          </div>
                        </div>
                      </>
                    )}
                    {packInstalled ? (
                      <div className="agent-runtime-ready">
                        <CheckCircle2 aria-hidden="true" />
                        <div>
                          <strong>{installedPack?.display_name ?? selectedPack.display_name} installed</strong>
                          <span>{selectedPack.contract_templates.length} protected actions ready. Run a test action next.</span>
                        </div>
                      </div>
                    ) : (
                      <div className="agent-pack-actions">
                        <DashboardButton
                          icon={<ShieldCheck />}
                          type="button"
                          variant="primary"
                          loading={installPackMutation.isPending}
                          disabled={installPackMutation.isPending || !selectedPack}
                          onClick={() => installPackMutation.mutate()}
                        >
                          Install protected actions
                        </DashboardButton>
                      </div>
                    )}
                  </div>
                ) : null}
              </div>
            )}
          </div>

          {/* 4 - Run */}
          <div
            className="agent-quickstart-card"
            data-step="run"
            data-active={activeStep === "run" ? "true" : "false"}
            data-done={live ? "true" : "false"}
            aria-disabled={!packInstalled || undefined}
          >
            <div className="agent-quickstart-card-head">
              <span>{live ? <CheckCircle2 aria-hidden="true" size={16} /> : "04"}</span>
              <div>
                <strong>Run</strong>
                <small>Send one protected action.</small>
              </div>
              <em>{stepStateLabel(activeStep, "run", live)}</em>
            </div>
            {packInstalled ? (
              <div className="agent-run-snippets">
                <CopyableCommand label="Install" value="pip install zroky" />
                <CopyableCommand label="Check" value="zroky doctor" />
                <CopyableCommand label="Send test action" value="zroky ingest --test" />
                <CopyableCommand label="Run scenario" value="python agent.py access-grant" />
                <details className="agent-python-example">
                  <summary>Python example</summary>
                  <CopyableCode label="Protected action" value={firstProtectedActionSnippet} />
                </details>
              </div>
            ) : (
              <div className="agent-run-locked">
                <strong>Install protected actions first.</strong>
                <span>Commands appear after Step 3.</span>
              </div>
            )}
            <div className="agent-setup-readiness-grid" aria-label="Live capture status">
              <div data-done={created ? "true" : "false"}>
                {created ? <CheckCircle2 aria-hidden="true" /> : <PlayCircle aria-hidden="true" />}
                <strong>SDK ready</strong>
                <span>{created ? "install the snippet" : "create agent first"}</span>
              </div>
              <div data-done={packInstalled ? "true" : "false"}>
                {packInstalled ? <CheckCircle2 aria-hidden="true" /> : <PlayCircle aria-hidden="true" />}
                <strong>Actions installed</strong>
                <span>{packInstalled ? "contracts ready" : "choose a pack"}</span>
              </div>
              <div data-done={firstAction ? "true" : "false"}>
                {firstAction ? <CheckCircle2 aria-hidden="true" /> : <PlayCircle aria-hidden="true" />}
                <strong>Action received</strong>
                <span>{created ? actionStatus : "waiting for SDK run"}</span>
              </div>
              <div data-done={policyChecked ? "true" : "false"}>
                {policyChecked ? <CheckCircle2 aria-hidden="true" /> : <PlayCircle aria-hidden="true" />}
                <strong>Policy checked</strong>
                <span>{policyChecked ? "evaluated" : "waiting for action"}</span>
              </div>
              <div data-done={live ? "true" : "false"}>
                {live ? <CheckCircle2 aria-hidden="true" /> : <PlayCircle aria-hidden="true" />}
                <strong>Signed receipt</strong>
                <span>{live ? "generated" : firstAction?.receipt_status?.replace(/_/g, " ") ?? "waiting for proof"}</span>
              </div>
            </div>
            {firstAction ? (
              <div className="agent-setup-inline-actions">
                <DashboardButtonLink href="/actions" variant="primary">
                  View first action
                </DashboardButtonLink>
              </div>
            ) : null}
          </div>

          {/* 5 - Live / what's next */}
          <div
            className="agent-quickstart-card"
            data-step="live"
            data-active={activeStep === "next" ? "true" : "false"}
            data-done={live ? "true" : "false"}
            aria-disabled={!live || undefined}
          >
            <div className="agent-quickstart-card-head">
              <span>{live ? <CheckCircle2 aria-hidden="true" size={16} /> : "05"}</span>
              <div>
                <strong>{live ? "You're live" : "What's next"}</strong>
                <small>
                  {live
                    ? "Tune from real captured actions."
                    : "Review the first receipt."}
                </small>
              </div>
              <em>{stepStateLabel(activeStep, "next", live)}</em>
            </div>
            {!live ? (
              <div className="agent-next-hint">
                <strong>Unlocks after your first receipt.</strong>
              </div>
            ) : (
              <>
                <p className="agent-setup-muted">Tune policy and evidence from real actions.</p>
                <div className="agent-setup-inline-actions agent-next-actions">
                  <DashboardButtonLink href="/policies" variant="primary">
                    Tune policy
                  </DashboardButtonLink>
                  <DashboardButtonLink href="/integrations" variant="soft">
                    Connect verifier
                  </DashboardButtonLink>
                  <DashboardButtonLink href="/actions" variant="soft">
                    Review action
                  </DashboardButtonLink>
                  <DashboardButtonLink href="/evidence" variant="soft">
                    Open receipt
                  </DashboardButtonLink>
                </div>
              </>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
