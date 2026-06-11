from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.services.detectors._payload import _as_bool, _as_str, _pick
from app.services.privacy import mask_value


_TOOL_CALL_FAILURE_CONFIDENCE = 0.93
_TOOL_SELECTION_FAILURE_CONFIDENCE = 0.88
_TOOL_ARGUMENT_MISMATCH_CONFIDENCE = 0.92


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _tool_name(tool: Mapping[str, Any]) -> str:
    return _as_str(
        tool.get("tool_name")
        or tool.get("name")
        or tool.get("tool")
        or tool.get("function_name")
    )


def _tool_status(tool: Mapping[str, Any]) -> str:
    return _as_str(tool.get("status") or tool.get("state")).lower()


def _tool_args(tool: Mapping[str, Any]) -> Mapping[str, Any]:
    args = tool.get("args") or tool.get("arguments") or tool.get("input") or tool.get("tool_args")
    return args if isinstance(args, Mapping) else {}


def _tool_error(tool: Mapping[str, Any]) -> str:
    error = tool.get("error") or tool.get("error_message") or tool.get("error_code")
    if isinstance(error, Mapping):
        error = error.get("message") or error.get("code")
    return _as_str(error)


def _tool_records(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    records: list[Mapping[str, Any]] = []
    for key in ("tool_calls", "tool_calls_made", "tools", "tool_lifecycle_summary"):
        for item in _as_list(payload.get(key)):
            if isinstance(item, Mapping):
                records.append(item)

    trace = _as_mapping(payload.get("trace_graph"))
    for span in _as_list(trace.get("spans")):
        if not isinstance(span, Mapping):
            continue
        span_type = _as_str(span.get("span_type")).lower()
        tool = _as_mapping(span.get("tool"))
        if span_type == "tool" or tool:
            merged = dict(tool)
            merged.setdefault("tool_name", span.get("span_name"))
            merged.setdefault("status", span.get("status"))
            merged.setdefault("error_code", span.get("error_code"))
            if span.get("input") is not None:
                merged.setdefault("args", span.get("input"))
            if span.get("output") is not None:
                merged.setdefault("output", span.get("output"))
            records.append(merged)

    single_name = _as_str(_pick(payload, ("tool_name",), ("tool", "name")))
    if single_name:
        records.append(
            {
                "tool_name": single_name,
                "args": _pick(payload, ("tool_args",), ("tool", "args")),
                "status": _pick(payload, ("tool_status",), ("tool", "status")),
                "error": _pick(payload, ("tool_error",), ("tool", "error")),
            }
        )
    return records


def detect_tool_call_failure(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    for tool in _tool_records(payload):
        name = _tool_name(tool) or "unknown_tool"
        status = _tool_status(tool)
        error = _tool_error(tool)
        success = tool.get("tool_success")
        failed = (
            status in {"failed", "error", "errored", "timeout", "rejected"}
            or bool(error)
            or (_as_bool(success, fallback=True) is False)
        )
        if not failed:
            continue
        signature = f"tool_call_failure:{name}:{status or error[:80] or 'failed'}"
        return {
            "category": "TOOL_CALL_FAILURE",
            "speed_class": "fast",
            "confidence": _TOOL_CALL_FAILURE_CONFIDENCE,
            "what_happened": f"{name} failed during the agent run.",
            "why_it_matters": "The agent cannot complete the business task when a required tool fails or returns an unusable result.",
            "root_cause": f"Tool {name} returned {status or 'a failure'}{f': {error}' if error else '.'}",
            "recommended_next_action": "Replay the trace with the same tool snapshot, then fix the tool integration or fallback path.",
            "grouping_signature": signature,
            "severity_hint": "high",
            "evidence": {
                "tool_name": name,
                "status": status or None,
                "error": error[:240] if error else None,
                "trigger_rule": "tool_status_or_error_indicates_failure",
            },
        }
    return None


def detect_tool_selection_failure(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    records = _tool_records(payload)
    actual_tools = [_tool_name(item) for item in records if _tool_name(item)]
    if not actual_tools:
        return None

    expected = _as_str(
        _pick(payload, ("expected_tool",), ("contract", "expected_tool"), ("tool", "expected_tool"))
    )
    required = _as_str(
        _pick(payload, ("required_tool",), ("contract", "required_tool"), ("tool", "required_tool"))
    )
    allowed_raw = _pick(payload, ("allowed_tools",), ("contract", "allowed_tools"), ("tool", "allowed_tools"))
    allowed = {str(item).strip() for item in _as_list(allowed_raw) if str(item).strip()}

    if expected and expected not in actual_tools:
        actual = actual_tools[0]
        reason = f"expected {expected}, used {actual}"
        signature = f"tool_selection_failure:expected:{expected}:actual:{actual}"
    elif required and required not in actual_tools:
        actual = actual_tools[0]
        reason = f"required {required}, used {actual}"
        signature = f"tool_selection_failure:required:{required}:actual:{actual}"
    elif allowed and any(tool not in allowed for tool in actual_tools):
        actual = next(tool for tool in actual_tools if tool not in allowed)
        reason = f"{actual} is outside the allowed tool set"
        signature = f"tool_selection_failure:disallowed:{actual}"
    else:
        return None

    return {
        "category": "TOOL_SELECTION_FAILURE",
        "speed_class": "fast",
        "confidence": _TOOL_SELECTION_FAILURE_CONFIDENCE,
        "what_happened": f"The agent selected the wrong tool: {reason}.",
        "why_it_matters": "Wrong tool choice usually means the agent can look successful while taking the wrong business action.",
        "root_cause": f"Tool routing contract was violated: {reason}.",
        "recommended_next_action": "Tighten tool descriptions and add a replay assertion for expected tool sequence.",
        "grouping_signature": signature,
        "severity_hint": "high",
        "evidence": {
            "actual_tools": actual_tools[:8],
            "expected_tool": expected or None,
            "required_tool": required or None,
            "allowed_tools": sorted(allowed) if allowed else None,
            "trigger_rule": "expected_required_or_allowed_tool_mismatch",
        },
    }


def detect_tool_argument_mismatch(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    explicit_errors = _as_list(
        _pick(payload, ("tool_argument_errors",), ("tool", "argument_errors"))
    )
    if explicit_errors:
        first = str(explicit_errors[0])
        name = _as_str(_pick(payload, ("tool_name",), ("tool", "name")), fallback="unknown_tool")
        return _argument_result(name, first, "explicit_tool_argument_errors")

    required_raw = _pick(payload, ("required_tool_args",), ("tool", "required_args"), ("contract", "required_tool_args"))
    required = [str(item).strip() for item in _as_list(required_raw) if str(item).strip()]
    arg_types = _as_mapping(_pick(payload, ("tool_arg_types",), ("tool", "arg_types"), ("contract", "tool_arg_types")))
    for tool in _tool_records(payload):
        name = _tool_name(tool) or "unknown_tool"
        args = _tool_args(tool)
        missing = [key for key in required if key not in args]
        if missing:
            return _argument_result(name, f"missing required args: {', '.join(missing)}", "missing_required_args")
        mismatch = _first_type_mismatch(args, arg_types)
        if mismatch:
            return _argument_result(name, mismatch, "argument_type_mismatch")
    return None


def _first_type_mismatch(args: Mapping[str, Any], arg_types: Mapping[str, Any]) -> str | None:
    type_map: dict[str, type | tuple[type, ...]] = {
        "string": str,
        "str": str,
        "number": (int, float),
        "integer": int,
        "int": int,
        "boolean": bool,
        "bool": bool,
        "object": Mapping,
        "array": list,
        "list": list,
    }
    for key, expected in arg_types.items():
        if key not in args:
            continue
        target = type_map.get(str(expected).strip().lower())
        if target is None:
            continue
        value = args[key]
        if target is int and isinstance(value, bool):
            return f"{key} expected integer, got bool"
        if not isinstance(value, target):
            return f"{key} expected {expected}, got {type(value).__name__}"
    return None


def _argument_result(tool_name: str, violation: str, trigger_rule: str) -> dict[str, Any]:
    signature = f"tool_argument_mismatch:{tool_name}:{violation[:120]}"
    return {
        "category": "TOOL_ARGUMENT_MISMATCH",
        "speed_class": "fast",
        "confidence": _TOOL_ARGUMENT_MISMATCH_CONFIDENCE,
        "what_happened": f"{tool_name} was called with invalid arguments.",
        "why_it_matters": "Bad tool arguments can execute the wrong operation or cause silent business-task failure.",
        "root_cause": f"Tool {tool_name} argument contract failed: {violation}.",
        "recommended_next_action": "Add argument validation before tool execution and replay the trace with a tool-argument assertion.",
        "grouping_signature": signature,
        "severity_hint": "high",
        "evidence": mask_value(
            {
                "tool_name": tool_name,
                "violation": violation,
                "trigger_rule": trigger_rule,
            }
        ),
    }
