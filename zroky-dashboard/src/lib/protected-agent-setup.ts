export type ProtectedAgentTemplate = {
  id: string;
  label: string;
  agentName: string;
  workflowId: string;
  toolName: string;
  sampleInput: string;
  sampleArgs: string;
  mandate: string;
  allowedActions: string[];
  holdConditions: string[];
  systemOfRecord: string;
  requiredEvidence: string[];
  connectorInputs: string[];
  proofStatus: "packaged_full_proof" | "custom_connector_required";
  liveSmokeScenario?: "refund" | "customer-record";
};

export const protectedAgentTemplates: ProtectedAgentTemplate[] = [
  {
    id: "refund",
    label: "Refund / payment",
    agentName: "refund-ops-agent",
    workflowId: "refund_guardrail",
    toolName: "issue_refund",
    sampleInput: "refund duplicate charge for order ord_123",
    sampleArgs: `{
        orderId: "ord_123",
        amountUsd: 250,
        reason: "duplicate_charge",
      }`,
    mandate: "Issue bounded refunds only when order, customer, amount, and reason are present.",
    allowedActions: ["lookup order", "hold refund for approval", "issue refund under mandate"],
    holdConditions: ["refund over approved amount", "missing order owner", "duplicate refund risk"],
    systemOfRecord: "payment ledger refund record",
    requiredEvidence: ["refund transaction id", "ledger status", "amount/currency match"],
    connectorInputs: [
      "ledger/refund API base URL",
      "read-scoped ledger bearer token",
      "safe refund id",
      "amount, currency, and status fields",
    ],
    proofStatus: "packaged_full_proof",
    liveSmokeScenario: "refund",
  },
  {
    id: "devops",
    label: "DevOps / release",
    agentName: "release-ops-agent",
    workflowId: "release_guardrail",
    toolName: "deploy_change",
    sampleInput: "deploy service api-gateway to production",
    sampleArgs: `{
        service: "api-gateway",
        environment: "production",
        changeId: "chg_742",
      }`,
    mandate: "Deploy approved changes only when the change ticket, checks, and rollback path exist.",
    allowedActions: ["read deployment status", "run approved release", "pause unsafe rollout"],
    holdConditions: ["production deploy without approval", "failing checks", "no rollback command"],
    systemOfRecord: "CI deployment and incident status",
    requiredEvidence: ["deployment id", "commit sha", "post-deploy health check"],
    connectorInputs: [
      "deployment or CI run API",
      "service, environment, and change id",
      "post-deploy health endpoint",
      "rollback or cancel action",
    ],
    proofStatus: "custom_connector_required",
  },
  {
    id: "crm",
    label: "CRM / data",
    agentName: "crm-record-agent",
    workflowId: "crm_mutation_guardrail",
    toolName: "update_customer_record",
    sampleInput: "update customer billing contact for acct_902",
    sampleArgs: `{
        accountId: "acct_902",
        field: "billing_contact",
        newValue: "ops@example.com",
      }`,
    mandate: "Modify customer records only with account id, source proof, and field-level scope.",
    allowedActions: ["read customer record", "update approved fields", "create audit note"],
    holdConditions: ["identity field change", "bulk update", "missing source proof"],
    systemOfRecord: "CRM account record",
    requiredEvidence: ["record id", "field diff", "CRM audit entry"],
    connectorInputs: [
      "CRM/customer API base URL",
      "read-scoped CRM bearer token",
      "safe customer or account id",
      "fields to compare after mutation",
    ],
    proofStatus: "packaged_full_proof",
    liveSmokeScenario: "customer-record",
  },
  {
    id: "outreach",
    label: "Lifecycle / outreach",
    agentName: "lifecycle-outreach-agent",
    workflowId: "outreach_guardrail",
    toolName: "send_customer_email",
    sampleInput: "send renewal notice to account acct_902",
    sampleArgs: `{
        accountId: "acct_902",
        templateId: "renewal_notice_v2",
        recipient: "ops@example.com",
      }`,
    mandate: "Send customer outreach only to eligible recipients with approved templates.",
    allowedActions: ["check consent", "send approved template", "record delivery result"],
    holdConditions: ["missing consent", "manual freeform body", "large recipient segment"],
    systemOfRecord: "email provider delivery event",
    requiredEvidence: ["message id", "recipient status", "bounce/complaint check"],
    connectorInputs: [
      "email provider event API",
      "message id or campaign id",
      "delivery, bounce, and complaint endpoints",
      "consent or suppression-list record",
    ],
    proofStatus: "custom_connector_required",
  },
  {
    id: "procurement",
    label: "Procurement / spend",
    agentName: "procurement-agent",
    workflowId: "procurement_guardrail",
    toolName: "create_purchase_order",
    sampleInput: "create PO for approved vendor security scan",
    sampleArgs: `{
        vendorId: "ven_118",
        amountUsd: 4200,
        budgetCode: "security-tools",
      }`,
    mandate: "Create spend commitments only inside approved vendor, budget, and amount limits.",
    allowedActions: ["validate vendor", "create purchase order", "route for approval"],
    holdConditions: ["new vendor", "budget mismatch", "amount over mandate"],
    systemOfRecord: "ERP purchase order",
    requiredEvidence: ["purchase order id", "approval status", "budget allocation"],
    connectorInputs: [
      "ERP or purchase-order API",
      "vendor and budget record id",
      "approval status endpoint",
      "amount, currency, and budget fields",
    ],
    proofStatus: "custom_connector_required",
  },
];

