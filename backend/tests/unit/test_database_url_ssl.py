from backend.app.config.settings import normalize_database_url
from backend.app.db.session import _prepare_asyncpg_url


def test_postgres_ssl_query_is_normalized_for_psycopg2() -> None:
    assert (
        normalize_database_url("postgresql://user:pass@host/db?ssl=true")
        == "postgresql+asyncpg://user:pass@host/db?sslmode=require"
    )
    assert (
        normalize_database_url("postgresql://user:pass@host/db?ssl=false")
        == "postgresql+asyncpg://user:pass@host/db?sslmode=disable"
    )


def test_asyncpg_url_removes_libpq_ssl_options() -> None:
    database_url, connect_args = _prepare_asyncpg_url(
        "postgresql+asyncpg://user:pass@host/db?sslmode=require&channel_binding=require"
    )

    assert database_url == "postgresql+asyncpg://user:pass@host/db"
    assert connect_args == {"ssl": True}


def test_asyncpg_sslmode_disable_does_not_enable_ssl_arg() -> None:
    database_url, connect_args = _prepare_asyncpg_url(
        "postgresql+asyncpg://user:pass@host/db?sslmode=disable"
    )

    assert database_url == "postgresql+asyncpg://user:pass@host/db"
    assert connect_args == {}
