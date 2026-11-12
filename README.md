<p align="center">
  <a href="https://query.farm/vgi/">
    <img src="https://raw.githubusercontent.com/Query-farm/vgi-kalshi/main/docs/vgi-logo.png" alt="Vector Gateway Interface logo" width="320">
  </a>
</p>

<h1 align="center">vgi-nhl</h1>

<p align="center">
  NHL standings, scores, play-by-play, and player statistics as ordinary DuckDB tables.<br>
  A <strong>read-only</strong> <a href="https://query.farm/vgi/">VGI</a> worker, built by <a href="https://query.farm">🚜 Query.Farm</a>
</p>

<p align="center">
  <a href="https://github.com/Query-farm/vgi-nhl/actions/workflows/ci.yml"><img src="https://github.com/Query-farm/vgi-nhl/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT license"></a>
  <img src="https://img.shields.io/badge/python-3.13%2B-3776AB.svg" alt="Python 3.13+">
  <a href="https://query.farm/vgi/"><img src="https://img.shields.io/badge/VGI-read--only-6f42c1.svg" alt="Read-only VGI worker"></a>
</p>

---

`vgi-nhl` fetches data on demand from the NHL's public, keyless web and stats
APIs and reformats the responses as typed Arrow data for Haybarn SQL. It needs
no credentials, and it does not rehost or persist any NHL dataset.

## Quick start

The worker is not published to PyPI. `uvx` runs the tagged release straight from
GitHub and caches it after the first use:

```bash
uvx --from git+https://github.com/Query-farm/vgi-nhl@v0.2.0 vgi-nhl --help
```

Launch Haybarn with the catalog already attached:

```bash
uvx haybarn-cli \
  -cmd "INSTALL vgi FROM community; LOAD vgi; ATTACH 'nhl' (TYPE vgi, LOCATION 'uvx --from git+https://github.com/Query-farm/vgi-nhl@v0.2.0 vgi-nhl');" \
  :memory:
```

Or attach it in an existing Haybarn session:

```sql
INSTALL vgi FROM community;
LOAD vgi;
ATTACH 'nhl' (
  TYPE vgi,
  LOCATION 'uvx --from git+https://github.com/Query-farm/vgi-nhl@v0.2.0 vgi-nhl'
);
```

For source development, run `uv lock --check --no-sources`, then
`uv sync --no-sources` and `uv run --no-sources vgi-nhl`.
The lockfile resolves every dependency from package registries, so you do not
need a sibling checkout.

## Catalog surface

The catalog has eight read-only tables and twenty-one parameterized table
functions:

| Kind | Objects |
| --- | --- |
| Today | `current_standings`, `current_schedule`, `current_scores`, `current_skater_leaders`, `current_goalie_leaders` |
| Reference | `teams`, `franchises`, `standings_seasons` |
| Standings and schedule | `standings()`, `schedule()`, `scores()`, `team_schedule()`, `playoff_bracket()`, `draft_picks()` |
| Season statistics | `skater_stats()`, `skater_realtime_stats()`, `goalie_stats()`, `team_stats()`, `skater_leaders()`, `goalie_leaders()` |
| Players | `roster()`, `player()`, `player_career()`, `player_game_log()`, `player_search()` |
| Game detail | `box_score()`, `box_score_goalies()`, `play_by_play()`, `shift_chart()` |

Each table is backed by a parameterless `all_*` scan, such as
`all_current_standings()`. Query the table rather than the scan.

The NHL identifies things in these ways:

- **Seasons** are 8-digit ids. `20252026` is the 2025-26 season. The
  `standings_seasons` table lists every id since `19171918`. A NULL season
  means the current one.
- **`game_type`** is `2` for the regular season (the default), `3` for the
  playoffs, and `1` for the preseason.
- **Game ids** have 10 digits. `2025020001` is game 1 of the 2025-26 regular
  season. Player ids have 7 digits, for example `8478402`. Use
  `player_search()` to look one up.
- **Team codes** are three letters, such as `TOR`.

Percentages are 0-1 fractions. Time on ice is given twice: as `MM:SS` text and
as integer seconds.

## Usage

### Standings

```sql
-- Today's division tables in the NHL's official tiebreak order
SELECT division_name, division_rank, team_abbrev, points, games_played
FROM nhl.main.current_standings
ORDER BY division_name, division_rank;

-- The final 2023-24 Atlantic Division
SELECT division_rank, team_name, wins, losses, ot_losses, points, clinch_indicator
FROM nhl.main.standings(date := DATE '2024-04-18')
WHERE division_name = 'Atlantic'
ORDER BY division_rank;
```

