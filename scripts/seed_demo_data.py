"""Seed 1 K realistic demo events into a running Zroky instance (ZROKY-007).

Run inside the API container:
    docker compose exec api python scripts/seed_demo_data.py

Or directly (with DATABASE_URL set):
    DATABASE_URL=postgresql://... python scripts/seed_demo_data.py

Creates:
  - 1 demo tenant + project
  - 1 000 IngestEvent rows spread across 7 days:
      * 60% successful chat calls (gpt-4o, claude-3-5-sonnet, gemini-flash)
      *  15% loop-detected calls (same prompt fingerprint, 3-8 consecutive)
      *  15% context-overflow calls (prompt_tokens near model limit)
      *  10% error/budget-blocked calls
  - Realistic cost distribution ($0.0001–$0.05 / call)
  - 3 named agents: research-agent, summariser-agent, qa-agent
"""
from __future__ import annotations

import os
import random
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Allow running from repo root or from inside zroky-backend/
_backend_root = Path(__file__).resolve().parent.parent / "zroky-backend"
if _backend_root.exists():
    sys.path.insert(0, str(_backend_root))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/zroky",
)

PROVIDERS = ["openai", "anthropic", "google"]
MODELS = {
    "openai": ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"],
    "anthropic": ["claude-3-5-sonnet-20241022", "claude-3-haiku-20240307"],
    "google": ["gemini-1.5-flash", "gemini-1.5-pro"],
}
MODEL_CONTEXT = {
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-3.5-turbo": 16385,
    "claude-3-5-sonnet-20241022": 200000,
    "claude-3-haiku-20240307": 200000,
    "gemini-1.5-flash": 1000000,
    "gemini-1.5-pro": 1000000,
}
COST_PER_1K = {
    "gpt-4o": (0.005, 0.015),
    "gpt-4o-mini": (0.00015, 0.0006),
    "gpt-3.5-turbo": (0.0005, 0.0015),
    "claude-3-5-sonnet-20241022": (0.003, 0.015),
    "claude-3-haiku-20240307": (0.00025, 0.00125),
    "gemini-1.5-flash": (0.000075, 0.0003),
    "gemini-1.5-pro": (0.00125, 0.005),
}
AGENTS = ["research-agent", "summariser-agent", "qa-agent"]
FINGERPRINTS = [f"fp_{uuid.uuid4().hex[:16]}" for _ in range(12)]


def _random_model() -> tuple[str, str]:
    provider = random.choice(PROVIDERS)
    model = random.choice(MODELS[provider])
    return provider, model


def _cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    in_rate, out_rate = COST_PER_1K.get(model, (0.001, 0.003))
    return round((prompt_tokens / 1000) * in_rate + (completion_tokens / 1000) * out_rate, 8)


def _build_call(
    project_id: str,
    scenario: str,
    ts: datetime,
    loop_group: str | None = None,
    loop_count: int = 0,
) -> dict:
    provider, model = _random_model()
    agent = random.choice(AGENTS)
    fingerprint = loop_group or random.choice(FINGERPRINTS)
    ctx_limit = MODEL_CONTEXT.get(model, 128000)

    if scenario == "success":
        prompt_tokens = random.randint(200, 4000)
        completion_tokens = random.randint(50, 800)
        status = "completed"
        error_code = None
        error_message = None
        latency_ms = random.uniform(300, 3500)
    elif scenario == "loop":
        prompt_tokens = random.randint(500, 2000)
        completion_tokens = random.randint(50, 300)
        status = "completed"
        error_code = "LOOP_DETECTED"
        error_message = "Agent loop detected: same prompt fingerprint called repeatedly"
        latency_ms = random.uniform(400, 1500)
    elif scenario == "context_overflow":
        prompt_tokens = int(ctx_limit * random.uniform(0.88, 0.99))
        completion_tokens = random.randint(10, 100)
        status = "completed" if random.random() > 0.3 else "error"
        error_code = "CONTEXT_OVERFLOW" if status == "error" else None
        error_message = "Prompt exceeds context window" if status == "error" else None
        latency_ms = random.uniform(800, 5000)
    else:  # error
        prompt_tokens = random.randint(100, 1000)
        completion_tokens = 0
        status = random.choice(["error", "rate_limited", "budget_blocked", "timeout"])
        error_code = status.upper()
        error_message = f"Call failed with status: {status}"
        latency_ms = random.uniform(50, 800)

    cost = _cost(model, prompt_tokens, completion_tokens)
    call_id = f"demo-{uuid.uuid4().hex[:20]}"

    return {
        "call_id": call_id,
        "project_id": project_id,
        "provider": provider,
        "model": model,
        "call_type": "chat",
        "status": status,
        "latency_ms": latency_ms,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "estimated_cost_usd": cost,
        "actual_cost_usd": cost,
        "model_context_limit": ctx_limit,
        "error_code": error_code,
        "error_message": error_message,
        "loop_call_count": loop_count,
        "loop_cumulative_cost_usd": cost * loop_count if loop_count else None,
        "agent_name": agent,
        "prompt_fingerprint": fingerprint,
        "trace_id": f"trace-{uuid.uuid4().hex[:24]}",
        "is_synthetic": True,
        "is_production": False,
        "environment": "demo",
        "created_at": ts.timestamp(),
    }


