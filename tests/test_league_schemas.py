"""Flattening of recorded standings, schedule, score, bracket, draft, and reference payloads."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pyarrow as pa
from conftest import load

from vgi_nhl.league_schemas import (
    BRACKET_SCHEMA,
    DRAFT_SCHEMA,
    FRANCHISES_SCHEMA,
    GAMES_SCHEMA,
    LEADERS_SCHEMA,
    STANDINGS_SCHEMA,
    STANDINGS_SEASONS_SCHEMA,
    TEAMS_SCHEMA,
    flatten_bracket,
    flatten_draft,
    flatten_franchises,
    flatten_games,
    flatten_leaders,
    flatten_schedule,
    flatten_standings,
    flatten_standings_seasons,
    flatten_teams,
    game_row,
)
from vgi_nhl.meta import batch_from_rows


def _batch(rows, schema: pa.Schema) -> pa.RecordBatch:
    batch = batch_from_rows(rows, schema)
    assert batch.schema == schema
    return batch


def test_standings_rows_are_typed_and_complete() -> None:
    rows = flatten_standings(load("standings_2024-04-18.json"))
    _batch(rows, STANDINGS_SCHEMA)
    by_team = {row["team_abbrev"]: row for row in rows}
    assert set(by_team) == {"NYR", "DAL", "FLA", "BOS"}
    florida = by_team["FLA"]
    assert florida["season"] == 20232024
    assert florida["standings_date"] == date(2024, 4, 18)
    assert florida["team_name"] == "Florida Panthers"
    assert florida["division_name"] == "Atlantic"
    assert florida["division_rank"] == 1
    assert (florida["wins"], florida["losses"], florida["ot_losses"], florida["points"]) == (52, 24, 6, 110)
    assert florida["points"] == 2 * florida["wins"] + florida["ot_losses"]
    assert florida["goal_differential"] == florida["goals_for"] - florida["goals_against"] == 68
    assert florida["clinch_indicator"] == "y"
    assert by_team["NYR"]["clinch_indicator"] == "p"
    for row in rows:
        assert row["home_wins"] + row["road_wins"] == row["wins"]


def test_standings_tolerate_malformed_entries() -> None:
    assert flatten_standings({"standings": [None, "x"]}) == []
    assert flatten_standings({}) == []


def test_standings_seasons() -> None:
    rows = flatten_standings_seasons(load("standings_season.json"))
    _batch(rows, STANDINGS_SEASONS_SCHEMA)
    first, last = rows[0], rows[-1]
    assert first["season"] == 19171918
    assert first["ties_in_use"] is True and first["wildcard_in_use"] is False
    assert last["season"] == 20262027
    assert last["standings_start"] == date(2026, 9, 29)


def test_schedule_week_uses_day_dates() -> None:
    rows = flatten_schedule(load("schedule_2025-10-07.json"))
    _batch(rows, GAMES_SCHEMA)
    assert [row["game_id"] for row in rows] == [2025020001, 2025020002, 2025020004, 2025020005]
    opener = rows[0]
    assert opener["game_date"] == date(2025, 10, 7)
    assert opener["start_time_utc"] == datetime(2025, 10, 7, 21, tzinfo=UTC)
    assert opener["away_team_name"] == "Chicago Blackhawks"
    assert opener["home_team_name"] == "Florida Panthers"
    assert (opener["away_score"], opener["home_score"]) == (2, 3)
    assert opener["winning_goalie_name"] == "S. Bobrovsky"
    assert opener["winning_goal_scorer_id"] == 8480003
    assert opener["game_center_url"] == "https://www.nhl.com/gamecenter/chi-vs-fla/2025/10/07/2025020001"


def test_scores_include_shots_and_outcome() -> None:
    rows = flatten_games(load("score_2025-10-07.json"))
    _batch(rows, GAMES_SCHEMA)
    assert len(rows) == 3
    opener = rows[0]
    assert (opener["away_shots_on_goal"], opener["home_shots_on_goal"]) == (19, 37)
    assert opener["period"] == 3 and opener["last_period_type"] == "REG"
    assert opener["game_state"] == "OFF"


def test_unstarted_games_have_no_period() -> None:
    row = game_row({"id": 1, "gameState": "FUT", "periodDescriptor": {"number": 1, "periodType": "REG"}})
    assert row["period"] is None and row["period_type"] is None
    assert row["game_center_url"] is None
    assert row["away_team_name"] is None


def test_team_schedule_covers_game_types() -> None:
    rows = flatten_games(load("club_schedule_TOR_20252026.json"))
    assert [row["game_type"] for row in rows] == [1, 2, 2]
    assert rows[1]["home_team_abbrev"] == "TOR" and rows[1]["home_score"] == 5


def test_leaders_are_long_format() -> None:
    rows = flatten_leaders(load("skater_leaders_20252026_2.json"), season=20252026, game_type=2)
    _batch(rows, LEADERS_SCHEMA)
    points = [row for row in rows if row["category"] == "points"]
    assert [row["rank"] for row in points] == [1, 2, 3]
    assert points[0]["player_name"] == "Connor McDavid"
    assert points[0]["value"] == 138
    assert {row["category"] for row in rows} >= {"goals", "assists", "toi", "faceoffLeaders"}
    goalies = flatten_leaders(load("goalie_leaders_20252026_2.json"), season=None, game_type=None)
    assert {row["category"] for row in goalies} == {"wins", "shutouts", "savePctg", "goalsAgainstAverage"}
    assert flatten_leaders({"x": [None], "y": 3}, season=None, game_type=None) == []


def test_playoff_bracket() -> None:
    rows = flatten_bracket(load("playoff_bracket_2025.json"), 2025)
    _batch(rows, BRACKET_SCHEMA)
    assert len(rows) == 15
    final = next(row for row in rows if row["series_abbrev"] == "SCF")
    assert final["playoff_round"] == 4
    assert {final["top_seed_team_abbrev"], final["bottom_seed_team_abbrev"]} == {"EDM", "FLA"}
    assert final["winning_team_id"] == 13
    assert max(final["top_seed_wins"], final["bottom_seed_wins"]) == 4


def test_draft_picks() -> None:
    rows = flatten_draft(load("draft_picks_2025.json"))
    _batch(rows, DRAFT_SCHEMA)
    assert rows[0]["overall_pick"] == 1
    assert rows[0]["player_name"] == "Matthew Schaefer"
    assert rows[0]["team_abbrev"] == "NYI"
    assert rows[0]["draft_year"] == 2025


def test_teams_and_franchises() -> None:
    teams = flatten_teams(load("team.json"))
    franchises = flatten_franchises(load("franchise.json"))
    _batch(teams, TEAMS_SCHEMA)
    _batch(franchises, FRANCHISES_SCHEMA)
    avalanche = {row["full_name"] for row in teams if row["franchise_id"] == 27}
    assert avalanche == {"Quebec Nordiques", "Colorado Avalanche"}
    assert {row["common_name"] for row in franchises} == {"Avalanche", "Canadiens", "Islanders"}
