"""VGI worker exposing NHL standings, schedules, game detail, and statistics as a SQL catalog."""

from __future__ import annotations

import json
import os
import sys

from vgi import Worker
from vgi.catalog import Catalog, ConstraintInfo, Schema, Table, constraint_record

from vgi_nhl.games import GAME_FUNCTIONS, ON_ICE_GOALS_EXAMPLE
from vgi_nhl.league import (
    LEAGUE_FUNCTIONS,
    CurrentScheduleFunction,
    CurrentScoresFunction,
    CurrentStandingsFunction,
    FranchisesFunction,
    StandingsSeasonsFunction,
    TeamsFunction,
)
from vgi_nhl.league_schemas import (
    FRANCHISES_SCHEMA,
    GAMES_SCHEMA,
    LEADERS_SCHEMA,
    STANDINGS_SCHEMA,
    STANDINGS_SEASONS_SCHEMA,
    TEAMS_SCHEMA,
)
from vgi_nhl.meta import column_comments
from vgi_nhl.players import PLAYER_FUNCTIONS, ROSTER_SCORING_EXAMPLE
from vgi_nhl.stats import (
    POWER_FORWARDS_EXAMPLE,
    STATS_FUNCTIONS,
    CurrentGoalieLeadersFunction,
    CurrentSkaterLeadersFunction,
)

SOURCE_URL = "https://github.com/Query-farm/vgi-nhl"


def _example_queries(queries: list[tuple[str, str]]) -> str:
    return json.dumps([{"description": description, "sql": sql} for description, sql in queries])


def _table_tags(
    *, category: str, title: str, keywords: list[str], llm: str, md: str, queries: list[tuple[str, str]]
) -> dict[str, str]:
    return {
        "provider": "nhl",
        "vgi.category": category,
        "vgi.title": title,
        "vgi.keywords": json.dumps(keywords),
        "vgi.doc_llm": llm,
        "vgi.doc_md": md,
        "vgi.example_queries": _example_queries(queries),
    }


_CURRENT_STANDINGS_QUERIES = [
    (
        "Current division tables in official order.",
        "SELECT division_name, division_rank, team_abbrev, points, games_played "
        "FROM nhl.main.current_standings ORDER BY division_name, division_rank",
    ),
    (
        "Eastern Conference wild-card race.",
        "SELECT wildcard_rank, team_abbrev, points, games_played FROM nhl.main.current_standings "
        "WHERE conference_name = 'Eastern' AND wildcard_rank > 0 ORDER BY wildcard_rank",
    ),
]

# Examples that combine several of the catalog's functions; each is also on the example list of
# the function that drives it, where agents discover function examples.
_COMPOSED_QUERIES = [ON_ICE_GOALS_EXAMPLE, ROSTER_SCORING_EXAMPLE, POWER_FORWARDS_EXAMPLE]

_CURRENT_STANDINGS_TAGS = _table_tags(
    category="standings",
    title="Current NHL Standings",
    keywords=["standings", "points", "division race", "wild card", "playoff race"],
    llm=(
        "Today's NHL standings, one row per team. Start here for points, record (W-L-OTL), "
        "point percentage, goal differential, division/conference/wild-card rank, streaks, and "
        "clinch markers. For standings on another date call standings(date := ...)."
    ),
    md=(
        "Today's NHL standings as an ordinary read-only table. `division_rank`, "
        "`conference_rank`, and `league_rank` follow the NHL's official tiebreaking order."
    ),
    queries=_CURRENT_STANDINGS_QUERIES,
)

_CURRENT_SCHEDULE_TAGS = _table_tags(
    category="schedule",
    title="This Week's NHL Schedule",
    keywords=["schedule", "games", "fixtures", "this week", "upcoming games"],
    llm=(
        "Every NHL game in the seven days starting today, one row per game, with start time, "
        "teams, venue, state, and scores once played. Use schedule(date := ...) for another week "
        "and team_schedule() for one club's season."
    ),
    md="This week's NHL games as a read-only table. Scores are NULL until a game starts.",
    queries=[
        (
            "This week's games in start order.",
            "SELECT game_date, start_time_utc, away_team_abbrev, home_team_abbrev, venue "
            "FROM nhl.main.current_schedule ORDER BY start_time_utc",
        )
    ],
)

