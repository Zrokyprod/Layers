"use client";

import Link from "next/link";
import { Activity, AlertCircle, Check, Clock3, Copy, PlayCircle, RefreshCw, Server, ShieldCheck, Terminal } from "lucide-react";
import { useMemo, useState } from "react";

import type { CaptureHealthResponse } from "@/lib/types";

type CaptureMethod = "sdk" | "gateway";

type ChecklistItem = {
  label: string;
  done: boolean;
};

type CaptureConnectPanelProps = {
  captureHealth: CaptureHealthResponse | null;
  checklistItems: ChecklistItem[];
  completedCount: number;
  totalCount: number;
  progressPct: number;
  onRefresh: () => void;
  onMarkOpened: () => void;
};

function CopyButton({
  value,
  label,
  onCopy,
}: {
  value: string;
  label: string;
  onCopy: () => void;
}) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    onCopy();
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      try {
        await navigator.clipboard.writeText(value);
      } catch {
        // Clipboard permissions vary by browser context; still mark the setup path opened.
      }
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }

  return (
    <button type="button" className="btn btn-soft btn-sm capture-copy-btn" onClick={() => void copy()}>
      {copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
      {copied ? "Copied" : label}
    </button>
  );
}

function CodeBlock({
  title,
  value,
  onCopy,
}: {
  title: string;
  value: string;
  onCopy: () => void;
}) {
  return (
    <div className="capture-code-block">
      <div className="capture-code-head">
        <span>{title}</span>
        <CopyButton value={value} label="Copy" onCopy={onCopy} />
      </div>
      <pre>
        <code>{value}</code>
      </pre>
    </div>
  );
}

