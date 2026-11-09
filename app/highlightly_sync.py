"""Bounded, category-by-category synchronization using the existing adapters."""
from datetime import datetime, timezone
from threading import Lock

from sqlalchemy.exc import SQLAlchemyError

from app import models
from app.highlightly_api import HIGHLIGHTLY_SERIE_A_LEAGUE_ID, HighlightlyError, local_quota
from app.highlightly_import import (
    convert_highlightly_lineups, has_player_performance, merge_highlightly_box_score,
    save_highlightly_lineups,
)
from app.match_service import save_or_update_match_statistics
from app.team_names import same_team

SYNC_LOCK = Lock()
CATEGORIES = ("statistics", "lineups", "box-score", "events")


class BudgetExhausted(Exception):
    pass


def completed_matches(session, season):
    return session.query(models.Match).filter(
        models.Match.data_source == "live",
        models.Match.football_data_match_id.is_not(None),
        models.Match.season == str(season), models.Match.status.ilike("finished"),
    ).order_by(models.Match.match_date.desc(), models.Match.id).all()


def lineups_complete(match):
    return len(match.lineups) == 2 and all(
        sum(player.player_role == "starter" for player in lineup.players) == 11
        for lineup in match.lineups)


def statistics_present(match):
    stats = match.statistics
    return stats is not None and any(getattr(stats, side + field) is not None
        for side in ("home_", "away_") for field in ("possession", "shots", "shots_on_target"))


def category_complete(match, category):
    if category == "statistics":
        return statistics_present(match)
    if category == "lineups":
        return lineups_complete(match)
    if category == "box-score":
        return has_player_performance(match)
    return bool(match.events)


def category_key(match, category):
    return f"{category}:{match.highlightly_match_id}"


def terminal(session, key):
    ledger = session.get(models.HighlightlyRequest, key)
    return ledger is not None and ledger.status in ("saved", "unavailable")


def needs_category(session, match, category):
    if match.highlightly_match_id and terminal(session, category_key(match, category)):
        return False
    if category == "box-score" and any(lineup.source == "highlightly" for lineup in match.lineups):
        return True
    return not category_complete(match, category)


def sync_plan(session, season, categories=CATEGORIES, match_ids=None, max_matches=4,
              allow_fixture_lookup=True):
    """A read-only budget proposal; it never creates state or calls a provider."""
    matches = completed_matches(session, season)
    if match_ids is not None:
        matches = [match for match in matches if match.id in match_ids]
        matches.sort(key=lambda match: match_ids.index(match.id))
    rows, fixture_dates = [], set()
    for match in matches:
        prior = session.get(models.MatchDetailSync, match.id)
        if not match.highlightly_match_id and prior is not None and prior.status == "unavailable":
            continue
        missing, cached, unavailable, blocked = [], [], [], []
        for category in categories:
            key = category_key(match, category)
            ledger = session.get(models.HighlightlyRequest, key) if match.highlightly_match_id else None
            if ledger is not None and ledger.status == "unavailable":
                unavailable.append(category)
                continue
            if ledger is not None and ledger.status == "saved":
                continue
            if not needs_category(session, match, category):
                continue
            if ledger is not None and ledger.status in ("pending", "error", "validation_error"):
                blocked.append({"category": category, "reason": ledger.last_error or ledger.status})
                continue
            if match.highlightly_match_id and session.get(models.HighlightlyResponse, key) is not None:
                cached.append(category)
            else:
                missing.append(category)
        if not (missing or cached or blocked):
            continue
        if not match.highlightly_match_id and not allow_fixture_lookup:
            blocked.append({"category": "fixtures", "reason": "Saved provider ID required"})
            missing = []
        lookup = False
        if not match.highlightly_match_id and allow_fixture_lookup:
            key = f"fixtures:{season}:{match.match_date.date().isoformat()}"
            lookup = key not in fixture_dates and session.get(models.HighlightlyResponse, key) is None
            fixture_dates.add(key)
        rows.append({"match_id": match.id, "home": match.home_team.name,
                     "away": match.away_team.name, "round": match.round_name,
                     "provider_match_id": match.highlightly_match_id,
                     "request_categories": missing, "cached_categories": cached,
                     "unavailable_categories": unavailable, "blocked_categories": blocked,
                     "fixture_lookup_requests": int(lookup)})
        if len(rows) >= max_matches:
            break
    requests = sum(len(row["request_categories"]) + row["fixture_lookup_requests"] for row in rows)
    quota = local_quota()
    return {"season": season, "matches": rows, "estimated_max_requests": requests,
            "quota": quota, "recommended_budget": min(requests, quota["remaining"])
            if quota["remaining"] is not None else requests,
            "categories": list(categories), "authorization_required": requests > 0}


