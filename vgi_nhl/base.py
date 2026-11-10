"""Shared machinery for the NHL table functions."""

from __future__ import annotations

import json
from typing import Any, ClassVar

import pyarrow as pa
from vgi.arguments import Arg
from vgi.cache_control import CacheControl
from vgi.metadata import FunctionExample
from vgi.table_function import ProcessParams, TableCardinality
from vgi_rpc.rpc import OutputCollector

from vgi_nhl import api
from vgi_nhl.meta import batch_from_rows, result_columns_schema, valid_season

Rows = tuple[list[dict[str, Any]], int]
"""Flattened rows plus the freshness lifetime, in seconds, to advertise for them."""

GAME_TYPES = (1, 2, 3)

SEASON_ARG = Arg(
    "season",
    default=None,
    arrow_type=pa.int32(),
    ge=19171918,
    le=20992100,
    doc="8-digit NHL season id such as 20252026 for 2025-26. NULL selects the current season.",
)
GAME_TYPE_ARG = Arg(
    "game_type",
    default=2,
    arrow_type=pa.int32(),
    choices=GAME_TYPES,
    doc="NHL game type: 2 regular season (default), 3 playoffs, or 1 preseason.",
)


def resolve_season(season: int | None) -> int:
    """Validate an explicit season id, or resolve the current one from the NHL."""
    return valid_season(season) if season is not None else api.current_season()


def cache_control(ttl: int) -> CacheControl | None:
    """Advertise the upstream freshness lifetime to VGI clients."""
    return CacheControl(ttl=ttl) if ttl > 0 else None


def make_tags(
    *,
    category: str,
    title: str,
    llm: str,
    md: str,
    schema: pa.Schema,
    examples: list[tuple[str, str]],
) -> dict[str, str]:
    """Build the discovery tags every NHL function carries."""
    return {
        "provider": "nhl",
        "vgi.category": category,
        "vgi.title": title,
        "vgi.result_columns_schema": result_columns_schema(schema),
        "vgi.doc_llm": llm,
        "vgi.doc_md": md,
        "vgi.example_queries": json.dumps(
            [{"description": description, "sql": sql} for description, sql in examples]
        ),
    }


def make_examples(pairs: list[tuple[str, str]]) -> list[FunctionExample]:
    """Mirror example queries as SDK function examples."""
    return [FunctionExample(sql=sql, description=description) for description, sql in pairs]


class Fetching:
    """Mixin implementing cardinality and processing for one-shot fetch-and-emit functions.

    Subclasses implement :meth:`rows`, returning flattened rows and the
    upstream freshness lifetime; the mixin projects them onto the requested
    output schema and emits a single batch.
    """

    ESTIMATE: ClassVar[int] = 100
    MAXIMUM: ClassVar[int | None] = None

    @classmethod
    def rows(cls, args: Any) -> Rows:
        """Fetch and flatten the rows for ``args``."""
        raise NotImplementedError

    @classmethod
    def cardinality(cls, params: object) -> TableCardinality:
        """Return a planner estimate for this function's result size."""
        return TableCardinality(estimate=cls.ESTIMATE, max=cls.MAXIMUM)

    @classmethod
    def process(cls, params: ProcessParams[Any], state: None, out: OutputCollector) -> None:
        """Fetch, flatten, and emit the result as one Arrow batch."""
        rows, ttl = cls.rows(params.args)
        out.emit(batch_from_rows(rows, params.output_schema), cache_control=cache_control(ttl))
        out.finish()
