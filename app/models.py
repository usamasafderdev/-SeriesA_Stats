from sqlalchemy import (
    CheckConstraint,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Session, declarative_base, relationship


Base = declarative_base()


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (
        UniqueConstraint("data_source", "name", name="uq_team_source_name"),
        UniqueConstraint(
            "data_source",
            "api_team_id",
            name="uq_team_source_api_id",
        ),
        CheckConstraint(
            "data_source IN ('demo', 'live')",
            name="ck_team_data_source",
        ),
    )

    id = Column(Integer, primary_key=True)
    api_team_id = Column(Integer, nullable=True)
    bbs_team_id = Column(String(100), nullable=True)
    football_data_team_id = Column(String(100), nullable=True)
    name = Column(String(100), nullable=False)
    logo_url = Column(String(500), nullable=True)
    data_source = Column(String(20), nullable=False, default="demo")

    home_matches = relationship(
        "Match",
        foreign_keys="Match.home_team_id",
        back_populates="home_team",
    )
    away_matches = relationship(
        "Match",
        foreign_keys="Match.away_team_id",
        back_populates="away_team",
    )
    lineups = relationship("MatchLineup", back_populates="team")


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        UniqueConstraint(
            "data_source",
            "api_match_id",
            name="uq_match_source_api_id",
        ),
        CheckConstraint(
            "data_source IN ('demo', 'live')",
            name="ck_match_data_source",
        ),
    )

    id = Column(Integer, primary_key=True)
    api_match_id = Column(Integer, nullable=True)
    bbs_match_id = Column(String(100), nullable=True)
    football_data_match_id = Column(String(100), nullable=True)
    highlightly_match_id = Column(String(100), nullable=True)
    season = Column(String(20), nullable=False)
    round_name = Column(String(80), nullable=True)
    match_date = Column(DateTime, nullable=False)
    kickoff_time_available = Column(Boolean, nullable=False, default=True)
    home_team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    away_team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    home_score = Column(Integer, nullable=True)
    away_score = Column(Integer, nullable=True)
    status = Column(String(30), nullable=False, default="scheduled")
    data_source = Column(String(20), nullable=False, default="demo")
    fetched_at = Column(DateTime, nullable=True)

    home_team = relationship(
        "Team",
        foreign_keys=[home_team_id],
        back_populates="home_matches",
    )
    away_team = relationship(
        "Team",
        foreign_keys=[away_team_id],
        back_populates="away_matches",
    )
    statistics = relationship(
        "MatchStatistics",
        back_populates="match",
        uselist=False,
        cascade="all, delete-orphan",
    )
    lineups = relationship(
        "MatchLineup",
        back_populates="match",
        cascade="all, delete-orphan",
    )
    events = relationship(
        "MatchEvent",
        cascade="all, delete-orphan",
        order_by="MatchEvent.id",
    )


class MatchStatistics(Base):
    __tablename__ = "match_statistics"

    id = Column(Integer, primary_key=True)
    match_id = Column(
        Integer,
        ForeignKey("matches.id"),
        nullable=False,
        unique=True,
    )
    home_possession = Column(Float, nullable=True)
    away_possession = Column(Float, nullable=True)
    home_shots = Column(Integer, nullable=True)
    away_shots = Column(Integer, nullable=True)
    home_shots_on_target = Column(Integer, nullable=True)
    away_shots_on_target = Column(Integer, nullable=True)
    source = Column(String(40), nullable=False, default="unknown")
    provider_match_id = Column(String(100), nullable=True)
    fetched_at = Column(DateTime, nullable=True)
    highlightly_match_id = Column(String(100), nullable=True)

    match = relationship("Match", back_populates="statistics")


class SavedMatch(Base):
    __tablename__ = "saved_matches"

    id = Column(Integer, primary_key=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False, unique=True)
    saved_at = Column(DateTime, nullable=False)

    match = relationship("Match")


