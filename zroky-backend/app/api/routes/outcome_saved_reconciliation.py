"""Saved connector reconciliation runtime helpers."""

import re
from typing import Any, Mapping

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.routes.outcome_reconciliation_helpers import (
    _claim_text,
    _customer_id,
    _customer_record_match_fields,
    _generic_rest_match_fields,
    _hubspot_crm_match_fields,
    _jira_issue_match_fields,
    _ledger_refund_match_fields,
    _map_protected_action_billing_error,
    _netsuite_finance_match_fields,
    _optional_float,
    _postgres_read_match_fields,
    _refund_id,
    _saved_customer_record_idempotency_key,
    _saved_generic_rest_idempotency_key,
    _saved_hubspot_crm_idempotency_key,
    _saved_jira_issue_idempotency_key,
    _saved_ledger_refund_idempotency_key,
    _saved_netsuite_finance_idempotency_key,
    _saved_postgres_read_idempotency_key,
    _saved_razorpay_refund_idempotency_key,
    _saved_salesforce_crm_idempotency_key,
    _saved_zendesk_ticket_idempotency_key,
    _saved_zoho_crm_idempotency_key,
    _salesforce_crm_match_fields,
    _zendesk_ticket_match_fields,
    _zoho_crm_match_fields,
)
from app.api.routes.outcome_serializers import _serialize_reconciliation
from app.core.config import get_settings
from app.schemas.outcomes import (
    OutcomeReconciliationView,
    SavedConnectorReconciliationIngest,
    SavedCustomerRecordReconciliationIngest,
    SavedGenericRestReconciliationIngest,
    SavedLedgerRefundReconciliationIngest,
    SavedPostgresReadReconciliationIngest,
)
from app.services.outcome_reconciliation import reconcile_outcome
from app.services.protected_action_billing import (
    ProtectedActionMeteringUnavailable,
    ProtectedActionQuotaExceeded,
)
from app.services.system_of_record_connectors import ConnectorConfigError
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
    EnvelopeFormatError,
    VaultCipherUnavailable,
    build_customer_record_connector,
    build_generic_rest_connector,
    build_hubspot_crm_connector,
    build_jira_issue_connector,
    build_ledger_refund_connector,
    build_netsuite_finance_connector,
    build_postgres_read_connector,
    build_razorpay_refund_connector,
    build_salesforce_crm_connector,
    build_stripe_refund_connector,
    build_zendesk_ticket_connector,
    build_zoho_crm_connector,
    decrypt_connector_bearer_token,
    decrypt_connector_database_url,
    get_connector_config,
)
from app.services.zoho_oauth import ZohoOAuthError, resolve_zoho_crm_bearer_token


def _map_saved_connector_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (ProtectedActionQuotaExceeded, ProtectedActionMeteringUnavailable)):
        return _map_protected_action_billing_error(exc)
    if isinstance(exc, VaultCipherUnavailable):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, EnvelopeFormatError):
        return HTTPException(
            status_code=500,
            detail="Connector secret could not be decrypted.",
        )
    if isinstance(exc, ZohoOAuthError):
        return HTTPException(status_code=502, detail=str(exc))
    return HTTPException(status_code=422, detail=str(exc))


def _bridge_record_ref(body: SavedConnectorReconciliationIngest) -> str:
    record_ref = (
        body.record_ref
        or _claim_text(body.claimed, "record_ref")
        or _claim_text(body.claimed, "id")
        or _claim_text(body.claimed, "external_ref")
        or ""
    ).strip()
    if not record_ref:
        raise HTTPException(
            status_code=422,
            detail="record_ref is required for Generic REST saved reconciliation.",
        )
    return record_ref


def _bridge_metadata(body: SavedConnectorReconciliationIngest) -> dict[str, Any]:
    return {
        **(body.metadata or {}),
        "runtime_path": "webhook_bridge",
        "bridge_connector": body.connector,
    }


def _bridge_salesforce_object_type(body: SavedConnectorReconciliationIngest) -> str:
    for source in (body.params, body.metadata):
        if not isinstance(source, Mapping):
            continue
        value = source.get("object_type") or source.get("salesforce_object")
        if value is None:
            continue
        cleaned = str(value).strip()
        if not cleaned:
            continue
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(__c)?", cleaned):
            raise HTTPException(
                status_code=422,
                detail="object_type must be a Salesforce object API name.",
            )
        return cleaned
    return "Account"


