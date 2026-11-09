"""Convert and safely save BigBallsData Serie A fixtures."""

import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.models import Match, Team
from app.statistics_converter import convert_provider_match, season_start_year


def _normalized_name(name: str) -> str:
    plain_text = unicodedata.normalize("NFKD", name)
    without_accents = plain_text.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", without_accents.casefold())


def _provider_id(value: Any, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise ValueError(f"{label} must be text or missing.")
    result = str(value).strip()
    if not result:
        raise ValueError(f"{label} must not be blank.")
    return result


def _team_for_provider(
    session: Session,
    name: str,
    provider_id: str | None,
) -> Team:
    if provider_id is not None:
        team = (
            session.query(Team)
            .filter(
                Team.data_source == "live",
                Team.bbs_team_id == provider_id,
            )
            .one_or_none()
        )
        if team is not None:
            if _normalized_name(team.name) != _normalized_name(name):
                raise ValueError("A provider team ID conflicts with its saved name.")
            return team

    named_teams = [
        team
        for team in session.query(Team).filter(Team.data_source == "live").all()
        if _normalized_name(team.name) == _normalized_name(name)
    ]
    if len(named_teams) > 1:
        raise ValueError("More than one saved team matches this provider team.")
    if named_teams:
        team = named_teams[0]
        if (
            provider_id is not None
            and team.bbs_team_id is not None
            and team.bbs_team_id != provider_id
        ):
            raise ValueError("The saved team has a different BBS team ID.")
        if provider_id is not None:
            team.bbs_team_id = provider_id
        return team

    team = Team(
        name=name,
        bbs_team_id=provider_id,
        data_source="live",
    )
    session.add(team)
    session.flush()
    return team


def _same_fixture(match: Match, converted: dict[str, Any]) -> bool:
    match_date = match.match_date
    if match_date.tzinfo is None:
        match_date = match_date.replace(tzinfo=timezone.utc)
    else:
        match_date = match_date.astimezone(timezone.utc)
    return (
        match_date.date() == converted["match_date"].date()
        and _normalized_name(match.home_team.name)
        == _normalized_name(converted["home_team_name"])
        and _normalized_name(match.away_team.name)
        == _normalized_name(converted["away_team_name"])
    )


def _find_existing_match(
    session: Session,
    season: str,
    converted: dict[str, Any],
) -> Match | None:
    existing = (
        session.query(Match)
        .options(joinedload(Match.home_team), joinedload(Match.away_team))
        .filter(
            Match.data_source == "live",
            Match.bbs_match_id == converted["provider_match_id"],
        )
        .one_or_none()
    )
    if existing is not None:
        if (
            season_start_year(existing.season) != int(season)
            or not _same_fixture(existing, converted)
        ):
            raise ValueError("The BBS match ID conflicts with the saved fixture.")
        return existing

    possible_matches = (
        session.query(Match)
        .options(joinedload(Match.home_team), joinedload(Match.away_team))
        .filter(
            Match.data_source == "live",
        )
        .all()
    )
    matches = [
        match
        for match in possible_matches
        if season_start_year(match.season) == int(season)
        and _same_fixture(match, converted)
    ]
    if len(matches) > 1:
        raise ValueError(
            "More than one saved match could match this BBS fixture; import stopped."
        )
    if matches and matches[0].bbs_match_id is not None:
        raise ValueError("A different BBS match ID is already linked to this fixture.")
    return matches[0] if matches else None


def save_bbs_matches(
    session: Session,
    provider_matches: list[dict[str, Any]],
    season_start_year: int,
) -> dict[str, int]:
    """Save verified BBS matches without conflating provider IDs."""
    if not isinstance(provider_matches, list) or len(provider_matches) > 1000:
        raise ValueError("At most 1000 provider matches may be saved at once.")
    if (
        isinstance(season_start_year, bool)
        or not isinstance(season_start_year, int)
        or season_start_year < 2000
    ):
        raise ValueError("season_start_year must be a four-digit year.")

    counts = {"created": 0, "updated": 0, "skipped": 0}
    season = str(season_start_year)
    for raw_match in provider_matches:
        converted = convert_provider_match(raw_match)
        if (
            converted["sport"].casefold() != "football"
            or _normalized_name(converted["league"]) != "seriea"
        ):
            raise ValueError("Only BigBallsData Serie A football matches can be saved.")
        if converted["status"].casefold() not in {
            "scheduled", "live", "in_progress", "finished", "completed",
        }:
            raise ValueError("Provider fixture has an unsupported status.")
        home_id = _provider_id(
            converted["home_team_id"], "BigBallsData home team ID"
        )
        away_id = _provider_id(
            converted["away_team_id"], "BigBallsData away team ID"
        )
        home_team = _team_for_provider(
            session, converted["home_team_name"], home_id
        )
        away_team = _team_for_provider(
            session, converted["away_team_name"], away_id
        )
        if home_team.id == away_team.id:
            raise ValueError("A match cannot have the same home and away team.")

        match = _find_existing_match(session, season, converted)
        if match is None:
            match = Match(
                bbs_match_id=converted["provider_match_id"],
                season=season,
                round_name=converted["round_name"],
                match_date=converted["match_date"].replace(tzinfo=None),
                kickoff_time_available=converted["kickoff_time_available"],
                home_team=home_team,
                away_team=away_team,
                home_score=converted["home_score"],
                away_score=converted["away_score"],
                status=converted["status"],
                data_source="live",
            )
            session.add(match)
            counts["created"] += 1
        else:
            same_provider_match = (
                match.bbs_match_id == converted["provider_match_id"]
            )
            if not same_provider_match and ((
                match.home_score is not None
                and converted["home_score"] is not None
                and match.home_score != converted["home_score"]
            ) or (
                match.away_score is not None
                and converted["away_score"] is not None
                and match.away_score != converted["away_score"]
            )):
                raise ValueError(
                    "Provider and saved scores disagree; fixture was not updated."
                )
            match.bbs_match_id = converted["provider_match_id"]
            if converted["round_name"] is not None:
                match.round_name = converted["round_name"]
            match.kickoff_time_available = converted["kickoff_time_available"]
            if converted["home_score"] is not None:
                match.home_score = converted["home_score"]
            if converted["away_score"] is not None:
                match.away_score = converted["away_score"]
            match.status = converted["status"]
            counts["updated"] += 1

        match.fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)

    session.flush()
    return counts
