# Player Evaluation Hub

Search for a hitter and see their Statcast data, traditional stats and a
home-made Contact Quality Score on one page, plus score leaderboards by
position.

Django, with Postgres in Docker (or SQLite when no `DATABASE_URL` is set).

## Run it

With Docker:

```sh
docker compose up -d
docker compose exec web python manage.py refresh_all
```

Without Docker (uses SQLite):

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py refresh_all
.venv/bin/python manage.py runserver
```

Then open http://localhost:8000. `refresh_all` takes about a minute the first
time and a few seconds after that, because every download is kept under
`data/raw/` and reused. Add `--refresh` to download again, or
`--seasons 2026` to limit the Statcast/FanGraphs seasons.

Tests: `python manage.py test hub`

## Data sources

| Source | What it supplies | How it is fetched |
| --- | --- | --- |
| Chadwick register | The id crosswalk: MLBAM, FanGraphs, Baseball-Reference, Retrosheet | `pybaseball.chadwick_register()` |
| Baseball Savant | Season exit velocity, launch angle, hard-hit, sweet-spot, barrel, xBA/xSLG/xwOBA (2015 on) | `pybaseball.statcast_batter_exitvelo_barrels` / `statcast_batter_expected_stats` |
| Lahman | Bio details, batting lines by season, positions | The Lahman R package's data files (see below) |
| FanGraphs | wRC+, WAR, wOBA, BB%, K% | `pybaseball.batting_stats`, or a CSV export (see below) |

**Lahman.** `pybaseball.lahman` downloads from a GitHub repo that has been
deleted, so it fails. The hub reads the same tables from the maintained Lahman
R package (`cdalzell/Lahman`) instead. Lahman is published once a year, so the
season in progress or just finished has Statcast data but no traditional line
until the next release.

**FanGraphs.** FanGraphs currently answers pybaseball's requests with a
Cloudflare block, so `load_fangraphs` reports that and `refresh_all` carries on
without it. To get FanGraphs numbers in, export a season's batting leaderboard
from fangraphs.com ("Export Data") and run:

```sh
python manage.py load_fangraphs --seasons 2026 --csv path/to/export.csv
```

## Matching players across sources

`Player` is keyed on the MLBAM id and carries the other sources' ids
(`hub/matching.py`):

1. Match on an id: MLBAM, then FanGraphs, then Baseball-Reference, then Retrosheet.
2. If no id hits, match on the normalised name (accents, punctuation, case and
   Jr./II suffixes removed), but only when exactly one player with that name
   was active within a year of the season in question.
3. Otherwise the row is not loaded. It is written to `UnmatchedRecord` with the
   reason, so nothing is guessed and nothing disappears silently.

A FanGraphs row matched by name teaches the hub that player's FanGraphs id for
next time.

## Contact Quality Score

Defined in `hub/metrics.py`. For each season, among hitters with 100+ batted
balls, three inputs are converted to z-scores and blended:

| Input | Weight |
| --- | --- |
| Average exit velocity | 40% |
| Hard-hit rate (95+ mph) | 30% |
| Sweet-spot rate (launch angle 8-32 degrees) | 30% |

The blend is rescaled so 100 is average and 15 points is one standard
deviation. Launch angle enters as sweet-spot rate because a raw average launch
angle has no "higher is better" direction.

Leaderboard positions come from Lahman (most games played that season). For a
season Lahman does not cover yet, the hitter's most recent position is used.

## Commands

| Command | Does |
| --- | --- |
| `refresh_all` | Everything below, in order |
| `load_players` | Id crosswalk |
| `load_lahman` | Bio, batting lines, positions |
| `load_statcast` | Savant season data |
| `load_fangraphs` | FanGraphs season data |
| `build_metrics` | Recompute Contact Quality Scores |