_CURRENT_SCORES_TAGS = _table_tags(
    category="schedule",
    title="Today's NHL Scores",
    keywords=["scores", "scoreboard", "today", "live scores", "results"],
    llm=(
        "Today's NHL scoreboard, one row per game: state (FUT, LIVE, CRIT, OFF), score, shots on "
        "goal, period, and how a finished game ended. Use scores(date := ...) for another day "
        "and box_score(game_id) for detail."
    ),
    md="Today's NHL games with live or final scores.",
    queries=[
        (
            "Today's scoreboard.",
            "SELECT away_team_abbrev, away_score, home_team_abbrev, home_score, game_state, period "
            "FROM nhl.main.current_scores ORDER BY start_time_utc",
        )
    ],
)

_CURRENT_SKATER_LEADERS_TAGS = _table_tags(
    category="leaders",
    title="Current NHL Skater Leaders",
    keywords=["leaders", "scoring leaders", "Art Ross", "goals", "assists", "points"],
    llm=(
        "The NHL's current top ten skaters in each category (points, goals, assists, plusMinus, "
        "goalsPp, goalsSh, penaltyMins, faceoffLeaders, toi), one row per category and rank with "
        "the stat in value. During the playoffs the NHL reports playoff leaders (game_type 3)."
    ),
    md="Current skater leaderboards in long format: filter on `category`.",
    queries=[
        (
            "Current scoring race.",
            "SELECT rank, player_name, team_abbrev, value AS points "
            "FROM nhl.main.current_skater_leaders WHERE category = 'points' ORDER BY rank",
        )
    ],
)

_CURRENT_GOALIE_LEADERS_TAGS = _table_tags(
    category="leaders",
    title="Current NHL Goalie Leaders",
    keywords=["goalie leaders", "save percentage", "GAA", "shutouts", "wins", "Vezina"],
    llm=(
        "The NHL's current top ten goalies in each category (wins, savePctg, goalsAgainstAverage, "
        "shutouts), one row per category and rank with the stat in value."
    ),
    md="Current goalie leaderboards in long format: filter on `category`.",
    queries=[
        (
            "Current save-percentage leaders.",
            "SELECT rank, player_name, team_abbrev, value AS save_pct "
            "FROM nhl.main.current_goalie_leaders WHERE category = 'savePctg' ORDER BY rank",
        )
    ],
)

_STANDINGS_SEASONS_TAGS = _table_tags(
    category="standings",
    title="NHL Seasons",
    keywords=["seasons", "season ids", "rules", "wild card", "ties"],
    llm=(
        "One row per NHL season id (e.g. 20252026) since 1917-18 with the first and last standings "
        "dates and which rules applied: ties, OT-loss point, regulation wins, wild card, "
        "conferences, divisions. Use standings_end as the day for a season's final standings and "
        "season ids as the season argument of other functions."
    ),
    md="Season ids, standings windows, and rule flags since 1917-18.",
    queries=[
        (
            "Seasons whose standings used the wild card, newest first.",
            "SELECT season, standings_start, standings_end FROM nhl.main.standings_seasons "
            "WHERE wildcard_in_use ORDER BY season DESC",
        )
    ],
)

_TEAMS_TAGS = _table_tags(
    category="reference",
    title="NHL Teams",
    keywords=["teams", "team ids", "tricodes", "relocations"],
    llm=(
        "Reference list of NHL team ids (the team_id used by team_stats(), scores, and box scores), "
        "three-letter tricodes, full names, and franchise ids, including relocated and defunct "
        "teams. Join franchises on franchise_id to group relocations."
    ),
    md="Current and historical teams from the NHL stats service.",
    queries=[
        (
            "Every team that has played for the Avalanche/Nordiques franchise.",
            "SELECT t.team_id, t.full_name, t.tricode FROM nhl.main.teams t "
            "JOIN nhl.main.franchises f USING (franchise_id) WHERE f.common_name = 'Avalanche'",
        )
    ],
)

_FRANCHISES_TAGS = _table_tags(
    category="reference",
    title="NHL Franchises",
    keywords=["franchises", "history", "relocations", "defunct teams"],
    llm=(
        "One row per NHL franchise with its latest name. A franchise spans relocations and renames "
        "(Quebec Nordiques to Colorado Avalanche); the teams table maps team ids to franchise ids."
    ),
    md="Active and defunct franchises from the NHL stats service.",
    queries=[
        (
            "All NHL franchises alphabetically.",
            "SELECT franchise_id, full_name FROM nhl.main.franchises ORDER BY full_name",
        )
    ],
)

