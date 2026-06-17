"""Documentation drift check (Rule 10).

Fails CI when a public API path mentioned in product docs no longer exists in
the frozen API contract.

Run locally:  python scripts/check_docs_drift.py
CI:           same (non-zero exit fails the job)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DOCS_DIRS = [_REPO_ROOT / "docs"]
_DOC_SOURCE_FILES = [
    _REPO_ROOT / "README.md",
    _REPO_ROOT / "zroky-landing" / "src" / "pages" / "docs" / "docsContent.ts",
    _REPO_ROOT / "zroky-landing" / "src" / "pages" / "DocsPage.tsx",
]
_OPENAPI_PATH = _REPO_ROOT / "api-contracts" / "zroky-api-v1.openapi.json"

_PATH_PATTERN = re.compile(
    r"(?P<path>/(?:api/zroky/|api/)?v\d+(?:/[A-Za-z0-9_{}.$%+~:=@-]+)+[^`'\"\s),]*)"
)


def _load_openapi_paths() -> set[str]:
    if not _OPENAPI_PATH.exists():
        return set()
    spec = json.loads(_OPENAPI_PATH.read_text(encoding="utf-8"))
    return set(spec.get("paths", {}).keys())


def _scan_doc_files() -> list[Path]:
    files: set[Path] = {path for path in _DOC_SOURCE_FILES if path.exists()}
    for directory in _DOCS_DIRS:
        if directory.exists():
            files.update(directory.rglob("*.md"))
            files.update(directory.rglob("*.mdx"))
    return sorted(files)


def _normalize_cited_path(raw: str) -> str:
    path = raw.split("?", 1)[0].split("#", 1)[0].rstrip("\\.,;:")
    if path.startswith("/api/zroky/"):
        path = "/" + path.removeprefix("/api/zroky/")
    elif path.startswith("/api/"):
        path = "/" + path.removeprefix("/api/")
    return path


def _path_matches_spec(cited_path: str, spec_path: str) -> bool:
    cited_segments = cited_path.strip("/").split("/")
    spec_segments = spec_path.strip("/").split("/")
    if len(cited_segments) != len(spec_segments):
        return False
    return all(
        cited == spec
        or (cited.startswith("{") and cited.endswith("}"))
        or (spec.startswith("{") and spec.endswith("}"))
        for cited, spec in zip(cited_segments, spec_segments, strict=True)
    )


def main() -> int:
    print("Docs drift check (Rule 10)")
    openapi_paths = _load_openapi_paths()
    print(f"  OpenAPI paths loaded : {len(openapi_paths)}")

    doc_files = _scan_doc_files()
    print(f"  Docs sources scanned : {len(doc_files)}")

    if not doc_files:
        print("\n::error::Docs drift check scanned zero documentation sources.")
        return 1

    violations: list[str] = []
    citation_count = 0

    for doc_path in doc_files:
        text = doc_path.read_text(encoding="utf-8")
        for match in _PATH_PATTERN.finditer(text):
            cited_path = match.group("path")
            base = _normalize_cited_path(cited_path)
            citation_count += 1
            found = any(
                spec_path == base or _path_matches_spec(base, spec_path)
                for spec_path in openapi_paths
            )
            if not found and openapi_paths:
                rel = doc_path.relative_to(_REPO_ROOT).as_posix()
                violations.append(
                    f"  [drift] {rel}: cited path '{cited_path}' not in OpenAPI spec"
                )

    print(f"  Endpoint citations : {citation_count}")

    if violations:
        print(f"\n::error::Docs drift violations ({len(violations)}):")
        for violation in violations:
            print(violation)
        return 1

    print("OK - no documentation drift detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
