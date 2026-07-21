"""Zroky MCP-native interception layer (Gap 1: distribution).

Zroky sits as an MCP proxy between an agent's MCP client and the real
MCP tool servers it calls. Every ``tools/call`` passes through the
interception :func:`app.mcp.gate.evaluate` gate, which classifies the
tool into a Zroky action contract and runs it through the *existing*
runtime-policy kernel before the call is allowed to reach the upstream
system of record.

Design altitude: this package owns ONLY the MCP protocol surface and the
tool→contract classification. All policy, verification, and receipt logic
is reused from ``app.services.action_kernel`` / ``runtime_policy`` /
``action_receipts`` — the gate never re-implements a decision.

Prod safety: the FastAPI proxy router is mounted only when
``Settings.MCP_INTERCEPTION_ENABLED`` is true (default False), so shipping
this module changes no existing request path.
"""
from __future__ import annotations

from app.mcp.gate import GateDecision, GateOutcome, McpSession, evaluate
from app.mcp.tool_binding import (
    ActionClassification,
    ToolBinding,
    classify_tool,
)

__all__ = [
    "ActionClassification",
    "ToolBinding",
    "classify_tool",
    "GateDecision",
    "GateOutcome",
    "McpSession",
    "evaluate",
]
