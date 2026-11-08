import argparse

from app.football_api import (
    FootballAPI,
    FootballAPIError,
    MissingAPIKeyError,
)


def main(arguments: list[str] | None = None) -> int:
    """Make a small live match-list request only after explicit confirmation."""
    parser = argparse.ArgumentParser(
        description="Show a small sample of StrikerAPI match data."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Allow one authenticated request after credit confirmation.",
    )
    parser.add_argument(
        "--season",
        default="2025",
        help="Season start year (for example, 2025 means 2025-26).",
    )
    options = parser.parse_args(arguments)

    if not options.live:
        print("No API requests sent. Add --live to request sample matches.")
        return 2

    print(
        "Estimated list_games cost: not independently verified. "
        "Check current StrikerAPI pricing before continuing."
    )
    confirmation = input("Type VERIFY to allow one request for up to 3 matches: ")
    if confirmation.strip() != "VERIFY":
        print("Live match-list request cancelled. No API requests sent.")
        return 2

    api = FootballAPI()
    try:
        match_data = api.get_matches(options.season, limit=3)
    except MissingAPIKeyError:
        print("No API key is configured. Add STRIKER_API_KEY to the project .env file.")
        return 1
    except FootballAPIError as error:
        print(f"StrikerAPI request failed: {error}")
        return 1

    for game in match_data["games"]:
        if not isinstance(game, dict):
            continue

        home_team = game.get("home")
        away_team = game.get("away")
        home_team = home_team if isinstance(home_team, dict) else {}
        away_team = away_team if isinstance(away_team, dict) else {}

        print("Match ID:", game.get("game_id", "Not provided"))
        print("Home team:", home_team.get("name", "Not provided"))
        print("Away team:", away_team.get("name", "Not provided"))
        print("Match date:", game.get("date", "Not provided"))

        home_score = home_team.get("score")
        away_score = away_team.get("score")
        if home_score is not None and away_score is not None:
            print(f"Score: {home_score} - {away_score}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
