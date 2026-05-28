from app.db.url import normalize_sqlalchemy_database_url


def test_driverless_postgresql_url_uses_psycopg_driver():
    assert (
        normalize_sqlalchemy_database_url("postgresql://user:pass@db.example.com:5432/app")
        == "postgresql+psycopg://user:pass@db.example.com:5432/app"
    )


def test_legacy_postgres_url_uses_psycopg_driver():
    assert (
        normalize_sqlalchemy_database_url("postgres://user:pass@db.example.com:5432/app")
        == "postgresql+psycopg://user:pass@db.example.com:5432/app"
    )


def test_explicit_driver_url_is_unchanged():
    url = "postgresql+psycopg://user:pass@db.example.com:5432/app"
    assert normalize_sqlalchemy_database_url(url) == url
