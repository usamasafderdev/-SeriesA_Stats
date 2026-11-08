import argparse
import os
from typing import Any

from app.football_api import (
    FootballAPI,
    FootballAPIError,
)


DEFAULT_SEASON = "2025"
PLACEHOLDER_KEYS = {
    "",
    "your_api_key_here",
    "put_your_key_here",
    "your_key_here",
    "your_api_key",
}
COMPLETED_STATUSES = {"final", "finished", "complete", "completed"}


def _has_value(record: dict[str, Any], field_name: str) -> bool:
    """Check that a response field exists and contains a useful value."""
    return field_name in record and record[field_name] is not None


def _field_status(
    record: dict[str, Any],
    field_name: str,
    path: str,
) -> dict[str, Any]:
    """Describe whether one expected JSON field was returned."""
    if _has_value(record, field_name):
        return {"status": "available", "path": path}
    return {"status": "missing", "path": path}


def _team_field_status(
    records: list[dict[str, Any]],
    field_name: str,
    path: str,
) -> dict[str, Any]:
    """Check whether at least one team statistics row has a value."""
    if any(_has_value(record, field_name) for record in records):
        return {"status": "available", "path": path}
    return {"status": "missing", "path": path}


def _is_completed_match(match: dict[str, Any]) -> bool:
    """Recognize the completed-match statuses used in provider responses."""
    status = match.get("status")
    return isinstance(status, str) and status.lower() in COMPLETED_STATUSES