`standings()` accepts any date back to 1917-18. A season's final standings are
on its `standings_end` date in `standings_seasons`.

### Schedules and scores

```sql
-- Tonight's scoreboard
SELECT away_team_abbrev, away_score, home_team_abbrev, home_score, game_state, period
FROM nhl.main.current_scores;

-- Opening night of 2025-26, with how each game ended
SELECT away_team_abbrev, away_score, home_team_abbrev, home_score, last_period_type
FROM nhl.main.scores(date := DATE '2025-10-07');

-- Toronto's 2025-26 regular-season home results
SELECT game_date, away_team_abbrev, away_score, home_score
FROM nhl.main.team_schedule('TOR', season := 20252026)
WHERE game_type = 2 AND home_team_abbrev = 'TOR'
ORDER BY game_date;
```

`schedule(date := ...)` returns the seven days that start on the given date.
`scores()` returns a single day and adds shots on goal.

### Season statistics and leaders

```sql
-- 2025-26 scoring leaders (traded players list every club in team_abbrevs)
SELECT player_name, team_abbrevs, games_played, goals, assists, points
FROM nhl.main.skater_stats(season := 20252026)
ORDER BY points DESC
LIMIT 10;

-- Save percentage among goalies with 40+ games
SELECT player_name, team_abbrevs, games_played, save_pct, goals_against_average
FROM nhl.main.goalie_stats(season := 20252026)
WHERE games_played >= 40
ORDER BY save_pct DESC;

-- Special teams
SELECT team_name, power_play_pct, penalty_kill_pct
FROM nhl.main.team_stats(season := 20252026)
ORDER BY power_play_pct + penalty_kill_pct DESC;

-- The official leaderboard, in long format
SELECT rank, player_name, team_abbrev, value AS goals
FROM nhl.main.skater_leaders(season := 20252026, category := 'goals', per_category := 5);
```

`skater_realtime_stats()` adds hits, blocked shots, giveaways, takeaways, and
shot-attempt breakdowns.

### Players

```sql
SELECT player_id, player_name, position_code, team_abbrev
FROM nhl.main.player_search('mcdavid');

SELECT season, team_name, games_played, goals, assists, points
FROM nhl.main.player_career(8478402)
WHERE league_abbrev = 'NHL' AND game_type = 2
ORDER BY season;

SELECT game_date, opponent_abbrev, goals, assists, points, toi
FROM nhl.main.player_game_log(8478402, season := 20252026)
WHERE points >= 3
ORDER BY game_date;
```

`player_career()` covers every league a player has appeared in, including
junior, AHL, and Olympic seasons. Skater and goalie columns are in the same
table, and the columns that don't apply to a player are NULL.

### Game detail

```sql
-- Every goal in the 2025-26 opener, with rink coordinates in feet
SELECT period, time_in_period, event_owner_team_abbrev, primary_player_name,
       shot_type, x_coord, y_coord, away_score, home_score
FROM nhl.main.play_by_play(2025020001)
WHERE event_type = 'goal'
ORDER BY sort_order;

-- Ice time per player from the shift chart
SELECT team_abbrev, player_name, count(*) AS shifts, sum(duration_seconds) AS seconds
FROM nhl.main.shift_chart(2025020001)
GROUP BY ALL
ORDER BY seconds DESC;
```

`box_score()` holds the skater lines and `box_score_goalies()` holds the goalie
lines. You can find out who was on the ice for an event by joining
`play_by_play().game_seconds` to the `start_seconds`/`end_seconds` interval in
`shift_chart()`.

## Data source, licence, and affiliation

**This project is not affiliated with, endorsed by, or sponsored by the
National Hockey League or any of its teams.** NHL, the NHL Shield, team names,
and team marks are trademarks of the NHL and its teams. All data and logos
belong to the NHL. The worker's code is MIT-licensed, but that licence does not
cover the data.

The worker reads three keyless endpoints that power NHL.com and the NHL apps:

- `api-web.nhle.com/v1` for standings, schedules, scores, rosters, players,
  game centre, leaders, the bracket, and the draft
- `api.nhle.com/stats/rest/en` for season reports, teams, franchises, and shift
  charts
- `search.d3.nhle.com` for player search

