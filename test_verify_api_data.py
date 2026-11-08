import pytest

from app import verify_api_data


class MockFootballAPI:
    """Return sample responses and record the calls made by the verifier."""

    def __init__(self):
        self.calls = []

    def get_matches(self, season, limit):
        self.calls.append(("matches", season, limit))
        return {
            "games": [
                {
                    "game_id": "scheduled-1",
                    "status": "scheduled",
                },
                {
                    "game_id": "completed-2",
                    "status": "final",
                    "date": "2025-05-01",
                    "home": {"name": "Demo Home", "score": 2},
                    "away": {"name": "Demo Away", "score": 1},
                },
            ],
            "count": 2,
        }

    def get_match_details(self, game_id):
        self.calls.append(("details", game_id))
        return {
            "game": {"game_id": game_id},
            "team_stats": [
                {
                    "team_id": "home-id",
                    "home": True,
                    "possession_pct": 55.0,
                    "shots": 12,
                    "shots_on_target": 5,
                },
                {
                    "team_id": "away-id",
                    "home": False,
                    "possession_pct": 45.0,
                    "shots": 8,
                    "shots_on_target": 3,
                },
            ],
            "players": [
                {
                    "name": "Sample scorer",
                    "goals": 1,
                    "assists": 0,
                    "yellow_cards": 1,
                    "red_cards": 0,
                }
            ],
            "key_events": [],
            "odds": [],
        }

    def get_lineups(self, game_id):
        self.calls.append(("lineups", game_id))
        return {
            "game": {"game_id": game_id},
            "lineups": [
                {
                    "formation": "4-3-3",
                    "starting_xi": [
                        {
                            "name": "Sample player",
                            "position": "Goalkeeper",
                        }
                    ],
                    "substitutes_used": [],
                    "unused_substitutes": [],
                }
            ],
        }

    def get_events(self, game_id):
        self.calls.append(("events", game_id))
        return {
            "events": [
                {
                    "type": "goal",
                    "player": "Sample scorer",
                    "player2": "Sample assister",
                }
            ],
            "count": 1,
        }


def test_verification_checks_one_completed_match_with_only_four_calls():
    api = MockFootballAPI()

    report = verify_api_data.run_verification(api, season=2025)

    assert api.calls == [
        ("matches", 2025, 3),
        ("details", "completed-2"),
        ("lineups", "completed-2"),
        ("events", "completed-2"),
    ]
    assert report["api_calls"] == 4
    assert report["match"]["id"] == "completed-2"
    assert report["match"]["home_team"] == "Demo Home"
    assert report["match"]["away_team"] == "Demo Away"
    assert report["fields"]["Team statistics"]["Possession"]["status"] == (
        "available"
    )
    assert report["fields"]["Player statistics"]["Goalscorers"]["status"] == (
        "available"
    )
    assert report["fields"]["Lineups"]["Formation"]["status"] == "available"


def test_verification_does_not_request_details_without_completed_match():
    api = MockFootballAPI()
    api.get_matches = lambda season, limit: {
        "games": [{"game_id": "scheduled-1", "status": "scheduled"}],
        "count": 1,
    }

    report = verify_api_data.run_verification(api)

    assert report["api_calls"] == 1
    assert report["match"] is None
    assert all(
        field["status"] == "unverified"
        for section in report["fields"].values()
        for field in section.values()
    )


def test_verification_reports_zero_zero_goal_fields_as_not_applicable():
    scorers, assists = verify_api_data._inspect_goals(
        [],
        {
            "home": {"score": 0},
            "away": {"score": 0},
        },
    )

    assert scorers["status"] == "not applicable"
    assert assists["status"] == "not applicable"


def test_cli_requires_explicit_live_flag_before_any_request(monkeypatch, capsys):
    monkeypatch.setattr(
        verify_api_data,
        "FootballAPI",
        lambda: pytest.fail("The client must not be initialized without --live."),
    )

    result = verify_api_data.main([])

    assert result == 2
    assert "No API requests sent" in capsys.readouterr().out


def test_cli_does_not_request_api_when_key_is_missing(monkeypatch, capsys):
    monkeypatch.setattr(verify_api_data, "_has_configured_key", lambda: False)
    monkeypatch.setattr(
        verify_api_data,
        "FootballAPI",
        lambda: pytest.fail("The client must not be used without a configured key."),
    )

    result = verify_api_data.main(["--live"])

    assert result == 2
    assert "API key configuration pending" in capsys.readouterr().out


def test_cli_requires_verify_after_displaying_credit_estimate(monkeypatch, capsys):
    monkeypatch.setattr(verify_api_data, "_has_configured_key", lambda: True)
    monkeypatch.setattr(
        verify_api_data,
        "FootballAPI",
        lambda: pytest.fail("No client should be created before VERIFY."),
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: "NO")

    result = verify_api_data.main(["--live"])

    output = capsys.readouterr().out
    assert result == 2
    assert "up to 20 credits" in output
    assert "list_games charge (not verified)" in output
    assert "No API requests sent" in output


def test_cli_runs_verification_only_after_verify(monkeypatch, capsys):
    monkeypatch.setattr(verify_api_data, "_has_configured_key", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _prompt: "VERIFY")
    monkeypatch.setattr(
        verify_api_data,
        "run_verification",
        lambda api, season: {
            "season": season,
            "api_calls": 4,
            "match": None,
            "fields": {},
        },
    )

    result = verify_api_data.main(["--live", "--season", "2025"])

    assert result == 0
    assert "Authenticated responses: Yes" in capsys.readouterr().out


def test_report_lists_exact_json_paths_without_raw_payloads():
    report = verify_api_data.run_verification(MockFootballAPI())

    output = verify_api_data.format_report(report)

    assert "team_stats[].possession_pct" in output
    assert "lineups[].starting_xi[].position" in output
    assert "Sample scorer" not in output
    assert "API key" not in output


def test_match_response_without_games_is_rejected():
    class InvalidMatchAPI:
        def get_matches(self, season, limit):
            return {"count": 0}

    with pytest.raises(ValueError, match="games list"):
        verify_api_data.run_verification(InvalidMatchAPI())
