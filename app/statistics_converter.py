"""Validate and match BigBallsData Serie A records before saving statistics."""

import re
import unicodedata
from datetime import datetime, timezone
from typing import Any
from uuid import UUID


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text.")
    return value.strip()


def _normalized_team_name(value: str) -> str:
    plain_text = unicodedata.normalize("NFKD", value)
    without_accents = plain_text.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", without_accents.casefold())


def season_start_year(season: str) -> int:
    """Return the starting year used by the provider's season filter."""
    if not isinstance(season, str):
        raise ValueError("The saved season must start with a four-digit year.")
    season_match = re.match(r"\s*(\d{4})", season)
    if season_match is None:
        raise ValueError("The saved season must start with a four-digit year.")
    return int(season_match.group(1))


def _utc_datetime(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be an ISO datetime.")
    try:
        result = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"{field_name} must be an ISO datetime.") from None
    if result.tzinfo is None:
        return result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def convert_provider_match(match: dict[str, Any]) -> dict[str, Any]:
    """Convert one BigBallsData fixture into consistent identity fields."""
    if not isinstance(match, dict):
        raise ValueError("Each provider match must be an object.")

    match_id = _required_text(match.get("id"), "provider match ID")
    try:
        UUID(match_id)
    except ValueError:
        raise ValueError("Provider match ID must be a canonical UUID.") from None
    sport = _required_text(match.get("sport"), "provider sport")
    league = _required_text(match.get("league"), "provider league")
    home = match.get("home")
    away = match.get("away")
    if not isinstance(home, dict) or not isinstance(away, dict):
        raise ValueError("Provider match must include home and away teams.")

    home_name = _required_text(home.get("name"), "home team name")
    away_name = _required_text(away.get("name"), "away team name")
    if _normalized_team_name(home_name) == _normalized_team_name(away_name):
        raise ValueError("Provider match cannot have the same home and away team.")

    score = match.get("score")
    if score is not None and not isinstance(score, dict):
        raise ValueError("Provider score must be an object or missing.")
    home_score = score.get("home") if score else None
    away_score = score.get("away") if score else None
    return {
        "provider_match_id": match_id,
        "sport": sport,
        "league": league,
        "match_date": _utc_datetime(
            match.get("kickoff_utc"),
            "kickoff_utc",
        ),
        "status": _required_text(match.get("status"), "provider match status"),
        "home_team_id": home.get("id"),
        "home_team_name": home_name,
        "away_team_id": away.get("id"),
        "away_team_name": away_name,
        "home_score": _non_negative_integer(home_score, "home score"),
        "away_score": _non_negative_integer(away_score, "away score"),
    }


