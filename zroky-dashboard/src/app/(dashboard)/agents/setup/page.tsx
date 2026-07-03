"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  CheckCircle2,
  Copy,
  KeyRound,
  PlayCircle,
  Rocket,
  ShieldCheck,
} from "lucide-react";

import { DashboardButton, DashboardButtonLink } from "@/components/dashboard-button";
import { DashboardVerdictHero } from "@/components/dashboard-scaffold";
import {
  createAgentProfile,
  enforceAgentProfile,
  listActionIntents,
  type AgentProfileResponse,
} from "@/lib/api";
import { buildProtectedAgentSnippet, protectedAgentTemplates } from "@/lib/protected-agent-setup";

const FRAMEWORKS = [
  "OpenAI Agents SDK",
  "LangGraph",
  "CrewAI",
  "AutoGen",
  "MCP client",
  "Custom agent runtime",
];

const ENVIRONMENTS = ["production", "staging", "development"];

function CopyableCode({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard unavailable — the snippet is still selectable
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

export default function ProtectedAgentSetupPage() {
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();

  const [agentName, setAgentName] = useState(() => (searchParams.get("agentName") ?? "").trim());
  const [framework, setFramework] = useState(FRAMEWORKS[0]);
  const [environment, setEnvironment] = useState(ENVIRONMENTS[0]);
  const [profile, setProfile] = useState<AgentProfileResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

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
        tool_names: [],
        allowed_action_types: [],
        blocked_action_types: [],
        risk_limits: {
          auto_allow_amount_usd: 0,
          approval_required_above_usd: 500,
          deny_above_usd: 5000,
          approval_ttl_minutes: 60,
        },
        verification_connectors: [],
        metadata: {},
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
  const actionStatus = firstAction
    ? firstAction.status.replace(/_/g, " ")
    : firstActionQuery.isFetching
      ? "polling"
      : "waiting";

  const snippet = useMemo(
    () =>
      buildProtectedAgentSnippet(protectedAgentTemplates[0], "current-project", {
        agentId: profile?.id ?? "agent_profile_id",
      }),
    [profile?.id],
  );

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
          copy: "Run your agent with the snippet below. Zroky captures and verifies the first real action automatically — no action list to declare.",
          pill: "Capturing",
        }
      : {
          tone: "neutral" as const,
          title: "Protect an agent",
          copy: "Name the agent and install the SDK. Zroky applies a safe default policy and verifies real actions — configure the details later, on real data.",
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
          {/* 1 — Connect */}
          <div className="agent-quickstart-card" data-step="connect" data-done={created ? "true" : "false"}>
            <div className="agent-quickstart-card-head">
              <span>{created ? <CheckCircle2 aria-hidden="true" size={16} /> : "01"}</span>
              <div>
                <strong>Connect</strong>
                <small>Name the agent and add one SDK wrapper. No upfront action or system list.</small>
              </div>
            </div>

            {created ? (
              <div className="agent-quickstart-connected">
                <p className="agent-setup-muted">
                  <strong>{profile?.display_name}</strong> is protected with the safe default policy.
                </p>
                <CopyableCode label="Minimal SDK starter" value={snippet} />
                <div className="agent-setup-inline-actions">
                  <DashboardButtonLink href="/settings/keys" icon={<KeyRound />} variant="primary">
                    Project keys
                  </DashboardButtonLink>
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
                      placeholder="Operations Agent"
                      aria-label="Agent name"
                    />
                  </label>
                  <label className="agent-setup-field">
                    <span>Framework</span>
                    <select value={framework} onChange={(event) => setFramework(event.target.value)} aria-label="Framework">
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
                >
                  Create &amp; enable protection
                </DashboardButton>
              </form>
            )}
          </div>

          {/* 2 — Run */}
          <div className="agent-quickstart-card" data-step="run" data-done={live ? "true" : "false"} aria-disabled={!created}>
            <div className="agent-quickstart-card-head">
              <span>{live ? <CheckCircle2 aria-hidden="true" size={16} /> : "02"}</span>
              <div>
                <strong>Run</strong>
                <small>Run your agent with the snippet. Zroky captures and verifies the first real action.</small>
              </div>
            </div>
            {created ? (
              <div className="agent-setup-readiness-grid" aria-label="Live capture status">
                <div data-done={firstAction ? "true" : "false"}>
                  {firstAction ? <CheckCircle2 aria-hidden="true" /> : <PlayCircle aria-hidden="true" />}
                  <strong>Action received</strong>
                  <span>{actionStatus}</span>
                </div>
                <div data-done={firstAction?.proof_status === "matched" ? "true" : "false"}>
                  {firstAction?.proof_status === "matched" ? <CheckCircle2 aria-hidden="true" /> : <PlayCircle aria-hidden="true" />}
                  <strong>Proof</strong>
                  <span>{firstAction?.proof_status?.replace(/_/g, " ") ?? "waiting"}</span>
                </div>
                <div data-done={live ? "true" : "false"}>
                  {live ? <CheckCircle2 aria-hidden="true" /> : <PlayCircle aria-hidden="true" />}
                  <strong>Signed receipt</strong>
                  <span>{live ? "generated" : firstAction?.receipt_status?.replace(/_/g, " ") ?? "waiting"}</span>
                </div>
              </div>
            ) : (
              <p className="agent-setup-muted">Create the agent above to start capturing its first action.</p>
            )}
          </div>

          {/* 3 — Live / what's next */}
          <div className="agent-quickstart-card" data-step="live" data-done={live ? "true" : "false"} aria-disabled={!created}>
            <div className="agent-quickstart-card-head">
              <span>{live ? <CheckCircle2 aria-hidden="true" size={16} /> : <Rocket aria-hidden="true" size={16} />}</span>
              <div>
                <strong>{live ? "You're live" : "What's next"}</strong>
                <small>
                  {live
                    ? "This agent is controlled and verified. Configure tighter control on real data."
                    : "After the first receipt, tune control on the actions Zroky actually saw."}
                </small>
              </div>
            </div>
            <div className="agent-setup-inline-actions">
              <DashboardButtonLink href="/policies" variant="soft">
                Set a policy
              </DashboardButtonLink>
              <DashboardButtonLink href="/integrations" variant="soft">
                Connect a verifier
              </DashboardButtonLink>
              <DashboardButtonLink href="/actions" variant="soft">
                Actions
              </DashboardButtonLink>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
