def normalize_sqlalchemy_database_url(url: str) -> str:
    """Return a SQLAlchemy URL that uses the installed PostgreSQL driver."""
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    return url
