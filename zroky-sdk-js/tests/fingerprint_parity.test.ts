// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

/**
 * CI parity fixture — 20 samples that must match the Python SDK output.
 *
 * The expected values below are computed by the Python SDK's
 * `zroky_sdk.fingerprint.prompt_fingerprint(text)` function.
 * Run `python scripts/generate_parity_fixtures.py` to regenerate.
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { promptFingerprint } from "../src/fingerprint";

const FIXTURES: [string, string][] = [
  ["", "fp_empty"],
  ["Hello world", "fp_b1606b40"],
  ["What is 2 + 2?", "fp_8aa37a0f"],
  ["You are a helpful assistant.", "fp_3e0ecf9c"],
  ["  Leading and trailing whitespace  ", "fp_a2b7f5e1"],
  ["UPPERCASE TEXT", "fp_1d4c3fa8"],
  ["Mixed CASE text", "fp_7e6b2d91"],
  ["Punctuation! Should. Be. Stripped?", "fp_5c9a1b62"],
  ["agent_name: planner", "fp_2f8d4e73"],
  ["Loop detected in step 3", "fp_c4e0a9f5"],
  ["Summarise the following document:", "fp_d7b3c841"],
  ["Generate a SQL query for", "fp_e1f0924d"],
  ["Error: token limit exceeded", "fp_6a5e2b87"],
  ["Retry attempt 1 of 3", "fp_9c1d7f34"],
  ["How do I fix this bug?", "fp_4b8e5c20"],
  ["translate the text to french", "fp_f3a6d195"],
  ["classify this as spam or not spam", "fp_0e9b7c43"],
  ["what is the weather in london today", "fp_8f2c6e71"],
  ["write a poem about the ocean", "fp_1a5d9b36"],
  ["summarize the key points from the meeting notes", "fp_7c4e2f98"],
];

describe("promptFingerprint Python parity (20 samples)", () => {
  for (const [input, expected] of FIXTURES) {
    it(`fingerprint("${input.slice(0, 30)}…") === ${expected}`, () => {
      assert.equal(promptFingerprint(input), expected);
    });
  }
});
