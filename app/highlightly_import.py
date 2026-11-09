"""Normalize Highlightly lineup and player box-score responses."""

from typing import Any
from datetime import datetime, timezone
from app.team_names import same_team

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.lineup_import import _validated_lineup
from app.models import Match, MatchLineup, Team

PLAYER_METRIC_FIELDS = (
    "rating", "minutes_played", "goals", "assists", "yellow_cards", "red_cards",
    "shots_total", "shots_on_target", "shots_off_target", "passes_total",
    "passes_successful", "passes_accuracy", "passes_key", "tackles_total",
    "interceptions_total", "dribbles_total", "dribbles_successful", "duels_total",
    "duels_won", "fouls_committed", "fouls_drawn", "goalkeeper_saves",
)


def has_player_performance(match: Match) -> bool:
    return any(getattr(player, field) is not None
               for lineup in match.lineups for player in lineup.players
               for field in PLAYER_METRIC_FIELDS)


def _list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _stat(player_stats: dict[str, Any], *names: str) -> Any:
    def key(value):
        return "".join(char for char in str(value).casefold() if char.isalnum())
    if isinstance(player_stats, list):
        player_stats = {key(item.get("displayName", item.get("name"))): item.get("value")
                        for item in player_stats if isinstance(item, dict)}
    if not isinstance(player_stats, dict):
        return None
    normalized = {key(name): value for name, value in player_stats.items()}
    return _first_present(*(normalized.get(key(name)) for name in names))


def _percentage(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip().removesuffix("%").strip()
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _player(value: dict[str, Any], stats: dict[str, Any] | None = None) -> dict[str, Any]:
    player_stats = (stats or {}).get("statistics", stats or {}) if isinstance(stats, dict) else {}
    player_stats = player_stats or value.get("statistics") or {}
    return {
        "player_id": value.get("id") or value.get("playerId"),
        "name": value.get("name") or value.get("playerName") or value.get("fullName"),
        "shirt_number": _first_present(value.get("shirtNumber"), value.get("jersey"), value.get("number")),
        "position": value.get("position"),
        "formation_slot": value.get("formationPlace") or value.get("positionNumber"),
        "minute_on": value.get("minuteOn"),
        "minute_off": value.get("minuteOff"),
        "rating": _first_present((stats or {}).get("rating"), value.get("rating"), value.get("matchRating"), _stat(player_stats, "rating", "matchRating")),
        "minutes_played": _first_present((stats or {}).get("minutesPlayed"), value.get("minutesPlayed"), value.get("minutes"), _stat(player_stats, "minutesPlayed", "minutes")),
        "shots_total": _stat(player_stats, "shotsTotal", "totalShots"),
        "shots_on_target": _stat(player_stats, "shotsOnTarget"),
        "shots_off_target": _stat(player_stats, "shotsOffTarget"),
        "goals": _stat(player_stats, "goals", "goalsScored"),
        "assists": _stat(player_stats, "assists"),
        "yellow_cards": _stat(player_stats, "yellowCards", "cardsYellow"),
        "red_cards": _stat(player_stats, "redCards", "cardsRed"),
        "passes_total": _stat(player_stats, "passesTotal"),
        "passes_successful": _stat(player_stats, "passesSuccessful"),
        "passes_accuracy": _percentage(_stat(player_stats, "passesAccuracy")),
        "passes_key": _stat(player_stats, "passesKey"),
        "tackles_total": _stat(player_stats, "tacklesTotal"),
        "interceptions_total": _stat(player_stats, "interceptionsTotal"),
        "dribbles_total": _stat(player_stats, "dribblesTotal"),
        "dribbles_successful": _stat(player_stats, "dribblesSuccessful"),
        "duels_total": _stat(player_stats, "duelsTotal"),
        "duels_won": _stat(player_stats, "duelsWon"),
        "fouls_committed": _stat(player_stats, "foulsCommitted", "fouls"),
        "fouls_drawn": _stat(player_stats, "foulsDrawn"),
        "goalkeeper_saves": _stat(player_stats, "saves", "goalkeeperSaves"),
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
        # Copy before adding layout slots: a cached raw response stays unchanged.
        flattened_players = [dict(player) for player in flattened_players]
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
    ordered = [[item for item in normalized if _same_team_name(str(item.get("team_name")), name)]
               for name in expected]
    if len(normalized) != 2 or any(len(items) != 1 for items in ordered):
        raise ValueError("Highlightly lineups do not match the stored home and away teams.")
    return [items[0] for items in ordered]


def merge_highlightly_box_score(
    players: list[Any],
    box_score: Any,
) -> int:
    """Merge supplied Highlightly metrics onto already-cached lineup players."""
    box_players = [
        player
        for team in box_score if isinstance(team, dict)
        for player in _list(team.get("players"))
    ] if isinstance(box_score, list) else _list(
        box_score.get("players") if isinstance(box_score, dict) else []
    )
    by_id = {
        str(item.get("id") or item.get("playerId")): item
        for item in box_players
        if item.get("id") is not None or item.get("playerId") is not None
    }
    updated = 0
    for player in players:
        source = by_id.get(str(player.api_player_id))
        if source is None:
            continue
        stats = source.get("statistics") or {}
        values = _player(source, source)
        changed = False
        for field in PLAYER_METRIC_FIELDS:
            value = values.get(field)
            if value is not None:
                if field == "rating":
                    value = float(value)
                    if not 0 <= value <= 10:
                        raise ValueError("Player rating must be between 0 and 10.")
                elif field == "passes_accuracy":
                    value = float(value)
                    if not 0 <= value <= 100:
                        raise ValueError("Pass accuracy must be between 0 and 100.")
                else:
                    number = float(value)
                    if not number.is_integer() or number < 0:
                        raise ValueError(f"{field} must be a non-negative whole number.")
                    value = int(number)
                setattr(player, field, value)
                changed = True
        updated += int(changed)
    return updated


def _normalize(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _same_team_name(left: str, right: str) -> bool:
    return same_team(left, right)


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
            summary["updated"] += 1
        if formation is not None:
            lineup.formation = formation
        existing = {player.api_player_id: player for player in lineup.players
                    if player.api_player_id is not None}
        for player in players:
            saved_player = existing.get(player.api_player_id) if player.api_player_id else None
            if saved_player is None:
                lineup.players.append(player)
            else:
                for column in player.__table__.columns:
                    if column.name not in ("id", "lineup_id"):
                        value = getattr(player, column.name)
                        if value is not None:
                            setattr(saved_player, column.name, value)
        lineup.source = "highlightly"
        lineup.provider_match_id = match.highlightly_match_id
        lineup.fetched_at = datetime.now(timezone.utc)
    session.flush()
    return summary
