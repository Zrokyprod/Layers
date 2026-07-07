// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

import type { CapturePayload, ZrokyConfig } from "./types";
import { maskPayload } from "./pii";

const DEFAULT_ENDPOINT = "https://api.zroky.com/v1/ingest";
const DISABLED_VALUES = new Set(["1", "true", "yes"]);
const RETRYABLE_STATUS = new Set([408, 409, 425, 429, 500, 502, 503, 504]);
const MAX_RETRIES = 2;
const RETRY_BASE_MS = 150;
const MAX_BUFFERED_EVENTS = 100;
const MAX_BATCH_EVENTS = 25;
const BUFFER_STORAGE_KEY = "zroky.capture.buffer.v1";
const BUFFER_PATH_ENV = "ZROKY_BUFFER_PATH";

type NodeEnv = { process?: { env: Record<string, string | undefined> } };
type BrowserStorageEnv = { localStorage?: Storage };
type ResolvedEmitterConfig = {
  endpoint: string;
  projectId: string;
  apiKey: string;
};

let bufferedEvents: CapturePayload[] = [];
let flushing = false;
let bufferLoaded = false;

function env(): Record<string, string | undefined> | undefined {
  return (globalThis as NodeEnv).process?.env;
}

function resolveEndpoint(config: ZrokyConfig, nodeEnv: Record<string, string | undefined> | undefined): string {
  const configured = config.endpoint ?? nodeEnv?.["ZROKY_API_URL"] ?? nodeEnv?.["ZROKY_ENDPOINT"];
  if (!configured) return DEFAULT_ENDPOINT;
  const normalized = configured.replace(/\/+$/, "");
  if (normalized.endsWith("/v1/ingest") || normalized.endsWith("/api/v1/ingest") || normalized.endsWith("/ingest")) {
    return normalized;
  }
  return `${normalized}/api/v1/ingest`;
}

function isDisabled(config: ZrokyConfig, nodeEnv: Record<string, string | undefined> | undefined): boolean {
  if (config.disabled) return true;
  const raw = nodeEnv?.["ZROKY_DISABLED"];
  return raw ? DISABLED_VALUES.has(raw.trim().toLowerCase()) : false;
}

function toBackendEvent(payload: CapturePayload): CapturePayload {
  const {
    output_tokens: _legacyOutputTokens,
    tool_calls_made: _legacyToolCallsMade,
    ...rest
  } = payload;
  const toolCalls = payload.tool_calls ?? payload.tool_calls_made;
  return maskPayload({
    ...rest,
    schema_version: payload.schema_version ?? "v2",
    completion_tokens: payload.completion_tokens ?? payload.output_tokens ?? 0,
    event_id: payload.event_id ?? `${payload.call_id}:capture`,
    tool_calls: toolCalls,
    capture_source: payload.capture_source ?? "js_sdk",
    masking_version: payload.masking_version ?? "js-sdk-pii-v1",
    pii_masked: payload.pii_masked ?? true,
  });
}

