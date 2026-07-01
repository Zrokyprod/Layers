/**
 * SDK identity — single source of truth for the landing surface.
 *
 * The renamed SDK is "zroky-ai"; its scoped package form is "@zroky-ai/sdk".
 * The landing snippet, the install line, and the copy-to-clipboard handler all
 * import from here so the rendered text and the clipboard text can never
 * diverge (Requirement 7.1–7.4).
 *
 * The prior identifier "@zroky/sdk" and the strings "zroky-sdk" / "new Zroky"
 * are forbidden anywhere in rendered landing output (Requirement 7.5, 7.6,
 * 11.4, 11.5). This module is intentionally tiny, fully typed, and free of any
 * DOM or runtime dependency so it is importable by both server components and
 * client islands.
 *
 * Derived strings (install command, import statement) are built from `scoped`
 * rather than hardcoded so a single edit keeps every call site consistent.
 */

const SCOPED = "@zroky-ai/sdk";
const PROSE = "zroky-ai";

export const SDK = {
  /** Scoped package name used in code, install commands, and imports. */
  scoped: SCOPED,
  /** Plain product name used in descriptive prose. */
  prose: PROSE,
  /** Install command shown in the Quickstart / Capture section. */
  install: `npm install ${SCOPED}`,
  /** Verbatim, contract-locked import statement for the legacy capture SDK snippet. */
  importStatement: `import { init, traceRun, wrap } from "${SCOPED}";`,
  /** Verbatim, contract-locked import statement for verified-action setup. */
  verifiedActionImportStatement: `import { init, verifiedAction, awaitActionProof } from "${SCOPED}";`,
} as const;

export type SdkIdentity = typeof SDK;
