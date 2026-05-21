"""
Prompt-suite loader and DB sync.

The suite is stored as a JSON file (`data/prompts.json`) so non-engineers
can review diffs in code review. The loader is pure: it parses the JSON,
validates each entry through `PromptSpec.__post_init__`, and returns an
immutable tuple. `sync_prompts_to_db` is the side-effecting entry point;
it upserts active rows and flips `active=False` on rows missing from the
suite.

Determinism: the loader sorts by `id` so iteration order is stable
across deploys and platforms.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ProviderDriftPrompt
from app.services.provider_drift.models import PromptSpec

_DATA_PATH: Final[Path] = Path(__file__).parent / "data" / "prompts.json"

PROMPT_SUITE_VERSION: Final[int] = 2


def load_prompt_suite(path: Path | None = None) -> tuple[PromptSpec, ...]:
    """Parse the suite JSON and return validated PromptSpec tuples.

    `path` override is used by tests to inject fixtures.
    Raises ValueError on schema mismatch (any prompt that fails
    `PromptSpec.__post_init__` aborts the whole load — half-loaded suites
    are an anti-pattern).
    """
    src = path or _DATA_PATH
    raw = json.loads(src.read_text(encoding="utf-8"))

    if not isinstance(raw, dict) or "prompts" not in raw:
        raise ValueError(f"Prompt suite at {src} missing 'prompts' key")

    prompts_raw = raw["prompts"]
    if not isinstance(prompts_raw, list):
        raise ValueError(f"Prompt suite 'prompts' must be a list")

    suite_version = int(raw.get("version", 1))

    seen_ids: set[str] = set()
    specs: list[PromptSpec] = []
    for entry in prompts_raw:
        if not isinstance(entry, dict):
            raise ValueError(f"Prompt entry must be an object, got {type(entry)}")
        pid = entry["id"]
        if pid in seen_ids:
            raise ValueError(f"Duplicate prompt id: {pid}")
        seen_ids.add(pid)
        spec = PromptSpec(
            id=pid,
            category=entry["category"],
            prompt_text=entry["prompt_text"],
            expected_signal=dict(entry.get("expected_signal") or {}),
            system_prompt=entry.get("system_prompt"),
            max_tokens=int(entry.get("max_tokens", 512)),
            version=int(entry.get("version", suite_version)),
            active=bool(entry.get("active", True)),
        )
        specs.append(spec)

    return tuple(sorted(specs, key=lambda s: s.id))


def sync_prompts_to_db(
    db: Session, *, suite: tuple[PromptSpec, ...] | None = None
) -> dict[str, int]:
    """Idempotently upsert the suite into `provider_drift_prompts`.

    Behavior:
        - Insert rows that don't exist.
        - Update prompt_text / system_prompt / max_tokens / expected_signal /
          version / active for rows that do.
        - Mark `active=False` on DB rows whose id is not in the suite (so
          we never silently keep a stale prompt running).

    Returns:
        {"inserted": int, "updated": int, "deactivated": int}
    """
    suite_specs = suite if suite is not None else load_prompt_suite()
    suite_by_id = {s.id: s for s in suite_specs}

    existing_rows = db.execute(select(ProviderDriftPrompt)).scalars().all()
    existing_by_id = {r.id: r for r in existing_rows}

    inserted = updated = deactivated = 0

    # Insert / update
    for spec in suite_specs:
        signal_json = json.dumps(
            spec.expected_signal, sort_keys=True, separators=(",", ":")
        )
        row = existing_by_id.get(spec.id)
        if row is None:
            db.add(
                ProviderDriftPrompt(
                    id=spec.id,
                    category=spec.category,
                    prompt_text=spec.prompt_text,
                    system_prompt=spec.system_prompt,
                    max_tokens=spec.max_tokens,
                    expected_signal=signal_json,
                    version=spec.version,
                    active=spec.active,
                )
            )
            inserted += 1
        else:
            changed = (
                row.category != spec.category
                or row.prompt_text != spec.prompt_text
                or (row.system_prompt or None) != (spec.system_prompt or None)
                or row.max_tokens != spec.max_tokens
                or (row.expected_signal or "{}") != signal_json
                or row.version != spec.version
                or row.active != spec.active
            )
            if changed:
                row.category = spec.category
                row.prompt_text = spec.prompt_text
                row.system_prompt = spec.system_prompt
                row.max_tokens = spec.max_tokens
                row.expected_signal = signal_json
                row.version = spec.version
                row.active = spec.active
                updated += 1

    # Deactivate orphans
    for row in existing_rows:
        if row.id not in suite_by_id and row.active:
            row.active = False
            deactivated += 1

    db.flush()
    return {"inserted": inserted, "updated": updated, "deactivated": deactivated}


def filter_active_by_category(
    suite: tuple[PromptSpec, ...], category: str
) -> tuple[PromptSpec, ...]:
    """Return active prompts in a single category, sorted by id."""
    return tuple(s for s in suite if s.active and s.category == category)