_EXECUTABLE_EXAMPLES = json.dumps(
    [
        {
            "name": "opener_final_score",
            "description": "The 2025-26 opener (game 2025020001) ended Florida 3, Chicago 2.",
            "sql": (
                "SELECT home_team_abbrev, home_score, away_team_abbrev, away_score "
                "FROM nhl.main.scores(date := DATE '2025-10-07') WHERE game_id = 2025020001"
            ),
            "expected_result": [
                {"home_team_abbrev": "FLA", "home_score": 3, "away_team_abbrev": "CHI", "away_score": 2}
            ],
        },
        {
            "name": "opener_goal_events",
            "description": "The opener's play-by-play contains its five goals.",
            "sql": (
                "SELECT count(*) AS goals FROM nhl.main.play_by_play(2025020001) WHERE event_type = 'goal'"
            ),
            "expected_result": [{"goals": 5}],
        },
        {
            "name": "current_standings_have_teams",
            "description": "Today's standings list every NHL team with a team code.",
            "sql": (
                "SELECT count(*) >= 32 AND count(team_abbrev) = count(*) AS populated "
                "FROM nhl.main.current_standings"
            ),
            "expected_result": [{"populated": True}],
        },
    ]
)

AGENT_TASKS = [
    {
        "name": "division_leaders",
        "prompt": (
            "Which team currently leads each NHL division and with how many points? Also say on "
            "what date the 2025-26 season's standings began."
        ),
    },
    {
        "name": "league_snapshot",
        "prompt": (
            "Give me today's NHL snapshot: the games on today's scoreboard, how many games are "
            "scheduled this week, and who currently leads the league in points and in goalie wins."
        ),
    },
    {
        "name": "opener_recap",
        "prompt": (
            "Recap NHL game 2025020001, the 2025-26 season opener on 7 October 2025: the final "
            "score, every goal scorer, and how many saves the winning goalie made. How many games "
            "were scheduled in the week starting that day?"
        ),
    },
    {
        "name": "opener_shots_and_ice_time",
        "prompt": (
            "For NHL game 2025020001, count each team's shots on goal from the play-by-play and "
            "tell me which player logged the most total ice time according to the shift chart."
        ),
    },
    {
        "name": "mcdavid_season_and_career",
        "prompt": (
            "Look up Connor McDavid's NHL player id, then give his 2025-26 regular-season points, "
            "his best single game that season, and his NHL regular-season points in each season "
            "of his career."
        ),
    },
    {
        "name": "skater_leaders_2025_26",
        "prompt": (
            "Who delivered the most hits in the 2025-26 NHL regular season, and who were the top "
            "five goal scorers on the official 2025-26 leaderboard?"
        ),
    },
    {
        "name": "goalies_2025_26",
        "prompt": (
            "Among NHL goalies with at least 40 games in 2025-26, who had the best save "
            "percentage? Also, who led the official 2025-26 leaderboard in shutouts?"
        ),
    },
    {
        "name": "maple_leafs_2025_26",
        "prompt": (
            "For the Toronto Maple Leafs in 2025-26: their regular-season home record from their "
            "schedule, their power-play percentage, and the goalies on their roster."
        ),
    },
    {
        "name": "champions_and_division_winner",
        "prompt": (
            "Who won the 2025 Stanley Cup and whom did they beat in the Final? And which team "
            "finished first in the Atlantic Division at the end of the 2023-24 regular season?"
        ),
    },
    {
        "name": "first_overall_franchise",
        "prompt": (
            "Who was the first overall pick in the 2025 NHL draft, and under which team names has "
            "the drafting franchise played?"
        ),
    },
    {
        "name": "leafs_roster_hits_leader",
        "prompt": (
            "Which skater on the Toronto Maple Leafs' 2025-26 roster delivered the most hits in "
            "the 2025-26 regular season, how many hits was that, and how many points did he score? "
            "Save your answer as a temp table named leafs_hits_leader with one row and columns "
            "player_id (INTEGER, NHL player id), hits (INTEGER), and points (INTEGER)."
        ),
    },
    {
        "name": "opener_ice_time_without_goals",
        "prompt": (
            "In NHL game 2025020001, which player logged the most total ice time without being on "
            "the ice for any goal by either team, and how much ice time was that? Save your answer "
            "as a temp table named opener_goalless_toi with one row and columns player_id (INTEGER, "
            "NHL player id) and toi_seconds (INTEGER, total ice time in seconds)."
        ),
    },
]


