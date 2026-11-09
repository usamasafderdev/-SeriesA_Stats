from datetime import datetime

from app.database import create_database_engine, create_database_session, initialize_database
from app.football_data_import import save_football_data_matches, save_football_data_standings
from app.models import LeagueStanding, Match
from fastapi.testclient import TestClient
from main import app


MATCHES = {
    "resultSet": {"count": 380},
    "matches": [{
        "id": 19722111,
        "utcDate": "2026-11-08T19:45:00Z",
        "status": "FINISHED",
        "matchday": 11,
        "homeTeam": {"id": 1, "name": "Fiorentina"},
        "awayTeam": {"id": 2, "name": "Juventus"},
        "score": {"fullTime": {"home": 2, "away": 2}},
    }],
}

STANDINGS = {
    "standings": [{
        "table": [{
            "position": 1,
            "team": {"id": 1, "name": "Fiorentina"},
            "playedGames": 11,
            "won": 7,
            "draw": 2,
            "lost": 2,
            "goalsFor": 20,
            "goalsAgainst": 10,
            "goalDifference": 10,
            "points": 23,
        }],
    }],
}


def test_football_data_imports_matches_and_standings(tmp_path):
    engine = create_database_engine(tmp_path / "football_data.db")
    initialize_database(engine)
    with create_database_session(engine) as session:
        assert save_football_data_matches(session, MATCHES, 2026) == {
            "created": 1,
            "updated": 0,
        }
        assert save_football_data_standings(session, STANDINGS, 2026) == 1
        session.commit()
        match = session.query(Match).one()
        assert match.football_data_match_id == "19722111"
        assert match.status == "finished"
        assert match.home_score == 2
        assert session.query(LeagueStanding).one().points == 23
    engine.dispose()


def test_sync_route_uses_exactly_two_client_calls(monkeypatch, tmp_path):
    class MockClient:
        def __init__(self):
            self.calls = []

        def get_matches(self, season):
            self.calls.append(("matches", season))
            return MATCHES

        def get_standings(self, season):
            self.calls.append(("standings", season))
            return STANDINGS

    mock = MockClient()
    monkeypatch.setattr("main.FootballDataClient", lambda: mock)
    engine = create_database_engine(tmp_path / "route.db")
    initialize_database(engine)

    def database_override():
        with create_database_session(engine) as session:
            yield session

    from app.database import get_database_session
    app.dependency_overrides[get_database_session] = database_override
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/football-data/sync",
                json={"season": 2026, "confirmed": True},
            )
        assert response.status_code == 200
        assert response.json()["requests_used"] == 2
        assert response.json()["records_returned"] == 1
        assert mock.calls == [("matches", 2026), ("standings", 2026)]
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
