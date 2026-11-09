from datetime import datetime

import pytest

from app.database import create_database_engine, create_database_session, initialize_database
from app.match_service import add_match, add_team
from app.striker_match_matching import find_matching_striker_game


def test_matches_striker_fixture_by_teams_date_and_score(tmp_path):
    engine = create_database_engine(tmp_path / "matching.db")
    initialize_database(engine)
    with create_database_session(engine) as session:
        home = add_team(session, "Fiorentina", data_source="live")
        away = add_team(session, "Juventus", data_source="live")
        match = add_match(
            session,
            season="2026",
            match_date=datetime(2026, 11, 8, 19, 45),
            home_team_id=home.id,
            away_team_id=away.id,
            home_score=2,
            away_score=2,
            status="finished",
            data_source="live",
        )
        game = find_matching_striker_game(
            match,
            [{
                "game_id": 737158,
                "date": "2026-11-08T19:45:00Z",
                "home": {"name": "Fiorentina", "score": 2},
                "away": {"name": "Juventus", "score": 2},
            }],
        )
        assert game["game_id"] == 737158
    engine.dispose()


def test_rejects_ambiguous_striker_fixture(tmp_path):
    engine = create_database_engine(tmp_path / "ambiguous.db")
    initialize_database(engine)
    with create_database_session(engine) as session:
        home = add_team(session, "Fiorentina", data_source="live")
        away = add_team(session, "Juventus", data_source="live")
        match = add_match(
            session,
            season="2026",
            match_date=datetime(2026, 11, 8, 19, 45),
            home_team_id=home.id,
            away_team_id=away.id,
            home_score=2,
            away_score=2,
            status="finished",
            data_source="live",
        )
        game = {
            "date": "2026-11-08T19:45:00Z",
            "home": {"name": "Fiorentina", "score": 2},
            "away": {"name": "Juventus", "score": 2},
        }
        with pytest.raises(ValueError, match="exactly one"):
            find_matching_striker_game(match, [{**game, "game_id": 1}, {**game, "game_id": 2}])
    engine.dispose()
