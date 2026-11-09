"""Convert provider match details into the application's common data shape.

The converter does not make network requests or save records. Provider adapters
can use it before handing data to the existing match and lineup services.
"""

import re
import unicodedata
from datetime import datetime, timezone
from typing import Any


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _whole_number(value: Any) -> int | None:
    if isinstance(value, str) and re.fullmatch(r"\d+", value.strip()):
        return int(value.strip())
    number = _number(value)
    if number is None or int(number) != number or number < 0:
        return None
    return int(number)


def _stat_value(stats: Any, name: str) -> int | float | None:
    if not isinstance(stats, list):
        return None
    for stat in stats:
        if isinstance(stat, dict) and stat.get("name") == name:
            return _number(stat.get("value"))
    return None


def _clock_minute(value: Any) -> int | None:
    if not isinstance(value, dict):
        return None
    clock = value.get("clock")
    if not isinstance(clock, dict):
        return None
    display_value = clock.get("displayValue")
    if not isinstance(display_value, str):
        return None
    match = re.search(r"\d{1,3}", display_value)
    return int(match.group()) if match else None


def _team_name(team: Any) -> str | None:
    if not isinstance(team, dict):
        return None
    return _text(team.get("displayName") or team.get("name"))


def _normalized_name(value: str) -> str:
    plain_text = unicodedata.normalize("NFKD", value)
    without_accents = plain_text.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", without_accents.casefold())


def _espn_date(header: dict[str, Any]) -> str | None:
    competitions = header.get("competitions")
    if not isinstance(competitions, list) or not competitions:
        return None
    value = competitions[0].get("date")
    return _text(value)


def _espn_fixture(summary: dict[str, Any], provider_match_id: str) -> dict[str, Any]:
    header = summary.get("header")
    if not isinstance(header, dict):
        raise ValueError("Provider summary must include a header object.")
    competitions = header.get("competitions")
    if not isinstance(competitions, list) or len(competitions) != 1:
        raise ValueError("Provider summary must include one competition.")
    competition = competitions[0]
    competitors = competition.get("competitors")
    if not isinstance(competitors, list) or len(competitors) != 2:
        raise ValueError("Provider summary must include two competitors.")

    sides: dict[str, dict[str, Any]] = {}
    for competitor in competitors:
        if not isinstance(competitor, dict):
            raise ValueError("Provider competitor must be an object.")
        side = competitor.get("homeAway")
        team = competitor.get("team")
        if side not in {"home", "away"} or not isinstance(team, dict):
            raise ValueError("Provider competitors must identify home and away teams.")
        if side in sides:
            raise ValueError("Provider summary contains duplicate fixture sides.")
        sides[side] = {
            "provider_team_id": _text(team.get("id")),
            "team_name": _team_name(team),
            "score": _whole_number(competitor.get("score")),
        }

    status = competition.get("status")
    status_type = status.get("type") if isinstance(status, dict) else {}
    return {
        "provider": "espn",
        "provider_match_id": str(provider_match_id),
        "home_team_id": sides["home"]["provider_team_id"],
        "home_team_name": sides["home"]["team_name"],
        "away_team_id": sides["away"]["provider_team_id"],
        "away_team_name": sides["away"]["team_name"],
        "match_date": _espn_date(header),
        "season": _text(
            header.get("season", {}).get("displayName")
            if isinstance(header.get("season"), dict)
            else None
        ),
        "status": _text(status_type.get("description")) if isinstance(status_type, dict) else None,
        "home_score": sides["home"]["score"],
        "away_score": sides["away"]["score"],
        "round_name": None,
    }


def _espn_statistics(summary: dict[str, Any]) -> dict[str, int | float | None]:
    teams = summary.get("boxscore", {}).get("teams", [])
    result: dict[str, int | float | None] = {}
    for team in teams if isinstance(teams, list) else []:
        if not isinstance(team, dict):
            continue
        side = team.get("homeAway")
        if side not in {"home", "away"}:
            continue
        stats = team.get("statistics")
        prefix = f"{side}_"
        result[prefix + "possession"] = _number(_stat_value(stats, "possessionPct"))
        result[prefix + "shots"] = _whole_number(_stat_value(stats, "totalShots"))
        result[prefix + "shots_on_target"] = _whole_number(
            _stat_value(stats, "shotsOnTarget")
        )
    for side in ("home", "away"):
        for field in ("possession", "shots", "shots_on_target"):
            result.setdefault(f"{side}_{field}", None)
    return result


