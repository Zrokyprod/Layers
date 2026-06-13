from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, TYPE_CHECKING

from app.services.privacy import mask_text

if TYPE_CHECKING:
    from app.services.fix_generator import FixGenerationInput

_BRANCH_SANITIZE_RE = re.compile(r"[^a-z0-9._/-]+")

def _token_overflow_diff_from_snippet(*, snippet: str, subtype: str, token_budget: int) -> str:
    line = _first_relevant_line(snippet, ("messages", "history", "max_tokens"))
    if not line:
        return _conceptual_diff(
            "Snippet did not expose message construction.",
            [
                f"Bound message/history tokens to about {token_budget} before provider call.",
            ],
        )

    if "max_tokens" in line and "=" in line:
        after = _replace_assignment_rhs(
            line,
            f"min({_assignment_rhs(line)}, {max(256, token_budget // 4)})",
        )
    elif "history" in line.lower() or subtype == "conversation_accumulation":
        after = _replace_assignment_rhs(
            line,
            f"<existing_history_summary_helper>({_assignment_rhs(line)}, token_budget={token_budget})",
        )
    else:
        after = _replace_assignment_rhs(
            line,
            f"<existing_prompt_budget_helper>({_assignment_rhs(line)}, token_budget={token_budget})",
        )

    return _before_after_diff(before=line, after=after)


def _loop_diff_from_snippet(snippet: str) -> str:
    line = _first_relevant_line(snippet, ("while True", "for "))
    if not line:
        return _conceptual_diff(
            "Snippet did not expose the loop dispatch.",
            [
                "Add a bounded loop counter and break on repeated no-progress signatures.",
            ],
        )

    stripped = line.strip()
    indent = line[: len(line) - len(line.lstrip())]
    if stripped.startswith("while True"):
        after = f"{indent}for _zroky_step in range(<configured_max_agent_steps>):"
    else:
        after = (
            f"{line}\n"
            f"{indent}    if <existing_no_progress_guard>(prompt_fingerprint):\n"
            f"{indent}        break"
        )

    return _before_after_diff(before=line, after=after)


def _derive_fix_confidence(
    *,
    diagnosis_confidence: float,
    strategy_confidence: float,
    has_code_snippet: bool,
) -> float:
    diagnosis = _clamp(diagnosis_confidence or 0.5, 0.0, 1.0)
    snippet_factor = 1.0 if has_code_snippet else 0.82
    return round(_clamp(diagnosis * strategy_confidence * snippet_factor, 0.25, 0.95), 2)


def _confidence_level(confidence: float) -> str:
    if confidence >= 0.80:
        return "high"
    if confidence >= 0.55:
        return "medium"
    return "low"


def _risk_level(diagnosis_type: str, confidence_level: str) -> str:
    if confidence_level == "low":
        return "high"
    if diagnosis_type == "LOOP_DETECTED":
        return "medium"
    if diagnosis_type == "TOKEN_OVERFLOW":
        return "low" if confidence_level == "high" else "medium"
    if diagnosis_type == "RATE_LIMIT":
        return "low" if confidence_level == "high" else "medium"
    if diagnosis_type == "AUTH_FAILURE":
        return "medium"
    if diagnosis_type == "COST_SPIKE":
        return "low"
    return "medium"


def _fix_scope(diagnosis_type: str) -> str:
    if diagnosis_type == "TOKEN_OVERFLOW":
        return "local"
    if diagnosis_type == "RATE_LIMIT":
        return "local"
    if diagnosis_type == "AUTH_FAILURE":
        return "module"
    if diagnosis_type == "COST_SPIKE":
        return "system"
    if diagnosis_type == "LOOP_DETECTED":
        return "module"
    return "local"


