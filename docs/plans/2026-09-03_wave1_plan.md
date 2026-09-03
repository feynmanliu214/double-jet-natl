# DJET-NATL Wave 1 — ERA5 double-jet vs single-jet time series, North Atlantic–Europe: plan

Date: 2026-09-03
Wave prompt of record: `wave1.md` at the repo root — a verbatim copy the planning session wrote,
because the prompt reached that session only as conversation text and existed nowhere on disk.
Status: **Gate 4 complete (2026-09-03).** The Codex review loop converged at round 3 — no P0, no P1,
three P2 wording/scope fixes applied; reviews `r1`–`r3` and resolution sidecars `r1`–`r2` are in
`docs/codex_reviews/`. Gate 3 approval was taken from the operator's `/codex-review-plan` invocation,
which the wave prompt defines as the post-approval step. No code was written in the planning session.

**This document authorizes no compute.** §5.2's smoke job is pre-authorized by the wave prompt's
five-submission budget; the §5.3 campaign needs the operator's explicit go, every time (§10 E1).

`wave1-plan.md` at the repo root is the executor's copy of this file; this path under `docs/plans/` is
the reviewed draft of record that the `docs/codex_reviews/` rounds cite by line number.

The executing session gets `wave1-plan.md` and `CLAUDE.md` and nothing else. Everything it needs is
therefore in this document — including the Gate 1 findings it must not re-derive and the Gate 2
rulings it must not reopen.

---

## 0. Operator rulings, 2026-09-03 (Gate 2)

| # | Question | Ruling | Effect |
|---|---|---|---|
| **R1** | Which CDS product supplies the daily mean | **Derived daily-statistics product for all 47 seasons, plus a one-time equivalence cross-check against the 6-hourly raw for the smoke season** | §4.1, §5.2, §7 M2 |
| **R2** | The `≥95 % of core latitudes in 25–70 °N` sanity check | **Report it, do not abort.** The band and the 95 % target stay printed verbatim; the run finishes and the operator judges | §4.4, §7 M5 |
| **R3** | Seasons included | **1979–2025, 47 complete MJJAS seasons, 7 191 days** | everywhere |

R2 is the only ruling that changes a frozen number's *role*. No threshold value is changed anywhere
in this plan.

Codex review rounds 1–3 (`docs/codex_reviews/2026-09-03_wave1_plan_codex_review_20260903_r{1,2,3}.md`)
refined **I3**, hardened §4.1–§4.6, §5.0, §5.3 and §6, and consolidated every derived output path into
the one table in §4.2. No operator ruling and no threshold value was touched. The one rejected
finding — relocating `data/` and `figs/` to `$WORK` — is recorded as §10 E6.

---

## 1. Established at Gate 1 — inputs this plan builds on, does not re-derive

Everything in this section was measured on 2026-09-03. The executor reads it; it does not re-inspect.

### 1.1 Repo state

`~/projects/double-jet-natl/` was empty and not a git repository. `docs/plans/` and
`docs/codex_reviews/` were created by the planning session; nothing else exists. There is no
`references/plan-template.md` anywhere on the machine — this document follows the house format used
in `~/projects/butterfly/docs/plans/`.

### 1.2 No usable ERA5 exists locally — checked before planning any download

All of `$WORK` and `$SCRATCH` were searched.

| Found | Why it does not serve |
|---|---|
| `$WORK/projects/butterfly/data/era5/` (24 GB) | 2020 pressure-level archive plus 2021 heatwave windows; regional subsets on the wrong domain, no MJJAS |
| `$WORK/projects/butterfly/data/era5/wb2/era5_1p5_u250.nc` | ERA5 u250 — but **1.5° global, 2020-01-01 → 2021-02-04** only |
| `$SCRATCH` | nothing ERA5; nothing named u250 / mjjas / jet |

The WB2 file was used for the zero-cost threshold probe in §1.7. It is **not** an input to any
deliverable.

### 1.3 CDS access is live

- `~/.cdsapirc` holds `url: https://cds.climate.copernicus.eu/api` (the post-2024 endpoint) and a
  valid token: authenticated calls to `/profiles/v1/account/licences` and to the costing API return
  HTTP 200.
- `licence-to-use-copernicus-products` rev 12 is on the account.
- The account's own CDS job history shows **40 of 40 successful ERA5 retrievals on 2026-08-25**
  (27 single-levels, 13 pressure-levels), all `origin: api`. Token and licence are proven for
  `reanalysis-era5-pressure-levels`.
- **The derived dataset has never been retrieved from this account.** Same licence, but unproven
  until the first retrieve. §8 R3 covers the failure mode.

### 1.4 The daily-mean product is exactly the contract's definition

