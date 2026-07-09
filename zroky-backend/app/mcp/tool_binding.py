"""Tool → action-contract classification (inverse of the tool registry).

``app.services._tool_registry_native`` maps a Zroky *native tool* to the
``supported_action_types`` it can perform. Interception needs the INVERSE:
given an arbitrary MCP tool name coming off the wire (chosen by whatever
upstream MCP server the agent talks to), decide which Zroky action type /
operation kind / connector family it corresponds to, and whether that
action is *protected* (must go through the policy gate) or unprotected
(observe-only passthrough).

Resolution order (first hit wins):
  1. Exact binding   — an operator-configured ``ToolBinding`` whose
                       ``match`` equals the tool name (case-insensitive).
  2. Pattern binding — a ``ToolBinding`` whose regex ``match`` matches.
  3. Heuristic       — verb/noun keywords in the tool name.
  4. Unclassified    — protected=False, so unknown tools are NEVER blocked
                       (fail-open at the classification layer; a read or an
                       unmapped tool must not break the agent).

Only actions whose resolved ``action_type`` is in
:data:`PROTECTED_ACTION_TYPES` are gated. Everything else is observe-only.
Operators extend coverage by adding bindings, not by editing code.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


# Action types that MUST pass through the runtime-policy gate. Seeded from
# the native tool registry's ``supported_action_types`` plus the broader
# access/identity/data verbs the action kernel already understands.
PROTECTED_ACTION_TYPES: frozenset[str] = frozenset(
    {
        # money
        "refund",
        "payment_adjustment",
        "vendor_payout",
        "invoice_spend_approval",
        "credit_issue",
        "coupon_issue",
        # commerce
        "order_cancel",
        "inventory_adjust",
        "discount_issue",
        # crm / customer state
        "customer_record_update",
        "account_status_change",
        "subscription_cancel",
        "subscription_pause",
        "subscription_reactivate",
        # identity / access (highest risk)
        "access_grant",
        "access_revoke",
        "identity_change",
        # data egress
        "data_export",
        "customer_bulk_read",
        # comms / support
        "email_send",
        "ticket_close",
    }
)

_UNCLASSIFIED = "unclassified"


@dataclass(frozen=True)
class ActionClassification:
    """The Zroky-side meaning of an incoming MCP tool call."""

    action_type: str
    operation_kind: str  # create | update | delete | read | custom
    connector_family: str  # money | commerce | crm | identity | support | postgres | unknown
    protected: bool
    binding_source: str  # exact | pattern | heuristic | unclassified
    # Populated only from a durable project binding — lets the kernel adapter
    # gate against an EXACT contract (no "latest active" ambiguity) and lets
    # the proxy override the default fail posture.
    contract_key: str | None = None
    contract_version: str | None = None
    fail_posture: str | None = None  # 'fail_open' | 'fail_closed' | None


@dataclass(frozen=True)
class ToolBinding:
    """Operator-declared mapping from an MCP tool name to a Zroky action.

    ``match`` is compared case-insensitively; when ``is_regex`` it is used
    as a ``re.search`` pattern, otherwise as an exact equality test.

    A durable (DB-backed) binding may pin an exact contract and/or force the
    protected flag and fail posture; the in-code default bindings leave those
    None and fall back to :data:`PROTECTED_ACTION_TYPES` membership.
    """

    match: str
    action_type: str
    operation_kind: str = "custom"
    connector_family: str = "unknown"
    is_regex: bool = False
    contract_key: str | None = None
    contract_version: str | None = None
    fail_posture: str | None = None
    protected_override: bool | None = None


# Default heuristics — keyword → (action_type, operation_kind, connector_family).
# Deliberately small and boring; real deployments override with exact bindings.
_KEYWORD_RULES: tuple[tuple[str, str, str, str], ...] = (
    ("refund", "refund", "create", "money"),
    ("payout", "vendor_payout", "create", "money"),
    ("credit", "credit_issue", "create", "money"),
    ("coupon", "coupon_issue", "create", "money"),
    ("discount", "discount_issue", "create", "commerce"),
    ("cancel_order", "order_cancel", "update", "commerce"),
    ("order_cancel", "order_cancel", "update", "commerce"),
    ("inventory", "inventory_adjust", "update", "commerce"),
    ("subscription_cancel", "subscription_cancel", "update", "crm"),
    ("grant", "access_grant", "create", "identity"),
    ("revoke", "access_revoke", "delete", "identity"),
    ("role", "access_grant", "update", "identity"),
    ("permission", "access_grant", "update", "identity"),
    ("email_change", "identity_change", "update", "identity"),
    ("phone_change", "identity_change", "update", "identity"),
    ("export", "data_export", "read", "postgres"),
    ("send_email", "email_send", "create", "support"),
    ("send_message", "email_send", "create", "support"),
    ("close_ticket", "ticket_close", "update", "support"),
    ("update_customer", "customer_record_update", "update", "crm"),
    ("customer_update", "customer_record_update", "update", "crm"),
)

# Verb prefixes for operation_kind inference when no rule matched.
_VERB_KINDS: tuple[tuple[str, str], ...] = (
    ("create", "create"),
    ("add", "create"),
    ("issue", "create"),
    ("update", "update"),
    ("set", "update"),
    ("patch", "update"),
    ("change", "update"),
    ("delete", "delete"),
    ("remove", "delete"),
    ("revoke", "delete"),
    ("get", "read"),
    ("list", "read"),
    ("read", "read"),
    ("fetch", "read"),
    ("search", "read"),
)


def _normalize(tool_name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", tool_name.strip().lower()).strip("_")


def _infer_operation_kind(name: str) -> str:
    for verb, kind in _VERB_KINDS:
        if name.startswith(verb) or f"_{verb}" in name:
            return kind
    return "custom"


def classify_tool(
    tool_name: str,
    arguments: dict | None = None,  # reserved: arg-shape signals (e.g. amount>0)
    bindings: list[ToolBinding] | None = None,
) -> ActionClassification:
    """Resolve an incoming MCP tool name to an :class:`ActionClassification`."""
    raw = tool_name or ""
    name = _normalize(raw)
    bindings = bindings or []

    # 1. exact binding
    for b in bindings:
        if not b.is_regex and _normalize(b.match) == name:
            return _from_binding(b, "exact")

    # 2. pattern binding
    for b in bindings:
        if b.is_regex and re.search(b.match, raw, flags=re.IGNORECASE):
            return _from_binding(b, "pattern")

    # 3. heuristic keyword rules
    for keyword, action_type, op_kind, family in _KEYWORD_RULES:
        if keyword in name:
            return _finalize(action_type, op_kind, family, "heuristic")

    # 4. unclassified — never protected, never blocks the agent
    return ActionClassification(
        action_type=_UNCLASSIFIED,
        operation_kind=_infer_operation_kind(name),
        connector_family="unknown",
        protected=False,
        binding_source="unclassified",
    )


def _finalize(
    action_type: str, operation_kind: str, connector_family: str, source: str
) -> ActionClassification:
    return ActionClassification(
        action_type=action_type,
        operation_kind=operation_kind,
        connector_family=connector_family,
        protected=action_type in PROTECTED_ACTION_TYPES,
        binding_source=source,
    )


def _from_binding(b: ToolBinding, source: str) -> ActionClassification:
    protected = b.protected_override if b.protected_override is not None else (
        b.action_type in PROTECTED_ACTION_TYPES
    )
    return ActionClassification(
        action_type=b.action_type,
        operation_kind=b.operation_kind,
        connector_family=b.connector_family,
        protected=protected,
        binding_source=source,
        contract_key=b.contract_key,
        contract_version=b.contract_version,
        fail_posture=b.fail_posture,
    )
