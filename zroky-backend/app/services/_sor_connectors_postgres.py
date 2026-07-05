from __future__ import annotations

from app.services._sor_connectors_core import *  # noqa: F403


@dataclass(frozen=True)
class PostgresReadOnlyConnector:
    """Read one source-of-record row through a constrained PostgreSQL query."""

    database_url: str
    query: str
    params: Mapping[str, Any] | None = None
    timeout_seconds: float = 5.0
    allow_private_hosts: bool = False
    allow_sqlite_for_tests: bool = False
    fail_closed_config_errors: bool = False
    connector_type: str = "postgres_read"

    def _validated(self) -> tuple[str, str, dict[str, str | int | float | bool | None]]:
        database_url = _safe_database_url(
            self.database_url,
            allow_private_hosts=self.allow_private_hosts,
            allow_sqlite_for_tests=self.allow_sqlite_for_tests,
        )
        query = validate_postgres_read_query(self.query)
        params = _normalize_sql_params(self.params)
        return database_url, query, params

    def fetch(self) -> SourceRecord:
        try:
            database_url, query, params = self._validated()
        except ConnectorConfigError:
            if not self.fail_closed_config_errors:
                raise
            safe_url = "postgres_connector_url_unavailable"
            safe_query = self.query or "postgres_connector_query_unavailable"
            return SourceRecord(
                record=None,
                record_found=None,
                metadata=_database_metadata(
                    connector_type=self.connector_type,
                    database_url=safe_url,
                    query=safe_query,
                    error="connector_config_error",
                    error_code="connector_config_invalid",
                    attempts=0,
                    timeout_seconds=self.timeout_seconds,
                    retryable=False,
                ),
            )

        engine = None
        try:
            connect_args: dict[str, Any] = {}
            if not self.allow_sqlite_for_tests:
                connect_args["connect_timeout"] = max(1, int(self.timeout_seconds))
            engine = create_engine(
                database_url,
                future=True,
                pool_pre_ping=False,
                connect_args=connect_args,
            )
            with engine.connect() as connection:
                with connection.begin():
                    if connection.dialect.name == "postgresql":
                        connection.execute(sql_text("SET TRANSACTION READ ONLY"))
                    result = connection.execute(sql_text(query), params)
                    row = result.mappings().first()
        except SQLAlchemyError as exc:
            return SourceRecord(
                record=None,
                record_found=None,
                metadata=_database_metadata(
                    connector_type=self.connector_type,
                    database_url=database_url,
                    query=query,
                    error=exc.__class__.__name__,
                    error_code=_sql_error_code(exc),
                    attempts=1,
                    timeout_seconds=self.timeout_seconds,
                    retryable=_sql_error_retryable(exc),
                ),
            )
        finally:
            if engine is not None:
                engine.dispose()

        if row is None:
            return SourceRecord(
                record=None,
                record_found=False,
                metadata=_database_metadata(
                    connector_type=self.connector_type,
                    database_url=database_url,
                    query=query,
                    attempts=1,
                    timeout_seconds=self.timeout_seconds,
                    retryable=False,
                    record_found=False,
                ),
            )

        record = _json_safe(dict(row))
        return SourceRecord(
            record=record,
            record_found=True,
            metadata=_database_metadata(
                connector_type=self.connector_type,
                database_url=database_url,
                query=query,
                attempts=1,
                timeout_seconds=self.timeout_seconds,
                retryable=False,
                record_found=True,
            ),
        )
