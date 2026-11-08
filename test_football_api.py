import json

import httpx
import pytest

from app.football_api import (
    BASE_URL,
    FootballAPI,
    FootballAPIConnectTimeoutError,
    FootballAPIIncompleteResponseError,
    FootballAPINetworkError,
    FootballAPIResponseBodyTimeoutError,
    FootballAPIResponseHeaderTimeoutError,
    FootballAPIRequestError,
    FootballAPITimeoutError,
    InsufficientCreditsError,
    InvalidAPIKeyError,
    MalformedFootballAPIResponseError,
    MissingAPIKeyError,
    RateLimitError,
)


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        body: object = None,
        body_error: Exception | None = None,
    ):
        self.status_code = status_code
        self.body = body
        self.body_error = body_error
        self.http_version = "HTTP/1.1"

    def read(self):
        if self.body_error is not None:
            raise self.body_error
        return b"mock response body"

    def json(self):
        if isinstance(self.body, Exception):
            raise self.body
        return self.body


class FakeClient:
    def __init__(self, options, calls, response=None, send_error=None):
        self.options = options
        self.calls = calls
        self.response = response
        self.send_error = send_error

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def build_request(self, method, url, json, headers):
        return httpx.Request(method, url, json=json, headers=headers)

    def send(self, request, stream=False):
        self.calls.append(
            (
                str(request.url),
                {
                    "json": json.loads(request.content),
                    "headers": request.headers,
                    "timeout": self.options["timeout"],
                    "stream": stream,
                    "client_options": self.options,
                },
            )
        )
        if self.send_error is not None:
            raise self.send_error
        return self.response


def patch_client(
    monkeypatch,
    calls,
    response=None,
    send_error=None,
    client_options=None,
):
    def client_factory(**options):
        if client_options is not None:
            client_options.update(options)
        return FakeClient(options, calls, response, send_error)

    monkeypatch.setattr("app.football_api.httpx.Client", client_factory)


def make_api(monkeypatch, response_body, status_code=200):
    """Create a client whose HTTP request returns a chosen response."""
    recorded_calls = []
    patch_client(
        monkeypatch,
        recorded_calls,
        response=FakeResponse(status_code, response_body),
    )
    return FootballAPI(api_key="test-key"), recorded_calls


def test_match_request_uses_documented_url_post_headers_and_parameters(monkeypatch):
    api, calls = make_api(monkeypatch, {"data": {"games": [], "count": 0}})

    result = api.get_matches(2025, limit=3)

    assert result == {"games": [], "count": 0}
    url, options = calls[0]
    assert url == f"{BASE_URL}/v1/list_games"
    assert options["json"] == {
        "league": "seriea",
        "season": 2025,
        "limit": 3,
    }
    assert options["headers"]["x-api-key"] == "test-key"
    assert options["headers"]["Content-Type"] == "application/json"
    assert options["timeout"] > 0


def test_match_request_includes_optional_final_status_and_custom_read_timeout(
    monkeypatch,
):
    api, calls = make_api(monkeypatch, {"data": {"games": [], "count": 0}})
    request_timeout = httpx.Timeout(10.0, read=30.0)

    api.get_matches(2025, limit=3, status="final", timeout=request_timeout)

    request_data = calls[0][1]["json"]
    assert request_data == {
        "league": "seriea",
        "season": 2025,
        "status": "final",
        "limit": 3,
    }
    assert calls[0][1]["timeout"].read == 30.0


@pytest.mark.parametrize("status", ["live", "FINAL", "", "postponed"])
def test_invalid_match_status_is_rejected_before_request(monkeypatch, status):
    def unexpected_client(*args, **kwargs):
        pytest.fail("Invalid status must not send an API request.")

    monkeypatch.setattr("app.football_api.httpx.Client", unexpected_client)
    api = FootballAPI(api_key="test-key")

    with pytest.raises(ValueError, match="status"):
        api.get_matches(2025, status=status)


