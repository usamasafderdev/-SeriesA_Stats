from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
import os
from typing import Literal

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

# Importing the models registers their tables with SQLAlchemy.
from app import models
from app.bbs_match_import import save_bbs_matches
from app.football_data_api import (
    FootballDataClient,
    FootballDataError,
    MissingFootballDataTokenError,
)
from app.football_data_import import (
    save_football_data_matches,
    save_football_data_standings,
)
from app.data_converter import convert_match
from app.database import get_database_session, initialize_database
from app.football_api import (
    FootballAPI,
    FootballAPIError,
    FootballAPITimeoutError,
    InsufficientCreditsError,
    InvalidAPIKeyError,
    MalformedFootballAPIResponseError,
    MissingAPIKeyError,
    RateLimitError,
)
from app.lineup_import import convert_and_save_api_lineups
from app.highlightly_api import (
    HIGHLIGHTLY_SERIE_A_LEAGUE_ID,
    HighlightlyClient,
    HighlightlyError,
    MissingHighlightlyKeyError,
    local_quota,
)
from app.highlightly_import import (
    _same_team_name,
    convert_highlightly_lineups,
    has_player_performance,
    merge_highlightly_box_score,
    save_highlightly_lineups,
)
from app.striker_match_matching import find_matching_striker_game
from app.match_import import save_api_matches
from app.match_service import (
    find_match_by_id,
    list_matches,
    save_or_update_match_statistics,
)
from app.statistics_api import (
    MalformedStatisticsAPIResponseError,
    MissingStatisticsAPIKeyError,
    StatisticsAPI,
    StatisticsAPIError,
    StatisticsAPINetworkError,
    StatisticsAPIPlanError,
    StatisticsAPIRateLimitError,
    StatisticsAPITimeoutError,
)
from app.statistics_converter import (
    convert_match_statistics,
    find_matching_provider_fixture,
    season_start_year,
)


