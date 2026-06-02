import type { GoldenSetView, GoldenTraceView, ReplayRunItem, ReplayRunTraceItem } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

export type GoldenHealth = "Healthy" | "Needs traces" | "Needs review" | "Flaky" | "Drift suspected";

export type CiBlockingLabel = "Blocks CI" | "Advisory only" | "Not blocking";

export function parseJsonObject(raw: string | null | undefined): Record<string, unknown> {
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed as Record<string, unknown> : {};
  } catch {
    return {};
  }
}

function cleanText(value: unknown): string | null {
  if (value == null) return null;
  if (typeof value === "string") return value.trim() || null;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) {
    const parts = value.map((item) => cleanText(item)).filter(Boolean);
    return parts.length ? parts.join(", ") : null;
  }
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>)
      .slice(0, 4)
      .map(([key, child]) => {
        const valueText = cleanText(child);
        return valueText ? `${labelize(key)}: ${valueText}` : null;
      })
      .filter(Boolean);
    return entries.length ? entries.join("; ") : null;
  }
  return String(value);
}

export function labelize(value: string): string {
  return value
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function statusLabel(status: string | null | undefined): string {
  if (!status) return "Never run";
  if (status === "pass") return "Passed";
  if (status === "fail") return "Failed";
  if (status === "not_verified") return "Not verified";
  return labelize(status);
}

export function statusBadgeClass(status: string | null | undefined): string {
  if (status === "pass" || status === "active") return "badge-green";
  if (status === "fail" || status === "error") return "badge-red";
  if (status === "pending" || status === "running" || status === "draft" || status === "not_verified") return "badge-yellow";
  return "badge-gray";
}

export function latestRunForSet(runs: ReplayRunItem[], goldenSetId: string): ReplayRunItem | null {
  const matches = runs.filter((run) => run.golden_set_id === goldenSetId);
  if (matches.length === 0) return null;
  return [...matches].sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at))[0];
}

export function isFailingRun(run: ReplayRunItem | null | undefined): boolean {
  return run?.status === "fail" || run?.status === "error" || run?.status === "not_verified";
}

export function hasDriftSignal(set: GoldenSetView): boolean {
  const config = parseJsonObject(set.judge_config_json);
  return (
    config.drift_suspected === true ||
    config.status === "drift_suspected" ||
    config.health === "drift_suspected" ||
    config.review_status === "drift_suspected"
  );
}

export function healthForSet(set: GoldenSetView, runs: ReplayRunItem[] = []): GoldenHealth {
  if (set.trace_count === 0) return "Needs traces";
  if (set.is_flaky) return "Flaky";
  if (hasDriftSignal(set)) return "Drift suspected";
  if (runs.some(isFailingRun)) return "Needs review";
  return "Healthy";
}

export function healthBadgeClass(health: GoldenHealth): string {
  if (health === "Healthy") return "badge-green";
  if (health === "Flaky" || health === "Drift suspected" || health === "Needs review") return "badge-yellow";
  return "badge-gray";
}

export function canBlockCi(set: GoldenSetView, runs: ReplayRunItem[] = []): boolean {
  return set.blocks_ci && healthForSet(set, runs) === "Healthy";
}

export function ciBlockingLabel(set: GoldenSetView, runs: ReplayRunItem[] = []): CiBlockingLabel {
  if (canBlockCi(set, runs)) return "Blocks CI";
  if (set.trace_count > 0 && !set.blocks_ci && healthForSet(set, runs) === "Healthy") return "Advisory only";
  return "Not blocking";
}

export function ciBadgeClass(label: CiBlockingLabel): string {
  if (label === "Blocks CI") return "badge-green";
  if (label === "Advisory only") return "badge-gray";
  return "badge-yellow";
}

export function passRateForRuns(runs: ReplayRunItem[]): string {
  const totals = runs.reduce(
    (acc, run) => {
      acc.pass += run.summary.pass_count;
      acc.fail += run.summary.fail_count;
      acc.error += run.summary.error_count;
      return acc;
    },
    { pass: 0, fail: 0, error: 0 },
  );
  const total = totals.pass + totals.fail + totals.error;
  if (total === 0) return "-";
  return `${((totals.pass / total) * 100).toFixed(1)}%`;
}

export function lastRunLabel(run: ReplayRunItem | null): string {
  if (!run) return "Never run";
  return `${statusLabel(run.status)} · ${formatDateTime(run.created_at)}`;
}

export function setMetadataLine(set: GoldenSetView): string {
  const config = parseJsonObject(set.judge_config_json);
  const source = cleanText(config.source_issue_id) ?? cleanText(config.source_call_id) ?? cleanText(config.source);
  return set.description?.trim() || source || "Protected production behavior";
}

export function expectedBehaviorSummary(trace: GoldenTraceView | null): string {
  if (!trace) return "No protected trace selected.";
  if (trace.expected_output_text?.trim()) return trace.expected_output_text.trim();
  const criteria = parseJsonObject(trace.criteria_json);
  return (
    cleanText(criteria.expected_behavior) ??
    cleanText(criteria.required_tool_behavior) ??
    cleanText(criteria.tool_behavior) ??
    cleanText(criteria.expected_output) ??
    "No expected behavior stored yet."
  );
}

export function sourceEvidenceSummary(trace: GoldenTraceView | null): string {
  if (!trace) return "No source evidence stored yet.";
  if (trace.source_output_text?.trim()) return trace.source_output_text.trim();
  const evidence = parseJsonObject(trace.source_evidence_json);
  return cleanText(evidence.summary) ?? cleanText(evidence.tool_behavior) ?? cleanText(evidence) ?? "No source evidence stored yet.";
}

export function replayTraceSummary(trace: ReplayRunTraceItem | null | undefined): {
  status: string;
  output: string;
  tool: string;
  cost: string;
  latency: string;
} {
  if (!trace) {
    return {
      status: "Never run",
      output: "No replay result captured yet.",
      tool: "No tool behavior result captured yet.",
      cost: "-",
      latency: "-",
    };
  }
  return {
    status: statusLabel(trace.status),
    output: cleanText(trace.output_diff) ?? trace.output_text ?? "No output diff captured.",
    tool: cleanText(trace.tool_behavior_diff) ?? "No tool behavior diff captured.",
    cost: trace.cost_delta_usd == null ? "-" : `$${trace.cost_delta_usd.toFixed(2)}`,
    latency: trace.latency_delta_ms == null ? "-" : `${trace.latency_delta_ms > 0 ? "+" : ""}${trace.latency_delta_ms} ms`,
  };
}
