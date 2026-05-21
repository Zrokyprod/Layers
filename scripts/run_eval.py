"""Detector eval runner (Rule 6 — ZROKY-006).

Usage:
    python scripts/run_eval.py --detector=TOKEN_OVERFLOW
    python scripts/run_eval.py --all
    python scripts/run_eval.py --all --ci          # exits non-zero on threshold failure

Each detector's fixtures live in:
    eval/detectors/<CODE>/fixtures.json

Fixture schema:
    [{"id": "...", "expected": "DETECT|SKIP", "rationale": "...", "input": {...}}, ...]

Thresholds (Rule 6): precision >= 0.85 AND recall >= 0.80.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_REPO = Path(__file__).resolve().parent.parent
_EVAL_DIR = _REPO / "eval" / "detectors"
_PRECISION_THRESHOLD = 0.85
_RECALL_THRESHOLD = 0.80


# ── detector loader ───────────────────────────────────────────────────────────

def _load_detector(code: str) -> Callable[[dict[str, Any]], Any]:
    code = code.upper()
    if code == "TOKEN_OVERFLOW":
        from app.services.detectors.token_overflow import detect
        return detect
    if code == "RATE_LIMIT":
        from app.services.detectors.rate_limit import detect
        return detect
    if code == "AUTH_FAILURE":
        from app.services.detectors.auth_failure import detect
        return detect
    if code == "PROVIDER_ERROR":
        from app.services.detectors.provider_error import detect
        return detect
    if code == "LOOP_DETECTED":
        from app.services.detectors.loop import detect_entry
        return detect_entry
    if code == "COST_SPIKE":
        from app.services.detectors.cost_spike import detect_entry
        return detect_entry
    raise ValueError(f"Unknown detector: {code!r}. Valid: TOKEN_OVERFLOW, RATE_LIMIT, AUTH_FAILURE, PROVIDER_ERROR, LOOP_DETECTED, COST_SPIKE")


# ── eval core ─────────────────────────────────────────────────────────────────

def _run_detector_eval(code: str) -> dict[str, Any]:
    fixtures_path = _EVAL_DIR / code / "fixtures.json"
    if not fixtures_path.exists():
        return {"code": code, "error": f"fixtures not found: {fixtures_path}"}

    fixtures = json.loads(fixtures_path.read_text())
    if len(fixtures) < 20:
        return {"code": code, "error": f"only {len(fixtures)} fixtures — Rule 6 requires >= 20"}

    try:
        detector = _load_detector(code)
    except Exception as e:
        return {"code": code, "error": f"load failed: {e}"}

    now = datetime.now(timezone.utc)
    tp = fp = fn = tn = 0
    failures: list[str] = []

    for fx in fixtures:
        fid = fx["id"]
        payload = fx["input"]
        expected_detect = fx["expected"] == "DETECT"

        try:
            result = detector(payload, now=now)
        except TypeError:
            result = detector(payload)
        except Exception as e:
            failures.append(f"{fid}: detector raised {e}")
            result = None

        did_detect = result is not None
        if expected_detect and did_detect:
            tp += 1
        elif expected_detect and not did_detect:
            fn += 1
            failures.append(f"{fid} FN: expected DETECT but got SKIP — {fx['rationale']}")
        elif not expected_detect and did_detect:
            fp += 1
            failures.append(f"{fid} FP: expected SKIP but got DETECT — {fx['rationale']}")
        else:
            tn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    passed = precision >= _PRECISION_THRESHOLD and recall >= _RECALL_THRESHOLD

    return {
        "code": code,
        "fixtures": len(fixtures),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "passed": passed,
        "failures": failures,
    }


def _print_result(r: dict[str, Any]) -> None:
    if "error" in r:
        print(f"  ERROR  [{r['code']}] {r['error']}")
        return
    status = "PASS" if r["passed"] else "FAIL"
    print(
        f"  {status:4s}   [{r['code']}]  "
        f"precision={r['precision']:.3f}  recall={r['recall']:.3f}  f1={r['f1']:.3f}  "
        f"tp={r['tp']} fp={r['fp']} fn={r['fn']} tn={r['tn']}"
    )
    for fail in r.get("failures", []):
        print(f"         >> {fail}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Zroky detector eval runner (Rule 6)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--detector", metavar="CODE", help="Run eval for one detector")
    group.add_argument("--all", action="store_true", help="Run eval for all known detectors")
    parser.add_argument("--ci", action="store_true", help="Exit non-zero if any detector fails threshold")
    args = parser.parse_args()

    codes = (
        ["TOKEN_OVERFLOW", "RATE_LIMIT", "AUTH_FAILURE", "PROVIDER_ERROR", "LOOP_DETECTED", "COST_SPIKE"]
        if args.all
        else [args.detector.upper()]
    )

    sys.path.insert(0, str(_REPO / "zroky-backend"))

    results = []
    for code in codes:
        r = _run_detector_eval(code)
        _print_result(r)
        results.append(r)

    print()
    overall = all(r.get("passed", False) for r in results if "error" not in r)
    print(f"Overall: {'PASS' if overall else 'FAIL'}")

    if args.ci and not overall:
        sys.exit(1)


if __name__ == "__main__":
    main()
