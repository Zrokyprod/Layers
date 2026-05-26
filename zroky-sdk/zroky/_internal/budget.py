# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""Real-time budget enforcement engine.

Prevents runaway AI spending with configurable limits at three scopes
(project, agent, user) across rolling time windows (hourly, daily, monthly).

Architecture:
  - _BudgetRule: limit_usd + window + action (warn/soft_block/hard_block)
  - _BudgetSpend: thread-safe in-memory accumulator per (scope, window)
  - SQLite WAL: persists spend across restarts, auto-cleanup on rollover
  - Pre-call estimate: blocks before expensive call if limit exceeded
  - Post-call record: tracks actual spend including waste from failures
  - Graceful: unknown model rates use configurable default, never silently
    disabled.  SQLite errors fall back to memory-only.
"""
from __future__ import annotations

import logging
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from zroky._internal.cost import calculate_cost

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class BudgetExceededError(Exception):
    """Raised when a hard_block budget rule is triggered."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


# ---------------------------------------------------------------------------
# Budget rule
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _BudgetRule:
    limit_usd: float
    window: str  # "hourly", "daily", "monthly"
    action: str  # "warn", "soft_block", "hard_block"


# ---------------------------------------------------------------------------
# Spend accumulator (in-memory + lazy DB sync)
# ---------------------------------------------------------------------------


class _SpendAccumulator:
    """Thread-safe counter for a single (scope, window) pair."""

    __slots__ = ("spend_usd", "_lock", "_dirty", "_last_sync")

    def __init__(self) -> None:
        self.spend_usd: float = 0.0
        self._lock = threading.Lock()
        self._dirty = False
        self._last_sync = 0.0

    def add(self, amount: float) -> None:
        with self._lock:
            self.spend_usd += amount
            self._dirty = True

    def get(self) -> float:
        with self._lock:
            return self.spend_usd

    def reset(self) -> None:
        with self._lock:
            self.spend_usd = 0.0
            self._dirty = True


# ---------------------------------------------------------------------------
# Window helpers
# ---------------------------------------------------------------------------


def _window_key(window: str) -> str:
    """Return a fixed bucket key for the current time.

    Uses wall-clock UTC so that a process restart sees the same window
    as the previous instance (the SQLite table is the source of truth).
    """
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc)
    if window == "hourly":
        return now.strftime("%Y-%m-%dT%H")
    if window == "daily":
        return now.strftime("%Y-%m-%d")
    if window == "monthly":
        return now.strftime("%Y-%m")
    return "ever"


# ---------------------------------------------------------------------------
# SQLite persistence
# ---------------------------------------------------------------------------


