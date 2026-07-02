"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { type FormEvent, type ReactNode, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  Bot,
  Check,
  CheckCircle2,
  ClipboardCheck,
  Database,
  FileJson,
  KeyRound,
  LockKeyhole,
  PlayCircle,
  Plug,
  RefreshCw,
  Save,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
  Workflow,
} from "lucide-react";

import { DashboardButton, DashboardButtonLink } from "@/components/dashboard-button";
import {
  DashboardMetricStrip,
  DashboardVerdictHero,
} from "@/components/dashboard-scaffold";
import {
  createAgentProfile,
  dryRunRuntimePolicy,
  enforceAgentProfile,
  getCustomerRecordConnectorStatus,
  getGenericRestConnectorStatus,
  getAgentProfile,
  getHubSpotCrmConnectorStatus,
  getJiraIssueConnectorStatus,
  getLedgerRefundConnectorStatus,
  getNetSuiteFinanceConnectorStatus,
  getPostgresReadConnectorStatus,
  getRazorpayRefundConnectorStatus,
  getSalesforceCrmConnectorStatus,
  getStripeRefundConnectorStatus,
  getToolRegistry,
  getZendeskTicketConnectorStatus,
  getZohoCrmConnectorStatus,
  listActionIntents,
  listActionRunners,
  updateAgentProfile,
  type ActionIntentResponse,
  type ActionRunnerResponse,
  type AgentProfileResponse,
  type AgentProfileCreatePayload,
  type AgentRiskActionType,
  type AgentRuntimePath,
  type AgentVerificationConnectorType,
  type CustomerRecordConnectorStatusResponse,
  type GenericRestConnectorStatusResponse,
  type HubSpotCrmConnectorStatusResponse,
  type JiraIssueConnectorStatusResponse,
  type LedgerRefundConnectorStatusResponse,
  type NetSuiteFinanceConnectorStatusResponse,
  type PostgresReadConnectorStatusResponse,
  type RazorpayRefundConnectorStatusResponse,
  type RuntimePolicyDryRunPayload,
  type RuntimePolicyDryRunResponse,
  type SalesforceCrmConnectorStatusResponse,
  type StripeRefundConnectorStatusResponse,
  type ToolRegistryResponse,
  type ZendeskTicketConnectorStatusResponse,
  type ZohoCrmConnectorStatusResponse,
} from "@/lib/api";
import {
  buildMandateStarter,
  buildProtectedAgentSnippet,
  protectedAgentTemplates,
} from "@/lib/protected-agent-setup";
import { deriveSetupReadiness, type SetupCheck, type SetupReadiness } from "@/lib/setup-readiness";
import { buildSetupFlowView } from "@/lib/setup-flow-view";

type WizardStepId =
  | "agent"
  | "control"
  | "live"
  | "proof"
  | "risk";

type AgentActionTemplateId =
  | "customer_refund"
  | "customer_record_update"
  | "support_ticket_update"
  | "customer_message"
  | "internal_api_change"
  | "production_deploy"
  | "custom_action";
type ApprovalSurface = "dashboard" | "slack" | "dashboard_slack";
type RunnerMode = "managed" | "customer_hosted";
type RiskClass = "R0" | "R1" | "R2" | "R3" | "R4";
type ProtectionState = "draft" | "plan_saved" | "enforced";
type ConnectorFamily = "ledger" | "stripe" | "razorpay" | "netsuite" | "customer" | "generic" | "hubspot" | "salesforce" | "zoho" | "postgres" | "zendesk" | "jira";
type ConnectorStatus =
  | CustomerRecordConnectorStatusResponse
  | GenericRestConnectorStatusResponse
  | HubSpotCrmConnectorStatusResponse
  | SalesforceCrmConnectorStatusResponse
  | StripeRefundConnectorStatusResponse
  | RazorpayRefundConnectorStatusResponse
  | NetSuiteFinanceConnectorStatusResponse
  | ZohoCrmConnectorStatusResponse
  | LedgerRefundConnectorStatusResponse
  | PostgresReadConnectorStatusResponse
  | ZendeskTicketConnectorStatusResponse
  | JiraIssueConnectorStatusResponse;

type ActionCatalogItem = {
  id: AgentRiskActionType;
  label: string;
  verb: "TRANSFER" | "UPDATE" | "SEND" | "EXECUTE";
  riskClass: RiskClass;
  sourceSystem: string;
  resource: string;
  defaultTool: string;
  verifier: AgentVerificationConnectorType;
  businessWhy: string;
};

type ActionTemplate = {
  id: AgentActionTemplateId;
  label: string;
  helper: string;
  actionType: AgentRiskActionType;
  selectedActionTypes: AgentRiskActionType[];
  toolNames: string;
  sourceOfRecord: string;
  proofAssertion: string;
  verifierConnector: AgentVerificationConnectorType;
};

type SetupDraft = {
  productName: string;
  productCategory: string;
  actionTemplateId: AgentActionTemplateId;
  businessGoal: string;
  criticalObjects: string[];
  sourceSystems: string[];
  agentName: string;
  ownerTeam: string;
  framework: string;
  environment: string;
  modelProvider: string;
  modelName: string;
  workflowId: string;
  workflowGoal: string;
  runtimePath: AgentRuntimePath;
  toolNamesText: string;
  selectedActionTypes: AgentRiskActionType[];
  primaryActionType: AgentRiskActionType;
  approvalSurface: ApprovalSurface;
  autoAllowAmountUsd: string;
  approvalRequiredAboveUsd: string;
  denyAboveUsd: string;
  approvalTtlMinutes: string;
  runnerMode: RunnerMode;
  credentialRef: string;
  verifierConnector: AgentVerificationConnectorType;
  sourceOfRecord: string;
  proofAssertion: string;
  idempotencyScope: string;
};

const STORAGE_KEY = "zroky.agentControlSetupWizard.v1";

const STEPS: {
  id: WizardStepId;
  label: string;
  kicker: string;
  icon: typeof ClipboardCheck;
}[] = [
  { id: "agent", label: "Agent Identity", kicker: "Who we protect", icon: Bot },
  { id: "risk", label: "Protected Action", kicker: "First risky path", icon: Plug },
  { id: "control", label: "Control Path", kicker: "Policy and runner", icon: SlidersHorizontal },
  { id: "proof", label: "Proof & Readiness", kicker: "Dry-run and handoff", icon: ShieldCheck },
  { id: "live", label: "Go Live", kicker: "First matched receipt", icon: CheckCircle2 },
];

const PRODUCT_CATEGORIES = [
  "B2B SaaS",
  "Fintech",
  "Customer support",
  "Internal operations",
  "Developer platform",
  "Commerce",
  "Healthcare operations",
  "Custom enterprise workflow",
];

const FRAMEWORK_OPTIONS = [
  "OpenAI Agents SDK",
  "LangGraph",
  "CrewAI",
  "AutoGen",
  "MCP client",
  "Custom agent runtime",
];

const RUNTIME_PATHS: { value: AgentRuntimePath; label: string; helper: string }[] = [
  {
    value: "sdk",
    label: "SDK guard plus capture",
    helper: "Fastest path for JS/Python agents. Captures proposed tool calls and policy context.",
  },
  {
    value: "webhook",
    label: "Webhook bridge",
    helper: "Works when the agent platform can POST action events after a tool call.",
  },
  {
    value: "http_gateway",
    label: "HTTP action gateway",
    helper: "For teams routing protected internal APIs through a Zroky-controlled endpoint.",
  },
  {
    value: "mcp_gateway",
    label: "MCP tool gateway",
    helper: "For MCP-native tool calls. Keep as planned unless customer already needs it.",
  },
];

const CRITICAL_OBJECTS = [
  "customer",
  "refund",
  "invoice",
  "subscription",
  "support ticket",
  "customer message",
  "internal record",
  "production service",
  "database row",
  "deployment",
  "purchase order",
  "user account",
];

const SOURCE_SYSTEMS = [
  "Stripe",
  "Razorpay",
  "Zendesk",
  "Salesforce",
  "HubSpot",
  "Zoho CRM",
  "PostgreSQL",
  "Generic REST",
  "Slack",
  "GitHub",
  "Vercel",
  "Internal admin API",
];

const ACTION_CATALOG: ActionCatalogItem[] = [
  {
    id: "refund",
    label: "Refund customer payment",
    verb: "TRANSFER",
    riskClass: "R4",
    sourceSystem: "Stripe, Razorpay, or payment ledger",
    resource: "refund",
    defaultTool: "stripe.refunds.create",
    verifier: "ledger_refund",
    businessWhy: "Moves money and must match the payment ledger after execution.",
  },
  {
    id: "payment_adjustment",
    label: "Adjust payment or credit",
    verb: "TRANSFER",
    riskClass: "R4",
    sourceSystem: "Payment or billing system",
    resource: "payment_adjustment",
    defaultTool: "billing.credits.apply",
    verifier: "ledger_refund",
    businessWhy: "Changes financial balance and must match billing or payment records.",
  },
  {
    id: "invoice_spend_approval",
    label: "Approve spend or invoice",
    verb: "TRANSFER",
    riskClass: "R4",
    sourceSystem: "ERP, procurement, or billing API",
    resource: "spend_commitment",
    defaultTool: "procurement.purchase_orders.create",
    verifier: "netsuite_finance",
    businessWhy: "Creates financial commitment and needs approval plus ledger proof.",
  },
  {
    id: "customer_record_update",
    label: "Update customer record",
    verb: "UPDATE",
    riskClass: "R3",
    sourceSystem: "CRM or internal customer API",
    resource: "customer_record",
    defaultTool: "crm.customers.update",
    verifier: "crm_record",
    businessWhy: "Mutates customer state and needs field-level proof from the source of record.",
  },
  {
    id: "ticket_close",
    label: "Update or close support ticket",
    verb: "UPDATE",
    riskClass: "R2",
    sourceSystem: "Zendesk or support API",
    resource: "support_ticket",
    defaultTool: "zendesk.tickets.update",
    verifier: "ticket_status",
    businessWhy: "Changes customer operations state and should be checked after the tool call.",
  },
  {
    id: "email_send",
    label: "Send customer-visible message",
    verb: "SEND",
    riskClass: "R2",
    sourceSystem: "Email or messaging provider",
    resource: "customer_message",
    defaultTool: "sendgrid.messages.send",
    verifier: "generic_rest",
    businessWhy: "A wrong recipient or unapproved message can create customer-facing damage.",
  },
  {
    id: "database_record_update",
    label: "Update database record",
    verb: "UPDATE",
    riskClass: "R3",
    sourceSystem: "Database or internal data service",
    resource: "database_record",
    defaultTool: "postgres.records.update",
    verifier: "database_read",
    businessWhy: "Mutates durable state and should be verified with read-only source-of-record access.",
  },
  {
    id: "internal_api_mutation",
    label: "Internal API change",
    verb: "UPDATE",
    riskClass: "R3",
    sourceSystem: "Generic REST",
    resource: "internal_api_action",
    defaultTool: "internal.ops.execute",
    verifier: "generic_rest",
    businessWhy: "Generic business mutation. Start with Generic REST until a native connector exists.",
  },
  {
    id: "deploy_change",
    label: "Deploy or change production service",
    verb: "EXECUTE",
    riskClass: "R4",
    sourceSystem: "GitHub, CI, or deploy platform",
    resource: "deployment",
    defaultTool: "github.deployments.create",
    verifier: "generic_rest",
    businessWhy: "Production infrastructure action. Requires approval and post-deploy proof.",
  },
  {
    id: "custom",
    label: "Custom protected action",
    verb: "EXECUTE",
    riskClass: "R3",
    sourceSystem: "Customer-defined system",
    resource: "custom_business_action",
    defaultTool: "custom.action.execute",
    verifier: "generic_rest",
    businessWhy: "Use this when the agent modifies a business system that does not fit a native template yet.",
  },
];

const ACTION_VERBS: ActionCatalogItem["verb"][] = ["TRANSFER", "UPDATE", "SEND", "EXECUTE"];

const CONNECTOR_FAMILY_BY_VERIFIER: Partial<Record<AgentVerificationConnectorType, ConnectorFamily>> = {
  ledger_refund: "ledger",
  stripe_refund: "stripe",
  razorpay_refund: "razorpay",
  netsuite_finance: "netsuite",
  crm_record: "customer",
  hubspot_crm: "hubspot",
  salesforce_crm: "salesforce",
  zoho_crm: "zoho",
  zendesk_ticket: "zendesk",
  jira_issue: "jira",
  generic_rest: "generic",
  database_read: "postgres",
  ticket_status: "generic",
  email_delivery: "generic",
  github_ci: "generic",
  webhook_callback: "generic",
};

const ACTION_TEMPLATES: ActionTemplate[] = [
  {
    id: "customer_refund",
    label: "Customer refund",
    helper: "Protect refunds and payment adjustments before money moves.",
    actionType: "refund",
    selectedActionTypes: ["refund", "payment_adjustment"],
    toolNames: "stripe.refunds.create, billing.credits.apply",
    sourceOfRecord: "Payment processor API",
    proofAssertion: "Refund exists in the payment system with expected amount and final status.",
    verifierConnector: "stripe_refund",
  },
  {
    id: "customer_record_update",
    label: "Customer record update",
    helper: "Control CRM or internal customer profile changes.",
    actionType: "customer_record_update",
    selectedActionTypes: ["customer_record_update"],
    toolNames: "crm.customers.update",
    sourceOfRecord: "CRM or internal customer API",
    proofAssertion: "Customer record was updated with the requested field value in the source of record.",
    verifierConnector: "crm_record",
  },
  {
    id: "support_ticket_update",
    label: "Support ticket update",
    helper: "Verify ticket status or assignment changes after the agent acts.",
    actionType: "ticket_close",
    selectedActionTypes: ["ticket_close"],
    toolNames: "zendesk.tickets.update",
    sourceOfRecord: "Zendesk or support API",
    proofAssertion: "Support ticket status changed to the expected state.",
    verifierConnector: "zendesk_ticket",
  },
  {
    id: "customer_message",
    label: "Customer-visible message",
    helper: "Protect messages before they reach customers.",
    actionType: "email_send",
    selectedActionTypes: ["email_send"],
    toolNames: "sendgrid.messages.send",
    sourceOfRecord: "Email or messaging provider",
    proofAssertion: "Message was sent to the approved recipient with the approved content reference.",
    verifierConnector: "email_delivery",
  },
  {
    id: "internal_api_change",
    label: "Internal API change",
    helper: "Control production business mutations behind internal APIs.",
    actionType: "internal_api_mutation",
    selectedActionTypes: ["internal_api_mutation", "customer_record_update"],
    toolNames: "internal.ops.execute, crm.customers.update",
    sourceOfRecord: "Primary business system API",
    proofAssertion: "Action result exists in the source of record and matches the requested intent.",
    verifierConnector: "generic_rest",
  },
  {
    id: "production_deploy",
    label: "Production deploy",
    helper: "Require approval and post-deploy proof for production changes.",
    actionType: "deploy_change",
    selectedActionTypes: ["deploy_change"],
    toolNames: "github.deployments.create, vercel.deployments.promote",
    sourceOfRecord: "GitHub, CI, or deploy platform",
    proofAssertion: "Deployment completed and the latest commit SHA matches the requested change.",
    verifierConnector: "github_ci",
  },
  {
    id: "custom_action",
    label: "Custom action",
    helper: "Start here when the protected action is unique to your system.",
    actionType: "custom",
    selectedActionTypes: ["custom"],
    toolNames: "custom.action.execute",
    sourceOfRecord: "Customer-defined source of truth",
    proofAssertion: "Source-of-record state matches the approved action intent.",
    verifierConnector: "generic_rest",
  },
];

