from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.database import (
    create_database_engine,
    create_database_session,
    get_database_session,
    initialize_database,
)
from app.match_service import add_match, add_team
from app.models import LineupPlayer, Match, MatchLineup, MatchStatistics
from app.statistics_api import StatisticsAPITimeoutError
from main import app


PROVIDER_MATCH_ID = "bbe0db21-9e62-4cb0-a65c-b1dc7781aa66"


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    database_engine = create_database_engine(tmp_path / "statistics_api.db")
    initialize_database(database_engine)
    monkeypatch.setattr(
        "main.initialize_database",
        lambda: initialize_database(database_engine),
    )

    def use_test_database():
        session = create_database_session(database_engine)
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_database_session] = use_test_database
    try:
        with TestClient(app) as client:
            yield client, database_engine
    finally:
        app.dependency_overrides.clear()
        database_engine.dispose()


def create_live_match(database_engine, status="final", data_source="live"):
    with create_database_session(database_engine) as session:
        live = data_source == "live"
        home = add_team(
            session,
            "Inter",
            api_team_id=239 if live else None,
            data_source=data_source,
        )
        away = add_team(
            session,
            "Juventus",
            api_team_id=268 if live else None,
            data_source=data_source,
        )
        match = add_match(
            session,
            season="2026/2027",
            match_date=datetime(2026, 10, 25, 18, 45),
            home_team_id=home.id,
            away_team_id=away.id,
            home_score=0,
            away_score=0,
            status=status,
            api_match_id=737158 if live else None,
            data_source=data_source,
        )
        return match.id


def provider_fixture():
    return {
        "id": PROVIDER_MATCH_ID,
        "sport": "football",
        "league": "Serie A",
        "kickoff_utc": "2026-10-25T18:45:00Z",
        "status": "finished",
        "home": {"id": "provider-home", "name": "Inter"},
        "away": {"id": "provider-away", "name": "Juventus"},
        "score": {"home": 0, "away": 0},
    }


def statistics_response(home=None, away=None, available=True):
    return {
        "data": {"home": home, "away": away},
        "meta": {"available": available},
        "error": None,
    }


def team_statistics(team_id, team_name, **values):
    return {
        "team_id": team_id,
        "team_name": team_name,
        **values,
    }


class MockStatisticsAPI:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def find_matches(self, match_date, season):
        self.calls.append(("matches", match_date, season))
        if self.error:
            raise self.error
        return [provider_fixture()]

    def get_match_statistics(self, provider_match_id):
        self.calls.append(("statistics", provider_match_id))
        if self.error:
            raise self.error
        return self.response


def install_mock_api(monkeypatch, api):
    monkeypatch.setattr("main.StatisticsAPI", lambda: api)


def test_import_requires_confirmation_and_stored_live_match(api_client, monkeypatch):
    client, database_engine = api_client
    match_id = create_live_match(database_engine)
    api = MockStatisticsAPI()
    install_mock_api(monkeypatch, api)

    response = client.post(
        f"/api/matches/{match_id}/statistics/import",
        json={"confirmed": False},
    )

    assert response.status_code == 400
    assert "two" in response.json()["detail"]
    assert api.calls == []

    demo_match_id = create_live_match(database_engine, data_source="demo")

    response = client.post(
        f"/api/matches/{demo_match_id}/statistics/import",
        json={"confirmed": True},
    )
    assert response.status_code == 404


def test_import_saves_provider_stats_and_provenance(api_client, monkeypatch):
    client, database_engine = api_client
    match_id = create_live_match(database_engine)
    api = MockStatisticsAPI(
        statistics_response(
            team_statistics(
                "provider-home",
                "Inter",
                ball_possession=55.5,
                total_shots=0,
                shots_on_target=0,
            ),
            team_statistics(
                "provider-away",
                "Juventus",
                ball_possession=44.5,
                total_shots=10,
                shots_on_target=3,
            ),
        )
    )
    install_mock_api(monkeypatch, api)

    response = client.post(
        f"/api/matches/{match_id}/statistics/import",
        json={"confirmed": True},
    )

    assert response.status_code == 200
    details = response.json()
    assert details["statistics"]["home_possession"] == 55.5
    assert details["statistics"]["away_possession"] == 44.5
    assert details["statistics"]["home_shots"] == 0
    assert details["statistics"]["home_shots_on_target"] == 0
    assert details["statistics_source"] == "bigballsdata"
    assert details["statistics_provider_match_id"] == PROVIDER_MATCH_ID
    assert details["statistics_import"]["requests_used"] == 2
    assert api.calls == [
        ("matches", "2026-10-25", 2026),
        ("statistics", PROVIDER_MATCH_ID),
    ]

    with create_database_session(database_engine) as session:
        saved = session.query(MatchStatistics).one()
        assert saved.source == "bigballsdata"
        assert saved.provider_match_id == PROVIDER_MATCH_ID


