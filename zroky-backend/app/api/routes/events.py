from __future__ import annotations

from typing import Any
import hashlib
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.api.routes.runs import AgentRunDeclareRequest, declare_run
from app.core.limiter import limiter
from app.db.models import FinalConnectorCapabilityDraft
from app.db.session import get_db_session


router = APIRouter(prefix="/v1/events")


class CloudEventIn(BaseModel):
    specversion: str
    id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    type: str = Field(min_length=1)
    subject: str | None = None
    time: str | None = None
    datacontenttype: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class McpToolIn(BaseModel):
    name: str
    description: str | None = None
    inputSchema: dict[str, Any] = Field(default_factory=dict)


class McpImportIn(BaseModel):
    environment: str = "production"
    source_ref: str | None = None
    tools: list[McpToolIn]


class A2AAgentCardIn(BaseModel):
    environment: str = "production"
    source_ref: str | None = None
    card: dict[str, Any]


def _digest_json(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _capability_draft(
    *,
    db: Session,
    project_id: str,
    environment: str,
    source_kind: str,
    source_ref: str | None,
    capability_key: str,
    schema: dict[str, Any],
) -> FinalConnectorCapabilityDraft:
    existing = db.execute(
        select(FinalConnectorCapabilityDraft).where(
            FinalConnectorCapabilityDraft.project_id == project_id,
            FinalConnectorCapabilityDraft.environment == environment,
            FinalConnectorCapabilityDraft.source_kind == source_kind,
            FinalConnectorCapabilityDraft.capability_key == capability_key,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    row = FinalConnectorCapabilityDraft(
        project_id=project_id,
        environment=environment,
        source_kind=source_kind,
        source_ref=source_ref,
        capability_key=capability_key,
        schema_digest=_digest_json(schema),
        schema_json=json.dumps(schema, sort_keys=True, separators=(",", ":")),
    )
    db.add(row)
    db.flush()
    return row


def _draft_response(row: FinalConnectorCapabilityDraft) -> dict[str, Any]:
    return {
        "id": row.id,
        "capability_key": row.capability_key,
        "trust_status": row.trust_status,
        "trusted_for_recovery": row.trusted_for_recovery,
    }


def _attrs(items: list[dict[str, Any]] | None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in items or []:
        key = item.get("key")
        value = item.get("value")
        if isinstance(key, str) and isinstance(value, dict):
            result[key] = next(iter(value.values()), None)
    return result


@router.post("/cloudevents", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("120/minute")
def ingest_cloudevent(
    request: Request,
    event: CloudEventIn,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    if event.specversion != "1.0":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Only CloudEvents specversion 1.0 is supported.")

    key = idempotency_key or event.id
    if event.type == "com.zroky.run.declared":
        body = AgentRunDeclareRequest(**event.data)
        run = declare_run(request, body, key, context, db)
        return {"accepted": True, "normalized_type": "run", "id": run.id}

    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Unsupported CloudEvent type: {event.type}.")


@router.post("/otlp/v1/traces", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("120/minute")
def ingest_otlp_traces(
    request: Request,
    payload: dict[str, Any],
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    resource_spans = payload.get("resourceSpans")
    if not isinstance(resource_spans, list):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="OTLP JSON payload must include resourceSpans.")

    created: list[str] = []
    for resource_span in resource_spans:
        resource_attrs = _attrs((resource_span.get("resource") or {}).get("attributes") if isinstance(resource_span, dict) else None)
        for scope_span in resource_span.get("scopeSpans", []) if isinstance(resource_span, dict) else []:
            for span in scope_span.get("spans", []) if isinstance(scope_span, dict) else []:
                attrs = {**resource_attrs, **_attrs(span.get("attributes"))}
                trace_id = str(span.get("traceId") or attrs.get("trace_id") or "").strip()
                span_id = str(span.get("spanId") or "").strip()
                if not trace_id:
                    continue
                run = declare_run(
                    request,
                    AgentRunDeclareRequest(
                        environment=str(attrs.get("deployment.environment") or "production"),
                        external_run_id=trace_id,
                        workflow_key=str(attrs.get("zroky.workflow.name") or attrs.get("zroky.workflow.id") or "otel-trace"),
                        agent_ref=str(attrs.get("zroky.agent.name") or attrs.get("service.name") or "otel-agent"),
                        status="running",
                        run={"trace_id": trace_id, "span_id": span_id, "otel": span},
                    ),
                    f"otlp:{trace_id}:{span_id}",
                    context,
                    db,
                )
                created.append(run.id)

    return {"accepted": True, "normalized_type": "run", "count": len(created), "ids": created}


@router.post("/mcp/tools/import", status_code=status.HTTP_201_CREATED)
@limiter.limit("60/minute")
def import_mcp_tools(
    request: Request,
    body: McpImportIn,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    imported: list[dict[str, Any]] = []
    environment = body.environment.strip().lower() or "production"
    for tool in body.tools:
        schema = {"name": tool.name, "description": tool.description, "inputSchema": tool.inputSchema}
        imported.append(_draft_response(_capability_draft(
            db=db,
            project_id=context.tenant_id,
            environment=environment,
            source_kind="mcp",
            source_ref=body.source_ref,
            capability_key=tool.name,
            schema=schema,
        )))
    db.commit()
    return {"imported": imported}


@router.post("/a2a/agent-card/import", status_code=status.HTTP_201_CREATED)
@limiter.limit("60/minute")
def import_a2a_agent_card(
    request: Request,
    body: A2AAgentCardIn,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    card = body.card
    environment = body.environment.strip().lower() or "production"
    agent_name = str(card.get("name") or card.get("id") or "a2a-agent").strip()
    skills = card.get("skills") if isinstance(card.get("skills"), list) else []
    capabilities = card.get("capabilities") if isinstance(card.get("capabilities"), list) else []
    entries = skills or capabilities or [{"name": agent_name, "description": card.get("description")}]

    imported = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("id") or entry.get("name") or entry.get("type") or "").strip()
        if not key:
            continue
        schema = {"agent": agent_name, "card": card, "capability": entry}
        imported.append(
            _draft_response(_capability_draft(
                db=db,
                project_id=context.tenant_id,
                environment=environment,
                source_kind="a2a",
                source_ref=body.source_ref,
                capability_key=key,
                schema=schema,
            ))
        )
    db.commit()
    return {"imported": imported}
