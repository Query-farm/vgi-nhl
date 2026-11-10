"""Arrow schemas and flattening for standings, schedules, scores, and league reference data."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pyarrow as pa

from vgi_nhl.meta import (
    field,
    full_name,
    mapping,
    text,
    to_bool,
    to_date,
    to_float,
    to_int,
    to_timestamp,
)

TIMESTAMP = pa.timestamp("us", tz="UTC")
NHL_WEB = "https://www.nhl.com"
_NOT_STARTED = frozenset({"FUT", "PRE", None})

STANDINGS_SCHEMA = pa.schema(
    [
        field("season", pa.int32(), "NHL season id, such as 20252026."),
        field("game_type", pa.int32(), "NHL game type: 2 regular season."),
        field("standings_date", pa.date32(), "Date the standings snapshot describes."),
        field("team_abbrev", pa.string(), "Three-letter team code, such as TOR."),
        field("team_name", pa.string(), "Full team name, such as Toronto Maple Leafs."),
        field("team_common_name", pa.string(), "Team nickname, such as Maple Leafs."),
        field("team_place_name", pa.string(), "Team location, such as Toronto."),
        field("conference_abbrev", pa.string(), "Conference code: E or W."),
        field("conference_name", pa.string(), "Conference name, such as Eastern."),
        field("division_abbrev", pa.string(), "Division code, such as A, M, C, or P."),
        field("division_name", pa.string(), "Division name, such as Atlantic."),
        field("league_rank", pa.int32(), "League-wide rank (1 = best)."),
        field("conference_rank", pa.int32(), "Position within the conference."),
        field("division_rank", pa.int32(), "Position within the division."),
        field("wildcard_rank", pa.int32(), "Wild-card rank; 0 for division-spot holders."),
        field("games_played", pa.int32(), "Count of games played so far."),
        field("wins", pa.int32(), "Wins, including overtime and shootout wins."),
        field("losses", pa.int32(), "Regulation losses."),
        field("ot_losses", pa.int32(), "Overtime and shootout losses (one point each)."),
        field("ties", pa.int32(), "Ties, before 2005-06."),
        field("points", pa.int32(), "Standings points."),
        field("point_pct", pa.float64(), "Points divided by points available (0-1)."),
        field("regulation_wins", pa.int32(), "Regulation wins, the first tiebreaker."),
        field("regulation_plus_ot_wins", pa.int32(), "Regulation plus overtime wins."),
        field("shootout_wins", pa.int32(), "Games won in a shootout."),
        field("shootout_losses", pa.int32(), "Games lost in a shootout."),
        field("goals_for", pa.int32(), "Goals scored."),
        field("goals_against", pa.int32(), "Goals allowed."),
        field("goal_differential", pa.int32(), "Goals for minus goals against."),
        field("home_wins", pa.int32(), "Wins at home."),
        field("home_losses", pa.int32(), "Regulation losses at home."),
        field("home_ot_losses", pa.int32(), "Overtime and shootout losses at home."),
        field("home_points", pa.int32(), "Points earned at home."),
        field("road_wins", pa.int32(), "Wins on the road."),
        field("road_losses", pa.int32(), "Regulation losses on the road."),
        field("road_ot_losses", pa.int32(), "Overtime and shootout losses on the road."),
        field("road_points", pa.int32(), "Points earned on the road."),
        field("last_10_wins", pa.int32(), "Wins in the last ten games."),
        field("last_10_losses", pa.int32(), "Regulation losses in the last ten games."),
        field("last_10_ot_losses", pa.int32(), "Overtime and shootout losses in the last ten games."),
        field("streak_code", pa.string(), "Streak type: W, L, or OT."),
        field("streak_count", pa.int32(), "Length of the current streak."),
        field(
            "clinch_indicator",
            pa.string(),
            "Clinch: p Presidents' Trophy, z conference, y division, x berth, e out.",
        ),
        field("team_logo_url", pa.string(), "Team logo SVG URL."),
    ]
)

STANDINGS_SEASONS_SCHEMA = pa.schema(
    [
        field("season", pa.int32(), "NHL season id, such as 19171918.", nullable=False),
        field("standings_start", pa.date32(), "First date standings exist for the season."),
        field("standings_end", pa.date32(), "Last date standings exist for the season."),
        field("conferences_in_use", pa.bool_(), "Whether the season grouped teams into conferences."),
        field("divisions_in_use", pa.bool_(), "Whether the season grouped teams into divisions."),
        field("point_for_ot_loss_in_use", pa.bool_(), "Whether overtime losses earned a standings point."),
        field("regulation_wins_in_use", pa.bool_(), "Whether regulation wins were tracked as a tiebreaker."),
        field("row_in_use", pa.bool_(), "Whether regulation-plus-overtime wins were tracked."),
        field("ties_in_use", pa.bool_(), "Whether games could end in a tie."),
        field("wildcard_in_use", pa.bool_(), "Whether playoff qualification used wild cards."),
    ]
)

GAMES_SCHEMA = pa.schema(
    [
        field("game_id", pa.int64(), "NHL game id, such as 2025020001 (season, type, number)."),
        field("season", pa.int32(), "NHL season id, such as 20252026."),
        field("game_type", pa.int32(), "NHL game type: 1 preseason, 2 regular season, 3 playoffs."),
        field("game_date", pa.date32(), "Local calendar date of the game."),
        field("start_time_utc", TIMESTAMP, "Scheduled puck-drop time in UTC."),
        field("venue", pa.string(), "Arena name."),
        field("venue_timezone", pa.string(), "IANA time zone of the arena."),
        field("neutral_site", pa.bool_(), "Whether the game is played at a neutral site."),
        field(
            "game_state",
            pa.string(),
            "Game state: FUT future, PRE pregame, LIVE/CRIT in progress, FINAL/OFF finished.",
        ),
        field("game_schedule_state", pa.string(), "Schedule state: OK, PPD postponed, or CNCL cancelled."),
        field("away_team_id", pa.int32(), "NHL team id of the visiting team."),
        field("away_team_abbrev", pa.string(), "Three-letter code of the visiting team."),
        field(
            "away_team_name",
            pa.string(),
            "Visiting team nickname, such as Blackhawks; join teams for the full name.",
        ),
        field("away_score", pa.int32(), "Visiting team goals; NULL before the game starts."),
        field(
            "away_shots_on_goal",
            pa.int32(),
            "Visiting team shots on goal; only scores() reports it, NULL in schedules.",
        ),
        field("home_team_id", pa.int32(), "NHL team id of the home team."),
        field("home_team_abbrev", pa.string(), "Three-letter code of the home team."),
        field(
            "home_team_name",
            pa.string(),
            "Home team nickname, such as Panthers; join teams for the full name.",
        ),
        field("home_score", pa.int32(), "Home team goals; NULL before the game starts."),
        field(
            "home_shots_on_goal",
            pa.int32(),
            "Home team shots on goal; only scores() reports it, NULL in schedules.",
        ),
        field("period", pa.int32(), "Current or final period number (4+ means overtime/shootout)."),
        field("period_type", pa.string(), "Current or final period type: REG, OT, or SO."),
        field("last_period_type", pa.string(), "How a finished game ended: REG, OT, or SO."),
        field(
            "winning_goalie_id",
            pa.int32(),
            "Player id of the winning goalie; schedules only, NULL in scores().",
        ),
        field("winning_goalie_name", pa.string(), "Winning goalie, as an initial and last name."),
        field(
            "winning_goal_scorer_id",
            pa.int32(),
            "Player id of the game-winning goal scorer; schedules only, NULL in scores().",
        ),
        field("winning_goal_scorer_name", pa.string(), "Game-winning goal scorer, as initial and last name."),
        field("game_center_url", pa.string(), "NHL.com GameCenter URL for the game."),
    ]
)

LEADERS_SCHEMA = pa.schema(
    [
        field("season", pa.int32(), "NHL season id the leaderboard covers."),
        field("game_type", pa.int32(), "NHL game type: 2 regular season, 3 playoffs."),
        field("category", pa.string(), "Leader category, such as points, goals, or savePctg."),
        field("rank", pa.int32(), "Position in the NHL's ordered leader list (1 = leader)."),
        field("player_id", pa.int32(), "Stable NHL player id."),
        field("player_name", pa.string(), "Player full name."),
        field("first_name", pa.string(), "Player first name."),
        field("last_name", pa.string(), "Player last name."),
        field("sweater_number", pa.int32(), "Jersey number."),
        field("position", pa.string(), "Position code: C, L, R, D, or G."),
        field("team_abbrev", pa.string(), "Three-letter code of the player's team."),
        field("team_name", pa.string(), "Team nickname, such as Oilers."),
        field(
            "value",
            pa.float64(),
            "Category value: a count, a 0-1 percentage, goals-against average, or TOI seconds per game.",
        ),
    ]
)

BRACKET_SCHEMA = pa.schema(
    [
        field("year", pa.int32(), "Playoff year (the calendar year the Stanley Cup Final is played)."),
        field("series_letter", pa.string(), "Series letter, A through O, in bracket order."),
        field("series_abbrev", pa.string(), "Round code: R1, R2, ECF, WCF, or SCF."),
        field("series_title", pa.string(), "Round title, such as 1st Round or Stanley Cup Final."),
        field("playoff_round", pa.int32(), "Round number from 1 (first round) to 4 (final)."),
        field("top_seed_team_id", pa.int32(), "NHL team id of the higher seed."),
        field("top_seed_team_abbrev", pa.string(), "Three-letter code of the higher seed."),
        field("top_seed_team_name", pa.string(), "Full name of the higher seed."),
        field("top_seed_rank_abbrev", pa.string(), "Seed label of the higher seed, such as D1 or WC1."),
        field("top_seed_wins", pa.int32(), "Games won by the higher seed in the series."),
        field("bottom_seed_team_id", pa.int32(), "NHL team id of the lower seed."),
        field("bottom_seed_team_abbrev", pa.string(), "Three-letter code of the lower seed."),
        field("bottom_seed_team_name", pa.string(), "Full name of the lower seed."),
        field("bottom_seed_rank_abbrev", pa.string(), "Seed label of the lower seed."),
        field("bottom_seed_wins", pa.int32(), "Games won by the lower seed in the series."),
        field("winning_team_id", pa.int32(), "NHL team id of the series winner; NULL while undecided."),
        field("losing_team_id", pa.int32(), "NHL team id of the series loser; NULL while undecided."),
    ]
)

DRAFT_SCHEMA = pa.schema(
    [
        field("draft_year", pa.int32(), "Entry draft year."),
        field("round", pa.int32(), "Draft round."),
        field("pick_in_round", pa.int32(), "Pick number within the round."),
        field("overall_pick", pa.int32(), "Overall pick number.", nullable=False),
        field("team_id", pa.int32(), "NHL team id of the selecting team."),
        field("team_abbrev", pa.string(), "Three-letter code of the selecting team."),
        field("team_name", pa.string(), "Full name of the selecting team."),
        field("team_pick_history", pa.string(), "Teams that held the pick, in order, separated by hyphens."),
        field("player_name", pa.string(), "Drafted player's full name."),
        field("first_name", pa.string(), "Drafted player's first name."),
        field("last_name", pa.string(), "Drafted player's last name."),
        field("position_code", pa.string(), "Position code: C, L, R, D, or G."),
        field("country_code", pa.string(), "Three-letter country code of the player."),
        field("height_inches", pa.int32(), "Height in inches at the draft."),
        field("weight_pounds", pa.int32(), "Weight in pounds at the draft."),
        field("amateur_league", pa.string(), "League the player was drafted from, such as OHL."),
        field("amateur_club_name", pa.string(), "Club the player was drafted from."),
    ]
)

TEAMS_SCHEMA = pa.schema(
    [
        field("team_id", pa.int32(), "NHL team id, current or historical.", nullable=False),
        field("franchise_id", pa.int32(), "Franchise id; relocated teams share one franchise."),
        field("full_name", pa.string(), "Full team name."),
        field("tricode", pa.string(), "Three-letter team code."),
        field("league_id", pa.int32(), "League id; 133 is the NHL."),
    ]
)

FRANCHISES_SCHEMA = pa.schema(
    [
        field("franchise_id", pa.int32(), "NHL franchise id.", nullable=False),
        field("full_name", pa.string(), "Most recent full name of the franchise."),
        field("common_name", pa.string(), "Franchise nickname."),
        field("place_name", pa.string(), "Franchise location."),
    ]
)


def flatten_standings(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Flatten an api-web ``standings`` document into one row per team."""
    rows: list[dict[str, Any]] = []
    for team in payload.get("standings") or []:
        if not isinstance(team, Mapping):
            continue
        rows.append(
            {
                "season": to_int(team.get("seasonId")),
                "game_type": to_int(team.get("gameTypeId")),
                "standings_date": to_date(team.get("date")),
                "team_abbrev": text(team.get("teamAbbrev")),
                "team_name": text(team.get("teamName")),
                "team_common_name": text(team.get("teamCommonName")),
                "team_place_name": text(team.get("placeName")),
                "conference_abbrev": team.get("conferenceAbbrev") or None,
                "conference_name": team.get("conferenceName") or None,
                "division_abbrev": team.get("divisionAbbrev") or None,
                "division_name": team.get("divisionName") or None,
                "league_rank": to_int(team.get("leagueSequence")),
                "conference_rank": to_int(team.get("conferenceSequence")),
                "division_rank": to_int(team.get("divisionSequence")),
                "wildcard_rank": to_int(team.get("wildcardSequence")),
                "games_played": to_int(team.get("gamesPlayed")),
                "wins": to_int(team.get("wins")),
                "losses": to_int(team.get("losses")),
                "ot_losses": to_int(team.get("otLosses")),
                "ties": to_int(team.get("ties")),
                "points": to_int(team.get("points")),
                "point_pct": to_float(team.get("pointPctg")),
                "regulation_wins": to_int(team.get("regulationWins")),
                "regulation_plus_ot_wins": to_int(team.get("regulationPlusOtWins")),
                "shootout_wins": to_int(team.get("shootoutWins")),
                "shootout_losses": to_int(team.get("shootoutLosses")),
                "goals_for": to_int(team.get("goalFor")),
                "goals_against": to_int(team.get("goalAgainst")),
                "goal_differential": to_int(team.get("goalDifferential")),
                "home_wins": to_int(team.get("homeWins")),
                "home_losses": to_int(team.get("homeLosses")),
                "home_ot_losses": to_int(team.get("homeOtLosses")),
                "home_points": to_int(team.get("homePoints")),
                "road_wins": to_int(team.get("roadWins")),
                "road_losses": to_int(team.get("roadLosses")),
                "road_ot_losses": to_int(team.get("roadOtLosses")),
                "road_points": to_int(team.get("roadPoints")),
                "last_10_wins": to_int(team.get("l10Wins")),
                "last_10_losses": to_int(team.get("l10Losses")),
                "last_10_ot_losses": to_int(team.get("l10OtLosses")),
                "streak_code": team.get("streakCode") or None,
                "streak_count": to_int(team.get("streakCount")),
                "clinch_indicator": team.get("clinchIndicator") or None,
                "team_logo_url": team.get("teamLogo") or None,
            }
        )
    return rows