`derived-era5-pressure-levels-daily-statistics`. ECMWF's algorithm documentation
(<https://confluence.ecmwf.int/x/Qx2XGw>) states the retrieval builds

```
this_time = [f"{i+(this_hour%frequency):02d}:00:00" for i in range(0, 24, frequency)]
daily_data = earthkit.transforms.aggregate.daily_reduce(
    how="mean", time_shift={"hours": this_hour}, remove_partial_periods=True)
```

With `time_zone: utc+00:00` (`this_hour = 0`) and `frequency: 6_hourly` that is literally
`["00:00","06:00","12:00","18:00"]`, mean-reduced per calendar day. **This is the contract's
"average of the 00, 06, 12, 18 UTC analyses."** Confirmation delivered as Gate 1 required.

Two properties the prompt's wording did not anticipate, both handled in §4.1:

1. It is **not pre-computed** — ECMWF: *"the daily aggregation is calculated during the retrieval
   process and is not part of a permanently archived dataset."* R1's cross-check exists because of
   this sentence.
2. It **always returns a ZIP** — *"provided in netCDF format only (in a zip file) … one netCDF file
   per variable, and all files will be archived in a zip file."* This is why the process exposes no
   `data_format` / `download_format` input.

Process inputs, complete: `product_type, variable, year, month, day, pressure_level,
daily_statistic, time_zone, frequency, area`. `area` schema is `[N, W, S, E]`.

### 1.5 Request cost, limits and queue wait — measured

Costing API (`POST /api/retrieve/v1/processes/<id>/costing?request_origin=api`), area
`[75, -60, 20, 30]`, `u_component_of_wind`, 250 hPa:

| Request | cost | limit |
|---|---|---|
| derived daily, MJJAS **1979** | 153 | 400 |
| derived daily, MJJAS **2018** | 153 | 400 |
| derived daily, MJJAS **2025** | 153 | 400 |
| derived daily, two seasons at once | 306 | 400 |
| hourly product, MJJAS 2018, 4 × / day | 3 672 | 60 000 |

- One season per request is valid on both products. The derived product caps at two seasons; one per
  request is what the contract wants regardless.
- `day: 01…31` against 30-day months is safe — CDS drops invalid dates, and cost 153 is exactly the
  MJJAS day count (31+30+31+31+30).
- **Queue wait**, from this account's 2026-08-25 history: **8–95 s to start** (median ≈ 15 s).
  Processing: 13–75 s for single-level requests, 250–320 s for 13-level × 6-variable pressure-level
  requests — far larger than anything here. A season is minutes, not hours. The derived product
  computes on retrieval, so budget nearer the upper end.

### 1.6 Grid, coordinate conventions, and the area-extraction change

Read from a real new-CDS ERA5 pressure-level netCDF on disk
(`$WORK/projects/butterfly/data/era5/pressure_levels_2021-06-23.nc`, retrieved 2026-02-08):

- Coordinates `valid_time` (datetime64) · `pressure_level` (float64, **hPa**, descending) ·
  `latitude` (float64, **descending**, 90 → −90) · `longitude` (float64).
- Scalar coordinates `number` (= 0) and `expver` (= `'0001'`) are also present and must be dropped.
- Variable `u`: **float32, zlib complevel 1, no packing** (no `scale_factor` / `add_offset`),
  `_FillValue = NaN`, units `m s**-1`, `Conventions: CF-1.7`, history `GRIB to CDM+CF via cfgrib`.
- The derived product's documentation states its *"structure and naming conventions … are the same
  as the hourly dataset used as input"*, so the same names are expected — but §4.2 resolves every
  coordinate by name-lookup with a hard failure rather than assuming.
- **Longitude sign for an area subset is unverified**: the on-disk sample is a global request
  (0 … 359). §4.2 normalizes to [−180, 180), sorts ascending, and asserts −60 / +30 / 361 points,
  which is correct under either convention and is what the contract demands.
- **Area extraction changed on 2026-02-25**: with a grid-aligned `area` and **no `grid` keyword**,
  CDS now *crops only, no interpolation*. The box 75 / −60 / 20 / 30 is grid-aligned on the 0.25°
  grid, so the return is exact native points. **The request must not carry a `grid` key** — passing
  one re-enables interpolation.

Expected grid: latitude (75 − 20)/0.25 + 1 = **221**; longitude (30 − (−60))/0.25 + 1 = **361**.

### 1.7 The threshold probe, and what it says about the sanity checks

The contract's classification was run on data already on disk (WB2 ERA5 u250, MJJAS 2020, sector
60 °W–30 °E, 20–75 °N, daily mean of 00/06/12/18, 2.5° boxcar applied on the 0.25° ladder).
**1.5° source, one year — indicative only.**

| | unsmoothed | 2.5° boxcar |
|---|---|---|
| double-jet fraction | 51.6 % | **48.4 %** (band 5–90 % ✓) |
| no-jet days | 0 / 153 | 0 / 153 |
| cores within 25–70 °N | 90.1 % | **89.9 %** (target ≥ 95 % ✗) |

Daily sector-max U: min 17.7, median 27.5, max 44.0 m s⁻¹ — the 15 m s⁻¹ core threshold never bites.

The 25–70 °N miss is **not an edge artifact**: zero out-of-band cores lie within 1.25° (one
half-window) of the domain boundary. They are 9 subtropical cores at 23.0–24.75 °N (median
22.6 m s⁻¹) and 14 high-latitude cores at 70.25–73.25 °N (median 19.4 m s⁻¹) — physically real.
For reference, 23–72 °N holds 97.4 % and 22–74 °N holds 100 %. **R2 rules that this is reported, not
fatal.** No band is moved.

### 1.8 Stampede3 compute nodes have outbound network — proven on `skx`, unverified on `skx-dev`

`srun -p skx -N 1 -t 00:03:00` on `c479-103.stampede3.tacc.utexas.edu`:

```
DNS    cds.climate.copernicus.eu -> 136.156.139.54
HTTPS  https://cds.climate.copernicus.eu/api           -> 202
HTTPS  https://object-store.os-api.cci2.ecmwf.int/     -> 200   (serves the data file itself)
proxy  none;  default route via 129.114.127.254 dev eth0
```

This was undocumented — `butterfly/openifs/docs/2026-07-27_openifs_task1_plan.md` lists Stampede3
compute-node outbound network as *"Unknown — undocumented"*. It is now proven **for `skx`**. The
wave prompt's compute-node constraint is executable and the executor must not fall back to a login
node for the download. (Note the tension the executor should not be surprised by: butterfly's
`era5-download` skill says downloads run on a login node "at either site". The wave prompt overrides
that here.)

