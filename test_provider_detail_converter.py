from app.provider_detail_converter import convert_match_detail, find_unambiguous_fixture


def summary_fixture():
    return {
        "header": {
            "season": {"displayName": "2026-2027 Italian Serie A"},
            "competitions": [
                {
                    "date": "2026-11-08T11:30Z",
                    "status": {"type": {"description": "Full Time"}},
                    "competitors": [
                        {
                            "homeAway": "home",
                            "score": "1",
                            "team": {"id": "114", "displayName": "Napoli"},
                        },
                        {
                            "homeAway": "away",
                            "score": "1",
                            "team": {"id": "112", "displayName": "Lazio"},
                        },
                    ],
                }
            ],
        },
        "boxscore": {
            "teams": [
                {
                    "homeAway": "home",
                    "statistics": [
                        {"name": "possessionPct", "value": 49},
                        {"name": "totalShots", "value": 15},
                        {"name": "shotsOnTarget", "value": 6},
                    ],
                },
                {
                    "homeAway": "away",
                    "statistics": [
                        {"name": "possessionPct", "value": 51},
                        {"name": "totalShots", "value": 0},
                    ],
                },
            ]
        },
        "rosters": [
            {
                "homeAway": "home",
                "team": {"id": "114", "displayName": "Napoli"},
                "formation": "3-4-2-1",
                "roster": [
                    {
                        "starter": True,
                        "jersey": "9",
                        "formationPlace": "1",
                        "athlete": {"id": "1", "displayName": "Starter"},
                        "position": {"name": "Forward"},
                        "stats": [
                            {"name": "totalGoals", "value": 0},
                            {"name": "goalAssists", "value": 1},
                        ],
                        "plays": [{"didScore": True}],
                        "subbedIn": False,
                        "subbedOut": False,
                    },
                    {
                        "starter": False,
                        "jersey": "20",
                        "athlete": {"id": "2", "displayName": "Substitute"},
                        "position": {"name": "Midfielder"},
                        "subbedIn": {"clock": {"displayValue": "75'"}},
                        "subbedOut": False,
                        "stats": [],
                    },
                ],
            },
            {
                "homeAway": "away",
                "team": {"id": "112", "displayName": "Lazio"},
                "formation": "4-3-3",
                "roster": [],
            },
        ],
    }


def test_espn_detail_converts_fixture_statistics_and_lineups():
    result = convert_match_detail(summary_fixture(), "espn", "401874810")

    assert result["fixture"]["provider_match_id"] == "401874810"
    assert result["fixture"]["home_team_id"] == "114"
    assert result["statistics"]["home_possession"] == 49
    assert result["statistics"]["away_shots"] == 0
    assert result["statistics"]["away_shots_on_target"] is None
    assert result["lineups"][0]["formation"] == "3-4-2-1"
    assert result["lineups"][0]["starting_players"][0]["assists"] == 1
    assert result["lineups"][0]["starting_players"][0]["goals"] == 0
    assert result["lineups"][0]["substitutes_used"][0]["minute_on"] == 75


def test_fixture_matching_rejects_ambiguous_provider_records():
    candidates = [
        {
            "home_team_name": "Napoli",
            "away_team_name": "Lazio",
            "match_date": "2026-11-08",
            "provider_match_id": "one",
        },
        {
            "home_team_name": "Napoli",
            "away_team_name": "Lazio",
            "match_date": "2026-11-08",
            "provider_match_id": "two",
        },
    ]

    try:
        find_unambiguous_fixture(candidates, "Napoli", "Lazio", "2026-11-08")
    except ValueError as error:
        assert "ambiguous" in str(error)
    else:
        raise AssertionError("Ambiguous fixtures must be rejected.")
