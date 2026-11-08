from typing import Any


def _record(value: Any) -> dict[str, Any]:
    """Return a response object, or an empty object when it is missing."""
    return value if isinstance(value, dict) else {}


def _players(value: Any) -> list[dict[str, Any]]:
    """Convert a response list into normalized player dictionaries."""
    if not isinstance(value, list):
        return []

    converted_players = []
    for player_value in value:
        if not isinstance(player_value, dict):
            continue

        player = player_value
        converted_players.append(
            {
                "player_id": player.get("player_id"),
                "name": player.get("name"),
                "shirt_number": player.get("jersey"),
                "position": player.get("position"),
                "formation_slot": player.get("formation_place"),
                "goals": player.get("goals"),
                "assists": player.get("assists"),
                "yellow_cards": player.get("yellow_cards"),
                "red_cards": player.get("red_cards"),
                "minute_on": player.get("minute_on"),
                "minute_off": player.get("minute_off"),
            }
        )

    return converted_players


def convert_match(api_match: dict[str, Any]) -> dict[str, Any]:
    """Convert one StrikerAPI match-list record to a consistent dictionary."""
    if not isinstance(api_match, dict):
        raise ValueError("api_match must be a dictionary.")

    home = _record(api_match.get("home"))
    away = _record(api_match.get("away"))

    return {
        "match_id": api_match.get("game_id"),
        "season": api_match.get("season"),
        "match_date": api_match.get("date"),
        "home_team_id": home.get("team_id"),
        "home_team_name": home.get("name"),
        "away_team_id": away.get("team_id"),
        "away_team_name": away.get("name"),
        "home_score": home.get("score"),
        "away_score": away.get("score"),
        "status": api_match.get("status"),
    }


def convert_lineup(api_lineup: dict[str, Any]) -> dict[str, Any]:
    """Convert one team's StrikerAPI lineup record to a consistent dictionary."""
    if not isinstance(api_lineup, dict):
        raise ValueError("api_lineup must be a dictionary.")

    return {
        "team_id": api_lineup.get("team_id"),
        "formation": api_lineup.get("formation"),
        "starting_players": _players(api_lineup.get("starting_xi")),
        "substitutes_used": _players(api_lineup.get("substitutes_used")),
        "unused_substitutes": _players(api_lineup.get("unused_substitutes")),
    }