**`skx-dev` is not proven.** Its probe was queued and cancelled once the `skx` one answered, and the
partition was fully allocated at the time. The smoke job runs on `skx-dev` (§5.2), so both job
scripts open with a **connectivity preflight** that resolves and reaches the CDS API and the ECMWF
object store and **exits with a labelled message before issuing any CDS request** if either fails.
This is butterfly's own response to exactly this unknown (`openifs/docs/2026-07-27_openifs_task1_plan.md`
§2.0: the preflight "probes it and **exits before doing any work**"). It costs seconds and turns a
partition surprise into one clean smoke-budget exit rather than a half-finished download.

Two short `srun` probes were consumed at Gate 1 (skx-dev, cancelled; skx, answered). They are
inspection, not smoke submissions, and do not count against the five-submission budget.

### 1.9 Environment

`/work2/11114/zhixingliu/stampede3/conda-envs/graphcast/bin/python` (Python 3.11.15) already carries
every package this wave needs and **nothing is installed or changed**:

| package | version |
|---|---|
| cdsapi | 0.7.7 |
| xarray | 2026.7.0 |
| netCDF4 | 1.7.4 |
| numpy | 2.4.3 |
| scipy | 1.17.1 |
| matplotlib | 3.10.9 |
| pandas | 3.0.3 |
| dask | 2026.7.1 |
| pyyaml | 6.0.3 |

Nothing else on the machine has `cdsapi` — not the `python/3.12.11` module, not `aires`, not any
venv. (butterfly's `era5-download` skill claims cdsapi is absent from this env; that statement is
stale.)

**Coupling, stated rather than hidden:** this env belongs to butterfly and is described there as
"shared and pinned". This wave uses it **read-only** and records the interpreter path and the table
above in the intermediate's attributes, so a future rebuild of that env is detectable rather than
silent. A dedicated venv would be a two-minute install, but creating one is an environment change
and `CLAUDE.md` puts that on the escalate list — so it is not planned. Raise it if you prefer it.

### 1.10 Space and allocation

`/home1` 9.8 / 14 GB used (≈ 4.2 GB headroom — this wave adds < 30 MB). `/work2` 688 / 1024 GB.
`/scratch` unquotaed. Allocation `TG-ATM170020`: 107 023 SUs, expiring 2026-09-30. Queue ceilings:
`skx` 48 h / 256 nodes, `skx-dev` 2 h / 16 nodes.

---

## 2. Interpretations this plan fixes (small, and stated so the executor does not re-decide)

These follow from the contract; none changes a threshold. They are recorded because a fresh session
would otherwise have to guess.

| # | Item | Ruling of this plan |
|---|---|---|
| **I1** | "boxcar-smoothed … with a 2.5° window" | **11 grid points** — the only centerable choice at 0.25° (11 points span exactly 2.5° first-centre to last-centre) |
| **I2** | Boxcar behaviour at 20 °N / 75 °N | **Truncated, renormalized** window (divide by the count of points actually inside the domain). Not edge-replication, not NaN. Empirically immaterial: no core in the §1.7 probe lands within a half-window of the boundary. The download area stays exactly as the contract states — no padding |
| **I3** | Core = "local maximum" | `scipy.signal.find_peaks` **at its defaults**: an interior sample strictly greater than its neighbours, or — for an exact flat top — the plateau's **midpoint**. The domain endpoints can never be cores by construction (§8 R7). Verified on the installed scipy 1.17.1: `find_peaks([0,1,2,3,3,3,2,1,0])` → index 4, the midpoint; `plateau_size=(None,1)` → `[]`, i.e. tightening to literal strictness would **discard** a flat-topped core rather than locate it. The default is the better science for a case whose probability in smoothed float32 is ≈ 0, so the *wording* here changed, not the behaviour |
| **I4** | "keep the two strongest that satisfy the separation rule" | Order surviving cores by descending U; scan pairs in that order and accept the **first pair** satisfying *both* the 10° separation and the 5 m s⁻¹ prominence. That pair is the strongest core that has any valid partner, paired with its strongest valid partner. A day is `double` iff some pair satisfies both |
| **I5** | "plausible mid-latitude jet (peak 20–40 m/s)" | Read as the **season median** of the daily maximum of the smoothed profile, not the single largest day (2020 probe: median 27.5, max 44.0). Printed as a number for the operator's eyeball check, never a gate |
| **I6** | Panel x-axis | **Day-of-season index 0…152** with month tick labels, so all 47 panels share an axis exactly (calendar day-of-year for 1 May shifts by one between leap and non-leap years) |
| **I7** | Zonal mean | Plain unweighted `mean` over the 361 longitudes, as the contract's "equal weight per longitude" states. No trapezoid, no cos φ (the average is along longitude at fixed latitude) |

---

## 3. Repository layout

```
double-jet-natl/
├── CLAUDE.md                              repo invariants (short; written in step 1)
├── wave1.md                               the wave prompt, verbatim (provenance)
├── wave1-plan.md                          this plan, post-Gate-4
├── configs/
│   └── double_jet.yaml                    THE config block — every threshold, one file
├── docs/
│   ├── plans/2026-09-03_wave1_plan.md     this draft
│   └── codex_reviews/                     Gate 4 output
├── double_jet/
│   ├── __init__.py
│   ├── __main__.py                        `python -m double_jet` — the canonical entry point
│   ├── cli.py                             argparse, stage dispatch, output-name derivation
│   ├── config.py                          dataclass + YAML loader + provenance and config hashes
│   ├── download.py                        CDS requests, idempotent, ≤ 3 in flight
│   ├── profile.py                         raw season files → U(φ, t) intermediate
│   ├── classify.py                        smoothing, core detection, state labels
│   └── figure.py                          smoke panel and the 8 × 6 grid
├── scripts/
│   └── double_jet.py                      thin shim: repo root onto sys.path, then cli.main()
├── jobs/
│   ├── smoke_2018.slurm
│   └── download_all.slurm
├── tests/
│   ├── test_classify.py                   synthetic profiles → known states
│   ├── test_profile.py                    synthetic netCDFs → every ingestion gate fires
│   ├── test_cli.py                        `python -m double_jet --help` imports and exits 0
│   └── test_config.py                     config round-trip, sector arithmetic, output naming
├── data/                                  intermediates (few MB) — gitignored
├── figs/                                  gitignored
└── logs/                                  gitignored
```

