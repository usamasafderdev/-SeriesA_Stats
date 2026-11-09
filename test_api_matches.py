from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.database import (
    create_database_engine,
    create_database_session,
    get_database_session,
    initialize_database,
)
from app.match_service import (
    add_match,
    add_team,
    save_or_update_match_statistics,
)
from app.models import Match, Team
from main import app


@pytest.fixture
def api_client(tmp_path):
    """Run API requests against a new database file for each test."""
    test_engine = create_database_engine(tmp_path / "test_api.db")
    initialize_database(test_engine)

    def use_test_database():
        session = create_database_session(test_engine)
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_database_session] = use_test_database
    try:
        with TestClient(app) as client:
            yield client, test_engine
    finally:
        app.dependency_overrides.clear()
        test_engine.dispose()


def create_match(
    database_engine,
    home_name="Inter",
    away_name="Roma",
    season="2024/2025",
    data_source="demo",
    home_score=2,
    away_score=1,
):
    """Add a match to the temporary database for an API test."""
    with create_database_session(database_engine) as session:
        home_team = (
            session.query(Team)
            .filter_by(name=home_name, data_source=data_source)
            .first()
        )
        if home_team is None:
            home_team = add_team(session, home_name, data_source=data_source)

        away_team = (
            session.query(Team)
            .filter_by(name=away_name, data_source=data_source)
            .first()
        )
        if away_team is None:
            away_team = add_team(session, away_name, data_source=data_source)

        return add_match(
            session,
            season=season,
            match_date=datetime(2025, 4, 22, 18, 0),
            home_team_id=home_team.id,
            away_team_id=away_team.id,
            home_score=home_score,
            away_score=away_score,
            status="finished",
            data_source=data_source,
        ).id


def test_empty_database_returns_empty_match_list(api_client):
    client, _database_engine = api_client

    response = client.get("/api/matches")

    assert response.status_code == 200
    assert response.json() == []


def test_stored_match_appears_in_response(api_client):
    client, database_engine = api_client
    match_id = create_match(database_engine)

    response = client.get("/api/matches")

    assert response.status_code == 200
    assert [match["id"] for match in response.json()] == [match_id]


def test_match_team_names_and_scores_are_correct(api_client):
    client, database_engine = api_client
    create_match(database_engine)

    match = client.get("/api/matches").json()[0]

    assert match["home_team_name"] == "Inter"
    assert match["away_team_name"] == "Roma"
    assert match["home_score"] == 2
    assert match["away_score"] == 1
    assert match["data_source"] == "demo"


def test_season_filter_returns_only_matching_matches(api_client):
    client, database_engine = api_client
    create_match(database_engine, season="2024/2025")
    create_match(
        database_engine,
        home_name="Milan",
        away_name="Napoli",
        season="2023/2024",
    )

    matches = client.get("/api/matches", params={"season": "2023/2024"}).json()

    assert len(matches) == 1
    assert matches[0]["season"] == "2023/2024"
    assert matches[0]["home_team_name"] == "Milan"


def test_team_filter_matches_either_team_case_insensitively(api_client):
    client, database_engine = api_client
    create_match(database_engine, home_name="Inter", away_name="Roma")
    create_match(
        database_engine,
        home_name="Milan",
        away_name="Napoli",
    )

    matches = client.get("/api/matches", params={"team": "nApOlI"}).json()

    assert len(matches) == 1
    assert matches[0]["away_team_name"] == "Napoli"


def test_source_filter_separates_demo_and_live_matches(api_client):
    client, database_engine = api_client
    create_match(database_engine, data_source="demo")
    create_match(
        database_engine,
        home_name="Juventus",
        away_name="Lazio",
        data_source="live",
        home_score=0,
        away_score=0,
    )

    matches = client.get("/api/matches", params={"source": "live"}).json()

    assert len(matches) == 1
    assert matches[0]["data_source"] == "live"
    assert matches[0]["home_team_name"] == "Juventus"


def test_match_details_include_match_teams_and_statistics(api_client):
    client, database_engine = api_client
    match_id = create_match(database_engine)
    with create_database_session(database_engine) as session:
        save_or_update_match_statistics(
            session,
            match_id,
            home_possession=57.5,
            away_possession=42.5,
            home_shots=12,
            away_shots=9,
            home_shots_on_target=6,
            away_shots_on_target=3,
        )

    response = client.get(f"/api/matches/{match_id}")
    details = response.json()

    assert response.status_code == 200
    assert details["home_team"]["name"] == "Inter"
    assert details["away_team"]["name"] == "Roma"
    assert details["home_score"] == 2
    assert details["away_score"] == 1
    assert details["status"] == "finished"
    assert details["data_source"] == "demo"
    assert details["statistics"] == {
        "home_possession": 57.5,
        "away_possession": 42.5,
        "home_shots": 12,
        "away_shots": 9,
        "home_shots_on_target": 6,
        "away_shots_on_target": 3,
    }


def test_missing_match_statistics_are_returned_as_null(api_client):
    client, database_engine = api_client
    match_id = create_match(database_engine)

    statistics = client.get(f"/api/matches/{match_id}").json()["statistics"]

    assert statistics == {
        "home_possession": None,
        "away_possession": None,
        "home_shots": None,
        "away_shots": None,
        "home_shots_on_target": None,
        "away_shots_on_target": None,
    }


def test_match_list_filters_by_round(api_client):
    client, database_engine = api_client
    first_id = create_match(database_engine)
    second_id = create_match(
        database_engine,
        home_name="Napoli",
        away_name="Milan",
    )
    with create_database_session(database_engine) as session:
        session.get(Match, first_id).round_name = "Round 1"
        session.get(Match, second_id).round_name = "Round 2"
        session.commit()

    response = client.get("/api/matches", params={"round": "Round 2"})

    assert response.status_code == 200
    assert [match["id"] for match in response.json()] == [second_id]
    assert response.json()[0]["round"] == "Round 2"


def test_unknown_match_id_returns_404(api_client):
    client, _database_engine = api_client

    response = client.get("/api/matches/9999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Match not found."}


@pytest.mark.parametrize(
    "query",
    [
        {"source": "other"},
        {"season": ""},
        {"team": ""},
        {"season": "   "},
        {"team": "   "},
    ],
)
def test_invalid_query_values_return_422(api_client, query):
    client, _database_engine = api_client

    response = client.get("/api/matches", params=query)

    assert response.status_code == 422


def test_api_uses_temporary_database_not_project_database(api_client):
    client, test_engine = api_client
    match_id = create_match(test_engine)

    production_engine = create_database_engine()
    try:
        with create_database_session(production_engine) as session:
            production_count_before = session.query(Match).count()

        response = client.get("/api/matches")

        with create_database_session(production_engine) as session:
            production_count_after = session.query(Match).count()
    finally:
        production_engine.dispose()

    assert response.status_code == 200
    assert [match["id"] for match in response.json()] == [match_id]
    assert production_count_after == production_count_before