def _key_constraints(table: str, key: tuple[str, ...]) -> tuple[ConstraintInfo, ...]:
    """Primary-key and NOT NULL records for a read-only table keyed by ``key``."""
    records = [
        constraint_record(
            ["main"],
            table,
            "pk",
            "PRIMARY_KEY",
            [[column] for column in key],
            enforcement="ENFORCED",
            validation="ALL_ROWS",
        )
    ]
    records += [
        constraint_record(
            ["main"],
            table,
            f"{column}_not_null",
            "NOT_NULL",
            [[column]],
            enforcement="ENFORCED",
            validation="ALL_ROWS",
        )
        for column in key
    ]
    return tuple(records)


_SCHEMA_CATEGORIES = [
    {
        "name": "standings",
        "title": "Standings",
        "description": "Team points, records, ranks, and clinch state on any date since 1917-18.",
        "keywords": ["standings", "points", "division", "wild card", "seasons"],
    },
    {
        "name": "schedule",
        "title": "Schedule and Scores",
        "description": "Games by week, by day with live scores, and by team season.",
        "keywords": ["schedule", "scores", "results", "games"],
    },
    {
        "name": "player-stats",
        "title": "Player Statistics",
        "description": "Season skater, real-time, and goalie reports for every player.",
        "keywords": ["skaters", "goalies", "points", "save percentage", "hits"],
    },
    {
        "name": "team-stats",
        "title": "Team Statistics",
        "description": "Season team reports: goals, shots, special teams, and faceoffs.",
        "keywords": ["teams", "power play", "penalty kill", "goals per game"],
    },
    {
        "name": "leaders",
        "title": "Leaders",
        "description": "Official ranked skater and goalie leaderboards by category.",
        "keywords": ["leaders", "leaderboard", "Art Ross", "Vezina"],
    },
    {
        "name": "players",
        "title": "Players",
        "description": "Rosters, player profiles, career lines, game logs, and name search.",
        "keywords": ["players", "roster", "career", "game log", "search"],
    },
    {
        "name": "games",
        "title": "Game Detail",
        "description": "Box scores, play-by-play with rink coordinates, and shift charts.",
        "keywords": ["box score", "play-by-play", "shots", "shifts", "coordinates"],
    },
    {
        "name": "playoffs",
        "title": "Playoffs",
        "description": "Stanley Cup playoff brackets and series results.",
        "keywords": ["playoffs", "Stanley Cup", "series", "bracket"],
    },
    {
        "name": "draft",
        "title": "Draft",
        "description": "Every pick of each NHL entry draft since 1979.",
        "keywords": ["draft", "prospects", "picks"],
    },
    {
        "name": "reference",
        "title": "Reference",
        "description": "Team and franchise identifiers, current and historical.",
        "keywords": ["teams", "franchises", "ids", "tricodes"],
    },
]