PROJECT_FOLDER = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Create the local database tables before serving requests."""
    initialize_database()
    yield


app = FastAPI(title="Serie A Tracker", lifespan=lifespan)


class LineupImportRequest(BaseModel):
    confirmed: bool = Field(
        default=False,
        description="Confirm the estimated 5-credit get_lineups request.",
    )


class HighlightlyDetailsImportRequest(BaseModel):
    confirmed: bool = Field(
        default=False,
        description="Confirm one box-score and one events request.",
    )


class MatchListImportRequest(BaseModel):
    season: str = Field(min_length=1, max_length=20)
    limit: int = Field(default=3, ge=1, le=3)
    refresh: bool = Field(
        default=False,
        description="Request a fresh list even when enough records are saved.",
    )
    confirmed: bool = Field(
        default=False,
        description="Confirm after checking the provider's current list_games cost.",
    )


class StatisticsImportRequest(BaseModel):
    confirmed: bool = Field(
        default=False,
        description=(
            "Confirm up to two BigBallsData requests, which count against the "
            "plan quota rather than per-call credits."
        ),
    )
    refresh: bool = Field(
        default=False,
        description="Fetch provider statistics even when they are already saved.",
    )


class BBSMatchListImportRequest(BaseModel):
    season: int = Field(ge=2000, le=2100)
    limit: int = Field(default=200, ge=1, le=200)
    max_pages: int = Field(default=5, ge=1, le=5)
    refresh: bool = Field(
        default=False,
        description="Request a fresh list even when enough records are saved.",
    )
    confirmed: bool = Field(
        default=False,
        description="Confirm bounded authenticated BBS season synchronization.",
    )


class SavedMatchRequest(BaseModel):
    match_id: int = Field(gt=0)


class FootballDataSyncRequest(BaseModel):
    season: int = Field(ge=2000, le=2100)
    confirmed: bool = False


class HighlightlySyncRequest(BaseModel):
    season: int = Field(ge=2000, le=2100)
    match_id: int | None = Field(default=None, gt=0)
    match_ids: list[int] | None = Field(default=None, max_length=10)
    allow_fixture_lookup: bool = True
    categories: list[Literal["statistics", "lineups", "box-score", "events"]] = Field(
        default_factory=lambda: ["statistics", "lineups", "box-score"], min_length=1, max_length=4)
    retry_failed: bool = False
    max_matches: int = Field(default=1, ge=1, le=10)
    max_requests: int = Field(default=4, ge=0, le=40)
    confirmed: bool = False


@app.get("/api/health")
def health_check():
    """Return a simple message that confirms the server is running."""
    return {
        "status": "ok",
        "application": "Serie A Tracker",
    }


@app.get("/api/data-coverage")
def data_coverage(session: Session = Depends(get_database_session)) -> dict:
    """Return cached completion coverage without contacting any provider."""
    completed = session.query(models.Match).filter(
        models.Match.data_source == "live",
        models.Match.football_data_match_id.is_not(None),
        models.Match.status.ilike("finished"),
    ).all()
    from app.highlightly_sync import lineups_complete, statistics_present
    detailed = sum(statistics_present(match) for match in completed)
    lineups = sum(
        lineups_complete(match)
        for match in completed
    )
    player_performance = sum(
        has_player_performance(match)
        for match in completed
    )
    events = sum(bool(match.events) for match in completed)
    remaining_matchdays = sorted({
        match.round_name for match in completed
        if match.round_name and (not statistics_present(match) or not lineups_complete(match)
            or not has_player_performance(match) or not match.events)
    }, key=lambda name: int(name.split()[-1]) if name.split()[-1].isdigit() else 0)
    return {
        "completed_fixtures": len(completed),
        "detailed_statistics": detailed,
        "lineups": lineups,
        "player_performance": player_performance,
        "events": events,
        "remaining_details": max(0, len(completed) - detailed),
        "requests_used": sum(row.attempts for row in session.query(models.HighlightlyRequest)),
        "request_count_note": "Recorded attempts since request-ledger installation; earlier usage is unknown.",
        "quota": local_quota(),
        "remaining_matchdays": remaining_matchdays,
    }


def _provider_team_name(value: object) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or value.get("teamName") or "")
    return str(value or "")


def _provider_score(value: object, side: str) -> int | None:
    if not isinstance(value, dict):
        return None
    score = value.get(f"{side}Score")
    if score is None:
        team = value.get(f"{side}Team")
        score = team.get("score") if isinstance(team, dict) else None
    if score is None:
        state = value.get("state")
        current = state.get("score", {}).get("current") if isinstance(state, dict) and isinstance(state.get("score"), dict) else None
        if isinstance(current, str):
            import re
            parts = re.fullmatch(r"\s*(\d+)\s*[-:]\s*(\d+)\s*", current)
            if parts:
                score = parts[1 if side == "home" else 2]
    try:
        return int(score) if score is not None else None
    except (TypeError, ValueError):
        return None


def _normal_name(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _same_provider_team(left: str, right: str) -> bool:
    return _same_team_name(left, right)


def _find_highlightly_fixture(
    body: object,
    match_record: models.Match,
) -> str | None:
    candidates = body.get("data", []) if isinstance(body, dict) else body
    if not isinstance(candidates, list):
        return None
    matches = [
        item for item in candidates
        if isinstance(item, dict)
        and _highlightly_fixture_metadata_matches(item, match_record)
        and _same_provider_team(
            _provider_team_name(item.get("homeTeam") or item.get("homeTeamName")),
            match_record.home_team.name,
        )
        and _same_provider_team(
            _provider_team_name(item.get("awayTeam") or item.get("awayTeamName")),
            match_record.away_team.name,
        )
        and (
            _provider_score(item, "home") is None
            or _provider_score(item, "home") == match_record.home_score
        )
        and (
            _provider_score(item, "away") is None
            or _provider_score(item, "away") == match_record.away_score
        )
    ]
    if len(matches) != 1:
        return None
    provider_id = matches[0].get("id", matches[0].get("matchId"))
    if provider_id is None or isinstance(provider_id, bool) or not str(provider_id).isdigit() or int(provider_id) <= 0:
        return None
    return str(provider_id)


def _highlightly_fixture_metadata_matches(
    item: dict,
    match_record: models.Match,
) -> bool:
    league = item.get("league")
    if isinstance(league, dict):
        if league.get("id") is not None:
            try:
                if int(league["id"]) != HIGHLIGHTLY_SERIE_A_LEAGUE_ID:
                    return False
            except (TypeError, ValueError):
                return False
        if league.get("season") is not None and str(league["season"]) != str(match_record.season):
            return False
    country = item.get("country")
    if isinstance(country, dict) and country.get("code") is not None:
        if str(country["code"]).upper() != "IT":
            return False
    raw_date = item.get("date")
    if raw_date:
        try:
            provider_date = datetime.fromisoformat(str(raw_date).replace("Z", "+00:00"))
        except ValueError:
            return False
        if provider_date.date() != match_record.match_date.date():
            return False
    return True


def _numeric(value: object) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip().replace("%", "")
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def _highlightly_statistics(body: object) -> dict[str, float | int | None]:
    result = {
        "home_possession": None, "away_possession": None,
        "home_shots": None, "away_shots": None,
        "home_shots_on_target": None, "away_shots_on_target": None,
    }
    if not isinstance(body, list):
        body = body.get("statistics", body.get("data", [])) if isinstance(body, dict) else []
    teams = body if isinstance(body, list) else []
    for index, team in enumerate(teams[:2]):
        if not isinstance(team, dict):
            continue
        stats = team.get("statistics", team)
        if isinstance(stats, list):
            entries = {
                "".join(character for character in str(item.get("displayName", "")).casefold() if character.isalnum()): item.get("value")
                for item in stats
                if isinstance(item, dict) and item.get("displayName") is not None
            }
        elif isinstance(stats, dict):
            entries = {
                "".join(character for character in str(name).casefold() if character.isalnum()): value
                for name, value in stats.items()
            }
        else:
            continue
        prefix = "home_" if index == 0 else "away_"
        def first(*names: str) -> object:
            return next(
                (entries[name] for name in names if entries.get(name) is not None),
                None,
            )
        possession = _numeric(
            first("ballpossession", "possession", "possessionpercentage")
        )
        if isinstance(possession, (int, float)) and 0 <= possession <= 1:
            possession *= 100
        result[prefix + "possession"] = possession
        result[prefix + "shots"] = _numeric(
            first("totalshots", "shots", "shotstotal")
        )
        result[prefix + "shots_on_target"] = _numeric(
            first("shotsontarget", "shotsongoal", "shotsontargettotal")
        )
    return result


def _match_date_value(match_record: models.Match) -> str:
    """Return date-only text when the provider did not supply kickoff time."""
    if not match_record.kickoff_time_available:
        return match_record.match_date.date().isoformat()
    return match_record.match_date.isoformat()


def _team_assists(match_record: models.Match, team_id: int) -> int | None:
    """Return a team's assist total only when its saved player values are complete."""
    lineup = next(
        (item for item in match_record.lineups if item.team_id == team_id),
        None,
    )
    if lineup is None:
        return None
    starters = [player for player in lineup.players if player.player_role == "starter"]
    if len(starters) < 11:
        return None
    total_assists = 0
    for player in lineup.players:
        if player.assists is None:
            return None
        total_assists += player.assists
    return total_assists


