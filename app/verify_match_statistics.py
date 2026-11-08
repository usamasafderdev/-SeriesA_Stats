import argparse
import json
import os
import time
from typing import Any

import httpx

from app.football_api import (
    FootballAPI,
    FootballAPIError,
)


MATCH_ID = "737158"
SEASON = 2025
LEAGUE = "seriea"
MAX_CREDIT_ESTIMATE = 20
READ_TIMEOUT_SECONDS = 30.0
MAX_READ_TIMEOUT_SECONDS = 60.0
ENDPOINT_CREDITS = {
    "game": 5,
    "lineups": 5,
    "events": 10,
    "all": MAX_CREDIT_ESTIMATE,
}
PLACEHOLDER_KEYS = {
    "",
    "your_api_key_here",
    "put_your_key_here",
    "your_key_here",
    "your_api_key",
}


def _has_value(record: dict[str, Any], field: str) -> bool:
    """Treat zero as a present value; only absent or null values are missing."""
    return field in record and record[field] is not None


def _status_for_values(values: list[Any], path: str) -> dict[str, Any]:
    """Summarize whether a value was found without treating zero as missing."""
    if not values:
        return {"status": "missing", "path": path}
    if all(value == 0 for value in values):
        return {"status": "available (zero recorded)", "path": path}
    return {"status": "available", "path": path}