class LeagueStanding(Base):
    __tablename__ = "league_standings"
    __table_args__ = (
        UniqueConstraint("source", "season", "team_id", name="uq_standing_team"),
    )

    id = Column(Integer, primary_key=True)
    season = Column(String(20), nullable=False)
    source = Column(String(40), nullable=False)
    position = Column(Integer, nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    played = Column(Integer, nullable=False)
    wins = Column(Integer, nullable=False)
    draws = Column(Integer, nullable=False)
    losses = Column(Integer, nullable=False)
    goals_for = Column(Integer, nullable=False)
    goals_against = Column(Integer, nullable=False)
    goal_difference = Column(Integer, nullable=False)
    points = Column(Integer, nullable=False)
    team = relationship("Team")


class MatchEvent(Base):
    __tablename__ = "match_events"
    id = Column(Integer, primary_key=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    provider_event_id = Column(String(100), nullable=True)
    minute = Column(Integer, nullable=True)
    event_type = Column(String(40), nullable=False)
    team_name = Column(String(100), nullable=True)
    player_name = Column(String(100), nullable=True)
    assist_name = Column(String(100), nullable=True)
    detail = Column(String(200), nullable=True)


class MatchLineup(Base):
    __tablename__ = "match_lineups"
    __table_args__ = (
        UniqueConstraint(
            "match_id",
            "team_id",
            name="uq_lineup_match_team",
        ),
    )

    id = Column(Integer, primary_key=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    formation = Column(String(20), nullable=True)

    match = relationship("Match", back_populates="lineups")
    team = relationship("Team", back_populates="lineups")
    players = relationship(
        "LineupPlayer",
        back_populates="lineup",
        cascade="all, delete-orphan",
    )


class LineupPlayer(Base):
    __tablename__ = "lineup_players"
    __table_args__ = (
        UniqueConstraint(
            "lineup_id",
            "api_player_id",
            name="uq_lineup_player_api_id",
        ),
        CheckConstraint(
            "player_role IN ('starter', 'used_substitute', 'unused_substitute')",
            name="ck_lineup_player_role",
        ),
        CheckConstraint(
            "shirt_number IS NULL OR shirt_number >= 0",
            name="ck_lineup_player_shirt_number_non_negative",
        ),
        CheckConstraint(
            "formation_slot IS NULL OR formation_slot >= 0",
            name="ck_lineup_player_formation_slot_non_negative",
        ),
        CheckConstraint(
            "minute_on IS NULL OR minute_on >= 0",
            name="ck_lineup_player_minute_on_non_negative",
        ),
        CheckConstraint(
            "minute_off IS NULL OR minute_off >= 0",
            name="ck_lineup_player_minute_off_non_negative",
        ),
        CheckConstraint(
            "goals IS NULL OR goals >= 0",
            name="ck_lineup_player_goals_non_negative",
        ),
        CheckConstraint(
            "assists IS NULL OR assists >= 0",
            name="ck_lineup_player_assists_non_negative",
        ),
        CheckConstraint(
            "yellow_cards IS NULL OR yellow_cards >= 0",
            name="ck_lineup_player_yellow_cards_non_negative",
        ),
        CheckConstraint(
            "red_cards IS NULL OR red_cards >= 0",
            name="ck_lineup_player_red_cards_non_negative",
        ),
    )

    id = Column(Integer, primary_key=True)
    lineup_id = Column(
        Integer,
        ForeignKey("match_lineups.id"),
        nullable=False,
    )
    api_player_id = Column(String(30), nullable=True)
    player_name = Column(String(100), nullable=False)
    shirt_number = Column(Integer, nullable=True)
    position = Column(String(50), nullable=True)
    formation_slot = Column(Integer, nullable=True)
    player_role = Column(String(30), nullable=False)
    minute_on = Column(Integer, nullable=True)
    minute_off = Column(Integer, nullable=True)
    goals = Column(Integer, nullable=True)
    assists = Column(Integer, nullable=True)
    yellow_cards = Column(Integer, nullable=True)
    red_cards = Column(Integer, nullable=True)
    rating = Column(Float, nullable=True)
    minutes_played = Column(Integer, nullable=True)
    shots_total = Column(Integer, nullable=True)
    shots_on_target = Column(Integer, nullable=True)
    shots_off_target = Column(Integer, nullable=True)
    passes_total = Column(Integer, nullable=True)
    passes_successful = Column(Integer, nullable=True)
    passes_accuracy = Column(Float, nullable=True)
    passes_key = Column(Integer, nullable=True)
    tackles_total = Column(Integer, nullable=True)
    interceptions_total = Column(Integer, nullable=True)
    dribbles_total = Column(Integer, nullable=True)
    dribbles_successful = Column(Integer, nullable=True)
    duels_total = Column(Integer, nullable=True)
    duels_won = Column(Integer, nullable=True)
    fouls_committed = Column(Integer, nullable=True)
    fouls_drawn = Column(Integer, nullable=True)
    goalkeeper_saves = Column(Integer, nullable=True)

    lineup = relationship("MatchLineup", back_populates="players")


@event.listens_for(Session, "before_flush")
def _validate_lineup_relationships(
    session: Session,
    _flush_context: object,
    _instances: object,
) -> None:
    """Check that lineups use match teams and players have a lineup."""
    for lineup in session.new.union(session.dirty):
        if not isinstance(lineup, MatchLineup):
            continue

        match = lineup.match
        if match is None and lineup.match_id is not None:
            match = session.get(Match, lineup.match_id)
        team = lineup.team
        if team is None and lineup.team_id is not None:
            team = session.get(Team, lineup.team_id)

        if match is None or team is None:
            raise ValueError("A lineup must reference an existing match and team.")
        if match.home_team is not team and match.away_team is not team:
            raise ValueError("The lineup team must be one of the match teams.")

    for player in session.new.union(session.dirty):
        if not isinstance(player, LineupPlayer):
            continue
        lineup = player.lineup
        if lineup is None and player.lineup_id is not None:
            lineup = session.get(MatchLineup, player.lineup_id)
        if lineup is None:
            raise ValueError("A lineup player must reference an existing lineup.")