NHL_CATALOG = Catalog(
    name="nhl",
    default_schema="main",
    source_url=SOURCE_URL,
    comment=(
        "Read-only National Hockey League standings, schedules, scores, game detail, and player "
        "and team statistics from the NHL's public web and stats APIs"
    ),
    tags={
        "provider": "nhl",
        "domain": "sports",
        "vgi.title": "National Hockey League Data",
        "vgi.subtitle": "NHL standings, scores, play-by-play, and player statistics as SQL tables.",
        "vgi.source_url": SOURCE_URL,
        "vgi.author": "Query Farm LLC <hello@query.farm>",
        "vgi.copyright": (
            "Worker (c) 2026 Query Farm LLC. NHL data and marks (c) NHL and its teams; use is "
            "subject to the NHL.com Terms of Service. Not affiliated with or endorsed by the NHL."
        ),
        "vgi.license": "MIT",
        "vgi.support_contact": "https://github.com/Query-farm/vgi-nhl/issues",
        "vgi.support_policy_url": "https://github.com/Query-farm/vgi-nhl/blob/main/README.md",
        "vgi.keywords": json.dumps(["NHL", "hockey", "ice hockey", "standings", "Stanley Cup"]),
        "vgi.executable_examples": _EXECUTABLE_EXAMPLES,
        "vgi.agent_test_tasks": json.dumps(AGENT_TASKS),
        "vgi.doc_llm": (
            "Read-only National Hockey League data fetched on demand from the NHL's public, keyless "
            "web and stats APIs. Current tables give today's standings, this week's schedule, "
            "today's scores, and skater and goalie leaders. Parameterized functions cover "
            "standings on any date since 1917-18, schedules and scores by date, team seasons, "
            "season skater/goalie/team reports, leaderboards, rosters, player profiles, career "
            "lines, game logs, name search, box scores, play-by-play with rink coordinates, shift "
            "charts, playoff brackets, drafts, teams, and franchises. Seasons are 8-digit ids "
            "such as 20252026; game_type is 2 regular season, 3 playoffs, 1 preseason; game ids "
            "are 10 digits such as 2025020001."
        ),
        "vgi.doc_md": (
            "# NHL standings, games, and statistics\n\n"
            "Query current and historical National Hockey League data directly from SQL: standings, "
            "schedules and scores, season reports for every skater, goalie, and team, official "
            "leaderboards, rosters and player careers, and per-game box scores, play-by-play, and "
            "shift charts.\n\n"
            "## Identifiers\n\n"
            "Seasons are 8-digit ids (`20252026` is 2025-26). `game_type` is 2 for the regular "
            "season, 3 for the playoffs, and 1 for the preseason. Game ids are 10 digits "
            "(`2025020001`) and player ids 7 digits (`8478402`); `player_search()` finds them.\n\n"
            "## Source\n\n"
            "All access is read-only, keyless, and on demand from NHL.com's own backends; nothing "
            "is stored or rehosted. This project is not affiliated with the NHL."
        ),
    },
    schemas=[
        Schema(
            path=["main"],
            comment="Current and historical NHL standings, games, and statistics",
            tags={
                "provider": "nhl",
                "domain": "sports",
                "vgi.title": "NHL Data",
                "vgi.keywords": json.dumps(
                    ["NHL", "hockey", "standings", "scores", "play-by-play", "skaters", "goalies"]
                ),
                "vgi.categories": json.dumps(_SCHEMA_CATEGORIES),
                "vgi.doc_llm": (
                    "Use current_standings, current_schedule, current_scores, current_skater_leaders, "
                    "and current_goalie_leaders for today's picture, and teams, franchises, and "
                    "standings_seasons for identifiers. Use skater_stats, goalie_stats, "
                    "and team_stats for full season reports; player_search then player, "
                    "player_career, and player_game_log for one player; box_score, play_by_play, and "
                    "shift_chart for one game."
                ),
                "vgi.doc_md": (
                    "## NHL analytical data\n\n"
                    "Rows are explicitly team-, game-, player-, player-season-, player-game-, event-, "
                    "or shift-grain. Current tables reflect today; functions take seasons, dates, "
                    "team codes, player ids, or game ids.\n\n"
                    "Reference tables (`teams`, `franchises`, `standings_seasons`) supply the "
                    "identifiers the functions accept. Percentages are 0-1 fractions and times on "
                    "ice come both as MM:SS text and as integer seconds."
                ),
                "vgi.example_queries": _example_queries([*_CURRENT_STANDINGS_QUERIES, *_COMPOSED_QUERIES]),
            },
            functions=[*LEAGUE_FUNCTIONS, *STATS_FUNCTIONS, *PLAYER_FUNCTIONS, *GAME_FUNCTIONS],
            tables=[
                Table(
                    name="current_standings",
                    function=CurrentStandingsFunction,
                    comment="Today's NHL standings, one row per team",
                    tags=_CURRENT_STANDINGS_TAGS,
                    column_comments=column_comments(STANDINGS_SCHEMA),
                    constraints=_key_constraints("current_standings", ("team_abbrev",)),
                    cardinality_estimate=32,
                ),
                Table(
                    name="current_schedule",
                    function=CurrentScheduleFunction,
                    comment="NHL games in the seven days starting today, one row per game",
                    tags=_CURRENT_SCHEDULE_TAGS,
                    column_comments=column_comments(GAMES_SCHEMA),
                    constraints=_key_constraints("current_schedule", ("game_id",)),
                    cardinality_estimate=50,
                ),
                Table(
                    name="current_scores",
                    function=CurrentScoresFunction,
                    comment="Today's NHL games with live or final scores, one row per game",
                    tags=_CURRENT_SCORES_TAGS,
                    column_comments=column_comments(GAMES_SCHEMA),
                    constraints=_key_constraints("current_scores", ("game_id",)),
                    cardinality_estimate=8,
                ),
                Table(
                    name="current_skater_leaders",
                    function=CurrentSkaterLeadersFunction,
                    comment="Current top-ten NHL skaters per stat category",
                    tags=_CURRENT_SKATER_LEADERS_TAGS,
                    column_comments=column_comments(LEADERS_SCHEMA),
                    constraints=_key_constraints("current_skater_leaders", ("category", "rank")),
                    cardinality_estimate=90,
                ),
                Table(
                    name="current_goalie_leaders",
                    function=CurrentGoalieLeadersFunction,
                    comment="Current top-ten NHL goalies per stat category",
                    tags=_CURRENT_GOALIE_LEADERS_TAGS,
                    column_comments=column_comments(LEADERS_SCHEMA),
                    constraints=_key_constraints("current_goalie_leaders", ("category", "rank")),
                    cardinality_estimate=40,
                ),
                Table(
                    name="standings_seasons",
                    function=StandingsSeasonsFunction,
                    comment="Every NHL season since 1917-18 with standings dates and rule flags",
                    tags=_STANDINGS_SEASONS_TAGS,
                    column_comments=column_comments(STANDINGS_SEASONS_SCHEMA),
                    constraints=_key_constraints("standings_seasons", ("season",)),
                    cardinality_estimate=110,
                ),
                Table(
                    name="teams",
                    function=TeamsFunction,
                    comment="Every current and historical NHL team with its id, tricode, and franchise",
                    tags=_TEAMS_TAGS,
                    column_comments=column_comments(TEAMS_SCHEMA),
                    constraints=_key_constraints("teams", ("team_id",)),
                    cardinality_estimate=62,
                ),
                Table(
                    name="franchises",
                    function=FranchisesFunction,
                    comment="Every NHL franchise, active and defunct",
                    tags=_FRANCHISES_TAGS,
                    column_comments=column_comments(FRANCHISES_SCHEMA),
                    constraints=_key_constraints("franchises", ("franchise_id",)),
                    cardinality_estimate=40,
                ),
            ],
        )
    ],
)


