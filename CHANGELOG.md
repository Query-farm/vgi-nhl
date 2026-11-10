# Changelog

All notable changes to this project are documented here.

## [Unreleased]

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
