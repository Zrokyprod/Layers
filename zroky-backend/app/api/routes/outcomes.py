"""Cost-of-Failure Attribution API — outcome ingest + attribution reads + webhooks.

Surface:
  POST /v1/outcomes                      — ingest (SDK + direct)
  GET  /v1/outcomes/summary              — KPI strip: total cost, by-type, by-cluster
  GET  /v1/outcomes/by-call/{call_id}    — outcome events for a specific call
  GET  /v1/outcomes/replay/{run_id}      — prevented savings for a replay run
  POST /v1/outcomes/webhooks/zendesk     — Zendesk ticket.created / ticket.updated
  POST /v1/outcomes/webhooks/salesforce  — Salesforce Opportunity stage-change
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import ROLE_RANK
from app.api.dependencies.tenant import TenantContext, require_tenant_context, require_tenant_id
from app.api.routes.outcome_serializers import (
    _serialize_outcome,
    _serialize_reconciliation,
    _serialize_source_mutation,
    _serialize_summary,
)
from app.api.routes.outcome_reconciliation_helpers import (
    _claim_text,
    _customer_id,
    _customer_record_idempotency_key,
    _customer_record_match_fields,
    _ledger_refund_idempotency_key,
    _ledger_refund_match_fields,
    _map_protected_action_billing_error,
    _optional_float,
    _postgres_read_idempotency_key,
    _postgres_read_match_fields,
    _refund_id,
)
from app.api.routes.outcome_saved_reconciliation import (
    _bridge_metadata,
    _bridge_netsuite_record_type,
    _bridge_record_ref,
    _bridge_salesforce_object_type,
    _bridge_zoho_module_name,
    _create_saved_customer_record_reconciliation,
    _create_saved_generic_rest_reconciliation,
    _create_saved_hubspot_crm_reconciliation,
    _create_saved_jira_issue_reconciliation,
    _create_saved_ledger_refund_reconciliation,
    _create_saved_netsuite_finance_reconciliation,
    _create_saved_postgres_read_reconciliation,
    _create_saved_razorpay_refund_reconciliation,
    _create_saved_salesforce_crm_reconciliation,
    _create_saved_stripe_refund_reconciliation,
    _create_saved_zendesk_ticket_reconciliation,
    _create_saved_zoho_crm_reconciliation,
)
from app.schemas.outcomes import (
    CustomerRecordReconciliationIngest,
    LedgerRefundReconciliationIngest,
    OutcomeIngest,
    OutcomeReconciliationIngest,
    OutcomeReconciliationListResponse,
    OutcomeReconciliationSummaryResponse,
    OutcomeReconciliationView,
    OutcomeMismatchResolveRequest,
    OutcomeMismatchResponseListResponse,
    OutcomeMismatchResponseView,
    OutcomeTypeView,
    OutcomeView,
    PostgresReadReconciliationIngest,
    ReplaySavingsResponse,
    SavedConnectorReconciliationIngest,
    SavedCustomerRecordReconciliationIngest,
    SavedGenericRestReconciliationIngest,
    SavedLedgerRefundReconciliationIngest,
    SavedPostgresReadReconciliationIngest,
    SourceMutationIngest,
    SourceMutationListResponse,
    SourceMutationSummaryResponse,
    SourceMutationView,
    SummaryResponse,
)
from app.core.config import get_settings
from app.core.limiter import limiter
from app.db.session import get_db_session
from app.services.outcome_attribution import (
    KNOWN_OUTCOME_TYPES,
    AttributionClusterRow,
    CallOutcomeView,
    OutcomeTypeRow,
    get_attribution_summary,
    get_call_outcomes,
    get_replay_prevented_savings,
    ingest_outcome,
    normalise_salesforce_event,
    normalise_zendesk_ticket,
)
from app.services.outcome_reconciliation import (
    ApiRecordConnector,
    VALID_VERDICTS,
    get_reconciliation,
    get_reconciliation_summary,
    list_reconciliations,
    reconcile_outcome,
)
from app.services.outcome_mismatch_response import (
    acknowledge_mismatch_response,
    get_mismatch_response,
    list_mismatch_responses,
    mismatch_response_to_dict,
    resolve_mismatch_response,
)
from app.services.protected_action_billing import (
    ProtectedActionMeteringUnavailable,
    ProtectedActionQuotaExceeded,
)
from app.services.system_of_record_connectors import (
    ConnectorConfigError,
)
from app.services.system_of_record_connector_config import (
    CUSTOMER_RECORD_CONNECTOR_TYPE,
    GENERIC_REST_CONNECTOR_TYPE,
    HUBSPOT_CRM_CONNECTOR_TYPE,
    JIRA_ISSUE_CONNECTOR_TYPE,
    LEDGER_REFUND_CONNECTOR_TYPE,
    NETSUITE_FINANCE_CONNECTOR_TYPE,
    POSTGRES_READ_CONNECTOR_TYPE,
    RAZORPAY_REFUND_CONNECTOR_TYPE,
    SALESFORCE_CRM_CONNECTOR_TYPE,
    STRIPE_REFUND_CONNECTOR_TYPE,
    ZENDESK_TICKET_CONNECTOR_TYPE,
    ZOHO_CRM_CONNECTOR_TYPE,
    build_inline_customer_record_connector,
    build_inline_ledger_refund_connector,
    build_inline_postgres_read_connector,
)
from app.services.source_mutations import (
    ingest_source_mutation,
    list_source_mutations,
    source_mutation_summary,
)
router = APIRouter(prefix="/v1/outcomes", tags=["outcomes"])
logger = logging.getLogger(__name__)


def _require_mismatch_role(context: TenantContext, minimum_role: str) -> None:
    if ROLE_RANK[context.role] < ROLE_RANK[minimum_role]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Tenant role '{minimum_role}' is required for this mismatch response action.",
        )



# -- Routes -------------------------------------------------------------------

# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("", response_model=OutcomeView, status_code=201)
@limiter.limit("120/minute")
def create_outcome(
    request: Request,
    body: OutcomeIngest = Body(...),
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> OutcomeView:
    """Ingest one business-outcome event and attribute it to a call."""
    evt = ingest_outcome(
        db,
        project_id=tenant_id,
        call_id=body.call_id,
        outcome_type=body.outcome_type,
        amount_usd=body.amount_usd,
        source="api",
        external_ref=body.external_ref,
        idempotency_key=body.idempotency_key,
        occurred_at=body.occurred_at,
        metadata=body.metadata,
    )
    return _serialize_outcome(evt)


@router.get("/summary", response_model=SummaryResponse)
@limiter.limit("30/minute")
def get_summary(
    request: Request,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
    days: int = Query(default=30, ge=1, le=365),
) -> SummaryResponse:
    """Attribution summary: total cost + by-type + by-cluster (agent × detector)."""
    s = get_attribution_summary(db, project_id=tenant_id, days=days)
    return _serialize_summary(s)


@router.post(
    "/reconciliation", response_model=OutcomeReconciliationView, status_code=201
)
@limiter.limit("120/minute")
def create_reconciliation(
    request: Request,
    body: OutcomeReconciliationIngest = Body(...),
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> OutcomeReconciliationView:
    """Reconcile an agent's claimed outcome against system-of-record evidence."""
    try:
        row = reconcile_outcome(
            db,
            project_id=tenant_id,
            claimed=body.claimed,
            connector=ApiRecordConnector(
                record=body.actual,
                record_found=body.actual_record_found,
                connector_type=body.connector_type,
            ),
            call_id=body.call_id,
            trace_id=body.trace_id,
            runtime_policy_decision_id=body.runtime_policy_decision_id,
            action_type=body.action_type,
            system_ref=body.system_ref,
            amount_usd=body.amount_usd,
            currency=body.currency,
            match_fields=body.match_fields,
            idempotency_key=body.idempotency_key,
            metadata=body.metadata,
        )
    except (ProtectedActionQuotaExceeded, ProtectedActionMeteringUnavailable) as exc:
        raise _map_protected_action_billing_error(exc) from exc
    return _serialize_reconciliation(row)


