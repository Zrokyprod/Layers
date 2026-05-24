// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

/**
 * wrap(openai) — patches openai.chat.completions.create to capture + emit.
 *
 * Usage:
 *   import OpenAI from "openai";
 *   import { wrap } from "@zroky/sdk";
 *
 *   const openai = wrap(new OpenAI());
 *   // All subsequent calls are captured automatically.
 */
import { generatePromptFingerprint } from "./fingerprint";
import type { ZrokyConfig } from "./types";
import { emit } from "./emitter";
import { newCallId, newEventId } from "./ids";
import { resolveConfig } from "./config";
import { _setOutcomeConfig } from "./outcome";

interface OpenAILike {
  chat: {
    completions: {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      create: (...args: any[]) => Promise<any>;
    };
  };
}

function extractOutputContent(response: unknown): string | undefined {
  const choices = (response as { choices?: unknown[] } | undefined)?.choices;
  const first = Array.isArray(choices) ? choices[0] : undefined;
  const content = (first as { message?: { content?: unknown } } | undefined)?.message?.content;
  return typeof content === "string" ? content.slice(0, 4000) : undefined;
}

function extractToolCalls(response: unknown): Record<string, unknown>[] | undefined {
  const choices = (response as { choices?: unknown[] } | undefined)?.choices;
  const first = Array.isArray(choices) ? choices[0] : undefined;
  const toolCalls = (first as { message?: { tool_calls?: unknown } } | undefined)?.message?.tool_calls;
  return Array.isArray(toolCalls) ? (toolCalls as Record<string, unknown>[]) : undefined;
}

function attachCallId(response: unknown, callId: string): void {
  if (response === null || (typeof response !== "object" && typeof response !== "function")) return;
  try {
    Object.defineProperty(response, "_zroky_call_id", {
      value: callId,
      enumerable: false,
      configurable: true,
    });
  } catch {
    // Capture must never mutate application behavior.
  }
}

function classifyErrorCode(statusCode: number, message: string | undefined): string | undefined {
  const text = (message ?? "").toLowerCase();
  if (statusCode === 401 || statusCode === 403) return "AUTH_FAILURE";
  if (statusCode === 408 || statusCode === 504 || text.includes("timeout")) return "TIMEOUT";
  if (statusCode === 429 || text.includes("rate limit")) return "RATE_LIMIT";
  if (statusCode >= 500) return "PROVIDER_ERROR";
  return message ? "UNKNOWN_ERROR" : undefined;
}

export function wrap<T extends OpenAILike>(client: T, config: ZrokyConfig = {}): T {
  const resolvedConfig = resolveConfig(config);
  _setOutcomeConfig(resolvedConfig);
  const original = client.chat.completions.create.bind(client.chat.completions);

  client.chat.completions.create = async (...args: unknown[]) => {
    const startMs = Date.now();
    const callId = newCallId();
    const reqBody = args[0] as Record<string, unknown> | undefined;
    const model = typeof reqBody?.model === "string" ? reqBody.model : "unknown";
    const messages = Array.isArray(reqBody?.messages) ? reqBody.messages : [];

    let response: unknown;
    let statusCode = 200;
    let errorMessage: string | undefined;

    try {
      response = await original(...args);
      attachCallId(response, callId);
    } catch (err: unknown) {
      statusCode = (err as { status?: number })?.status ?? 500;
      errorMessage = String((err as { message?: unknown })?.message ?? err);
      throw err;
    } finally {
      const latencyMs = Date.now() - startMs;
      const usage = (
        response as
          | {
              id?: string;
              usage?: {
                prompt_tokens?: number;
                completion_tokens?: number;
                output_tokens?: number;
                total_tokens?: number;
              };
            }
          | undefined
      )?.usage;
      const completionTokens = usage?.completion_tokens ?? usage?.output_tokens ?? 0;
      const promptTokens = usage?.prompt_tokens ?? 0;

      void emit(
        {
          schema_version: "v2",
          call_id: callId,
          event_id: newEventId(callId),
          request_id: typeof (response as { id?: unknown } | undefined)?.id === "string" ? (response as { id: string }).id : undefined,
          provider: "openai",
          model,
          call_type: "chat",
          latency_ms: latencyMs,
          prompt_tokens: promptTokens,
          completion_tokens: completionTokens,
          total_tokens: usage?.total_tokens ?? promptTokens + completionTokens,
          status: errorMessage ? "error" : "success",
          error_code: classifyErrorCode(statusCode, errorMessage),
          error_message: errorMessage,
          prompt_fingerprint: generatePromptFingerprint(
            messages,
            Array.isArray(reqBody?.tools) ? (reqBody.tools as Record<string, unknown>[]) : undefined,
            model,
          ),
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
          output_content: extractOutputContent(response),
          tool_definitions: Array.isArray(reqBody?.tools) ? (reqBody.tools as Record<string, unknown>[]) : undefined,
          tool_calls: extractToolCalls(response),
          metadata: {
            ...(resolvedConfig.metadata ?? {}),
            status_code: statusCode,
          },
        },
        resolvedConfig,
      );
    }

    return response;
  };

  return client;
}
