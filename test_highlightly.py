from datetime import datetime

from app.database import create_database_engine, create_database_session, initialize_database
from app.highlightly_import import convert_highlightly_lineups, save_highlightly_lineups
from app.match_service import add_match, add_team
from app.models import LineupPlayer, MatchLineup


def _players(start, count=11):
    return [
        {
            "id": start + index,
            "name": f"Player {start + index}",
            "shirtNumber": index,
            "position": "Midfielder",
            "formationPlace": index,
        }
        for index in range(1, count + 1)
    ]


def test_highlightly_lineups_merge_box_score_contributions(tmp_path):
    body = {
        "lineups": [
            {"team": {"id": 1, "name": "Fiorentina"}, "formation": "4-3-3", "initialLineup": _players(0), "substitutes": []},
            {"team": {"id": 2, "name": "Juventus"}, "formation": "3-5-2", "initialLineup": _players(20), "substitutes": []},
        ]
    }
    box = {"players": [{"id": 1, "name": "Player 1", "statistics": {"goals": 1, "assists": 0, "yellowCards": 1, "redCards": 0}}]}
    converted = convert_highlightly_lineups(body, box, "Fiorentina", "Juventus")
    assert len(converted) == 2
    assert len(converted[0]["starting_players"]) == 11
    assert converted[0]["starting_players"][0]["goals"] == 1
    assert converted[0]["starting_players"][0]["yellow_cards"] == 1


def test_highlightly_lineups_persist_against_local_teams(tmp_path):
    engine = create_database_engine(tmp_path / "highlightly.db")
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
        lineups = [
            {"team_id": 1, "team_name": "Fiorentina", "formation": "4-3-3", "starting_players": [{"name": f"F{i}"} for i in range(11)], "substitutes_used": [], "unused_substitutes": []},
            {"team_id": 2, "team_name": "Juventus", "formation": "3-5-2", "starting_players": [{"name": f"J{i}"} for i in range(11)], "substitutes_used": [], "unused_substitutes": []},
        ]
        result = save_highlightly_lineups(session, match.id, lineups)
        session.commit()
        assert result == {"created": 2, "updated": 0}
        assert session.query(MatchLineup).count() == 2
        assert session.query(LineupPlayer).count() == 22
    engine.dispose()
