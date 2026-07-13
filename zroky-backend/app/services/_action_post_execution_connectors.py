from __future__ import annotations

from app.services._action_post_execution_core import *  # noqa: F403


def _saved_connector_for_context(
    *,
    db: Session,
    intent: ActionIntent,
    context: Mapping[str, Any],
) -> tuple[Any | None, str, str | None]:
    settings = get_settings()
    connector_type = _connector_alias(context.get("connector_type")) or GENERIC_REST_CONNECTOR_TYPE
    verification = _as_dict(context.get("verification"))
    target = _as_dict(context.get("target"))
    result = _as_dict(context.get("result"))
    claimed = _as_dict(context.get("claimed"))
    config = get_connector_config(db, project_id=intent.project_id, connector_type=connector_type)
    if config is None or not config.is_active:
        return None, connector_type, "connector_not_configured"

    if connector_type == LEDGER_REFUND_CONNECTOR_TYPE:
        refund_id = _text(verification.get("refund_id"), target.get("refund_id"), claimed.get("refund_id"), result.get("refund_id"))
        if refund_id is None:
            return None, connector_type, "refund_id_missing"
        bearer_token = decrypt_connector_bearer_token(config, project_id=intent.project_id, db=db)
        return (
            build_ledger_refund_connector(
                config,
                refund_id=refund_id,
                bearer_token=bearer_token,
                timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
                max_attempts=settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS,
                allow_private_hosts=settings.OUTCOME_CONNECTOR_ALLOW_PRIVATE_HOSTS,
            ),
            connector_type,
            None,
        )

    if connector_type == STRIPE_REFUND_CONNECTOR_TYPE:
        refund_id = _text(verification.get("refund_id"), target.get("refund_id"), claimed.get("refund_id"), result.get("refund_id"))
        if refund_id is None:
            return None, connector_type, "stripe_refund_id_missing"
        bearer_token = decrypt_connector_bearer_token(config, project_id=intent.project_id, db=db)
        return (
            build_stripe_refund_connector(
                config,
                refund_id=refund_id,
                bearer_token=bearer_token,
                timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
                max_attempts=settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS,
            ),
            connector_type,
            None,
        )

    if connector_type == RAZORPAY_REFUND_CONNECTOR_TYPE:
        refund_id = _text(
            verification.get("refund_id"),
            verification.get("razorpay_refund_id"),
            target.get("refund_id"),
            target.get("razorpay_refund_id"),
            claimed.get("refund_id"),
            claimed.get("razorpay_refund_id"),
            result.get("refund_id"),
            result.get("razorpay_refund_id"),
        )
        if refund_id is None:
            return None, connector_type, "razorpay_refund_id_missing"
        key_secret = decrypt_connector_bearer_token(config, project_id=intent.project_id, db=db)
        return (
            build_razorpay_refund_connector(
                config,
                refund_id=refund_id,
                key_secret=key_secret,
                timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
                max_attempts=settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS,
            ),
            connector_type,
            None,
        )

    if connector_type == CUSTOMER_RECORD_CONNECTOR_TYPE:
        customer_id = _text(verification.get("customer_id"), target.get("customer_id"), claimed.get("customer_id"), result.get("customer_id"))
        if customer_id is None:
            return None, connector_type, "customer_id_missing"
        bearer_token = decrypt_connector_bearer_token(config, project_id=intent.project_id, db=db)
        return (
            build_customer_record_connector(
                config,
                customer_id=customer_id,
                bearer_token=bearer_token,
                timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
                max_attempts=settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS,
                allow_private_hosts=settings.OUTCOME_CONNECTOR_ALLOW_PRIVATE_HOSTS,
            ),
            connector_type,
            None,
        )

    if connector_type == HUBSPOT_CRM_CONNECTOR_TYPE:
        record_ref = _text(
            verification.get("record_ref"),
            verification.get("contact_id"),
            verification.get("email"),
            target.get("record_ref"),
            target.get("contact_id"),
            target.get("email"),
            claimed.get("record_ref"),
            claimed.get("hs_object_id"),
            claimed.get("hubspot_id"),
            claimed.get("email"),
            result.get("record_ref"),
            result.get("provider_ref"),
        )
        if record_ref is None:
            return None, connector_type, "hubspot_record_ref_missing"
        bearer_token = decrypt_connector_bearer_token(config, project_id=intent.project_id, db=db)
        return (
            build_hubspot_crm_connector(
                config,
                record_ref=record_ref,
                bearer_token=bearer_token,
                timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
                max_attempts=settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS,
            ),
            connector_type,
            None,
        )

    if connector_type == ZENDESK_TICKET_CONNECTOR_TYPE:
        record_ref = _text(
            verification.get("record_ref"),
            verification.get("ticket_id"),
            target.get("record_ref"),
            target.get("ticket_id"),
            target.get("support_ticket_id"),
            claimed.get("record_ref"),
            claimed.get("ticket_id"),
            result.get("record_ref"),
            result.get("ticket_id"),
            result.get("provider_ref"),
        )
        if record_ref is None:
            return None, connector_type, "zendesk_ticket_ref_missing"
        bearer_token = decrypt_connector_bearer_token(config, project_id=intent.project_id, db=db)
        return (
            build_zendesk_ticket_connector(
                config,
                record_ref=record_ref,
                bearer_token=bearer_token,
                timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
                max_attempts=settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS,
            ),
            connector_type,
            None,
        )

    if connector_type == JIRA_ISSUE_CONNECTOR_TYPE:
        record_ref = _text(
            verification.get("record_ref"),
            verification.get("jira_issue_key"),
            verification.get("issue_key"),
            verification.get("ticket_id"),
            target.get("record_ref"),
            target.get("jira_issue_key"),
            target.get("issue_key"),
            target.get("ticket_id"),
            target.get("support_ticket_id"),
            claimed.get("record_ref"),
            claimed.get("jira_issue_key"),
            claimed.get("issue_key"),
            claimed.get("ticket_id"),
            result.get("record_ref"),
            result.get("jira_issue_key"),
            result.get("issue_key"),
            result.get("ticket_id"),
            result.get("provider_ref"),
        )
        if record_ref is None:
            return None, connector_type, "jira_issue_ref_missing"
        bearer_token = resolve_jira_bearer_token(
            config,
            project_id=intent.project_id,
            settings=settings,
            db=db,
        )
        return (
            build_jira_issue_connector(
                config,
                record_ref=record_ref,
                bearer_token=bearer_token,
                timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
                max_attempts=settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS,
            ),
            connector_type,
            None,
        )

    if connector_type == SALESFORCE_CRM_CONNECTOR_TYPE:
        object_type = _text(
            verification.get("object_type"),
            verification.get("salesforce_object"),
            target.get("object_type"),
            target.get("salesforce_object"),
            target.get("resource_type"),
            claimed.get("object_type"),
            claimed.get("salesforce_object"),
            result.get("object_type"),
            result.get("salesforce_object"),
        ) or "Account"
        record_ref = _text(
            verification.get("record_ref"),
            verification.get("salesforce_id"),
            target.get("record_ref"),
            target.get("salesforce_id"),
            target.get("resource_ref"),
            claimed.get("record_ref"),
            claimed.get("salesforce_id"),
            claimed.get("Id"),
            result.get("record_ref"),
            result.get("salesforce_id"),
            result.get("provider_ref"),
        )
        if record_ref is None:
            return None, connector_type, "salesforce_record_ref_missing"
        bearer_token = decrypt_connector_bearer_token(config, project_id=intent.project_id, db=db)
        return (
            build_salesforce_crm_connector(
                config,
                object_type=object_type,
                record_ref=record_ref,
                bearer_token=bearer_token,
                timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
                max_attempts=settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS,
            ),
            connector_type,
            None,
        )

    if connector_type == ZOHO_CRM_CONNECTOR_TYPE:
        module_name = _text(
            verification.get("module_name"),
            verification.get("zoho_module"),
            target.get("module_name"),
            target.get("zoho_module"),
            target.get("resource_type"),
            claimed.get("module_name"),
            claimed.get("zoho_module"),
            result.get("module_name"),
            result.get("zoho_module"),
        ) or "Contacts"
        record_ref = _text(
            verification.get("record_ref"),
            verification.get("zoho_record_id"),
            target.get("record_ref"),
            target.get("zoho_record_id"),
            target.get("resource_ref"),
            claimed.get("record_ref"),
            claimed.get("zoho_record_id"),
            claimed.get("id"),
            result.get("record_ref"),
            result.get("zoho_record_id"),
            result.get("provider_ref"),
        )
        if record_ref is None:
            return None, connector_type, "zoho_record_ref_missing"
        bearer_token = resolve_zoho_crm_bearer_token(
            config,
            project_id=intent.project_id,
            settings=settings,
            db=db,
        )
        return (
            build_zoho_crm_connector(
                config,
                module_name=module_name,
                record_ref=record_ref,
                bearer_token=bearer_token,
                timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
                max_attempts=settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS,
            ),
            connector_type,
            None,
        )

    if connector_type == NETSUITE_FINANCE_CONNECTOR_TYPE:
        record_type = _text(
            verification.get("record_type"),
            verification.get("netsuite_record_type"),
            target.get("record_type"),
            target.get("netsuite_record_type"),
            target.get("resource_type"),
            claimed.get("record_type"),
            claimed.get("netsuite_record_type"),
            result.get("record_type"),
            result.get("netsuite_record_type"),
        ) or "vendorBill"
        record_ref = _text(
            verification.get("record_ref"),
            verification.get("netsuite_record_id"),
            target.get("record_ref"),
            target.get("netsuite_record_id"),
            target.get("resource_ref"),
            claimed.get("record_ref"),
            claimed.get("netsuite_record_id"),
            claimed.get("id"),
            result.get("record_ref"),
            result.get("netsuite_record_id"),
            result.get("provider_ref"),
        )
        if record_ref is None:
            return None, connector_type, "netsuite_record_ref_missing"
        bearer_token = decrypt_connector_bearer_token(
            config, project_id=intent.project_id, db=db
        )
        return (
            build_netsuite_finance_connector(
                config,
                record_type=record_type,
                record_ref=record_ref,
                bearer_token=bearer_token,
                timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
                max_attempts=settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS,
            ),
            connector_type,
            None,
        )

    if connector_type == POSTGRES_READ_CONNECTOR_TYPE:
        if not config.read_query:
            return None, connector_type, "postgres_read_query_missing"
        database_url = decrypt_connector_database_url(config, project_id=intent.project_id, db=db)
        if not database_url:
            return None, connector_type, "postgres_database_url_missing"
        params = verification.get("params") if isinstance(verification.get("params"), Mapping) else result.get("params")
        return (
            build_postgres_read_connector(
                config,
                database_url=database_url,
                params=_as_dict(params),
                timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
                allow_private_hosts=settings.OUTCOME_CONNECTOR_ALLOW_PRIVATE_HOSTS,
            ),
            connector_type,
            None,
        )

    record_ref = _text(
        verification.get("record_ref"),
        target.get("record_ref"),
        target.get("resource_ref"),
        claimed.get("record_ref"),
        result.get("record_ref"),
        result.get("provider_ref"),
    )
    if record_ref is None:
        return None, GENERIC_REST_CONNECTOR_TYPE, "record_ref_missing"
    bearer_token = decrypt_connector_bearer_token(config, project_id=intent.project_id, db=db)
    return (
        build_generic_rest_connector(
            config,
            record_ref=record_ref,
            bearer_token=bearer_token,
            timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
            max_attempts=settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS,
            allow_private_hosts=settings.OUTCOME_CONNECTOR_ALLOW_PRIVATE_HOSTS,
        ),
        GENERIC_REST_CONNECTOR_TYPE,
        None,
    )


__all__ = [name for name in globals() if not name.startswith("__")]