const DEFAULT_DRAFT: SetupDraft = {
  productName: "Production Agent Workflow",
  productCategory: "Custom enterprise workflow",
  actionTemplateId: "internal_api_change",
  businessGoal: "Control one autonomous agent before it changes customer, money, data, or production systems.",
  criticalObjects: ["customer", "internal record", "production service"],
  sourceSystems: ["Generic REST", "PostgreSQL", "Slack"],
  agentName: "Operations Agent",
  ownerTeam: "AI Platform",
  framework: "LangGraph",
  environment: "production",
  modelProvider: "openai",
  modelName: "gpt-4.1",
  workflowId: "protected_action_workflow",
  workflowGoal: "Review context, propose a risky action, wait for Zroky control, then produce evidence after execution.",
  runtimePath: "sdk",
  toolNamesText: "internal.ops.execute, crm.customers.update, slack.approvals.create",
  selectedActionTypes: ["internal_api_mutation", "customer_record_update"],
  primaryActionType: "internal_api_mutation",
  approvalSurface: "dashboard_slack",
  autoAllowAmountUsd: "100",
  approvalRequiredAboveUsd: "500",
  denyAboveUsd: "5000",
  approvalTtlMinutes: "30",
  runnerMode: "customer_hosted",
  credentialRef: "cred_prod_protected_actions",
  verifierConnector: "generic_rest",
  sourceOfRecord: "Primary business system API",
  proofAssertion: "Action result exists in the source of record and matches the requested intent.",
  idempotencyScope: "workflow_id + resource_id + action_type",
};

type SetupStepGuidance = {
  title: string;
  detail: string;
  tone: "green" | "yellow" | "blue";
};

function stepMissingChecks(readinessItems: SetupCheck[], ids: string[]): SetupCheck[] {
  const wanted = new Set(ids);
  return readinessItems.filter((item) => wanted.has(item.id) && !item.done);
}

function missingLabels(items: SetupCheck[]): string {
  return items.map((item) => item.label.toLowerCase()).join(", ");
}

function setupStepGuidance({
  activeStep,
  draft,
  firstActionCount,
  firstActionsLoading,
  firstReceiptMatched,
  policyEnforced,
  readiness,
  readinessItems,
  toolNames,
}: {
  activeStep: WizardStepId;
  draft: SetupDraft;
  firstActionCount: number;
  firstActionsLoading: boolean;
  firstReceiptMatched: boolean;
  policyEnforced: boolean;
  readiness: SetupReadiness;
  readinessItems: SetupCheck[];
  toolNames: string[];
}): SetupStepGuidance {
  if (activeStep === "agent") {
    if (!draft.agentName.trim()) {
      return {
        tone: "yellow",
        title: "Name the agent before saving",
        detail: "Framework and environment already have launch defaults; owner/team context can stay in Advanced.",
      };
    }
    return {
      tone: "green",
      title: "Agent identity is ready",
      detail: "Continue when the runtime path matches where this agent will call protected tools.",
    };
  }

  if (activeStep === "risk") {
    const missing = stepMissingChecks(readinessItems, ["first_action"]);
    if (missing.length > 0) {
      return {
        tone: "yellow",
        title: "Choose the first protected action",
        detail: "Pick a template or detect risky actions from tool names so Zroky knows what to control.",
      };
    }
    return {
      tone: "green",
      title: `${draft.selectedActionTypes.length} protected action path${draft.selectedActionTypes.length === 1 ? "" : "s"} selected`,
      detail: `${toolNames.length} tool key${toolNames.length === 1 ? "" : "s"} will be matched against this control plan.`,
    };
  }

  if (activeStep === "control") {
    const missing = stepMissingChecks(readinessItems, ["policy_thresholds", "credential_alias"]);
    if (missing.length > 0) {
      return {
        tone: "yellow",
        title: "Control path needs one more guardrail",
        detail: `Fix ${missingLabels(missing)} before enabling the project policy.`,
      };
    }
    if (readiness.runnerStatus !== "ready") {
      return {
        tone: "blue",
        title: "Policy shape is ready; runner still needs to come online",
        detail: "You can save the plan now, then start the protected runner before the first live action.",
      };
    }
    return {
      tone: "green",
      title: "Policy and runner path are ready",
      detail: "The action will be gated by policy and executed through the protected runner.",
    };
  }

  if (activeStep === "proof") {
    const missing = readinessItems.filter((item) => !item.done);
    if (missing.length > 0) {
      return {
        tone: "yellow",
        title: "Finish essentials before enforcement",
        detail: `Still missing: ${missingLabels(missing)}.`,
      };
    }
    if (!policyEnforced) {
      return {
        tone: "green",
        title: "Ready to enable the project policy",
        detail: "Enable once, then run the dry-run and route the first real action.",
      };
    }
    if (readiness.verifierStatus !== "ready") {
      return {
        tone: "yellow",
        title: "Policy is enabled; verifier still needs a healthy connector",
        detail: "Connect or retest the source-of-record verifier before trusting live proof.",
      };
    }
    return {
      tone: "green",
      title: "Proof path is ready for a real receipt",
      detail: "Go live and run the first protected action to close the loop.",
    };
  }

  if (firstReceiptMatched) {
    return {
      tone: "green",
      title: "Home can unlock from this first matched receipt",
      detail: "The agent produced matched proof and a signed receipt through the protected path.",
    };
  }
  if (!readiness.canRunFirstAction) {
    return {
      tone: "yellow",
      title: "Live action is not ready yet",
      detail: "Policy, runner, and verifier must all be ready before the first receipt can arrive.",
    };
  }
  if (firstActionCount === 0) {
    return {
      tone: firstActionsLoading ? "blue" : "yellow",
      title: firstActionsLoading ? "Polling for the first protected action" : "No protected action received yet",
      detail: "Run the starter snippet with the project API key and this agent_id; the wizard will update when traffic arrives.",
    };
  }
  return {
    tone: "blue",
    title: "Action received; proof is still resolving",
    detail: "Use Actions or Evidence if the action needs approval, verification, or receipt review.",
  };
}

function slugify(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 80);
}

function agentProfileSlug(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 255) || "unknown-agent";
}

function hashString(value: string): string {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) >>> 0;
  }
  return hash.toString(16).padStart(8, "0");
}