def _team_statistics(
    stats: list[dict[str, Any]],
    home_team_id: Any,
    away_team_id: Any,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Match statistics rows to the home and away teams."""
    by_side: dict[str, dict[str, Any]] = {}
    issues: list[str] = []

    for row in stats:
        side = "home" if row.get("home") is True else "away" if row.get("home") is False else None
        if side is None:
            team_id = str(row.get("team_id"))
            if team_id == str(home_team_id):
                side = "home"
            elif team_id == str(away_team_id):
                side = "away"

        if side is None:
            issues.append("A team-statistics row could not be matched to either team.")
        elif side in by_side:
            issues.append(f"More than one team-statistics row matched the {side} team.")
        else:
            by_side[side] = row

    return by_side, issues


def _field_result(
    record: dict[str, Any] | None,
    field: str,
    path: str,
) -> dict[str, Any]:
    if record is None or not _has_value(record, field):
        return {"status": "missing", "path": path}
    value = record[field]
    return {
        "status": "available (zero recorded)" if value == 0 else "available",
        "value": value,
        "path": path,
    }


def _lineup_report(
    lineups_data: dict[str, Any],
    home_team_id: Any,
    away_team_id: Any,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Summarize each side's lineup and keep players for consistency checks."""
    lineup_rows = lineups_data.get("lineups")
    if not isinstance(lineup_rows, list):
        lineup_rows = []

    report: dict[str, Any] = {}
    all_players: list[dict[str, Any]] = []
    for side, team_id in (("home", home_team_id), ("away", away_team_id)):
        lineup = next(
            (
                row
                for row in lineup_rows
                if isinstance(row, dict)
                and str(row.get("team_id")) == str(team_id)
            ),
            None,
        )
        if lineup is None:
            report[side] = {"status": "missing"}
            continue

        starting_xi = lineup.get("starting_xi")
        starting_xi = starting_xi if isinstance(starting_xi, list) else []
        substitutes = lineup.get("substitutes_used")
        substitutes = substitutes if isinstance(substitutes, list) else []
        unused_substitutes = lineup.get("unused_substitutes")
        unused_substitutes = (
            unused_substitutes if isinstance(unused_substitutes, list) else []
        )
        players = [
            player
            for player in starting_xi + substitutes + unused_substitutes
            if isinstance(player, dict)
        ]
        all_players.extend(players)

        report[side] = {
            "status": "available" if starting_xi else "missing",
            "team_id": lineup.get("team_id"),
            "formation": _field_result(
                lineup,
                "formation",
                "data.lineups[].formation",
            ),
            "starting_xi_count": len(starting_xi),
            "starting_xi": [
                {
                    "name": player.get("name"),
                    "player_id": player.get("player_id"),
                    "position": player.get("position"),
                    "jersey": player.get("jersey"),
                    "formation_place": player.get("formation_place"),
                    "minute_on": player.get("minute_on"),
                    "minute_off": player.get("minute_off"),
                    "goals": player.get("goals"),
                    "assists": player.get("assists"),
                    "yellow_cards": player.get("yellow_cards"),
                    "red_cards": player.get("red_cards"),
                }
                for player in starting_xi
            ],
            "substitutes_used_count": len(substitutes),
            "unused_substitutes_count": len(unused_substitutes),
            "substitutes_used": [
                {
                    "name": player.get("name"),
                    "player_id": player.get("player_id"),
                    "position": player.get("position"),
                    "jersey": player.get("jersey"),
                    "formation_place": player.get("formation_place"),
                    "minute_on": player.get("minute_on"),
                    "minute_off": player.get("minute_off"),
                    "goals": player.get("goals"),
                    "assists": player.get("assists"),
                    "yellow_cards": player.get("yellow_cards"),
                    "red_cards": player.get("red_cards"),
                }
                for player in substitutes
            ],
            "unused_substitutes": [
                {
                    "name": player.get("name"),
                    "player_id": player.get("player_id"),
                    "position": player.get("position"),
                    "jersey": player.get("jersey"),
                    "formation_place": player.get("formation_place"),
                    "minute_on": player.get("minute_on"),
                    "minute_off": player.get("minute_off"),
                    "goals": player.get("goals"),
                    "assists": player.get("assists"),
                    "yellow_cards": player.get("yellow_cards"),
                    "red_cards": player.get("red_cards"),
                }
                for player in unused_substitutes
            ],
            "coordinates_available": any(
                "x" in player or "y" in player for player in players
            ),
        }

    return report, all_players


def _event_summary(
    events: list[dict[str, Any]],
    home_team_id: Any,
    away_team_id: Any,
    expected_home_score: Any,
    expected_away_score: Any,
    players: list[dict[str, Any]],
) -> dict[str, Any]:
    """Check event goals, assists, cards, and consistency against the score."""
    goal_events = [
        event
        for event in events
        if isinstance(event, dict)
        and (
            event.get("is_goal") is True
            or str(event.get("type", "")).lower() == "goal"
        )
        and event.get("shootout") is not True
    ]

    home_goals = sum(
        str(event.get("team_id")) == str(home_team_id) for event in goal_events
    )
    away_goals = sum(
        str(event.get("team_id")) == str(away_team_id) for event in goal_events
    )
    score_is_numeric = (
        isinstance(expected_home_score, int)
        and not isinstance(expected_home_score, bool)
        and isinstance(expected_away_score, int)
        and not isinstance(expected_away_score, bool)
    )
    goals_consistency = "unverified"
    if score_is_numeric:
        goals_consistency = (
            "consistent"
            if (home_goals, away_goals)
            == (expected_home_score, expected_away_score)
            else "inconsistent"
        )

    known_player_ids = {
        str(player["player_id"])
        for player in players
        if player.get("player_id") is not None
    }
    unmapped_events = [
        event
        for event in events
        if isinstance(event, dict)
        and any(
            player_id is not None and str(player_id) not in known_player_ids
            for player_id in (event.get("player_id"), event.get("player2_id"))
        )
        and known_player_ids
    ]
    known_team_ids = {str(home_team_id), str(away_team_id)}
    events_with_unknown_team = [
        event
        for event in events
        if isinstance(event, dict)
        and event.get("team_id") is not None
        and str(event.get("team_id")) not in known_team_ids
    ]

    def card_result(name: str) -> dict[str, Any]:
        field = f"{name}_cards"
        values = [
            player[field]
            for player in players
            if _has_value(player, field)
        ]
        path = f"data.lineups[].starting_xi[].{field}"
        if name == "yellow":
            path = (
                "data.lineups[].starting_xi[].yellow_cards, "
                "data.lineups[].substitutes_used[].yellow_cards"
            )
        if name == "red":
            path = (
                "data.lineups[].starting_xi[].red_cards, "
                "data.lineups[].substitutes_used[].red_cards"
            )
        if not values:
            return {"status": "missing", "path": path}
        if all(value == 0 for value in values):
            return {"status": "available (zero recorded)", "path": path}
        return {"status": "available", "path": path}

    scorers = [
        {
            "name": event.get("player"),
            "player_id": event.get("player_id"),
            "team_id": event.get("team_id"),
        }
        for event in goal_events
    ]
    assists = [
        {
            "name": event.get("player2"),
            "player_id": event.get("player2_id"),
            "team_id": event.get("team_id"),
        }
        for event in goal_events
        if _has_value(event, "player2") or _has_value(event, "player2_id")
    ]

    return {
        "goal_events": goal_events,
        "goalscorers": {
            "status": "available" if goal_events else "missing",
            "path": "data.events[].player, data.events[].player_id",
            "values": scorers,
        },
        "assists": {
            "status": (
                "available"
                if assists
                else "missing (no assist value returned)"
            ),
            "path": "data.events[].player2, data.events[].player2_id",
            "values": assists,
        },
        "yellow_cards": card_result("yellow"),
        "red_cards": card_result("red"),
        "goal_score_consistency": goals_consistency,
        "event_player_ids_unmapped": len(unmapped_events),
        "events_with_unknown_team": len(events_with_unknown_team),
    }


def analyze_match_data(
    details: dict[str, Any],
    lineups_data: dict[str, Any],
    events_data: dict[str, Any],
) -> dict[str, Any]:
    """Inspect returned data, preserving zero values and reporting missing fields."""
    match = details.get("game")
    match = match if isinstance(match, dict) else {}
    home = match.get("home")
    home = home if isinstance(home, dict) else {}
    away = match.get("away")
    away = away if isinstance(away, dict) else {}
    stats = details.get("team_stats")
    stats = stats if isinstance(stats, list) else []
    stat_rows = [row for row in stats if isinstance(row, dict)]
    side_stats, mapping_issues = _team_statistics(
        stat_rows,
        home.get("team_id"),
        away.get("team_id"),
    )

    teams: dict[str, Any] = {}
    for side in ("home", "away"):
        row = side_stats.get(side)
        teams[side] = {
            "team_id": row.get("team_id") if row else None,
            "possession": _field_result(
                row,
                "possession_pct",
                "data.team_stats[team].possession_pct",
            ),
            "shots": _field_result(
                row,
                "shots",
                "data.team_stats[team].shots",
            ),
            "shots_on_target": _field_result(
                row,
                "shots_on_target",
                "data.team_stats[team].shots_on_target",
            ),
        }

    lineup_report, lineup_players = _lineup_report(
        lineups_data,
        home.get("team_id"),
        away.get("team_id"),
    )
    events = events_data.get("events")
    events = events if isinstance(events, list) else []
    event_players = details.get("players")
    event_players = event_players if isinstance(event_players, list) else []
    event_checks = _event_summary(
        [event for event in events if isinstance(event, dict)],
        home.get("team_id"),
        away.get("team_id"),
        home.get("score"),
        away.get("score"),
        lineup_players or [p for p in event_players if isinstance(p, dict)],
    )

    detail_score = (home.get("score"), away.get("score"))
    lineup_game = lineups_data.get("game")
    lineup_game = lineup_game if isinstance(lineup_game, dict) else {}
    list_home = lineup_game.get("home")
    list_home = list_home if isinstance(list_home, dict) else {}
    list_away = lineup_game.get("away")
    list_away = list_away if isinstance(list_away, dict) else {}
    list_score = (list_home.get("score"), list_away.get("score"))

    score_consistency = "unverified"
    if all(isinstance(value, int) and not isinstance(value, bool) for value in detail_score):
        if all(isinstance(value, int) and not isinstance(value, bool) for value in list_score):
            score_consistency = "consistent" if detail_score == list_score else "inconsistent"
        else:
            score_consistency = "available; lineup endpoint did not include both scores"

    return {
        "match": {
            "id": match.get("game_id"),
            "home": home.get("name"),
            "away": away.get("name"),
            "home_score": home.get("score"),
            "away_score": away.get("score"),
            "status": match.get("status"),
        },
        "score_path": "data.game.home.score, data.game.away.score",
        "team_statistics": teams,
        "lineups": lineup_report,
        "player_statistics": {
            "player_goals": _status_for_values(
                [
                    player.get("goals")
                    for player in event_players
                    if isinstance(player, dict) and _has_value(player, "goals")
                ],
                "data.players[].goals; lineup rows may also contain goals",
            ),
            "player_assists": _status_for_values(
                [
                    player.get("assists")
                    for player in event_players
                    if isinstance(player, dict) and _has_value(player, "assists")
                ],
                "data.players[].assists; lineup rows may also contain assists",
            ),
            "yellow_cards": event_checks["yellow_cards"],
            "red_cards": event_checks["red_cards"],
        },
        "events": {
            "goalscorers": event_checks["goalscorers"],
            "assists": event_checks["assists"],
        },
        "consistency": {
            "details_vs_lineup_score": score_consistency,
            "event_goals_vs_final_score": event_checks["goal_score_consistency"],
            "event_player_ids_unmapped": event_checks["event_player_ids_unmapped"],
            "events_with_unknown_team": event_checks["events_with_unknown_team"],
            "team_statistics_mapping_issues": mapping_issues,
            "statistics_rows": len(stat_rows),
        },
        "coordinates_available": any(
            lineup.get("coordinates_available") for lineup in lineup_report.values()
        ),
    }


def analyze_game_response(details: dict[str, Any]) -> dict[str, Any]:
    """Check only the match-details response, without needing other endpoints."""
    match = details.get("game")
    match = match if isinstance(match, dict) else {}
    home = match.get("home")
    home = home if isinstance(home, dict) else {}
    away = match.get("away")
    away = away if isinstance(away, dict) else {}
    stats = details.get("team_stats")
    stats = [row for row in stats if isinstance(row, dict)] if isinstance(stats, list) else []
    players = details.get("players")
    players = [player for player in players if isinstance(player, dict)] if isinstance(players, list) else []
    by_side, mapping_issues = _team_statistics(
        stats,
        home.get("team_id"),
        away.get("team_id"),
    )

    teams = {}
    for side in ("home", "away"):
        row = by_side.get(side)
        teams[side] = {
            "team_id": row.get("team_id") if row else None,
            "possession": _field_result(
                row, "possession_pct", "data.team_stats[].possession_pct"
            ),
            "shots": _field_result(row, "shots", "data.team_stats[].shots"),
            "shots_on_target": _field_result(
                row,
                "shots_on_target",
                "data.team_stats[].shots_on_target",
            ),
        }

    def player_stat(field: str) -> dict[str, Any]:
        values = [player[field] for player in players if _has_value(player, field)]
        return _status_for_values(values, f"data.players[].{field}")

    key_events = details.get("key_events")
    events_available = isinstance(key_events, list)
    if not events_available:
        key_events = []
    goal_events = [
        event
        for event in key_events
        if isinstance(event, dict)
        and (
            str(event.get("type", "")).lower() == "goal"
            or event.get("outcome") == "goal"
        )
    ]
    goal_event_values = [
        {
            "minute": event.get("minute"),
            "added_minute": event.get("added_minute"),
            "team_id": event.get("team_id"),
            "player": event.get("player"),
            "player_id": event.get("player_id"),
            "player2": event.get("player2"),
            "player2_id": event.get("player2_id"),
            "own_goal": event.get("own_goal"),
            "penalty": event.get("penalty"),
        }
        for event in goal_events
    ]

    return {
        "endpoint": "game",
        "match": {
            "id": match.get("game_id"),
            "home": home.get("name"),
            "away": away.get("name"),
            "home_score": home.get("score"),
            "away_score": away.get("score"),
            "status": match.get("status"),
        },
        "team_statistics": teams,
        "player_statistics": {
            "goals": player_stat("goals"),
            "assists": player_stat("assists"),
            "yellow_cards": player_stat("yellow_cards"),
            "red_cards": player_stat("red_cards"),
        },
        "key_goal_events": {
            "status": (
                "available"
                if goal_events
                else "not present in this match"
                if events_available
                else "missing"
            ),
            "path": "data.key_events[]",
            "count": len(goal_events) if events_available else None,
            "values": goal_event_values,
        },
        "team_statistics_mapping_issues": mapping_issues,
    }


def analyze_lineups_response(lineups_data: dict[str, Any]) -> dict[str, Any]:
    """Check lineups and player fields using only the lineup response."""
    game = lineups_data.get("game")
    game = game if isinstance(game, dict) else {}
    home = game.get("home")
    home = home if isinstance(home, dict) else {}
    away = game.get("away")
    away = away if isinstance(away, dict) else {}
    lineups, players = _lineup_report(
        lineups_data,
        home.get("team_id"),
        away.get("team_id"),
    )

    def player_stat(field: str) -> dict[str, Any]:
        values = [player[field] for player in players if _has_value(player, field)]
        return _status_for_values(values, f"data.lineups[].player.{field}")

    return {
        "endpoint": "lineups",
        "match": {
            "id": game.get("game_id"),
            "home": home.get("name"),
            "away": away.get("name"),
        },
        "lineups": lineups,
        "player_statistics": {
            "goals": player_stat("goals"),
            "assists": player_stat("assists"),
            "yellow_cards": player_stat("yellow_cards"),
            "red_cards": player_stat("red_cards"),
        },
        "coordinates_available": any(
            lineup.get("coordinates_available") for lineup in lineups.values()
        ),
    }


def analyze_events_response(events_data: dict[str, Any]) -> dict[str, Any]:
    """Check goal, card, and substitution events from one events response."""
    events = events_data.get("events")
    events_available = isinstance(events, list)
    if not events_available:
        events = []
    event_rows = [event for event in events if isinstance(event, dict)]
    goals = [
        event
        for event in event_rows
        if event.get("is_goal") is True
        or str(event.get("type", "")).lower() == "goal"
    ]

    def matching_events(names: set[str]) -> list[dict[str, Any]]:
        return [
            event
            for event in event_rows
            if str(event.get("type", "")).lower() in names
        ]

    yellow_cards = matching_events({"yellow-card", "yellow_card"})
    red_cards = matching_events({"red-card", "red_card"})
    substitutions = matching_events({"substitution", "substitutions"})
    assists = [
        event for event in goals
        if _has_value(event, "player2") or _has_value(event, "player2_id")
    ]

    def event_values(found: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "type": event.get("type"),
                "player": event.get("player"),
                "player_id": event.get("player_id"),
                "player2": event.get("player2"),
                "player2_id": event.get("player2_id"),
                "team_id": event.get("team_id"),
            }
            for event in found
        ]

    def event_status(
        found: list[dict[str, Any]],
        path: str,
        missing_status: str = "missing",
    ) -> dict[str, Any]:
        if found:
            return {
                "status": "available",
                "path": path,
                "count": len(found),
                "values": event_values(found),
            }
        if not events_available:
            return {"status": missing_status, "path": path}
        return {
            "status": "not present in this match",
            "path": path,
            "count": 0,
            "values": [],
        }

    return {
        "endpoint": "events",
        "event_count": events_data.get("count"),
        "goals": event_status(goals, "data.events[].type == 'goal'"),
        "goalscorers": event_status(
            [event for event in goals if _has_value(event, "player") or _has_value(event, "player_id")],
            "data.events[].player, data.events[].player_id",
        ),
        "assists": event_status(
            assists,
            "data.events[].player2, data.events[].player2_id",
            "missing (no assist value returned)",
        ),
        "yellow_cards": event_status(
            yellow_cards,
            "data.events[].type == 'yellow-card'",
        ),
        "red_cards": event_status(
            red_cards,
            "data.events[].type == 'red-card'",
        ),
        "substitutions": event_status(
            substitutions,
            "data.events[].type == 'substitution'",
        ),
    }


