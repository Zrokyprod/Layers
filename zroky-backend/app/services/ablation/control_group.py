"""Control group selector — find similar successful calls via embedding NN.

Uses the existing EmbeddingService (text-embedding-3-small, 1536 dims)
to embed the failing call's normalized_output and find the closest
successful calls by cosine similarity.

"Successful" means:
  - call.status in SUCCESS_STATUSES
  - No diagnosis_job with a severity ≥ WARNING attached
  - Same project_id and agent_name (optional — falls back to same project)
  - Within LOOKBACK_DAYS

The control group provides the "what success looks like" baseline for
the axis confidence scorer.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Call, DiagnosisJob
from app.services.embedding_service import get_embedding_service
from app.services.regression_ci.diff_metric import cosine_similarity

logger = logging.getLogger(__name__)

LOOKBACK_DAYS = 14
TARGET_SIZE = 12
MIN_SIMILARITY = 0.72
SUCCESS_STATUSES = frozenset({"completed", "success", "ok"})


@dataclass
class ControlTrace:
    call_id: str
    model: str
    agent_name: str | None
    prompt_fingerprint: str | None
    latency_ms: float | None
    output_tokens: int
    error_code: str | None
    tool_count: int
    fallback_len: int
    similarity: float
    payload: dict[str, Any]


def select_control_group(
    db: Session,
    *,
    project_id: str,
    failing_call: Call,
    target_size: int = TARGET_SIZE,
) -> list[ControlTrace]:
    """Return up to ``target_size`` similar successful calls.

    Falls back gracefully: if fewer than 3 similar calls are found
    with agent_name filter, the agent filter is dropped and the search
    widens to all agents in the project.
    """
    since = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    agent = failing_call.agent_name

    # Phase 1: try same agent first (tighter semantic match)
    candidates = _fetch_candidates(db, project_id=project_id, since=since, agent=agent)

    # Phase 2: widen if not enough
    if len(candidates) < 3 and agent:
        logger.debug("control_group: widening search (agent=%s, found=%d)", agent, len(candidates))
        candidates = _fetch_candidates(db, project_id=project_id, since=since, agent=None)

    if not candidates:
        logger.debug("control_group: no candidate calls found for project=%s", project_id)
        return []

    # Embed the failing call's output as the query vector
    query_text = _output_text(failing_call)
    if not query_text:
        # No output to embed — use agent+model as fallback (weaker match)
        logger.debug("control_group: no output text on failing call, using structural match")
        return _structural_fallback(candidates, failing_call, target_size)

    svc = get_embedding_service()
    query_vec = svc.generate_embedding(query_text)
    if query_vec is None:
        logger.warning("control_group: embedding service returned None")
        return _structural_fallback(candidates, failing_call, target_size)

    # Score candidates by cosine similarity
    scored: list[tuple[float, ControlTrace]] = []
    for c in candidates:
        ctext = _output_text(c)
        if not ctext:
            continue
        cvec = svc.generate_embedding(ctext)
        if cvec is None:
            continue
        sim = cosine_similarity(query_vec, cvec)
        if sim >= MIN_SIMILARITY:
            scored.append((sim, _to_control(c, sim)))

    scored.sort(key=lambda x: -x[0])
    return [ct for _, ct in scored[:target_size]]


# ── Helpers ────────────────────────────────────────────────────────────────────


def _fetch_candidates(
    db: Session,
    *,
    project_id: str,
    since: datetime,
    agent: str | None,
) -> list[Call]:
    q = select(Call).where(
        Call.project_id == project_id,
        Call.status.in_(SUCCESS_STATUSES),
        Call.created_at >= since,
    )
    if agent:
        q = q.where(Call.agent_name == agent)
    q = q.order_by(Call.created_at.desc()).limit(200)
    return list(db.execute(q).scalars().all())


def _output_text(call: Call) -> str | None:
    import json
    try:
        p = json.loads(call.payload_json or "{}")
    except Exception:
        return None
    return p.get("normalized_output") or p.get("output_content") or None


def _to_control(call: Call, similarity: float) -> ControlTrace:
    import json
    try:
        p = json.loads(call.payload_json or "{}")
    except Exception:
        p = {}
    tool_calls = p.get("tool_calls_made") or []
    fallback = p.get("fallback_chain") or []
    fp = getattr(call, "prompt_fingerprint", None) or p.get("prompt_fingerprint")
    return ControlTrace(
        call_id=call.id,
        model=call.model or "unknown",
        agent_name=call.agent_name,
        prompt_fingerprint=fp,
        latency_ms=float(call.latency_ms or 0),
        output_tokens=int(call.output_tokens or 0),
        error_code=call.error_code,
        tool_count=len(tool_calls) if isinstance(tool_calls, list) else 0,
        fallback_len=len(fallback) if isinstance(fallback, list) else 0,
        similarity=similarity,
        payload=p,
    )


def _structural_fallback(
    candidates: list[Call],
    failing_call: Call,
    target_size: int,
) -> list[ControlTrace]:
    """When embedding is unavailable, score by structural similarity."""
    fp = getattr(failing_call, "prompt_fingerprint", None)
    scored = []
    for c in candidates:
        cfp = getattr(c, "prompt_fingerprint", None)
        score = 0.5  # base for same agent
        if fp and cfp and fp == cfp:
            score += 0.3
        if c.model == failing_call.model:
            score += 0.2
        scored.append((score, _to_control(c, score)))
    scored.sort(key=lambda x: -x[0])
    return [ct for _, ct in scored[:target_size]]
