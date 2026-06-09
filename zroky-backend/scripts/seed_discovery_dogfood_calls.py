#!/usr/bin/env python3
"""Seed a local calls table for Discovery dogfood testing.

This creates a SQLite/Postgres `calls` dataset using the same mixed synthetic
trace shapes as the offline harness generator, but persisted through the real
ORM model. It is for mechanics only: exporter/runtime/harness plumbing can be
tested end-to-end, but this does not satisfy the real-trace precision gate.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from generate_discovery_mixed_dataset import (  # noqa: E402
    DEFAULT_COUNTS,
    PROJECT_ID as SYNTHETIC_PROJECT_ID,
    DatasetCounts,
    build_dataset,
)

from app.db.base import Base  # noqa: E402
from app.db.models import (  # noqa: E402
    Anomaly,
    BehavioralBaseline,
    Call,
    DiscoveryScanState,
    Project,
)
from app.db.url import normalize_sqlalchemy_database_url  # noqa: E402


DEFAULT_DATABASE_URL = "sqlite:///./.data/discovery_dogfood.db"
DEFAULT_PROJECT_ID = "dogfood_discovery_project"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=DEFAULT_DATABASE_URL)
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID)
    parser.add_argument("--project-name", default="Discovery Dogfood")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--normal-primary", type=int, default=DEFAULT_COUNTS.normal_primary)
    parser.add_argument("--normal-low-volume", type=int, default=DEFAULT_COUNTS.normal_low_volume)
    parser.add_argument(
        "--missing-tool-failures",
        type=int,
        default=DEFAULT_COUNTS.missing_tool_failures,
    )
    parser.add_argument(
        "--schema-break-failures",
        type=int,
        default=DEFAULT_COUNTS.schema_break_failures,
    )
    parser.add_argument(
        "--outcome-mismatch-failures",
        type=int,
        default=DEFAULT_COUNTS.outcome_mismatch_failures,
    )
    parser.add_argument(
        "--latency-cost-failures",
        type=int,
        default=DEFAULT_COUNTS.latency_cost_failures,
    )
    parser.add_argument("--no-create-schema", action="store_true")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing calls/project rows for --project-id before seeding.",
    )
    parser.add_argument("--summary-out", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    counts = DatasetCounts(
        normal_primary=max(0, args.normal_primary),
        normal_low_volume=max(0, args.normal_low_volume),
        missing_tool_failures=max(0, args.missing_tool_failures),
        schema_break_failures=max(0, args.schema_break_failures),
        outcome_mismatch_failures=max(0, args.outcome_mismatch_failures),
        latency_cost_failures=max(0, args.latency_cost_failures),
    )
    normal, injected = build_dataset(counts, seed=args.seed)
    rows = [_rewrite_project_id(row, args.project_id) for row in [*normal, *injected]]

    engine = _create_engine(args.database_url)
    if not args.no_create_schema:
        Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        future=True,
    )
    try:
        with session_factory() as session:
            if args.reset:
                session.execute(delete(Anomaly).where(Anomaly.project_id == args.project_id))
                session.execute(
                    delete(BehavioralBaseline).where(
                        BehavioralBaseline.project_id == args.project_id
                    )
                )
                session.execute(
                    delete(DiscoveryScanState).where(
                        DiscoveryScanState.project_id == args.project_id
                    )
                )
                session.execute(delete(Call).where(Call.project_id == args.project_id))
                session.execute(delete(Project).where(Project.id == args.project_id))
                session.flush()

            project = session.execute(
                select(Project).where(Project.id == args.project_id)
            ).scalar_one_or_none()
            if project is None:
                session.add(
                    Project(
                        id=args.project_id,
                        name=args.project_name,
                        is_active=True,
                    )
                )

            for row in rows:
                session.merge(_call_from_trace(row))
            session.commit()
    finally:
        engine.dispose()

    summary = _summary(rows, database_url=args.database_url, project_id=args.project_id)
    if args.summary_out:
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    print(f"Seeded calls:          {summary['rows_seeded']}")
    print(f"Project:               {args.project_id}")
    print(f"Database:              {args.database_url}")
    print(f"Injected failures:     {summary['injected_failures']}")
    if args.summary_out:
        print(f"Wrote summary:         {args.summary_out}")
    print("Reminder: dogfood data is mechanics-only, not real precision proof.")
    return 0


def _create_engine(database_url: str):
    normalized = normalize_sqlalchemy_database_url(database_url)
    kwargs: dict[str, Any] = {"future": True, "pool_pre_ping": True}
    if normalized.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(normalized, **kwargs)


def _rewrite_project_id(row: Mapping[str, Any], project_id: str) -> dict[str, Any]:
    rewritten = dict(row)
    rewritten["project_id"] = project_id
    return rewritten


def _call_from_trace(row: Mapping[str, Any]) -> Call:
    call_id = str(row["call_id"])
    payload = {
        "workflow_name": row.get("workflow_name"),
        "tool_calls": row.get("tool_calls") or [],
        "output_content": row.get("output_content"),
        "finish_reason": row.get("finish_reason"),
        "outcome": row.get("outcome"),
        "injected_failure_type": row.get("injected_failure_type"),
        "metadata": row.get("metadata"),
    }
    payload = {key: value for key, value in payload.items() if value is not None}
    metadata = {
        **(row.get("metadata") if isinstance(row.get("metadata"), dict) else {}),
        "source": "discovery_dogfood_seed",
    }
    if row.get("injected_failure_type"):
        metadata["injected_failure_type"] = row.get("injected_failure_type")

    return Call(
        id=call_id,
        project_id=str(row.get("project_id") or SYNTHETIC_PROJECT_ID),
        event_id=call_id,
        created_at=_parse_time(str(row["created_at"])),
        agent_name=_optional_str(row.get("agent_name")),
        provider="openai",
        model="gpt-discovery-dogfood",
        status=str(row.get("status") or "completed"),
        latency_ms=float(row["latency_ms"]) if row.get("latency_ms") is not None else None,
        cost_total=float(row.get("cost_usd") or 0.0),
        output_fingerprint=None,
        is_production=True,
        tool_lifecycle_summary_json=json.dumps(
            row.get("tool_calls") or [],
            separators=(",", ":"),
        ),
        payload_json=json.dumps(payload, separators=(",", ":"), sort_keys=True),
        metadata_json=json.dumps(metadata, separators=(",", ":"), sort_keys=True),
    )


def _summary(
    rows: Sequence[Mapping[str, Any]],
    *,
    database_url: str,
    project_id: str,
) -> dict[str, Any]:
    injected = [row for row in rows if row.get("injected_failure_type")]
    return {
        "database_url": database_url,
        "project_id": project_id,
        "rows_seeded": len(rows),
        "normal_rows": len(rows) - len(injected),
        "injected_failures": len(injected),
        "dogfood_only": True,
    }


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


if __name__ == "__main__":
    raise SystemExit(main())