function splitToolNames(value: string): string[] {
  return value
    .split(/[,\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function actionById(id: AgentRiskActionType): ActionCatalogItem {
  return ACTION_CATALOG.find((item) => item.id === id) ?? ACTION_CATALOG[0];
}

function operationKindsForActions(actions: ActionCatalogItem[]): ActionCatalogItem["verb"][] {
  const seen = new Set<ActionCatalogItem["verb"]>();
  const kinds: ActionCatalogItem["verb"][] = [];
  for (const action of actions) {
    if (!seen.has(action.verb)) {
      seen.add(action.verb);
      kinds.push(action.verb);
    }
  }
  return kinds;
}

function metadataRecord(profile: AgentProfileResponse | null | undefined): Record<string, unknown> {
  const metadata = profile?.metadata;
  return metadata && typeof metadata === "object" && !Array.isArray(metadata) ? metadata : {};
}

function runtimeMandate(profile: AgentProfileResponse | null | undefined): Record<string, unknown> {
  const mandate = metadataRecord(profile).runtime_policy_mandate;
  return mandate && typeof mandate === "object" && !Array.isArray(mandate)
    ? mandate as Record<string, unknown>
    : {};
}

function runnerIdForProfile(profile: AgentProfileResponse | null | undefined): string | null {
  const runnerId = runtimeMandate(profile).runner_id;
  return typeof runnerId === "string" && runnerId.trim() ? runnerId.trim() : null;
}

function runnerNameForProfile(profile: AgentProfileResponse | null | undefined, draft: SetupDraft): string {
  const slug = profile?.slug?.trim() || agentProfileSlug(draft.agentName);
  return `${slug}-runner`;
}

function findSetupRunner(
  runners: ActionRunnerResponse[] | undefined,
  profile: AgentProfileResponse | null,
  draft: SetupDraft,
): ActionRunnerResponse | null {
  const items = runners ?? [];
  const runnerId = runnerIdForProfile(profile);
  if (runnerId) {
    const byId = items.find((item) => item.runner_id === runnerId);
    if (byId) return byId;
  }
  const expectedName = runnerNameForProfile(profile, draft);
  const expectedEnvironment = (profile?.environment || draft.environment || "production").trim();
  return items.find((item) => item.name === expectedName && item.environment === expectedEnvironment) ?? null;
}

function connectorFamilyForVerifier(value: AgentVerificationConnectorType): ConnectorFamily {
  return CONNECTOR_FAMILY_BY_VERIFIER[value] ?? "generic";
}

function connectorStatusForFamily(
  family: ConnectorFamily,
  statuses: Partial<Record<ConnectorFamily, ConnectorStatus | null>>,
): ConnectorStatus | null {
  return statuses[family] ?? null;
}

function connectorHrefForFamily(family: ConnectorFamily): string {
  if (family === "ledger") return "/integrations#ledger-refund-connector";
  if (family === "stripe") return "/integrations?connector=stripe_refund";
  if (family === "razorpay") return "/integrations?connector=razorpay_refund";
  if (family === "netsuite") return "/integrations?connector=netsuite_finance";
  if (family === "customer") return "/integrations#customer-record-connector";
  if (family === "hubspot") return "/integrations?connector=hubspot_crm";
  if (family === "salesforce") return "/integrations?connector=salesforce_crm";
  if (family === "zoho") return "/integrations?connector=zoho_crm";
  if (family === "zendesk") return "/integrations?connector=zendesk_ticket";
  if (family === "jira") return "/integrations?connector=jira_issue";
  if (family === "postgres") return "/integrations#postgres-read-connector";
  return "/integrations#generic-rest-connector";
}

function connectorFamilyLabel(family: ConnectorFamily): string {
  if (family === "ledger") return "Ledger refund connector";
  if (family === "stripe") return "Stripe refund verifier";
  if (family === "razorpay") return "Razorpay refund verifier";
  if (family === "netsuite") return "NetSuite finance verifier";
  if (family === "customer") return "Customer record connector";
  if (family === "hubspot") return "HubSpot CRM verifier";
  if (family === "salesforce") return "Salesforce CRM verifier";
  if (family === "zoho") return "Zoho CRM verifier";
  if (family === "zendesk") return "Zendesk ticket verifier";
  if (family === "jira") return "Jira / JSM verifier";
  if (family === "postgres") return "PostgreSQL read connector";
  return "Generic REST connector";
}

function connectorAttempted(connector: ConnectorStatus | null): boolean {
  return Boolean(connector?.last_tested_at || (connector?.last_attempts ?? 0) >= 1);
}

function connectorHealthy(connector: ConnectorStatus | null): boolean {
  return Boolean(
    connector?.connected
      && connector.health_status === "healthy"
      && connector.last_verdict === "matched"
      && connector.readiness?.status === "ready"
      && !connector.last_error_code,
  );
}

function connectorCompatibleForPrimary(draft: SetupDraft): boolean {
  const requiredVerifier = actionById(draft.primaryActionType).verifier;
  return draft.verifierConnector === requiredVerifier
    || (requiredVerifier === "ledger_refund" && draft.verifierConnector === "stripe_refund")
    || (requiredVerifier === "ledger_refund" && draft.verifierConnector === "razorpay_refund")
    || (
      requiredVerifier === "ledger_refund"
      && draft.verifierConnector === "netsuite_finance"
      && draft.primaryActionType === "payment_adjustment"
    )
    || (requiredVerifier === "crm_record" && draft.verifierConnector === "hubspot_crm")
    || (requiredVerifier === "crm_record" && draft.verifierConnector === "salesforce_crm")
    || (requiredVerifier === "crm_record" && draft.verifierConnector === "zoho_crm")
    || (requiredVerifier === "ticket_status" && draft.verifierConnector === "zendesk_ticket")
    || (requiredVerifier === "ticket_status" && draft.verifierConnector === "jira_issue")
    || (
      connectorFamilyForVerifier(requiredVerifier) === "generic"
      && draft.verifierConnector === "generic_rest"
    );
}

function verifierStatusTitle(
  connector: ConnectorStatus | null,
  compatible: boolean,
): string {
  if (!compatible) return "Verifier mismatch";
  if (!connector?.connected) return "Connector missing";
  if (!connectorAttempted(connector)) return "Connector not tested";
  if (connectorHealthy(connector)) return "Verifier ready";
  return "Connector failing";
}

function verifierStatusDetail(
  draft: SetupDraft,
  family: ConnectorFamily,
  connector: ConnectorStatus | null,
  compatible: boolean,
): string {
  const required = connectorLabel(actionById(draft.primaryActionType).verifier);
  const selected = connectorLabel(draft.verifierConnector);
  const familyLabel = connectorFamilyLabel(family);
  if (!compatible) {
    return `${businessActionLabel(actionById(draft.primaryActionType))} expects ${required}; selected ${selected}.`;
  }
  if (!connector?.connected) {
    return `No saved ${familyLabel} config exists yet. Link one in Integrations; secrets stay there.`;
  }
  if (!connectorAttempted(connector)) {
    return `${familyLabel} is saved, but no matched saved test has run yet.`;
  }
  if (connectorHealthy(connector)) {
    return `${familyLabel} is healthy and the latest saved test matched the source of record.`;
  }
  return connector.last_error_code
    ? `${familyLabel} last failed with ${connector.last_error_code}.`
    : `${familyLabel} has not produced a matched saved test yet.`;
}

function templateById(id: AgentActionTemplateId): ActionTemplate {
  return ACTION_TEMPLATES.find((item) => item.id === id) ?? ACTION_TEMPLATES[0];
}

function businessActionLabel(action: ActionCatalogItem): string {
  const labels: Record<AgentRiskActionType, string> = {
    refund: "Customer refund",
    payment_adjustment: "Payment or credit change",
    invoice_spend_approval: "Spend or invoice approval",
    customer_record_update: "Customer record update",
    ticket_close: "Support ticket update",
    email_send: "Customer-visible message",
    database_record_update: "Database record update",
    internal_api_mutation: "Internal API change",
    deploy_change: "Production deployment",
    custom: "Custom business action",
  };
  return labels[action.id] ?? action.label;
}

function connectorLabel(value: AgentVerificationConnectorType): string {
  const labels: Record<AgentVerificationConnectorType, string> = {
    generic_rest: "Generic REST verifier",
    webhook_callback: "Webhook outcome callback",
    database_read: "PostgreSQL read verifier",
    ledger_refund: "Ledger / refund verifier",
    stripe_refund: "Stripe refund verifier",
    razorpay_refund: "Razorpay refund verifier",
    netsuite_finance: "NetSuite finance verifier",
    crm_record: "CRM record verifier",
    hubspot_crm: "HubSpot CRM verifier",
    salesforce_crm: "Salesforce CRM verifier",
    zoho_crm: "Zoho CRM verifier",
    zendesk_ticket: "Zendesk ticket verifier",
    jira_issue: "Jira / JSM verifier",
    ticket_status: "Ticket status verifier",
    email_delivery: "Email delivery verifier",
    github_ci: "GitHub CI verifier",
  };
  return labels[value] ?? value;
}

function runtimeLabel(value: AgentRuntimePath): string {
  return RUNTIME_PATHS.find((item) => item.value === value)?.label ?? value;
}

function runnerModeLabel(value: RunnerMode): string {
  return value === "customer_hosted" ? "Customer-hosted protected runner" : "Managed Zroky runner";
}

function runnerStatusTone(runner: ActionRunnerResponse | null, capabilityMatches: boolean, environmentMatches: boolean): "green" | "yellow" {
  if (runner?.status === "online" && capabilityMatches && environmentMatches) return "green";
  return "yellow";
}

function runnerStatusTitle(
  runner: ActionRunnerResponse | null,
  capabilityMatches: boolean,
  environmentMatches: boolean,
): string {
  if (!runner) return "Runner will register on enable";
  if (!environmentMatches) return "Runner environment mismatch";
  if (!capabilityMatches) return "Runner capability mismatch";
  if (runner.status === "online") return "Runner ready";
  return "Registered, not online";
}

function runnerStatusDetail(
  runner: ActionRunnerResponse | null,
  capabilityMatches: boolean,
  environmentMatches: boolean,
  expectedOperationKinds: string[],
): string {
  const expected = expectedOperationKinds.join(", ") || "selected operation kinds";
  if (!runner) {
    return "Enabling protection creates a real ActionRunner row for the selected action types.";
  }
  if (!environmentMatches) {
    return `Expected environment does not match this runner. Current runner environment: ${runner.environment}.`;
  }
  if (!capabilityMatches) {
    return `Runner must support ${expected}. Current capabilities: ${runner.supported_operation_kinds.join(", ") || "none"}.`;
  }
  if (runner.status === "online") {
    return `${runner.name} is online and supports ${expected}.`;
  }
  return runner.runner_type === "customer_hosted"
    ? `${runner.name} is registered. Start the customer-hosted runner heartbeat to mark it online.`
    : `${runner.name} is registered but not online yet.`;
}

function approvalPlanLabel(value: ApprovalSurface): string {
  if (value === "dashboard_slack") return "Dashboard or Slack approval";
  if (value === "slack") return "Slack approval";
  return "Dashboard approval";
}

function assuranceLevel(draft: SetupDraft): string {
  if (!draft.credentialRef.trim() || !draft.verifierConnector) return "A1";
  if (
    draft.runnerMode === "managed"
    && (
      draft.verifierConnector === "ledger_refund"
      || draft.verifierConnector === "stripe_refund"
      || draft.verifierConnector === "razorpay_refund"
      || draft.verifierConnector === "netsuite_finance"
    )
  ) return "A4";
  return "A3";
}

function verificationLevel(draft: SetupDraft): string {
  if (
    draft.verifierConnector === "ledger_refund"
    || draft.verifierConnector === "stripe_refund"
    || draft.verifierConnector === "razorpay_refund"
    || draft.verifierConnector === "netsuite_finance"
    || draft.verifierConnector === "crm_record"
    || draft.verifierConnector === "hubspot_crm"
    || draft.verifierConnector === "salesforce_crm"
    || draft.verifierConnector === "zoho_crm"
    || draft.verifierConnector === "zendesk_ticket"
    || draft.verifierConnector === "jira_issue"
  ) return "V4";
  if (draft.verifierConnector === "generic_rest") return "V3";
  return "V2";
}

function templateForDraft(draft: SetupDraft) {
  if (draft.primaryActionType === "refund" || draft.primaryActionType === "payment_adjustment") {
    return protectedAgentTemplates.find((item) => item.id === "refund") ?? protectedAgentTemplates[0];
  }
  if (draft.primaryActionType === "customer_record_update" || draft.primaryActionType === "database_record_update") {
    return protectedAgentTemplates.find((item) => item.id === "crm") ?? protectedAgentTemplates[0];
  }
  if (draft.primaryActionType === "deploy_change") {
    return protectedAgentTemplates.find((item) => item.id === "devops") ?? protectedAgentTemplates[0];
  }
  if (draft.primaryActionType === "email_send" || draft.primaryActionType === "ticket_close") {
    return protectedAgentTemplates.find((item) => item.id === "outreach") ?? protectedAgentTemplates[0];
  }
  if (draft.primaryActionType === "invoice_spend_approval") {
    return protectedAgentTemplates.find((item) => item.id === "procurement") ?? protectedAgentTemplates[0];
  }
  return protectedAgentTemplates[0];
}

function actionContractId(draft: SetupDraft): string {
  return `${slugify(draft.workflowId || "workflow")}.${draft.primaryActionType}`;
}

function intentDigest(draft: SetupDraft): string {
  const action = actionById(draft.primaryActionType);
  const payload = {
    agent: draft.agentName,
    workflow: draft.workflowId,
    verb: action.verb,
    system: action.sourceSystem,
    resource: action.resource,
    environment: draft.environment,
  };
  return `zrk_intent_${hashString(JSON.stringify(payload))}`;
}

function parseDryRunAmount(value: string): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function buildPolicyDryRunPayload(
  draft: SetupDraft,
  toolNames: string[],
  amountUsd: number,
): RuntimePolicyDryRunPayload {
  const action = actionById(draft.primaryActionType);
  const toolName = toolNames[0] ?? action.defaultTool;
  return {
    agent_name: draft.agentName.trim() || "agent-setup-dry-run",
    role: draft.ownerTeam.trim() || "agent",
    action_type: draft.primaryActionType,
    operation_kind: action.verb,
    tool_name: toolName,
    tool_args: {
      dry_run: true,
      action_contract_id: actionContractId(draft),
      resource_id: "zroky-setup-dry-run",
      amount_usd: amountUsd,
      currency: "USD",
    },
    external_action: true,
    environment: draft.environment,
    business_impact_summary: "Agent setup policy dry-run · not recorded",
    impact_usd: amountUsd,
    estimated_cost_usd: amountUsd,
    resource_id: "zroky-setup-dry-run",
    metadata: {
      source: "agent_setup_policy_dry_run",
      recorded: false,
    },
  };
}

type LaunchTool = {
  id: string;
  label: string;
  kind: string;
  status: string;
  recommended: boolean;
};

const FALLBACK_LAUNCH_TOOLS: LaunchTool[] = [
  { id: "sdk", label: "SDK guard", kind: "runtime", status: "available", recommended: true },
  { id: "http_gateway", label: "HTTP gateway", kind: "runtime", status: "available", recommended: false },
  { id: "webhook", label: "Webhook bridge", kind: "runtime", status: "available", recommended: false },
  { id: "mcp_gateway", label: "MCP gateway", kind: "runtime", status: "planned", recommended: false },
  { id: "dashboard_approval", label: "Dashboard approvals", kind: "approval", status: "available", recommended: true },
  { id: "slack_approval", label: "Slack approvals", kind: "approval", status: "available", recommended: true },
  { id: "generic_rest", label: "Generic REST verifier", kind: "verifier", status: "available", recommended: true },
  { id: "stripe_refund", label: "Stripe refund verifier", kind: "verifier", status: "available", recommended: false },
  { id: "razorpay_refund", label: "Razorpay refund verifier", kind: "verifier", status: "available", recommended: false },
  { id: "netsuite_finance", label: "NetSuite finance verifier", kind: "verifier", status: "template", recommended: false },
  { id: "hubspot_crm", label: "HubSpot CRM verifier", kind: "verifier", status: "available", recommended: false },
  { id: "salesforce_crm", label: "Salesforce CRM verifier", kind: "verifier", status: "template", recommended: false },
  { id: "zoho_crm", label: "Zoho CRM verifier", kind: "verifier", status: "template", recommended: false },
  { id: "zendesk_ticket", label: "Zendesk ticket verifier", kind: "verifier", status: "available", recommended: false },
  { id: "jira_issue", label: "Jira / JSM verifier", kind: "verifier", status: "available", recommended: false },
  { id: "webhook_callback", label: "Webhook evidence", kind: "verifier", status: "available", recommended: false },
  { id: "database_read", label: "PostgreSQL read", kind: "verifier", status: "available", recommended: false },
  { id: "ledger_refund", label: "Payment ledger", kind: "verifier", status: "available", recommended: false },
  { id: "crm_record", label: "CRM record", kind: "verifier", status: "available", recommended: false },
  { id: "github_ci", label: "CI/deploy proof", kind: "verifier", status: "planned", recommended: false },
];

function launchTools(registry: ToolRegistryResponse | undefined): LaunchTool[] {
  if (!registry) return FALLBACK_LAUNCH_TOOLS;
  const recommended = new Set([
    ...registry.recommended.runtime_path_ids,
    ...registry.recommended.verification_connector_ids,
    ...registry.recommended.native_tool_family_ids,
  ]);
  const runtimeTools = registry.runtime_paths.map((item) => ({
    id: item.id,
    label: item.label,
    kind: "runtime",
    status: item.implementation_status,
    recommended: recommended.has(item.id),
  }));
  const nativeTools = registry.native_tool_families.map((item) => ({
    id: item.id,
    label: approvalToolLabel(item.id, item.label),
    kind: item.category || "connector",
    status: item.implementation_status,
    recommended: recommended.has(item.id),
  }));
  const verifierTools = registry.verification_connectors.map((item) => ({
    id: item.id,
    label: item.label,
    kind: "verifier",
    status: item.implementation_status,
    recommended: recommended.has(item.id),
  }));
  const approvalTools = nativeTools.filter(isApprovalLaunchTool);
  const recommendedNativeTools = nativeTools
    .filter((item) => !isApprovalLaunchTool(item) && item.recommended)
    .sort(compareLaunchTools);
  const remainingNativeTools = nativeTools
    .filter((item) => !isApprovalLaunchTool(item) && !item.recommended)
    .sort(compareLaunchTools);
  return [
    ...runtimeTools.sort(compareLaunchTools),
    ...approvalTools.sort(compareLaunchTools),
    ...recommendedNativeTools,
    ...verifierTools.sort(compareLaunchTools),
    ...remainingNativeTools,
  ].slice(0, 12);
}

function approvalToolLabel(id: string, label: string): string {
  const normalized = `${id} ${label}`.toLowerCase();
  if (normalized.includes("dashboard")) return "Dashboard approvals";
  if (normalized.includes("slack")) return "Slack approvals";
  return label;
}

function isApprovalLaunchTool(item: LaunchTool): boolean {
  return `${item.id} ${item.label} ${item.kind}`.toLowerCase().includes("approval");
}

function compareLaunchTools(a: LaunchTool, b: LaunchTool): number {
  if (a.recommended !== b.recommended) return a.recommended ? -1 : 1;
  return launchToolStatusRank(a.status) - launchToolStatusRank(b.status);
}

function launchToolStatusRank(status: string): number {
  if (status === "available") return 0;
  if (status === "template") return 1;
  if (status === "planned") return 2;
  return 3;
}

function toggleListValue(values: string[], value: string): string[] {
  return values.includes(value)
    ? values.filter((item) => item !== value)
    : [...values, value];
}

function toggleActionValue(
  values: AgentRiskActionType[],
  value: AgentRiskActionType,
): AgentRiskActionType[] {
  if (values.includes(value)) {
    const next = values.filter((item) => item !== value);
    return next.length > 0 ? next : values;
  }
  return [...values, value];
}

function mergeDraft(value: Partial<SetupDraft>): SetupDraft {
  return {
    ...DEFAULT_DRAFT,
    ...value,
    criticalObjects: Array.isArray(value.criticalObjects) ? value.criticalObjects : DEFAULT_DRAFT.criticalObjects,
    sourceSystems: Array.isArray(value.sourceSystems) ? value.sourceSystems : DEFAULT_DRAFT.sourceSystems,
    selectedActionTypes: Array.isArray(value.selectedActionTypes)
      ? value.selectedActionTypes
      : DEFAULT_DRAFT.selectedActionTypes,
  };
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function textValue(value: unknown, fallback = ""): string {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function numberString(value: unknown, fallback: string): string {
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "string" && value.trim()) return value.trim();
  return fallback;
}

function stringArray(value: unknown, fallback: string[]): string[] {
  if (!Array.isArray(value)) return fallback;
  const cleaned = value.map((item) => String(item).trim()).filter(Boolean);
  return cleaned.length > 0 ? cleaned : fallback;
}

function safeActionTypes(value: AgentRiskActionType[]): AgentRiskActionType[] {
  const catalogIds = new Set(ACTION_CATALOG.map((item) => item.id));
  const cleaned = value.filter((item) => catalogIds.has(item));
  return cleaned.length > 0 ? cleaned : DEFAULT_DRAFT.selectedActionTypes;
}

function draftFromProfile(profile: AgentProfileResponse): SetupDraft {
  const metadata = asRecord(profile.metadata);
  const product = asRecord(metadata.product_context);
  const workflow = asRecord(metadata.workflow_manifest);
  const policy = asRecord(metadata.policy_preview);
  const runner = asRecord(metadata.runner_verification);
  const proof = asRecord(metadata.proof);
  const riskLimits = asRecord(profile.risk_limits);
  const selectedActionTypes = safeActionTypes(profile.allowed_action_types);
  const primaryActionType = selectedActionTypes[0] ?? DEFAULT_DRAFT.primaryActionType;

  return mergeDraft({
    productName: textValue(product.product_name, DEFAULT_DRAFT.productName),
    productCategory: textValue(product.product_category, DEFAULT_DRAFT.productCategory),
    businessGoal: textValue(product.business_goal, DEFAULT_DRAFT.businessGoal),
    criticalObjects: stringArray(product.critical_objects, DEFAULT_DRAFT.criticalObjects),
    sourceSystems: stringArray(product.source_systems, DEFAULT_DRAFT.sourceSystems),
    agentName: profile.display_name,
    ownerTeam: textValue(workflow.owner_team, DEFAULT_DRAFT.ownerTeam),
    framework: profile.framework ?? DEFAULT_DRAFT.framework,
    environment: profile.environment ?? DEFAULT_DRAFT.environment,
    modelProvider: profile.model_provider ?? DEFAULT_DRAFT.modelProvider,
    modelName: profile.model_name ?? DEFAULT_DRAFT.modelName,
    workflowId: textValue(workflow.workflow_id, DEFAULT_DRAFT.workflowId),
    workflowGoal: textValue(workflow.goal, DEFAULT_DRAFT.workflowGoal),
    runtimePath: profile.runtime_path,
    toolNamesText: profile.tool_names.length > 0 ? profile.tool_names.join(", ") : DEFAULT_DRAFT.toolNamesText,
    selectedActionTypes,
    primaryActionType,
    approvalSurface: textValue(policy.approval_surface, DEFAULT_DRAFT.approvalSurface) as ApprovalSurface,
    autoAllowAmountUsd: numberString(riskLimits.auto_allow_amount_usd, DEFAULT_DRAFT.autoAllowAmountUsd),
    approvalRequiredAboveUsd: numberString(
      riskLimits.approval_required_above_usd ?? policy.approval_required_above_usd,
      DEFAULT_DRAFT.approvalRequiredAboveUsd,
    ),
    denyAboveUsd: numberString(riskLimits.deny_above_usd ?? policy.deny_above_usd, DEFAULT_DRAFT.denyAboveUsd),
    approvalTtlMinutes: numberString(
      riskLimits.approval_ttl_minutes ?? policy.approval_ttl_minutes,
      DEFAULT_DRAFT.approvalTtlMinutes,
    ),
    runnerMode: textValue(runner.runner_mode, DEFAULT_DRAFT.runnerMode) as RunnerMode,
    credentialRef: textValue(runner.credential_ref, DEFAULT_DRAFT.credentialRef),
    verifierConnector: (
      profile.verification_connectors[0] ??
      textValue(runner.verifier_connector, actionById(primaryActionType).verifier)
    ) as AgentVerificationConnectorType,
    sourceOfRecord: textValue(runner.source_of_record, DEFAULT_DRAFT.sourceOfRecord),
    proofAssertion: textValue(proof.proof_assertion, DEFAULT_DRAFT.proofAssertion),
    idempotencyScope: textValue(runner.idempotency_scope, DEFAULT_DRAFT.idempotencyScope),
  });
}

function setupMetadata(draft: SetupDraft, options: { protectionState: ProtectionState }) {
  const selectedActions = draft.selectedActionTypes.map(actionById);
  const primaryAction = actionById(draft.primaryActionType);
  return {
    setup_source: "agent_control_setup_wizard",
    protection_state: options.protectionState,
    product_context: {
      product_name: draft.productName,
      product_category: draft.productCategory,
      business_goal: draft.businessGoal,
      critical_objects: draft.criticalObjects,
      source_systems: draft.sourceSystems,
    },
    workflow_manifest: {
      workflow_id: draft.workflowId,
      owner_team: draft.ownerTeam,
      goal: draft.workflowGoal,
      protected_actions: selectedActions.map((action) => action.id),
      environment: draft.environment,
    },
    action_contracts: selectedActions.map((action) => ({
      id: `${slugify(draft.workflowId)}.${action.id}`,
      verb: action.verb,
      system: action.sourceSystem,
      resource: action.resource,
      risk_class: action.riskClass,
      verifier: action.verifier,
      runner_required: true,
      receipt_required: true,
      proof_assertion: draft.proofAssertion,
    })),
    policy_preview: {
      auto_allow_amount_usd: Number(draft.autoAllowAmountUsd),
      approval_required_above_usd: Number(draft.approvalRequiredAboveUsd),
      deny_above_usd: Number(draft.denyAboveUsd),
      approval_surface: draft.approvalSurface,
      approval_ttl_minutes: Number(draft.approvalTtlMinutes),
      unknown_contract_decision: "deny",
      changed_recipient_decision: "deny",
    },
    runner_verification: {
      runner_mode: draft.runnerMode,
      credential_ref: draft.credentialRef,
      verifier_connector: draft.verifierConnector,
      source_of_record: draft.sourceOfRecord,
      proof_assertion: draft.proofAssertion,
      idempotency_scope: draft.idempotencyScope,
      assurance_level: assuranceLevel(draft),
      verification_level: verificationLevel(draft),
    },
    proof: {
      verifier: draft.verifierConnector,
      source_of_truth: draft.sourceOfRecord,
      proof_assertion: draft.proofAssertion,
      receipt_required: true,
      evidence_pack_required: true,
    },
    control_binding: {
      agent_profile: {
        name: draft.agentName,
        owner_team: draft.ownerTeam,
        framework: draft.framework,
        environment: draft.environment,
        goal: draft.businessGoal,
      },
      protected_action: {
        primary_action: businessActionLabel(primaryAction),
        action_type: draft.primaryActionType,
        verb: primaryAction.verb,
        resource: primaryAction.resource,
        risk_class: primaryAction.riskClass,
        tool_names: splitToolNames(draft.toolNamesText),
      },
      control_path: {
        runtime_path: draft.runtimePath,
        runner_mode: draft.runnerMode,
        approval_surface: draft.approvalSurface,
        credential_ref: draft.credentialRef,
        policy: {
          known_low_risk: "allow_with_receipt",
          high_risk: "approval_required",
          unknown: "deny",
        },
      },
      proof: {
        verifier: draft.verifierConnector,
        source_of_truth: draft.sourceOfRecord,
        proof_assertion: draft.proofAssertion,
        receipt_required: true,
        evidence_pack_required: true,
      },
    },
    runtime_policy_mandate_enforced: false,
  };
}

export default function AgentControlSetupPage() {
  const searchParams = useSearchParams();
  const editAgentId = searchParams.get("agentId") ?? searchParams.get("agent_id");
  const initialAgentName = searchParams.get("agentName") ?? searchParams.get("agent_name");
  const [activeStep, setActiveStep] = useState<WizardStepId>("agent");
  const [draft, setDraft] = useState<SetupDraft>(DEFAULT_DRAFT);
  const [dryRunAmountUsd, setDryRunAmountUsd] = useState("600");
  const [policyDryRunResult, setPolicyDryRunResult] = useState<RuntimePolicyDryRunResponse | null>(null);
  const [savedProfile, setSavedProfile] = useState<AgentProfileResponse | null>(null);
  const [savedMode, setSavedMode] = useState<ProtectionState | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [loadedAgentId, setLoadedAgentId] = useState<string | null>(null);
  const queryClient = useQueryClient();

  useEffect(() => {
    if (editAgentId) return;
    let nextDraft = DEFAULT_DRAFT;
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw) {
        nextDraft = mergeDraft(JSON.parse(raw) as Partial<SetupDraft>);
      }
    } catch {
      window.localStorage.removeItem(STORAGE_KEY);
    }
    if (initialAgentName?.trim()) {
      nextDraft = mergeDraft({ ...nextDraft, agentName: initialAgentName.trim() });
    }
    setDraft(nextDraft);
  }, [editAgentId, initialAgentName]);

  useEffect(() => {
    if (editAgentId) return;
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(draft));
  }, [draft, editAgentId]);

  const selectedAction = actionById(draft.primaryActionType);
  const selectedActions = useMemo(
    () => draft.selectedActionTypes.map(actionById),
    [draft.selectedActionTypes],
  );
  const toolNames = useMemo(() => splitToolNames(draft.toolNamesText), [draft.toolNamesText]);
  const stepIndex = STEPS.findIndex((step) => step.id === activeStep);
  const progress = Math.round(((stepIndex + 1) / STEPS.length) * 100);
  const registryQuery = useQuery({
    queryKey: ["agent-control-setup", "tool-registry", draft.primaryActionType],
    queryFn: ({ signal }) => getToolRegistry({ actionType: draft.primaryActionType }, signal),
    staleTime: 60_000,
  });
  const profileQuery = useQuery({
    queryKey: ["agents", "profile", editAgentId],
    queryFn: ({ signal }) => getAgentProfile(editAgentId ?? "", signal),
    enabled: Boolean(editAgentId),
    staleTime: 15_000,
    retry: false,
  });
  const runnersQuery = useQuery({
    queryKey: ["action-runners"],
    queryFn: ({ signal }) => listActionRunners(signal),
    staleTime: 15_000,
    refetchInterval: 30_000,
  });
  const ledgerConnectorQuery = useQuery({
    queryKey: ["system-of-record", "ledger-refund", "status"],
    queryFn: ({ signal }) => getLedgerRefundConnectorStatus(signal),
    staleTime: 30_000,
  });
  const stripeConnectorQuery = useQuery({
    queryKey: ["system-of-record", "stripe-refund", "status"],
    queryFn: ({ signal }) => getStripeRefundConnectorStatus(signal),
    staleTime: 30_000,
  });
  const razorpayConnectorQuery = useQuery({
    queryKey: ["system-of-record", "razorpay-refund", "status"],
    queryFn: ({ signal }) => getRazorpayRefundConnectorStatus(signal),
    staleTime: 30_000,
  });
  const customerConnectorQuery = useQuery({
    queryKey: ["system-of-record", "customer-record", "status"],
    queryFn: ({ signal }) => getCustomerRecordConnectorStatus(signal),
    staleTime: 30_000,
  });
  const genericConnectorQuery = useQuery({
    queryKey: ["system-of-record", "generic-rest", "status"],
    queryFn: ({ signal }) => getGenericRestConnectorStatus(signal),
    staleTime: 30_000,
  });
  const hubSpotConnectorQuery = useQuery({
    queryKey: ["system-of-record", "hubspot-crm", "status"],
    queryFn: ({ signal }) => getHubSpotCrmConnectorStatus(signal),
    staleTime: 30_000,
  });
  const salesforceConnectorQuery = useQuery({
    queryKey: ["system-of-record", "salesforce-crm", "status"],
    queryFn: ({ signal }) => getSalesforceCrmConnectorStatus(signal),
    staleTime: 30_000,
  });
  const zohoConnectorQuery = useQuery({
    queryKey: ["system-of-record", "zoho-crm", "status"],
    queryFn: ({ signal }) => getZohoCrmConnectorStatus(signal),
    staleTime: 30_000,
  });
  const zendeskConnectorQuery = useQuery({
    queryKey: ["system-of-record", "zendesk-ticket", "status"],
    queryFn: ({ signal }) => getZendeskTicketConnectorStatus(signal),
    staleTime: 30_000,
  });
  const jiraConnectorQuery = useQuery({
    queryKey: ["system-of-record", "jira-issue", "status"],
    queryFn: ({ signal }) => getJiraIssueConnectorStatus(signal),
    staleTime: 30_000,
  });
  const netsuiteConnectorQuery = useQuery({
    queryKey: ["system-of-record", "netsuite-finance", "status"],
    queryFn: ({ signal }) => getNetSuiteFinanceConnectorStatus(signal),
    staleTime: 30_000,
  });
  const postgresConnectorQuery = useQuery({
    queryKey: ["system-of-record", "postgres-read", "status"],
    queryFn: ({ signal }) => getPostgresReadConnectorStatus(signal),
    staleTime: 30_000,
  });
  const registry = registryQuery.data;

  useEffect(() => {
    const profile = profileQuery.data;
    if (!profile || loadedAgentId === profile.id) return;
    const nextDraft = draftFromProfile(profile);
    setDraft(nextDraft);
    setPolicyDryRunResult(null);
    setSavedProfile(null);
    setSavedMode(null);
    setFormError(null);
    setLoadedAgentId(profile.id);
  }, [loadedAgentId, profileQuery.data]);

  useEffect(() => {
    if (profileQuery.error) {
      setFormError(profileQuery.error instanceof Error ? profileQuery.error.message : "Could not load agent profile.");
    }
  }, [profileQuery.error]);

  const activeProfile = savedProfile ?? profileQuery.data ?? null;
  const expectedOperationKinds = useMemo(
    () => operationKindsForActions(selectedActions),
    [selectedActions],
  );
  const setupRunner = useMemo(
    () => findSetupRunner(runnersQuery.data?.items, activeProfile, draft),
    [activeProfile, draft, runnersQuery.data?.items],
  );
  const runnerEnvironmentMatches = setupRunner
    ? setupRunner.environment === (activeProfile?.environment || draft.environment || "production").trim()
    : false;
  const runnerCapabilityMatches = setupRunner
    ? runnerEnvironmentMatches
      && expectedOperationKinds.every((kind) => setupRunner.supported_operation_kinds.includes(kind))
    : false;
  const runnerReadiness = useMemo(
    () => setupRunner
      ? {
          exists: true,
          online: setupRunner.status === "online",
          capabilityMatches: runnerCapabilityMatches,
        }
      : { exists: false },
    [runnerCapabilityMatches, setupRunner],
  );
  const connectorStatuses = useMemo<Partial<Record<ConnectorFamily, ConnectorStatus | null>>>(() => ({
    ledger: ledgerConnectorQuery.data ?? null,
    stripe: stripeConnectorQuery.data ?? null,
    razorpay: razorpayConnectorQuery.data ?? null,
    customer: customerConnectorQuery.data ?? null,
    generic: genericConnectorQuery.data ?? null,
    hubspot: hubSpotConnectorQuery.data ?? null,
    salesforce: salesforceConnectorQuery.data ?? null,
    zoho: zohoConnectorQuery.data ?? null,
    zendesk: zendeskConnectorQuery.data ?? null,
    jira: jiraConnectorQuery.data ?? null,
    netsuite: netsuiteConnectorQuery.data ?? null,
    postgres: postgresConnectorQuery.data ?? null,
  }), [
    customerConnectorQuery.data,
    genericConnectorQuery.data,
    hubSpotConnectorQuery.data,
    ledgerConnectorQuery.data,
    razorpayConnectorQuery.data,
    stripeConnectorQuery.data,
    postgresConnectorQuery.data,
    salesforceConnectorQuery.data,
    zohoConnectorQuery.data,
    zendeskConnectorQuery.data,
    jiraConnectorQuery.data,
    netsuiteConnectorQuery.data,
  ]);
  const verifierConnectorFamily = connectorFamilyForVerifier(draft.verifierConnector);
  const verifierConnectorStatus = connectorStatusForFamily(verifierConnectorFamily, connectorStatuses);
  const verifierCompatible = connectorCompatibleForPrimary(draft);
  const verifierReadiness = useMemo(() => ({
    selected: Boolean(draft.verifierConnector),
    configured: Boolean(verifierConnectorStatus?.connected),
    tested: connectorAttempted(verifierConnectorStatus),
    healthy: connectorHealthy(verifierConnectorStatus),
    compatible: verifierCompatible,
  }), [draft.verifierConnector, verifierCompatible, verifierConnectorStatus]);
  const policyEnforced = activeProfile?.metadata?.runtime_policy_mandate_enforced === true;
  const firstReceiptQuery = useQuery({
    queryKey: ["agent-control-setup", "first-receipt", activeProfile?.id],
    queryFn: ({ signal }) => listActionIntents({
      agent_id: activeProfile?.id ?? null,
      proof_status: "matched",
      receipt_status: "generated",
      limit: 1,
    }, signal),
    enabled: Boolean(activeProfile?.id),
    staleTime: 15_000,
    refetchInterval: 15_000,
  });
  const firstActionQuery = useQuery({
    queryKey: ["agent-control-setup", "first-actions", activeProfile?.id],
    queryFn: ({ signal }) => listActionIntents({
      agent_id: activeProfile?.id ?? null,
      limit: 5,
    }, signal),
    enabled: Boolean(activeProfile?.id),
    staleTime: 5_000,
    refetchInterval: 5_000,
  });
  const firstReceiptMatched = (firstReceiptQuery.data?.items.length ?? 0) > 0;
  const firstActions = firstActionQuery.data?.items ?? [];
  const firstActionsLoading = firstActionQuery.isLoading || firstActionQuery.isFetching;

  const readiness = useMemo(() => deriveSetupReadiness({
    agentName: draft.agentName,
    runtimePath: draft.runtimePath,
    selectedActionTypes: draft.selectedActionTypes,
    toolNames,
    approvalRequiredAboveUsd: draft.approvalRequiredAboveUsd,
    denyAboveUsd: draft.denyAboveUsd,
    credentialRef: draft.credentialRef,
    verifierConnector: draft.verifierConnector,
    sourceOfRecord: draft.sourceOfRecord,
    proofAssertion: draft.proofAssertion,
    productName: draft.productName,
    businessGoal: draft.businessGoal,
    workflowId: draft.workflowId,
    workflowGoal: draft.workflowGoal,
    ownerTeam: draft.ownerTeam,
    criticalObjects: draft.criticalObjects,
    sourceSystems: draft.sourceSystems,
    approvalSurface: draft.approvalSurface,
    policyEnforced,
    runner: runnerReadiness,
    verifier: verifierReadiness,
    firstReceiptMatched,
  }), [draft, firstReceiptMatched, policyEnforced, runnerReadiness, toolNames, verifierReadiness]);

  const readinessItems = readiness.essentialChecks;
  const enrichmentItems = readiness.enrichmentChecks;
  const canSaveControlPlan = readiness.canEnablePolicy;
  const setupFlow = useMemo(() => buildSetupFlowView(readiness, draft.agentName), [draft.agentName, readiness]);
  const stepGuidance = useMemo(() => setupStepGuidance({
    activeStep,
    draft,
    firstActionCount: firstActions.length,
    firstActionsLoading,
    firstReceiptMatched,
    policyEnforced,
    readiness,
    readinessItems,
    toolNames,
  }), [
    activeStep,
    draft,
    firstActions.length,
    firstActionsLoading,
    firstReceiptMatched,
    policyEnforced,
    readiness,
    readinessItems,
    toolNames,
  ]);

  const saveMutation = useMutation({
    mutationFn: async (mode: ProtectionState) => {
      const profileState: ProtectionState = mode === "enforced" ? "plan_saved" : mode;
      const payload: AgentProfileCreatePayload = {
        display_name: draft.agentName.trim(),
        description: `${draft.productName} - ${draft.workflowGoal}`,
        runtime_path: draft.runtimePath,
        framework: draft.framework,
        environment: draft.environment,
        model_provider: draft.modelProvider,
        model_name: draft.modelName,
        tool_names: toolNames,
        allowed_action_types: draft.selectedActionTypes,
        blocked_action_types: [],
        risk_limits: {
          auto_allow_amount_usd: Number(draft.autoAllowAmountUsd),
          approval_required_above_usd: Number(draft.approvalRequiredAboveUsd),
          deny_above_usd: Number(draft.denyAboveUsd),
          approval_ttl_minutes: Number(draft.approvalTtlMinutes),
        },
        verification_connectors: [draft.verifierConnector],
        metadata: setupMetadata(draft, {
          protectionState: profileState,
        }),
      };
      const profile = editAgentId
        ? await updateAgentProfile(editAgentId, payload)
        : await createAgentProfile(payload);
      if (mode === "enforced") {
        return enforceAgentProfile(profile.id);
      }
      return profile;
    },
    onSuccess: (profile, mode) => {
      setSavedProfile(profile);
      setSavedMode(mode);
      setFormError(null);
      void queryClient.invalidateQueries({ queryKey: ["agents", "profiles"] });
      void queryClient.invalidateQueries({ queryKey: ["agents", "profile", profile.id] });
      void queryClient.invalidateQueries({ queryKey: ["action-runners"] });
      void queryClient.invalidateQueries({ queryKey: ["agent-control-setup", "first-receipt", profile.id] });
      void queryClient.invalidateQueries({ queryKey: ["agent-control-setup", "first-actions", profile.id] });
    },
    onError: (error) => {
      setFormError(error instanceof Error ? error.message : "Could not save setup.");
    },
  });

  const policyDryRunMutation = useMutation({
    mutationFn: async (amountUsd: number) => dryRunRuntimePolicy(
      buildPolicyDryRunPayload(draft, toolNames, amountUsd),
    ),
    onSuccess: (result) => {
      setPolicyDryRunResult(result);
      setFormError(null);
    },
    onError: (error) => {
      setFormError(error instanceof Error ? error.message : "Could not run policy dry-run.");
    },
  });

  function updateDraft(patch: Partial<SetupDraft>) {
    setDraft((current) => mergeDraft({ ...current, ...patch }));
    setPolicyDryRunResult(null);
    setSavedProfile(null);
    setSavedMode(null);
    setFormError(null);
  }

  function goToStep(id: WizardStepId) {
    setActiveStep(id);
  }

  function nextStep() {
    const next = STEPS[Math.min(stepIndex + 1, STEPS.length - 1)];
    setActiveStep(next.id);
  }

  function previousStep() {
    const previous = STEPS[Math.max(stepIndex - 1, 0)];
    setActiveStep(previous.id);
  }

  function discoverRiskActions() {
    const detected = ACTION_CATALOG.filter((action) => {
      const haystack = `${draft.toolNamesText} ${draft.businessGoal} ${draft.workflowGoal}`.toLowerCase();
      if (action.id === "refund") return /refund|payment|stripe|razorpay|ledger/.test(haystack);
      if (action.id === "payment_adjustment") return /credit|adjust|chargeback|payment|balance|billing/.test(haystack);
      if (action.id === "invoice_spend_approval") return /invoice|purchase|po|spend|vendor|budget|procure/.test(haystack);
      if (action.id === "customer_record_update") return /crm|customer|record|account/.test(haystack);
      if (action.id === "ticket_close") return /ticket|zendesk|support/.test(haystack);
      if (action.id === "email_send") return /email|message|recipient|sendgrid/.test(haystack);
      if (action.id === "database_record_update") return /database|postgres|sql|row|table/.test(haystack);
      if (action.id === "deploy_change") return /deploy|github|vercel|ci/.test(haystack);
      if (action.id === "custom") return /custom|workflow|agent action/.test(haystack);
      return /api|execute|workflow/.test(haystack);
    });
    const nextActions: AgentRiskActionType[] = detected.length > 0
      ? detected.map((action) => action.id)
      : ["internal_api_mutation"];
    const fallbackPrimary = nextActions[0] ?? "internal_api_mutation";
    const primary: AgentRiskActionType = nextActions.includes(draft.primaryActionType)
      ? draft.primaryActionType
      : fallbackPrimary;
    updateDraft({
      selectedActionTypes: nextActions,
      primaryActionType: primary,
      verifierConnector: actionById(primary).verifier,
      toolNamesText: Array.from(new Set([...toolNames, ...nextActions.map((id) => actionById(id).defaultTool)])).join(", "),
    });
  }

  function applyActionTemplate(templateId: AgentActionTemplateId) {
    const template = templateById(templateId);
    updateDraft({
      actionTemplateId: template.id,
      primaryActionType: template.actionType,
      selectedActionTypes: template.selectedActionTypes,
      toolNamesText: template.toolNames,
      verifierConnector: template.verifierConnector,
      sourceOfRecord: template.sourceOfRecord,
      proofAssertion: template.proofAssertion,
    });
  }

  function runPolicyDryRun() {
    if (!policyEnforced) {
      setFormError("Enable the project policy before running a policy dry-run.");
      setActiveStep("proof");
      return;
    }
    const amountUsd = parseDryRunAmount(dryRunAmountUsd);
    if (amountUsd == null) {
      setFormError("Enter a valid non-negative dry-run amount.");
      setActiveStep("proof");
      return;
    }
    setFormError(null);
    setActiveStep("proof");
    policyDryRunMutation.mutate(amountUsd);
  }

  function saveDraft() {
    if (!draft.agentName.trim()) {
      setFormError("Add an agent name before saving a draft.");
      return;
    }
    if (editAgentId && profileQuery.isLoading) {
      setFormError("Wait for the agent profile to finish loading before saving.");
      return;
    }
    saveMutation.mutate("draft");
  }

  function submitSetup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (editAgentId && profileQuery.isLoading) {
      setFormError("Wait for the agent profile to finish loading before enabling policy.");
      return;
    }
    if (!canSaveControlPlan) {
      setFormError("Complete the essential readiness checklist before enabling the project policy.");
      return;
    }
    saveMutation.mutate("enforced");
  }

  return (
    <div className="agent-setup-screen">
      <DashboardVerdictHero
        eyebrow="Agent Control Setup"
        icon={<Workflow aria-hidden="true" size={18} />}
        title={setupFlow.title}
        copy={setupFlow.copy}
        tone={setupFlow.tone}
        pill={setupFlow.pill}
        updatedLabel={`Step ${stepIndex + 1} of ${STEPS.length}`}
        notices={(
          <Link href="/agents" className="agents-text-link">
            <ArrowLeft aria-hidden="true" />
            Agents
          </Link>
        )}
        actions={(
          <>
            {activeProfile ? (
              <DashboardButtonLink href={`/agents/${activeProfile.id}`} variant="soft">
                Agent home
              </DashboardButtonLink>
            ) : null}
            <DashboardButtonLink href="/integrations" variant="soft">
              Connectors
            </DashboardButtonLink>
          </>
        )}
      />
      <DashboardMetricStrip
        ariaLabel="Agent setup readiness"
        columns={5}
        metrics={setupFlow.metrics}
      />

      <section className="agent-setup-layout">
        <aside className="agent-setup-stepper" aria-label="Agent setup steps">
          <div className="agent-setup-progress">
            <span>Setup progress</span>
            <strong>{progress}%</strong>
            <div>
              <i style={{ width: `${progress}%` }} />
            </div>
          </div>
          {STEPS.map((step, index) => {
            const Icon = step.icon;
            const active = step.id === activeStep;
            const complete = index < stepIndex;
            return (
              <button
                key={step.id}
                type="button"
                className={`agent-setup-step${active ? " is-active" : ""}${complete ? " is-complete" : ""}`}
                onClick={() => goToStep(step.id)}
              >
                <span className="agent-setup-step-icon">
                  {complete ? <Check aria-hidden="true" /> : <Icon aria-hidden="true" />}
                </span>
                <span>
                  <strong>{step.label}</strong>
                  <small>{step.kicker}</small>
                </span>
              </button>
            );
          })}
        </aside>

        <form className="agent-setup-card" onSubmit={submitSetup}>
          {activeStep === "agent" ? (
            <AgentBasicsStep draft={draft} updateDraft={updateDraft} />
          ) : null}
          {activeStep === "risk" ? (
            <RiskActionStep
              draft={draft}
              registry={registry}
              registryLoading={registryQuery.isLoading}
              selectedActions={selectedActions}
              toolNames={toolNames}
              updateDraft={updateDraft}
              onApplyTemplate={applyActionTemplate}
              onDiscover={discoverRiskActions}
            />
          ) : null}
          {activeStep === "control" ? (
            <ControlRulesStep
              draft={draft}
              expectedOperationKinds={expectedOperationKinds}
              runner={setupRunner}
              runnerCapabilityMatches={runnerCapabilityMatches}
              runnerEnvironmentMatches={runnerEnvironmentMatches}
              updateDraft={updateDraft}
            />
          ) : null}
          {activeStep === "proof" ? (
            <ProofReadinessStep
              draft={draft}
              readinessItems={readinessItems}
              enrichmentItems={enrichmentItems}
              verifierConnector={verifierConnectorStatus}
              verifierConnectorFamily={verifierConnectorFamily}
              verifierCompatible={verifierCompatible}
              readiness={readiness}
              policyEnforced={policyEnforced}
              dryRunAmountUsd={dryRunAmountUsd}
              policyDryRunResult={policyDryRunResult}
              dryRunPending={policyDryRunMutation.isPending}
              savedMode={savedMode}
              savedProfile={savedProfile}
              saving={saveMutation.isPending}
              formError={formError}
              updateDraft={updateDraft}
              onDryRunAmountChange={setDryRunAmountUsd}
              onRunPolicyDryRun={runPolicyDryRun}
            />
          ) : null}
          {activeStep === "live" ? (
            <GoLiveStep
              draft={draft}
              readiness={readiness}
              activeProfile={activeProfile}
              firstActions={firstActions}
              firstActionsLoading={firstActionsLoading}
              firstReceiptMatched={firstReceiptMatched}
              firstReceiptAction={firstReceiptQuery.data?.items[0] ?? null}
              policyDryRunResult={policyDryRunResult}
            />
          ) : null}

          <SetupStepGuidancePanel guidance={stepGuidance} />

          <div className="agent-setup-actions">
            <DashboardButton icon={<ArrowLeft />} onClick={previousStep} disabled={stepIndex === 0} variant="soft">
              Back
            </DashboardButton>
            {activeStep === "proof" ? (
              <span className="agent-setup-action-cluster">
                <DashboardButton icon={<Save />} onClick={saveDraft} disabled={saveMutation.isPending} variant="soft">
                  {saveMutation.isPending ? "Saving..." : editAgentId ? "Save changes" : "Save draft"}
                </DashboardButton>
                <DashboardButton icon={<ShieldCheck />} type="submit" disabled={saveMutation.isPending} variant="primary">
                  {saveMutation.isPending ? "Enforcing..." : "Enable project policy"}
                </DashboardButton>
                <DashboardButton icon={<ArrowRight />} iconPosition="right" onClick={nextStep} variant="soft">
                  Go live
                </DashboardButton>
              </span>
            ) : activeStep === "live" ? (
              <span className="agent-setup-action-cluster">
                <DashboardButtonLink href="/actions" variant="soft">
                  Open Actions
                </DashboardButtonLink>
                <DashboardButtonLink href="/evidence" variant="primary">
                  Open Evidence
                </DashboardButtonLink>
              </span>
            ) : (
              <DashboardButton icon={<ArrowRight />} iconPosition="right" onClick={nextStep} variant="primary">
                Continue
              </DashboardButton>
            )}
          </div>
        </form>

        <ProtectionPlanPreview
          draft={draft}
          registry={registry}
          registryLoading={registryQuery.isLoading}
          selectedAction={selectedAction}
          selectedActions={selectedActions}
          toolNames={toolNames}
        />
      </section>
    </div>
  );
}

