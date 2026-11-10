"""Season skater, goalie, and team reports plus stat leaderboards."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Annotated, Any, ClassVar

import pyarrow as pa
from vgi.arguments import Arg
from vgi.table_function import TableFunctionGenerator, bind_fixed_schema, init_single_worker

from vgi_nhl import api
from vgi_nhl.base import (
    GAME_TYPE_ARG,
    SEASON_ARG,
    Fetching,
    Rows,
    make_examples,
    make_tags,
    resolve_season,
)
from vgi_nhl.league_schemas import LEADERS_SCHEMA, flatten_leaders
from vgi_nhl.meta import Spec, flatten
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

_CATEGORIES = ["hockey", "nhl", "statistics"]
SKATER_CATEGORIES = (
    "points",
    "goals",
    "assists",
    "plusMinus",
    "goalsPp",
    "goalsSh",
    "penaltyMins",
    "faceoffLeaders",
    "toi",
)
GOALIE_CATEGORIES = ("wins", "savePctg", "goalsAgainstAverage", "shutouts")
CURRENT_LEADER_LIMIT = 10
_SEASON_IN_URL = re.compile(r"/(\d{8})/(\d)(?:[/?]|$)")


@dataclass(kw_only=True)
class SeasonArgs:
    """Season and game type for a season report."""

    season: Annotated[int | None, SEASON_ARG]
    game_type: Annotated[int, GAME_TYPE_ARG]


_PER_CATEGORY = Arg(
    "per_category",
    default=10,
    arrow_type=pa.int32(),
    ge=1,
    le=1000,
    doc="Players returned per category (default 10).",
)


@dataclass(kw_only=True)
class SkaterLeaderArgs:
    """Arguments for skater leaderboards."""

    season: Annotated[int | None, SEASON_ARG]
    game_type: Annotated[int, GAME_TYPE_ARG]
    category: Annotated[
        str | None,
        Arg(
            "category",
            default=None,
            arrow_type=pa.string(),
            choices=SKATER_CATEGORIES,
            doc="One leader category; NULL returns every skater category.",
        ),
    ]
    per_category: Annotated[int, _PER_CATEGORY]


@dataclass(kw_only=True)
class GoalieLeaderArgs:
    """Arguments for goalie leaderboards."""

    season: Annotated[int | None, SEASON_ARG]
    game_type: Annotated[int, GAME_TYPE_ARG]
    category: Annotated[
        str | None,
        Arg(
            "category",
            default=None,
            arrow_type=pa.string(),
            choices=GOALIE_CATEGORIES,
            doc="One leader category; NULL returns every goalie category.",
        ),
    ]
    per_category: Annotated[int, _PER_CATEGORY]


class _Report(Fetching):
    """A complete stats REST report for one season and game type."""

    REPORT: ClassVar[str]
    SPEC: ClassVar[list[Spec]]
    SORT: ClassVar[list[tuple[str, str]]]
    KEY: ClassVar[tuple[str, ...]]

    @classmethod
    def rows(cls, args: SeasonArgs) -> Rows:
        """Fetch every row of the report."""
        season = resolve_season(args.season)
        response = api.stats_report(cls.REPORT, season=season, game_type=args.game_type, sort=cls.SORT)
        records = api.require_list(response.payload["data"], f"{cls.REPORT} data")
        defaults = {"season": season, "game_type": args.game_type}
        return flatten(records, cls.SPEC, defaults=defaults, key=cls.KEY), response.ttl


_SKATER_EXAMPLES = [
    (
        "The 2025-26 regular-season scoring leaders.",
        "SELECT player_name, team_abbrevs, games_played, goals, assists, points "
        "FROM nhl.main.skater_stats(season := 20252026) ORDER BY points DESC LIMIT 10",
    ),
    (
        "2025-26 playoff goal leaders.",
        "SELECT player_name, team_abbrevs, goals FROM nhl.main.skater_stats(season := 20252026, "
        "game_type := 3) ORDER BY goals DESC LIMIT 10",
    ),
]


@init_single_worker
@bind_fixed_schema
class SkaterStatsFunction(_Report, TableFunctionGenerator[SeasonArgs]):
    """Season scoring summary for every skater."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = SKATER_STATS_SCHEMA
    REPORT = "skater/summary"
    SPEC = SKATER_STATS_SPEC
    SORT = [("points", "DESC"), ("goals", "DESC"), ("playerId", "ASC")]
    KEY = ("player_id",)
    ESTIMATE, MAXIMUM = 950, 1_500

    class Meta:
        """Function discovery metadata."""

        name = "skater_stats"
        description = "Season scoring summary for every NHL skater (goals, assists, points, TOI)"
        categories = [*_CATEGORIES, "skaters"]
        projection_pushdown = True
        tags = make_tags(
            category="player-stats",
            title="NHL Skater Season Stats",
            llm=(
                "One row per skater for a season and game type: games, goals, assists, points, "
                "plus-minus, PIM, points per game, even-strength/power-play/shorthanded goals and "
                "points, game-winning and OT goals, shots, shooting %, faceoff %, and average TOI "
                "in seconds. Traded players have one combined row; team_abbrevs lists every club. "
                "Percentages are 0-1 fractions."
            ),
            md=(
                "The NHL.com/stats skater summary report. `season` is an 8-digit id such as "
                "20252026 (default current); `game_type` 2 regular season, 3 playoffs."
            ),
            schema=SKATER_STATS_SCHEMA,
            examples=_SKATER_EXAMPLES,
        )
        examples = make_examples(_SKATER_EXAMPLES)


