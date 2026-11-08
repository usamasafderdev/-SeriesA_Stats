from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.database import (
    create_database_engine,
    create_database_session,
    initialize_database,
)
from app.match_service import add_match, add_team
from app.models import LineupPlayer, Match, MatchLineup


@pytest.fixture
def database(tmp_path):
    """Create and clean up an isolated SQLite database."""
    database_engine = create_database_engine(tmp_path / "lineup_test.db")
    initialize_database(database_engine)
    session = create_database_session(database_engine)
    try:
        yield session, database_engine
    finally:
        session.close()
        database_engine.dispose()


def create_match(session):
    home_team = add_team(session, "Home Team")
    away_team = add_team(session, "Away Team")
    match = add_match(
        session,
        season="2025",
        match_date=datetime(2025, 4, 22, 18, 0),
        home_team_id=home_team.id,
        away_team_id=away_team.id,
        home_score=0,
        away_score=1,
        status="finished",
    )
    return match, home_team, away_team


def create_lineup(session, match, team, formation="4-3-3"):
    lineup = MatchLineup(match=match, team=team, formation=formation)
    session.add(lineup)
    session.flush()
    return lineup


def test_lineup_and_player_roles_are_saved(database):
    session, _ = database
    match, home_team, _ = create_match(session)
    lineup = create_lineup(session, match, home_team)
    lineup.players.extend(
        [
            LineupPlayer(
                api_player_id="player-1",
                player_name="Starter Example",
                shirt_number=9,
                position="Forward",
                formation_slot=1,
                player_role="starter",
                goals=1,
                assists=0,
                yellow_cards=0,
                red_cards=0,
            ),
            LineupPlayer(
                api_player_id="player-2",
                player_name="Used Substitute",
                player_role="used_substitute",
                minute_on=70,
                minute_off=90,
            ),
            LineupPlayer(
                api_player_id="player-3",
                player_name="Unused Substitute",
                player_role="unused_substitute",
            ),
        ]
    )
    session.commit()

    saved_match = session.get(Match, match.id)
    saved_lineup = saved_match.lineups[0]
    saved_players = {player.player_name: player for player in saved_lineup.players}
    starter = saved_players["Starter Example"]

    assert saved_lineup.team.name == "Home Team"
    assert saved_lineup.formation == "4-3-3"
    assert starter.player_role == "starter"
    assert starter.shirt_number == 9
    assert starter.formation_slot == 1
    assert starter.goals == 1
    assert starter.assists == 0
    assert starter.yellow_cards == 0
    assert starter.red_cards == 0
    assert saved_players["Used Substitute"].minute_on == 70
    assert saved_players["Used Substitute"].minute_off == 90
    assert saved_players["Unused Substitute"].goals is None


def test_optional_formation_and_player_fields_can_be_missing(database):
    session, _ = database
    match, _, away_team = create_match(session)
    lineup = create_lineup(session, match, away_team, formation=None)
    player = LineupPlayer(
        player_name="Player Without Optional Details",
        player_role="starter",
        formation_slot=None,
        goals=None,
        assists=0,
    )
    lineup.players.append(player)
    session.commit()

    assert lineup.formation is None
    assert player.api_player_id is None
    assert player.formation_slot is None
    assert player.goals is None
    assert player.assists == 0


def test_a_team_must_belong_to_the_match(database):
    session, _ = database
    match, _, _ = create_match(session)
    other_team = add_team(session, "Unrelated Team")

    session.add(MatchLineup(match=match, team=other_team))
    with pytest.raises(ValueError, match="one of the match teams"):
        session.flush()


def test_lineup_requires_an_existing_match_and_team(database):
    session, _ = database
    session.add(MatchLineup(match_id=999, team_id=999))

    with pytest.raises(ValueError, match="existing match and team"):
        session.flush()


def test_player_requires_an_existing_lineup(database):
    session, _ = database
    session.add(
        LineupPlayer(
            lineup_id=999,
            player_name="Player Without Lineup",
            player_role="starter",
        )
    )

    with pytest.raises(ValueError, match="existing lineup"):
        session.flush()


def test_duplicate_team_lineup_for_a_match_is_rejected(database):
    session, _ = database
    match, home_team, _ = create_match(session)
    create_lineup(session, match, home_team)
    session.add(MatchLineup(match=match, team=home_team))

    with pytest.raises(IntegrityError):
        session.flush()


def test_known_player_id_cannot_be_repeated_in_a_lineup(database):
    session, _ = database
    match, home_team, _ = create_match(session)
    lineup = create_lineup(session, match, home_team)
    lineup.players.extend(
        [
            LineupPlayer(
                api_player_id="same-player",
                player_name="First Entry",
                player_role="starter",
            ),
            LineupPlayer(
                api_player_id="same-player",
                player_name="Duplicate Entry",
                player_role="unused_substitute",
            ),
        ]
    )

    with pytest.raises(IntegrityError):
        session.flush()


def test_missing_player_ids_can_repeat_in_a_lineup(database):
    session, _ = database
    match, home_team, _ = create_match(session)
    lineup = create_lineup(session, match, home_team)
    lineup.players.extend(
        [
            LineupPlayer(player_name="First Unknown ID", player_role="starter"),
            LineupPlayer(
                player_name="Second Unknown ID",
                player_role="unused_substitute",
            ),
        ]
    )

    session.commit()

    assert len(lineup.players) == 2
    assert all(player.api_player_id is None for player in lineup.players)


@pytest.mark.parametrize(
    ("stat_name", "invalid_value"),
    [
        ("goals", -1),
        ("assists", -1),
        ("yellow_cards", -1),
        ("red_cards", -1),
    ],
)
def test_player_statistics_cannot_be_negative(database, stat_name, invalid_value):
    session, _ = database
    match, home_team, _ = create_match(session)
    lineup = create_lineup(session, match, home_team)
    player = LineupPlayer(
        player_name="Invalid Statistics Player",
        player_role="starter",
        **{stat_name: invalid_value},
    )
    lineup.players.append(player)

    with pytest.raises(IntegrityError):
        session.flush()


def test_player_role_must_be_one_of_the_supported_values(database):
    session, _ = database
    match, home_team, _ = create_match(session)
    lineup = create_lineup(session, match, home_team)
    lineup.players.append(
        LineupPlayer(player_name="Unknown Role", player_role="reserve")
    )

    with pytest.raises(IntegrityError):
        session.flush()


def test_create_all_keeps_existing_match_records(database):
    session, database_engine = database
    match, _, _ = create_match(session)
    match_id = match.id
    session.close()

    initialize_database(database_engine)
    second_session = create_database_session(database_engine)
    try:
        saved_match = second_session.get(Match, match_id)
        assert saved_match is not None
        assert saved_match.home_score == 0
        assert saved_match.away_score == 1
    finally:
        second_session.close()
