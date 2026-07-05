from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.db.models import Agent
from app.services.agent_profiles import (
    SCHEMA_VERSION,
    json_list,
)


RegistryKind = Literal["runtime_path", "verification_connector", "native_tool_family"]
ImplementationStatus = Literal["available", "template", "planned"]
LaunchTier = Literal["p0", "p1", "p2"]


ALL_LAUNCH_ACTION_TYPES = (
    "refund",
    "payment_adjustment",
    "customer_record_update",
    "ticket_close",
    "email_send",
    "deploy_change",
    "invoice_spend_approval",
    "invoice_approve",
    "journal_entry",
    "vendor_payout",
    "order_cancel",
    "inventory_adjust",
    "discount_issue",
    "sequence_enroll",
    "campaign_launch",
    "pipeline_run",
    "records_purge",
    "data_export",
    "internal_api_mutation",
    "database_record_update",
    "custom",
)


@dataclass(frozen=True)
class ToolRegistryItem:
    id: str
    kind: RegistryKind
    label: str
    description: str
    category: str
    implementation_status: ImplementationStatus
    supported_action_types: tuple[str, ...]
    launch_tier: LaunchTier = "p0"
    recommended_for_action_types: tuple[str, ...] = ()
    requires_customer_credentials: bool = False
    dashboard_href: str | None = None
    backend_capability: str | None = None
    availability_notes: str | None = None

