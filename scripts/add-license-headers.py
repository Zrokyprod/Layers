#!/usr/bin/env python3
"""CI rule 16 — stamp missing SPDX license headers on all OSS source files.

Usage:
    python scripts/add-license-headers.py [--check]

Without --check: adds the header to any file that is missing it (idempotent).
With    --check: exits non-zero if any file is missing the header (CI mode).
"""
from __future__ import annotations

import sys
from pathlib import Path

HEADER_SPDX = "SPDX-License-Identifier: FSL-1.1-MIT"
HEADER_COPYRIGHT = "Copyright 2026 Zroky AI"

EXTENSIONS = {
    ".py": "#",
    ".go": "//",
    ".ts": "//",
}

OSS_DIRS = [
    "zroky-sdk/zroky",
    "zroky-sdk/tests",
    "zroky-sdk-js/src",
    "zroky-sdk-js/tests",
    "zroky-gateway/internal",
    "zroky-gateway/cmd",
]

ROOT = Path(__file__).parent.parent


def make_header(comment: str) -> str:
    return f"{comment} {HEADER_SPDX}\n{comment} {HEADER_COPYRIGHT}\n"


def has_header(text: str) -> bool:
    return HEADER_SPDX in text


def stamp_file(path: Path, comment: str, check_only: bool) -> bool:
    """Return True if the file was missing the header (needed stamping)."""
    text = path.read_text(encoding="utf-8")
    if has_header(text):
        return False
    if check_only:
        print(f"MISSING header: {path.relative_to(ROOT)}")
        return True
    header = make_header(comment)
    # Preserve shebang line if present
    if text.startswith("#!"):
        first_newline = text.index("\n") + 1
        new_text = text[:first_newline] + header + "\n" + text[first_newline:]
    else:
        new_text = header + "\n" + text
    path.write_text(new_text, encoding="utf-8")
    print(f"Stamped: {path.relative_to(ROOT)}")
    return True


def main() -> None:
    check_only = "--check" in sys.argv

    missing: list[Path] = []
    for rel_dir in OSS_DIRS:
        src_dir = ROOT / rel_dir
        if not src_dir.exists():
            continue
        for path in sorted(src_dir.rglob("*")):
            if not path.is_file():
                continue
            comment = EXTENSIONS.get(path.suffix)
            if comment is None:
                continue
            if stamp_file(path, comment, check_only):
                missing.append(path)

    if check_only and missing:
        print(f"\n{len(missing)} file(s) missing the SPDX license header.")
        print("Run:  python scripts/add-license-headers.py")
        sys.exit(1)
    elif not check_only:
        print(f"\nDone — stamped {len(missing)} file(s).")
    else:
        print("All source files have the SPDX license header.")


if __name__ == "__main__":
    main()
