/**
 * API client for the Zroky assistant.
 * Follows the same request pattern as api.ts (cookie-based auth, /api/zroky proxy).
 */

import { readAccessTokenFromBrowser } from "@/lib/auth";

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

function buildAuthHeader(token: string): string {
  return token.toLowerCase().startsWith("bearer ") ? token : `Bearer ${token}`;
}

export async function sendAssistantMessage(
  message: string,
  sessionId: string,
  signal?: AbortSignal,
): Promise<AssistantChatResponse> {
  const token = readAccessTokenFromBrowser();
  const headers: Record<string, string> = {
    "content-type": "application/json",
  };
  if (token) {
    headers.authorization = buildAuthHeader(token);
  }

  const response = await fetch("/api/zroky/v1/assistant/chat", {
    method: "POST",
    cache: "no-store",
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
  const token = readAccessTokenFromBrowser();
  const headers: Record<string, string> = {};
  if (token) {
    headers.authorization = buildAuthHeader(token);
  }

  await fetch(`/api/zroky/v1/assistant/chat/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
    cache: "no-store",
    headers,
  });
}