def _bridge_zoho_module_name(body: SavedConnectorReconciliationIngest) -> str:
    for source in (body.params, body.metadata):
        if not isinstance(source, Mapping):
            continue
        value = source.get("module_name") or source.get("zoho_module")
        if value is None:
            continue
        cleaned = str(value).strip()
        if not cleaned:
            continue
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", cleaned):
            raise HTTPException(
                status_code=422,
                detail="module_name must be a Zoho CRM module API name.",
            )
        return cleaned
    return "Contacts"


def _bridge_netsuite_record_type(body: SavedConnectorReconciliationIngest) -> str:
    for source in (body.params, body.metadata):
        if not isinstance(source, Mapping):
            continue
        value = source.get("record_type") or source.get("netsuite_record_type")
        if value is None:
            continue
        cleaned = str(value).strip()
        if not cleaned:
            continue
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", cleaned):
            raise HTTPException(
                status_code=422,
                detail="record_type must be a NetSuite record type API name.",
            )
        return cleaned
    return "vendorBill"


def _create_saved_ledger_refund_reconciliation(
    *,
    db: Session,
    tenant_id: str,
    body: SavedLedgerRefundReconciliationIngest,
) -> OutcomeReconciliationView:
    config = get_connector_config(
        db,
        project_id=tenant_id,
        connector_type=LEDGER_REFUND_CONNECTOR_TYPE,
    )
    if config is None or not config.is_active:
        raise HTTPException(
            status_code=404,
            detail="Ledger refund connector is not configured.",
        )

    refund_id = _refund_id(body)
    claimed = dict(body.claimed)
    claimed.setdefault("refund_id", refund_id)
    settings = get_settings()

    try:
        bearer_token = decrypt_connector_bearer_token(config, project_id=tenant_id)
        connector = build_ledger_refund_connector(
            config,
            refund_id=refund_id,
            bearer_token=bearer_token,
            timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
            max_attempts=settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS,
            allow_private_hosts=settings.OUTCOME_CONNECTOR_ALLOW_PRIVATE_HOSTS,
        )
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
            idempotency_key=_saved_ledger_refund_idempotency_key(
                body, refund_id=refund_id
            ),
            metadata={
                **(body.metadata or {}),
                "connector_kind": "ledger_refund_api",
                "connector_config_id": config.id,
                "refund_id": refund_id,
                "source": "saved_connector_runtime",
            },
        )
    except (
        ConnectorConfigError,
        EnvelopeFormatError,
        VaultCipherUnavailable,
        ValueError,
    ) as exc:
        raise _map_saved_connector_error(exc) from exc

    return _serialize_reconciliation(row)


def _create_saved_stripe_refund_reconciliation(
    *,
    db: Session,
    tenant_id: str,
    body: SavedLedgerRefundReconciliationIngest,
) -> OutcomeReconciliationView:
    config = get_connector_config(
        db,
        project_id=tenant_id,
        connector_type=STRIPE_REFUND_CONNECTOR_TYPE,
    )
    if config is None or not config.is_active:
        raise HTTPException(
            status_code=404,
            detail="Stripe refund connector is not configured.",
        )

    refund_id = _refund_id(body)
    claimed = dict(body.claimed)
    claimed.setdefault("refund_id", refund_id)
    claimed.setdefault("stripe_refund_id", refund_id)
    settings = get_settings()

    try:
        bearer_token = decrypt_connector_bearer_token(config, project_id=tenant_id)
        connector = build_stripe_refund_connector(
            config,
            refund_id=refund_id,
            bearer_token=bearer_token,
            timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
            max_attempts=settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS,
        )
        row = reconcile_outcome(
            db,
            project_id=tenant_id,
            claimed=claimed,
            connector=connector,
            call_id=body.call_id,
            trace_id=body.trace_id,
            runtime_policy_decision_id=body.runtime_policy_decision_id,
            action_type=body.action_type or "refund",
            system_ref=body.system_ref or f"stripe:refund:{refund_id}",
            amount_usd=body.amount_usd
            if body.amount_usd is not None
            else _optional_float(claimed.get("amount_usd")),
            currency=body.currency or _claim_text(claimed, "currency"),
            match_fields=_ledger_refund_match_fields(claimed, body.match_fields),
            idempotency_key=_saved_razorpay_refund_idempotency_key(
                body, refund_id=refund_id
            ),
            metadata={
                **(body.metadata or {}),
                "connector_kind": STRIPE_REFUND_CONNECTOR_TYPE,
                "connector_config_id": config.id,
                "refund_id": refund_id,
                "source": "saved_connector_runtime",
            },
        )
    except (
        ConnectorConfigError,
        EnvelopeFormatError,
        VaultCipherUnavailable,
        ValueError,
    ) as exc:
        raise _map_saved_connector_error(exc) from exc

    return _serialize_reconciliation(row)


