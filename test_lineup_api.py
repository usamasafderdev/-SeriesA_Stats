from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.database import (
    create_database_engine,
    create_database_session,
    get_database_session,
    initialize_database,
)
from app.football_api import FootballAPIReadTimeoutError
from app.match_service import add_match, add_team
from app.models import LineupPlayer, Match, MatchLineup
from main import app


@pytest.fixture
def api_client(tmp_path):
    database_engine = create_database_engine(tmp_path / "lineup_api.db")
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


def create_live_match(database_engine, source="live"):
    with create_database_session(database_engine) as session:
        home = add_team(
            session,
            "Live Home" if source == "live" else "Demo Home",
            api_team_id=239 if source == "live" else None,
            data_source=source,
        )
        away = add_team(
            session,
            "Live Away" if source == "live" else "Demo Away",
            api_team_id=268 if source == "live" else None,
            data_source=source,
        )
        match = add_match(
            session,
            season="2025",
            match_date=datetime(2026, 5, 24),
            home_team_id=home.id,
            away_team_id=away.id,
            home_score=2,
            away_score=2,
            status="final",
            api_match_id=737158 if source == "live" else None,
            data_source=source,
        )
        return match.id


def api_lineup(team_id, offset):
    return {
        "team_id": str(team_id),
        "formation": "4-3-3",
        "starting_xi": [
            {
                "player_id": str(offset + index),
                "name": f"Starter {offset + index}",
                "jersey": str(index),
                "position": "Defender",
                "formation_place": index,
                "minute_on": 0,
                "goals": 0,
                "assists": None if index == 1 else 0,
                "yellow_cards": 0,
                "red_cards": 0,
            }
            for index in range(1, 12)
        ],
        "substitutes_used": [
            {
                "player_id": str(offset + 12),
                "name": "Used substitute",
                "jersey": "17",
                "position": "Forward",
                "minute_on": 75,
                "goals": 1,
                "assists": 0,
                "yellow_cards": 0,
                "red_cards": 0,
            }
        ],
        "unused_substitutes": [
            {"player_id": str(offset + 13), "name": "Unused substitute"}
        ],
    }


class MockFootballAPI:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.lineup_calls = []
        self.match_calls = []

    def get_lineups(self, game_id):
        self.lineup_calls.append(game_id)
        if self.error:
            raise self.error
        return self.response

    def get_matches(self, season, limit):
        self.match_calls.append((season, limit))
        if self.error:
            raise self.error
        return self.response


def valid_lineup_data():
    return {
        "game": {"game_id": "737158"},
        "lineups": [api_lineup(239, 0), api_lineup(268, 100)],
    }


def test_get_lineups_returns_clear_empty_response(api_client):
    client, database_engine = api_client
    match_id = create_live_match(database_engine)

    response = client.get(f"/api/matches/{match_id}/lineups")

    assert response.status_code == 200
    assert response.json()["available"] is False
    assert response.json()["lineups"] == []
    assert "No lineup data" in response.json()["message"]


def test_get_lineups_returns_both_teams_and_player_statistics(api_client):
    client, database_engine = api_client
    match_id = create_live_match(database_engine)
    with create_database_session(database_engine) as session:
        match = session.get(Match, match_id)
        home_team = match.home_team
        away_team = match.away_team
        home_lineup = MatchLineup(
            match=match,
            team=home_team,
            formation="4-3-3",
        )
        session.add(home_lineup)
        away_lineup = MatchLineup(
            match=match,
            team=away_team,
            formation="3-5-2",
        )
        session.add(away_lineup)
        session.flush()
        for lineup in match.lineups:
            for index in range(11):
                lineup.players.append(
                    LineupPlayer(
                        api_player_id=f"{lineup.team_id}-{index}",
                        player_name=f"Player {lineup.team_id}-{index}",
                        player_role="starter",
                        goals=0 if index == 0 else None,
                        assists=1 if index == 0 else None,
                    )
                )
        session.commit()

    response = client.get(f"/api/matches/{match_id}/lineups")
    body = response.json()

    assert response.status_code == 200
    assert body["available"] is True
    assert body["complete"] is True
    assert len(body["lineups"]) == 2
    assert body["lineups"][0]["formation"] == "4-3-3"
    first_player = body["lineups"][0]["starting_players"][0]
    assert first_player["goals"] == 0
    assert first_player["assists"] == 1
    assert body["lineups"][1]["starting_players"][0]["goals"] == 0


