// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

const SECRET_KEYS = new Set([
  "api_key",
  "apikey",
  "authorization",
  "password",
  "secret",
  "token",
  "access_token",
  "refresh_token",
]);

const EMAIL_RE = /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi;
const PHONE_RE = /\b(?:\+?\d[\s-]?){9,14}\d\b/g;
const KEY_RE = /\b(?:sk|rk|pk|zk)[-_](?:live|test|proj)?[-_]?[A-Za-z0-9_-]{16,}\b/g;
const BEARER_RE = /\bBearer\s+[A-Za-z0-9._~+/=-]{16,}\b/gi;

function maskString(value: string): string {
  return value
    .replace(EMAIL_RE, "[REDACTED_EMAIL]")
    .replace(PHONE_RE, "[REDACTED_PHONE]")
    .replace(KEY_RE, "[REDACTED_KEY]")
    .replace(BEARER_RE, "Bearer [REDACTED_KEY]");
}

export function maskPayload<T>(value: T): T {
  if (typeof value === "string") return maskString(value) as T;
  if (Array.isArray(value)) return value.map((item) => maskPayload(item)) as T;
  if (value && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
      const normalizedKey = key.toLowerCase().replace(/[^a-z0-9]/g, "");
      out[key] = SECRET_KEYS.has(normalizedKey) ? "[REDACTED_KEY]" : maskPayload(item);
    }
    return out as T;
  }
  return value;
}
