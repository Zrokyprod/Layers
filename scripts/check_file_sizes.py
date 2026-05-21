"""File-size lint (Rule 3 of ZROKY-Q1-90DAY-PLAN.md).

Fails CI if any tracked Python file under the scanned roots exceeds 30 KB,
unless explicitly whitelisted in .github/file-size-whitelist.txt.

Files under any `_internal/` directory are always excluded (internal implementation
detail that intentionally concentrates logic). `__pycache__/` and virtualenvs are
also skipped.

Run locally:  python scripts/check_file_sizes.py
Run in CI:    same (non-zero exit fails the job).

When splitting a file below 30 KB, REMOVE its entry from the whitelist so the
lint stays honest.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

MAX_BYTES = 30 * 1024  # 30 KB hard limit per Rule 3

SCAN_ROOTS = [
    "zroky-backend/app",
    "zroky-sdk/zroky",
]

EXCLUDE_PATH_SEGMENTS = {
    "_internal",
    "__pycache__",
    ".venv",
    "venv",
    ".pytest_basetemp",
    ".pytest_tmp_privacy",
    ".pytest_run_temp_payload",
}


def find_repo_root() -> Path:
    """Locate the repo root by walking up from this script to find `.git/`."""
    here = Path(__file__).resolve()
    for ancestor in [here.parent, *here.parents]:
        if (ancestor / ".git").exists():
            return ancestor
    # Fallback: one level above scripts/
    return here.parent.parent


def load_whitelist(path: Path) -> set[str]:
    """Parse the whitelist file. Ignores blank lines and `#` comments."""
    if not path.exists():
        return set()
    entries: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            # Normalize to POSIX separators for cross-OS consistency
            entries.add(line.replace("\\", "/"))
    return entries


def is_excluded(path: Path) -> bool:
    return any(seg in EXCLUDE_PATH_SEGMENTS for seg in path.parts)


def scan_root(root: Path, base: Path) -> list[tuple[str, int]]:
    """Return (posix_relpath, size_bytes) for every non-excluded *.py under `base`."""
    found: list[tuple[str, int]] = []
    if not base.exists():
        return found
    for path in base.rglob("*.py"):
        if is_excluded(path):
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        rel = path.relative_to(root).as_posix()
        found.append((rel, size))
    return found


def main() -> int:
    root = find_repo_root()
    whitelist_path = root / ".github" / "file-size-whitelist.txt"
    whitelist = load_whitelist(whitelist_path)

    all_files: list[tuple[str, int]] = []
    for scan in SCAN_ROOTS:
        all_files.extend(scan_root(root, root / scan))

    violations: list[tuple[str, int]] = []
    whitelisted_oversize: list[tuple[str, int]] = []
    for rel, size in all_files:
        if size <= MAX_BYTES:
            continue
        if rel in whitelist:
            whitelisted_oversize.append((rel, size))
        else:
            violations.append((rel, size))

    # Also flag stale whitelist entries (listed but no longer exist or no longer oversize)
    oversize_set = {rel for rel, _ in whitelisted_oversize}
    stale = sorted(whitelist - oversize_set)

    print(f"File-size lint (Rule 3): scanned {len(all_files)} Python files across {len(SCAN_ROOTS)} roots.")
    print(f"  limit       : {MAX_BYTES // 1024} KB")
    print(f"  oversize    : {len(whitelisted_oversize) + len(violations)}")
    print(f"  whitelisted : {len(whitelisted_oversize)}")
    print(f"  violations  : {len(violations)}")
    print(f"  stale wl    : {len(stale)}")
    print()

    if whitelisted_oversize:
        print("Accepted (whitelisted) oversize files — split tickets pending:")
        for rel, size in sorted(whitelisted_oversize, key=lambda x: -x[1]):
            print(f"  [wl] {size/1024:>6.1f} KB  {rel}")
        print()

    if violations:
        print("::error::File-size lint violations (new files exceeding 30 KB must be split or whitelisted with a ticket ref):")
        for rel, size in sorted(violations, key=lambda x: -x[1]):
            print(f"  [FAIL] {size/1024:>6.1f} KB  {rel}")
        print()
        print("Fix: split the file into smaller modules, or add the path to")
        print(f"     {whitelist_path.relative_to(root).as_posix()} with a comment")
        print(f"     referencing the split ticket.")
        return 1

    if stale:
        print("::warning::Stale whitelist entries (path no longer exists or is now under 30 KB — remove from whitelist):")
        for rel in stale:
            print(f"  [stale] {rel}")
        # Stale entries don't fail the build but should be cleaned up.

    print("OK — no new oversize files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