def test_match_summary_calculates_assists_only_from_complete_lineups(api_client):
    client, database_engine = api_client
    match_id = create_live_match(database_engine)
    with create_database_session(database_engine) as session:
        match = session.get(Match, match_id)
        for team in (match.home_team, match.away_team):
            lineup = MatchLineup(match=match, team=team, formation="4-3-3")
            session.add(lineup)
            session.flush()
            for index in range(11):
                lineup.players.append(
                    LineupPlayer(
                        api_player_id=f"{team.id}-{index}",
                        player_name=f"Player {team.id}-{index}",
                        player_role="starter",
                        assists=1 if team == match.home_team and index == 0 else 0,
                    )
                )
        session.commit()

    match_summary = client.get("/api/matches?source=live").json()[0]

    assert match_summary["home_assists"] == 1
    assert match_summary["away_assists"] == 0


def test_get_lineups_identifies_a_missing_team_lineup(api_client):
    client, database_engine = api_client
    match_id = create_live_match(database_engine)
    with create_database_session(database_engine) as session:
        match = session.get(Match, match_id)
        lineup = MatchLineup(match=match, team=match.home_team, formation="4-3-3")
        session.add(lineup)
        session.flush()
        for index in range(11):
            lineup.players.append(
                LineupPlayer(
                    api_player_id=f"home-{index}",
                    player_name=f"Home player {index}",
                    player_role="starter",
                )
            )
        session.commit()

    body = client.get(f"/api/matches/{match_id}/lineups").json()

    assert body["available"] is True
    assert body["complete"] is False
    assert len(body["lineups"]) == 2
    assert body["lineups"][0]["available"] is True
    assert body["lineups"][1]["available"] is False
    assert body["lineups"][1]["starting_players"] == []


def test_unknown_match_lineups_return_404(api_client):
    client, _database_engine = api_client

    response = client.get("/api/matches/9999/lineups")

    assert response.status_code == 404


def test_lineup_import_requires_confirmation_and_makes_no_call(
    api_client,
    monkeypatch,
):
    client, database_engine = api_client
    match_id = create_live_match(database_engine)
    mock_api = MockFootballAPI(valid_lineup_data())
    monkeypatch.setattr("main.FootballAPI", lambda: mock_api)

    response = client.post(f"/api/matches/{match_id}/lineups/import", json={})

    assert response.status_code == 400
    assert "5 API credits" in response.json()["detail"]
    assert mock_api.lineup_calls == []


def test_confirmed_lineup_import_saves_players_and_returns_both_teams(
    api_client,
    monkeypatch,
):
    client, database_engine = api_client
    match_id = create_live_match(database_engine)
    mock_api = MockFootballAPI(valid_lineup_data())
    monkeypatch.setattr("main.FootballAPI", lambda: mock_api)

    response = client.post(
        f"/api/matches/{match_id}/lineups/import",
        json={"confirmed": True},
    )
    body = response.json()

    assert response.status_code == 200
    assert body["source"] == "strikerapi"
    assert body["estimated_credits"] == 5
    assert len(body["lineups"]) == 2
    assert body["lineups"][0]["team_name"] == "Live Home"
    assert body["lineups"][1]["team_name"] == "Live Away"
    assert len(body["lineups"][0]["starting_players"]) == 11
    assert body["lineups"][0]["substitutes_used"][0]["goals"] == 1
    assert body["lineups"][0]["unused_substitutes"][0]["goals"] is None
    assert mock_api.lineup_calls == [737158]