def verify_endpoint(
    api: FootballAPI,
    endpoint: str,
    read_timeout: float = READ_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Call and inspect only the requested endpoint."""
    timeout = httpx.Timeout(
        10.0,
        connect=10.0,
        read=read_timeout,
        write=10.0,
        pool=10.0,
    )
    if endpoint == "game":
        details = api.get_match_details(MATCH_ID, timeout=timeout)
        return analyze_game_response(details)
    if endpoint == "lineups":
        lineups = api.get_lineups(MATCH_ID, timeout=timeout)
        return analyze_lineups_response(lineups)
    if endpoint == "events":
        events = api.get_events(MATCH_ID, timeout=timeout)
        return analyze_events_response(events)
    raise ValueError("endpoint must be game, lineups, or events.")


def verify_selected_endpoint(
    api: FootballAPI,
    endpoint: str,
    read_timeout: float = READ_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Run one endpoint independently, or all three when explicitly requested."""
    if endpoint != "all":
        return verify_endpoint(api, endpoint, read_timeout)

    timeout = httpx.Timeout(
        10.0,
        connect=10.0,
        read=read_timeout,
        write=10.0,
        pool=10.0,
    )
    details = api.get_match_details(MATCH_ID, timeout=timeout)
    lineups = api.get_lineups(MATCH_ID, timeout=timeout)
    events = api.get_events(MATCH_ID, timeout=timeout)
    return analyze_match_data(details, lineups, events)


def verify_match(api: FootballAPI) -> dict[str, Any]:
    """Make exactly one request to each detail, lineup, and event endpoint."""
    return verify_selected_endpoint(api, "all")


def format_report(report: dict[str, Any]) -> str:
    """Format concise result data without printing raw responses or credentials."""
    match = report["match"]
    lines = [
        f"Match {match.get('id')}: {match.get('home')} vs {match.get('away')}",
        (
            f"Score: {match.get('home_score')} - {match.get('away_score')} "
            f"({match.get('status')})"
        ),
    ]
    for side, title in (("home", "Home"), ("away", "Away")):
        team_stats = report["team_statistics"][side]
        lines.append(
            f"{title} stats: possession {team_stats['possession']['status']}, "
            f"shots {team_stats['shots']['status']}, "
            f"shots on target {team_stats['shots_on_target']['status']}"
        )
        lineup = report["lineups"][side]
        lines.append(
            f"{title} lineup: {lineup['status']}, "
            f"formation {lineup.get('formation', {}).get('status', 'missing')}, "
            f"starters {lineup.get('starting_xi_count', 0)}, "
            f"used substitutes {lineup.get('substitutes_used_count', 0)}"
        )
    lines.append(
        "Events: goalscorers "
        f"{report['events']['goalscorers']['status']}, assists "
        f"{report['events']['assists']['status']}"
    )
    lines.append(
        "Consistency: "
        f"score {report['consistency']['details_vs_lineup_score']}, "
        "event goals "
        f"{report['consistency']['event_goals_vs_final_score']}, "
        "unmapped event player IDs "
        f"{report['consistency']['event_player_ids_unmapped']}"
    )
    lines.append(
        "Pitch coordinates: "
        + ("available" if report["coordinates_available"] else "not provided")
    )
    return "\n".join(lines)


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Independently verify one endpoint for a Serie A match."
    )
    parser.add_argument(
        "--endpoint",
        choices=("game", "lineups", "events", "all"),
        default="all",
        help="Select one endpoint, or all three (default: all).",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Allow authenticated requests after cost confirmation.",
    )
    parser.add_argument(
        "--read-timeout",
        type=float,
        default=READ_TIMEOUT_SECONDS,
        help="Response-read timeout in seconds (maximum 60; default 30).",
    )
    options = parser.parse_args(arguments)

    if not 0 < options.read_timeout <= MAX_READ_TIMEOUT_SECONDS:
        parser.error("--read-timeout must be greater than 0 and at most 60.")
    if not options.live:
        print("No API requests sent. Add --live to request live verification.")
        return 2
    key = os.getenv("STRIKER_API_KEY", "").strip()
    if not key or key.lower() in PLACEHOLDER_KEYS:
        print("API key configuration pending. No API requests sent.")
        return 2

    estimated_cost = ENDPOINT_CREDITS[options.endpoint]
    print(f"Estimated maximum cost: {estimated_cost} credits.")
    print(f"Response-read timeout: {options.read_timeout:g} seconds.")
    confirmation = input(
        f"Type VERIFY to allow the {options.endpoint} request(s) "
        f"for match {MATCH_ID}: "
    )
    if confirmation.strip() != "VERIFY":
        print("Live verification cancelled. No API requests sent.")
        return 2

    api = FootballAPI()
    start_time = time.monotonic()
    try:
        report = verify_selected_endpoint(
            api,
            options.endpoint,
            read_timeout=options.read_timeout,
        )
    except FootballAPIError as error:
        elapsed = time.monotonic() - start_time
        status = (
            str(api.last_status_code)
            if api.last_status_code is not None
            else "not received"
        )
        http_version = api.last_http_version or "not received"
        print(f"Verification failed: {type(error).__name__}.")
        print(f"HTTP status: {status}.")
        print(f"HTTP version: {http_version}.")
        print(f"Elapsed time: {elapsed:.2f} seconds.")
        return 1

    elapsed = time.monotonic() - start_time
    status = (
        str(api.last_status_code)
        if api.last_status_code is not None
        else "not received"
    )
    print(f"HTTP status: {status}.")
    print(f"HTTP version: {api.last_http_version or 'unknown'}.")
    print(f"Elapsed time: {elapsed:.2f} seconds.")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
