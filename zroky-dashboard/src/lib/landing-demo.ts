/**
 * Landing demo logic — pure, testable helpers with no DOM dependency.
 *
 * These functions back the interactive landing-page islands (the Loop tabs,
 * the dashboard ModuleSwitcher, and the progressive-disclosure controls) but
 * deliberately contain no React, no browser APIs, and no styling so they can be
 * imported by both server components and `"use client"` islands and exercised
 * directly by property-based + example tests.
 *
 * Contracts are intentionally *total*: every helper returns a defined value for
 * every input it accepts (selection helpers return `undefined` only for empty
 * collections; over a non-empty collection they always return a member). This
 * keeps the islands robust when a requested step/module key is missing or when
 * content cannot be retrieved (Requirement 3.10).
 *
 * Supports Correctness Properties 4 (summary length bound), 5 (disclosure
 * round-trip), 6 (selection returns requested-or-current), and 7 (cyclic,
 * total module advance).
 */

/** The three run outcomes that drive the Verdict_System (Requirement 5.4). */
export type Verdict = "pass" | "block" | "review";

/**
 * Rich content for a single Loop step / dashboard module panel. Kept loose and
 * presentation-agnostic so islands can render whatever evidence a step carries
 * (payloads, diffs, gate results) without the pure logic depending on shape.
 */
export interface LoopDetail {
  /** Optional panel heading (e.g. the contract-locked Replay step heading). */
  heading?: string;
  /** Primary body copy for the panel. */
  body: string;
  /** Optional verbatim evidence block (payload, diff, event stream, etc.). */
  evidence?: string;
}

/** A single step in The Loop (Capture → Diagnose → Replay → Promote → Gate). */
export interface LoopStep {
  /** Stable identity used for selection. */
  key: string;
  /** Zero-based position used for ordering and the lifecycle rail. */
  index: number;
  /** Short tab/step title. */
  title: string;
  /** The run outcome this step demonstrates, for Verdict_System treatment. */
  verdict: Verdict;
  /** Collapsed, length-bounded summary shown before disclosure. */
  summary: string;
  /** Full panel content revealed on selection / disclosure. */
  detail: LoopDetail;
}

/** A dashboard module surfaced by the ModuleSwitcher. */
export interface Module {
  /** Stable identity used for selection and auto-advance. */
  key: string;
  /** Human-readable label shown in the switcher. */
  label: string;
  /** Optional collapsed summary for the module. */
  summary?: string;
  /** Optional full panel content. */
  detail?: LoopDetail;
}

/** State of a single progressive-disclosure control. */
export interface DisclosureState {
  expanded: boolean;
}

/** Default maximum length for a collapsed evidence summary (Requirement 2.1). */
export const SUMMARY_MAX = 280;

const ELLIPSIS = "…";
const WHITESPACE = /\s+/g;

/**
 * Selection helper for the Loop tabs and the ModuleSwitcher.
 *
 * Total contract: returns the item whose `key` matches `key` when it exists;
 * otherwise falls back to the item matching `currentKey` (the currently
 * displayed item) so a missing/unavailable selection leaves the panel
 * unchanged (Requirement 3.10); otherwise returns the first item. Returns
 * `undefined` only when `items` is empty.
 *
 * Validates Property 6.
 */
export function selectStep<TItem extends { key: string }>(
  items: readonly TItem[],
  key: string,
  currentKey?: string,
): TItem | undefined {
  if (items.length === 0) {
    return undefined;
  }
  const requested = items.find((item) => item.key === key);
  if (requested) {
    return requested;
  }
  const current =
    currentKey != null ? items.find((item) => item.key === currentKey) : undefined;
  return current ?? items[0];
}

/**
 * Cyclic advance for the ModuleSwitcher auto-advance.
 *
 * Total over non-empty lists: returns the module following `currentKey`,
 * wrapping from the last module back to the first. When `currentKey` is not in
 * the list, advancing begins at the first module. Returns `undefined` only when
 * `modules` is empty.
 *
 * Validates Property 7.
 */
export function nextModule<TModule extends { key: string }>(
  modules: readonly TModule[],
  currentKey: string,
): TModule | undefined {
  if (modules.length === 0) {
    return undefined;
  }
  const currentIndex = modules.findIndex((module) => module.key === currentKey);
  const nextIndex = currentIndex < 0 ? 0 : (currentIndex + 1) % modules.length;
  return modules[nextIndex];
}

/**
 * Pure boolean flip for a disclosure control. Applying it twice returns the
 * original state; applying it once always inverts the state.
 *
 * Validates Property 5.
 */
export function toggleDisclosure(state: DisclosureState): DisclosureState {
  return { expanded: !state.expanded };
}

/**
 * Produce a length-bounded, whitespace-collapsed summary of `text`.
 *
 * The result is at most `max` characters for any input. When the collapsed text
 * fits, it is returned as-is; otherwise it is truncated with a trailing ellipsis
 * kept within the bound. A `max` of zero or less yields an empty string.
 *
 * Validates Property 4.
 */
export function summarize(text: string, max = SUMMARY_MAX): string {
  const collapsed = text.replace(WHITESPACE, " ").trim();
  if (max <= 0) {
    return "";
  }
  if (collapsed.length <= max) {
    return collapsed;
  }
  if (max <= ELLIPSIS.length) {
    return collapsed.slice(0, max);
  }
  return collapsed.slice(0, max - ELLIPSIS.length).trimEnd() + ELLIPSIS;
}
