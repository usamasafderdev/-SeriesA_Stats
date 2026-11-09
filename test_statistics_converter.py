from datetime import datetime, timezone

import pytest

from app.statistics_converter import (
    convert_match_statistics,
    convert_provider_match,
    find_matching_provider_fixture,
    season_start_year,
)


PROVIDER_FIXTURE = {
    "id": "bbe0db21-9e62-4cb0-a65c-b1dc7781aa66",
    "sport": "football",
    "league": "Serie A",
    "kickoff_utc": "2026-10-25T18:45:00Z",
    "status": "finished",
    "home": {"id": "provider-home", "name": "Inter"},
    "away": {"id": "provider-away", "name": "Juventus"},
    "score": {"home": 0, "away": 0},
}


def matching_fixture(**changes):
    return {**PROVIDER_FIXTURE, **changes}


def test_provider_match_conversion_keeps_canonical_id_and_zero_score():
    converted = convert_provider_match(PROVIDER_FIXTURE)

    assert converted["provider_match_id"] == PROVIDER_FIXTURE["id"]
    assert converted["home_team_name"] == "Inter"
    assert converted["away_team_name"] == "Juventus"
    assert converted["home_score"] == 0
    assert converted["away_score"] == 0
    assert converted["match_date"] == datetime(
        2026, 10, 25, 18, 45, tzinfo=timezone.utc
    )
    assert converted["round_name"] is None


def test_provider_round_is_saved_as_display_text():
    assert convert_provider_match(matching_fixture(round=12))["round_name"] == "12"
    assert (
        convert_provider_match(matching_fixture(round="Round 12"))["round_name"]
        == "Round 12"
    )


@pytest.mark.parametrize("round_value", [True, [], "x" * 81])
def test_provider_round_rejects_invalid_values(round_value):
    with pytest.raises(ValueError, match="round"):
        convert_provider_match(matching_fixture(round=round_value))


def test_date_only_provider_fixture_does_not_claim_a_kickoff_time():
    converted = convert_provider_match(
        matching_fixture(kickoff_utc="2026-11-08")
    )

    assert converted["match_date"] == datetime(
        2026, 11, 8, tzinfo=timezone.utc
    )
    assert converted["kickoff_time_available"] is False


def test_match_lookup_requires_exact_date_and_oriented_team_names():
    selected = find_matching_provider_fixture(
        [PROVIDER_FIXTURE],
        "2026/2027",
        datetime(2026, 10, 25, 18, 45),
        "Inter",
        "Juventus",
        0,
        0,
    )

    assert selected["provider_match_id"] == PROVIDER_FIXTURE["id"]


@pytest.mark.parametrize(
    ("home_name", "away_name"),
    [("Juventus", "Inter"), ("Inter", "AC Milan")],
)
def test_match_lookup_rejects_wrong_team_pair_or_home_away_order(
    home_name,
    away_name,
):
    with pytest.raises(ValueError, match="No BigBallsData fixture"):
        find_matching_provider_fixture(
            [PROVIDER_FIXTURE],
            "2026",
            datetime(2026, 10, 25),
            home_name,
            away_name,
            0,
            0,
        )


def test_match_lookup_rejects_ambiguous_matches():
    with pytest.raises(ValueError, match="More than one"):
        find_matching_provider_fixture(
            [PROVIDER_FIXTURE, PROVIDER_FIXTURE],
            "2026",
            datetime(2026, 10, 25),
            "Inter",
            "Juventus",
            0,
            0,
        )


def test_match_lookup_rejects_score_conflict_and_unfinished_fixtures():
    with pytest.raises(ValueError, match="scores disagree"):
        find_matching_provider_fixture(
            [PROVIDER_FIXTURE],
            "2026",
            datetime(2026, 10, 25),
            "Inter",
            "Juventus",
            1,
            0,
        )

    with pytest.raises(ValueError, match="finished match"):
        find_matching_provider_fixture(
            [matching_fixture(status="scheduled")],
            "2026",
            datetime(2026, 10, 25),
            "Inter",
            "Juventus",
            0,
            0,
        )


