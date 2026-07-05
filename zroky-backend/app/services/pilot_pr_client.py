"""
Pilot Tier-2 PR client seam (ZROKY-TECHNICAL-PLAN-V2 §17.3 #2 / Module 10).

The plan has an OPEN decision: GitHub App vs OAuth for the auto-PR
flow. Rather than commit to either, Module 10 ships the entire Tier-2
pipeline behind this `GitHubPRClient` protocol. The pure-logic
producer (`pilot_pr_payload.build_pr_payload`) and the policy gate
(`pilot_pr_dispatch.evaluate_tier2_dispatch`) talk to this protocol
only — when the team picks an auth strategy, a single ~200-line
implementation file replaces `DryRunPRClient` as the production
factory return, and nothing else changes.

Three implementations ship in this file:

  * `DryRunPRClient`     — test-default. Returns a sentinel
                            `dry-run://...` URL and records the
                            payload in-memory for assertions. Does
                            NOT touch the network.
  * `RecordingPRClient`  — staging-friendly. Same as DryRun but
                            persists each call to a structured log
                            line for off-line audit.
  * `RaisingPRClient`    — every call raises. Useful to assert that
                            policy gates fail-CLOSED before the
                            client is ever invoked (e.g. when
                            entitlements are missing).

The selection is driven by `Settings.PILOT_PR_CLIENT_BACKEND`:

    "dry_run"  (default in tests + dev)
    "recording"
    # "github_app" / "github_oauth" added when §17.3 #2 lands.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from app.services.pilot_pr_payload import PRPayload

logger = logging.getLogger(__name__)


# ── return type ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PRCreateResult:
    """The minimal contract every backend honors.

    `pr_url` is what gets persisted to `pilot_actions.pr_url`. The
    DryRun backend uses a `dry-run://` scheme so downstream code can
    distinguish at audit time without an extra column. `head_sha` is
    informational — useful when the dashboard wants to render
    "applied at commit X".
    """

    pr_url: str
    head_sha: str | None = None
    # `dry_run=True` rows are excluded from the "PRs opened today"
    # daily cap counter — the cap protects the customer's repo, not
    # an in-memory log.
    dry_run: bool = False


# ── protocol ─────────────────────────────────────────────────────────────────


@runtime_checkable
class GitHubPRClient(Protocol):
    """All backends implement this single method.

    `open_pr` is responsible for:  # noqa: F401  # noqa: replay-lint
      * resolving the target repo (from project_id → repo binding,
        looked up by the implementation — NOT by the dispatcher),
      * idempotency at the GitHub level (an existing PR for the same
        head_branch should be UPDATED, not duplicated),
      * raising `PRClientError` on transient / retryable failures and
        `PRClientPermanentError` on permanent failures (no token,
        repo deleted, branch protection, etc.).

    The dispatch layer handles the retry / skip / fail decision based
    on which error subclass surfaces.
    """

    def open_pr(self, payload: PRPayload) -> PRCreateResult:  # noqa: F401  # noqa: replay-lint
        ...


# ── exceptions ───────────────────────────────────────────────────────────────


class PRClientError(RuntimeError):
    """Transient client failure — the dispatcher should mark the
    action `failed` but a follow-up retry has a reasonable chance of
    succeeding. Examples: 5xx from GitHub, network timeout, rate
    limit with a Retry-After."""


class PRClientPermanentError(PRClientError):
    """Permanent client failure — retrying will not help. Examples:
    missing repo binding for the project, customer revoked the
    GitHub App installation, branch protection rejected the PR,
    invalid path in the patch. The dispatcher marks the action
    `failed` and does NOT retry."""


# ── dry-run backend (test + dev default) ─────────────────────────────────────


class DryRunPRClient:
    """In-memory backend. Records every payload it receives so tests
    can assert on the produced PR shape without monkeypatching HTTP.

    Thread-safe — uses a Lock around the call log so concurrent
    Celery workers in test mode don't drop records.
    """

    def __init__(self) -> None:
        self._calls: list[PRPayload] = []
        self._lock = threading.Lock()

    def open_pr(self, payload: PRPayload) -> PRCreateResult:  # noqa: F401  # noqa: replay-lint
        with self._lock:
            self._calls.append(payload)
        url = f"dry-run://pilot-action/{payload.fingerprint}"
        logger.info(
            "dry_run_pr_opened project=%s anomaly=%s action=%s fp=%s",
            payload.project_id,
            payload.anomaly_id,
            payload.action_type,
            payload.fingerprint[:12],
        )
        return PRCreateResult(pr_url=url, head_sha=None, dry_run=True)

    # ── test helpers ─────────────────────────────────────────────────

    @property
    def calls(self) -> list[PRPayload]:
        """Snapshot copy of the call log. Mutating the returned list
        does not affect the backend's internal record."""
        with self._lock:
            return list(self._calls)

    def reset(self) -> None:
        with self._lock:
            self._calls.clear()


