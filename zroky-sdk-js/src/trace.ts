// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

/**
 * @zroky/trace — function-level trace decorator / wrapper.
 *
 * Usage:
 *   import { trace } from "@zroky/sdk";
 *
 *   const tracedFn = trace(myAgentFunction, { agentName: "planner" });
 *   await tracedFn(args);
 */
import type { ZrokyConfig } from "./types";
import { promptFingerprint } from "./fingerprint";
import { emit } from "./emitter";

type AnyFn = (...args: unknown[]) => unknown;

export function trace<T extends AnyFn>(fn: T, config: ZrokyConfig = {}): T {
  return (async (...args: Parameters<T>) => {
    const startMs = Date.now();
    const firstArg = args[0];
    const promptText =
      typeof firstArg === "string"
        ? firstArg
        : typeof (firstArg as { prompt?: unknown })?.prompt === "string"
        ? (firstArg as { prompt: string }).prompt
        : "";

    let result: unknown;
    let errorMessage: string | undefined;
    let statusCode = 200;

    try {
      result = await fn(...args);
    } catch (err: unknown) {
      statusCode = 500;
      errorMessage = String((err as { message?: unknown })?.message ?? err);
      throw err;
    } finally {
      void emit(
        {
          provider: "custom",
          model: "unknown",
          call_type: "trace",
          latency_ms: Date.now() - startMs,
          prompt_tokens: 0,
          output_tokens: 0,
          total_tokens: 0,
          status: errorMessage ? "error" : "success",
          status_code: statusCode,
          error_message: errorMessage,
          prompt_fingerprint: promptFingerprint(promptText),
          agent_name: config.agentName,
          session_id: config.sessionId,
          workflow_id: config.workflowId,
        },
        config,
      );
    }

    return result;
  }) as T;
}
