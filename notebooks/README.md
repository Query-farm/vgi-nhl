# National Hockey League Data notebooks

Four independent SQL stories use the published **vgi-nhl v0.2.0** worker and real NHL response recordings. Each begins with a question, materializes source calls before displaying them, and finishes with checks plus a one-parameter experiment.

| Notebook | Question and demonstrated result | Experiment |
| --- | --- | --- |
| [01 · Events at shift boundaries](01_events_at_shift_boundaries.ipynb) | Which half-open interval contains an event exactly at a recorded shift endpoint? Retains unmatched events and distinguishes a trimmed recording from complete game coverage. | `BOUNDARY_POLICY="starting_shift"`: associations change from 2 to 1 of 6 selected events; 330 recorded shift seconds stay fixed. |
| [02 · Reconcile the opener](02_reconcile_the_opener.ipynb) | How do day, week and club schedules identify one game, and how do scoreboard, skater and goalie grains reconcile? CHI 2–FLA 3 agrees across all three aggregates; two listed goalies faced no shots. | `MIN_SHOTS=1`: eligible goalies change from 1 to 2; rates with zero shots remain undefined. `100` selects none. |
| [03 · Join season identity before comparing ledgers](03_join_season_identity_before_comparing_ledgers.ipynb) | Which dated season and team identity should anchor a standings comparison? A code-only Utah join duplicates a row; the season team ID preserves all 32 teams. Equal points coexist with different goal ledgers. | `MIN_POINTS=100`: the selected cohort changes from 18 to 9 teams; all 32 raw season records remain fixed. |
| [04 · A roster does not scope season totals](04_a_roster_does_not_scope_season_totals.ipynb) | Does joining a Florida roster make league-wide player totals Florida-specific? Brad Marchand's 2024–25 total is 51 points, but his Florida stint contributes 4; career rows and game logs independently reconcile by team. | `MIN_GAMES=70`: eligible roster skaters change from 22 to 15 of 23; rates and historical stints remain fixed. |

## Run locally or in Colab

Open any notebook's **Open in Colab** link and run all cells. Its visible bootstrap installs only the base shared package and retrieves SHA-verified companions; it does not replace the existing kernel or Jupyter client. First use needs network access for the shared package, public worker release, VGI extension and managed Python. No NHL credentials or worker source checkout are needed.

