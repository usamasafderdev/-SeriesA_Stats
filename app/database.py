from pathlib import Path
import os
from typing import Generator

from sqlalchemy import URL, create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.models import Base


PROJECT_FOLDER = Path(__file__).resolve().parent.parent
DATABASE_PATH = Path(os.getenv("SERIE_A_DATABASE", str(PROJECT_FOLDER / "serie_a.db")))


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
    _add_provider_identity_columns(database_engine)
    _add_detail_provenance_columns(database_engine)


def _add_detail_provenance_columns(database_engine: Engine) -> None:
    additions = {
        "match_events": {"added_minute": "INTEGER", "source": "VARCHAR(40)"},
        "match_lineups": {"source": "VARCHAR(40)", "provider_match_id": "VARCHAR(100)",
                          "fetched_at": "DATETIME"},
    }
    with database_engine.begin() as connection:
        for table, fields in additions.items():
            existing = {column["name"] for column in inspect(connection).get_columns(table)}
            for name, kind in fields.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {kind}"))


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


def _add_provider_identity_columns(database_engine: Engine) -> None:
    """Add BBS identities and refresh timestamps without replacing saved rows."""
    table_columns = {
        table_name: {
            column["name"]
            for column in inspect(database_engine).get_columns(table_name)
        }
        for table_name in ("teams", "matches", "match_statistics")
    }
    additions = {
        "teams": {"bbs_team_id": "VARCHAR(100)"},
        "matches": {
            "bbs_match_id": "VARCHAR(100)",
            "fetched_at": "DATETIME",
            "kickoff_time_available": "BOOLEAN NOT NULL DEFAULT 1",
            "round_name": "VARCHAR(80)",
        },
        "match_statistics": {"fetched_at": "DATETIME"},
    }
    with database_engine.begin() as connection:
        for table_name, columns in additions.items():
            for column_name, column_type in columns.items():
                if column_name not in table_columns[table_name]:
                    connection.execute(
                        text(
                            f"ALTER TABLE {table_name} "
                            f"ADD COLUMN {column_name} {column_type}"
                        )
                    )
        for table_name, column_name in (
            ("teams", "football_data_team_id"),
            ("matches", "football_data_match_id"),
            ("matches", "highlightly_match_id"),
        ):
            columns = {
                column["name"]
                for column in inspect(database_engine).get_columns(table_name)
            }
            if column_name not in columns:
                connection.execute(
                    text(
                        f"ALTER TABLE {table_name} "
                        f"ADD COLUMN {column_name} VARCHAR(100)"
                    )
                )
        lineup_columns = {
            column["name"]
            for column in inspect(database_engine).get_columns("lineup_players")
        }
        for column_name, column_type in {
            "rating": "FLOAT",
            "minutes_played": "INTEGER",
            "shots_total": "INTEGER",
            "shots_on_target": "INTEGER",
            "shots_off_target": "INTEGER",
            "passes_total": "INTEGER",
            "passes_successful": "INTEGER",
            "passes_accuracy": "FLOAT",
            "passes_key": "INTEGER",
            "tackles_total": "INTEGER",
            "interceptions_total": "INTEGER",
            "dribbles_total": "INTEGER",
            "dribbles_successful": "INTEGER",
            "duels_total": "INTEGER",
            "duels_won": "INTEGER",
            "fouls_committed": "INTEGER",
            "fouls_drawn": "INTEGER",
            "goalkeeper_saves": "INTEGER",
        }.items():
            if column_name not in lineup_columns:
                connection.execute(
                    text(
                        f"ALTER TABLE lineup_players ADD COLUMN "
                        f"{column_name} {column_type}"
                    )
                )
        statistics_columns = {
            column["name"]
            for column in inspect(database_engine).get_columns("match_statistics")
        }
        if "highlightly_match_id" not in statistics_columns:
            connection.execute(
                text(
                    "ALTER TABLE match_statistics "
                    "ADD COLUMN highlightly_match_id VARCHAR(100)"
                )
            )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_teams_bbs_team_id "
                "ON teams (bbs_team_id) WHERE bbs_team_id IS NOT NULL"
            )
        )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_matches_bbs_match_id "
                "ON matches (bbs_match_id) WHERE bbs_match_id IS NOT NULL"
            )
        )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_teams_football_data_id "
                "ON teams (football_data_team_id) "
                "WHERE football_data_team_id IS NOT NULL"
            )
        )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_matches_football_data_id "
                "ON matches (football_data_match_id) "
                "WHERE football_data_match_id IS NOT NULL"
            )
        )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_matches_highlightly_id "
                "ON matches (highlightly_match_id) "
                "WHERE highlightly_match_id IS NOT NULL"
            )
        )
