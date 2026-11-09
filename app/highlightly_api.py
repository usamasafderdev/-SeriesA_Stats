"""Small no-retry client for Highlightly Football through RapidAPI."""

import os
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv


PROJECT_FOLDER = Path(__file__).resolve().parent.parent
BASE_URL = "https://football-highlights-api.p.rapidapi.com"
REQUEST_TIMEOUT = 15.0
HIGHLIGHTLY_SERIE_A_LEAGUE_ID = 115669
DIAGNOSTIC_FOLDER = PROJECT_FOLDER / "runtime" / "highlightly"
load_dotenv(PROJECT_FOLDER / ".env")


class HighlightlyError(Exception):
    """Base error for Highlightly requests."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class MissingHighlightlyKeyError(HighlightlyError):
    """Raised when the RapidAPI key is not configured."""


class HighlightlyClient:
    """Fetch one match, lineup, and box-score response without retries."""

    def __init__(self, api_key: str | None = None):
        configured = api_key if api_key is not None else os.getenv("X_API_KEY")
        self._api_key = configured.strip() if configured else ""

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

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
        # Only quota metadata is retained; never persist authentication headers.
        quota = {
            str(name).lower(): value
            for name, value in getattr(response, "headers", {}).items()
            if str(name).lower().startswith(("x-ratelimit-", "ratelimit-"))
        }
        if quota:
            try:
                DIAGNOSTIC_FOLDER.mkdir(parents=True, exist_ok=True)
                (DIAGNOSTIC_FOLDER / "quota.json").write_text(json.dumps({
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                    "headers": quota,
                }, indent=2), encoding="utf-8")
            except OSError:
                pass
        if response.status_code >= 400:
            raise HighlightlyError(
                f"Highlightly returned HTTP {response.status_code}.", response.status_code,
            )
        try:
            payload = response.json()
        except ValueError as error:
            raise HighlightlyError("Highlightly returned invalid JSON.") from error
        self._save_diagnostic(path, params, response.status_code, payload)
        if isinstance(payload, dict) and (payload.get("error") or payload.get("errors")):
            raise HighlightlyError("Highlightly returned an error payload. Batch stopped.")
        return payload

    @staticmethod
    def _save_diagnostic(
        path: str,
        params: dict[str, Any],
        status_code: int,
        payload: Any,
    ) -> None:
        """Save a response without authentication headers for local diagnosis."""
        try:
            DIAGNOSTIC_FOLDER.mkdir(parents=True, exist_ok=True)
            endpoint = path.strip("/").replace("/", "_") or "root"
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            target = DIAGNOSTIC_FOLDER / f"{timestamp}_{endpoint}.json"
            target.write_text(
                json.dumps(
                    {
                        "path": path,
                        "params": params,
                        "status_code": status_code,
                        "payload": payload,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError:
            return

    def get_matches(
        self,
        date: str,
        home_team: str | None = None,
        away_team: str | None = None,
        league_id: int | None = None,
        season: int | None = None,
    ) -> Any:
        params: dict[str, Any] = {
            "date": date,
            "limit": 20,
            "timezone": "Etc/UTC",
        }
        if home_team:
            params["homeTeamName"] = home_team
        if away_team:
            params["awayTeamName"] = away_team
        if league_id is not None:
            params["leagueId"] = league_id
        if season is not None:
            params["season"] = season
        return self._get(
            "/matches",
            params,
        )

    def get_match(self, match_id: int) -> Any:
        return self._get(f"/matches/{self._match_id_path(match_id)}", {})

    def get_lineups(self, match_id: int) -> Any:
        return self._get(f"/lineups/{self._match_id_path(match_id)}", {})

    def get_box_score(self, match_id: int) -> Any:
        return self._get(f"/box-score/{self._match_id_path(match_id)}", {})

    def get_events(self, match_id: int) -> Any:
        return self._get(f"/events/{self._match_id_path(match_id)}", {})

    def get_statistics(self, match_id: int) -> Any:
        return self._get(f"/statistics/{self._match_id_path(match_id)}", {})


def local_quota() -> dict:
    """Read the last observed provider quota without contacting RapidAPI."""
    try:
        saved = json.loads((DIAGNOSTIC_FOLDER / "quota.json").read_text(encoding="utf-8"))
        headers = {key.casefold(): value for key, value in saved["headers"].items()}
        remaining = headers.get("x-ratelimit-requests-remaining")
        if remaining is None:
            return {"remaining": None, "observed_at": saved.get("observed_at"), "status": "unknown"}
        observed = datetime.fromisoformat(saved["observed_at"])
        reset = headers.get("x-ratelimit-requests-reset")
        age = (datetime.now(timezone.utc) - observed).total_seconds()
        if age < 0 or age > 86400 or (reset and age >= float(reset)):
            return {"remaining": None, "observed_at": saved["observed_at"], "status": "stale"}
        return {"remaining": max(0, int(remaining)), "observed_at": saved["observed_at"],
                "status": "last_observed", "reset_seconds": reset}
    except (OSError, ValueError, KeyError, TypeError):
        return {"remaining": None, "observed_at": None, "status": "unknown"}