These endpoints are undocumented and come with no API licence. The
[NHL.com Terms of Service](https://www.nhl.com/info/terms-of-service) allow NHL
content only for non-commercial, informational, personal use. They also
prohibit unauthorized scraping and prohibit entering NHL content into a
database or redistributing it. `vgi-nhl` is designed to respect those terms:

- It makes requests only when a user runs a query, for that user's own query.
  It does no bulk crawling or background harvesting.
- It never stores, mirrors, or republishes NHL data. The only copy is a short,
  in-memory response cache inside the process.
- It identifies itself honestly as
  `vgi-nhl/<version> (+https://github.com/Query-farm/vgi-nhl)` and limits its
  own request rate.

You are responsible for using the data in line with the NHL's terms. Do not use
this worker to build a commercial product or a redistributed dataset unless you
have your own licence from the NHL.

## Production HTTP deployment

Stdio is the recommended transport when Haybarn can start the worker locally.
Use HTTP when several hosts need to share one worker. The production HTTP entry
point refuses to start unless it has a stable signing key and either
authentication or an explicit decision to allow anonymous access:

```bash
export VGI_SIGNING_KEY='a-long-random-secret-shared-by-every-replica'
export VGI_BEARER_TOKENS='replace-with-a-random-token=haybarn'

uvx --from git+https://github.com/Query-farm/vgi-nhl@v0.2.0 vgi-nhl-http \
  --host 0.0.0.0 \
  --port 8000 \
  --cors-origins 'https://sql.example.com' \
  --log-format json
```

`vgi-nhl-http` disables the description pages and cross-origin access unless
you configure them explicitly. Terminate TLS at a trusted proxy or load
balancer. Every replica must get the same `VGI_SIGNING_KEY`. Outstanding state
tokens are signed with that key, so rotate it as a coordinated deployment.

Supported authentication options:

- `VGI_BEARER_TOKENS`: comma-separated `token=principal` pairs.
- `VGI_JWT_ISSUER` and `VGI_JWT_AUDIENCE`: JWT/JWKS authentication.
- `VGI_PROXY_PROOF_MODE=require`, with the matching VGI proxy-proof settings,
  when a trusted proxy authenticates users.

`VGI_ALLOW_ANONYMOUS=1` allows anonymous access. Even then, a deployment is
still subject to the NHL's non-commercial terms, so do not offer an anonymous
endpoint as a public data service. The health probe is `GET /health`.

### Container

```bash
docker build -t vgi-nhl .
docker run --rm -p 8000:8000 \
  -e VGI_SIGNING_KEY='replace-with-a-stable-random-secret' \
  -e VGI_BEARER_TOKENS='replace-with-a-random-token=haybarn' \
  vgi-nhl
```

The image runs as an unprivileged user, emits JSON logs, disables the
interactive description pages, and includes a health check.

## Reliability and operations

Every upstream call has a 30-second request timeout, and each query has a
120-second total deadline. A call is tried at most four times, and a process
makes at most four NHL requests at once. HTTP 429 and transient 5xx responses
are retried with jittered exponential backoff, and `Retry-After` is honored up
to 30 seconds per retry. The client follows the NHL's 307 redirects from its
`now` and `current` aliases.

Successful responses stay in an in-process LRU cache, capped at 256 entries,
for the origin's `max-age` (capped at one hour). If the origin sends no
`max-age`, which is the case for the stats service, the cache keeps the
response for 60 seconds. The same lifetime is passed to VGI clients as result
`Cache-Control`. Success timings are logged at debug level. Retries and
transport failures are logged as warnings.

For hermetic tests, `NHL_WEB_BASE_URL`, `NHL_STATS_BASE_URL`, and
`NHL_SEARCH_BASE_URL` can point the client at alternate roots. Never set them
from untrusted input.

## Development and release checks

```bash
uv lock --check --no-sources
uv sync --no-sources
uv run --no-sources ruff check .
uv run --no-sources ruff format --check .
uv run --no-sources pytest --cov=vgi_nhl --cov-fail-under=80
uv build
uvx twine check dist/*
uvx --no-sources --from vgi-lint-check==2.5.0 vgi-lint lint \
  'uv run --no-sources nhl_worker.py' \
  --no-execute --no-check-links --audit-waivers --fail-on warning
```

The offline suite needs no network. It replays trimmed real NHL responses from
`tests/fixtures/` through a local HTTP server, and it attaches the worker in
Haybarn to query every table. Live smoke tests are opt-in with
`uv run pytest -m live`. They also run in a serialized scheduled workflow, along
with vgi-lint's executing pass over every catalog example.

Publishing is driven by releases. Create a GitHub release named `vX.Y.Z` that
matches the version in `pyproject.toml`. CI then builds, validates and attests
the wheel and sdist, attaches them to the release, and publishes a
multi-platform container image to `ghcr.io/query-farm/vgi-nhl`. The package is
not published to PyPI; install it from the release tag as shown in the quick
start.

---

Copyright 2026 Query Farm LLC - https://query.farm
