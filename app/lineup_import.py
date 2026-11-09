from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.data_converter import convert_lineup
from app.models import LineupPlayer, Match, MatchLineup, Team


PLAYER_LISTS = (
    ("starting_players", "starter"),
    ("substitutes_used", "used_substitute"),
    ("unused_substitutes", "unused_substitute"),
)
PLAYER_STATISTICS = (
    "goals",
    "assists",
    "yellow_cards",
    "red_cards",
)


def _integer_or_none(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a non-negative whole number.")
    try:
        converted = int(value)
    except (TypeError, ValueError):
        raise ValueError(
            f"{field_name} must be a non-negative whole number."
        ) from None
    if str(value).strip() != str(converted) and not isinstance(value, int):
        raise ValueError(f"{field_name} must be a non-negative whole number.")
    if converted < 0:
        raise ValueError(f"{field_name} cannot be negative.")
    return converted


def _required_player_name(player: dict[str, Any]) -> str:
    name = player.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Every lineup player must have a name.")
    return name.strip()


def _player_record(
    player_data: dict[str, Any],
    player_role: str,
) -> LineupPlayer:
    player_id = player_data.get("player_id")
    if isinstance(player_id, bool) or (
        player_id is not None and not isinstance(player_id, (int, str))
    ):
        raise ValueError("player_id must be a whole number or string.")
    if player_id is not None and not str(player_id).strip():
        player_id = None
    position = player_data.get("position")
    if position is not None and not isinstance(position, str):
        raise ValueError("position must be text or missing.")

    player_fields: dict[str, Any] = {
        "api_player_id": str(player_id) if player_id is not None else None,
        "player_name": _required_player_name(player_data),
        "shirt_number": _integer_or_none(
            player_data.get("shirt_number"),
            "shirt_number",
        ),
        "position": position,
        "formation_slot": _integer_or_none(
            player_data.get("formation_slot"),
            "formation_slot",
        ),
        "player_role": player_role,
        "minute_on": _integer_or_none(player_data.get("minute_on"), "minute_on"),
        "minute_off": _integer_or_none(
            player_data.get("minute_off"),
            "minute_off",
        ),
        "rating": player_data.get("rating"),
        "minutes_played": _integer_or_none(
            player_data.get("minutes_played"), "minutes_played"
        ),
        "shots_total": _integer_or_none(
            player_data.get("shots_total"), "shots_total"
        ),
        "shots_on_target": _integer_or_none(
            player_data.get("shots_on_target"), "shots_on_target"
        ),
        "shots_off_target": _integer_or_none(
            player_data.get("shots_off_target"), "shots_off_target"
        ),
        "passes_total": _integer_or_none(player_data.get("passes_total"), "passes_total"),
        "passes_successful": _integer_or_none(
            player_data.get("passes_successful"), "passes_successful"
        ),
        "passes_accuracy": player_data.get("passes_accuracy"),
        "passes_key": _integer_or_none(player_data.get("passes_key"), "passes_key"),
        "tackles_total": _integer_or_none(
            player_data.get("tackles_total"), "tackles_total"
        ),
        "interceptions_total": _integer_or_none(
            player_data.get("interceptions_total"), "interceptions_total"
        ),
        "dribbles_total": _integer_or_none(
            player_data.get("dribbles_total"), "dribbles_total"
        ),
        "dribbles_successful": _integer_or_none(
            player_data.get("dribbles_successful"), "dribbles_successful"
        ),
        "duels_total": _integer_or_none(player_data.get("duels_total"), "duels_total"),
        "duels_won": _integer_or_none(player_data.get("duels_won"), "duels_won"),
        "fouls_committed": _integer_or_none(
            player_data.get("fouls_committed"), "fouls_committed"
        ),
        "fouls_drawn": _integer_or_none(player_data.get("fouls_drawn"), "fouls_drawn"),
        "goalkeeper_saves": _integer_or_none(
            player_data.get("goalkeeper_saves"), "goalkeeper_saves"
        ),
    }
    player_fields.update(
        {
            statistic: _integer_or_none(player_data.get(statistic), statistic)
            for statistic in PLAYER_STATISTICS
        }
    )
    return LineupPlayer(**player_fields)


def _validated_lineup(
    lineup_data: dict[str, Any],
) -> tuple[int, str | None, list[LineupPlayer]]:
    team_id = _integer_or_none(lineup_data.get("team_id"), "team_id")
    if team_id is None:
        raise ValueError("Each lineup must include a valid team ID.") from None

    formation = lineup_data.get("formation")
    if formation is not None:
        if not isinstance(formation, str) or not formation.strip():
            raise ValueError("Formation must be a non-empty string or missing.")
        formation = formation.strip()

    starting_players = lineup_data.get("starting_players")
    used_substitutes = lineup_data.get("substitutes_used")
    unused_substitutes = lineup_data.get("unused_substitutes")
    for field_name, players in (
        ("starting_players", starting_players),
        ("substitutes_used", used_substitutes),
        ("unused_substitutes", unused_substitutes),
    ):
        if not isinstance(players, list):
            raise ValueError(f"{field_name} must be a list.")
    if len(starting_players) != 11:
        raise ValueError("Each team lineup must contain exactly 11 starters.")

    all_players = []
    seen_player_ids = set()
    for player_list, role in PLAYER_LISTS:
        for player_data in lineup_data[player_list]:
            if not isinstance(player_data, dict):
                raise ValueError("Each player record must be an object.")
            player = _player_record(player_data, role)
            if player.api_player_id is not None:
                if player.api_player_id in seen_player_ids:
                    raise ValueError("A player ID cannot repeat within a lineup.")
                seen_player_ids.add(player.api_player_id)
            all_players.append(player)

    return team_id, formation, all_players


def _transaction(db_session: Session):
    """Use a savepoint if the caller already has an open transaction."""
    if db_session.in_transaction():
        return db_session.begin_nested()
    return db_session.begin()


def save_api_lineups(
    db_session: Session,
    match_id: int,
    normalized_lineups: list[dict[str, Any]],
) -> dict[str, int]:
    """Create or safely replace both teams' lineups for a stored live match."""
    if not isinstance(normalized_lineups, list) or len(normalized_lineups) != 2:
        raise ValueError("Exactly two team lineups are required.")

    parsed_lineups = [_validated_lineup(lineup) for lineup in normalized_lineups]
    api_team_ids = [lineup[0] for lineup in parsed_lineups]
    if api_team_ids[0] == api_team_ids[1]:
        raise ValueError("The home and away lineups must use different teams.")

    with _transaction(db_session):
        match = db_session.scalar(
            select(Match)
            .options(selectinload(Match.lineups).selectinload(MatchLineup.players))
            .where(Match.id == match_id, Match.data_source == "live")
        )
        if match is None:
            raise ValueError("Lineups can only be saved for a stored live match.")

        match_api_team_ids = {
            match.home_team.api_team_id,
            match.away_team.api_team_id,
        }
        if set(api_team_ids) != match_api_team_ids:
            raise ValueError("Lineup teams must match the stored match teams.")

        saved_lineups = {lineup.team_id: lineup for lineup in match.lineups}
        summary = {"created": 0, "updated": 0}
        for api_team_id, formation, players in parsed_lineups:
            team = db_session.scalar(
                select(Team).where(
                    Team.data_source == "live",
                    Team.api_team_id == api_team_id,
                )
            )
            if team is None:
                raise ValueError("Each lineup team must be a stored live team.")

            lineup = saved_lineups.get(team.id)
            if lineup is None:
                lineup = MatchLineup(match=match, team=team)
                db_session.add(lineup)
                summary["created"] += 1
            else:
                lineup.players.clear()
                db_session.flush()
                summary["updated"] += 1

            lineup.formation = formation
            lineup.players.extend(players)
        db_session.flush()

    return summary


def convert_and_save_api_lineups(
    db_session: Session,
    match_id: int,
    api_lineups: list[dict[str, Any]],
) -> dict[str, int]:
    """Normalize provider lineup records, then store them in one transaction."""
    if not isinstance(api_lineups, list):
        raise ValueError("The provider lineups field must be a list.")
    normalized_lineups = []
    for api_lineup in api_lineups:
        if not isinstance(api_lineup, dict):
            raise ValueError("Each provider lineup must be an object.")
        normalized_lineups.append(convert_lineup(api_lineup))
    return save_api_lineups(db_session, match_id, normalized_lineups)
