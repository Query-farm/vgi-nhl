"""Standings, schedules, scores, brackets, drafts, and league reference functions."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Annotated, ClassVar

import pyarrow as pa
from vgi.arguments import Arg
from vgi.table_function import TableFunctionGenerator, bind_fixed_schema, init_single_worker

from vgi_nhl import api
from vgi_nhl.base import SEASON_ARG, Fetching, Rows, make_examples, make_tags, resolve_season
from vgi_nhl.league_schemas import (
    BRACKET_SCHEMA,
    DRAFT_SCHEMA,
    FRANCHISES_SCHEMA,
    GAMES_SCHEMA,
    STANDINGS_SCHEMA,
    STANDINGS_SEASONS_SCHEMA,
    TEAMS_SCHEMA,
    flatten_bracket,
    flatten_draft,
    flatten_franchises,
    flatten_games,
    flatten_schedule,
    flatten_standings,
    flatten_standings_seasons,
    flatten_teams,
)
from vgi_nhl.meta import TEAM_PATTERN

_CATEGORIES = ["hockey", "nhl"]

_CURRENT_STANDINGS_SCAN_EXAMPLES = [
    (
        "Division leaders from the backing scan.",
        "SELECT division_name, team_abbrev, points FROM nhl.main.all_current_standings() "
        "WHERE division_rank = 1 ORDER BY division_name",
    )
]
_CURRENT_SCHEDULE_SCAN_EXAMPLES = [
    (
        "Upcoming games from the backing scan.",
        "SELECT game_date, away_team_abbrev, home_team_abbrev "
        "FROM nhl.main.all_current_schedule() ORDER BY start_time_utc",
    )
]
_CURRENT_SCORES_SCAN_EXAMPLES = [
    (
        "Today's games from the backing scan.",
        "SELECT away_team_abbrev, away_score, home_team_abbrev, home_score, game_state "
        "FROM nhl.main.all_current_scores()",
    )
]


def _day(value: dt.date | None) -> str:
    return value.isoformat() if value is not None else "now"


def standings_rows(on: dt.date | None) -> Rows:
    """Standings for a date (NULL = today)."""
    response = api.web(f"standings/{_day(on)}")
    return flatten_standings(api.require_dict(response, "standings")), response.ttl


def schedule_rows(on: dt.date | None) -> Rows:
    """The seven-day schedule week starting on a date (NULL = today)."""
    response = api.web(f"schedule/{_day(on)}")
    return flatten_schedule(api.require_dict(response, "gameWeek")), response.ttl


def scores_rows(on: dt.date | None) -> Rows:
    """One day's games with live or final scores (NULL = today)."""
    response = api.web(f"score/{_day(on)}")
    return flatten_games(api.require_dict(response, "games")), response.ttl


@dataclass(kw_only=True)
class DateArgs:
    """An optional calendar date."""

    date: Annotated[
        dt.date | None,
        Arg(
            "date",
            default=None,
            arrow_type=pa.date32(),
            doc="Day to report, for example 2025-10-07. NULL selects today (the NHL's own 'now').",
        ),
    ]


@dataclass(kw_only=True)
class TeamSeasonArgs:
    """A team code and optional season."""

    team: Annotated[
        str,
        Arg(0, arrow_type=pa.string(), pattern=TEAM_PATTERN, doc="Three-letter NHL team code, such as TOR."),
    ]
    season: Annotated[int | None, SEASON_ARG]


@dataclass(kw_only=True)
class YearArgs:
    """A calendar year."""

    year: Annotated[int, Arg(0, arrow_type=pa.int32(), ge=1918, le=2100, doc="Calendar year.")]


@dataclass(kw_only=True)
class DraftArgs:
    """A draft year."""

    year: Annotated[
        int,
        Arg(0, arrow_type=pa.int32(), ge=1979, le=2100, doc="NHL entry draft year (1979 onward)."),
    ]


_STANDINGS_EXAMPLES = [
    (
        "Final 2023-24 Atlantic Division table.",
        "SELECT division_rank, team_name, wins, losses, ot_losses, points "
        "FROM nhl.main.standings(date := DATE '2024-04-18') "
        "WHERE division_name = 'Atlantic' ORDER BY division_rank",
    ),
]


