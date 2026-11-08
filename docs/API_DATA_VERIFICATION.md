# StrikerAPI Data Verification

## Previously verified match list

- Season: `2025` (the provider defines this as the 2025-26 season).
- Filter: `league=seriea`, `status=final`, `limit=3`.
- One authenticated `POST /v1/list_games` returned HTTP 200 and three matches.
- Match `737158` was Torino 2-2 Juventus on `2026-05-24`.
- The match-list response confirmed `data.games[].game_id`, `date`, `status`, `home.name`, `away.name`, and both score fields.

## Controlled match-statistics check

The checker uses the existing `FootballAPI` client for match `737158` only. It is designed to request:

1. `POST /v1/get_game` with `{"game_id":"737158","league":"seriea"}`.
2. `POST /v1/get_lineups` with `{"game_id":"737158","league":"seriea"}`.
3. `POST /v1/get_events` with `{"game_id":"737158","league":"seriea"}`.

Each request has a 30-second response-read timeout. There are no retries. The script requires `--live`, displays an estimated maximum of 20 credits, and requires the user to type `VERIFY` before sending requests.

### Live result

- Explicit live authorization: Yes.
- Estimated maximum displayed before confirmation: 20 credits.
- First operation attempted: `POST /v1/get_game`.
- Result: `FootballAPIReadTimeoutError`; no HTTP status was received.
- Retries: None.
- `get_lineups`: Not called.
- `get_events`: Not called.
- Credits consumed: Unknown. The request timed out, and actual account billing was not checked.
- Match details, team/player statistics, lineups, events, and consistency checks: Unverified.
- No new match records were stored.

## Fields inspected and JSON paths

| Information | JSON path(s) |
|---|---|
| Match and final score | `data.game.game_id`, `data.game.home.score`, `data.game.away.score`, `data.game.status` |
| Home/away team statistics | `data.team_stats[]` matched by `home` and `team_id` |
| Possession | `data.team_stats[].possession_pct` |
| Total shots | `data.team_stats[].shots` |
| Shots on target | `data.team_stats[].shots_on_target` |
| Player goals and assists | `data.players[].goals`, `data.players[].assists` |
| Yellow/red card totals | `data.players[].yellow_cards`, `data.players[].red_cards`; lineup player rows are also checked |
| Goal scorers and assists | `data.events[].player`, `player_id`, `player2`, `player2_id` |
| Event team mapping | `data.events[].team_id` |
| Home and away formations | `data.lineups[]` matched by `team_id`; `data.lineups[].formation` |
| Starting players | `data.lineups[].starting_xi[]` |
| Player name, ID, position, shirt number | `data.lineups[].starting_xi[].name`, `player_id`, `position`, `jersey` |
| Player goals, assists, cards | `data.lineups[].starting_xi[].goals`, `assists`, `yellow_cards`, `red_cards` |
| Used and unused substitutes | `data.lineups[].substitutes_used[]`, `data.lineups[].unused_substitutes[]` |
| Possible pitch coordinates | Coordinates are checked on returned lineup player objects; `formation_place` is not treated as an x/y coordinate |

The checker treats numeric zero as an available value and `null` or absent values as missing. A missing assist is not counted as zero. Scoreless matches do not establish that the event or player-stat endpoints support a field.

## Consistency checks

- Match score from `get_game` is compared with the score nested in the lineup response when provided.
- `team_stats[].home` and `team_id` are used to associate statistics with teams.
- Goal events are counted by `team_id` and compared with the final score, excluding shootout events.
- Event player and assist IDs are checked against the returned lineup players; event team IDs are checked against the match teams.
- Red-card zero totals are distinct from missing red-card fields.

The API may omit statistics. Any absent field will remain marked missing or unverified; no values are fabricated. The public documentation lists the relevant operations as credit-consuming. The displayed 20-credit figure is a conservative estimate; actual billing must be checked in the provider account.

## Independent endpoint verification (Milestone 6D)

The verification command now supports selecting an operation independently:

```text
python -m app.verify_match_statistics --live --endpoint game
python -m app.verify_match_statistics --live --endpoint lineups
python -m app.verify_match_statistics --live --endpoint events
python -m app.verify_match_statistics --live --endpoint all
```

Each command requires typing `VERIFY` after the estimate is displayed. Without
`--live`, the script makes no request. A single endpoint selection makes at
most one request to that endpoint; `all` makes at most one request to each
endpoint and stops at the first error. No retries or match-list requests are
performed. Each request has a 10-second connect timeout and a 30-second
response-read timeout by default. `--read-timeout` can set a positive read
timeout up to 60 seconds.

| Endpoint | Documented estimate | Actual authenticated result |
|---|---:|---|
| `game` (`POST /v1/get_game`) | 5 credits | Prior requests timed out while reading; see Milestone 6F. Match details and statistics remain unverified. |
| `lineups` (`POST /v1/get_lineups`) | 5 credits | Verified in Milestone 6E: HTTP 200 in 7.28 seconds. |
| `events` (`POST /v1/get_events`) | 10 credits | Not called live; event fields remain unverified. |
| `all` | Up to 20 credits | Not run in Milestone 6D. |

Credit estimates are taken from the provider's published endpoint documentation;
actual account billing is not confirmed. These values are estimates, not a
guarantee of account charges.

### Field interpretation and paths

The script reports the response fields without saving API records. In
`game`, team statistics are associated with `data.team_stats[]` using the
documented home flag or team IDs from `data.game.home.team_id` and
`data.game.away.team_id`. It separately reports:

- Score and match state: `data.game.game_id`,
  `data.game.home.score`, `data.game.away.score`, and `data.game.status`.
- Possession, shots, and shots on target:
  `data.team_stats[].possession_pct`, `data.team_stats[].shots`, and
  `data.team_stats[].shots_on_target`.
- Player goals, assists, and card totals: `data.players[].goals`,
  `data.players[].assists`, `data.players[].yellow_cards`, and
  `data.players[].red_cards`.
- Lineup and player details: `data.lineups[].formation`,
  `data.lineups[].starting_xi[]`, `data.lineups[].substitutes_used[]`, and
  `data.lineups[].unused_substitutes[]`; lineup player objects are checked for
  `name`, `player_id`, `position`, `jersey`, goals, assists, and cards.
- Lineup substitutions and formation placement: lineup player objects may
  contain `formation_place`, `minute_on`, and `minute_off`. The documentation
  example uses `formation_place` as an ordinal formation slot, not as pitch
  x/y coordinates; actual pitch coordinates are not inferred from it.
- Event details: `data.events[]` and its `type`, `player`, `player_id`,
  `player2`, `player2_id`, and `team_id` fields.

An omitted or null numeric field is reported as missing; a returned zero is
reported as available with zero recorded. A returned empty `events` array
indicates that no event of the requested type was present in that response.
An absent or non-list `events` field remains missing. This does not prove that
the provider supports every statistic for every match.

No authenticated requests were made while implementing or testing Milestone
6D. At that time, only the earlier `list_games` response was confirmed live
data; the later Milestone 6E lineup check is recorded below.

## Live lineup verification (Milestone 6E)

- Test date: 2026-11-08.
- Match: `737158`, Torino vs Juventus.
- Request: one authenticated `POST /v1/get_lineups` with `game_id=737158` and
  `league=seriea`, using the existing `FootballAPI` client.
- Result: HTTP 200; elapsed time 7.28 seconds.
- Request count: exactly one. No retries, `get_game`, or `get_events` calls.
- Estimated cost: 5 credits. Actual account billing was not available to
  verify.

### Returned fields

The response identified the teams and returned both formations:

- Home: Torino, `3-4-1-2`; `data.game.home.name` and
  `data.lineups[].formation`.
- Away: Juventus, `3-4-2-1`; `data.game.away.name` and
  `data.lineups[].formation`.
- Both sides returned 11 starting players. For all 22 starters,
  `name`, `player_id`, `position`, `jersey`, `formation_place`, `minute_on`,
  `goals`, `assists`, `yellow_cards`, and `red_cards` were populated at
  `data.lineups[].starting_xi[]`.
