"""Every table function fetches through the real HTTP client against the replay server."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pyarrow as pa
import pytest

from vgi_nhl import games, league, players, stats
from vgi_nhl.base import cache_control, resolve_season
from vgi_nhl.league_schemas import STANDINGS_SCHEMA

pytestmark = pytest.mark.usefixtures("replay")

SEASON = 20252026


def _rows(function, args=None) -> list[dict]:
    rows, ttl = function.rows(args)
    assert 0 < ttl <= 30
    return rows


def test_standings_follow_redirect_for_today_and_take_a_date() -> None:
    today = _rows(league.CurrentStandingsFunction)
    dated = _rows(league.StandingsFunction, league.DateArgs(date=date(2024, 4, 18)))
    assert today == dated
    assert len(today) == 4


def test_league_reference_functions() -> None:
    assert len(_rows(league.StandingsSeasonsFunction)) == 5
    assert len(_rows(league.TeamsFunction)) == 3
    assert len(_rows(league.FranchisesFunction)) == 3
    assert len(_rows(league.PlayoffBracketFunction, league.YearArgs(year=2025))) == 15
    assert _rows(league.DraftPicksFunction, league.DraftArgs(year=2025))[0]["overall_pick"] == 1


def test_schedule_and_scores() -> None:
    assert len(_rows(league.CurrentScheduleFunction)) == 4
    assert len(_rows(league.ScheduleFunction, league.DateArgs(date=date(2025, 10, 7)))) == 4
    assert len(_rows(league.CurrentScoresFunction)) == 3
    assert len(_rows(league.ScoresFunction, league.DateArgs(date=None))) == 3


def test_team_schedule_accepts_lowercase_codes_and_current_season() -> None:
    explicit = _rows(league.TeamScheduleFunction, league.TeamSeasonArgs(team="tor", season=SEASON))
    current = _rows(league.TeamScheduleFunction, league.TeamSeasonArgs(team="TOR", season=None))
    assert explicit == current
    assert len(explicit) == 3


def test_season_reports() -> None:
    args = stats.SeasonArgs(season=SEASON, game_type=2)
    skaters = _rows(stats.SkaterStatsFunction, args)
    assert skaters[0]["player_id"] == 8478402
    assert all(row["season"] == SEASON and row["game_type"] == 2 for row in skaters)
    assert len(_rows(stats.SkaterRealtimeStatsFunction, args)) == 3
    assert len(_rows(stats.GoalieStatsFunction, args)) == 3
    assert len(_rows(stats.TeamStatsFunction, args)) == 3


def test_leaderboards() -> None:
    skaters = _rows(
        stats.SkaterLeadersFunction,
        stats.SkaterLeaderArgs(season=SEASON, game_type=2, category=None, per_category=3),
    )
    assert {row["season"] for row in skaters} == {SEASON}
    goalies = _rows(
        stats.GoalieLeadersFunction,
        stats.GoalieLeaderArgs(season=SEASON, game_type=2, category="wins", per_category=3),
    )
    assert goalies
    current = _rows(stats.CurrentSkaterLeadersFunction)
    assert {(row["season"], row["game_type"]) for row in current} == {(SEASON, 2)}
    assert {row["category"] for row in _rows(stats.CurrentGoalieLeadersFunction)} >= {"wins"}


def test_player_functions() -> None:
    roster = _rows(players.RosterFunction, players.RosterArgs(team="tor", season=None))
    assert {row["season"] for row in roster} == {SEASON}
    assert roster == _rows(players.RosterFunction, players.RosterArgs(team="TOR", season=SEASON))
    [profile] = _rows(players.PlayerFunction, players.PlayerArgs(player_id=8478402))
    assert profile["player_name"] == "Connor McDavid"
    assert _rows(players.PlayerCareerFunction, players.PlayerArgs(player_id=8475683))
    log = _rows(
        players.PlayerGameLogFunction, players.GameLogArgs(player_id=8478402, season=SEASON, game_type=2)
    )
    assert len(log) == 3
    found = _rows(
        players.PlayerSearchFunction, players.SearchArgs(query=" mcdavid ", active_only=True, max_results=5)
    )
    assert 8478402 in {row["player_id"] for row in found}


def test_game_functions() -> None:
    args = games.GameArgs(game_id=2025020001)
    assert len(_rows(games.BoxScoreFunction, args)) == 36
    assert len(_rows(games.BoxScoreGoaliesFunction, args)) == 4
    assert len(_rows(games.PlayByPlayFunction, args)) == 18
    assert len(_rows(games.ShiftChartFunction, args)) == 6


def test_unknown_resources_raise_not_found() -> None:
    from vgi_nhl.api import NhlNotFoundError

    with pytest.raises(NhlNotFoundError):
        games.BoxScoreFunction.rows(games.GameArgs(game_id=2025029999))


def test_current_season_resolution_and_validation() -> None:
    assert resolve_season(None) == 20262027
    assert resolve_season(SEASON) == SEASON
    with pytest.raises(ValueError, match="8-digit"):
        resolve_season(20252027)


def test_process_projects_and_advertises_freshness() -> None:
    emitted: list = []
    out = SimpleNamespace(
        emit=lambda batch, cache_control=None: emitted.append((batch, cache_control)),
        finish=lambda: emitted.append("finished"),
    )
    schema = pa.schema([STANDINGS_SCHEMA.field("team_abbrev"), STANDINGS_SCHEMA.field("points")])
    league.StandingsFunction.process(
        SimpleNamespace(args=league.DateArgs(date=None), output_schema=schema), None, out
    )
    batch, control = emitted[0]
    assert batch.schema.names == schema.names
    assert batch.num_rows == 4
    assert 0 < control.ttl <= 30
    assert emitted[-1] == "finished"
    assert cache_control(0) is None


def test_cardinality_hints() -> None:
    hint = games.PlayByPlayFunction.cardinality(None)
    assert hint.estimate == 350 and hint.max == 1_000
