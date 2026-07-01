// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

export const DEFAULT_API_BASE = "https://api.zroky.com";

type NodeEnv = { process?: { env: Record<string, string | undefined> } };

export function nodeEnv(): Record<string, string | undefined> | undefined {
  return (globalThis as NodeEnv).process?.env;
}

export function resolveApiBase(endpoint: string | undefined): string {
  const normalized = (endpoint ?? DEFAULT_API_BASE).replace(/\/+$/, "");
  if (normalized.endsWith("/v1/ingest")) {
    return normalized.slice(0, -"/v1/ingest".length).replace(/\/+$/, "") || DEFAULT_API_BASE;
  }
  if (normalized.endsWith("/ingest")) {
    return normalized.slice(0, -"/ingest".length).replace(/\/+$/, "") || DEFAULT_API_BASE;
  }
  return normalized;
}

export function runtimePolicyUrl(endpoint: string | undefined): string {
  return `${resolveApiBase(endpoint)}/v1/runtime-policy/check`;
}

export function apiUrl(endpoint: string | undefined, path: string): string {
  return `${resolveApiBase(endpoint)}${path}`;
}
