from app.services._internal.replay_executor_common import *

def make_live_llm_resolver(
    *,
    replay_mode: str = REPLAY_MODE_REAL_LLM,
    candidate_prompt_override: Optional[str] = None,
    candidate_model_override: Optional[str] = None,
    budget_tracker: Optional[ReplayBudgetTracker] = None,
) -> ActualOutputResolver:
    """Return an ``ActualOutputResolver`` that re-executes the source Call
    against the live LLM provider, applying optional prompt/model overrides.

    Parameters
    ----------
    candidate_prompt_override
        When set, replaces the ``messages`` or ``prompt`` field from the
        original Call payload before issuing the provider request.
    candidate_model_override
        When set, replaces the model slug from the original Call payload.
    budget_tracker
        Optional spend guard. The resolver checks ``can_spend`` before
        each provider call and returns ``reason="budget_exceeded"`` when
        the cap would be breached.
    """
    resolved_replay_mode = _normalize_live_replay_mode(replay_mode)

    def _resolve(trace: GoldenTrace, source_call: Optional[Call]) -> ActualOutput:
        mode_metadata: dict[str, Any] = {
            "requested_replay_mode": resolved_replay_mode,
        }
        if source_call is None:
            return ActualOutput(
                text=None,
                reason="source_call_missing",
                metadata=mode_metadata,
            )

        payload = _safe_json_object(source_call.payload_json)

        if resolved_replay_mode == REPLAY_MODE_LIVE_SANDBOX:
            return _run_live_sandbox_replay(
                trace=trace,
                source_call=source_call,
                payload=payload,
                candidate_prompt_override=candidate_prompt_override,
                candidate_model_override=candidate_model_override,
                budget_tracker=budget_tracker,
                mode_metadata=mode_metadata,
            )

        # Build messages list. Prefer the modern "messages" array; fall
        # back to a single user message from "prompt".
        messages: list[dict[str, Any]]
        raw_messages = payload.get("messages")
        if isinstance(raw_messages, list):
            messages = [dict(m) for m in raw_messages if isinstance(m, dict)]
        else:
            prompt_text = str(payload.get("prompt") or "")
            if not prompt_text:
                return ActualOutput(
                    text=None,
                    reason="source_call_missing_prompt",
                    metadata=mode_metadata,
                )
            messages = [{"role": "user", "content": prompt_text}]

        if resolved_replay_mode == REPLAY_MODE_MOCKED_TOOL:
            tool_snapshot = _extract_tool_snapshot(source_call)
            if tool_snapshot is None:
                mode_metadata["tool_behavior_diff"] = {
                    "available": False,
                    "changed": None,
                    "mode": "mocked_tool",
                    "reason": "tool_snapshot_missing",
                }
                return ActualOutput(
                    text=None,
                    reason="tool_snapshot_missing",
                    metadata=mode_metadata,
                )
            _prepend_replay_context(
                messages,
                title=(
                    "Replay mode: use these frozen tool outputs as the only "
                    "tool evidence. Do not invent new tool results."
                ),
                value=tool_snapshot["data"],
            )
            mode_metadata["tool_behavior_diff"] = {
                "available": True,
                "changed": False,
                "baseline": tool_snapshot["data"],
                "candidate": tool_snapshot["data"],
                "mode": "mocked_tool_frozen_outputs",
                "source": tool_snapshot["source"],
            }
        elif resolved_replay_mode == REPLAY_MODE_SHADOW:
            mode_metadata["shadow_comparison"] = {
                "baseline": "golden_trace_expected_output",
                "candidate": "live_model_output",
            }

        # Apply prompt override — replace the user message content when
        # only one user message exists, otherwise prepend a system message.
        if candidate_prompt_override and candidate_prompt_override.strip():
            user_msgs = [i for i, m in enumerate(messages) if m.get("role") == "user"]
            if len(user_msgs) == 1:
                messages[user_msgs[0]]["content"] = candidate_prompt_override.strip()
            else:
                messages.insert(
                    0,
                    {
                        "role": "system",
                        "content": candidate_prompt_override.strip(),
                    },
                )

        # Determine model — override wins, then original payload, then
        # the source Call column.
        model = candidate_model_override or str(payload.get("model") or "") or source_call.model
        if not model:
            return ActualOutput(
                text=None,
                reason="source_call_missing_model",
                metadata=mode_metadata,
            )

        # Budget gate — refuse the call if we'd exceed the run cap.
        if budget_tracker is not None and not budget_tracker.can_spend():
            return ActualOutput(
                text=None,
                reason="budget_exceeded",
                metadata=mode_metadata,
            )

        # Issue the live provider call.
        try:
            from app.services.llm_client import get_llm_client

            start = datetime.now(timezone.utc)
            response = get_llm_client().chat_completions_create(
                messages=messages,
                model=model,
            )
            latency_ms = int(
                (datetime.now(timezone.utc) - start).total_seconds() * 1000
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "live_llm_resolver.provider_error run=%s trace=%s err=%s",
                trace.golden_set_id,
                trace.id,
                exc,
                exc_info=True,
            )
            return ActualOutput(
                text=None,
                reason=f"provider_error:{type(exc).__name__}",
                metadata=mode_metadata,
            )

        # Extract text from the completion.
        try:
            text = str(response.choices[0].message.content or "")
        except Exception:  # noqa: BLE001
            text = ""

        # Extract usage when available (OpenRouter / OpenAI shape).
        usage = getattr(response, "usage", None) or {}
        input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)

        # Rough cost estimate (OpenRouter-style pricing is ~$ per 1M tokens).
        # We keep the estimate conservative so the budget gate doesn't overshoot.
        # A more precise calculation lives in the cost-ingestion pipeline.
        cost_total = _estimate_llm_cost(model, input_tokens, output_tokens)

        if budget_tracker is not None:
            budget_tracker.record_spend(cost_total)

        return ActualOutput(
            text=text,
            model=model,
            latency_ms=latency_ms,
            cost_total=cost_total,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            metadata=mode_metadata,
        )

    return _resolve


