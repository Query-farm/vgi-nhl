"""Hermetic end-to-end coverage through Haybarn and the VGI transport."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from conftest import replay_env


def test_haybarn_attaches_and_queries_every_table(replay_server: str) -> None:
    project = Path(__file__).resolve().parent.parent
    location = f"uv run --project {project} vgi-nhl"
    sql = (
        f"INSTALL vgi FROM community; LOAD vgi; ATTACH 'nhl' (TYPE vgi, LOCATION '{location}'); "
        "SELECT "
        "(SELECT count(*) FROM nhl.main.current_standings) AS standings, "
        "(SELECT count(*) FROM nhl.main.current_schedule) AS schedule, "
        "(SELECT count(*) FROM nhl.main.current_scores) AS scores, "
        "(SELECT count(*) FROM nhl.main.current_skater_leaders) AS skater_leaders, "
        "(SELECT count(*) FROM nhl.main.current_goalie_leaders) AS goalie_leaders, "
        "(SELECT count(*) FROM nhl.main.standings_seasons) AS seasons, "
        "(SELECT count(*) FROM nhl.main.teams) AS teams, "
        "(SELECT count(*) FROM nhl.main.franchises) AS franchises, "
        "(SELECT count(*) FROM nhl.main.play_by_play(2025020001) WHERE event_type = 'goal') AS goals, "
        "(SELECT home_team_abbrev FROM nhl.main.scores(date := DATE '2025-10-07') "
        "WHERE game_id = 2025020001) AS opener_home;"
    )
    env = {**os.environ, **replay_env(replay_server)}
    result = subprocess.run(
        ["uvx", "haybarn-cli", ":memory:", "-csv", "-c", sql],
        cwd=project,
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert (
        "standings,schedule,scores,skater_leaders,goalie_leaders,seasons,teams,franchises,goals,opener_home"
        in result.stdout
    )
    assert "4,4,3,27,12,5,3,3,5,FLA" in result.stdout
