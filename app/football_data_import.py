"""Convert football-data.org fixtures and standings into the local schema."""

from datetime import datetime, timezone
import re
import unicodedata
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.models import LeagueStanding, Match, Team
from app.team_names import same_team


def _date(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def _name(value: str) -> str:
    plain = unicodedata.normalize("NFKD", value)
    return re.sub(r"[^a-z0-9]", "", plain.encode("ascii", "ignore").decode().casefold())


def _same_team(left: str, right: str) -> bool:
    return same_team(left, right)


def _team(session: Session, value: dict[str, Any]) -> Team:
    provider_id = str(value["id"])
    team = (
        session.query(Team)
        .filter(Team.data_source == "live", Team.football_data_team_id == provider_id)
        .one_or_none()
    )
    name = str(value["name"]).strip()
    if team is not None and not _same_team(team.name, name):
        raise ValueError("A football-data.org team ID conflicts with its saved name.")
    if team is None:
        team = (
            next(
                (
                    saved
                    for saved in session.query(Team).filter(
                        Team.data_source == "live"
                    ).all()
                    if _same_team(saved.name, name)
                ),
                None,
            )
        )
    if team is None:
        team = Team(name=name, data_source="live")
        session.add(team)
        session.flush()
    team.football_data_team_id = provider_id
    if value.get("crest"):
        team.logo_url = value["crest"]
    return team


def save_football_data_matches(
    session: Session, body: dict[str, Any], season_start_year: int
) -> dict[str, int]:
    matches = body.get("matches")
    if not isinstance(matches, list):
        raise ValueError("football-data.org did not return a matches list.")
    counts = {"created": 0, "updated": 0}
    for item in matches:
        if not isinstance(item, dict):
            raise ValueError("football-data.org returned an invalid match.")
        home = _team(session, item["homeTeam"])
        away = _team(session, item["awayTeam"])
        match = (
            session.query(Match)
            .options(joinedload(Match.home_team), joinedload(Match.away_team))
            .filter(
                Match.data_source == "live",
                Match.football_data_match_id == str(item["id"]),
            )
            .one_or_none()
        )
        kickoff = _date(item["utcDate"])
        if match is not None and (match.season != str(season_start_year)
                or not _same_team(match.home_team.name, home.name)
                or not _same_team(match.away_team.name, away.name)):
            raise ValueError("A football-data.org match ID conflicts with its saved fixture identity.")
        if match is None:
            candidates = (
                session.query(Match)
                .options(joinedload(Match.home_team), joinedload(Match.away_team))
                .filter(
                    Match.data_source == "live",
                    Match.season == str(season_start_year),
                )
                .all()
            )
            matching = [
                saved
                for saved in candidates
                if saved.match_date.date() == kickoff.date()
                and _same_team(saved.home_team.name, home.name)
                and _same_team(saved.away_team.name, away.name)
            ]
            if len(matching) > 1:
                raise ValueError("More than one saved match matches the provider fixture.")
            match = matching[0] if matching else None
        score = item.get("score", {}).get("fullTime", {})
        status = str(item.get("status", "SCHEDULED")).casefold()
        status = {
            "finished": "finished",
            "in_play": "live",
            "paused": "live",
            "timed": "scheduled",
            "scheduled": "scheduled",
        }.get(status, status)
        if match is None:
            match = Match(
                season=str(season_start_year),
                match_date=kickoff,
                home_team=home,
                away_team=away,
                data_source="live",
            )
            session.add(match)
            counts["created"] += 1
        else:
            counts["updated"] += 1
        match.football_data_match_id = str(item["id"])
        match.match_date = kickoff
        match.fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)
        match.round_name = (
            f"Matchday {item['matchday']}" if item.get("matchday") else match.round_name
        )
        match.home_score = score.get("home")
        match.away_score = score.get("away")
        match.status = status
        match.kickoff_time_available = True
    return counts


def save_football_data_standings(
    session: Session, body: dict[str, Any], season_start_year: int
) -> int:
    tables = body.get("standings")
    if not isinstance(tables, list) or not tables:
        raise ValueError("football-data.org returned no standings table.")
    total = next((table for table in tables if table.get("type") == "TOTAL"), tables[0])
    rows = total.get("table")
    if not isinstance(rows, list):
        raise ValueError("football-data.org standings table is malformed.")
    session.query(LeagueStanding).filter(
        LeagueStanding.source == "football-data.org",
        LeagueStanding.season == str(season_start_year),
    ).delete(synchronize_session=False)
    for row in rows:
        team = _team(session, row["team"])
        session.add(LeagueStanding(
            season=str(season_start_year),
            source="football-data.org",
            position=row["position"],
            team_id=team.id,
            played=row["playedGames"],
            wins=row["won"],
            draws=row["draw"],
            losses=row["lost"],
            goals_for=row["goalsFor"],
            goals_against=row["goalsAgainst"],
            goal_difference=row["goalDifference"],
            points=row["points"],
        ))
    return len(rows)