def test_game_details_request_uses_documented_post_endpoint_and_league(monkeypatch):
    response = {
        "data": {
            "game": {},
            "team_stats": [],
            "players": [],
            "key_events": [],
            "odds": [],
        }
    }
    api, calls = make_api(monkeypatch, response)

    result = api.get_match_details("game-123")

    assert result == response["data"]
    assert calls[0][0] == f"{BASE_URL}/v1/get_game"
    assert calls[0][1]["json"] == {
        "game_id": "game-123",
        "league": "seriea",
    }
    assert calls[0][1]["stream"] is True
    assert calls[0][1]["client_options"]["verify"] is True
    assert calls[0][1]["client_options"]["trust_env"] is True
    assert calls[0][1]["client_options"]["http2"] is False
    assert api.last_status_code == 200
    assert api.last_http_version == "HTTP/1.1"


def test_lineups_request_uses_documented_post_endpoint_and_league(monkeypatch):
    response = {"data": {"game": {}, "lineups": []}}
    api, calls = make_api(monkeypatch, response)

    assert api.get_lineups(123) == response["data"]
    assert calls[0][0] == f"{BASE_URL}/v1/get_lineups"
    assert calls[0][1]["json"] == {"game_id": "123", "league": "seriea"}


def test_events_request_uses_documented_post_endpoint_and_league(monkeypatch):
    response = {"data": {"events": [], "count": 0}}
    api, calls = make_api(monkeypatch, response)

    assert api.get_events("123") == response["data"]
    assert calls[0][0] == f"{BASE_URL}/v1/get_events"
    assert calls[0][1]["json"] == {"game_id": "123", "league": "seriea"}


def test_match_listing_returns_unwrapped_data_envelope(monkeypatch):
    data = {"games": [{"game_id": "1"}], "count": 1, "next_offset": None}
    api, _ = make_api(monkeypatch, {"data": data})

    assert api.get_matches("2025") == data


def test_missing_api_key_is_reported_without_sending_a_request(monkeypatch):
    def unexpected_post(*args, **kwargs):
        pytest.fail("A request must not be sent without an API key.")

    monkeypatch.setattr("app.football_api.httpx.Client", unexpected_post)
    api = FootballAPI(api_key="")

    with pytest.raises(MissingAPIKeyError, match="STRIKER_API_KEY"):
        api.get_matches(2025)


def test_invalid_api_key_response_is_reported(monkeypatch):
    api, _ = make_api(monkeypatch, {"error": "unauthorized"}, status_code=401)

    with pytest.raises(InvalidAPIKeyError, match="rejected"):
        api.get_matches(2025)


def test_insufficient_credit_response_is_reported(monkeypatch):
    api, _ = make_api(monkeypatch, {"error": "credits"}, status_code=402)

    with pytest.raises(InsufficientCreditsError, match="credits"):
        api.get_matches(2025)


def test_rate_limit_response_is_reported(monkeypatch):
    api, _ = make_api(monkeypatch, {"error": "rate limited"}, status_code=429)

    with pytest.raises(RateLimitError, match="rate limit"):
        api.get_matches(2025)


def test_invalid_arguments_response_is_reported(monkeypatch):
    api, _ = make_api(monkeypatch, {"error": "invalid"}, status_code=400)

    with pytest.raises(FootballAPIRequestError, match="arguments"):
        api.get_matches(2025)


def test_header_timeout_is_reported_before_any_response_status(monkeypatch):
    calls = []
    patch_client(
        monkeypatch,
        calls,
        send_error=httpx.ReadTimeout("request timed out"),
    )
    api = FootballAPI(api_key="test-key")

    with pytest.raises(
        FootballAPIResponseHeaderTimeoutError,
        match="did not send response headers",
    ):
        api.get_matches(2025)
    assert api.last_status_code is None


