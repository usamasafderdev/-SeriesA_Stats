from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models import Match, MatchStatistics, Team


DATA_SOURCES = {"demo", "live"}


def _check_data_source(data_source: str) -> None:
    """Keep sample and live records in clearly named groups."""
    if data_source not in DATA_SOURCES:
        raise ValueError("data_source must be 'demo' or 'live'.")


def _check_possession(value: float | None, field_name: str) -> None:
    if value is not None and (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 0 <= value <= 100
    ):
        raise ValueError(f"{field_name} must be a number between 0 and 100.")


def _check_non_negative_integer(value: int | None, field_name: str) -> None:
    if value is not None and (
        isinstance(value, bool) or not isinstance(value, int) or value < 0
    ):
        raise ValueError(f"{field_name} must be a non-negative whole number.")


def add_team(
    session: Session,
    name: str,
    api_team_id: int | None = None,
    logo_url: str | None = None,
    data_source: str = "demo",
) -> Team:
    """Add a team and return the saved database record."""
    team_name = name.strip()
    if not team_name:
        raise ValueError("Team name cannot be empty.")
    _check_data_source(data_source)

    team = Team(
        name=team_name,
        api_team_id=api_team_id,
        logo_url=logo_url,
        data_source=data_source,
    )
    session.add(team)
    try:
        session.commit()
        session.refresh(team)
    except IntegrityError:
        session.rollback()
        raise
    return team


def find_team_by_id(
    session: Session,
    team_id: int,
    data_source: str = "demo",
) -> Team | None:
    """Find a team only within the requested data source."""
    _check_data_source(data_source)
    return (
        session.query(Team)
        .filter(Team.id == team_id, Team.data_source == data_source)
        .first()
    )


def add_match(
    session: Session,
    season: str,
    match_date: datetime,
    home_team_id: int,
    away_team_id: int,
    home_score: int | None = None,
    away_score: int | None = None,
    status: str = "scheduled",
    api_match_id: int | None = None,
    data_source: str = "demo",
) -> Match:
    """Add a match whose teams belong to the same data source."""
    season_name = season.strip()
    if not season_name:
        raise ValueError("Season cannot be empty.")
    if not isinstance(match_date, datetime):
        raise ValueError("match_date must be a datetime value.")
    if home_team_id == away_team_id:
        raise ValueError("A team cannot play against itself.")
    _check_non_negative_integer(home_score, "home_score")
    _check_non_negative_integer(away_score, "away_score")
    match_status = status.strip()
    if not match_status:
        raise ValueError("Status cannot be empty.")
    _check_data_source(data_source)

    home_team = find_team_by_id(session, home_team_id, data_source)
    away_team = find_team_by_id(session, away_team_id, data_source)
    if home_team is None or away_team is None:
        raise ValueError("Both teams must exist in the selected data source.")

    match_record = Match(
        api_match_id=api_match_id,
        season=season_name,
        match_date=match_date,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        home_score=home_score,
        away_score=away_score,
        status=match_status,
        data_source=data_source,
    )
    session.add(match_record)
    try:
        session.commit()
        session.refresh(match_record)
    except IntegrityError:
        session.rollback()
        raise
    return match_record


def find_match_by_id(
    session: Session,
    match_id: int,
    data_source: str | None = "demo",
) -> Match | None:
    """Find a match, optionally limited to one data source."""
    if data_source is not None:
        _check_data_source(data_source)

    query = (
        session.query(Match)
        .options(
            joinedload(Match.home_team),
            joinedload(Match.away_team),
            joinedload(Match.statistics),
        )
        .filter(Match.id == match_id)
    )
    if data_source is not None:
        query = query.filter(Match.data_source == data_source)
    return query.first()


def list_matches(
    session: Session,
    data_source: str | None = "demo",
    season: str | None = None,
    team: str | None = None,
) -> list[Match]:
    """List matches with optional source, season, and team filters."""
    if data_source is not None:
        _check_data_source(data_source)

    query = (
        session.query(Match)
        .options(
            joinedload(Match.home_team),
            joinedload(Match.away_team),
            joinedload(Match.statistics),
        )
    )
    if data_source is not None:
        query = query.filter(Match.data_source == data_source)
    if season is not None:
        query = query.filter(Match.season == season)
    if team is not None:
        team_name = team.strip().lower()
        query = query.filter(
            or_(
                Match.home_team.has(func.lower(Team.name) == team_name),
                Match.away_team.has(func.lower(Team.name) == team_name),
            )
        )
    return query.order_by(Match.match_date.desc()).all()


def save_or_update_match_statistics(
    session: Session,
    match_id: int,
    home_possession: float | None = None,
    away_possession: float | None = None,
    home_shots: int | None = None,
    away_shots: int | None = None,
    home_shots_on_target: int | None = None,
    away_shots_on_target: int | None = None,
    source: str = "unknown",
    provider_match_id: str | None = None,
) -> MatchStatistics:
    """Save new statistics or replace the values for an existing match."""
    match_record = session.get(Match, match_id)
    if match_record is None:
        raise ValueError("The match was not found.")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("source must be non-empty text.")
    if provider_match_id is not None and (
        not isinstance(provider_match_id, str) or not provider_match_id.strip()
    ):
        raise ValueError("provider_match_id must be non-empty text or missing.")

    _check_possession(home_possession, "home_possession")
    _check_possession(away_possession, "away_possession")
    _check_non_negative_integer(home_shots, "home_shots")
    _check_non_negative_integer(away_shots, "away_shots")
    _check_non_negative_integer(home_shots_on_target, "home_shots_on_target")
    _check_non_negative_integer(away_shots_on_target, "away_shots_on_target")

    statistics = match_record.statistics
    if statistics is None:
        statistics = MatchStatistics(match_id=match_id)
        session.add(statistics)

    statistics.home_possession = home_possession
    statistics.away_possession = away_possession
    statistics.home_shots = home_shots
    statistics.away_shots = away_shots
    statistics.home_shots_on_target = home_shots_on_target
    statistics.away_shots_on_target = away_shots_on_target
    statistics.source = source.strip()
    statistics.provider_match_id = (
        provider_match_id.strip() if provider_match_id is not None else None
    )

    try:
        session.commit()
        session.refresh(statistics)
    except IntegrityError:
        session.rollback()
        raise
    return statistics
