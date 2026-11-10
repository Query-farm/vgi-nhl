"""One game's box score, goalie lines, play-by-play, and shift chart."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, ClassVar

import pyarrow as pa
from vgi.arguments import Arg
from vgi.table_function import TableFunctionGenerator, bind_fixed_schema, init_single_worker

from vgi_nhl import api
from vgi_nhl.base import Fetching, Rows, make_examples, make_tags
from vgi_nhl.game_schemas import (
    BOX_SCORE_GOALIES_SCHEMA,
    BOX_SCORE_SCHEMA,
    PLAY_BY_PLAY_SCHEMA,
    SHIFT_CHART_SCHEMA,
    flatten_box_score,
    flatten_play_by_play,
    flatten_shift_chart,
)

_CATEGORIES = ["hockey", "nhl", "games"]


@dataclass(kw_only=True)
class GameArgs:
    """One game id."""

    game_id: Annotated[
        int,
        Arg(
            0,
            arrow_type=pa.int64(),
            ge=1_917_000_000,
            le=2_100_999_999,
            doc=(
                "10-digit NHL game id: season start year, 2-digit game type, 4-digit number "
                "(2025020001 = 2025-26 regular-season game 1). Find ids with scores() or schedule()."
            ),
        ),
    ]


_BOX_EXAMPLES = [
    (
        "Skater lines from the 2025-26 opener, by points.",
        "SELECT team_abbrev, player_name, goals, assists, shots_on_goal, toi "
        "FROM nhl.main.box_score(2025020001) ORDER BY points DESC, toi_seconds DESC",
    )
]


@init_single_worker
@bind_fixed_schema
class BoxScoreFunction(Fetching, TableFunctionGenerator[GameArgs]):
    """Skater box-score lines for one game."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = BOX_SCORE_SCHEMA
    ESTIMATE, MAXIMUM = 36, 50

    class Meta:
        """Function discovery metadata."""

        name = "box_score"
        description = "Skater box-score lines (both teams) for one NHL game"
        categories = [*_CATEGORIES, "box-score"]
        projection_pushdown = True
        tags = make_tags(
            category="games",
            title="NHL Box Score (Skaters)",
            llm=(
                "One row per skater who played in a game, both teams (team_side away/home): goals, "
                "assists, points, plus-minus, PIM, hits, power-play goals, shots on goal, faceoff "
                "%, blocked shots, shifts, giveaways, takeaways, and TOI. Goalies are in "
                "box_score_goalies(). Game ids come from scores(), schedule(), or player_game_log()."
            ),
            md="Gamecenter box score, skaters only. Available once a game starts.",
            schema=BOX_SCORE_SCHEMA,
            examples=_BOX_EXAMPLES,
        )
        examples = make_examples(_BOX_EXAMPLES)

    @classmethod
    def rows(cls, args: GameArgs) -> Rows:
        """Fetch skater lines."""
        response = api.web(f"gamecenter/{args.game_id}/boxscore")
        return flatten_box_score(api.require_dict(response), goalies=False), response.ttl


_GOALIE_BOX_EXAMPLES = [
    (
        "Goaltending in the 2025-26 opener.",
        "SELECT team_abbrev, player_name, decision, shots_against, saves, save_pct "
        "FROM nhl.main.box_score_goalies(2025020001)",
    )
]