def _expected_impact(*, diagnosis_type: str, confidence_level: str) -> dict[str, Any]:
    if diagnosis_type == "TOKEN_OVERFLOW":
        return {
            "prevents": ["TOKEN_OVERFLOW errors", "provider context-length rejections"],
            "improves": ["request success rate", "latency stability"],
            "confidence": confidence_level,
        }
    if diagnosis_type == "RATE_LIMIT":
        return {
            "prevents": ["RATE_LIMIT errors", "request failures due to throttling"],
            "improves": ["request reliability", "transient failure handling"],
            "confidence": confidence_level,
        }
    if diagnosis_type == "AUTH_FAILURE":
        return {
            "prevents": ["AUTH_FAILURE errors", "unauthorized request rejections"],
            "improves": ["security posture", "credential management"],
            "confidence": confidence_level,
        }
    if diagnosis_type == "COST_SPIKE":
        return {
            "prevents": ["unexpected cost overruns", "budget exhaustion"],
            "improves": ["cost predictability", "resource efficiency"],
            "confidence": confidence_level,
        }
    if diagnosis_type == "LOOP_DETECTED":
        return {
            "prevents": ["runaway agent loops", "repeated no-progress tool calls"],
            "improves": ["agent reliability", "cost predictability"],
            "confidence": confidence_level,
        }
    return {
        "prevents": ["recurrence of the diagnosed failure if the selected fix is correct"],
        "improves": ["debuggability"],
        "confidence": confidence_level,
    }


def _blast_radius(*, fix_scope: str, target_file: str) -> str:
    if target_file == "unknown":
        return "medium"
    if fix_scope == "local":
        return "low"
    if fix_scope == "module":
        return "medium"
    return "high"


def _affected_paths(*, request: FixGenerationInput, target_file: str) -> list[str]:
    paths: list[str] = []
    if target_file and target_file != "unknown":
        paths.append(target_file)
    additional_paths = _as_text_list(request.call_context.get("affected_paths"))
    for path in additional_paths:
        if path not in paths:
            paths.append(path)
    return paths


def _fix_conflicts_with(request: FixGenerationInput) -> list[str]:
    raw = request.call_context.get("fix_conflicts_with")
    return _as_text_list(raw)


def _time_to_apply_estimate(
    *,
    diagnosis_type: str,
    target_file: str,
    patch_unified: str,
) -> str:
    if target_file == "unknown" or not patch_unified:
        return "15-30 minutes"
    if diagnosis_type == "LOOP_DETECTED":
        return "15-30 minutes"
    if diagnosis_type == "TOKEN_OVERFLOW":
        return "5-10 minutes"
    if diagnosis_type == "RATE_LIMIT":
        return "5-15 minutes"
    if diagnosis_type == "AUTH_FAILURE":
        return "10-20 minutes"
    if diagnosis_type == "COST_SPIKE":
        return "20-40 minutes"
    return "10-20 minutes"


def _rollout_strategy(diagnosis_type: str) -> str:
    strategies = {
        "TOKEN_OVERFLOW": "single-call",
        "RATE_LIMIT": "gradual",
        "AUTH_FAILURE": "guarded",
        "COST_SPIKE": "gradual",
        "LOOP_DETECTED": "guarded",
    }
    return strategies.get(diagnosis_type, "guarded")


def _requires_tests_update(diagnosis_type: str) -> bool:
    return diagnosis_type in {"TOKEN_OVERFLOW", "LOOP_DETECTED", "RATE_LIMIT", "AUTH_FAILURE", "COST_SPIKE"}


def _observability_checks(diagnosis_type: str) -> list[str]:
    if diagnosis_type == "TOKEN_OVERFLOW":
        return [
            "Monitor TOKEN_OVERFLOW error rate after deployment.",
            "Track request success rate for the affected route.",
            "Track response latency and response-quality complaints.",
        ]
    if diagnosis_type == "RATE_LIMIT":
        return [
            "Monitor RATE_LIMIT error rate and retry success rate.",
            "Track p99 latency under rate limiting conditions.",
        ]
    if diagnosis_type == "AUTH_FAILURE":
        return [
            "Monitor AUTH_FAILURE error rate and credential rotation success.",
            "Track authentication success rate after deployment.",
        ]
    if diagnosis_type == "COST_SPIKE":
        return [
            "Monitor cost per request and total spend trends.",
            "Track cache hit rates if caching is implemented.",
        ]
    if diagnosis_type == "LOOP_DETECTED":
        return [
            "Monitor LOOP_DETECTED recurrence after deployment.",
            "Track guard-trigger counts and agent task completion rate.",
            "Watch cost per task for unexpected increases or drops.",
        ]
    return [
        "Monitor recurrence of the diagnosed failure.",
        "Track error rate and latency for the affected path.",
    ]


