from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import ROLE_RANK
from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.api.routes._action_intents_helpers import _intent_response
from app.api.routes._action_intents_schemas import (
    ActionIntentCreateRequest,
    ActionIntentDecisionResponse,
)
from app.api.routes.outcome_reconciliation_helpers import _map_protected_action_billing_error
from app.core.limiter import limiter
from app.db.session import get_db_session
from app.services.action_kernel import (
    ActionContractNotFound,
    ActionIntentConflict,
    ActionKernelError,
    create_action_intent,
    decide_action_intent,
)
from app.services.notification_dispatch import dispatch_runtime_policy_approval_slack_request
from app.services.outcome_mismatch_response import get_mismatch_response, link_corrective_action
from app.services.protected_action_billing import (
    ProtectedActionMeteringUnavailable,
    ProtectedActionQuotaExceeded,
)


router = APIRouter()
logger = logging.getLogger(__name__)


def _require_member(context: TenantContext) -> None:
    if ROLE_RANK[context.role] < ROLE_RANK["member"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant role 'member' is required for corrective actions.",
        )


@router.post(
    "/reconciliation/mismatch-responses/{response_id}/corrective-action",
    response_model=ActionIntentDecisionResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("30/minute")
def create_mismatch_corrective_action(
    request: Request,
    response_id: str,
    body: ActionIntentCreateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ActionIntentDecisionResponse:
    _require_member(context)
    response = get_mismatch_response(db, project_id=context.tenant_id, response_id=response_id)
    if response is None:
        raise HTTPException(status_code=404, detail="Mismatch response case not found.")
    if response.status == "RESOLVED":
        raise HTTPException(status_code=409, detail="Resolved mismatch cases cannot create corrective actions.")
    if not idempotency_key or not idempotency_key.strip():
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required.")

    actor = context.subject or "dashboard-operator"
    purpose = {
        **body.purpose,
        "kind": "outcome_mismatch_correction",
        "mismatch_response_id": response.id,
        "reconciliation_check_id": response.reconciliation_check_id,
        "original_action_intent_id": response.action_intent_id,
    }
    try:
        created = create_action_intent(
            db,
            project_id=context.tenant_id,
            agent_id=None,
            contract_version=body.contract_version,
            action_type=body.action_type,
            operation_kind=body.operation_kind,
            environment=body.environment,
            idempotency_key=idempotency_key.strip(),
            principal={"id": actor, "type": "human_operator"},
            actor_chain=[{"id": actor, "type": "human_operator"}],
            purpose=purpose,
            resource=body.resource,
            parameters=body.parameters,
            execution_request=body.execution_request,
            verification_profile=body.verification_profile,
            deadline_at=body.deadline,
            trace_context={
                **(body.trace_context or {}),
                "source": "outcomes_dashboard",
                "mismatch_response_id": response.id,
            },
        )
        decision = decide_action_intent(
            db,
            project_id=context.tenant_id,
            action_id=created.row.id,
            actor=actor,
        )
        link_corrective_action(
            db,
            response=response,
            corrective_action_intent_id=created.row.id,
            decision_status=decision.row.status,
            actor=actor,
        )
    except (ProtectedActionQuotaExceeded, ProtectedActionMeteringUnavailable) as exc:
        raise _map_protected_action_billing_error(exc) from exc
    except ActionContractNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ActionIntentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ActionKernelError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if decision.requires_approval and decision.runtime_result is not None:
        try:
            dispatch_runtime_policy_approval_slack_request(
                db,
                tenant_id=context.tenant_id,
                decision=decision.runtime_result.decision,
            )
        except Exception:
            logger.debug("outcomes.corrective_action_slack_dispatch_failed", exc_info=True)
    db.commit()
    return ActionIntentDecisionResponse(
        **_intent_response(db, decision.row).model_dump(),
        allowed=decision.allowed,
        requires_approval=decision.requires_approval,
        reasons=decision.reasons,
    )
