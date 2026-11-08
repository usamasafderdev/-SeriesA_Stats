from datetime import datetime

import pytest
from sqlalchemy import inspect
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.database import (
    create_database_engine,
    create_database_session,
    initialize_database,
)
from app.match_service import (
    add_match,
    add_team,
    find_match_by_id,
    find_team_by_id,
    list_matches,
    save_or_update_match_statistics,
)
from app.models import MatchStatistics


@pytest.fixture
def database_session(tmp_path):
    """Create a fresh temporary database for each test."""
    database_engine = create_database_engine(tmp_path / "test_serie_a.db")
    initialize_database(database_engine)
    session = create_database_session(database_engine)

    try:
        yield session
    finally:
        session.close()
        database_engine.dispose()


def add_test_teams(session, data_source="demo"):
    home_team = add_team(session, "Home Team", data_source=data_source)
    away_team = add_team(session, "Away Team", data_source=data_source)
    return home_team, away_team


def add_test_match(session, home_team, away_team, **match_details):
    return add_match(
        session,
        season="2025",
        match_date=datetime(2025, 4, 22, 18, 0),
        home_team_id=home_team.id,
        away_team_id=away_team.id,
        **match_details,
    )


def test_database_tables_are_created(database_session):
    table_names = inspect(database_session.get_bind()).get_table_names()

    assert set(table_names) == {
        "teams",
        "matches",
        "match_statistics",
        "match_lineups",
        "lineup_players",
    }


def test_sqlite_foreign_keys_are_enabled(database_session):
    database_engine = database_session.get_bind()
    database_engine.dispose()
    with database_engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1


def test_team_can_be_added_and_retrieved(database_session):
    team = add_team(database_session, "  Inter  ", api_team_id=100)

    found_team = find_team_by_id(database_session, team.id)

    assert found_team is not None
    assert found_team.name == "Inter"
    assert found_team.api_team_id == 100
    assert found_team.data_source == "demo"


def test_match_can_be_added_and_retrieved(database_session):
    home_team, away_team = add_test_teams(database_session)
    match = add_test_match(
        database_session,
        home_team,
        away_team,
        home_score=2,
        away_score=1,
        status="finished",
    )

    found_match = find_match_by_id(database_session, match.id)

    assert found_match is not None
    assert found_match.home_team.name == "Home Team"
    assert found_match.away_team.name == "Away Team"
    assert found_match.home_score == 2
    assert found_match.away_score == 1
    assert found_match.status == "finished"


def test_match_statistics_can_be_saved(database_session):
    home_team, away_team = add_test_teams(database_session)
    match = add_test_match(database_session, home_team, away_team)

    statistics = save_or_update_match_statistics(
        database_session,
        match.id,
        home_possession=55.5,
        away_possession=44.5,
        home_shots=12,
        away_shots=8,
        home_shots_on_target=5,
        away_shots_on_target=3,
    )

    assert statistics.match_id == match.id
    assert statistics.home_possession == 55.5
    assert statistics.away_shots_on_target == 3


def test_match_statistics_can_be_updated(database_session):
    home_team, away_team = add_test_teams(database_session)
    match = add_test_match(database_session, home_team, away_team)
    first_statistics = save_or_update_match_statistics(
        database_session,
        match.id,
        home_possession=55,
        away_possession=45,
        home_shots=10,
    )

    updated_statistics = save_or_update_match_statistics(
        database_session,
        match.id,
        home_possession=60,
        away_possession=40,
        home_shots=14,
    )

    assert updated_statistics.id == first_statistics.id
    assert updated_statistics.home_possession == 60
    assert updated_statistics.home_shots == 14
    assert database_session.query(MatchStatistics).count() == 1


def test_missing_match_statistics_are_allowed(database_session):
    home_team, away_team = add_test_teams(database_session)
    match = add_test_match(database_session, home_team, away_team)

    statistics = save_or_update_match_statistics(database_session, match.id)

    assert statistics.home_possession is None
    assert statistics.away_possession is None
    assert statistics.home_shots is None
    assert statistics.away_shots is None
    assert statistics.home_shots_on_target is None
    assert statistics.away_shots_on_target is None


def test_duplicate_external_match_id_is_rejected(database_session):
    home_team, away_team = add_test_teams(database_session)
    add_test_match(
        database_session,
        home_team,
        away_team,
        api_match_id=500,
    )

    with pytest.raises(IntegrityError):
        add_test_match(
            database_session,
            home_team,
            away_team,
            api_match_id=500,
        )

    assert len(list_matches(database_session)) == 1


def test_demo_and_live_matches_stay_separate(database_session):
    demo_home, demo_away = add_test_teams(database_session)
    live_home = add_team(database_session, "Home Team", data_source="live")
    live_away = add_team(database_session, "Away Team", data_source="live")
    demo_match = add_test_match(database_session, demo_home, demo_away)
    live_match = add_test_match(
        database_session,
        live_home,
        live_away,
        api_match_id=700,
        data_source="live",
    )

    assert [item.id for item in list_matches(database_session)] == [demo_match.id]
    assert [
        item.id for item in list_matches(database_session, data_source="live")
    ] == [live_match.id]
    assert find_match_by_id(database_session, live_match.id) is None
    assert find_match_by_id(
        database_session,
        live_match.id,
        data_source="live",
    ) is not None
    assert find_team_by_id(database_session, live_home.id) is None
    with pytest.raises(ValueError):
        add_test_match(
            database_session,
            live_home,
            live_away,
            data_source="demo",
        )


def test_duplicate_external_match_id_is_allowed_for_different_sources(
    database_session,
):
    demo_home, demo_away = add_test_teams(database_session)
    live_home, live_away = add_test_teams(database_session, data_source="live")
    demo_match = add_test_match(
        database_session,
        demo_home,
        demo_away,
        api_match_id=800,
    )
    live_match = add_test_match(
        database_session,
        live_home,
        live_away,
        api_match_id=800,
        data_source="live",
    )

    assert demo_match.api_match_id == live_match.api_match_id
    assert demo_match.data_source != live_match.data_source
