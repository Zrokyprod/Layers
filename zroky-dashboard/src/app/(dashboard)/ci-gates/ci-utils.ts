import type { RegressionCIRunDetailResponse, ReplayRunItem } from "@/lib/api";

export const NOT_VERIFIED_COPY =
  "This CI run did not execute trusted replay, so it cannot prove this PR is safe.";

export type CiGateStatus = "pass" | "warn" | "fail" | "error" | "not_verified" | "skipped" | "running" | "pending" | string;

export function isCiRun(run: ReplayRunItem): boolean {
  return run.trigger === "github" || run.golden_set_id.startsWith("regression-ci:");
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

export function stringField(source: Record<string, unknown> | null | undefined, key: string): string | null {
  const value = source?.[key];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

export function numericField(source: Record<string, unknown> | null | undefined, key: string): number | null {
  const value = source?.[key];
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

function nestedRecord(source: Record<string, unknown> | null | undefined, key: string): Record<string, unknown> | null {
  const value = source?.[key];
  return isRecord(value) ? value : null;
}

export function normalizeStatus(run: ReplayRunItem, detail?: RegressionCIRunDetailResponse | null): CiGateStatus {
  const reportVerdict = stringField(detail?.report, "verdict");
  const rawStatus = (detail?.status || reportVerdict || run.status || "pending").trim().toLowerCase();
  if (rawStatus === "failed") return "fail";
  if (rawStatus === "queued") return "pending";
  if (rawStatus === "success") return "pass";
  return rawStatus;
}

export function statusLabel(status: CiGateStatus): string {
  const labels: Record<string, string> = {
    pass: "Passed",
    warn: "Warning",
    fail: "Failed",
    error: "Error",
    not_verified: "Not verified",
    skipped: "Skipped",
    running: "Running",
    pending: "Pending",
  };
  return labels[status] ?? status.replaceAll("_", " ");
}

export function statusBadgeClass(status: CiGateStatus): string {
  if (status === "pass") return "badge-green";
  if (status === "fail" || status === "error") return "badge-red";
  if (status === "warn" || status === "not_verified") return "badge-yellow";
  if (status === "running" || status === "pending") return "badge-blue";
  return "badge-gray";
}

export function actionLabel(status: CiGateStatus): string {
  if (status === "pass") return "View";
  if (status === "warn") return "Review warnings";
  if (status === "running" || status === "pending") return "View status";
  return "Review";
}

export function verdictSubtitle(status: CiGateStatus): string {
  if (status === "pass") return "Trusted replay completed under threshold.";
  if (status === "warn") return "Only warning-only evidence failed; blocking Contracts passed.";
  if (status === "fail") return "Regression CI blocked this change.";
  if (status === "error") return "The run encountered an infrastructure or provider error.";
  if (status === "not_verified") return NOT_VERIFIED_COPY;
  if (status === "running") return "Regression CI is still running replay-backed checks.";
  if (status === "pending") return "Regression CI is waiting to start replay-backed checks.";
  return "Regression CI did not produce a blocking verdict.";
}

export function regressionRate(run: ReplayRunItem, detail?: RegressionCIRunDetailResponse | null): number | null {
  const fromReport = numericField(detail?.report, "regression_rate");
  if (fromReport != null) return fromReport;
  const executed = run.summary.trace_count_executed || run.summary.trace_count_at_dispatch;
  if (!executed) return null;
  return run.summary.fail_count / executed;
}

export function formatRate(value: number | null): string {
  if (value == null) return "-";
  return `${(value * 100).toFixed(value > 0 && value < 0.01 ? 2 : 1)}%`;
}

export function thresholdRate(detail?: RegressionCIRunDetailResponse | null): number | null {
  return (
    numericField(detail?.report, "threshold") ??
    numericField(detail?.report, "regression_threshold") ??
    numericField(detail?.report, "max_regression_rate")
  );
}

export function failedFlowCount(run: ReplayRunItem, detail?: RegressionCIRunDetailResponse | null): number | null {
  return (
    numericField(detail?.report, "regressed_count") ??
    numericField(detail?.report, "failed_flows") ??
    numericField(detail?.report, "failed_flow_count") ??
    run.summary.fail_count ??
    null
  );
}

export function protectedFlowCount(run: ReplayRunItem, detail?: RegressionCIRunDetailResponse | null): number {
  return (
    numericField(detail?.report, "protected_flows") ??
    numericField(detail?.report, "trace_count") ??
    run.summary.trace_count_at_dispatch ??
    0
  );
}

export function shortSha(sha: string | null | undefined): string {
  if (!sha) return "-";
  return sha.length > 12 ? sha.slice(0, 12) : sha;
}

export function replayProofLabel(run: ReplayRunItem, detail?: RegressionCIRunDetailResponse | null): string {
  const status = normalizeStatus(run, detail);
  if (status === "not_verified") return "No trusted replay";
  const rawMode =
    stringField(detail?.report, "replay_mode") ??
    stringField(detail?.report, "executor_replay_mode") ??
    run.executor_replay_mode ??
    run.replay_mode ??
    "";
  const mode = rawMode.trim().toLowerCase().replaceAll("-", "_");
  if (mode === "real_llm") return "Managed provider replay";
  if (mode === "mocked_tool") return "Repository replay";
  if (mode === "frozen_rag") return "Frozen RAG replay";
  if (mode === "sandbox" || mode === "live_sandbox") return "Sandbox replay";
  if (mode === "shadow") return "Shadow comparison";
  return "No trusted replay";
}

export function replayProofBadgeClass(run: ReplayRunItem, detail?: RegressionCIRunDetailResponse | null): string {
  return replayProofLabel(run, detail) === "No trusted replay" ? "badge-yellow" : "badge-blue";
}

export function githubReport(detail?: RegressionCIRunDetailResponse | null): Record<string, unknown> | null {
  return nestedRecord(detail?.report, "github");
}

export function prUrl(detail?: RegressionCIRunDetailResponse | null): string | null {
  const github = githubReport(detail);
  const direct =
    stringField(detail?.report, "pr_url") ??
    stringField(detail?.report, "github_pr_url") ??
    stringField(detail?.report, "pull_request_url") ??
    stringField(github, "pr_url") ??
    stringField(github, "pull_request_url") ??
    stringField(github, "html_url");
  if (direct) return direct;
  const match = detail?.pr_comment_markdown?.match(/https:\/\/github\.com\/[^\s)]+\/pull\/\d+/);
  return match?.[0] ?? null;
}

export function prNumber(detail?: RegressionCIRunDetailResponse | null): string | null {
  const github = githubReport(detail);
  const numeric =
    numericField(detail?.report, "pr_number") ??
    numericField(detail?.report, "pull_request_number") ??
    numericField(github, "number") ??
    numericField(github, "pr_number");
  if (numeric != null) return String(numeric);
  return stringField(detail?.report, "pr_number") ?? stringField(github, "number");
}

export function prTitle(detail?: RegressionCIRunDetailResponse | null): string | null {
  const github = githubReport(detail);
  return (
    stringField(detail?.report, "pr_title") ??
    stringField(detail?.report, "pull_request_title") ??
    stringField(detail?.report, "title") ??
    stringField(github, "title")
  );
}

export function runTitle(run: ReplayRunItem, detail?: RegressionCIRunDetailResponse | null): string {
  const number = prNumber(detail);
  const title = prTitle(detail);
  if (number && title) return `PR #${number} - ${title}`;
  if (number) return `PR #${number}`;
  if (title) return title;
  return `Run ${run.id}`;
}

export function runMeta(run: ReplayRunItem, detail?: RegressionCIRunDetailResponse | null): string {
  const github = githubReport(detail);
  return (
    stringField(detail?.report, "branch") ??
    stringField(detail?.report, "branch_name") ??
    stringField(detail?.report, "head_ref") ??
    stringField(github, "head_ref") ??
    stringField(github, "branch") ??
    run.trigger
  );
}

export function summaryUrl(run: Pick<ReplayRunItem, "id">, detail?: RegressionCIRunDetailResponse | null): string {
  return (
    stringField(detail?.report, "summary_url") ??
    stringField(detail?.report, "summaryUrl") ??
    stringField(detail?.report, "details_url") ??
    stringField(detail?.report, "detailsUrl") ??
    `/v1/regression-ci/runs/${detail?.run_id ?? run.id}`
  );
}

export function failedProtectedFlows(run: ReplayRunItem, detail?: RegressionCIRunDetailResponse | null): string[] {
  const clusters = detail?.report?.clusters;
  if (Array.isArray(clusters)) {
    const labels = clusters
      .map((cluster) => {
        if (!isRecord(cluster)) return null;
        const label = stringField(cluster, "label") ?? stringField(cluster, "name") ?? "Protected flow";
        const size = numericField(cluster, "size") ?? numericField(cluster, "count");
        const reason = stringField(cluster, "reason") ?? stringField(cluster, "failure_reason");
        const prefix = size == null ? label : `${label} (${size})`;
        return reason ? `${prefix}: ${reason}` : prefix;
      })
      .filter((label): label is string => Boolean(label));
    if (labels.length > 0) return labels;
  }
  const flows = detail?.report?.failed_flows;
  if (Array.isArray(flows)) {
    const labels = flows
      .map((flow) => {
        if (typeof flow === "string") return flow;
        if (!isRecord(flow)) return null;
        const name = stringField(flow, "name") ?? stringField(flow, "flow") ?? stringField(flow, "golden_name") ?? "Protected flow";
        const reason = stringField(flow, "reason") ?? stringField(flow, "failure_reason");
        return reason ? `${name}: ${reason}` : name;
      })
      .filter((label): label is string => Boolean(label));
    if (labels.length > 0) return labels;
  }
  const regressed = failedFlowCount(run, detail) ?? 0;
  if (regressed > 0) return [`${regressed} protected flow${regressed === 1 ? "" : "s"} regressed`];
  return [];
}

export function prCommentPreview(run: ReplayRunItem, detail?: RegressionCIRunDetailResponse | null): string {
  if (detail?.pr_comment_markdown?.trim()) return detail.pr_comment_markdown.trim();
  const status = statusLabel(normalizeStatus(run, detail));
  const rate = formatRate(regressionRate(run, detail));
  return [`Replay CI: ${status}`, `SHA: ${run.git_sha ?? "not captured"}`, `Regression rate: ${rate}`].join("\n");
}

export function goldenSetId(run: ReplayRunItem, detail?: RegressionCIRunDetailResponse | null): string | null {
  return stringField(detail?.report, "golden_set_id") ?? (run.golden_set_id.startsWith("regression-ci:") ? null : run.golden_set_id);
}

export function runNotes(detail?: RegressionCIRunDetailResponse | null): string {
  return (
    stringField(detail?.report, "notes") ??
    stringField(detail?.report, "message") ??
    "No additional run notes captured."
  );
}
