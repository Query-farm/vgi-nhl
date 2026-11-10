"""Flattening of recorded player, stats-report, and single-game payloads."""

from __future__ import annotations

from datetime import date

from conftest import load

from vgi_nhl.game_schemas import (
    BOX_SCORE_GOALIES_SCHEMA,
    BOX_SCORE_SCHEMA,
    PLAY_BY_PLAY_SCHEMA,
    SHIFT_CHART_SCHEMA,
    flatten_box_score,
    flatten_play_by_play,
    flatten_shift_chart,
)
from vgi_nhl.meta import batch_from_rows, flatten
from vgi_nhl.player_schemas import (
    CAREER_SCHEMA,
    GAME_LOG_SCHEMA,
    PLAYER_SCHEMA,
    ROSTER_SCHEMA,
    SEARCH_SCHEMA,
    flatten_career,
    flatten_game_log,
    flatten_player,
    flatten_roster,
    flatten_search,
)
from vgi_nhl.stats_schemas import (
    GOALIE_STATS_SCHEMA,
    GOALIE_STATS_SPEC,
    SKATER_REALTIME_SCHEMA,
    SKATER_REALTIME_SPEC,
    SKATER_STATS_SCHEMA,
    SKATER_STATS_SPEC,
    TEAM_STATS_SCHEMA,
    TEAM_STATS_SPEC,
)


def test_roster_groups_and_bio() -> None:
    rows = flatten_roster(load("roster_TOR_20252026.json"), season=20252026, team="TOR")
    batch_from_rows(rows, ROSTER_SCHEMA)
    assert [row["position_group"] for row in rows] == ["forwards"] * 2 + ["defensemen"] * 2 + ["goalies"]
    domi = rows[0]
    assert domi["player_name"] == "Max Domi"
    assert domi["birth_date"] == date(1995, 3, 2)
    assert domi["sweater_number"] == 11
    assert rows[2]["sweater_number"] is None


def test_player_landing_for_skater_and_goalie() -> None:
    [mcdavid] = flatten_player(load("player_8478402_landing.json"))
    batch_from_rows([mcdavid], PLAYER_SCHEMA)
    assert mcdavid["player_name"] == "Connor McDavid"
    assert (mcdavid["draft_year"], mcdavid["draft_overall_pick"]) == (2015, 1)
    assert mcdavid["career_points"] >= 1_268
    assert mcdavid["career_wins"] is None
    [bobrovsky] = flatten_player(load("player_8475683_landing.json"))
    assert bobrovsky["position"] == "G"
    assert bobrovsky["draft_year"] is None
    assert bobrovsky["career_wins"] >= 459
    assert 0.9 < bobrovsky["career_save_pct"] < 0.92
    assert flatten_player({}) == []


def test_career_lines_mix_leagues_and_game_types() -> None:
    rows = flatten_career(load("player_8478402_landing.json"))
    batch_from_rows(rows, CAREER_SCHEMA)
    nhl = [row for row in rows if row["league_abbrev"] == "NHL" and row["season"] == 20252026]
    regular = next(row for row in nhl if row["game_type"] == 2)
    assert regular["points"] == 138 and regular["team_name"] == "Edmonton Oilers"
    assert regular["avg_toi_seconds"] is not None
    assert {row["league_abbrev"] for row in rows} >= {"NHL", "OG"}
    goalie = flatten_career(load("player_8475683_landing.json"))
    line = next(row for row in goalie if row["season"] == 20252026)
    assert (line["wins"], line["time_on_ice"], line["time_on_ice_seconds"]) == (27, "3009:39", 180_579)
    assert all(row["player_id"] == 8475683 for row in goalie)


def test_game_logs() -> None:
    rows = flatten_game_log(
        load("game_log_8478402_20252026_2.json"), player_id=8478402, season=20252026, game_type=2
    )
    batch_from_rows(rows, GAME_LOG_SCHEMA)
    assert rows[0]["game_id"] == 2025021311
    assert rows[0]["game_date"] == date(2026, 4, 16)
    assert (rows[0]["points"], rows[0]["toi_seconds"]) == (4, 18 * 60 + 16)
    assert rows[0]["season"] == 20252026 and rows[0]["game_type"] == 2
    goalie = flatten_game_log(
        load("game_log_8475683_20252026_2.json"), player_id=8475683, season=None, game_type=2
    )
    assert goalie[0]["decision"] == "L" and goalie[0]["save_pct"] == 0.84
    assert goalie[0]["points"] is None


def test_player_search() -> None:
    rows = flatten_search(load("search_mcdavid.json"))
    batch_from_rows(rows, SEARCH_SCHEMA)
    connor = next(row for row in rows if row["player_id"] == 8478402)
    assert connor["active"] is True and connor["team_abbrev"] == "EDM"
    assert flatten_search({"not": "a list"}) == []