_REALTIME_EXAMPLES = [
    (
        "The most physical skaters of 2025-26.",
        "SELECT player_name, team_abbrevs, hits, blocked_shots "
        "FROM nhl.main.skater_realtime_stats(season := 20252026) ORDER BY hits DESC LIMIT 10",
    )
]


@init_single_worker
@bind_fixed_schema
class SkaterRealtimeStatsFunction(_Report, TableFunctionGenerator[SeasonArgs]):
    """Season real-time event counts for every skater."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = SKATER_REALTIME_SCHEMA
    REPORT = "skater/realtime"
    SPEC = SKATER_REALTIME_SPEC
    SORT = [("hits", "DESC"), ("playerId", "ASC")]
    KEY = ("player_id",)
    ESTIMATE, MAXIMUM = 950, 1_500

    class Meta:
        """Function discovery metadata."""

        name = "skater_realtime_stats"
        description = "Season hits, blocks, giveaways, takeaways, and shot attempts for every skater"
        categories = [*_CATEGORIES, "skaters"]
        projection_pushdown = True
        tags = make_tags(
            category="player-stats",
            title="NHL Skater Real-Time Stats",
            llm=(
                "One row per skater with the NHL's real-time event counts and per-60 rates: hits, "
                "blocked shots, giveaways, takeaways, missed shots by kind, total shot attempts, "
                "empty-net goals and points, and first goals. Join to skater_stats() on player_id "
                "for scoring."
            ),
            md="The NHL.com/stats skater real-time report for a season and game type.",
            schema=SKATER_REALTIME_SCHEMA,
            examples=_REALTIME_EXAMPLES,
        )
        examples = make_examples(_REALTIME_EXAMPLES)


_GOALIE_EXAMPLES = [
    (
        "2025-26 save-percentage leaders with at least 40 games.",
        "SELECT player_name, team_abbrevs, games_played, save_pct, goals_against_average "
        "FROM nhl.main.goalie_stats(season := 20252026) WHERE games_played >= 40 "
        "ORDER BY save_pct DESC LIMIT 10",
    )
]


@init_single_worker
@bind_fixed_schema
class GoalieStatsFunction(_Report, TableFunctionGenerator[SeasonArgs]):
    """Season summary for every goalie."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = GOALIE_STATS_SCHEMA
    REPORT = "goalie/summary"
    SPEC = GOALIE_STATS_SPEC
    SORT = [("wins", "DESC"), ("playerId", "ASC")]
    KEY = ("player_id",)
    ESTIMATE, MAXIMUM = 100, 200

    class Meta:
        """Function discovery metadata."""

        name = "goalie_stats"
        description = "Season summary for every NHL goalie (wins, save %, GAA, shutouts)"
        categories = [*_CATEGORIES, "goalies"]
        projection_pushdown = True
        tags = make_tags(
            category="player-stats",
            title="NHL Goalie Season Stats",
            llm=(
                "One row per goalie for a season and game type: games played and started, wins, "
                "losses, OT losses, shots against, saves, goals against, save % (0-1), "
                "goals-against average, shutouts, and total TOI in seconds. Apply your own "
                "games-played minimum when ranking rate stats."
            ),
            md="The NHL.com/stats goalie summary report for a season and game type.",
            schema=GOALIE_STATS_SCHEMA,
            examples=_GOALIE_EXAMPLES,
        )
        examples = make_examples(_GOALIE_EXAMPLES)


_TEAM_EXAMPLES = [
    (
        "2025-26 special-teams ranking.",
        "SELECT team_name, power_play_pct, penalty_kill_pct, power_play_pct + penalty_kill_pct AS "
        "special_teams FROM nhl.main.team_stats(season := 20252026) ORDER BY special_teams DESC",
    )
]