def _fix_tags(diagnosis_type: str) -> list[str]:
    if diagnosis_type == "TOKEN_OVERFLOW":
        return ["token", "prompt", "context-limit"]
    if diagnosis_type == "RATE_LIMIT":
        return ["rate-limit", "retry", "backoff"]
    if diagnosis_type == "AUTH_FAILURE":
        return ["auth", "credentials", "security"]
    if diagnosis_type == "COST_SPIKE":
        return ["cost", "budget", "optimization"]
    if diagnosis_type == "LOOP_DETECTED":
        return ["agent-loop", "guardrail", "no-progress"]
    return ["diagnosis", "manual-review"]


def _fix_category(diagnosis_type: str) -> str:
    categories = {
        "TOKEN_OVERFLOW": "reliability",
        "RATE_LIMIT": "reliability",
        "AUTH_FAILURE": "security",
        "COST_SPIKE": "cost",
        "LOOP_DETECTED": "safety",
    }
    return categories.get(diagnosis_type, "reliability")


def _recommended_priority(*, diagnosis_type: str, confidence_level: str) -> str:
    if confidence_level == "low":
        return "P2"
    if diagnosis_type == "TOKEN_OVERFLOW":
        return "P0"
    if diagnosis_type == "LOOP_DETECTED":
        return "P1"
    if diagnosis_type == "RATE_LIMIT":
        return "P1"
    if diagnosis_type == "AUTH_FAILURE":
        return "P0"
    if diagnosis_type == "COST_SPIKE":
        return "P1"
    return "P1"


def _reversibility(*, patch_unified: str, target_file: str, diagnosis_type: str) -> str:
    # When no patch is generated (empty patch_unified), return moderate
    if not patch_unified:
        return "moderate"
    if target_file == "unknown":
        return "hard"
    reversibility_map = {
        "TOKEN_OVERFLOW": "easy",
        "RATE_LIMIT": "easy",
        "AUTH_FAILURE": "moderate",
        "COST_SPIKE": "easy",
        "LOOP_DETECTED": "moderate",
    }
    return reversibility_map.get(diagnosis_type, "moderate")


def _apply_instructions(*, target_file: str, anchor: str, patch_unified: str) -> list[str]:
    if target_file == "unknown":
        return [
            "Locate the file described by file_hint.",
            f"Find the relevant anchor or equivalent code: {anchor}.",
            "Apply the AFTER block manually after confirming it matches the call site.",
            "Run the scenario that previously triggered the diagnosis.",
        ]

    if patch_unified:
        return [
            f"Open `{target_file}`.",
            f"Locate the anchor line: `{anchor}`.",
            "Apply the unified patch draft or replace the BEFORE block with the AFTER block.",
            "Run the scenario that previously triggered the diagnosis.",
        ]

    return [
        f"Open `{target_file}`.",
        f"Locate the anchor or equivalent code: `{anchor}`.",
        "Apply the conceptual advisory change manually.",
        "Run the scenario that previously triggered the diagnosis.",
    ]


def _fix_id(*, diagnosis_type: str, diagnosis_id: str | None) -> str:
    safe_id = _slug(diagnosis_id or "diagnosis", fallback="diagnosis")
    return f"fix-{diagnosis_type.lower()}-{safe_id}"


def _target_file(request: FixGenerationInput) -> str:
    for value in (
        request.target_file,
        request.call_context.get("target_file"),
        request.call_context.get("file_path"),
        request.evidence.get("target_file"),
        request.evidence.get("file_path"),
    ):
        normalized = _as_text(value)
        if normalized:
            return normalized
    return "unknown"