def _create_saved_razorpay_refund_reconciliation(
    *,
    db: Session,
    tenant_id: str,
    body: SavedLedgerRefundReconciliationIngest,
) -> OutcomeReconciliationView:
    config = get_connector_config(
        db,
        project_id=tenant_id,
        connector_type=RAZORPAY_REFUND_CONNECTOR_TYPE,
    )
    if config is None or not config.is_active:
        raise HTTPException(
            status_code=404,
            detail="Razorpay refund connector is not configured.",
        )

    refund_id = _refund_id(body)
    claimed = dict(body.claimed)
    claimed.setdefault("refund_id", refund_id)
    claimed.setdefault("razorpay_refund_id", refund_id)
    settings = get_settings()

    try:
        key_secret = decrypt_connector_bearer_token(config, project_id=tenant_id)
        connector = build_razorpay_refund_connector(
            config,
            refund_id=refund_id,
            key_secret=key_secret,
            timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
            max_attempts=settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS,
        )
        row = reconcile_outcome(
            db,
            project_id=tenant_id,
            claimed=claimed,
            connector=connector,
            call_id=body.call_id,
            trace_id=body.trace_id,
            runtime_policy_decision_id=body.runtime_policy_decision_id,
            action_type=body.action_type or "refund",
            system_ref=body.system_ref or f"razorpay:refund:{refund_id}",
            amount_usd=body.amount_usd
            if body.amount_usd is not None
            else _optional_float(claimed.get("amount_usd")),
            currency=body.currency or _claim_text(claimed, "currency"),
            match_fields=_ledger_refund_match_fields(claimed, body.match_fields),
            idempotency_key=_saved_ledger_refund_idempotency_key(
                body, refund_id=refund_id
            ),
            metadata={
                **(body.metadata or {}),
                "connector_kind": RAZORPAY_REFUND_CONNECTOR_TYPE,
                "connector_config_id": config.id,
                "refund_id": refund_id,
                "source": "saved_connector_runtime",
            },
        )
    except (
        ConnectorConfigError,
        EnvelopeFormatError,
        VaultCipherUnavailable,
        ValueError,
    ) as exc:
        raise _map_saved_connector_error(exc) from exc

    return _serialize_reconciliation(row)


def _create_saved_customer_record_reconciliation(
    *,
    db: Session,
    tenant_id: str,
    body: SavedCustomerRecordReconciliationIngest,
) -> OutcomeReconciliationView:
    config = get_connector_config(
        db,
        project_id=tenant_id,
        connector_type=CUSTOMER_RECORD_CONNECTOR_TYPE,
    )
    if config is None or not config.is_active:
        raise HTTPException(
            status_code=404,
            detail="Customer record connector is not configured.",
        )

    customer_id = _customer_id(body)
    claimed = dict(body.claimed)
    claimed.setdefault("customer_id", customer_id)
    settings = get_settings()

    try:
        bearer_token = decrypt_connector_bearer_token(config, project_id=tenant_id)
        connector = build_customer_record_connector(
            config,
            customer_id=customer_id,
            bearer_token=bearer_token,
            timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
            max_attempts=settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS,
            allow_private_hosts=settings.OUTCOME_CONNECTOR_ALLOW_PRIVATE_HOSTS,
        )
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
            idempotency_key=_saved_customer_record_idempotency_key(
                body, customer_id=customer_id
            ),
            metadata={
                **(body.metadata or {}),
                "connector_kind": "customer_record_api",
                "connector_config_id": config.id,
                "customer_id": customer_id,
                "source": "saved_connector_runtime",
            },
        )
    except (
        ConnectorConfigError,
        EnvelopeFormatError,
        VaultCipherUnavailable,
        ValueError,
    ) as exc:
        raise _map_saved_connector_error(exc) from exc

    return _serialize_reconciliation(row)


