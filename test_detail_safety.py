"""Regression checks for fixture identity, provider fields and quota metadata."""
from datetime import datetime, timezone
from types import SimpleNamespace
import json

import pytest

from app import models
from app.highlightly_import import convert_highlightly_lineups, merge_highlightly_box_score
from app.highlightly_api import local_quota
from app.team_names import same_team
from main import _find_highlightly_fixture, _save_highlightly_events


@pytest.mark.parametrize("official,provider", [
    ("AS Roma", "Roma"), ("Atalanta BC", "Atalanta"), ("Bologna FC 1909", "Bologna"),
    ("Cagliari Calcio", "Cagliari"), ("Genoa CFC", "Genoa"),
    ("FC Internazionale Milano", "Inter Milan"), ("Juventus FC", "Juventus"),
    ("SS Lazio", "Lazio"), ("Parma Calcio 1913", "Parma"), ("SSC Napoli", "Napoli"),
    ("Udinese Calcio", "Udinese"), ("Venezia FC", "Venezia"),
    ("Frosinone Calcio", "Frosinone"), ("US Sassuolo Calcio", "Sassuolo"),
    ("Torino FC", "Torino"), ("US Lecce", "Lecce"), ("AC Monza", "Monza"),
    ("Como 1907", "Como"), ("AC Milan", "Milan"), ("ACF Fiorentina", "Fiorentina"),
])
def test_official_twenty_team_aliases(official, provider):
    assert same_team(official, provider)
    assert not same_team(official, "Different Club")


def test_nested_box_metrics_preserve_zero_and_unsupplied_saved_values():
    player = SimpleNamespace(api_player_id="1", rating=8, minutes_played=90,
        goals=1, assists=2, shots_total=5, yellow_cards=1)
    result = merge_highlightly_box_score([player], {"players": [{"id": 1,
        "statistics": {"rating": 0, "goals": 0, "passesAccuracy": "84%"}}]})
    assert result == 1
    assert (player.rating, player.goals, player.minutes_played, player.assists) == (0, 0, 90, 2)
    assert player.passes_accuracy == 84


def test_lineups_can_be_reordered_without_mutating_provider_response():
    body = [{"team": {"id": 2, "name": "Como"}, "initialLineup": [{"id": 2, "name": "Away"}]},
            {"team": {"id": 1, "name": "Inter"}, "initialLineup": [{"id": 1, "name": "Home"}]}]
    result = convert_highlightly_lineups(body, None, "Inter Milan", "Como 1907")
    assert result[0]["team_name"] == "Inter"
    assert "formationPlace" not in body[0]["initialLineup"][0]


def test_nested_fixture_score_mismatch_is_rejected():
    match = SimpleNamespace(season="2026", match_date=datetime(2026, 11, 8), home_score=2,
        away_score=0, home_team=SimpleNamespace(name="Inter"), away_team=SimpleNamespace(name="Como"))
    body = [{"id": 123, "homeTeam": {"name": "Inter"}, "awayTeam": {"name": "Como"},
             "state": {"score": {"current": "0 - 2"}}}]
    assert _find_highlightly_fixture(body, match) is None


def test_invalid_event_does_not_clear_saved_events():
    old = models.MatchEvent(minute=2, event_type="Goal", source="highlightly")
    match = SimpleNamespace(home_team=SimpleNamespace(name="Inter"),
                            away_team=SimpleNamespace(name="Como"), events=[old])
    with pytest.raises(ValueError):
        _save_highlightly_events(None, match, [{"type": "Goal", "team": {"name": "Another team"}}])
    assert match.events == [old]


def test_quota_unknown_and_last_observed_metadata_are_local(tmp_path, monkeypatch):
    monkeypatch.setattr("app.highlightly_api.DIAGNOSTIC_FOLDER", tmp_path)
    assert local_quota()["remaining"] is None
    (tmp_path / "quota.json").write_text(json.dumps({
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "headers": {"x-ratelimit-requests-remaining": "7", "x-ratelimit-requests-reset": "3600"},
    }))
    assert local_quota()["remaining"] == 7