def _espn_player(player: dict[str, Any]) -> dict[str, Any]:
    athlete = player.get("athlete") if isinstance(player.get("athlete"), dict) else {}
    subbed_in = player.get("subbedIn")
    subbed_out = player.get("subbedOut")
    is_subbed_in = bool(subbed_in) if isinstance(subbed_in, bool) else bool(subbed_in)
    is_subbed_out = bool(subbed_out) if isinstance(subbed_out, bool) else bool(subbed_out)
    starter = player.get("starter") is True
    role = "starter" if starter else (
        "used_substitute" if is_subbed_in else "unused_substitute"
    )
    plays = player.get("plays")
    player_plays = plays if isinstance(plays, list) else []
    event_flags = {
        "goals": any(
            isinstance(play, dict)
            and (play.get("didScore") is True or play.get("scoringPlay") is True)
            for play in player_plays
        ),
        "assists": any(
            isinstance(play, dict) and play.get("didAssist") is True
            for play in player_plays
        ),
        "yellow_cards": any(
            isinstance(play, dict) and play.get("yellowCard") is True
            for play in player_plays
        ),
        "red_cards": any(
            isinstance(play, dict) and play.get("redCard") is True
            for play in player_plays
        ),
    }

    def statistic_or_event(stat_name: str, event_name: str) -> int | None:
        statistic = _whole_number(_stat_value(player.get("stats"), stat_name))
        if statistic is not None:
            return statistic
        return 1 if event_flags[event_name] else None

    return {
        "player_id": _text(athlete.get("id")),
        "name": _text(athlete.get("displayName") or athlete.get("fullName")),
        "shirt_number": _whole_number(player.get("jersey")),
        "position": _text(
            player.get("position", {}).get("name")
            if isinstance(player.get("position"), dict)
            else None
        ),
        "formation_slot": _whole_number(player.get("formationPlace")),
        "player_role": role,
        "minute_on": 0 if starter else _clock_minute(subbed_in),
        "minute_off": _clock_minute(subbed_out) if is_subbed_out else None,
        "goals": statistic_or_event("totalGoals", "goals"),
        "assists": statistic_or_event("goalAssists", "assists"),
        "yellow_cards": statistic_or_event("yellowCards", "yellow_cards"),
        "red_cards": statistic_or_event("redCards", "red_cards"),
    }


def _espn_lineups(summary: dict[str, Any]) -> list[dict[str, Any]]:
    rosters = summary.get("rosters")
    if not isinstance(rosters, list):
        return []
    lineups = []
    for roster in rosters:
        if not isinstance(roster, dict):
            continue
        team = roster.get("team") if isinstance(roster.get("team"), dict) else {}
        players = roster.get("roster")
        if not isinstance(players, list):
            continue
        converted = [_espn_player(player) for player in players if isinstance(player, dict)]
        lineups.append(
            {
                "provider_team_id": _text(team.get("id")),
                "team_name": _team_name(team),
                "home_away": roster.get("homeAway"),
                "formation": _text(roster.get("formation")),
                "starting_players": [
                    player for player in converted if player["player_role"] == "starter"
                ],
                "substitutes_used": [
                    player
                    for player in converted
                    if player["player_role"] == "used_substitute"
                ],
                "unused_substitutes": [
                    player
                    for player in converted
                    if player["player_role"] == "unused_substitute"
                ],
            }
        )
    return lineups


def convert_match_detail(
    summary: dict[str, Any],
    provider: str,
    provider_match_id: str,
) -> dict[str, Any]:
    """Return provider-neutral fixture, statistics, and lineup data.

    Currently the saved ESPN schema is supported. Adding another provider
    should produce the same output shape without sharing provider IDs.
    """
    if not isinstance(summary, dict):
        raise ValueError("Provider summary must be an object.")
    if not isinstance(provider, str) or provider.casefold() != "espn":
        raise ValueError("No converter is registered for this provider.")
    if not isinstance(provider_match_id, str) or not provider_match_id.strip():
        raise ValueError("provider_match_id must be non-empty text.")
    fixture = _espn_fixture(summary, provider_match_id.strip())
    return {
        "fixture": fixture,
        "statistics": _espn_statistics(summary),
        "lineups": _espn_lineups(summary),
        "provider_ids_are_separate": True,
    }


def find_unambiguous_fixture(
    candidates: list[dict[str, Any]],
    home_team_name: str,
    away_team_name: str,
    match_date: str,
) -> dict[str, Any]:
    """Match one provider fixture without mixing IDs from another provider."""
    matches = [
        candidate
        for candidate in candidates
        if _normalized_name(str(candidate.get("home_team_name", "")))
        == _normalized_name(home_team_name)
        and _normalized_name(str(candidate.get("away_team_name", "")))
        == _normalized_name(away_team_name)
        and candidate.get("match_date") == match_date
    ]
    if len(matches) != 1:
        raise ValueError("Fixture identity was missing or ambiguous.")
    return matches[0]
