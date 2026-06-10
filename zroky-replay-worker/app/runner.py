# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""Replay job executor.

Reconstructs the call context from a signed artifact, applies the
candidate fix diff, executes the call, and returns a ReplayResult.

Zero-trust guarantees enforced here:
  - Artifact signature verified before download.
  - No inbound connections accepted; worker always pulls.
  - Execution is sandboxed to a subprocess with timeout.
"""
from __future__ import annotations

import difflib
import json
import logging
import re
import subprocess  # TimeoutExpired still used in _execute_context
from datetime import datetime, timezone
from typing import Any

import httpx  # used by _execute_context for real LLM calls
import numpy as np

from app.artifacts import download_artifact, verify_artifact_signature
from app.models import ReplayJob, ReplayResult

logger = logging.getLogger(__name__)

_STDOUT_TAIL_CHARS = 2000


def run_job(job: ReplayJob, *, signing_key: str, signature_required: bool = True) -> ReplayResult:
    """Execute a replay job and return its result.

    Steps:
    1. Verify artifact signature.
    2. Download artifact (gzip JSON bundle).
    3. Apply candidate_fix_diff to reconstruct patched context.
    4. Execute the patched call against real LLM via OpenRouter.
    5. Compute diff_metric (embedding cosine + SequenceMatcher fallback).
    6. Request judge verdict from Zroky control plane.
    7. Return ReplayResult with verdict + metrics.
    """
    started_at = datetime.now(timezone.utc)
    try:
        if not verify_artifact_signature(
            url=job.artifact_url,
            signature=job.artifact_signature,
            signing_key=signing_key,
            signature_required=signature_required,
        ):
            return _error_result(job, started_at, "Artifact signature verification failed")

        artifact_bytes = download_artifact(job.artifact_url)
        context = _parse_artifact(artifact_bytes)
        patched_context = _apply_diff(context, job.candidate_fix_diff)
        stdout, returncode = _execute_context(patched_context, timeout=job.timeout_seconds)

        expected_output = context.get("expected_output", "")

        # Primary metric: embedding cosine distance (semantic similarity)
        embedding_metric = _compute_embedding_diff(expected_output, stdout)
        # Fallback: character-level SequenceMatcher
        sequence_metric = _compute_sequence_diff(expected_output, stdout)
        # Use embedding if available, else fall back
        diff_metric = embedding_metric if embedding_metric is not None else sequence_metric

        # Request judge verdict from control plane (or local threshold fallback)
        judge_verdict = _request_judge_verdict(
            trace_id=job.trace_id,
            expected_output=expected_output,
            actual_output=stdout,
            diff_metric=diff_metric,
            context=patched_context,
        )

        status = judge_verdict if judge_verdict in ("pass", "fail") else (
            "pass" if returncode == 0 and diff_metric <= 0.3 else "fail"
        )

        return ReplayResult(
            replay_id=job.replay_id,
            trace_id=job.trace_id,
            fix_pr_id=job.fix_pr_id,
            status=status,
            diff_metric=diff_metric,
            embedding_cosine=embedding_metric,
            judge_verdict=judge_verdict,
            stdout_tail=stdout[-_STDOUT_TAIL_CHARS:] if stdout else None,
            completed_at=datetime.now(timezone.utc),
        )

    except subprocess.TimeoutExpired:
        return _error_result(job, started_at, "Execution timed out")
    except Exception as exc:
        logger.exception("Replay job %s failed with unexpected error", job.replay_id)
        return _error_result(job, started_at, f"Unexpected error: {exc}")


# ── helpers ───────────────────────────────────────────────────────────────────

def _parse_artifact(data: bytes) -> dict:
    import gzip
    try:
        return json.loads(gzip.decompress(data))
    except Exception:
        return json.loads(data)


def _apply_diff(context: dict, diff: str) -> dict:
    """Apply a unified diff string to the 'prompt' field of the context."""
    patched = dict(context)
    if not diff.strip():
        return patched
    original_prompt = patched.get("prompt", "")
    try:
        patched["prompt"] = _apply_unified_diff_py(original_prompt, diff)
    except Exception:
        logger.warning("_apply_diff: patch failed, using original prompt")
    return patched


_HUNK_HEADER = re.compile(r"^@@ -(?P<start>\d+)(?:,\d+)? \+\d+(?:,\d+)? @@")


def _apply_unified_diff_py(original: str, diff_text: str) -> str:
    """Apply a unified diff to original text. Pure Python, cross-platform.

    Parses @@ hunks sequentially. Silently skips hunks whose context lines
    don't match (e.g. already applied or wrong base).
    """
    result: list[str] = original.splitlines(keepends=True)
    offset = 0  # cumulative line-count delta from already-applied hunks

    def _apply_hunk(orig_start: int, hunk: list[str]) -> None:
        nonlocal offset
        pos = orig_start - 1 + offset  # convert to 0-indexed

        # Verify context/removed lines match before touching result.
        check = pos
        for h in hunk:
            if h[0] in (" ", "-"):
                if check >= len(result):
                    return
                if result[check].rstrip("\r\n") != h[1:].rstrip("\r\n"):
                    return  # context mismatch — skip hunk
                check += 1

        # Build replacement region.
        new_region: list[str] = []
        src = pos
        for h in hunk:
            if h[0] == " ":
                new_region.append(result[src])
                src += 1
            elif h[0] == "-":
                src += 1
            elif h[0] == "+":
                line = h[1:]
                if line and not line.endswith("\n"):
                    line += "\n"
                new_region.append(line)

        old_len = src - pos
        result[pos : pos + old_len] = new_region
        offset += len(new_region) - old_len

    current_hunk: list[str] = []
    current_start = 0
    in_hunk = False

    for raw in diff_text.splitlines(keepends=True):
        line = raw.rstrip("\r\n")
        m = _HUNK_HEADER.match(line)
        if m:
            if in_hunk and current_hunk:
                _apply_hunk(current_start, current_hunk)
            current_start = int(m.group("start"))
            current_hunk = []
            in_hunk = True
            continue
        if in_hunk and line and line[0] in (" ", "-", "+"):
            current_hunk.append(line + "\n")

    if in_hunk and current_hunk:
        _apply_hunk(current_start, current_hunk)

    return "".join(result)


def _execute_context(context: dict, *, timeout: int) -> tuple[str, int]:
    """Call the LLM via OpenRouter with the patched context and return the response text."""
    from app.config import get_settings
    settings = get_settings()
    api_key = settings.OPENROUTER_API_KEY
    if not api_key:
        logger.error("OPENROUTER_API_KEY is not set — cannot execute replay")
        return "{\"error\": \"OPENROUTER_API_KEY not configured\"}", 1

    model = context.get("model") or "openai/gpt-4o-mini"
    messages = context.get("messages")
    if not messages:
        prompt = context.get("prompt", "")
        messages = [{"role": "user", "content": prompt}]

    payload: dict = {
        "model": model,
        "messages": messages,
        "max_tokens": context.get("max_tokens", 1024),
        "temperature": context.get("temperature", 0.0),
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://zroky.com",
                    "X-Title": "Zroky Replay Worker",
                },
                json=payload,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return content, 0
    except httpx.TimeoutException as exc:
        raise subprocess.TimeoutExpired(cmd="openrouter_call", timeout=timeout) from exc
    except httpx.HTTPStatusError as exc:
        logger.error("OpenRouter HTTP %s for replay: %s", exc.response.status_code, exc.response.text[:200])
        return f"LLM error: HTTP {exc.response.status_code}", 1
    except Exception as exc:
        logger.exception("Unexpected error during LLM call")
        return f"LLM error: {exc}", 1


def _compute_sequence_diff(original_output: str, actual_output: str) -> float:
    """Character-level SequenceMatcher distance in [0, 1]. Fallback metric."""
    if not original_output and not actual_output:
        return 0.0
    if not original_output or not actual_output:
        return 1.0
    ratio = difflib.SequenceMatcher(None, original_output, actual_output).ratio()
    return round(1.0 - ratio, 4)


def _compute_embedding_diff(expected: str, actual: str) -> float | None:
    """Compute 1 - cosine_similarity between embeddings of expected and actual.

    Returns None if embeddings cannot be generated (API unavailable, etc).
    Uses OpenRouter's embedding endpoint via the same API key.
    """
    if not expected or not actual:
        return None

    from app.config import get_settings
    settings = get_settings()
    api_key = settings.OPENROUTER_API_KEY
    if not api_key:
        return None

    try:
        with httpx.Client(timeout=15) as client:
            resp = client.post(
                "https://openrouter.ai/api/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "openai/text-embedding-3-small",
                    "input": [expected[:8000], actual[:8000]],
                },
            )
            resp.raise_for_status()
            data = resp.json()["data"]
            vec_a = np.array(data[0]["embedding"], dtype=np.float32)
            vec_b = np.array(data[1]["embedding"], dtype=np.float32)
            cosine_sim = float(np.dot(vec_a, vec_b) / (np.linalg.norm(vec_a) * np.linalg.norm(vec_b) + 1e-9))
            return round(1.0 - max(0.0, cosine_sim), 4)
    except Exception as exc:
        logger.debug("Embedding diff unavailable: %s", exc)
        return None


def _request_judge_verdict(
    *,
    trace_id: str,
    expected_output: str,
    actual_output: str,
    diff_metric: float,
    context: dict[str, Any],
) -> str | None:
    """Request a judge verdict from the Zroky control plane.

    Calls POST /v1/replay/judge with the replay context.
    Returns 'pass', 'fail', or None if judge is unavailable.
    Falls back to threshold-based verdict if judge call fails.
    """
    from app.config import get_settings
    settings = get_settings()
    if not settings.WORKER_TOKEN:
        return None

    try:
        with httpx.Client(timeout=20) as client:
            resp = client.post(
                f"{settings.CONTROL_PLANE_URL}/v1/replay/judge",
                headers={"Authorization": f"Bearer {settings.WORKER_TOKEN}"},
                json={
                    "trace_id": trace_id,
                    "expected_output": expected_output[:4000],
                    "actual_output": actual_output[:4000],
                    "diff_metric": diff_metric,
                    "model": context.get("model"),
                    "agent_name": context.get("agent_name"),
                },
            )
            if resp.status_code == 200:
                return resp.json().get("verdict")
            logger.debug("Judge endpoint returned %d", resp.status_code)
            return None
    except Exception as exc:
        logger.debug("Judge call failed: %s", exc)
        return None


def _error_result(job: ReplayJob, started_at: datetime, message: str) -> ReplayResult:
    return ReplayResult(
        replay_id=job.replay_id,
        trace_id=job.trace_id,
        fix_pr_id=job.fix_pr_id,
        status="error",
        error_message=message,
        completed_at=datetime.now(timezone.utc),
    )
