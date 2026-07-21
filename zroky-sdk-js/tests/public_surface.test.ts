import assert from "node:assert/strict";
import test from "node:test";

import * as sdk from "../src/index";

test("public SDK surface excludes old capture and prompt-fingerprint exports", () => {
  const exported = new Set(Object.keys(sdk));

  for (const oldName of [
    "promptFingerprint",
    "captureHandoff",
    "captureMemory",
    "capturePolicyDecision",
    "captureRetrieval",
    "captureToolCall",
  ]) {
    assert.equal(exported.has(oldName), false, `${oldName} must stay out of the final public SDK`);
  }
});

test("public SDK surface keeps final policy, action, and outcome entrypoints", () => {
  const exported = new Set(Object.keys(sdk));

  for (const finalName of [
    "guard",
    "preExecutionGuard",
    "protect",
    "verifiedAction",
    "awaitActionProof",
    "verifyOutcome",
    "outcome",
  ]) {
    assert.equal(exported.has(finalName), true, `${finalName} must remain public`);
  }
});
