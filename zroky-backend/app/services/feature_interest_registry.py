"""Feature-interest registry — smoke-test "coming soon" feature polls.

Each entry maps a stable `feature_key` (used in the
`feature_interest_votes` table + the dashboard's <ComingSoonPoll>) to
its display metadata + ship threshold.

Adding a new poll to the dashboard is a one-line change to this dict.
No migration, no new endpoints. The customer endpoint
`POST /v1/feature-interest` validates `feature_key` against this
registry so unknown keys cannot be voted on.

Plan ref: Module 9 smoke-test alternative (validate demand before
building Tier-1 autonomy executor).
"""
from __future__ import annotations

from typing import Final


COMING_SOON_FEATURES: Final[dict[str, dict[str, object]]] = {
    "pilot.tier1_autonomy": {
        "name": "Tier-1 Autonomy",
        "description": (
            "Auto-apply safe config fixes (model rollback, fallback "
            "swap, retry tune) without a PR. Fully reversible, "
            "kill-switch protected."
        ),
        # Ship the feature when this fraction of total votes are
        # "interested". The CLI/admin dashboard surfaces a
        # "ABOVE THRESHOLD — consider shipping" badge once crossed.
        "ships_after_threshold": 0.30,
    },
}


def is_known_feature(feature_key: str) -> bool:
    """True if `feature_key` is currently accepting votes."""
    return feature_key in COMING_SOON_FEATURES


def get_feature_metadata(feature_key: str) -> dict[str, object] | None:
    """Return display metadata for a feature_key (or None if unknown)."""
    return COMING_SOON_FEATURES.get(feature_key)


def list_features() -> list[dict[str, object]]:
    """All registered coming-soon features, with their key inlined.

    Used by the admin "list all polls" endpoint.
    """
    return [
        {"feature_key": key, **meta}
        for key, meta in COMING_SOON_FEATURES.items()
    ]
