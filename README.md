# Serie A Match Statistics Tracker

The approved, responsive frontend is served by a small Python FastAPI application. It has a clearly marked Demo Mode for fictional sample data and a separate Live Data Mode that reads only provider records saved in local SQLite.

## Run on Windows

1. Install Python 3.10 or later if it is not already installed.
2. Open PowerShell in this project folder.
3. Create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   If PowerShell blocks activation, use Command Prompt instead:

   ```bat
   py -m venv .venv
   .venv\Scripts\activate.bat
   ```

4. Install the project dependencies and start the server:

   ```powershell
   python -m pip install -r requirements.txt
   python main.py
   ```

5. Open <http://127.0.0.1:8000> in a browser. Stop the server with **Ctrl+C** in the terminal.

## Run from VS Code

1. Use **File → Open Folder** and choose this project folder.
2. Install the Microsoft Python extension if needed, then select your Python interpreter with **Python: Select Interpreter**. Choose `.venv` after creating it.
3. Open **Terminal → New Terminal** and run the virtual-environment, installation, and startup commands in the Windows instructions above.

## Run from PyCharm

1. Open this existing project folder in PyCharm.
2. Open **Settings → Project → Python Interpreter** and add a local virtual environment at `.venv` if one is not already selected.
3. Open the PyCharm terminal and run `python -m pip install -r requirements.txt`, followed by `python main.py`.
4. Open <http://127.0.0.1:8000> in a browser.

## Run the tests

With the project virtual environment activated, run:

```powershell
python -m pytest -v
```

The tests cover the match endpoints, lineup models and importer, explicit API confirmation, match timeouts, and frontend asset serving. Formation placement has a separate Node.js test.

## Preview features

- Start on the illustrated landing page and choose **Get Started**.
- Use the sidebar to move between the dashboard, matches, team statistics, league statistics, saved matches, and About.
- Search fixtures by either team, filter by season and round, and open a match with **View**.
- Choose **Demo Mode** or **Live Data Mode** on the Dashboard or Matches screen. Live mode reads only the local database; it never silently fills empty data with fictional samples.
- In Live Data Mode, match results are filtered from `GET /api/matches`; **View** loads saved details from `GET /api/matches/{match_id}`. Missing scores and statistics are displayed as unavailable, not zero.
- Import at most three matches only after pressing the import button and confirming the prompt. The application does not fetch at startup. The `list_games` credit estimate is not verified, so check the provider pricing before confirmation. Timeouts are shown without retry.
- If enough matches are already saved for the selected season, the import action reuses them without a provider request. **Refresh saved sample** is a separate, confirmed action for getting updated records.
- Change the selected team and chart metric on Team Statistics.
- Save matches with the bookmark controls and remove them from Saved Matches. Saved selections are temporary and reset when the server page reloads.
- The Events tab shows fictional events in Demo Mode and an honest unavailable message for live records, because `get_game` remains unverified after timeouts. The Lineups tab links to a football-pitch view; saved live lineups are read from SQLite, with a separate confirmation before any lineup API request.

The fonts, Chart.js charts, and Lucide icons are loaded from third-party CDNs, so an internet connection is needed for those resources.

## SQLite database foundation

SQLite is a small database that stores its information in a local file, so this project does not need a separate database server. It is a good fit for a student project that runs on one computer.

The database file is `serie_a.db` in the project folder. When FastAPI starts, it creates the Team, Match, MatchStatistics, MatchLineup, and LineupPlayer tables if they do not already exist. The demo and live records have separate data-source labels. Match-list data can be explicitly mapped into the existing team and match tables, but the application does not contact the football API or import records automatically.

### How normalized match data is saved

The API sends JSON, which Python reads as dictionaries and lists. `convert_match()` in `app/data_converter.py` changes one API match dictionary into a smaller dictionary with consistent names, such as `home_team_name` and `home_score`. The import functions in `app/match_import.py` check those values, convert the ISO date into a Python `datetime`, and save the teams and match in SQLite. They do not make network requests.

Each saved row has a **primary key**, a local number that uniquely identifies that row. A match also has foreign keys to its home and away team rows. A **foreign key** is a link to a row in another table, so the match refers to existing teams instead of copying their names into every match.

