"""Metadata and value-conversion helpers shared by every NHL schema."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime
from typing import Any

import pyarrow as pa

_COMMENT_KEY = b"comment"
Source = str | Callable[[Mapping[str, Any]], Any]
"""A JSON key, or a callable that derives the value from the source object."""
Spec = tuple[str, pa.DataType, str, Source]
"""One output column: ``(name, Arrow type, comment, source)``."""

TEAM_PATTERN = r"^[A-Za-z]{3}$"
"""Three-letter NHL team codes, matched case-insensitively."""

_CLOCK = re.compile(r"^(\d{1,4}):([0-5]\d)$")


def field(name: str, kind: pa.DataType, comment: str, *, nullable: bool = True) -> pa.Field:
    """Build an Arrow field carrying its SQL column comment."""
    return pa.field(name, kind, nullable=nullable, metadata={_COMMENT_KEY: comment.encode()})


def comment_of(value: pa.Field) -> str:
    """Return the comment stored on an Arrow field."""
    if value.metadata and _COMMENT_KEY in value.metadata:
        return value.metadata[_COMMENT_KEY].decode()
    return ""


def column_comments(schema: pa.Schema) -> dict[str, str]:
    """Return the column-comment mapping expected by a catalog table."""
    return {value.name: comment_of(value) for value in schema if comment_of(value)}


def _sql_type(kind: pa.DataType) -> str:
    if pa.types.is_timestamp(kind):
        return "TIMESTAMP WITH TIME ZONE" if kind.tz else "TIMESTAMP"
    if pa.types.is_date(kind):
        return "DATE"
    if pa.types.is_boolean(kind):
        return "BOOLEAN"
    if pa.types.is_int32(kind):
        return "INTEGER"
    if pa.types.is_int64(kind):
        return "BIGINT"
    if pa.types.is_float64(kind):
        return "DOUBLE"
    if pa.types.is_string(kind):
        return "VARCHAR"
    raise ValueError(f"Unsupported NHL result type: {kind}")


def result_columns_schema(schema: pa.Schema) -> str:
    """Render a static Arrow result schema as VGI discovery metadata."""
    return json.dumps(
        [
            {
                "name": value.name,
                "type": _sql_type(value.type),
                "description": comment_of(value).removesuffix("."),
            }
            for value in schema
        ],
        separators=(",", ":"),
    )


def batch_from_rows(rows: Sequence[Mapping[str, Any]], schema: pa.Schema) -> pa.RecordBatch:
    """Build a record batch in the (possibly projected) declared column order."""
    return pa.RecordBatch.from_arrays(
        [pa.array([row.get(value.name) for row in rows], type=value.type) for value in schema],
        schema=schema,
    )


def mapping(value: Any) -> Mapping[str, Any]:
    """Return ``value`` when it is a JSON object, else an empty mapping."""
    return value if isinstance(value, Mapping) else {}


def text(value: Any) -> str | None:
    """Return the default-locale string from an NHL ``{"default": ..., "fr": ...}`` object."""
    if isinstance(value, Mapping):
        value = value.get("default")
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def full_name(first: Any, last: Any) -> str | None:
    """Join localized first and last names, tolerating either being absent."""
    parts = [part for part in (text(first), text(last)) if part]
    return " ".join(parts) or None


def to_int(value: Any) -> int | None:
    """Parse an integer-like API value without treating booleans as integers."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def to_float(value: Any) -> float | None:
    """Parse a finite numeric API value as a float."""
    if value is None or isinstance(value, bool) or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if result == result and result not in (float("inf"), float("-inf")) else None


def to_bool(value: Any) -> bool | None:
    """Parse a JSON boolean, or a 0/1 integer flag, as a boolean."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    return None


def to_date(value: Any) -> date | None:
    """Parse an ISO ``YYYY-MM-DD`` date (or the date part of a timestamp)."""
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def to_timestamp(value: Any) -> datetime | None:
    """Parse an RFC-3339 timestamp into UTC."""
    if not isinstance(value, str) or not value:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError):
        return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=UTC)
    return result.astimezone(UTC)


def clock_seconds(value: Any) -> int | None:
    """Convert an NHL ``MM:SS`` clock or time-on-ice string into whole seconds."""
    if not isinstance(value, str):
        return None
    match = _CLOCK.match(value.strip())
    if match is None:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))


def valid_season(season: int) -> int:
    """Reject a season id that is not two consecutive years, such as 20252026."""
    start, end = divmod(season, 10_000)
    if end != start + 1:
        raise ValueError(f"season must be an 8-digit NHL season id such as 20252026, not {season}")
    return season


def schema_of(spec: Sequence[Spec], *, key: Sequence[str] = ()) -> pa.Schema:
    """Build the Arrow schema for a report spec; key columns are NOT NULL."""
    return pa.schema(
        [field(name, kind, comment, nullable=name not in key) for name, kind, comment, _ in spec]
    )


def flatten(
    records: Sequence[Mapping[str, Any]],
    spec: Sequence[Spec],
    *,
    defaults: Mapping[str, Any],
    key: Sequence[str] = (),
) -> list[dict[str, Any]]:
    """Flatten stats REST rows using ``spec``.

    ``defaults`` fill context the report omits (season and game type), and
    rows missing any ``key`` column are dropped so NOT NULL keys hold.
    """
    rows: list[dict[str, Any]] = []
    for record in records:
        row: dict[str, Any] = {}
        for name, kind, _, source in spec:
            raw = source(record) if callable(source) else record.get(source)
            if raw is None and name in defaults:
                raw = defaults[name]
            if pa.types.is_floating(kind):
                row[name] = to_float(raw)
            elif pa.types.is_integer(kind):
                row[name] = to_int(raw)
            elif pa.types.is_string(kind):
                row[name] = raw if isinstance(raw, str) and raw else None
            else:
                row[name] = raw
        if all(row.get(name) is not None for name in key):
            rows.append(row)
    return rows
