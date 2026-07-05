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
  listActionIntents,
  listProjectApiKeys,
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
const CONTROL_LOOP_STEPS = ["Propose", "Policy", "Approval", "Execution", "Verification", "Receipt"];
const DEFAULT_RUNTIME_KEY_NAME = "Protected agent runtime key";
type SetupStep = "key" | "connect" | "run" | "next";

function configuredApiBaseUrl() {
  return (process.env.NEXT_PUBLIC_ZROKY_API_BASE_URL ?? "https://api.zroky.com").replace(/\/+$/, "");
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

function stepStateLabel(activeStep: SetupStep, step: SetupStep, done: boolean) {
  if (done) return "Done";
  if (activeStep === step) return "Now";
  return "Locked";
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
  const apiBaseUrl = configuredApiBaseUrl();

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

  const firstActionQuery = useQuery({
    queryKey: ["agent-setup", "first-actions", profile?.id],
    queryFn: ({ signal }) => listActionIntents({ agent_id: profile?.id ?? null, limit: 5 }, signal),
    enabled: Boolean(profile?.id),
    refetchInterval: 5_000,
  });
  const firstReceiptQuery = useQuery({
    queryKey: ["agent-setup", "first-receipt", profile?.id],
    queryFn: ({ signal }) =>
      listActionIntents(
        { agent_id: profile?.id ?? null, proof_status: "matched", receipt_status: "generated", limit: 1 },
        signal,
      ),
    enabled: Boolean(profile?.id),
    refetchInterval: 15_000,
  });

  const created = Boolean(profile);
  const firstAction = firstActionQuery.data?.items[0] ?? null;
  const live = (firstReceiptQuery.data?.items.length ?? 0) > 0;
  const activeStep: SetupStep = !hasRuntimeKey ? "key" : !created ? "connect" : !live ? "run" : "next";
  const actionStatus = firstAction
    ? firstAction.status.replace(/_/g, " ")
    : firstActionQuery.isFetching
      ? "polling"
      : "waiting";

  const runtimeEnvSnippet = `pip install zroky
export ZROKY_API_KEY="${newRuntimeKey?.api_key ?? "zk_live_..."}"
export ZROKY_PROJECT_ID="${projectId || "proj_..."}"
export ZROKY_INGEST_URL="${apiBaseUrl}"

zroky doctor
zroky ingest --test`;
  const firstProtectedActionSnippet = `import zroky

zroky.init()

receipt = zroky.protect(
    action="customer.access.grant",
    params={"customer_id": "cus_123", "role": "viewer"},
    run=lambda: grant_access("cus_123", "viewer"),
)

print(receipt.status)`;

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
        copy: "Zroky is now controlling and verifying this agent's protected actions. Tune the policy or add a verifier when you want tighter control.",
        pill: "Live",
      }
    : created
      ? {
          tone: "warning" as const,
          title: "Waiting for the first protected action",
          copy: "Run your agent with the snippet below. Zroky captures and verifies the first real action automatically, with no upfront action list to declare.",
          pill: "Capturing",
        }
      : {
          tone: "neutral" as const,
          title: "Protect an agent",
          copy: "Name the agent and install the SDK. Zroky applies a safe default policy and verifies real actions. Configure policies, verifiers, and approvals later from real captured actions.",
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
            <DashboardButtonLink href={`/agents/${profile?.id ?? ""}`} variant="soft">
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
                <small>Create the runtime key your agent uses to call Zroky.</small>
              </div>
              <em>{stepStateLabel(activeStep, "key", hasRuntimeKey)}</em>
            </div>

            {projectQuery.error ? (
              <p className="agent-setup-status is-error">Project context did not load. Refresh before creating a key.</p>
            ) : newRuntimeKey ? (
              <div className="agent-runtime-key-reveal">
                <div className="agent-runtime-secret">
                  <span className="mono">{newRuntimeKey.api_key}</span>
                  <button type="button" onClick={() => void copyRuntimeKey(newRuntimeKey.api_key)}>
                    <Copy size={13} aria-hidden="true" />
                    {runtimeKeyCopied ? "Copied" : "Copy key"}
                  </button>
                </div>
                <CopyableCode label="Runtime environment" value={runtimeEnvSnippet} />
                <p className="agent-setup-muted">This secret is shown once. Store it in the agent runtime before closing the page.</p>
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
                <DashboardButtonLink href="/settings/keys" icon={<KeyRound />} variant="soft">
                  Manage keys
                </DashboardButtonLink>
              </div>
            ) : (
              <div className="agent-runtime-create">
                <p className="agent-setup-muted">
                  Keys authenticate SDK and verified-action requests. They do not grant model-provider access.
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
                <small>Name the agent and add one SDK wrapper. No upfront action or system list.</small>
              </div>
              <em>{stepStateLabel(activeStep, "connect", created)}</em>
            </div>

            {created ? (
              <div className="agent-quickstart-connected">
                <p className="agent-setup-muted">
                  <strong>{profile?.display_name}</strong> is protected with the safe default policy.
                </p>
                <div className="agent-profile-summary">
                  <span>{framework}</span>
                  <span>{environment}</span>
                  <span>Fail-closed default</span>
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
                <p className="agent-setup-muted">
                  Safe default: unknown actions are denied, risky actions are held for approval, everything is recorded.
                </p>
                <DashboardButton
                  icon={<ShieldCheck />}
                  type="submit"
                  variant="primary"
                  loading={createMutation.isPending}
                  disabled={!hasRuntimeKey || createMutation.isPending}
                >
                  {hasRuntimeKey ? "Create & enable protection" : "Create project key first"}
                </DashboardButton>
              </form>
            )}
          </div>

          {/* 3 - Run */}
          <div
            className="agent-quickstart-card"
            data-step="run"
            data-active={activeStep === "run" ? "true" : "false"}
            data-done={live ? "true" : "false"}
            aria-disabled={!created || undefined}
          >
            <div className="agent-quickstart-card-head">
              <span>{live ? <CheckCircle2 aria-hidden="true" size={16} /> : "03"}</span>
              <div>
                <strong>Run</strong>
                <small>Run the checks, then send one protected action from your agent runtime.</small>
              </div>
              <em>{stepStateLabel(activeStep, "run", live)}</em>
            </div>
            {created ? (
              <div className="agent-run-snippets">
                <CopyableCode label="CLI smoke test" value={runtimeEnvSnippet} />
                <CopyableCode label="Protected action" value={firstProtectedActionSnippet} />
              </div>
            ) : (
              <div className="agent-run-locked">
                <strong>Create the agent profile first.</strong>
                <span>The install commands appear here after the runtime key and agent profile are ready.</span>
              </div>
            )}
            <div className="agent-setup-readiness-grid" aria-label="Live capture status">
              <div data-done={created ? "true" : "false"}>
                {created ? <CheckCircle2 aria-hidden="true" /> : <PlayCircle aria-hidden="true" />}
                <strong>SDK ready</strong>
                <span>{created ? "install the snippet" : "create agent first"}</span>
              </div>
              <div data-done={firstAction ? "true" : "false"}>
                {firstAction ? <CheckCircle2 aria-hidden="true" /> : <PlayCircle aria-hidden="true" />}
                <strong>Action received</strong>
                <span>{created ? actionStatus : "waiting for SDK run"}</span>
              </div>
              <div data-done={live ? "true" : "false"}>
                {live ? <CheckCircle2 aria-hidden="true" /> : <PlayCircle aria-hidden="true" />}
                <strong>Signed receipt</strong>
                <span>{live ? "generated" : firstAction?.receipt_status?.replace(/_/g, " ") ?? "waiting for proof"}</span>
              </div>
            </div>
          </div>

          {/* 4 - Live / what's next */}
          <div
            className="agent-quickstart-card"
            data-step="live"
            data-active={activeStep === "next" ? "true" : "false"}
            data-done={live ? "true" : "false"}
            aria-disabled={!live || undefined}
          >
            <div className="agent-quickstart-card-head">
              <span>{live ? <CheckCircle2 aria-hidden="true" size={16} /> : "04"}</span>
              <div>
                <strong>{live ? "You're live" : "What's next"}</strong>
                <small>
                  {live
                    ? "This agent is controlled and verified. Configure tighter control on real data."
                    : "After the first receipt, tune control on the actions Zroky actually saw."}
                </small>
              </div>
              <em>{stepStateLabel(activeStep, "next", live)}</em>
            </div>
            {!live ? (
              <div className="agent-next-hint">
                <span>Available after the first receipt</span>
                <strong>Use real captured actions to tune policy, verifier coverage, and evidence.</strong>
              </div>
            ) : null}
            <div className="agent-setup-inline-actions agent-next-actions" data-locked={!live ? "true" : "false"}>
              <DashboardButtonLink href="/policies" variant={live ? "primary" : "soft"} aria-disabled={!live || undefined}>
                Set a policy
              </DashboardButtonLink>
              <DashboardButtonLink href="/integrations" variant="soft" aria-disabled={!live || undefined}>
                Connect a verifier
              </DashboardButtonLink>
              <DashboardButtonLink href="/actions" variant="soft" aria-disabled={!live || undefined}>
                Actions
              </DashboardButtonLink>
            </div>
          </div>
        </div>

        <div className="agent-control-loop-strip" aria-label="Zroky control loop">
          <div>
            <span>Control loop after first run</span>
            <strong>Every protected action moves through the same proof path.</strong>
          </div>
          <ol>
            {CONTROL_LOOP_STEPS.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        </div>
      </section>
    </div>
  );
}
