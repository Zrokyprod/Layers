// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, it } from "node:test";
import { _resetEmitterForTest, emit } from "../src/emitter";
import { init } from "../src/config";
import { outcome } from "../src/outcome";
import { captureMemory, captureRetrieval } from "../src/spans";
import { trace } from "../src/trace";
import { wrap } from "../src/wrap";

type FetchCall = {
  input: RequestInfo | URL;
  init?: RequestInit;
};

const originalFetch = globalThis.fetch;
const originalLocalStorageDescriptor = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
const originalBufferPath = process.env.ZROKY_BUFFER_PATH;

function recordFetches(): FetchCall[] {
  const calls: FetchCall[] = [];
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ input, init });
    return Promise.resolve({ ok: true, status: 202 } as Response);
  }) as typeof fetch;
  return calls;
}

function parseBody(call: FetchCall): { events: Record<string, unknown>[] } {
  assert.equal(typeof call.init?.body, "string");
  return JSON.parse(call.init.body) as { events: Record<string, unknown>[] };
}

async function waitForFetches(calls: FetchCall[], minimum: number): Promise<void> {
  for (let attempt = 0; attempt < 25; attempt += 1) {
    if (calls.length >= minimum) return;
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
  assert.equal(calls.length, minimum);
}

function installFakeLocalStorage(): Map<string, string> {
  const values = new Map<string, string>();
  const fakeStorage = {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {
      values.set(key, value);
    },
    removeItem: (key: string) => {
      values.delete(key);
    },
    clear: () => values.clear(),
    key: (index: number) => Array.from(values.keys())[index] ?? null,
    get length() {
      return values.size;
    },
  } as Storage;
  Object.defineProperty(globalThis, "localStorage", {
    value: fakeStorage,
    configurable: true,
  });
  return values;
}

function restoreLocalStorage(): void {
  if (originalLocalStorageDescriptor) {
    Object.defineProperty(globalThis, "localStorage", originalLocalStorageDescriptor);
  } else {
    delete (globalThis as { localStorage?: Storage }).localStorage;
  }
}

afterEach(() => {
  globalThis.fetch = originalFetch;
  _resetEmitterForTest();
  restoreLocalStorage();
  if (originalBufferPath === undefined) {
    delete process.env.ZROKY_BUFFER_PATH;
  } else {
    process.env.ZROKY_BUFFER_PATH = originalBufferPath;
  }
  init({});
});

describe("capture contract", () => {
  it("emits backend-compatible IngestBatchRequest payloads", async () => {
    const calls = recordFetches();

    await emit(
      {
        call_id: "call_123",
        provider: "openai",
        model: "gpt-4o-mini",
        call_type: "chat",
        latency_ms: 42,
        prompt_tokens: 7,
        completion_tokens: 11,
        total_tokens: 18,
        status: "success",
      },
      {
        projectId: "proj_123",
        apiKey: "zk_test",
        endpoint: "https://capture.example/v1/ingest",
      },
    );

    assert.equal(calls.length, 1);
    assert.equal(calls[0].input, "https://capture.example/v1/ingest");
    const headers = calls[0].init?.headers as Record<string, string>;
    assert.equal(headers["x-api-key"], "zk_test");
    assert.equal(headers["x-project-id"], "proj_123");

    const body = parseBody(calls[0]);
    assert.equal(body.events.length, 1);
    assert.equal(body.events[0].schema_version, "v2");
    assert.equal(body.events[0].call_id, "call_123");
    assert.equal(body.events[0].event_id, "call_123:capture");
    assert.equal(body.events[0].completion_tokens, 11);
    assert.equal("output_tokens" in body.events[0], false);
    assert.equal("project_id" in body.events[0], false);
  });

  it("preserves system IDs while masking phone-like content", async () => {
    const calls = recordFetches();
    const phoneLikeCallId = "16081e8b-1b21-4cb9-ac8c-610877734263";

    await emit(
      {
        call_id: phoneLikeCallId,
        trace_id: "trace_16081e8b-1b21-4cb9-ac8c-610877734263",
        provider: "openai",
        model: "gpt-4o-mini",
        call_type: "chat",
        latency_ms: 42,
        prompt_tokens: 7,
        completion_tokens: 11,
        total_tokens: 18,
        status: "success",
        output_content: "Customer phone 610877734263 should be masked.",
      },
      {
        projectId: "proj_123",
        apiKey: "zk_test",
        endpoint: "https://capture.example/v1/ingest",
      },
    );

    const event = parseBody(calls[0]).events[0];
    assert.equal(event.call_id, phoneLikeCallId);
    assert.equal(event.event_id, `${phoneLikeCallId}:capture`);
    assert.equal(event.trace_id, "trace_16081e8b-1b21-4cb9-ac8c-610877734263");
    assert.equal(event.output_content, "Customer phone [REDACTED_PHONE] should be masked.");
  });

  it("buffers retry-exhausted events and flushes them with the next successful emit", async () => {
    const calls: FetchCall[] = [];
    let attempt = 0;
    globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ input, init });
      attempt += 1;
      if (attempt <= 3) {
        return Promise.resolve({ ok: false, status: 503 } as Response);
      }
      return Promise.resolve({ ok: true, status: 202 } as Response);
    }) as typeof fetch;

    const config = {
      projectId: "proj_123",
      apiKey: "zk_test",
      endpoint: "https://capture.example/v1/ingest",
    };

    await emit(
      {
        call_id: "call_retry_1",
        provider: "openai",
        model: "gpt-4o-mini",
        call_type: "chat",
        latency_ms: 1,
        prompt_tokens: 1,
        completion_tokens: 1,
        total_tokens: 2,
        status: "success",
      },
      config,
    );
    await emit(
      {
        call_id: "call_retry_2",
        provider: "openai",
        model: "gpt-4o-mini",
        call_type: "chat",
        latency_ms: 1,
        prompt_tokens: 2,
        completion_tokens: 3,
        total_tokens: 5,
        status: "success",
      },
      config,
    );

    assert.equal(calls.length, 4);
    const flushed = parseBody(calls[3]).events;
    assert.deepEqual(
      flushed.map((event) => event.call_id),
      ["call_retry_1", "call_retry_2"],
    );
  });

  it("persists buffered browser events and flushes them after a reload", async () => {
    const stored = installFakeLocalStorage();
    const calls: FetchCall[] = [];
    let failing = true;
    globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ input, init });
      if (failing) {
        return Promise.resolve({ ok: false, status: 503 } as Response);
      }
      return Promise.resolve({ ok: true, status: 202 } as Response);
    }) as typeof fetch;

    const config = {
      projectId: "proj_123",
      apiKey: "zk_test",
      endpoint: "https://capture.example/v1/ingest",
    };

    await emit(
      {
        call_id: "call_persisted_1",
        provider: "openai",
        model: "gpt-4o-mini",
        call_type: "chat",
        latency_ms: 1,
        prompt_tokens: 1,
        completion_tokens: 1,
        total_tokens: 2,
        status: "success",
      },
      config,
    );

    assert.match(stored.get("zroky.capture.buffer.v1") ?? "", /call_persisted_1/);

    _resetEmitterForTest({ preserveStorage: true });
    failing = false;

    await emit(
      {
        call_id: "call_persisted_2",
        provider: "openai",
        model: "gpt-4o-mini",
        call_type: "chat",
        latency_ms: 1,
        prompt_tokens: 2,
        completion_tokens: 3,
        total_tokens: 5,
        status: "success",
      },
      config,
    );

    const flushed = parseBody(calls[calls.length - 1]).events;
    assert.deepEqual(
      flushed.map((event) => event.call_id),
      ["call_persisted_1", "call_persisted_2"],
    );
    assert.equal(stored.has("zroky.capture.buffer.v1"), false);
  });

  it("persists buffered node events on disk and flushes them after restart", async () => {
    const tempDir = await mkdtemp(join(tmpdir(), "zroky-buffer-"));
    process.env.ZROKY_BUFFER_PATH = join(tempDir, "capture-buffer.json");

    const calls: FetchCall[] = [];
    let failing = true;
    globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ input, init });
      if (failing) {
        return Promise.resolve({ ok: false, status: 503 } as Response);
      }
      return Promise.resolve({ ok: true, status: 202 } as Response);
    }) as typeof fetch;

    const config = {
      projectId: "proj_123",
      apiKey: "zk_test",
      endpoint: "https://capture.example/v1/ingest",
    };

    try {
      await emit(
        {
          call_id: "call_disk_1",
          provider: "openai",
          model: "gpt-4o-mini",
          call_type: "chat",
          latency_ms: 1,
          prompt_tokens: 1,
          completion_tokens: 1,
          total_tokens: 2,
          status: "success",
        },
        config,
      );

      assert.match(await readFile(process.env.ZROKY_BUFFER_PATH, "utf8"), /call_disk_1/);

      _resetEmitterForTest({ preserveStorage: true });
      failing = false;

      await emit(
        {
          call_id: "call_disk_2",
          provider: "openai",
          model: "gpt-4o-mini",
          call_type: "chat",
          latency_ms: 1,
          prompt_tokens: 2,
          completion_tokens: 3,
          total_tokens: 5,
          status: "success",
        },
        config,
      );

      const flushed = parseBody(calls[calls.length - 1]).events;
      assert.deepEqual(
        flushed.map((event) => event.call_id),
        ["call_disk_1", "call_disk_2"],
      );
      await assert.rejects(readFile(process.env.ZROKY_BUFFER_PATH, "utf8"));
    } finally {
      await rm(tempDir, { recursive: true, force: true });
    }
  });

  it("wrap() links the emitted event to the returned response call id", async () => {
    const calls = recordFetches();
    const client = {
      chat: {
        completions: {
          create: async () => ({
            id: "resp_123",
            usage: { prompt_tokens: 5, completion_tokens: 6, total_tokens: 11 },
            choices: [
              {
                message: {
                  content: "done",
                  tool_calls: [{ id: "tool_1", function: { name: "lookup" } }],
                },
              },
            ],
          }),
        },
      },
    };

    const wrapped = wrap(client, {
      projectId: "proj_123",
      apiKey: "zk_test",
      endpoint: "https://capture.example/v1/ingest",
      agentName: "support-agent",
      agentFramework: "custom-js",
      sessionId: "sess_1",
      workflowId: "wf_1",
      workflowName: "support-resolution",
      promptVersion: "support-v42",
      traceId: "trace_1",
      environment: "production",
      metadata: { release: "2026.05.23" },
    });

    const response = await wrapped.chat.completions.create({
      model: "gpt-4o-mini",
      messages: [{ role: "user", content: "help me" }],
      tools: [{ type: "function", function: { name: "lookup" } }],
    });
    const responseCallId = (response as { _zroky_call_id?: string })._zroky_call_id;

    await waitForFetches(calls, 1);
    assert.equal(typeof responseCallId, "string");
    assert.equal(calls.length, 1);
    const event = parseBody(calls[0]).events[0];
    assert.equal(event.call_id, responseCallId);
    assert.equal(event.request_id, "resp_123");
    assert.equal(event.provider, "openai");
    assert.equal(event.model, "gpt-4o-mini");
    assert.equal(event.prompt_fingerprint, "6e572e615b8e749f2a5738d26e6ee27b39094c7d8f109405bd472b75ea85d80e");
    assert.equal(event.completion_tokens, 6);
    assert.equal(event.agent_name, "support-agent");
    assert.equal(event.agent_framework, "custom-js");
    assert.equal(event.session_id, "sess_1");
    assert.equal(event.workflow_id, "wf_1");
    assert.equal(event.workflow_name, "support-resolution");
    assert.equal(event.prompt_version, "support-v42");
    assert.equal(event.trace_id, "trace_1");
    assert.equal(event.environment, "production");
    assert.equal(event.output_content, "done");
    assert.deepEqual(event.tool_definitions, [{ type: "function", function: { name: "lookup" } }]);
    assert.deepEqual(event.tool_calls, [{ id: "tool_1", function: { name: "lookup" } }]);
    assert.equal("tool_calls_made" in event, false);
    assert.deepEqual(event.metadata, { release: "2026.05.23", status_code: 200 });
    assert.equal("output_tokens" in event, false);
  });

  it("trace() emits a linked synthetic function span without breaking return values", async () => {
    const calls = recordFetches();
    const traced = trace(async (prompt: string) => ({ prompt, ok: true }), {
      projectId: "proj_123",
      apiKey: "zk_test",
      endpoint: "https://capture.example/v1/ingest",
      agentName: "planner",
      workflowId: "wf_2",
      workflowName: "planner-workflow",
      promptVersion: "planner-v7",
    });

    const result = await traced("plan this");
    const responseCallId = (result as { _zroky_call_id?: string })._zroky_call_id;

    await waitForFetches(calls, 1);
    assert.deepEqual({ prompt: result.prompt, ok: result.ok }, { prompt: "plan this", ok: true });
    assert.equal(typeof responseCallId, "string");
    const event = parseBody(calls[0]).events[0];
    assert.equal(event.call_id, responseCallId);
    assert.equal(event.provider, "custom");
    assert.equal(event.call_type, "trace");
    assert.equal(event.completion_tokens, 0);
    assert.equal(event.agent_name, "planner");
    assert.equal(event.workflow_id, "wf_2");
    assert.equal(event.workflow_name, "planner-workflow");
    assert.equal(event.prompt_version, "planner-v7");
  });

  it("captureRetrieval() emits first-class RAG context spans", async () => {
    const calls = recordFetches();

    const callId = await captureRetrieval(
      {
        query: "refund policy",
        indexName: "support-kb",
        retrieverVersion: "hybrid-v3",
        latencyMs: 17,
        documents: [
          {
            id: "doc_1",
            title: "Refunds",
            score: 0.91,
            contentPreview: "Refunds are available within 30 days.",
          },
        ],
        parentCallId: "parent_call",
        workflowName: "rag-workflow",
        promptVersion: "rag-v1",
      },
      {
        projectId: "proj_123",
        apiKey: "zk_test",
        endpoint: "https://capture.example/v1/ingest",
        workflowId: "wf_rag",
      },
    );

    await waitForFetches(calls, 1);
    const event = parseBody(calls[0]).events[0];
    assert.equal(event.call_id, callId);
    assert.equal(event.provider, "retrieval");
    assert.equal(event.model, "support-kb");
    assert.equal(event.call_type, "retrieval");
    assert.equal(event.latency_ms, 17);
    assert.equal(event.workflow_id, "wf_rag");
    assert.equal(event.workflow_name, "rag-workflow");
    assert.equal(event.prompt_version, "rag-v1");
    assert.equal(event.parent_call_id, "parent_call");
    assert.equal(event.output_content, "doc_1");
    assert.equal(typeof event.prompt_fingerprint, "string");
    assert.deepEqual(event.retrieval, {
      query: "refund policy",
      index_name: "support-kb",
      retriever_version: "hybrid-v3",
      documents: [
        {
          id: "doc_1",
          title: "Refunds",
          score: 0.91,
          contentPreview: "Refunds are available within 30 days.",
        },
      ],
      result_count: 1,
    });
    assert.deepEqual(event.metadata, {
      span_type: "retrieval",
      index_name: "support-kb",
      retriever_version: "hybrid-v3",
      result_count: 1,
      documents: [
        {
          id: "doc_1",
          title: "Refunds",
          score: 0.91,
          contentPreview: "Refunds are available within 30 days.",
        },
      ],
    });
  });

  it("captureMemory() emits memory operation spans", async () => {
    const calls = recordFetches();

    await captureMemory(
      {
        operation: "write",
        namespace: "customer-memory",
        keys: ["user_123:preferences"],
        itemCount: 1,
        bytes: 512,
        valuePreview: "prefers email updates",
      },
      {
        projectId: "proj_123",
        apiKey: "zk_test",
        endpoint: "https://capture.example/v1/ingest",
      },
    );

    await waitForFetches(calls, 1);
    const event = parseBody(calls[0]).events[0];
    assert.equal(event.provider, "memory");
    assert.equal(event.model, "customer-memory");
    assert.equal(event.call_type, "memory");
    assert.equal(event.output_content, "prefers email updates");
    assert.deepEqual(event.metadata, {
      span_type: "memory",
      operation: "write",
      namespace: "customer-memory",
      keys: ["user_123:preferences"],
      item_count: 1,
      bytes: 512,
    });
  });

  it("outcome() posts to the API base even when configured with an ingest endpoint", async () => {
    const calls = recordFetches();
    init({
      projectId: "proj_123",
      apiKey: "zk_test",
      endpoint: "https://capture.example/api/v1/ingest",
    });

    outcome("call_123", {
      type: "ticket_escalated",
      amountUsd: 12.5,
      idempotencyKey: "call_123:ticket_escalated",
      metadata: { ticket: "T-1" },
    });

    assert.equal(calls.length, 1);
    assert.equal(calls[0].input, "https://capture.example/api/v1/outcomes");
    const headers = calls[0].init?.headers as Record<string, string>;
    assert.equal(headers["x-api-key"], "zk_test");
    assert.equal(headers["x-project-id"], "proj_123");
    const body = JSON.parse(calls[0].init?.body as string) as Record<string, unknown>;
    assert.equal(body.call_id, "call_123");
    assert.equal(body.outcome_type, "ticket_escalated");
    assert.equal(body.amount_usd, 12.5);
    assert.deepEqual(body.metadata, { ticket: "T-1" });
  });
});
