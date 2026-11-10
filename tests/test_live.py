"""Opt-in smoke tests against the NHL's public web and stats APIs."""

from __future__ import annotations

from datetime import date

import pytest

from vgi_nhl import api, games, league, players, stats

pytestmark = pytest.mark.live

SEASON = 20252026


def test_current_standings_cover_the_league() -> None:
    rows, _ = league.CurrentStandingsFunction.rows(None)
    assert len(rows) == 32
    assert sum(row["wins"] for row in rows) == sum(row["losses"] + row["ot_losses"] for row in rows)
    assert sum(row["goals_for"] for row in rows) == sum(row["goals_against"] for row in rows)


def test_final_2023_24_standings() -> None:
    rows, _ = league.StandingsFunction.rows(league.DateArgs(date=date(2024, 4, 18)))
    atlantic = sorted(
        (row for row in rows if row["division_name"] == "Atlantic"), key=lambda r: r["division_rank"]
    )
    assert atlantic[0]["team_abbrev"] == "FLA" and atlantic[0]["points"] == 110
    assert sum(row["games_played"] for row in rows) == 32 * 82


def test_current_season_is_resolved() -> None:
    assert api.current_season() >= SEASON


def test_opener_box_score_matches_play_by_play() -> None:
    args = games.GameArgs(game_id=2025020001)
    box, _ = games.BoxScoreFunction.rows(args)
    plays, _ = games.PlayByPlayFunction.rows(args)
    shifts, _ = games.ShiftChartFunction.rows(args)
    assert sum(row["goals"] for row in box) == 5
    assert len([row for row in plays if row["event_type"] == "goal"]) == 5
    shots = {"CHI": 0, "FLA": 0}
    for row in plays:
        if row["event_type"] in {"goal", "shot-on-goal"}:
            shots[row["event_owner_team_abbrev"]] += 1
    assert shots == {"CHI": 19, "FLA": 37}
    assert len(shifts) > 700


def test_mcdavid_2025_26_points_agree_across_endpoints() -> None:
    summary, _ = stats.SkaterStatsFunction.rows(stats.SeasonArgs(season=SEASON, game_type=2))
    mcdavid = next(row for row in summary if row["player_id"] == 8478402)
    log, _ = players.PlayerGameLogFunction.rows(
        players.GameLogArgs(player_id=8478402, season=SEASON, game_type=2)
    )
    career, _ = players.PlayerCareerFunction.rows(players.PlayerArgs(player_id=8478402))
    line = next(
        r for r in career if r["season"] == SEASON and r["league_abbrev"] == "NHL" and r["game_type"] == 2
    )
    assert mcdavid["points"] == sum(row["points"] for row in log) == line["points"] == 138
    assert len(summary) > 800


def test_leaders_bracket_draft_and_search() -> None:
    leaders, _ = stats.SkaterLeadersFunction.rows(
        stats.SkaterLeaderArgs(season=SEASON, game_type=2, category="points", per_category=1)
    )
    assert leaders[0]["player_id"] == 8478402
    bracket, _ = league.PlayoffBracketFunction.rows(league.YearArgs(year=2025))
    assert next(row for row in bracket if row["series_abbrev"] == "SCF")["winning_team_id"] == 13
    draft, _ = league.DraftPicksFunction.rows(league.DraftArgs(year=2025))
    assert draft[0]["player_name"] == "Matthew Schaefer"
    found, _ = players.PlayerSearchFunction.rows(
        players.SearchArgs(query="mcdavid", active_only=False, max_results=25)
    )
    assert 8478402 in {row["player_id"] for row in found}


def test_unknown_game_is_not_found() -> None:
    with pytest.raises(api.NhlNotFoundError):
        games.BoxScoreFunction.rows(games.GameArgs(game_id=2025029999))