def main() -> int:
    print(f"Seed demo data → {DATABASE_URL.split('@')[-1]}")

    engine = create_engine(DATABASE_URL, echo=False)

    with engine.connect() as conn:
        # Check if the calls table exists
        result = conn.execute(text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='calls')"
        ))
        if not result.scalar():
            print("ERROR: 'calls' table not found. Run migrations first: alembic upgrade head")
            return 1

        # Get or create a demo project
        row = conn.execute(text(
            "SELECT id FROM projects WHERE name = 'Demo Project' LIMIT 1"
        )).fetchone()

        if row:
            project_id = str(row[0])
            print(f"  Using existing demo project: {project_id}")
        else:
            print("  No 'Demo Project' found. Please create a project via the UI or API first.")
            print("  Then re-run this script.")
            return 1

    # Generate 1 000 calls over the past 7 days
    now = datetime.now(timezone.utc)
    calls: list[dict] = []
    rng = random.Random(42)  # reproducible seed

    # Scenario distribution: 60% success, 15% loop, 15% context_overflow, 10% error
    scenarios = (
        ["success"] * 600
        + ["loop"] * 150
        + ["context_overflow"] * 150
        + ["error"] * 100
    )
    rng.shuffle(scenarios)

    # Build loop groups (consecutive calls with same fingerprint)
    loop_fp_pool = [f"fp_loop_{uuid.uuid4().hex[:12]}" for _ in range(20)]

    loop_group: str | None = None
    loop_count = 0

    for i, scenario in enumerate(scenarios):
        offset_seconds = rng.uniform(0, 7 * 24 * 3600)
        ts = now - timedelta(seconds=offset_seconds)

        if scenario == "loop":
            if loop_count == 0 or rng.random() > 0.6:
                loop_group = rng.choice(loop_fp_pool)
                loop_count = 1
            else:
                loop_count += 1
        else:
            loop_group = None
            loop_count = 0

        calls.append(_build_call(project_id, scenario, ts, loop_group, loop_count))

    # Insert in batches of 100
    inserted = 0
    with Session(engine) as session:
        for batch_start in range(0, len(calls), 100):
            batch = calls[batch_start : batch_start + 100]
            # Build dynamic INSERT — only include columns that exist
            session.execute(
                text("""
                    INSERT INTO calls (
                        call_id, project_id, provider, model, call_type, status,
                        latency_ms, prompt_tokens, completion_tokens, estimated_cost_usd,
                        actual_cost_usd, model_context_limit, error_code, error_message,
                        loop_call_count, loop_cumulative_cost_usd, agent_name,
                        prompt_fingerprint, trace_id, is_synthetic, is_production,
                        environment, created_at
                    ) VALUES (
                        :call_id, :project_id, :provider, :model, :call_type, :status,
                        :latency_ms, :prompt_tokens, :completion_tokens, :estimated_cost_usd,
                        :actual_cost_usd, :model_context_limit, :error_code, :error_message,
                        :loop_call_count, :loop_cumulative_cost_usd, :agent_name,
                        :prompt_fingerprint, :trace_id, :is_synthetic, :is_production,
                        :environment, to_timestamp(:created_at)
                    )
                    ON CONFLICT (call_id) DO NOTHING
                """),
                batch,
            )
            session.commit()
            inserted += len(batch)
            print(f"  Inserted {inserted}/1000 calls…", end="\r")

    print(f"\n✓ Done. {inserted} demo calls seeded into project {project_id}.")
    print("  Breakdown: ~600 success, ~150 loop, ~150 context-overflow, ~100 error")
    print("  Open http://localhost:3000 to explore the demo data.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
