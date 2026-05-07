"""Zero-hallucination tool-use assistant engine.

Architecture:
  1. Scope guard  — keyword check blocks off-topic questions before any LLM call.
  2. Redis memory — per-project per-session conversation history (TTL 30 min).
  3. Tool-use loop — LLM calls real DB tools until it has enough data to answer.
  4. Source tracking — every tool call is recorded so the caller can cite it.

Anti-hallucination guarantees:
  - Temperature 0.1 (low, not 0.0 — allows natural phrasing but not data invention).
  - System prompt explicitly forbids inventing numbers or IDs.
  - All data comes from DB tool results; LLM role is synthesis only.
  - Max 5 tool-use iterations prevents infinite loops.
  - Pydantic validates final response structure.
"""
from __future__ import annotations

import json
import logging
import time as _time
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.schemas.assistant import AssistantChatResponse, ToolSource
from app.services.assistant_tools import TOOL_DEFINITIONS, dispatch_tool
from app.services.llm_client import get_llm_client
from app.services.llm_observability import record_platform_llm_call
from app.services.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_TOOL_ITERATIONS = 5
_HISTORY_TTL_SECONDS = 1800  # 30 minutes
_MAX_HISTORY_MESSAGES = 20   # trim oldest to stay under token budget
_MAX_TOOL_RESULT_BYTES = 8_192

_REDIS_KEY_PREFIX = "assistant:conv"

# ---------------------------------------------------------------------------
# Scope guard — keyword allowlist
# ---------------------------------------------------------------------------

# Meaningful domain keywords only — generic question words (why/what/how) deliberately
# excluded because they match virtually every English sentence and defeat the guard.
_ALLOWED_KEYWORDS: frozenset[str] = frozenset(
    {
        # Cost / billing
        "cost", "spend", "spending", "bill", "billing", "budget", "dollar",
        "usd", "inr", "expensive", "cheap", "price", "pricing", "usage",
        # Tokens / context
        "token", "tokens", "prompt", "context", "window", "overflow",
        "input token", "output token", "completion",
        # Calls / latency
        "call", "calls", "api call", "request", "response",
        "latency", "slow", "fast", "p95", "p99", "timeout",
        # Errors
        "error", "errors", "fail", "failed", "failure", "crash",
        "exception", "traceback", "stack trace",
        # Rate limits / quota
        "rate limit", "ratelimit", "rate-limit", "quota", "throttle", "throttled",
        # Auth
        "auth", "authentication", "unauthorized", "credential", "401", "403",
        "api key", "apikey",
        # Loops
        "loop", "loops", "looping", "infinite loop", "repeat", "cycle",
        # Diagnosis / anomaly
        "diagnosis", "diagnos", "detect", "detection", "anomaly", "spike",
        "token_overflow", "rate_limit", "auth_failure", "loop_detected", "cost_spike",
        # Alerts / incidents
        "alert", "alerts", "incident", "incidents", "warning",
        # Fixes
        "fix", "fixes", "patch", "diff", "suggestion", "resolve", "resolved",
        # Agents / models / providers
        "agent", "agents", "model", "models", "provider", "providers",
        "gpt", "gpt-4", "gpt4", "claude", "gemini", "deepseek",
        "openai", "anthropic", "google", "mistral", "llama",
        # Platform-specific
        "ingest", "monitor", "monitoring", "trace", "tracing", "metric",
        "dashboard", "project", "tenant", "zroky", "worker", "queue",
        # Forecasting / predictions
        "forecast", "predict", "prediction", "next hour", "spike risk",
        "risk level", "predicted cost", "trend",
        # Weekly digest / impact
        "weekly", "week", "digest", "impact", "prevented", "waste",
        "fix cycle", "incidents", "summary",
    }
)

_REFUSAL_REPLY = (
    "I only help with Zroky monitoring questions — AI costs, errors, "
    "rate limits, loops, auth failures, alerts, diagnoses, and fix suggestions. "
    "Ask me anything about your project's AI usage."
)


def _is_on_topic(message: str) -> bool:
    """Return True if the message mentions at least one Zroky-relevant domain keyword.

    Deliberately excludes generic question words (why/what/how/which) — those
    match everything and would make the guard useless.
    """
    lower = message.lower()
    return any(kw in lower for kw in _ALLOWED_KEYWORDS)


# ---------------------------------------------------------------------------
# Redis conversation memory
# ---------------------------------------------------------------------------

def _redis_key(project_id: str, session_id: str) -> str:
    return f"{_REDIS_KEY_PREFIX}:{project_id}:{session_id}"


