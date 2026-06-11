/**
 * Detector / issue category metadata — single source of truth for the UI.
 *
 * Backend emits distinct issue categories across Layer 1 (deterministic
 * fast rules), Layer 2 (statistical baseline drift), and Layer 3 (LLM-as-judge
 * bridge). Previously each dashboard page hardcoded its own subset of 6 codes
 * with no labels for the other 10 — users saw raw snake_case for any new
 * detector. This module fixes that with one map every page imports.
 *
 * Adding a new detector: register it here. Pages auto-pick up label + badge.
 */

export type DetectorCategory =
  // Layer 1 — fast rules (single-call deterministic)
  | "TOKEN_OVERFLOW"
  | "RATE_LIMIT"
  | "AUTH_FAILURE"
  | "PROVIDER_ERROR"
  | "EMPTY_OUTPUT"
  | "OUTPUT_TRUNCATED"
  | "SCHEMA_VIOLATION"
  | "TOOL_SELECTION_FAILURE"
  | "TOOL_CALL_FAILURE"
  | "TOOL_ARGUMENT_MISMATCH"
  | "UNSAFE_ACTION"
  | "TASK_OUTCOME_FAILURE"
  | "LATENCY_ANOMALY"
  // Layer 2 — pattern rules (statistical baseline drift)
  | "LOOP_DETECTED"
  | "COST_SPIKE"
  | "REPEATED_OUTPUT"
  | "OUTPUT_LENGTH_DRIFT"
  | "LATENCY_DRIFT"
  | "ERROR_RATE_DRIFT"
  | "TOKEN_USAGE_DRIFT"
  // Layer 3 — judge-engine bridged categories
  | "HALLUCINATION_RISK"
  | "RAG_GROUNDING_FAILURE"
  | "ACCURACY_REGRESSION";

export type DetectorLayer = "fast" | "pattern" | "judge";

export type DetectorBadgeColor =
  | "red"
  | "accent"
  | "yellow"
  | "purple"
  | "blue"
  | "teal"
  | "gray";

export interface DetectorMeta {
  /** Stable category code as emitted by backend. */
  code: DetectorCategory | string;
  /** Human-readable Title-Case label for headings, badges, and table cells. */
  label: string;
  /** One-line user-facing description for tooltips and detail headers. */
  description: string;
  /** Color token used by `.alert-cat-badge.badge-<color>` styles in globals.css. */
  badgeColor: DetectorBadgeColor;
  /** Default severity floor for this detector (helps when severity is missing). */
  defaultSeverity: "critical" | "high" | "medium" | "low";
  /** Detection layer — used by Layer-attribution badges and filter groups. */
  layer: DetectorLayer;
  /** Inline icon glyph (single Unicode char) for compact list rows. */
  icon: string;
}