def test_stats_reports_map_every_column() -> None:
    defaults = {"season": 20252026, "game_type": 2}
    skaters = flatten(load("skater_summary_20252026_2.json")["data"], SKATER_STATS_SPEC, defaults=defaults)
    batch_from_rows(skaters, SKATER_STATS_SCHEMA)
    mcdavid = skaters[0]
    assert (mcdavid["player_name"], mcdavid["points"], mcdavid["game_type"]) == ("Connor McDavid", 138, 2)
    assert mcdavid["goals"] + mcdavid["assists"] == mcdavid["points"]
    panarin = next(row for row in skaters if row["player_id"] == 8478550)
    assert panarin["team_abbrevs"] == "NYR,LAK"
    for spec, schema, name in (
        (SKATER_REALTIME_SPEC, SKATER_REALTIME_SCHEMA, "skater_realtime_20252026_2.json"),
        (GOALIE_STATS_SPEC, GOALIE_STATS_SCHEMA, "goalie_summary_20252026_2.json"),
        (TEAM_STATS_SPEC, TEAM_STATS_SCHEMA, "team_summary_20252026_2.json"),
    ):
        rows = flatten(load(name)["data"], spec, defaults=defaults)
        batch = batch_from_rows(rows, schema)
        assert batch.num_rows == 3
        populated = [column for column in batch.schema.names if batch.column(column).null_count < 3]
        assert len(populated) >= len(schema) - 1, name


def test_report_rows_missing_a_key_are_dropped() -> None:
    rows = flatten([{"playerId": None}, {"playerId": 5}], SKATER_STATS_SPEC, defaults={}, key=("player_id",))
    assert [row["player_id"] for row in rows] == [5]


def test_box_score_splits_skaters_and_goalies() -> None:
    payload = load("boxscore_2025020001.json")
    skaters = flatten_box_score(payload, goalies=False)
    goalies = flatten_box_score(payload, goalies=True)
    batch_from_rows(skaters, BOX_SCORE_SCHEMA)
    batch_from_rows(goalies, BOX_SCORE_GOALIES_SCHEMA)
    assert len(skaters) == 36 and len(goalies) == 4
    goals = {
        side: sum(row["goals"] for row in skaters if row["team_side"] == side) for side in ("away", "home")
    }
    assert goals == {"away": 2, "home": 3}
    shots = sum(row["shots_on_goal"] for row in skaters if row["team_abbrev"] == "FLA")
    assert shots == 37
    winner = next(row for row in goalies if row["decision"] == "W")
    assert (winner["player_name"], winner["saves"], winner["shots_against"]) == ("S. Bobrovsky", 17, 19)
    assert winner["starter"] is True


def test_play_by_play_actors_and_clock() -> None:
    rows = flatten_play_by_play(load("play_by_play_2025020001.json"))
    batch_from_rows(rows, PLAY_BY_PLAY_SCHEMA)
    assert [row["sort_order"] for row in rows] == sorted(row["sort_order"] for row in rows)
    goals = [row for row in rows if row["event_type"] == "goal"]
    assert len(goals) == 5
    first = goals[0]
    assert first["primary_player_name"] == "Frank Nazar"
    assert first["event_owner_team_abbrev"] == "CHI"
    assert (first["x_coord"], first["y_coord"], first["shot_type"]) == (66, -1, "snap")
    assert first["game_seconds"] == 603
    assert first["assist1_player_id"] == first["secondary_player_id"]
    assert (goals[-1]["away_score"], goals[-1]["home_score"]) == (2, 3)
    penalty = next(row for row in rows if row["event_type"] == "penalty")
    assert (penalty["penalty_severity"], penalty["penalty_type"], penalty["penalty_minutes"]) == (
        "MIN",
        "slashing",
        2,
    )
    faceoff = next(row for row in rows if row["event_type"] == "faceoff")
    assert faceoff["primary_player_id"] and faceoff["secondary_player_id"]
    start = next(row for row in rows if row["event_type"] == "period-start")
    assert start["primary_player_id"] is None and start["x_coord"] is None


def test_shift_chart_drops_goal_markers() -> None:
    rows = flatten_shift_chart(load("shiftcharts_2025020001.json"))
    batch_from_rows(rows, SHIFT_CHART_SCHEMA)
    assert len(rows) == 6
    assert all(row["player_name"] == "Brad Marchand" for row in rows)
    second = rows[1]
    assert (second["start_seconds"], second["end_seconds"], second["duration_seconds"]) == (183, 258, 75)