For a local copy of this directory, install [uv](https://docs.astral.sh/uv/) and Git, then run:

```bash
uv sync --frozen
uv run --frozen vgi-notebooks
```

The local lock includes the shared publication `[runner]` extra at **v0.3.49** and Haybarn **2.0.0rc11**. Every notebook keeps this release connection visible:

```sql
INSTALL vgi FROM community;
LOAD vgi;
ATTACH 'nhl' (TYPE vgi, LOCATION 'uvx --python 3.13 --from git+https://github.com/Query-farm/vgi-nhl@v0.2.0 vgi-nhl');
```

The worker runs in its own environment. Shared setup establishes UTC and an empty temporary SQL-secret directory with persistent secrets disabled. Run each notebook in a fresh kernel, or restart and run all after changing parameters, so its worker owns the correct replay endpoint. The final cells close both connection and replay server.

For local interactive use:

```bash
uv run --frozen python -m ipykernel install --user --name vgi-nhl-notebooks --display-name 'Python (vgi-nhl notebooks)'
```

## Parameter experiments

Overrides require a separate destination; failed runs leave saved defaults intact.

```bash
uv run --frozen vgi-notebooks 01_events_at_shift_boundaries.ipynb --parameters '{"BOUNDARY_POLICY":"starting_shift"}' --output-dir validation/starting-shift
uv run --frozen vgi-notebooks 02_reconcile_the_opener.ipynb --parameters '{"MIN_SHOTS":1}' --output-dir validation/one-shot
uv run --frozen vgi-notebooks 03_join_season_identity_before_comparing_ledgers.ipynb --parameters '{"MIN_POINTS":100}' --output-dir validation/hundred-points
uv run --frozen vgi-notebooks 04_a_roster_does_not_scope_season_totals.ipynb --parameters '{"MIN_GAMES":70}' --output-dir validation/seventy-games
```

Each also supports `DATA_MODE="live"`. This makes bounded public reads of the documented historical game, season or player; source failures remain errors, with no replay fallback:

```bash
uv run --frozen vgi-notebooks 02_reconcile_the_opener.ipynb --parameters '{"DATA_MODE":"live"}' --output-dir validation/live-opener --timeout 600
```

## Recording provenance and analytical limits

Book 01 preserves two unchanged, trimmed real fixtures from the original repository. [Fixture provenance](fixtures/provenance.json) records their hashes and coverage; the original acquisition timestamps are unknown. There are 18 selected play-by-play events and six first-period Brad Marchand shifts plus one raw non-shift goal marker omitted by the worker. Incomplete coverage cannot establish that unmatched events happened while a player was off the ice. Neither endpoint convention establishes sub-second physical presence or player impact.

Books 02–04 use **15 unchanged public JSON response bodies acquired independently on 2026-11-15 UTC**. [Recording provenance](recordings/provenance.json) lists each URL, acquisition time, status and SHA256. Historical dates are separate from acquisition dates: the opener is 2025-10-07, while the season comparison and roster use 2024–25. The player profile and team/franchise reference data reflect their acquisition time. The responses are real public observations, not synthetic examples or an atomic database snapshot.

`nhl_examples.py` serves only exact allowed requests through the released worker's supported base-URL settings. It verifies recording hashes, rejects unexpected paths or query values, and audits exactly 2, 4, 5 and 6 HTTP requests in the four replay stories. Several SQL projections share a cached source body. Analytical joins, aggregates, denominator choices and checks remain visible SQL.

The season goal residuals equal shootout wins/losses in these 32 returned records; this observed equality is not asserted as a universal API contract. A local points cutoff is not a playoff-qualification rule. Player per-game values describe full-season reports, including traded players; a null top-100 leader rank means absence from that bounded list, not zero scoring. Profile career totals require explicit NHL and regular-season filtering before comparison with season lines.

## Coverage and validation

[coverage.json](coverage.json) maps **19 of 37** distinct public SQL names to executed cells, results and interpretations, meeting the 19-name target. Actual complete `duckdb_functions()`, `duckdb_tables()` and `duckdb_views()` exports reconcile both the v0.2.0 release (`dc053b9f4df0b67951bd467776ee7ae21ba10514`) and reviewed public source (`cae069f814d63408dce7dad628e4b058ead2104c`). Same-name aliases count once; differently named backing scans remain in the denominator. The other 18 names remain explicitly uncovered. Analytical execution uses the release: current-interface correspondence is 19/37, while exact-current-runtime analytical coverage is zero.

All four saved defaults, four notebook-only detached parameter experiments, the zero-eligible-goalie boundary, and all four bounded live runs passed **44 SQL invariants**. Replay request audits and cross-run comparisons passed. Live books 02–04 reproduced all analytical tables; live book 01 returned the fuller game population (nine selected shifts, 420 seconds, 45 shot-related events and 18 default-policy associations), as its preserved recording is trimmed. Read-only public results can change on later runs.

A fresh notebook-only Python 3.12 bootstrap passed with pandas, Matplotlib, IPython, ipykernel and Jupyter client already imported. Their versions were retained, only base dependencies were installed in the kernel, and the full fourth notebook reproduced all replay results. This is a local Colab-compatibility test; hosted Colab was not manually executed. Eight runner/parameter guards, Ruff, formatting, presentation and coverage validation passed; all changed figures were reviewed. The unchanged worker's [green source CI](https://github.com/Query-farm/vgi-nhl/actions/runs/43576061464) was reused without rebuilding or dispatching source/container CI.

Defaults contain native SVG plus GitHub image links to committed `charts/` assets. Experiments retain native SVG; logs, PNG previews and temporary copies are ignored under `validation/` and `artifacts/`. The shared [standard](https://github.com/Query-farm/vgi-example-notebooks/blob/v0.3.49/docs/standard.md) describes presentation and evidence. The repository README documents NHL affiliation and usage conditions; the worker's MIT code license does not license NHL data.
