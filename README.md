# Serie A Match Statistics Tracker

A local FastAPI and SQLite application for official Serie A fixtures, standings,
available match statistics, player lineups, player performance and events.
The existing dark-navy interface reads saved records without consuming API quota.

## Current supplied data

The supplied 2026?27 database contains **380 official fixtures**, **110 unique
completed results**, and **20 standings rows**. Coverage is **2/110** for match
statistics, **1/110** for lineups, **1/110** for player performance and **0/110** for
events. Five Highlightly fixture IDs are saved. Some older provider records are
retained in SQLite, but official league lists and totals exclude them.

The application supports all 20 teams. Advanced averages use only supplied values
and show sample sizes. Missing fields remain absent; missing values are not zeros.
Data availability beyond the supplied records depends on the providers and plan.
This is a working local application with partial data, not a completed league-wide
statistics dataset. See `docs/DELIVERY_STATUS.md` for acceptance and limitations.

## Setup on Windows

Python 3.11 or newer is recommended; final acceptance records the tested version.
Open a terminal in the extracted project folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe main.py
```

Open **http://127.0.0.1:8000**. Stop the server with Ctrl+C. Running `python main.py`
with the selected environment starts the same application. If the port is in use,
change `SERIE_A_PORT` in `.env` and open that port instead. Do not open `index.html`
directly with a file URL. Keep one application process per database during imports.

No API credentials are needed to browse the supplied data. Chart.js and Lucide are
bundled locally with their licenses. Optional web fonts use Google Fonts; the UI
falls back to system fonts if offline.

### PyCharm

Open this folder as a project. In Settings > Project > Python Interpreter choose
`.venv\Scripts\python.exe`. Create a Python run configuration with script
`main.py` and the project folder as the working directory, then Run.

### VS Code

Open this folder, install the Python extension, choose **Python: Select
Interpreter**, and select `.venv\Scripts\python.exe`. Run `python main.py` from
the integrated terminal or use **Run Python File** on `main.py`.

## Provider setup and approval

Copy `.env.example` to `.env` and configure only the providers you intend to use:

- `FOOTBALL_DATA_TOKEN`: official fixture and standings synchronization.
- `X_API_KEY`: Highlightly through RapidAPI, used for match details.
- `BBS_API_KEY`: optional legacy BigBallsData integration.
- `STRIKER_API_KEY`: optional compatibility integration; not used by the website's
  current detail controls.

Do not put credentials in HTML, JavaScript, screenshots or delivery archives.
The running app's API documentation is at `/docs`.

On Home choose **Review missing data**, inspect the proposed matches, categories,
request maximum and last saved quota observation, then explicitly approve one
batch. Events are optional. Match details also have category-specific review
buttons. Every batch requires a new approval. A successful category is saved
independently, and restarts reuse persisted results. API errors stop the batch.
Unavailable categories are retained as unavailable rather than repeatedly fetched.
See `docs/SYNC_WORKFLOW.md` for recovery and endpoint details.

The first pending four-match batch needs at most 11 authenticated requests and
excludes events and fixture lookups. It has **not** been executed. The remaining
RapidAPI quota is unknown locally. Live multi-match import verification and further
league enrichment require explicit authorization and permitted provider access.

## Website features

- Home: genuine completed results, league totals and detail coverage.
- Matches: newest completed results first, team search, rounds and optional future
  fixture filters; every official fixture can open its saved details.
- Match details: supplied possession and shots, final scores, player contributions,
  chronological events, starting XIs and substitutes.
- Team statistics: results, goals, points, advanced averages and charts with gaps
  for missing values and visible sample sizes.
- Player pitch: supplied formations, schematic formation slots, readable clickable
  names, ratings and contribution/card indicators. Unknown formations use a player
  list without inventing pitch positions. Select a starter or substitute for all
  available saved performance metrics.
- League Statistics: official saved football-data.org standings, with a clearly
  labeled local comparison only when no official table is available.
- Saved Matches: persistent selections and outcome summaries.

## Verification and delivery

Tests use isolated SQLite files and mocked providers; they do not need live keys:

```powershell
python -m pytest -q
node --test js/formation-layout.test.cjs
python tools/acceptance_check.py
python tools/build_delivery.py
```

Node is needed only for the optional formation tests. The acceptance checker
launches `python main.py` on a free local port and verifies the supplied snapshot
and major screens in headless Chrome or Edge if installed. It makes no football
provider calls. Results go to `docs/ACCEPTANCE.json`.

The build command creates `delivery/SerieA_Tracker.zip` with an allowlisted source
structure and a consistent SQLite backup. It excludes `.env`, virtual environments,
Git history, IDE settings, caches, screenshots and runtime diagnostics. Keep a
backup of `serie_a.db` before replacing the delivered snapshot with another file.