def test_imported_lineups_are_returned_by_local_endpoint_without_duplicates(
    api_client,
    monkeypatch,
):
    client, database_engine = api_client
    match_id = create_live_match(database_engine)
    provider_data = valid_lineup_data()
    provider_data["lineups"][0]["starting_xi"][0].update(
        {"goals": 2, "assists": 1, "yellow_cards": 1, "red_cards": 0}
    )
    provider_data["lineups"][0]["starting_xi"][1]["assists"] = None
    provider_data["lineups"][1]["starting_xi"][1]["red_cards"] = 1
    mock_api = MockFootballAPI(provider_data)
    monkeypatch.setattr("main.FootballAPI", lambda: mock_api)

    imported = client.post(
        f"/api/matches/{match_id}/lineups/import",
        json={"confirmed": True},
    )
    stored = client.get(f"/api/matches/{match_id}/lineups")
    repeated_import = client.post(
        f"/api/matches/{match_id}/lineups/import",
        json={"confirmed": True},
    )

    assert imported.status_code == 200
    assert stored.status_code == 200
    assert stored.json()["complete"] is True
    home_lineup, away_lineup = stored.json()["lineups"]
    assert home_lineup["formation"] == "4-3-3"
    assert len(home_lineup["starting_players"]) == 11
    assert len(home_lineup["substitutes_used"]) == 1
    assert len(home_lineup["unused_substitutes"]) == 1
    assert home_lineup["starting_players"][0]["goals"] == 2
    assert home_lineup["starting_players"][0]["assists"] == 1
    assert home_lineup["starting_players"][0]["yellow_cards"] == 1
    assert home_lineup["starting_players"][0]["red_cards"] == 0
    assert away_lineup["starting_players"][1]["red_cards"] == 1
    assert home_lineup["starting_players"][1]["assists"] is None
    assert repeated_import.json()["source"] == "database"
    assert mock_api.lineup_calls == [737158]
    with create_database_session(database_engine) as session:
        assert session.query(MatchLineup).count() == 2
        assert session.query(LineupPlayer).count() == 26


def test_missing_provider_lineups_fail_without_storing_partial_data(
    api_client,
    monkeypatch,
):
    client, database_engine = api_client
    match_id = create_live_match(database_engine)
    mock_api = MockFootballAPI(response={"game": {"game_id": "737158"}, "lineups": []})
    monkeypatch.setattr("main.FootballAPI", lambda: mock_api)

    response = client.post(
        f"/api/matches/{match_id}/lineups/import",
        json={"confirmed": True},
    )
    with create_database_session(database_engine) as session:
        saved_lineup_count = session.query(MatchLineup).count()

    assert response.status_code == 502
    assert saved_lineup_count == 0
    assert mock_api.lineup_calls == [737158]


def test_cached_lineups_skip_the_live_request(api_client, monkeypatch):
    client, database_engine = api_client
    match_id = create_live_match(database_engine)
    mock_api = MockFootballAPI(valid_lineup_data())
    monkeypatch.setattr("main.FootballAPI", lambda: mock_api)
    first = client.post(
        f"/api/matches/{match_id}/lineups/import",
        json={"confirmed": True},
    )
    assert first.status_code == 200

    second = client.post(f"/api/matches/{match_id}/lineups/import", json={})

    assert second.status_code == 200
    assert second.json()["source"] == "database"
    assert second.json()["estimated_credits"] == 0
    assert mock_api.lineup_calls == [737158]


def test_demo_match_cannot_import_live_lineups(api_client, monkeypatch):
    client, database_engine = api_client
    match_id = create_live_match(database_engine, source="demo")
    mock_api = MockFootballAPI(valid_lineup_data())
    monkeypatch.setattr("main.FootballAPI", lambda: mock_api)

    response = client.post(
        f"/api/matches/{match_id}/lineups/import",
        json={"confirmed": True},
    )

    assert response.status_code == 404
    assert mock_api.lineup_calls == []


def test_lineup_api_timeout_is_reported_without_retry(
    api_client,
    monkeypatch,
):
    client, database_engine = api_client
    match_id = create_live_match(database_engine)
    mock_api = MockFootballAPI(error=FootballAPIReadTimeoutError("timeout"))
    monkeypatch.setattr("main.FootballAPI", lambda: mock_api)

    response = client.post(
        f"/api/matches/{match_id}/lineups/import",
        json={"confirmed": True},
    )

    assert response.status_code == 504
    assert "No retry" in response.json()["detail"]
    assert mock_api.lineup_calls == [737158]