def test_body_timeout_is_reported_separately_after_headers(monkeypatch):
    calls = []
    patch_client(
        monkeypatch,
        calls,
        response=FakeResponse(
            200,
            {"data": {"games": [], "count": 0}},
            body_error=httpx.ReadTimeout("body stalled"),
        ),
    )
    api = FootballAPI(api_key="test-key")

    with pytest.raises(
        FootballAPIResponseBodyTimeoutError,
        match="response body stalled",
    ):
        api.get_matches(2025)

    assert api.last_status_code == 200


def test_incomplete_response_body_is_reported(monkeypatch):
    calls = []
    patch_client(
        monkeypatch,
        calls,
        response=FakeResponse(
            200,
            {"data": {"games": [], "count": 0}},
            body_error=httpx.RemoteProtocolError("incomplete body"),
        ),
    )
    api = FootballAPI(api_key="test-key")

    with pytest.raises(
        FootballAPIIncompleteResponseError,
        match="body was complete",
    ):
        api.get_matches(2025)

    assert api.last_status_code == 200


def test_connection_timeout_is_reported_separately(monkeypatch):
    patch_client(
        monkeypatch,
        [],
        send_error=httpx.ConnectTimeout("connection timed out"),
    )
    api = FootballAPI(api_key="test-key")

    with pytest.raises(
        FootballAPIConnectTimeoutError,
        match="Could not connect to StrikerAPI",
    ):
        api.get_matches(2025)


def test_other_timeout_is_reported_as_a_general_timeout(monkeypatch):
    patch_client(
        monkeypatch,
        [],
        send_error=httpx.WriteTimeout("request send timed out"),
    )
    api = FootballAPI(api_key="test-key")

    with pytest.raises(FootballAPITimeoutError, match="sending or waiting"):
        api.get_matches(2025)


def test_network_connection_error_is_reported(monkeypatch):
    request = httpx.Request("POST", f"{BASE_URL}/v1/list_games")
    patch_client(
        monkeypatch,
        [],
        send_error=httpx.ConnectError("connection failed", request=request),
    )
    api = FootballAPI(api_key="test-key")

    with pytest.raises(FootballAPINetworkError, match="connect"):
        api.get_matches(2025)


def test_invalid_json_response_is_reported(monkeypatch):
    api, _ = make_api(
        monkeypatch,
        json.JSONDecodeError("invalid", "{", 0),
    )

    with pytest.raises(MalformedFootballAPIResponseError, match="invalid JSON"):
        api.get_matches(2025)


@pytest.mark.parametrize(
    "response_body",
    [
        {},
        {"data": []},
        {"data": {"count": 0}},
        {"data": {"games": "not a list", "count": 0}},
        {"data": {"games": [], "count": "zero"}},
    ],
)
def test_missing_or_malformed_match_fields_are_reported(monkeypatch, response_body):
    api, _ = make_api(monkeypatch, response_body)

    with pytest.raises(MalformedFootballAPIResponseError):
        api.get_matches(2025)


def test_unexpected_details_field_types_are_reported(monkeypatch):
    response = {
        "data": {
            "game": [],
            "team_stats": [],
            "players": [],
            "key_events": [],
            "odds": [],
        }
    }
    api, _ = make_api(monkeypatch, response)

    with pytest.raises(MalformedFootballAPIResponseError, match="game"):
        api.get_match_details(123)


@pytest.mark.parametrize(
    ("season", "limit"),
    [
        (" ", 20),
        (True, 20),
        (2025, 0),
        (2025, 201),
        (2025, True),
    ],
)
def test_invalid_match_list_arguments_are_rejected(season, limit):
    api = FootballAPI(api_key="test-key")

    with pytest.raises(ValueError):
        api.get_matches(season, limit=limit)


def test_empty_game_id_is_rejected():
    api = FootballAPI(api_key="test-key")

    with pytest.raises(ValueError, match="game_id"):
        api.get_match_details(" ")