export const pilotHandoffSteps = [
  "Create project key",
  "Copy mandate and SDK wrapper",
  "Connect system of record",
  "Run connector preflight",
  "Run full proof command",
  "Export evidence pack",
];

export const pilotHandoffCriteria = [
  "captured_call_linked",
  "unsafe_action_stopped",
  "connector_configured",
  "connector_health_verified",
  "real_connector_ready",
  "saved_test_endpoint_used",
  "matched_outcome_shown",
  "evidence_hash_visible",
  "evidence_json_exported",
  "not_verified_when_missing",
  "evidence_pack_passed",
  "secrets_redacted",
];

export function humanizeIntent(value: string | null) {
  if (!value) return null;
  return value
    .split(/[-_]/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function buildMandateStarter(template: ProtectedAgentTemplate) {
  return `agent: ${template.agentName}
workflow: ${template.workflowId}
mandate: ${template.mandate}
allowed_actions:
${template.allowedActions.map((action) => `  - ${action}`).join("\n")}
hold_for_approval:
${template.holdConditions.map((condition) => `  - ${condition}`).join("\n")}
block:
  - missing required identifiers
  - no trusted system-of-record path
  - repeat fail or not_verified outcome
outcome_verification:
  system_of_record: ${template.systemOfRecord}
  required_evidence:
${template.requiredEvidence.map((evidence) => `    - ${evidence}`).join("\n")}
status_contract:
  pass: outcome matched system of record
  warn: action allowed but evidence incomplete
  fail: mandate breach or wrong outcome
  not_verified: trusted proof missing`;
}

export function buildProtectedAgentSnippet(template: ProtectedAgentTemplate, projectId: string) {
  return `import { init, traceRun, captureToolCall } from "@zroky-ai/sdk";

init({
  projectId: "${projectId}",
  apiKey: process.env.ZROKY_API_KEY,
  agentName: "${template.agentName}",
  workflowId: "${template.workflowId}",
  environment: "production",
});

await traceRun(
  { name: "${template.workflowId}", userInput: "${template.sampleInput}" },
  async () => {
    await captureToolCall({
      name: "${template.toolName}",
      args: ${template.sampleArgs},
      result: {
        status: "not_verified",
        systemOfRecord: "${template.systemOfRecord}",
      },
      policy: {
        mandate: "${template.workflowId}",
        failClosed: true,
        decision: "hold_if_over_mandate",
      },
    });

    return "submitted_for_outcome_verification";
  },
);`;
}

export function proofReadinessLabel(template: ProtectedAgentTemplate) {
  return template.proofStatus === "packaged_full_proof"
    ? "Packaged full proof runner"
    : "Custom connector required";
}

export function proofReadinessDetail(template: ProtectedAgentTemplate) {
  if (template.liveSmokeScenario === "refund") {
    return "Refund and payment agents can use the packaged ledger/refund preflight and full proof runner.";
  }
  if (template.liveSmokeScenario === "customer-record") {
    return "CRM and data agents can use the packaged customer-record preflight and full proof runner.";
  }
  return `This template has mandate and SDK capture coverage. Add a connector that reads ${template.systemOfRecord} before calling the pilot verified.`;
}

export function buildLiveSmokeCommand(template: ProtectedAgentTemplate) {
  if (template.liveSmokeScenario === "refund") {
    return [
      "python scripts/run_design_partner_install_kit.py",
      "--scenario refund",
      "--api-base-url https://api.zroky.ai",
      "--api-key <zroky_api_key>",
      "--ledger-base-url https://ledger.example.com/api",
      "--ledger-bearer-token <ledger_token>",
      "--refund-id <refund_id>",
      "--json",
      "--write-summary artifacts/design-partner-refund-live-summary.json",
      "--write-evidence artifacts/design-partner-refund-live-evidence.json",
    ].join(" ");
  }

  if (template.liveSmokeScenario === "customer-record") {
    return [
      "python scripts/run_design_partner_install_kit.py",
      "--scenario customer-record",
      "--api-base-url https://api.zroky.ai",
      "--api-key <zroky_api_key>",
      "--crm-base-url https://crm.example.com/api",
      "--crm-bearer-token <crm_token>",
      "--customer-id <customer_id>",
      "--json",
      "--write-summary artifacts/design-partner-crm-live-summary.json",
      "--write-evidence artifacts/design-partner-crm-live-evidence.json",
    ].join(" ");
  }

  return null;
}