Small modules, not one 500-line script and not a framework: each stage has a distinct input
contract, a distinct verification, and is separately re-runnable.

**The entry point is `python -m double_jet --config configs/double_jet.yaml`.** The wave prompt asks
for `python scripts/double_jet.py --config <yaml>` *"or equivalent"*; the module form is that
equivalent and is what the jobs run, because executing `scripts/double_jet.py` directly puts
`scripts/` — not the repository root — on `sys.path`, so `import double_jet` fails. The script is
kept as a documented shim that inserts the repo root on `sys.path` and calls `cli.main()`, so both
spellings work. Nothing is pip-installed: an env change is on the escalate list (§1.9).

`data/`, `figs/` and `logs/` are gitignored, and **`logs/` must already exist at the first `sbatch`** —
Slurm opens `-o`/`-e` before the job body runs (butterfly's own note,
`jobs/stampede3/submit_lead30_smoke.sh:25`). Step 1 of §9 creates it.

---

## 4. What each module does, and how it is verified

### 4.1 `download.py` — CDS retrieval

**Request template**, built once from the config, saved verbatim beside every file it produces:

```python
{
  "product_type":    "reanalysis",
  "variable":        ["u_component_of_wind"],
  "year":            "<YYYY>",
  "month":           ["05", "06", "07", "08", "09"],
  "day":             ["01", …, "31"],
  "pressure_level":  ["250"],
  "daily_statistic": "daily_mean",
  "time_zone":       "utc+00:00",
  "frequency":       "6_hourly",
  "area":            [75, -60, 20, 30],      # N, W, S, E
}
```

**No `grid` key** (§1.6). Dataset `derived-era5-pressure-levels-daily-statistics`.

- Output lands on `$SCRATCH` as `u250_natl_mjjas_<year>.zip` — the transport container the derived
  product always returns (§1.4) — whose single member is extracted to `u250_natl_mjjas_<year>.nc`,
  with the request dict written to `u250_natl_mjjas_<year>.request.json`. **The `.nc` and the
  `.request.json` are the season's artifacts; the ZIP is an incidental transport file.** It is left
  in place — the pipeline deletes nothing, per the wave prompt's storage contract — but it is not
  promised, not validated and not required: a season whose ZIP is gone is complete.
- **Idempotent, and identity-checked**: a season is skipped only when *all* of — the `.nc` exists and
  opens with 153 time steps × 221 latitudes × 361 longitudes; the `.request.json` sidecar exists; and
  that sidecar **equals, key for key, the request that would be issued now**. Anything else is
  re-requested. This is what stops a file fetched under a different area, level or frequency from
  being silently reused after a config edit. `--skip-download` never issues a request and instead
  fails loudly, listing every season that is missing or fails any part of that check.
- **Atomic**: every download writes `<name>.part` and renames only after the ZIP extracts and the
  shape check passes, so an interrupted or killed job cannot leave a truncated file that a later run
  accepts as complete. The same rule covers the 6-hourly cross-check file.
- **Concurrency**: `ThreadPoolExecutor(max_workers=3)`, one `cdsapi.Client()` per worker (the client
  is not documented thread-safe, and one per worker costs nothing). Never more than 3 in flight.
- **Failures are not swallowed**: each season's exception is collected and the stage exits non-zero
  with the list. A rerun of the identical command completes only the missing seasons.

**R1 cross-check, smoke season only.** A second request to `reanalysis-era5-pressure-levels` for the
same season — `time: ["00:00","06:00","12:00","18:00"]`, `data_format: "netcdf"`,
`download_format: "unarchived"`, same area, no `grid` — lands as
`u250_natl_mjjas_2018_6hourly.nc`.

**Both operands are read through the single normalizing reader of §4.2** (steps 1–8), so longitude
convention, latitude order, units and scalar-coordinate handling are identical by construction before
anything is subtracted. They are then aligned with **`xr.align(a, b, join="exact")`**, which raises
rather than silently intersecting: installed xarray 2026.7.0 defaults `arithmetic_join` to `inner`, so
a bare `a - b` on `300…30` versus `−60…30` coordinates would compare only the overlap and **pass a
gate it never actually tested** (verified on this env: subtracting two 3-point arrays sharing 2
coordinates yields a silent 2-point result). The assertion is then

```
n_compared == 153 × 221 × 361    and    max | mean_local(00,06,12,18) − derived_daily | < 1e-3 m/s
```

with the achieved maximum **and the compared point count** printed and written to
`data/smoke_2018_r1_validation.json`. 1e-3 is far above float32 round-off on a four-term mean
(≈ 1e-5 m s⁻¹ at 30 m s⁻¹) and far below any wrong-hour-set error, which would be O(1) m s⁻¹.
**This assertion is a hard gate** — the campaign does not start if it fails.

### 4.2 `profile.py` — raw seasons → the cached intermediate

Per season file, in order, every step a hard failure if it does not hold:

1. Resolve coordinate names by lookup — latitude ∈ {`latitude`, `lat`}, longitude ∈
   {`longitude`, `lon`}, time ∈ {`valid_time`, `time`}, level ∈ {`pressure_level`, `level`,
   `isobaricInhPa`}. An unrecognised name is an error, never a guess.
2. **Assert the level is 250 by reading the pressure coordinate's value**, never by index. If it is
   a size-1 dimension, squeeze after asserting. If the coordinate is absent, fail.