def match_summary(match_record: models.Match) -> dict:
    """Convert a match database record into a simple JSON-ready dictionary."""
    return {
        "id": match_record.id,
        "season": match_record.season,
        "round": match_record.round_name,
        "match_date": _match_date_value(match_record),
        "home_team_name": match_record.home_team.name,
        "away_team_name": match_record.away_team.name,
        "home_score": match_record.home_score,
        "away_score": match_record.away_score,
        "home_assists": _team_assists(match_record, match_record.home_team_id),
        "away_assists": _team_assists(match_record, match_record.away_team_id),
        "status": match_record.status,
        "data_source": match_record.data_source,
        "statistics_source": (
            match_record.statistics.source if match_record.statistics else None
        ),
        "statistics_fetched_at": (
            match_record.statistics.fetched_at.isoformat()
            if match_record.statistics is not None
            and match_record.statistics.fetched_at is not None
            else None
        ),
        "statistics": {
            "home_possession": (
                match_record.statistics.home_possession
                if match_record.statistics
                else None
            ),
            "away_possession": (
                match_record.statistics.away_possession
                if match_record.statistics
                else None
            ),
            "home_shots": (
                match_record.statistics.home_shots if match_record.statistics else None
            ),
            "away_shots": (
                match_record.statistics.away_shots if match_record.statistics else None
            ),
            "home_shots_on_target": (
                match_record.statistics.home_shots_on_target
                if match_record.statistics
                else None
            ),
            "away_shots_on_target": (
                match_record.statistics.away_shots_on_target
                if match_record.statistics
                else None
            ),
        },
        "fetched_at": (
            match_record.fetched_at.isoformat()
            if match_record.fetched_at is not None
            else None
        ),
    }


@app.get("/api/matches")
def get_matches(
    season: str | None = Query(default=None, min_length=1),
    source: str | None = Query(default=None, pattern="^(demo|live)$"),
    team: str | None = Query(default=None, min_length=1),
    round_name: str | None = Query(default=None, alias="round", min_length=1),
    status: str | None = Query(default=None, pattern="^(finished|live|scheduled|all)$"),
    session: Session = Depends(get_database_session),
) -> list[dict]:
    """Return stored matches, optionally filtered by season, source, or team."""
    if season is not None and not season.strip():
        raise HTTPException(status_code=422, detail="Season cannot be blank.")
    if team is not None and not team.strip():
        raise HTTPException(status_code=422, detail="Team cannot be blank.")
    if round_name is not None and not round_name.strip():
        raise HTTPException(status_code=422, detail="Round cannot be blank.")

    matches = list_matches(
        session,
        data_source=source,
        season=season.strip() if season is not None else None,
        team=team,
        round_name=round_name.strip() if round_name is not None else None,
        status=None if status in (None, "all") else status,
    )
    if source == "live":
        official_query = session.query(models.Match.id).filter(
            models.Match.data_source == "live", models.Match.football_data_match_id.is_not(None))
        if season is not None:
            official_query = official_query.filter(models.Match.season == season)
        if official_query.first() is not None:
            matches = [
                match_record
                for match_record in matches
                if match_record.football_data_match_id is not None
            ]
    return [match_summary(match_record) for match_record in matches]


@app.get("/api/standings")
def get_standings(
    season: str | None = Query(default=None, min_length=1),
    session: Session = Depends(get_database_session),
) -> list[dict]:
    query = session.query(models.LeagueStanding).join(models.Team)
    if season:
        query = query.filter(models.LeagueStanding.season == season)
    return [
        {
            "season": row.season,
            "position": row.position,
            "team_name": row.team.name,
            "played": row.played,
            "wins": row.wins,
            "draws": row.draws,
            "losses": row.losses,
            "goals_for": row.goals_for,
            "goals_against": row.goals_against,
            "goal_difference": row.goal_difference,
            "points": row.points,
            "source": row.source,
        }
        for row in query.order_by(models.LeagueStanding.position).all()
    ]


@app.post("/api/football-data/sync")
def sync_football_data(
    request: FootballDataSyncRequest,
    session: Session = Depends(get_database_session),
) -> dict:
    if not request.confirmed:
        raise HTTPException(
            status_code=400,
            detail="Set confirmed=true to authorize exactly two football-data.org requests.",
        )
    try:
        client = FootballDataClient()
        matches_body = client.get_matches(request.season)
        standings_body = client.get_standings(request.season)
        fixture_summary = save_football_data_matches(
            session, matches_body, request.season
        )
        standing_count = save_football_data_standings(
            session, standings_body, request.season
        )
        session.commit()
    except MissingFootballDataTokenError as error:
        session.rollback()
        raise HTTPException(status_code=503, detail=str(error)) from error
    except (FootballDataError, ValueError) as error:
        session.rollback()
        raise HTTPException(status_code=502, detail=str(error)) from error
    return {
        "source": "football-data.org",
        "season": request.season,
        "requests_used": 2,
        "provider_match_count": matches_body.get("resultSet", {}).get("count"),
        "records_returned": len(matches_body.get("matches", [])),
        "coverage_complete": (
            matches_body.get("resultSet", {}).get("count")
            == len(matches_body.get("matches", []))
        ),
        "imported_records": fixture_summary,
        "standings_rows": standing_count,
    }


@app.get("/api/saved-matches")
def get_saved_matches(
    session: Session = Depends(get_database_session),
) -> list[dict]:
    """Return saved live matches from SQLite."""
    saved_records = (
        session.query(models.SavedMatch)
        .join(models.Match)
        .options(
            joinedload(models.SavedMatch.match).joinedload(models.Match.home_team),
            joinedload(models.SavedMatch.match).joinedload(models.Match.away_team),
            joinedload(models.SavedMatch.match).joinedload(models.Match.statistics),
            joinedload(models.SavedMatch.match)
            .joinedload(models.Match.lineups)
            .joinedload(models.MatchLineup.players),
        )
        .filter(models.Match.data_source == "live")
        .order_by(models.SavedMatch.saved_at.desc())
        .all()
    )
    return [
        {**match_summary(record.match), "saved_at": record.saved_at.isoformat()}
        for record in saved_records
    ]