@init_single_worker
@bind_fixed_schema
class TeamStatsFunction(_Report, TableFunctionGenerator[SeasonArgs]):
    """Season summary for every team."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = TEAM_STATS_SCHEMA
    REPORT = "team/summary"
    SPEC = TEAM_STATS_SPEC
    SORT = [("points", "DESC"), ("teamId", "ASC")]
    KEY = ("team_id",)
    ESTIMATE, MAXIMUM = 32, 40

    class Meta:
        """Function discovery metadata."""

        name = "team_stats"
        description = "Season team summary: record, goals, shots, special teams, faceoffs"
        categories = [*_CATEGORIES, "teams"]
        projection_pushdown = True
        tags = make_tags(
            category="team-stats",
            title="NHL Team Season Stats",
            llm=(
                "One row per team for a season and game type: record and points, regulation and "
                "shootout wins, goals and shots for/against (totals and per game), power-play and "
                "penalty-kill % (plain and net), faceoff %, and shutouts. Percentages are 0-1."
            ),
            md="The NHL.com/stats team summary report for a season and game type.",
            schema=TEAM_STATS_SCHEMA,
            examples=_TEAM_EXAMPLES,
        )
        examples = make_examples(_TEAM_EXAMPLES)


def leader_rows(kind: str, *, season: int | None, game_type: int, category: str | None, limit: int) -> Rows:
    """Fetch a skater or goalie leaderboard; ``season=None`` asks the NHL for its current one."""
    params: dict[str, str | int] = {"limit": limit}
    if category is not None:
        params["categories"] = category
    if season is None:
        response = api.web(f"{kind}-stats-leaders/current", params)
        match = _SEASON_IN_URL.search(response.url)
        resolved, resolved_type = (int(match.group(1)), int(match.group(2))) if match else (None, None)
    else:
        resolved, resolved_type = season, game_type
        response = api.web(f"{kind}-stats-leaders/{season}/{game_type}", params)
    payload: dict[str, Any] = api.require_dict(response)
    return flatten_leaders(payload, season=resolved, game_type=resolved_type), response.ttl


_SKATER_LEADER_EXAMPLES = [
    (
        "The 2025-26 top-ten point scorers.",
        "SELECT rank, player_name, team_abbrev, value AS points FROM nhl.main.skater_leaders("
        "season := 20252026, category := 'points') ORDER BY rank",
    )
]


@init_single_worker
@bind_fixed_schema
class SkaterLeadersFunction(Fetching, TableFunctionGenerator[SkaterLeaderArgs]):
    """Skater stat leaderboards for a season."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = LEADERS_SCHEMA
    ESTIMATE, MAXIMUM = 90, 9_000

    class Meta:
        """Function discovery metadata."""

        name = "skater_leaders"
        description = "NHL skater leaderboards by category for a season and game type"
        categories = [*_CATEGORIES, "leaders", "skaters"]
        projection_pushdown = True
        tags = make_tags(
            category="leaders",
            title="NHL Skater Leaders",
            llm=(
                "Ranked skater leaders in categories points, goals, assists, plusMinus, goalsPp, "
                "goalsSh, penaltyMins, faceoffLeaders (0-1), and toi (seconds per game). Long "
                "format: one row per category and rank, with the stat in value. season defaults to "
                "the current season and game_type to the regular season."
            ),
            md="The NHL.com leaderboards; `per_category` sets players per category (default 10).",
            schema=LEADERS_SCHEMA,
            examples=_SKATER_LEADER_EXAMPLES,
        )
        examples = make_examples(_SKATER_LEADER_EXAMPLES)

    @classmethod
    def rows(cls, args: SkaterLeaderArgs) -> Rows:
        """Fetch the leaderboard."""
        season = resolve_season(args.season)
        return leader_rows(
            "skater", season=season, game_type=args.game_type, category=args.category, limit=args.per_category
        )


_GOALIE_LEADER_EXAMPLES = [
    (
        "The 2025-26 regular-season wins leaders.",
        "SELECT rank, player_name, team_abbrev, value AS wins FROM nhl.main.goalie_leaders("
        "season := 20252026, category := 'wins') ORDER BY rank",
    )
]


