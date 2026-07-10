"""Production canary support for the MCP interception path.

This module is deliberately narrow:

* ``/internal/mcp-canary/setup`` is provisioning-token protected and creates a
  short-lived canary tenant, API key, action contract, tool binding, and policy.
* ``/internal/mcp-canary/upstream`` is a no-side-effect synthetic MCP server.
  It is inert unless ``MCP_CANARY_UPSTREAM_ENABLED`` is true.

The goal is to prove the live inline path plus async proof/receipt worker
without touching a customer system-of-record.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.provisioning import require_owner_provisioning_access
from app.core.config import Settings, get_settings
from app.db.models import ActionContractVersion, ApiKey, McpToolBinding, Project
from app.db.session import get_db_session
from app.services.action_kernel import ActionContractConflict, register_action_contract
from app.services.pilot import upsert_policy
from app.services.security import generate_api_key_material

router = APIRouter()

CANARY_PROJECT_ID = "proj_mcp_canary"
CANARY_TOOL_NAME = "zroky_canary_adjust_inventory"
CANARY_CONTRACT_KEY = "zroky.mcp.canary.inventory_adjust"
CANARY_CONTRACT_VERSION = "1.0"
CANARY_ACTION_TYPE = "inventory_adjust"
CANARY_OPERATION_KIND = "UPDATE"


class McpCanarySetupRequest(BaseModel):
    project_id: str = Field(default=CANARY_PROJECT_ID, min_length=3, max_length=64)
    tool_name: str = Field(default=CANARY_TOOL_NAME, min_length=3, max_length=255)
    api_key_expires_in_hours: int = Field(default=24, ge=1, le=168)


class McpCanarySetupResponse(BaseModel):
    project_id: str
    tool_name: str
    contract_version: str
    api_key: str
    api_key_prefix: str
    api_key_expires_at: datetime
    mcp_upstream_path: str
    required_project_allowlist: str


@router.post("/internal/mcp-canary/setup", response_model=McpCanarySetupResponse)
def setup_mcp_canary(
    request: Request,
    body: McpCanarySetupRequest,
    _: None = Depends(require_owner_provisioning_access),
    db: Session = Depends(get_db_session),
) -> McpCanarySetupResponse:
    """Create or refresh the canary tenant config and mint a short-lived key."""
    project_id = body.project_id.strip()
    tool_name = body.tool_name.strip()
    _ensure_project(db, project_id)
    contract = _ensure_contract(db, project_id)
    _ensure_binding(db, project_id, tool_name)
    upsert_policy(
        db,
        project_id=project_id,
        payload={
            # The canary action is intentionally safe and should exercise the
            # ALLOW path, not Slack/human approval.
            "runtime_sensitive_actions_require_approval": False,
            "runtime_sensitive_tools": [],
        },
        updated_by="mcp-canary-setup",
    )
    api_key, key_prefix, key_hash = generate_api_key_material()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=body.api_key_expires_in_hours)
    db.add(
        ApiKey(
            project_id=project_id,
            name="MCP canary smoke key",
            key_prefix=key_prefix,
            key_hash=key_hash,
            scopes_json=json.dumps(["project:member"], separators=(",", ":")),
            expires_at=expires_at,
        )
    )
    db.commit()
    return McpCanarySetupResponse(
        project_id=project_id,
        tool_name=tool_name,
        contract_version=f"{contract.contract_key}/{contract.version}",
        api_key=api_key,
        api_key_prefix=key_prefix,
        api_key_expires_at=expires_at,
        mcp_upstream_path="/internal/mcp-canary/upstream",
        required_project_allowlist=project_id,
    )


@router.post("/internal/mcp-canary/upstream")
def mcp_canary_upstream(
    message: dict[str, Any],
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Tiny synthetic MCP server for production smoke tests."""
    if not settings.MCP_CANARY_UPSTREAM_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")

    request_id = message.get("id")
    method = message.get("method")
    params = message.get("params") or {}

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": [
                    {
                        "name": CANARY_TOOL_NAME,
                        "description": "No-side-effect MCP canary inventory adjustment.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "record_ref": {"type": "string"},
                                "status": {"type": "string"},
                            },
                            "required": ["record_ref", "status"],
                        },
                    }
                ]
            },
        }

    if method == "tools/call":
        name = str(params.get("name") or "")
        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        if name != CANARY_TOOL_NAME:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32602, "message": f"unknown canary tool: {name}"},
            }
        record_ref = str(arguments.get("record_ref") or "canary_1")
        observed_status = str(arguments.get("status") or "completed")
        observed = {"record_ref": record_ref, "status": observed_status}
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [{"type": "text", "text": f"canary observed {record_ref}"}],
                "isError": False,
                "_meta": {
                    "zroky": {
                        "verification": {
                            "claimed": dict(observed),
                            "actual": dict(observed),
                            "match_fields": ["record_ref", "status"],
                            "connector_type": "mcp_canary",
                            "system_ref": f"mcp-canary:{record_ref}",
                        }
                    }
                },
            },
        }

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"method not found: {method}"},
    }


def _ensure_project(db: Session, project_id: str) -> None:
    project = db.get(Project, project_id)
    if project is None:
        db.add(
            Project(
                id=project_id,
                name="MCP Production Canary",
                owner_ref="mcp-canary",
                is_active=True,
            )
        )
        db.flush()
        return
    project.name = project.name or "MCP Production Canary"
    project.is_active = True
    db.add(project)
    db.flush()


def _ensure_contract(db: Session, project_id: str) -> ActionContractVersion:
    try:
        result = register_action_contract(
            db,
            project_id=project_id,
            contract_key=CANARY_CONTRACT_KEY,
            version=CANARY_CONTRACT_VERSION,
            action_type=CANARY_ACTION_TYPE,
            operation_kind=CANARY_OPERATION_KIND,
            domain_family="mcp_canary",
            schema={
                "type": "object",
                "properties": {
                    "record_ref": {"type": "string"},
                    "status": {"type": "string"},
                },
                "required": ["record_ref", "status"],
            },
            risk_class="R2",
            verification_profile={"source": "mcp_canary"},
            connector_family="mcp_canary",
            created_by_subject="mcp-canary-setup",
        )
        return result.row
    except ActionContractConflict:
        existing = db.execute(
            select(ActionContractVersion).where(
                ActionContractVersion.project_id == project_id,
                ActionContractVersion.contract_key == CANARY_CONTRACT_KEY,
                ActionContractVersion.version == CANARY_CONTRACT_VERSION,
            )
        ).scalar_one_or_none()
        if existing is None:
            raise
        if existing.action_type != CANARY_ACTION_TYPE:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Existing canary contract has a different action_type.",
            )
        return existing


def _ensure_binding(db: Session, project_id: str, tool_name: str) -> None:
    binding = db.execute(
        select(McpToolBinding).where(
            McpToolBinding.project_id == project_id,
            McpToolBinding.tool_name == tool_name,
        )
    ).scalar_one_or_none()
    if binding is None:
        binding = McpToolBinding(project_id=project_id, tool_name=tool_name)
    binding.is_regex = False
    binding.action_type = CANARY_ACTION_TYPE
    binding.operation_kind = "update"
    binding.connector_family = "mcp_canary"
    binding.contract_key = CANARY_CONTRACT_KEY
    binding.contract_version = CANARY_CONTRACT_VERSION
    binding.fail_posture = "fail_closed"
    binding.protected = True
    binding.status = "active"
    db.add(binding)
    db.flush()
