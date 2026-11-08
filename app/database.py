from pathlib import Path
from typing import Generator

from sqlalchemy import URL, create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.models import Base


PROJECT_FOLDER = Path(__file__).resolve().parent.parent
DATABASE_PATH = PROJECT_FOLDER / "serie_a.db"


def create_database_engine(database_path: Path = DATABASE_PATH) -> Engine:
    """Create a SQLite engine for the given file."""
    database_url = URL.create(
        "sqlite",
        database=str(database_path.resolve()),
    )
    database_engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(database_engine, "connect")
    def enable_foreign_keys(connection, _connection_record) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return database_engine


engine = create_database_engine()


def create_database_session(database_engine: Engine = engine) -> Session:
    """Open a session for reading and writing database records."""
    return Session(bind=database_engine)


def get_database_session() -> Generator[Session, None, None]:
    """Provide a session and close it after the request is finished."""
    session = create_database_session()
    try:
        yield session
    finally:
        session.close()


def initialize_database(database_engine: Engine = engine) -> None:
    """Create any database tables that do not exist yet."""
    Base.metadata.create_all(bind=database_engine)
    _add_match_statistics_source_columns(database_engine)


def _add_match_statistics_source_columns(database_engine: Engine) -> None:
    """Add provider tracking to older databases without replacing saved rows."""
    columns = {
        column["name"]
        for column in inspect(database_engine).get_columns("match_statistics")
    }
    with database_engine.begin() as connection:
        if "source" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE match_statistics "
                    "ADD COLUMN source VARCHAR(40) NOT NULL DEFAULT 'unknown'"
                )
            )
        if "provider_match_id" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE match_statistics "
                    "ADD COLUMN provider_match_id VARCHAR(100)"
                )
            )
