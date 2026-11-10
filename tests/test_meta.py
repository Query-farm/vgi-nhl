"""Value conversion and discovery-metadata helpers."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pyarrow as pa
import pytest

from vgi_nhl.meta import (
    clock_seconds,
    column_comments,
    field,
    full_name,
    result_columns_schema,
    text,
    to_bool,
    to_date,
    to_float,
    to_int,
    to_timestamp,
    valid_season,
)


def test_localized_text_and_names() -> None:
    assert text({"default": " Montréal ", "fr": "Montréal"}) == "Montréal"
    assert text("plain") == "plain"
    assert text({"fr": "x"}) is None and text("  ") is None and text(3) is None
    assert full_name({"default": "Connor"}, {"default": "McDavid"}) == "Connor McDavid"
    assert full_name(None, {"default": "Ovechkin"}) == "Ovechkin"
    assert full_name(None, None) is None


def test_numbers() -> None:
    assert to_int("12") == 12 and to_int(3.0) == 3
    assert to_int(True) is None and to_int(2.5) is None and to_int("x") is None and to_int(None) is None
    assert to_float("0.5") == 0.5 and to_float(1) == 1.0
    assert to_float(float("nan")) is None and to_float(float("inf")) is None
    assert to_float("") is None and to_float(False) is None and to_float("x") is None


def test_booleans_dates_and_clocks() -> None:
    assert to_bool(True) is True and to_bool(0) is False and to_bool(1) is True
    assert to_bool(2) is None and to_bool("true") is None
    assert to_date("2025-10-07") == date(2025, 10, 7)
    assert to_date("2027-06-10T00:00:00") == date(2027, 6, 10)
    assert to_date("bad-date!!") is None and to_date(None) is None
    assert to_timestamp("2025-10-07T21:00:00Z") == datetime(2025, 10, 7, 21, tzinfo=UTC)
    assert to_timestamp("2025-10-07T21:00:00") == datetime(2025, 10, 7, 21, tzinfo=UTC)
    assert to_timestamp("nope") is None and to_timestamp("") is None
    assert clock_seconds("21:54") == 1_314
    assert clock_seconds("3009:39") == 180_579
    assert clock_seconds("1:60") is None and clock_seconds(None) is None


def test_season_validation() -> None:
    assert valid_season(20252026) == 20252026
    with pytest.raises(ValueError, match="8-digit"):
        valid_season(2025)


def test_result_columns_schema_types_and_comments() -> None:
    schema = pa.schema(
        [
            field("a", pa.int32(), "An int."),
            field("b", pa.int64(), "A big int."),
            field("c", pa.float64(), "A double."),
            field("d", pa.string(), "Text."),
            field("e", pa.bool_(), "Flag."),
            field("f", pa.date32(), "Day."),
            field("g", pa.timestamp("us", tz="UTC"), "Instant."),
            field("h", pa.timestamp("us"), "Local."),
        ]
    )
    rendered = json.loads(result_columns_schema(schema))
    assert [column["type"] for column in rendered] == [
        "INTEGER",
        "BIGINT",
        "DOUBLE",
        "VARCHAR",
        "BOOLEAN",
        "DATE",
        "TIMESTAMP WITH TIME ZONE",
        "TIMESTAMP",
    ]
    assert rendered[0]["description"] == "An int"
    assert column_comments(schema)["d"] == "Text."
    with pytest.raises(ValueError, match="Unsupported"):
        result_columns_schema(pa.schema([pa.field("x", pa.binary())]))