@init_single_worker
@bind_fixed_schema
class StandingsFunction(Fetching, TableFunctionGenerator[DateArgs]):
    """NHL standings as of a date."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = STANDINGS_SCHEMA
    ESTIMATE, MAXIMUM = 32, 40

    class Meta:
        """Function discovery metadata."""

        name = "standings"
        description = "NHL standings on any date back to 1917-18, one row per team"
        categories = [*_CATEGORIES, "standings"]
        projection_pushdown = True
        tags = make_tags(
            category="standings",
            title="NHL Standings By Date",
            llm=(
                "League standings as they stood on a date, one row per team: points, record "
                "(wins, regulation losses, OT losses), point percentage, regulation wins, goal "
                "differential, home/road/last-10 splits, streak, conference/division/wild-card "
                "ranks, and clinch markers. Pass the day as the named date argument (see the "
                "example); a season's final standings are on its last regular-season day, listed "
                "in the standings_seasons table."
            ),
            md=(
                "NHL standings snapshot for `date` (default today). Ranks come from the NHL's own "
                "ordering, so `division_rank = 1` is the division leader. Older seasons have no "
                "conferences, divisions, or OT losses; those columns are NULL or zero."
            ),
            schema=STANDINGS_SCHEMA,
            examples=_STANDINGS_EXAMPLES,
        )
        examples = make_examples(_STANDINGS_EXAMPLES)

    @classmethod
    def rows(cls, args: DateArgs) -> Rows:
        """Fetch standings for the requested date."""
        return standings_rows(args.date)


@init_single_worker
@bind_fixed_schema
class CurrentStandingsFunction(Fetching, TableFunctionGenerator[None]):
    """Today's standings, backing the ``current_standings`` table."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = STANDINGS_SCHEMA
    ESTIMATE, MAXIMUM = 32, 40

    class Meta:
        """Function discovery metadata."""

        name = "all_current_standings"
        description = "Today's NHL standings (scan behind current_standings)"
        categories = [*_CATEGORIES, "standings"]
        projection_pushdown = True
        tags = make_tags(
            category="standings",
            title="Current NHL Standings Scan",
            llm=(
                "The scan behind the current_standings table. Prefer the table; use standings() "
                "with a date for historical standings."
            ),
            md="Returns today's standings. Selecting `current_standings` is normally clearer.",
            schema=STANDINGS_SCHEMA,
            examples=_CURRENT_STANDINGS_SCAN_EXAMPLES,
        )
        examples = make_examples(_CURRENT_STANDINGS_SCAN_EXAMPLES)

    @classmethod
    def rows(cls, args: None) -> Rows:
        """Fetch today's standings."""
        return standings_rows(None)


_SEASONS_EXAMPLES = [
    (
        "Seasons whose standings used the wild card, newest first.",
        "SELECT season, standings_start, standings_end FROM nhl.main.all_standings_seasons() "
        "WHERE wildcard_in_use ORDER BY season DESC",
    )
]


@init_single_worker
@bind_fixed_schema
class StandingsSeasonsFunction(Fetching, TableFunctionGenerator[None]):
    """Every NHL season with its standings window and rule flags."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = STANDINGS_SEASONS_SCHEMA
    ESTIMATE, MAXIMUM = 110, 200

    class Meta:
        """Function discovery metadata."""

        name = "all_standings_seasons"
        description = "Every NHL season with standings dates and rule flags (scan behind standings_seasons)"
        categories = [*_CATEGORIES, "standings", "seasons"]
        projection_pushdown = True
        tags = make_tags(
            category="standings",
            title="NHL Seasons",
            llm=(
                "One row per NHL season id (e.g. 20252026) with the first and last standings dates "
                "and which rules applied: ties, OT-loss point, regulation wins, wild card, "
                "conferences, divisions. Use standings_end as the date for a season's final "
                "standings, and season ids as the season argument of other functions. Prefer the "
                "standings_seasons table; this is its backing scan."
            ),
            md="Season ids, standings windows, and rule flags since 1917-18.",
            schema=STANDINGS_SEASONS_SCHEMA,
            examples=_SEASONS_EXAMPLES,
        )
        examples = make_examples(_SEASONS_EXAMPLES)

    @classmethod
    def rows(cls, args: None) -> Rows:
        """Fetch the season list."""
        response = api.web("standings-season")
        return flatten_standings_seasons(api.require_dict(response, "seasons")), response.ttl


_SCHEDULE_EXAMPLES = [
    (
        "The first week of the 2025-26 regular season.",
        "SELECT game_date, away_team_abbrev, home_team_abbrev, away_score, home_score "
        "FROM nhl.main.schedule(date := DATE '2025-10-07') ORDER BY start_time_utc",
    )
]


@init_single_worker
@bind_fixed_schema
class ScheduleFunction(Fetching, TableFunctionGenerator[DateArgs]):
    """The seven-day NHL schedule week starting on a date."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = GAMES_SCHEMA
    ESTIMATE, MAXIMUM = 50, 120

    class Meta:
        """Function discovery metadata."""

        name = "schedule"
        description = "NHL games in the seven days starting on a date, one row per game"
        categories = [*_CATEGORIES, "schedule"]
        projection_pushdown = True
        tags = make_tags(
            category="schedule",
            title="NHL Schedule Week",
            llm=(
                "Every NHL game in the seven days starting on date (default today): game id, "
                "local date, UTC start time, venue, teams, state, and final scores with the "
                "winning goalie and game-winning scorer once played. For one day only with "
                "shots on goal use scores(); for a team's full season use team_schedule()."
            ),
            md=(
                "A seven-day schedule window. `game_state` is FUT before, LIVE/CRIT during, and "
                "OFF/FINAL after a game; scores are NULL until the game starts."
            ),
            schema=GAMES_SCHEMA,
            examples=_SCHEDULE_EXAMPLES,
        )
        examples = make_examples(_SCHEDULE_EXAMPLES)

    @classmethod
    def rows(cls, args: DateArgs) -> Rows:
        """Fetch the schedule week."""
        return schedule_rows(args.date)