class _BudgetStore:
    """Lightweight SQLite backing for budget spend."""

    def __init__(self, db_path: str | None) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        if db_path:
            try:
                self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
                self._conn.execute("PRAGMA journal_mode=WAL")
                self._ensure_schema()
            except Exception:  # noqa: BLE001
                _logger.warning("[ZROKY] Budget DB unavailable: %s", db_path, exc_info=True)
                self._conn = None

    def _ensure_schema(self) -> None:
        if self._conn is None:
            return
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS budget_spend (
                scope_type TEXT NOT NULL,
                scope_id   TEXT NOT NULL,
                window_key TEXT NOT NULL,
                spend_usd  REAL DEFAULT 0.0,
                updated_at REAL DEFAULT 0.0,
                PRIMARY KEY (scope_type, scope_id, window_key)
            );
            CREATE TABLE IF NOT EXISTS budget_rules (
                scope_type TEXT NOT NULL,
                scope_id   TEXT NOT NULL,
                window     TEXT NOT NULL,
                limit_usd  REAL NOT NULL,
                action     TEXT NOT NULL,
                PRIMARY KEY (scope_type, scope_id, window)
            );
            CREATE INDEX IF NOT EXISTS idx_budget_spend_updated
                ON budget_spend(updated_at);
            """
        )
        self._conn.commit()

    # -- rules ---------------------------------------------------------------

    def load_rules(self) -> dict[str, dict[str, _BudgetRule]]:
        """Return {scope_type: {scope_id: _BudgetRule}} from DB."""
        out: dict[str, dict[str, _BudgetRule]] = {}
        if self._conn is None:
            return out
        try:
            cur = self._conn.execute(
                "SELECT scope_type, scope_id, window, limit_usd, action FROM budget_rules"
            )
            for row in cur:
                st, sid, win, limit_usd, action = row
                out.setdefault(st, {})[sid] = _BudgetRule(
                    limit_usd=float(limit_usd),
                    window=win,
                    action=action,
                )
        except Exception:  # noqa: BLE001
            _logger.warning("[ZROKY] Failed to load budget rules", exc_info=True)
        return out

    def save_rule(self, scope_type: str, scope_id: str, rule: _BudgetRule) -> None:
        if self._conn is None:
            return
        try:
            self._conn.execute(
                """INSERT INTO budget_rules (scope_type, scope_id, window, limit_usd, action)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(scope_type, scope_id, window)
                   DO UPDATE SET limit_usd=excluded.limit_usd,
                                 action=excluded.action""",
                (scope_type, scope_id, rule.window, rule.limit_usd, rule.action),
            )
            self._conn.commit()
        except Exception:  # noqa: BLE001
            _logger.warning("[ZROKY] Failed to save budget rule", exc_info=True)

    # -- spend ---------------------------------------------------------------

    def load_spend(self, scope_type: str, scope_id: str, window_key: str) -> float:
        if self._conn is None:
            return 0.0
        try:
            row = self._conn.execute(
                "SELECT spend_usd FROM budget_spend WHERE scope_type=? AND scope_id=? AND window_key=?",
                (scope_type, scope_id, window_key),
            ).fetchone()
            return float(row[0]) if row else 0.0
        except Exception:  # noqa: BLE001
            return 0.0

    def save_spend(self, scope_type: str, scope_id: str, window_key: str, spend_usd: float) -> None:
        if self._conn is None:
            return
        try:
            self._conn.execute(
                """INSERT INTO budget_spend (scope_type, scope_id, window_key, spend_usd, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(scope_type, scope_id, window_key)
                   DO UPDATE SET spend_usd=excluded.spend_usd,
                                 updated_at=excluded.updated_at""",
                (scope_type, scope_id, window_key, spend_usd, time.time()),
            )
            self._conn.commit()
        except Exception:  # noqa: BLE001
            _logger.warning("[ZROKY] Failed to save budget spend", exc_info=True)

    def cleanup_old_windows(self, keep_hours: int = 72) -> None:
        """Delete windows older than *keep_hours* to keep the table small."""
        if self._conn is None:
            return
        cutoff = time.time() - (keep_hours * 3600)
        try:
            self._conn.execute(
                "DELETE FROM budget_spend WHERE updated_at < ?",
                (cutoff,),
            )
            self._conn.commit()
        except Exception:  # noqa: BLE001
            pass

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:  # noqa: BLE001
                pass
            self._conn = None


# ---------------------------------------------------------------------------
# Budget result returned to caller
# ---------------------------------------------------------------------------


@dataclass
class BudgetCheckResult:
    action: str  # "allow", "warn", "soft_block", "hard_block"
    message: str
    estimated_cost_usd: float
    remaining_usd: float | None = None
    # window keys captured at pre-call time, passed to post-call record
    window_keys: dict[str, str] | None = None


# ---------------------------------------------------------------------------
# Main tracker
# ---------------------------------------------------------------------------


class BudgetTracker:
    """Global budget tracker with in-memory accumulators + SQLite persistence."""

    def __init__(
        self,
        *,
        db_path: str | None = None,
        default_rate_per_1m_tokens: float = 5.0,
        rules: dict[str, dict[str, dict[str, dict[str, Any]]]] | None = None,
    ) -> None:
        """
        *rules* shape:
            {"project": {"default": {"daily": {"limit_usd": 500.0, "action": "warn"}}},
             "agent":   {"research": {"hourly": {"limit_usd": 50.0, "action": "hard_block"}}}}
        """
        self._default_rate = default_rate_per_1m_tokens
        self._store = _BudgetStore(db_path)
        self._spend: dict[str, _SpendAccumulator] = {}  # key = "scope_type|scope_id|window_key"
        self._rules: dict[str, dict[str, _BudgetRule]] = {}
        self._lock = threading.Lock()

        # Load persisted rules first, then overlay explicit rules (explicit wins)
        self._rules = self._store.load_rules()
        if rules:
            for scope_type, scope_map in rules.items():
                for scope_id, windows in scope_map.items():
                    for window, spec in windows.items():
                        rule = _BudgetRule(
                            limit_usd=float(spec["limit_usd"]),
                            window=window,
                            action=spec["action"],
                        )
                        self._rules.setdefault(scope_type, {})[scope_id] = rule
                        self._store.save_rule(scope_type, scope_id, rule)

    # -- configuration -------------------------------------------------------

    def set_rule(self, scope_type: str, scope_id: str, rule: _BudgetRule) -> None:
        with self._lock:
            self._rules.setdefault(scope_type, {})[scope_id] = rule
            self._store.save_rule(scope_type, scope_id, rule)

    # -- helpers --------------------------------------------------------------

    def _accumulator(self, scope_type: str, scope_id: str, window_key: str) -> _SpendAccumulator:
        key = f"{scope_type}|{scope_id}|{window_key}"
        acc = self._spend.get(key)
        if acc is not None:
            return acc
        # Seed from DB on first access
        db_val = self._store.load_spend(scope_type, scope_id, window_key)
        acc = _SpendAccumulator()
        if db_val > 0:
            acc.spend_usd = db_val
        self._spend[key] = acc
        return acc

    def _matching_rules(
        self,
        scope_type: str,
        scope_id: str,
    ) -> list[tuple[str, _BudgetRule, str]]:
        """Return list of (resolved_scope_id, rule, window_key) that match."""
        out: list[tuple[str, _BudgetRule, str]] = []
        scope_rules = self._rules.get(scope_type, {})
        # Exact match first
        if scope_id in scope_rules:
            rule = scope_rules[scope_id]
            out.append((scope_id, rule, _window_key(rule.window)))
        # Wildcard fallback
        if "*" in scope_rules:
            rule = scope_rules["*"]
            out.append(("*", rule, _window_key(rule.window)))
        return out

    def _estimate_cost(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int = 0,
    ) -> float:
        """Return estimated USD cost for a call.

        Uses calculate_cost when model rates are known; falls back to
        default_rate_per_1m_tokens otherwise.
        """
        try:
            breakdown = calculate_cost(
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                status="success",
            )
            cost = breakdown["total_cost_usd"]
            if cost > 0:
                return cost
        except Exception:  # noqa: BLE001
            pass
        # Fallback: default rate per 1M tokens
        total_tokens = prompt_tokens + completion_tokens
        return (total_tokens * self._default_rate) / 1_000_000.0

    # -- pre-call check -------------------------------------------------------

    def check(
        self,
        *,
        project: str | None,
        agent: str | None,
        user: str | None,
        model: str,
        prompt_tokens: int,
        completion_tokens: int = 0,
    ) -> BudgetCheckResult:
        """Evaluate all matching budget rules before a call.

        Returns the most severe action among all triggered rules.
        Captures window keys so post-call ``record_spend`` uses the same
        buckets even if the wall-clock window rolled over mid-call.
        """
        estimate = self._estimate_cost(model, prompt_tokens, completion_tokens)

        scopes = [
            ("project", project or "default"),
            ("agent", agent or "default"),
            ("user", user or "default"),
        ]

        worst_action = "allow"
        worst_message = ""
        min_remaining: float | None = None
        captured_window_keys: dict[str, str] = {}

        for scope_type, scope_id in scopes:
            for resolved_id, rule, wkey in self._matching_rules(scope_type, scope_id):
                acc = self._accumulator(scope_type, resolved_id, wkey)
                spent = acc.get()
                remaining = rule.limit_usd - spent
                # Store window key for this scope so post-call uses same bucket
                captured_window_keys[f"{scope_type}|{resolved_id}"] = wkey

                if remaining < 0:
                    remaining = 0.0

                if min_remaining is None or remaining < min_remaining:
                    min_remaining = remaining

                if spent + estimate > rule.limit_usd:
                    if rule.action == "hard_block" and worst_action != "hard_block":
                        worst_action = "hard_block"
                        worst_message = (
                            f"Budget hard_block: {scope_type}/{resolved_id} "
                            f"{rule.window} limit ${rule.limit_usd:.2f} exceeded "
                            f"(spent ${spent:.4f}, estimate ${estimate:.4f})"
                        )
                    elif rule.action == "soft_block" and worst_action not in ("hard_block",):
                        worst_action = "soft_block"
                        worst_message = (
                            f"Budget soft_block: {scope_type}/{resolved_id} "
                            f"{rule.window} limit ${rule.limit_usd:.2f} exceeded"
                        )
                    elif rule.action == "warn" and worst_action not in ("hard_block", "soft_block"):
                        worst_action = "warn"
                        worst_message = (
                            f"Budget warn: {scope_type}/{resolved_id} "
                            f"{rule.window} limit ${rule.limit_usd:.2f} nearly exceeded "
                            f"(remaining ${remaining:.4f})"
                        )

        return BudgetCheckResult(
            action=worst_action,
            message=worst_message,
            estimated_cost_usd=estimate,
            remaining_usd=min_remaining,
            window_keys=captured_window_keys,
        )

    # -- post-call record -----------------------------------------------------

    def record_spend(
        self,
        *,
        project: str | None,
        agent: str | None,
        user: str | None,
        cost_usd: float,
        window_keys: dict[str, str] | None = None,
    ) -> None:
        """Add actual spend to all matching accumulators and persist to DB.

        *window_keys* should be the dict returned by ``check()`` so the
        same time bucket is used even if the call crossed a window boundary.
        """
        scopes = [
            ("project", project or "default"),
            ("agent", agent or "default"),
            ("user", user or "default"),
        ]

        for scope_type, scope_id in scopes:
            if window_keys:
                wkey = window_keys.get(f"{scope_type}|{scope_id}")
                if wkey is None:
                    # Fallback: re-compute (rare — only when no rule matched)
                    wkey = _window_key("daily")
            else:
                wkey = _window_key("daily")

            acc = self._accumulator(scope_type, scope_id, wkey)
            acc.add(cost_usd)
            self._store.save_spend(scope_type, scope_id, wkey, acc.get())

        # Periodic cleanup (cheap: every ~100 calls is fine, here every call)
        self._store.cleanup_old_windows()

    def cleanup_old_windows(self, keep_hours: int = 72) -> None:
        """Delete stale persisted spend windows from the backing store."""
        self._store.cleanup_old_windows(keep_hours)

    # -- inspection -----------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Return current spend and rule status for all active scopes."""
        out: dict[str, Any] = {}
        with self._lock:
            for scope_type, scope_map in self._rules.items():
                for scope_id, rule in scope_map.items():
                    wkey = _window_key(rule.window)
                    acc = self._accumulator(scope_type, scope_id, wkey)
                    out[f"{scope_type}/{scope_id}"] = {
                        "window": rule.window,
                        "window_key": wkey,
                        "limit_usd": rule.limit_usd,
                        "action": rule.action,
                        "spent_usd": round(acc.get(), 6),
                        "remaining_usd": round(max(0.0, rule.limit_usd - acc.get()), 6),
                    }
        return out

    def close(self) -> None:
        self._store.close()


# ---------------------------------------------------------------------------
# Convenience: build rules dict from flat spec list
# ---------------------------------------------------------------------------


def build_budget_rules(
    specs: list[dict[str, Any]],
) -> dict[str, dict[str, dict[str, dict[str, Any]]]]:
    """Convert a flat list of rule specs into the nested rules dict.

    Example spec::

        {"scope_type": "project", "scope_id": "default",
         "window": "daily", "limit_usd": 500.0, "action": "warn"}
    """
    out: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
    for spec in specs:
        st = spec["scope_type"]
        sid = spec["scope_id"]
        win = spec["window"]
        out.setdefault(st, {}).setdefault(sid, {})[win] = {
            "limit_usd": float(spec["limit_usd"]),
            "action": spec["action"],
        }
    return out
