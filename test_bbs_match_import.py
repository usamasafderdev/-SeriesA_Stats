from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.bbs_match_import import save_bbs_matches
from app.database import (
    create_database_engine,
    create_database_session,
    get_database_session,
    initialize_database,
)
from app.match_service import add_match, add_team, save_or_update_match_statistics
from app.models import Match, MatchStatistics, Team
from main import app


FIXTURE = {
    "id": "5a5e7d30-3b82-4965-bede-8cead82536e6",
    "sport": "football",
    "league": "Serie A",
    "kickoff_utc": "2026-11-08T17:00:00Z",
    "status": "finished",
    "home": {"id": "bbs-fiorentina", "name": "Fiorentina"},
    "away": {"id": "bbs-juventus", "name": "Juventus"},
    "score": {"home": 2, "away": 2},
}


@pytest.fixture
def api_client(tmp_path):
    database_engine = create_database_engine(tmp_path / "test_bbs.db")
    initialize_database(database_engine)

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


def test_fixture_import_stores_provider_ids_and_updates_without_duplicates(
    tmp_path,
):
    database_engine = create_database_engine(tmp_path / "import.db")
    initialize_database(database_engine)
    with create_database_session(database_engine) as session:
        first = save_bbs_matches(session, [FIXTURE], 2026)
        session.commit()
        second = save_bbs_matches(session, [FIXTURE], 2026)
        session.commit()

        assert first == {"created": 1, "updated": 0, "skipped": 0}
        assert second == {"created": 0, "updated": 1, "skipped": 0}
        assert session.query(Match).count() == 1
        assert session.query(Team).count() == 2
        match = session.query(Match).one()
        assert match.bbs_match_id == FIXTURE["id"]
        assert match.api_match_id is None
        assert match.home_team.name == "Fiorentina"
        assert match.away_team.name == "Juventus"
        assert match.home_score == 2
        assert match.away_score == 2
        assert match.home_team.bbs_team_id == "bbs-fiorentina"
    database_engine.dispose()


def test_refresh_updates_score_and_round_for_same_bbs_match(tmp_path):
    database_engine = create_database_engine(tmp_path / "corrected_score.db")
    initialize_database(database_engine)
    with create_database_session(database_engine) as session:
        initial = {**FIXTURE, "round": "Round 11"}
        save_bbs_matches(session, [initial], 2026)
        session.commit()

        updated = {**FIXTURE, "round": "Round 12", "score": {"home": 3, "away": 2}}
        result = save_bbs_matches(session, [updated], 2026)
        session.commit()

        match = session.query(Match).one()
        assert result == {"created": 0, "updated": 1, "skipped": 0}
        assert match.home_score == 3
        assert match.away_score == 2
        assert match.round_name == "Round 12"
        assert session.query(Match).count() == 1
    database_engine.dispose()


def test_fixture_cache_reuses_season_labels_with_start_year_suffix(
    api_client,
    monkeypatch,
):
    client, database_engine = api_client
    with create_database_session(database_engine) as session:
        save_bbs_matches(session, [FIXTURE], 2026)
        session.query(Match).one().season = "2026/2027"
        session.commit()

    class UnexpectedStatisticsAPI:
        def list_season_matches(self, _season, _page, _limit):
            raise AssertionError("A cached fixture list should not make a request.")

    monkeypatch.setattr("main.StatisticsAPI", UnexpectedStatisticsAPI)
    response = client.post(
        "/api/bbs/matches/import",
        json={"season": 2026, "limit": 1, "confirmed": False},
    )

    assert response.status_code == 200
    assert response.json()["source"] == "database"
    assert response.json()["requests_used"] == 0
    assert response.json()["matches"][0]["season"] == "2026/2027"


