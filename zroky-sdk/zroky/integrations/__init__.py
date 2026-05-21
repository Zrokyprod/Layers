# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""ZROKY SDK integrations.

Integrations are imported lazily so optional extras do not break base SDK usage.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = ["ZROKYCallbackHandler"]


def __getattr__(name: str) -> Any:
	if name == "ZROKYCallbackHandler":
		from zroky.integrations.langchain import ZROKYCallbackHandler

		return ZROKYCallbackHandler
	raise AttributeError(f"module 'zroky.integrations' has no attribute {name!r}")


if TYPE_CHECKING:
	from zroky.integrations.langchain import ZROKYCallbackHandler
