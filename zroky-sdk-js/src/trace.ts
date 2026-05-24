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
import { newCallId, newEventId } from "./ids";
import { resolveConfig } from "./config";
import { _setOutcomeConfig } from "./outcome";

type AnyFn = (...args: unknown[]) => unknown;

export function trace<T extends AnyFn>(fn: T, config: ZrokyConfig = {}): T {
  const resolvedConfig = resolveConfig(config);
  _setOutcomeConfig(resolvedConfig);
  return (async (...args: Parameters<T>) => {
    const startMs = Date.now();
    const callId = newCallId();
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
      if (result !== null && (typeof result === "object" || typeof result === "function")) {
        try {
          Object.defineProperty(result, "_zroky_call_id", {
            value: callId,
            enumerable: false,
            configurable: true,
          });
        } catch {
          // Capture must never mutate application behavior.
        }
      }
    } catch (err: unknown) {
      statusCode = 500;
      errorMessage = String((err as { message?: unknown })?.message ?? err);
      throw err;
    } finally {
      void emit(
        {
          schema_version: "v2",
          call_id: callId,
          event_id: newEventId(callId),
          provider: "custom",
          model: "unknown",
          call_type: "trace",
          latency_ms: Date.now() - startMs,
          prompt_tokens: 0,
          completion_tokens: 0,
          total_tokens: 0,
          status: errorMessage ? "error" : "success",
          error_code: errorMessage ? "UNKNOWN_ERROR" : undefined,
          error_message: errorMessage,
          prompt_fingerprint: promptFingerprint(promptText),
          agent_name: resolvedConfig.agentName,
          agent_framework: resolvedConfig.agentFramework,
          session_id: resolvedConfig.sessionId,
          workflow_id: resolvedConfig.workflowId,
          workflow_name: resolvedConfig.workflowName,
          prompt_version: resolvedConfig.promptVersion,
          trace_id: resolvedConfig.traceId,
          parent_call_id: resolvedConfig.parentCallId,
          user_id: resolvedConfig.userId,
          environment: resolvedConfig.environment,
          step_index: resolvedConfig.stepIndex,
          metadata: {
            ...(resolvedConfig.metadata ?? {}),
            status_code: statusCode,
          },
        },
        resolvedConfig,
      );
    }

    return result;
  }) as T;
}