@app.post("/api/saved-matches")
def save_match(
    request: SavedMatchRequest,
    session: Session = Depends(get_database_session),
) -> dict:
    """Save a locally stored live match to the user's SQLite collection."""
    match_record = find_match_by_id(
        session, request.match_id, data_source="live"
    )
    if match_record is None:
        raise HTTPException(
            status_code=404,
            detail="Only a stored live match can be saved.",
        )
    saved_record = (
        session.query(models.SavedMatch)
        .filter(models.SavedMatch.match_id == match_record.id)
        .one_or_none()
    )
    if saved_record is None:
        saved_record = models.SavedMatch(
            match_id=match_record.id,
            saved_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(saved_record)
        try:
            session.commit()
        except SQLAlchemyError as error:
            session.rollback()
            raise HTTPException(
                status_code=500,
                detail="Saved match could not be stored in SQLite.",
            ) from error
    return {**match_summary(match_record), "saved": True}


@app.delete("/api/saved-matches/{match_id}")
def remove_saved_match(
    match_id: int,
    session: Session = Depends(get_database_session),
) -> dict:
    """Remove a saved-match selection without deleting the match itself."""
    saved_record = (
        session.query(models.SavedMatch)
        .filter(models.SavedMatch.match_id == match_id)
        .one_or_none()
    )
    if saved_record is not None:
        session.delete(saved_record)
        try:
            session.commit()
        except SQLAlchemyError as error:
            session.rollback()
            raise HTTPException(
                status_code=500,
                detail="Saved-match selection could not be removed.",
            ) from error
    return {"match_id": match_id, "saved": False}


@app.get("/api/matches/{match_id}")
def get_match_details(
    match_id: int,
    session: Session = Depends(get_database_session),
) -> dict:
    """Return a stored match and its statistics, if they are available."""
    match_record = find_match_by_id(session, match_id, data_source=None)
    if match_record is None:
        raise HTTPException(status_code=404, detail="Match not found.")

    return _match_details(match_record)


def _match_details(match_record: models.Match) -> dict:
    """Convert a match, its saved statistics, and lineup contributions to JSON."""
    statistics = match_record.statistics
    players = [
        (lineup.team.name, player)
        for lineup in match_record.lineups
        for player in lineup.players
    ]
    goal_scorers = [
        {
            "player_name": player.player_name,
            "team_name": team_name,
            "goals": player.goals,
        }
        for team_name, player in players
        if player.goals is not None and player.goals > 0
    ]
    goal_assists = [
        {
            "player_name": player.player_name,
            "team_name": team_name,
            "assists": player.assists,
        }
        for team_name, player in players
        if player.assists is not None and player.assists > 0
    ]
    events = [
        {
            "id": event.id,
            "minute": event.minute,
            "added_minute": event.added_minute,
            "source": event.source,
            "type": event.event_type,
            "team_name": event.team_name,
            "player_name": event.player_name,
            "assist_name": event.assist_name,
            "detail": event.detail,
        }
        for event in sorted(match_record.events, key=lambda row: (row.minute is None, row.minute or 0, row.added_minute or 0, row.id))
    ]
    statistics_values = (
        (
            statistics.home_possession,
            statistics.away_possession,
            statistics.home_shots,
            statistics.away_shots,
            statistics.home_shots_on_target,
            statistics.away_shots_on_target,
        )
        if statistics is not None
        else ()
    )
    return {
        "id": match_record.id,
        "season": match_record.season,
        "round": match_record.round_name,
        "match_date": _match_date_value(match_record),
        "home_team": {
            "id": match_record.home_team.id,
            "name": match_record.home_team.name,
            "logo_url": match_record.home_team.logo_url,
        },
        "away_team": {
            "id": match_record.away_team.id,
            "name": match_record.away_team.name,
            "logo_url": match_record.away_team.logo_url,
        },
        "home_score": match_record.home_score,
        "away_score": match_record.away_score,
        "status": match_record.status,
        "api_match_id": match_record.api_match_id,
        "data_source": match_record.data_source,
        "bbs_match_id": match_record.bbs_match_id,
        "fetched_at": (
            match_record.fetched_at.isoformat()
            if match_record.fetched_at is not None
            else None
        ),
        "statistics_source": (
            statistics.source
            if statistics is not None and statistics.source != "unknown"
            else None
        ),
        "statistics_provider_match_id": (
            statistics.provider_match_id if statistics is not None else None
        ),
        "statistics_fetched_at": (
            statistics.fetched_at.isoformat()
            if statistics is not None and statistics.fetched_at is not None
            else None
        ),
        "statistics_available": any(
            value is not None for value in statistics_values
        ),
        "statistics": {
            "home_possession": statistics.home_possession if statistics else None,
            "away_possession": statistics.away_possession if statistics else None,
            "home_shots": statistics.home_shots if statistics else None,
            "away_shots": statistics.away_shots if statistics else None,
            "home_shots_on_target": (
                statistics.home_shots_on_target if statistics else None
            ),
            "away_shots_on_target": (
                statistics.away_shots_on_target if statistics else None
            ),
        },
        "goal_scorers": goal_scorers,
        "goal_assists": goal_assists,
        "goal_scorers_available": any(
            player.goals is not None for _team_name, player in players
        ),
        "goal_scorers_complete": bool(players) and all(
            player.goals is not None for _team_name, player in players
        ),
        "goal_assists_available": any(
            player.assists is not None for _team_name, player in players
        ),
        "goal_assists_complete": bool(players) and all(
            player.assists is not None for _team_name, player in players
        ),
        "contributions_source": next((lineup.source for lineup in match_record.lineups if lineup.source), "saved_lineups") if players else None,
        "events": events,
        "events_available": bool(events),
    }


def _save_highlightly_events(
    session: Session,
    match_record: models.Match,
    body: object,
) -> int:
    if isinstance(body, dict):
        body = body.get("events", body.get("data"))
    if not isinstance(body, list):
        raise ValueError("Highlightly returned malformed event data.")
    parsed = []
    def name(value):
        if isinstance(value, dict):
            value = value.get("name")
        return str(value) if value is not None else None
    for item in body:
        if not isinstance(item, dict) or not item.get("type"):
            raise ValueError("Highlightly returned an invalid event.")
        team_name = name(item.get("team"))
        if team_name:
            matched = [team.name for team in (match_record.home_team, match_record.away_team)
                       if _same_provider_team(team_name, team.name)]
            if len(matched) != 1:
                raise ValueError("An event team does not match the stored fixture.")
            team_name = matched[0]
        clock = item.get("time", item.get("minute"))
        minute, added = None, None
        if clock is not None:
            raw = str(clock).strip().removesuffix("'")
            parts = raw.split("+", 1)
            if any(not part.strip().isdigit() for part in parts):
                raise ValueError("An event minute could not be parsed safely.")
            minute = int(parts[0])
            added = int(parts[1]) if len(parts) == 2 else None
        identity = item.get("id", item.get("eventId"))
        parsed.append(models.MatchEvent(
            provider_event_id=str(identity) if identity is not None else None,
            minute=minute, added_minute=added, source="highlightly",
            event_type=str(item["type"]), team_name=team_name,
            player_name=name(item.get("player")), assist_name=name(item.get("assist")),
            detail=name(item.get("substituted")),
        ))
    # Validate the entire payload before replacing this provider's event records.
    if parsed:
        for event in list(match_record.events):
            if event.source == "highlightly":
                match_record.events.remove(event)
        match_record.events.extend(parsed)
    session.flush()
    return len(parsed)



def _statistics_api_http_error(error: StatisticsAPIError) -> None:
    """Map provider errors to safe messages without exposing the API key."""
    if isinstance(error, MissingStatisticsAPIKeyError):
        raise HTTPException(
            status_code=503,
            detail=(
                "BigBallsData is not configured or rejected its key. "
                "Set BBS_API_KEY locally."
            ),
        ) from error
    if isinstance(error, StatisticsAPIPlanError):
        raise HTTPException(status_code=403, detail=str(error)) from error
    if isinstance(error, StatisticsAPIRateLimitError):
        raise HTTPException(
            status_code=429,
            detail="BigBallsData rate limit reached. No retry was attempted.",
        ) from error
    if isinstance(error, StatisticsAPITimeoutError):
        raise HTTPException(
            status_code=504,
            detail="BigBallsData request timed out. No retry was attempted.",
        ) from error
    if isinstance(error, MalformedStatisticsAPIResponseError):
        raise HTTPException(status_code=502, detail=str(error)) from error
    if isinstance(error, StatisticsAPINetworkError):
        raise HTTPException(status_code=502, detail=str(error)) from error
    raise HTTPException(
        status_code=502,
        detail="BigBallsData request failed. No retry was attempted.",
    ) from error


@app.post("/api/bbs/matches/import")
def import_bbs_match_list(
    request: BBSMatchListImportRequest,
    session: Session = Depends(get_database_session),
) -> dict:
    """Synchronize a bounded number of BBS season pages into SQLite."""
    existing_matches = (
        session.query(models.Match)
        .filter(
            models.Match.data_source == "live",
            models.Match.bbs_match_id.is_not(None),
            or_(
                models.Match.season == str(request.season),
                models.Match.season.like(f"{request.season}/%"),
                models.Match.season.like(f"{request.season}-%"),
            ),
        )
        .order_by(models.Match.match_date.desc())
        .all()
    )
    if len(existing_matches) >= request.limit and not request.refresh:
        return {
            "season": request.season,
            "requested_limit": request.limit,
            "imported_records": {"created": 0, "updated": 0, "skipped": request.limit},
            "source": "database",
            "requests_used": 0,
            "matches": [
                match_summary(match_record)
                for match_record in existing_matches[: request.limit]
            ],
        }
    if not request.confirmed:
        raise HTTPException(
            status_code=400,
            detail=(
                "This action makes up to five authenticated BigBallsData page "
                "requests. Confirm before continuing."
            ),
        )

    try:
        api = StatisticsAPI()
        provider_matches = []
        seen_ids = set()
        for page in range(1, request.max_pages + 1):
            page_matches = api.list_season_matches(
            request.season, page, request.limit
            )
            new_matches = [
                match for match in page_matches
                if isinstance(match, dict)
                and match.get("id") not in seen_ids
            ]
            if not new_matches:
                break
            provider_matches.extend(new_matches)
            seen_ids.update(
                match.get("id") for match in new_matches
                if isinstance(match, dict)
            )
            if len(page_matches) < request.limit:
                break
        summary = save_bbs_matches(
            session,
            provider_matches,
            request.season,
        )
        session.commit()
    except StatisticsAPIError as error:
        session.rollback()
        _statistics_api_http_error(error)
    except ValueError as error:
        session.rollback()
        raise HTTPException(
            status_code=502,
            detail=f"Provider match data could not be safely imported: {error}",
        ) from error
    except SQLAlchemyError as error:
        session.rollback()
        raise HTTPException(
            status_code=500,
            detail="Live match records could not be saved to SQLite.",
        ) from error

    saved_matches = (
        session.query(models.Match)
        .options(
            joinedload(models.Match.home_team),
            joinedload(models.Match.away_team),
            joinedload(models.Match.statistics),
        )
        .filter(
            models.Match.data_source == "live",
            models.Match.bbs_match_id.is_not(None),
            or_(
                models.Match.season == str(request.season),
                models.Match.season.like(f"{request.season}/%"),
                models.Match.season.like(f"{request.season}-%"),
            ),
        )
        .order_by(models.Match.match_date.desc())
        .limit(request.limit)
        .all()
    )
    return {
        "season": request.season,
        "requested_limit": request.limit,
        "imported_records": summary,
        "source": "bigballsdata",
        "requests_used": page,
        "matches": [match_summary(match_record) for match_record in saved_matches],
    }


@app.post("/api/matches/{match_id}/statistics/import")
def import_match_statistics(
    match_id: int,
    request: StatisticsImportRequest,
    session: Session = Depends(get_database_session),
) -> dict:
    """Import one live match's stats after explicit confirmation."""
    match_record = find_match_by_id(session, match_id, data_source="live")
    if match_record is None:
        raise HTTPException(
            status_code=404,
            detail="Statistics can only be imported for a stored live match.",
        )
    if match_record.status.casefold() not in {"final", "finished", "completed"}:
        raise HTTPException(
            status_code=409,
            detail="Match statistics can only be imported for a completed match.",
        )

    saved_statistics = match_record.statistics
    if (
        saved_statistics is not None
        and saved_statistics.source == "bigballsdata"
        and saved_statistics.provider_match_id
        and not request.refresh
    ):
        response = _match_details(match_record)
        response["statistics_import"] = {
            "source": "database",
            "cached": True,
            "provider_match_id": saved_statistics.provider_match_id,
            "requests_used": 0,
        }
        return response

    if not request.confirmed:
        request_estimate = (
            1
            if match_record.bbs_match_id
            or (
                saved_statistics is not None
                and saved_statistics.source == "bigballsdata"
                and saved_statistics.provider_match_id
            )
            else 2
        )
        request_word = "one" if request_estimate == 1 else "two"
        raise HTTPException(
            status_code=400,
            detail=(
                f"This import uses {request_word} ({request_estimate}) "
                "BigBallsData request(s). "
                "Set confirmed=true only after approving the request."
            ),
        )

    try:
        api = StatisticsAPI()
        known_provider_match_id = match_record.bbs_match_id
        if (
            known_provider_match_id is None
            and saved_statistics is not None
            and saved_statistics.source == "bigballsdata"
        ):
            known_provider_match_id = saved_statistics.provider_match_id
        if known_provider_match_id:
            provider_match = {
                "provider_match_id": known_provider_match_id,
                "sport": "football",
                "league": "Serie A",
                "match_date": match_record.match_date,
                "status": match_record.status,
                "home_team_id": match_record.home_team.bbs_team_id,
                "home_team_name": match_record.home_team.name,
                "away_team_id": match_record.away_team.bbs_team_id,
                "away_team_name": match_record.away_team.name,
                "home_score": match_record.home_score,
                "away_score": match_record.away_score,
            }
            requests_used = 1
        else:
            season = season_start_year(match_record.season)
            match_date = match_record.match_date.date().isoformat()
            provider_matches = api.find_matches(match_date, season)
            provider_match = find_matching_provider_fixture(
                provider_matches,
                match_record.season,
                match_record.match_date,
                match_record.home_team.name,
                match_record.away_team.name,
                match_record.home_score,
                match_record.away_score,
            )
            requests_used = 2
        api_response = api.get_match_statistics(
            provider_match["provider_match_id"]
        )
        normalized_statistics = convert_match_statistics(
            api_response,
            provider_match,
        )
        match_record.bbs_match_id = provider_match["provider_match_id"]
        saved_statistics = save_or_update_match_statistics(
            session,
            match_record.id,
            home_possession=normalized_statistics["home_possession"],
            away_possession=normalized_statistics["away_possession"],
            home_shots=normalized_statistics["home_shots"],
            away_shots=normalized_statistics["away_shots"],
            home_shots_on_target=normalized_statistics[
                "home_shots_on_target"
            ],
            away_shots_on_target=normalized_statistics[
                "away_shots_on_target"
            ],
            source="bigballsdata",
            provider_match_id=provider_match["provider_match_id"],
        )
    except StatisticsAPIError as error:
        session.rollback()
        _statistics_api_http_error(error)
    except ValueError as error:
        session.rollback()
        raise HTTPException(
            status_code=502,
            detail=f"Provider match data could not be matched or converted: {error}",
        ) from error
    except SQLAlchemyError as error:
        session.rollback()
        raise HTTPException(
            status_code=500,
            detail="Match statistics could not be saved to the local database.",
        ) from error

    saved_match = find_match_by_id(session, match_id, data_source="live")
    response = _match_details(saved_match)
    response["statistics_import"] = {
        "source": "bigballsdata",
        "cached": False,
        "provider_match_id": saved_statistics.provider_match_id,
        "requests_used": requests_used,
        "available": normalized_statistics["available"],
    }
    return response


def _lineup_details(match_record: models.Match) -> dict:
    """Return saved lineup and player records without hiding missing values."""
    lineup_records = []
    for lineup in sorted(match_record.lineups, key=lambda row: row.team_id):
        players_by_role = {
            "starting_players": [],
            "substitutes_used": [],
            "unused_substitutes": [],
        }
        role_names = {
            "starter": "starting_players",
            "used_substitute": "substitutes_used",
            "unused_substitute": "unused_substitutes",
        }
        for player in sorted(lineup.players, key=lambda row: row.id):
            players_by_role[role_names[player.player_role]].append(
                {
                    "id": player.id,
                    "player_id": player.api_player_id,
                    "name": player.player_name,
                    "shirt_number": player.shirt_number,
                    "position": player.position,
                    "formation_slot": player.formation_slot,
                    "player_role": player.player_role,
                    "minute_on": player.minute_on,
                    "minute_off": player.minute_off,
                    "goals": player.goals,
                    "assists": player.assists,
                    "yellow_cards": player.yellow_cards,
                    "red_cards": player.red_cards,
                    "rating": player.rating,
                    "minutes_played": player.minutes_played,
                    "shots_total": player.shots_total,
                    "shots_on_target": player.shots_on_target,
                    "shots_off_target": player.shots_off_target,
                    "passes_total": player.passes_total,
                    "passes_successful": player.passes_successful,
                    "passes_accuracy": player.passes_accuracy,
                    "passes_key": player.passes_key,
                    "tackles_total": player.tackles_total,
                    "interceptions_total": player.interceptions_total,
                    "dribbles_total": player.dribbles_total,
                    "dribbles_successful": player.dribbles_successful,
                    "duels_total": player.duels_total,
                    "duels_won": player.duels_won,
                    "fouls_committed": player.fouls_committed,
                    "fouls_drawn": player.fouls_drawn,
                    "goalkeeper_saves": player.goalkeeper_saves,
                }
            )
        lineup_records.append(
            {
                "team_id": lineup.team_id,
                "team_name": lineup.team.name,
                "formation": lineup.formation,
                "source": lineup.source,
                "provider_match_id": lineup.provider_match_id,
                "available": True,
                **players_by_role,
            }
        )

    if lineup_records:
        lineups_by_team = {
            lineup_record["team_id"]: lineup_record
            for lineup_record in lineup_records
        }
        lineup_records = []
        for team in (match_record.home_team, match_record.away_team):
            lineup_records.append(
                lineups_by_team.get(
                    team.id,
                    {
                        "team_id": team.id,
                        "team_name": team.name,
                        "formation": None,
                        "available": False,
                        "starting_players": [],
                        "substitutes_used": [],
                        "unused_substitutes": [],
                    },
                )
            )
    complete = bool(lineup_records) and all(
        lineup.get("available") is True
        and len(lineup["starting_players"]) == 11
        for lineup in lineup_records
    )
    return {
        "match_id": match_record.id,
        "data_source": match_record.data_source,
        "available": bool(lineup_records),
        "complete": complete,
        "message": (
            "Stored lineups are available for both teams."
            if complete
            else "Stored lineup data is incomplete for this match."
            if lineup_records
            else "No lineup data is stored for this match yet."
        ),
        "lineups": lineup_records,
    }


def _raise_api_http_error(error: FootballAPIError) -> None:
    """Turn known provider errors into useful responses without exposing secrets."""
    if isinstance(error, MissingAPIKeyError):
        raise HTTPException(
            status_code=503,
            detail="StrikerAPI is not configured. Set STRIKER_API_KEY locally.",
        ) from error
    if isinstance(error, InvalidAPIKeyError):
        raise HTTPException(
            status_code=502,
            detail="StrikerAPI rejected the configured credentials.",
        ) from error
    if isinstance(error, InsufficientCreditsError):
        raise HTTPException(
            status_code=402,
            detail="StrikerAPI reports that the account has insufficient credits.",
        ) from error
    if isinstance(error, RateLimitError):
        raise HTTPException(
            status_code=429,
            detail="StrikerAPI rate limit reached. No retry was attempted.",
        ) from error
    if isinstance(error, FootballAPITimeoutError):
        raise HTTPException(
            status_code=504,
            detail="StrikerAPI request timed out. No retry was attempted.",
        ) from error
    if isinstance(error, MalformedFootballAPIResponseError):
        raise HTTPException(
            status_code=502,
            detail="StrikerAPI returned missing or malformed lineup data.",
        ) from error
    raise HTTPException(
        status_code=502,
        detail="StrikerAPI request failed. Check the provider status and logs.",
    ) from error


@app.get("/api/matches/{match_id}/lineups")
def get_match_lineups(
    match_id: int,
    session: Session = Depends(get_database_session),
) -> dict:
    """Return locally stored lineups; this endpoint never calls StrikerAPI."""
    match_record = find_match_by_id(session, match_id, data_source=None)
    if match_record is None:
        raise HTTPException(status_code=404, detail="Match not found.")
    return _lineup_details(match_record)


@app.post("/api/matches/{match_id}/highlightly-details/import")
def import_highlightly_details(
    match_id: int,
    request: HighlightlyDetailsImportRequest,
    session: Session = Depends(get_database_session),
) -> dict:
    """Fetch and cache Highlightly player metrics and events on demand."""
    match_record = find_match_by_id(session, match_id, data_source="live")
    if match_record is None or match_record.highlightly_match_id is None:
        raise HTTPException(status_code=404, detail="Highlightly match identity is unavailable.")
    if not request.confirmed:
        raise HTTPException(
            status_code=400,
            detail="Set confirmed=true to authorize one box-score and one events request.",
        )
    result = sync_highlightly_details(HighlightlySyncRequest(
        season=int(match_record.season), match_id=match_id, max_requests=2,
        categories=["box-score", "events"], allow_fixture_lookup=False,
        confirmed=True), session)
    session.refresh(match_record)
    return {"match_id": match_id, "player_records_updated": sum(
        player.rating is not None or player.minutes_played is not None
        for lineup in match_record.lineups for player in lineup.players),
        "events_imported": len(match_record.events), "details": _match_details(match_record),
        "requests_used": result["requests_used"], "stopped_reason": result["stopped_reason"]}



@app.post("/api/highlightly/sync")
def sync_highlightly_details(
    request: HighlightlySyncRequest,
    session: Session = Depends(get_database_session),
) -> dict:
    """Run only the explicitly approved categories under a bounded budget."""
    from app.highlightly_sync import SYNC_LOCK, run_sync
    if not request.confirmed:
        raise HTTPException(status_code=400, detail="Set confirmed=true to authorize this bounded sync batch.")
    if not SYNC_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="A synchronization batch is already running.")
    try:
        result = run_sync(session, request, HighlightlyClient(), _find_highlightly_fixture,
                          _highlightly_statistics, _save_highlightly_events)
        result["coverage"] = data_coverage(session)
        return result
    finally:
        SYNC_LOCK.release()


