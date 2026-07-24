from app.database import BACKEND_DIR, DEFAULT_DATABASE_URL, resolve_database_url
from app import storage


def test_database_url_uses_backend_default_when_unset() -> None:
    assert resolve_database_url(None) == DEFAULT_DATABASE_URL


def test_relative_sqlite_url_is_resolved_against_backend_directory() -> None:
    expected = f"sqlite:///{(BACKEND_DIR / 'custom.db').resolve()}"
    assert resolve_database_url("sqlite:///./custom.db") == expected


def test_external_database_url_is_preserved() -> None:
    url = "postgresql+psycopg://user:password@example.test/fof"
    assert resolve_database_url(url) == url


def test_uploaded_image_paths_are_portable_and_stay_inside_upload_root(
    tmp_path, monkeypatch
) -> None:
    upload_root = tmp_path / "uploads"
    image = upload_root / "report-1" / "image.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"test")
    monkeypatch.setattr(storage, "UPLOAD_DIR", upload_root)

    reference = storage.upload_relative_path(image)
    assert reference == "report-1/image.png"
    assert storage.resolve_uploaded_image(reference) == image.resolve()