def _create_saved_generic_rest_reconciliation(
    *,
    db: Session,
    tenant_id: str,
    body: SavedGenericRestReconciliationIngest,
) -> OutcomeReconciliationView:
    config = get_connector_config(
        db,
        project_id=tenant_id,
        connector_type=GENERIC_REST_CONNECTOR_TYPE,
    )
    if config is None or not config.is_active:
        raise HTTPException(
            status_code=404,
            detail="Generic REST connector is not configured.",
        )

    record_ref = body.record_ref.strip()
    claimed = dict(body.claimed)
    claimed.setdefault("record_ref", record_ref)
    settings = get_settings()

    try:
        bearer_token = decrypt_connector_bearer_token(config, project_id=tenant_id)
        connector = build_generic_rest_connector(
            config,
            record_ref=record_ref,
            bearer_token=bearer_token,
            timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
            max_attempts=settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS,
            allow_private_hosts=settings.OUTCOME_CONNECTOR_ALLOW_PRIVATE_HOSTS,
        )
        row = reconcile_outcome(
            db,
            project_id=tenant_id,
            claimed=claimed,
            connector=connector,
            call_id=body.call_id,
            trace_id=body.trace_id,
            runtime_policy_decision_id=body.runtime_policy_decision_id,
            action_type=body.action_type or "custom",
            system_ref=body.system_ref or f"generic:{record_ref}",
            amount_usd=body.amount_usd,
            currency=body.currency,
            match_fields=_generic_rest_match_fields(claimed, body.match_fields),
            idempotency_key=_saved_generic_rest_idempotency_key(
                body, record_ref=record_ref
            ),
            metadata={
                **(body.metadata or {}),
                "connector_kind": GENERIC_REST_CONNECTOR_TYPE,
                "connector_config_id": config.id,
                "record_ref": record_ref,
                "source": "saved_connector_runtime",
            },
        )
    except (
        ConnectorConfigError,
        EnvelopeFormatError,
        VaultCipherUnavailable,
        ValueError,
    ) as exc:
        raise _map_saved_connector_error(exc) from exc

    return _serialize_reconciliation(row)


def _create_saved_hubspot_crm_reconciliation(
    *,
    db: Session,
    tenant_id: str,
    body: SavedGenericRestReconciliationIngest,
) -> OutcomeReconciliationView:
    config = get_connector_config(
        db,
        project_id=tenant_id,
        connector_type=HUBSPOT_CRM_CONNECTOR_TYPE,
    )
    if config is None or not config.is_active:
        raise HTTPException(
            status_code=404,
            detail="HubSpot CRM connector is not configured.",
        )

    record_ref = body.record_ref.strip()
    claimed = dict(body.claimed)
    claimed.setdefault("record_ref", record_ref)
    if "@" in record_ref and "email" not in claimed:
        claimed["email"] = record_ref.strip().lower()
    settings = get_settings()

    try:
        bearer_token = decrypt_connector_bearer_token(config, project_id=tenant_id)
        connector = build_hubspot_crm_connector(
            config,
            record_ref=record_ref,
            bearer_token=bearer_token,
            timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
            max_attempts=settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS,
        )
        row = reconcile_outcome(
            db,
            project_id=tenant_id,
            claimed=claimed,
            connector=connector,
            call_id=body.call_id,
            trace_id=body.trace_id,
            runtime_policy_decision_id=body.runtime_policy_decision_id,
            action_type=body.action_type or "customer_record_update",
            system_ref=body.system_ref or f"hubspot:contact:{record_ref}",
            amount_usd=body.amount_usd,
            currency=body.currency,
            match_fields=_hubspot_crm_match_fields(claimed, body.match_fields),
            idempotency_key=_saved_hubspot_crm_idempotency_key(
                body, record_ref=record_ref
            ),
            metadata={
                **(body.metadata or {}),
                "connector_kind": HUBSPOT_CRM_CONNECTOR_TYPE,
                "connector_config_id": config.id,
                "record_ref": record_ref,
                "source": "saved_connector_runtime",
            },
        )
    except (
        ConnectorConfigError,
        EnvelopeFormatError,
        VaultCipherUnavailable,
        ValueError,
    ) as exc:
        raise _map_saved_connector_error(exc) from exc

    return _serialize_reconciliation(row)


