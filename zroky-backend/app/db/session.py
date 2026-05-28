from typing import Any

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.url import normalize_sqlalchemy_database_url

settings = get_settings()


def _inject_search_path(url: str) -> str:
    """Append search_path=public to PostgreSQL connection URLs.

    Railway (and many hosted providers) configure a non-public default
    search_path at the database level.  Embedding it in the URL is the
    most reliable way to override it — it is handled by the driver's own
    connection-string parser before SQLAlchemy adds anything else.
    """
    if not url.startswith("postgresql"):
        return url
    if "search_path" in url:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}options=-c%20search_path%3Dpublic"


def _build_engine_kwargs(url: str) -> dict[str, Any]:
    """Build SQLAlchemy engine kwargs with connection pool tuning per dialect."""
    kwargs: dict[str, Any] = {"pool_pre_ping": True, "future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # Postgres / MySQL — apply pool sizing.
        kwargs["pool_size"] = settings.DB_POOL_SIZE
        kwargs["max_overflow"] = settings.DB_MAX_OVERFLOW
        kwargs["pool_timeout"] = settings.DB_POOL_TIMEOUT_SECONDS
        kwargs["pool_recycle"] = settings.DB_POOL_RECYCLE_SECONDS
    return kwargs


def _attach_statement_timeout(target_engine: Engine) -> None:
    """Apply a per-connection ``statement_timeout`` on Postgres."""
    if target_engine.dialect.name != "postgresql":
        return
    timeout_ms = settings.DB_STATEMENT_TIMEOUT_MS
    if timeout_ms <= 0:
        return

    @event.listens_for(target_engine, "connect")
    def _set_statement_timeout(dbapi_conn, _connection_record):  # noqa: ANN001
        cursor = dbapi_conn.cursor()
        try:
            cursor.execute(f"SET statement_timeout TO {int(timeout_ms)}")
        finally:
            cursor.close()


def _attach_search_path(target_engine: Engine) -> None:
    """Ensure search_path=public on every Postgres connection.

    Railway (and some managed Postgres providers) set a non-public default
    search_path. This makes all tables created by Alembic (which explicitly
    sets search_path=public) invisible to the app engine.
    """
    if target_engine.dialect.name != "postgresql":
        return

    @event.listens_for(target_engine, "connect")
    def _set_search_path(dbapi_conn, _connection_record):  # noqa: ANN001
        cursor = dbapi_conn.cursor()
        try:
            cursor.execute("SET search_path TO public")
        finally:
            cursor.close()


_db_url = _inject_search_path(normalize_sqlalchemy_database_url(settings.DATABASE_URL))
engine = create_engine(_db_url, **_build_engine_kwargs(_db_url))
_attach_search_path(engine)
_attach_statement_timeout(engine)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

_read_url = _inject_search_path(
    normalize_sqlalchemy_database_url(settings.DATABASE_READ_REPLICA_URL or settings.DATABASE_URL)
)
read_engine = create_engine(_read_url, **_build_engine_kwargs(_read_url))
_attach_search_path(read_engine)
_attach_statement_timeout(read_engine)
SessionLocalRead = sessionmaker(bind=read_engine, autoflush=False, autocommit=False, future=True)


def set_db_tenant_context(db: Session, tenant_id: str) -> None:
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return

    db.info["tenant_id"] = tenant_id
    db.execute(
        text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
        {"tenant_id": tenant_id},
    )


@event.listens_for(Session, "after_begin")
def _apply_tenant_context_on_new_transaction(
    session: Session,
    _transaction,
    connection,
) -> None:
    tenant_id = session.info.get("tenant_id")
    if not tenant_id:
        return
    if connection.dialect.name != "postgresql":
        return

    connection.execute(
        text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
        {"tenant_id": tenant_id},
    )


def get_db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_db_session_read():
    """Yield a session bound to the read-replica engine.

    When ``DATABASE_READ_REPLICA_URL`` is unset, this transparently falls back
    to the primary engine so the same dependency works in all environments.
    """
    session = SessionLocalRead()
    try:
        yield session
    finally:
        session.close()


def db_healthcheck() -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        return False