def _empty(body, category):
    if body is None or body == [] or body == {}:
        return True
    if isinstance(body, dict):
        for name in {"statistics": ("statistics", "data"), "lineups": ("lineups", "data"),
                     "box-score": ("players", "data"), "events": ("events", "data")}[category]:
            if name in body and body[name] == []:
                return True
    return False


def _ordered_statistics(body, match):
    teams = body.get("statistics", body.get("data", [])) if isinstance(body, dict) else body
    if not isinstance(teams, list):
        raise ValueError("Malformed statistics response.")
    named = [item for item in teams if isinstance(item, dict) and isinstance(item.get("team"), dict)
             and item["team"].get("name")]
    if named:
        ordered = [[item for item in named if same_team(item["team"]["name"], name)]
                   for name in (match.home_team.name, match.away_team.name)]
        if any(len(items) != 1 for items in ordered):
            raise ValueError("Statistics teams do not match the stored fixture.")
        return [items[0] for items in ordered]
    return body


def run_sync(session, request, client, fixture_matcher, statistics_parser, event_saver):
    """The caller holds SYNC_LOCK; each call and each category commits separately."""
    matches = completed_matches(session, request.season)
    identities = request.match_ids if request.match_ids is not None else (
        [request.match_id] if request.match_id is not None else None)
    if identities is not None:
        matches = [match for match in matches if match.id in identities]
        matches.sort(key=lambda match: identities.index(match.id))
    quota = local_quota()
    budget = min(request.max_requests, quota["remaining"]) if quota["remaining"] is not None else request.max_requests
    used, processed, stopped, outcomes = 0, 0, None, []

    def response(key, fetch, sync):
        nonlocal used
        cached = session.get(models.HighlightlyResponse, key)
        if cached is not None:
            return cached.payload
        ledger = session.get(models.HighlightlyRequest, key)
        if ledger is not None:
            if ledger.status == "unavailable":
                return None
            if not request.retry_failed:
                raise HighlightlyError("An earlier request failed or was interrupted; review its saved status before explicitly retrying.")
        if used >= budget:
            raise BudgetExhausted
        current_quota = local_quota()
        if current_quota["remaining"] == 0:
            raise BudgetExhausted
        if getattr(client, "is_configured", True) is False:
            raise HighlightlyError("Set X_API_KEY in the local .env file.")
        if ledger is None:
            ledger = models.HighlightlyRequest(cache_key=key, attempts=0)
            session.add(ledger)
        ledger.status = "pending"
        ledger.attempts += 1
        ledger.updated_at = datetime.now(timezone.utc)
        sync.requests_used += 1
        session.commit()
        used += 1
        try:
            body = fetch()
        except HighlightlyError as error:
            ledger.status = "unavailable" if error.status_code == 404 else "error"
            ledger.last_error = str(error)[:300]
            session.commit()
            if error.status_code == 404:
                return None
            raise
        session.add(models.HighlightlyResponse(cache_key=key, payload=body,
                    fetched_at=datetime.now(timezone.utc)))
        ledger.status = "received"
        session.commit()
        return body

    for match in matches:
        if processed >= request.max_matches:
            break
        prior = session.get(models.MatchDetailSync, match.id)
        if (not match.highlightly_match_id and prior is not None
                and prior.status == "unavailable" and not request.retry_failed):
            continue
        # Saved, complete and explicitly unavailable categories need no new call.
        def needs(category):
            key = category_key(match, category)
            if match.highlightly_match_id and terminal(session, key):
                return False
            if category == "box-score" and match.highlightly_match_id:
                # A cached box score is still applied even when lineups contain ratings.
                if session.get(models.HighlightlyResponse, key) is not None:
                    return True
            return needs_category(session, match, category)
        if not any(needs(category) for category in request.categories):
            continue
        sync = session.get(models.MatchDetailSync, match.id)
        if sync is None:
            sync = models.MatchDetailSync(match_id=match.id)
            session.add(sync)
        sync.status, sync.last_error = "in_progress", None
        sync.updated_at = datetime.now(timezone.utc)
        session.commit()
        key = None
        try:
            if not match.highlightly_match_id:
                if not request.allow_fixture_lookup:
                    raise ValueError("Fixture lookup disabled; a saved Highlightly ID is required.")
                date = match.match_date.date().isoformat()
                key = f"fixtures:{request.season}:{date}"
                lookup = response(key, lambda: client.get_matches(date,
                    league_id=HIGHLIGHTLY_SERIE_A_LEAGUE_ID, season=request.season), sync)
                # Match the whole date, even when this batch imports only one fixture.
                for candidate in completed_matches(session, request.season):
                    if candidate.match_date.date() == match.match_date.date() and not candidate.highlightly_match_id:
                        identity = fixture_matcher(lookup, candidate)
                        if identity is not None:
                            candidate.highlightly_match_id = identity
                session.commit()
                if not match.highlightly_match_id:
                    sync.status = "unavailable"
                    sync.last_error = "No unique provider fixture in the saved date response."
                    session.commit()
                    processed += 1
                    continue
            sync.provider_match_id = match.highlightly_match_id
            provider_id = int(match.highlightly_match_id)
            for category in request.categories:
                if not needs(category):
                    continue
                key = category_key(match, category)
                fetch = getattr(client, {"statistics": "get_statistics", "lineups": "get_lineups",
                    "box-score": "get_box_score", "events": "get_events"}[category])
                body = response(key, lambda: fetch(provider_id), sync)
                available = False
                if not _empty(body, category):
                    if category == "statistics":
                        values = statistics_parser(_ordered_statistics(body, match))
                        available = any(value is not None for value in values.values())
                        if available:
                            save_or_update_match_statistics(session, match.id,
                                source="highlightly", provider_match_id=str(provider_id), **values)
                            match.statistics.highlightly_match_id = str(provider_id)
                    elif category == "lineups":
                        normalized = convert_highlightly_lineups(body, None,
                            match.home_team.name, match.away_team.name)
                        save_highlightly_lineups(session, match.id, normalized)
                        available = lineups_complete(match)
                    elif category == "box-score":
                        players = [player for lineup in match.lineups for player in lineup.players]
                        available = merge_highlightly_box_score(players, body) > 0
                        if not players:
                            # Retain the response until a later batch supplies lineups.
                            outcomes.append({"match_id": match.id, "category": category, "status": "cached_waiting_for_lineups"})
                            continue
                    else:
                        available = event_saver(session, match, body) > 0
                ledger = session.get(models.HighlightlyRequest, key)
                if ledger is None:
                    ledger = models.HighlightlyRequest(cache_key=key, attempts=0,
                        updated_at=datetime.now(timezone.utc))
                    session.add(ledger)
                ledger.status = "saved" if available else "unavailable"
                ledger.last_error = None if available else "Provider supplied no supported fields for this category."
                session.commit()
                outcomes.append({"match_id": match.id, "category": category, "status": ledger.status})
            sync.statistics_complete = statistics_present(match)
            sync.lineup_complete = lineups_complete(match)
            sync.player_performance_complete = has_player_performance(match)
            sync.events_complete = bool(match.events)
            sync.status = "complete" if all(category_complete(match, category)
                for category in CATEGORIES) else "partial"
            sync.updated_at = datetime.now(timezone.utc)
            session.commit()
            processed += 1
        except BudgetExhausted:
            sync.status = "partial"
            session.commit()
            stopped = "Approved request budget or last observed quota reached."
            break
        except (HighlightlyError, ValueError, TypeError, SQLAlchemyError) as error:
            session.rollback()
            sync = session.get(models.MatchDetailSync, match.id)
            sync.status = "retryable_error"
            # Database exceptions may contain raw parameters; keep those private.
            stopped = "Local database validation failed; batch stopped." if isinstance(error, SQLAlchemyError) else str(error)
            sync.last_error = stopped[:300]
            ledger = session.get(models.HighlightlyRequest, key) if key else None
            if ledger is not None and ledger.status == "received":
                ledger.status, ledger.last_error = "validation_error", stopped[:300]
            session.commit()
            processed += 1
            break
    return {"processed_matches": processed, "requests_used": used,
            "request_budget": request.max_requests, "effective_budget": budget,
            "stopped_reason": stopped, "outcomes": outcomes}
