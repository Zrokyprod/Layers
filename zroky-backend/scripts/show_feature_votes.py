#!/usr/bin/env python3
"""Owner CLI — show all feature-interest votes at a glance.

Module 9 smoke-test alternative. Reads `feature_interest_votes`
directly from the database and prints a pretty summary + the most
recent "interested" votes (with use_case text) per feature.

Usage:
    # Default — print summary + 10 most recent per feature
    python scripts/show_feature_votes.py

    # Only one feature
    python scripts/show_feature_votes.py --feature pilot.tier1_autonomy

    # Show more recent rows per feature
    python scripts/show_feature_votes.py --limit 50

    # Export everything to CSV
    python scripts/show_feature_votes.py --csv tier1_votes.csv

    # JSON output (for scripting / piping into jq)
    python scripts/show_feature_votes.py --json

The script honors DATABASE_URL from env so it works against local
SQLite or a remote Postgres equally well.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Allow `python scripts/show_feature_votes.py` from the repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.services.feature_interest_registry import COMING_SOON_FEATURES
from app.services.feature_interest_service import (
    list_recent_votes,
    summarize_all,
    summarize_feature,
)


# ── ANSI colors (degrade gracefully on Windows < Win10) ─────────────────────


def _supports_color() -> bool:
    if os.name == "nt":
        # Windows Terminal / VSCode terminal support ANSI; classic cmd
        # does not. Best-effort: only enable when running inside one of
        # the modern terminals (env var WT_SESSION or TERM_PROGRAM).
        return any(k in os.environ for k in ("WT_SESSION", "TERM_PROGRAM"))
    return sys.stdout.isatty()


class C:
    ENABLED = _supports_color()
    RESET = "\033[0m" if ENABLED else ""
    BOLD = "\033[1m" if ENABLED else ""
    DIM = "\033[2m" if ENABLED else ""
    GREEN = "\033[92m" if ENABLED else ""
    RED = "\033[91m" if ENABLED else ""
    YELLOW = "\033[93m" if ENABLED else ""
    CYAN = "\033[96m" if ENABLED else ""
    GRAY = "\033[90m" if ENABLED else ""


# ── helpers ─────────────────────────────────────────────────────────────────


def _make_session():
    """Open a DB session honoring DATABASE_URL env var."""
    db_url = os.environ.get("DATABASE_URL", "sqlite:///./.data/test_shared.db")
    engine = create_engine(db_url, future=True)
    return sessionmaker(bind=engine, autoflush=False, future=True)()


def _bar(pct: float, width: int = 24) -> str:
    """Return a 24-char unicode progress bar for `pct` in [0, 1]."""
    if pct < 0 or pct > 1:
        pct = max(0.0, min(1.0, pct))
    filled = int(round(pct * width))
    return "▓" * filled + "░" * (width - filled)


def _status_badge(status: str) -> str:
    if status == "above_threshold":
        return f"{C.GREEN}✓ ABOVE THRESHOLD — consider shipping{C.RESET}"
    if status == "below_threshold":
        return f"{C.YELLOW}↓ below threshold{C.RESET}"
    return f"{C.GRAY}(no votes yet){C.RESET}"


def _fmt_dt(value: datetime | None) -> str:
    if value is None:
        return "—"
    return value.strftime("%Y-%m-%d %H:%M UTC")


# ── printers ────────────────────────────────────────────────────────────────


def _print_header() -> None:
    line = "═" * 64
    print(f"{C.BOLD}{C.CYAN}{line}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}  Zroky Feature Interest — Owner Dashboard{C.RESET}")
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    print(f"{C.DIM}  Generated: {now}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}{line}{C.RESET}\n")


def _print_feature(
    db, summary: dict[str, object], *, recent_limit: int,
) -> None:
    key = summary["feature_key"]
    name = summary["name"]
    total = summary["total"]
    interested = summary["interested"]
    pct = float(summary["interested_pct"])
    threshold = float(summary["ships_after_threshold"])
    status = summary["status"]

    print(f"{C.BOLD}▶ {key}{C.RESET}  ({name})")
    print(f"   Total votes:        {total}")
    print(
        f"   {C.GREEN}👍 Interested:{C.RESET}      {interested:>3}  "
        f"({int(round(pct * 100))}%)"
    )
    print(
        f"   {C.RED}👎 Not interested:{C.RESET}  "
        f"{summary['not_interested']:>3}  "
        f"({int(round((1 - pct) * 100)) if total else 0}%)"
    )
    print(f"   {C.DIM}{_bar(pct)}{C.RESET}  threshold: {int(threshold * 100)}%")
    print(f"   Status:             {_status_badge(str(status))}")
    print(f"   Last vote:          {_fmt_dt(summary['last_voted_at'])}")  # type: ignore[arg-type]

    if int(total) == 0:
        print()
        return

    recent = list_recent_votes(
        db, feature_key=str(key), limit=recent_limit, vote_filter="interested"
    )
    if recent:
        print(f"\n   {C.BOLD}Recent 'interested' voters:{C.RESET}")
        print(f"   {C.DIM}{'─' * 60}{C.RESET}")
        for row in recent:
            dt = _fmt_dt(row["created_at"])  # type: ignore[arg-type]
            email = row["user_email_masked"] or row["user_subject"]
            project = row["project_name"] or row["project_id"]
            print(f"   {C.DIM}{dt}{C.RESET}  • {email} / {project}")
            use_case = row["use_case"]
            if use_case:
                # indent + wrap-light
                text = str(use_case).strip()
                if len(text) > 90:
                    text = text[:87] + "..."
                print(f"                     {C.CYAN}\"{text}\"{C.RESET}")
    print()


def _export_csv(db, path: str, feature_filter: str | None) -> None:
    keys = [feature_filter] if feature_filter else list(COMING_SOON_FEATURES.keys())
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, quoting=csv.QUOTE_MINIMAL)
        writer.writerow([
            "feature_key", "created_at", "updated_at", "vote",
            "user_email_masked", "user_subject", "project_id",
            "project_name", "use_case",
        ])
        total_rows = 0
        for key in keys:
            rows = list_recent_votes(db, feature_key=key, limit=10000)
            for row in rows:
                writer.writerow([
                    row["feature_key"],
                    row["created_at"].isoformat() if row["created_at"] else "",  # type: ignore[union-attr]
                    row["updated_at"].isoformat() if row["updated_at"] else "",  # type: ignore[union-attr]
                    row["vote"],
                    row["user_email_masked"] or "",
                    row["user_subject"],
                    row["project_id"],
                    row["project_name"] or "",
                    (row["use_case"] or "").replace("\n", " ").replace("\r", " "),  # type: ignore[union-attr]
                ])
                total_rows += 1
    print(f"{C.GREEN}✓ Exported {total_rows} vote(s) to {path}{C.RESET}")


def _print_json(db, feature_filter: str | None) -> None:
    summaries = summarize_all(db)
    if feature_filter:
        summaries = [s for s in summaries if s["feature_key"] == feature_filter]
    output = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "features": [
            {
                **{k: v for k, v in s.items() if k != "last_voted_at"},
                "last_voted_at": (
                    s["last_voted_at"].isoformat()  # type: ignore[union-attr]
                    if s["last_voted_at"] else None
                ),
            }
            for s in summaries
        ],
    }
    print(json.dumps(output, indent=2))


# ── entry point ─────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Show feature-interest votes (owner CLI).",
    )
    parser.add_argument(
        "--feature", help="Filter to one feature_key (default: all)",
    )
    parser.add_argument(
        "--limit", type=int, default=10,
        help="How many recent 'interested' votes to print per feature (default 10)",
    )
    parser.add_argument(
        "--csv", metavar="PATH",
        help="Export all votes to this CSV path (no pretty output)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Emit JSON summary instead of pretty output",
    )
    args = parser.parse_args()

    db = _make_session()
    try:
        if args.csv:
            _export_csv(db, args.csv, args.feature)
            return 0

        if args.json:
            _print_json(db, args.feature)
            return 0

        _print_header()

        if args.feature:
            summary = summarize_feature(db, feature_key=args.feature)
            _print_feature(db, summary, recent_limit=args.limit)
        else:
            summaries = summarize_all(db)
            if not summaries:
                print(f"{C.DIM}(No coming-soon features are registered.){C.RESET}")
                return 0
            for s in summaries:
                _print_feature(db, s, recent_limit=args.limit)

        # Footer hint
        print(f"{C.DIM}Tip: export everything with:")
        print(f"  python scripts/show_feature_votes.py --csv votes.csv{C.RESET}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