def _file_hint(request: FixGenerationInput, diagnosis_type: str) -> str:
    explicit_hint = _as_text(request.file_hint)
    if explicit_hint:
        return explicit_hint

    if _target_file(request) != "unknown":
        return "Review the target file around the anchor before applying the patch."
    if diagnosis_type == "TOKEN_OVERFLOW":
        return "Apply where messages/history/max_tokens are constructed before the provider call."
    if diagnosis_type == "RATE_LIMIT":
        return "Apply at the provider client request site where rate limiting occurs."
    if diagnosis_type == "AUTH_FAILURE":
        return "Apply at the credential management or authentication flow code."
    if diagnosis_type == "COST_SPIKE":
        return "Apply cost controls at the provider call site or request routing layer."
    if diagnosis_type == "LOOP_DETECTED":
        return "Apply at the agent or tool dispatch loop that repeats without progress."
    return "Apply at the smallest call site directly responsible for the diagnosed behavior."


def _fallback_anchor(diagnosis_type: str) -> str:
    if diagnosis_type == "TOKEN_OVERFLOW":
        return "messages construction before provider call"
    if diagnosis_type == "RATE_LIMIT":
        return "provider request site"
    if diagnosis_type == "AUTH_FAILURE":
        return "credential configuration"
    if diagnosis_type == "COST_SPIKE":
        return "model request configuration"
    if diagnosis_type == "LOOP_DETECTED":
        return "agent/tool dispatch loop"
    return "unknown"


def _anchor_from_diff(diff: str) -> str | None:
    before, _after = _extract_before_after(diff)
    if before:
        return before.splitlines()[0].strip() or None
    return None


def _build_unified_patch(*, target_file: str, diff: str) -> str:
    if target_file == "unknown":
        return ""

    before, after = _extract_before_after(diff)
    if not before or not after:
        return ""

    before_lines = before.splitlines()
    after_lines = after.splitlines()
    old_count = max(1, len(before_lines))
    new_count = max(1, len(after_lines))
    hunk = [
        f"diff --git a/{target_file} b/{target_file}",
        f"--- a/{target_file}",
        f"+++ b/{target_file}",
        f"@@ -1,{old_count} +1,{new_count} @@",
    ]
    hunk.extend(f"-{line}" for line in before_lines)
    hunk.extend(f"+{line}" for line in after_lines)
    return "\n".join(hunk)


def _extract_before_after(diff: str) -> tuple[str | None, str | None]:
    if "--- BEFORE ---" not in diff or "--- AFTER ---" not in diff:
        return None, None

    before_part, after_part = diff.split("--- AFTER ---", 1)
    before = before_part.replace("--- BEFORE ---", "", 1).strip("\n")
    after = after_part.strip("\n")
    if not before.strip() or not after.strip():
        return None, None
    return before, after


def _conceptual_diff(header: str, lines: list[str]) -> str:
    rendered = ["--- ADVISORY ---", f"# {header}"]
    rendered.extend(f"# - {line}" for line in lines)
    return "\n".join(rendered)


def _before_after_diff(*, before: str, after: str) -> str:
    return "\n".join(
        [
            "--- BEFORE ---",
            before.rstrip(),
            "",
            "--- AFTER ---",
            after.rstrip(),
        ]
    )


def _first_relevant_line(snippet: str, needles: tuple[str, ...]) -> str | None:
    for line in snippet.splitlines():
        lowered = line.lower()
        if any(needle.lower() in lowered for needle in needles):
            return line
    return None


def _replace_assignment_rhs(line: str, replacement: str) -> str:
    if "=" not in line:
        return line
    left, _right = line.split("=", 1)
    suffix = "," if line.rstrip().endswith(",") else ""
    return f"{left.rstrip()} = {replacement}{suffix}"


def _assignment_rhs(line: str) -> str:
    if "=" not in line:
        return "messages"
    rhs = line.split("=", 1)[1].strip().rstrip(",")
    return rhs or "messages"


