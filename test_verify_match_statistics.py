import json

import httpx
import pytest

from app import verify_match_statistics as verifier
from app.football_api import FootballAPIReadTimeoutError


def make_details():
    return {
        "game": {
            "game_id": "737158",
            "status": "final",
            "home": {"team_id": "home-id", "name": "Torino", "score": 2},
            "away": {"team_id": "away-id", "name": "Juventus", "score": 2},
        },
        "team_stats": [
            {
                "team_id": "away-id",
                "home": False,
                "possession_pct": 0,
                "shots": 11,
                "shots_on_target": 4,
            },
            {
                "team_id": "home-id",
                "home": True,
                "possession_pct": 0,
                "shots": 12,
                "shots_on_target": 5,
            },
        ],
        "players": [
            {
                "player_id": "scorer-1",
                "name": "Sample scorer",
                "goals": 1,
                "assists": 0,
                "yellow_cards": 0,
                "red_cards": 0,
            },
            {
                "player_id": "scorer-2",
                "name": "Sample scorer two",
                "goals": 1,
                "assists": 0,
                "yellow_cards": 1,
                "red_cards": 0,
            },
        ],
        "key_events": [],
        "odds": [],
    }


def make_lineups():
    return {
        "game": {
            "home": {"score": 2},
            "away": {"score": 2},
        },
        "lineups": [
            {
                "team_id": "home-id",
                "formation": "3-4-2-1",
                "starting_xi": [
                    {
                        "player_id": "scorer-1",
                        "name": "Sample scorer",
                        "position": "Forward",
                        "jersey": "9",
                        "formation_place": 1,
                        "minute_on": 0,
                        "minute_off": None,
                        "goals": 1,
                        "assists": 0,
                        "yellow_cards": 0,
                        "red_cards": 0,
                    }
                ],
                "substitutes_used": [],
                "unused_substitutes": [{"player_id": "sub-1", "name": "Bench player"}],
            },
            {
                "team_id": "away-id",
                "formation": "4-3-3",
                "starting_xi": [
                    {
                        "player_id": "scorer-2",
                        "name": "Sample scorer two",
                        "position": "Forward",
                        "jersey": "10",
                        "formation_place": 2,
                        "minute_on": 0,
                        "minute_off": 75,
                        "goals": 1,
                        "assists": 0,
                        "yellow_cards": 1,
                        "red_cards": 0,
                    }
                ],
                "substitutes_used": [
                    {
                        "player_id": "sub-2",
                        "name": "Used substitute",
                        "jersey": "17",
                        "position": None,
                        "formation_place": None,
                        "minute_on": 75,
                        "minute_off": None,
                        "goals": 0,
                        "assists": 0,
                        "yellow_cards": 0,
                        "red_cards": 0,
                    }
                ],
                "unused_substitutes": [],
            },
        ],
    }


def make_events():
    return {
        "events": [
            {
                "type": "goal",
                "is_goal": True,
                "team_id": "home-id",
                "player_id": "scorer-1",
                "player": "Sample scorer",
                "player2_id": "assist-1",
                "player2": "Sample assister",
            },
            {
                "type": "goal",
                "is_goal": True,
                "team_id": "away-id",
                "player_id": "scorer-2",
                "player": "Sample scorer two",
                "player2_id": None,
                "player2": None,
            },
            {
                "type": "goal",
                "is_goal": True,
                "team_id": "away-id",
                "player_id": "scorer-2",
                "player": "Sample scorer two",
                "player2_id": None,
                "player2": None,
            },
        ],
        "count": 3,
    }


def test_analyzer_distinguishes_zero_from_missing_and_maps_team_statistics():
    details = make_details()
    details["team_stats"][1].pop("possession_pct")

    report = verifier.analyze_match_data(
        details,
        make_lineups(),
        make_events(),
    )

    assert report["team_statistics"]["home"]["possession"]["status"] == "missing"
    assert report["team_statistics"]["away"]["possession"] == {
        "status": "available (zero recorded)",
        "value": 0,
        "path": "data.team_stats[team].possession_pct",
    }
    assert report["team_statistics"]["home"]["shots"]["value"] == 12
    assert report["team_statistics"]["away"]["shots"]["value"] == 11
    assert report["consistency"]["details_vs_lineup_score"] == "consistent"
    assert report["consistency"]["event_goals_vs_final_score"] == "inconsistent"


