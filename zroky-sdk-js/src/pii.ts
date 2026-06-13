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
const PHONE_RE = /(^|[^\w-])((?:\+?\d[\s-]?){9,14}\d)(?![\w-])/g;
const KEY_RE = /\b(?:sk|rk|pk|zk)[-_](?:live|test|proj)?[-_]?[A-Za-z0-9_-]{16,}\b/g;
const BEARER_RE = /\bBearer\s+[A-Za-z0-9._~+/=-]{16,}\b/gi;

const SYSTEM_IDENTIFIER_KEYS = new Set([
  "callid",
  "eventid",
  "traceid",
  "parentcallid",
  "workflowid",
  "sessionid",
  "requestid",
  "spanid",
  "projectid",
  "promptfingerprint",
  "promptversion",
]);

function maskString(value: string): string {
  return value
    .replace(EMAIL_RE, "[REDACTED_EMAIL]")
    .replace(PHONE_RE, "$1[REDACTED_PHONE]")
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
      if (SECRET_KEYS.has(normalizedKey)) {
        out[key] = "[REDACTED_KEY]";
      } else if (SYSTEM_IDENTIFIER_KEYS.has(normalizedKey)) {
        out[key] = item;
      } else {
        out[key] = maskPayload(item);
      }
    }
    return out as T;
  }
  return value;
}