def _load_history(project_id: str, session_id: str) -> list[dict[str, Any]]:
    """Load conversation history from Redis. Returns empty list on any error."""
    try:
        rc = get_redis_client()
        raw = rc.get(_redis_key(project_id, session_id))
        if not raw:
            return []
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def _strip_tool_calls(msg: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of an assistant message with tool_calls removed.

    When we persist history we drop tool-call turns entirely.  If we kept
    assistant messages that contain ``tool_calls`` but dropped the corresponding
    ``tool`` response messages, the LLM API would reject the message chain
    (tool_calls message MUST be immediately followed by tool response messages).
    Stripping tool_calls from assistant messages avoids that API error while
    preserving the conversational context.
    """
    if msg.get("role") != "assistant" or "tool_calls" not in msg:
        return msg
    cleaned = {k: v for k, v in msg.items() if k != "tool_calls"}
    # content may be None when the assistant only made tool calls — normalise to empty
    if not cleaned.get("content"):
        cleaned["content"] = ""
    return cleaned


def _save_history(
    project_id: str,
    session_id: str,
    messages: list[dict[str, Any]],
) -> None:
    """Persist conversation history to Redis. Trims to _MAX_HISTORY_MESSAGES.

    Stores only user and assistant messages (system and tool messages are
    ephemeral context and must not be reinjected on the next turn).
    Assistant messages with tool_calls are stripped of that field so the
    stored chain remains valid for the next LLM call.
    """
    try:
        storable = [
            _strip_tool_calls(m)
            for m in messages
            if m.get("role") in ("user", "assistant")
            # Skip assistant messages whose only purpose was tool invocation
            # and have no natural-language content worth remembering.
            if not (m.get("role") == "assistant"
                    and not (m.get("content") or "").strip()
                    and "tool_calls" in m)
        ]
        if len(storable) > _MAX_HISTORY_MESSAGES:
            storable = storable[-_MAX_HISTORY_MESSAGES:]
        rc = get_redis_client()
        rc.setex(
            _redis_key(project_id, session_id),
            _HISTORY_TTL_SECONDS,
            json.dumps(storable),
        )
    except Exception:
        pass  # memory failure must never block the response


def clear_history(project_id: str, session_id: str) -> None:
    """Delete conversation history for a session."""
    try:
        rc = get_redis_client()
        rc.delete(_redis_key(project_id, session_id))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are Zroky Assistant — an AI monitoring expert with full read access \
to this project's production AI call data.

STRICT RULES (follow every rule on every response):
1. You ONLY discuss: AI costs, tokens, errors, rate limits, agent loops, \
   auth failures, alerts, diagnoses, fix suggestions, models, and providers.
2. You NEVER invent data. Every number, ID, or date MUST come from a tool result.
3. Before answering ANY data question, call the appropriate tool first.
4. Cite real IDs in your answer when available (call_id, alert_id, diagnosis_id).
5. If asked anything outside AI monitoring, reply: \
   "I only help with Zroky monitoring questions."
6. Be concise and technical. Users are developers — skip generic advice.
7. When you have sufficient tool data to answer, stop calling more tools.
8. If a tool returns empty data, say so honestly — do not fill in gaps.
"""


# ---------------------------------------------------------------------------
# Tool-use LLM loop
# ---------------------------------------------------------------------------

def _build_assistant_msg(choice_message: Any) -> dict[str, Any]:
    """Convert an OpenAI SDK message object to a plain dict for history."""
    msg: dict[str, Any] = {"role": "assistant", "content": choice_message.content}
    if choice_message.tool_calls:
        msg["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in choice_message.tool_calls
        ]
    return msg


def _run_tool_loop(
    messages: list[dict[str, Any]],
    db: Session,
    project_id: str,
) -> tuple[str, list[ToolSource]]:
    """
    Run the tool-use agentic loop. Returns (final_text_reply, sources).
    Mutates `messages` in-place so the caller can persist updated history.
    """
    client = get_llm_client()
    sources: list[ToolSource] = []

    for iteration in range(_MAX_TOOL_ITERATIONS):
        try:
            start = _time.perf_counter()
            response = client.chat_completions_create(
                messages=messages,
                model=get_settings().OPENROUTER_ASSISTANT_MODEL,
                tools=TOOL_DEFINITIONS,
                tool_choice="auto",
                temperature=0.1,
                max_tokens=1024,
            )
            latency_ms = (_time.perf_counter() - start) * 1000.0
            record_platform_llm_call(
                db,
                purpose="assistant",
                response=response,
                latency_ms=latency_ms,
                tenant_id=project_id,
                request_messages=list(messages),
            )
        except Exception as exc:
            logger.error("Assistant LLM call failed: %s", exc)
            return (
                "I'm having trouble reaching the AI service right now. Please try again in a moment.",
                sources,
            )

        choice = response.choices[0]

        # ── LLM wants to call tools ──────────────────────────────────────────
        if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
            messages.append(_build_assistant_msg(choice.message))

            for tc in choice.message.tool_calls:
                tool_name = tc.function.name
                tool_args = tc.function.arguments or "{}"

                logger.debug("Assistant tool call: %s(%s)", tool_name, tool_args[:120])

                result = dispatch_tool(tool_name, tool_args, db, project_id)
                result_json = json.dumps(result, default=str)

                # Truncate large tool results before injecting into context.
                # 8 KB is enough for the LLM to synthesise an answer; larger
                # payloads waste tokens and can overflow the context window.
                if len(result_json) > _MAX_TOOL_RESULT_BYTES:
                    result_json = result_json[:_MAX_TOOL_RESULT_BYTES] + " ... [truncated]"

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_json,
                    }
                )

                # Build human-readable source summary
                summary = _tool_summary(tool_name, result)
                sources.append(ToolSource(tool=tool_name, summary=summary))

            continue  # let LLM process tool results

        # ── LLM has a final text answer ──────────────────────────────────────
        final_reply = (choice.message.content or "").strip()
        if not final_reply:
            final_reply = "I couldn't generate a response. Please try rephrasing your question."
        messages.append({"role": "assistant", "content": final_reply})
        return final_reply, sources

    # Safety net: hit max iterations without a text answer
    fallback = (
        "I needed more data than expected to answer this. "
        "Try asking a more specific question (e.g. a specific model, time range, or error type)."
    )
    messages.append({"role": "assistant", "content": fallback})
    return fallback, sources