@app.post("/api/highlightly/plan")
def plan_highlightly_details(request: HighlightlySyncRequest,
                            session: Session = Depends(get_database_session)) -> dict:
    """Inspect cached records and quota metadata; no authenticated requests."""
    from app.highlightly_sync import sync_plan
    return sync_plan(session, request.season, request.categories,
                     request.match_ids if request.match_ids is not None else (
                         [request.match_id] if request.match_id else None),
                     request.max_matches, request.allow_fixture_lookup)



@app.post("/api/matches/{match_id}/lineups/import")
def import_match_lineups(
    match_id: int,
    request: LineupImportRequest,
    session: Session = Depends(get_database_session),
) -> dict:
    """Explicitly request lineups for a stored live match (estimated 5 credits)."""
    match_record = find_match_by_id(session, match_id, data_source="live")
    if match_record is None:
        raise HTTPException(
            status_code=404,
            detail="Lineups can only be imported for a stored live match.",
        )

    saved_data = _lineup_details(match_record)
    if saved_data["complete"]:
        saved_data["source"] = "database"
        saved_data["estimated_credits"] = 0
        return saved_data

    if not request.confirmed:
        raise HTTPException(
            status_code=400,
            detail=(
                "This request may use an estimated 5 API credits. "
                "Set confirmed=true only after approving the request."
            ),
        )

    if match_record.football_data_match_id is not None or match_record.highlightly_match_id is not None:
        result = sync_highlightly_details(HighlightlySyncRequest(
            season=int(match_record.season), match_id=match_id,
            categories=["lineups"], max_requests=2, confirmed=True), session)
        session.refresh(match_record)
        response = _lineup_details(match_record)
        response.update(source="highlightly", requests_used=result["requests_used"],
                        stopped_reason=result["stopped_reason"])
        return response
    try:
        striker_api = FootballAPI()
        used_match_lookup = match_record.api_match_id is None
        if match_record.api_match_id is None:
            games_data = striker_api.get_matches(
                match_record.season,
                limit=200,
                status="final",
            )
            games = games_data.get("games")
            if not isinstance(games, list):
                raise ValueError("StrikerAPI did not return a completed fixture list.")
            game = find_matching_striker_game(match_record, games)
            match_record.api_match_id = int(game["game_id"])
            match_record.home_team.api_team_id = int(game["home"]["team_id"])
            match_record.away_team.api_team_id = int(game["away"]["team_id"])
            session.flush()

        api_data = striker_api.get_lineups(match_record.api_match_id)
        provider_game = api_data.get("game", {})
        if not isinstance(provider_game, dict):
            provider_game = {}
        provider_game_id = provider_game.get("game_id")
        if provider_game_id is not None and str(provider_game_id) != str(
            match_record.api_match_id
        ):
            raise HTTPException(
                status_code=502,
                detail="StrikerAPI returned a lineup for a different match.",
            )
        convert_and_save_api_lineups(
            session,
            match_record.id,
            api_data.get("lineups"),
        )
        session.commit()
    except MissingHighlightlyKeyError as error:
        session.rollback()
        raise HTTPException(status_code=503, detail=str(error)) from error
    except HighlightlyError as error:
        session.rollback()
        raise HTTPException(status_code=502, detail=str(error)) from error
    except FootballAPIError as error:
        _raise_api_http_error(error)
    except ValueError as error:
        session.rollback()
        raise HTTPException(
            status_code=502,
            detail=f"StrikerAPI lineup data could not be saved: {error}",
        ) from error
    except SQLAlchemyError as error:
        session.rollback()
        raise HTTPException(
            status_code=500,
            detail="Lineup data could not be saved to the local database.",
        ) from error

    saved_match = find_match_by_id(session, match_id, data_source="live")
    response = _lineup_details(saved_match)
    response["source"] = "strikerapi"
    response["estimated_credits"] = 7 if used_match_lookup else 5
    return response


