import httpx
import pytest

from app.statistics_api import (
    BASE_URL,
    MissingStatisticsAPIKeyError,
    StatisticsAPI,
    StatisticsAPIPlanError,
    StatisticsAPIRateLimitError,
    StatisticsAPITimeoutError,
)


def test_match_list_uses_documented_serie_a_filters_and_bearer_auth(monkeypatch):
    calls = []

    class MockClient:
        def __init__(self, timeout):
            assert timeout == 15.0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, url, params, headers):
            calls.append((url, params, headers))
            return httpx.Response(
                200,
                json={"data": [{"id": "provider-id"}], "meta": {}, "error": None},
            )

    monkeypatch.setattr("app.statistics_api.httpx.Client", MockClient)
    matches = StatisticsAPI(api_key="mock-key").find_matches("2026-10-25", 2026)

    assert matches == [{"id": "provider-id"}]
    assert calls == [
        (
            f"{BASE_URL}/v1/matches",
            {
                "sport": "football",
                "league": "seriea",
                "date": "2026-10-25",
                "season": 2026,
                "limit": 200,
            },
            {"Authorization": "Bearer mock-key"},
        )
    ]


def test_statistics_request_uses_bigballs_match_id_not_striker_id(monkeypatch):
    calls = []

    class MockClient:
        def __init__(self, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, url, params, headers):
            calls.append((url, params))
            return httpx.Response(
                200,
                json={"data": {"home": None, "away": None}, "meta": {}},
            )

    monkeypatch.setattr("app.statistics_api.httpx.Client", MockClient)
    api = StatisticsAPI(api_key="mock-key")
    api.get_match_statistics("bbe0db21-9e62-4cb0-a65c-b1dc7781aa66")

    assert calls == [
        (
            f"{BASE_URL}/v1/matches/bbe0db21-9e62-4cb0-a65c-b1dc7781aa66/statistics",
            {},
        )
    ]


def test_missing_key_fails_before_network_request(monkeypatch):
    monkeypatch.delenv("BIGBALLSDATA_API_KEY", raising=False)
    monkeypatch.setattr(
        "app.statistics_api.httpx.Client",
        lambda **_options: pytest.fail("No key must cause no request."),
    )

    with pytest.raises(MissingStatisticsAPIKeyError):
        StatisticsAPI().find_matches("2026-10-25", 2026)


@pytest.mark.parametrize(
    ("status_code", "exception_type"),
    [
        (403, StatisticsAPIPlanError),
        (429, StatisticsAPIRateLimitError),
    ],
)
def test_provider_plan_and_rate_limit_errors_are_explicit(
    monkeypatch,
    status_code,
    exception_type,
):
    class MockClient:
        def __init__(self, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, *_args, **_kwargs):
            return httpx.Response(status_code, json={"error": {"code": "error"}})

    monkeypatch.setattr("app.statistics_api.httpx.Client", MockClient)

    with pytest.raises(exception_type):
        StatisticsAPI(api_key="mock-key").find_matches("2026-10-25", 2026)


def test_provider_timeout_is_not_retried(monkeypatch):
    calls = []

    class MockClient:
        def __init__(self, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, *_args, **_kwargs):
            calls.append("request")
            raise httpx.ReadTimeout("mock timeout")

    monkeypatch.setattr("app.statistics_api.httpx.Client", MockClient)

    with pytest.raises(StatisticsAPITimeoutError):
        StatisticsAPI(api_key="mock-key").find_matches("2026-10-25", 2026)

    assert calls == ["request"]
