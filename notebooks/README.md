# NHL SQL notebooks

[Which shift contains an event at the boundary?](01_events_at_shift_boundaries.ipynb) joins play-by-play event times to recorded shifts for Brad Marchand (8473419), in period 1 of game 2025020001 on 2025-10-07. It compares two half-open interval policies and preserves unmatched events. This is a join-semantics walkthrough, not official on-ice attribution or a player-performance evaluation.

## Run from this directory

Install [uv](https://docs.astral.sh/uv/), Git, and Python 3.13 or 3.14. First use needs network access for notebook dependencies, the published Haybarn/VGI extension and the public pinned worker revision. A copy of this entire directory is sufficient; the worker checkout is not required.

```bash
uv sync --frozen
uv run --frozen python execute.py
```

The visible SQL launches `uvx --python 3.13 --with vgi-python==0.51.0 --with vgi-rpc==0.53.1 --from git+https://github.com/Query-farm/vgi-nhl@d8aff6a88c64704047a3cd0a078c83a561de8633 vgi-nhl`. `uvx` fetches the public Git revision into its own environment; the separately locked notebook environment runs Haybarn 2.0.0rc11. When changing worker or SDK pins, repeat default, changed-parameter and live checks.

For interactive use, register this interpreter and select it in Jupyter:

```bash
uv run --frozen python -m ipykernel install --user --name vgi-nhl-notebooks --display-name 'Python (vgi-nhl notebooks)'
```

Restart and run all after changing a visible parameter. Python setup, charts and cleanup are folded; SQL and results remain visible. The execution runner creates a temporary kernel, uses this directory as cwd and saves only after success. Overrides require a separate destination; unknown parameters and destinations equal to the source directory are rejected.

## Experiment and public API

```bash
uv run --frozen python execute.py --parameters '{"BOUNDARY_POLICY":"starting_shift"}' --output-dir validation/starting-shift
uv run --frozen python execute.py --parameters '{"DATA_MODE":"live"}' --output-dir validation/live --timeout 180
```

The default `ending_shift` policy is `start < event <= end`. The experiment changes only that convention to `start <= event < end`. An event at an exact shift end can lose its match; event timestamps, shift durations and event counts remain unchanged. Neither convention establishes sub-second physical presence.

Replay serves two unchanged, recorded and trimmed real responses from this repository's tests via the worker's supported `NHL_WEB_BASE_URL` and `NHL_STATS_BASE_URL` overrides. Only exact requests for the documented game are accepted. [Provenance](fixtures/provenance.json) records hashes, source revision and coverage. The play fixture has 18 selected events; the shift fixture has six first-period Brad Marchand shifts plus a raw non-shift goal marker, which the worker omits. Original capture timestamps are unavailable. This incomplete coverage cannot establish that unmatched events occurred while a player was off the ice.

Live mode clears all inherited NHL URL overrides, retrieves the same historical game and applies the same player/period filters. More complete responses can change event and shift counts. Required-source failures remain errors without fixture fallback. The run clock is UTC, not a fixture capture timestamp; event and shift clocks are elapsed first-period seconds. Both endpoint reads are independent.

## Validation and limits

The default and detached starting-shift experiment passed: associations changed from 2 of 6 events to 1 of 6, while 330 recorded shift seconds stayed fixed. A live run on 2026-11-14 UTC passed with 361 events and 851 shifts overall; the player/period selection had nine shifts, 420 seconds and 45 shot-related events, with 18 default-policy matches. Both modes found one event where the policies disagreed.

Repository checks passed: 78 offline tests, 98.90% coverage, Ruff, packaging, entry points and runtime dependency audit. Configured metadata lint scored 97/100, L1 structural, with zero errors/warnings and 64 informational findings; declared waivers remain unchanged. Docker container validation was unavailable because Docker Desktop could not start.

Eleven SQL checks cover record identity, clock ranges, positive durations, non-overlapping shift interiors, event retention, boundary-only disagreement, exact policy selection and matched/unmatched count reconciliation. The example intentionally stays within regulation period 1. It does not model overtime clocks, certify official on-ice totals, infer responsibility or estimate player impact.

Saved default outputs are embedded in the notebook. Logs, extracted charts and experiment copies are ignored under `validation/`. The runner copies all relative assets, fixtures and runtime companions alongside executed experiment copies. [STANDARD.md](STANDARD.md) records presentation conventions. The repository README documents the NHL source data, affiliation and usage conditions; the worker's MIT code license does not license NHL data.
