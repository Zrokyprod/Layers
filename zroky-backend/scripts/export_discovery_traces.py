#!/usr/bin/env python3
"""Export calls rows into Discovery harness JSONL.

This is a read-only collection helper for the real-trace precision gate. It
does not run migrations, does not create product data, and defaults to a
shape-only privacy mode so harness inputs can be shared/reviewed without raw
prompts or raw model outputs.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.db.models import Call  # noqa: E402
from app.db.url import normalize_sqlalchemy_database_url  # noqa: E402
from app.services.privacy import mask_payload, mask_value  # noqa: E402


OUTPUT_KEYS = ("output", "normalized_output", "output_content", "response")
TOOL_KEYS = ("tool_calls", "tool_calls_made", "tool_lifecycle_summary")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        help="SQLAlchemy DB URL. Defaults to Settings.DATABASE_URL.",
    )
    parser.add_argument("--project-id", help="Project/tenant id to export.")
    parser.add_argument("--agent-name", help="Optional agent_name filter.")
    parser.add_argument("--since", help="Inclusive created_at lower bound, ISO-8601.")
    parser.add_argument("--until", help="Exclusive created_at upper bound, ISO-8601.")
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument(
        "--include-non-production",
        action="store_true",
        help="Include calls where is_production=false.",
    )
    parser.add_argument(
        "--privacy-mode",
        choices=("shape-only", "masked"),
        default="shape-only",
        help="shape-only removes raw output text; masked redacts sensitive strings.",
    )
    parser.add_argument("--out", type=Path, required=True, help="Output JSONL path.")
    parser.add_argument(
        "--summary-out",
        type=Path,
        help="Summary JSON path. Defaults beside --out.",
    )
    parser.add_argument(
        "--min-rows",
        type=int,
        default=0,
        help="Exit 1 if fewer rows are exported.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    database_url = args.database_url or get_settings().DATABASE_URL
    engine = _create_engine(database_url)
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        future=True,
    )

    with session_factory() as session:
        if args.project_id:
            _set_tenant_context(session, args.project_id)
        calls = _load_calls(
            session,
            project_id=args.project_id,
            agent_name=args.agent_name,
            since=_parse_time(args.since),
            until=_parse_time(args.until),
            limit=max(1, int(args.limit)),
            production_only=not args.include_non_production,
        )

    records = [_call_to_record(call, privacy_mode=args.privacy_mode) for call in calls]
    _write_jsonl(args.out, records)
    summary = _build_summary(records, args=args)
    summary_path = args.summary_out or args.out.with_suffix(".summary.json")
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Exported traces: {len(records)}")
    print(f"Wrote JSONL: {args.out}")
    print(f"Wrote summary: {summary_path}")
    if len(records) < max(0, int(args.min_rows)):
        print(
            f"Gate collection failed: exported {len(records)} < min_rows {args.min_rows}",
            file=sys.stderr,
        )
        return 1
    return 0


def _create_engine(database_url: str):
    normalized = normalize_sqlalchemy_database_url(database_url)
    kwargs: dict[str, Any] = {"future": True, "pool_pre_ping": True}
    if normalized.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(normalized, **kwargs)


def _set_tenant_context(session: Session, project_id: str) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    session.execute(
        text("SELECT set_config('app.current_tenant_id', :project_id, true)"),
        {"project_id": project_id},
    )


def _load_calls(
    session: Session,
    *,
    project_id: str | None,
    agent_name: str | None,
    since: datetime | None,
    until: datetime | None,
    limit: int,
    production_only: bool,
) -> list[Call]:
    predicates = []
    if project_id:
        predicates.append(Call.project_id == project_id)
    if agent_name:
        predicates.append(Call.agent_name == agent_name)
    if since:
        predicates.append(Call.created_at >= since)
    if until:
        predicates.append(Call.created_at < until)
    if production_only:
        predicates.append(Call.is_production.is_(True))

    query = select(Call)
    if predicates:
        query = query.where(*predicates)
    query = query.order_by(Call.created_at.asc(), Call.id.asc()).limit(limit)
    return list(session.execute(query).scalars().all())


def _call_to_record(call: Call, *, privacy_mode: str) -> dict[str, Any]:
    payload = _safe_json_object(call.payload_json)
    if privacy_mode == "masked":
        exported_payload = mask_payload(payload)
    else:
        exported_payload = _shape_only_payload(payload)

    return {
        "call_id": call.id,
        "id": call.id,
        "project_id": call.project_id,
        "event_id": call.event_id,
        "created_at": call.created_at.isoformat() if call.created_at else None,
        "agent_name": call.agent_name,
        "provider": call.provider,
        "model": call.model,
        "status": call.status,
        "error_code": call.error_code,
        "latency_ms": call.latency_ms,
        "cost_total": float(call.cost_total or 0.0),
        "output_fingerprint": call.output_fingerprint,
        "tool_lifecycle_summary_json": call.tool_lifecycle_summary_json,
        "payload_json": json.dumps(exported_payload, separators=(",", ":"), default=str),
    }


def _shape_only_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    exported: dict[str, Any] = {}
    for key in ("workflow_name", "finish_reason", "stop_reason"):
        if payload.get(key) not in (None, ""):
            exported[key] = str(payload[key])

    for key in TOOL_KEYS:
        if key in payload:
            exported[key] = _tool_names_only(payload.get(key))

    if "outcome" in payload:
        exported["outcome"] = mask_value(payload.get("outcome"))

    for key in OUTPUT_KEYS:
        if key in payload:
            exported["output_content"] = _redacted_output_like(payload.get(key))
            break
    return exported


def _tool_names_only(value: Any) -> list[dict[str, str]]:
    parsed = _safe_json(value)
    if not isinstance(parsed, list):
        return []
    names: list[dict[str, str]] = []
    for item in parsed:
        name = _tool_name(item)
        if name:
            names.append({"name": name})
    return names


def _tool_name(item: Any) -> str | None:
    if isinstance(item, str):
        return item.strip() or None
    if not isinstance(item, Mapping):
        return None
    for key in ("name", "tool_name", "tool", "function_name", "called_tool"):
        value = item.get(key)
        if value not in (None, ""):
            return str(value).strip() or None
    function_value = item.get("function")
    if isinstance(function_value, Mapping):
        value = function_value.get("name")
        if value not in (None, ""):
            return str(value).strip() or None
    return None


def _redacted_output_like(value: Any) -> str:
    parsed = _safe_json(value)
    if isinstance(parsed, Mapping):
        return json.dumps(_redact_json_shape(parsed), separators=(",", ":"), sort_keys=True)
    if isinstance(parsed, list):
        return json.dumps(
            [_redact_json_shape(item) for item in parsed[:20]],
            separators=(",", ":"),
        )

    text_value = "" if value is None else str(value)
    word_count = len(text_value.split())
    if word_count <= 0:
        return ""
    return " ".join(["redacted"] * min(word_count, 500))


def _redact_json_shape(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _redact_json_shape(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_redact_json_shape(item) for item in value[:20]]
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return 0
    return "[redacted]"


def _build_summary(
    records: Sequence[Mapping[str, Any]],
    *,
    args: argparse.Namespace,
) -> dict[str, Any]:
    agents = Counter(str(record.get("agent_name") or "") for record in records)
    workflows: Counter[str] = Counter()
    created_values = [
        str(record["created_at"]) for record in records if record.get("created_at")
    ]
    for record in records:
        payload = _safe_json_object(record.get("payload_json"))
        workflow = payload.get("workflow_name")
        if workflow:
            workflows[str(workflow)] += 1

    return {
        "rows_exported": len(records),
        "project_id": args.project_id,
        "agent_name": args.agent_name,
        "since": args.since,
        "until": args.until,
        "production_only": not args.include_non_production,
        "privacy_mode": args.privacy_mode,
        "created_at_min": min(created_values) if created_values else None,
        "created_at_max": max(created_values) if created_values else None,
        "agents": dict(sorted(agents.items())),
        "workflows": dict(sorted(workflows.items())),
    }


def _write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, separators=(",", ":"), default=str))
            handle.write("\n")


def _safe_json(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def _safe_json_object(value: Any) -> dict[str, Any]:
    parsed = _safe_json(value)
    return parsed if isinstance(parsed, dict) else {}


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


if __name__ == "__main__":
    raise SystemExit(main())