@init_single_worker
@bind_fixed_schema
class BoxScoreGoaliesFunction(Fetching, TableFunctionGenerator[GameArgs]):
    """Goalie box-score lines for one game."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = BOX_SCORE_GOALIES_SCHEMA
    ESTIMATE, MAXIMUM = 4, 8

    class Meta:
        """Function discovery metadata."""

        name = "box_score_goalies"
        description = "Goalie box-score lines (both teams) for one NHL game"
        categories = [*_CATEGORIES, "box-score", "goalies"]
        projection_pushdown = True
        tags = make_tags(
            category="games",
            title="NHL Box Score (Goalies)",
            llm=(
                "One row per goalie dressed for a game: starter flag, decision (W/L/O), shots "
                "against, saves, goals against, save %, goals against by strength, and TOI. "
                "Backups who did not play have zero TOI."
            ),
            md="Gamecenter box score, goalies only.",
            schema=BOX_SCORE_GOALIES_SCHEMA,
            examples=_GOALIE_BOX_EXAMPLES,
        )
        examples = make_examples(_GOALIE_BOX_EXAMPLES)

    @classmethod
    def rows(cls, args: GameArgs) -> Rows:
        """Fetch goalie lines."""
        response = api.web(f"gamecenter/{args.game_id}/boxscore")
        return flatten_box_score(api.require_dict(response), goalies=True), response.ttl


_PBP_EXAMPLES = [
    (
        "Every goal in the 2025-26 opener with scorer and location.",
        "SELECT period, time_in_period, event_owner_team_abbrev, primary_player_name, shot_type, "
        "x_coord, y_coord, away_score, home_score FROM nhl.main.play_by_play(2025020001) "
        "WHERE event_type = 'goal' ORDER BY sort_order",
    ),
    (
        "Shot attempts by team and type of outcome.",
        "SELECT event_owner_team_abbrev, event_type, count(*) AS events "
        "FROM nhl.main.play_by_play(2025020001) "
        "WHERE event_type IN ('goal', 'shot-on-goal', 'missed-shot', 'blocked-shot') "
        "GROUP BY ALL ORDER BY ALL",
    ),
]


@init_single_worker
@bind_fixed_schema
class PlayByPlayFunction(Fetching, TableFunctionGenerator[GameArgs]):
    """Every event in one game with rink coordinates."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = PLAY_BY_PLAY_SCHEMA
    ESTIMATE, MAXIMUM = 350, 1_000

    class Meta:
        """Function discovery metadata."""

        name = "play_by_play"
        description = "Every event of one NHL game with x/y rink coordinates and involved players"
        categories = [*_CATEGORIES, "play-by-play", "shots"]
        projection_pushdown = True
        tags = make_tags(
            category="games",
            title="NHL Play-By-Play",
            llm=(
                "One row per game event in order (sort_order): faceoffs, shots on goal, missed and "
                "blocked shots, goals, hits, giveaways, takeaways, penalties, and stoppages, with "
                "period clock, game_seconds, situation code (strength), owning team, x/y rink "
                "coordinates in feet, shot type, and primary/secondary players with names. For a "
                "goal the primary player is the scorer and assists are in assist1/assist2."
            ),
            md=(
                "Gamecenter play-by-play. Coordinates are feet from centre ice; "
                "`situation_code` 1551 means 5-on-5 with both goalies in net."
            ),
            schema=PLAY_BY_PLAY_SCHEMA,
            examples=_PBP_EXAMPLES,
        )
        examples = make_examples(_PBP_EXAMPLES)

    @classmethod
    def rows(cls, args: GameArgs) -> Rows:
        """Fetch the play-by-play."""
        response = api.web(f"gamecenter/{args.game_id}/play-by-play")
        return flatten_play_by_play(api.require_dict(response, "plays")), response.ttl


_SHIFT_EXAMPLES = [
    (
        "Total ice time and shifts per player in the 2025-26 opener.",
        "SELECT team_abbrev, player_name, count(*) AS shifts, sum(duration_seconds) AS seconds "
        "FROM nhl.main.shift_chart(2025020001) GROUP BY ALL ORDER BY seconds DESC",
    )
]


@init_single_worker
@bind_fixed_schema
class ShiftChartFunction(Fetching, TableFunctionGenerator[GameArgs]):
    """Every player shift in one game."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = SHIFT_CHART_SCHEMA
    ESTIMATE, MAXIMUM = 850, 2_000

    class Meta:
        """Function discovery metadata."""

        name = "shift_chart"
        description = "Every player shift of one NHL game with start, end, and duration"
        categories = [*_CATEGORIES, "shifts"]
        projection_pushdown = True
        tags = make_tags(
            category="games",
            title="NHL Shift Chart",
            llm=(
                "One row per player shift in a game: player, team, period, shift number, start and "
                "end as period clock strings and as seconds since the opening faceoff, and "
                "duration. Join start_seconds/end_seconds with play_by_play().game_seconds to "
                "find who was on the ice for an event."
            ),
            md="NHL stats-service shift chart; goal markers in the source are omitted.",
            schema=SHIFT_CHART_SCHEMA,
            examples=_SHIFT_EXAMPLES,
        )
        examples = make_examples(_SHIFT_EXAMPLES)

    @classmethod
    def rows(cls, args: GameArgs) -> Rows:
        """Fetch the shift chart."""
        response = api.stats("shiftcharts", {"cayenneExp": f"gameId={args.game_id}"})
        return flatten_shift_chart(api.require_dict(response, "data")), response.ttl


GAME_FUNCTIONS = [BoxScoreFunction, BoxScoreGoaliesFunction, PlayByPlayFunction, ShiftChartFunction]
