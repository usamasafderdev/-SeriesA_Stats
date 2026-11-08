from datetime import datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.database import (
    create_database_engine,
    create_database_session,
    initialize_database,
)
from app.lineup_import import convert_and_save_api_lineups, save_api_lineups
from app.match_service import add_match, add_team
from app.models import LineupPlayer, Match, MatchLineup


@pytest.fixture
def database(tmp_path):
    database_engine = create_database_engine(tmp_path / "lineup_import.db")
    initialize_database(database_engine)
    session = create_database_session(database_engine)
    try:
        yield session
    finally:
        session.close()
        database_engine.dispose()


def add_live_match(session):
    home = add_team(session, "Live Home", api_team_id=239, data_source="live")
    away = add_team(session, "Live Away", api_team_id=268, data_source="live")
    match = add_match(
        session,
        season="2025",
        match_date=datetime(2026, 5, 24),
        home_team_id=home.id,
        away_team_id=away.id,
        home_score=2,
        away_score=2,
        status="final",
        api_match_id=737158,
        data_source="live",
    )
    return match, home, away


def player_record(index, role, **values):
    return {
        "player_id": str(index),
        "name": f"Sample Player {index}",
        "shirt_number": str(index),
        "position": "Forward",
        "formation_slot": index,
        "minute_on": 0 if role == "starter" else None,
        "minute_off": None,
        "goals": 0,
        "assists": 0,
        "yellow_cards": 0,
        "red_cards": 0,
        **values,
    }


def raw_lineup(team_id, offset=0, formation="4-3-3"):
    return {
        "team_id": str(team_id),
        "formation": formation,
        "starting_xi": [
            {
                "player_id": str(offset + index),
                "name": f"Starting Player {offset + index}",
                "jersey": str(index),
                "position": "Midfielder",
                "formation_place": index,
                "minute_on": 0,
                "goals": 0,
                "assists": 0,
                "yellow_cards": 0,
                "red_cards": 0,
            }
            for index in range(1, 12)
        ],
        "substitutes_used": [
            {
                "player_id": str(offset + 12),
                "name": "Used Substitute",
                "jersey": "17",
                "position": "Forward",
                "formation_place": None,
                "minute_on": 70,
                "minute_off": None,
                "goals": 1,
                "assists": None,
                "yellow_cards": 0,
                "red_cards": 0,
            }
        ],
        "unused_substitutes": [
            {
                "player_id": str(offset + 13),
                "name": "Unused Substitute",
                "jersey": "21",
                "position": None,
                "formation_place": None,
            }
        ],
    }


def normalized_lineup(team_id, offset=0, formation="4-3-3"):
    return {
        "team_id": team_id,
        "formation": formation,
        "starting_players": [
            player_record(offset + index, "starter")
            for index in range(1, 12)
        ],
        "substitutes_used": [
            player_record(
                offset + 12,
                "used_substitute",
                minute_on=70,
                goals=1,
                assists=None,
            )
        ],
        "unused_substitutes": [
            player_record(
                offset + 13,
                "unused_substitute",
                shirt_number=None,
                position=None,
                formation_slot=None,
                minute_on=None,
                minute_off=None,
                goals=None,
                assists=None,
                yellow_cards=None,
                red_cards=None,
            )
        ],
    }


def two_lineups(home_id, away_id, offset=0, formation="4-3-3"):
    return [
        normalized_lineup(home_id, offset, formation),
        normalized_lineup(away_id, offset + 100, formation),
    ]


def test_import_saves_both_teams_and_every_player_role(database):
    match, home, away = add_live_match(database)

    summary = convert_and_save_api_lineups(
        database,
        match.id,
        [raw_lineup(239, 0), raw_lineup(268, 100, "3-5-2")],
    )
    database.commit()

    saved_lineups = database.scalars(
        select(MatchLineup).order_by(MatchLineup.team_id)
    ).all()
    home_lineup = next(item for item in saved_lineups if item.team_id == home.id)
    away_lineup = next(item for item in saved_lineups if item.team_id == away.id)

    assert summary == {"created": 2, "updated": 0}
    assert home_lineup.match_id == match.id
    assert away_lineup.team_id == away.id
    assert home_lineup.formation == "4-3-3"
    assert away_lineup.formation == "3-5-2"
    assert sum(player.player_role == "starter" for player in home_lineup.players) == 11
    imported_starter = next(
        player for player in home_lineup.players if player.player_role == "starter"
    )
    assert imported_starter.api_player_id == "1"
    assert imported_starter.player_name == "Starting Player 1"
    assert imported_starter.shirt_number == 1
    assert imported_starter.position == "Midfielder"
    assert any(
        player.player_role == "used_substitute"
        and player.minute_on == 70
        and player.goals == 1
        and player.assists is None
        for player in home_lineup.players
    )
    assert any(
        player.player_role == "unused_substitute"
        and player.goals is None
        and player.yellow_cards is None
        for player in home_lineup.players
    )


