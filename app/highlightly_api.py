"""Small no-retry client for Highlightly Football through RapidAPI."""

import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv


PROJECT_FOLDER = Path(__file__).resolve().parent.parent
BASE_URL = "https://football-highlights-api.p.rapidapi.com"
REQUEST_TIMEOUT = 15.0
load_dotenv(PROJECT_FOLDER / ".env")


class HighlightlyError(Exception):
    """Base error for Highlightly requests."""


class MissingHighlightlyKeyError(HighlightlyError):
    """Raised when the RapidAPI key is not configured."""


class HighlightlyClient:
    """Fetch one match, lineup, and box-score response without retries."""

    def __init__(self, api_key: str | None = None):
        configured = api_key if api_key is not None else os.getenv("X_API_KEY")
        self._api_key = configured.strip() if configured else ""

    @staticmethod
    def _match_id_path(match_id: int) -> str:
        if isinstance(match_id, bool) or not isinstance(match_id, int) or match_id <= 0:
            raise ValueError("match_id must be a positive whole number.")
        return str(match_id)

    def _get(self, path: str, params: dict[str, Any]) -> Any:
        if not self._api_key:
            raise MissingHighlightlyKeyError("Set X_API_KEY in the local .env file.")
        try:
            with httpx.Client(
                timeout=REQUEST_TIMEOUT,
                verify=True,
                trust_env=True,
                http1=True,
                http2=False,
            ) as client:
                response = client.get(
                    f"{BASE_URL}{path}",
                    params=params,
                    headers={
                        "x-rapidapi-key": self._api_key,
                        "x-rapidapi-host": "football-highlights-api.p.rapidapi.com",
                    },
                )
        except httpx.TimeoutException as error:
            raise HighlightlyError(
                "Highlightly timed out. No retry was made."
            ) from error
        except httpx.RequestError as error:
            raise HighlightlyError("Could not connect to Highlightly.") from error
        if response.status_code >= 400:
            raise HighlightlyError(
                f"Highlightly returned HTTP {response.status_code}."
            )
        try:
            return response.json()
        except ValueError as error:
            raise HighlightlyError("Highlightly returned invalid JSON.") from error

    def get_matches(self, date: str, home_team: str, away_team: str) -> Any:
        return self._get(
            "/matches",
            {
                "date": date,
                "homeTeamName": home_team,
                "awayTeamName": away_team,
                "limit": 20,
                "timezone": "Etc/UTC",
            },
        )

    def get_lineups(self, match_id: int) -> Any:
        return self._get(f"/lineups/{self._match_id_path(match_id)}", {})

    def get_box_score(self, match_id: int) -> Any:
        return self._get(f"/box-score/{self._match_id_path(match_id)}", {})

    def get_events(self, match_id: int) -> Any:
        return self._get(f"/events/{self._match_id_path(match_id)}", {})

    def get_statistics(self, match_id: int) -> Any:
        return self._get(f"/statistics/{self._match_id_path(match_id)}", {})