def _normalize_live_replay_mode(replay_mode: str | None) -> str:
    mode = (replay_mode or REPLAY_MODE_REAL_LLM).strip() or REPLAY_MODE_REAL_LLM
    if mode in REAL_COMPARISON_REPLAY_MODES:
        return mode
    return REPLAY_MODE_REAL_LLM


def _prepend_replay_context(
    messages: list[dict[str, Any]],
    *,
    title: str,
    value: Any,
) -> None:
    messages.insert(
        0,
        {
            "role": "system",
            "content": f"{title}\n\n{_compact_json(value, limit=6000)}",
        },
    )


def _compact_json(value: Any, *, limit: int = 6000) -> str:
    try:
        text = json.dumps(value, separators=(",", ":"), default=str)
    except Exception:
        text = str(value)
    if len(text) <= limit:
        return text
    return text[:limit] + "...[truncated]"


def _safe_json_value(raw: Optional[str]) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return raw


def _extract_tool_snapshot(source_call: Optional[Call]) -> dict[str, Any] | None:
    if source_call is None:
        return None

    summary_raw = source_call.tool_lifecycle_summary_json
    if summary_raw:
        return {
            "source": "tool_lifecycle_summary_json",
            "data": _safe_json_value(summary_raw),
        }

    payload = _safe_json_object(source_call.payload_json)
    for key in (
        "tool_lifecycle_summary",
        "tool_calls_made",
        "tool_calls",
        "tool_results",
        "tools",
    ):
        value = payload.get(key)
        if value not in (None, "", [], {}):
            return {
                "source": f"payload.{key}",
                "data": value,
            }
    return None