def test_repeated_import_updates_instead_of_duplicating(database):
    match, home, away = add_live_match(database)
    first = save_api_lineups(database, match.id, two_lineups(239, 268))
    database.commit()
    first_lineup = database.scalar(
        select(MatchLineup).where(MatchLineup.team_id == home.id)
    )
    first_lineup_id = first_lineup.id

    changed = two_lineups(239, 268, formation="4-2-3-1")
    changed[0]["starting_players"][0]["name"] = "Updated Sample Name"
    changed[0]["starting_players"][0]["goals"] = 2
    second = save_api_lineups(database, match.id, changed)
    database.commit()

    saved_lineups = database.scalars(select(MatchLineup)).all()
    updated_home = database.get(MatchLineup, first_lineup_id)
    assert first == {"created": 2, "updated": 0}
    assert second == {"created": 0, "updated": 2}
    assert len(saved_lineups) == 2
    assert updated_home.formation == "4-2-3-1"
    assert len(updated_home.players) == 11 + 2
    assert any(
        player.player_name == "Updated Sample Name" and player.goals == 2
        for player in updated_home.players
    )


def test_missing_statistics_and_recorded_zero_are_preserved(database):
    match, home, away = add_live_match(database)
    lineups = two_lineups(239, 268)
    lineups[0]["starting_players"][0]["goals"] = 0
    lineups[0]["starting_players"][1]["goals"] = None

    save_api_lineups(database, match.id, lineups)
    database.commit()

    players = database.scalars(
        select(LineupPlayer).where(LineupPlayer.lineup_id == 1)
    ).all()
    goals_by_player_id = {
        player.api_player_id: player.goals for player in players
    }
    assert goals_by_player_id["1"] == 0
    assert goals_by_player_id["2"] is None


def test_invalid_or_incomplete_second_lineup_does_not_replace_saved_data(database):
    match, home, away = add_live_match(database)
    save_api_lineups(database, match.id, two_lineups(239, 268))
    database.commit()
    saved_player = database.scalar(
        select(LineupPlayer).where(
            LineupPlayer.lineup_id == 1,
            LineupPlayer.player_role == "starter",
        )
    )
    original_name = saved_player.player_name

    incomplete = two_lineups(239, 268)
    incomplete[0]["starting_players"][0]["player_name"] = "Changed Name"
    incomplete[1]["starting_players"].pop()
    with pytest.raises(ValueError, match="exactly 11 starters"):
        save_api_lineups(database, match.id, incomplete)

    database.expire_all()
    saved_player = database.get(LineupPlayer, saved_player.id)
    assert saved_player.player_name == original_name


def test_database_failure_rolls_back_replacement(database, monkeypatch):
    match, home, away = add_live_match(database)
    save_api_lineups(database, match.id, two_lineups(239, 268))
    database.commit()
    first_player = database.scalar(
        select(LineupPlayer).where(LineupPlayer.lineup_id == 1)
    )
    first_player_id = first_player.id
    original_name = first_player.player_name

    original_flush = database.flush

    def fail_flush(*_args, **_kwargs):
        raise RuntimeError("simulated database failure")

    monkeypatch.setattr(database, "flush", fail_flush)
    with pytest.raises(RuntimeError, match="simulated database failure"):
        save_api_lineups(
            database,
            match.id,
            two_lineups(239, 268, formation="3-4-2-1"),
        )
    monkeypatch.setattr(database, "flush", original_flush)
    database.expire_all()

    saved_lineup = database.scalar(
        select(MatchLineup).where(MatchLineup.team_id == home.id)
    )
    saved_player = database.get(LineupPlayer, first_player_id)
    assert saved_lineup.formation == "4-3-3"
    assert saved_player.player_name == original_name


def test_lineups_cannot_be_saved_to_demo_match(database):
    home = add_team(database, "Demo Home")
    away = add_team(database, "Demo Away")
    match = add_match(
        database,
        season="2025",
        match_date=datetime(2025, 1, 1),
        home_team_id=home.id,
        away_team_id=away.id,
    )

    with pytest.raises(ValueError, match="stored live match"):
        save_api_lineups(
            database,
            match.id,
            two_lineups(239, 268),
        )


def test_team_ids_must_match_the_match(database):
    match, _home, _away = add_live_match(database)
    other = add_team(database, "Other Live", api_team_id=999, data_source="live")

    with pytest.raises(ValueError, match="must match the stored match teams"):
        save_api_lineups(database, match.id, two_lineups(999, 1000))


def test_negative_player_statistics_are_rejected(database):
    match, home, away = add_live_match(database)
    lineups = two_lineups(239, 268)
    lineups[0]["starting_players"][0]["yellow_cards"] = -1

    with pytest.raises(ValueError, match="cannot be negative"):
        save_api_lineups(database, match.id, lineups)


def test_invalid_foreign_keys_are_rejected_by_sqlite(database):
    with pytest.raises(IntegrityError):
        database.execute(
            text(
                "INSERT INTO match_lineups (match_id, team_id, formation) "
                "VALUES (999, 999, NULL)"
            )
        )
