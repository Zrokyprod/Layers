# Multi-provider Gateway Quickstart

Zroky Gateway is not OpenAI-only. It is an open-source telemetry gateway for OpenAI-compatible APIs, Anthropic, and Gemini routes.

## OpenAI-compatible client

```bash
export OPENAI_BASE_URL=http://localhost:8090/v1
```

```ts
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "http://localhost:8090/v1",
  defaultHeaders: {
    "X-Zroky-Project-Id": process.env.ZROKY_PROJECT_ID!,
    "X-Zroky-Agent-Name": "refund-agent",
    "X-Zroky-Workflow-Name": "refund-review",
  },
});
```

## Anthropic route

Send Anthropic Messages requests through:

```text
POST http://localhost:8090/v1/messages
```

The gateway forwards to:

```text
https://api.anthropic.com/v1/messages
```

## Gemini route

Send Gemini requests through:

```text
POST http://localhost:8090/v1beta/models/...
```

The gateway forwards to:

```text
https://generativelanguage.googleapis.com/v1beta/models/...
```

## Zroky headers

`X-Zroky-*` headers are used for telemetry context and stripped before provider forwarding.