def test_match_list_import_needs_confirmation_and_is_capped_at_three(
    api_client,
    monkeypatch,
):
    client, _database_engine = api_client
    mock_api = MockFootballAPI(
        response={
            "games": [
                {
                    "game_id": "1234",
                    "season": 2025,
                    "date": "2025-01-01",
                    "status": "final",
                    "home": {"team_id": "1", "name": "Home FC", "score": 1},
                    "away": {"team_id": "2", "name": "Away FC", "score": 0},
                }
            ]
        }
    )
    monkeypatch.setattr("main.FootballAPI", lambda: mock_api)

    unconfirmed = client.post(
        "/api/live-matches/import",
        json={"season": "2025"},
    )
    assert unconfirmed.status_code == 400
    assert mock_api.match_calls == []

    response = client.post(
        "/api/live-matches/import",
        json={"season": "2025", "limit": 3, "confirmed": True},
    )
    assert response.status_code == 200
    assert response.json()["imported_records"] == {
        "created": 1,
        "updated": 0,
        "skipped": 0,
    }
    saved_matches = client.get("/api/matches", params={"source": "live"}).json()
    assert len(saved_matches) == 1
    assert saved_matches[0]["home_score"] == 1
    assert saved_matches[0]["away_score"] == 0
    details = client.get(f"/api/matches/{saved_matches[0]['id']}").json()
    assert details["home_team"]["name"] == "Home FC"
    assert details["away_team"]["name"] == "Away FC"
    assert details["statistics"]["home_possession"] is None
    assert mock_api.match_calls == [("2025", 3)]


def test_match_list_import_reuses_enough_saved_records_without_api_call(
    api_client,
    monkeypatch,
):
    client, database_engine = api_client
    create_live_match(database_engine)
    monkeypatch.setattr(
        "main.FootballAPI",
        lambda: pytest.fail("Saved matches should be reused without a request."),
    )

    response = client.post(
        "/api/live-matches/import",
        json={"season": "2025", "limit": 1},
    )

    assert response.status_code == 200
    assert response.json()["source"] == "database"
    assert response.json()["imported_records"] == {
        "created": 0,
        "updated": 0,
        "skipped": 1,
    }


def test_confirmed_match_list_refresh_updates_a_saved_score(api_client, monkeypatch):
    client, database_engine = api_client
    match_id = create_live_match(database_engine)
    mock_api = MockFootballAPI(
        response={
            "games": [
                {
                    "game_id": 737158,
                    "season": "2025",
                    "date": "2026-05-24",
                    "status": "final",
                    "home": {"team_id": 239, "name": "Live Home", "score": 3},
                    "away": {"team_id": 268, "name": "Live Away", "score": 2},
                }
            ]
        }
    )
    monkeypatch.setattr("main.FootballAPI", lambda: mock_api)

    response = client.post(
        "/api/live-matches/import",
        json={"season": "2025", "limit": 1, "refresh": True, "confirmed": True},
    )

    assert response.status_code == 200
    assert response.json()["imported_records"]["updated"] == 1
    assert response.json()["source"] == "strikerapi"
    details = client.get(f"/api/matches/{match_id}").json()
    assert details["home_score"] == 3
    assert details["away_score"] == 2
    assert mock_api.match_calls == [("2025", 1)]


def test_match_list_import_handles_insufficient_credits(api_client, monkeypatch):
    from app.football_api import InsufficientCreditsError

    client, _database_engine = api_client
    mock_api = MockFootballAPI(error=InsufficientCreditsError("out of credits"))
    monkeypatch.setattr("main.FootballAPI", lambda: mock_api)

    response = client.post(
        "/api/live-matches/import",
        json={"season": "2025", "confirmed": True},
    )

    assert response.status_code == 402
    assert "insufficient credits" in response.json()["detail"]


def test_match_list_import_reports_timeout_without_retry(api_client, monkeypatch):
    client, _database_engine = api_client
    mock_api = MockFootballAPI(error=FootballAPIReadTimeoutError("timeout"))
    monkeypatch.setattr("main.FootballAPI", lambda: mock_api)

    response = client.post(
        "/api/live-matches/import",
        json={"season": "2025", "confirmed": True},
    )

    assert response.status_code == 504
    assert "No retry" in response.json()["detail"]
    assert mock_api.match_calls == [("2025", 3)]
