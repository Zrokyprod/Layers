"""AUTH_FAILURE template fix strategy."""
from __future__ import annotations

from typing import Any

from app.services._fix_utils import _as_int, _as_text, _clean_snippet
from app.services.strategies._diff import (
    _before_after_diff,
    _conceptual_diff,
    _first_relevant_line,
)
from app.services.strategies.ai_fix import FixTuple


def generate(request: Any) -> FixTuple:
    return _auth_failure_fix(request)


def _auth_failure_fix(request: Any) -> FixTuple:
    evidence = request.evidence
    provider = _as_text(evidence.get("provider") or request.call_context.get("provider"))
    status_code = _as_int(evidence.get("status_code"))
    snippet = _clean_snippet(request.code_snippet)

    if snippet:
        diff = _auth_failure_diff_from_snippet(snippet, status_code=status_code)
        strategy_confidence = 0.90 if "AFTER" in diff else 0.72
    else:
        diff = _conceptual_diff(
            "No code snippet was provided. Review credential management and authentication flow.",
            [
                "Verify API keys/secrets are correctly configured and not expired.",
                "Check for missing or malformed authorization headers.",
                "Implement credential rotation mechanism.",
            ],
        )
        strategy_confidence = 0.60

    auth_type = "token" if status_code == 401 else "permission" if status_code == 403 else "credential"
    explanation = (
        f"Authentication failed for provider {provider or 'unknown'} ({status_code or 'unknown'}). "
        f"The fix addresses {auth_type} issues to restore API access."
    )
    fix_rationale = "Proper credential management and error handling prevents auth failures and enables graceful degradation."
    alternatives = [
        {"option": "credential_rotation", "tradeoff": "More secure but requires infrastructure to distribute new keys."},
        {"option": "fallback_provider", "tradeoff": "Maintains availability but increases complexity and cost."},
        {"option": "graceful_degradation", "tradeoff": "Keeps app functional but with reduced capabilities."},
    ]
    review_points = [
        "Verify credentials are not logged or exposed in error messages.",
        "Check that credential rotation does not cause downtime.",
        "Ensure auth errors are surfaced to operators, not silently swallowed.",
    ]
    verification_steps = [
        "Confirm API calls succeed with valid credentials.",
        "Verify graceful handling when credentials are invalid.",
        "Test credential rotation without service restart.",
    ]
    rollback_instructions = [
        "Revert credential changes.",
        "Restore previous authentication configuration.",
        "Verify auth failures return with previous behavior.",
    ]
    return (
        "Fix AUTH_FAILURE with proper credential handling",
        diff,
        explanation,
        fix_rationale,
        alternatives,
        review_points,
        verification_steps,
        rollback_instructions,
        strategy_confidence,
    )


def _auth_failure_diff_from_snippet(snippet: str, *, status_code: int) -> str:
    line = _first_relevant_line(snippet, ("api_key", "token", "auth", "authorization", "credential"))
    if line and "=" in line:
        return _before_after_diff(
            before=line,
            after="api_key = <existing_credential_manager>.get_valid_key()  # Rotatable, validated",
        )
    return _before_after_diff(
        before="# Original authentication code",
        after=(
            "# Add credential validation and rotation\n"
            "api_key = <existing_credential_manager>.get_valid_key()\n"
            "if not api_key:\n"
            "    raise AuthenticationError(\"No valid credentials available\")"
        ),
    )