@init_single_worker
@bind_fixed_schema
class CurrentScheduleFunction(Fetching, TableFunctionGenerator[None]):
    """This week's schedule, backing the ``current_schedule`` table."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = GAMES_SCHEMA
    ESTIMATE, MAXIMUM = 50, 120

    class Meta:
        """Function discovery metadata."""

        name = "all_current_schedule"
        description = "NHL games in the seven days starting today (scan behind current_schedule)"
        categories = [*_CATEGORIES, "schedule"]
        projection_pushdown = True
        tags = make_tags(
            category="schedule",
            title="Current NHL Schedule Scan",
            llm="The scan behind current_schedule. Prefer the table; use schedule() for other weeks.",
            md="Returns this week's games. Selecting `current_schedule` is normally clearer.",
            schema=GAMES_SCHEMA,
            examples=_CURRENT_SCHEDULE_SCAN_EXAMPLES,
        )
        examples = make_examples(_CURRENT_SCHEDULE_SCAN_EXAMPLES)

    @classmethod
    def rows(cls, args: None) -> Rows:
        """Fetch this week's schedule."""
        return schedule_rows(None)


_SCORES_EXAMPLES = [
    (
        "Opening night of 2025-26 with shots on goal.",
        "SELECT away_team_abbrev, away_score, home_team_abbrev, home_score, last_period_type "
        "FROM nhl.main.scores(date := DATE '2025-10-07') ORDER BY start_time_utc",
    )
]


@init_single_worker
@bind_fixed_schema
class ScoresFunction(Fetching, TableFunctionGenerator[DateArgs]):
    """One day's NHL games with live or final scores."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = GAMES_SCHEMA
    ESTIMATE, MAXIMUM = 8, 20

    class Meta:
        """Function discovery metadata."""

        name = "scores"
        description = "NHL games on one date with live or final scores and shots on goal"
        categories = [*_CATEGORIES, "schedule", "scores"]
        projection_pushdown = True
        tags = make_tags(
            category="schedule",
            title="NHL Scores By Date",
            llm=(
                "Games on a single date (default today) with score, shots on goal, current or "
                "final period, and how the game ended (REG, OT, SO). Use game_id with box_score() "
                "or play_by_play() for detail."
            ),
            md="One day's scoreboard. Live games report the current period and running score.",
            schema=GAMES_SCHEMA,
            examples=_SCORES_EXAMPLES,
        )
        examples = make_examples(_SCORES_EXAMPLES)

    @classmethod
    def rows(cls, args: DateArgs) -> Rows:
        """Fetch the day's scoreboard."""
        return scores_rows(args.date)


@init_single_worker
@bind_fixed_schema
class CurrentScoresFunction(Fetching, TableFunctionGenerator[None]):
    """Today's scoreboard, backing the ``current_scores`` table."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = GAMES_SCHEMA
    ESTIMATE, MAXIMUM = 8, 20

    class Meta:
        """Function discovery metadata."""

        name = "all_current_scores"
        description = "Today's NHL games with live or final scores (scan behind current_scores)"
        categories = [*_CATEGORIES, "schedule", "scores"]
        projection_pushdown = True
        tags = make_tags(
            category="schedule",
            title="Current NHL Scores Scan",
            llm="The scan behind current_scores. Prefer the table; use scores() for another date.",
            md="Returns today's scoreboard. Selecting `current_scores` is normally clearer.",
            schema=GAMES_SCHEMA,
            examples=_CURRENT_SCORES_SCAN_EXAMPLES,
        )
        examples = make_examples(_CURRENT_SCORES_SCAN_EXAMPLES)

    @classmethod
    def rows(cls, args: None) -> Rows:
        """Fetch today's scoreboard."""
        return scores_rows(None)


