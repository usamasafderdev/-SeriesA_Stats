import pytest

from app import smoke_test


def test_live_match_list_requires_live_flag(monkeypatch, capsys):
    monkeypatch.setattr(
        smoke_test,
        "FootballAPI",
        lambda: pytest.fail("The client must not be created without --live."),
    )

    result = smoke_test.main([])

    assert result == 2
    assert "No API requests sent" in capsys.readouterr().out


def test_live_match_list_requires_verify(monkeypatch, capsys):
    monkeypatch.setattr(
        smoke_test,
        "FootballAPI",
        lambda: pytest.fail("The client must not be created before VERIFY."),
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: "no")

    result = smoke_test.main(["--live"])

    output = capsys.readouterr().out
    assert result == 2
    assert "not independently verified" in output
    assert "No API requests sent" in output


def test_live_match_list_uses_mock_api_after_verify(monkeypatch, capsys):
    calls = []

    class MockFootballAPI:
        def get_matches(self, season, limit):
            calls.append((season, limit))
            return {"games": []}

    monkeypatch.setattr(smoke_test, "FootballAPI", MockFootballAPI)
    monkeypatch.setattr("builtins.input", lambda _prompt: "VERIFY")

    result = smoke_test.main(["--live", "--season", "2025"])

    assert result == 0
    assert calls == [("2025", 3)]
