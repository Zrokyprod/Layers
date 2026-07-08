"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import type { ComponentType } from "react";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  CheckCircle2,
  Copy,
  Database,
  Globe,
  KeyRound,
  Landmark,
  PlayCircle,
  Receipt,
  ShieldCheck,
  Users,
} from "lucide-react";
import {
  SiFresh,
  SiGithub,
  SiHubspot,
  SiIntercom,
  SiPostgresql,
  SiQuickbooks,
  SiSalesforce,
  SiShopify,
  SiSlack,
  SiStripe,
  SiZendesk,
} from "react-icons/si";

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
import {
  CONNECTOR_LABELS,
  DEFAULT_DEVOPS_CAPABILITIES,
  DEFAULT_DEVOPS_SYSTEM_ID,
  DEFAULT_ECOMMERCE_CAPABILITIES,
  DEFAULT_ECOMMERCE_SYSTEM_ID,
  DEFAULT_FINANCE_CAPABILITIES,
  DEFAULT_FINANCE_SYSTEM_ID,
  DEFAULT_PACK_ID,
  DEFAULT_SUPPORT_CAPABILITIES,
  DEFAULT_SUPPORT_ENGINE_ID,
  DEVOPS_CAPABILITIES,
  DEVOPS_SYSTEMS,
  ECOMMERCE_CAPABILITIES,
  ECOMMERCE_SYSTEMS,
  FINANCE_CAPABILITIES,
  FINANCE_SYSTEMS,
  LAUNCH_READY_PACK_IDS,
  PACK_SHORT_COPY,
  PRIMARY_PACK_IDS,
  SUPPORT_CAPABILITIES,
  SUPPORT_ENGINES,
  devopsCapabilityById,
  devopsConnectorsFor,
  devopsContractsFor,
  ecommerceCapabilityById,
  ecommerceConnectorsFor,
  ecommerceContractsFor,
  financeCapabilityById,
  financeConnectorsFor,
  financeContractsFor,
  packSort,
  supportCapabilityById,
  supportConnectorsFor,
  supportContractsFor,
  type DevopsCapabilityId,
  type EcommerceCapabilityId,
  type FinanceCapabilityId,
  type SupportCapabilityId,
} from "./pack-config";

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

type SystemLogoDef = {
  Icon: ComponentType<{ size?: number; className?: string }>;
  color: string;
};

const SYSTEM_LOGOS: Record<string, SystemLogoDef> = {
  "support:zendesk": { Icon: SiZendesk, color: "#03363D" },
  "support:intercom": { Icon: SiIntercom, color: "#1F8DED" },
  "support:freshdesk": { Icon: SiFresh, color: "#25C16F" },
  "support:hubspot": { Icon: SiHubspot, color: "#FF7A59" },
  "support:salesforce": { Icon: SiSalesforce, color: "#00A1E0" },
  "support:custom": { Icon: Globe, color: "#2F5F66" },
  "finance:netsuite": { Icon: Landmark, color: "#1F6FEB" },
  "finance:stripe": { Icon: SiStripe, color: "#635BFF" },
  "finance:generic": { Icon: Receipt, color: "#2F5F66" },
  "finance:postgres": { Icon: SiPostgresql, color: "#4169E1" },
  "finance:quickbooks": { Icon: SiQuickbooks, color: "#2CA01C" },
  "devops:github": { Icon: SiGithub, color: "#181717" },
  "devops:generic": { Icon: Database, color: "#2F5F66" },
  "devops:slack": { Icon: SiSlack, color: "#4A154B" },
  "ecommerce:shopify": { Icon: SiShopify, color: "#95BF47" },
  "ecommerce:order": { Icon: Receipt, color: "#2F5F66" },
  "ecommerce:inventory": { Icon: Database, color: "#2F5F66" },
  "ecommerce:generic": { Icon: Globe, color: "#2F5F66" },
};
const FALLBACK_SYSTEM_LOGO: SystemLogoDef = { Icon: Users, color: "#2F5F66" };

