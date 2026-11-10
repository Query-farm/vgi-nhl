"""Arrow schemas and flattening for NHL stats REST season reports.

Each report is described once as ``(column, type, comment, source key)`` and
both the Arrow schema and the row flattener are generated from that spec, so
the two cannot drift apart.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import pyarrow as pa

from vgi_nhl.meta import Spec, schema_of

INT, DBL, STR = pa.int32(), pa.float64(), pa.string()


def _string(key: str) -> Callable[[Mapping[str, Any]], Any]:
    return lambda row: row.get(key) or None


_PLAYER_CONTEXT: list[Spec] = [
    ("season", INT, "NHL season id, such as 20252026.", "seasonId"),
    ("game_type", INT, "NHL game type: 1 preseason, 2 regular season, 3 playoffs.", "gameTypeId"),
    ("player_id", INT, "Stable NHL player id.", "playerId"),
]

SKATER_STATS_SPEC: list[Spec] = [
    *_PLAYER_CONTEXT,
    ("player_name", STR, "Player full name.", _string("skaterFullName")),
    ("last_name", STR, "Player last name.", _string("lastName")),
    (
        "team_abbrevs",
        STR,
        "Team codes the player skated for this season, in order, comma-separated.",
        _string("teamAbbrevs"),
    ),
    ("position_code", STR, "Position code: C, L, R, or D.", _string("positionCode")),
    ("shoots_catches", STR, "Handedness: L or R.", _string("shootsCatches")),
    ("games_played", INT, "Games played.", "gamesPlayed"),
    ("goals", INT, "Goals.", "goals"),
    ("assists", INT, "Assists.", "assists"),
    ("points", INT, "Points (goals plus assists).", "points"),
    ("plus_minus", INT, "Plus-minus.", "plusMinus"),
    ("penalty_minutes", INT, "Penalty minutes.", "penaltyMinutes"),
    ("points_per_game", DBL, "Points per game played.", "pointsPerGame"),
    ("even_strength_goals", INT, "Even-strength goals.", "evGoals"),
    ("even_strength_points", INT, "Even-strength points.", "evPoints"),
    ("power_play_goals", INT, "Power-play goals.", "ppGoals"),
    ("power_play_points", INT, "Power-play points.", "ppPoints"),
    ("shorthanded_goals", INT, "Shorthanded goals.", "shGoals"),
    ("shorthanded_points", INT, "Shorthanded points.", "shPoints"),
    ("game_winning_goals", INT, "Game-winning goals.", "gameWinningGoals"),
    ("overtime_goals", INT, "Overtime goals.", "otGoals"),
    ("shots", INT, "Shots on goal.", "shots"),
    ("shooting_pct", DBL, "Goals divided by shots on goal (0-1).", "shootingPct"),
    (
        "faceoff_win_pct",
        DBL,
        "Faceoffs won divided by faceoffs taken (0-1); NULL without faceoffs.",
        "faceoffWinPct",
    ),
    ("time_on_ice_per_game_seconds", DBL, "Average time on ice per game, in seconds.", "timeOnIcePerGame"),
]

SKATER_REALTIME_SPEC: list[Spec] = [
    *_PLAYER_CONTEXT,
    ("player_name", STR, "Player full name.", _string("skaterFullName")),
    ("last_name", STR, "Player last name.", _string("lastName")),
    (
        "team_abbrevs",
        STR,
        "Team codes the player skated for this season, comma-separated.",
        _string("teamAbbrevs"),
    ),
    ("position_code", STR, "Position code: C, L, R, or D.", _string("positionCode")),
    ("shoots_catches", STR, "Handedness: L or R.", _string("shootsCatches")),
    ("games_played", INT, "Games played.", "gamesPlayed"),
    ("hits", INT, "Body checks delivered.", "hits"),
    ("hits_per_60", DBL, "Hits per 60 minutes of ice time.", "hitsPer60"),
    ("blocked_shots", INT, "Opponent shots blocked.", "blockedShots"),
    ("blocked_shots_per_60", DBL, "Blocked shots per 60 minutes of ice time.", "blockedShotsPer60"),
    ("giveaways", INT, "Giveaways.", "giveaways"),
    ("giveaways_per_60", DBL, "Giveaways per 60 minutes of ice time.", "giveawaysPer60"),
    ("takeaways", INT, "Takeaways.", "takeaways"),
    ("takeaways_per_60", DBL, "Takeaways per 60 minutes of ice time.", "takeawaysPer60"),
    ("total_shot_attempts", INT, "All shot attempts: on goal, missed, and blocked.", "totalShotAttempts"),
    ("missed_shots", INT, "Shot attempts that missed the net.", "missedShots"),
    ("missed_shot_wide_of_net", INT, "Missed shots wide of the net.", "missedShotWideOfNet"),
    ("missed_shot_over_net", INT, "Missed shots over the net.", "missedShotOverNet"),
    ("missed_shot_goalpost", INT, "Missed shots that hit a goalpost.", "missedShotGoalpost"),
    ("missed_shot_crossbar", INT, "Missed shots that hit the crossbar.", "missedShotCrossbar"),
    ("missed_shot_short", INT, "Missed shots that fell short.", "missedShotShort"),
    (
        "missed_shot_failed_bank_attempt",
        INT,
        "Missed bank-shot attempts.",
        "missedShotFailedBankAttempt",
    ),
    (
        "shot_attempts_blocked",
        INT,
        "The player's own shot attempts that were blocked.",
        "shotAttemptsBlocked",
    ),
    ("empty_net_goals", INT, "Empty-net goals.", "emptyNetGoals"),
    ("empty_net_assists", INT, "Empty-net assists.", "emptyNetAssists"),
    ("empty_net_points", INT, "Empty-net points.", "emptyNetPoints"),
    ("first_goals", INT, "Games in which the player scored the first goal.", "firstGoals"),
    ("overtime_goals", INT, "Overtime goals.", "otGoals"),
    ("time_on_ice_per_game_seconds", DBL, "Average time on ice per game, in seconds.", "timeOnIcePerGame"),
]

GOALIE_STATS_SPEC: list[Spec] = [
    *_PLAYER_CONTEXT,
    ("player_name", STR, "Goalie full name.", _string("goalieFullName")),
    ("last_name", STR, "Goalie last name.", _string("lastName")),
    (
        "team_abbrevs",
        STR,
        "Team codes the goalie played for this season, comma-separated.",
        _string("teamAbbrevs"),
    ),
    ("shoots_catches", STR, "Catching hand: L or R.", _string("shootsCatches")),
    ("games_played", INT, "Games played.", "gamesPlayed"),
    ("games_started", INT, "Games started.", "gamesStarted"),
    ("wins", INT, "Wins credited.", "wins"),
    ("losses", INT, "Regulation losses credited.", "losses"),
    ("ot_losses", INT, "Overtime and shootout losses credited.", "otLosses"),
    ("ties", INT, "Ties credited (before 2005-06); NULL otherwise.", "ties"),
    ("shots_against", INT, "Shots on goal faced.", "shotsAgainst"),
    ("saves", INT, "Saves.", "saves"),
    ("goals_against", INT, "Goals allowed.", "goalsAgainst"),
    ("save_pct", DBL, "Saves divided by shots against (0-1).", "savePct"),
    ("goals_against_average", DBL, "Goals allowed per 60 minutes played.", "goalsAgainstAverage"),
    ("shutouts", INT, "Shutouts.", "shutouts"),
    ("time_on_ice_seconds", INT, "Total time on ice, in seconds.", "timeOnIce"),
    ("goals", INT, "Goals scored by the goalie.", "goals"),
    ("assists", INT, "Assists credited to the goalie.", "assists"),
    ("points", INT, "Points credited to the goalie.", "points"),
    ("penalty_minutes", INT, "Penalty minutes.", "penaltyMinutes"),
]

TEAM_STATS_SPEC: list[Spec] = [
    ("season", INT, "NHL season id, such as 20252026.", "seasonId"),
    ("game_type", INT, "NHL game type: 1 preseason, 2 regular season, 3 playoffs.", "gameTypeId"),
    ("team_id", INT, "NHL team id.", "teamId"),
    ("team_name", STR, "Full team name.", _string("teamFullName")),
    ("games_played", INT, "Games played.", "gamesPlayed"),
    ("wins", INT, "Wins.", "wins"),
    ("losses", INT, "Regulation losses.", "losses"),
    ("ot_losses", INT, "Overtime and shootout losses.", "otLosses"),
    ("ties", INT, "Ties (before 2005-06); NULL otherwise.", "ties"),
    ("points", INT, "Standings points.", "points"),
    ("point_pct", DBL, "Points earned divided by points available (0-1).", "pointPct"),
    ("regulation_wins", INT, "Regulation wins.", "winsInRegulation"),
    ("regulation_and_ot_wins", INT, "Regulation plus overtime wins.", "regulationAndOtWins"),
    ("shootout_wins", INT, "Shootout wins.", "winsInShootout"),
    ("goals_for", INT, "Goals scored.", "goalsFor"),
    ("goals_against", INT, "Goals allowed.", "goalsAgainst"),
    ("goals_for_per_game", DBL, "Goals scored per game.", "goalsForPerGame"),
    ("goals_against_per_game", DBL, "Goals allowed per game.", "goalsAgainstPerGame"),
    ("shots_for_per_game", DBL, "Shots on goal per game.", "shotsForPerGame"),
    ("shots_against_per_game", DBL, "Shots on goal allowed per game.", "shotsAgainstPerGame"),
    ("power_play_pct", DBL, "Power-play goals per power-play opportunity (0-1).", "powerPlayPct"),
    (
        "power_play_net_pct",
        DBL,
        "Power-play percentage net of shorthanded goals allowed (0-1).",
        "powerPlayNetPct",
    ),
    ("penalty_kill_pct", DBL, "Share of opponent power plays killed (0-1).", "penaltyKillPct"),
    (
        "penalty_kill_net_pct",
        DBL,
        "Penalty-kill percentage net of shorthanded goals scored (0-1).",
        "penaltyKillNetPct",
    ),
    ("faceoff_win_pct", DBL, "Faceoffs won divided by faceoffs taken (0-1).", "faceoffWinPct"),
    ("shutouts", INT, "Team shutouts.", "teamShutouts"),
]


SKATER_STATS_SCHEMA = schema_of(SKATER_STATS_SPEC, key=("player_id",))
SKATER_REALTIME_SCHEMA = schema_of(SKATER_REALTIME_SPEC, key=("player_id",))
GOALIE_STATS_SCHEMA = schema_of(GOALIE_STATS_SPEC, key=("player_id",))
TEAM_STATS_SCHEMA = schema_of(TEAM_STATS_SPEC, key=("team_id",))
