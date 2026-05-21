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
import { promptFingerprint } from "./fingerprint";
import type { ZrokyConfig } from "./types";
import { emit } from "./emitter";

interface OpenAILike {
  chat: {
    completions: {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      create: (...args: any[]) => Promise<any>;
    };
  };
}

export function wrap<T extends OpenAILike>(client: T, config: ZrokyConfig = {}): T {
  const original = client.chat.completions.create.bind(client.chat.completions);

  client.chat.completions.create = async (...args: unknown[]) => {
    const startMs = Date.now();
    const reqBody = args[0] as Record<string, unknown> | undefined;
    const model = typeof reqBody?.model === "string" ? reqBody.model : "unknown";
    const messages = Array.isArray(reqBody?.messages) ? reqBody.messages : [];
    const firstUserMsg = messages.find((m: unknown) => (m as { role?: string }).role === "user");
    const promptText =
      typeof (firstUserMsg as { content?: unknown })?.content === "string"
        ? (firstUserMsg as { content: string }).content
        : "";

    let response: unknown;
    let statusCode = 200;
    let errorMessage: string | undefined;

    try {
      response = await original(...args);
    } catch (err: unknown) {
      statusCode = (err as { status?: number })?.status ?? 500;
      errorMessage = String((err as { message?: unknown })?.message ?? err);
      throw err;
    } finally {
      const latencyMs = Date.now() - startMs;
      const usage = (response as { usage?: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number } } | undefined)?.usage;

      void emit(
        {
          provider: "openai",
          model,
          call_type: "chat",
          latency_ms: latencyMs,
          prompt_tokens: usage?.prompt_tokens ?? 0,
          output_tokens: usage?.completion_tokens ?? 0,
          total_tokens: usage?.total_tokens ?? 0,
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

    return response;
  };

  return client;
}