def test_import_keeps_missing_statistics_null_and_caches_empty_result(
    api_client,
    monkeypatch,
):
    client, database_engine = api_client
    match_id = create_live_match(database_engine)
    api = MockStatisticsAPI(statistics_response(None, None, available=False))
    install_mock_api(monkeypatch, api)
    url = f"/api/matches/{match_id}/statistics/import"

    first = client.post(url, json={"confirmed": True})
    second = client.post(url, json={"confirmed": True})

    assert first.status_code == 200
    assert first.json()["statistics_available"] is False
    assert first.json()["statistics"]["home_shots"] is None
    assert first.json()["statistics"]["away_possession"] is None
    assert second.json()["statistics_import"]["cached"] is True
    assert len(api.calls) == 2
    with create_database_session(database_engine) as session:
        assert session.query(MatchStatistics).count() == 1


def test_refresh_updates_existing_statistics_without_duplicate_rows(
    api_client,
    monkeypatch,
):
    client, database_engine = api_client
    match_id = create_live_match(database_engine)
    api = MockStatisticsAPI(
        statistics_response(
            team_statistics(
                "provider-home",
                "Inter",
                ball_possession=50,
                total_shots=9,
                shots_on_target=3,
            ),
            team_statistics(
                "provider-away",
                "Juventus",
                ball_possession=50,
                total_shots=7,
                shots_on_target=2,
            ),
        )
    )
    install_mock_api(monkeypatch, api)
    url = f"/api/matches/{match_id}/statistics/import"

    client.post(url, json={"confirmed": True})
    api.response["data"]["home"]["total_shots"] = 12
    refreshed = client.post(url, json={"confirmed": True, "refresh": True})

    assert refreshed.status_code == 200
    assert refreshed.json()["statistics"]["home_shots"] == 12
    with create_database_session(database_engine) as session:
        assert session.query(MatchStatistics).count() == 1


def test_import_rejects_incomplete_provider_identity_without_writes(
    api_client,
    monkeypatch,
):
    client, database_engine = api_client
    match_id = create_live_match(database_engine)
    api = MockStatisticsAPI(
        statistics_response(
            team_statistics("wrong-home", "Inter"),
            team_statistics("provider-away", "Juventus"),
        )
    )
    install_mock_api(monkeypatch, api)
    api.find_matches = lambda _match_date, _season: [
        {**provider_fixture(), "home": {"id": "wrong-home", "name": "Milan"}}
    ]

    response = client.post(
        f"/api/matches/{match_id}/statistics/import",
        json={"confirmed": True},
    )

    assert response.status_code == 502
    assert "No BigBallsData fixture" in response.json()["detail"]
    with create_database_session(database_engine) as session:
        assert session.query(MatchStatistics).count() == 0


def test_import_rejects_unfinished_match_without_provider_request(
    api_client,
    monkeypatch,
):
    client, database_engine = api_client
    match_id = create_live_match(database_engine, status="scheduled")
    api = MockStatisticsAPI()
    install_mock_api(monkeypatch, api)

    response = client.post(
        f"/api/matches/{match_id}/statistics/import",
        json={"confirmed": True},
    )

    assert response.status_code == 409
    assert api.calls == []


def test_provider_timeout_is_returned_without_retry_or_database_write(
    api_client,
    monkeypatch,
):
    client, database_engine = api_client
    match_id = create_live_match(database_engine)
    api = MockStatisticsAPI(error=StatisticsAPITimeoutError("timeout"))
    install_mock_api(monkeypatch, api)

    response = client.post(
        f"/api/matches/{match_id}/statistics/import",
        json={"confirmed": True},
    )

    assert response.status_code == 504
    assert "No retry" in response.json()["detail"]
    assert len(api.calls) == 1
    with create_database_session(database_engine) as session:
        assert session.query(MatchStatistics).count() == 0


def test_match_details_include_saved_goal_scorers_and_assists(api_client):
    client, database_engine = api_client
    match_id = create_live_match(database_engine)
    with create_database_session(database_engine) as session:
        match = session.get(Match, match_id)
        home_lineup = MatchLineup(match=match, team=match.home_team)
        session.add(home_lineup)
        away_lineup = MatchLineup(match=match, team=match.away_team)
        session.add(away_lineup)
        home_lineup.players.append(
            LineupPlayer(
                player_name="Home scorer",
                player_role="starter",
                goals=2,
                assists=0,
            )
        )
        away_lineup.players.append(
            LineupPlayer(
                player_name="Away assist provider",
                player_role="starter",
                goals=0,
                assists=1,
            )
        )
        session.commit()

    response = client.get(f"/api/matches/{match_id}")

    assert response.status_code == 200
    details = response.json()
    assert details["goal_scorers"] == [
        {"player_name": "Home scorer", "team_name": "Inter", "goals": 2}
    ]
    assert details["goal_assists"] == [
        {"player_name": "Away assist provider", "team_name": "Juventus", "assists": 1}
    ]
    # These rows have no saved provider provenance; do not invent a provider.
    assert details["contributions_source"] == "saved_lineups"
