from datetime import datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.data_converter import convert_match
from app.database import (
    create_database_engine,
    create_database_session,
    initialize_database,
)
from app.match_import import save_api_match, save_api_matches
from app.match_service import add_match, add_team, list_matches
from app.models import Match, Team


@pytest.fixture
def import_session(tmp_path):
    database_path = tmp_path / "import_test.db"
    database_engine = create_database_engine(database_path)
    initialize_database(database_engine)
    session = create_database_session(database_engine)
    try:
        yield session
    finally:
        session.close()
        database_engine.dispose()


def api_match(
    match_id="737158",
    home_id="239",
    away_id="268",
    home_name="Torino",
    away_name="Juventus",
    home_score=2,
    away_score=2,
    date="2026-05-24",
):
    return convert_match(
        {
            "game_id": match_id,
            "season": 2025,
            "date": date,
            "status": "final",
            "home": {
                "team_id": home_id,
                "name": home_name,
                "score": home_score,
            },
            "away": {
                "team_id": away_id,
                "name": away_name,
                "score": away_score,
            },
        }
    )


def test_saves_match_teams_and_converts_iso_date(import_session):
    saved_match = save_api_match(import_session, api_match())

    assert saved_match.api_match_id == 737158
    assert saved_match.season == "2025"
    assert saved_match.match_date == datetime(2026, 5, 24)
    assert saved_match.home_team.name == "Torino"
    assert saved_match.away_team.name == "Juventus"
    assert saved_match.home_team.api_team_id == 239
    assert saved_match.away_team.api_team_id == 268
    assert saved_match.data_source == "live"
    assert saved_match.home_score == 2
    assert saved_match.away_score == 2
    assert saved_match.status == "final"


def test_preserves_zero_scores_and_allows_missing_scores(import_session):
    zero_match = save_api_match(
        import_session,
        api_match(match_id="700001", home_score=0, away_score=0),
    )
    missing_match = save_api_match(
        import_session,
        api_match(match_id="700002", home_score=None, away_score=None),
    )

    assert zero_match.home_score == 0
    assert zero_match.away_score == 0
    assert missing_match.home_score is None
    assert missing_match.away_score is None


def test_batch_creates_several_matches(import_session):
    records = [
        api_match(match_id="700101"),
        api_match(
            match_id="700102",
            home_id="301",
            away_id="302",
            home_name="Milan",
            away_name="Inter",
            home_score=1,
            away_score=0,
        ),
    ]

    summary = save_api_matches(import_session, records)

    assert summary == {"created": 2, "updated": 0, "skipped": 0}
    assert len(list_matches(import_session, data_source="live")) == 2
    assert import_session.query(Team).filter_by(data_source="live").count() == 4


def test_repeated_import_skips_unchanged_match(import_session):
    record = api_match()

    first = save_api_matches(import_session, [record])
    second = save_api_matches(import_session, [record])

    assert first == {"created": 1, "updated": 0, "skipped": 0}
    assert second == {"created": 0, "updated": 0, "skipped": 1}
    assert import_session.query(Match).filter_by(data_source="live").count() == 1
    assert import_session.query(Team).filter_by(data_source="live").count() == 2


def test_reimport_updates_existing_match_without_duplicate(import_session):
    save_api_match(import_session, api_match())
    updated_data = api_match(home_score=3, away_score=2, date="2026-05-25")

    summary = save_api_matches(import_session, [updated_data])
    saved_match = (
        import_session.query(Match)
        .filter_by(data_source="live", api_match_id=737158)
        .one()
    )

    assert summary == {"created": 0, "updated": 1, "skipped": 0}
    assert saved_match.home_score == 3
    assert saved_match.away_score == 2
    assert saved_match.match_date == datetime(2026, 5, 25)
    assert import_session.query(Match).filter_by(data_source="live").count() == 1


def test_demo_and_live_teams_and_matches_are_separate(import_session):
    demo_home = add_team(import_session, "Torino", api_team_id=239)
    demo_away = add_team(import_session, "Juventus", api_team_id=268)
    add_match(
        import_session,
        season="2025",
        match_date=datetime(2026, 5, 24),
        home_team_id=demo_home.id,
        away_team_id=demo_away.id,
        home_score=2,
        away_score=2,
        status="final",
        api_match_id=737158,
    )

    live_match = save_api_match(import_session, api_match())

    assert live_match.data_source == "live"
    assert live_match.home_team_id != demo_home.id
    assert live_match.away_team_id != demo_away.id
    assert import_session.query(Match).filter_by(api_match_id=737158).count() == 2
    assert import_session.query(Team).filter_by(name="Torino").count() == 2


def test_rejects_invalid_date_before_writing_records(import_session):
    with pytest.raises(ValueError, match="match_date"):
        save_api_match(import_session, api_match(date="not-a-date"))

    assert import_session.query(Match).count() == 0
    assert import_session.query(Team).count() == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("match_id", None),
        ("home_team_id", None),
        ("away_team_id", None),
    ],
)
def test_rejects_missing_external_ids(import_session, field, value):
    record = api_match()
    record[field] = value

    with pytest.raises(ValueError, match=field):
        save_api_match(import_session, record)

    assert import_session.query(Match).count() == 0
    assert import_session.query(Team).count() == 0


def test_rejects_same_home_and_away_team(import_session):
    with pytest.raises(ValueError, match="different"):
        save_api_match(import_session, api_match(away_id="239"))

    assert import_session.query(Match).count() == 0


def test_batch_database_error_rolls_back_all_matches_and_teams(import_session):
    import_session.execute(
        text(
            """
            CREATE TRIGGER reject_second_import
            BEFORE INSERT ON matches
            WHEN NEW.api_match_id = 700202
            BEGIN
                SELECT RAISE(ABORT, 'test import failure');
            END;
            """
        )
    )
    import_session.commit()
    records = [
        api_match(match_id="700201"),
        api_match(
            match_id="700202",
            home_id="401",
            away_id="402",
            home_name="Napoli",
            away_name="Lazio",
        ),
    ]

    with pytest.raises(IntegrityError):
        save_api_matches(import_session, records)

    assert import_session.query(Match).filter_by(data_source="live").count() == 0
    assert import_session.query(Team).filter_by(data_source="live").count() == 0


def test_import_uses_temporary_database_only(import_session, tmp_path):
    database_path = import_session.get_bind().url.database

    save_api_match(import_session, api_match())

    assert database_path == str((tmp_path / "import_test.db").resolve())
    assert database_path.endswith("import_test.db")
