/**
 * API client for the Zroky assistant.
 * Follows the same request pattern as api.ts (cookie-based auth, /api/zroky proxy).
 */

import {
  legacyProductSurfaceDisabledError,
  legacyProductSurfaceEnabled,
} from "./legacy-product-surfaces";

export interface ToolSource {
  tool: string;
  summary: string;
}

export interface AssistantChatResponse {
  reply: string;
  sources: ToolSource[];
  session_id: string;
  off_topic: boolean;
}

export async function sendAssistantMessage(
  message: string,
  sessionId: string,
  signal?: AbortSignal,
): Promise<AssistantChatResponse> {
  if (!legacyProductSurfaceEnabled) {
    throw legacyProductSurfaceDisabledError("Assistant");
  }

  const headers: Record<string, string> = {
    "content-type": "application/json",
  };

  const response = await fetch("/api/zroky/v1/assistant/chat", {
    method: "POST",
    cache: "no-store",
    credentials: "same-origin",
    headers,
    body: JSON.stringify({ message, session_id: sessionId }),
    signal,
  });

  if (!response.ok) {
    let detail: string | null = null;
    try {
      const payload = (await response.json()) as { detail?: string };
      detail = typeof payload.detail === "string" ? payload.detail : null;
    } catch {
      /* ignore */
    }
    throw new Error(detail ?? `Assistant request failed (${response.status})`);
  }

  return response.json() as Promise<AssistantChatResponse>;
}

export async function clearAssistantSession(sessionId: string): Promise<void> {
  if (!legacyProductSurfaceEnabled) {
    throw legacyProductSurfaceDisabledError("Assistant");
  }

  await fetch(`/api/zroky/v1/assistant/chat/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
    cache: "no-store",
    credentials: "same-origin",
  });
}
