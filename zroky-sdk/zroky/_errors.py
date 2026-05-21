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