def _token_budget(model_limit: int) -> int:
    if model_limit <= 0:
        return 3000
    return max(512, int(model_limit * 0.75))


def _evidence_summary_lines(evidence: Mapping[str, Any]) -> list[str]:
    keys = (
        "detected_by",
        "detection_signals",
        "estimated_tokens",
        "model_limit",
        "overflow_by",
        "repeat_count",
        "repeat_window_seconds",
        "prompt_fingerprint",
        "error_snippet",
    )
    lines: list[str] = []
    for key in keys:
        value = evidence.get(key)
        if value is None or value == "":
            continue
        lines.append(f"- `{key}`: `{value}`")
    return lines


def _normalize_diagnosis_type(value: str) -> str:
    normalized = _as_text(value, fallback="UNKNOWN").upper().replace("-", "_").replace(" ", "_")
    return normalized or "UNKNOWN"


def _slug(value: str, *, fallback: str) -> str:
    normalized = _as_text(value).lower().replace(" ", "-")
    normalized = _BRANCH_SANITIZE_RE.sub("-", normalized)
    normalized = re.sub(r"-+", "-", normalized).strip("-./")
    return normalized or fallback


def _clean_snippet(value: str | None) -> str:
    if not isinstance(value, str):
        return ""
    masked = mask_text(value.strip())
    return masked if masked is not None else ""


def _as_text(value: Any, *, fallback: str = "") -> str:
    if value is None:
        return fallback
    if isinstance(value, str):
        return mask_text(value.strip()) or fallback
    try:
        text = mask_text(str(value).strip())
    except Exception:
        return fallback
    return text or fallback


def _as_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value.strip()))
        except ValueError:
            return 0
    return 0


def _as_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list | tuple | set):
        result: list[str] = []
        for item in value:
            text = _as_text(item)
            if text and text not in result:
                result.append(text)
        return result
    text = _as_text(value)
    return [text] if text else []


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _as_float(value: Any) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return 0.0
    return 0.0


def _rate_limit_diff_from_snippet(snippet: str, *, retry_after: int) -> str:
    line = _first_relevant_line(snippet, ("request", "post", "get", "client", "call"))
    if line:
        return _before_after_diff(
            before=line,
            after=f"<existing_retry_wrapper>(\n    lambda: {line},\n    max_retries=3,\n    base_delay=1.0,\n)",
        )
    return _before_after_diff(
        before="# Original request code",
        after=(
            "# Add retry logic around the rate-limited request\n"
            "response = <existing_retry_wrapper>(\n"
            "    make_request,\n"
            "    max_retries=3,\n"
            "    base_delay=1.0,\n"
            ")"
        ),
    )


def _auth_failure_diff_from_snippet(snippet: str, *, status_code: int) -> str:
    line = _first_relevant_line(snippet, ("api_key", "token", "auth", "authorization", "credential"))
    if line and "=" in line:
        return _before_after_diff(
            before=line,
            after="api_key = <existing_credential_manager>.get_valid_key()  # Rotatable, validated",
        )
    return _before_after_diff(
        before="# Original authentication code",
        after=(
            "# Add credential validation and rotation\n"
            "api_key = <existing_credential_manager>.get_valid_key()\n"
            "if not api_key:\n"
            "    raise AuthenticationError(\"No valid credentials available\")"
        ),
    )


def _cost_spike_diff_from_snippet(snippet: str) -> str:
    line = _first_relevant_line(snippet, ("model", "gpt", "claude", "completion", "request"))
    if line and "=" in line:
        return _before_after_diff(
            before=line,
            after="# Add cost tracking and model selection based on cost\nresponse = <existing_cost_aware_client>.request_with_budget(",
        )
    return _before_after_diff(
        before="# Original model request",
        after=(
            "# Add cost tracking and budget controls\n"
            "if <existing_cost_tracker>.estimate_cost(request) > budget_limit:\n"
            "    request = <existing_cost_optimizer>.downgrade_if_possible(request)\n"
            "response = client.request(request)"
        ),
    )
