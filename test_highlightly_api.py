from app.highlightly_api import HighlightlyClient


class FakeResponse:
    status_code = 200

    def json(self):
        return {"lineups": []}


class FakeClient:
    last_url = None

    def __init__(self, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def get(self, url, **_kwargs):
        self.last_url = url
        FakeClient.last_url = url
        return FakeResponse()


def test_lineup_url_uses_decimal_match_id(monkeypatch):
    monkeypatch.setattr("app.highlightly_api.httpx.Client", FakeClient)
    HighlightlyClient(api_key="test-key").get_lineups(1319211623)
    assert FakeClient.last_url.endswith("/lineups/1319211623")
    assert "e+" not in FakeClient.last_url
