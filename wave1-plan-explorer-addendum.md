# DJET-NATL Wave 1 — explorer addendum: the panel figure is retired, the explorer replaces it

**Written:** 2026-09-06 · **Machine:** NCAR Derecho · **Status:** post-Gate-4, reviewed
**Review:** Codex (gpt-5.6-sol), 3 rounds, `verdict: APPROVED` at round 3 —
`docs/codex_reviews/2026-09-06_wave1_explorer_addendum_plan_codex_review_20260906_r{1,2,3}.md`
**Extends:** `wave1-plan.md` (post-Gate-4, 2026-09-03) and `wave1-plan-derecho-addendum.md` (D3,
2026-09-04). **Does not restate either.**
**Authorized by:** the operator's wave-1 addendum-2 brief and the Gate-2 rulings in §B2 below.

This addendum covers exactly one deliverable swap: the 47-panel figure is retired, and an
**interactive HTML explorer** plus a **tracked season-summary table** plus a **static annual chart**
replace it. Everything upstream of the figure — the sector, the level, the season, the year range,
the thresholds, the state rules, the sanity bands, the daily-mean definition, the intermediate, the
classifier, the CSV, `profile_sha256` — is untouched. Where this document is silent, the plan and
the Derecho addendum govern.

> **Note on the template.** The brief asks that this follow `references/plan-template.md`. That file
> does not exist in this repository or anywhere on this machine (searched `$HOME/project/**`) — the
> same absence `wave1-plan-derecho-addendum.md` recorded for `~/projects/CLAUDE.md` in §A1.6. This
> document therefore mirrors the section structure of the Derecho addendum, which is the reviewed
> exemplar in the tree. Sections are numbered `B0…B17` so that "§4.2" is unambiguously the plan's,
> "§A5" the Derecho addendum's, and "§B9" this one's.

---

## B0. Role, and what this addendum does not authorize

The session that reads this is **executing**. The gates are closed. Do not re-plan, do not re-argue
D1–D4, do not reopen a ruling.

**It authorizes:** one new module (`double_jet/explorer.py`), one new test file
(`tests/test_explorer.py`), the enumerated `cli.py` edits of §B10, the enumerated existing-test
edits of §B12.4 (**three files, five sites**), the D4 entry of §B13, the documentation edits of §B14, and moving
the approved mockup into `docs/mockup/`. Every one of those is enumerated; nothing outside the
enumeration is authorized.

**It does not authorize:** any change to `configs/double_jet.yaml` — and therefore
`config_sha256` and `profile_sha256` are unchanged and every committed artifact stays valid; any
change to `classify.py`, `profile.py`, `rda.py`, `source.py`, `download.py`, `config.py`, or
`figure.py`; deleting the panel-figure code or its outputs; any new dependency, CDN, bundler or
JavaScript framework; any analysis beyond the summary table (no trend fit, no significance test, no
persistence statistics); any restyling of the approved mockup.

**If a method-block field cannot be filled from the intermediate, the config or the CSV, that is a
discrepancy. Stop and report it — do not substitute a string literal.** §B6 maps every field to a
source that exists; nothing measured at Gate 1 suggests a gap.

**No compute.** Everything here runs in seconds on a login or Casper node. No PBS submission of any
shape, for any reason.

---

## B1. Established at Gate 1 — measured on this machine, 2026-09-06

Do not re-derive these. Do re-check any that a failure implicates.

### B1.1 The CSV — `data/jet_states_mjjas_1979-2025.csv`

| Property | Measured |
|---|---|
| Rows | 7 191 + header; columns `date,state,lat_1,u_1,lat_2,u_2,interjet_min` |
| Seasons | 47, **every one exactly 153 days** (min = max = 153). §B11 G1 will pass as written |
| States | `single` 3 932 · `double` 3 246 · `none` 13 |
| Null structure | exact and exceptionless: `none` → `lat_1`,`u_1` null (13 rows); `single` → `lat_2`,`u_2`,`interjet_min` null; `double` → all seven present. 0 counterexamples in each direction |
| Range | 1979-05-01 → 2025-09-30 |
| Latitudes | on the 0.25° grid, so **2 decimals is lossless** and the round-trip of §B12.1 is exact by construction |

### B1.2 The intermediate — `data/u250_natl_mjjas_1979-2025.nc`

Dims are **`time` 7191 × `latitude` 221 and nothing else**: the zonal mean is already taken, so
**the file carries no `longitude` coordinate.** The `latitude` coordinate runs 20.0 → 75.0 at a
measured step of exactly 0.25.

Global attributes present and usable: `title`, `source_dataset` (`ds633.0`), `variable`,
`pressure_level` (250), `pressure_level_units` (`hPa`), `sector` (JSON, carrying `resolution: 0.25`),
`season_months`, `years`, `days_per_season` (153), `source_files`, `request_template`,
`request_template_year`, `profile_fields` (JSON), `config_path`, `config_sha256`, `profile_sha256`,
`interpreter`, `package_versions`, `created`, `plan`.

The `U` variable carries `long_name`, `units` (`m s**-1`), `cell_methods`, `comment`.

### B1.3 Config identity — currently exact

`configs/double_jet.yaml` hashes to `9a6116ad4637bcbb…`, **identical** to the intermediate's
recorded `config_sha256`. The config on disk is provably the one the pipeline ran on. §B11 G3 does
*not* gate on this hash — see §B11 for why, and §B15 BR1 for the residual exposure it leaves.

### B1.4 The mockup — `docs/mockup/double_jet_explorer_v2.html`

Supplied by the operator at Gate 2 and moved into `docs/mockup/` unchanged (SHA-256
`042e57e01521e53c753d66f55cfd72c94b2edb6acd33e14d7330e695baa3189a` before and after the move). 260
lines, dependency-free, no `<link>`, no `@import`, no external `src`. **This file is the design
contract.** It is committed in the structure-only commit of §B16.

Its runtime data shape is `seasons: [{year, days}]` ascending by year, `days` exactly 153 entries of
`{d, date, state, lat1, u1, lat2, u2, inter}` — `d` the 0–152 day-of-season index, `date` a
`YYYY-MM-DD` string, `state` one of `double`/`single`/`none`, the rest numbers or `NaN`. It is fed by
`genToy()` or `parseCSV()`, **both of which are removed** (§B3).

### B1.5 Three consequences of B1.4 that the implementation must handle

1. **The embedded JSON is columnar; the renderers consume per-day objects.** A hydration step
   converts one to the other. It is the seam the round-trip test bites on.