class NhlWorker(Worker):
    """Worker process hosting the read-only NHL catalog."""

    catalog = NHL_CATALOG


def main() -> None:
    """Run over stdio by default, or HTTP when VGI's ``--http`` flag is supplied."""
    NhlWorker.main()


def main_http() -> None:
    """Run HTTP with production-safe configuration requirements."""
    if not os.environ.get("VGI_SIGNING_KEY"):
        raise SystemExit(
            "VGI_SIGNING_KEY is required for HTTP mode so state remains valid across restarts and replicas"
        )
    auth_configured = bool(os.environ.get("VGI_BEARER_TOKENS") or os.environ.get("VGI_JWT_ISSUER"))
    auth_configured = auth_configured or os.environ.get("VGI_PROXY_PROOF_MODE", "").lower() == "require"
    if not auth_configured and os.environ.get("VGI_ALLOW_ANONYMOUS") != "1":
        raise SystemExit(
            "HTTP authentication is required; configure bearer/JWT/proxy proof, or explicitly set "
            "VGI_ALLOW_ANONYMOUS=1 for an intentionally public deployment"
        )
    argv = sys.argv[1:]
    if "--http" not in argv:
        argv = ["--http", *argv]
    if "--describe" not in argv and "--no-describe" not in argv:
        argv = ["--no-describe", *argv]
    if not any(value == "--cors-origins" or value.startswith("--cors-origins=") for value in argv):
        argv = ["--cors-origins", "", *argv]
    sys.argv = [sys.argv[0], *argv]
    NhlWorker.main()