For live records, the combination of the data-source label and the API match ID is unique. This prevents importing the same match twice while still allowing a demo record and a live record to have the same external ID. Re-importing an unchanged match skips it; changed match details update the existing row.

A database transaction groups related saves together. If a batch fails partway through, SQLite can roll back the batch so it does not leave only some of the matches or teams saved. `match_import.py` imports match and team rows; the separate lineup importer saves player rows only after a lineup request has been explicitly confirmed.

### Lineup database tables

`MatchLineup` stores one team's formation for one match. It links to both a match and a team using foreign keys. A match can have one lineup for each team, and the database prevents saving a second lineup for the same match and team. The application also checks that the lineup team is actually the home or away team in that match.

`LineupPlayer` stores the players belonging to a lineup, including their name, optional shirt number and position, and whether they started, were used as a substitute, or stayed unused. Player statistics can be `null` when the source did not provide a value; a recorded zero stays `0`. Negative statistics and unsupported player roles are rejected. A known external player ID cannot be repeated within one lineup. SQLite foreign-key checks are enabled on every new database connection.

Keeping lineup and player information in separate tables avoids copying the same match or team details into every player row. Their foreign keys and relationships let the pitch page find a match's teams, formations, and players. `save_api_lineups()` in `app/lineup_import.py` matches provider team IDs to the two live teams on a stored match. It saves both lineups in one transaction, preserves missing values as `null`, and replaces previous player rows safely when the provider data changes. Incomplete responses are rejected instead of overwriting good saved lineups.

### Lineup API and football-pitch screen

- `GET /api/matches/{match_id}/lineups` reads local data only. It never calls StrikerAPI and returns an explanatory message with an empty `lineups` list when nothing is stored.
- The pitch view uses the saved home and away formations and places starters approximately by formation. Substitute roles and recorded goals, assists, and cards stay attached to their saved player records. A missing statistic remains “Not provided.”
- `POST /api/matches/{match_id}/lineups/import` only accepts a stored live match. The pitch screen shows the documented estimate of 5 credits and asks for confirmation before sending the request. A complete saved response is reused without another request. A timeout is reported without retrying.
- If live match records are missing, Dashboard and Matches offer a `list_games` import limited to three matches. Its current credit cost has not been independently verified, so the screen and confirmation prompt warn the user to check provider pricing. The API route also requires `confirmed: true`.
- The pitch screen displays local saved player names, numbers, positions, goals, assists, cards, and substitutes. A null value is displayed as “Not provided,” not as zero.
- `js/formation-layout.js` supports 4-3-3, 4-4-2, 3-5-2, 4-2-3-1, 3-4-1-2, and 3-4-2-1. It distributes players evenly inside formation rows and approximately across pitch depth. Provider formation slots are treated as ordinal slots, not as real pitch coordinates.
- The default pitch demonstration uses clearly labeled fictional sample names and statistics. It does not claim they are authentic match data.

To test the formation placement helper with Node.js, run:

```powershell
node --test js/formation-layout.test.cjs
```

The tests use temporary SQLite files and mocked provider responses; they do not make authenticated API requests. For the API and database tests, use `python -m pytest -v`. To run the formation helper tests, use:

```powershell
node --test js/formation-layout.test.cjs
```

## Read-only match API

A REST API lets one program request information from another using web addresses. A `GET` request asks to read information; it does not add or change a match.

- `GET /api/matches` lists the matches already stored in the database. You can add filters such as `?season=2024%2F2025`, `?source=demo`, or `?team=Inter`. If there are no matching records, it returns an empty list.
- `GET /api/matches/{match_id}` shows one saved match, its teams, and its statistics. Statistics that have not been saved are returned as `null`; an unknown match ID returns `404`.

With the server running, open <http://127.0.0.1:8000/docs> to try the endpoints in the interactive FastAPI documentation. `GET` endpoints only return local database records. The lineup `POST` endpoint retrieves from StrikerAPI only after the user supplies explicit confirmation. The small match-list `POST` endpoint also requires confirmation, limits the request to three games, and warns that its credit price needs to be checked with the provider.

## StrikerAPI client foundation

The Python StrikerAPI client sends JSON `POST` requests to the documented StrikerAPI routes and returns the successful response's `data` object. It does not make requests automatically when the app starts. The pitch screen calls it only when a user explicitly chooses an import and confirms the displayed cost.