2. **`NaN` is not JSON, and `null` is a live trap.** `isFinite(null)` is `true` in JavaScript, so a
   `null` latitude reaching `renderDetail` would draw a core at 0 °N instead of drawing nothing.
   Every `isFinite` guard in the mockup depends on hydration mapping `null → NaN`. §B12.1 tests it.
3. **`date` need not be embedded.** MJJAS contains no 29 February, so day-index ↔ calendar-date is a
   bijection per season — the identity `figure.py:_day_of_season` already relies on. Deriving it in
   JS drops 7 191 strings from the payload.

### B1.6 Where the code and the build command are

`cli.output_names()` is **the sole owner of every path under `data/` and `figs/`** (plan §4.2, risk
R12), and its `all_paths()` backs a pairwise-disjointness test asserted in *two* places
(`tests/test_config.py:162` and `tests/test_rda.py:1097`), both of which additionally assert
`len(all_paths()) == 5` and compare the campaign set against a `CONTRACT_NAMES` literal duplicated
at `tests/test_config.py:32` and `tests/test_rda.py:78`. Adding outputs touches all of it — §B12.4
enumerates exactly what.

`tests/test_cli.py:test_parse_stages_accepts_all` asserts the stage tuple **literally**
(`cli.STAGES == ("download","profile","classify","figure")`), and `test_stage_defaults_to_all`
asserts `args.stage == cli.STAGES`. Both change; both are enumerated.

The build command is plan **M8** (`wave1-plan.md:636`): `python -m double_jet --config
configs/double_jet.yaml`. It is also the body of `jobs/derecho/campaign.pbs` (§A10.2).

`classify.py:58` defines `ProfileMismatchError` and `classify.py:343-352` performs the
`profile_sha256` check the explorer reuses.

Test suite: **90 tests** across 5 files. There is no `test_figure.py`, so the explorer's test file is
new, not an extension.

---

## B2. Operator decisions carried into this addendum (2026-09-06)

Both were asked at Gate 2 as multiple choice with a recommendation; both recommendations were taken.

**O6 — the grid spacing in the method block's Data row comes from the intermediate's `sector`
attribute, cross-checked against the `latitude` coordinate.** The intermediate has no longitude
coordinate (§B1.2), so the brief's "computed from the intermediate's lat/lon coordinates" cannot be
satisfied literally. `resolution` is read from the `sector` attribute — which the `profile` stage
wrote *after* asserting the source longitude grid against it (`profile._assert_grid`), so it is a
verified record rather than a config echo — and the build hard-fails unless it equals the step
measured from the `latitude` coordinate. Both operands are the intermediate's own; the pair is
strictly stronger than either alone.

**O7 — the mockup's `.src` line survives as a static provenance label.** With `#file` and `#regen`
removed, the line retains its third child, `#srcname`, filled from data with the source CSV's
filename. It is the one element of `.src` the brief's removal list does not name; keeping it
preserves the mockup's vertical spacing between the method block and the annual chart and makes the
artifact self-identifying about which CSV produced it. No build stamp, no hash: that would be
addition, not transcription.

---

## B3. The design contract — what is transcribed, what changes

**Transcribed verbatim from `docs/mockup/double_jet_explorer_v2.html`:** every CSS rule and custom
property (`--double #1b9e77`, `--single #d95f02`, `--ink #1f2320`, `--mute #6f766f`,
`--rule #d9dcd8`, `--hover #f2f4f1`, `--bg #ffffff`, `--none #ebece9`, the Inter-with-system-fallback
stack); the DOM skeleton; `renderAnnual` and `renderDetail` in full, including their geometry
constants (`W 1100`, annual `H 250` / margins `46,16,14,30`, detail `plotH 250` / margins
`46,16,14,26`), the `ymax = min(100, ceil((max+5)/10)*10)` rule, gridlines every 10 %, x labels every
5 years from `ceil(y0/5)*5`, point radii 3.5 / 5 with a 9 px invisible hit target, the bridge/link/
core marks and their opacities, both tooltip formats, `runs()`, `stat()`, the prev/next buttons, the
`ArrowLeft`/`ArrowRight` handlers, the `.detail-note` sentence
(`"<n> double-jet days (<p>% of the season) in <r> runs; longest <l> d."` — note it prints the
percentage at **0** decimals while the annual tooltip prints **1**, and that asymmetry is
transcribed, not corrected), the legend, and the `.foot` sentence. Initial selection stays **2018**.

**Removed, not hidden** (the brief's list; the rest of it — grid, slider, sort control, smoothed-wind
background — is not present in v2 to begin with): the `#file` input, its `change` handler, the
`.src input[type=file]` rule and `parseCSV`; the `#regen` button, its handler, the `.src button`
rules, and `genToy`/`rng`/`gauss`/`seed`.

**Changed, and only this:**

1. Data is **embedded as JSON at build time** (§B5) instead of generated or loaded.
2. The method block is **filled from data** (§B6) instead of from the `META` literal at
   `docs/mockup/double_jet_explorer_v2.html:82-89`.
3. `#srcname` becomes the static provenance label of O7.
4. `<title>` drops the `— mockup on synthetic data` suffix. The `<h1>` prose is kept
   ("Double-jet frequency over the North Atlantic–Europe sector, extended summer …") with **only the
   year range substituted** from the CSV; "North Atlantic–Europe" and "extended summer" are layout
   prose, not method-block fields, and the from-data rule does not reach them.
5. `NDAYS`, `MONTH_STARTS`, `MONTHS` and `LAT` stop being JS literals and come from the embedded
   JSON (§B5). This is not required by the brief's from-data rule, which is scoped to the method
   block, but leaving `153` and `[20,75]` hard-coded beside a method block that swears they came
   from data would be the same defect the rule exists to prevent.

**The file must open from `file://` with no network access and no external scripts.** The mockup
already satisfies this; §B12.7 asserts it of the product.

---

## B4. Files touched — the complete enumeration

**New:**

| Path | What |
|---|---|
| `double_jet/explorer.py` | the builder (§B9) |
| `tests/test_explorer.py` | the test (§B12) |
| `docs/mockup/double_jet_explorer_v2.html` | the approved design, moved in unchanged (§B1.4) |
| `wave1-plan-explorer-addendum.md` | this plan |
| `docs/plans/2026-09-06_wave1_explorer_addendum_plan.md` | byte-identical mirror, per the tree's convention |

**Edited, by enumeration:**

