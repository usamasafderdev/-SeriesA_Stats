# Serie A Match Statistics Tracker

This is a local Python/FastAPI application with a responsive browser interface. It displays provider records saved in SQLite. The production UI does not load fictional fixtures or generated statistics.

## Run on Windows

1. Install Python 3.10 or later.
2. Open PowerShell in this project folder.
3. Create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

4. Install dependencies and start the app:

   ```powershell
   python -m pip install -r requirements.txt
   python main.py
   ```

5. Open <http://127.0.0.1:8000>. Stop the server with **Ctrl+C**.

The same commands work in the PyCharm terminal after selecting the `.venv` interpreter. Do not open `index.html` using `file://`; the pages read the local FastAPI endpoints.

## Configure football-data.org and BigBallsData

The official competition fixture and standings source is football-data.org.
Set its token locally when you have access:

```text
FOOTBALL_DATA_TOKEN=your_token_here
```

The Statistics page uses the saved football-data.org table when synchronized.
The Sync fixtures + standings action makes exactly two bounded requests for the
selected season and does not retry. The response's `resultSet.count` is returned
alongside the actual records returned for coverage checking; the application
does not assume a complete season.

BigBallsData remains the detail-statistics source:

Copy `.env.example` to `.env` and set your own key locally:

```text
BBS_API_KEY=your_key_here
```

`.env` is Git-ignored. The application never prints or returns the key. `BIGBALLSDATA_API_KEY` is accepted only as a backward-compatible fallback. StrikerAPI credentials, when used for lineups, also remain in the local environment.

No provider request is made at application startup or by opening a page. On Dashboard or Matches, choose **Sync current season** or **Refresh latest fixtures** and confirm the prompt to make up to five bounded, paginated authenticated BigBallsData requests. **Refresh saved records** only reloads SQLite. Statistics are imported separately from Match Details after another confirmation. A BBS-linked match uses one statistics request; an older live fixture without its BBS UUID requires an exact date-and-team lookup followed by the statistics request. Requests are bounded, failures are shown, and there are no automatic retries.

The Free-plan documentation describes current-season factual match statistics, but access is subject to the provider account's limits. The app does not promise that every match has every statistic. When a provider omits a field, it stays null and the UI shows **Not available**.

## Verified provider response

Two separately authorized authenticated requests succeeded during integration: one current-season finished-fixture list request and one statistics request for Fiorentina–Juventus (provider match UUID `5a5e7d30-3b82-4965-bede-8cead82536e6`, 8 November 2026, 2–2). The returned match-statistics response contained:

| Team       | Possession | Total shots | Shots on target |
| ---------- | ---------: | ----------: | --------------: |
| Fiorentina |        41% |          22 |               6 |
| Juventus   |        59% |          18 |               6 |

These are values from that real response, not estimates. The provider did not include `team_stats_available` or `withheld` metadata in the statistics response. Availability beyond the populated fields is not assumed. No further authenticated calls are needed for tests.

The verified fixture and statistics have been saved once in the local SQLite database. The retained verification details included the match date but not a kickoff time, so it is stored and shown as date-only rather than assigning a made-up time. Opening or refreshing the application reads this saved record and makes no provider request.

## Screens and interactions

- **Dashboard:** totals derived from saved match rows and a recent-match table.
- **Matches:** filter by season and any provider-supplied round, search both team names, open details, save, and remove.
- **Match Details:** actual score, saved statistics, available player contributions, and lineup data. Last-updated times come from saved provider timestamps. Statistics refresh and lineup import require explicit confirmation.
- **Team Statistics:** calculate wins/draws/losses and goals from saved scores; possession, shots, and shots on target are averaged only where present. Assists are totaled only for matches with complete saved player-assist data. Chart tabs plot actual match values, with gaps for missing data.
- **Statistics:** a comparison of imported finished results, not a claim of full official standings. The current BBS standings response returned no usable rows, so official standings remain unavailable rather than being inferred from local results.
- **Saved Matches:** selections persist in SQLite and the chart uses only saved matches with known scores.
- **About:** explains provider limitations and data provenance.

The Lineups tab and football pitch show locally stored permitted provider lineups when available. The current synchronized BBS fixture set has no stored lineup rows, so the interface reports lineups as unavailable until a safely matched StrikerAPI lineup is explicitly imported. The app does not fabricate formations, player events, or player statistics. A BBS fixture UUID is stored separately from any StrikerAPI integer match ID; the application does not treat the two providers' IDs as interchangeable.

## Provider-neutral detail contract

The provider-neutral converter in `app/provider_detail_converter.py` is a
local transformation only. It does not fetch or save data. A permitted live
provider must supply a stable match ID, oriented home and away teams, match
date, status, and final scores. For detailed statistics it must identify
possession, total shots, and shots on target for each side. For the lineup
screen it must identify each team's formation, starting players, substitutes,
player IDs or names, positions, shirt numbers when available, and player
events such as goals, assists, cards, and substitutions. Missing fields remain
`None`; zero is preserved as zero. Provider IDs must remain separate until an
exact, unambiguous fixture match is proven.

## SQLite and migrations

The local database file is `serie_a.db`. Startup creates missing tables and adds BBS team/match UUIDs, provider rounds, fetch timestamps, and the saved-match table using additive SQLite migrations. Existing match, lineup, and statistics rows are preserved. `Match.api_match_id` remains the StrikerAPI ID, while `Match.bbs_match_id` stores the BBS UUID. Saved matches reference local match rows and removing a saved selection does not delete the fixture.

Fixture imports reuse an existing exact local match when its season, UTC date, and home/away team names identify one unique row. Conflicting scores or ambiguous matches are rejected. Statistics are matched by the stored BBS UUID whenever possible. Older records use the stricter date, season, oriented-team, and score checks before any statistics are attached.

The current-season Sync action requests up to five BBS pages, with up to 200
fixtures per page, stops at the provider's short page or a repeated page, and
deduplicates provider fixture IDs before saving. Scheduled, live, and finished
fixtures are retained; detailed statistics and lineups remain on-demand.

## Tests

Run the Python tests with:

```powershell
python -m pytest -v
```

The automated provider tests use mocked responses. They do not send authenticated requests. The formation helper also has a Node.js test; run it with:

```powershell
node js\formation-layout.test.cjs
```

Chart.js and Lucide are loaded from CDNs, so those visual assets require internet access; the local application and SQLite database run on the computer.
