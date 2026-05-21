// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

/**
 * Prompt fingerprinting — parity with Python SDK implementation.
 * Uses a simple 32-bit FNV-1a hash over the normalised prompt text.
 * CI parity fixture: tests/fingerprint_parity.test.ts verifies 20 samples.
 */

const FNV_PRIME = 0x01000193;
const FNV_OFFSET = 0x811c9dc5;

function fnv1a32(str: string): number {
  let hash = FNV_OFFSET;
  for (let i = 0; i < str.length; i++) {
    hash ^= str.charCodeAt(i);
    hash = Math.imul(hash, FNV_PRIME) >>> 0;
  }
  return hash >>> 0;
}

function normalise(text: string): string {
  return text
    .toLowerCase()
    .replace(/\s+/g, " ")
    .replace(/[^\w\s]/g, "")
    .trim();
}

export function promptFingerprint(prompt: string | undefined | null): string {
  if (!prompt) return "fp_empty";
  const h = fnv1a32(normalise(prompt));
  return "fp_" + h.toString(16).padStart(8, "0");
}
