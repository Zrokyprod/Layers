"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import { formatUsd } from "@/lib/format";
import type { TraceTreeNode } from "@/lib/types";
import { StatusPill } from "@/components/status-pill";

const FAILED_TRACE_STATUS_SET = new Set(["failed", "error", "timeout", "auth_failure", "loop_detected"]);

export function isFailedTraceStatus(status: string): boolean {
  return FAILED_TRACE_STATUS_SET.has(status.toLowerCase());
}

function providerTone(provider: string | null): string {
  const key = (provider ?? "").toLowerCase();
  if (key.includes("openai")) return "openai";
  if (key.includes("anthropic")) return "anthropic";
  if (key.includes("google") || key.includes("gemini")) return "google";
  if (key.includes("cohere")) return "cohere";
  if (key.includes("mistral")) return "mistral";
  return "default";
}

function latencyLabel(value: number | null | undefined): string | null {
  if (value == null) return null;
  return value < 1000 ? `${value}ms` : `${(value / 1000).toFixed(1)}s`;
}

export function TraceTreeView({ node, depth = 0 }: { node: TraceTreeNode; depth?: number }) {
  const hasChildren = node.children.length > 0;
  const [expanded, setExpanded] = useState(depth < 3);
  const isFailed = isFailedTraceStatus(node.status);
  const tone = isFailed ? "is-failed" : node.status.toLowerCase() === "success" ? "is-success" : "is-warning";
  const agentLabel = node.agent_name ?? node.call_id.slice(0, 8);
  const latency = latencyLabel(node.latency_ms);

  return (
    <li className="trace-tree-item">
      <article className={`trace-tree-node ${tone}`}>
        {hasChildren ? (
          <button
            type="button"
            className="trace-tree-toggle"
            onClick={() => setExpanded((current) => !current)}
            aria-label={expanded ? "Collapse trace branch" : "Expand trace branch"}
          >
            {expanded ? <ChevronDown aria-hidden="true" /> : <ChevronRight aria-hidden="true" />}
          </button>
        ) : (
          <span className="trace-tree-toggle-placeholder" aria-hidden="true" />
        )}

        <div className="trace-tree-main">
          <div className="trace-tree-title">
            <strong>{agentLabel}</strong>
            {node.wasted_cost_usd > 0 && (
              <span className="trace-tree-badge trace-tree-badge-danger">
                wasted {formatUsd(node.wasted_cost_usd)}
              </span>
            )}
            {node.error_code && (
              <span className="trace-tree-badge trace-tree-badge-error">{node.error_code}</span>
            )}
          </div>

          <div className="trace-tree-meta">
            {node.provider && (
              <span className={`trace-provider-chip provider-${providerTone(node.provider)}`}>
                {node.provider}
              </span>
            )}
            {node.model && <span className="trace-tree-badge trace-tree-badge-muted">{node.model}</span>}
            {latency && <span className="trace-tree-latency">{latency}</span>}
            <StatusPill value={node.status} />
          </div>
        </div>
      </article>

      {hasChildren && expanded && (
        <ul className="trace-tree-children">
          {node.children.map((child) => (
            <TraceTreeView key={child.call_id} node={child} depth={depth + 1} />
          ))}
        </ul>
      )}
    </li>
  );
}
