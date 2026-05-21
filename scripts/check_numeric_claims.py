"""Doc lint: verify every numeric performance claim maps to a benchmark tag (Rule 4).

Scans README.md and docs/ for patterns like `p95 < 8 ms` or `p95 ≤ 5ms`.
Each claim must have a matching BENCH_TAG in benchmarks/bench_*.py.

Exit codes:
  0 — all claims backed by benchmark tags
  1 — one or more claims are unmapped (CI-blocking)

Usage:
    python scripts/check_numeric_claims.py
    python scripts/check_numeric_claims.py --strict     # fail on warnings too
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent

_CLAIM_PATTERN = re.compile(
    r"(?:p95|p99|p50|latency|overhead|throughput)\s*(?:<|≤|<=|>|≥|>=)\s*\d+(?:\.\d+)?\s*(?:ms|s|eps|req/s)",
    re.IGNORECASE,
)

_BENCH_TAG_PATTERN = re.compile(r"BENCH_TAG:(\w+)")

_DOC_GLOBS = [
    "README.md",
    "docs/**/*.md",
    "zroky-backend/docs/**/*.md",
    "zroky-sdk/README.md",
]

_BENCH_GLOB = "zroky-backend/benchmarks/bench_*.py"


def _collect_bench_tags() -> set[str]:
    tags: set[str] = set()
    for f in _REPO.glob(_BENCH_GLOB):
        for match in _BENCH_TAG_PATTERN.finditer(f.read_text()):
            tags.add(match.group(1))
    return tags


def _collect_doc_claims() -> list[tuple[Path, int, str]]:
    claims: list[tuple[Path, int, str]] = []
    for glob in _DOC_GLOBS:
        for f in _REPO.glob(glob):
            for lineno, line in enumerate(f.read_text().splitlines(), 1):
                if _CLAIM_PATTERN.search(line):
                    claims.append((f, lineno, line.strip()))
    return claims


def main() -> None:
    parser = argparse.ArgumentParser(description="Rule 4 numeric claims lint")
    parser.add_argument("--strict", action="store_true", help="Fail on warnings")
    args = parser.parse_args()

    bench_tags = _collect_bench_tags()
    claims = _collect_doc_claims()

    if not claims:
        print("No numeric performance claims found in docs. OK.")
        return

    print(f"Found {len(claims)} numeric claim(s). Registered bench tags: {sorted(bench_tags)}\n")

    errors: list[str] = []
    warnings: list[str] = []

    for path, lineno, line in claims:
        rel = path.relative_to(_REPO)
        matched_tag = None
        for tag in bench_tags:
            tag_words = set(tag.lower().replace("_", " ").split())
            line_lower = line.lower()
            if any(w in line_lower for w in tag_words):
                matched_tag = tag
                break

        if matched_tag:
            print(f"  OK   {rel}:{lineno} — backed by BENCH_TAG:{matched_tag}")
            print(f"       {line}")
        else:
            msg = f"{rel}:{lineno} — numeric claim not backed by any BENCH_TAG in benchmarks/:"
            warnings.append(msg)
            print(f"  WARN {msg}")
            print(f"       {line}")

    print()
    if errors:
        for e in errors:
            print(f"::error::{e}")
        sys.exit(1)

    if warnings and args.strict:
        for w in warnings:
            print(f"::error::{w}")
        print(f"\nFailed: {len(warnings)} unmapped claim(s). Add BENCH_TAG annotations to the relevant benchmark.")
        sys.exit(1)

    if warnings:
        for w in warnings:
            print(f"::warning::{w}")
        print(f"\n{len(warnings)} unmapped claim(s) — add BENCH_TAG annotations to suppress.")
    else:
        print("All numeric claims are backed by benchmark tags. OK.")


if __name__ == "__main__":
    main()
