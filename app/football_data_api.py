"""Small client for the official football-data.org competition endpoints."""

import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv


PROJECT_FOLDER = Path(__file__).resolve().parent.parent
BASE_URL = "https://api.football-data.org/v4"
REQUEST_TIMEOUT = 15.0
load_dotenv(PROJECT_FOLDER / ".env")


class FootballDataError(Exception):
    """Base error for football-data.org requests."""


class MissingFootballDataTokenError(FootballDataError):
    """Raised when no football-data.org token is configured."""


class MalformedFootballDataResponseError(FootballDataError):
    """Raised when the provider response is not the documented object shape."""


class FootballDataClient:
    """Fetch one fixture list and one standings table without retries."""

    def __init__(self, token: str | None = None):
        configured = token if token is not None else os.getenv("FOOTBALL_DATA_TOKEN")
        self._token = configured.strip() if configured else ""

    def _get(self, path: str, season: int) -> dict[str, Any]:
        if not self._token:
            raise MissingFootballDataTokenError(
                "Set FOOTBALL_DATA_TOKEN in the project .env file."
            )
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
                    params={"season": season},
                    headers={"X-Auth-Token": self._token},
                )
        except httpx.TimeoutException as error:
            raise FootballDataError(
                "football-data.org did not respond before the timeout. No retry was made."
            ) from error
        except httpx.RequestError as error:
            raise FootballDataError(
                "Could not connect to football-data.org."
            ) from error
        if response.status_code >= 400:
            raise FootballDataError(
                f"football-data.org returned HTTP {response.status_code}."
            )
        try:
            body = response.json()
        except ValueError as error:
            raise MalformedFootballDataResponseError(
                "football-data.org returned invalid JSON."
            ) from error
        if not isinstance(body, dict):
            raise MalformedFootballDataResponseError(
                "football-data.org response must be a JSON object."
            )
        return body

    def get_matches(self, season: int) -> dict[str, Any]:
        return self._get("/competitions/SA/matches", season)

    def get_standings(self, season: int) -> dict[str, Any]:
        return self._get("/competitions/SA/standings", season)