def _non_negative_integer(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative whole number.")
    return value


def find_matching_provider_fixture(
    provider_matches: list[dict[str, Any]],
    season: str,
    match_date: datetime,
    home_team_name: str,
    away_team_name: str,
    home_score: int | None,
    away_score: int | None,
) -> dict[str, Any]:
    """Require one exact date, season-query, and home/away team match."""
    season_start_year(season)
    expected_date = match_date
    if expected_date.tzinfo is None:
        expected_date = expected_date.replace(tzinfo=timezone.utc)
    else:
        expected_date = expected_date.astimezone(timezone.utc)
    local_home = _normalized_team_name(home_team_name)
    local_away = _normalized_team_name(away_team_name)

    matches = [
        convert_provider_match(provider_match)
        for provider_match in provider_matches
    ]
    matches = [
        provider_match
        for provider_match in matches
        if provider_match["sport"].casefold() == "football"
        and _normalized_team_name(provider_match["league"]) == "seriea"
        and provider_match["match_date"].date() == expected_date.date()
        and _normalized_team_name(provider_match["home_team_name"]) == local_home
        and _normalized_team_name(provider_match["away_team_name"]) == local_away
    ]
    if not matches:
        raise ValueError(
            "No BigBallsData fixture exactly matched the saved season, UTC date, "
            "and home/away team names."
        )
    if len(matches) != 1:
        raise ValueError(
            "More than one BigBallsData fixture matched; statistics were not attached."
        )

    provider_match = matches[0]
    if provider_match["status"].casefold() != "finished":
        raise ValueError("Statistics can only be imported for a finished match.")
    if (
        home_score is not None
        and provider_match["home_score"] is not None
        and provider_match["home_score"] != home_score
    ) or (
        away_score is not None
        and provider_match["away_score"] is not None
        and provider_match["away_score"] != away_score
    ):
        raise ValueError(
            "Provider and saved scores disagree; verify the fixture before importing."
        )
    return provider_match


STATISTIC_FIELDS = (
    "home_possession",
    "away_possession",
    "home_shots",
    "away_shots",
    "home_shots_on_target",
    "away_shots_on_target",
)


def _team_statistics(
    value: Any,
    side: str,
    expected_team_id: Any,
    expected_team_name: str,
) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"Provider {side} statistics must be an object or null.")

    provider_team_id = value.get("team_id")
    if (
        expected_team_id is not None
        and provider_team_id is not None
        and str(provider_team_id) != str(expected_team_id)
    ):
        raise ValueError(f"Provider {side} statistics use a different team ID.")
    provider_team_name = value.get("team_name")
    if (
        isinstance(provider_team_name, str)
        and provider_team_name.strip()
        and _normalized_team_name(provider_team_name)
        != _normalized_team_name(expected_team_name)
    ):
        raise ValueError(f"Provider {side} statistics use a different team name.")

    possession = value.get("ball_possession")
    if possession is not None and (
        isinstance(possession, bool)
        or not isinstance(possession, (int, float))
        or not 0 <= possession <= 100
    ):
        raise ValueError(f"Provider {side} possession must be between 0 and 100.")
    return {
        f"{side}_possession": possession,
        f"{side}_shots": _non_negative_integer(
            value.get("total_shots"),
            f"{side} total shots",
        ),
        f"{side}_shots_on_target": _non_negative_integer(
            value.get("shots_on_target"),
            f"{side} shots on target",
        ),
    }


def convert_match_statistics(
    response: dict[str, Any],
    provider_match: dict[str, Any],
) -> dict[str, Any]:
    """Convert the documented home/away statistics response, preserving nulls."""
    if not isinstance(response, dict):
        raise ValueError("Provider statistics response must be an object.")
    data = response.get("data")
    if not isinstance(data, dict):
        raise ValueError("Provider statistics response must include a data object.")
    if "home" not in data or "away" not in data:
        raise ValueError(
            "Provider statistics data must include both home and away fields."
        )
    metadata = response.get("meta")
    if metadata is not None and not isinstance(metadata, dict):
        raise ValueError("Provider statistics metadata must be an object.")
    available_flag = metadata.get("available") if metadata else None
    if available_flag is not None and not isinstance(available_flag, bool):
        raise ValueError("Provider statistics availability must be true or false.")

    home = _team_statistics(
        data.get("home"),
        "home",
        provider_match.get("home_team_id"),
        provider_match["home_team_name"],
    )
    away = _team_statistics(
        data.get("away"),
        "away",
        provider_match.get("away_team_id"),
        provider_match["away_team_name"],
    )
    return {
        **(home or {
            "home_possession": None,
            "home_shots": None,
            "home_shots_on_target": None,
        }),
        **(away or {
            "away_possession": None,
            "away_shots": None,
            "away_shots_on_target": None,
        }),
        "available": available_flag is not False
        and any(
            value is not None
            for value in (
                (home or {}).get("home_possession"),
                (home or {}).get("home_shots"),
                (home or {}).get("home_shots_on_target"),
                (away or {}).get("away_possession"),
                (away or {}).get("away_shots"),
                (away or {}).get("away_shots_on_target"),
            )
        ),
    }
