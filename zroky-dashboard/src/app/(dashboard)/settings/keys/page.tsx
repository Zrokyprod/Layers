"use client";

import Link from "next/link";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  ArrowRight,
  CheckCircle2,
  Code2,
  Copy,
  KeyRound,
  Plug,
  RotateCcw,
  Route,
  ShieldCheck,
  Terminal,
} from "lucide-react";

import { formatDateTime } from "@/lib/format";
import type { ApiKeyCreateResponse, ApiKeyResponse } from "@/lib/types";
import {
  useProjectSettings,
  useListProjectApiKeys,
  useCreateProjectApiKey,
  useRevokeProjectApiKey,
  useRotateProjectApiKey,
} from "@/lib/hooks";
import {
  buildLiveSmokeCommand,
  buildMandateStarter,
  buildProtectedAgentSnippet,
  humanizeIntent,
  pilotHandoffCriteria,
  pilotHandoffSteps,
  protectedAgentTemplates,
} from "@/lib/protected-agent-setup";
import { apiKeySchema, type ApiKeyFormData } from "@/lib/schemas";

const defaultKeyName = "Production capture key";
const capturePath = ["Create key", "Run SDK/Gateway", "First trace", "Fixture validation"];

function ApiKeysContent() {
  const searchParams = useSearchParams();
  const projectQuery = useProjectSettings();
  const projectId = projectQuery.data?.project_id ?? "";
  const keysQuery = useListProjectApiKeys(projectId);

  const createMutation = useCreateProjectApiKey();
  const revokeMutation = useRevokeProjectApiKey();
  const rotateMutation = useRotateProjectApiKey();

  const [newKey, setNewKey] = useState<ApiKeyCreateResponse | null>(null);
  const [copied, setCopied] = useState(false);
  const [statusMsg, setStatusMsg] = useState("");
  const [expiresInDays, setExpiresInDays] = useState("90");
  const [revokeTarget, setRevokeTarget] = useState<ApiKeyResponse | null>(null);
  const [rotateTarget, setRotateTarget] = useState<ApiKeyResponse | null>(null);
  const [selectedAgentId, setSelectedAgentId] = useState(protectedAgentTemplates[0].id);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<ApiKeyFormData>({
    resolver: zodResolver(apiKeySchema),
    defaultValues: { name: defaultKeyName },
  });

  const onCreate = handleSubmit(async (data) => {
    if (!projectId) return;
    setStatusMsg("");
    setNewKey(null);
    try {
      const parsedExpiry = expiresInDays.trim() === "" ? null : Number(expiresInDays);
      const created = await createMutation.mutateAsync({
        projectId,
        name: data.name.trim(),
        expires_in_days: Number.isFinite(parsedExpiry ?? 0) ? parsedExpiry : null,
        scopes: ["project:member"],
      });
      setNewKey(created);
      reset({ name: defaultKeyName });
    } catch (err) {
      setStatusMsg(err instanceof Error ? err.message : "Failed to create key.");
    }
  });

  async function onRevoke() {
    if (!revokeTarget || !projectId) return;
    try {
      await revokeMutation.mutateAsync({ projectId, keyId: revokeTarget.key_id });
      setStatusMsg(`Key "${revokeTarget.name}" revoked.`);
    } catch (err) {
      setStatusMsg(err instanceof Error ? err.message : "Revoke failed.");
    } finally {
      setRevokeTarget(null);
    }
  }

  async function onRotate() {
    if (!projectId || !rotateTarget) return;
    try {
      const rotated = await rotateMutation.mutateAsync({ projectId, keyId: rotateTarget.key_id });
      setNewKey(rotated);
      setStatusMsg(`Key "${rotateTarget.name}" rotated. Copy the replacement key now.`);
    } catch (err) {
      setStatusMsg(err instanceof Error ? err.message : "Rotation failed.");
    } finally {
      setRotateTarget(null);
    }
  }

  async function copyKey(raw: string) {
    try {
      await navigator.clipboard.writeText(raw);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setStatusMsg("Copy failed. Select the key and copy it manually.");
    }
  }

  const keys = keysQuery.data ?? [];
  const loading = projectQuery.isLoading || keysQuery.isLoading;
  const error = projectQuery.error?.message ?? keysQuery.error?.message ?? null;
  const activeKeys = keys.filter((key) => !key.revoked && !key.expired);
  const hasActiveKey = activeKeys.length > 0 || newKey !== null;
  const currentStepIndex = hasActiveKey ? 1 : 0;
  const snippetProjectId = projectId || "proj_...";
  const protectedAgentIntent = searchParams.get("intent") === "protect-agent";
  const planIntent = humanizeIntent(searchParams.get("plan"));
  const sourceIntent = humanizeIntent(searchParams.get("source"));
  const pilotHandoffIntent = searchParams.get("source") === "pilot";
  const selectedAgent =
    protectedAgentTemplates.find((template) => template.id === selectedAgentId) ?? protectedAgentTemplates[0];
  const protectedMandateStarter = buildMandateStarter(selectedAgent);
  const protectedAgentSnippet = buildProtectedAgentSnippet(selectedAgent, snippetProjectId);
  const liveSmokeCommand = buildLiveSmokeCommand(selectedAgent);
  const connectorSetupHref =
    selectedAgent.liveSmokeScenario === "refund"
      ? "/settings/integrations#ledger-refund-connector"
      : selectedAgent.liveSmokeScenario === "customer-record"
        ? "/settings/integrations#customer-record-connector"
        : "/settings/integrations";
  const connectorSetupLabel =
    selectedAgent.liveSmokeScenario === "refund"
      ? "Configure ledger connector"
      : selectedAgent.liveSmokeScenario === "customer-record"
        ? "Configure CRM connector"
        : "Open integrations";
  const jsSetupSnippet = `npm install @zroky-ai/sdk
export ZROKY_PROJECT_ID="${snippetProjectId}"
export ZROKY_API_KEY="${newKey?.api_key ?? "zk_live_..."}"
export ZROKY_ENDPOINT="https://api.zroky.com/v1/ingest"`;
  const pythonSetupSnippet = `pip install zroky
export ZROKY_PROJECT="${snippetProjectId}"
export ZROKY_API_KEY="${newKey?.api_key ?? "zk_live_..."}"
export ZROKY_INGEST_URL="https://api.zroky.com/v1/ingest"`;
  const jsSmokeSnippet = `import { init, traceRun, captureToolCall } from "@zroky-ai/sdk";

init({
  agentName: "first-capture-agent",
  workflowId: "first-capture",
  environment: "production",
});

await traceRun({ name: "first-capture", userInput: "smoke test" }, async () => {
  await captureToolCall({
    name: "lookup_order",
    result: { ok: true },
  });
  return "captured";
});`;
  const pythonSmokeSnippet = `import zroky

zroky.init()

with zroky.trace_run(
    name="first-capture",
    user_input="smoke test",
    environment="production",
) as run:
    zroky.capture_tool_call(
        name="lookup_order",
        result={"ok": True},
    )
    run.set_final_answer("captured")

zroky.flush()`;
  const gatewaySnippet = `docker run -p 8090:8090 \\
  -e ZROKY_API_KEY=zk_live_... \\
  ghcr.io/zroky-ai/zroky-gateway:latest

export OPENAI_BASE_URL=http://localhost:8090/v1`;

  return (
    <div className="page-content keys-setup-page">
      <section className="panel keys-onboarding-panel" aria-labelledby="project-key-setup-title">
        <header className="keys-onboarding-header">
          <div>
            <span className="settings-section-kicker">
              <KeyRound aria-hidden="true" />
              Capture setup
            </span>
            <h2 id="project-key-setup-title">Project key setup</h2>
            <p>Create one key, run one SDK or Gateway call, then confirm your first trace.</p>
          </div>
          <Link href="/trace" className="btn btn-soft">
            Open traces
            <ArrowRight aria-hidden="true" />
          </Link>
        </header>
        <div className="keys-capture-path" aria-label="Project key to verified replay path">
          {capturePath.map((step, index) => (
            <span
              key={step}
              className={
                index < currentStepIndex ? "is-done" : index === currentStepIndex ? "is-current" : undefined
              }
            >
              {String(index + 1).padStart(2, "0")}
              <strong>{step}</strong>
            </span>
          ))}
        </div>
      </section>

      {protectedAgentIntent && (
        <section className="panel keys-protected-setup-panel" aria-labelledby="protected-agent-setup-title">
          <header className="keys-onboarding-header">
            <div>
              <span className="settings-section-kicker">
                <ShieldCheck aria-hidden="true" />
                Protected agent
              </span>
              <h2 id="protected-agent-setup-title">First protected agent setup</h2>
              <p>
                Choose the agent type, copy the matching mandate, create a project key, then run one captured action.
              </p>
              <div className="keys-protected-meta" aria-label="Signup intent context">
                {planIntent && <span>Plan intent: {planIntent}</span>}
                {sourceIntent && <span>Source: {sourceIntent}</span>}
                <span>{protectedAgentTemplates.length} starter mandates</span>
              </div>
            </div>
            <Link href="#create-project-key" className="btn btn-primary">
              Create project key
              <ArrowRight aria-hidden="true" />
            </Link>
          </header>

          <div className="keys-agent-tabs" role="tablist" aria-label="Protected agent templates">
            {protectedAgentTemplates.map((template) => (
              <button
                key={template.id}
                type="button"
                role="tab"
                aria-selected={template.id === selectedAgent.id}
                className={template.id === selectedAgent.id ? "keys-agent-tab is-active" : "keys-agent-tab"}
                onClick={() => setSelectedAgentId(template.id)}
              >
                {template.label}
              </button>
            ))}
          </div>

          {pilotHandoffIntent && (
            <div className="keys-pilot-handoff" aria-label="Pilot handoff readiness">
              <div className="keys-pilot-copy">
                <span className="settings-section-kicker">
                  <Route aria-hidden="true" />
                  Pilot handoff
                </span>
                <h3>Pilot handoff readiness</h3>
                <p>
                  Before marking this verified, prove the action was captured, stopped or held, reconciled against{" "}
                  {selectedAgent.systemOfRecord}, and exported with a usable evidence hash.
                </p>
              </div>
              <ol className="keys-pilot-steps">
                {pilotHandoffSteps.map((step) => (
                  <li key={step}>
                    <CheckCircle2 aria-hidden="true" />
                    {step}
                  </li>
                ))}
              </ol>
              <article className="keys-pilot-card">
                <h4>System-of-record connector</h4>
                <ul>
                  {selectedAgent.connectorInputs.map((input) => (
                    <li key={input}>{input}</li>
                  ))}
                </ul>
                <Link href={connectorSetupHref} className="btn btn-primary btn-sm">
                  {connectorSetupLabel}
                  <ArrowRight aria-hidden="true" />
                </Link>
              </article>
              <article className="keys-pilot-card">
                <h4>Pass criteria</h4>
                <ul>
                  {pilotHandoffCriteria.map((criterion) => (
                    <li key={criterion}>
                      <code>{criterion}</code>
                    </li>
                  ))}
                </ul>
              </article>
              <article className="keys-pilot-card keys-pilot-live">
                <h4>{liveSmokeCommand ? "Live smoke command" : "Connector gap before live smoke"}</h4>
                {liveSmokeCommand ? (
                  <>
                    <pre aria-label="Design-partner live smoke command">
                      <code>{liveSmokeCommand}</code>
                    </pre>
                    <button type="button" className="btn btn-soft btn-sm" onClick={() => void copyKey(liveSmokeCommand)}>
                      <Copy aria-hidden="true" />
                      Copy live smoke command
                    </button>
                  </>
                ) : (
                  <p>
                    No packaged live-smoke runner exists for this agent type yet. Capture the action with the SDK
                    wrapper, then add the connector that reads {selectedAgent.systemOfRecord}.
                  </p>
                )}
              </article>
            </div>
          )}

          <div className="keys-protected-grid">
            <article className="keys-protected-block">
              <div>
                <h3>Mandate starter</h3>
                <p>{selectedAgent.mandate}</p>
              </div>
              <dl className="keys-mandate-facts">
                <div>
                  <dt>Agent</dt>
                  <dd>{selectedAgent.agentName}</dd>
                </div>
                <div>
                  <dt>Outcome source</dt>
                  <dd>{selectedAgent.systemOfRecord}</dd>
                </div>
              </dl>
              <div className="keys-mandate-lists">
                <div>
                  <strong>Hold if</strong>
                  <ul>
                    {selectedAgent.holdConditions.map((condition) => (
                      <li key={condition}>{condition}</li>
                    ))}
                  </ul>
                </div>
                <div>
                  <strong>Evidence required</strong>
                  <ul>
                    {selectedAgent.requiredEvidence.map((evidence) => (
                      <li key={evidence}>{evidence}</li>
                    ))}
                  </ul>
                </div>
              </div>
              <div className="keys-copy-actions">
                <button type="button" className="btn btn-soft" onClick={() => void copyKey(protectedMandateStarter)}>
                  <Copy aria-hidden="true" />
                  Copy mandate
                </button>
              </div>
            </article>

            <article className="keys-protected-block">
              <div>
                <h3>SDK action wrapper</h3>
                <p>Wrap the first high-stakes tool call so Zroky can hold unsafe action and verify real outcome.</p>
              </div>
              <pre aria-label="Protected agent SDK snippet">
                <code>{protectedAgentSnippet}</code>
              </pre>
              <div className="keys-copy-actions">
                <button type="button" className="btn btn-soft" onClick={() => void copyKey(protectedAgentSnippet)}>
                  <Copy aria-hidden="true" />
                  Copy SDK wrapper
                </button>
                <Link href="/trace" className="btn btn-soft">
                  Open traces
                  <ArrowRight aria-hidden="true" />
                </Link>
              </div>
            </article>
          </div>
        </section>
      )}

      {newKey && (
        <section className="panel keys-newkey-banner" aria-label="One-time project key">
          <div className="keys-copy-head">
            <span className="keys-copy-icon">
              <Copy aria-hidden="true" />
            </span>
            <div>
              <h2>Copy this project key now.</h2>
              <p>This secret is shown once. Save it in your runtime environment before closing this panel.</p>
            </div>
          </div>
          <div className="share-url-row keys-newkey-row">
            <span className="share-url settings-key-reveal">{newKey.api_key}</span>
            <button type="button" className="btn btn-primary" onClick={() => void copyKey(newKey.api_key)}>
              <Copy aria-hidden="true" />
              {copied ? "Copied" : "Copy key"}
            </button>
          </div>
          <div className="keys-next-grid">
            <div>
              <span>Project</span>
              <strong>{newKey.project_id}</strong>
            </div>
            <div>
              <span>Expires</span>
              <strong>{newKey.expires_at ? formatDateTime(newKey.expires_at) : "Never"}</strong>
            </div>
            <div>
              <span>Scope</span>
              <strong>{newKey.scopes.join(", ")}</strong>
            </div>
          </div>
          <div className="keys-command-grid" aria-label="One-time setup commands">
            <pre aria-label="Node SDK environment setup">
              <code>{jsSetupSnippet}</code>
            </pre>
            <pre aria-label="Python SDK environment setup">
              <code>{pythonSetupSnippet}</code>
            </pre>
          </div>
          <div className="keys-copy-actions">
            <button type="button" className="btn btn-soft" onClick={() => void copyKey(jsSetupSnippet)}>
              <Copy aria-hidden="true" />
              Copy Node setup
            </button>
            <button type="button" className="btn btn-soft" onClick={() => void copyKey(pythonSetupSnippet)}>
              <Copy aria-hidden="true" />
              Copy Python setup
            </button>
            <button type="button" className="btn btn-soft" onClick={() => setNewKey(null)}>
              Done
            </button>
            <Link href="/trace" className="btn btn-primary">
              Open traces
              <ArrowRight aria-hidden="true" />
            </Link>
          </div>
        </section>
      )}

      {statusMsg && (
        <p className={statusMsg.toLowerCase().includes("failed") ? "field-error keys-status-msg" : "field-success keys-status-msg"}>
          {statusMsg}
        </p>
      )}

      <section className="keys-primary-grid">
        <article className="panel keys-create-panel" id="create-project-key">
          <header className="panel-header">
            <div>
              <h2>Create project key</h2>
              <p>Use it only for Zroky capture. It does not grant model-provider access.</p>
            </div>
          </header>

          <form onSubmit={onCreate} className="keys-create-form">
            <div className="field settings-key-field keys-keyname-field">
              <label htmlFor="key-name" className="field-label">
                Key name
              </label>
              <input
                id="key-name"
                type="text"
                className="input"
                {...register("name")}
                placeholder="Production capture key"
                disabled={createMutation.isPending || !projectId}
              />
              {errors.name && <span className="field-error">{errors.name.message}</span>}
            </div>
            <div className="field settings-key-field">
              <label htmlFor="key-expiry" className="field-label">
                Expires in days
              </label>
              <input
                id="key-expiry"
                type="number"
                className="input"
                min="1"
                max="3650"
                value={expiresInDays}
                onChange={(event) => setExpiresInDays(event.target.value)}
                placeholder="90"
                disabled={createMutation.isPending || !projectId}
              />
              <span className="field-hint">Leave blank for no automatic expiry. Scope is project:member.</span>
            </div>
            <button type="submit" className="btn btn-primary" disabled={createMutation.isPending || !projectId}>
              {createMutation.isPending ? "Creating..." : "Create project key"}
            </button>
          </form>

          <div className="keys-provider-note">
            <Plug aria-hidden="true" />
            <div>
              <strong>Provider keys are not needed for capture.</strong>
              <span>Add them later only when verified replay needs live model calls.</span>
            </div>
            <Link href="/settings/providers" className="btn btn-soft btn-sm">
              Provider settings
            </Link>
          </div>
        </article>

        <aside className="panel keys-setup-card">
          <span className="settings-section-kicker">
            <Terminal aria-hidden="true" />
            First run
          </span>
          <h2>What to do next</h2>
          <p>After the key exists, run one smoke capture and open Traces to verify delivery.</p>
          <ol className="keys-checklist">
            {["Create project key", "Install SDK or Gateway", "Run one smoke capture", "Confirm trace"].map((step, index) => (
              <li key={step} className={index === 0 && hasActiveKey ? "is-done" : undefined}>
                <CheckCircle2 aria-hidden="true" />
                {step}
              </li>
            ))}
          </ol>
        </aside>
      </section>

      <section className="keys-snippet-grid" aria-label="Capture setup snippets">
        <article className="panel keys-snippet-card">
          <div className="keys-snippet-head">
            <Code2 aria-hidden="true" />
            <div>
              <h2>SDK capture</h2>
              <p>Use when you can add Zroky directly inside your app code.</p>
            </div>
          </div>
          <div className="keys-code-grid">
            <pre aria-label="TypeScript SDK project key snippet">
              <code>{jsSmokeSnippet}</code>
            </pre>
            <pre aria-label="Python SDK project key snippet">
              <code>{pythonSmokeSnippet}</code>
            </pre>
          </div>
        </article>

        <article className="panel keys-snippet-card">
          <div className="keys-snippet-head">
            <Route aria-hidden="true" />
            <div>
              <h2>Gateway capture</h2>
              <p>Use when you need evidence without changing agent code first.</p>
            </div>
          </div>
          <pre aria-label="Gateway project key snippet">
            <code>{gatewaySnippet}</code>
          </pre>
        </article>
      </section>

      <section className="panel keys-table-panel">
        <header className="panel-header">
          <div>
            <h2>Project keys</h2>
            <p>{keys.length} key{keys.length !== 1 ? "s" : ""} for this project.</p>
          </div>
        </header>

        {loading && <div className="loading" />}
        {error && <p className="field-error">{error}</p>}
        {!loading && !error && keys.length === 0 && (
          <div className="empty">No project keys yet. Create one to start capturing calls.</div>
        )}

        {!loading && !error && keys.length > 0 && (
          <div className="table-wrap">
            <table className="settings-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Prefix</th>
                  <th>Scope</th>
                  <th>Expires</th>
                  <th>Created</th>
                  <th>Last used</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {keys.map((key) => (
                  <tr key={key.key_id} className={key.revoked ? "keys-row-revoked" : ""}>
                    <td>{key.name}</td>
                    <td className="mono">{key.key_prefix}...</td>
                    <td>{key.scopes?.join(", ") || "project:member"}</td>
                    <td>{key.expires_at ? formatDateTime(key.expires_at) : "Never"}</td>
                    <td>{formatDateTime(key.created_at)}</td>
                    <td>{key.last_used_at ? formatDateTime(key.last_used_at) : "Never"}</td>
                    <td>
                      {key.revoked ? (
                        <span className="pill pill-red">Revoked</span>
                      ) : key.expired ? (
                        <span className="pill pill-red">Expired</span>
                      ) : (
                        <span className="pill pill-green">Active</span>
                      )}
                    </td>
                    <td>
                      {!key.revoked && !key.expired && (
                        <div className="actions">
                          <button
                            type="button"
                            className="btn btn-soft btn-sm"
                            disabled={rotateMutation.isPending}
                            onClick={() => setRotateTarget(key)}
                          >
                            <RotateCcw aria-hidden="true" />
                            Rotate
                          </button>
                          <button type="button" className="btn btn-danger btn-sm" onClick={() => setRevokeTarget(key)}>
                            Revoke
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {revokeTarget && (
        <div
          className="fix-modal-backdrop"
          role="presentation"
          onClick={() => !revokeMutation.isPending && setRevokeTarget(null)}
        >
          <section
            className="panel keys-revoke-modal"
            role="dialog"
            aria-modal="true"
            aria-label="Revoke API key"
            onClick={(event) => event.stopPropagation()}
          >
            <header className="panel-header">
              <div>
                <h2>Revoke project key</h2>
                <p>
                  This action is irreversible. Requests using <strong>{revokeTarget.name}</strong> will stop working.
                </p>
              </div>
            </header>
            <div className="actions">
              <button type="button" className="btn btn-danger" disabled={revokeMutation.isPending} onClick={onRevoke}>
                {revokeMutation.isPending ? "Revoking..." : "Yes, revoke key"}
              </button>
              <button
                type="button"
                className="btn btn-soft"
                disabled={revokeMutation.isPending}
                onClick={() => setRevokeTarget(null)}
              >
                Cancel
              </button>
            </div>
          </section>
        </div>
      )}

      {rotateTarget && (
        <div
          className="fix-modal-backdrop"
          role="presentation"
          onClick={() => !rotateMutation.isPending && setRotateTarget(null)}
        >
          <section
            className="panel keys-revoke-modal"
            role="dialog"
            aria-modal="true"
            aria-label="Rotate API key"
            onClick={(event) => event.stopPropagation()}
          >
            <header className="panel-header">
              <div>
                <h2>Rotate project key</h2>
                <p>
                  Zroky will revoke <strong>{rotateTarget.name}</strong> and create a replacement. Copy the
                  replacement before closing the banner.
                </p>
              </div>
            </header>
            <div className="settings-modal-facts">
              <span>
                Current prefix <strong className="mono">{rotateTarget.key_prefix}...</strong>
              </span>
              <span>
                Scope <strong>{rotateTarget.scopes?.join(", ") || "project:member"}</strong>
              </span>
            </div>
            <div className="actions">
              <button type="button" className="btn btn-primary" disabled={rotateMutation.isPending} onClick={() => void onRotate()}>
                {rotateMutation.isPending ? "Rotating..." : "Rotate and show replacement"}
              </button>
              <button
                type="button"
                className="btn btn-soft"
                disabled={rotateMutation.isPending}
                onClick={() => setRotateTarget(null)}
              >
                Cancel
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

export default function ApiKeysPage() {
  return (
    <Suspense fallback={<div className="page-content keys-setup-page"><section className="panel"><div className="loading" /></section></div>}>
      <ApiKeysContent />
    </Suspense>
  );
}
