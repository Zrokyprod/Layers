from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.api.routes.runs import AgentRunDeclareRequest, declare_run
from app.core.limiter import limiter
from app.db.models import FinalAgentRun, FinalAssurancePack, FinalConnectorCapabilityDraft, FinalWorkflowIntent
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

    traces = _group_otlp_spans(resource_spans)
    run_ids: list[str] = []
    intents_declared = 0
    spans_observed = 0
    for trace_id, spans in traces.items():
        spans_observed += len(spans)
        run = _upsert_otlp_run(db, context=context, trace_id=trace_id, spans=spans)
        run_ids.append(run.id)
        intent_ids = []
        for item in spans:
            tool_name = _tool_name(item["attrs"])
            if not tool_name:
                continue
            pack = _pack_for_tool(db, project_id=context.tenant_id, environment=run.environment, tool_name=tool_name)
            if pack is None:
                continue
            intent, created = _create_otlp_intent(
                db,
                context=context,
                environment=run.environment,
                agent_ref=run.agent_ref,
                trace_id=trace_id,
                span=item["span"],
                attrs=item["attrs"],
            )
            intent_ids.append(intent.id)
            if created:
                intents_declared += 1
        if len(intent_ids) == 1 and run.intent_id is None:
            run.intent_id = intent_ids[0]
            db.add(run)
    db.commit()
    return {
        "accepted": True,
        "normalized_type": "run",
        "runs": len(run_ids),
        "intents_declared": intents_declared,
        "spans_observed": spans_observed,
        "count": len(run_ids),
        "ids": run_ids,
    }


def _group_otlp_spans(resource_spans: list[Any]) -> dict[str, list[dict[str, Any]]]:
    traces: dict[str, list[dict[str, Any]]] = {}
    for resource_span in resource_spans:
        if not isinstance(resource_span, dict):
            continue
        resource_attrs = _attrs((resource_span.get("resource") or {}).get("attributes"))
        for scope_span in resource_span.get("scopeSpans", []):
            if not isinstance(scope_span, dict):
                continue
            for span in scope_span.get("spans", []):
                if not isinstance(span, dict):
                    continue
                attrs = {**resource_attrs, **_attrs(span.get("attributes"))}
                trace_id = str(span.get("traceId") or attrs.get("trace_id") or "").strip()
                if trace_id:
                    traces.setdefault(trace_id, []).append({"span": span, "attrs": attrs})
    return traces


def _upsert_otlp_run(
    db: Session,
    *,
    context: TenantContext,
    trace_id: str,
    spans: list[dict[str, Any]],
) -> FinalAgentRun:
    root = next((item for item in spans if not str(item["span"].get("parentSpanId") or "").strip()), None)
    source = root or spans[0]
    attrs = source["attrs"]
    span = source["span"]
    environment = _first_text(attrs, "zroky.environment", "deployment.environment.name", "deployment.environment") or "production"
    run_payload = {
        "trace_id": trace_id,
        "root_span_id": root["span"].get("spanId") if root else None,
        "spans": [item["span"] for item in spans],
    }
    row = db.execute(
        select(FinalAgentRun).where(
            FinalAgentRun.project_id == context.tenant_id,
            FinalAgentRun.idempotency_key == f"otlp:{trace_id}",
        )
    ).scalar_one_or_none()
    if row is None:
        row = FinalAgentRun(
            project_id=context.tenant_id,
            environment=environment,
            idempotency_key=f"otlp:{trace_id}",
            external_run_id=trace_id,
            workflow_key=_workflow_key(attrs, span if root else None),
            agent_ref=_agent_ref(attrs),
        )
    row.environment = environment
    row.status = _run_status(root["span"] if root else None)
    row.run_json = json.dumps(run_payload, sort_keys=True, separators=(",", ":"))
    row.run_digest = _digest_json(run_payload)
    row.started_at = _otlp_time(span.get("startTimeUnixNano")) or row.started_at
    row.finished_at = _otlp_time(span.get("endTimeUnixNano")) if root else None
    if root:
        row.workflow_key = _workflow_key(attrs, span)
        row.agent_ref = _agent_ref(attrs)
    db.add(row)
    db.flush()
    return row


def _create_otlp_intent(
    db: Session,
    *,
    context: TenantContext,
    environment: str,
    agent_ref: str | None,
    trace_id: str,
    span: dict[str, Any],
    attrs: dict[str, Any],
) -> tuple[FinalWorkflowIntent, bool]:
    span_id = str(span.get("spanId") or "").strip()
    key = f"otlp:{trace_id}:{span_id}"
    intent = _tool_arguments(attrs.get("gen_ai.tool.call.arguments"))
    digest = _digest_json(intent)
    existing = db.execute(
        select(FinalWorkflowIntent).where(
            FinalWorkflowIntent.project_id == context.tenant_id,
            FinalWorkflowIntent.idempotency_key == key,
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.intent_digest != digest:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="OTLP tool-call intent conflicts with an existing span.")
        return existing, False
    row = FinalWorkflowIntent(
        project_id=context.tenant_id,
        environment=environment,
        idempotency_key=key,
        agent_ref=agent_ref,
        intent_digest=digest,
        intent_json=json.dumps(intent, sort_keys=True, separators=(",", ":")),
    )
    db.add(row)
    db.flush()
    return row, True


def _pack_for_tool(
    db: Session,
    *,
    project_id: str,
    environment: str,
    tool_name: str,
) -> FinalAssurancePack | None:
    rows = db.execute(
        select(FinalAssurancePack).where(
            FinalAssurancePack.project_id == project_id,
            FinalAssurancePack.environment == environment,
            FinalAssurancePack.status == "active",
        )
    ).scalars()
    for row in rows:
        try:
            pack = json.loads(row.pack_json)
        except Exception:
            continue
        if tool_name in (pack.get("tool_bindings") or []):
            return row
    return None


def _tool_name(attrs: dict[str, Any]) -> str | None:
    name = str(attrs.get("gen_ai.tool.name") or "").strip()
    if name:
        return name
    if str(attrs.get("gen_ai.operation.name") or "").strip() == "execute_tool":
        return str(attrs.get("gen_ai.tool.name") or "").strip() or None
    return None


def _tool_arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value in (None, ""):
        return {}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {"raw": value}
        return parsed if isinstance(parsed, dict) else {"raw": value}
    return {"raw": value}


def _workflow_key(attrs: dict[str, Any], root_span: dict[str, Any] | None) -> str:
    return _first_text(attrs, "zroky.workflow.name") or str((root_span or {}).get("name") or "otel-trace").strip() or "otel-trace"


def _agent_ref(attrs: dict[str, Any]) -> str:
    return _first_text(attrs, "zroky.agent.name", "gen_ai.agent.name", "gen_ai.agent.id", "service.name") or "otel-agent"


def _run_status(root_span: dict[str, Any] | None) -> str:
    if root_span is None:
        return "running"
    code = (root_span.get("status") or {}).get("code") if isinstance(root_span.get("status"), dict) else None
    if code in {"STATUS_CODE_ERROR", 2, "2"}:
        return "failed"
    return "succeeded" if root_span.get("endTimeUnixNano") else "running"


def _first_text(attrs: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = attrs.get(key)
        if value not in (None, "", [], {}):
            return str(value).strip().lower() if key.startswith("deployment.environment") or key == "zroky.environment" else str(value).strip()
    return None


def _otlp_time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1_000_000_000, timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


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
