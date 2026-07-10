"""Post-execution enqueue bridge for MCP tool calls.

This is the Slice-2 bridge from the MCP proxy into the existing verified
actions substrate. It deliberately reuses the normal tables and services:

* ``ActionExecutionAttempt`` records the MCP proxy as the executor.
* ``ActionPostExecutionJob`` lets workers verify SOR state and generate a
  signed receipt asynchronously, off the inline agent-to-SOR path.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ActionExecutionAttempt, ActionIntent
from app.services.action_kernel import canonical_json, get_action_intent, sha256_digest
from app.services.action_post_execution import enqueue_post_execution_verification
from app.services.action_runner import register_action_runner
from app.services.action_timeline import record_action_timeline_event
from app.services.protected_action_billing import METER_RUNNER_EXECUTIONS, reserve_usage_meter


MCP_RUNNER_NAME = "zroky-mcp-proxy"
MCP_RUNNER_TYPE = "managed_sandbox"
MCP_CREDENTIAL_REF = "zroky-secret://mcp/proxy"


@dataclass(frozen=True)
class McpPostExecutionResult:
    post_execution_status: str
    execution_attempt_id: str
    post_execution_job_id: str
    proof_status: str
    receipt_status: str

    def to_meta(self) -> dict[str, Any]:
        return {
            "post_execution_status": self.post_execution_status,
            "execution_attempt_id": self.execution_attempt_id,
            "post_execution_job_id": self.post_execution_job_id,
            "proof_status": self.proof_status,
            "receipt_status": self.receipt_status,
        }


class McpPostExecutionProcessor:
    """Record execution and queue verification/receipt off the inline path."""

    def __init__(self, db: Session, *, actor: str | None = "mcp-proxy") -> None:
        self._db = db
        self._actor = actor

    def process(
        self,
        *,
        project_id: str,
        intent_id: str,
        event_id: str | None,
        tool_name: str,
        arguments: dict[str, Any],
        execution_state: str,
        upstream_result: dict[str, Any] | None,
        upstream_error: str | None,
    ) -> McpPostExecutionResult:
        intent = get_action_intent(self._db, project_id=project_id, action_id=intent_id)
        runner = register_action_runner(
            self._db,
            project_id=project_id,
            name=MCP_RUNNER_NAME,
            runner_type=MCP_RUNNER_TYPE,
            environment=intent.environment,
            supported_operation_kinds=[],
            credential_scope={"default_credential_ref": MCP_CREDENTIAL_REF},
            capability_version="mcp-proxy/v1",
            registered_by_subject=self._actor,
        ).row

        attempt = self._record_execution_attempt(
            intent=intent,
            runner_id=runner.id,
            event_id=event_id,
            tool_name=tool_name,
            arguments=arguments,
            execution_state=execution_state,
            upstream_result=upstream_result,
            upstream_error=upstream_error,
        )
        job = enqueue_post_execution_verification(
            self._db,
            project_id=project_id,
            action_id=intent_id,
            attempt_id=attempt.id,
            actor=self._actor,
            payload={
                "source": "mcp_proxy",
                "mcp_event_id": event_id,
                "tool_name": tool_name,
                "execution_state": execution_state,
            },
        )
        self._db.commit()
        return McpPostExecutionResult(
            post_execution_status="queued",
            execution_attempt_id=attempt.id,
            post_execution_job_id=job.id,
            proof_status="pending",
            receipt_status="pending",
        )

    def _record_execution_attempt(
        self,
        *,
        intent: ActionIntent,
        runner_id: str,
        event_id: str | None,
        tool_name: str,
        arguments: dict[str, Any],
        execution_state: str,
        upstream_result: dict[str, Any] | None,
        upstream_error: str | None,
    ) -> ActionExecutionAttempt:
        existing = self._db.execute(
            select(ActionExecutionAttempt).where(
                ActionExecutionAttempt.project_id == intent.project_id,
                ActionExecutionAttempt.action_intent_id == intent.id,
                ActionExecutionAttempt.idempotency_key == _attempt_idempotency_key(intent.id, event_id),
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        now = datetime.now(timezone.utc)
        attempt_number = int(
            self._db.execute(
                select(func.count(ActionExecutionAttempt.id)).where(
                    ActionExecutionAttempt.project_id == intent.project_id,
                    ActionExecutionAttempt.action_intent_id == intent.id,
                )
            ).scalar_one()
            or 0
        ) + 1
        final_status = "succeeded" if execution_state == "succeeded" else "ambiguous"
        verification = _verification_hint(upstream_result)
        plan_document = {
            "action_intent_id": intent.id,
            "intent_digest": intent.intent_digest,
            "contract_version": f"{intent.contract_key}/{intent.contract_version}",
            "action_type": intent.action_type,
            "operation_kind": intent.operation_kind,
            "environment": intent.environment,
            "runner": {
                "id": runner_id,
                "type": MCP_RUNNER_TYPE,
                "environment": intent.environment,
                "capability_version": "mcp-proxy/v1",
            },
            "credential_ref": MCP_CREDENTIAL_REF,
            "execution_plan": {
                "adapter": "mcp_proxy",
                "operation": tool_name,
                "target": {"tool_name": tool_name},
                "arguments": arguments,
                "verification": verification,
            },
        }
        plan_canonical = canonical_json(plan_document)
        reserve_usage_meter(self._db, intent.project_id, METER_RUNNER_EXECUTIONS)
        row = ActionExecutionAttempt(
            project_id=intent.project_id,
            action_intent_id=intent.id,
            runner_id=runner_id,
            attempt_number=attempt_number,
            idempotency_key=_attempt_idempotency_key(intent.id, event_id),
            status=final_status,
            credential_ref=MCP_CREDENTIAL_REF,
            plan_digest=sha256_digest(plan_canonical),
            plan_json=plan_canonical,
            result_summary_json=_json_dumps(
                {
                    "source": "mcp_proxy",
                    "execution_state": execution_state,
                    "tool_name": tool_name,
                    "upstream_result": upstream_result,
                    "upstream_error": upstream_error,
                    "verification": verification,
                }
            ),
            protected_credential_returned=False,
            requested_by_subject=self._actor,
            started_at=now,
            finished_at=now,
        )
        self._db.add(row)
        self._db.flush()
        record_action_timeline_event(
            self._db,
            project_id=intent.project_id,
            action_id=intent.id,
            event_type="execution_planned",
            payload={
                "source": "mcp_proxy",
                "execution_attempt_id": row.id,
                "runner_id": runner_id,
                "attempt_number": attempt_number,
                "idempotency_key": row.idempotency_key,
                "plan_digest": row.plan_digest,
                "credential_ref": MCP_CREDENTIAL_REF,
            },
            actor=self._actor,
        )
        record_action_timeline_event(
            self._db,
            project_id=intent.project_id,
            action_id=intent.id,
            event_type=f"execution_{final_status}",
            payload={
                "source": "mcp_proxy",
                "execution_attempt_id": row.id,
                "runner_id": runner_id,
                "attempt_number": attempt_number,
                "status": final_status,
                "execution_state": execution_state,
                "error_message": upstream_error,
            },
            actor=self._actor,
        )
        return row


def _attempt_idempotency_key(intent_id: str, event_id: str | None) -> str:
    return f"mcp-execution:{intent_id}:{event_id or 'no-event'}"


def _verification_hint(result: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(result, Mapping):
        return {}
    meta = result.get("_meta")
    if not isinstance(meta, Mapping):
        return {}
    zroky = meta.get("zroky")
    if isinstance(zroky, Mapping) and isinstance(zroky.get("verification"), Mapping):
        return dict(zroky["verification"])
    if isinstance(meta.get("verification"), Mapping):
        return dict(meta["verification"])
    return {}


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True, default=str)
