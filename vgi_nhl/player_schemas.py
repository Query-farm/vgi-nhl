"""Arrow schemas and flattening for rosters, player pages, careers, game logs, and search."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pyarrow as pa

from vgi_nhl.meta import (
    Spec,
    clock_seconds,
    field,
    flatten,
    full_name,
    mapping,
    schema_of,
    text,
    to_bool,
    to_date,
    to_float,
    to_int,
)

INT, DBL, STR = pa.int32(), pa.float64(), pa.string()

_BIO_FIELDS = [
    field("shoots_catches", STR, "Handedness: L or R."),
    field("height_inches", INT, "Height in inches."),
    field("weight_pounds", INT, "Weight in pounds."),
    field("height_cm", INT, "Height in centimetres."),
    field("weight_kg", INT, "Weight in kilograms."),
    field("birth_date", pa.date32(), "Date of birth."),
    field("birth_city", STR, "City of birth."),
    field("birth_state_province", STR, "State or province of birth, when recorded."),
    field("birth_country", STR, "Three-letter country code of birth."),
    field("headshot_url", STR, "URL of the player's NHL headshot image."),
]

ROSTER_SCHEMA = pa.schema(
    [
        field("season", INT, "NHL season id of the roster, such as 20252026."),
        field("team_abbrev", STR, "Three-letter team code."),
        field("player_id", INT, "Stable NHL player id.", nullable=False),
        field("player_name", STR, "Player full name."),
        field("first_name", STR, "Player first name."),
        field("last_name", STR, "Player last name."),
        field("sweater_number", INT, "Jersey number."),
        field("position_code", STR, "Position code: C, L, R, D, or G."),
        field("position_group", STR, "Roster group: forwards, defensemen, or goalies."),
        *_BIO_FIELDS,
    ]
)

PLAYER_SCHEMA = pa.schema(
    [
        field("player_id", INT, "Stable NHL player id.", nullable=False),
        field("player_name", STR, "Player full name."),
        field("first_name", STR, "Player first name."),
        field("last_name", STR, "Player last name."),
        field("is_active", pa.bool_(), "Whether the player is currently active."),
        field("current_team_id", INT, "NHL team id of the current team; NULL for inactive players."),
        field("current_team_abbrev", STR, "Three-letter code of the current team."),
        field("current_team_name", STR, "Full name of the current team."),
        field("sweater_number", INT, "Current jersey number."),
        field("position", STR, "Position code: C, L, R, D, or G."),
        *_BIO_FIELDS,
        field("draft_year", INT, "NHL entry draft year; NULL if undrafted."),
        field("draft_team_abbrev", STR, "Three-letter code of the drafting team."),
        field("draft_round", INT, "Draft round."),
        field("draft_pick_in_round", INT, "Pick number within the draft round."),
        field("draft_overall_pick", INT, "Overall draft pick number."),
        field("in_hockey_hall_of_fame", pa.bool_(), "Whether the player is in the Hockey Hall of Fame."),
        field("in_top_100_all_time", pa.bool_(), "Whether the NHL lists the player among its top 100 ever."),
        field("career_games_played", INT, "Career NHL regular-season games played."),
        field("career_goals", INT, "Career NHL regular-season goals (skaters and goalies)."),
        field("career_assists", INT, "Career NHL regular-season assists."),
        field("career_points", INT, "Career NHL regular-season points; NULL for goalies."),
        field("career_wins", INT, "Career NHL regular-season wins; goalies only."),
        field("career_shutouts", INT, "Career NHL regular-season shutouts; goalies only."),
        field("career_save_pct", DBL, "Career NHL regular-season save percentage (0-1); goalies only."),
        field("career_goals_against_average", DBL, "Career NHL regular-season goals-against average."),
        field("career_playoff_games_played", INT, "Career NHL playoff games played."),
        field("career_playoff_points", INT, "Career NHL playoff points; NULL for goalies."),
    ]
)


def _toi(key: str):
    return lambda row: clock_seconds(row.get(key))


_SKATER_LINE: list[Spec] = [
    ("goals", INT, "Goals.", "goals"),
    ("assists", INT, "Assists.", "assists"),
    ("points", INT, "Points; NULL for goalies.", "points"),
    ("plus_minus", INT, "Plus-minus; skaters only.", "plusMinus"),
    ("penalty_minutes", INT, "Penalty minutes.", "pim"),
    ("power_play_goals", INT, "Power-play goals; skaters only.", "powerPlayGoals"),
    ("power_play_points", INT, "Power-play points; skaters only.", "powerPlayPoints"),
    ("shorthanded_goals", INT, "Shorthanded goals; skaters only.", "shorthandedGoals"),
    ("shorthanded_points", INT, "Shorthanded points; skaters only.", "shorthandedPoints"),
    ("game_winning_goals", INT, "Game-winning goals; skaters only.", "gameWinningGoals"),
    ("overtime_goals", INT, "Overtime goals; skaters only.", "otGoals"),
    ("shots", INT, "Shots on goal; skaters only.", "shots"),
]

_GOALIE_LINE: list[Spec] = [
    ("games_started", INT, "Games started; goalies only.", "gamesStarted"),
    ("shots_against", INT, "Shots on goal faced; goalies only.", "shotsAgainst"),
    ("goals_against", INT, "Goals allowed; goalies only.", "goalsAgainst"),
    ("save_pct", DBL, "Save percentage (0-1); goalies only.", "savePctg"),
    ("shutouts", INT, "Shutouts; goalies only.", "shutouts"),
]

CAREER_SPEC: list[Spec] = [
    ("player_id", INT, "Stable NHL player id.", "playerId"),
    ("season", INT, "Season id, such as 20252026.", "season"),
    ("game_type", INT, "Game type: 2 regular season, 3 playoffs.", "gameTypeId"),
    ("league_abbrev", STR, "League of the line, such as NHL, AHL, OHL, or OG (Olympics).", "leagueAbbrev"),
    ("team_name", STR, "Team name for the line.", lambda row: text(row.get("teamName"))),
    ("sequence", INT, "Order of the line within the season, for players with several teams.", "sequence"),
    ("games_played", INT, "Games played.", "gamesPlayed"),
    *_SKATER_LINE,
    ("shooting_pct", DBL, "Goals divided by shots (0-1); NHL skater lines only.", "shootingPctg"),
    ("faceoff_win_pct", DBL, "Faceoff win percentage (0-1); NHL skater lines only.", "faceoffWinningPctg"),
    ("avg_toi", STR, "Average time on ice per game as MM:SS; NHL skater lines only.", "avgToi"),
    ("avg_toi_seconds", INT, "Average time on ice per game in seconds.", _toi("avgToi")),
    *_GOALIE_LINE,
    ("wins", INT, "Wins; goalies only.", "wins"),
    ("losses", INT, "Regulation losses; goalies only.", "losses"),
    ("ot_losses", INT, "Overtime and shootout losses; goalies only.", "otLosses"),
    ("ties", INT, "Ties; goalies only, before 2005-06.", "ties"),
    ("goals_against_average", DBL, "Goals allowed per 60 minutes; goalies only.", "goalsAgainstAvg"),
    ("time_on_ice", STR, "Total time on ice as MM:SS; goalies only.", "timeOnIce"),
    ("time_on_ice_seconds", INT, "Total time on ice in seconds; goalies only.", _toi("timeOnIce")),
]

GAME_LOG_SPEC: list[Spec] = [
    ("player_id", INT, "Stable NHL player id.", "playerId"),
    ("season", INT, "Season id, such as 20252026.", "seasonId"),
    ("game_type", INT, "Game type: 1 preseason, 2 regular season, 3 playoffs.", "gameTypeId"),
    ("game_id", pa.int64(), "NHL game id; joins to box_score() and play_by_play().", "gameId"),
    ("game_date", pa.date32(), "Local date of the game.", lambda row: to_date(row.get("gameDate"))),
    ("team_abbrev", STR, "The player's team code for the game.", "teamAbbrev"),
    ("opponent_abbrev", STR, "Opponent team code.", "opponentAbbrev"),
    ("home_road_flag", STR, "H for a home game, R for a road game.", "homeRoadFlag"),
    *_SKATER_LINE,
    ("shifts", INT, "Shifts taken; skaters only.", "shifts"),
    ("toi", STR, "Time on ice as MM:SS.", "toi"),
    ("toi_seconds", INT, "Time on ice in seconds.", _toi("toi")),
    *_GOALIE_LINE,
    (
        "decision",
        STR,
        "Goalie decision: W win, L loss, O overtime/shootout loss; NULL otherwise.",
        "decision",
    ),
]

SEARCH_SCHEMA = pa.schema(
    [
        field("player_id", INT, "Stable NHL player id.", nullable=False),
        field("player_name", STR, "Player full name."),
        field("position_code", STR, "Position code: C, L, R, D, or G."),
        field("active", pa.bool_(), "Whether the player is currently active."),
        field("team_id", INT, "NHL team id of the current team; NULL for inactive players."),
        field("team_abbrev", STR, "Three-letter code of the current team."),
        field("last_team_id", INT, "NHL team id of the most recent team."),
        field("last_team_abbrev", STR, "Three-letter code of the most recent team."),
        field("last_season", INT, "Most recent NHL season id played, such as 20252026."),
        field("sweater_number", INT, "Most recent jersey number."),
        field("height_inches", INT, "Height in inches."),
        field("weight_pounds", INT, "Weight in pounds."),
        field("birth_city", STR, "City of birth."),
        field("birth_state_province", STR, "State or province of birth, when recorded."),
        field("birth_country", STR, "Three-letter country code of birth."),
    ]
)

CAREER_SCHEMA = schema_of(CAREER_SPEC, key=("player_id",))
GAME_LOG_SCHEMA = schema_of(GAME_LOG_SPEC, key=("player_id",))


def _bio(player: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "shoots_catches": player.get("shootsCatches") or None,
        "height_inches": to_int(player.get("heightInInches")),
        "weight_pounds": to_int(player.get("weightInPounds")),
        "height_cm": to_int(player.get("heightInCentimeters")),
        "weight_kg": to_int(player.get("weightInKilograms")),
        "birth_date": to_date(player.get("birthDate")),
        "birth_city": text(player.get("birthCity")),
        "birth_state_province": text(player.get("birthStateProvince")),
        "birth_country": player.get("birthCountry") or None,
        "headshot_url": player.get("headshot") or None,
    }


def flatten_roster(payload: Mapping[str, Any], *, season: int | None, team: str) -> list[dict[str, Any]]:
    """Flatten an api-web ``roster`` document into one row per player."""
    rows: list[dict[str, Any]] = []
    for group in ("forwards", "defensemen", "goalies"):
        for player in payload.get(group) or []:
            if not isinstance(player, Mapping) or to_int(player.get("id")) is None:
                continue
            rows.append(
                {
                    "season": season,
                    "team_abbrev": team,
                    "player_id": to_int(player.get("id")),
                    "player_name": full_name(player.get("firstName"), player.get("lastName")),
                    "first_name": text(player.get("firstName")),
                    "last_name": text(player.get("lastName")),
                    "sweater_number": to_int(player.get("sweaterNumber")),
                    "position_code": player.get("positionCode") or None,
                    "position_group": group,
                    **_bio(player),
                }
            )
    return rows


def flatten_player(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Flatten an api-web player ``landing`` document into one row."""
    player_id = to_int(payload.get("playerId"))
    if player_id is None:
        return []
    draft = mapping(payload.get("draftDetails"))
    totals = mapping(payload.get("careerTotals"))
    regular = mapping(totals.get("regularSeason"))
    playoffs = mapping(totals.get("playoffs"))
    return [
        {
            "player_id": player_id,
            "player_name": full_name(payload.get("firstName"), payload.get("lastName")),
            "first_name": text(payload.get("firstName")),
            "last_name": text(payload.get("lastName")),
            "is_active": to_bool(payload.get("isActive")),
            "current_team_id": to_int(payload.get("currentTeamId")),
            "current_team_abbrev": payload.get("currentTeamAbbrev") or None,
            "current_team_name": text(payload.get("fullTeamName")),
            "sweater_number": to_int(payload.get("sweaterNumber")),
            "position": payload.get("position") or None,
            **_bio(payload),
            "draft_year": to_int(draft.get("year")),
            "draft_team_abbrev": draft.get("teamAbbrev") or None,
            "draft_round": to_int(draft.get("round")),
            "draft_pick_in_round": to_int(draft.get("pickInRound")),
            "draft_overall_pick": to_int(draft.get("overallPick")),
            "in_hockey_hall_of_fame": to_bool(payload.get("inHHOF")),
            "in_top_100_all_time": to_bool(payload.get("inTop100AllTime")),
            "career_games_played": to_int(regular.get("gamesPlayed")),
            "career_goals": to_int(regular.get("goals")),
            "career_assists": to_int(regular.get("assists")),
            "career_points": to_int(regular.get("points")),
            "career_wins": to_int(regular.get("wins")),
            "career_shutouts": to_int(regular.get("shutouts")),
            "career_save_pct": to_float(regular.get("savePctg")),
            "career_goals_against_average": to_float(regular.get("goalsAgainstAvg")),
            "career_playoff_games_played": to_int(playoffs.get("gamesPlayed")),
            "career_playoff_points": to_int(playoffs.get("points")),
        }
    ]