const CATALOG: Record<DetectorCategory, DetectorMeta> = {
  // ── Layer 1 ────────────────────────────────────────────────────────────
  TOKEN_OVERFLOW: {
    code: "TOKEN_OVERFLOW",
    label: "Token Overflow",
    description: "Request exceeded the model's max context window.",
    badgeColor: "accent",
    defaultSeverity: "high",
    layer: "fast",
    icon: "⛔",
  },
  RATE_LIMIT: {
    code: "RATE_LIMIT",
    label: "Rate Limit",
    description: "Provider returned 429 — quota or RPM/TPM cap hit.",
    badgeColor: "yellow",
    defaultSeverity: "medium",
    layer: "fast",
    icon: "⏳",
  },
  AUTH_FAILURE: {
    code: "AUTH_FAILURE",
    label: "Auth Failure",
    description: "Provider rejected the API key — production-down risk.",
    badgeColor: "red",
    defaultSeverity: "critical",
    layer: "fast",
    icon: "🔒",
  },
  PROVIDER_ERROR: {
    code: "PROVIDER_ERROR",
    label: "Provider Error",
    description: "Upstream provider returned 5xx or unexpected failure.",
    badgeColor: "gray",
    defaultSeverity: "high",
    layer: "fast",
    icon: "⚠",
  },
  EMPTY_OUTPUT: {
    code: "EMPTY_OUTPUT",
    label: "Empty Output",
    description: "Call succeeded but the response payload was blank.",
    badgeColor: "accent",
    defaultSeverity: "high",
    layer: "fast",
    icon: "∅",
  },
  OUTPUT_TRUNCATED: {
    code: "OUTPUT_TRUNCATED",
    label: "Output Truncated",
    description: "Response hit `max_tokens` before the model finished.",
    badgeColor: "accent",
    defaultSeverity: "high",
    layer: "fast",
    icon: "✂",
  },
  SCHEMA_VIOLATION: {
    code: "SCHEMA_VIOLATION",
    label: "Schema Violation",
    description: "Response did not parse against the declared output schema.",
    badgeColor: "purple",
    defaultSeverity: "high",
    layer: "fast",
    icon: "{}",
  },
  TOOL_SELECTION_FAILURE: {
    code: "TOOL_SELECTION_FAILURE",
    label: "Wrong Tool",
    description: "Agent chose a tool outside the expected or allowed path.",
    badgeColor: "purple",
    defaultSeverity: "high",
    layer: "fast",
    icon: "T",
  },
  TOOL_CALL_FAILURE: {
    code: "TOOL_CALL_FAILURE",
    label: "Tool Error",
    description: "A required tool failed, timed out, or returned an unusable result.",
    badgeColor: "red",
    defaultSeverity: "high",
    layer: "fast",
    icon: "!",
  },
  TOOL_ARGUMENT_MISMATCH: {
    code: "TOOL_ARGUMENT_MISMATCH",
    label: "Bad Tool Args",
    description: "Tool arguments did not satisfy the expected argument contract.",
    badgeColor: "purple",
    defaultSeverity: "high",
    layer: "fast",
    icon: "{}",
  },
  UNSAFE_ACTION: {
    code: "UNSAFE_ACTION",
    label: "Unsafe Action",
    description: "Sensitive action path lacked policy approval evidence.",
    badgeColor: "red",
    defaultSeverity: "critical",
    layer: "fast",
    icon: "!",
  },
  TASK_OUTCOME_FAILURE: {
    code: "TASK_OUTCOME_FAILURE",
    label: "Outcome Failure",
    description: "The customer-facing task failed even if the model call completed.",
    badgeColor: "red",
    defaultSeverity: "high",
    layer: "fast",
    icon: "X",
  },
  LATENCY_ANOMALY: {
    code: "LATENCY_ANOMALY",
    label: "Latency Issue",
    description: "Single call latency exceeded the project's p99 ceiling.",
    badgeColor: "yellow",
    defaultSeverity: "medium",
    layer: "fast",
    icon: "🐢",
  },

  // ── Layer 2 ────────────────────────────────────────────────────────────
  LOOP_DETECTED: {
    code: "LOOP_DETECTED",
    label: "Loop Detected",
    description: "Agent emitted the same step/output repeatedly — infinite loop signature.",
    badgeColor: "purple",
    defaultSeverity: "high",
    layer: "pattern",
    icon: "🔁",
  },
  COST_SPIKE: {
    code: "COST_SPIKE",
    label: "Cost Spike",
    description: "Project spend exceeded the rolling baseline by a material margin.",
    badgeColor: "red",
    defaultSeverity: "critical",
    layer: "pattern",
    icon: "💸",
  },
  REPEATED_OUTPUT: {
    code: "REPEATED_OUTPUT",
    label: "Repeated Output",
    description: "Same response body returned across multiple distinct inputs — cache or stub bug.",
    badgeColor: "purple",
    defaultSeverity: "medium",
    layer: "pattern",
    icon: "♻",
  },
  OUTPUT_LENGTH_DRIFT: {
    code: "OUTPUT_LENGTH_DRIFT",
    label: "Output Length Drift",
    description: "Completion length materially diverged from the trailing baseline.",
    badgeColor: "blue",
    defaultSeverity: "medium",
    layer: "pattern",
    icon: "📏",
  },
  LATENCY_DRIFT: {
    code: "LATENCY_DRIFT",
    label: "Latency Drift",
    description: "Rolling p95 latency drifted upward vs the project's historical window.",
    badgeColor: "yellow",
    defaultSeverity: "medium",
    layer: "pattern",
    icon: "📈",
  },
  ERROR_RATE_DRIFT: {
    code: "ERROR_RATE_DRIFT",
    label: "Error Rate Drift",
    description: "Recent failure rate is materially above the rolling baseline.",
    badgeColor: "red",
    defaultSeverity: "critical",
    layer: "pattern",
    icon: "📉",
  },
  TOKEN_USAGE_DRIFT: {
    code: "TOKEN_USAGE_DRIFT",
    label: "Token Usage Drift",
    description: "Average tokens-per-call moved meaningfully — likely prompt or context bloat.",
    badgeColor: "blue",
    defaultSeverity: "medium",
    layer: "pattern",
    icon: "🧮",
  },

  // ── Layer 3 ────────────────────────────────────────────────────────────
  HALLUCINATION_RISK: {
    code: "HALLUCINATION_RISK",
    label: "Hallucination Risk",
    description: "Judge scored groundedness below the trust floor — unsupported claims present.",
    badgeColor: "red",
    defaultSeverity: "critical",
    layer: "judge",
    icon: "👻",
  },
  RAG_GROUNDING_FAILURE: {
    code: "RAG_GROUNDING_FAILURE",
    label: "RAG Grounding Failure",
    description: "Answer was not sufficiently supported by retrieved evidence.",
    badgeColor: "red",
    defaultSeverity: "high",
    layer: "judge",
    icon: "R",
  },
  ACCURACY_REGRESSION: {
    code: "ACCURACY_REGRESSION",
    label: "Accuracy Regression",
    description: "Judge accuracy score dropped below floor or rolling baseline — answers are wrong.",
    badgeColor: "red",
    defaultSeverity: "critical",
    layer: "judge",
    icon: "🎯",
  },
};

