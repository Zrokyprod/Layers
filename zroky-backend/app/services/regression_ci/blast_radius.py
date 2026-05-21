"""
Blast-radius detection.

Two paths produce a `BlastRadius`:

  1. DECLARED (precise) — customer wrote `zroky-blast-radius: <category>[:target]`
     in the PR body or a `.zroky.yml` file. Always wins when present.
  2. AUTO_DETECTED (heuristic) — we inspect the changed file paths and
     diff hunks against an ordered rule list. Best-effort.

A third path, OVERRIDE, is set by an operator from the dashboard and
is treated like DECLARED.

This module is **pure-functional** — no DB, no I/O. Inputs are:
  - `pr_body: str | None`   (text of the PR description)
  - `zroky_yaml: str | None` (raw bytes of `.zroky.yml` if present)
  - `changed_files: Sequence[ChangedFile]`  (path + diff hunks)

Outputs: a `BlastRadius` dataclass.

Rationale for ordered-rule auto-detection (first match wins):
    Specific > general. SYSTEM_PROMPT and MODEL_SWAP have the broadest
    blast — if a PR touches both a system prompt AND a tool prompt, we
    classify as SYSTEM_PROMPT (the larger blast). Only when no high-blast
    rule matches do we drop to TOOL_*.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from app.services.regression_ci.models import (
    BlastRadius,
    BlastRadiusCategory,
    BlastRadiusSource,
    VALID_CATEGORIES,
)

logger = logging.getLogger(__name__)


# ── input shape ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ChangedFile:
    """One changed file in the PR.

    `hunks` is the concatenation of all `+` lines from the unified diff
    (no leading `+`). We only look at additions because they're the
    forward-going behavior change; deletions are noise for blast-radius
    classification (a removed line can't introduce a regression by itself —
    the surrounding still-present code defines the new behavior).
    """

    path: str
    hunks: str = ""


# ── declaration parsing ─────────────────────────────────────────────────────

# `zroky-blast-radius: tool_prompt:refund_handler`
# Case-insensitive, allows whitespace, target is optional.
_DECLARATION_RE = re.compile(
    r"zroky-blast-radius\s*:\s*([a-z_]+)(?:\s*:\s*([A-Za-z0-9_./-]+))?",
    re.IGNORECASE,
)


def parse_declaration(text: str | None) -> BlastRadius | None:
    """Extract a declared blast radius from PR body OR `.zroky.yml`.

    Returns None when no declaration is present or when the declared
    category is invalid (we fall back to auto-detect rather than rejecting
    the PR — a typo in the declaration shouldn't block CI).
    """
    if not text:
        return None
    match = _DECLARATION_RE.search(text)
    if match is None:
        return None
    category = match.group(1).lower()
    target = match.group(2) or None
    if category not in VALID_CATEGORIES:
        logger.info(
            "regression_ci.blast_radius unknown declared category %r — "
            "falling back to auto-detect", category,
        )
        return None
    return BlastRadius(
        category=category,
        source=BlastRadiusSource.DECLARED,
        files=tuple(),
        target=target,
        confidence=1.0,
    )


# ── auto-detection rules ────────────────────────────────────────────────────
#
# Ordered: first match wins. Each rule is a (category, predicate) pair
# where predicate is a callable that returns the matched files.
#
# Heuristics chosen to be conservative — false negatives drop us to
# UNKNOWN (1000 sample, safe) rather than mis-classifying as TOOL_PROMPT
# (200 sample, dangerous). Don't add aggressive rules without raising
# the matched threshold.


_SYSTEM_PROMPT_PATH_RE = re.compile(
    r"(^|/)("
    r"system[_-]?prompt|"
    r"prompts?/system|"
    r"prompts?/base|"
    r"prompts?/main|"
    r"agent[_-]?prompt"
    r")\.(md|txt|yaml|yml|json|py|ts|tsx|js)$",
    re.IGNORECASE,
)

_TOOL_PROMPT_PATH_RE = re.compile(
    r"(^|/)prompts?/tools?/[A-Za-z0-9_-]+\.(md|txt|yaml|yml|json)$",
    re.IGNORECASE,
)

_TOOL_DEFINITION_PATH_RE = re.compile(
    r"(^|/)tools?/[A-Za-z0-9_-]+\.(py|ts|tsx|js|go)$",
    re.IGNORECASE,
)

_RETRIEVAL_CONFIG_PATH_RE = re.compile(
    r"(^|/)("
    r"rag[_-]?config|"
    r"retrieval[_-]?config|"
    r"vector[_-]?config|"
    r"index[_-]?config"
    r")\.(yaml|yml|json|toml|py|ts)$",
    re.IGNORECASE,
)

# Hunk-content rules — looked at when path rules don't fire.
# Keep these tight; broad regex on diff content produces false positives.
_MODEL_SWAP_HUNK_RE = re.compile(
    r"""(?ix)
    (?:
        ^\s*model\s*[:=]\s*['"][^'"]+['"] |
        \bmodel_name\s*[:=]\s*['"][^'"]+['"] |
        \bgpt-[0-9]\.?[0-9]?[a-z-]* |
        \bclaude-[a-z]+(?:-[0-9]+)? |
        \bgemini-[a-z0-9.-]+
    )
    """,
    re.MULTILINE,
)

_MODEL_PARAMS_HUNK_RE = re.compile(
    r"""(?ix)
    (?:
        \btemperature\s*[:=]\s*[0-9.]+ |
        \btop_?p\s*[:=]\s*[0-9.]+ |
        \btop_?k\s*[:=]\s*[0-9]+ |
        \bseed\s*[:=]\s*[0-9]+ |
        \bmax_?tokens?\s*[:=]\s*[0-9]+ |
        \bfrequency_?penalty\s*[:=]\s*[0-9.-]+ |
        \bpresence_?penalty\s*[:=]\s*[0-9.-]+
    )
    """,
    re.MULTILINE,
)


def _match_path(files: Sequence[ChangedFile], pattern: re.Pattern[str]) -> tuple[ChangedFile, ...]:
    return tuple(f for f in files if pattern.search(f.path))


def _match_hunks(files: Sequence[ChangedFile], pattern: re.Pattern[str]) -> tuple[ChangedFile, ...]:
    return tuple(f for f in files if f.hunks and pattern.search(f.hunks))


def auto_detect(changed_files: Sequence[ChangedFile]) -> BlastRadius:
    """Apply ordered rules; first match wins. Falls back to UNKNOWN.

    Confidence reflects how many distinct evidence signals fired:
      - Path-rule match     → 0.85
      - Hunk-rule match     → 0.70 (more noisy)
      - UNKNOWN fallback    → 0.30
    These numbers are reported to the customer in the PR comment so
    they can see WHY we classified the way we did and override if needed.
    """
    if not changed_files:
        return BlastRadius(
            category=BlastRadiusCategory.UNKNOWN,
            source=BlastRadiusSource.AUTO_DETECTED,
            files=tuple(),
            target=None,
            confidence=0.30,
        )

    # 1. SYSTEM_PROMPT — broadest blast, check first.
    matched = _match_path(changed_files, _SYSTEM_PROMPT_PATH_RE)
    if matched:
        return BlastRadius(
            category=BlastRadiusCategory.SYSTEM_PROMPT,
            source=BlastRadiusSource.AUTO_DETECTED,
            files=tuple(f.path for f in matched),
            target=None,
            confidence=0.85,
        )

    # 2. MODEL_SWAP — next-broadest. Check hunks (rare to have a dedicated file).
    matched = _match_hunks(changed_files, _MODEL_SWAP_HUNK_RE)
    if matched:
        return BlastRadius(
            category=BlastRadiusCategory.MODEL_SWAP,
            source=BlastRadiusSource.AUTO_DETECTED,
            files=tuple(f.path for f in matched),
            target=None,
            confidence=0.70,
        )

    # 3. RETRIEVAL_CONFIG.
    matched = _match_path(changed_files, _RETRIEVAL_CONFIG_PATH_RE)
    if matched:
        return BlastRadius(
            category=BlastRadiusCategory.RETRIEVAL_CONFIG,
            source=BlastRadiusSource.AUTO_DETECTED,
            files=tuple(f.path for f in matched),
            target=None,
            confidence=0.85,
        )

    # 4. MODEL_PARAMS.
    matched = _match_hunks(changed_files, _MODEL_PARAMS_HUNK_RE)
    if matched:
        return BlastRadius(
            category=BlastRadiusCategory.MODEL_PARAMS,
            source=BlastRadiusSource.AUTO_DETECTED,
            files=tuple(f.path for f in matched),
            target=None,
            confidence=0.70,
        )

    # 5. TOOL_DEFINITION.
    matched = _match_path(changed_files, _TOOL_DEFINITION_PATH_RE)
    if matched:
        target = _extract_tool_name(matched[0].path)
        return BlastRadius(
            category=BlastRadiusCategory.TOOL_DEFINITION,
            source=BlastRadiusSource.AUTO_DETECTED,
            files=tuple(f.path for f in matched),
            target=target,
            confidence=0.85,
        )

    # 6. TOOL_PROMPT — narrowest. Last specific rule before UNKNOWN.
    matched = _match_path(changed_files, _TOOL_PROMPT_PATH_RE)
    if matched:
        target = _extract_tool_name(matched[0].path)
        return BlastRadius(
            category=BlastRadiusCategory.TOOL_PROMPT,
            source=BlastRadiusSource.AUTO_DETECTED,
            files=tuple(f.path for f in matched),
            target=target,
            confidence=0.85,
        )

    # 7. Fallback.
    return BlastRadius(
        category=BlastRadiusCategory.UNKNOWN,
        source=BlastRadiusSource.AUTO_DETECTED,
        files=tuple(f.path for f in changed_files),
        target=None,
        confidence=0.30,
    )


def _extract_tool_name(path: str) -> str | None:
    """Extract `refund_handler` from `prompts/tools/refund_handler.md`."""
    parts = path.rsplit("/", 1)
    leaf = parts[-1] if parts else path
    name = leaf.rsplit(".", 1)[0]
    return name or None


# ── public surface ─────────────────────────────────────────────────────────


def detect(
    *,
    changed_files: Sequence[ChangedFile],
    pr_body: str | None = None,
    zroky_yaml: str | None = None,
    operator_override: BlastRadius | None = None,
) -> BlastRadius:
    """Resolve the final BlastRadius using the precedence:

        operator_override > zroky_yaml declaration >
        pr_body declaration > auto_detect(changed_files)

    Each upstream layer can short-circuit; auto-detect is only run when
    nothing higher fires. This minimizes embedding+sampling work for
    customers who configure declarations.
    """
    if operator_override is not None:
        if operator_override.source != BlastRadiusSource.OVERRIDE:
            raise ValueError(
                "operator_override must have source=OVERRIDE, "
                f"got {operator_override.source!r}"
            )
        return operator_override

    declared = parse_declaration(zroky_yaml) or parse_declaration(pr_body)
    if declared is not None:
        return declared

    return auto_detect(changed_files)