def flatten_career(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Flatten a player landing's ``seasonTotals`` into one row per season, league, and team."""
    player_id = to_int(payload.get("playerId"))
    records = [value for value in payload.get("seasonTotals") or [] if isinstance(value, Mapping)]
    return flatten(records, CAREER_SPEC, defaults={"player_id": player_id}, key=("player_id",))


def flatten_game_log(
    payload: Mapping[str, Any], *, player_id: int, season: int | None, game_type: int | None
) -> list[dict[str, Any]]:
    """Flatten an api-web player ``game-log`` document into one row per game."""
    records = [value for value in payload.get("gameLog") or [] if isinstance(value, Mapping)]
    return flatten(
        records,
        GAME_LOG_SPEC,
        defaults={
            "player_id": player_id,
            "season": to_int(payload.get("seasonId")) or season,
            "game_type": to_int(payload.get("gameTypeId")) or game_type,
        },
        key=("player_id",),
    )


def flatten_search(payload: Any) -> list[dict[str, Any]]:
    """Flatten the player-search result array."""
    rows: list[dict[str, Any]] = []
    for player in payload if isinstance(payload, list) else []:
        if not isinstance(player, Mapping) or to_int(player.get("playerId")) is None:
            continue
        rows.append(
            {
                "player_id": to_int(player.get("playerId")),
                "player_name": player.get("name") or None,
                "position_code": player.get("positionCode") or None,
                "active": to_bool(player.get("active")),
                "team_id": to_int(player.get("teamId")),
                "team_abbrev": player.get("teamAbbrev") or None,
                "last_team_id": to_int(player.get("lastTeamId")),
                "last_team_abbrev": player.get("lastTeamAbbrev") or None,
                "last_season": to_int(player.get("lastSeasonId")),
                "sweater_number": to_int(player.get("sweaterNumber")),
                "height_inches": to_int(player.get("heightInInches")),
                "weight_pounds": to_int(player.get("weightInPounds")),
                "birth_city": player.get("birthCity") or None,
                "birth_state_province": player.get("birthStateProvince") or None,
                "birth_country": player.get("birthCountry") or None,
            }
        )
    return rows