def test_fixture_import_rejects_ambiguous_local_identity(tmp_path):
    database_engine = create_database_engine(tmp_path / "ambiguous.db")
    initialize_database(database_engine)
    with create_database_session(database_engine) as session:
        home = add_team(session, "Fiorentina", data_source="live")
        away = add_team(session, "Juventus", data_source="live")
        for _ in range(2):
            add_match(
                session,
                season="2026/2027",
                match_date=datetime(2026, 11, 8, 17),
                home_team_id=home.id,
                away_team_id=away.id,
                home_score=2,
                away_score=2,
                status="finished",
                data_source="live",
            )

        with pytest.raises(ValueError, match="More than one saved match"):
            save_bbs_matches(session, [FIXTURE], 2026)
    database_engine.dispose()


def test_fixture_import_accepts_scheduled_provider_record(tmp_path):
    database_engine = create_database_engine(tmp_path / "scheduled.db")
    initialize_database(database_engine)
    with create_database_session(database_engine) as session:
        scheduled = {**FIXTURE, "status": "scheduled"}
        result = save_bbs_matches(session, [scheduled], 2026)
        assert result["created"] == 1
        assert session.query(Match).one().status == "scheduled"
    database_engine.dispose()


def test_import_endpoint_requires_confirmation_and_saves_verified_fixture(
    api_client,
    monkeypatch,
):
    client, database_engine = api_client
    calls = []

    class MockStatisticsAPI:
        def list_season_matches(self, season, page, limit):
            calls.append((season, page, limit))
            return [FIXTURE]

    monkeypatch.setattr("main.StatisticsAPI", MockStatisticsAPI)
    rejected = client.post(
        "/api/bbs/matches/import",
        json={"season": 2026, "limit": 5, "confirmed": False},
    )
    assert rejected.status_code == 400
    assert calls == []

    response = client.post(
        "/api/bbs/matches/import",
        json={"season": 2026, "limit": 5, "confirmed": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["requests_used"] == 1
    assert body["imported_records"]["created"] == 1
    assert body["matches"][0]["home_team_name"] == "Fiorentina"
    assert body["matches"][0]["away_team_name"] == "Juventus"
    assert calls == [(2026, 1, 5)]

    cached = client.post(
        "/api/bbs/matches/import",
        json={"season": 2026, "limit": 1, "confirmed": False},
    )
    assert cached.status_code == 200
    assert cached.json()["requests_used"] == 0
    assert len(calls) == 1

    with create_database_session(database_engine) as session:
        saved = session.query(Match).one()
        assert saved.bbs_match_id == FIXTURE["id"]
        assert saved.api_match_id is None


def test_date_only_import_keeps_kickoff_time_unavailable(api_client, monkeypatch):
    client, database_engine = api_client

    class MockStatisticsAPI:
        def list_season_matches(self, _season, _page, _limit):
            return [{**FIXTURE, "kickoff_utc": "2026-11-08"}]

    monkeypatch.setattr("main.StatisticsAPI", MockStatisticsAPI)
    response = client.post(
        "/api/bbs/matches/import",
        json={"season": 2026, "limit": 1, "confirmed": True},
    )
    match_id = response.json()["matches"][0]["id"]

    assert response.status_code == 200
    assert response.json()["matches"][0]["match_date"] == "2026-11-08"
    assert client.get(f"/api/matches/{match_id}").json()["match_date"] == "2026-11-08"
    with create_database_session(database_engine) as session:
        assert session.query(Match).one().kickoff_time_available is False


def test_statistics_import_uses_linked_bbs_uuid_without_fixture_lookup(
    api_client,
    monkeypatch,
):
    client, database_engine = api_client
    with create_database_session(database_engine) as session:
        save_bbs_matches(session, [FIXTURE], 2026)
        session.commit()
        match_id = session.query(Match).one().id

    class MockStatisticsAPI:
        def __init__(self):
            self.calls = []

        def get_match_statistics(self, provider_match_id):
            self.calls.append(provider_match_id)
            return {
                "data": {
                    "home": {
                        "team_id": "bbs-fiorentina",
                        "team_name": "Fiorentina",
                        "ball_possession": 41,
                        "total_shots": 22,
                        "shots_on_target": 6,
                    },
                    "away": {
                        "team_id": "bbs-juventus",
                        "team_name": "Juventus",
                        "ball_possession": 59,
                        "total_shots": 18,
                        "shots_on_target": 6,
                    },
                },
                "meta": {"available": True},
            }

    mock_api = MockStatisticsAPI()
    monkeypatch.setattr("main.StatisticsAPI", lambda: mock_api)

    response = client.post(
        f"/api/matches/{match_id}/statistics/import",
        json={"confirmed": True},
    )

    assert response.status_code == 200
    assert response.json()["statistics"]["home_possession"] == 41
    assert response.json()["statistics"]["away_possession"] == 59
    assert response.json()["statistics"]["home_shots"] == 22
    assert response.json()["statistics"]["away_shots"] == 18
    assert response.json()["statistics_import"]["requests_used"] == 1
    assert mock_api.calls == [FIXTURE["id"]]
    with create_database_session(database_engine) as session:
        assert session.query(MatchStatistics).one().provider_match_id == FIXTURE["id"]


def test_statistics_refresh_reuses_saved_provider_id_without_fixture_lookup(
    api_client,
    monkeypatch,
):
    client, database_engine = api_client
    with create_database_session(database_engine) as session:
        home = add_team(session, "Fiorentina", data_source="live")
        away = add_team(session, "Juventus", data_source="live")
        match = add_match(
            session,
            season="2026/2027",
            match_date=datetime(2026, 11, 8, 17),
            home_team_id=home.id,
            away_team_id=away.id,
            home_score=2,
            away_score=2,
            status="finished",
            data_source="live",
        )
        save_or_update_match_statistics(
            session,
            match.id,
            home_possession=40,
            away_possession=60,
            source="bigballsdata",
            provider_match_id=FIXTURE["id"],
        )
        match_id = match.id

    class MockStatisticsAPI:
        def find_matches(self, _match_date, _season):
            raise AssertionError("A known provider match ID skips fixture lookup.")

        def get_match_statistics(self, provider_match_id):
            assert provider_match_id == FIXTURE["id"]
            return {
                "data": {
                    "home": {"team_name": "Fiorentina", "ball_possession": 41},
                    "away": {"team_name": "Juventus", "ball_possession": 59},
                },
                "meta": {"available": True},
            }

    monkeypatch.setattr("main.StatisticsAPI", MockStatisticsAPI)
    response = client.post(
        f"/api/matches/{match_id}/statistics/import",
        json={"confirmed": True, "refresh": True},
    )

    assert response.status_code == 200
    assert response.json()["statistics_import"]["requests_used"] == 1
    assert response.json()["statistics"]["home_possession"] == 41
    with create_database_session(database_engine) as session:
        match = session.get(Match, match_id)
        assert match.bbs_match_id == FIXTURE["id"]


def test_saved_match_endpoints_persist_only_selection_not_match_deletion(api_client):
    client, database_engine = api_client
    with create_database_session(database_engine) as session:
        home = add_team(session, "Fiorentina", data_source="live")
        away = add_team(session, "Juventus", data_source="live")
        match = add_match(
            session,
            season="2026",
            match_date=datetime(2026, 11, 8, 17),
            home_team_id=home.id,
            away_team_id=away.id,
            home_score=2,
            away_score=2,
            status="finished",
            data_source="live",
        )
        match_id = match.id

    saved = client.post("/api/saved-matches", json={"match_id": match_id})
    assert saved.status_code == 200
    assert client.get("/api/saved-matches").json()[0]["id"] == match_id

    removed = client.delete(f"/api/saved-matches/{match_id}")
    assert removed.status_code == 200
    assert removed.json()["saved"] is False
    assert client.get("/api/saved-matches").json() == []
    with create_database_session(database_engine) as session:
        assert session.query(Match).count() == 1