_TEAM_SCHEDULE_EXAMPLES = [
    (
        "Toronto's 2025-26 regular-season home results.",
        "SELECT game_date, away_team_abbrev, away_score, home_score "
        "FROM nhl.main.team_schedule('TOR', season := 20252026) "
        "WHERE game_type = 2 AND home_team_abbrev = 'TOR' ORDER BY game_date",
    )
]


@init_single_worker
@bind_fixed_schema
class TeamScheduleFunction(Fetching, TableFunctionGenerator[TeamSeasonArgs]):
    """One team's full season schedule and results."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = GAMES_SCHEMA
    ESTIMATE, MAXIMUM = 90, 130

    class Meta:
        """Function discovery metadata."""

        name = "team_schedule"
        description = "One NHL team's full season schedule and results, including preseason and playoffs"
        categories = [*_CATEGORIES, "schedule", "teams"]
        projection_pushdown = True
        tags = make_tags(
            category="schedule",
            title="NHL Team Season Schedule",
            llm=(
                "Every game of one team's season: team code first (e.g. 'TOR'), optional "
                "season := 20252026 (default current). Includes preseason (game_type 1), regular "
                "season (2), and playoffs (3) with final scores, so filter game_type = 2 for the "
                "82-game schedule."
            ),
            md="A club's season schedule. The team code is positional; `season` is named.",
            schema=GAMES_SCHEMA,
            examples=_TEAM_SCHEDULE_EXAMPLES,
        )
        examples = make_examples(_TEAM_SCHEDULE_EXAMPLES)

    @classmethod
    def rows(cls, args: TeamSeasonArgs) -> Rows:
        """Fetch the club's season schedule."""
        season = str(resolve_season(args.season)) if args.season is not None else "now"
        response = api.web(f"club-schedule-season/{args.team.upper()}/{season}")
        return flatten_games(api.require_dict(response, "games")), response.ttl


_BRACKET_EXAMPLES = [
    (
        "The 2025 playoff bracket by round.",
        "SELECT playoff_round, series_letter, top_seed_team_abbrev, top_seed_wins, "
        "bottom_seed_team_abbrev, bottom_seed_wins FROM nhl.main.playoff_bracket(2025) "
        "ORDER BY series_letter",
    )
]


@init_single_worker
@bind_fixed_schema
class PlayoffBracketFunction(Fetching, TableFunctionGenerator[YearArgs]):
    """One year's Stanley Cup playoff bracket."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = BRACKET_SCHEMA
    ESTIMATE, MAXIMUM = 15, 30

    class Meta:
        """Function discovery metadata."""

        name = "playoff_bracket"
        description = "Stanley Cup playoff series for one year with seeds, series wins, and winners"
        categories = [*_CATEGORIES, "playoffs"]
        projection_pushdown = True
        tags = make_tags(
            category="playoffs",
            title="NHL Playoff Bracket",
            llm=(
                "Playoff series for a year (the calendar year of the final, e.g. 2025 for the "
                "2024-25 playoffs): round, seeds, games won by each side, and winning/losing team "
                "ids. The Stanley Cup Final is series_abbrev = 'SCF'; its winning_team_id is the "
                "champion. Empty before the playoffs begin."
            ),
            md="One row per playoff series, lettered A-O in bracket order.",
            schema=BRACKET_SCHEMA,
            examples=_BRACKET_EXAMPLES,
        )
        examples = make_examples(_BRACKET_EXAMPLES)

    @classmethod
    def rows(cls, args: YearArgs) -> Rows:
        """Fetch the bracket."""
        response = api.web(f"playoff-bracket/{args.year}")
        return flatten_bracket(api.require_dict(response), args.year), response.ttl


_DRAFT_EXAMPLES = [
    (
        "The first round of the 2025 NHL draft.",
        "SELECT overall_pick, team_abbrev, player_name, position_code, amateur_club_name "
        "FROM nhl.main.draft_picks(2025) WHERE round = 1 ORDER BY overall_pick",
    )
]


@init_single_worker
@bind_fixed_schema
class DraftPicksFunction(Fetching, TableFunctionGenerator[DraftArgs]):
    """Every pick of one NHL entry draft."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = DRAFT_SCHEMA
    ESTIMATE, MAXIMUM = 224, 400

    class Meta:
        """Function discovery metadata."""

        name = "draft_picks"
        description = "Every pick of one NHL entry draft (1979 onward)"
        categories = [*_CATEGORIES, "draft"]
        projection_pushdown = True
        tags = make_tags(
            category="draft",
            title="NHL Draft Picks",
            llm=(
                "All picks in one entry draft year: round, pick in round, overall pick, selecting "
                "team (with pick-trade history), and the drafted player's position, nationality, "
                "size, and amateur club. The draft's players have no NHL player id here; use "
                "player_search() to find one."
            ),
            md="One row per draft pick, ordered by `overall_pick`.",
            schema=DRAFT_SCHEMA,
            examples=_DRAFT_EXAMPLES,
        )
        examples = make_examples(_DRAFT_EXAMPLES)

    @classmethod
    def rows(cls, args: DraftArgs) -> Rows:
        """Fetch the draft."""
        response = api.web(f"draft/picks/{args.year}/all")
        return flatten_draft(api.require_dict(response, "picks")), response.ttl