def test_match_lookup_rejects_wrong_date_or_league():
    with pytest.raises(ValueError, match="No BigBallsData fixture"):
        find_matching_provider_fixture(
            [matching_fixture(kickoff_utc="2026-10-26T18:45:00Z")],
            "2026",
            datetime(2026, 10, 25),
            "Inter",
            "Juventus",
            0,
            0,
        )

    with pytest.raises(ValueError, match="No BigBallsData fixture"):
        find_matching_provider_fixture(
            [matching_fixture(league="Premier League")],
            "2026",
            datetime(2026, 10, 25),
            "Inter",
            "Juventus",
            0,
            0,
        )


def test_statistics_conversion_maps_home_and_away_and_keeps_zero():
    response = {
        "data": {
            "home": {
                "team_id": "provider-home",
                "team_name": "Inter",
                "ball_possession": 0,
                "total_shots": 0,
                "shots_on_target": 0,
            },
            "away": {
                "team_id": "provider-away",
                "team_name": "Juventus",
                "ball_possession": 100,
                "total_shots": 12,
                "shots_on_target": 4,
            },
        },
        "meta": {"available": True},
    }

    converted = convert_match_statistics(
        response,
        convert_provider_match(PROVIDER_FIXTURE),
    )

    assert converted["home_possession"] == 0
    assert converted["home_shots"] == 0
    assert converted["home_shots_on_target"] == 0
    assert converted["away_possession"] == 100
    assert converted["away_shots"] == 12
    assert converted["away_shots_on_target"] == 4
    assert converted["available"] is True


def test_statistics_conversion_preserves_missing_fields_as_null():
    response = {
        "data": {
            "home": {"team_id": "provider-home", "team_name": "Inter"},
            "away": None,
        },
        "meta": {"available": True},
    }

    converted = convert_match_statistics(
        response,
        convert_provider_match(PROVIDER_FIXTURE),
    )

    assert converted["home_possession"] is None
    assert converted["home_shots"] is None
    assert converted["away_possession"] is None
    assert converted["away_shots"] is None
    assert converted["available"] is False


def test_statistics_metadata_can_mark_present_fields_unavailable():
    response = {
        "data": {
            "home": {
                "team_id": "provider-home",
                "team_name": "Inter",
                "ball_possession": 55,
                "total_shots": 10,
                "shots_on_target": 4,
            },
            "away": None,
        },
        "meta": {"available": False},
    }

    converted = convert_match_statistics(
        response,
        convert_provider_match(PROVIDER_FIXTURE),
    )

    assert converted["home_possession"] is None
    assert converted["home_shots"] is None
    assert converted["home_shots_on_target"] is None
    assert converted["available"] is False


def test_statistics_conversion_rejects_team_mismatch_and_invalid_values():
    wrong_team = {
        "data": {
            "home": {"team_id": "another-team", "team_name": "Inter"},
            "away": None,
        }
    }
    with pytest.raises(ValueError, match="different team ID"):
        convert_match_statistics(
            wrong_team,
            convert_provider_match(PROVIDER_FIXTURE),
        )

    bad_shots = {
        "data": {
            "home": {
                "team_id": "provider-home",
                "total_shots": -1,
            },
            "away": None,
        }
    }
    with pytest.raises(ValueError, match="non-negative"):
        convert_match_statistics(
            bad_shots,
            convert_provider_match(PROVIDER_FIXTURE),
        )


@pytest.mark.parametrize(
    "possession",
    [-0.1, 100.1, True, "50"],
)
def test_statistics_conversion_rejects_invalid_possession(possession):
    response = {
        "data": {
            "home": {
                "team_id": "provider-home",
                "ball_possession": possession,
            },
            "away": None,
        }
    }

    with pytest.raises(ValueError, match="between 0 and 100"):
        convert_match_statistics(
            response,
            convert_provider_match(PROVIDER_FIXTURE),
        )


def test_season_filter_uses_start_year():
    assert season_start_year("2026/2027") == 2026
    assert season_start_year("2026") == 2026
    with pytest.raises(ValueError, match="four-digit year"):
        season_start_year("unknown")