3. Drop the scalar `number` / `expver` coordinates if present.
4. Longitude → `((lon + 180) % 360) − 180`, sort ascending; then assert the **whole array** equals
   `np.arange(-60.0, 30.0 + 1e-9, 0.25)` to 1e-6 — 361 points *and* uniform spacing. Asserting only
   the count and the two bounds would accept a non-uniform 361-point axis, which I1's "11 samples =
   2.5°" reading silently depends on. Correct under either sign convention CDS may have used.
5. Latitude → sort ascending; assert the whole array equals `np.arange(20.0, 75.0 + 1e-9, 0.25)` to
   1e-6 — 221 points, uniform spacing.
6. **Units, read not assumed**: `latitude.units == degrees_north`, `longitude.units == degrees_east`,
   the pressure coordinate's units `hPa` (a `Pa`-tagged coordinate would make step 2's "= 250" check
   wrong by a factor of 100), and `u.units` one of the accepted m s⁻¹ spellings (`m s**-1`, `m s-1`,
   `m/s`). Anything else fails: the thresholds in `configs/double_jet.yaml` are in m s⁻¹ and nothing
   downstream converts.
7. Time → assert 153 unique days, all in May–September of that year, no NaT.
8. Assert `u` is **everywhere finite** (`np.isfinite`), not merely non-NaN, so ±inf is caught too.
9. `U = u.mean("longitude")` — plain unweighted mean (I7).

The 47 season profiles are concatenated along time, sorted, and written as float32 to
`data/u250_natl_mjjas_1979-2025.nc` (7 191 × 221, ≈ 6.4 MB raw, ≈ 5 MB with zlib=4). **Unsmoothed**,
as the contract requires.

**One function owns every derived output path.** `cli.output_names(years, smoke)` is the *only* place
that constructs a path under `data/` or `figs/`; no analysis stage builds one of its own. Raw-cache
names under `$SCRATCH` stay with `download.py` (§4.1) and Slurm log paths stay in the job headers —
routing those through the CLI helper would be coupling that buys nothing. It returns:

| Run | intermediate | states CSV | summary | panels | R1 record |
|---|---|---|---|---|---|
| **full campaign** (1979–2025) | `data/u250_natl_mjjas_1979-2025.nc` | `data/jet_states_mjjas_1979-2025.csv` | `data/jet_states_summary.txt` | `figs/double_jet_natl_panels.{pdf,png}` | — |
| **smoke** (`--smoke`) | `data/smoke_2018_profile.nc` | `data/smoke_2018_jet_states.csv` | `data/smoke_2018_summary.txt` | `figs/smoke_2018.png` | `data/smoke_2018_r1_validation.json` |
| **any other `--years` subset** | `…_<first>-<last>.nc` | `…_<first>-<last>.csv` | `data/jet_states_summary_<first>-<last>.txt` | `figs/double_jet_natl_panels_<first>-<last>.{pdf,png}` | — |

The full-campaign row is the wave prompt's contract text, reproduced exactly, and **only** that row
may use those names.

Two rules make the `<first>-<last>` suffix a faithful label rather than an ambiguous one:
`--years` is parsed as a **validated inclusive contiguous range** `FIRST-LAST` and nothing else — an
arbitrary year list such as `1979,2025` is rejected at parse time — and the full-campaign row is
selected by **exact equality to 1979–2025**. Without the first rule a gappy set sharing the campaign's
endpoints would silently claim the campaign's filenames. No partial run can therefore overwrite a
campaign artifact: the collision is removed at its root rather than guarded after the fact. §4.3, §4.4
and §4.5 name their outputs by referring to this table, never by restating a literal.

Attributes recorded on the file: sector bounds, level, `source_dataset`, the full list of source
filenames with byte sizes and SHA-256, the request template, the config SHA-256, the interpreter
path and the §1.9 version table, the creation timestamp, and this plan's path.

Every downstream stage reads only this file. **Changing a threshold and re-running touches no raw
file** — the contract's requirement, satisfied structurally.

### 4.3 `classify.py` — states and the CSV

A pure function of `(U, lat, params)`:

1. **Smooth** with the 11-point centered boxcar, truncated and renormalized at the two ends (I1, I2).
2. **Cores** = `scipy.signal.find_peaks` on the smoothed profile **at its defaults** — interior
   samples above both neighbours, plus the **midpoint** of any exact flat top, exactly as I3
   specifies; the domain endpoints are excluded by construction — keeping those with `U ≥ 15 m/s`.
3. **State** (I4):
   - no surviving core → `none`; all core columns blank.
   - a pair passes both `lat_north − lat_south ≥ 10°` and
     `min(U_smoothed between them) ≤ min(U_south, U_north) − 5` → `double`; record both cores
     **ordered south to north** and the between-cores minimum.
   - otherwise → `single`; record the strongest core in `lat_1` / `u_1`, leave `lat_2` / `u_2` /
     `interjet_min` blank.
4. Write the states CSV named by §4.2's table: `date,state,lat_1,u_1,lat_2,u_2,interjet_min`,
   dates `YYYY-MM-DD`, 7 191 rows for the full campaign.

Before classifying, the stage compares the **profile-determining** part of the config it was handed
(sector, level, season months, year range) against the hash recorded in the intermediate's attributes
and **fails** if they differ — that is the "I changed the sector and reused the old intermediate"
error, which is otherwise silent. The detection thresholds are deliberately *excluded* from that
hash: changing a threshold and re-running against the same intermediate is exactly what the contract
requires to keep working.

### 4.4 The sanity checks, and which of them stop the run

Written to the summary file named by §4.2's table (full campaign: `data/jet_states_summary.txt`) and printed:

| Check | Contract text | Behaviour |
|---|---|---|
| Double-jet fraction | in 5–90 % over all MJJAS days | **hard gate** — non-zero exit |
| Core latitudes | ≥ 95 % within 25–70 °N | **reported, not a gate (R2)** — prints the achieved fraction against the 95 % target, the count of out-of-band cores, and the dates and latitudes of the worst offenders |
| Smoke profile | plausible mid-latitude jet, peak 20–40 m s⁻¹ | printed as the season median of the daily maximum (I5) plus min/max, for the operator's eyeball check before anything downstream is trusted |
| Grid | 361 longitudes, bounds read from the file | **hard gate** in `profile.py` (§4.2 step 4) |
| Level | pressure coordinate asserted = 250, never indexed | **hard gate** in `profile.py` (§4.2 step 2) |
| R1 equivalence | derived daily == local mean of 00/06/12/18 | **hard gate**, smoke only (§4.1) |

### 4.5 `figure.py`

Filenames come from §4.2's table; the full-campaign and smoke instances are:

- `figs/smoke_2018.png` — the single smoke panel, produced first and alone.
- `figs/double_jet_natl_panels.pdf` and `.png` — 47 panels in an 8 × 6 grid (48 cells, last blank),
  shared axes: x = day-of-season 0…152 with month ticks (I6), y = 20–75 °N.
- Background: `pcolormesh` of the **smoothed** profile in greys with **`rasterized=True`** — 47 ×
  153 × 221 ≈ 1.6 M quads would otherwise produce an unusable vector PDF. One shared colorbar.
- Cores: scatter points coloured by state (single vs double), both cores drawn on double days,
  none-days left blank.
- One legend; the config thresholds, the source dataset id and the date range printed in the
  suptitle/margin. `matplotlib.use("Agg")`.

### 4.6 Tests

`pytest tests/` must be green before any job is submitted.

- `test_classify.py` — synthetic latitude profiles with analytically known answers: a single
  Gaussian → `single`; two Gaussians 20° apart with a deep trough → `double` with the expected core
  latitudes; the same pair 8° apart → `single` (separation rule); the same pair 20° apart with a
  3 m s⁻¹ trough → `single` (prominence rule); a flat 10 m s⁻¹ profile → `none`; three cores where
  the strongest pair fails separation but another pair passes → `double` on the right pair (I4); a
  monotone ramp to the domain edge → no core at the edge (I3); and an **above-threshold exact flat
  top** → one core at the plateau's midpoint, which locks in I3's chosen `find_peaks` behaviour so a
  later `plateau_size` "tightening" fails the suite instead of silently dropping cores.
- `test_profile.py` — synthetic netCDFs written to `tmp_path`, one per gate, each asserted to *fire*:
  longitudes supplied as `300…30` normalize to `−60…30` and pass; a non-uniform 221-point latitude
  axis is rejected; `Pa`-tagged pressure is rejected; a `K`-tagged wind field is rejected; a 200 hPa
  level is rejected; scalar `number`/`expver` coordinates are dropped; a `+inf` cell is rejected; a
  one-member ZIP extracts to the expected `.nc`; a request sidecar that differs from the current
  request forces a re-download instead of a skip.
- `test_cli.py` — `python -m double_jet --help` exits 0, which is a direct regression test for the
  `sys.path` failure mode above; `scripts/double_jet.py --help` exits 0 too.
- `test_config.py` — the YAML round-trips into the dataclass; the sector arithmetic yields 221 × 361;
  the boxcar window resolves to 11 points; `cli.output_names` yields **pairwise disjoint** paths for
  the full campaign, the smoke run and a `--years` subset, with only the full-campaign case producing
  the contract names; a non-contiguous `--years` argument (`1979,2025`) is **rejected at parse time**
  rather than silently borrowing the campaign's endpoints; the profile-determining hash ignores
  threshold changes and reacts to sector changes.

---

## 5. Jobs

`CLAUDE.md`: never run a model or a driver bare on a login node; five smoke-scale submissions per
wave; production submission needs explicit approval every time.

### 5.0 Job-script contract — both scripts, identical prologue

Taken from the house pattern at `butterfly/jobs/stampede3/submit_lead30_smoke.sh:27-49`, because it is
already proven on this machine:

```bash
set -euo pipefail
[[ -n "${SLURM_JOB_ID:-}" ]] || { echo "ALARM: run via sbatch, not on a login node." >&2; exit 2; }
cd /home1/11114/zhixingliu/projects/double-jet-natl
module purge
source /work2/11114/zhixingliu/stampede3/miniforge3/etc/profile.d/conda.sh
conda activate /work2/11114/zhixingliu/stampede3/conda-envs/graphcast
python -c 'import cdsapi, xarray, scipy, matplotlib'                      # env is what we think it is
python -m double_jet --config configs/double_jet.yaml --preflight-network  # §1.8; exits 2 on failure
```

Three things this fixes that a bare `python …` would not: the machine's default `python` is
`/usr/bin/python` and **has no `cdsapi`**; the `cd` to the repo root is what makes `python -m
double_jet` resolve at all; and the network preflight fails the job in seconds on an unproven
partition instead of part-way through a download. `logs/` must already exist at submit time (§3).

### 5.1 Staging — no job

`git init`, the module skeleton, the config, and `pytest tests/`. Pure-CPU unit tests on synthetic
arrays; no data, no network.

### 5.2 The smoke job — pre-authorized, 1 of 5

```
sbatch jobs/smoke_2018.slurm          # -A TG-ATM170020 -p skx-dev -N 1 -n 1 -t 00:30:00
```

Runs `python -m double_jet --config configs/double_jet.yaml --smoke`, which is:

1. the derived-daily request for MJJAS 2018 (153 fields) **and** the 6-hourly request for the same
   season (612 fields), ≤ 3 in flight;
2. the R1 equivalence assertion;
3. profile → `data/smoke_2018_profile.nc` (named apart from the campaign intermediate so the two can
   never be confused);
4. classify → the summary block;
5. `figs/smoke_2018.png`.

