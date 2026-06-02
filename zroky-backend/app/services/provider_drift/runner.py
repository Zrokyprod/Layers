"""
Provider Drift Watch — daily probe runner (Layer 3).

This module orchestrates one (model, run_date) execution: for each active
prompt, it calls the provider via a pluggable `ProviderClient`, optionally
embeds the output, judges it, and persists a `provider_drift_probes` row.

Dependency injection at the boundaries:
  - `ProviderClient`:    pure interface; production wiring lives in
                          `app/services/provider_drift/clients/*.py`.
                          Tests inject a stub.
  - `Embedder`:          pure interface; defaults to
                          `app.services.embedding_service.get_embedding_service()`
                          when None.
  - `judge`:             pure-functional, defaults to
                          `provider_drift.judge.judge`.

Behaviour rules:
  1. Hard budget cap per run (`budget_usd`). When the running cost would
     exceed the cap the runner emits a `budget_exceeded` probe for every
     remaining prompt and marks the run `partial`.
  2. Retry on transient errors (`rate_limited`, `timeout`) with bounded
     exponential backoff (max 3 attempts). Other errors fail through.
  3. Determinism: probes are processed in `prompt.id` order. The set of
     prompts is the suite snapshot at run time (active=True).
  4. Idempotency at the run level: re-running the same (model, run_date)
     is a no-op once status is terminal. Probes are NOT re-run.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Callable, Iterable, Protocol, Sequence
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ProviderDriftModel,
    ProviderDriftProbe,
    ProviderDriftPrompt,
    ProviderDriftRun,
)
from app.services.provider_drift.judge import judge as default_judge
from app.services.provider_drift.models import (
    ModelSpec,
    ProbeOutcome,
    ProbeResult,
    PromptSpec,
)

logger = logging.getLogger(__name__)


# ── interfaces ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProviderCallResult:
    """Wire-level result from a provider client.

    `outcome` must be one of the `ProbeOutcome.*` constants. `cost_usd`
    is the provider-billed cost of this single call (best-effort; 0 is
    acceptable when the runner can't compute it).
    """

    outcome: str
    output_text: str | None = None
    latency_ms: int | None = None
    cost_usd: float = 0.0
    error_code: str | None = None


class ProviderClient(Protocol):
    """Pluggable provider adapter.

    Implementations MUST honour the prompt's `max_tokens`, set
    temperature=0 (or provider-equivalent for determinism), and translate
    transport errors into `ProbeOutcome` values without raising.
    """

    def call(self, *, model_spec: ModelSpec, prompt: PromptSpec) -> ProviderCallResult:
        ...


class Embedder(Protocol):
    """Pluggable text embedder."""

    def embed(self, text: str) -> tuple[float, ...] | None:
        ...

    @property
    def model_tag(self) -> str:
        ...


JudgeFn = Callable[[str | None, dict], tuple[bool, float]]


# ── budget tracker ──────────────────────────────────────────────────────────


class BudgetTracker:
    """Bounded per-run cost tracker.

    Thread-unsafe (we're single-threaded per-run). `would_exceed(cost)`
    returns True if charging `cost` would push us over the cap. The
    runner uses it pre-call so we never spend over the cap.
    """

    def __init__(self, budget_usd: float) -> None:
        if budget_usd < 0:
            raise ValueError("budget_usd must be non-negative")
        self._budget = float(budget_usd)
        self._spent = 0.0

    @property
    def spent(self) -> float:
        return self._spent

    @property
    def remaining(self) -> float:
        return max(0.0, self._budget - self._spent)

    def would_exceed(self, cost: float) -> bool:
        return (self._spent + max(0.0, cost)) > self._budget

    def charge(self, cost: float) -> None:
        if cost < 0:
            return
        self._spent += float(cost)


# ── retry helper ────────────────────────────────────────────────────────────


_RETRYABLE = frozenset({ProbeOutcome.RATE_LIMITED, ProbeOutcome.TIMEOUT})


def call_with_retry(
    client: ProviderClient,
    *,
    model_spec: ModelSpec,
    prompt: PromptSpec,
    max_attempts: int = 3,
    base_backoff_seconds: float = 0.5,
    sleep: Callable[[float], None] = time.sleep,
) -> ProviderCallResult:
    """Call a provider with bounded exponential backoff on transient errors."""
    if max_attempts < 1:
        max_attempts = 1
    last: ProviderCallResult | None = None
    for attempt in range(max_attempts):
        result = client.call(model_spec=model_spec, prompt=prompt)
        last = result
        if result.outcome not in _RETRYABLE:
            return result
        if attempt + 1 >= max_attempts:
            return result
        # Exponential backoff: base, 2*base, 4*base, ...
        sleep(base_backoff_seconds * (2**attempt))
    assert last is not None
    return last


# ── runner ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RunOutcome:
    """Summary the scheduler logs / surfaces."""

    run_id: str
    model_id: str
    run_date: date
    status: str
    prompts_total: int
    prompts_ok: int
    prompts_error: int
    cost_usd: float


def execute_run(
    *,
    db: Session,
    model_spec: ModelSpec,
    run_date: date,
    prompts: Sequence[PromptSpec],
    provider_client: ProviderClient,
    embedder: Embedder | None = None,
    judge_fn: JudgeFn = default_judge,
    budget_usd: float = 5.0,
    max_retry_attempts: int = 3,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> RunOutcome:
    """Run the deterministic suite for one (model, run_date).

    The function is idempotent at the run level: if a row already exists
    for (model_id, run_date) AND its status is terminal, the existing
    summary is returned without re-running. This matches Postgres
    UNIQUE-aware idempotency without needing ON CONFLICT.
    """
    if not prompts:
        raise ValueError("prompts must be non-empty")

    # Idempotency check.
    existing = db.execute(
        select(ProviderDriftRun).where(
            ProviderDriftRun.model_id == model_spec.id,
            ProviderDriftRun.run_date == run_date,
        )
    ).scalar_one_or_none()

    terminal = {"complete", "partial", "error"}
    if existing is not None and existing.status in terminal:
        return RunOutcome(
            run_id=existing.id,
            model_id=existing.model_id,
            run_date=existing.run_date,
            status=existing.status,
            prompts_total=existing.prompts_total,
            prompts_ok=existing.prompts_ok,
            prompts_error=existing.prompts_error,
            cost_usd=float(existing.cost_usd or 0.0),
        )

    # Create or claim the run row.
    run_row: ProviderDriftRun
    if existing is None:
        run_row = ProviderDriftRun(
            id=str(uuid4()),
            model_id=model_spec.id,
            run_date=run_date,
            status="running",
            prompts_total=len(prompts),
            prompts_ok=0,
            prompts_error=0,
            cost_usd=0.0,
            started_at=now(),
        )
        db.add(run_row)
        db.flush()
    else:
        run_row = existing
        run_row.status = "running"
        run_row.started_at = now()
        run_row.prompts_total = len(prompts)

    sorted_prompts = sorted(prompts, key=lambda p: p.id)

    budget = BudgetTracker(budget_usd)
    ok_count = 0
    err_count = 0

    for prompt in sorted_prompts:
        # Pre-flight budget gate. We use a conservative pessimistic
        # estimate: if remaining budget can't cover even a tiny call,
        # mark the rest as budget_exceeded.
        if budget.remaining <= 0:
            _persist_probe(
                db=db,
                run_row=run_row,
                model_spec=model_spec,
                prompt=prompt,
                run_date=run_date,
                result=ProbeResult(
                    prompt_id=prompt.id,
                    model_id=model_spec.id,
                    outcome=ProbeOutcome.BUDGET_EXCEEDED,
                ),
                expected_signal=prompt.expected_signal,
                judge_fn=judge_fn,
                embedder=embedder,
                now=now,
            )
            err_count += 1
            continue

        call_res = call_with_retry(
            provider_client,
            model_spec=model_spec,
            prompt=prompt,
            max_attempts=max_retry_attempts,
            sleep=sleep,
        )
        budget.charge(call_res.cost_usd)

        # Build embedding only on successful calls.
        embedding: tuple[float, ...] | None = None
        embedding_model: str | None = None
        if call_res.outcome == ProbeOutcome.OK and call_res.output_text and embedder is not None:
            try:
                vec = embedder.embed(call_res.output_text)
                if vec:
                    embedding = tuple(vec)
                    embedding_model = embedder.model_tag
            except Exception:  # noqa: BLE001
                logger.warning(
                    "provider_drift.runner.embedding_failed prompt=%s model=%s",
                    prompt.id, model_spec.id, exc_info=True,
                )

        # Judge only on OK outcome.
        judge_pass: bool | None = None
        judge_score: float | None = None
        if call_res.outcome == ProbeOutcome.OK:
            verdict = judge_fn(call_res.output_text, prompt.expected_signal)
            judge_pass = bool(verdict[0])
            judge_score = float(verdict[1])

        result = ProbeResult(
            prompt_id=prompt.id,
            model_id=model_spec.id,
            outcome=call_res.outcome,
            output_text=call_res.output_text,
            output_embedding=embedding,
            embedding_model=embedding_model,
            judge_pass=judge_pass,
            judge_score=judge_score,
            latency_ms=call_res.latency_ms,
            cost_usd=call_res.cost_usd,
            error_code=call_res.error_code,
        )

        _persist_probe(
            db=db,
            run_row=run_row,
            model_spec=model_spec,
            prompt=prompt,
            run_date=run_date,
            result=result,
            expected_signal=prompt.expected_signal,
            judge_fn=judge_fn,
            embedder=embedder,
            now=now,
        )

        if call_res.outcome == ProbeOutcome.OK:
            ok_count += 1
        else:
            err_count += 1

    # Finalise run row.
    final_status = _final_status(
        ok_count=ok_count,
        err_count=err_count,
        total=len(sorted_prompts),
        budget_exceeded=budget.remaining <= 0 and err_count > 0,
    )
    run_row.status = final_status
    run_row.prompts_ok = ok_count
    run_row.prompts_error = err_count
    run_row.cost_usd = budget.spent
    run_row.completed_at = now()
    db.flush()

    return RunOutcome(
        run_id=run_row.id,
        model_id=run_row.model_id,
        run_date=run_row.run_date,
        status=run_row.status,
        prompts_total=run_row.prompts_total,
        prompts_ok=run_row.prompts_ok,
        prompts_error=run_row.prompts_error,
        cost_usd=float(run_row.cost_usd or 0.0),
    )


def _final_status(
    *, ok_count: int, err_count: int, total: int, budget_exceeded: bool
) -> str:
    """Determine the run row's terminal status.

    Rules:
      - All OK → 'complete'
      - All errored → 'error'
      - Mix → 'partial' (still useful: detector applies coverage gate)
      - If budget_exceeded set, prefer 'partial' over 'complete' so the
        operator can see the truncation.
    """
    if ok_count == total:
        return "complete"
    if ok_count == 0:
        return "error"
    if budget_exceeded:
        return "partial"
    return "partial"


def _persist_probe(
    *,
    db: Session,
    run_row: ProviderDriftRun,
    model_spec: ModelSpec,
    prompt: PromptSpec,
    run_date: date,
    result: ProbeResult,
    expected_signal: dict,
    judge_fn: JudgeFn,
    embedder: Embedder | None,
    now: Callable[[], datetime],
) -> None:
    """Persist a probe row. Embedding stored as JSON-string on TEXT column."""
    embedding_json: str | None = None
    if result.output_embedding is not None:
        embedding_json = json.dumps(list(result.output_embedding))

    db.add(
        ProviderDriftProbe(
            id=str(uuid4()),
            run_id=run_row.id,
            prompt_id=prompt.id,
            model_id=model_spec.id,
            run_date=run_date,
            category=prompt.category,
            output_text=result.output_text,
            output_embedding=embedding_json,
            embedding_model=result.embedding_model,
            judge_pass=result.judge_pass,
            judge_score=result.judge_score,
            latency_ms=result.latency_ms,
            cost_usd=result.cost_usd,
            outcome=result.outcome,
            error_code=result.error_code,
            created_at=now(),
        )
    )
    db.flush()


# ── helpers for the scheduler ───────────────────────────────────────────────


def load_active_prompts(db: Session) -> tuple[PromptSpec, ...]:
    """Read active prompts from DB and return as PromptSpec tuple."""
    rows = (
        db.execute(
            select(ProviderDriftPrompt).where(ProviderDriftPrompt.active.is_(True))
        )
        .scalars()
        .all()
    )
    out: list[PromptSpec] = []
    for r in rows:
        signal = json.loads(r.expected_signal or "{}")
        out.append(
            PromptSpec(
                id=r.id,
                category=r.category,
                prompt_text=r.prompt_text,
                expected_signal=signal,
                system_prompt=r.system_prompt,
                max_tokens=r.max_tokens,
                version=r.version,
                active=r.active,
            )
        )
    return tuple(sorted(out, key=lambda s: s.id))


def load_active_models(db: Session) -> tuple[ModelSpec, ...]:
    """Read active models from DB."""
    rows = (
        db.execute(
            select(ProviderDriftModel).where(ProviderDriftModel.active.is_(True))
        )
        .scalars()
        .all()
    )
    out = [
        ModelSpec(
            id=r.id,
            provider=r.provider,
            model_id=r.model_id,
            display_name=r.display_name,
            family=r.family,
            active=r.active,
        )
        for r in rows
    ]
    return tuple(sorted(out, key=lambda s: s.id))