@router.post(
    "/reconciliation/postgres-read",
    response_model=OutcomeReconciliationView,
    status_code=201,
)
@limiter.limit("30/minute")
def create_postgres_read_reconciliation(
    request: Request,
    body: PostgresReadReconciliationIngest = Body(...),
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> OutcomeReconciliationView:
    """Verify a claimed state against one read-only PostgreSQL source row."""
    settings = get_settings()
    timeout = body.connector.timeout_seconds or settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS
    connector = build_inline_postgres_read_connector(
        database_url=body.connector.database_url,
        query=body.connector.query,
        params=body.connector.params,
        timeout_seconds=timeout,
        allow_private_hosts=settings.OUTCOME_CONNECTOR_ALLOW_PRIVATE_HOSTS,
    )

    try:
        row = reconcile_outcome(
            db,
            project_id=tenant_id,
            claimed=body.claimed,
            connector=connector,
            call_id=body.call_id,
            trace_id=body.trace_id,
            runtime_policy_decision_id=body.runtime_policy_decision_id,
            action_type=body.action_type or "internal_record_verification",
            system_ref=body.system_ref or "postgres:source-record",
            amount_usd=body.amount_usd,
            currency=body.currency,
            match_fields=_postgres_read_match_fields(body.claimed, body.match_fields),
            idempotency_key=_postgres_read_idempotency_key(body),
            metadata={
                **(body.metadata or {}),
                "connector_kind": "postgres_read",
                "source": "postgres_read_verifier",
            },
        )
    except ConnectorConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (ProtectedActionQuotaExceeded, ProtectedActionMeteringUnavailable) as exc:
        raise _map_protected_action_billing_error(exc) from exc

    return _serialize_reconciliation(row)


@router.post(
    "/reconciliation/ledger-refund",
    response_model=OutcomeReconciliationView,
    status_code=201,
)
@limiter.limit("60/minute")
def create_ledger_refund_reconciliation(
    request: Request,
    body: LedgerRefundReconciliationIngest = Body(...),
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> OutcomeReconciliationView:
    """Fetch a refund from a ledger API and reconcile it against the agent claim."""
    refund_id = _refund_id(body)
    claimed = dict(body.claimed)
    claimed.setdefault("refund_id", refund_id)

    settings = get_settings()
    timeout = (
        body.connector.timeout_seconds or settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS
    )
    max_attempts = (
        body.connector.max_attempts or settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS
    )
    connector = build_inline_ledger_refund_connector(
        base_url=body.connector.base_url,
        refund_id=refund_id,
        bearer_token=body.connector.bearer_token,
        path_template=body.connector.path_template,
        query=body.connector.query,
        record_path=body.connector.record_path,
        timeout_seconds=timeout,
        max_attempts=max_attempts,
        allow_private_hosts=settings.OUTCOME_CONNECTOR_ALLOW_PRIVATE_HOSTS,
    )

    try:
        row = reconcile_outcome(
            db,
            project_id=tenant_id,
            claimed=claimed,
            connector=connector,
            call_id=body.call_id,
            trace_id=body.trace_id,
            runtime_policy_decision_id=body.runtime_policy_decision_id,
            action_type=body.action_type or "refund",
            system_ref=body.system_ref or f"ledger:{refund_id}",
            amount_usd=body.amount_usd
            if body.amount_usd is not None
            else _optional_float(claimed.get("amount_usd")),
            currency=body.currency or _claim_text(claimed, "currency"),
            match_fields=_ledger_refund_match_fields(claimed, body.match_fields),
            idempotency_key=_ledger_refund_idempotency_key(body, refund_id=refund_id),
            metadata={
                **(body.metadata or {}),
                "connector_kind": "ledger_refund_api",
                "refund_id": refund_id,
            },
        )
    except ConnectorConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (ProtectedActionQuotaExceeded, ProtectedActionMeteringUnavailable) as exc:
        raise _map_protected_action_billing_error(exc) from exc

    return _serialize_reconciliation(row)


@router.post(
    "/reconciliation/ledger-refund/saved",
    response_model=OutcomeReconciliationView,
    status_code=201,
)
@limiter.limit("60/minute")
def create_saved_ledger_refund_reconciliation(
    request: Request,
    body: SavedLedgerRefundReconciliationIngest = Body(...),
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> OutcomeReconciliationView:
    """Use the saved ledger connector to verify a refund without resending its secret."""
    return _create_saved_ledger_refund_reconciliation(
        db=db,
        tenant_id=tenant_id,
        body=body,
    )


@router.post(
    "/reconciliation/stripe-refund/saved",
    response_model=OutcomeReconciliationView,
    status_code=201,
)
@limiter.limit("60/minute")
def create_saved_stripe_refund_reconciliation(
    request: Request,
    body: SavedLedgerRefundReconciliationIngest = Body(...),
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> OutcomeReconciliationView:
    """Use the saved Stripe connector to verify a refund without resending its secret."""
    return _create_saved_stripe_refund_reconciliation(
        db=db,
        tenant_id=tenant_id,
        body=body,
    )


@router.post(
    "/reconciliation/razorpay-refund/saved",
    response_model=OutcomeReconciliationView,
    status_code=201,
)
@limiter.limit("60/minute")
def create_saved_razorpay_refund_reconciliation(
    request: Request,
    body: SavedLedgerRefundReconciliationIngest = Body(...),
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> OutcomeReconciliationView:
    """Use the saved Razorpay connector to verify a refund without resending its secret."""
    return _create_saved_razorpay_refund_reconciliation(
        db=db,
        tenant_id=tenant_id,
        body=body,
    )


@router.post(
    "/reconciliation/customer-record",
    response_model=OutcomeReconciliationView,
    status_code=201,
)
@limiter.limit("60/minute")
def create_customer_record_reconciliation(
    request: Request,
    body: CustomerRecordReconciliationIngest = Body(...),
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> OutcomeReconciliationView:
    """Fetch a CRM/customer record and reconcile it against the agent claim."""
    customer_id = _customer_id(body)
    claimed = dict(body.claimed)
    claimed.setdefault("customer_id", customer_id)

    settings = get_settings()
    timeout = (
        body.connector.timeout_seconds or settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS
    )
    max_attempts = (
        body.connector.max_attempts or settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS
    )
    connector = build_inline_customer_record_connector(
        base_url=body.connector.base_url,
        customer_id=customer_id,
        bearer_token=body.connector.bearer_token,
        path_template=body.connector.path_template,
        query=body.connector.query,
        record_path=body.connector.record_path,
        timeout_seconds=timeout,
        max_attempts=max_attempts,
        allow_private_hosts=settings.OUTCOME_CONNECTOR_ALLOW_PRIVATE_HOSTS,
    )

    try:
        row = reconcile_outcome(
            db,
            project_id=tenant_id,
            claimed=claimed,
            connector=connector,
            call_id=body.call_id,
            trace_id=body.trace_id,
            runtime_policy_decision_id=body.runtime_policy_decision_id,
            action_type=body.action_type or "customer_record_update",
            system_ref=body.system_ref or f"crm:{customer_id}",
            amount_usd=body.amount_usd,
            currency=body.currency,
            match_fields=_customer_record_match_fields(claimed, body.match_fields),
            idempotency_key=_customer_record_idempotency_key(
                body, customer_id=customer_id
            ),
            metadata={
                **(body.metadata or {}),
                "connector_kind": "customer_record_api",
                "customer_id": customer_id,
            },
        )
    except ConnectorConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (ProtectedActionQuotaExceeded, ProtectedActionMeteringUnavailable) as exc:
        raise _map_protected_action_billing_error(exc) from exc

    return _serialize_reconciliation(row)


@router.post(
    "/reconciliation/customer-record/saved",
    response_model=OutcomeReconciliationView,
    status_code=201,
)
@limiter.limit("60/minute")
def create_saved_customer_record_reconciliation(
    request: Request,
    body: SavedCustomerRecordReconciliationIngest = Body(...),
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> OutcomeReconciliationView:
    """Use the saved CRM connector to verify a customer record without resending its secret."""
    return _create_saved_customer_record_reconciliation(
        db=db,
        tenant_id=tenant_id,
        body=body,
    )


@router.post(
    "/reconciliation/generic-rest/saved",
    response_model=OutcomeReconciliationView,
    status_code=201,
)
@limiter.limit("60/minute")
def create_saved_generic_rest_reconciliation(
    request: Request,
    body: SavedGenericRestReconciliationIngest = Body(...),
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> OutcomeReconciliationView:
    """Use the saved Generic REST connector to verify a custom system record."""
    return _create_saved_generic_rest_reconciliation(
        db=db,
        tenant_id=tenant_id,
        body=body,
    )


@router.post(
    "/reconciliation/postgres-read/saved",
    response_model=OutcomeReconciliationView,
    status_code=201,
)
@limiter.limit("60/minute")
def create_saved_postgres_read_reconciliation(
    request: Request,
    body: SavedPostgresReadReconciliationIngest = Body(...),
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> OutcomeReconciliationView:
    """Use the saved PostgreSQL connector to verify one source-of-record row."""
    return _create_saved_postgres_read_reconciliation(
        db=db,
        tenant_id=tenant_id,
        body=body,
    )


@router.post(
    "/reconciliation/saved",
    response_model=OutcomeReconciliationView,
    status_code=201,
)
@limiter.limit("60/minute")
def create_saved_connector_reconciliation(
    request: Request,
    body: SavedConnectorReconciliationIngest = Body(...),
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> OutcomeReconciliationView:
    """Bridge webhook/HTTP agents into the saved connector verification runtime."""
    common = {
        "call_id": body.call_id,
        "trace_id": body.trace_id,
        "runtime_policy_decision_id": body.runtime_policy_decision_id,
        "action_type": body.action_type,
        "system_ref": body.system_ref,
        "claimed": body.claimed,
        "match_fields": body.match_fields,
        "amount_usd": body.amount_usd,
        "currency": body.currency,
        "idempotency_key": body.idempotency_key,
        "metadata": _bridge_metadata(body),
    }

    if body.connector == LEDGER_REFUND_CONNECTOR_TYPE:
        return _create_saved_ledger_refund_reconciliation(
            db=db,
            tenant_id=tenant_id,
            body=SavedLedgerRefundReconciliationIngest(
                refund_id=body.refund_id,
                **common,
            ),
        )
    if body.connector == STRIPE_REFUND_CONNECTOR_TYPE:
        return _create_saved_stripe_refund_reconciliation(
            db=db,
            tenant_id=tenant_id,
            body=SavedLedgerRefundReconciliationIngest(
                refund_id=body.refund_id,
                **common,
            ),
        )
    if body.connector == RAZORPAY_REFUND_CONNECTOR_TYPE:
        return _create_saved_razorpay_refund_reconciliation(
            db=db,
            tenant_id=tenant_id,
            body=SavedLedgerRefundReconciliationIngest(
                refund_id=body.refund_id,
                **common,
            ),
        )
    if body.connector == CUSTOMER_RECORD_CONNECTOR_TYPE:
        return _create_saved_customer_record_reconciliation(
            db=db,
            tenant_id=tenant_id,
            body=SavedCustomerRecordReconciliationIngest(
                customer_id=body.customer_id,
                **common,
            ),
        )
    if body.connector == GENERIC_REST_CONNECTOR_TYPE:
        return _create_saved_generic_rest_reconciliation(
            db=db,
            tenant_id=tenant_id,
            body=SavedGenericRestReconciliationIngest(
                record_ref=_bridge_record_ref(body),
                **common,
            ),
        )
    if body.connector == HUBSPOT_CRM_CONNECTOR_TYPE:
        return _create_saved_hubspot_crm_reconciliation(
            db=db,
            tenant_id=tenant_id,
            body=SavedGenericRestReconciliationIngest(
                record_ref=_bridge_record_ref(body),
                **common,
            ),
        )
    if body.connector == ZENDESK_TICKET_CONNECTOR_TYPE:
        return _create_saved_zendesk_ticket_reconciliation(
            db=db,
            tenant_id=tenant_id,
            body=SavedGenericRestReconciliationIngest(
                record_ref=_bridge_record_ref(body),
                **common,
            ),
        )
    if body.connector == JIRA_ISSUE_CONNECTOR_TYPE:
        return _create_saved_jira_issue_reconciliation(
            db=db,
            tenant_id=tenant_id,
            body=SavedGenericRestReconciliationIngest(
                record_ref=_bridge_record_ref(body),
                **common,
            ),
        )
    if body.connector == SALESFORCE_CRM_CONNECTOR_TYPE:
        return _create_saved_salesforce_crm_reconciliation(
            db=db,
            tenant_id=tenant_id,
            body=SavedGenericRestReconciliationIngest(
                record_ref=_bridge_record_ref(body),
                **common,
            ),
            object_type=_bridge_salesforce_object_type(body),
        )
    if body.connector == ZOHO_CRM_CONNECTOR_TYPE:
        return _create_saved_zoho_crm_reconciliation(
            db=db,
            tenant_id=tenant_id,
            body=SavedGenericRestReconciliationIngest(
                record_ref=_bridge_record_ref(body),
                **common,
            ),
            module_name=_bridge_zoho_module_name(body),
        )
    if body.connector == NETSUITE_FINANCE_CONNECTOR_TYPE:
        return _create_saved_netsuite_finance_reconciliation(
            db=db,
            tenant_id=tenant_id,
            body=SavedGenericRestReconciliationIngest(
                record_ref=_bridge_record_ref(body),
                **common,
            ),
            record_type=_bridge_netsuite_record_type(body),
        )
    if body.connector == POSTGRES_READ_CONNECTOR_TYPE:
        return _create_saved_postgres_read_reconciliation(
            db=db,
            tenant_id=tenant_id,
            body=SavedPostgresReadReconciliationIngest(
                params=body.params,
                **common,
            ),
        )

    raise HTTPException(status_code=422, detail="Unsupported saved connector.")


@router.get("/reconciliation", response_model=OutcomeReconciliationListResponse)
@limiter.limit("60/minute")
def list_reconciliation_checks(
    request: Request,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
    verdict: str | None = Query(default=None),
    days: int | None = Query(default=None, ge=1, le=365),
    limit: int = Query(default=50, ge=1, le=100),
) -> OutcomeReconciliationListResponse:
    """List recent outcome reconciliation checks for the current project."""
    if verdict is not None and verdict not in VALID_VERDICTS:
        raise HTTPException(
            status_code=422,
            detail=f"verdict must be one of: {', '.join(sorted(VALID_VERDICTS))}",
        )
    since = datetime.now(timezone.utc) - timedelta(days=days) if days is not None else None
    rows = list_reconciliations(
        db,
        project_id=tenant_id,
        verdict=verdict,
        since=since,
        limit=limit,
    )
    return OutcomeReconciliationListResponse(
        items=[_serialize_reconciliation(row) for row in rows],
        total_in_page=len(rows),
    )


@router.get(
    "/reconciliation/summary", response_model=OutcomeReconciliationSummaryResponse
)
@limiter.limit("30/minute")
def get_reconciliation_kpis(
    request: Request,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
    days: int = Query(default=30, ge=1, le=365),
) -> OutcomeReconciliationSummaryResponse:
    """Summary of matched, mismatched, and not_verified outcome checks."""
    summary = get_reconciliation_summary(db, project_id=tenant_id, days=days)
    return OutcomeReconciliationSummaryResponse(
        window_days=summary.window_days,
        total=summary.total,
        matched=summary.matched,
        mismatched=summary.mismatched,
        not_verified=summary.not_verified,
        verified=summary.verified,
        pending=summary.pending,
        unverifiable=summary.unverifiable,
        partial=summary.partial,
        cancelled=summary.cancelled,
    )


@router.get(
    "/reconciliation/mismatch-responses",
    response_model=OutcomeMismatchResponseListResponse,
)
@limiter.limit("60/minute")
def list_mismatch_response_cases(
    request: Request,
    response_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> OutcomeMismatchResponseListResponse:
    _require_mismatch_role(context, "viewer")
    try:
        rows = list_mismatch_responses(
            db,
            project_id=context.tenant_id,
            status=response_status,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return OutcomeMismatchResponseListResponse(
        items=[OutcomeMismatchResponseView(**mismatch_response_to_dict(db, row)) for row in rows],
        total_in_page=len(rows),
    )


@router.get(
    "/reconciliation/mismatch-responses/{response_id}",
    response_model=OutcomeMismatchResponseView,
)
@limiter.limit("60/minute")
def get_mismatch_response_case(
    request: Request,
    response_id: str,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> OutcomeMismatchResponseView:
    _require_mismatch_role(context, "viewer")
    row = get_mismatch_response(db, project_id=context.tenant_id, response_id=response_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Mismatch response case not found.")
    return OutcomeMismatchResponseView(**mismatch_response_to_dict(db, row))


@router.post(
    "/reconciliation/mismatch-responses/{response_id}/acknowledge",
    response_model=OutcomeMismatchResponseView,
)
@limiter.limit("30/minute")
def acknowledge_mismatch_response_case(
    request: Request,
    response_id: str,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> OutcomeMismatchResponseView:
    _require_mismatch_role(context, "member")
    row = get_mismatch_response(db, project_id=context.tenant_id, response_id=response_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Mismatch response case not found.")
    row = acknowledge_mismatch_response(db, response=row, actor=context.subject)
    return OutcomeMismatchResponseView(**mismatch_response_to_dict(db, row))


@router.post(
    "/reconciliation/mismatch-responses/{response_id}/resolve",
    response_model=OutcomeMismatchResponseView,
)
@limiter.limit("30/minute")
def resolve_mismatch_response_case(
    request: Request,
    response_id: str,
    body: OutcomeMismatchResolveRequest,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> OutcomeMismatchResponseView:
    _require_mismatch_role(context, "owner")
    row = get_mismatch_response(db, project_id=context.tenant_id, response_id=response_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Mismatch response case not found.")
    try:
        row = resolve_mismatch_response(
            db,
            response=row,
            resolution_code=body.resolution_code,
            resolution_note=body.resolution_note,
            actor=context.subject,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return OutcomeMismatchResponseView(**mismatch_response_to_dict(db, row))


@router.get(
    "/reconciliation/by-call/{call_id}",
    response_model=OutcomeReconciliationListResponse,
)
@limiter.limit("60/minute")
def get_reconciliations_for_call(
    request: Request,
    call_id: str,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> OutcomeReconciliationListResponse:
    """List reconciliation checks linked to a specific Zroky call."""
    rows = list_reconciliations(db, project_id=tenant_id, call_id=call_id, limit=100)
    return OutcomeReconciliationListResponse(
        items=[_serialize_reconciliation(row) for row in rows],
        total_in_page=len(rows),
    )


@router.post(
    "/reconciliation/source-mutations",
    response_model=SourceMutationView,
    status_code=201,
)
@limiter.limit("60/minute")
def ingest_source_mutation_record(
    request: Request,
    body: SourceMutationIngest,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> SourceMutationView:
    try:
        row = ingest_source_mutation(
            db,
            project_id=tenant_id,
            source_system=body.source_system,
            mutation_id=body.mutation_id,
            action_type=body.action_type,
            resource_type=body.resource_type,
            resource_id=body.resource_id,
            system_ref=body.system_ref,
            actor_type=body.actor_type,
            actor_id=body.actor_id,
            zroky_action_id=body.zroky_action_id,
            action_receipt_id=body.action_receipt_id,
            idempotency_key=body.idempotency_key,
            metadata=body.metadata,
            occurred_at=body.occurred_at,
        )
    except (ProtectedActionQuotaExceeded, ProtectedActionMeteringUnavailable) as exc:
        raise _map_protected_action_billing_error(exc) from exc
    db.commit()
    return _serialize_source_mutation(row)


@router.get(
    "/reconciliation/source-mutations",
    response_model=SourceMutationListResponse,
)
@limiter.limit("60/minute")
def list_source_mutation_records(
    request: Request,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
    classification: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=100, ge=1, le=500),
) -> SourceMutationListResponse:
    rows = list_source_mutations(
        db,
        project_id=tenant_id,
        classification=classification,
        limit=limit,
    )
    return SourceMutationListResponse(
        items=[_serialize_source_mutation(row) for row in rows],
        total_in_page=len(rows),
    )


@router.get(
    "/reconciliation/source-mutations/unreceipted",
    response_model=SourceMutationListResponse,
)
@limiter.limit("60/minute")
def list_unreceipted_source_mutations(
    request: Request,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
    limit: int = Query(default=100, ge=1, le=500),
) -> SourceMutationListResponse:
    rows = list_source_mutations(
        db,
        project_id=tenant_id,
        unreceipted_only=True,
        limit=limit,
    )
    return SourceMutationListResponse(
        items=[_serialize_source_mutation(row) for row in rows],
        total_in_page=len(rows),
    )


@router.get(
    "/reconciliation/source-mutations/summary",
    response_model=SourceMutationSummaryResponse,
)
@limiter.limit("60/minute")
def get_source_mutation_summary(
    request: Request,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> SourceMutationSummaryResponse:
    return SourceMutationSummaryResponse(**source_mutation_summary(db, project_id=tenant_id))


@router.get("/reconciliation/{check_id}", response_model=OutcomeReconciliationView)
@limiter.limit("60/minute")
def get_reconciliation_check(
    request: Request,
    check_id: str,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> OutcomeReconciliationView:
    """Read one outcome reconciliation check."""
    row = get_reconciliation(db, project_id=tenant_id, check_id=check_id)
    if row is None:
        raise HTTPException(
            status_code=404, detail="Outcome reconciliation check not found."
        )
    return _serialize_reconciliation(row)


@router.get("/by-call/{call_id}", response_model=list[OutcomeTypeView])
@limiter.limit("60/minute")
def get_outcomes_for_call(
    request: Request,
    call_id: str,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> list[OutcomeTypeView]:
    """All outcome events linked to a specific call."""
    views = get_call_outcomes(db, project_id=tenant_id, call_id=call_id)
    return [
        OutcomeTypeView(
            outcome_type=v.outcome_type,
            total_usd=v.amount_usd,
            count=1,
            avg_usd=v.amount_usd,
        )
        for v in views
    ]


@router.get("/replay/{run_id}", response_model=ReplaySavingsResponse)
@limiter.limit("30/minute")
def get_replay_savings(
    request: Request,
    run_id: str,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> ReplaySavingsResponse:
    """Compute the $ value of failures a replay run's candidate prompt would prevent."""
    savings = get_replay_prevented_savings(db, project_id=tenant_id, run_id=run_id)
    return ReplaySavingsResponse(
        run_id=run_id,
        prevented_outcome_cost_usd=savings,
        message=(
            f"This candidate prevents failures worth ${savings:,.2f} in linked outcome costs."
            if savings > 0
            else "No linked outcome events found for passing traces in this run."
        ),
    )


# ── Webhooks ──────────────────────────────────────────────────────────────────


@router.post("/webhooks/zendesk", status_code=200)
@limiter.limit("30/minute")
async def zendesk_webhook(
    request: Request,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> dict[str, str]:
    """Receive Zendesk ticket webhook and ingest escalations as outcome_events."""
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc

    fields = normalise_zendesk_ticket(payload)
    ingest_outcome(db, project_id=tenant_id, **fields)
    return {"status": "ok"}


@router.post("/webhooks/salesforce", status_code=200)
@limiter.limit("30/minute")
async def salesforce_webhook(
    request: Request,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> dict[str, str]:
    """Receive Salesforce Opportunity stage-change and ingest churn as outcome_events."""
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc

    fields = normalise_salesforce_event(payload)
    ingest_outcome(db, project_id=tenant_id, **fields)
    return {"status": "ok"}
