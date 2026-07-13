from __future__ import annotations

from app.services.connectors.sor.config.core import *  # noqa: F403


def upsert_hubspot_crm_connector_config(
    db: Session,
    *,
    project_id: str,
    path_template: str = "/crm/v3/objects/contacts/{record_ref}",
    record_path: str | None = None,
    query: Mapping[str, Any] | None = None,
    bearer_token: str | None = None,
    clear_bearer_token: bool = False,
    updated_by_subject: str | None = None,
) -> SystemOfRecordConnectorConfig:
    try:
        normalized = validate_hubspot_crm_config(
            path_template=path_template,
            record_path=record_path,
        )
    except ConnectorConfigError as exc:
        raise InvalidSystemOfRecordConnectorError(str(exc)) from exc

    normalized_query = {
        **_HUBSPOT_DEFAULT_QUERY,
        **(_normalize_query(query) or {}),
    }
    enforce_system_of_record_connector_limit(
        db,
        project_id,
        connector_type=HUBSPOT_CRM_CONNECTOR_TYPE,
    )
    row = get_connector_config(
        db, project_id=project_id, connector_type=HUBSPOT_CRM_CONNECTOR_TYPE
    )
    now = datetime.now(timezone.utc)
    if row is None:
        row = SystemOfRecordConnectorConfig(
            id=str(uuid4()),
            project_id=project_id,
            connector_type=HUBSPOT_CRM_CONNECTOR_TYPE,
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


def upsert_zendesk_ticket_connector_config(
    db: Session,
    *,
    project_id: str,
    base_url: str,
    path_template: str = "/api/v2/tickets/{record_ref}.json",
    record_path: str | None = "ticket",
    query: Mapping[str, Any] | None = None,
    auth_username: str | None = None,
    bearer_token: str | None = None,
    clear_bearer_token: bool = False,
    updated_by_subject: str | None = None,
) -> SystemOfRecordConnectorConfig:
    try:
        normalized = validate_zendesk_ticket_config(
            base_url=base_url,
            path_template=path_template,
            record_path=record_path,
        )
    except ConnectorConfigError as exc:
        raise InvalidSystemOfRecordConnectorError(str(exc)) from exc

    normalized_query = _normalize_query(query) or {}
    cleaned_username = (auth_username or "").strip()
    if cleaned_username:
        normalized_query["auth_username"] = cleaned_username
    enforce_system_of_record_connector_limit(
        db,
        project_id,
        connector_type=ZENDESK_TICKET_CONNECTOR_TYPE,
    )
    row = get_connector_config(
        db, project_id=project_id, connector_type=ZENDESK_TICKET_CONNECTOR_TYPE
    )
    now = datetime.now(timezone.utc)
    if row is None:
        row = SystemOfRecordConnectorConfig(
            id=str(uuid4()),
            project_id=project_id,
            connector_type=ZENDESK_TICKET_CONNECTOR_TYPE,
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


def upsert_jira_issue_connector_config(
    db: Session,
    *,
    project_id: str,
    base_url: str,
    path_template: str = "/rest/api/3/issue/{record_ref}",
    record_path: str | None = None,
    query: Mapping[str, Any] | None = None,
    auth_username: str | None = None,
    bearer_token: str | None = None,
    clear_bearer_token: bool = False,
    oauth_refresh_token: str | None = None,
    clear_oauth_refresh_token: bool = False,
    updated_by_subject: str | None = None,
) -> SystemOfRecordConnectorConfig:
    try:
        normalized = validate_jira_issue_config(
            base_url=base_url,
            path_template=path_template,
            record_path=record_path,
        )
    except ConnectorConfigError as exc:
        raise InvalidSystemOfRecordConnectorError(str(exc)) from exc

    normalized_query = {
        **_JIRA_DEFAULT_QUERY,
        **(_normalize_query(query) or {}),
    }
    cleaned_username = (auth_username or "").strip()
    if cleaned_username:
        normalized_query["auth_username"] = cleaned_username
    enforce_system_of_record_connector_limit(
        db,
        project_id,
        connector_type=JIRA_ISSUE_CONNECTOR_TYPE,
    )
    row = get_connector_config(
        db, project_id=project_id, connector_type=JIRA_ISSUE_CONNECTOR_TYPE
    )
    now = datetime.now(timezone.utc)
    if row is None:
        row = SystemOfRecordConnectorConfig(
            id=str(uuid4()),
            project_id=project_id,
            connector_type=JIRA_ISSUE_CONNECTOR_TYPE,
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

    if clear_oauth_refresh_token:
        row.oauth_refresh_token_ciphertext = None
        row.oauth_refresh_token_fingerprint = None
        row.oauth_refresh_token_last4 = None
    elif oauth_refresh_token is not None:
        cleaned_refresh = oauth_refresh_token.strip()
        if not cleaned_refresh:
            raise InvalidSystemOfRecordConnectorError(
                "oauth_refresh_token must not be empty when provided"
            )
        refresh_bundle = encrypt_provider_key(
            plaintext=cleaned_refresh,
            project_id=project_id,
        )
        row.oauth_refresh_token_ciphertext = refresh_bundle.ciphertext
        row.oauth_refresh_token_fingerprint = refresh_bundle.key_fingerprint
        row.oauth_refresh_token_last4 = refresh_bundle.key_last4
        row.kms_key_id = refresh_bundle.kms_key_id

    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def upsert_salesforce_crm_connector_config(
    db: Session,
    *,
    project_id: str,
    base_url: str,
    path_template: str = "/services/data/v60.0/sobjects/{object_type}/{record_ref}",
    record_path: str | None = None,
    query: Mapping[str, Any] | None = None,
    bearer_token: str | None = None,
    clear_bearer_token: bool = False,
    updated_by_subject: str | None = None,
) -> SystemOfRecordConnectorConfig:
    try:
        normalized = validate_salesforce_crm_config(
            base_url=base_url,
            path_template=path_template,
            record_path=record_path,
        )
    except ConnectorConfigError as exc:
        raise InvalidSystemOfRecordConnectorError(str(exc)) from exc

    normalized_query = {
        **_SALESFORCE_DEFAULT_QUERY,
        **(_normalize_query(query) or {}),
    }
    enforce_system_of_record_connector_limit(
        db,
        project_id,
        connector_type=SALESFORCE_CRM_CONNECTOR_TYPE,
    )
    row = get_connector_config(
        db, project_id=project_id, connector_type=SALESFORCE_CRM_CONNECTOR_TYPE
    )
    now = datetime.now(timezone.utc)
    if row is None:
        row = SystemOfRecordConnectorConfig(
            id=str(uuid4()),
            project_id=project_id,
            connector_type=SALESFORCE_CRM_CONNECTOR_TYPE,
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


def upsert_zoho_crm_connector_config(
    db: Session,
    *,
    project_id: str,
    base_url: str = "https://www.zohoapis.com",
    path_template: str = "/crm/v8/{module_name}/{record_ref}",
    record_path: str | None = "data.0",
    query: Mapping[str, Any] | None = None,
    bearer_token: str | None = None,
    clear_bearer_token: bool = False,
    oauth_refresh_token: str | None = None,
    clear_oauth_refresh_token: bool = False,
    updated_by_subject: str | None = None,
) -> SystemOfRecordConnectorConfig:
    try:
        normalized = validate_zoho_crm_config(
            base_url=base_url,
            path_template=path_template,
            record_path=record_path,
        )
    except ConnectorConfigError as exc:
        raise InvalidSystemOfRecordConnectorError(str(exc)) from exc

    normalized_query = {
        **_ZOHO_DEFAULT_QUERY,
        **(_normalize_query(query) or {}),
    }
    enforce_system_of_record_connector_limit(
        db,
        project_id,
        connector_type=ZOHO_CRM_CONNECTOR_TYPE,
    )
    row = get_connector_config(
        db, project_id=project_id, connector_type=ZOHO_CRM_CONNECTOR_TYPE
    )
    now = datetime.now(timezone.utc)
    if row is None:
        row = SystemOfRecordConnectorConfig(
            id=str(uuid4()),
            project_id=project_id,
            connector_type=ZOHO_CRM_CONNECTOR_TYPE,
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

    if clear_oauth_refresh_token:
        row.oauth_refresh_token_ciphertext = None
        row.oauth_refresh_token_fingerprint = None
        row.oauth_refresh_token_last4 = None
    elif oauth_refresh_token is not None:
        cleaned_refresh = oauth_refresh_token.strip()
        if not cleaned_refresh:
            raise InvalidSystemOfRecordConnectorError(
                "oauth_refresh_token must not be empty when provided"
            )
        refresh_bundle = encrypt_provider_key(
            plaintext=cleaned_refresh,
            project_id=project_id,
        )
        row.oauth_refresh_token_ciphertext = refresh_bundle.ciphertext
        row.oauth_refresh_token_fingerprint = refresh_bundle.key_fingerprint
        row.oauth_refresh_token_last4 = refresh_bundle.key_last4
        row.kms_key_id = refresh_bundle.kms_key_id

    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def upsert_netsuite_finance_connector_config(
    db: Session,
    *,
    project_id: str,
    base_url: str,
    path_template: str = "/services/rest/record/v1/{record_type}/{record_ref}",
    record_path: str | None = None,
    query: Mapping[str, Any] | None = None,
    bearer_token: str | None = None,
    clear_bearer_token: bool = False,
    updated_by_subject: str | None = None,
) -> SystemOfRecordConnectorConfig:
    try:
        normalized = validate_netsuite_finance_config(
            base_url=base_url,
            path_template=path_template,
            record_path=record_path,
        )
    except ConnectorConfigError as exc:
        raise InvalidSystemOfRecordConnectorError(str(exc)) from exc

    normalized_query = {
        **_NETSUITE_DEFAULT_QUERY,
        **(_normalize_query(query) or {}),
    }
    enforce_system_of_record_connector_limit(
        db,
        project_id,
        connector_type=NETSUITE_FINANCE_CONNECTOR_TYPE,
    )
    row = get_connector_config(
        db, project_id=project_id, connector_type=NETSUITE_FINANCE_CONNECTOR_TYPE
    )
    now = datetime.now(timezone.utc)
    if row is None:
        row = SystemOfRecordConnectorConfig(
            id=str(uuid4()),
            project_id=project_id,
            connector_type=NETSUITE_FINANCE_CONNECTOR_TYPE,
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


def upsert_postgres_read_connector_config(
    db: Session,
    *,
    project_id: str,
    database_url: str | None = None,
    read_query: str,
    clear_database_url: bool = False,
    updated_by_subject: str | None = None,
    allow_private_hosts: bool = False,
) -> SystemOfRecordConnectorConfig:
    row = get_connector_config(
        db, project_id=project_id, connector_type=POSTGRES_READ_CONNECTOR_TYPE
    )
    if row is None and not database_url:
        raise InvalidSystemOfRecordConnectorError("database_url is required")
    if clear_database_url:
        raise InvalidSystemOfRecordConnectorError(
            "database_url cannot be cleared for an active PostgreSQL connector"
        )

    normalized_query: str
    public_database_url = row.base_url if row is not None else None
    normalized_database_url: str | None = None
    if database_url is not None:
        try:
            normalized = validate_postgres_read_config(
                database_url=database_url,
                read_query=read_query,
                allow_private_hosts=allow_private_hosts,
            )
        except ConnectorConfigError as exc:
            raise InvalidSystemOfRecordConnectorError(str(exc)) from exc
        normalized_database_url = normalized["database_url"]
        public_database_url = normalized["public_database_url"]
        normalized_query = normalized["read_query"]
    else:
        try:
            normalized = validate_postgres_read_config(
                database_url="postgresql://placeholder.example.com/placeholder",
                read_query=read_query,
                allow_private_hosts=True,
            )
        except ConnectorConfigError as exc:
            raise InvalidSystemOfRecordConnectorError(str(exc)) from exc
        normalized_query = normalized["read_query"]

    enforce_system_of_record_connector_limit(
        db,
        project_id,
        connector_type=POSTGRES_READ_CONNECTOR_TYPE,
    )
    now = datetime.now(timezone.utc)
    if row is None:
        row = SystemOfRecordConnectorConfig(
            id=str(uuid4()),
            project_id=project_id,
            connector_type=POSTGRES_READ_CONNECTOR_TYPE,
            created_by_subject=updated_by_subject,
            created_at=now,
        )

    row.base_url = public_database_url or "postgresql://source-record"
    row.path_template = "/"
    row.record_path = None
    row.query_json = None
    row.read_query = normalized_query
    row.updated_by_subject = updated_by_subject
    row.updated_at = now
    row.is_active = True

    if normalized_database_url is not None:
        bundle = encrypt_provider_key(
            plaintext=normalized_database_url,
            project_id=project_id,
        )
        row.database_url_ciphertext = bundle.ciphertext
        row.database_url_fingerprint = bundle.key_fingerprint
        row.database_url_last4 = bundle.key_last4
        row.kms_key_id = bundle.kms_key_id

    db.add(row)
    db.commit()
    db.refresh(row)
    return row