def flatten_standings_seasons(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Flatten the api-web ``standings-season`` list."""
    return [
        {
            "season": to_int(season.get("id")),
            "standings_start": to_date(season.get("standingsStart")),
            "standings_end": to_date(season.get("standingsEnd")),
            "conferences_in_use": to_bool(season.get("conferencesInUse")),
            "divisions_in_use": to_bool(season.get("divisionsInUse")),
            "point_for_ot_loss_in_use": to_bool(season.get("pointForOTlossInUse")),
            "regulation_wins_in_use": to_bool(season.get("regulationWinsInUse")),
            "row_in_use": to_bool(season.get("rowInUse")),
            "ties_in_use": to_bool(season.get("tiesInUse")),
            "wildcard_in_use": to_bool(season.get("wildcardInUse")),
        }
        for season in payload.get("seasons") or []
        if isinstance(season, Mapping) and to_int(season.get("id")) is not None
    ]


def _team_name(team: Mapping[str, Any]) -> str | None:
    """Return the team nickname, which schedule (commonName) and score (name) payloads both carry."""
    return text(team.get("commonName")) or text(team.get("name"))


def _initial_name(player: Mapping[str, Any]) -> str | None:
    return full_name(player.get("firstInitial"), player.get("lastName"))


def game_row(game: Mapping[str, Any], fallback_date: Any = None) -> dict[str, Any]:
    """Flatten one schedule, score, or club-schedule game object."""
    away = mapping(game.get("awayTeam"))
    home = mapping(game.get("homeTeam"))
    period = mapping(game.get("periodDescriptor"))
    goalie = mapping(game.get("winningGoalie"))
    scorer = mapping(game.get("winningGoalScorer"))
    link = game.get("gameCenterLink")
    started = game.get("gameState") not in _NOT_STARTED
    return {
        "game_id": to_int(game.get("id")),
        "season": to_int(game.get("season")),
        "game_type": to_int(game.get("gameType")),
        "game_date": to_date(game.get("gameDate") or fallback_date),
        "start_time_utc": to_timestamp(game.get("startTimeUTC")),
        "venue": text(game.get("venue")),
        "venue_timezone": game.get("venueTimezone") or None,
        "neutral_site": to_bool(game.get("neutralSite")),
        "game_state": game.get("gameState") or None,
        "game_schedule_state": game.get("gameScheduleState") or None,
        "away_team_id": to_int(away.get("id")),
        "away_team_abbrev": away.get("abbrev") or None,
        "away_team_name": _team_name(away),
        "away_score": to_int(away.get("score")),
        "away_shots_on_goal": to_int(away.get("sog")),
        "home_team_id": to_int(home.get("id")),
        "home_team_abbrev": home.get("abbrev") or None,
        "home_team_name": _team_name(home),
        "home_score": to_int(home.get("score")),
        "home_shots_on_goal": to_int(home.get("sog")),
        "period": None if not started else to_int(game.get("period", period.get("number"))),
        "period_type": (period.get("periodType") or None) if started else None,
        "last_period_type": mapping(game.get("gameOutcome")).get("lastPeriodType") or None,
        "winning_goalie_id": to_int(goalie.get("playerId")),
        "winning_goalie_name": _initial_name(goalie),
        "winning_goal_scorer_id": to_int(scorer.get("playerId")),
        "winning_goal_scorer_name": _initial_name(scorer),
        "game_center_url": f"{NHL_WEB}{link}" if isinstance(link, str) and link.startswith("/") else None,
    }


def flatten_schedule(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Flatten an api-web ``schedule`` week into one row per game."""
    rows: list[dict[str, Any]] = []
    for day in payload.get("gameWeek") or []:
        if not isinstance(day, Mapping):
            continue
        for game in day.get("games") or []:
            if isinstance(game, Mapping):
                rows.append(game_row(game, day.get("date")))
    return rows


def flatten_games(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Flatten a ``score`` day or ``club-schedule-season`` document into one row per game."""
    return [game_row(game) for game in payload.get("games") or [] if isinstance(game, Mapping)]


def flatten_leaders(
    payload: Mapping[str, Any], *, season: int | None, game_type: int | None
) -> list[dict[str, Any]]:
    """Flatten a skater or goalie leaders document into one row per category and rank."""
    rows: list[dict[str, Any]] = []
    for category, leaders in payload.items():
        if not isinstance(leaders, list):
            continue
        for rank, leader in enumerate(leaders, start=1):
            if not isinstance(leader, Mapping):
                continue
            rows.append(
                {
                    "season": season,
                    "game_type": game_type,
                    "category": category,
                    "rank": rank,
                    "player_id": to_int(leader.get("id")),
                    "player_name": full_name(leader.get("firstName"), leader.get("lastName")),
                    "first_name": text(leader.get("firstName")),
                    "last_name": text(leader.get("lastName")),
                    "sweater_number": to_int(leader.get("sweaterNumber")),
                    "position": leader.get("position") or None,
                    "team_abbrev": leader.get("teamAbbrev") or None,
                    "team_name": text(leader.get("teamName")),
                    "value": to_float(leader.get("value")),
                }
            )
    return rows


def _seed(series: Mapping[str, Any], prefix: str) -> dict[str, Any]:
    team = mapping(series.get(f"{prefix}SeedTeam"))
    return {
        f"{prefix}_seed_team_id": to_int(team.get("id")),
        f"{prefix}_seed_team_abbrev": team.get("abbrev") or None,
        f"{prefix}_seed_team_name": text(team.get("name")),
        f"{prefix}_seed_rank_abbrev": series.get(f"{prefix}SeedRankAbbrev") or None,
        f"{prefix}_seed_wins": to_int(series.get(f"{prefix}SeedWins")),
    }


def flatten_bracket(payload: Mapping[str, Any], year: int) -> list[dict[str, Any]]:
    """Flatten a ``playoff-bracket`` document into one row per series."""
    return [
        {
            "year": year,
            "series_letter": series.get("seriesLetter") or None,
            "series_abbrev": series.get("seriesAbbrev") or None,
            "series_title": series.get("seriesTitle") or None,
            "playoff_round": to_int(series.get("playoffRound")),
            **_seed(series, "top"),
            **_seed(series, "bottom"),
            "winning_team_id": to_int(series.get("winningTeamId")) or None,
            "losing_team_id": to_int(series.get("losingTeamId")) or None,
        }
        for series in payload.get("series") or []
        if isinstance(series, Mapping)
    ]


def flatten_draft(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Flatten a ``draft/picks`` document into one row per pick."""
    year = to_int(payload.get("draftYear"))
    return [
        {
            "draft_year": year,
            "round": to_int(pick.get("round")),
            "pick_in_round": to_int(pick.get("pickInRound")),
            "overall_pick": to_int(pick.get("overallPick")),
            "team_id": to_int(pick.get("teamId")),
            "team_abbrev": pick.get("teamAbbrev") or None,
            "team_name": text(pick.get("teamName")),
            "team_pick_history": pick.get("teamPickHistory") or None,
            "player_name": full_name(pick.get("firstName"), pick.get("lastName")),
            "first_name": text(pick.get("firstName")),
            "last_name": text(pick.get("lastName")),
            "position_code": pick.get("positionCode") or None,
            "country_code": pick.get("countryCode") or None,
            "height_inches": to_int(pick.get("height")),
            "weight_pounds": to_int(pick.get("weight")),
            "amateur_league": pick.get("amateurLeague") or None,
            "amateur_club_name": pick.get("amateurClubName") or None,
        }
        for pick in payload.get("picks") or []
        if isinstance(pick, Mapping) and to_int(pick.get("overallPick")) is not None
    ]


def flatten_teams(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Flatten the stats REST ``team`` list."""
    return [
        {
            "team_id": to_int(team.get("id")),
            "franchise_id": to_int(team.get("franchiseId")),
            "full_name": team.get("fullName") or None,
            "tricode": team.get("triCode") or team.get("rawTricode") or None,
            "league_id": to_int(team.get("leagueId")),
        }
        for team in payload.get("data") or []
        if isinstance(team, Mapping) and to_int(team.get("id")) is not None
    ]


def flatten_franchises(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Flatten the stats REST ``franchise`` list."""
    return [
        {
            "franchise_id": to_int(franchise.get("id")),
            "full_name": franchise.get("fullName") or None,
            "common_name": franchise.get("teamCommonName") or None,
            "place_name": franchise.get("teamPlaceName") or None,
        }
        for franchise in payload.get("data") or []
        if isinstance(franchise, Mapping) and to_int(franchise.get("id")) is not None
    ]
