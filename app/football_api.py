import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv


PROJECT_FOLDER = Path(__file__).resolve().parent.parent
BASE_URL = "https://mcp.strikerapi.com"
SERIE_A_LEAGUE = "seriea"
REQUEST_TIMEOUT = 10.0

# Load local settings when this module is imported. A missing .env is okay.
load_dotenv(PROJECT_FOLDER / ".env")


class FootballAPIError(Exception):
    """Base error for problems when contacting StrikerAPI."""


class MissingAPIKeyError(FootballAPIError):
    """Raised when no API key is configured."""


class InvalidAPIKeyError(FootballAPIError):
    """Raised when StrikerAPI rejects the API key."""


class InsufficientCreditsError(FootballAPIError):
    """Raised when the account does not have enough API credits."""


class RateLimitError(FootballAPIError):
    """Raised when StrikerAPI temporarily limits requests."""


class FootballAPITimeoutError(FootballAPIError):
    """Raised when a request takes too long."""


class FootballAPIConnectTimeoutError(FootballAPITimeoutError):
    """Raised when a connection to StrikerAPI cannot be established in time."""


class FootballAPIReadTimeoutError(FootballAPITimeoutError):
    """Raised when StrikerAPI does not send a response in time."""


class FootballAPIResponseHeaderTimeoutError(FootballAPIReadTimeoutError):
    """Raised when StrikerAPI does not send response headers in time."""


class FootballAPIResponseBodyTimeoutError(FootballAPIReadTimeoutError):
    """Raised when StrikerAPI response body stops arriving in time."""


class FootballAPIIncompleteResponseError(FootballAPIError):
    """Raised when the server closes a response before the body is complete."""


class FootballAPINetworkError(FootballAPIError):
    """Raised when a request cannot reach StrikerAPI."""


class FootballAPIRequestError(FootballAPIError):
    """Raised when StrikerAPI reports another request error."""


class MalformedFootballAPIResponseError(FootballAPIError):
    """Raised when StrikerAPI returns an unexpected response structure."""


