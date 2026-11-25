# Changelog

All notable changes to this project are documented here.

## 0.3.0 (2026-11-25)

- Speaks VGI protocol 3.4: require vgi-python `>=0.55.2,<0.56`; uv.lock re-locked. This release
  needs Haybarn 2.0.1 (or stock DuckDB 2.0 with `INSTALL vgi FROM query_farm`): Haybarn 2.0.0
  loads a 3.3 `vgi` extension that cannot attach it.
- SQL tests run on haybarn-unittest 2.0.1rc3.
- `serve` extra is `vgi-python[http,oauth]`; the Docker image installs it, so the image runs in
  Orchard hosted mode (`VGI_ORCHARD_HOSTED=1` with VGI_JWT_ISSUER, VGI_JWT_AUDIENCE,
  VGI_JWT_JWKS_URI and VGI_SIGNING_KEY). The HEALTHCHECK uses `HEAD /health`, which stays
  anonymous in hosted mode.

## [Unreleased]

## 0.2.2 (2026-11-16)

- Bump vgi-python to 0.52.2.
- Requires Python 3.14 (CI, Docker image and tooling moved to 3.14).
- CI runs the SQL tests over stdio, launch and HTTP transports.

## [0.2.1]

- Docs link to NHL.com, NHL Stats, the NHL.com Terms of Service and a community
  API reference: the catalog's documentation gains a Sources and references
  section (vgi-lint VGI183).
- The schema documentation gives an overview of the worker instead of listing its
  functions (vgi-lint VGI173); per-function guidance lives on each function's own docs.

## [0.2.0]

- Speaks VGI protocol 3.3 (vgi-python 0.51); requires the current VGI DuckDB
  extension (3.2 extensions are incompatible).
- CI lints with vgi-lint-check 2.5.0.

## [0.1.0]

- Initial release on VGI protocol 3.2 (vgi-python 0.50, vgi-lint-check 2.2.0).
- Current tables for standings, this week's schedule, today's scores, skater and
  goalie leaders, plus seasons, teams, and franchises reference tables.
- Table functions for standings by date, schedules and scores by date, team
  seasons, skater/real-time/goalie/team season reports, leaderboards, rosters,
  player profiles, career lines, game logs, player search, box scores,
  play-by-play with rink coordinates, shift charts, playoff brackets, and drafts.
- Typed Arrow schemas with column comments and agent-facing discovery metadata.
- httpx client with retries, `Retry-After` backoff, redirect following for the
  NHL's `now`/`current` aliases, bounded concurrency, a query deadline, and an
  in-process response cache that honors the origin's `max-age`.
- Hermetic Haybarn end-to-end test over recorded responses, opt-in live tests,
  container image, CI, and trusted-publishing workflows.