def _run_live_sandbox_replay(
    *,
    trace: GoldenTrace,
    source_call: Call,
    payload: dict[str, Any],
    candidate_prompt_override: Optional[str],
    candidate_model_override: Optional[str],
    budget_tracker: Optional[ReplayBudgetTracker],
    mode_metadata: dict[str, Any],
) -> ActualOutput:
    from app.core.config import get_settings

    settings = get_settings()
    sandbox_url = (settings.REPLAY_SANDBOX_WORKER_URL or "").strip()
    if not sandbox_url:
        mode_metadata["tool_behavior_diff"] = {
            "available": False,
            "changed": None,
            "mode": "live_sandbox",
            "reason": "sandbox_tool_runtime_unavailable",
        }
        return ActualOutput(
            text=None,
            reason="sandbox_tool_runtime_unavailable",
            metadata=mode_metadata,
        )

    if budget_tracker is not None and not budget_tracker.can_spend():
        return ActualOutput(
            text=None,
            reason="budget_exceeded",
            metadata=mode_metadata,
        )

    tool_snapshot = _extract_tool_snapshot(source_call)
    body = {
        "project_id": source_call.project_id,
        "call_id": source_call.id,
        "golden_trace_id": trace.id,
        "payload": payload,
        "candidate_prompt_override": candidate_prompt_override,
        "candidate_model_override": candidate_model_override,
        "tool_snapshot": tool_snapshot["data"] if tool_snapshot else None,
    }
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if settings.REPLAY_SANDBOX_WORKER_TOKEN:
        headers["Authorization"] = f"Bearer {settings.REPLAY_SANDBOX_WORKER_TOKEN}"

    try:
        import httpx

        start = datetime.now(timezone.utc)
        response = httpx.post(
            sandbox_url,
            json=body,
            headers=headers,
            timeout=float(settings.REPLAY_SANDBOX_TIMEOUT_SECONDS),
        )
        latency_ms = int(
            (datetime.now(timezone.utc) - start).total_seconds() * 1000
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "live_sandbox_resolver.worker_error call=%s trace=%s err=%s",
            source_call.id,
            trace.id,
            exc,
            exc_info=True,
        )
        mode_metadata["tool_behavior_diff"] = {
            "available": False,
            "changed": None,
            "mode": "live_sandbox",
            "reason": f"sandbox_worker_error:{type(exc).__name__}",
        }
        return ActualOutput(
            text=None,
            reason=f"sandbox_worker_error:{type(exc).__name__}",
            metadata=mode_metadata,
        )

    if not isinstance(data, dict):
        return ActualOutput(
            text=None,
            reason="sandbox_worker_invalid_response",
            metadata=mode_metadata,
        )

    text_value = (
        data.get("output_text")
        or data.get("text")
        or data.get("response")
        or data.get("completion")
    )
    if text_value is None:
        return ActualOutput(
            text=None,
            reason="sandbox_worker_missing_output",
            metadata=mode_metadata,
        )

    tool_diff = data.get("tool_behavior_diff")
    if isinstance(tool_diff, dict):
        mode_metadata["tool_behavior_diff"] = tool_diff
    else:
        mode_metadata["tool_behavior_diff"] = {
            "available": tool_snapshot is not None,
            "changed": bool(data.get("tool_behavior_changed")),
            "baseline": tool_snapshot["data"] if tool_snapshot else None,
            "candidate": data.get("tool_results"),
            "mode": "live_sandbox",
            "source": "sandbox_worker",
        }

    cost_total = _as_float(data.get("cost_total") or data.get("cost_usd"), 0.0)
    if budget_tracker is not None:
        budget_tracker.record_spend(cost_total)

    return ActualOutput(
        text=str(text_value),
        model=str(data.get("model") or candidate_model_override or source_call.model or "") or None,
        latency_ms=_as_int(data.get("latency_ms"), latency_ms),
        cost_total=cost_total,
        input_tokens=_as_int(data.get("input_tokens"), 0),
        output_tokens=_as_int(data.get("output_tokens") or data.get("completion_tokens"), 0),
        metadata=mode_metadata,
    )


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _estimate_llm_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Return a conservative USD cost estimate for a provider call.

    Uses cached per-model pricing heuristics. Real billing is computed
    by the ingestion pipeline from the provider invoice; this is only
    for the replay budget tracker.
    """
    # Normalise model slug (strip provider prefix).
    slug = model.lower().split("/")[-1]

    # Conservative defaults — over-estimate so the budget gate is safe.
    # Values are per-1M-tokens in USD.
    PRICING: dict[str, tuple[float, float]] = {
        # Anthropic
        "claude-3-haiku": (0.25, 1.25),
        "claude-3-sonnet": (3.0, 15.0),
        "claude-3-opus": (15.0, 75.0),
        "claude-3.5-sonnet": (3.0, 15.0),
        "claude-3.5-haiku": (0.25, 1.25),
        # OpenAI
        "gpt-4o": (5.0, 15.0),
        "gpt-4o-mini": (0.15, 0.6),
        "gpt-4-turbo": (10.0, 30.0),
        "gpt-4": (30.0, 60.0),
        "gpt-3.5-turbo": (0.5, 1.5),
        # DeepSeek
        "deepseek-chat": (0.14, 0.28),
        "deepseek-chat-v3": (0.14, 0.28),
        # Default fallback — high enough to be safe, low enough not to
        # starve runs on unknown models.
    }

    in_rate, out_rate = PRICING.get(slug, (5.0, 15.0))
    return round(
        (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000, 8
    )


__all__ = [name for name in globals() if not name.startswith("__")]
