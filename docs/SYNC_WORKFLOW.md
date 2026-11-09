# Controlled synchronization

Opening screens reads SQLite. It never refreshes a football provider automatically.
The supported website uses football-data.org for official fixtures and standings,
Highlightly for match details, and preserves previously saved BigBallsData data.
Highlightly's configured Serie A league ID is `115669`.

## Review and approve a batch

On Home, choose the match count and maximum request budget. Events are optional and
off by default. Click **Review missing data**. The application inspects saved
categories and locally recorded quota headers before showing a single inline
approval. No authenticated request is made by this review. Check the RapidAPI
dashboard when quota is unknown or the saved observation might be out of date.

Approval applies to one batch. A later batch requires a fresh approval. Statistics,
lineups, box scores and optionally events are processed sequentially. A request is
counted before sending; its raw successful response is saved in SQLite before
normalization, and each category commits separately. The application stops on API,
quota, database or systemic validation errors. Explicit provider HTTP 404s and
empty supported categories are recorded as unavailable and skipped on later runs.
No missing metric is converted to zero.

## Resume and diagnose

Restart with `python main.py`, review another batch and approve it. Provider match
IDs, responses, unavailable categories, completion state and request attempts all
persist in SQLite. One date lookup is reused to match every official completed
fixture on that date, including fixtures outside the current detail batch.
League/date/season/team/score checks reject ambiguous identities.

`highlightly_requests` records category states. `pending` after an interruption
means that the outcome of an earlier request is uncertain. `error` means a provider
call failed. Neither is silently retried. A successful cached response can be
processed again after correcting a parser without another request.

After resolving the cause, an explicitly approved maintenance call may use
`retry_failed: true` to retry failed/interrupted calls within a new request budget.
This must not be used as an automatic retry loop. Do not run multiple application
processes against the same SQLite file during synchronization.

## Endpoints

`POST /api/highlightly/plan` is read-only and needs no confirmation. Example:

```json
{
  "season": 2026,
  "max_matches": 4,
  "max_requests": 11,
  "categories": ["statistics", "lineups", "box-score"],
  "allow_fixture_lookup": false,
  "match_ids": [384, 382, 381, 383]
}
```

These IDs describe the supplied snapshot only. Normal application operation chooses
fixtures from SQLite and is not tied to these matches. The four-match proposal
uses at most 11 new requests: Inter–Como 2, Genoa–Milan 3, Napoli–Lazio 3,
Monza–Atalanta 3. Inter–Como statistics and all existing Fiorentina–Juventus data
are preserved. No fixture lookup or events request belongs to this proposal.

Only after authorization, send the reviewed body with `confirmed: true` to
`POST /api/highlightly/sync`. It returns actual request attempts, effective budget,
category outcomes, stop reason and coverage. The backend reduces a budget against
usable locally observed request quota. Quota metadata is an observation, not a
guarantee that another client has not consumed requests.

The saved response/request ledgers support approved date-by-date continuation for
all completed matchdays. An unavailable fixture or category never becomes invented
data. A cached box score received before lineups is retained for later application.
