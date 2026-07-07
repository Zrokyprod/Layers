// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

/**
 * outcome() — attach a business cost to a Zroky call.
 *
 * Usage:
 *   import { outcome } from "@zroky-ai/sdk";
 *
 *   // After your AI call:
 *   const result = await wrappedClient.chat(params);
 *   const callId = result._zroky_call_id;
 *
 *   // When a downstream business event occurs:
 *   outcome(callId, {
 *     type: "refund_issued",
 *     amountUsd: 49.00,
 *     metadata: { orderId: "ORD-9182" },
 *   });
 *
 * Fire-and-forget: never throws, never blocks.
 */

import type { ZrokyConfig } from "./types";
import { nodeEnv, resolveApiBase } from "./api";

export interface OutcomeOptions {
  /** Business event type: refund_issued | ticket_escalated | human_handoff | churn | compliance_fine | retry_cost | custom */
  type: string;
  /** Monetary cost in USD (default 0) */
  amountUsd?: number;
  /** When the event happened (defaults to now) */
  occurredAt?: Date;
  /** Dedup key — same key always returns the same server row */
  idempotencyKey?: string;
  /** Arbitrary context (order_id, customer_id, …) */
  metadata?: Record<string, unknown>;
}

let _config: ZrokyConfig | null = null;

/** @internal — called by init() */
export function _setOutcomeConfig(config: ZrokyConfig): void {
  _config = config;
}

/**
 * Attach a business-outcome cost to a Zroky call.
 * Fire-and-forget — never throws, never blocks the caller.
 */
export function outcome(callId: string, opts: OutcomeOptions): void {
  if (!_config || _config.disabled) return;

  const env = nodeEnv();
  const apiKey = _config.apiKey ?? env?.["ZROKY_API_KEY"];
  const projectId = _config.projectId ?? env?.["ZROKY_PROJECT_ID"] ?? env?.["ZROKY_PROJECT"];
  if (!apiKey || !projectId) return;

  const endpoint = resolveApiBase(_config.endpoint ?? env?.["ZROKY_API_URL"] ?? env?.["ZROKY_ENDPOINT"]);
  const url = `${endpoint}/v1/outcomes`;

  const key = opts.idempotencyKey ?? `${callId}:${opts.type}`;
  const body = JSON.stringify({
    call_id: callId,
    outcome_type: opts.type,
    amount_usd: opts.amountUsd ?? 0,
    occurred_at: (opts.occurredAt ?? new Date()).toISOString(),
    idempotency_key: key,
    metadata: opts.metadata ?? null,
  });

  // Fire-and-forget — never block, never throw
  try {
    fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": apiKey,
        "x-project-id": projectId,
        Authorization: `Bearer ${apiKey}`,
      },
      body,
      keepalive: true,
    }).catch(() => {});
  } catch {
    // Best-effort: silently drop
  }
}