def test_analyzer_checks_both_lineups_and_player_fields():
    report = verifier.analyze_match_data(
        make_details(),
        make_lineups(),
        make_events(),
    )

    assert report["lineups"]["home"]["formation"]["value"] == "3-4-2-1"
    assert report["lineups"]["away"]["starting_xi"][0] == {
        "name": "Sample scorer two",
        "player_id": "scorer-2",
        "position": "Forward",
        "jersey": "10",
        "formation_place": 2,
        "minute_on": 0,
        "minute_off": 75,
        "goals": 1,
        "assists": 0,
        "yellow_cards": 1,
        "red_cards": 0,
    }
    assert report["lineups"]["home"]["unused_substitutes_count"] == 1
    assert report["lineups"]["away"]["substitutes_used_count"] == 1
    assert report["lineups"]["away"]["starting_xi"][0]["formation_place"] == 2
    assert report["lineups"]["away"]["starting_xi"][0]["minute_off"] == 75
    assert report["lineups"]["away"]["substitutes_used"][0]["minute_on"] == 75
    assert report["coordinates_available"] is False
    assert report["player_statistics"]["red_cards"]["status"] == (
        "available (zero recorded)"
    )
    assert report["player_statistics"]["yellow_cards"]["status"] == "available"
    assert report["events"]["assists"]["status"] == "available"
    assert len(report["events"]["assists"]["values"]) == 1
    assert report["consistency"]["events_with_unknown_team"] == 0


def test_game_analyzer_reports_statistics_and_key_goal_event_minutes():
    details = make_details()
    details["key_events"] = [
        {
            "minute": 19,
            "added_minute": 2,
            "type": "goal",
            "team_id": "home-id",
            "player_id": "scorer-1",
            "player": "Sample scorer",
            "player2_id": "assist-1",
            "player2": "Sample assister",
            "own_goal": False,
            "penalty": False,
        }
    ]

    report = verifier.analyze_game_response(details)

    assert report["match"]["id"] == "737158"
    assert report["match"]["home_score"] == 2
    assert report["team_statistics"]["home"]["possession"]["value"] == 0
    assert report["team_statistics"]["away"]["shots"]["value"] == 11
    assert report["player_statistics"]["goals"]["status"] == "available"
    assert report["player_statistics"]["assists"]["status"] == (
        "available (zero recorded)"
    )
    assert report["key_goal_events"]["values"][0]["minute"] == 19
    assert report["key_goal_events"]["values"][0]["added_minute"] == 2
    assert report["key_goal_events"]["values"][0]["player2"] == "Sample assister"


def test_game_analyzer_distinguishes_missing_key_events_from_empty_list():
    details = make_details()
    details.pop("key_events")

    report = verifier.analyze_game_response(details)
    assert report["key_goal_events"]["status"] == "missing"

    details["key_events"] = []
    report = verifier.analyze_game_response(details)
    assert report["key_goal_events"]["status"] == "not present in this match"
    assert report["key_goal_events"]["count"] == 0


def test_unmapped_event_player_ids_are_reported():
    events = make_events()
    events["events"][0]["player2_id"] = "not-in-lineups"

    report = verifier.analyze_match_data(
        make_details(),
        make_lineups(),
        events,
    )

    assert report["consistency"]["event_player_ids_unmapped"] == 1


def test_missing_assists_are_not_reported_as_zero():
    events = make_events()
    for event in events["events"]:
        event["player2"] = None
        event["player2_id"] = None

    report = verifier.analyze_match_data(
        make_details(),
        make_lineups(),
        events,
    )

    assert report["events"]["assists"]["status"] == (
        "missing (no assist value returned)"
    )


def test_verification_makes_only_three_requests_with_read_timeout():
    class MockAPI:
        def __init__(self):
            self.calls = []

        def get_match_details(self, game_id, timeout):
            self.calls.append(("details", game_id, timeout.read))
            return make_details()

        def get_lineups(self, game_id, timeout):
            self.calls.append(("lineups", game_id, timeout.read))
            return make_lineups()

        def get_events(self, game_id, timeout):
            self.calls.append(("events", game_id, timeout.read))
            return make_events()

    api = MockAPI()

    verifier.verify_match(api)

    assert api.calls == [
        ("details", "737158", 30.0),
        ("lineups", "737158", 30.0),
        ("events", "737158", 30.0),
    ]