def _create_saved_zendesk_ticket_reconciliation(
    *,
    db: Session,
    tenant_id: str,
    body: SavedGenericRestReconciliationIngest,
) -> OutcomeReconciliationView:
    config = get_connector_config(
        db,
        project_id=tenant_id,
        connector_type=ZENDESK_TICKET_CONNECTOR_TYPE,
    )
    if config is None or not config.is_active:
        raise HTTPException(
            status_code=404,
            detail="Zendesk ticket connector is not configured.",
        )

    record_ref = body.record_ref.strip()
    claimed = dict(body.claimed)
    claimed.setdefault("record_ref", record_ref)
    claimed.setdefault("ticket_id", record_ref)
    settings = get_settings()

    try:
        bearer_token = decrypt_connector_bearer_token(config, project_id=tenant_id)
        connector = build_zendesk_ticket_connector(
            config,
            record_ref=record_ref,
            bearer_token=bearer_token,
            timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
            max_attempts=settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS,
        )
        row = reconcile_outcome(
            db,
            project_id=tenant_id,
            claimed=claimed,
            connector=connector,
            call_id=body.call_id,
            trace_id=body.trace_id,
            runtime_policy_decision_id=body.runtime_policy_decision_id,
            action_type=body.action_type or "ticket_close",
            system_ref=body.system_ref or f"zendesk:ticket:{record_ref}",
            amount_usd=body.amount_usd,
            currency=body.currency,
            match_fields=_zendesk_ticket_match_fields(claimed, body.match_fields),
            idempotency_key=_saved_zendesk_ticket_idempotency_key(
                body, record_ref=record_ref
            ),
            metadata={
                **(body.metadata or {}),
                "connector_kind": ZENDESK_TICKET_CONNECTOR_TYPE,
                "connector_config_id": config.id,
                "record_ref": record_ref,
                "source": "saved_connector_runtime",
            },
        )
    except (
        ConnectorConfigError,
        EnvelopeFormatError,
        VaultCipherUnavailable,
        ValueError,
    ) as exc:
        raise _map_saved_connector_error(exc) from exc

    return _serialize_reconciliation(row)


def _create_saved_jira_issue_reconciliation(
    *,
    db: Session,
    tenant_id: str,
    body: SavedGenericRestReconciliationIngest,
) -> OutcomeReconciliationView:
    config = get_connector_config(
        db,
        project_id=tenant_id,
        connector_type=JIRA_ISSUE_CONNECTOR_TYPE,
    )
    if config is None or not config.is_active:
        raise HTTPException(
            status_code=404,
            detail="Jira issue connector is not configured.",
        )

    record_ref = body.record_ref.strip()
    claimed = dict(body.claimed)
    claimed.setdefault("record_ref", record_ref)
    claimed.setdefault("jira_issue_key", record_ref)
    claimed.setdefault("issue_key", record_ref)
    settings = get_settings()

    try:
        bearer_token = decrypt_connector_bearer_token(config, project_id=tenant_id)
        connector = build_jira_issue_connector(
            config,
            record_ref=record_ref,
            bearer_token=bearer_token,
            timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
            max_attempts=settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS,
        )
        row = reconcile_outcome(
            db,
            project_id=tenant_id,
            claimed=claimed,
            connector=connector,
            call_id=body.call_id,
            trace_id=body.trace_id,
            runtime_policy_decision_id=body.runtime_policy_decision_id,
            action_type=body.action_type or "ticket_close",
            system_ref=body.system_ref or f"jira:issue:{record_ref}",
            amount_usd=body.amount_usd,
            currency=body.currency,
            match_fields=_jira_issue_match_fields(claimed, body.match_fields),
            idempotency_key=_saved_jira_issue_idempotency_key(
                body, record_ref=record_ref
            ),
            metadata={
                **(body.metadata or {}),
                "connector_kind": JIRA_ISSUE_CONNECTOR_TYPE,
                "connector_config_id": config.id,
                "record_ref": record_ref,
                "source": "saved_connector_runtime",
            },
        )
    except (
        ConnectorConfigError,
        EnvelopeFormatError,
        VaultCipherUnavailable,
        ValueError,
    ) as exc:
        raise _map_saved_connector_error(exc) from exc

    return _serialize_reconciliation(row)