function SetupStepGuidancePanel({ guidance }: { guidance: SetupStepGuidance }) {
  const Icon = guidance.tone === "green" ? CheckCircle2 : guidance.tone === "blue" ? PlayCircle : ShieldAlert;
  return (
    <div className="agent-setup-step-guidance" data-tone={guidance.tone} aria-label="Setup step guidance">
      <Icon aria-hidden="true" />
      <span>
        <strong>{guidance.title}</strong>
        <small>{guidance.detail}</small>
      </span>
    </div>
  );
}

function AgentBasicsStep({
  draft,
  updateDraft,
}: {
  draft: SetupDraft;
  updateDraft: (patch: Partial<SetupDraft>) => void;
}) {
  return (
    <section className="agent-setup-step-content">
      <StepHeader
        eyebrow="Step 1"
        title="Agent Identity"
        body="Tell Zroky which agent and operating context this protection will apply to."
      />
      <div className="agent-setup-form-grid">
        <label className="agent-setup-field">
          <span>Agent name</span>
          <input
            value={draft.agentName}
            onChange={(event) => updateDraft({ agentName: event.target.value })}
            placeholder="Operations Agent"
          />
        </label>
        <label className="agent-setup-field">
          <span>Agent framework</span>
          <select value={draft.framework} onChange={(event) => updateDraft({ framework: event.target.value })}>
            {FRAMEWORK_OPTIONS.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </label>
        <label className="agent-setup-field">
          <span>Environment</span>
          <select value={draft.environment} onChange={(event) => updateDraft({ environment: event.target.value })}>
            <option value="production">production</option>
            <option value="staging">staging</option>
            <option value="development">development</option>
          </select>
        </label>
      </div>
      <AdvancedDetails title="Advanced agent context">
        <div className="agent-setup-form-grid">
          <label className="agent-setup-field">
            <span>Owner team</span>
            <input value={draft.ownerTeam} onChange={(event) => updateDraft({ ownerTeam: event.target.value })} />
          </label>
          <label className="agent-setup-field">
            <span>Workflow name</span>
            <input
              value={draft.productName}
              onChange={(event) => updateDraft({ productName: event.target.value })}
              placeholder="Production Agent Workflow"
            />
          </label>
          <label className="agent-setup-field">
            <span>Business category</span>
            <select
              value={draft.productCategory}
              onChange={(event) => updateDraft({ productCategory: event.target.value })}
            >
              {PRODUCT_CATEGORIES.map((category) => (
                <option key={category} value={category}>{category}</option>
              ))}
            </select>
          </label>
          <label className="agent-setup-field">
            <span>Workflow ID</span>
            <input value={draft.workflowId} onChange={(event) => updateDraft({ workflowId: slugify(event.target.value) })} />
          </label>
          <label className="agent-setup-field">
            <span>Model</span>
            <input
              value={`${draft.modelProvider}/${draft.modelName}`}
              onChange={(event) => {
                const [provider, ...modelParts] = event.target.value.split("/");
                updateDraft({
                  modelProvider: provider.trim(),
                  modelName: modelParts.join("/").trim() || draft.modelName,
                });
              }}
              placeholder="openai/gpt-4.1"
            />
          </label>
        </div>
        <label className="agent-setup-field">
          <span>Primary business goal</span>
          <textarea
            value={draft.businessGoal}
            onChange={(event) => updateDraft({ businessGoal: event.target.value })}
            rows={3}
          />
        </label>
        <label className="agent-setup-field">
          <span>Workflow notes</span>
          <textarea
            value={draft.workflowGoal}
            onChange={(event) => updateDraft({ workflowGoal: event.target.value })}
            rows={3}
          />
        </label>
        <SelectionGrid
          label="Business objects this agent may touch"
          values={CRITICAL_OBJECTS}
          selected={draft.criticalObjects}
          onToggle={(value) => updateDraft({ criticalObjects: toggleListValue(draft.criticalObjects, value) })}
        />
        <SelectionGrid
          label="Systems Zroky should verify against"
          values={SOURCE_SYSTEMS}
          selected={draft.sourceSystems}
          onToggle={(value) => updateDraft({ sourceSystems: toggleListValue(draft.sourceSystems, value) })}
        />
      </AdvancedDetails>
    </section>
  );
}

function RiskActionStep({
  draft,
  registry,
  registryLoading,
  selectedActions,
  toolNames,
  updateDraft,
  onApplyTemplate,
  onDiscover,
}: {
  draft: SetupDraft;
  registry: ToolRegistryResponse | undefined;
  registryLoading: boolean;
  selectedActions: ActionCatalogItem[];
  toolNames: string[];
  updateDraft: (patch: Partial<SetupDraft>) => void;
  onApplyTemplate: (templateId: AgentActionTemplateId) => void;
  onDiscover: () => void;
}) {
  const tools = launchTools(registry);
  const selectedTemplate = templateById(draft.actionTemplateId);
  return (
    <section className="agent-setup-step-content">
      <StepHeader
        eyebrow="Step 2"
        title="Protected Action"
        body="Choose the first action Zroky should control. Start with one high-value path; you can add more after the first receipt."
      />
      <div className="agent-setup-template-panel">
        <label className="agent-setup-field">
          <span>Start from a template</span>
          <select
            value={draft.actionTemplateId}
            onChange={(event) => onApplyTemplate(event.target.value as AgentActionTemplateId)}
          >
            {ACTION_TEMPLATES.map((template) => (
              <option key={template.id} value={template.id}>{template.label}</option>
            ))}
          </select>
        </label>
        <p className="agent-setup-muted">{selectedTemplate.helper}</p>
      </div>
      <label className="agent-setup-field">
        <span>Agent tools or function names</span>
        <textarea
          value={draft.toolNamesText}
          onChange={(event) => updateDraft({ toolNamesText: event.target.value })}
          rows={4}
          placeholder="crm.customers.update, deploy.service, billing.credits.apply"
        />
      </label>
      <div className="agent-setup-inline-actions">
        <DashboardButton icon={<RefreshCw />} onClick={onDiscover} variant="soft">
          Detect risky actions
        </DashboardButton>
        <span>{toolNames.length} tool call{toolNames.length === 1 ? "" : "s"} parsed</span>
      </div>
      <div className="agent-setup-primary-action" aria-label="Primary protected action">
        <div>
          <span>Primary action</span>
          <strong>{actionById(draft.primaryActionType).label}</strong>
          <small>{actionById(draft.primaryActionType).businessWhy}</small>
        </div>
        <select
          value={draft.primaryActionType}
          onChange={(event) => {
            const primary = event.target.value as AgentRiskActionType;
            updateDraft({
              primaryActionType: primary,
              selectedActionTypes: draft.selectedActionTypes.includes(primary)
                ? draft.selectedActionTypes
                : [...draft.selectedActionTypes, primary],
              verifierConnector: actionById(primary).verifier,
            });
          }}
        >
          {ACTION_CATALOG.map((action) => (
            <option key={action.id} value={action.id}>{action.label}</option>
          ))}
        </select>
      </div>
      <div className="agent-setup-action-groups" aria-label="Detected risky actions">
        {ACTION_VERBS.map((verb) => (
          <div key={verb} className="agent-setup-action-group">
            <div className="agent-setup-action-group-head">
              <span>{verb}</span>
              <small>{ACTION_CATALOG.filter((action) => action.verb === verb).length} launch actions</small>
            </div>
            <div className="agent-setup-action-grid">
              {ACTION_CATALOG.filter((action) => action.verb === verb).map((action) => {
                const selected = draft.selectedActionTypes.includes(action.id);
                return (
                  <button
                    key={action.id}
                    type="button"
                    className={`agent-setup-action-card${selected ? " is-selected" : ""}`}
                    onClick={() => {
                      const nextSelected = toggleActionValue(draft.selectedActionTypes, action.id);
                      const safeSelected = nextSelected.length > 0 ? nextSelected : [action.id];
                      const fallbackAction = safeSelected[0] ?? action.id;
                      const primaryAction = safeSelected.includes(draft.primaryActionType)
                        ? draft.primaryActionType
                        : fallbackAction;
                      updateDraft({
                        selectedActionTypes: safeSelected,
                        primaryActionType: primaryAction,
                        verifierConnector: actionById(primaryAction).verifier,
                      });
                    }}
                  >
                    <span>{action.riskClass}</span>
                    <strong>{action.label}</strong>
                    <small>{action.sourceSystem}</small>
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>
      <div className="agent-setup-registry-strip">
        <Plug aria-hidden="true" />
        <div>
          <strong>{registryLoading ? "Loading launch tools" : `${tools.filter((item) => item.status === "available").length} available launch tools`}</strong>
          <span>
            {registry?.recommended.next_steps[0]
              ?? "Runtime, approval, and proof connectors appear here based on the protected action."}
          </span>
        </div>
      </div>
      <div className="agent-setup-toolbox" aria-label="Available launch tools">
        {tools.map((tool) => (
          <div key={tool.id} data-recommended={tool.recommended ? "true" : "false"} data-status={tool.status}>
            <span>{tool.kind}</span>
            <strong>{tool.label}</strong>
            <small>{tool.recommended ? "Recommended" : tool.status.replace(/_/g, " ")}</small>
          </div>
        ))}
      </div>
      <AdvancedDetails title="Advanced machine contract">
        <div className="agent-setup-contract-list">
          {selectedActions.map((action) => (
            <label key={action.id} className={`agent-setup-contract-row${draft.primaryActionType === action.id ? " is-active" : ""}`}>
              <input
                type="radio"
                name="primary-action"
                value={action.id}
                checked={draft.primaryActionType === action.id}
                onChange={() => updateDraft({ primaryActionType: action.id, verifierConnector: action.verifier })}
              />
              <span className="agent-setup-contract-risk">{action.riskClass}</span>
              <span>
                <strong>{action.label}</strong>
                <small>{action.verb} / {action.resource}</small>
              </span>
              <em>{action.verb}</em>
            </label>
          ))}
        </div>
        <div className="agent-setup-code-panel" aria-label="Machine contract preview">
          <span>Machine contract preview</span>
          <pre>{JSON.stringify({
            id: actionContractId(draft),
            verb: actionById(draft.primaryActionType).verb,
            system: actionById(draft.primaryActionType).sourceSystem,
            resource: actionById(draft.primaryActionType).resource,
            risk_class: actionById(draft.primaryActionType).riskClass,
            canonical_intent_digest: intentDigest(draft),
            runner_required: true,
            verifier_required: true,
            receipt_required: true,
          }, null, 2)}</pre>
        </div>
      </AdvancedDetails>
    </section>
  );
}

function ControlRulesStep({
  draft,
  expectedOperationKinds,
  runner,
  runnerCapabilityMatches,
  runnerEnvironmentMatches,
  updateDraft,
}: {
  draft: SetupDraft;
  expectedOperationKinds: string[];
  runner: ActionRunnerResponse | null;
  runnerCapabilityMatches: boolean;
  runnerEnvironmentMatches: boolean;
  updateDraft: (patch: Partial<SetupDraft>) => void;
}) {
  const runnerTitle = runnerStatusTitle(runner, runnerCapabilityMatches, runnerEnvironmentMatches);
  const runnerDetail = runnerStatusDetail(
    runner,
    runnerCapabilityMatches,
    runnerEnvironmentMatches,
    expectedOperationKinds,
  );
  const runnerTone = runnerStatusTone(runner, runnerCapabilityMatches, runnerEnvironmentMatches);
  return (
    <section className="agent-setup-step-content">
      <StepHeader
        eyebrow="Step 3"
        title="Control Path"
        body="Set policy, approval, runner, and credential isolation for this protected action."
      />
      <div className="agent-setup-policy-grid" aria-label="Policy decision preview">
        <div>
          <span>KNOWN LOW RISK</span>
          <strong>Allow with receipt</strong>
          <small>Only for selected action types inside the agent mandate.</small>
        </div>
        <div>
          <span>HIGH RISK</span>
          <strong>Hold for approval</strong>
          <small>Dashboard and Slack approvals bind to the exact proposed action.</small>
        </div>
        <div>
          <span>UNKNOWN</span>
          <strong>Deny by default</strong>
          <small>Anything outside the selected action map fails closed.</small>
        </div>
      </div>
      <div className="agent-setup-intent-note">
        <ShieldCheck aria-hidden="true" />
        <span>
          <strong>Approval binds to the exact action intent.</strong>
          <small>Operators approve one specific action, not a vague future permission.</small>
        </span>
      </div>
      <div className="agent-setup-intent-note" data-tone={runnerTone} aria-label="Runner readiness">
        <Plug aria-hidden="true" />
        <span>
          <strong>{runnerTitle}</strong>
          <small>{runnerDetail}</small>
        </span>
      </div>
      <div className="agent-setup-form-grid">
        <label className="agent-setup-field">
          <span>Runtime path</span>
          <select
            value={draft.runtimePath}
            onChange={(event) => updateDraft({ runtimePath: event.target.value as AgentRuntimePath })}
          >
            {RUNTIME_PATHS.map((item) => (
              <option key={item.value} value={item.value}>{item.label}</option>
            ))}
          </select>
        </label>
        <label className="agent-setup-field">
          <span>Runner mode</span>
          <select
            value={draft.runnerMode}
            onChange={(event) => updateDraft({ runnerMode: event.target.value as RunnerMode })}
          >
            <option value="managed">Managed Zroky runner</option>
            <option value="customer_hosted">Customer-hosted runner</option>
          </select>
        </label>
        <label className="agent-setup-field">
          <span>Approval surface</span>
          <select
            value={draft.approvalSurface}
            onChange={(event) => updateDraft({ approvalSurface: event.target.value as ApprovalSurface })}
          >
            <option value="dashboard">Zroky dashboard only</option>
            <option value="slack">Slack only</option>
            <option value="dashboard_slack">Zroky dashboard and Slack</option>
          </select>
        </label>
        <label className="agent-setup-field">
          <span>Credential reference</span>
          <input
            value={draft.credentialRef}
            onChange={(event) => updateDraft({ credentialRef: event.target.value })}
            placeholder="cred_prod_protected_actions"
          />
        </label>
      </div>
      <div className="agent-setup-runtime-grid">
        <div>
          <KeyRound aria-hidden="true" />
          <strong>Agent does not get secrets</strong>
          <span>The runner uses a credential reference; raw protected credentials stay out of the agent.</span>
        </div>
        <div>
          <LockKeyhole aria-hidden="true" />
          <strong>Approval is exact</strong>
          <span>The approval applies only to the proposed action, not a broad future permission.</span>
        </div>
        <div>
          <ShieldAlert aria-hidden="true" />
          <strong>Unknown means deny</strong>
          <span>If the agent calls a tool outside this setup, Zroky blocks it by default.</span>
        </div>
      </div>
      <AdvancedDetails title="Advanced policy thresholds">
        <div className="agent-setup-form-grid">
          <label className="agent-setup-field">
            <span>Auto-allow value ceiling</span>
            <input
              type="number"
              min="0"
              value={draft.autoAllowAmountUsd}
              onChange={(event) => updateDraft({ autoAllowAmountUsd: event.target.value })}
            />
          </label>
          <label className="agent-setup-field">
            <span>Approval required above</span>
            <input
              type="number"
              min="0"
              value={draft.approvalRequiredAboveUsd}
              onChange={(event) => updateDraft({ approvalRequiredAboveUsd: event.target.value })}
            />
          </label>
          <label className="agent-setup-field">
            <span>Deny above</span>
            <input
              type="number"
              min="0"
              value={draft.denyAboveUsd}
              onChange={(event) => updateDraft({ denyAboveUsd: event.target.value })}
            />
          </label>
          <label className="agent-setup-field">
            <span>Approval expiry minutes</span>
            <input
              type="number"
              min="1"
              value={draft.approvalTtlMinutes}
              onChange={(event) => updateDraft({ approvalTtlMinutes: event.target.value })}
            />
          </label>
        </div>
        <p className="agent-setup-muted">
          These numbers are optional guardrails for money, spend, or value-like actions. Non-money actions still use action type, environment, role, and approval rules.
        </p>
      </AdvancedDetails>
    </section>
  );
}

function ProofReadinessStep({
  draft,
  readinessItems,
  enrichmentItems,
  verifierConnector,
  verifierConnectorFamily,
  verifierCompatible,
  readiness,
  policyEnforced,
  dryRunAmountUsd,
  policyDryRunResult,
  dryRunPending,
  savedMode,
  savedProfile,
  saving,
  formError,
  updateDraft,
  onDryRunAmountChange,
  onRunPolicyDryRun,
}: {
  draft: SetupDraft;
  readinessItems: SetupCheck[];
  enrichmentItems: SetupCheck[];
  verifierConnector: ConnectorStatus | null;
  verifierConnectorFamily: ConnectorFamily;
  verifierCompatible: boolean;
  readiness: SetupReadiness;
  policyEnforced: boolean;
  dryRunAmountUsd: string;
  policyDryRunResult: RuntimePolicyDryRunResponse | null;
  dryRunPending: boolean;
  savedMode: ProtectionState | null;
  savedProfile: AgentProfileResponse | null;
  saving: boolean;
  formError: string | null;
  updateDraft: (patch: Partial<SetupDraft>) => void;
  onDryRunAmountChange: (value: string) => void;
  onRunPolicyDryRun: () => void;
}) {
  const template = templateForDraft(draft);
  const snippet = buildProtectedAgentSnippet(template, "current-project");
  const mandate = buildMandateStarter(template);
  const selectedAction = actionById(draft.primaryActionType);
  const actionLabel = businessActionLabel(selectedAction);
  const verifierTitle = verifierStatusTitle(verifierConnector, verifierCompatible);
  const verifierDetail = verifierStatusDetail(draft, verifierConnectorFamily, verifierConnector, verifierCompatible);
  const verifierReady = verifierCompatible && connectorHealthy(verifierConnector);
  const verifierHref = connectorHrefForFamily(verifierConnectorFamily);

  return (
    <section className="agent-setup-step-content">
      <StepHeader
        eyebrow="Step 4"
        title="Proof & Readiness"
        body="Define what success means, enable the project-level runtime policy, then run a real policy dry-run that is not recorded."
      />
      <div className="agent-setup-form-grid">
        <label className="agent-setup-field">
          <span>Verifier</span>
          <select
            value={draft.verifierConnector}
            onChange={(event) => updateDraft({ verifierConnector: event.target.value as AgentVerificationConnectorType })}
          >
            {(["generic_rest", "database_read", "stripe_refund", "razorpay_refund", "netsuite_finance", "ledger_refund", "crm_record", "hubspot_crm", "salesforce_crm", "zoho_crm", "zendesk_ticket", "jira_issue", "ticket_status", "email_delivery", "github_ci", "webhook_callback"] as AgentVerificationConnectorType[]).map((item) => (
              <option key={item} value={item}>{connectorLabel(item)}</option>
            ))}
          </select>
        </label>
        <label className="agent-setup-field">
          <span>Source of truth</span>
          <input
            value={draft.sourceOfRecord}
            onChange={(event) => updateDraft({ sourceOfRecord: event.target.value })}
            placeholder="Primary business system API"
          />
        </label>
      </div>
      <label className="agent-setup-field">
        <span>Proof assertion</span>
        <textarea
          value={draft.proofAssertion}
          onChange={(event) => updateDraft({ proofAssertion: event.target.value })}
          rows={3}
          placeholder="Example: refund exists in Stripe with expected amount and status=succeeded."
        />
      </label>
      <div className="agent-setup-intent-note" data-tone={verifierReady ? "green" : "yellow"} aria-label="Verifier readiness">
        <Database aria-hidden="true" />
        <span>
          <strong>{verifierTitle}</strong>
          <small>{verifierDetail}</small>
          {!verifierReady ? (
            <Link href={verifierHref} className="agent-setup-inline-link">
              Connect in Integrations
            </Link>
          ) : null}
        </span>
      </div>
      <p className="agent-setup-muted">Essentials gate policy enable. Optional context enriches receipts but does not block the first proof.</p>
      <div className="agent-setup-readiness-grid" aria-label="Essential readiness">
        {readinessItems.map((item) => (
          <div key={item.id} data-done={item.done ? "true" : "false"}>
            {item.done ? <CheckCircle2 aria-hidden="true" /> : <ShieldAlert aria-hidden="true" />}
            <strong>{item.label}</strong>
            <span>{item.done ? "Ready" : "Needs attention"}</span>
          </div>
        ))}
      </div>
      <AdvancedDetails title="Optional context">
        <div className="agent-setup-readiness-grid" aria-label="Optional enrichment">
          {enrichmentItems.map((item) => (
            <div key={item.id} data-done={item.done ? "true" : "false"}>
              {item.done ? <CheckCircle2 aria-hidden="true" /> : <ShieldAlert aria-hidden="true" />}
              <strong>{item.label}</strong>
              <span>{item.done ? "Added" : "Optional"}</span>
            </div>
          ))}
        </div>
      </AdvancedDetails>
      <div className="agent-setup-simulation agent-setup-dry-run-panel" aria-label="Policy dry-run">
        <PlayCircle aria-hidden="true" />
        <span>
          <strong>Policy dry-run · not recorded</strong>
          <small>
            Runs the real runtime-policy gate without creating a decision row, approval request, runner execution, verifier read, or receipt.
          </small>
        </span>
        <div className="agent-setup-dry-run-controls">
          <label className="agent-setup-field">
            <span>Test amount USD</span>
            <input
              type="number"
              min="0"
              value={dryRunAmountUsd}
              onChange={(event) => onDryRunAmountChange(event.target.value)}
            />
          </label>
          <DashboardButton onClick={onRunPolicyDryRun} disabled={!policyEnforced || dryRunPending} variant="soft">
            {dryRunPending ? "Running..." : "Run policy dry-run"}
          </DashboardButton>
        </div>
        {!policyEnforced ? (
          <small className="agent-setup-dry-run-note">Enable project policy before running a dry-run.</small>
        ) : null}
        {policyDryRunResult ? (
          <div className="agent-setup-dry-run-result" role="status">
            <strong>{policyDryRunResult.status.replace(/_/g, " ")}</strong>
            <span>{policyDryRunResult.recorded ? "recorded" : "not recorded"}</span>
            {policyDryRunResult.reasons.length > 0 ? <small>{policyDryRunResult.reasons.join("; ")}</small> : null}
          </div>
        ) : null}
      </div>
      <div className="agent-setup-receipt-preview" aria-label="First Action Receipt">
        <div className="agent-setup-receipt-head">
          <div>
            <span>First Action Receipt</span>
            <strong>{readiness.state === "live" ? "Matched receipt seen" : "Waiting for first real Action Receipt"}</strong>
          </div>
          <span className={`alert-cat-badge ${readiness.state === "live" ? "badge-green" : "badge-yellow"}`}>
            {readiness.state === "live" ? "live" : "pending"}
          </span>
        </div>
        <div className="agent-setup-receipt-grid">
          <div>
            <span>Agent</span>
            <strong>{draft.agentName}</strong>
          </div>
          <div>
            <span>Action</span>
            <strong>{actionLabel}</strong>
          </div>
          <div>
            <span>Intent digest</span>
            <strong>{intentDigest(draft)}</strong>
          </div>
          <div>
            <span>Policy decision</span>
            <strong>{policyDryRunResult ? policyDryRunResult.status.replace(/_/g, " ") : "run policy dry-run"}</strong>
          </div>
          <div>
            <span>Approver</span>
            <strong>{approvalPlanLabel(draft.approvalSurface)}</strong>
          </div>
          <div>
            <span>Runner</span>
            <strong>{runnerModeLabel(draft.runnerMode)}</strong>
          </div>
          <div>
            <span>Verifier</span>
            <strong>{connectorLabel(draft.verifierConnector)}</strong>
          </div>
          <div>
            <span>Source of truth</span>
            <strong>{draft.sourceOfRecord}</strong>
          </div>
          <div>
            <span>Outcome</span>
            <strong>{policyDryRunResult ? `${policyDryRunResult.status.replace(/_/g, " ")} · not recorded` : "no dry-run yet"}</strong>
          </div>
          <div>
            <span>Evidence pack</span>
            <strong>{readiness.state === "live" ? "generated from real receipt" : "generated only after real action receipt"}</strong>
          </div>
        </div>
      </div>
      <AdvancedDetails title="Advanced implementation snippets">
        <div className="agent-setup-code-split">
          <CopyableCode label="SDK capture starter" value={snippet} />
          <CopyableCode label="Mandate starter" value={mandate} />
        </div>
      </AdvancedDetails>
      <AdvancedDetails title="Advanced proof settings">
        <label className="agent-setup-field">
          <span>Idempotency scope</span>
          <input
            value={draft.idempotencyScope}
            onChange={(event) => updateDraft({ idempotencyScope: event.target.value })}
          />
        </label>
        <div className="agent-setup-runtime-grid">
          <div>
            <Database aria-hidden="true" />
            <strong>{verificationLevel(draft)} verification</strong>
            <span>{connectorLabel(draft.verifierConnector)} checks source-of-truth state, not only HTTP success.</span>
          </div>
          <div>
            <FileJson aria-hidden="true" />
            <strong>{assuranceLevel(draft)} assurance</strong>
            <span>Policy, approval, runner, verifier, and receipt will be enforced through the project runtime gate.</span>
          </div>
        </div>
      </AdvancedDetails>
      {formError ? <p className="agent-setup-error">{formError}</p> : null}
      {savedProfile ? (
        <div className="agent-setup-success" role="status">
          <CheckCircle2 aria-hidden="true" />
          <div>
            <strong>
              {savedMode === "enforced"
                ? `Project policy enabled for ${savedProfile.display_name}.`
                : savedMode === "plan_saved"
                  ? `Control plan saved for ${savedProfile.display_name}.`
                  : `${savedProfile.display_name} draft saved.`}
            </strong>
            <span>
              {savedMode === "enforced"
                ? "Project runtime policy enforced. Next: route one real action and confirm the first Action Receipt."
                : savedMode === "plan_saved"
                  ? "Control plan saved. Enable the project policy before trusting live agent actions."
                  : "Draft saved. Run the simulated preview and enable the project policy when the route is ready."}
            </span>
            <div>
              <Link href={`/agents/${savedProfile.id}`}>Agent profile</Link>
              <Link href="/policies">Policies</Link>
              <Link href="/actions">Actions</Link>
              <Link href="/evidence">Evidence</Link>
            </div>
            <SetupHandoff
              draft={draft}
              profile={savedProfile}
              readiness={readiness}
              policyDryRunResult={policyDryRunResult}
            />
          </div>
        </div>
      ) : saving ? (
        <p className="agent-setup-saving">Saving setup to the protected agent registry...</p>
      ) : null}
    </section>
  );
}

function SetupHandoff({
  draft,
  profile,
  readiness,
  policyDryRunResult,
}: {
  draft: SetupDraft;
  profile: AgentProfileResponse;
  readiness: SetupReadiness;
  policyDryRunResult: RuntimePolicyDryRunResponse | null;
}) {
  const template = templateForDraft(draft);
  const snippet = buildProtectedAgentSnippet(template, "current-project");
  let href = `/agents/${profile.id}`;
  let cta = "Open agent profile";
  let title = "Control plan saved";
  let body = "Use the domain pages below to manage profile, policy, runner, connector, actions, and evidence.";

  if (readiness.verifierStatus !== "ready") {
    href = connectorHrefForFamily(connectorFamilyForVerifier(draft.verifierConnector));
    cta = "Fix verifier";
    title = "Verifier still needs a real connector";
    body = "Connect or retest the source-of-record connector. Until it is healthy, real actions resolve honestly as not_verified.";
  } else if (readiness.runnerStatus !== "ready") {
    href = "/agents?tab=runners";
    cta = "Open runners";
    title = readiness.runnerStatus === "registered_offline" ? "Runner registered, not online" : "Runner not registered";
    body = "Bring the protected runner online before expecting the first real action to execute.";
  } else if (readiness.canRunFirstAction) {
    href = "/actions";
    cta = "Run first action";
    title = "Waiting for first real Action Receipt";
    body = "Policy, runner, and verifier are ready. Route one real protected action to generate the first signed receipt.";
  }

  if (readiness.state === "live") {
    href = "/evidence";
    cta = "Open evidence";
    title = "First receipt matched";
    body = "A real matched Action Receipt exists. Evidence is ready for audit review.";
  }

  return (
    <div className="agent-setup-handoff">
      <div>
        <span>Next handoff</span>
        <strong>{title}</strong>
        <small>{body}</small>
        {policyDryRunResult ? (
          <small>
            Latest policy dry-run: {policyDryRunResult.status.replace(/_/g, " ")} · not recorded.
          </small>
        ) : null}
      </div>
      <Link href={href}>{cta}</Link>
      {readiness.canRunFirstAction && readiness.state !== "live" ? (
        <div className="agent-setup-handoff-code">
          <CopyableCode label="First receipt starter" value={snippet} />
        </div>
      ) : null}
    </div>
  );
}

function latestIntent(items: ActionIntentResponse[]): ActionIntentResponse | null {
  if (items.length === 0) return null;
  return [...items].sort((a, b) => {
    const left = new Date(a.created_at).getTime();
    const right = new Date(b.created_at).getTime();
    return (Number.isNaN(right) ? 0 : right) - (Number.isNaN(left) ? 0 : left);
  })[0] ?? null;
}

function intentTone(intent: ActionIntentResponse | null): "success" | "warning" | "danger" | "neutral" {
  if (!intent) return "neutral";
  if (intent.proof_status === "mismatched" || intent.status === "denied") return "danger";
  if (intent.proof_status === "matched" && intent.receipt_status === "generated") return "success";
  return "warning";
}

function intentLiveTitle(intent: ActionIntentResponse | null, firstReceiptMatched: boolean): string {
  if (firstReceiptMatched) return "First matched receipt generated";
  if (!intent) return "Waiting for first protected action";
  if (intent.status === "approval_pending") return "Action is waiting for approval";
  if (intent.status === "authorized") return "Action authorized, waiting for runner";
  if (intent.proof_status === "mismatched") return "Verification mismatch needs review";
  if (intent.proof_status === "not_verified") return "Action completed but is not verified";
  if (intent.receipt_status === "pending") return "Receipt generation is pending";
  return "Action received, proof still resolving";
}

function buildFirstReceiptSnippet(draft: SetupDraft, profile: AgentProfileResponse | null): string {
  const action = actionById(draft.primaryActionType);
  const agentId = profile?.id ?? "agent_profile_id";
  const resource = {
    id: "replace-with-real-record-id",
    system: draft.sourceOfRecord,
    type: action.resource,
  };
  const parameters = {
    requested_change: businessActionLabel(action),
    verifier: draft.verifierConnector,
  };
  return `import os
import zroky

zroky.init(
    api_key=os.environ["ZROKY_API_KEY"],
    project="current-project",
    agent_id="${agentId}",
)

decision = zroky.verified_action(
    contract_version="zroky.agent_action.v1",
    action_type="${draft.primaryActionType}",
    operation_kind="${action.verb}",
    environment="${draft.environment || "production"}",
    purpose={"summary": "${draft.workflowGoal.replace(/"/g, '\\"')}"},
    resource=${JSON.stringify(resource, null, 4)},
    parameters=${JSON.stringify(parameters, null, 4)},
    execution_request={
        "capability": "${action.verb}",
        "plan": {"summary": "${businessActionLabel(action).replace(/"/g, '\\"')}"},
    },
    trace_context={"agent_name": "${draft.agentName.replace(/"/g, '\\"')}"},
    raise_on_approval=False,
)

proof = zroky.await_action_proof(decision["action_id"])
print(proof["proof_status"], proof["receipt_status"])`;
}

function GoLiveStep({
  activeProfile,
  draft,
  firstActions,
  firstActionsLoading,
  firstReceiptAction,
  firstReceiptMatched,
  policyDryRunResult,
  readiness,
}: {
  activeProfile: AgentProfileResponse | null;
  draft: SetupDraft;
  firstActions: ActionIntentResponse[];
  firstActionsLoading: boolean;
  firstReceiptAction: ActionIntentResponse | null;
  firstReceiptMatched: boolean;
  policyDryRunResult: RuntimePolicyDryRunResponse | null;
  readiness: SetupReadiness;
}) {
  const action = latestIntent(firstActions);
  const tone = firstReceiptMatched ? "success" : intentTone(action);
  const snippet = buildFirstReceiptSnippet(draft, activeProfile);
  const actionHref = action ? `/actions?action_id=${encodeURIComponent(action.action_id)}` : "/actions";
  const evidenceHref = firstReceiptAction
    ? `/evidence?action_id=${encodeURIComponent(firstReceiptAction.action_id)}`
    : action
      ? `/evidence?action_id=${encodeURIComponent(action.action_id)}`
      : "/evidence";

  return (
    <section className="agent-setup-step-content">
      <StepHeader
        eyebrow="Step 5"
        title="Go Live"
        body="Route one real protected action through this agent. Zroky only marks it live after matched proof and a signed receipt."
      />

      <div className="agent-setup-simulation" data-tone={tone} aria-label="First protected action status">
        {firstReceiptMatched ? <CheckCircle2 aria-hidden="true" /> : <PlayCircle aria-hidden="true" />}
        <span>
          <strong>{intentLiveTitle(action, firstReceiptMatched)}</strong>
          <small>
            {firstReceiptMatched
              ? "A real action for this agent reached proof_status=matched and receipt_status=generated."
              : readiness.canRunFirstAction
                ? "Keep this page open after running the SDK snippet. The wizard polls action intents and receipts for this agent."
                : "Finish policy, runner, and verifier readiness before expecting a live receipt."}
          </small>
        </span>
      </div>

      <div className="agent-setup-readiness-grid" aria-label="Live readiness">
        <div data-done={readiness.canRunFirstAction ? "true" : "false"}>
          {readiness.canRunFirstAction ? <CheckCircle2 aria-hidden="true" /> : <ShieldAlert aria-hidden="true" />}
          <strong>Ready to run</strong>
          <span>{readiness.canRunFirstAction ? "Policy, runner, and verifier ready" : "Complete policy, runner, and verifier"}</span>
        </div>
        <div data-done={action ? "true" : "false"}>
          {action ? <CheckCircle2 aria-hidden="true" /> : <ShieldAlert aria-hidden="true" />}
          <strong>Action received</strong>
          <span>{action ? action.status.replace(/_/g, " ") : firstActionsLoading ? "polling" : "waiting"}</span>
        </div>
        <div data-done={action?.proof_status === "matched" ? "true" : "false"}>
          {action?.proof_status === "matched" ? <CheckCircle2 aria-hidden="true" /> : <ShieldAlert aria-hidden="true" />}
          <strong>Proof</strong>
          <span>{action?.proof_status?.replace(/_/g, " ") ?? "waiting"}</span>
        </div>
        <div data-done={firstReceiptMatched ? "true" : "false"}>
          {firstReceiptMatched ? <CheckCircle2 aria-hidden="true" /> : <ShieldAlert aria-hidden="true" />}
          <strong>Signed receipt</strong>
          <span>{firstReceiptMatched ? "matched receipt generated" : action?.receipt_status?.replace(/_/g, " ") ?? "waiting"}</span>
        </div>
      </div>

      {!action && !firstActionsLoading && readiness.canRunFirstAction && !firstReceiptMatched ? (
        <div className="agent-setup-intent-note" data-tone="yellow" aria-label="No protected action received yet">
          <KeyRound aria-hidden="true" />
          <span>
            <strong>No protected action received yet</strong>
            <small>
              Check that the starter snippet is running with the project API key, this agent_id, and the selected contract/action_type.
            </small>
            <Link href="/settings/keys" className="agent-setup-inline-link">
              Check project keys
            </Link>
          </span>
        </div>
      ) : null}

      {action?.status === "approval_pending" ? (
        <div className="agent-setup-intent-note" data-tone="yellow">
          <ShieldAlert aria-hidden="true" />
          <span>
            <strong>Approval required</strong>
            <small>The action is held at the policy gate. Approve it from Approvals, then the runner can execute.</small>
            <Link href="/approvals" className="agent-setup-inline-link">
              Open Approvals
            </Link>
          </span>
        </div>
      ) : null}

      {action?.proof_status === "mismatched" || action?.proof_status === "not_verified" ? (
        <div className="agent-setup-intent-note" data-tone={action.proof_status === "mismatched" ? "red" : "yellow"}>
          <ShieldAlert aria-hidden="true" />
          <span>
            <strong>{action.proof_status === "mismatched" ? "Proof mismatch" : "Not verified"}</strong>
            <small>
              {action.proof_status === "mismatched"
                ? "The system-of-record does not match the claimed action. Review the diff before going live."
                : "The connector could not verify this action yet. Check connector health or receipt status."}
            </small>
            <Link href={evidenceHref} className="agent-setup-inline-link">
              Open Evidence
            </Link>
          </span>
        </div>
      ) : null}

      <CopyableCode label="First protected action starter" value={snippet} />

      <div className="agent-setup-inline-actions">
        <DashboardButtonLink href={actionHref} variant="soft">
          Open Actions
        </DashboardButtonLink>
        <DashboardButtonLink href={evidenceHref} variant={firstReceiptMatched ? "primary" : "soft"}>
          Open Evidence
        </DashboardButtonLink>
        <DashboardButtonLink href={`/agents/${activeProfile?.id ?? ""}`} aria-disabled={!activeProfile || undefined} variant="soft">
          Agent home
        </DashboardButtonLink>
      </div>

      {policyDryRunResult ? (
        <p className="agent-setup-muted">
          Last policy dry-run: {policyDryRunResult.status.replace(/_/g, " ")} / not recorded.
        </p>
      ) : null}
    </section>
  );
}

function ProtectionPlanPreview({
  draft,
  registry,
  registryLoading,
  selectedAction,
  selectedActions,
  toolNames,
}: {
  draft: SetupDraft;
  registry: ToolRegistryResponse | undefined;
  registryLoading: boolean;
  selectedAction: ActionCatalogItem;
  selectedActions: ActionCatalogItem[];
  toolNames: string[];
}) {
  const tools = launchTools(registry);
  const actionLabel = businessActionLabel(selectedAction);
  const recommendedToolLabels = tools
    .filter((item) => item.recommended)
    .slice(0, 3)
    .map((item) => item.label);
  return (
    <aside className="agent-setup-preview agent-setup-plan-preview" aria-label="Protection plan">
      <div className="agent-setup-plan-head">
        <div>
          <span>Control Plan</span>
          <strong>{draft.agentName} control path is being planned before production enforcement.</strong>
          <small>{draft.productName}</small>
        </div>
        <span className="alert-cat-badge badge-green">{selectedAction.riskClass}</span>
      </div>
      <div className="agent-setup-plan-grid">
        <div>
          <span>Agent</span>
          <strong>{draft.agentName}</strong>
          <small>{draft.ownerTeam}</small>
        </div>
        <div>
          <span>Protected action</span>
          <strong>{actionLabel}</strong>
          <small>{selectedAction.sourceSystem}</small>
        </div>
        <div>
          <span>Control</span>
          <strong>High-risk changes should require approval</strong>
          <small>{approvalPlanLabel(draft.approvalSurface)}; unknown actions deny by default through the project runtime policy.</small>
        </div>
        <div>
          <span>Execution</span>
          <strong>{runnerModeLabel(draft.runnerMode)}</strong>
          <small>{runtimeLabel(draft.runtimePath)}</small>
        </div>
        <div>
          <span>Proof</span>
          <strong>{draft.sourceOfRecord}</strong>
          <small>{draft.proofAssertion}</small>
        </div>
        <div>
          <span>Receipt</span>
          <strong>Signed Action Receipt</strong>
          <small>Generated after the verifier confirms the source-of-record result.</small>
        </div>
      </div>
      <div className="agent-setup-preview-section">
        <span>Planned protected path</span>
        <div className="agent-setup-plan-path">
          <div>
            <em>1</em>
            <span>
              <strong>Agent proposes</strong>
              <small>{actionLabel}</small>
            </span>
          </div>
          <div>
            <em>2</em>
            <span>
              <strong>Zroky should control</strong>
              <small>{approvalPlanLabel(draft.approvalSurface)} when policy says hold</small>
            </span>
          </div>
          <div>
            <em>3</em>
            <span>
              <strong>Runner executes</strong>
              <small>No protected credential is returned to the agent</small>
            </span>
          </div>
          <div>
            <em>4</em>
            <span>
              <strong>Verifier checks</strong>
              <small>{draft.sourceOfRecord}</small>
            </span>
          </div>
          <div>
            <em>5</em>
            <span>
              <strong>Receipt should be generated</strong>
              <small>Evidence pack links policy, runner, verifier, and outcome</small>
            </span>
          </div>
        </div>
      </div>
      <div className="agent-setup-preview-section agent-setup-plan-coverage">
        <span>Coverage</span>
        <p>
          {selectedActions.map((item) => businessActionLabel(item)).join(", ")}
        </p>
        <div className="agent-setup-chip-row" aria-label="Protection coverage">
          <span>{selectedActions.length} protected action{selectedActions.length === 1 ? "" : "s"}</span>
          <span>{toolNames.length} tool call{toolNames.length === 1 ? "" : "s"}</span>
          <span>{registryLoading ? "Loading tools" : `${tools.filter((item) => item.status === "available").length} launch tools`}</span>
          <span>{recommendedToolLabels.join(", ") || "Recommendations pending"}</span>
        </div>
      </div>
      <AdvancedDetails title="Advanced technical preview">
        <div className="agent-setup-preview-grid">
          <div>
            <span>Action ID</span>
            <strong>{actionContractId(draft)}</strong>
          </div>
          <div>
            <span>Intent digest</span>
            <strong>{intentDigest(draft)}</strong>
          </div>
          <div>
            <span>Verification</span>
            <strong>{verificationLevel(draft)} / {connectorLabel(draft.verifierConnector)}</strong>
          </div>
          <div>
            <span>Assurance</span>
            <strong>{assuranceLevel(draft)}</strong>
          </div>
        </div>
      </AdvancedDetails>
    </aside>
  );
}

function StepHeader({
  body,
  eyebrow,
  title,
}: {
  body: string;
  eyebrow: string;
  title: string;
}) {
  return (
    <header className="agent-setup-section-head">
      <span>{eyebrow}</span>
      <h2>{title}</h2>
      <p>{body}</p>
    </header>
  );
}

function AdvancedDetails({
  children,
  title,
}: {
  children: ReactNode;
  title: string;
}) {
  return (
    <details className="agent-setup-advanced">
      <summary>{title}</summary>
      <div>{children}</div>
    </details>
  );
}

function CopyableCode({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  const [copied, setCopied] = useState(false);

  async function copyCode() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="agent-setup-code-panel">
      <div className="agent-setup-code-head">
        <span>{label}</span>
        <button type="button" onClick={copyCode} aria-label={`Copy ${label}`}>
          {copied ? <Check aria-hidden="true" /> : <ClipboardCheck aria-hidden="true" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre>{value}</pre>
    </div>
  );
}

function SelectionGrid({
  label,
  onToggle,
  selected,
  values,
}: {
  label: string;
  onToggle: (value: string) => void;
  selected: string[];
  values: string[];
}) {
  return (
    <div className="agent-setup-choice-block">
      <span>{label}</span>
      <div className="agent-setup-choice-grid">
        {values.map((value) => {
          const active = selected.includes(value);
          return (
            <button
              key={value}
              type="button"
              className={active ? "is-selected" : ""}
              onClick={() => onToggle(value)}
            >
              {active ? <Check aria-hidden="true" /> : null}
              {value}
            </button>
          );
        })}
      </div>
    </div>
  );
}
