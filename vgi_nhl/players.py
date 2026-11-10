"""Rosters, player pages, careers, game logs, and player search."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Annotated, ClassVar

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
from vgi_nhl.meta import TEAM_PATTERN
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

_CATEGORIES = ["hockey", "nhl", "players"]
_SEASON_IN_URL = re.compile(r"/(\d{8})(?:[/?]|$)")
_PLAYER_ID = Arg(
    0,
    arrow_type=pa.int32(),
    ge=8_000_000,
    le=9_999_999,
    doc="Stable 7-digit NHL player id, such as 8478402 (find one with player_search()).",
)


@dataclass(kw_only=True)
class RosterArgs:
    """A team code and optional season."""

    team: Annotated[
        str,
        Arg(0, arrow_type=pa.string(), pattern=TEAM_PATTERN, doc="Three-letter NHL team code, such as TOR."),
    ]
    season: Annotated[int | None, SEASON_ARG]


@dataclass(kw_only=True)
class PlayerArgs:
    """One player id."""

    player_id: Annotated[int, _PLAYER_ID]


@dataclass(kw_only=True)
class GameLogArgs:
    """A player id plus season and game type."""

    player_id: Annotated[int, _PLAYER_ID]
    season: Annotated[int | None, SEASON_ARG]
    game_type: Annotated[int, GAME_TYPE_ARG]


@dataclass(kw_only=True)
class SearchArgs:
    """A player-name search."""

    query: Annotated[
        str,
        Arg(0, arrow_type=pa.string(), pattern=r"\S", doc="Player name or part of one, such as 'mcdavid'."),
    ]
    active_only: Annotated[
        bool,
        Arg(
            "active_only",
            default=False,
            arrow_type=pa.bool_(),
            doc="Return only currently active players.",
        ),
    ]
    max_results: Annotated[
        int,
        Arg("max_results", default=25, arrow_type=pa.int32(), ge=1, le=100, doc="Maximum players to return."),
    ]


def _player(player_id: int) -> api.ApiResponse:
    return api.web(f"player/{player_id}/landing")


_ROSTER_EXAMPLES = [
    (
        "Toronto's 2025-26 defensemen.",
        "SELECT sweater_number, player_name, shoots_catches, height_inches, birth_country "
        "FROM nhl.main.roster('TOR', season := 20252026) WHERE position_group = 'defensemen' "
        "ORDER BY sweater_number",
    )
]


@init_single_worker
@bind_fixed_schema
class RosterFunction(Fetching, TableFunctionGenerator[RosterArgs]):
    """One team's roster for a season."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = ROSTER_SCHEMA
    ESTIMATE, MAXIMUM = 35, 80

    class Meta:
        """Function discovery metadata."""

        name = "roster"
        description = "One NHL team's roster for a season with positions and biographical detail"
        categories = [*_CATEGORIES, "teams", "rosters"]
        projection_pushdown = True
        tags = make_tags(
            category="players",
            title="NHL Team Roster",
            llm=(
                "Players on a team's roster: team code first ('TOR'), optional season := 20252026 "
                "(default current). Each row has player_id, name, sweater number, position and "
                "group (forwards, defensemen, goalies), handedness, size, and birth date and place. "
                "Historical seasons list everyone who appeared for the club."
            ),
            md="A club roster from NHL.com. The team code is positional; `season` is named.",
            schema=ROSTER_SCHEMA,
            examples=_ROSTER_EXAMPLES,
        )
        examples = make_examples(_ROSTER_EXAMPLES)

    @classmethod
    def rows(cls, args: RosterArgs) -> Rows:
        """Fetch the roster."""
        team = args.team.upper()
        if args.season is None:
            response = api.web(f"roster/{team}/current")
            match = _SEASON_IN_URL.search(response.url)
            season = int(match.group(1)) if match else None
        else:
            season = resolve_season(args.season)
            response = api.web(f"roster/{team}/{season}")
        return flatten_roster(api.require_dict(response), season=season, team=team), response.ttl


_PLAYER_EXAMPLES = [
    (
        "Connor McDavid's profile and NHL career totals.",
        "SELECT player_name, current_team_abbrev, position, birth_date, draft_year, draft_overall_pick, "
        "career_games_played, career_points FROM nhl.main.player(8478402)",
    )
]