def _create_saved_salesforce_crm_reconciliation(
    *,
    db: Session,
    tenant_id: str,
    body: SavedGenericRestReconciliationIngest,
    object_type: str,
) -> OutcomeReconciliationView:
    config = get_connector_config(
        db,
        project_id=tenant_id,
        connector_type=SALESFORCE_CRM_CONNECTOR_TYPE,
    )
    if config is None or not config.is_active:
        raise HTTPException(
            status_code=404,
            detail="Salesforce CRM connector is not configured.",
        )

    record_ref = body.record_ref.strip()
    claimed = dict(body.claimed)
    claimed.setdefault("record_ref", record_ref)
    claimed.setdefault("salesforce_id", record_ref)
    claimed.setdefault("object_type", object_type)
    settings = get_settings()

    try:
        bearer_token = decrypt_connector_bearer_token(config, project_id=tenant_id)
        connector = build_salesforce_crm_connector(
            config,
            object_type=object_type,
            record_ref=record_ref,
            bearer_token=bearer_token,
            timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
            max_attempts=settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS,
        )
        row = reconcile_outcome(
            db,
            project_id=tenant_id,
            claimed=claimed,
            connector=connector,
            call_id=body.call_id,
            trace_id=body.trace_id,
            runtime_policy_decision_id=body.runtime_policy_decision_id,
            action_type=body.action_type or "customer_record_update",
            system_ref=body.system_ref or f"salesforce:{object_type}:{record_ref}",
            amount_usd=body.amount_usd
            if body.amount_usd is not None
            else _optional_float(claimed.get("amount_usd") or claimed.get("Amount")),
            currency=body.currency or _claim_text(claimed, "currency"),
            match_fields=_salesforce_crm_match_fields(claimed, body.match_fields),
            idempotency_key=_saved_salesforce_crm_idempotency_key(
                body,
                object_type=object_type,
                record_ref=record_ref,
            ),
            metadata={
                **(body.metadata or {}),
                "connector_kind": SALESFORCE_CRM_CONNECTOR_TYPE,
                "connector_config_id": config.id,
                "object_type": object_type,
                "record_ref": record_ref,
                "source": "saved_connector_runtime",
            },
        )
    except (
        ConnectorConfigError,
        EnvelopeFormatError,
        VaultCipherUnavailable,
        ValueError,
    ) as exc:
        raise _map_saved_connector_error(exc) from exc

    return _serialize_reconciliation(row)


def _create_saved_zoho_crm_reconciliation(
    *,
    db: Session,
    tenant_id: str,
    body: SavedGenericRestReconciliationIngest,
    module_name: str,
) -> OutcomeReconciliationView:
    config = get_connector_config(
        db,
        project_id=tenant_id,
        connector_type=ZOHO_CRM_CONNECTOR_TYPE,
    )
    if config is None or not config.is_active:
        raise HTTPException(
            status_code=404,
            detail="Zoho CRM connector is not configured.",
        )

    record_ref = body.record_ref.strip()
    claimed = dict(body.claimed)
    claimed.setdefault("record_ref", record_ref)
    claimed.setdefault("zoho_record_id", record_ref)
    claimed.setdefault("module_name", module_name)
    settings = get_settings()

    try:
        bearer_token = resolve_zoho_crm_bearer_token(
            config,
            project_id=tenant_id,
            settings=settings,
        )
        connector = build_zoho_crm_connector(
            config,
            module_name=module_name,
            record_ref=record_ref,
            bearer_token=bearer_token,
            timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
            max_attempts=settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS,
        )
        row = reconcile_outcome(
            db,
            project_id=tenant_id,
            claimed=claimed,
            connector=connector,
            call_id=body.call_id,
            trace_id=body.trace_id,
            runtime_policy_decision_id=body.runtime_policy_decision_id,
            action_type=body.action_type or "customer_record_update",
            system_ref=body.system_ref or f"zoho:{module_name}:{record_ref}",
            amount_usd=body.amount_usd
            if body.amount_usd is not None
            else _optional_float(claimed.get("amount_usd") or claimed.get("Amount")),
            currency=body.currency or _claim_text(claimed, "currency"),
            match_fields=_zoho_crm_match_fields(claimed, body.match_fields),
            idempotency_key=_saved_zoho_crm_idempotency_key(
                body,
                module_name=module_name,
                record_ref=record_ref,
            ),
            metadata={
                **(body.metadata or {}),
                "connector_kind": ZOHO_CRM_CONNECTOR_TYPE,
                "connector_config_id": config.id,
                "module_name": module_name,
                "record_ref": record_ref,
                "source": "saved_connector_runtime",
            },
        )
    except (
        ConnectorConfigError,
        EnvelopeFormatError,
        VaultCipherUnavailable,
        ZohoOAuthError,
        ValueError,
    ) as exc:
        raise _map_saved_connector_error(exc) from exc

    return _serialize_reconciliation(row)


