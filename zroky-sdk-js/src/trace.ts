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
import { versionMetadata } from "./versions";

type AnyFn = (...args: unknown[]) => unknown;

export interface TraceRunContext {
  traceId: string;
  rootCallId: string;
  setFinalAnswer(value: unknown): void;
}

export interface TraceRunOptions {
  name?: string;
  traceId?: string;
  callId?: string;
  userInput?: string;
  systemPrompt?: string;
  input?: Record<string, unknown>;
  userId?: string;
  environment?: string;
  metadata?: Record<string, unknown>;
}

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
          trace_id: resolvedConfig.traceId ?? callId,
          parent_call_id: resolvedConfig.parentCallId,
          span_type: "agent_run",
          span_name: resolvedConfig.agentName ?? fn.name ?? "Agent run",
          span_index: resolvedConfig.stepIndex ?? 0,
          input: { args },
          user_input: promptText || undefined,
          final_answer: typeof result === "string" ? result.slice(0, 12000) : undefined,
          output_content: typeof result === "string" ? result.slice(0, 4000) : undefined,
          versions: versionMetadata(resolvedConfig),
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

export async function traceRun<T>(
  options: TraceRunOptions,
  fn: (ctx: TraceRunContext) => Promise<T> | T,
  config: ZrokyConfig = {},
): Promise<T> {
  const resolvedConfig = resolveConfig(config);
  _setOutcomeConfig(resolvedConfig);
  const rootCallId = options.callId ?? newCallId();
  const traceId = options.traceId ?? rootCallId;
  const startMs = Date.now();
  let result: T;
  let finalAnswer: unknown;
  let errorMessage: string | undefined;
  const ctx: TraceRunContext = {
    traceId,
    rootCallId,
    setFinalAnswer(value: unknown) {
      finalAnswer = value;
    },
  };
  try {
    result = await fn(ctx);
    if (finalAnswer === undefined) finalAnswer = result;
  } catch (err: unknown) {
    errorMessage = String((err as { message?: unknown })?.message ?? err);
    throw err;
  } finally {
    void emit(
      {
        schema_version: "v2",
        call_id: rootCallId,
        event_id: newEventId(rootCallId),
        provider: "agent",
        model: options.name ?? resolvedConfig.agentName ?? "agent_run",
        call_type: "agent_run",
        latency_ms: Date.now() - startMs,
        prompt_tokens: 0,
        completion_tokens: 0,
        total_tokens: 0,
        status: errorMessage ? "error" : "success",
        error_code: errorMessage ? "UNKNOWN_ERROR" : undefined,
        error_message: errorMessage,
        agent_name: resolvedConfig.agentName,
        agent_framework: resolvedConfig.agentFramework,
        prompt_version: resolvedConfig.promptVersion,
        trace_id: traceId,
        span_type: "agent_run",
        span_name: options.name ?? resolvedConfig.agentName ?? "Agent run",
        span_index: 0,
        input: options.input ?? { user_input: options.userInput, system_prompt: options.systemPrompt },
        system_prompt: options.systemPrompt,
        user_input: options.userInput,
        final_answer: typeof finalAnswer === "string" ? finalAnswer.slice(0, 12000) : undefined,
        output_content: typeof finalAnswer === "string" ? finalAnswer.slice(0, 4000) : undefined,
        versions: versionMetadata(resolvedConfig),
        user_id: options.userId ?? resolvedConfig.userId,
        environment: options.environment ?? resolvedConfig.environment,
        step_index: 0,
        metadata: {
          ...(resolvedConfig.metadata ?? {}),
          ...(options.metadata ?? {}),
        },
      },
      resolvedConfig,
    );
  }
  return result!;
}
