import pytest

from app.data_converter import convert_lineup, convert_match


def match_list_fixture():
    return {
        "game_id": "737158",
        "season": 2025,
        "date": "2026-05-24",
        "status": "final",
        "home": {
            "team_id": "239",
            "name": "Torino",
            "score": 2,
        },
        "away": {
            "team_id": "268",
            "name": "Juventus",
            "score": 2,
        },
    }


def lineup_fixture():
    return {
        "team_id": "239",
        "formation": "3-4-1-2",
        "starting_xi": [
            {
                "player_id": "241414",
                "name": "Demo Goalkeeper",
                "jersey": "1",
                "position": "Goalkeeper",
                "formation_place": 1,
                "minute_on": 0,
                "minute_off": None,
                "goals": 0,
                "assists": 0,
                "yellow_cards": 0,
                "red_cards": 0,
            },
            {
                "player_id": "129285",
                "name": "Demo Forward",
                "jersey": "9",
                "position": "Forward",
                "formation_place": 11,
                "minute_on": 0,
                "minute_off": 69,
                "goals": 1,
                "assists": None,
                "yellow_cards": 1,
                "red_cards": 0,
            },
        ],
        "substitutes_used": [
            {
                "player_id": "100001",
                "name": "Demo Substitute",
                "jersey": "17",
                "position": None,
                "formation_place": None,
                "minute_on": 69,
                "minute_off": None,
                "goals": 0,
                "assists": 0,
                "yellow_cards": 0,
                "red_cards": 0,
            }
        ],
        "unused_substitutes": [
            {
                "player_id": "100002",
                "name": "Demo Bench Player",
                "jersey": "21",
            }
        ],
    }


def test_convert_match_maps_verified_match_list_fields():
    converted = convert_match(match_list_fixture())

    assert converted == {
        "match_id": "737158",
        "season": 2025,
        "match_date": "2026-05-24",
        "home_team_id": "239",
        "home_team_name": "Torino",
        "away_team_id": "268",
        "away_team_name": "Juventus",
        "home_score": 2,
        "away_score": 2,
        "status": "final",
    }


def test_convert_match_preserves_zero_scores_and_missing_fields():
    api_match = {"game_id": "0", "home": {"score": 0}, "away": {}}

    converted = convert_match(api_match)

    assert converted["match_id"] == "0"
    assert converted["home_score"] == 0
    assert converted["away_score"] is None
    assert converted["home_team_name"] is None
    assert converted["season"] is None
    assert converted["match_date"] is None


def test_convert_match_rejects_non_dictionary_input():
    with pytest.raises(ValueError, match="api_match"):
        convert_match(None)


def test_convert_lineup_maps_starting_players_and_statistics():
    converted = convert_lineup(lineup_fixture())

    assert converted["team_id"] == "239"
    assert converted["formation"] == "3-4-1-2"
    assert converted["starting_players"] == [
        {
            "player_id": "241414",
            "name": "Demo Goalkeeper",
            "shirt_number": "1",
            "position": "Goalkeeper",
            "formation_slot": 1,
            "goals": 0,
            "assists": 0,
            "yellow_cards": 0,
            "red_cards": 0,
            "minute_on": 0,
            "minute_off": None,
        },
        {
            "player_id": "129285",
            "name": "Demo Forward",
            "shirt_number": "9",
            "position": "Forward",
            "formation_slot": 11,
            "goals": 1,
            "assists": None,
            "yellow_cards": 1,
            "red_cards": 0,
            "minute_on": 0,
            "minute_off": 69,
        },
    ]


def test_convert_lineup_can_normalize_both_team_records():
    home_lineup = lineup_fixture()
    away_lineup = {
        "team_id": "268",
        "formation": "3-4-2-1",
        "starting_xi": [{"player_id": "200001", "name": "Demo Away Player"}],
        "substitutes_used": [],
        "unused_substitutes": [],
    }

    converted_teams = [
        convert_lineup(home_lineup),
        convert_lineup(away_lineup),
    ]

    assert [team["team_id"] for team in converted_teams] == ["239", "268"]
    assert [team["formation"] for team in converted_teams] == [
        "3-4-1-2",
        "3-4-2-1",
    ]
    assert len(converted_teams[0]["starting_players"]) == 2
    assert len(converted_teams[1]["starting_players"]) == 1


def test_convert_lineup_keeps_used_and_unused_substitutes_separate():
    converted = convert_lineup(lineup_fixture())

    assert converted["substitutes_used"] == [
        {
            "player_id": "100001",
            "name": "Demo Substitute",
            "shirt_number": "17",
            "position": None,
            "formation_slot": None,
            "goals": 0,
            "assists": 0,
            "yellow_cards": 0,
            "red_cards": 0,
            "minute_on": 69,
            "minute_off": None,
        }
    ]
    assert converted["unused_substitutes"] == [
        {
            "player_id": "100002",
            "name": "Demo Bench Player",
            "shirt_number": "21",
            "position": None,
            "formation_slot": None,
            "goals": None,
            "assists": None,
            "yellow_cards": None,
            "red_cards": None,
            "minute_on": None,
            "minute_off": None,
        }
    ]


def test_convert_lineup_handles_missing_players_and_keeps_zero_distinct():
    converted = convert_lineup(
        {
            "team_id": "239",
            "starting_xi": [
                {"player_id": None, "goals": 0, "assists": None},
                None,
            ],
        }
    )

    assert converted["formation"] is None
    assert converted["starting_players"] == [
        {
            "player_id": None,
            "name": None,
            "shirt_number": None,
            "position": None,
            "formation_slot": None,
            "goals": 0,
            "assists": None,
            "yellow_cards": None,
            "red_cards": None,
            "minute_on": None,
            "minute_off": None,
        }
    ]
    assert converted["substitutes_used"] == []
    assert converted["unused_substitutes"] == []


def test_convert_lineup_rejects_non_dictionary_input():
    with pytest.raises(ValueError, match="api_lineup"):
        convert_lineup([])
