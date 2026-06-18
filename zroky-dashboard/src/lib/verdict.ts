/**
 * Verdict mapping + accent-color helpers — pure logic, no DOM.
 *
 * The redesign uses a monochrome foundation where color appears *only* to
 * express the Verdict_System (pass = green, block = red, review = amber) plus a
 * single restrained brand-accent. This module is the single source of truth for
 * mapping a run outcome to its visual token and for validating that a color is
 * one of the allowed accents (Requirements 5.4–5.7).
 *
 * Design decisions:
 * - `verdictToken` is TOTAL: "pass", "block", "review" map to dedicated tokens,
 *   and every other string returns the single neutral-default token, which is
 *   distinct from all three verdict treatments (Requirement 5.6).
 * - Token `fg`/`border` reference the meaning-only CSS custom properties from
 *   `globals.css` (task 1.1) so the helper stays consistent with the design
 *   system; `bg` uses the soft verdict tints.
 * - `isVerdictColor` is a case-normalized membership check over the allowed
 *   accent set: the three verdict colors plus the one brand accent.
 *
 * Kept free of any DOM or runtime dependency so it is importable by both server
 * components and client islands, and trivially unit/property testable.
 */

/** The three defined run outcomes. */
export type Verdict = "pass" | "block" | "review";

/**
 * The visual treatment for a single outcome. `fg` and `border` reference the
 * meaning-only CSS custom properties; `bg` uses the matching soft tint.
 */
export type VerdictToken = {
  fg: string;
  bg: string;
  border: string;
  label: string;
};

/** The dedicated tokens for the three defined verdicts. */
const PASS_TOKEN: VerdictToken = {
  fg: "var(--zlp-pass)",
  bg: "var(--zlp-pass-soft)",
  border: "var(--zlp-pass)",
  label: "Pass",
};

const BLOCK_TOKEN: VerdictToken = {
  fg: "var(--zlp-block)",
  bg: "var(--zlp-block-soft)",
  border: "var(--zlp-block)",
  label: "Block",
};

const REVIEW_TOKEN: VerdictToken = {
  fg: "var(--zlp-review)",
  bg: "var(--zlp-review-soft)",
  border: "var(--zlp-review)",
  label: "Review",
};

/**
 * The single neutral-default token, distinct from all three verdict treatments
 * (Requirement 5.6). It references the neutral-verdict token (tertiary grey),
 * keeping off-path outcomes monochrome rather than borrowing a verdict hue.
 */
const NEUTRAL_TOKEN: VerdictToken = {
  fg: "var(--zlp-neutral-verdict)",
  bg: "rgba(103, 110, 124, 0.12)",
  border: "var(--zlp-line-strong)",
  label: "Neutral",
};

const VERDICT_TOKENS: Record<Verdict, VerdictToken> = {
  pass: PASS_TOKEN,
  block: BLOCK_TOKEN,
  review: REVIEW_TOKEN,
};

/**
 * Map a run outcome to its visual token. TOTAL over all strings: "pass",
 * "block", and "review" return their dedicated tokens; any other value returns
 * the single neutral-default token (Requirements 5.5, 5.6).
 */
export function verdictToken(outcome: string): VerdictToken {
  if (outcome === "pass" || outcome === "block" || outcome === "review") {
    return VERDICT_TOKENS[outcome];
  }
  return NEUTRAL_TOKEN;
}

/**
 * The exhaustive set of color values allowed to appear anywhere on the surface:
 * the three verdict colors plus the single brand accent. Used to enforce the
 * monochrome-elsewhere invariant (Requirements 5.4, 5.7).
 */
const ALLOWED_ACCENT_COLORS: ReadonlySet<string> = new Set([
  "#3bd68b", // pass (green)
  "#fb6a6a", // block (red)
  "#fbbf24", // review (amber)
  "#7c5cff", // brand accent
]);

/**
 * Membership check over the allowed accent set (the three verdict colors plus
 * the single brand accent). Case is normalized so "#3BD68B" and "#3bd68b" both
 * match (Requirements 5.4, 5.7).
 */
export function isVerdictColor(hex: string): boolean {
  return ALLOWED_ACCENT_COLORS.has(hex.trim().toLowerCase());
}
