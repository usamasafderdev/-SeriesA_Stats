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


def test_match_list_uses_official_serie_a_code_and_api_key_header(monkeypatch):
    calls = []

    class MockClient:
        def __init__(self, timeout, **options):
            assert timeout == 15.0
            assert options == {
                "verify": True,
                "trust_env": True,
                "http1": True,
                "http2": False,
            }

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

    assert calls[0][2] == {"x-api-key": "mock-key"}
    assert matches == [{"id": "provider-id"}]
    assert calls == [
        (
            f"{BASE_URL}/v1/matches",
            {
                "sport": "football",
                "league": "serie_a",
                "date": "2026-10-25",
                "season": 2026,
                "limit": 200,
            },
            {"x-api-key": "mock-key"},
        )
    ]


def test_bounded_finished_match_list_uses_verified_request_parameters(monkeypatch):
    calls = []

    class MockClient:
        def __init__(self, timeout, **options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, url, params, headers):
            calls.append((url, params, headers))
            return httpx.Response(200, json={"data": [{"id": "sample"}]})

    monkeypatch.setattr("app.statistics_api.httpx.Client", MockClient)

    result = StatisticsAPI(api_key="mock-key").list_finished_matches(2026, 5)

    assert result == [{"id": "sample"}]
    assert calls == [
        (
            f"{BASE_URL}/v1/matches",
            {
                "sport": "football",
                "league": "serie_a",
                "season": 2026,
                "status": "finished",
                "limit": 5,
            },
            {"x-api-key": "mock-key"},
        )
    ]


def test_current_season_page_uses_documented_page_and_limit(monkeypatch):
    calls = []

    class MockClient:
        def __init__(self, timeout, **options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, url, params, headers):
            calls.append((url, params, headers))
            return httpx.Response(200, json={"data": [{"id": "sample"}]})

    monkeypatch.setattr("app.statistics_api.httpx.Client", MockClient)

    result = StatisticsAPI(api_key="mock-key").list_season_matches(
        2026, page=2, limit=200
    )

    assert result == [{"id": "sample"}]
    assert calls[0][1] == {
        "sport": "football",
        "league": "serie_a",
        "season": 2026,
        "page": 2,
        "limit": 200,
    }


@pytest.mark.parametrize("limit", [0, 6, True])
def test_finished_match_list_rejects_unsafe_limits_before_request(monkeypatch, limit):
    monkeypatch.setattr(
        "app.statistics_api.httpx.Client",
        lambda **_options: pytest.fail("Invalid limits must not make requests."),
    )

    with pytest.raises(ValueError, match="between 1 and 5"):
        StatisticsAPI(api_key="mock-key").list_finished_matches(2026, limit)


def test_statistics_request_uses_bigballs_match_id_not_striker_id(monkeypatch):
    calls = []

    class MockClient:
        def __init__(self, timeout, **options):
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
    monkeypatch.delenv("BBS_API_KEY", raising=False)
    monkeypatch.delenv("BIGBALLSDATA_API_KEY", raising=False)
    monkeypatch.setattr(
        "app.statistics_api.httpx.Client",
        lambda **_options: pytest.fail("No key must cause no request."),
    )

    with pytest.raises(MissingStatisticsAPIKeyError):
        StatisticsAPI().find_matches("2026-10-25", 2026)


def test_bbs_api_key_is_the_primary_environment_variable(monkeypatch):
    monkeypatch.setenv("BBS_API_KEY", "primary-mock-key")
    monkeypatch.setenv("BIGBALLSDATA_API_KEY", "legacy-mock-key")

    api = StatisticsAPI()

    assert api._api_key == "primary-mock-key"


def test_legacy_api_key_remains_a_fallback(monkeypatch):
    monkeypatch.delenv("BBS_API_KEY", raising=False)
    monkeypatch.setenv("BIGBALLSDATA_API_KEY", "legacy-mock-key")

    api = StatisticsAPI()

    assert api._api_key == "legacy-mock-key"


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
        def __init__(self, timeout, **options):
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
        def __init__(self, timeout, **options):
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
