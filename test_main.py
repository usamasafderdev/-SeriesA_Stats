from pathlib import Path
from datetime import datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from main import _find_highlightly_fixture, _highlightly_statistics, app


client = TestClient(app)
PROJECT_FOLDER = Path(__file__).resolve().parent


def test_home_page_returns_original_html():
    response = client.get("/")
    original_html = (PROJECT_FOLDER / "index.html").read_bytes()

    assert response.status_code == 200
    assert response.content == original_html


def test_health_endpoint_returns_expected_message():
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "application": "Serie A Tracker",
    }


def test_frontend_static_files_are_available():
    file_paths = [
        "/css/style.css",
        "/js/app.js",
        "/js/formation-layout.js",
        "/assets/logo.svg",
        "/assets/stadium.jpg",
    ]

    for file_path in file_paths:
        response = client.get(file_path)

        assert response.status_code == 200, file_path
        assert response.content, file_path


def test_highlightly_fixture_matching_requires_verified_identity():
    match = SimpleNamespace(
        season="2026",
        match_date=datetime(2026, 11, 8, 19, 45),
        home_score=2,
        away_score=0,
        home_team=SimpleNamespace(name="Inter Milan"),
        away_team=SimpleNamespace(name="Como 1907"),
    )
    body = {
        "data": [
            {
                "id": 1319213325,
                "date": "2026-11-08T17:00:00.000Z",
                "homeTeam": {"name": "Inter"},
                "awayTeam": {"name": "Como"},
                "state": {"score": {"current": "2 - 0"}},
                "country": {"code": "IT"},
                "league": {"id": 115669, "season": 2026},
            },
            {
                "id": 999,
                "date": "2026-11-08T17:00:00.000Z",
                "homeTeam": {"name": "Como"},
                "awayTeam": {"name": "Inter"},
                "state": {"score": {"current": "0 - 2"}},
                "country": {"code": "IT"},
                "league": {"id": 115669, "season": 2026},
            },
        ]
    }
    assert _find_highlightly_fixture(body, match) == "1319213325"


def test_highlightly_documented_statistics_array_is_normalized():
    body = [
        {
            "team": {"id": 430539, "name": "Inter"},
            "statistics": [
                {"displayName": "Ball possession", "value": 0.61},
                {"displayName": "Total shots", "value": 18},
                {"displayName": "Shots on target", "value": 7},
            ],
        },
        {
            "team": {"id": 762429, "name": "Como"},
            "statistics": [
                {"displayName": "Ball Possession", "value": 0.39},
                {"displayName": "Total Shots", "value": 4},
                {"displayName": "Shots On Target", "value": 1},
            ],
        },
    ]
    assert _highlightly_statistics(body) == {
        "home_possession": 61,
        "away_possession": 39,
        "home_shots": 18,
        "away_shots": 4,
        "home_shots_on_target": 7,
        "away_shots_on_target": 1,
    }


def test_highlightly_statistics_preserve_zero_values():
    body = [
        {"statistics": [{"displayName": "Total shots", "value": 0}]},
        {"statistics": [{"displayName": "Total shots", "value": 0}]},
    ]
    result = _highlightly_statistics(body)
    assert result["home_shots"] == 0
    assert result["away_shots"] == 0
