"""Small HTTP client for the documented BigBallsData football endpoints."""

import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv


PROJECT_FOLDER = Path(__file__).resolve().parent.parent
BASE_URL = "https://api.bigballsdata.com"
REQUEST_TIMEOUT = 15.0
load_dotenv(PROJECT_FOLDER / ".env")


class StatisticsAPIError(Exception):
    """Base error for problems when contacting BigBallsData."""


class MissingStatisticsAPIKeyError(StatisticsAPIError):
    """Raised when no local BigBallsData API key is configured."""


class StatisticsAPITimeoutError(StatisticsAPIError):
    """Raised when BigBallsData does not respond before the timeout."""


class StatisticsAPIRateLimitError(StatisticsAPIError):
    """Raised when the BigBallsData request limit is reached."""


class StatisticsAPIPlanError(StatisticsAPIError):
    """Raised when the configured plan cannot access the requested data."""


class StatisticsAPINetworkError(StatisticsAPIError):
    """Raised when the API cannot be reached."""


class MalformedStatisticsAPIResponseError(StatisticsAPIError):
    """Raised when the API response does not match its documented shape."""


class StatisticsAPI:
    """Read Serie A fixtures and stored match statistics."""

    def __init__(self, api_key: str | None = None):
        configured_key = api_key if api_key is not None else os.getenv(
            "BIGBALLSDATA_API_KEY"
        )
        self._api_key = configured_key.strip() if configured_key else ""

    def _get(
        self,
        path: str,
        params: dict[str, str | int],
    ) -> dict[str, Any]:
        """Send one authenticated GET request without retrying."""
        if not self._api_key:
            raise MissingStatisticsAPIKeyError(
                "Set BIGBALLSDATA_API_KEY in the local .env file."
            )

        try:
            with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
                response = client.get(
                    f"{BASE_URL}{path}",
                    params=params,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
        except httpx.TimeoutException as error:
            raise StatisticsAPITimeoutError(
                "BigBallsData did not respond before the timeout. No retry was made."
            ) from error
        except httpx.RequestError as error:
            raise StatisticsAPINetworkError(
                "Could not connect to BigBallsData."
            ) from error

        if response.status_code == 401:
            raise MissingStatisticsAPIKeyError(
                "BigBallsData rejected the configured API key."
            )
        if response.status_code == 403:
            raise StatisticsAPIPlanError(
                "This BigBallsData plan cannot access the requested season or data."
            )
        if response.status_code == 404:
            raise MalformedStatisticsAPIResponseError(
                "BigBallsData could not find the requested match."
            )
        if response.status_code == 429:
            raise StatisticsAPIRateLimitError(
                "BigBallsData rate limit reached. No retry was made."
            )
        if response.status_code >= 400:
            raise StatisticsAPIError(
                f"BigBallsData returned HTTP {response.status_code}."
            )

        try:
            body = response.json()
        except ValueError as error:
            raise MalformedStatisticsAPIResponseError(
                "BigBallsData returned invalid JSON."
            ) from error

        if not isinstance(body, dict):
            raise MalformedStatisticsAPIResponseError(
                "BigBallsData response must be a JSON object."
            )
        if body.get("error"):
            raise MalformedStatisticsAPIResponseError(
                "BigBallsData returned an error in its response envelope."
            )
        return body

    def find_matches(
        self,
        match_date: str,
        season: int,
    ) -> list[dict[str, Any]]:
        """Find fixtures for one UTC day and the requested season."""
        body = self._get(
            "/v1/matches",
            {
                "sport": "football",
                "league": "seriea",
                "date": match_date,
                "season": season,
                "limit": 200,
            },
        )
        matches = body.get("data")
        if not isinstance(matches, list) or any(
            not isinstance(match, dict) for match in matches
        ):
            raise MalformedStatisticsAPIResponseError(
                "BigBallsData match data must be a list of match objects."
            )
        return matches

    def get_match_statistics(self, provider_match_id: str) -> dict[str, Any]:
        """Read the stored-only statistics for a BigBallsData match ID."""
        if not isinstance(provider_match_id, str) or not provider_match_id.strip():
            raise ValueError("provider_match_id must be non-empty text.")
        return self._get(
            f"/v1/matches/{provider_match_id.strip()}/statistics",
            {},
        )
