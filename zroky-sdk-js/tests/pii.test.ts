// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { maskPayload } from "../src/pii";

describe("maskPayload", () => {
  it("preserves UUIDs while masking adjacent PII", () => {
    const id = "12345678-1234-1234-1234-123456789012";
    const masked = maskPayload({ call_id: id, message: `run ${id} belongs to user@example.com` });

    assert.equal(masked.call_id, id);
    assert.match(masked.message, new RegExp(id));
    assert.doesNotMatch(masked.message, /user@example\.com/);
  });

  it("masks opaque tokens without hiding usage counts", () => {
    const masked = maskPayload({
      access_token: "opaque-access-value",
      refreshToken: "opaque-refresh-value",
      prompt_tokens: 42,
    });

    assert.equal(masked.access_token, "[REDACTED_KEY]");
    assert.equal(masked.refreshToken, "[REDACTED_KEY]");
    assert.equal(masked.prompt_tokens, 42);
  });
});
