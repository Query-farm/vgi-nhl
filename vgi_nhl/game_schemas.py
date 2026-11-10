"""Arrow schemas and flattening for one game's box score, play-by-play, and shift chart."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pyarrow as pa

from vgi_nhl.meta import clock_seconds, field, full_name, mapping, text, to_float, to_int

INT, BIG, DBL, STR = pa.int32(), pa.int64(), pa.float64(), pa.string()
PERIOD_SECONDS = 20 * 60

_GAME_TEAM = [
    field("game_id", BIG, "NHL game id."),
    field("team_side", STR, "away or home."),
    field("team_id", INT, "NHL team id."),
    field("team_abbrev", STR, "Three-letter team code."),
    field("player_id", INT, "Stable NHL player id.", nullable=False),
    field("player_name", STR, "Player name as an initial and last name, such as C. McDavid."),
    field("sweater_number", INT, "Jersey number."),
]

BOX_SCORE_SCHEMA = pa.schema(
    [
        *_GAME_TEAM,
        field("position", STR, "Position code: C, L, R, or D."),
        field("goals", INT, "Goals."),
        field("assists", INT, "Assists."),
        field("points", INT, "Points."),
        field("plus_minus", INT, "Plus-minus."),
        field("penalty_minutes", INT, "Penalty minutes."),
        field("hits", INT, "Hits delivered."),
        field("power_play_goals", INT, "Power-play goals."),
        field("shots_on_goal", INT, "Shots on goal."),
        field("faceoff_win_pct", DBL, "Faceoffs won divided by faceoffs taken (0-1); 0 when none taken."),
        field("toi", STR, "Time on ice as MM:SS."),
        field("toi_seconds", INT, "Time on ice in seconds."),
        field("blocked_shots", INT, "Opponent shots blocked."),
        field("shifts", INT, "Shifts taken."),
        field("giveaways", INT, "Giveaways."),
        field("takeaways", INT, "Takeaways."),
    ]
)

BOX_SCORE_GOALIES_SCHEMA = pa.schema(
    [
        *_GAME_TEAM,
        field("starter", pa.bool_(), "Whether the goalie started the game."),
        field("decision", STR, "Decision: W win, L loss, O overtime/shootout loss; NULL otherwise."),
        field("shots_against", INT, "Shots on goal faced."),
        field("saves", INT, "Saves."),
        field("goals_against", INT, "Goals allowed."),
        field("save_pct", DBL, "Saves divided by shots against (0-1); NULL without shots faced."),
        field("even_strength_goals_against", INT, "Even-strength goals allowed."),
        field("power_play_goals_against", INT, "Goals allowed while the opponent was on a power play."),
        field("shorthanded_goals_against", INT, "Goals allowed while the opponent was shorthanded."),
        field("penalty_minutes", INT, "Penalty minutes."),
        field("toi", STR, "Time on ice as MM:SS."),
        field("toi_seconds", INT, "Time on ice in seconds."),
    ]
)

PLAY_BY_PLAY_SCHEMA = pa.schema(
    [
        field("game_id", BIG, "NHL game id."),
        field("event_id", INT, "Event id, unique within the game.", nullable=False),
        field("sort_order", INT, "Chronological ordering key for events."),
        field("period", INT, "Period number; 4 and above are overtime (5 is a regular-season shootout)."),
        field("period_type", STR, "Period type: REG, OT, or SO."),
        field("time_in_period", STR, "Elapsed time in the period as MM:SS."),
        field("time_remaining", STR, "Time remaining in the period as MM:SS."),
        field("game_seconds", INT, "Seconds since the opening faceoff, assuming 20-minute periods."),
        field(
            "situation_code",
            STR,
            "Four digits: away goalie in net, away skaters, home skaters, home goalie in net (1551 = 5v5).",
        ),
        field("home_team_defending_side", STR, "Side of the rink the home team defends: left or right."),
        field("type_code", INT, "NHL numeric event type code."),
        field(
            "event_type",
            STR,
            "Event type, such as goal, shot-on-goal, missed-shot, blocked-shot, hit, faceoff, or penalty.",
        ),
        field("event_owner_team_id", INT, "NHL team id credited with the event."),
        field("event_owner_team_abbrev", STR, "Three-letter code of the team credited with the event."),
        field("x_coord", INT, "Rink x coordinate in feet from centre ice (-100 to 100)."),
        field("y_coord", INT, "Rink y coordinate in feet from centre ice (-42.5 to 42.5)."),
        field("zone_code", STR, "Zone relative to the event owner: O offensive, D defensive, N neutral."),
        field("shot_type", STR, "Shot type, such as wrist, snap, slap, backhand, tip-in, or deflected."),
        field("reason", STR, "Reason for a miss or stoppage, such as wide-of-net or icing."),
        field("secondary_reason", STR, "Secondary stoppage reason, such as tv-timeout."),
        field("penalty_severity", STR, "Penalty class: MIN minor, MAJ major, MIS misconduct, BEN bench."),
        field("penalty_type", STR, "Penalty infraction, such as tripping or slashing."),
        field("penalty_minutes", INT, "Penalty duration in minutes."),
        field(
            "primary_player_id",
            INT,
            "Main actor: scorer, shooter, faceoff winner, hitter, penalized player, or puck carrier.",
        ),
        field("primary_player_name", STR, "Full name of the primary player."),
        field(
            "secondary_player_id",
            INT,
            "Counterpart: primary assist, goalie or blocker, faceoff loser, player hit, or penalty drawer.",
        ),
        field("secondary_player_name", STR, "Full name of the secondary player."),
        field("assist1_player_id", INT, "Primary assist on a goal."),
        field("assist2_player_id", INT, "Secondary assist on a goal."),
        field("goalie_in_net_id", INT, "Defending goalie on a shot or goal; NULL for an empty net."),
        field("away_score", INT, "Away team score after a goal."),
        field("home_score", INT, "Home team score after a goal."),
        field("away_shots_on_goal", INT, "Away team shots on goal after a shot."),
        field("home_shots_on_goal", INT, "Home team shots on goal after a shot."),
    ]
)

SHIFT_CHART_SCHEMA = pa.schema(
    [
        field("game_id", BIG, "NHL game id."),
        field("shift_id", BIG, "Shift record id.", nullable=False),
        field("player_id", INT, "Stable NHL player id."),
        field("player_name", STR, "Player full name."),
        field("team_id", INT, "NHL team id."),
        field("team_abbrev", STR, "Three-letter team code."),
        field("period", INT, "Period number."),
        field("shift_number", INT, "The player's shift number in the game."),
        field("start_time", STR, "Shift start as elapsed MM:SS in the period."),
        field("end_time", STR, "Shift end as elapsed MM:SS in the period."),
        field("duration", STR, "Shift length as MM:SS."),
        field("start_seconds", INT, "Shift start in seconds since the opening faceoff."),
        field("end_seconds", INT, "Shift end in seconds since the opening faceoff."),
        field("duration_seconds", INT, "Shift length in seconds."),
    ]
)

# Which detail keys name the primary and secondary players for each event type.
_ACTORS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "goal": (("scoringPlayerId",), ("assist1PlayerId",)),
    "shot-on-goal": (("shootingPlayerId",), ("goalieInNetId",)),
    "missed-shot": (("shootingPlayerId",), ("goalieInNetId",)),
    "failed-shot-attempt": (("shootingPlayerId",), ("goalieInNetId",)),
    "blocked-shot": (("shootingPlayerId",), ("blockingPlayerId",)),
    "faceoff": (("winningPlayerId",), ("losingPlayerId",)),
    "hit": (("hittingPlayerId",), ("hitteePlayerId",)),
    "penalty": (("committedByPlayerId", "servedByPlayerId"), ("drawnByPlayerId",)),
    "giveaway": (("playerId",), ()),
    "takeaway": (("playerId",), ()),
}


def _game_seconds(period: int | None, clock: Any) -> int | None:
    seconds = clock_seconds(clock)
    if period is None or seconds is None:
        return None
    return (period - 1) * PERIOD_SECONDS + seconds


def flatten_box_score(payload: Mapping[str, Any], *, goalies: bool) -> list[dict[str, Any]]:
    """Flatten a gamecenter ``boxscore`` into one row per skater (or per goalie)."""
    game_id = to_int(payload.get("id"))
    by_side = mapping(payload.get("playerByGameStats"))
    rows: list[dict[str, Any]] = []
    for side in ("away", "home"):
        team = mapping(payload.get(f"{side}Team"))
        groups = mapping(by_side.get(f"{side}Team"))
        names = ("goalies",) if goalies else ("forwards", "defense")
        for group in names:
            for player in groups.get(group) or []:
                if not isinstance(player, Mapping) or to_int(player.get("playerId")) is None:
                    continue
                row: dict[str, Any] = {
                    "game_id": game_id,
                    "team_side": side,
                    "team_id": to_int(team.get("id")),
                    "team_abbrev": team.get("abbrev") or None,
                    "player_id": to_int(player.get("playerId")),
                    "player_name": text(player.get("name")),
                    "sweater_number": to_int(player.get("sweaterNumber")),
                    "penalty_minutes": to_int(player.get("pim")),
                    "toi": player.get("toi") or None,
                    "toi_seconds": clock_seconds(player.get("toi")),
                }
                if goalies:
                    row |= {
                        "starter": player.get("starter") if isinstance(player.get("starter"), bool) else None,
                        "decision": player.get("decision") or None,
                        "shots_against": to_int(player.get("shotsAgainst")),
                        "saves": to_int(player.get("saves")),
                        "goals_against": to_int(player.get("goalsAgainst")),
                        "save_pct": to_float(player.get("savePctg")),
                        "even_strength_goals_against": to_int(player.get("evenStrengthGoalsAgainst")),
                        "power_play_goals_against": to_int(player.get("powerPlayGoalsAgainst")),
                        "shorthanded_goals_against": to_int(player.get("shorthandedGoalsAgainst")),
                    }
                else:
                    row |= {
                        "position": player.get("position") or None,
                        "goals": to_int(player.get("goals")),
                        "assists": to_int(player.get("assists")),
                        "points": to_int(player.get("points")),
                        "plus_minus": to_int(player.get("plusMinus")),
                        "hits": to_int(player.get("hits")),
                        "power_play_goals": to_int(player.get("powerPlayGoals")),
                        "shots_on_goal": to_int(player.get("sog")),
                        "faceoff_win_pct": to_float(player.get("faceoffWinningPctg")),
                        "blocked_shots": to_int(player.get("blockedShots")),
                        "shifts": to_int(player.get("shifts")),
                        "giveaways": to_int(player.get("giveaways")),
                        "takeaways": to_int(player.get("takeaways")),
                    }
                rows.append(row)
    return rows


def _first(details: Mapping[str, Any], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        value = to_int(details.get(key))
        if value is not None:
            return value
    return None


def flatten_play_by_play(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Flatten a gamecenter ``play-by-play`` into one row per event."""
    game_id = to_int(payload.get("id"))
    names = {
        to_int(spot.get("playerId")): full_name(spot.get("firstName"), spot.get("lastName"))
        for spot in payload.get("rosterSpots") or []
        if isinstance(spot, Mapping)
    }
    teams = {
        to_int(mapping(payload.get(side)).get("id")): mapping(payload.get(side)).get("abbrev")
        for side in ("awayTeam", "homeTeam")
    }
    rows: list[dict[str, Any]] = []
    for play in payload.get("plays") or []:
        if not isinstance(play, Mapping) or to_int(play.get("eventId")) is None:
            continue
        details = mapping(play.get("details"))
        period = mapping(play.get("periodDescriptor"))
        event_type = play.get("typeDescKey") or None
        primary_keys, secondary_keys = _ACTORS.get(event_type or "", ((), ()))
        primary, secondary = _first(details, primary_keys), _first(details, secondary_keys)
        owner = to_int(details.get("eventOwnerTeamId"))
        period_number = to_int(period.get("number"))
        is_penalty = event_type == "penalty"
        rows.append(
            {
                "game_id": game_id,
                "event_id": to_int(play.get("eventId")),
                "sort_order": to_int(play.get("sortOrder")),
                "period": period_number,
                "period_type": period.get("periodType") or None,
                "time_in_period": play.get("timeInPeriod") or None,
                "time_remaining": play.get("timeRemaining") or None,
                "game_seconds": _game_seconds(period_number, play.get("timeInPeriod")),
                "situation_code": play.get("situationCode") or None,
                "home_team_defending_side": play.get("homeTeamDefendingSide") or None,
                "type_code": to_int(play.get("typeCode")),
                "event_type": event_type,
                "event_owner_team_id": owner,
                "event_owner_team_abbrev": teams.get(owner) if owner is not None else None,
                "x_coord": to_int(details.get("xCoord")),
                "y_coord": to_int(details.get("yCoord")),
                "zone_code": details.get("zoneCode") or None,
                "shot_type": details.get("shotType") or None,
                "reason": details.get("reason") or None,
                "secondary_reason": details.get("secondaryReason") or None,
                "penalty_severity": (details.get("typeCode") or None) if is_penalty else None,
                "penalty_type": (details.get("descKey") or None) if is_penalty else None,
                "penalty_minutes": to_int(details.get("duration")) if is_penalty else None,
                "primary_player_id": primary,
                "primary_player_name": names.get(primary) if primary is not None else None,
                "secondary_player_id": secondary,
                "secondary_player_name": names.get(secondary) if secondary is not None else None,
                "assist1_player_id": to_int(details.get("assist1PlayerId")),
                "assist2_player_id": to_int(details.get("assist2PlayerId")),
                "goalie_in_net_id": to_int(details.get("goalieInNetId")),
                "away_score": to_int(details.get("awayScore")),
                "home_score": to_int(details.get("homeScore")),
                "away_shots_on_goal": to_int(details.get("awaySOG")),
                "home_shots_on_goal": to_int(details.get("homeSOG")),
            }
        )
    rows.sort(key=lambda row: (row["sort_order"] is None, row["sort_order"] or 0, row["event_id"]))
    return rows


