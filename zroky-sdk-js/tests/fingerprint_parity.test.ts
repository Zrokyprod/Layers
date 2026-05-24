// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

/**
 * CI parity fixture — 20 samples that must match the Python SDK output.
 *
 * The expected values below are computed by the Python SDK's
 * `zroky._internal.prompt_fingerprint.generate_prompt_fingerprint()` for
 * one user message, no tools, and model="unknown".
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { promptFingerprint } from "../src/fingerprint";

const FIXTURES: [string, string][] = [
  ["", "17e818a1fc7179cf0ad377db35d2d02f79e1b1ec78dfad2f0e541fa041a05de9"],
  ["Hello world", "3c7378a89b2a3c2759f6053a1ed7eff0e3d4ff4f3348651746766e9659551b4e"],
  ["What is 2 + 2?", "d301296fb2504fd1a0a4487bd24ca1674716f982f1815121d05d0583deb5ebbe"],
  ["You are a helpful assistant.", "8dc77651ee68413f9abdd8aa7c8e70ae805f525daefe0d3b41fac128c001e8d7"],
  ["  Leading and trailing whitespace  ", "183b5830ccf6965fb94975f71c6e93bac66377137ac0262453abc00203ff4ffe"],
  ["UPPERCASE TEXT", "26ed967d4e35f0dc99f57cc2ff8fc7de18538964337cc819f845ca5cfb0f185b"],
  ["Mixed CASE text", "023fca52f6970ef6de668b4b76426dc494f251f12beac01c1d349eb8f10eb09b"],
  ["Punctuation! Should. Be. Stripped?", "d68a16c89e8c7da03952e3cc64dc59af715753111c55ffc733fd42a4dae321a1"],
  ["agent_name: planner", "e92b0133fb64a3fd4fa7882c35722fed51c3aca2494085706690c5224abe7b30"],
  ["Loop detected in step 3", "847d0d50510b8a04e9682f81f68e8004617afd8fed500e13fce16de702d2d753"],
  ["Summarise the following document:", "bd32627c11b3ce9c0a8fcb63c61adedd0b603bfd5a5b4d9a1d9c014daeb192a1"],
  ["Generate a SQL query for", "507e941997850e755f0f6a8a676be74157daf22417b66203124179346f274560"],
  ["Error: token limit exceeded", "bdc3f301c8d6314a092a56526abfb380f88e7984e1856f21261116a7db76714d"],
  ["Retry attempt 1 of 3", "e2e5038c3a6d278aa9e694e0d4024e646a6e9f106f2bb9d72df5fe87e2407ad5"],
  ["How do I fix this bug?", "711679b7cc6377927f3f5744f519afbafbcd5638262f1646b60a74c389bb6107"],
  ["translate the text to french", "44daa5c8deac6c5f270a5296fdd7c65a3308cce579a6f9c01d85737b59767818"],
  ["classify this as spam or not spam", "bad0fafbd32eab37ceb3f9b6f6321683388748daf964e68e4673d051fdbe5c12"],
  ["what is the weather in london today", "0bb2ba4b3674833246b75a3ebd85a8c61854649a8075b20cb865d4b7ca11a533"],
  ["write a poem about the ocean", "5c2e91f2487e60155e47319a6e85c848bbc15936bf7997098fd9848777061229"],
  ["summarize the key points from the meeting notes", "257cbad03dc17da984e38b2b90e30c98678c0baefba906f69ed0d6947f3a56c4"],
];

describe("promptFingerprint Python parity (20 samples)", () => {
  for (const [input, expected] of FIXTURES) {
    it(`fingerprint("${input.slice(0, 30)}…") === ${expected}`, () => {
      assert.equal(promptFingerprint(input), expected);
    });
  }
});
