from __future__ import annotations

from app.services.connectors.sor.config.core import *  # noqa: F403


def upsert_ledger_refund_connector_config(
    db: Session,
    *,
    project_id: str,
    base_url: str,
    path_template: str = "/refunds/{refund_id}",
    record_path: str | None = None,
    query: Mapping[str, Any] | None = None,
    bearer_token: str | None = None,
    clear_bearer_token: bool = False,
    updated_by_subject: str | None = None,
    allow_private_hosts: bool = False,
) -> SystemOfRecordConnectorConfig:
    try:
        normalized = validate_ledger_refund_api_config(
            base_url=base_url,
            path_template=path_template,
            record_path=record_path,
            allow_private_hosts=allow_private_hosts,
        )
    except ConnectorConfigError as exc:
        raise InvalidSystemOfRecordConnectorError(str(exc)) from exc

    normalized_query = _normalize_query(query)
    enforce_system_of_record_connector_limit(
        db,
        project_id,
        connector_type=LEDGER_REFUND_CONNECTOR_TYPE,
    )
    row = get_connector_config(db, project_id=project_id)
    now = datetime.now(timezone.utc)
    if row is None:
        row = SystemOfRecordConnectorConfig(
            id=str(uuid4()),
            project_id=project_id,
            connector_type=LEDGER_REFUND_CONNECTOR_TYPE,
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


def upsert_stripe_refund_connector_config(
    db: Session,
    *,
    project_id: str,
    base_url: str = "https://api.stripe.com",
    path_template: str = "/v1/refunds/{refund_id}",
    record_path: str | None = None,
    query: Mapping[str, Any] | None = None,
    bearer_token: str | None = None,
    clear_bearer_token: bool = False,
    updated_by_subject: str | None = None,
) -> SystemOfRecordConnectorConfig:
    try:
        normalized = validate_stripe_refund_config(
            base_url=base_url,
            path_template=path_template,
            record_path=record_path,
        )
    except ConnectorConfigError as exc:
        raise InvalidSystemOfRecordConnectorError(str(exc)) from exc

    normalized_query = _normalize_query(query)
    enforce_system_of_record_connector_limit(
        db,
        project_id,
        connector_type=STRIPE_REFUND_CONNECTOR_TYPE,
    )
    row = get_connector_config(
        db, project_id=project_id, connector_type=STRIPE_REFUND_CONNECTOR_TYPE
    )
    now = datetime.now(timezone.utc)
    if row is None:
        row = SystemOfRecordConnectorConfig(
            id=str(uuid4()),
            project_id=project_id,
            connector_type=STRIPE_REFUND_CONNECTOR_TYPE,
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


def upsert_razorpay_refund_connector_config(
    db: Session,
    *,
    project_id: str,
    key_id: str,
    key_secret: str | None = None,
    base_url: str = "https://api.razorpay.com",
    path_template: str = "/v1/refunds/{refund_id}",
    record_path: str | None = None,
    query: Mapping[str, Any] | None = None,
    clear_key_secret: bool = False,
    updated_by_subject: str | None = None,
) -> SystemOfRecordConnectorConfig:
    try:
        normalized = validate_razorpay_refund_config(
            base_url=base_url,
            path_template=path_template,
            record_path=record_path,
        )
    except ConnectorConfigError as exc:
        raise InvalidSystemOfRecordConnectorError(str(exc)) from exc

    cleaned_key_id = key_id.strip()
    if len(cleaned_key_id) < 4:
        raise InvalidSystemOfRecordConnectorError("key_id must be at least 4 characters")
    normalized_query = {
        **(_normalize_query(query) or {}),
        "key_id": cleaned_key_id,
    }
    enforce_system_of_record_connector_limit(
        db,
        project_id,
        connector_type=RAZORPAY_REFUND_CONNECTOR_TYPE,
    )
    row = get_connector_config(
        db, project_id=project_id, connector_type=RAZORPAY_REFUND_CONNECTOR_TYPE
    )
    now = datetime.now(timezone.utc)
    if row is None:
        row = SystemOfRecordConnectorConfig(
            id=str(uuid4()),
            project_id=project_id,
            connector_type=RAZORPAY_REFUND_CONNECTOR_TYPE,
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

    if clear_key_secret:
        row.bearer_token_ciphertext = None
        row.bearer_token_fingerprint = None
        row.bearer_token_last4 = None
        row.kms_key_id = None
    elif key_secret is not None:
        cleaned_secret = key_secret.strip()
        if not cleaned_secret:
            raise InvalidSystemOfRecordConnectorError(
                "key_secret must not be empty when provided"
            )
        bundle = encrypt_provider_key(plaintext=cleaned_secret, project_id=project_id)
        row.bearer_token_ciphertext = bundle.ciphertext
        row.bearer_token_fingerprint = bundle.key_fingerprint
        row.bearer_token_last4 = bundle.key_last4
        row.kms_key_id = bundle.kms_key_id

    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def upsert_customer_record_connector_config(
    db: Session,
    *,
    project_id: str,
    base_url: str,
    path_template: str = "/customers/{customer_id}",
    record_path: str | None = None,
    query: Mapping[str, Any] | None = None,
    bearer_token: str | None = None,
    clear_bearer_token: bool = False,
    updated_by_subject: str | None = None,
    allow_private_hosts: bool = False,
) -> SystemOfRecordConnectorConfig:
    try:
        normalized = validate_customer_record_api_config(
            base_url=base_url,
            path_template=path_template,
            record_path=record_path,
            allow_private_hosts=allow_private_hosts,
        )
    except ConnectorConfigError as exc:
        raise InvalidSystemOfRecordConnectorError(str(exc)) from exc

    normalized_query = _normalize_query(query)
    enforce_system_of_record_connector_limit(
        db,
        project_id,
        connector_type=CUSTOMER_RECORD_CONNECTOR_TYPE,
    )
    row = get_connector_config(
        db, project_id=project_id, connector_type=CUSTOMER_RECORD_CONNECTOR_TYPE
    )
    now = datetime.now(timezone.utc)
    if row is None:
        row = SystemOfRecordConnectorConfig(
            id=str(uuid4()),
            project_id=project_id,
            connector_type=CUSTOMER_RECORD_CONNECTOR_TYPE,
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


def upsert_generic_rest_connector_config(
    db: Session,
    *,
    project_id: str,
    base_url: str,
    path_template: str = "/records/{record_ref}",
    record_path: str | None = None,
    query: Mapping[str, Any] | None = None,
    bearer_token: str | None = None,
    clear_bearer_token: bool = False,
    updated_by_subject: str | None = None,
    allow_private_hosts: bool = False,
) -> SystemOfRecordConnectorConfig:
    try:
        normalized = validate_generic_rest_api_config(
            base_url=base_url,
            path_template=path_template,
            record_path=record_path,
            allow_private_hosts=allow_private_hosts,
        )
    except ConnectorConfigError as exc:
        raise InvalidSystemOfRecordConnectorError(str(exc)) from exc

    normalized_query = _normalize_query(query)
    enforce_system_of_record_connector_limit(
        db,
        project_id,
        connector_type=GENERIC_REST_CONNECTOR_TYPE,
    )
    row = get_connector_config(
        db, project_id=project_id, connector_type=GENERIC_REST_CONNECTOR_TYPE
    )
    now = datetime.now(timezone.utc)
    if row is None:
        row = SystemOfRecordConnectorConfig(
            id=str(uuid4()),
            project_id=project_id,
            connector_type=GENERIC_REST_CONNECTOR_TYPE,
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