def test_verification_stops_after_first_failed_request():
    class FailedAPI:
        def __init__(self):
            self.calls = []

        def get_match_details(self, game_id, timeout):
            self.calls.append(("details", game_id))
            raise FootballAPIReadTimeoutError("timeout")

        def get_lineups(self, game_id, timeout):
            self.calls.append(("lineups", game_id))
            return make_lineups()

        def get_events(self, game_id, timeout):
            self.calls.append(("events", game_id))
            return make_events()

    api = FailedAPI()

    with pytest.raises(FootballAPIReadTimeoutError):
        verifier.verify_match(api)

    assert api.calls == [("details", "737158")]


@pytest.mark.parametrize(
    ("endpoint", "expected_call"),
    [
        ("game", "details"),
        ("lineups", "lineups"),
        ("events", "events"),
    ],
)
def test_selected_endpoint_calls_only_its_matching_api_method(
    endpoint,
    expected_call,
):
    class IndependentAPI:
        def __init__(self):
            self.calls = []

        def get_match_details(self, game_id, timeout):
            self.calls.append(("details", game_id, timeout.read))
            return make_details()

        def get_lineups(self, game_id, timeout):
            self.calls.append(("lineups", game_id, timeout.read))
            return make_lineups()

        def get_events(self, game_id, timeout):
            self.calls.append(("events", game_id, timeout.read))
            return make_events()

    api = IndependentAPI()

    report = verifier.verify_selected_endpoint(api, endpoint)

    assert report["endpoint"] == endpoint
    assert len(api.calls) == 1
    assert api.calls[0][0] == expected_call
    assert api.calls[0][1] == "737158"
    assert api.calls[0][2] == 30.0


def test_game_endpoint_accepts_sixty_second_read_timeout():
    class GameAPI:
        def __init__(self):
            self.calls = []

        def get_match_details(self, game_id, timeout):
            self.calls.append((game_id, timeout.connect, timeout.read))
            return make_details()

    api = GameAPI()

    report = verifier.verify_selected_endpoint(
        api,
        "game",
        read_timeout=60.0,
    )

    assert report["endpoint"] == "game"
    assert api.calls == [("737158", 10.0, 60.0)]


@pytest.mark.parametrize(
    ("endpoint", "failed_method"),
    [
        ("game", "get_match_details"),
        ("lineups", "get_lineups"),
        ("events", "get_events"),
    ],
)
def test_independent_endpoint_failure_does_not_call_another_method(
    endpoint,
    failed_method,
):
    class FailingAPI:
        def __init__(self):
            self.calls = []

        def get_match_details(self, game_id, timeout):
            self.calls.append("get_match_details")
            raise FootballAPIReadTimeoutError("timeout")

        def get_lineups(self, game_id, timeout):
            self.calls.append("get_lineups")
            raise FootballAPIReadTimeoutError("timeout")

        def get_events(self, game_id, timeout):
            self.calls.append("get_events")
            raise FootballAPIReadTimeoutError("timeout")

    api = FailingAPI()

    with pytest.raises(FootballAPIReadTimeoutError):
        verifier.verify_selected_endpoint(api, endpoint)

    assert api.calls == [failed_method]


def test_events_response_distinguishes_empty_events_from_missing_field():
    report = verifier.analyze_events_response({"events": [], "count": 0})

    assert report["goals"]["status"] == "not present in this match"
    assert report["yellow_cards"]["status"] == "not present in this match"

    report = verifier.analyze_events_response(
        {"events": [{"type": "foul"}], "count": 1}
    )

    assert report["goals"]["status"] == "not present in this match"
    assert report["red_cards"]["status"] == "not present in this match"
    assert report["substitutions"]["status"] == "not present in this match"

    report = verifier.analyze_events_response({"count": 0})

    assert report["goals"]["status"] == "missing"


def test_events_response_includes_goal_scorers_and_assisting_players():
    report = verifier.analyze_events_response(
        {
            "events": [
                {
                    "type": "goal",
                    "player": "Demo scorer",
                    "player_id": "player-1",
                    "player2": "Demo assister",
                    "player2_id": "player-2",
                    "team_id": "team-1",
                },
                {
                    "type": "yellow-card",
                    "player": "Demo player",
                    "player_id": "player-3",
                    "team_id": "team-2",
                },
                {
                    "type": "substitution",
                    "player": "Player off",
                    "player2": "Player on",
                    "team_id": "team-1",
                },
            ],
            "count": 3,
        }
    )

    assert report["goalscorers"]["values"][0]["player"] == "Demo scorer"
    assert report["assists"]["values"][0]["player2"] == "Demo assister"
    assert report["yellow_cards"]["values"][0]["player"] == "Demo player"
    assert report["substitutions"]["values"][0]["player2"] == "Player on"