SHIFT_TYPE_CODE = 517


def flatten_shift_chart(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Flatten a stats REST ``shiftcharts`` response into one row per shift (goal markers dropped)."""
    rows: list[dict[str, Any]] = []
    for shift in payload.get("data") or []:
        if not isinstance(shift, Mapping) or to_int(shift.get("typeCode")) != SHIFT_TYPE_CODE:
            continue
        if to_int(shift.get("id")) is None:
            continue
        period = to_int(shift.get("period"))
        rows.append(
            {
                "game_id": to_int(shift.get("gameId")),
                "shift_id": to_int(shift.get("id")),
                "player_id": to_int(shift.get("playerId")),
                "player_name": full_name(shift.get("firstName"), shift.get("lastName")),
                "team_id": to_int(shift.get("teamId")),
                "team_abbrev": shift.get("teamAbbrev") or None,
                "period": period,
                "shift_number": to_int(shift.get("shiftNumber")),
                "start_time": shift.get("startTime") or None,
                "end_time": shift.get("endTime") or None,
                "duration": shift.get("duration") or None,
                "start_seconds": _game_seconds(period, shift.get("startTime")),
                "end_seconds": _game_seconds(period, shift.get("endTime")),
                "duration_seconds": clock_seconds(shift.get("duration")),
            }
        )
    rows.sort(key=lambda row: (row["start_seconds"] or 0, row["team_id"] or 0, row["player_id"] or 0))
    return rows