// ── Lookup helpers ─────────────────────────────────────────────────────────

/**
 * Resolve any backend-supplied category string to its metadata.
 *
 * Unknown codes are gracefully title-cased ("FOO_BAR" → "Foo Bar") and assigned
 * a neutral gray badge so a brand-new backend category still renders cleanly
 * without a UI deploy.
 */
export function getDetectorMeta(code: string | null | undefined): DetectorMeta {
  if (!code) {
    return unknownMeta("Unknown");
  }
  const upper = code.trim().toUpperCase();
  const hit = CATALOG[upper as DetectorCategory];
  if (hit) return hit;
  return unknownMeta(upper);
}

function unknownMeta(code: string): DetectorMeta {
  const label = code
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
  return {
    code,
    label,
    description: "Detector category not yet recognized by this dashboard build.",
    badgeColor: "gray",
    defaultSeverity: "medium",
    layer: "fast",
    icon: "•",
  };
}

/** CSS class for a colored category badge. Matches existing `.alert-cat-badge.badge-<color>` pattern. */
export function detectorBadgeClass(code: string | null | undefined): string {
  const meta = getDetectorMeta(code);
  return `alert-cat-badge badge-${meta.badgeColor}`;
}

/** Human-readable label, with safe fallback for unknown codes. */
export function detectorLabel(code: string | null | undefined): string {
  return getDetectorMeta(code).label;
}

/** Ordered list of all known categories — useful for filter dropdowns. */
export function allDetectorCategories(): DetectorMeta[] {
  return Object.values(CATALOG);
}

/** Subset by layer — useful for "Layer 1 / Layer 2 / Layer 3" filter groups. */
export function detectorCategoriesByLayer(layer: DetectorLayer): DetectorMeta[] {
  return allDetectorCategories().filter((m) => m.layer === layer);
}

/**
 * Quick-filter set shown on alerts page above the full filter dropdown.
 * Curated for "highest-incident-value" categories — kept short so the chip row
 * doesn't overflow on mobile.
 */
export const QUICK_FILTER_CATEGORIES: DetectorCategory[] = [
  "AUTH_FAILURE",
  "LOOP_DETECTED",
  "COST_SPIKE",
  "HALLUCINATION_RISK",
  "ACCURACY_REGRESSION",
  "ERROR_RATE_DRIFT",
];

/** Severity → badge color (used by severity-only pills, independent of detector code). */
export function severityBadgeColor(
  sev: string | null | undefined,
): DetectorBadgeColor {
  switch ((sev ?? "").toLowerCase()) {
    case "critical":
      return "red";
    case "high":
      return "red";
    case "medium":
      return "yellow";
    case "low":
      return "gray";
    default:
      return "gray";
  }
}
