"""
Model registry loader and DB sync.

Same pattern as `prompt_suite.py`: JSON file is the source of truth,
loader is pure, sync is idempotent.

Adding a new model: append to `data/models.json`, redeploy. The
scheduler picks it up on the next daily run. Removing a model: flip
`active=false` in the JSON; we never hard-delete so historical alerts
remain joinable.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ProviderDriftModel
from app.services.provider_drift.models import ModelSpec

_DATA_PATH: Final[Path] = Path(__file__).parent / "data" / "models.json"

MODEL_REGISTRY_VERSION: Final[int] = 1


def load_model_registry(path: Path | None = None) -> tuple[ModelSpec, ...]:
    """Parse the registry JSON and return validated ModelSpec tuples."""
    src = path or _DATA_PATH
    raw = json.loads(src.read_text(encoding="utf-8"))

    if not isinstance(raw, dict) or "models" not in raw:
        raise ValueError(f"Model registry at {src} missing 'models' key")
    items = raw["models"]
    if not isinstance(items, list):
        raise ValueError("'models' must be a list")

    seen: set[str] = set()
    specs: list[ModelSpec] = []
    for entry in items:
        if not isinstance(entry, dict):
            raise ValueError(f"Model entry must be an object, got {type(entry)}")
        mid = entry["id"]
        if mid in seen:
            raise ValueError(f"Duplicate model id: {mid}")
        seen.add(mid)
        spec = ModelSpec(
            id=mid,
            provider=entry["provider"],
            model_id=entry["model_id"],
            display_name=entry["display_name"],
            family=entry["family"],
            active=bool(entry.get("active", True)),
        )
        specs.append(spec)

    return tuple(sorted(specs, key=lambda s: s.id))


def sync_models_to_db(
    db: Session, *, registry: tuple[ModelSpec, ...] | None = None
) -> dict[str, int]:
    """Idempotently upsert the registry into `provider_drift_models`."""
    specs = registry if registry is not None else load_model_registry()
    spec_by_id = {s.id: s for s in specs}

    existing = db.execute(select(ProviderDriftModel)).scalars().all()
    existing_by_id = {r.id: r for r in existing}

    inserted = updated = deactivated = 0
    for spec in specs:
        row = existing_by_id.get(spec.id)
        if row is None:
            db.add(
                ProviderDriftModel(
                    id=spec.id,
                    provider=spec.provider,
                    model_id=spec.model_id,
                    display_name=spec.display_name,
                    family=spec.family,
                    active=spec.active,
                )
            )
            inserted += 1
        else:
            changed = (
                row.provider != spec.provider
                or row.model_id != spec.model_id
                or row.display_name != spec.display_name
                or row.family != spec.family
                or row.active != spec.active
            )
            if changed:
                row.provider = spec.provider
                row.model_id = spec.model_id
                row.display_name = spec.display_name
                row.family = spec.family
                row.active = spec.active
                updated += 1

    for row in existing:
        if row.id not in spec_by_id and row.active:
            row.active = False
            deactivated += 1

    db.flush()
    return {"inserted": inserted, "updated": updated, "deactivated": deactivated}
