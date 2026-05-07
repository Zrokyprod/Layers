# ZROKY Agent Coverage Matrix (V1 Launch)

Purpose:

- Set clear developer expectations before integration.
- Prevent churn from unsupported/partial agent frameworks.
- Build trust through upfront coverage honesty.

---

## Coverage Matrix

| Agent Pattern | V1 Coverage | Support Level | What Is Captured in V1 | Notes |
|---|---:|---|---|---|
| Custom Python agent | 95% | Strong | LLM call metadata, errors, tokens, cost, tool-call payloads, diagnosis mapping | Recommended default for production V1 |
| LangChain agent | 80% | Partial | LLM calls only (prompt/response metadata, latency, tokens, errors) | Chain steps and tool results deferred to V1.1 |
| Multi-agent custom | 85% | Strong (Foundation) | `agent_name`, `trace_id`, `parent_call_id`, linked-call diagnosis context | Full multi-agent UI deferred; blast radius shown in Call Detail |
| LangGraph | 65% | Manual wrap | Works with manual wrapper/instrumentation boundaries | Not plug-and-play in V1 |
| CrewAI / AutoGen | V1.1 | Planned | Not supported in V1 | Do not commit production rollout in V1 |
| OpenAI Assistants | V2 | Planned | Not supported in V1 | Use custom Python path for V1 launches |

---

## Practical Integration Guidance

If you want fastest path to value in V1:

1. Start with custom Python agent or basic OpenAI/Anthropic integration.
2. Add LangChain callback only when you only need LLM-call capture.
3. Use multi-agent tags (`agent_name`, `trace_id`, `parent_call_id`) from day 1 even without multi-agent UI.

---

## Non-Surprise Policy

Before onboarding a project, always confirm:

- framework in use
- required coverage depth (LLM-only vs full chain/tool lifecycle)
- accepted gap level for V1

If required depth is beyond V1 support, communicate defer decision upfront.
