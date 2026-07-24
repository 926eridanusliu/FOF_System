from app.database import BACKEND_DIR, DEFAULT_DATABASE_URL, resolve_database_url


def test_database_url_uses_backend_default_when_unset() -> None:
    assert resolve_database_url(None) == DEFAULT_DATABASE_URL


def test_relative_sqlite_url_is_resolved_against_backend_directory() -> None:
    expected = f"sqlite:///{(BACKEND_DIR / 'custom.db').resolve()}"
    assert resolve_database_url("sqlite:///./custom.db") == expected


def test_external_database_url_is_preserved() -> None:
    url = "postgresql+psycopg://user:password@example.test/fof"
    assert resolve_database_url(url) == url