def _create_saved_netsuite_finance_reconciliation(
    *,
    db: Session,
    tenant_id: str,
    body: SavedGenericRestReconciliationIngest,
    record_type: str,
) -> OutcomeReconciliationView:
    config = get_connector_config(
        db,
        project_id=tenant_id,
        connector_type=NETSUITE_FINANCE_CONNECTOR_TYPE,
    )
    if config is None or not config.is_active:
        raise HTTPException(
            status_code=404,
            detail="NetSuite finance connector is not configured.",
        )

    record_ref = body.record_ref.strip()
    claimed = dict(body.claimed)
    claimed.setdefault("record_ref", record_ref)
    claimed.setdefault("netsuite_record_id", record_ref)
    claimed.setdefault("record_type", record_type)
    settings = get_settings()

    try:
        bearer_token = decrypt_connector_bearer_token(config, project_id=tenant_id)
        connector = build_netsuite_finance_connector(
            config,
            record_type=record_type,
            record_ref=record_ref,
            bearer_token=bearer_token,
            timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
            max_attempts=settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS,
        )
        row = reconcile_outcome(
            db,
            project_id=tenant_id,
            claimed=claimed,
            connector=connector,
            call_id=body.call_id,
            trace_id=body.trace_id,
            runtime_policy_decision_id=body.runtime_policy_decision_id,
            action_type=body.action_type or "finance_record_update",
            system_ref=body.system_ref or f"netsuite:{record_type}:{record_ref}",
            amount_usd=body.amount_usd
            if body.amount_usd is not None
            else _optional_float(
                claimed.get("amount_usd")
                or claimed.get("Amount")
                or claimed.get("total")
            ),
            currency=body.currency or _claim_text(claimed, "currency"),
            match_fields=_netsuite_finance_match_fields(claimed, body.match_fields),
            idempotency_key=_saved_netsuite_finance_idempotency_key(
                body,
                record_type=record_type,
                record_ref=record_ref,
            ),
            metadata={
                **(body.metadata or {}),
                "connector_kind": NETSUITE_FINANCE_CONNECTOR_TYPE,
                "connector_config_id": config.id,
                "record_type": record_type,
                "record_ref": record_ref,
                "source": "saved_connector_runtime",
            },
        )
    except (
        ConnectorConfigError,
        EnvelopeFormatError,
        VaultCipherUnavailable,
        ValueError,
    ) as exc:
        raise _map_saved_connector_error(exc) from exc

    return _serialize_reconciliation(row)


def _create_saved_postgres_read_reconciliation(
    *,
    db: Session,
    tenant_id: str,
    body: SavedPostgresReadReconciliationIngest,
) -> OutcomeReconciliationView:
    config = get_connector_config(
        db,
        project_id=tenant_id,
        connector_type=POSTGRES_READ_CONNECTOR_TYPE,
    )
    if config is None or not config.is_active:
        raise HTTPException(
            status_code=404,
            detail="PostgreSQL read connector is not configured.",
        )
    if not config.read_query:
        raise HTTPException(
            status_code=422,
            detail="PostgreSQL read connector query is not configured.",
        )

    settings = get_settings()
    try:
        database_url = decrypt_connector_database_url(config, project_id=tenant_id)
        if not database_url:
            raise ValueError("PostgreSQL database URL is not configured.")
        connector = build_postgres_read_connector(
            config,
            database_url=database_url,
            params=body.params,
            timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
            allow_private_hosts=settings.OUTCOME_CONNECTOR_ALLOW_PRIVATE_HOSTS,
        )
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
            idempotency_key=_saved_postgres_read_idempotency_key(
                body,
                read_query=config.read_query,
            ),
            metadata={
                **(body.metadata or {}),
                "connector_kind": POSTGRES_READ_CONNECTOR_TYPE,
                "connector_config_id": config.id,
                "source": "saved_connector_runtime",
            },
        )
    except (
        ConnectorConfigError,
        EnvelopeFormatError,
        VaultCipherUnavailable,
        ValueError,
    ) as exc:
        raise _map_saved_connector_error(exc) from exc

    return _serialize_reconciliation(row)


