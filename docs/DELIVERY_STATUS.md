# Delivery status

**Local application and clean delivery package: ready for review.**
**Complete league-wide detailed dataset and new live import acceptance: pending
provider authorization and availability.** This is not a claim that all 110
matches now have detailed data.

## Actual supplied coverage

| Category | Saved coverage |
| --- | ---: |
| Official season fixtures | 380 |
| Unique official completed results | 110 |
| Official standings rows / teams | 20 |
| Verified saved Highlightly match IDs | 5 |
| Detailed match statistics | 2 / 110 |
| Both starting lineups | 1 / 110 |
| At least some individual player performance | 1 / 110 |
| Chronological events | 0 / 110 |

All verified pre-existing records remain preserved. Fiorentina–Juventus has
possession, total shots, shots on target, two lineups and 44 saved players including
substitutes. Inter–Como has possession 43%–57% and shots on target 4–1; total shots
were not supplied and are hidden. The other three identified fixtures still need
detailed categories. Advanced possession and shots averages are calculated from
only the matches supplying that metric, with visible sample counts.

## Completed work

- Shared canonical team matching covers all 20 supplied official clubs, prefixes,
  suffixes, aliases and trailing founding years. Fixture matching validates
  identity and nested final scores and rejects ambiguous or conflicting records.
- A read-only planner identifies missing categories and reads local quota
  metadata. Every visible import control uses an inline, bounded batch approval.
- Successful raw responses and each normalized category commit independently.
  A persistent request ledger counts attempts, prevents silent retries after
  interruptions, caches unavailable categories, and supports restarting.
- League/date fixture lookups use league ID 115669, save matched provider IDs for
  all matching official fixtures from one response, and resume across dates.
- Statistics, lineups, box scores and optional events use the same controlled
  workflow. Systemic/API/quota errors stop the batch without losing earlier data.
- Unknown player metrics remain null. Nested supplied box-score metrics preserve
  valid zeros and do not erase existing fields. Events retain stoppage minutes,
  provider event IDs and provenance.
- Home and team figures use completed official results independently of match
  filters. Legacy duplicates remain stored but are excluded from league totals.
  Standings show the saved official table; fallback GD is actual goal difference.
- All major pages have working local navigation and truthful empty states.
  Upcoming fixtures are optional, advanced metrics have sample sizes, and empty
  optional charts are hidden.
- Pitch layouts support supplied formations, schematic positions, readable
  clickable starters and substitutes, ratings, goals, assists and card indicators.
  Player selection exposes every saved performance metric. Unknown formations
  use a player list without inventing a formation.
- Chart.js and Lucide are bundled locally with license files. The approved
  dark-navy styling is preserved. No native alert/confirm/prompt dialogs are used.
- Dependencies, blank provider configuration, PyCharm/VS Code setup and an
  allowlisted ZIP builder are included. No Git commits or pushes were made.

## Verification

The full Python run executed 262 tests: 261 passed and one existing assertion
expected an invented StrikerAPI provenance label for rows with no saved source.
That expectation was corrected to `saved_lineups`, and the affected test passed
in a targeted rerun. No production code changed for that test correction.
All 262 Python tests have therefore passed against the resulting implementation;
the full suite was not rerun unnecessarily. Three JavaScript formation tests pass.

`docs/ACCEPTANCE.json` records successful launch through `python main.py` on Python
3.14.3, SQLite integrity and foreign-key checks, all 110 completed match-detail
routes, all 20 teams reconciled with standings, and browser checks at desktop and
an actual 390px mobile viewport. Browser checks cover home, matches, upcoming
filter, statistics, team charts, saved, about, both real starting XIs, substitutes,
player selection, saved metrics, request review and cancellation. No browser
script errors were recorded. Real saved Inter–Como, Genoa–Milan and
Fiorentina–Juventus screens were inspected.

**Authenticated football-provider requests consumed during this work: 0.**
Historical account usage before the installed request ledger is unknown; it is
not represented as zero remaining usage or as a free-plan quota guarantee.

## Pending external work and request proposal

No local quota record or saved usable rate-limit headers currently establish
remaining RapidAPI quota. No authenticated request was made to investigate it.
The next proposed batch is:

| Match | New categories | Maximum calls |
| --- | --- | ---: |
| Inter–Como | Lineups, box score | 2 |
| Genoa–Milan | Statistics, lineups, box score | 3 |
| Napoli–Lazio | Statistics, lineups, box score | 3 |
| Monza–Atalanta | Statistics, lineups, box score | 3 |
| Total | No fixture lookups or events | 11 |

This proposal has not been executed. Authorization is still required. A smaller
remaining quota must reduce this budget. Process sequentially and stop on systemic
errors. Further matchdays and event imports need fresh batch authorization.
Matchdays 1–11 still have incomplete categories. The exact number of future
requests depends on availability and shared date lookups and cannot be promised.

New genuine multi-match provider imports cannot be called verified until an
authorized batch has actually run. Free access may omit fields or deny categories;
the application handles those limitations but cannot create missing provider data.
Client redistribution/retention must remain within the configured providers'
permitted access. Optional Google Fonts need internet; system fonts are a fallback.