@init_single_worker
@bind_fixed_schema
class PlayerFunction(Fetching, TableFunctionGenerator[PlayerArgs]):
    """One player's profile."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = PLAYER_SCHEMA
    ESTIMATE, MAXIMUM = 1, 1

    class Meta:
        """Function discovery metadata."""

        name = "player"
        description = "One NHL player's profile, draft details, and career NHL totals"
        categories = [*_CATEGORIES]
        projection_pushdown = True
        tags = make_tags(
            category="players",
            title="NHL Player Profile",
            llm=(
                "A single row for one player id: name, active flag, current team, position, "
                "handedness, size, birth date and place, draft year/round/pick, Hall of Fame flag, "
                "and NHL career regular-season totals (skater goals/assists/points or goalie "
                "wins/shutouts/save %/GAA) plus playoff games and points."
            ),
            md="An NHL.com player landing page as one row.",
            schema=PLAYER_SCHEMA,
            examples=_PLAYER_EXAMPLES,
        )
        examples = make_examples(_PLAYER_EXAMPLES)

    @classmethod
    def rows(cls, args: PlayerArgs) -> Rows:
        """Fetch the player profile."""
        response = _player(args.player_id)
        return flatten_player(api.require_dict(response, "playerId")), response.ttl


_CAREER_EXAMPLES = [
    (
        "Connor McDavid's NHL regular-season lines by season.",
        "SELECT season, team_name, games_played, goals, assists, points "
        "FROM nhl.main.player_career(8478402) WHERE league_abbrev = 'NHL' AND game_type = 2 "
        "ORDER BY season",
    )
]


@init_single_worker
@bind_fixed_schema
class PlayerCareerFunction(Fetching, TableFunctionGenerator[PlayerArgs]):
    """One player's season-by-season career."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = CAREER_SCHEMA
    ESTIMATE, MAXIMUM = 30, 200

    class Meta:
        """Function discovery metadata."""

        name = "player_career"
        description = "One player's season-by-season lines in every league, regular season and playoffs"
        categories = [*_CATEGORIES, "career"]
        projection_pushdown = True
        tags = make_tags(
            category="players",
            title="NHL Player Career Lines",
            llm=(
                "Season-by-season lines for one player id across every league (NHL, AHL, junior, "
                "Olympics...), regular season (game_type 2) and playoffs (3). Filter league_abbrev "
                "= 'NHL' for NHL totals. Skater columns (goals, points, shots) and goalie columns "
                "(wins, save_pct, goals_against_average) share the table; the other set is NULL."
            ),
            md="Every season line from the player's NHL.com page, including pre-NHL leagues.",
            schema=CAREER_SCHEMA,
            examples=_CAREER_EXAMPLES,
        )
        examples = make_examples(_CAREER_EXAMPLES)

    @classmethod
    def rows(cls, args: PlayerArgs) -> Rows:
        """Fetch the career lines."""
        response = _player(args.player_id)
        return flatten_career(api.require_dict(response, "playerId")), response.ttl


_GAME_LOG_EXAMPLES = [
    (
        "Connor McDavid's multi-point games in 2025-26.",
        "SELECT game_date, opponent_abbrev, goals, assists, points, toi "
        "FROM nhl.main.player_game_log(8478402, season := 20252026) WHERE points >= 2 "
        "ORDER BY game_date",
    )
]


@init_single_worker
@bind_fixed_schema
class PlayerGameLogFunction(Fetching, TableFunctionGenerator[GameLogArgs]):
    """One player's per-game log for a season."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = GAME_LOG_SCHEMA
    ESTIMATE, MAXIMUM = 82, 120

    class Meta:
        """Function discovery metadata."""

        name = "player_game_log"
        description = "One NHL player's game-by-game log for a season and game type"
        categories = [*_CATEGORIES, "game-log"]
        projection_pushdown = True
        tags = make_tags(
            category="players",
            title="NHL Player Game Log",
            llm=(
                "One row per game a player appeared in: player id first, optional season := "
                "20252026 (default current) and game_type := 2 or 3. Skaters get goals, assists, "
                "points, plus-minus, shots, shifts, and TOI; goalies get decision, shots against, "
                "goals against, save %, and shutouts. game_id joins to box_score()."
            ),
            md="An NHL.com player game log. Rows are newest-first from the source; sort by `game_date`.",
            schema=GAME_LOG_SCHEMA,
            examples=_GAME_LOG_EXAMPLES,
        )
        examples = make_examples(_GAME_LOG_EXAMPLES)

    @classmethod
    def rows(cls, args: GameLogArgs) -> Rows:
        """Fetch the game log."""
        season = resolve_season(args.season)
        response = api.web(f"player/{args.player_id}/game-log/{season}/{args.game_type}")
        payload = api.require_dict(response, "gameLog")
        rows = flatten_game_log(payload, player_id=args.player_id, season=season, game_type=args.game_type)
        return rows, response.ttl


_SEARCH_EXAMPLES = [
    (
        "Find players named Hughes who are active.",
        "SELECT player_id, player_name, position_code, team_abbrev "
        "FROM nhl.main.player_search('hughes', active_only := true)",
    )
]


@init_single_worker
@bind_fixed_schema
class PlayerSearchFunction(Fetching, TableFunctionGenerator[SearchArgs]):
    """Find player ids by name."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = SEARCH_SCHEMA
    ESTIMATE, MAXIMUM = 10, 100

    class Meta:
        """Function discovery metadata."""

        name = "player_search"
        description = "Find NHL players (current and historical) by name to get their player ids"
        categories = [*_CATEGORIES, "search"]
        projection_pushdown = True
        tags = make_tags(
            category="players",
            title="NHL Player Search",
            llm=(
                "Name search over every NHL player, past and present. Pass the name text first "
                "('mcdavid'); returns player_id (for player(), player_career(), player_game_log()), "
                "position, active flag, and current or last team. active_only := true drops "
                "retired players."
            ),
            md="The NHL.com player search index. Matching is the NHL's own fuzzy name match.",
            schema=SEARCH_SCHEMA,
            examples=_SEARCH_EXAMPLES,
        )
        examples = make_examples(_SEARCH_EXAMPLES)

    @classmethod
    def rows(cls, args: SearchArgs) -> Rows:
        """Run the search."""
        params: dict[str, str | int] = {
            "culture": "en-us",
            "limit": args.max_results,
            "q": args.query.strip(),
        }
        if args.active_only:
            params["active"] = "true"
        response = api.search("search/player", params)
        return flatten_search(response.payload), response.ttl


PLAYER_FUNCTIONS = [
    RosterFunction,
    PlayerFunction,
    PlayerCareerFunction,
    PlayerGameLogFunction,
    PlayerSearchFunction,
]
