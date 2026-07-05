from __future__ import annotations

from app.services._sor_connector_config_core import *  # noqa: F403


def build_stripe_payment_connector(
    row: SystemOfRecordConnectorConfig,
    *,
    payment_id: str,
    bearer_token: str | None,
    timeout_seconds: float,
    max_attempts: int,
) -> StripePaymentConnector:
    return StripePaymentConnector(
        payment_id=payment_id,
        bearer_token=bearer_token,
        base_url=row.base_url or "https://api.stripe.com",
        path_template=row.path_template or "/v1/payment_intents/{record_ref}",
        query=_json_loads(row.query_json),
        record_path=row.record_path,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        fail_closed_config_errors=True,
    )


def build_shopify_admin_connector(
    row: SystemOfRecordConnectorConfig,
    *,
    record_ref: str,
    bearer_token: str | None,
    timeout_seconds: float,
    max_attempts: int,
) -> ShopifyAdminConnector:
    return ShopifyAdminConnector(
        record_ref=record_ref,
        bearer_token=bearer_token,
        base_url=row.base_url or "https://example.myshopify.com",
        path_template=row.path_template or "/admin/api/2025-01/orders/{record_ref}.json",
        query=_json_loads(row.query_json),
        record_path=row.record_path or "order",
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        fail_closed_config_errors=True,
    )


def upsert_stripe_payment_connector_config(
    db: Session,
    *,
    project_id: str,
    base_url: str = "https://api.stripe.com",
    path_template: str = "/v1/payment_intents/{record_ref}",
    record_path: str | None = None,
    query: Mapping[str, Any] | None = None,
    bearer_token: str | None = None,
    clear_bearer_token: bool = False,
    updated_by_subject: str | None = None,
) -> SystemOfRecordConnectorConfig:
    try:
        normalized = validate_generic_rest_api_config(
            base_url=base_url,
            path_template=path_template,
            record_path=record_path,
        )
    except ConnectorConfigError as exc:
        raise InvalidSystemOfRecordConnectorError(str(exc)) from exc

    return _upsert_bearer_http_connector(
        db,
        project_id=project_id,
        connector_type=STRIPE_PAYMENT_CONNECTOR_TYPE,
        normalized=normalized,
        query=query,
        bearer_token=bearer_token,
        clear_bearer_token=clear_bearer_token,
        updated_by_subject=updated_by_subject,
    )


def upsert_shopify_admin_connector_config(
    db: Session,
    *,
    project_id: str,
    base_url: str,
    path_template: str = "/admin/api/2025-01/orders/{record_ref}.json",
    record_path: str | None = "order",
    query: Mapping[str, Any] | None = None,
    bearer_token: str | None = None,
    clear_bearer_token: bool = False,
    updated_by_subject: str | None = None,
) -> SystemOfRecordConnectorConfig:
    try:
        normalized = validate_generic_rest_api_config(
            base_url=base_url,
            path_template=path_template,
            record_path=record_path,
        )
    except ConnectorConfigError as exc:
        raise InvalidSystemOfRecordConnectorError(str(exc)) from exc

    return _upsert_bearer_http_connector(
        db,
        project_id=project_id,
        connector_type=SHOPIFY_ADMIN_CONNECTOR_TYPE,
        normalized=normalized,
        query=query,
        bearer_token=bearer_token,
        clear_bearer_token=clear_bearer_token,
        updated_by_subject=updated_by_subject,
    )


def _upsert_bearer_http_connector(
    db: Session,
    *,
    project_id: str,
    connector_type: str,
    normalized: Mapping[str, Any],
    query: Mapping[str, Any] | None,
    bearer_token: str | None,
    clear_bearer_token: bool,
    updated_by_subject: str | None,
) -> SystemOfRecordConnectorConfig:
    normalized_query = _normalize_query(query)
    enforce_system_of_record_connector_limit(
        db,
        project_id,
        connector_type=connector_type,
    )
    row = get_connector_config(db, project_id=project_id, connector_type=connector_type)
    now = datetime.now(timezone.utc)
    if row is None:
        row = SystemOfRecordConnectorConfig(
            id=str(uuid4()),
            project_id=project_id,
            connector_type=connector_type,
            created_by_subject=updated_by_subject,
            created_at=now,
        )

    row.base_url = str(normalized["base_url"])
    row.path_template = str(normalized["path_template"])
    row.record_path = normalized["record_path"]
    row.query_json = _json_dumps(normalized_query)
    row.updated_by_subject = updated_by_subject
    row.updated_at = now
    row.is_active = True

    if clear_bearer_token:
        row.bearer_token_ciphertext = None
        row.bearer_token_fingerprint = None
        row.bearer_token_last4 = None
        row.kms_key_id = None
    elif bearer_token is not None:
        cleaned = bearer_token.strip()
        if not cleaned:
            raise InvalidSystemOfRecordConnectorError(
                "bearer_token must not be empty when provided"
            )
        bundle = encrypt_provider_key(plaintext=cleaned, project_id=project_id)
        row.bearer_token_ciphertext = bundle.ciphertext
        row.bearer_token_fingerprint = bundle.key_fingerprint
        row.bearer_token_last4 = bundle.key_last4
        row.kms_key_id = bundle.kms_key_id

    db.add(row)
    db.commit()
    db.refresh(row)
    return row


__all__ = [name for name in globals() if not name.startswith("__")]
