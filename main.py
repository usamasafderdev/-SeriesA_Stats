from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

# Importing the models registers their tables with SQLAlchemy.
from app import models
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
        description="Confirm the two BigBallsData GET requests.",
    )
    refresh: bool = Field(
        default=False,
        description="Fetch provider statistics even when they are already saved.",
    )


@app.get("/api/health")
def health_check():
    """Return a simple message that confirms the server is running."""
    return {
        "status": "ok",
        "application": "Serie A Tracker",
    }


def match_summary(match_record: models.Match) -> dict:
    """Convert a match database record into a simple JSON-ready dictionary."""
    return {
        "id": match_record.id,
        "season": match_record.season,
        "match_date": match_record.match_date.isoformat(),
        "home_team_name": match_record.home_team.name,
        "away_team_name": match_record.away_team.name,
        "home_score": match_record.home_score,
        "away_score": match_record.away_score,
        "status": match_record.status,
        "data_source": match_record.data_source,
    }


@app.get("/api/matches")
def get_matches(
    season: str | None = Query(default=None, min_length=1),
    source: str | None = Query(default=None, pattern="^(demo|live)$"),
    team: str | None = Query(default=None, min_length=1),
    session: Session = Depends(get_database_session),
) -> list[dict]:
    """Return stored matches, optionally filtered by season, source, or team."""
    if season is not None and not season.strip():
        raise HTTPException(status_code=422, detail="Season cannot be blank.")
    if team is not None and not team.strip():
        raise HTTPException(status_code=422, detail="Team cannot be blank.")

    matches = list_matches(
        session,
        data_source=source,
        season=season.strip() if season is not None else None,
        team=team,
    )
    return [match_summary(match_record) for match_record in matches]


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
        "match_date": match_record.match_date.isoformat(),
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
        "data_source": match_record.data_source,
        "statistics_source": (
            statistics.source
            if statistics is not None and statistics.source != "unknown"
            else None
        ),
        "statistics_provider_match_id": (
            statistics.provider_match_id if statistics is not None else None
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
        "goal_assists_available": any(
            player.assists is not None for _team_name, player in players
        ),
        "contributions_source": "strikerapi_lineups" if players else None,
    }


def _statistics_api_http_error(error: StatisticsAPIError) -> None:
    """Map provider errors to safe messages without exposing the API key."""
    if isinstance(error, MissingStatisticsAPIKeyError):
        raise HTTPException(
            status_code=503,
            detail=(
                "BigBallsData is not configured or rejected its key. "
                "Set BIGBALLSDATA_API_KEY locally."
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
        raise HTTPException(status_code=504, detail=str(error)) from error
    if isinstance(error, MalformedStatisticsAPIResponseError):
        raise HTTPException(status_code=502, detail=str(error)) from error
    if isinstance(error, StatisticsAPINetworkError):
        raise HTTPException(status_code=502, detail=str(error)) from error
    raise HTTPException(
        status_code=502,
        detail="BigBallsData request failed. No retry was attempted.",
    ) from error


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
        raise HTTPException(
            status_code=400,
            detail=(
                "This import uses up to two BigBallsData requests. "
                "Set confirmed=true only after approving the request."
            ),
        )

    try:
        season = season_start_year(match_record.season)
        match_date = match_record.match_date.date().isoformat()
        api = StatisticsAPI()
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
        api_response = api.get_match_statistics(
            provider_match["provider_match_id"]
        )
        normalized_statistics = convert_match_statistics(
            api_response,
            provider_match,
        )
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
        "requests_used": 2,
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
                }
            )
        lineup_records.append(
            {
                "team_id": lineup.team_id,
                "team_name": lineup.team.name,
                "formation": lineup.formation,
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
    if match_record.api_match_id is None:
        raise HTTPException(
            status_code=422,
            detail="The stored live match has no external API match ID.",
        )

    try:
        api_data = FootballAPI().get_lineups(match_record.api_match_id)
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
    response["estimated_credits"] = 5
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
    uvicorn.run(app, host="127.0.0.1", port=8000)