- `minute_on` was 0 for all starters. `minute_off` was non-null for 5 of 11
  starters on each side, at `data.lineups[].starting_xi[].minute_off`.
- Each side returned 5 used substitutes. Their `name`, `player_id`, `jersey`,
  `minute_on`, `goals`, `assists`, `yellow_cards`, and `red_cards` were
  populated at `data.lineups[].substitutes_used[]`. Substitutes' `position`,
  `formation_place`, and `minute_off` were null in this response.
- Torino had 9 unused substitutes and Juventus had 8. Their `name`,
  `player_id`, and `jersey` were populated at
  `data.lineups[].unused_substitutes[]`; position, minutes, and player stats
  were not populated.
- Numeric zero values were returned for some goals, assists, and cards and are
  valid recorded zeros. For unused substitutes, those statistics were absent,
  not zero. Red-card fields were returned as zero for starters and used
  substitutes in both lineups.

`formation_place` contained the integer slots 1 through 11 for each starting
XI. The public example also presents this as a placement field, but the
response does not define a pitch-coordinate mapping. No x/y coordinates were
returned (`coordinates_available: false`). Therefore, this endpoint is enough
to display team names, formations, player lists, identities, roles, shirt
numbers, and lineup statistics. It is not by itself enough to draw accurate
player locations on a pitch: do not treat `formation_place` as x/y coordinates.

### Limitations after this request

`get_lineups` is now verified for this match. The result does not verify that
lineup fields are populated for every match. `get_game` previously timed out,
and `get_events` has not been tested live. The lineup response contains useful
player goal/assist/card totals, but unused-substitute stats were missing and
the lineup endpoint alone does not establish full event detail or pitch
coordinates. No match data was written to SQLite.

## Final match-statistics verification (Milestone 6F)

- Test date: 2026-11-08.
- Match: `737158`, Serie A (`league=seriea`).
- Official endpoint documentation: `POST /v1/get_game`; request fields are
  `game_id` and `league`. The existing client sends
  `{"game_id":"737158","league":"seriea"}` to
  `https://mcp.strikerapi.com/v1/get_game`, using `x-api-key` authentication.
- Explicit authorization: Yes. Exactly one authenticated request was made.
  `list_games`, `get_lineups`, and `get_events` were not called, and no retry
  was attempted.
- Timeout settings: 10-second connect timeout and 60-second response-read
  timeout.
- Result: `FootballAPIReadTimeoutError`; no HTTP status was received. The
  script measured 65.65 seconds elapsed overall.
- Estimated endpoint cost: 5 credits. Actual account billing is unknown; a
  timeout does not establish whether the provider charged for the request.

The official `get_game` response example documents these locations:

| Information | JSON path(s) |
|---|---|
| Match ID and final score/status | `data.game.game_id`, `data.game.home.score`, `data.game.away.score`, `data.game.status` |
| Home/away possession | `data.team_stats[].possession_pct`, associated with `home` or `team_id` |
| Total shots and shots on target | `data.team_stats[].shots`, `data.team_stats[].shots_on_target` |
| Player goals and assists | `data.players[].goals`, `data.players[].assists` |
| Player yellow/red cards | `data.players[].yellow_cards`, `data.players[].red_cards` |
| Goal scorers, assists, and event minutes | `data.key_events[]` fields `type`, `minute`, `added_minute`, `player`, `player_id`, `player2`, `player2_id`, and `team_id` |

These are documented response paths, not verified values for match `737158`.
Because the request timed out before an HTTP response, the match score,
possession, shots, player goals, assists, cards, and key goal events/minutes
from `get_game` remain unverified. Missing values cannot be distinguished from
recorded zeros without an actual response. Previously verified lineup
statistics remain documented in the Milestone 6E section above.

The request was not retried and the timeout was not extended further. The
recommended next action is to contact StrikerAPI support with the endpoint,
match ID, approximate UTC request time, and timeout outcome, or evaluate an
alternative data provider before implementing the full live-statistics
integration. Do not treat the documented schema or fictional preview data as
verified match statistics.