function formatAge(seconds: number | null | undefined): string {
  if (seconds == null) return "No event";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ago`;
}

function formatSeenAt(value: string | null | undefined): string {
  if (!value) return "Waiting";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown time";
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function sourceLabel(source: string | null | undefined): string {
  if (!source) return "Unknown";
  if (source.startsWith("gateway")) return "Gateway";
  if (source === "sdk_ingest") return "SDK";
  if (source === "retrieval") return "Retrieval";
  if (source === "memory") return "Memory";
  return source.replaceAll("_", " ");
}

export function CaptureConnectPanel({
  captureHealth,
  checklistItems,
  completedCount,
  totalCount,
  progressPct,
  onRefresh,
  onMarkOpened,
}: CaptureConnectPanelProps) {
  const [method, setMethod] = useState<CaptureMethod>("gateway");
  const projectId = captureHealth?.project_id || "your-project-id";

  const snippets = useMemo(() => {
    const apiBaseUrl = process.env.NEXT_PUBLIC_ZROKY_API_BASE_URL || "https://api.zroky.com";
    const ingestUrl = `${apiBaseUrl.replace(/\/$/, "")}/v1/ingest`;
    const sdkInstall = "npm install @zroky-ai/sdk";
    const sdkCode = `import OpenAI from "openai";
import { init, wrap } from "@zroky-ai/sdk";

init({
  apiKey: "zk_your_key",
  projectId: "${projectId}",
  endpoint: "${ingestUrl}",
  agentName: "support-agent",
  workflowName: "support-resolution",
  promptVersion: "support-v42",
});

const openai = wrap(new OpenAI());
const response = await openai.chat.completions.create({
  model: "gpt-4o-mini",
  messages: [{ role: "user", content: prompt }],
});`;
    const gatewayEnv = `$env:ZROKY_EMIT_MODE="http"
$env:ZROKY_INGEST_URL="${ingestUrl}"
$env:ZROKY_GATEWAY_HEARTBEAT_URL="${apiBaseUrl.replace(/\/$/, "")}/api/v1/capture/gateway-heartbeat"
$env:ZROKY_CAPTURE_DURABILITY_MODE="fail_closed"
$env:ZROKY_GATEWAY_API_KEY="zk_your_key"
go run ./cmd/gateway`;
const gatewayClient = `OPENAI_BASE_URL=https://gateway.your-company.com/v1
X-Zroky-Project-Id: ${projectId}
X-Zroky-Agent-Name: support-agent
X-Zroky-Workflow-Name: support-resolution
X-Zroky-Prompt-Version: support-v42`;
    const smoke = ".\\make.ps1 capture-smoke-local";

    return { sdkInstall, sdkCode, gatewayEnv, gatewayClient, smoke };
  }, [projectId]);

  const statusLabel =
    captureHealth?.status === "stale"
      ? "Capture is stale"
      : captureHealth?.status === "connected"
        ? "Capture is connected"
        : "Waiting for first call";
  const connected = captureHealth?.status === "connected";
  const stale = captureHealth?.status === "stale";
  const lastCallHref = captureHealth?.last_call_id ? `/calls/${encodeURIComponent(captureHealth.last_call_id)}` : "/calls";
  const verificationTitle = connected
    ? "Integration verified"
    : stale
      ? "Capture was connected, now stale"
      : "Send one call to verify";
  const verificationDetail = connected
    ? `${sourceLabel(captureHealth?.last_source)} event received ${formatAge(captureHealth?.seconds_since_last_call)}.`
    : stale
      ? `Last event was ${formatAge(captureHealth?.seconds_since_last_call)}; run the smoke check or restart your agent.`
      : "Run the gateway command below, then send one agent request.";
  const validationWarnings = captureHealth?.validation_warnings ?? [];
  const gatewayStatus = captureHealth?.gateway_worst_status ?? "unknown";
  const gatewayBacklog = captureHealth?.gateway_spool_backlog ?? 0;
  const gatewayLoss = captureHealth?.gateway_loss_count ?? 0;

  function selectMethod(nextMethod: CaptureMethod) {
    setMethod(nextMethod);
    onMarkOpened();
  }

  return (
    <section className="panel capture-connect-panel">
      <div className="capture-connect-head">
        <div className="capture-connect-title">
          <Server aria-hidden="true" />
          <div>
            <h2>{statusLabel}</h2>
            <p>
              Send one real agent call through Zroky. The dashboard will switch to live mode after the first event lands.
            </p>
          </div>
        </div>
        <button type="button" className="btn btn-soft" onClick={onRefresh}>
          <RefreshCw aria-hidden="true" />
          Check again
        </button>
      </div>

      <div className={`capture-verification-strip ${connected ? "connected" : stale ? "stale" : "waiting"}`}>
        <div className="capture-verification-main">
          {connected ? <ShieldCheck aria-hidden="true" /> : <Activity aria-hidden="true" />}
          <div>
            <strong>{verificationTitle}</strong>
            <span>{verificationDetail}</span>
          </div>
        </div>
        <div className="capture-health-metrics" aria-label="Capture health details">
          <div className="capture-health-metric">
            <span>Last event</span>
            <strong>{formatAge(captureHealth?.seconds_since_last_call)}</strong>
            <small>{formatSeenAt(captureHealth?.last_seen_at)}</small>
          </div>
          <div className="capture-health-metric">
            <span>Source</span>
            <strong>{sourceLabel(captureHealth?.last_source)}</strong>
            <small>
              SDK {captureHealth?.sdk_events_24h ?? 0} / Gateway {captureHealth?.gateway_events_24h ?? 0}
            </small>
          </div>
          <div className="capture-health-metric">
            <span>24h calls</span>
            <strong>{captureHealth?.calls_24h ?? 0}</strong>
            <small>{captureHealth?.error_events_24h ?? 0} errors</small>
          </div>
          <div className="capture-health-metric">
            <span>Durability</span>
            <strong>{gatewayStatus.replaceAll("_", " ")}</strong>
            <small>{gatewayLoss > 0 ? `${gatewayLoss} lost` : `${gatewayBacklog} queued`}</small>
          </div>
          <Link href={lastCallHref} className="capture-health-metric capture-health-link">
            <span>Last call</span>
            <strong>{captureHealth?.last_call_id ? "Open" : "None"}</strong>
            <small>{captureHealth?.last_model || captureHealth?.last_provider || "Waiting"}</small>
          </Link>
        </div>
      </div>

      {validationWarnings.length > 0 ? (
        <div className="capture-validation-warnings" aria-label="Capture validation warnings">
          {validationWarnings.map((warning) => (
            <div key={warning.code} className="capture-validation-warning">
              <AlertCircle aria-hidden="true" />
              <div>
                <strong>{warning.label}</strong>
                <span>{warning.detail}</span>
              </div>
            </div>
          ))}
        </div>
      ) : null}

      <div className="onboarding-progress" role="status" aria-live="polite">
        <div className="onboarding-progress-head">
          <strong>Setup progress</strong>
          <span className="mono">
            {completedCount}/{totalCount} done
          </span>
        </div>
        <div className="onboarding-progress-track" aria-hidden="true">
          <div className="onboarding-progress-fill" style={{ width: `${progressPct}%` }} />
        </div>
        <div className="onboarding-progress-grid">
          {checklistItems.map((item) => (
            <span key={item.label} className={`onboarding-progress-item${item.done ? " done" : ""}`}>
              {item.done ? "Done" : "Todo"}: {item.label}
            </span>
          ))}
        </div>
      </div>

      <div className="capture-method-toggle" role="tablist" aria-label="Capture setup method">
        <button
          type="button"
          role="tab"
          aria-selected={method === "gateway"}
          className={method === "gateway" ? "active" : ""}
          onClick={() => selectMethod("gateway")}
        >
          <Terminal aria-hidden="true" />
          Gateway
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={method === "sdk"}
          className={method === "sdk" ? "active" : ""}
          onClick={() => selectMethod("sdk")}
        >
          <PlayCircle aria-hidden="true" />
          SDK
        </button>
      </div>

      {method === "gateway" ? (
        <div className="capture-connect-grid">
          <CodeBlock title="Run gateway in direct HTTP mode" value={snippets.gatewayEnv} onCopy={onMarkOpened} />
          <CodeBlock title="Point your agent at the gateway" value={snippets.gatewayClient} onCopy={onMarkOpened} />
          <CodeBlock title="Local smoke check" value={snippets.smoke} onCopy={onMarkOpened} />
        </div>
      ) : (
        <div className="capture-connect-grid">
          <CodeBlock title="Install SDK" value={snippets.sdkInstall} onCopy={onMarkOpened} />
          <CodeBlock title="Wrap one LLM call" value={snippets.sdkCode} onCopy={onMarkOpened} />
        </div>
      )}

      <div className="capture-connect-actions">
        <Link href="/settings/keys" className="btn btn-primary">
          Get API key
        </Link>
        <Link href="/calls" className="btn btn-soft">
          <Clock3 aria-hidden="true" />
          Open Calls
        </Link>
      </div>
    </section>
  );
}
