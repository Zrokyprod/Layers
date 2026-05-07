# ZROKY V1 Docs

This repository contains the V1 blueprint and launch-facing support documents.

## Primary Docs

- Blueprint: [zroky-blueprint.md](zroky-blueprint.md)
- Agent coverage: [docs/agent-coverage.md](docs/agent-coverage.md)

## Dashboard Frontend (Phase 1 Start)

The dashboard frontend now lives in `zroky-dashboard` (Next.js App Router + TypeScript).

Run locally:

1. `cd zroky-dashboard`
2. `npm install`
3. `npm run dev`

Required backend proxy env (in `zroky-dashboard/.env.local`):

1. `ZROKY_API_BASE_URL=http://127.0.0.1:8000`
2. `ZROKY_PROJECT_ID=<your_project_id>`
3. `ZROKY_API_KEY=<your_project_api_key>`

Optional provisioning env (only if project/API-key admin endpoints are protected):

1. `ZROKY_PROVISIONING_TOKEN=<provisioning_token>`
2. `ZROKY_PROVISIONING_TOKEN_HEADER=x-provisioning-token`

## Integration Compatibility (V1)

Use this as the upfront expectation guide before onboarding developers.

| Agent Pattern | V1 Coverage | Launch Guidance |
|---|---:|---|
| Custom Python agent | 95% | Recommended for production V1 |
| LangChain agent | 80% | Supported for LLM-call capture only |
| Multi-agent custom | 85% | Supported with agent tags and trace linkage |
| LangGraph | 65% | Manual wrapper required |
| CrewAI and AutoGen | V1.1 | Not supported in V1 |
| OpenAI Assistants | V2 | Not supported in V1 |

Why this exists:

- Upfront compatibility honesty prevents failed integrations and early churn.
- Teams can choose a supported path before implementation starts.
- Expectations stay aligned with the V1 scope lock.

For full support details and boundaries, see [docs/agent-coverage.md](docs/agent-coverage.md).
