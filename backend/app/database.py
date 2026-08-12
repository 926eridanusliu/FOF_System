import os
from collections.abc import Generator
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.storage import DATA_DIR


BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
DEFAULT_DATABASE_URL = f"sqlite:///{DATA_DIR / 'fof_reports.db'}"


def resolve_database_url(value: str | None) -> str:
    """Resolve a relative SQLite URL against backend/, not the shell directory."""
    if not value:
        return DEFAULT_DATABASE_URL
    relative_prefix = "sqlite:///./"
    if value.startswith(relative_prefix):
        database_path = (BACKEND_DIR / value.removeprefix(relative_prefix)).resolve()
        return f"sqlite:///{database_path}"
    return value


DATABASE_URL = resolve_database_url(os.getenv("DATABASE_URL"))

# SQLite only permits a connection to be used in the thread that created it by
# default. FastAPI may execute request handlers in different worker threads.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)


if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Base class inherited by all SQLAlchemy database models."""


def upgrade_existing_schema() -> None:
    """Apply the small, backwards-compatible upgrade needed by existing installs."""
    inspector = inspect(engine)
    if "report_invitations" not in inspector.get_table_names():
        return
    columns = {item["name"] for item in inspector.get_columns("report_invitations")}
    if "can_edit" not in columns:
        default = "1" if DATABASE_URL.startswith("sqlite") else "TRUE"
        with engine.begin() as connection:
            connection.execute(text(
                f"ALTER TABLE report_invitations ADD COLUMN can_edit BOOLEAN NOT NULL DEFAULT {default}"
            ))


def get_db() -> Generator[Session, None, None]:
    """Provide one database session per request and always close it afterward."""
    database = SessionLocal()
    try:
        yield database
    finally:
        database.close()
