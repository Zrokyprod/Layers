# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""
Public exception types for the Zroky SDK.

Kept in a separate module so every submodule can import them
without creating circular dependencies with zroky.__init__.
"""
from __future__ import annotations

from typing import Any

from zroky._internal.models import ErrorCode


class ZrokyPreflightError(RuntimeError):
    """Raised when configured preflight blocking warnings are present."""

    def __init__(self, warnings: list[dict[str, Any]]) -> None:
        self.warnings = warnings
        self.warning_types = [
            str(warning.get("type", "UNKNOWN")).strip().upper()
            for warning in warnings
        ]
        self.error_code = self._error_code_from_warning_types(self.warning_types)
        warning_types = ", ".join(
            warning_type or "UNKNOWN" for warning_type in self.warning_types
        )
        super().__init__(
            "[ZROKY] Preflight blocked provider call due to: "
            f"{warning_types or 'UNKNOWN'}"
        )

    @staticmethod
    def _error_code_from_warning_types(warning_types: list[str]) -> str:
        if "AUTH_RISK" in warning_types:
            return ErrorCode.AUTH_FAILURE
        if "TOKEN_OVERFLOW" in warning_types:
            return ErrorCode.TOKEN_OVERFLOW
        if "RATE_LIMIT_RISK" in warning_types:
            return ErrorCode.RATE_LIMIT
        return ErrorCode.UNKNOWN_ERROR


class ZrokyRuntimePolicyError(RuntimeError):
    """Raised when the runtime policy gate cannot produce an allow decision."""

    def __init__(self, message: str, *, decision: dict[str, Any] | None = None) -> None:
        self.decision = decision or {}
        super().__init__(message)


class ZrokyOutcomeVerificationError(RuntimeError):
    """Raised when saved connector outcome verification cannot complete."""


class ZrokyVerifiedActionError(RuntimeError):
    """Raised when a backend-owned verified action cannot make safe progress."""

    def __init__(
        self,
        message: str,
        *,
        action: dict[str, Any] | None = None,
        decision: dict[str, Any] | None = None,
    ) -> None:
        self.action = action or {}
        self.decision = decision or {}
        super().__init__(message)


class ZrokyVerifiedActionBlocked(ZrokyVerifiedActionError):
    """Raised when a verified action is denied, expired, or otherwise blocked."""


class ZrokyVerifiedActionApprovalRequired(ZrokyVerifiedActionBlocked):
    """Raised when a verified action is paused for human approval."""

    def __init__(
        self,
        message: str,
        *,
        action: dict[str, Any],
        decision: dict[str, Any],
    ) -> None:
        super().__init__(message, action=action, decision=decision)
        self.action_id = self._action_id_from(action, decision)
        self.approval_id = self._approval_id_from(decision)

    @staticmethod
    def _action_id_from(action: dict[str, Any], decision: dict[str, Any]) -> str | None:
        value = action.get("action_id") or decision.get("action_id")
        return str(value) if value else None

    @staticmethod
    def _approval_id_from(decision: dict[str, Any]) -> str | None:
        value = decision.get("runtime_policy_decision_id") or decision.get("id")
        if value:
            return str(value)
        queue_item = decision.get("approval_queue_item")
        if isinstance(queue_item, dict) and queue_item.get("id"):
            return str(queue_item["id"])
        return None


class ZrokyRuntimePolicyBlocked(ZrokyRuntimePolicyError):
    """Raised when the runtime policy gate blocks or pauses an agent action."""


class ZrokyRuntimePolicyApprovalRequired(ZrokyRuntimePolicyBlocked):
    """Raised when the runtime policy gate pauses an action for approval."""

    def __init__(self, message: str, *, decision: dict[str, Any]) -> None:
        super().__init__(message, decision=decision)
        self.approval_id = self._approval_id_from(decision)
        self.expires_at = self._expires_at_from(decision)

    @staticmethod
    def _approval_id_from(decision: dict[str, Any]) -> str | None:
        queue_item = decision.get("approval_queue_item")
        if isinstance(queue_item, dict) and queue_item.get("id"):
            return str(queue_item["id"])
        if decision.get("id"):
            return str(decision["id"])
        return None

    @staticmethod
    def _expires_at_from(decision: dict[str, Any]) -> str | None:
        value = decision.get("expires_at")
        if value is not None:
            return str(value)
        queue_item = decision.get("approval_queue_item")
        if isinstance(queue_item, dict) and queue_item.get("expires_at") is not None:
            return str(queue_item["expires_at"])
        return None