_TEAMS_EXAMPLES = [
    (
        "Every team that has played for the Avalanche/Nordiques franchise.",
        "SELECT t.team_id, t.full_name, t.tricode FROM nhl.main.all_teams() t "
        "JOIN nhl.main.all_franchises() f USING (franchise_id) WHERE f.common_name = 'Avalanche'",
    )
]


@init_single_worker
@bind_fixed_schema
class TeamsFunction(Fetching, TableFunctionGenerator[None]):
    """Every current and historical NHL team."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = TEAMS_SCHEMA
    ESTIMATE, MAXIMUM = 62, 200

    class Meta:
        """Function discovery metadata."""

        name = "all_teams"
        description = "Every current and historical NHL team (scan behind the teams table)"
        categories = [*_CATEGORIES, "teams", "reference"]
        projection_pushdown = True
        tags = make_tags(
            category="reference",
            title="NHL Teams",
            llm=(
                "Reference list of NHL team ids (the team_id used by team_stats(), scores, and box "
                "scores), three-letter tricodes, full names, and franchise ids. Includes relocated "
                "and defunct teams; join franchises on franchise_id to group relocations. Prefer the "
                "teams table; this is its backing scan."
            ),
            md="Current and historical teams from the NHL stats service.",
            schema=TEAMS_SCHEMA,
            examples=_TEAMS_EXAMPLES,
        )
        examples = make_examples(_TEAMS_EXAMPLES)

    @classmethod
    def rows(cls, args: None) -> Rows:
        """Fetch the team list."""
        response = api.stats("team")
        return flatten_teams(api.require_dict(response, "data")), response.ttl


_FRANCHISES_EXAMPLES = [
    (
        "All NHL franchises alphabetically.",
        "SELECT franchise_id, full_name FROM nhl.main.all_franchises() ORDER BY full_name",
    )
]


@init_single_worker
@bind_fixed_schema
class FranchisesFunction(Fetching, TableFunctionGenerator[None]):
    """Every NHL franchise."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = FRANCHISES_SCHEMA
    ESTIMATE, MAXIMUM = 40, 100

    class Meta:
        """Function discovery metadata."""

        name = "all_franchises"
        description = "Every NHL franchise, active and defunct (scan behind the franchises table)"
        categories = [*_CATEGORIES, "teams", "reference"]
        projection_pushdown = True
        tags = make_tags(
            category="reference",
            title="NHL Franchises",
            llm=(
                "One row per franchise with its latest name. A franchise spans relocations and "
                "renames (e.g. Quebec Nordiques to Colorado Avalanche); the teams table maps team ids to "
                "franchise ids."
            ),
            md="Active and defunct franchises from the NHL stats service.",
            schema=FRANCHISES_SCHEMA,
            examples=_FRANCHISES_EXAMPLES,
        )
        examples = make_examples(_FRANCHISES_EXAMPLES)

    @classmethod
    def rows(cls, args: None) -> Rows:
        """Fetch the franchise list."""
        response = api.stats("franchise")
        return flatten_franchises(api.require_dict(response, "data")), response.ttl


LEAGUE_FUNCTIONS = [
    StandingsFunction,
    CurrentStandingsFunction,
    StandingsSeasonsFunction,
    ScheduleFunction,
    CurrentScheduleFunction,
    ScoresFunction,
    CurrentScoresFunction,
    TeamScheduleFunction,
    PlayoffBracketFunction,
    DraftPicksFunction,
    TeamsFunction,
    FranchisesFunction,
]