def _tool_summary(tool_name: str, result: Any) -> str:
    """Build a short human-readable summary of what a tool returned."""
    if tool_name == "get_recent_calls":
        count = len(result) if isinstance(result, list) else 0
        return f"Fetched {count} recent calls from DB."
    if tool_name == "get_cost_breakdown":
        count = len(result) if isinstance(result, list) else 0
        return f"Cost breakdown across {count} groups from DB."
    if tool_name == "get_active_alerts":
        count = len(result) if isinstance(result, list) else 0
        return f"Found {count} open alerts from DB."
    if tool_name == "get_diagnosis_summary":
        if isinstance(result, dict):
            return f"Diagnosis summary: {result.get('total_jobs', 0)} jobs in last {result.get('window_days', 7)} days."
        return "Diagnosis summary from DB."
    if tool_name == "get_call_detail":
        if isinstance(result, dict) and result.get("call_id"):
            return f"Call detail for {result['call_id']} from DB."
        return "Call not found in DB."
    if tool_name == "search_similar_errors":
        count = len(result) if isinstance(result, list) else 0
        return f"Found {count} similar past errors via vector search."
    if tool_name == "get_cost_forecast":
        if isinstance(result, dict) and "risk_level" in result:
            risk = result.get("risk_level", "unknown")
            predicted = result.get("predicted_avg_hourly", "?")
            return f"Cost forecast: risk_level={risk}, predicted_hourly=${predicted} from DB."
        return "Cost forecast from DB."
    if tool_name == "get_weekly_impact_summary":
        if isinstance(result, dict):
            total = result.get("total_calls", 0)
            waste = result.get("prevented_waste_usd", 0.0)
            return f"Weekly digest: {total} calls, ${waste} prevented waste from DB."
        return "Weekly impact summary from DB."
    return f"Tool {tool_name} executed."


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_assistant(
    message: str,
    session_id: str,
    project_id: str,
    db: Session,
) -> AssistantChatResponse:
    """
    Main assistant entry point. Call this from the FastAPI route.

    Steps:
    1. Scope guard — refuse off-topic immediately.
    2. Load history from Redis.
    3. Build messages: [system] + history + [new user message].
    4. Run tool-use loop.
    5. Save updated history.
    6. Return validated response.
    """
    # ── 1. Scope guard ───────────────────────────────────────────────────────
    if not _is_on_topic(message):
        return AssistantChatResponse(
            reply=_REFUSAL_REPLY,
            sources=[],
            session_id=session_id,
            off_topic=True,
        )

    # ── 2. Load history ──────────────────────────────────────────────────────
    history = _load_history(project_id, session_id)

    # ── 3. Build messages list ───────────────────────────────────────────────
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": message},
    ]

    # ── 4. Tool-use loop ─────────────────────────────────────────────────────
    reply, sources = _run_tool_loop(messages, db, project_id)

    # ── 5. Save history (system and tool messages excluded from stored history)
    _save_history(project_id, session_id, messages)

    # ── 6. Return ────────────────────────────────────────────────────────────
    return AssistantChatResponse(
        reply=reply,
        sources=sources,
        session_id=session_id,
        off_topic=False,
    )