function resolveEmitterConfig(config: ZrokyConfig): ResolvedEmitterConfig | undefined {
  const nodeEnv = env();
  if (isDisabled(config, nodeEnv)) return;
  const projectId = config.projectId ?? nodeEnv?.["ZROKY_PROJECT_ID"] ?? nodeEnv?.["ZROKY_PROJECT"];
  const apiKey = config.apiKey ?? nodeEnv?.["ZROKY_API_KEY"];
  if (!projectId || !apiKey) return;
  return {
    endpoint: resolveEndpoint(config, nodeEnv),
    projectId,
    apiKey,
  };
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function storage(): Storage | undefined {
  return (globalThis as BrowserStorageEnv).localStorage;
}

function parseStoredEvents(raw: string | null | undefined): CapturePayload[] {
  if (!raw) return [];
  const parsed = JSON.parse(raw) as unknown;
  if (!Array.isArray(parsed)) return [];
  return parsed.filter((item): item is CapturePayload => {
    return Boolean(item && typeof item === "object" && typeof (item as CapturePayload).call_id === "string");
  });
}

function readBrowserStoredEvents(): CapturePayload[] {
  try {
    return parseStoredEvents(storage()?.getItem(BUFFER_STORAGE_KEY));
  } catch {
    return [];
  }
}

function writeBrowserStoredEvents(events: CapturePayload[]): void {
  try {
    if (!events.length) {
      storage()?.removeItem(BUFFER_STORAGE_KEY);
      return;
    }
    storage()?.setItem(BUFFER_STORAGE_KEY, JSON.stringify(events.slice(-MAX_BUFFERED_EVENTS)));
  } catch {
    // Storage can be disabled or full; in-memory buffering still applies.
  }
}

async function resolveDiskBufferPath(): Promise<string | undefined> {
  if (storage()) return undefined;
  const nodeEnv = env();
  if (!nodeEnv) return undefined;

  const configuredPath = nodeEnv[BUFFER_PATH_ENV]?.trim();
  if (configuredPath) return configuredPath;

  try {
    const [{ homedir }, path] = await Promise.all([import("node:os"), import("node:path")]);
    const home = homedir();
    return home ? path.join(home, ".zroky", "capture-buffer.json") : undefined;
  } catch {
    return undefined;
  }
}

async function readDiskStoredEvents(): Promise<CapturePayload[]> {
  const filePath = await resolveDiskBufferPath();
  if (!filePath) return [];
  try {
    const fs = await import("node:fs/promises");
    return parseStoredEvents(await fs.readFile(filePath, "utf8"));
  } catch {
    return [];
  }
}

async function writeDiskStoredEvents(events: CapturePayload[]): Promise<void> {
  const filePath = await resolveDiskBufferPath();
  if (!filePath) return;
  try {
    const [fs, path] = await Promise.all([import("node:fs/promises"), import("node:path")]);
    if (!events.length) {
      await fs.rm(filePath, { force: true });
      return;
    }
    await fs.mkdir(path.dirname(filePath), { recursive: true });
    await fs.writeFile(filePath, JSON.stringify(events.slice(-MAX_BUFFERED_EVENTS)), "utf8");
  } catch {
    // Disk persistence is best-effort; in-memory buffering still protects the hot process.
  }
}

async function readStoredEvents(): Promise<CapturePayload[]> {
  const browserEvents = readBrowserStoredEvents();
  if (browserEvents.length > 0 || storage()) return browserEvents;
  return readDiskStoredEvents();
}

async function writeStoredEvents(events: CapturePayload[]): Promise<void> {
  writeBrowserStoredEvents(events);
  if (!storage()) {
    await writeDiskStoredEvents(events);
  }
}

async function loadStoredBuffer(): Promise<void> {
  if (bufferLoaded) return;
  const storedEvents = (await readStoredEvents()).slice(-MAX_BUFFERED_EVENTS);
  if (bufferedEvents.length > 0) {
    bufferedEvents = [...storedEvents, ...bufferedEvents].slice(-MAX_BUFFERED_EVENTS);
  } else {
    bufferedEvents = storedEvents;
  }
  bufferLoaded = true;
}

async function postBatch(events: CapturePayload[], resolved: ResolvedEmitterConfig): Promise<boolean> {
  const body = JSON.stringify({ events: events.map(toBackendEvent) });

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt += 1) {
    try {
      const response = await fetch(resolved.endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-api-key": resolved.apiKey,
          "x-project-id": resolved.projectId,
          Authorization: `Bearer ${resolved.apiKey}`,
        },
        body,
        // keepalive allows the request to complete even if the page unloads
        keepalive: true,
      });
      if (response.ok || !RETRYABLE_STATUS.has(response.status)) {
        return true;
      }
    } catch {
      // Best-effort: retry below, then buffer.
    }

    if (attempt < MAX_RETRIES) {
      await sleep(RETRY_BASE_MS * 2 ** attempt);
    }
  }

  return false;
}

async function bufferEvents(events: CapturePayload[]): Promise<void> {
  bufferedEvents.push(...events.map(toBackendEvent));
  if (bufferedEvents.length > MAX_BUFFERED_EVENTS) {
    bufferedEvents.splice(0, bufferedEvents.length - MAX_BUFFERED_EVENTS);
  }
  await writeStoredEvents(bufferedEvents);
}

async function drainBuffer(resolved: ResolvedEmitterConfig): Promise<void> {
  if (flushing) return;

  flushing = true;
  try {
    while (bufferedEvents.length > 0) {
      const batch = bufferedEvents.splice(0, MAX_BATCH_EVENTS);
      await writeStoredEvents(bufferedEvents);
      const posted = await postBatch(batch, resolved);
      if (!posted) {
        bufferedEvents = [...batch, ...bufferedEvents].slice(-MAX_BUFFERED_EVENTS);
        await writeStoredEvents(bufferedEvents);
        break;
      }
    }
    await writeStoredEvents(bufferedEvents);
  } finally {
    flushing = false;
  }
}

export function _resetEmitterForTest(options: { preserveStorage?: boolean } = {}): void {
  bufferedEvents = [];
  flushing = false;
  bufferLoaded = false;
  if (!options.preserveStorage) {
    writeBrowserStoredEvents([]);
    void writeDiskStoredEvents([]);
  }
}

export async function emit(payload: CapturePayload, config: ZrokyConfig): Promise<void> {
  const resolved = resolveEmitterConfig(config);
  if (!resolved) return;

  await loadStoredBuffer();
  await bufferEvents([payload]);
  await drainBuffer(resolved);
}
