"""Offline checks of bounded imports and restart behavior; no provider calls."""
from datetime import datetime

import pytest

import main
from app import models
from app.database import create_database_engine, create_database_session, initialize_database
from app.highlightly_api import HighlightlyError
from app.match_service import add_match, add_team


@pytest.fixture
def database(tmp_path):
    engine = create_database_engine(tmp_path / "sync.db")
    initialize_database(engine)
    with create_database_session(engine) as session:
        for index, names in enumerate((("Inter", "Como"), ("Genoa", "Milan"))):
            home, away = [add_team(session, name, data_source="live") for name in names]
            match = add_match(session, "2026", datetime(2026, 11, 8, 14 + index),
                home.id, away.id, 2, 0, "finished", data_source="live")
            match.football_data_match_id = str(index + 1)
            match.highlightly_match_id = str(100 + index)
        session.commit()
    yield engine
    engine.dispose()


class Provider:
    def __init__(self):
        self.calls = []
        self.fail_lineups = False

    def get_statistics(self, identity):
        self.calls.append(("statistics", identity))
        return [{"possession": 43, "shotsOnTarget": 4},
                {"possession": 57, "shotsOnTarget": 1}]

    def get_lineups(self, identity):
        self.calls.append(("lineups", identity))
        if self.fail_lineups:
            raise HighlightlyError("Highlightly returned HTTP 429.")
        names = ("Inter", "Como") if identity == 100 else ("Genoa", "Milan")
        return [{"team": {"name": name, "id": side + 1}, "formation": "4-4-2",
                 "initialLineup": [{"id": side * 20 + n, "name": f"Player {side}-{n}"}
                                   for n in range(1, 12)]}
                for side, name in enumerate(names)]

    def get_box_score(self, identity):
        self.calls.append(("box-score", identity))
        return {"players": [{"id": 1, "rating": 7.2, "minutesPlayed": 90,
                             "statistics": {"goals": 0}}]}


def run(engine, **kwargs):
    with create_database_session(engine) as session:
        return main.sync_highlightly_details(main.HighlightlySyncRequest(
            season=2026, max_matches=2, confirmed=True, **kwargs), session)


def test_saved_statistics_skipped_and_batch_resumes_after_restart(database, monkeypatch):
    provider = Provider()
    monkeypatch.setattr(main, "HighlightlyClient", lambda: provider)
    with create_database_session(database) as session:
        match = session.query(models.Match).filter_by(highlightly_match_id="100").one()
        match.statistics = models.MatchStatistics(home_possession=43, source="highlightly")
        session.commit()
    first = run(database, max_requests=2, allow_fixture_lookup=False)
    assert first["requests_used"] == 2
    assert provider.calls == [("statistics", 101), ("lineups", 101)]
    # New sessions read durable category state; no events or fixture lookups exist on this fake.
    second = run(database, max_requests=5, allow_fixture_lookup=False)
    assert first["requests_used"] + second["requests_used"] == 5
    assert len(provider.calls) == len(set(provider.calls))
    assert second["coverage"]["detailed_statistics"] == 2
    assert second["coverage"]["lineups"] == 2
    assert second["coverage"]["player_performance"] == 2


def test_quota_error_stops_batch_and_preserves_statistics(database, monkeypatch):
    provider = Provider()
    provider.fail_lineups = True
    monkeypatch.setattr(main, "HighlightlyClient", lambda: provider)
    result = run(database, max_requests=6, allow_fixture_lookup=False)
    assert result["requests_used"] == 2
    assert "429" in result["stopped_reason"]
    with create_database_session(database) as session:
        assert session.query(models.MatchStatistics).count() == 1
        assert session.query(models.HighlightlyResponse).count() == 1
        assert sum(row.requests_used for row in session.query(models.MatchDetailSync)) == 2
    provider.fail_lineups = False
    blocked = run(database, max_requests=6, allow_fixture_lookup=False)
    assert blocked["requests_used"] == 0
    run(database, max_requests=6, allow_fixture_lookup=False, retry_failed=True)
    assert provider.calls.count(("statistics", 101)) == 1