function SystemCardTitle({ iconKey, label }: { iconKey: string; label: string }) {
  const { Icon, color } = SYSTEM_LOGOS[iconKey] ?? FALLBACK_SYSTEM_LOGO;
  return (
    <strong className="system-card-title">
      <span
        className="system-logo-badge"
        style={{ ["--system-logo-color" as string]: color }}
        aria-hidden="true"
      >
        <Icon size={15} />
      </span>
      <span>{label}</span>
    </strong>
  );
}

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

class AgentSetupEnforcementError extends Error {
  profile: AgentProfileResponse;

  constructor(profile: AgentProfileResponse, message: string) {
    super(message);
    this.name = "AgentSetupEnforcementError";
    this.profile = profile;
  }
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

function agentProfileMatchesSetupRequest(profile: AgentProfileResponse, agentId: string, agentName: string) {
  const id = agentId.trim();
  if (id) return profile.id === id;

  const name = agentName.trim().toLowerCase();
  if (!name) return true;
  return profile.display_name.trim().toLowerCase() === name || profile.slug.trim().toLowerCase() === name;
}

export default function ProtectedAgentSetupPage() {
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();

  const requestedAgentId = (searchParams.get("agentId") ?? "").trim();
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
  const existingProfile = profilesQuery.data?.items?.find((item) => (
    agentProfileMatchesSetupRequest(item, requestedAgentId, agentName)
  )) ?? null;
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
  const selectedPackLaunchReady = Boolean(selectedPack && LAUNCH_READY_PACK_IDS.has(selectedPack.id));
  const selectedPackRequestAccess = Boolean(selectedPack && !selectedPackLaunchReady);
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
      if (connectedProfile) {
        return enforceAgentProfile(connectedProfile.id);
      }
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
      try {
        return await enforceAgentProfile(created.id);
      } catch (err) {
        const detail = err instanceof Error ? err.message : "Safe defaults could not be enforced.";
        throw new AgentSetupEnforcementError(
          created,
          `Agent profile was created, but safe defaults were not enforced. Retry from this profile before running production actions. ${detail}`,
        );
      }
    },
    onSuccess: (created) => {
      setProfile(created);
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["agents", "profiles"] });
      void queryClient.invalidateQueries({ queryKey: ["agent-setup", "profiles"] });
    },
    onError: (err) => {
      if (err instanceof AgentSetupEnforcementError) {
        setProfile(err.profile);
        setError(err.message);
        void queryClient.invalidateQueries({ queryKey: ["agents", "profiles"] });
        void queryClient.invalidateQueries({ queryKey: ["agent-setup", "profiles"] });
        return;
      }
      setError(err instanceof Error ? err.message : "Could not create the agent.");
    },
  });

  const installPackMutation = useMutation({
    mutationFn: async () => {
      if (!selectedPack) {
        throw new Error("Protected action templates are still loading.");
      }
      if (!selectedPackLaunchReady) {
        throw new Error("This action pack is available by request during launch.");
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
                <small>Choose the workflows Zroky should govern.</small>
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
                      {!LAUNCH_READY_PACK_IDS.has(pack.id) ? <em>Request access</em> : null}
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
                                <SystemCardTitle iconKey={`support:${engine.id}`} label={engine.label} />
                                <span>{engine.summary}</span>
                              </button>
                            ))}
                          </div>
                        </div>
                        <div>
                          <span className="dashboard-eyebrow">What support risk should Zroky govern?</span>
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
                                <SystemCardTitle iconKey={`finance:${system.id}`} label={system.label} />
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
                                <SystemCardTitle iconKey={`devops:${system.id}`} label={system.label} />
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
                                <SystemCardTitle iconKey={`ecommerce:${system.id}`} label={system.label} />
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
                    ) : selectedPackRequestAccess ? (
                      <div className="agent-runtime-ready">
                        <Users aria-hidden="true" />
                        <div>
                          <strong>Request access for {selectedPack.display_name.replace(" operations", "")}</strong>
                          <span>We keep this pack available, but launch installs are reviewed before production use.</span>
                        </div>
                      </div>
                    ) : (
                      <div className="agent-pack-actions">
                        <DashboardButton
                          icon={<ShieldCheck />}
                          type="button"
                          variant="primary"
                          loading={installPackMutation.isPending}
                          disabled={installPackMutation.isPending || !selectedPack || !selectedPackLaunchReady}
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
