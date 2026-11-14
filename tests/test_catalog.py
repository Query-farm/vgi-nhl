"""Tests for the SQL-facing catalog shape and discovery metadata."""

from __future__ import annotations

import json
import re
from pathlib import Path

from vgi_nhl import league, stats
from vgi_nhl.games import ON_ICE_GOALS_EXAMPLE
from vgi_nhl.players import ROSTER_SCORING_EXAMPLE
from vgi_nhl.stats import POWER_FORWARDS_EXAMPLE
from vgi_nhl.worker import AGENT_TASKS, NHL_CATALOG

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = NHL_CATALOG.schemas[0]


def test_catalog_surface() -> None:
    assert NHL_CATALOG.name == "nhl"
    assert SCHEMA.path == ["main"]
    assert {function.Meta.name for function in SCHEMA.functions} == {
        "standings",
        "all_current_standings",
        "all_standings_seasons",
        "schedule",
        "all_current_schedule",
        "scores",
        "all_current_scores",
        "team_schedule",
        "playoff_bracket",
        "draft_picks",
        "all_teams",
        "all_franchises",
        "skater_stats",
        "skater_realtime_stats",
        "goalie_stats",
        "team_stats",
        "skater_leaders",
        "goalie_leaders",
        "all_current_skater_leaders",
        "all_current_goalie_leaders",
        "roster",
        "player",
        "player_career",
        "player_game_log",
        "player_search",
        "box_score",
        "box_score_goalies",
        "play_by_play",
        "shift_chart",
    }
    assert {table.name: table.function for table in SCHEMA.tables} == {
        "current_standings": league.CurrentStandingsFunction,
        "current_schedule": league.CurrentScheduleFunction,
        "current_scores": league.CurrentScoresFunction,
        "current_skater_leaders": stats.CurrentSkaterLeadersFunction,
        "current_goalie_leaders": stats.CurrentGoalieLeadersFunction,
        "standings_seasons": league.StandingsSeasonsFunction,
        "teams": league.TeamsFunction,
        "franchises": league.FranchisesFunction,
    }


def _key_of(table, kind: str) -> list[tuple[str, ...]]:
    return [
        tuple(name for path in record.definition.column_paths for name in path)
        for record in table.constraints
        if record.definition.kind == kind
    ]


def test_table_keys() -> None:
    keys = {table.name: _key_of(table, "PRIMARY_KEY") for table in SCHEMA.tables}
    assert keys == {
        "current_standings": [("team_abbrev",)],
        "current_schedule": [("game_id",)],
        "current_scores": [("game_id",)],
        "current_skater_leaders": [("category", "rank")],
        "current_goalie_leaders": [("category", "rank")],
        "standings_seasons": [("season",)],
        "teams": [("team_id",)],
        "franchises": [("franchise_id",)],
    }
    leaders = next(table for table in SCHEMA.tables if table.name == "current_skater_leaders")
    assert _key_of(leaders, "NOT_NULL") == [("category",), ("rank",)]


def test_every_function_has_discovery_metadata() -> None:
    for function in SCHEMA.functions:
        tags = function.Meta.tags
        for key in ("vgi.title", "vgi.doc_llm", "vgi.doc_md", "vgi.result_columns_schema"):
            assert tags.get(key), f"{function.Meta.name} lacks {key}"
        queries = json.loads(tags["vgi.example_queries"])
        assert queries and all("nhl.main." in query["sql"] for query in queries)
        columns = json.loads(tags["vgi.result_columns_schema"])
        assert [column["name"] for column in columns] == function.FIXED_SCHEMA.names
        assert all(column["description"] for column in columns)


def test_table_tags_and_column_comments() -> None:
    for table in SCHEMA.tables:
        assert (
            table.tags["vgi.title"] and table.tags["vgi.doc_llm"] and json.loads(table.tags["vgi.keywords"])
        )
        assert set(table.column_comments) == set(table.function.FIXED_SCHEMA.names)


def test_catalog_discovery_contract_is_public_and_machine_readable() -> None:
    examples = json.loads(NHL_CATALOG.tags["vgi.executable_examples"])
    tasks = json.loads(NHL_CATALOG.tags["vgi.agent_test_tasks"])
    assert examples
    assert all({"name", "description", "sql", "expected_result"} <= example.keys() for example in examples)
    assert 6 <= len(tasks) <= 12
    assert all(set(task) == {"name", "prompt"} for task in tasks)
    assert len({task["name"] for task in tasks}) == len(tasks)
    for key in ("vgi.title", "vgi.subtitle", "vgi.doc_llm", "vgi.doc_md", "vgi.keywords"):
        assert NHL_CATALOG.tags[key]
    assert "Not affiliated" in NHL_CATALOG.tags["vgi.copyright"]


def test_agent_sidecar_grades_every_task_with_check_sql() -> None:
    text = (ROOT / "vgi-agent-tests.yaml").read_text()
    names = re.findall(r"^  - name: (\S+)$", text, re.MULTILINE)
    assert names == [task["name"] for task in AGENT_TASKS]
    assert "\n    reference_sql:" not in text
    assert text.count("check_sql:") == len(AGENT_TASKS)
    exercised = set(re.findall(r"nhl\.main\.(\w+)", text))
    public = {table.name for table in SCHEMA.tables} | {
        function.Meta.name for function in SCHEMA.functions if not function.Meta.name.startswith("all_")
    }
    assert public <= exercised, sorted(public - exercised)


def test_composed_examples_reach_schema_and_driving_function() -> None:
    composed = {
        "play_by_play": ON_ICE_GOALS_EXAMPLE,
        "roster": ROSTER_SCORING_EXAMPLE,
        "skater_stats": POWER_FORWARDS_EXAMPLE,
    }
    schema_queries = json.loads(SCHEMA.tags["vgi.example_queries"])
    functions = {function.Meta.name: function for function in SCHEMA.functions}
    for name, (description, sql) in composed.items():
        assert len(set(re.findall(r"nhl\.main\.(\w+)", sql))) >= 2, name
        assert {"description": description, "sql": sql} in schema_queries
        # Agents see only the first five examples of each function.
        first_five = json.loads(functions[name].Meta.tags["vgi.example_queries"])[:5]
        assert {"description": description, "sql": sql} in first_five, name
        assert any(example.sql == sql for example in functions[name].Meta.examples[:5]), name


def test_saved_answer_tasks_grade_the_saved_answer() -> None:
    # A check_sql that only re-derives the truth passes whatever the analyst answers; tasks that
    # ask for a saved temp table must read that table so a wrong answer fails.
    text = (ROOT / "vgi-agent-tests.yaml").read_text()
    blocks = dict(re.findall(r"^  - name: (\S+)\n(.*?)(?=^  - name: |\Z)", text, re.MULTILINE | re.DOTALL))
    saved = {
        task["name"]: match.group(1)
        for task in AGENT_TASKS
        if (match := re.search(r"temp table named (\w+)", task["prompt"]))
    }
    assert saved
    for name, table in saved.items():
        assert re.search(rf"\bFROM {table}\b", blocks[name]), name