30 minutes against measured queue waits of 8–95 s and processing of minutes gives ample headroom
inside the 2 h `skx-dev` ceiling.

**The wave stops here and reports.** The contract requires the smoke profile to be inspected before
anything downstream is trusted.

### 5.3 The campaign — requires explicit approval, not pre-authorized

```
sbatch jobs/download_all.slurm        # -A TG-ATM170020 -p skx -N 1 -n 1 -t 04:00:00
```

Runs `python -m double_jet --config configs/double_jet.yaml --stage all` over 1979–2025:
47 requests at ≤ 3 in flight, then profile, classify and figure in the same job (seconds of CPU on a
7 191 × 221 array). Four hours is ≈ 3× the worst-case estimate from the measured per-request times.
One node-hour is ≈ 4 SUs against 107 023 available.

A threshold re-run afterwards touches **no raw file and no `$SCRATCH` path at all** — `classify` and
`figure` read only `data/u250_natl_mjjas_1979-2025.nc`, so they keep working after `$SCRATCH` is
purged. It takes about a second; run it in `idev`:

```
python -m double_jet --config configs/double_jet.yaml --skip-download --stage classify,figure
```

**Do not reach for `download_all.slurm` to do this.** That script is pinned to `--stage all`, so it
would re-validate the entire raw cache and — after a `$SCRATCH` purge — silently re-issue all 47 CDS
requests. It is also a production-queue submission, which needs fresh operator approval every time
(§10 E1). Exactly **two** scripts issue CDS requests and they are not interchangeable:
`smoke_2018.slurm` issues **2** (one season, both products — §5.2) and is pre-authorized;
`download_all.slurm` issues **47** and is not.

### 5.4 Budget

Smoke: 1 of 5. Four remain for diagnosing and resubmitting a failed smoke, which `CLAUDE.md` says is
exactly what they are for. The campaign is not a smoke job at any size.

---

## 6. Where every byte lands

Nothing raw is written under `$HOME` or `$WORK` — the wave prompt's storage contract, which also
places the few-MB intermediate in the repo's `data/` with the `$HOME` quota explicitly called out.

**The `$SCRATCH` tree is a cache, not a durable artifact.** It is purge-on-inactivity by design; the
pipeline never deletes from it, but nothing downstream depends on it surviving — `classify` and
`figure` read only `data/u250_natl_mjjas_1979-2025.nc`. After a purge the intermediate still
regenerates every deliverable, and the raw files themselves regenerate by re-running the same command
(≈ 2 GB, minutes per season). `$HOME` is not backed up either; the intermediate is 5 MB and fully
reproducible, which is why the contract puts it there rather than in `$WORK`. §10 E6 records the
mirror-to-`$WORK` option if durability is later wanted.

| Path | FS | Size | Written by |
|---|---|---|---|
| `$SCRATCH/double-jet-natl/era5_raw/u250_natl_mjjas_<year>.zip` × 47 — transport containers, not artifacts (§4.1) | scratch | ≈ 30 MB ea | 4.1 |
| `$SCRATCH/double-jet-natl/era5_raw/u250_natl_mjjas_<year>.nc` × 47 | scratch | ≈ 30 MB ea | 4.1 |
| `$SCRATCH/double-jet-natl/era5_raw/u250_natl_mjjas_<year>.request.json` × 47 | scratch | ≈ 1 KB ea | 4.1 |
| `$SCRATCH/double-jet-natl/era5_raw/u250_natl_mjjas_2018_6hourly.nc` (+ `.request.json`) | scratch | ≈ 130 MB | 4.1 (R1) |
| `data/u250_natl_mjjas_1979-2025.nc` | $HOME | ≈ 5 MB | 4.2 |
| `data/smoke_2018_profile.nc` | $HOME | ≈ 150 KB | 4.2 |
| `data/smoke_2018_jet_states.csv`, `data/smoke_2018_summary.txt` | $HOME | ≈ 15 KB | 4.3 |
| `data/smoke_2018_r1_validation.json` | $HOME | ≈ 1 KB | 4.1 |
| `data/jet_states_mjjas_1979-2025.csv` | $HOME | ≈ 500 KB | 4.3 |
| `data/jet_states_summary.txt` | $HOME | ≈ 4 KB | 4.4 |
| `figs/double_jet_natl_panels.pdf` / `.png` | $HOME | ≈ 5–15 MB / ≈ 3 MB | 4.5 |
| `figs/smoke_2018.png` | $HOME | ≈ 300 KB | 4.5 |
| `logs/*.out` | $HOME | small | slurm |

`$SCRATCH` total ≈ 3 GB. `$HOME` total added < 30 MB against 4.2 GB headroom.

---

## 7. Deliverables and how each is verified

| # | Deliverable | Produced by | Verified by |
|---|---|---|---|
| **M1** | 47 raw season `.nc` + request JSON on `$SCRATCH` — a **purgeable cache**, not a durable artifact (§6); the ZIPs are incidental transport files, not artifacts (§4.1) | 4.1 | shape check *and* request-sidecar identity per file; `.part` + atomic rename; rerun completes only what is missing |
| **M2** | Derived daily == mean of 00/06/12/18 | 4.1, smoke | hard assertion, max abs diff < 1e-3 m s⁻¹, achieved value printed |
| **M3** | `data/u250_natl_mjjas_1979-2025.nc` | 4.2 | level asserted 250 by value; 361 longitudes with bounds read from the file; 7 191 unique MJJAS days; no NaN; provenance attributes present |
| **M4** | `data/jet_states_mjjas_1979-2025.csv` | 4.3 | 7 191 rows; every row's state consistent with its core columns; `pytest tests/test_classify.py` green |
| **M5** | Sanity block | 4.4 | double fraction in 5–90 % (gate); core-latitude fraction reported against 95 % (R2); smoke peak median reported |
| **M6** | `figs/smoke_2018.png` | 4.5 | produced before anything else; operator inspects the profile |
| **M7** | `figs/double_jet_natl_panels.pdf` / `.png` | 4.5 | 47 populated panels, shared axes, one legend, thresholds printed, PDF opens and is < 20 MB |
| **M8** | One documented command | cli | `python -m double_jet --config configs/double_jet.yaml` reproduces M1–M7 end to end; `--skip-download` reuses `$SCRATCH` |
| **M9** | The entry point runs from a clean shell | cli, scripts/ | `python -m double_jet --help` exits 0 in `test_cli.py` and again in the job prologue, before any request |

