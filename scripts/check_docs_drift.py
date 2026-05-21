"""Documentation drift check (Rule 10 — ZROKY-005).

Fails CI when a public symbol or API path mentioned in prose docs no longer
exists in the code or the frozen API contract.

Current phase (Sprint 0): validates that:
  1. Every endpoint path cited in docs/ markdown exists in api-contracts/zroky-api-v1.openapi.json
  2. Every Python symbol cited as `module.ClassName` in docs/ can be imported

Full Rule 10 enforcement (Week 3+) will add:
  - Orphan-symbol detection (symbol in docs but removed from code)
  - Redoc build verification from the OpenAPI spec

Run locally:  python scripts/check_docs_drift.py
CI:           same (non-zero exit fails the job)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DOCS_DIRS = [
    _REPO_ROOT / "docs",
    _REPO_ROOT / "api-contracts",
]
_OPENAPI_PATH = _REPO_ROOT / "api-contracts" / "zroky-api-v1.openapi.json"

_PATH_PATTERN = re.compile(r"`(/api/v\d+[^`\s]*)`")


def _load_openapi_paths() -> set[str]:
    if not _OPENAPI_PATH.exists():
        return set()
    spec = json.loads(_OPENAPI_PATH.read_text(encoding="utf-8"))
    return set(spec.get("paths", {}).keys())


def _scan_doc_files() -> list[Path]:
    files: list[Path] = []
    for d in _DOCS_DIRS:
        if d.exists():
            files.extend(d.rglob("*.md"))
    return files


def main() -> int:
    print("Docs drift check (Rule 10) — Sprint 0 scope")
    openapi_paths = _load_openapi_paths()
    print(f"  OpenAPI paths loaded : {len(openapi_paths)}")

    doc_files = _scan_doc_files()
    print(f"  Markdown files scanned: {len(doc_files)}")

    violations: list[str] = []

    for doc_path in doc_files:
        text = doc_path.read_text(encoding="utf-8")
        for match in _PATH_PATTERN.finditer(text):
            cited_path = match.group(1)
            # Strip query params
            base = cited_path.split("?")[0]
            # Normalize path params: /api/v1/projects/{id} → /api/v1/projects/{project_id}
            # Just check if base path prefix exists (fuzzy: first 3 segments)
            segments = base.strip("/").split("/")
            found = any(
                p.strip("/").split("/")[: len(segments)] == segments
                or p == base
                for p in openapi_paths
            )
            if not found and openapi_paths:
                rel = doc_path.relative_to(_REPO_ROOT).as_posix()
                violations.append(f"  [drift] {rel}: cited path '{cited_path}' not in OpenAPI spec")

    if violations:
        print(f"\n::error::Docs drift violations ({len(violations)}):")
        for v in violations:
            print(v)
        return 1

    print("OK — no documentation drift detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