| Path | Edit |
|---|---|
| `double_jet/cli.py` | the `OutputNames` docstring at `cli.py:43` ("a second field would make a smoke run's `all_paths()` **six** long" → **nine**, since three fields are being added), `STAGES`, `OutputNames` +3 fields, `output_names` ×3 shapes, new `default_stages`, `--stage` default **and both places that document it** — the help string at `cli.py:149-150`
(`'all' (default)`) and the usage line in the module docstring at `cli.py:4`
(`[--stage all|download,profile,classify,figure]`) — the `stages` resolution and its downstream uses, one dispatch block (§B10) |
| `tests/test_config.py` | `CONTRACT_NAMES` +3 entries; `5` → `8`; the campaign-name assertions (§B12.4) |
| `tests/test_rda.py` | `CONTRACT_NAMES` +3 entries; `== 5` → `== 8`; **the `OutputNames` fixture at :974**; **the stage-dispatch mocks and expected `calls` at :1156-1186**; the docstrings at :1099 and :1101 ("lengths stay **5**" → **8**, "six paths long" → **nine**) (§B12.4) |
| `tests/test_cli.py` | the `STAGES` literal; `test_stage_defaults_to_all`; the module docstring at `:10`, which lists the deferred `run()` imports and omits `explorer` (§B12.4) |
| `docs/deviations.md` | D4 (§B13) |
| `wave1-plan.md` **and** `docs/plans/2026-09-03_wave1_plan.md` | M7/M8 rows — **both, identically**; they are byte-identical files and must stay so (§B14) |
| `docs/results/2026-09-06_wave1_results.md` | **the deliverables table at line 46 only** (§B14) |
| `jobs/derecho/campaign.pbs` | **line 5's comment only** — "All four stages (download -> profile -> classify -> figure)" becomes the new campaign default ending in `explorer`. **The job body, the `#PBS` block and the resource shape are untouched**, so HANDOFF §7's compute authorization is unaffected. The body passes no `--stage`, so it picks up the new default with no edit; leaving the comment would make a pre-authorized job script lie about what it runs |

**New tracked artifacts** — derived, but committed, so they are part of the enumeration §B0 governs:

| Path | What |
|---|---|
| `results/season_summary.csv` | the summary table of §B7 — the file the write-up cites |
| `results/campaign/double_jet_natl_explorer.html` | committed copy, per the precedent that puts the panels there while `figs/` is gitignored |
| `results/campaign/double_jet_natl_annual.png` | same |

**Explicitly untouched:** `configs/double_jet.yaml`, `double_jet/figure.py`, `classify.py`,
`profile.py`, `config.py`, `rda.py`, `source.py`, `download.py`, `README.md`, `CLAUDE.md`,
`HANDOFF.md`, `wave1-plan-derecho-addendum.md`, and every executable line of `jobs/**` — including
`jobs/download_all.slurm`, whose `--stage all` is discussed in §B10 and deliberately left as it is.

The panel-figure code stays in the tree, importable, and still exercised: it remains the smoke run's
**M6** deliverable (§B10) and `--stage figure` still builds the campaign panels on demand.

---

## B5. The embedded JSON — schema and encoding

Two blocks, both `<script type="application/json">`, both parsed with `JSON.parse` at startup. No
data lives in JavaScript source.

```html
<script id="djet-data" type="application/json">{ … }</script>
<script id="djet-meta" type="application/json">{ … }</script>
```

### B5.1 `djet-data`

```jsonc
{
  "days_per_season": 153,
  "first_month": 5,
  "month_starts": [0, 31, 61, 92, 123],
  "month_labels": ["May", "Jun", "Jul", "Aug", "Sep"],
  "lat_range": [20.0, 75.0],
  "state_codes": {"d": "double", "s": "single", "n": "none"},
  "seasons": [
    {
      "year": 1979,
      "state": "ddsss…",                       // exactly days_per_season chars, one of d/s/n
      "lat_1": [24.5, 24.0, null, …],          // 2 decimals, null where the CSV is blank
      "u_1":   [33.0, 30.5, null, …],          // 1 decimal
      "lat_2": [66.5, 65.75, null, …],
      "u_2":   [16.1, 15.4, null, …],
      "interjet_min": [7.4, 6.7, null, …]      // m s⁻¹, so 1 decimal
    }
  ]
}
```

- `seasons` ascending by year; every array exactly `days_per_season` long, indexed by day-of-season.
- **State as a 153-character string.** 153 bytes per season against ~1 000 for an array of strings,
  and trivially round-trippable. `state_codes` ships in the payload so the HTML holds no literal
  state name that could drift from the CSV's.
- `month_starts`/`month_labels` derived from `season_months` with `calendar.monthrange(2001, m)` —
  the same non-leap reference `figure.py:_month_ticks` uses, and correct for every season because no
  configured month is February.
- **Rounding.** Latitudes `round(x, 2)` (lossless — §B1.1); winds and `interjet_min` `round(x, 1)`
  (lossy against the CSV float, which is what "round-trip … exactly at the stated rounding" means).
  Python's shortest-round-tripping float repr means `json.dumps` emits `24.5`, never
  `24.500000000000004`.
- **`NaN` → `null`,** and `json.dumps(..., allow_nan=False)` so a stray non-finite raises at build
  rather than emitting an invalid bare `NaN` literal.
- **Escaping.** `json.dumps(...).replace("<", "\\u003c")` before insertion. Still valid JSON, and it
  cannot terminate the `<script>` element no matter what a path or dataset id contains.
- **Hydration in JS** builds the mockup's per-day objects: `state_codes[code]`, `v === null ? NaN : v`
  for every numeric, and `date` derived from `Date.UTC(year, first_month - 1, 1 + d)`. The
  `null → NaN` mapping is load-bearing (§B1.5 item 2).

Size: 47 × 153 × 5 numerics ≈ 216 KB of JSON, so an HTML file of roughly 250–300 KB. Logged at
build; not gated.

### B5.2 `djet-meta`

```jsonc
{
  "title": "Double-jet frequency over the North Atlantic–Europe sector, extended summer 1979–2025",
  "source_csv": "jet_states_mjjas_1979-2025.csv",
  "method": [["Data", ["…", "…", "…"]], ["Sector", […]], … ]
}
```

`method` is an array of `[label, [parts]]` pairs — exactly the shape the mockup's renderer consumes,
so `docs/mockup/double_jet_explorer_v2.html:90-91` is transcribed unchanged.

---

## B6. The method block — every field, its source, and its failure mode

Six rows, in the mockup's order. **Every value below is read; none is written as a literal in the
generated JavaScript.** A missing attribute raises naming the attribute (§B11 G4).

