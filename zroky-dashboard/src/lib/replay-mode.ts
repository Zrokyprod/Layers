import type { ReplayMode } from "./api";

export const DEFAULT_VERIFICATION_REPLAY_MODE: ReplayMode = "real_llm";
export const STUB_REPLAY_MODE: ReplayMode = "stub";

export const REPLAY_MODE_OPTIONS: { value: ReplayMode; label: string; proof: string }[] = [
  { value: "real_llm", label: "real_llm", proof: "real comparison" },
  { value: "mocked-tool", label: "mocked-tool", proof: "frozen tool outputs required" },
  { value: "live-sandbox", label: "live-sandbox", proof: "sandbox worker required" },
  { value: "shadow", label: "shadow", proof: "side-by-side comparison" },
  { value: "stub", label: "stub", proof: "sanity only" },
];

export function replayModeLabel(mode: string): string {
  return REPLAY_MODE_OPTIONS.find((option) => option.value === mode)?.label ?? mode;
}

export function replayModeProof(mode: string): string {
  return REPLAY_MODE_OPTIONS.find((option) => option.value === mode)?.proof ?? "proof unknown";
}

export function replayVerificationLabel(mode: string, verifiedFix: boolean, verificationStatus: string): string {
  if (mode === STUB_REPLAY_MODE) return "sanity_check_only";
  return verifiedFix ? "verified fix" : verificationStatus;
}

export function replayVerifiedFix(mode: string, verifiedFix: boolean): boolean {
  return mode !== STUB_REPLAY_MODE && verifiedFix;
}