@init_single_worker
@bind_fixed_schema
class GoalieLeadersFunction(Fetching, TableFunctionGenerator[GoalieLeaderArgs]):
    """Goalie stat leaderboards for a season."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = LEADERS_SCHEMA
    ESTIMATE, MAXIMUM = 40, 4_000

    class Meta:
        """Function discovery metadata."""

        name = "goalie_leaders"
        description = "NHL goalie leaderboards by category for a season and game type"
        categories = [*_CATEGORIES, "leaders", "goalies"]
        projection_pushdown = True
        tags = make_tags(
            category="leaders",
            title="NHL Goalie Leaders",
            llm=(
                "Ranked goalie leaders in categories wins, savePctg (0-1), goalsAgainstAverage, "
                "and shutouts, one row per category and rank with the stat in value. The NHL "
                "applies its own games-played qualification to rate categories."
            ),
            md="The NHL.com goalie leaderboards; `per_category` sets goalies per category (default 10).",
            schema=LEADERS_SCHEMA,
            examples=_GOALIE_LEADER_EXAMPLES,
        )
        examples = make_examples(_GOALIE_LEADER_EXAMPLES)

    @classmethod
    def rows(cls, args: GoalieLeaderArgs) -> Rows:
        """Fetch the leaderboard."""
        season = resolve_season(args.season)
        return leader_rows(
            "goalie", season=season, game_type=args.game_type, category=args.category, limit=args.per_category
        )


_CURRENT_SKATER_LEADER_EXAMPLES = [
    (
        "Current points leaders from the backing scan.",
        "SELECT rank, player_name, value FROM nhl.main.all_current_skater_leaders() "
        "WHERE category = 'points' ORDER BY rank",
    )
]


@init_single_worker
@bind_fixed_schema
class CurrentSkaterLeadersFunction(Fetching, TableFunctionGenerator[None]):
    """Current skater leaders, backing the ``current_skater_leaders`` table."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = LEADERS_SCHEMA
    ESTIMATE, MAXIMUM = 90, 200

    class Meta:
        """Function discovery metadata."""

        name = "all_current_skater_leaders"
        description = "Current NHL top-ten skater leaders per category (scan behind current_skater_leaders)"
        categories = [*_CATEGORIES, "leaders", "skaters"]
        projection_pushdown = True
        tags = make_tags(
            category="leaders",
            title="Current NHL Skater Leaders Scan",
            llm="The scan behind current_skater_leaders. Prefer the table; use skater_leaders() for options.",
            md="Top ten per skater category for the current season.",
            schema=LEADERS_SCHEMA,
            examples=_CURRENT_SKATER_LEADER_EXAMPLES,
        )
        examples = make_examples(_CURRENT_SKATER_LEADER_EXAMPLES)

    @classmethod
    def rows(cls, args: None) -> Rows:
        """Fetch the current leaderboard."""
        return leader_rows("skater", season=None, game_type=2, category=None, limit=CURRENT_LEADER_LIMIT)


_CURRENT_GOALIE_LEADER_EXAMPLES = [
    (
        "Current wins leaders from the backing scan.",
        "SELECT rank, player_name, value FROM nhl.main.all_current_goalie_leaders() "
        "WHERE category = 'wins' ORDER BY rank",
    )
]


@init_single_worker
@bind_fixed_schema
class CurrentGoalieLeadersFunction(Fetching, TableFunctionGenerator[None]):
    """Current goalie leaders, backing the ``current_goalie_leaders`` table."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = LEADERS_SCHEMA
    ESTIMATE, MAXIMUM = 40, 100

    class Meta:
        """Function discovery metadata."""

        name = "all_current_goalie_leaders"
        description = "Current NHL top-ten goalie leaders per category (scan behind current_goalie_leaders)"
        categories = [*_CATEGORIES, "leaders", "goalies"]
        projection_pushdown = True
        tags = make_tags(
            category="leaders",
            title="Current NHL Goalie Leaders Scan",
            llm="The scan behind current_goalie_leaders. Prefer the table; use goalie_leaders() for options.",
            md="Top ten per goalie category for the current season.",
            schema=LEADERS_SCHEMA,
            examples=_CURRENT_GOALIE_LEADER_EXAMPLES,
        )
        examples = make_examples(_CURRENT_GOALIE_LEADER_EXAMPLES)

    @classmethod
    def rows(cls, args: None) -> Rows:
        """Fetch the current leaderboard."""
        return leader_rows("goalie", season=None, game_type=2, category=None, limit=CURRENT_LEADER_LIMIT)


STATS_FUNCTIONS = [
    SkaterStatsFunction,
    SkaterRealtimeStatsFunction,
    GoalieStatsFunction,
    TeamStatsFunction,
    SkaterLeadersFunction,
    GoalieLeadersFunction,
    CurrentSkaterLeadersFunction,
    CurrentGoalieLeadersFunction,
]
