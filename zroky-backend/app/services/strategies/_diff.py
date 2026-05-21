"""
Pure diff-formatting helpers used by all strategy modules.
No I/O, no external dependencies.
"""
from __future__ import annotations


def _conceptual_diff(header: str, lines: list[str]) -> str:
    rendered = ["--- ADVISORY ---", f"# {header}"]
    rendered.extend(f"# - {line}" for line in lines)
    return "\n".join(rendered)


def _before_after_diff(*, before: str, after: str) -> str:
    return "\n".join(
        [
            "--- BEFORE ---",
            before.rstrip(),
            "",
            "--- AFTER ---",
            after.rstrip(),
        ]
    )


def _extract_before_after(diff: str) -> tuple[str | None, str | None]:
    if "--- BEFORE ---" not in diff or "--- AFTER ---" not in diff:
        return None, None
    before_part, after_part = diff.split("--- AFTER ---", 1)
    before = before_part.replace("--- BEFORE ---", "", 1).strip("\n")
    after = after_part.strip("\n")
    if not before.strip() or not after.strip():
        return None, None
    return before, after


def _build_unified_patch(*, target_file: str, diff: str) -> str:
    if target_file == "unknown":
        return ""
    before, after = _extract_before_after(diff)
    if not before or not after:
        return ""
    before_lines = before.splitlines()
    after_lines = after.splitlines()
    old_count = max(1, len(before_lines))
    new_count = max(1, len(after_lines))
    hunk = [
        f"diff --git a/{target_file} b/{target_file}",
        f"--- a/{target_file}",
        f"+++ b/{target_file}",
        f"@@ -1,{old_count} +1,{new_count} @@",
    ]
    hunk.extend(f"-{line}" for line in before_lines)
    hunk.extend(f"+{line}" for line in after_lines)
    return "\n".join(hunk)


def _anchor_from_diff(diff: str) -> str | None:
    before, _after = _extract_before_after(diff)
    if before:
        return before.splitlines()[0].strip() or None
    return None


def _first_relevant_line(snippet: str, needles: tuple[str, ...]) -> str | None:
    for line in snippet.splitlines():
        lowered = line.lower()
        if any(needle.lower() in lowered for needle in needles):
            return line
    return None


def _replace_assignment_rhs(line: str, replacement: str) -> str:
    if "=" not in line:
        return line
    left, _right = line.split("=", 1)
    suffix = "," if line.rstrip().endswith(",") else ""
    return f"{left.rstrip()} = {replacement}{suffix}"


def _assignment_rhs(line: str) -> str:
    if "=" not in line:
        return "messages"
    rhs = line.split("=", 1)[1].strip().rstrip(",")
    return rhs or "messages"


def _token_budget(model_limit: int) -> int:
    if model_limit <= 0:
        return 3000
    return max(512, int(model_limit * 0.75))