def test_later_category_error_preserves_lineups_and_can_retry_explicitly(database, monkeypatch):
    provider = Provider()
    def denied(identity):
        provider.calls.append(("box-score", identity))
        raise HighlightlyError("Plan access denied", 403)
    provider.get_box_score = denied
    monkeypatch.setattr(main, "HighlightlyClient", lambda: provider)
    result = run(database, max_requests=6, allow_fixture_lookup=False)
    assert result["requests_used"] == 3
    assert result["coverage"]["lineups"] == 1
    with create_database_session(database) as session:
        assert session.query(models.HighlightlyResponse).count() == 2
        assert session.query(models.LineupPlayer).count() == 22
    provider.get_box_score = Provider.get_box_score.__get__(provider)
    result = run(database, max_requests=1, allow_fixture_lookup=False, retry_failed=True)
    assert result["requests_used"] == 1
    assert result["coverage"]["player_performance"] == 1
    assert provider.calls.count(("lineups", 101)) == 1


def test_unavailable_categories_are_not_requested_again(database, monkeypatch):
    provider = Provider()
    provider.get_statistics = lambda identity: provider.calls.append(("statistics", identity)) or []
    provider.get_lineups = lambda identity: provider.calls.append(("lineups", identity)) or []
    provider.get_box_score = lambda identity: provider.calls.append(("box-score", identity)) or []
    monkeypatch.setattr(main, "HighlightlyClient", lambda: provider)
    assert run(database, max_requests=6)["requests_used"] == 6
    assert run(database, max_requests=6)["requests_used"] == 0
    with create_database_session(database) as session:
        assert session.query(models.HighlightlyRequest).filter_by(status="unavailable").count() == 6


def test_events_save_stoppage_time_independently_and_do_not_refetch(database, monkeypatch):
    provider = Provider()
    def events(identity):
        provider.calls.append(("events", identity))
        return [{"id": "event-1", "type": "Goal", "time": "45+2",
                 "team": {"name": "Genoa" if identity == 101 else "Inter"},
                 "player": {"name": "Scorer"}, "assist": "Assister"}]
    provider.get_events = events
    monkeypatch.setattr(main, "HighlightlyClient", lambda: provider)
    result = run(database, max_requests=2, categories=["events"])
    assert result["requests_used"] == 2
    assert result["coverage"]["events"] == 2
    assert result["coverage"]["lineups"] == 0
    with create_database_session(database) as session:
        event = session.query(models.MatchEvent).first()
        assert (event.minute, event.added_minute, event.source) == (45, 2, "highlightly")
    assert run(database, max_requests=2, categories=["events"])["requests_used"] == 0


def test_reversed_named_statistics_use_canonical_home_away(database, monkeypatch):
    provider = Provider()
    provider.get_statistics = lambda identity: [
        {"team": {"name": "AC Milan"}, "possession": 70},
        {"team": {"name": "Genoa CFC"}, "possession": 30}]
    monkeypatch.setattr(main, "HighlightlyClient", lambda: provider)
    result = run(database, max_requests=1, categories=["statistics"])
    assert not result["stopped_reason"] or "budget" in result["stopped_reason"]
    with create_database_session(database) as session:
        stats = session.query(models.MatchStatistics).one()
        assert (stats.home_possession, stats.away_possession) == (30, 70)


def test_unknown_fixture_date_does_not_stall_all_future_batches(database, monkeypatch):
    provider = Provider()
    provider.get_matches = lambda *args, **kwargs: {"data": []}
    monkeypatch.setattr(main, "HighlightlyClient", lambda: provider)
    with create_database_session(database) as session:
        for match in session.query(models.Match):
            match.highlightly_match_id = None
        session.commit()
    assert run(database, max_requests=2)["requests_used"] == 1
    assert run(database, max_requests=2)["requests_used"] == 0


def test_one_date_lookup_saves_all_matching_ids(database, monkeypatch):
    provider = Provider()
    def fixtures(date, **params):
        provider.calls.append(("fixtures", date))
        assert params["league_id"] == 115669
        return {"data": [
            {"id": 100, "homeTeam": {"name": "Inter"}, "awayTeam": {"name": "Como"}},
            {"id": 101, "homeTeam": {"name": "Genoa"}, "awayTeam": {"name": "Milan"}},
        ]}
    provider.get_matches = fixtures
    monkeypatch.setattr(main, "HighlightlyClient", lambda: provider)
    with create_database_session(database) as session:
        for match in session.query(models.Match):
            match.highlightly_match_id = None
        session.commit()
    assert run(database, max_requests=1)["requests_used"] == 1
    with create_database_session(database) as session:
        assert session.query(models.Match).filter(models.Match.highlightly_match_id.is_not(None)).count() == 2
    run(database, max_requests=6)
    assert sum(category == "fixtures" for category, _ in provider.calls) == 1