@pytest.mark.parametrize(
    ("endpoint", "credits"),
    [("game", 5), ("lineups", 5), ("events", 10), ("all", 20)],
)
def test_cli_shows_selected_endpoint_cost_before_confirmation(
    monkeypatch,
    capsys,
    endpoint,
    credits,
):
    monkeypatch.setenv("STRIKER_API_KEY", "mock-key")
    monkeypatch.setattr("builtins.input", lambda _prompt: "no")
    monkeypatch.setattr(
        verifier,
        "verify_selected_endpoint",
        lambda *_args: pytest.fail("Cancelled verification must not call the API."),
    )

    result = verifier.main(["--live", "--endpoint", endpoint])

    output = capsys.readouterr().out
    assert result == 2
    assert f"{credits} credits" in output


def test_api_client_passes_timeout_to_each_documented_operation(monkeypatch):
    from app.football_api import FootballAPI

    calls = []

    class Response:
        status_code = 200
        http_version = "HTTP/1.1"

        def __init__(self, data):
            self.data = data

        def read(self):
            return b"mock body"

        def json(self):
            return {"data": self.data}

    class Client:
        def __init__(self, **options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def build_request(self, method, url, json, headers):
            return httpx.Request(method, url, json=json, headers=headers)

        def send(self, request, stream=False):
            calls.append(
                (
                    str(request.url),
                    {
                        "json": json.loads(request.content),
                        "timeout": self.options["timeout"],
                    },
                )
            )
            if request.url.path.endswith("/get_game"):
                return Response(
                    {
                        "game": {},
                        "team_stats": [],
                        "players": [],
                        "key_events": [],
                        "odds": [],
                    }
                )
            if request.url.path.endswith("/get_lineups"):
                return Response({"game": {}, "lineups": []})
            return Response({"events": [], "count": 0})

    monkeypatch.setattr("app.football_api.httpx.Client", Client)
    api = FootballAPI(api_key="mock-key")
    timeout = httpx.Timeout(10.0, read=30.0)

    api.get_match_details("737158", timeout=timeout)
    api.get_lineups("737158", timeout=timeout)
    api.get_events("737158", timeout=timeout)

    assert [call[0].rsplit("/", 1)[-1] for call in calls] == [
        "get_game",
        "get_lineups",
        "get_events",
    ]
    assert all(call[1]["json"]["league"] == "seriea" for call in calls)
    assert all(call[1]["json"]["game_id"] == "737158" for call in calls)
    assert all(call[1]["timeout"].read == 30.0 for call in calls)


def test_cli_shows_cost_and_requires_confirmation_before_requests(monkeypatch, capsys):
    monkeypatch.setenv("STRIKER_API_KEY", "mock-key")
    monkeypatch.setattr("builtins.input", lambda _prompt: "no")
    monkeypatch.setattr(
        verifier,
        "verify_selected_endpoint",
        lambda *_args: pytest.fail("Cancelled verification must not call the API."),
    )

    result = verifier.main(["--live"])

    output = capsys.readouterr().out
    assert result == 2
    assert "20 credits" in output
    assert "cancelled" in output.lower()


def test_cli_runs_only_selected_endpoint_after_verify_confirmation(
    monkeypatch,
    capsys,
):
    class MockAPI:
        last_status_code = 200
        last_http_version = "HTTP/1.1"

    calls = []
    monkeypatch.setenv("STRIKER_API_KEY", "mock-key")
    monkeypatch.setattr("builtins.input", lambda _prompt: "VERIFY")
    monkeypatch.setattr(verifier, "FootballAPI", MockAPI)
    monkeypatch.setattr(
        verifier,
        "verify_selected_endpoint",
        lambda api, endpoint, **_options: (
            calls.append((api, endpoint)) or {"endpoint": endpoint}
        ),
    )

    result = verifier.main(["--live", "--endpoint", "lineups"])

    assert result == 0
    assert len(calls) == 1
    assert isinstance(calls[0][0], MockAPI)
    assert calls[0][1] == "lineups"
    output = capsys.readouterr().out
    assert '"endpoint": "lineups"' in output
    assert "HTTP status: 200." in output
    assert "HTTP version: HTTP/1.1." in output
    assert "Elapsed time:" in output


def test_cli_requires_live_flag_without_calling_api(monkeypatch, capsys):
    monkeypatch.setattr(
        verifier,
        "verify_selected_endpoint",
        lambda *_args: pytest.fail("Without --live, the API must not be called."),
    )

    result = verifier.main([])

    assert result == 2
    assert "No API requests sent" in capsys.readouterr().out