## Response-delivery diagnosis (Milestone 6G)

No authenticated StrikerAPI requests were made during this investigation.

### Findings

- The existing request matches the reviewed `get_game` REST operation:
  `POST https://mcp.strikerapi.com/v1/get_game`, JSON body
  `{"game_id":"737158","league":"seriea"}`, and `x-api-key` authentication.
  The published endpoint page describes the match box score, player lines,
  key events, and response fields. No Python-SDK-specific transport behavior
  was identified in the endpoint documentation reviewed.
- Runtime HTTPX is 0.28.1. The previous top-level `httpx.post()` call used
  HTTPX's buffered request behavior: it reads the response body before
  returning. Its `ReadTimeout` therefore did not establish whether the client
  was waiting for response headers or for a body chunk.
- The client now uses `httpx.Client.send(..., stream=True)` to receive headers
  first, then reads the response body separately. A read timeout during
  `send()` is reported as `FootballAPIResponseHeaderTimeoutError`; one during
  `response.read()` is `FootballAPIResponseBodyTimeoutError`. A premature
  connection close while reading the body is
  `FootballAPIIncompleteResponseError`. Status and negotiated HTTP version
  are retained once headers arrive.
- HTTPX settings are explicit and preserve its previous safe defaults:
  certificate verification on, environment proxy trust on, HTTP/1.1 enabled,
  HTTP/2 disabled. HTTPX 0.28.1 defaults to those settings. No HTTP proxy
  environment variables were configured at inspection time, and Windows
  WinHTTP reported direct access (no proxy). This does not inspect every
  possible network appliance between this machine and the provider.
- The previous top-level HTTPX call created a short-lived client for each call,
  so it did not reuse connections between separate API calls. The new client
  is also scoped to a single call; connection reuse is not the reason for the
  new phase-specific error reporting. No HTTP/2 experiment was run.
- No SSL verification was disabled and no credential values were printed.

### Interpreting provider dashboard records

The project owner reports that the StrikerAPI dashboard shows several
`get_game` HTTP 200 entries with sub-second provider-reported latency. The
dashboard request IDs and timestamps were not available to match them to the
local timed-out attempts. These records therefore cannot be assumed to be the
same requests. A server-side success/processing latency also does not by
itself prove that the complete response reached and was decoded by this HTTPX
client.

The Milestone 6F timeout was measured as 65.65 seconds overall with a 60-second
read timeout, but because it used the buffered call, it cannot be classified
as a header wait versus a stalled body. The new mocked tests verify that future
header waits, body stalls, and incomplete response bodies are reported
separately. No new live data was obtained, so the real failure phase and
root-cause remain unverified.

### Suggested support request

> We are calling `POST /v1/get_game` for Serie A match `737158` with the
> documented JSON fields `game_id` and `league`, using HTTPX 0.28.1 over
> verified TLS and HTTP/1.1. The client previously timed out after a 60-second
> read timeout without receiving an HTTP status. Our dashboard shows several
> successful HTTP 200 `get_game` entries with sub-second provider-reported
> latency, but we cannot confirm those entries correspond to these same
> request attempts. Could you check whether the response for this match is
> unusually large or whether any response-body delivery issue is known? If
> possible, please provide a request ID/timestamp correlation method and
> confirm the expected response content length or transfer encoding. We have
> not retried during this investigation.

## Data normalization preparation (Milestone 7A)

`app.data_converter` converts one match-list record and one team lineup record
into dictionaries with stable field names. Match teams are read from nested
`home` and `away` objects. Lineups are normalized per team; call the converter
once for each entry in `data.lineups[]`. It keeps used and unused substitutes
in separate lists.

Missing fields become `None`, and returned numeric zeros remain `0`. External
IDs retain the API's original values. Match dates remain the provider's ISO
date string. The converter does not access SQLite or make API requests.
Before persisting, an integration step still needs to map normalized names to
the database model's field names and types (including converting the ISO date
to `datetime`). The current database schema has no player or lineup tables,
so player data is not ready for direct persistence without a separately
approved schema change.
