from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Match, Team


LIVE_SOURCE = "live"


def _as_integer(value: Any, field_name: str, allow_missing: bool = False) -> int | None:
    if value is None and allow_missing:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a whole number.")
    try:
        converted = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a whole number.") from None
    if str(value).strip() != str(converted) and not isinstance(value, int):
        raise ValueError(f"{field_name} must be a whole number.")
    if converted < 0:
        raise ValueError(f"{field_name} cannot be negative.")
    return converted


def _required_name(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required.")
    return value.strip()


def _parse_match_date(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("match_date must be a valid ISO date or datetime.")
    try:
        result = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("match_date must be a valid ISO date or datetime.") from None

    if result.tzinfo is not None:
        result = result.astimezone(timezone.utc).replace(tzinfo=None)
    return result


def _validate_match(match: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(match, dict):
        raise ValueError("Each normalized match must be a dictionary.")

    match_id = _as_integer(match.get("match_id"), "match_id")
    home_team_id = _as_integer(match.get("home_team_id"), "home_team_id")
    away_team_id = _as_integer(match.get("away_team_id"), "away_team_id")
    if match_id is None or home_team_id is None or away_team_id is None:
        raise ValueError("Match and team IDs are required.")
    if home_team_id == away_team_id:
        raise ValueError("Home and away teams must be different.")

    season = match.get("season")
    if season is None or not str(season).strip():
        raise ValueError("season is required.")

    home_score = _as_integer(match.get("home_score"), "home_score", True)
    away_score = _as_integer(match.get("away_score"), "away_score", True)

    return {
        "match_id": match_id,
        "season": str(season).strip(),
        "match_date": _parse_match_date(match.get("match_date")),
        "home_team_id": home_team_id,
        "home_team_name": _required_name(
            match.get("home_team_name"),
            "home_team_name",
        ),
        "away_team_id": away_team_id,
        "away_team_name": _required_name(
            match.get("away_team_name"),
            "away_team_name",
        ),
        "home_score": home_score,
        "away_score": away_score,
        "status": _required_name(match.get("status"), "status"),
    }


def _get_or_create_team(
    db_session: Session,
    team_id: int,
    team_name: str,
) -> tuple[Team, bool]:
    team = db_session.scalar(
        select(Team).where(
            Team.data_source == LIVE_SOURCE,
            Team.api_team_id == team_id,
        )
    )
    changed = False

    if team is not None:
        if team.name != team_name:
            name_owner = db_session.scalar(
                select(Team).where(
                    Team.data_source == LIVE_SOURCE,
                    Team.name == team_name,
                    Team.id != team.id,
                )
            )
            if name_owner is not None:
                raise ValueError(
                    f"Team name '{team_name}' is already assigned to another live team."
                )
            team.name = team_name
            changed = True
        return team, changed

    team = db_session.scalar(
        select(Team).where(
            Team.data_source == LIVE_SOURCE,
            Team.name == team_name,
        )
    )
    if team is not None:
        if team.api_team_id not in (None, team_id):
            raise ValueError(
                f"Team name '{team_name}' belongs to a different live team ID."
            )
        if team.api_team_id is None:
            team.api_team_id = team_id
            changed = True
        return team, changed

    team = Team(
        api_team_id=team_id,
        name=team_name,
        data_source=LIVE_SOURCE,
    )
    db_session.add(team)
    db_session.flush()
    return team, True


def _save_one(
    db_session: Session,
    match: dict[str, Any],
) -> tuple[Match, str]:
    home_team, home_team_changed = _get_or_create_team(
        db_session,
        match["home_team_id"],
        match["home_team_name"],
    )
    away_team, away_team_changed = _get_or_create_team(
        db_session,
        match["away_team_id"],
        match["away_team_name"],
    )
    if home_team.id == away_team.id:
        raise ValueError("Home and away teams must be different.")

    saved_match = db_session.scalar(
        select(Match).where(
            Match.data_source == LIVE_SOURCE,
            Match.api_match_id == match["match_id"],
        )
    )
    match_values = {
        "season": match["season"],
        "match_date": match["match_date"],
        "home_team_id": home_team.id,
        "away_team_id": away_team.id,
        "home_score": match["home_score"],
        "away_score": match["away_score"],
        "status": match["status"],
    }

    if saved_match is None:
        saved_match = Match(
            api_match_id=match["match_id"],
            data_source=LIVE_SOURCE,
            **match_values,
        )
        db_session.add(saved_match)
        db_session.flush()
        return saved_match, "created"

    changed = home_team_changed or away_team_changed
    for field_name, new_value in match_values.items():
        if getattr(saved_match, field_name) != new_value:
            setattr(saved_match, field_name, new_value)
            changed = True

    return saved_match, "updated" if changed else "skipped"


def _transaction(db_session: Session):
    """Use a transaction when possible, or a savepoint in an existing one."""
    if db_session.in_transaction():
        return db_session.begin_nested()
    return db_session.begin()


def save_api_match(
    db_session: Session,
    normalized_match: dict[str, Any],
) -> Match:
    """Validate and save one normalized API match and its teams."""
    match = _validate_match(normalized_match)
    with _transaction(db_session):
        saved_match, _result = _save_one(db_session, match)
    return saved_match


def save_api_matches(
    db_session: Session,
    normalized_matches: list[dict[str, Any]],
) -> dict[str, int]:
    """Save a batch of normalized API matches in one transaction."""
    if not isinstance(normalized_matches, (list, tuple)):
        raise ValueError("normalized_matches must be a list or tuple.")
    matches = [_validate_match(match) for match in normalized_matches]
    summary = {"created": 0, "updated": 0, "skipped": 0}

    with _transaction(db_session):
        for match in matches:
            _saved_match, result = _save_one(db_session, match)
            summary[result] += 1

    return summary
