"""Safely match a StrikerAPI fixture to one stored live fixture."""

import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

from app.models import Match


def _name(value: str) -> str:
    plain = unicodedata.normalize("NFKD", value)
    return re.sub(r"[^a-z0-9]", "", plain.encode("ascii", "ignore").decode().casefold())


def _date(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _score(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def find_matching_striker_game(
    match_record: Match,
    games: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return one exact season/team/date/score match or raise clearly."""
    candidates = []
    match_date = match_record.match_date
    if match_date.tzinfo is None:
        match_date = match_date.replace(tzinfo=timezone.utc)
    else:
        match_date = match_date.astimezone(timezone.utc)

    for game in games:
        if not isinstance(game, dict):
            continue
        home = game.get("home")
        away = game.get("away")
        if not isinstance(home, dict) or not isinstance(away, dict):
            continue
        if (
            _name(str(home.get("name", ""))) != _name(match_record.home_team.name)
            or _name(str(away.get("name", ""))) != _name(match_record.away_team.name)
        ):
            continue
        game_date = _date(game.get("date"))
        if game_date is None or game_date.date() != match_date.date():
            continue
        home_score = _score(home.get("score"))
        away_score = _score(away.get("score"))
        if (
            match_record.home_score is not None
            and home_score != match_record.home_score
        ) or (
            match_record.away_score is not None
            and away_score != match_record.away_score
        ):
            continue
        candidates.append(game)

    if len(candidates) != 1:
        raise ValueError(
            "StrikerAPI did not return exactly one fixture matching the stored "
            "teams, season date, and score."
        )
    game_id = candidates[0].get("game_id")
    if game_id is None:
        raise ValueError("The matched StrikerAPI fixture has no game ID.")
    return candidates[0]
