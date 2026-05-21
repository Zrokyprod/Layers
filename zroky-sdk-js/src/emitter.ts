// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

import type { CapturePayload, ZrokyConfig } from "./types";

const DEFAULT_ENDPOINT = "https://api.zroky.com/v1/ingest";

export async function emit(payload: CapturePayload, config: ZrokyConfig): Promise<void> {
  if (config.disabled) return;
  type NodeEnv = { process?: { env: Record<string, string | undefined> } };
  const nodeEnv = (globalThis as NodeEnv).process?.env;
  const projectId = config.projectId ?? nodeEnv?.["ZROKY_PROJECT_ID"];
  const apiKey = config.apiKey ?? nodeEnv?.["ZROKY_API_KEY"];
  if (!projectId || !apiKey) return;

  const endpoint = config.endpoint ?? DEFAULT_ENDPOINT;
  const body = JSON.stringify({ ...payload, project_id: projectId, timestamp_utc: new Date().toISOString() });

  try {
    await fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body,
      // keepalive allows the request to complete even if the page unloads
      keepalive: true,
    });
  } catch {
    // Best-effort: never throw from emit
  }
}