def _inspect_goals(
    events: list[dict[str, Any]],
    match: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Check whether goal scorers and assists can be read from match events."""
    goals = [
        event
        for event in events
        if isinstance(event, dict)
        and (
            event.get("is_goal") is True
            or str(event.get("type", "")).lower() == "goal"
        )
    ]

    home = match.get("home")
    away = match.get("away")
    home_score = home.get("score") if isinstance(home, dict) else None
    away_score = away.get("score") if isinstance(away, dict) else None
    score_is_zero_zero = home_score == 0 and away_score == 0

    if not goals and score_is_zero_zero:
        not_applicable = {"status": "not applicable", "path": "events[]"}
        return not_applicable, not_applicable.copy()

    scorer_available = any(
        _has_value(event, "player") or _has_value(event, "player_id")
        for event in goals
    )
    assist_available = any(
        _has_value(event, "player2") or _has_value(event, "player2_id")
        for event in goals
    )

    scorer_status = "available" if scorer_available else "missing"
    assist_status = "available" if assist_available else "missing"
    return (
        {"status": scorer_status, "path": "events[].player"},
        {"status": assist_status, "path": "events[].player2"},
    )


def _inspect_card_events(
    events: list[dict[str, Any]],
    players: list[dict[str, Any]],
    card_name: str,
) -> dict[str, Any]:
    """Check player card totals and event names for one card type."""
    player_field = f"{card_name}_cards"
    event_names = {card_name, f"{card_name}-card", f"{card_name}_card"}
    has_player_totals = any(
        _has_value(player, player_field)
        for player in players
        if isinstance(player, dict)
    )
    has_card_event = any(
        isinstance(event, dict)
        and str(event.get("type", "")).lower() in event_names
        for event in events
    )
    status = "available" if has_player_totals or has_card_event else "missing"
    return {
        "status": status,
        "path": f"players[].{player_field} or events[].type",
    }


def _inspect_lineups(lineups_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Check the requested starting lineup and substitute fields."""
    lineups = lineups_data.get("lineups")
    if not isinstance(lineups, list):
        return {
            field_name: {"status": "missing", "path": path}
            for field_name, path in (
                ("Starting XI", "lineups[].starting_xi"),
                ("Player names", "lineups[].starting_xi[].name"),
                ("Positions", "lineups[].starting_xi[].position"),
                ("Formation", "lineups[].formation"),
                ("Substitutes", "lineups[].substitutes_used"),
            )
        }

    starting_players = [
        player
        for lineup in lineups
        if isinstance(lineup, dict)
        and isinstance(lineup.get("starting_xi"), list)
        for player in lineup["starting_xi"]
        if isinstance(player, dict)
    ]

    def has_lineup_field(field_name: str) -> bool:
        return any(
            isinstance(lineup, dict) and _has_value(lineup, field_name)
            for lineup in lineups
        )

    def has_player_field(field_name: str) -> bool:
        return any(_has_value(player, field_name) for player in starting_players)

    return {
        "Starting XI": {
            "status": (
                "available"
                if starting_players
                else "missing"
            ),
            "path": "lineups[].starting_xi",
        },
        "Player names": {
            "status": "available" if has_player_field("name") else "missing",
            "path": "lineups[].starting_xi[].name",
        },
        "Positions": {
            "status": "available" if has_player_field("position") else "missing",
            "path": "lineups[].starting_xi[].position",
        },
        "Formation": {
            "status": "available" if has_lineup_field("formation") else "missing",
            "path": "lineups[].formation",
        },
        "Substitutes": {
            "status": (
                "available"
                if has_lineup_field("substitutes_used")
                or has_lineup_field("unused_substitutes")
                else "missing"
            ),
            "path": (
                "lineups[].substitutes_used, "
                "lineups[].unused_substitutes"
            ),
        },
    }


def run_verification(
    api: FootballAPI,
    season: int | str = DEFAULT_SEASON,
) -> dict[str, Any]:
    """Check up to three games and inspect one completed match."""
    match_data = api.get_matches(season, limit=3)
    matches = match_data.get("games")
    if not isinstance(matches, list):
        raise ValueError("The match response did not contain a games list.")

    completed_match = next(
        (
            match
            for match in matches
            if isinstance(match, dict) and _is_completed_match(match)
        ),
        None,
    )
    if completed_match is None:
        return {
            "season": season,
            "match": None,
            "api_calls": 1,
            "fields": {
                "Match information": {
                    field_name: {"status": "unverified", "path": path}
                    for field_name, path in (
                        ("Match ID", "games[].game_id"),
                        ("Home team", "games[].home.name"),
                        ("Away team", "games[].away.name"),
                        ("Date", "games[].date"),
                        ("Score", "games[].home.score, games[].away.score"),
                        ("Match status", "games[].status"),
                    )
                },
                "Team statistics": {
                    field_name: {"status": "unverified", "path": path}
                    for field_name, path in (
                        ("Possession", "team_stats[].possession_pct"),
                        ("Total shots", "team_stats[].shots"),
                        ("Shots on target", "team_stats[].shots_on_target"),
                    )
                },
                "Player statistics": {
                    field_name: {"status": "unverified", "path": path}
                    for field_name, path in (
                        ("Goalscorers", "events[].player"),
                        ("Assists", "events[].player2"),
                        ("Yellow cards", "players[].yellow_cards"),
                        ("Red cards", "players[].red_cards"),
                    )
                },
                "Lineups": {
                    field_name: {"status": "unverified", "path": path}
                    for field_name, path in (
                        ("Starting XI", "lineups[].starting_xi"),
                        ("Player names", "lineups[].starting_xi[].name"),
                        ("Positions", "lineups[].starting_xi[].position"),
                        ("Formation", "lineups[].formation"),
                        ("Substitutes", "lineups[].substitutes_used"),
                    )
                },
            },
        }

    game_id = completed_match.get("game_id")
    if game_id is None or not str(game_id).strip():
        raise ValueError("The completed match did not contain a game ID.")

    details = api.get_match_details(game_id)
    lineups_data = api.get_lineups(game_id)
    events_data = api.get_events(game_id)

    match_details = details.get("game")
    match_details = match_details if isinstance(match_details, dict) else {}
    team_stats = details.get("team_stats")
    team_stats = team_stats if isinstance(team_stats, list) else []
    players = details.get("players")
    players = players if isinstance(players, list) else []
    events = events_data.get("events")
    events = events if isinstance(events, list) else []
    events_for_players = details.get("key_events")
    events_for_players = (
        events_for_players if isinstance(events_for_players, list) else events
    )

    scorer_status, assist_status = _inspect_goals(events, completed_match)
    fields = {
        "Match information": {
            "Match ID": _field_status(
                completed_match, "game_id", "games[].game_id"
            ),
            "Home team": _field_status(
                completed_match.get("home", {})
                if isinstance(completed_match.get("home"), dict)
                else {},
                "name",
                "games[].home.name",
            ),
            "Away team": _field_status(
                completed_match.get("away", {})
                if isinstance(completed_match.get("away"), dict)
                else {},
                "name",
                "games[].away.name",
            ),
            "Date": _field_status(completed_match, "date", "games[].date"),
            "Score": {
                "status": (
                    "available"
                    if isinstance(completed_match.get("home"), dict)
                    and isinstance(completed_match.get("away"), dict)
                    and _has_value(completed_match["home"], "score")
                    and _has_value(completed_match["away"], "score")
                    else "missing"
                ),
                "path": "games[].home.score, games[].away.score",
            },
            "Match status": _field_status(
                completed_match, "status", "games[].status"
            ),
        },
        "Team statistics": {
            "Possession": _team_field_status(
                team_stats, "possession_pct", "team_stats[].possession_pct"
            ),
            "Total shots": _team_field_status(
                team_stats, "shots", "team_stats[].shots"
            ),
            "Shots on target": _team_field_status(
                team_stats,
                "shots_on_target",
                "team_stats[].shots_on_target",
            ),
        },
        "Player statistics": {
            "Goalscorers": scorer_status,
            "Assists": assist_status,
            "Yellow cards": _inspect_card_events(
                events_for_players, players, "yellow"
            ),
            "Red cards": _inspect_card_events(
                events_for_players, players, "red"
            ),
        },
        "Lineups": _inspect_lineups(lineups_data),
    }

    home = completed_match.get("home")
    away = completed_match.get("away")
    home = home if isinstance(home, dict) else {}
    away = away if isinstance(away, dict) else {}
    return {
        "season": season,
        "match": {
            "id": game_id,
            "home_team": home.get("name"),
            "away_team": away.get("name"),
            "date": completed_match.get("date"),
            "home_score": home.get("score"),
            "away_score": away.get("score"),
            "status": completed_match.get("status"),
        },
        "details_match": match_details,
        "fields": fields,
        "api_calls": 4,
    }


def format_report(report: dict[str, Any]) -> str:
    """Create a short text report without showing credentials or full payloads."""
    lines = [
        "StrikerAPI Serie A data verification",
        f"Season: {report['season']}",
        f"Authenticated responses: {'Yes' if report.get('real_responses') else 'No'}",
        f"API calls: {report['api_calls']}",
    ]
    match = report.get("match")
    if match is None:
        lines.append("Completed match: not found in the returned sample.")
    else:
        lines.extend(
            [
                f"Match ID: {match.get('id', 'missing')}",
                (
                    "Fixture: "
                    f"{match.get('home_team') or 'missing'} vs "
                    f"{match.get('away_team') or 'missing'}"
                ),
                f"Date: {match.get('date') or 'missing'}",
                (
                    "Score: "
                    f"{match.get('home_score', 'missing')} - "
                    f"{match.get('away_score', 'missing')}"
                ),
                f"Status: {match.get('status') or 'missing'}",
            ]
        )

    for section_name, section_fields in report["fields"].items():
        lines.append(f"{section_name}:")
        for field_name, result in section_fields.items():
            lines.append(f"  {field_name}: {result['status']} ({result['path']})")
    return "\n".join(lines)


def _has_configured_key() -> bool:
    """Return whether a non-placeholder key is available without displaying it."""
    key = os.getenv("STRIKER_API_KEY", "").strip()
    return key.lower() not in PLACEHOLDER_KEYS


def main(arguments: list[str] | None = None) -> int:
    """Run the live check only when the user explicitly supplies --live."""
    parser = argparse.ArgumentParser(
        description="Verify a small sample of live Serie A match data."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Allow authenticated requests that may use API credits.",
    )
    parser.add_argument(
        "--season",
        default=DEFAULT_SEASON,
        help="Season start year (2025 means the 2025-26 season).",
    )
    options = parser.parse_args(arguments)

    if not options.live:
        print("No API requests sent. Add --live to explicitly allow verification.")
        return 2
    if not _has_configured_key():
        print("API key configuration pending. No API requests sent.")
        return 2

    print(
        "Estimated cost: up to 20 credits for match, lineup, and event "
        "requests, plus any list_games charge (not verified)."
    )
    confirmation = input(
        "Type VERIFY to allow the match-list, match, lineup, and event requests: "
    )
    if confirmation.strip() != "VERIFY":
        print("Live verification cancelled. No API requests sent.")
        return 2

    try:
        report = run_verification(FootballAPI(), options.season)
    except FootballAPIError as error:
        print(f"Verification failed: {error}")
        return 1
    except ValueError as error:
        print(f"Verification could not read the response: {error}")
        return 1

    report["real_responses"] = True
    print(format_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