# ── recording backend (staging-friendly) ─────────────────────────────────────


class RecordingPRClient:
    """Same as DryRun but writes a structured log line on every call
    so a separate off-line auditor can reconstruct what the autopilot
    would have done. Used in staging environments where we want to
    see the volume + shape of real anomalies without yet committing
    to opening real PRs.
    """

    def open_pr(self, payload: PRPayload) -> PRCreateResult:  # noqa: F401  # noqa: replay-lint
        logger.info(
            "recording_pr_open project=%s anomaly=%s action=%s fp=%s "
            "title=%r files=%d base=%s head=%s",
            payload.project_id,
            payload.anomaly_id,
            payload.action_type,
            payload.fingerprint,
            payload.title,
            len(payload.files),
            payload.base_branch,
            payload.head_branch,
        )
        url = f"recording://pilot-action/{payload.fingerprint}"
        return PRCreateResult(pr_url=url, head_sha=None, dry_run=True)


# ── raising backend (defense-in-depth tests) ─────────────────────────────────


class RaisingPRClient:
    """Every call raises `PRClientPermanentError`. Tests use this to
    assert that policy gates fail-CLOSED — e.g. when
    `pilot.tier2_pr_enabled` is False, the dispatcher must NOT even
    construct a client call, so swapping in this backend should not
    produce an exception on the policy-gate path."""

    def open_pr(self, payload: PRPayload) -> PRCreateResult:  # noqa: F401  # noqa: replay-lint
        raise PRClientPermanentError(
            "RaisingPRClient invoked — a policy gate should have "
            "short-circuited before this point"
        )


# ── factory ──────────────────────────────────────────────────────────────────


_DEFAULT_BACKEND = "dry_run"

# Module-level singleton — every call to `get_pr_client` returns the
# same instance so DryRunPRClient's recorded call log survives across
# a single test's two dispatch calls. Reset by `reset_pr_client()` in
# the test fixture.
_singleton_lock = threading.Lock()
_singleton: GitHubPRClient | None = None


def get_pr_client() -> GitHubPRClient:
    """Return the configured backend.

    Selection is driven by `Settings.PILOT_PR_CLIENT_BACKEND` so test
    suites can swap implementations without monkeypatching the
    dispatcher. Unknown values log a warning and fall back to
    `DryRunPRClient` — fail-CLOSED for safety (a typo in env vars
    should not silently start opening PRs on customer repos).
    """
    global _singleton
    with _singleton_lock:
        if _singleton is not None:
            return _singleton
        _singleton = _build_backend_from_settings()
        return _singleton


def reset_pr_client() -> None:
    """Test helper — clear the cached singleton so the next
    `get_pr_client()` call rebuilds from current settings."""
    global _singleton
    with _singleton_lock:
        _singleton = None


def _build_backend_from_settings() -> GitHubPRClient:
    # Local import to avoid module-load circular (settings → services).
    from app.core.config import get_settings

    settings = get_settings()
    backend = (
        getattr(settings, "PILOT_PR_CLIENT_BACKEND", None) or _DEFAULT_BACKEND
    )
    backend = str(backend).strip().lower()
    if backend == "dry_run":
        return DryRunPRClient()
    if backend == "recording":
        return RecordingPRClient()
    # Future: github_app / github_oauth wired in once §17.3 #2 lands.
    logger.warning(
        "pilot_pr_client_unknown_backend backend=%r — falling back to dry_run "
        "(fail-CLOSED). This means no real PRs will be opened.",
        backend,
    )
    return DryRunPRClient()