@app.post("/api/live-matches/import")
def import_small_live_match_list(
    request: MatchListImportRequest,
    session: Session = Depends(get_database_session),
) -> dict:
    """Explicitly import at most three matches using one list_games request."""
    if not request.season.strip():
        raise HTTPException(status_code=422, detail="Season cannot be blank.")
    saved_matches = list_matches(
        session,
        data_source="live",
        season=request.season.strip(),
    )
    if len(saved_matches) >= request.limit and not request.refresh:
        return {
            "season": request.season.strip(),
            "requested_limit": request.limit,
            "imported_records": {
                "created": 0,
                "updated": 0,
                "skipped": request.limit,
            },
            "source": "database",
            "credit_estimate": "0; existing saved match records were reused.",
        }
    if not request.confirmed:
        raise HTTPException(
            status_code=400,
            detail=(
                "Review StrikerAPI's current list_games cost, then set "
                "confirmed=true to request up to three matches."
            ),
        )
    try:
        api_data = FootballAPI().get_matches(
            request.season.strip(),
            limit=request.limit,
        )
        games = api_data.get("games")
        if not isinstance(games, list):
            raise HTTPException(
                status_code=502,
                detail="StrikerAPI did not return a match list.",
            )
        if len(games) > request.limit:
            raise HTTPException(
                status_code=502,
                detail="StrikerAPI returned more matches than the confirmed limit.",
            )
        normalized_matches = [
            convert_match(game)
            for game in games
            if isinstance(game, dict)
        ]
        if len(normalized_matches) != len(games):
            raise HTTPException(
                status_code=502,
                detail="StrikerAPI returned a match list containing invalid records.",
            )
        summary = save_api_matches(session, normalized_matches)
        session.commit()
    except FootballAPIError as error:
        _raise_api_http_error(error)
    except ValueError as error:
        session.rollback()
        raise HTTPException(
            status_code=502,
            detail=f"StrikerAPI match data could not be saved: {error}",
        ) from error
    except SQLAlchemyError as error:
        session.rollback()
        raise HTTPException(
            status_code=500,
            detail="Live match records could not be saved locally.",
        ) from error

    return {
        "season": request.season,
        "requested_limit": request.limit,
        "imported_records": summary,
        "source": "strikerapi",
        "credit_estimate": (
            "Not independently verified; check StrikerAPI's current list_games "
            "pricing before confirming."
        ),
    }


@app.get("/")
def home_page():
    """Send the existing frontend home page to the browser."""
    return FileResponse(PROJECT_FOLDER / "index.html")


# Serve the folders used by the existing links in index.html and style.css.
app.mount(
    "/assets",
    StaticFiles(directory=PROJECT_FOLDER / "assets"),
    name="assets",
)
app.mount(
    "/css",
    StaticFiles(directory=PROJECT_FOLDER / "css"),
    name="css",
)
app.mount(
    "/js",
    StaticFiles(directory=PROJECT_FOLDER / "js"),
    name="javascript",
)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("SERIE_A_PORT", "8000")))