To try the client:

1. Create an account at [StrikerAPI](https://strikerapi.com/signup) and copy an API key from your account dashboard.
2. Copy `.env.example` to `.env` in the project folder.
3. Replace the example value with your key:

   ```text
   STRIKER_API_KEY=put_your_key_here
   ```

   The `.env` file is ignored by Git. Never put the key in frontend code, share it, or commit it. The application still starts when no key is configured; only an API request needs one.

StrikerAPI provides a limited number of free credits each month, and API requests use credits. Check the provider's current account plan and documentation before making live requests. Automated tests use mocked responses and do not contact StrikerAPI.

The client supports match lists, match details, lineups, and events for Serie A. To explicitly run a small live match-list check (up to three matches), use:

```powershell
python -m app.smoke_test --live --season 2025
```

The command displays that the match-list credit cost has not been independently verified and requires typing `VERIFY` before sending its one request. Its output is limited to match ID, teams, date, and score when available. Do not proceed unless you intend to use API credits and have checked current provider pricing. The separate `app.verify_match_statistics` script shows its endpoint cost estimate and also requires `VERIFY`.

To run the client tests without internet access or API credits:

```powershell
python -m pytest -v
```

## Match statistics provider

The `get_game` StrikerAPI request has timed out repeatedly, so the app does not keep retrying it. BigBallsData is the documented fallback for match-level possession and shot counts. Its official soccer page lists Serie A and says the free plan covers the current season; it advertises 1,000 requests per day and 100 per minute. Older seasons may require a paid plan. Check its current [pricing](https://bigballsdata.com/pricing), [Serie A coverage](https://bigballsdata.com/serie-a-api), and [rate limits](https://bigballsdata.com/docs/rate-limits) before use.

The implementation follows the provider's [OpenAPI contract](https://bigballsdata.com/openapi.json): it looks up the fixture with `GET /v1/matches?sport=football&league=seriea&date=...&season=...`, then reads stored team stats from `GET /v1/matches/{id}/statistics`. This statistics route is described as free and stored-only. Its response places home and away records in `data.home` and `data.away`; possession is `ball_possession`, total attempts are `total_shots`, and shots on target are `shots_on_target`. The values may be null or unavailable. The provider's canonical match ID comes from its own fixture list; a StrikerAPI ID is never sent as a BigBallsData ID.

To configure the new provider, copy `.env.example` to `.env` and set `BIGBALLSDATA_API_KEY` from the BigBallsData dashboard. Keep that key in the ignored `.env` file only. Do not put it in JavaScript, share it, or commit it. The API key is used only by the Python backend.

On a saved live match's Overview tab, **Import match statistics** asks for confirmation before making up to two BigBallsData requests. The first request matches the season, UTC date, and exact home/away team names; the second uses the canonical provider match ID returned by that lookup. A mismatch or ambiguous fixture is rejected. Successful results are saved in the existing `MatchStatistics` row with their provider name and canonical provider ID. Reopening the match reads SQLite; **Refresh statistics** is a separate, confirmed request. No automatic requests or retries are made. A timeout, plan restriction, or provider response with missing statistics is shown honestly.

The displayed final score remains the saved match-list score. Goal scorers and assists are shown only when they were included in the already-saved StrikerAPI player lineups; the BigBallsData team-stat response does not itself identify those players. If lineup contributions are unavailable, the page says so rather than deriving scorers from the score.

Automated tests use mocked responses and temporary SQLite databases. No provider request is made during tests. A real authenticated response has not yet been verified; it still requires explicit approval and a locally configured key.

## Preview screenshots

- [Landing page](./screenshots/01-landing.png)
- [Dashboard](./screenshots/02-dashboard.png)
- [Match details](./screenshots/03-match-details.png)
- [Matches](./screenshots/04-matches.png)
- [Team statistics](./screenshots/05-team-statistics.png)
- [Saved matches](./screenshots/06-saved-matches.png)

## Demo-data notice

**DEMO DATA — SAMPLE VALUES.** All scores, goals, assists, dates, player names, and team statistics are fictional examples for UI demonstration only. They are not authentic historical results or an official live feed. The geometric tracker mark and illustrated stadium are original assets; this project is not affiliated with a football league or club.
