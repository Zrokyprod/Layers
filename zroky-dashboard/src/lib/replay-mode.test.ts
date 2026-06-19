import { describe, expect, it } from "vitest";

import {
  DEFAULT_VERIFICATION_REPLAY_MODE,
  REPLAY_MODE_OPTIONS,
  STUB_REPLAY_MODE,
  replayVerificationLabel,
  replayVerifiedFix,
} from "./replay-mode";

describe("replay mode strictness", () => {
  it("defaults new verification workflows to real_llm, not stub", () => {
    expect(DEFAULT_VERIFICATION_REPLAY_MODE).toBe("real_llm");
    expect(REPLAY_MODE_OPTIONS[0].value).toBe(DEFAULT_VERIFICATION_REPLAY_MODE);
    expect(REPLAY_MODE_OPTIONS[0].label).toBe("Managed provider replay");
  });

  it("never treats stub replay as a verified fix", () => {
    expect(replayVerifiedFix(STUB_REPLAY_MODE, true)).toBe(false);
    expect(replayVerificationLabel(STUB_REPLAY_MODE, true, "verified_fix")).toBe("sanity_check_only");
  });

  it("requires backend verified_fix evidence for non-stub modes", () => {
    expect(replayVerifiedFix(DEFAULT_VERIFICATION_REPLAY_MODE, false)).toBe(false);
    expect(replayVerifiedFix(DEFAULT_VERIFICATION_REPLAY_MODE, true)).toBe(true);
  });
});
