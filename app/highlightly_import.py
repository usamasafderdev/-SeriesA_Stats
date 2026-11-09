"""Normalize Highlightly lineup and player box-score responses."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.lineup_import import _validated_lineup
from app.models import Match, MatchLineup, Team


def _list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _player(value: dict[str, Any], stats: dict[str, Any] | None = None) -> dict[str, Any]:
    player_stats = (stats or {}).get("statistics", stats or {}) if isinstance(stats, dict) else {}
    player_stats = player_stats or value.get("statistics") or {}
    return {
        "player_id": value.get("id") or value.get("playerId"),
        "name": value.get("name") or value.get("playerName") or value.get("fullName"),
        "shirt_number": value.get("shirtNumber") or value.get("jersey") or value.get("number"),
        "position": value.get("position"),
        "formation_slot": value.get("formationPlace") or value.get("positionNumber"),
        "minute_on": value.get("minuteOn"),
        "minute_off": value.get("minuteOff"),
        "rating": _first_present(value.get("rating"), value.get("matchRating")),
        "minutes_played": _first_present(value.get("minutesPlayed"), value.get("minutes")),
        "shots_total": _first_present(player_stats.get("shotsTotal"), player_stats.get("totalShots")),
        "shots_on_target": player_stats.get("shotsOnTarget"),
        "goals": _first_present(player_stats.get("goals"), player_stats.get("goalsScored")),
        "assists": player_stats.get("assists"),
        "yellow_cards": _first_present(player_stats.get("yellowCards"), player_stats.get("cardsYellow")),
        "red_cards": _first_present(player_stats.get("redCards"), player_stats.get("cardsRed")),
    }


def _team_id(lineup: dict[str, Any]) -> Any:
    team = lineup.get("team") or lineup
    return lineup.get("teamId") or (team.get("id") if isinstance(team, dict) else None)


def _team_name(lineup: dict[str, Any]) -> str | None:
    team = lineup.get("team") or lineup
    return lineup.get("teamName") or (
        team.get("name") if isinstance(team, dict) else None
    )


def convert_highlightly_lineups(
    body: Any,
    box_score: Any,
    home_name: str,
    away_name: str,
) -> list[dict[str, Any]]:
    """Return the existing importer's normalized two-lineup contract."""
    records = body.get("lineups") if isinstance(body, dict) else body
    if isinstance(body, dict) and "homeTeam" in body and "awayTeam" in body:
        records = [body["homeTeam"], body["awayTeam"]]
    if isinstance(records, dict):
        records = records.get("home", []) + records.get("away", [])
    records = _list(records)
    if isinstance(box_score, list):
        box_players = [
            player
            for team in box_score
            if isinstance(team, dict)
            for player in _list(team.get("players"))
        ]
    else:
        box_players = box_score.get("players", []) if isinstance(box_score, dict) else []
    by_id = {
        str(item.get("id") or item.get("playerId")): item
        for item in _list(box_players)
        if item.get("id") is not None or item.get("playerId") is not None
    }
    normalized = []
    for lineup in records:
        name = _team_name(lineup)
        players = lineup.get("initialLineup") or lineup.get("startingXI") or lineup.get("startingPlayers") or []
        substitutes = lineup.get("substitutes") or lineup.get("substitutePlayers") or []
        flattened_players = [
            player
            for row in players if isinstance(row, list)
            for player in row
            if isinstance(player, dict)
        ] if any(isinstance(row, list) for row in players) else _list(players)
        for index, player in enumerate(flattened_players, start=1):
            player.setdefault("formationPlace", index)
        starters = [_player(item, by_id.get(str(item.get("id") or item.get("playerId")))) for item in flattened_players]
        subs = [_player(item, by_id.get(str(item.get("id") or item.get("playerId")))) for item in _list(substitutes)]
        normalized.append({
            "team_id": _team_id(lineup),
            "team_name": name,
            "formation": lineup.get("formation"),
            "starting_players": starters,
            "substitutes_used": [item for item in subs if item.get("minute_on") is not None],
            "unused_substitutes": [item for item in subs if item.get("minute_on") is None],
        })
    expected = [home_name, away_name]
    actual = [str(item.get("team_name")) for item in normalized]
    if len(actual) != 2 or any(
        not _same_team_name(provider_name, stored_name)
        for provider_name, stored_name in zip(actual, expected)
    ):
        raise ValueError("Highlightly lineups do not match the stored home and away teams.")
    return normalized


def _normalize(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _same_team_name(left: str, right: str) -> bool:
    left_name = _normalize(left)
    right_name = _normalize(right)
    if left_name == right_name:
        return True
    aliases = ("acf", "fc", "calcio", "footballclub")
    for alias in aliases:
        left_name = left_name.removeprefix(alias).removesuffix(alias)
        right_name = right_name.removeprefix(alias).removesuffix(alias)
    return left_name == right_name


def save_highlightly_lineups(
    session: Any,
    match_id: int,
    normalized_lineups: list[dict[str, Any]],
) -> dict[str, int]:
    """Persist Highlightly lineups using the existing local lineup schema."""
    if len(normalized_lineups) != 2:
        raise ValueError("Highlightly must return both team lineups.")
    match = session.scalar(
        select(Match)
        .options(selectinload(Match.lineups).selectinload(MatchLineup.players))
        .where(Match.id == match_id, Match.data_source == "live")
    )
    if match is None:
        raise ValueError("Lineups can only be saved for a stored live match.")
    parsed = [_validated_lineup(item) for item in normalized_lineups]
    saved = {lineup.team_id: lineup for lineup in match.lineups}
    summary = {"created": 0, "updated": 0}
    for source, (_source_team_id, formation, players) in zip(normalized_lineups, parsed):
        team_name = _normalize(str(source.get("team_name")))
        team = next(
            team for team in (match.home_team, match.away_team)
            if _same_team_name(str(source.get("team_name")), team.name)
        )
        lineup = saved.get(team.id)
        if lineup is None:
            lineup = MatchLineup(match=match, team=team)
            session.add(lineup)
            summary["created"] += 1
        else:
            lineup.players.clear()
            summary["updated"] += 1
        lineup.formation = formation
        lineup.players.extend(players)
    session.flush()
    return summary
