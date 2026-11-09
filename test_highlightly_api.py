from app.highlightly_api import HIGHLIGHTLY_SERIE_A_LEAGUE_ID, HighlightlyClient
import pytest


@pytest.fixture(autouse=True)
def isolated_diagnostics(tmp_path, monkeypatch):
    monkeypatch.setattr("app.highlightly_api.DIAGNOSTIC_FOLDER", tmp_path)


class FakeResponse:
    status_code = 200

    def json(self):
        return {"lineups": []}


class FakeClient:
    last_url = None
    last_params = None

    def __init__(self, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def get(self, url, **_kwargs):
        self.last_url = url
        FakeClient.last_url = url
        FakeClient.last_params = _kwargs.get("params")
        return FakeResponse()


def test_lineup_url_uses_decimal_match_id(monkeypatch):
    monkeypatch.setattr("app.highlightly_api.httpx.Client", FakeClient)
    HighlightlyClient(api_key="test-key").get_lineups(1319211623)
    assert FakeClient.last_url.endswith("/lineups/1319211623")
    assert "e+" not in FakeClient.last_url


def test_match_lookup_uses_serie_a_season_filter(monkeypatch):
    monkeypatch.setattr("app.highlightly_api.httpx.Client", FakeClient)
    HighlightlyClient(api_key="test-key").get_matches(
        "2026-11-08",
        league_id=HIGHLIGHTLY_SERIE_A_LEAGUE_ID,
        season=2026,
    )
    assert FakeClient.last_url.endswith("/matches")
    assert FakeClient.last_params["date"] == "2026-11-08"
    assert FakeClient.last_params["leagueId"] == HIGHLIGHTLY_SERIE_A_LEAGUE_ID
    assert FakeClient.last_params["season"] == 2026