| Row | Part | Source | Rendered |
|---|---|---|---|
| **Data** | collection | attr `profile_fields.source` selects the phrasing; attr `source_dataset` supplies the id | `ERA5, NCAR RDA ds633.0` (`rda_hourly`) / `ERA5, CDS <dataset>` (`cds_derived`) |
| | variable + level | attrs `variable`, `pressure_level`, `pressure_level_units` | `u_component_of_wind at 250 hPa` — **see the note below** |
| | grid | attr `sector.resolution`, cross-checked against the `latitude` coordinate (O6, §B11 G3) | `0.25° grid` |
| **Sector** | longitudes | attr `sector.lon_min`/`lon_max`, formatted sign→hemisphere | `60°W–30°E zonal mean` |
| | latitudes | attr `sector.lat_min`/`lat_max` | `20–75°N` |
| **Time** | season + years | months from attr `season_months` via `calendar.month_name`; **years from the CSV**, cross-checked against attr `years` (§B11 G5) | `May–September, 1979–2025` |
| | daily mean | attr `profile_fields.daily_statistic` and `profile_fields.hourly_times` | `daily mean of the 00, 06, 12, 18 UTC analyses` |
| **Profile** | smoothing | config `detection.smooth_window_deg` | `2.5° boxcar smoothing in latitude` |
| **Double jet** | core threshold | config `detection.u_core_min` | `core u ≥ 15 m s⁻¹` |
| | separation | config `detection.separation_min_deg` | `two cores ≥ 10° apart` |
| | prominence | config `detection.prominence_min` | `minimum between them ≥ 5 m s⁻¹ below the weaker core` |
| **Each point** | denominator | the CSV's asserted per-season day count, cross-checked against attr `days_per_season` | `share of the season's 153 days classified double jet` |

**One visible departure from the mockup, and it is forced.** The mockup renders the variable as the
prose `zonal wind u at 250 hPa`. `u_component_of_wind` is the name the data actually records
(attr `variable`, and `profile_fields.variable`); rendering "zonal wind u" would require a
display-alias table in the script — precisely the string literal the brief forbids. The row
therefore reads `u_component_of_wind at 250 hPa`. **This is flagged for the operator at review** as
the single place where rendered method-block text departs from the mockup; it is a one-line change
to overrule if the prose is preferred to the recorded name.

The three detection thresholds and the smoothing window come from the config in hand. §B11 G6 checks
them against the CSV rather than trusting them; §B15 BR1 states exactly what that does and does not
close.

---

## B7. `results/season_summary.csv` — the column contract

One row per season, ascending by year, header exactly:

```
year,n_days,n_double,n_single,n_none,pct_double,n_double_runs,longest_double_run
```

| Column | Definition |
|---|---|
| `year` | the season's calendar year (every MJJAS season lies in one year) |
| `n_days` | rows in the CSV for that season; **asserted equal to `days_per_season`** (§B11 G1) |
| `n_double`, `n_single`, `n_none` | counts of each state; they sum to `n_days`, asserted |
| `pct_double` | `100 · n_double / n_days`, written `%.4f` |
| `n_double_runs` | number of maximal runs of consecutive `double` days within the season's ordered 153-day sequence; `0` if none |
| `longest_double_run` | length of the longest such run; `0` if none |

Runs are exactly the mockup's `runs()` filtered to `state === "double"` — maximal, within-season, no
wrap across season boundaries.

`pct_double` in the CSV is a **derived convenience**: the HTML recomputes `100·nD/n_days` in JS and
the static chart reads the CSV, so §B12.2 asserts the two agree to within `5e-5`. Both display at 1
decimal, and the `.detail-note` at 0, per §B3.

**This file is the table the HTML embeds and the write-up cites**, and it is written *before* the
PNG so the static chart is rendered from it, not from a parallel computation (§B8).

Path is shape-dependent, per §B10: campaign → `results/season_summary.csv` (tracked); smoke and
subset runs write under `data/` so an exploratory run can never dirty a tracked directory or
overwrite the deliverable.

---

## B8. `figs/double_jet_natl_annual.png` — the static chart

Matplotlib, `Agg` backend selected before `pyplot` (the same reason `figure.py` gives: no `DISPLAY`
on a batch node). **The top chart only** — no detail panel, no selection highlight, nothing the
mockup's annual axis does not have.

Read from `results/season_summary.csv`, which the build has just written. "Same numbers by
construction" is therefore literal, not an argument.

Transcribed from `renderAnnual`: `ymax = min(100, ceil((max_pct + 5)/10)·10)`; horizontal rules every
10 % in `--rule #d9dcd8`; y labels `0%`…`ymax%` and x labels every 5 years from `ceil(y0/5)·5`, both
in `--mute #6f766f`; the series line in `--double #1b9e77`; points white-filled with a `--double`
edge. Aspect matches the mockup's 1100 × 250 viewBox — `figsize=(11, 2.5)`, `dpi=200`. Title is
`djet-meta.title`. No trend line, no running mean, no second series, no grid beyond those rules.

Font is matplotlib's default (DejaVu Sans). Chasing Inter on Derecho would be a new dependency and
is not authorized; the HTML is where the type is.

---

## B9. `double_jet/explorer.py` — the module

Single public entry, mirroring `figure.run_figure`'s signature discipline (paths in, no path
construction inside — plan §4.2):

```python
def run_explorer(cfg, profile_path, csv_path, explorer_path, summary_path, annual_path, log) -> None
```

Order of operations, and each step's failure is §B11's:

1. Open the intermediate via `profile.open_intermediate` (deferred import, as `figure.py` does).
   Read the `latitude` coordinate and the required attributes. **G2, G3, G4.**
2. Read the CSV with `pandas`, declared dtypes for the five numeric columns (`figure.py`'s lesson:
   an all-blank column otherwise arrives as strings). Check the column set. **G7.**
3. Group by season; assert day counts and state/null consistency. **G1, G8.**
4. Check the CSV against the configured thresholds. **G6.**
5. Build the summary rows and write `summary_path`.
6. Build `djet-data` and `djet-meta`; render the HTML from a module-level template string that is
   the mockup with the substitutions of §B3; write `explorer_path`.
7. Render the annual PNG **from `summary_path`**; write `annual_path`.
8. Log: seasons, days, state counts, JSON bytes, HTML bytes, and each path written.

The HTML template is a module-level constant carrying the mockup's `<style>`, DOM and script with
two `{}` slots for the JSON blocks — not string-concatenated markup. The mockup's own comment
markers (`// ---------- … ----------`) are kept so a diff against `docs/mockup/` stays readable.