---

## 8. Risks, named

| # | Risk | Response |
|---|---|---|
| **R1** | The derived product's netCDF structure differs from the hourly one | Docs say it does not (§1.4). §4.2 asserts every coordinate by name and value, so a mismatch fails on season 1 of the smoke run, not after 47 requests |
| **R2** | Longitude returned as 300…30 rather than −60…30 | Normalized to [−180, 180) and asserted; correct either way (§4.2 step 4) |
| **R3** | The derived dataset's licence is unaccepted on this account | Never retrieved from here before (§1.3). A 403 on the smoke run's first request is the symptom; the fix is accepting the licence on the CDS profile, which is the operator's to do. Do not work around it |
| **R4** | Derived daily mean is not the contract's mean | R1's cross-check is exactly this test, and it gates the campaign (§4.1) |
| **R5** | CDS throttling or a transient failure mid-campaign | ≤ 3 in flight; per-season exceptions collected and reported with a non-zero exit; idempotent rerun completes only the gaps |
| **R6** | 47-panel vector PDF is unusably large | `rasterized=True` on every pcolormesh (§4.5); M7 asserts < 20 MB |
| **R7** | A jet core exactly at 20 °N or 75 °N is unrepresentable | True by construction (I3). The §1.7 probe puts the extreme cores at 23.0 and 73.25 °N, so it is not binding. Recorded, not worked around |
| **R8** | The double-jet fraction gate (5–90 %) fires | The probe gives ≈ 48 % at 1.5°. If it fires on the real archive, that is the contract's stop-and-report, and the run exits non-zero |
| **R9** | The `graphcast` env is rebuilt by butterfly and drifts | Version table recorded in the intermediate's attributes (§1.9, §4.2), so drift is detectable rather than silent |
| **R10** | `skx-dev` outbound network is unproven (§1.8) | Connectivity preflight at the top of both job scripts exits in seconds with a labelled message, before any CDS request; recoverable inside the smoke budget |
| **R11** | A stale `$SCRATCH` file from a different request is silently reused | Request-sidecar identity check on every skip (§4.1); `.part` + atomic rename so a truncated file never looks complete |
| **R12** | A smoke or `--years` rerun overwrites campaign outputs | One function owns every derived output path (§4.2's table); `--years` must be a contiguous range and the campaign row is selected by exact equality to 1979–2025, so a subset cannot borrow the contract names. Tested pairwise, plus the non-contiguous case (§4.6) |
| **R13** | `import double_jet` fails under the documented invocation | `python -m double_jet` is canonical; `test_cli.py` and the job prologue both exercise it (§3, §5.0) |
| ~~(retired)~~ | ~~compute nodes lack outbound network at all~~ | Answered at Gate 1 for `skx` (§1.8). The residual `skx-dev` case is R10 above |

---

## 9. Execution order

1. `git init`; skeleton, `CLAUDE.md`, `.gitignore`, `mkdir -p logs data figs`, this plan.
   Structure-only commit. **`wave1.md` is already on disk** — the planning session wrote it verbatim
   before handoff, because the prompt existed only in that conversation and the executor could not
   have reproduced it.
2. Config + the six modules + tests. `pytest tests/` green. Behaviour commit, separate from step 1.
3. **Smoke** (§5.2, submission 1 of 5): MJJAS 2018 both products → R1 assertion → profile → classify
   → `figs/smoke_2018.png`.
4. **Report and stop.** Smoke profile, the R1 achieved tolerance, the state counts, and the
   core-latitude diagnostic go to the operator. No campaign submission before approval.
5. On approval: `download_all.slurm` (§5.3) → M1, M3, M4, M5, M7.
6. Report: state counts over 7 191 days, the 25–70 °N diagnostic against its 95 % target, and the
   figures.

---

## 10. Escalations carried into execution

| # | Item | Who decides |
|---|---|---|
| **E1** | The 47-season campaign submission (§5.3) | Operator, explicitly, after the smoke reports — `CLAUDE.md` |
| **E2** | If the double-jet fraction gate fires | Operator. The executor reports and stops; it does not retune |
| **E3** | If the core-latitude fraction is far below 95 % on the full archive | Operator. Under R2 the run finishes and reports; no band is moved without a ruling |
| **E4** | If a dedicated venv is preferred over the shared `graphcast` env (§1.9) | Operator. Not planned; an env change is on the escalate list |
| **E5** | A CDS 403 on the derived dataset (R3) | Operator accepts the licence; the executor does not work around it |
| **E6** | Whether `data/` should be mirrored to `$WORK` for durability | Operator. The wave prompt's storage contract puts the intermediate in the repo under `$HOME` with the quota called out, so no mirror is planned. Codex round 1 flagged the tension with the parent `CLAUDE.md`'s general "anything that must survive goes to `$WORK`" rule; recorded here rather than resolved unilaterally |

## 11. Decision boundary, instantiated

**Escalate:** every threshold in `configs/double_jet.yaml`; the year range; the sector; the level;
which sanity checks gate versus report; any environment or dependency change; every non-smoke
submission.

**Decide in-session:** module decomposition, function signatures, naming, logging, the thread-pool
mechanics, error-handling shape, test structure, figure styling that does not change what is
plotted.