class FootballAPI:
    """A small client for the documented StrikerAPI football endpoints."""

    def __init__(self, api_key: str | None = None):
        configured_key = api_key if api_key is not None else os.getenv(
            "STRIKER_API_KEY"
        )
        self._api_key = configured_key.strip() if configured_key else ""
        self.last_status_code: int | None = None
        self.last_http_version: str | None = None

    def _post(
        self,
        endpoint: str,
        request_data: dict[str, Any],
        required_fields: tuple[str, ...],
        timeout: httpx.Timeout | float | None = None,
    ) -> dict[str, Any]:
        """Send one POST request and return its validated data object."""
        if not self._api_key:
            raise MissingAPIKeyError(
                "Set STRIKER_API_KEY in the project .env file before making a request."
            )

        self.last_status_code = None
        self.last_http_version = None
        request_timeout = timeout if timeout is not None else REQUEST_TIMEOUT
        try:
            with httpx.Client(
                timeout=request_timeout,
                verify=True,
                trust_env=True,
                http1=True,
                http2=False,
            ) as client:
                request = client.build_request(
                    "POST",
                    f"{BASE_URL}/v1/{endpoint}",
                    json=request_data,
                    headers={
                        "x-api-key": self._api_key,
                        "Content-Type": "application/json",
                    },
                )
                try:
                    response = client.send(request, stream=True)
                except httpx.ReadTimeout as error:
                    raise FootballAPIResponseHeaderTimeoutError(
                        "StrikerAPI did not send response headers before the read timeout."
                    ) from error

                self.last_status_code = response.status_code
                self.last_http_version = response.http_version
                if response.status_code == 401:
                    raise InvalidAPIKeyError("StrikerAPI rejected the API key.")
                if response.status_code == 402:
                    raise InsufficientCreditsError(
                        "The StrikerAPI account does not have enough credits."
                    )
                if response.status_code == 429:
                    raise RateLimitError("StrikerAPI rate limit reached.")
                if response.status_code == 400:
                    raise FootballAPIRequestError(
                        "StrikerAPI rejected the request arguments."
                    )
                if response.status_code >= 300:
                    raise FootballAPIRequestError(
                        f"StrikerAPI returned HTTP {response.status_code}."
                    )
                try:
                    response.read()
                except httpx.ReadTimeout as error:
                    raise FootballAPIResponseBodyTimeoutError(
                        "StrikerAPI sent response headers, but its response body stalled."
                    ) from error
                except httpx.RemoteProtocolError as error:
                    raise FootballAPIIncompleteResponseError(
                        "StrikerAPI closed the connection before the response body was complete."
                    ) from error
        except httpx.ConnectTimeout as error:
            raise FootballAPIConnectTimeoutError(
                "Could not connect to StrikerAPI before the connection timeout."
            ) from error
        except httpx.TimeoutException as error:
            raise FootballAPITimeoutError(
                "The StrikerAPI request timed out while sending or waiting for a connection."
            ) from error
        except httpx.RequestError as error:
            raise FootballAPINetworkError(
                "Could not connect to StrikerAPI."
            ) from error

        try:
            response_body = response.json()
        except ValueError as error:
            raise MalformedFootballAPIResponseError(
                "StrikerAPI returned invalid JSON."
            ) from error

        if not isinstance(response_body, dict):
            raise MalformedFootballAPIResponseError(
                "StrikerAPI response must be a JSON object."
            )

        data = response_body.get("data")
        if not isinstance(data, dict):
            raise MalformedFootballAPIResponseError(
                "StrikerAPI response is missing its data object."
            )

        missing_fields = [
            field_name for field_name in required_fields if field_name not in data
        ]
        if missing_fields:
            field_list = ", ".join(missing_fields)
            raise MalformedFootballAPIResponseError(
                f"StrikerAPI response is missing required data: {field_list}."
            )

        return data

    @staticmethod
    def _check_list_field(data: dict[str, Any], field_name: str) -> None:
        """Make sure a documented list field contains a JSON array."""
        if not isinstance(data[field_name], list):
            raise MalformedFootballAPIResponseError(
                f"StrikerAPI data field '{field_name}' must be a list."
            )

    @staticmethod
    def _check_object_field(data: dict[str, Any], field_name: str) -> None:
        """Make sure a documented object field contains a JSON object."""
        if not isinstance(data[field_name], dict):
            raise MalformedFootballAPIResponseError(
                f"StrikerAPI data field '{field_name}' must be an object."
            )

    @staticmethod
    def _check_count_field(data: dict[str, Any]) -> None:
        """Check that the documented result count is numeric."""
        count = data["count"]
        if isinstance(count, bool) or not isinstance(count, (int, float)):
            raise MalformedFootballAPIResponseError(
                "StrikerAPI data field 'count' must be a number."
            )

    def get_matches(
        self,
        season: int | str,
        limit: int = 20,
        status: str | None = None,
        timeout: httpx.Timeout | float | None = None,
    ) -> dict[str, Any]:
        """List Serie A games for the requested season."""
        if isinstance(season, bool) or not isinstance(season, (int, str)):
            raise ValueError("season must be a year number or non-empty string.")
        if not str(season).strip():
            raise ValueError("season cannot be empty.")
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 200
        ):
            raise ValueError("limit must be a whole number between 1 and 200.")
        if status is not None and status not in {"scheduled", "final"}:
            raise ValueError("status must be 'scheduled' or 'final'.")

        request_data: dict[str, Any] = {
            "league": SERIE_A_LEAGUE,
            "season": season,
            "limit": limit,
        }
        if status is not None:
            request_data["status"] = status
        data = self._post(
            "list_games",
            request_data,
            ("games", "count"),
            timeout=timeout,
        )
        self._check_list_field(data, "games")
        self._check_count_field(data)
        return data

    def get_match_details(
        self,
        game_id: int | str,
        timeout: httpx.Timeout | float | None = None,
    ) -> dict[str, Any]:
        """Return the documented game details and statistics."""
        normalized_game_id = self._check_game_id(game_id)
        data = self._post(
            "get_game",
            {"game_id": normalized_game_id, "league": SERIE_A_LEAGUE},
            ("game", "team_stats", "players", "key_events", "odds"),
            timeout=timeout,
        )
        self._check_object_field(data, "game")
        for field_name in ("team_stats", "players", "key_events", "odds"):
            self._check_list_field(data, field_name)
        return data

    def get_lineups(
        self,
        game_id: int | str,
        timeout: httpx.Timeout | float | None = None,
    ) -> dict[str, Any]:
        """Return the documented lineup information for a game."""
        normalized_game_id = self._check_game_id(game_id)
        data = self._post(
            "get_lineups",
            {"game_id": normalized_game_id, "league": SERIE_A_LEAGUE},
            ("game", "lineups"),
            timeout=timeout,
        )
        self._check_object_field(data, "game")
        self._check_list_field(data, "lineups")
        return data

    def get_events(
        self,
        game_id: int | str,
        timeout: httpx.Timeout | float | None = None,
    ) -> dict[str, Any]:
        """Return the documented event list for a game."""
        normalized_game_id = self._check_game_id(game_id)
        data = self._post(
            "get_events",
            {"game_id": normalized_game_id, "league": SERIE_A_LEAGUE},
            ("events", "count"),
            timeout=timeout,
        )
        self._check_list_field(data, "events")
        self._check_count_field(data)
        return data

    @staticmethod
    def _check_game_id(game_id: int | str) -> str:
        """Convert a match ID to the string format used by StrikerAPI."""
        if isinstance(game_id, bool) or not isinstance(game_id, (int, str)):
            raise ValueError("game_id must be an integer or non-empty string.")
        normalized_game_id = str(game_id).strip()
        if not normalized_game_id:
            raise ValueError("game_id cannot be empty.")
        return normalized_game_id