**The `profile_sha256` check is duplicated, deliberately.** `classify.py:343-352` performs exactly
this comparison and raises `ProfileMismatchError`. The explorer repeats those lines and imports the
exception rather than factoring a shared helper, because factoring would mean editing `classify.py`
— the classifier that D3's addendum and this one both hold untouched. Eight duplicated lines is the
cheaper price, and the duplication is commented as such so it does not read as an oversight.

**No `scripts/make_explorer.py`.** The brief left this to Gate 3. A stage inside the entry point is
chosen because (a) the brief requires "the one-command reproduction … now ends with the explorer",
and a separate script makes it two commands; (b) a standalone script writing `figs/` would either
violate plan §4.2's "one owner of every derived path" or have to import `output_names` anyway.

---

## B10. `double_jet/cli.py` — the enumerated edits

**1. `OutputNames` gains three fields**, all populated for all three shapes, so `all_paths()` is
uniformly 8 and the disjointness invariant keeps the same shape it has today:

```python
explorer: Path
season_summary: Path
annual: Path
```

**2. `output_names` — the three shapes** (plan §4.2's table, extended):

| | campaign | smoke | subset |
|---|---|---|---|
| `explorer` | `figs/double_jet_natl_explorer.html` | `figs/smoke_<y>_explorer.html` | `figs/double_jet_natl_explorer_<f>-<l>.html` |
| `season_summary` | `results/season_summary.csv` | `data/smoke_<y>_season_summary.csv` | `data/season_summary_<f>-<l>.csv` |
| `annual` | `figs/double_jet_natl_annual.png` | `figs/smoke_<y>_annual.png` | `figs/double_jet_natl_annual_<f>-<l>.png` |

`output_names`' docstring says it owns every path under `data/` and `figs/`. The campaign's
`season_summary` is the first derived output under `results/`, and the docstring is amended to say
so: it is a *derived* output that is also *tracked*, unlike `REGRESSION_BASELINE`, which is a tracked
repository artifact and stays outside. Only the campaign shape writes there — an exploratory
`--years` run cannot dirty a tracked directory.

**3. `STAGES` gains `explorer`:**

```python
STAGES = ("download", "profile", "classify", "figure", "explorer")
```

**4. The default stage list becomes shape-dependent.** `--stage` default changes from `STAGES` to
`None`, and `run()` resolves it:

```python
def default_stages(smoke: bool) -> tuple[str, ...]:
    """D4: the panel figure is retired as a campaign deliverable and leaves the one-command build.

    It stays reachable by name (`--stage figure`) and stays the smoke run's M6 deliverable, which
    D4 does not retire: a one-season explorer is a single point on the annual axis and is not a
    deliverable, while the smoke panel is what the operator eyeballs the profile on.
    """
    return (("download", "profile", "classify", "figure") if smoke
            else ("download", "profile", "classify", "explorer"))
```

**The resolution is an exact assignment, and every downstream use changes with it.** In `run()`,
immediately before the `log.info("run: …")` call at `cli.py:205`:

```python
stages = args.stage or default_stages(smoke)
```

and **every** subsequent `args.stage` in `run()` becomes `stages`. There are exactly **six**
executable sites today — `cli.py:208` (`",".join(...)`), `:211` (`"download" in ...`), `:233`
(`profile`), `:237` (`classify`), `:242` (`figure`), and `:258` (the
`missing = [stage for stage in ("profile", "classify") if stage not in ...]` guard of §A7.3) —
**plus the new `explorer` block of item 5, which makes seven.** The comment at `:255` quotes
`"download" in args.stage` and is updated to match, so the code and its explanation do not diverge.

`grep -n 'args\.stage' double_jet/cli.py` before editing and again after: the only occurrence that
may survive is the `stages = args.stage or …` assignment itself. A missed site is a `TypeError` on
`None`, not a silent wrong answer, but §B12.3's run-level test is what actually proves the
one-command build still works: asserting on `default_stages()` alone would pass while
`python -m double_jet --config …` crashes.

**`--stage all` is deliberately NOT the same thing as the default any more.** `parse_stages("all")`
returns `STAGES`, so `all` now means *five* stages and a campaign run with `--stage all` builds the
panels **and** the explorer. That is the correct reading of the word and it is left alone; but it
means "the panel figure is no longer built" is true of the **default** build only, and the
distinction has to be stated rather than assumed. `jobs/download_all.slurm:52` passes `--stage all`
and would therefore build both — it is the superseded Stampede3 CDS job that CLAUDE.md records as
"not to be resubmitted", so this is noted and **not** fixed.

This is the whole mechanism by which "the panel-figure code stays in the tree; it is no longer run
by the one-command build" is true. `figs/double_jet_natl_panels.*` keep their `output_names` entries
and their place in `CONTRACT_NAMES`, so `--stage figure` still builds them and R12 still covers them
— the campaign simply stops producing them by default.

**5. One dispatch block**, after the `figure` block and before the RDA regression check (whose
placement and gating §A7.3 fixed and this addendum does not move):

```python
if "explorer" in stages:
    explorer_mod.run_explorer(cfg, out.profile, out.states_csv, out.explorer,
                              out.season_summary, out.annual, log=log)
```

with `from . import explorer as explorer_mod` alongside the other deferred stage imports in `run()`.

Exit codes are unchanged: an explorer failure is an exception → `EXIT_ERROR` (3), like a figure
failure. The explorer sets no gate and never returns `EXIT_SANITY`.

---

## B11. Hard failures — the complete list

Every one raises with the offending name **in the message**. None is a warning, none has a fallback.

| # | Check | Message carries |
|---|---|---|
| **G1** | every season's `date` column equals **exactly** that year's expected MJJAS date vector — right count, right dates, ascending, no duplicates — modelled on `rda._assert_season_dates` (`rda.py:531`) and `profile._assert_time`. A bare row count would accept a duplicated, missing or reordered day, which silently shifts every downstream day index, tooltip and run length | the season year, the count, and the first differing date |
| **G2** | `profile_sha256` recorded == `cfg.profile_sha256` | both hashes, the two paths (`ProfileMismatchError`, `classify.py`'s wording) |
| **G3** | attr `sector.resolution` == step measured from the `latitude` coordinate, **and** the coordinate equals `arange(sector.lat_min, sector.lat_max + res/2, res)` elementwise — endpoints as well as spacing, the check `profile._assert_grid` already applies upstream. Spacing alone would accept a shifted axis, and `open_intermediate` verifies only dimension names (`profile.py:426-428`) | both values, and the first differing index (O6) |
| **G4** | every required attribute present, and JSON attributes parse | **the attribute name** |
| **G5** | seasons in the CSV == attr `years`; `season_months` non-empty and contiguous-from-first-of-month | the symmetric difference |
| **G6** | every CSV row satisfies the configured thresholds (§B15 BR1) | the date and the violating value |
| **G7** | CSV columns exactly `classify.CSV_COLUMNS` | the missing/extra columns |
| **G8** | state/null consistency: `none` → all five blank; `single` → **`lat_1` and `u_1` both present**, `lat_2`/`u_2`/`interjet_min` blank; `double` → all five present | the first offending date |
| **G9** | `json.dumps(..., allow_nan=False)` succeeds | Python's own `ValueError` |

**G6 in full.** These three invariants hold for every row by construction of `classify.py`, and are
checkable from the CSV alone against the config:

- every recorded core satisfies `u ≥ u_core_min` (`classify.py:124`);
- every `double` day satisfies `lat_2 − lat_1 ≥ separation_min_deg` (`classify.py:147`, with
  `lat_1` south and `lat_2` north by construction);
- every `double` day satisfies `interjet_min ≤ min(u_1, u_2) − prominence_min` (`classify.py:153`).

Compared with a `1e-9` absolute tolerance, since the CSV carries full float precision and the
thresholds are exact decimals.

**G2 gates on `profile_sha256`, not on `config_sha256`, and that is deliberate.**
`classify.py:328-332` records the reason in the code: detection thresholds are outside that hash
*by design*, because "changing a threshold and re-running against the same cached intermediate is
exactly what the contract requires to keep working". Gating the explorer on `config_sha256` would
break that documented workflow, and would also hard-fail on a comment-only edit to the YAML. G6 is
the substitute, and §B15 BR1 states honestly what it leaves open.

---

## B12. Tests — `tests/test_explorer.py`

The brief requires one test; this is that test plus the failure modes that make it meaningful.
Fixtures build a synthetic 3-season CSV and a synthetic intermediate whose attributes are written
explicitly (not via `profile._intermediate_attrs`, so the test file itself documents the attribute
contract the explorer depends on).

### B12.1 The round-trip — the brief's test

Build the HTML; extract `<script id="djet-data">` with a regex; `json.loads` it. Then for **every**
season and **every** day assert:

- `state_codes[state[d]]` equals the CSV's `state` for that date;
- `lat_1[d]` equals `round(csv.lat_1, 2)` and `u_1[d]` equals `round(csv.u_1, 1)`, likewise
  `lat_2`, `u_2`, `interjet_min` — with `null` ↔ `NaN` in both directions, checked explicitly so a
  `null` that should be a number, or a number that should be `null`, fails (§B1.5 item 2);
- the day index maps to the CSV's `date` via `first_month` + `d`;
- the payload's `lat_range`, `days_per_season`, `month_starts` and `month_labels` equal the sector
  endpoints, the asserted day count, and the month offsets derived from `season_months`. This is a
  **test assertion, not a runtime gate**: the payload is constructed from those very values, so a
  runtime comparison would be tautological — G3 is what actually proves the coordinate and the
  attribute agree.

**What this does and does not prove.** `json.loads` verifies the *payload* — that a blank CSV cell
became `null` and a number stayed a number. It does **not** exercise the JavaScript that converts
`null → NaN` before the mockup's `isFinite` guards
(`docs/mockup/double_jet_explorer_v2.html:210`, `:211`, `:230`), and a browser harness would be
disproportionate for a zero-compute change. The test therefore adds one **string** assertion on the
emitted script — that the hydration statement is present and maps `null` to `NaN` rather than
passing the value through — and §B1.5 item 2's claim is scoped accordingly: the payload half is
proven, the JS half is pinned against silent deletion, and neither is called a browser test.

### B12.2 The summary — the brief's test

Recompute all eight columns **independently, from the CSV, with pandas** — `groupby` on the year,
`value_counts` for the three states, and a run-length pass written separately from the module's —
and assert row-for-row equality with `results/season_summary.csv` as written. Assert
`pct_double ≈ 100·n_double/n_days` within `5e-5`, and that the three counts sum to `n_days`.

### B12.3 The rest

| Test | Asserts |
|---|---|
| `test_stage_defaults_are_shape_dependent` | lives in `tests/test_cli.py`. Asserts the parser yields `args.stage is None`, that `default_stages(smoke=True)` ends in `figure` and `default_stages(smoke=False)` ends in `explorer`, **and** — with **seven** callables monkeypatched (`source.preflight`, `source.materialize_seasons`, `profile.build_intermediate`, `classify.run_classify`, `figure.run_figure`, **`explorer.run_explorer`**, `rda.check_regression_2018`), extending the six-mock pattern at `tests/test_rda.py:1156` — that `cli.run()` with `stage=None` actually dispatches those tuples for both shapes. The helper-only assertion would pass while the one-command build crashed on `None` (§B10 item 4) |
| `test_summary_and_embedded_json_agree` | counts derived from the embedded state strings equal the summary CSV's rows — the HTML and the table cannot drift |
| `test_a_short_season_fails_naming_it` | drop one day → raises, message contains the season year and `152` (G1) |
| `test_a_missing_attribute_fails_naming_it` | delete `sector` → raises naming `sector`; parametrized over every required attribute (G4) |
| `test_a_profile_hash_mismatch_fails` | perturbed `profile_sha256` → `ProfileMismatchError` (G2) |
| `test_resolution_disagreeing_with_latitude_fails` | `sector.resolution` 0.5 against a 0.25 coordinate → raises with both values (G3) |
| `test_each_threshold_arm_fails_alone` | parametrized over all **three** G6 arms — `u_1` under `u_core_min`, `lat_2 − lat_1` under `separation_min_deg` (`classify.py:147`), `interjet_min` above `min(u₁,u₂) − prominence_min` (`classify.py:153`) — each perturbed alone, each raising and naming the date. One arm tested is one arm proven |
| `test_a_reordered_or_duplicated_date_fails` | swap two dates, then duplicate one → raises naming the season and the first differing date (G1) |
| `test_a_shifted_latitude_axis_fails` | coordinate `20.25…75.25` at the right spacing → raises (G3) |
| `test_malformed_csv_shapes_fail` | parametrized: a missing column and an extra column (G7); a `single` row carrying `lat_2`, a `double` row missing `interjet_min`, a `none` row carrying `lat_1`, and a `single` row missing `u_1` (G8) |
| `test_method_block_is_config_driven_not_literal` | build with `u_core_min` 17.0 and `pressure_level` 500 → `17` and `500` appear in `djet-meta`; the frozen values do not |
| `test_the_html_has_no_external_references` | no `http://`, `https://`, `<link`, `@import`, or `src=` anywhere in the output (§B3) |
| `test_the_embedded_json_is_valid_and_finite` | both blocks `json.loads` cleanly; no bare `NaN`/`Infinity`; no `</script>` inside either block |
| `test_the_annual_png_is_written` | file exists, is a PNG by magic bytes, non-trivial size |
| `test_against_the_real_artifacts` | **skipped unless** `data/jet_states_mjjas_1979-2025.csv` and the intermediate exist; then runs B12.1 + B12.2 against them, so the actual deliverable is verified and not merely its synthetic analogue |

### B12.4 The enumerated existing-test edits — three files, **five** sites

1. `tests/test_config.py:32` — `CONTRACT_NAMES` gains `results/season_summary.csv`,
   `figs/double_jet_natl_explorer.html`, `figs/double_jet_natl_annual.png`; `len(...) == 5`
   (line 167) becomes `== 8`; `test_only_the_full_campaign_produces_the_contract_names` gains the
   three campaign-path assertions.
2. `tests/test_rda.py:78` — `CONTRACT_NAMES` gains the same three; `== 5` (line 1123) becomes
   `== 8`. The docstring's "all three `all_paths()` lengths stay 5" becomes 8; its point — one
   evidence slot, equal lengths, disjointness intact — is unchanged.
3. **`tests/test_rda.py:974` — `cli.OutputNames(...)` is constructed directly** with five keyword
   arguments, so three new *required* fields raise `TypeError` and take the whole regression-check
   suite with them. The fixture gains `explorer=`, `season_summary=` and `annual=` under the same
   `current / f"{tag}_…"` convention as its siblings. **Alternative, if the execution session
   prefers it:** give the three fields `= None` defaults on the dataclass and have `all_paths()`
   skip them, exactly as `evidence` already does — but then `all_paths()` lengths stop being
   uniform and §B10's stated invariant changes, so the fixture edit is preferred.
4. **`tests/test_rda.py:1156-1186` — the stage-dispatch test runs `cli.STAGES`** and asserts
   `calls == ["preflight","materialize","profile","classify","figure","regression"]`. With
   `explorer` in `STAGES` the unmocked `run_explorer` would be called for real against files that do
   not exist. The test gains `monkeypatch.setattr(explorer, "run_explorer", …)` alongside the other
   five stage mocks, and `"explorer"` in the expected `calls` list between `figure` and
   `regression` — which is also the assertion that pins §B10 item 5's dispatch position.
5. `tests/test_cli.py` — `test_parse_stages_accepts_all`'s `cli.STAGES` literal gains `"explorer"`;
   `test_stage_defaults_to_all` becomes `test_stage_defaults_are_shape_dependent` (§B12.3).

`grep -rn 'OutputNames(\|cli\.STAGES\|CONTRACT_NAMES\|all_paths()) == 5' tests/` before editing
and again after. It returns more than five lines — `== 5` also matches unrelated assertions at
`tests/test_rda.py:440` and `:594`, which are **not** sites and must not be touched — so read it as
a candidate list to triage, not a hit count. The five *relevant* sites are the ones enumerated
above; the re-grep is what proves no sixth was missed.

**One import detail:** `tests/test_rda.py:53` imports `cli, download, figure, profile, rda, source`
and does **not** include `explorer`. Site 4 adds it to that line (or takes a local import inside the
test); without it the new mock is a `NameError`.

Nothing else in the existing suite changes. **`pytest tests/ -q` must be green** — that is the
acceptance command. No count is projected here: several of §B12.3's tests are parametrized and
pytest counts each case separately, so a forecast would only invite a spurious mismatch. Codex
measured the pre-change baseline at **90 passed in 21.44 s** on 2026-09-06.

---

## B13. D4 — the deviation entry

Appended to `docs/deviations.md` in the tree's established shape (dated, authority, plan text
superseded, what changed, why it is not a science change, scope):

> **D4 — The 47-panel figure is retired; an interactive explorer replaces it**
>
> **Date:** 2026-09-06 · **Authority:** operator, explicit, this date
> **Plan text superseded:** §7 **M7** and §4.5's campaign instance.
>
> **The decision.** `figs/double_jet_natl_panels.{pdf,png}` is no longer a deliverable. In its place
> the build produces `figs/double_jet_natl_explorer.html` (one self-contained interactive explorer,
> no network and no external scripts), `results/season_summary.csv` (tracked; one row per season)
> and `figs/double_jet_natl_annual.png` (a static rendering of the explorer's top chart, from that
> CSV). **The reason:** the 47-panel grid buries the state sequence under a noisy background and
> offers no way to see a merge.
>
> **What is unchanged.** The classification, every threshold, the sector, the level, the season, the
> year range, `data/u250_natl_mjjas_1979-2025.nc`, `data/jet_states_mjjas_1979-2025.csv`,
> `config_sha256` and `profile_sha256`. No frozen number is touched and no config value changes.
> Every number the explorer plots is read from the CSV, and every number in its method block is read
> from the CSV, the intermediate's attributes, or the config — a test recomputes the summary table
> independently from the CSV and asserts equality. The one limit, recorded rather than papered over:
> the four detection numbers (three thresholds and the smoothing window) live outside
> `profile_sha256` by design, so they are read from the config in hand; the three thresholds are
> additionally checked against every CSV row, and the smoothing window cannot be checked from the
> CSV at all.
>
> **Scope.** The panel-figure code stays in the tree and stays working: it remains the smoke run's
> **M6** deliverable and `--stage figure` still builds the campaign panels on demand. It is simply
> no longer part of the one-command build (`cli.default_stages`). The committed
> `results/campaign/double_jet_natl_panels.{pdf,png}` are left in place as the record of what the
> 2026-09-05 campaign run actually produced.

---

## B14. Documents to update

1. **`wave1-plan.md` and `docs/plans/2026-09-03_wave1_plan.md` — both, identically.** They are
   byte-identical today (verified) and `CLAUDE.md` requires they stay so. §7's table: **M7** is
   struck through and annotated *(retired — D4)*, and three rows are added for the explorer, the
   summary table and the annual chart with their verifications (§B11 and §B12). **M8**'s text
   becomes: `python -m double_jet --config configs/double_jet.yaml` reproduces **M1, M3, M4, M5**
   and the D4 deliverables end to end — i.e. **the one-command reproduction now ends with the
   explorer.** M2 and M6 are `--smoke` deliverables and M7 is retired, so the campaign command has
   never truthfully reproduced "M1–M7" and the corrected row must not repeat that claim.
2. **`docs/results/2026-09-06_wave1_results.md` — the deliverables table at line 46, and nothing
   else.** The panels row is replaced by rows for the explorer, the summary table and the annual
   chart, with a one-line note that the panels are what the 2026-09-05 run produced and are retained
   in `results/campaign/`.

   **No other line in that document changes.** The word "figure" appears on several other lines and
   none of them is a pointer to the retired deliverable; three representative reasons, so the
   pattern is clear: **line 283** describes what `figure.py` captions and is still true of the panel
   code; **line 367** is a measured statement about the 2026-09-05 job's peak memory ("the
   concatenated intermediate and the 47-panel figure") and is history, not a pointer; **line 396**
   uses "figure" to mean *a numerical value* ("every per-month, per-season and per-core figure in
   §2–§5"), not a visualization. Do not sweep the document for the word. **No number in the write-up
   changes** — nothing upstream moved.
3. **`results/campaign/`** gains committed copies of `double_jet_natl_explorer.html` and
   `double_jet_natl_annual.png`, matching the precedent by which the panels are committed there
   while `figs/` is gitignored. `results/season_summary.csv` is tracked at its own path.

**Not updated, deliberately, and left knowingly stale.** `CLAUDE.md` does not name the figure.
`HANDOFF.md:307` **does** — deliverable 4, "`figs/double_jet_natl_panels.{pdf,png}` — the figure" —
but HANDOFF is the *2026-09-04 brief to the Derecho agent*, a historical document whose job is done;
editing it would rewrite what was actually handed over. `README.md`'s Status block is stale in
other respects too (it says 63 tests and describes the campaign as not done). Both are **reported,
not fixed** — out of scope for this addendum, and recorded here so the next reader knows the
staleness was seen rather than missed.

---

## B15. Risks

| # | Risk | Response |
|---|---|---|
| **BR1** | The config's **detection block** drifts from what the classifier actually used, so the method block describes the CSV inaccurately | `profile_fields()` excludes the whole detection block by design (`config.py:216`), so none of the four Profile/Double-jet numbers is covered by G2's hash. **G6** checks the three *thresholds* against every CSV row: it catches **tightening** (a raised threshold the existing rows violate) but **not loosening** — every row satisfying a strict threshold satisfies a looser one. **`smooth_window_deg` is weaker still: it is neither hashed nor checkable at all**, because smoothing changes the profile non-monotonically and leaves no inequality in the CSV to violate. Gating on `config_sha256` would close both but would break the threshold-retuning workflow `classify.py:328-332` documents as required, and would fire on a comment-only YAML edit. Named, bounded, not worked around. Currently moot: the hashes match exactly (§B1.3) |
| **BR2** | The Data row reads `u_component_of_wind at 250 hPa` where the mockup reads `zonal wind u at 250 hPa` | Forced by the brief's from-data rule; a display alias would be the forbidden literal. **Flagged for the operator at review** (§B6); one line to overrule |
| **BR3** | `isFinite(null) === true` draws an absent core at 0 °N | Hydration maps `null → NaN` before any renderer sees a value; §B12.1 asserts both directions on every day of every season |
| **BR4** | The 47-panel figure becomes unbuildable | It does not: `output_names` keeps the panel paths in all three shapes and `--stage figure` still builds them. Only the *default* stage list changes (§B10) |
| **BR5** | `--stage`'s default becoming shape-dependent surprises a caller | The only in-tree caller is `jobs/derecho/campaign.pbs`, which passes no `--stage` and therefore gets the campaign default — which is the intended behaviour change. `test_stage_defaults_are_shape_dependent` pins both tuples |
| **BR6** | The embedded JSON breaks out of its `<script>` element | `<` escaped as `\\u003c` at insertion (§B5.1); §B12 asserts no `</script>` inside either block |
| **BR7** | A future season with a leap-affected day count breaks `month_starts` | No configured month is February, so the reference year is irrelevant — the same argument `figure.py:_month_ticks` and I6 already rest on. G1 would fail loudly if it ever stopped being true |
| **BR8** | ~300 KB of HTML is slow to open | 47 × 153 points is trivial for SVG; the payload is logged so a size surprise is visible. No gate |

---

## B16. Execution order

1. **Structure-only commit.** `docs/mockup/double_jet_explorer_v2.html` (moved, unchanged),
   `wave1-plan-explorer-addendum.md`, `docs/plans/2026-09-06_wave1_explorer_addendum_plan.md`, and
   the Codex review under `docs/codex_reviews/`. No behaviour.
2. **Behaviour commit.** `double_jet/explorer.py`, the `cli.py` edits of §B10,
   `tests/test_explorer.py`, and the three enumerated test edits of §B12.4.
   **`python -m pytest tests/ -q` green before the commit is written.**
3. **Build and inspect.**
   `python -m double_jet --config configs/double_jet.yaml --stage explorer --skip-download` — reads
   the existing intermediate and CSV, writes nothing upstream. Open the HTML in a browser from
   `file://`: click a point, step with the arrow keys, hover both charts, confirm the method block
   reads as §B6 and the note line as §B3. Check `results/season_summary.csv` against
   `data/jet_states_summary.txt`'s totals by eye (3 246 double, 3 932 single, 13 none).
4. **Documentation commit.** D4; the M-table in both plan copies; the write-up; the
   `results/campaign/` copies and `results/season_summary.csv`.
5. **Push.**

No PBS submission at any step. Step 3 runs on a login or Casper node in seconds.

---

## B17. Decision boundary on this machine

**Escalate — operator only:** every value in `configs/double_jet.yaml`; the year range; the sector,
level or season; anything in the mockup's visual design; any new dependency, CDN or framework; any
addition to the analysis (a trend fit, a significance test, persistence statistics); deleting the
panel-figure code or the committed `results/campaign/` panels.

**Decide in session:** the HTML template's internal organisation; log wording; test names and
fixture construction; error-message phrasing (subject to §B11's requirement that the offending name
appears); the exact matplotlib incantation that reproduces §B8's transcribed geometry.

**Report, do not accommodate:** any method-block field that turns out to have no source in the
intermediate, the config or the CSV; any season whose day count is not 153; any CSV row that
violates §B11 G6. Each of those is a discrepancy in the artifacts, and the explorer's job is to make
it visible, not to render around it.
