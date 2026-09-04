# DJET-NATL Wave 1 — Derecho addendum: the RDA loader and the 47-season campaign

**Written:** 2026-09-04 · **Machine:** NCAR Derecho · **Status:** post-Gate-4, reviewed
**Extends:** `wave1-plan.md` (post-Gate-4, 2026-09-03). **Does not restate it.**
**Authorized by:** deviation **D3** (`docs/deviations.md`) and the operator's Gate-2 rulings below.

This addendum covers exactly four things: the **loader** that replaces the CDS download stage, its
**sidecar**, the **PBS campaign** shape on this machine, and the **2018 regression check** that
stands between the loader and the campaign. Everything else — the sector, the level, the season, the
year range, the thresholds, the state rules, the sanity bands, the daily-mean definition, the figure
design, and every stage downstream of `profile.open_normalized` — is `wave1-plan.md`'s and is
untouched. Where this document is silent, the plan governs.

> **Note on the template.** The brief asks that this follow `references/plan-template.md`. That file
> does not exist in this repository or anywhere on this machine (searched). This document therefore
> mirrors the section structure of `wave1-plan.md` itself, which is the reviewed exemplar in the
> tree. Sections are numbered `A0…A15` so that a cross-reference to "§4.2" is unambiguously the
> plan's and "§A5" is unambiguously this addendum's.

---

## A0. Role, and what this addendum does not authorize

The session that reads this is **executing**. The gates are closed. Do not re-plan, do not re-argue
D1–D3, do not reopen a ruling.

It authorizes: a new reader module, a new dispatcher module, a new test file, **four** narrowly
named provenance edits (`profile.py` ×2, `figure.py` ×1, plus the `cli.py` dispatch of §A7.3),
**two** enumerated existing-test edits (one line in `tests/test_profile.py`'s fixture helper, two
in `tests/test_config.py` — §A8), additive config keys, one PBS job script, and the campaign at the
shape in §A10. Every one of those is enumerated; nothing outside
the enumeration is authorized.

It does not authorize: any change to a frozen number; any change to `open_normalized`,
`season_profile`, or `classify.py`; **any *other* change to `figure.py`** than the one provenance
line of §A7.2; deleting or gutting `download.py`; any CDS retrieval from Derecho for any reason;
any job larger than §A10's shape.

**If the loader would require changing a frozen number to work, that is a discrepancy. Stop and
report it.** Nothing measured at Gate 1 suggests it will.

---

## A1. Established at Gate 1 — measured on this machine, 2026-09-04

Do not re-derive these. Do re-check any of them that a failure implicates.

### A1.1 The archive

`/glade/campaign/collections/rda/data/d633000/e5.oper.an.pl/{YYYYMM}/`

| Property | Measured value |
|---|---|
| **Granularity** | **One file per day.** `e5.oper.an.pl.128_131_u.ll025uv.{YYYYMMDD}00_{YYYYMMDD}23.nc`, ≈ 1.6 GB each. HANDOFF §4 guessed two half-month files; it is neither that nor one-per-month |
| Dims | `time = 24` (UNLIMITED, hours 00…23 all present), `level = 37`, `latitude = 721`, `longitude = 1440` |
| Wind variable | **`U`** (uppercase), `float32`, `units = "m s**-1"`, `_FillValue = missing_value = 9.999e+20`, `number_of_significant_digits = 7` |
| Second data variable | **`utc_date(time)`** shares the file. Two data variables, and `u` lowercase is absent — a raw archive file therefore **cannot** be handed to `open_normalized`, whose `_resolve_wind` would reject it. The loader's output carries one variable named `u` |
| Level coordinate | **`level`**, `float64`, **`units = "hPa"`** (not Pa), 37 values, `250.0` present **exactly**, at index 16 |
| Latitude | `latitude`, `float64`, **descending 90 → −90**, `units = "degrees_north"` |
| Longitude | `longitude`, `float64`, **0 … 359.75 ascending**, `units = "degrees_east"` — the wrap HANDOFF §4 anticipated is required |
| Time | `time`, `int`, `hours since 1900-01-01 00:00:00`, `calendar = gregorian`; decodes to `datetime64[ns]` |
| **Chunking** | **`(1, 37, 721, 1440)`**, `shuffle`, `deflate level 1`. One chunk = one timestep × **all 37 levels** = 154 MB uncompressed, ≈ 67 MB on disk. **The level axis is inside the chunk**, so extracting a single level costs a full-chunk decompress. This, and nothing else, is the cost model |
| Uniformity | Headers for 1979-05-01, 2018-05-01 and 2025 are identical. No era split, no format change |

Every coordinate name, every unit string, and the level value are already exactly what
`profile.open_normalized` accepts. **No frozen number has to move.**

### A1.2 Coverage, and the last complete season

A full inventory of MJJAS 1979–2026 was walked by name:

- **1979–2025: all 7 191 daily `128_131_u` files present. Zero gaps, zero short months.**
- The archive extends to `202606`. MJJAS 2026 has May and June only.
- **The last complete MJJAS in the archive is 2025**, which is exactly `year_last: 2025`.
  47 seasons × 153 days = 7 191. Ruling R3 needs no revision. **Report this figure in the write-up.**

### A1.3 Timing — measured, job `7317125`, `main`, `dec1933`, `1:ncpus=8:mem=64gb`, exit 0

| Measurement | Value |
|---|---|
| Serial, per day (compute node) | **4.69 s** |
| Serial, per season | 12.0 min |
| **Serial × 47** | **9.37 h** |
| **8-way process-parallel, one full season (MJJAS 2018, 153 days)** | **65.8 s** |
| **8-way × 47** | **0.86 h ≈ 52 min** (speed-up 10.9×) |
| Peak memory | **2.49 GB** of the 64 GB requested |
| `/glade/campaign` visible from a `main` compute node | **Yes** — verified in-job, not assumed |

**This decides §A10: one job, not a chain.** Serial does not fit 12 h with defensible margin
(9.37 h against a hard 12 h ceiling, on a shared filesystem whose read rate is not under our
control). Eight-way parallel finishes the loader stage in under an hour, ~14× inside the ceiling.
Per-season resume is still built (§A6) — the authorization is "resubmit the same shape until
complete", and a design that only works if nothing goes wrong is not idempotent.

### A1.4 Compute account — HANDOFF §7's caveat applies, and bites

`groups` returns `ncar uric0009 uchi0014 uchi0018`.

**`URIC0009` — the account `butterfly` uses — is EXPIRED.** `qsub` refuses it at submit time:
`qsub: Account is in state: Expired`. Had this addendum copied `butterfly`'s account, the campaign
would have failed at submission. §7 was right to flag it.

**Operator ruling, 2026-09-04: the account is `UCHI0014`.** It is Normal/Active, it is the account
behind every PBS script in the operator's other NCAR work, and the Gate-1 probe ran clean under it.

### A1.5 Environment — no gap, nothing to ask for

`/glade/work/zhil/conda_envs/aires/bin/python`, Python 3.11.11: xarray 2025.1.2, netCDF4 1.7.2,
numpy 2.2.4, scipy 1.15.2, matplotlib 3.10.0, pandas 2.2.3, pyyaml 6.0.2, pytest 9.0.2, `cdsapi`
importable. **All 63 existing tests pass on Derecho under this interpreter.**

Versions differ from Stampede3's (xarray 2026.7.0, numpy 2.4.3, scipy 1.17.1). Plan §8 R9 already
names env drift as a risk and answers it: the version table is recorded in the intermediate's
`package_versions` attribute, so drift is detectable rather than silent. Nothing is pip-installed;
no env is rebuilt. `scipy.signal.find_peaks`' documented default behaviour (plan §2 I3) is stable
across 1.15 and 1.17; the 63 green tests include the I3 cases.

### A1.6 Two documents HANDOFF cites that do not exist here

- **`~/projects/CLAUDE.md`** — the "machine rules" file HANDOFF §0/§5.3/§7 defers to repeatedly —
  **does not exist on Derecho** (there is no `~/projects`; the checkout root is `~/project`). Its
  decide-yourself / escalate boundary is reproduced in §A15 so nothing depends on a missing file.
- **`references/plan-template.md`** — see the note under the title.

Neither is a blocker. Both are recorded so the next reader does not hunt for them.

### A1.7 One measurement Gate 1 got for free, and its consequence

The timing probe's byproduct is the RDA-built MJJAS-2018 daily-mean field. Reduced to the zonal-mean
profile and compared against the committed CDS-built `results/smoke_2018/smoke_2018_profile.nc`:

```
max |diff| = 1.907e-04 m/s     mean |diff| = 2.92e-05 m/s     over 33 813 points (153 x 221)
```

That is **250× inside** the operator's 0.05 m/s allowance. Two things follow.

1. **The magnitude is explained, not merely small.** The CDS operands are `int16`-packed: the 2018
   R1 evidence pair is 91.8 MB for 612 × 221 × 361 = 48.8 M points (1.88 bytes/point) and 29.5 MB
   for 12.2 M points. A ±100 m/s int16 range quantizes at ≈ 0.003 m/s, i.e. ±0.0015 m/s per point,
   which after averaging 4 hours and 361 longitudes lands at ≈ 4e-5 — the observed mean difference.
   The RDA archive is **unpacked float32**. **A bit-exact profile match is therefore impossible and
   must not be pursued.** The operator's 0.05 m/s allowance is the correct instrument and the
   correct reading of it: the discrepancy is CDS's packing, not the loader's arithmetic.
2. **It is not the executor's measurement.** The probe accumulated in float64 outside the pipeline.
   §A9 re-measures through the real code path and reports the real number.

---

## A2. Operator decisions carried into this addendum (2026-09-04)

These are settled. Do not reopen them; do not raise them as questions.

| # | Decision | Effect |
|---|---|---|
| **O1** | **The source key goes into `profile_sha256`.** A CDS-built and an RDA-built intermediate must never be silently interchangeable | §A4, §A7 |
| **O2** | **The 81.4 % core-latitude result stays under R2** — reported, never gated. **No threshold moves in response to it.** Report the same statistic over all 47 seasons in the campaign summary; the operator rules once the full-period number exists | §A12, §A14 |
| **O3** | **2018 regression tolerance.** State labels and core latitudes in `smoke_2018_jet_states.csv` must match the baseline **exactly**; the summary block must match **exactly**; profile values may differ by at most **0.05 m/s max-abs**, and the actual max-abs diff is reported. Anything outside this: **stop and show the operator the diff.** Do not change the loader, the seam, or a threshold to make it match | §A9 |
| **O4** | **Account is `UCHI0014`** (§A1.4) | §A10 |
| **O5** | **Gate timing is unchanged** (HANDOFF §9.1): a double-jet-fraction gate failure lets the run finish, figure included, and *then* exits 1. A gate failure hands the operator a figure to look at | unchanged |
| **O6** | **`request_template` keeps being rebuilt from config** (HANDOFF §9.3), not read from the on-disk sidecar | §A7 |

---

## A3. Interpretations this addendum fixes

Small, and stated so the executor does not re-decide them. None changes a threshold.

| # | Item | Ruling of this addendum |
|---|---|---|
| **J1** | Which four fields make the daily mean | **Selected by timestamp, never by index.** `isel(time=[0,6,12,18])` is forbidden even though every file inspected has 24 ordered hourly steps. Match `cfg.hourly_times` against the decoded hour-of-day; assert exactly four hits; a day that does not carry all four is a hard error naming the date. Index selection would silently become a different statistic on any file whose time axis is not what we saw |
| **J2** | Accumulation precision of the four-sample mean | Accumulate in **float64**, store **float32**. This is still exactly "the unweighted mean of the 00, 06, 12, 18 UTC analyses" — the frozen definition — and the float32-vs-float64 accumulation of four values differs by ≤ 1 ulp, three orders of magnitude below the packing floor of §A1.7. Chosen because the source is unpacked and there is no reason to discard precision |
| **J3** | Storage dtype of the per-season file | **float32, zlib complevel 4**, mirroring the intermediate's encoding. Deliberately **not** int16-packed: we have the precision, and re-packing would reintroduce exactly the error §A1.7 identifies in the CDS path |
| **J4** | How the sector is cut | **Assert, then adopt.** Wrap the file's longitudes to [−180, 180), select the sector, sort ascending, assert the whole array equals `cfg.sector.longitudes()` to 1e-6 (and likewise latitude ascending against `cfg.sector.latitudes()`), then **replace the coordinate with the config's own values**. This is precisely what `open_normalized` step 6 does, applied one stage earlier, so no two seasons can differ in a last float bit and misalign on `concat` |
| **J5** | Latitude order written | **Ascending, 20 → 75.** The archive is descending. `open_normalized` would `sortby` either way; writing ascending makes the file and the intermediate agree by inspection |
| **J6** | The level coordinate written | A **scalar** coord named `level`, value `250.0`, `units = "hPa"`, copied from the source. `_resolve_name` finds it in `ds.variables`; it is not a dim, so no squeeze; the seam drops it. `_check_shape`'s `_DIM_CANDIDATES` covers only time/lat/lon, so a scalar level cannot be mistaken for a wrong shape |
| **J7** | Units written | **Copied from the source file and asserted against the accepted sets, never synthesized.** All four the seam demands are present upstream (`m s**-1`, `degrees_north`, `degrees_east`, `hPa`). "Units are read, not assumed" holds across the new boundary too |
| **J8** | The `download` stage name | **Unchanged.** The CLI's `--stage download,profile,classify,figure` and `test_cli.py`'s pins stay as they are; the stage now reads "**materialize the per-season raw cache**", by CDS or by RDA according to `cfg.source`. Renaming a documented flag to describe an internal change would break the entry point for no scientific gain |

---

## A4. Configuration

### A4.1 Where the new keys go, and why not a second file

HANDOFF §5.3 suggests "a Derecho block in `configs/` rather than editing the frozen numbers". Taken
literally as a **second config file**, that would duplicate every frozen number in the contract and
create exactly the drift `CLAUDE.md` forbids ("Frozen numbers — all live in
`configs/double_jet.yaml`, nowhere else"). §5.3 also states in the same breath that file layout is
the executor's to decide.

**Therefore: extend `configs/double_jet.yaml` additively. Change no existing value.** The frozen
numbers keep exactly one home. This is a deliberate, recorded departure from §5.3's *suggested
shape*, not from its intent.

```yaml
# --- which stage-1 source supplies the daily mean (deviation D3) --------------
source: rda_hourly        # rda_hourly | cds_derived. cds_derived keeps download.py live.

# --- the RDA archive on /glade (Derecho). Verified at Gate 1, 2026-09-04. ----
rda:
  root: /glade/campaign/collections/rda/data/d633000/e5.oper.an.pl
  file_template: "e5.oper.an.pl.128_131_u.ll025uv.{ymd}00_{ymd}23.nc"
  dataset_id: ds633.0          # for the intermediate's source_dataset attribute
  workers: 8                   # overridden by $PBS_NCPUS when set; see A10
```

Nothing here is a scientific threshold; all of it is machine addressing. The archive root and file
template live in config rather than in code so that a repointed archive is a config edit with a
hash consequence (§A4.3), not a code edit.

### A4.2 `config.py` changes

- `Config.source: str`, validated against `{"rda_hourly", "cds_derived"}` at load, with a clear
  failure naming both.
- A frozen `Rda` dataclass (`root: Path`, `file_template: str`, `dataset_id: str`, `workers: int`)
  and `Config.rda: Rda`.
- `load_config` **defaults `source` to `cds_derived`** and `rda` to a `None`-safe default when the
  keys are absent, so every existing test config still loads and no test that omits the key changes
  behaviour. (The one fixture that *copies the shipped YAML* is handled in §A4.3 and §A8.)
- `Config.active_dataset` property → `cfg.dataset` when CDS, `cfg.rda.dataset_id` when RDA.
- **`load_config` must not touch the filesystem while parsing the `rda` block.** It validates the
  block's *shape* (keys present, types right, `source` in the allowed set) and expands the root with
  the existing `_expand`, which deliberately only resolves `$VARS` and never stats
  (`config.py:223`). **Archive existence and readability belong to `preflight_archive` alone**
  (§A7.1). This is load-bearing, not tidiness: `tests/test_classify.py:68` and
  `tests/test_config.py:51` both call `load_config(CONFIG_PATH)` on the **shipped** YAML, so a
  filesystem check at load time would make the whole suite fail on any host without
  `/glade/campaign` mounted — including every off-machine run.

### A4.3 `profile_fields()` — O1, implemented

`profile_fields()` gains, in sorted-key order:

```python
"source": self.source,
"hourly_times": list(self.hourly_times),
# only when source == "rda_hourly":
"rda_root": str(self.rda.root),
"rda_file_template": self.rda.file_template,
```

**`hourly_times` is not decoration.** On the CDS path the daily mean was defined *inside* the
derived product and `frequency: 6_hourly` was an adequate proxy for it. **On the RDA path the
loader reads `cfg.hourly_times` directly** (§A5.2) — it *is* the definition of the statistic. Left
out of the hash, an authorized future change to the hour set would alter every value of `U(φ, t)`
while leaving `profile_sha256` identical, and `classify.py`'s guard would then accept a stale
intermediate on a `--stage classify` re-run. It goes in.

Consequences, all intended:

- `profile_sha256` now separates a CDS-built from an RDA-built intermediate — **O1**.
- It also separates two RDA builds that read **different archive roots**. A repointed archive is a
  different provenance and must not be silently reusable.
- Detection thresholds stay **excluded** (plan §4.3). A threshold-only re-run remains free. This is
  the property `test_config.py:232` pins and it must keep passing.
- `config_sha256` changes because the file changed. That is provenance working.

**What this does and does not break in the existing tests.** `test_config.py` pins **no literal
hash** — only the relative properties (threshold ⇒ same `profile_sha256`; sector ⇒ different), and
both survive: neither `source` nor `hourly_times` is a detection threshold. Two constraints the
executor must respect, both verified against the code:

- `test_config.py`'s `_variant` helper asserts its anchor string occurs **exactly once** in the
  shipped YAML (`u_core_min: 15.0`, `lon_min: -60.0`). **The new keys must not duplicate either
  anchor.** §A4.1's block does not.
- `test_profile.py:54`'s `make_cfg` builds every fixture by copying **the shipped
  `configs/double_jet.yaml`**. Once that file says `source: rda_hourly`, those CDS-path fixtures
  would follow the RDA dispatch — asserting `source_dataset == cfg.dataset` against
  `cfg.active_dataset`, expecting a CDS-shaped `request_template["pressure_level"] == ["250"]`, and
  worst of all making a synthetic unit test stat 153 real archive files (and fail off-machine).
  **This is the one existing-test edit this addendum authorizes** (§A8).

**One thing the executor must not do:** the committed `results/smoke_2018/smoke_2018_profile.nc`
carries the *old* `profile_sha256` (`f890aa7b…`). It is a **numeric comparison operand only**
(§A9). Never feed it to `classify.py`; the hash comparison would fail, correctly, and it would mean
nothing.

---

## A5. `double_jet/rda.py` — the loader

New module. It mirrors `download.py`'s **pair** of stage entry points — one that writes and one
that only validates — so `source.py` can dispatch each to its counterpart (§A7.1). `download.py`
and its tests are **not touched**.

### A5.1 Public surface

```python
season_source_files(cfg, year)   -> list[Path]    # the 153 daily archive files, date-ordered
build_rda_request(cfg, year)     -> dict          # the sidecar payload (A6)
season_is_complete(cfg, year)    -> (bool, str)   # the RDA identity check (A6)
write_season(cfg, year, log)     -> Path          # one season -> the seam's .nc + sidecar
ensure_local(cfg, years, smoke, log)   -> None    # MATERIALIZES; skips seasons already complete
validate_local(cfg, years, smoke, log) -> None    # VALIDATES ONLY; never writes (--skip-download)
preflight_archive(cfg, years, log)     -> None    # raises download.PreflightError (A7.1)
check_regression_2018(cfg, baseline_dir, out_paths, out_json, log) -> dict   # A9
```

### A5.2 What one season does

1. **Enumerate.** `season_source_files` builds the 153 paths from `cfg.season_months`,
   `cfg.year_first/last` arithmetic and `cfg.rda.file_template`. A missing path is a hard error
   **naming the date and the expected filename** — never a silently short season. (Gate 1 found no
   gaps 1979–2025; this exists so a future gap is loud.)
2. **Read each day, in a worker process** (`ProcessPoolExecutor`, `ex.map` so input order is
   preserved). The pool size is `int(os.environ["PBS_NCPUS"])` when that variable is set and
   `cfg.rda.workers` otherwise, so the job's requested shape and the parallelism can never
   disagree — and so a 1-cpu interactive session does not silently spawn 8 workers:
   - open, assert `time.size == 24` and that all four `cfg.hourly_times` are present exactly once
     (**J1**);
   - resolve the level by **value** against `cfg.pressure_level`, and read its `units` and assert
     `hPa` — a Pa-tagged coordinate must fail here, not 47 seasons later (**J6**, **J7**);
   - subset the sector by **assert-then-adopt** (**J4**), yielding `(4, 221, 361)`;
   - assert every value finite, **naming the date** on failure (the archive carries
     `_FillValue = 9.999e+20`, which xarray masks to NaN; a masked cell in our sector must stop the
     run, not average into a mean);
   - return the float64 four-sample mean as `(221, 361)` (**J2**), with its date.
3. **Assemble.** Stack in date order; assert the dates are exactly the season's 153 MJJAS days of
   that one year, ascending, no duplicates — the same conditions `_assert_time` will re-check.
4. **Write** `u(time, latitude, longitude)` float32/zlib-4 (**J3**), one data variable named `u`,
   with the scalar `level` coord and all four `units` attributes copied from the source (**J6**,
   **J7**), and `TIME_ENCODING` reused from `profile.py` so a rebuild is byte-reproducible.
   Suppress xarray's automatic `_FillValue` on `u` (`encoding={"u": {"_FillValue": None, ...}}`) —
   the field is proven finite and an invented fill value is noise in the provenance.
5. **Self-check at the seam — on the `.part`, before it is published.** Open `<stem>.part`
   through `profile.open_normalized(part_path, cfg)` (deferred import, the pattern
   `download.check_r1_equivalence` already uses) and let it throw. The loader's contract is
   "survives the seam", so a violation is reported against the season that caused it rather than
   against a `concat` 46 seasons later. Cost is ~0.2 s on a 30 MB file.

   **The order matters and is load-bearing.** `download._check_shape` — all that
   `season_is_complete` can apply to the bytes — validates *dimension sizes only*. It cannot see a
   wrong unit string, a drifted grid, a bad time axis, a second data variable, or a non-finite
   cell. If the self-check ran *after* `os.replace` and after the sidecar, a season that fails any
   of those would sit on disk looking **complete**, and the next run would skip it. Validating the
   `.part` means a failed season is never published at all.
6. **Land it atomically.** Only once step 5 passes: `os.replace` the `.part` onto
   `download.season_paths(cfg, year)["nc"]`, **then** write the sidecar. Never the reverse — a job
   killed between the two rebuilds the season next time, which is merely wasted work, whereas a
   sidecar written first could describe bytes that do not exist.

### A5.3 Paths — the seam's, not new ones

The output path is `download.season_paths(cfg, year)["nc"]` exactly as HANDOFF §5.1 specifies, and
the sidecar is that function's `["request"]`. `season_paths` stays in `download.py`: it is shared
addressing, the seam contract names it there, and moving it would be a structure change for no gain.
The `["zip"]` entry is meaningless on this path and is simply unused.

Consequence, and it is the right one: a CDS-built and an RDA-built season occupy the same path, and
the sidecar's `source` key makes them **refuse each other** (§A6). They are not interchangeable and
the cache says so.

---

## A6. The sidecar and idempotence

The three-part contract of plan §4.1 / HANDOFF §5.2 is preserved exactly: the `.nc` opens with the
expected shape **and** a `.request.json` exists **and** it equals the request that would be issued
now.

### A6.1 What `build_rda_request(cfg, year)` records

```json
{
  "source": "rda_hourly",
  "archive_root": "/glade/campaign/collections/rda/data/d633000/e5.oper.an.pl",
  "file_template": "e5.oper.an.pl.128_131_u.ll025uv.{ymd}00_{ymd}23.nc",
  "variable": "u_component_of_wind",
  "pressure_level": 250,
  "level_units": "hPa",
  "year": "2018",
  "month": ["05", "06", "07", "08", "09"],
  "hours": ["00:00", "06:00", "12:00", "18:00"],
  "daily_statistic": "daily_mean",
  "area": [75.0, -60.0, 20.0, 30.0],
  "resolution": 0.25,
  "n_source_files": 153,
  "source_files": [{"name": "...", "bytes": 1606316972, "mtime_ns": 1567...}, "... x153"]
}
```

- **The subset spec** (`pressure_level`, `area`, `resolution`, `hours`, `month`, `year`) is what
  makes a *sector* or *level* change refuse the cache.
- **`area` keeps `[N, W, S, E]` order**, reusing `download._canonical_request`'s rule: a permuted
  box is a different box and must mismatch.
- **The file inventory** (`name`, `bytes`, `mtime_ns` per file) is the "archive moved under you"
  detector HANDOFF §5.2 asks for. Size + mtime, not a content hash: hashing 153 × 1.6 GB per season
  is 245 GB of reads to validate a 30 MB output, which would cost more than rebuilding it.
- **`daily_statistic: daily_mean`** is recorded even though the loader computes it, so a sidecar
  read in isolation states which statistic the bytes are.

Sidecar size ≈ 14 KB (plan §6 estimated ≈ 1 KB for the CDS sidecar); 47 × 14 KB is immaterial.

### A6.2 Comparison, and why it is not just `_canonical_request`

`rda.season_is_complete` reuses `download._check_shape` (unchanged) and `download._canonical_request`
for the **spec** keys, then compares the **file inventory entry by entry** and reports the *first*
differing filename with its stored and current `(bytes, mtime_ns)`. `_canonical_request` alone would
stringify 153 dicts and truncate the mismatch message to 60 characters, which is a useless failure
for the one case the inventory exists to catch.

### A6.3 The properties this preserves — each of which gets a test (§A8)

| Property | Behaviour |
|---|---|
| Threshold-only change | Season stays **complete**; nothing is re-read; classification re-runs alone |
| Sector or level change | Season **refuses** the cache and rebuilds |
| Source change (CDS ↔ RDA) | Season **refuses** the cache — the `source` key differs |
| An archive file's size or mtime changed | Season **refuses** the cache, naming the file |
| Job killed mid-write | `.part` orphan only; the season reads as incomplete and rebuilds; no truncated file ever looks complete |
| A season that would fail the seam (bad units, drifted grid, bad time axis, non-finite cell) | **Never published.** Caught on the `.part` before `os.replace` (§A5.2 step 5), because `_check_shape` alone cannot see any of those |
| Resume after a wall clock kill | Completed seasons are skipped; only gaps are built |

**mtime caveat, recorded not worked around:** a filesystem migration that preserved content but
changed mtimes would force a needless rebuild. At 52 minutes for the whole campaign that is an
acceptable false positive, and it fails in the safe direction.

---

## A7. The dispatcher, and the four edits outside it

### A7.1 `double_jet/source.py` — new, small, the only place the choice lives

```python
request_for(cfg, year)                       # -> rda.build_rda_request  | download.build_request
season_is_complete(cfg, year)                # -> rda.season_is_complete | download.season_is_complete
materialize_seasons(cfg, years, smoke, log)  # -> rda.ensure_local       | download.run_download
validate_seasons(cfg, years, smoke, log)     # -> rda.validate_local     | download.ensure_downloaded
preflight(cfg, years, log)                   # -> rda.preflight_archive  | download.preflight_network
```

**`materialize_*` and `validate_*` are two functions, never one.** `download.run_download` mutates
the cache; `download.ensure_downloaded` only inspects it and raises listing every missing season.
That separation is exactly what `--skip-download` means, and collapsing the two behind one name
would let `--skip-download` *materialize* RDA seasons — the opposite of the flag. `rda.py` mirrors
the pair: `ensure_local` writes, `validate_local` reports and never writes.

**`preflight` takes the years** because there is no fixed season to probe: `--smoke` wants 2018 and
`--years` wants its own first season. It raises **`download.PreflightError`**, the type `cli.run`
already catches to return `EXIT_PREFLIGHT`, so the CLI's exception handling needs no edit.

Imports are deferred inside each function, the pattern `profile.build_intermediate` and
`download.check_r1_equivalence` already use, so no import cycle is created.

### A7.2 `profile.py` and `figure.py` — three provenance lines, and why they are not "touching the seam"

HANDOFF §5 freezes `open_normalized` **and everything downstream of it**. `build_intermediate` is
neither: it is the seam's consumer, and two of its provenance attributes are **factually false** on
the RDA path if left alone.

- `request_template` is currently `download.build_request(cfg, years[0])` — a CDS request that was
  never issued. Change to `source.request_for(cfg, years[0])`.
- `source_dataset` is currently `cfg.dataset` — likewise names a CDS dataset the bytes did not come
  from. Change to `cfg.active_dataset`.

A third line, in `figure.py`, is the same defect in the same class. The panel suptitle prints
`source: {cfg.dataset}` (`figure.py:252`), so **the 47-season figure — the wave's headline
deliverable — would be captioned as CDS-derived data it was not built from.** Change to
`cfg.active_dataset`.

Per **O6** the template is still *rebuilt from config*, not read off the sidecar; only which builder
runs changes. `open_normalized`, `_assert_time`, `season_profile` and every line of `classify.py`
are **not touched by a single character**, and nothing about *what is plotted* changes — plan §11
places figure styling that does not change the plotted content on the decide-in-session side, and a
provenance caption is not plotted content. Provenance that lies is worse than provenance that is
absent; these three lines are the minimum that keeps it honest, and they are named exhaustively
here so the reviewer can hold this addendum to that count.

**The count is exhaustive because the codebase was swept for the class, not just for the cited
line.** Outside `download.py` and `config.py`, `cfg.dataset` occurs in exactly two places —
`profile.py:391` and `figure.py:252` — and both are fixed above. `classify.py` reads no
source-specific attribute at all: its only provenance touch is the `profile_sha256` comparison
(`classify.py:341`–`348`), which §A4.3 makes *more* discriminating, not less. `cdsapi` appears
outside `download.py` only in `config.py:29`'s `PROVENANCE_DISTRIBUTIONS`, and
`package_versions()` already records a missing distribution as `"absent"` rather than raising —
verified by running it — so the RDA path needs no change there and records the fact truthfully.
The two `jobs/*.slurm` scripts import `cdsapi` in their prologues; they are Stampede3's and stay
untouched (repo `CLAUDE.md`). **There is no fourth site.**

### A7.3 `double_jet/cli.py` — four dispatches, and one of them **moves**

1. **Preflight.** `cli.run` currently calls `download_mod.preflight_network(log)` unconditionally
   whenever `download` is in the stages. **On Derecho this would abort the campaign at
   `EXIT_PREFLIGHT` before reading a single file**, since the RDA path uses no network and compute
   nodes need not reach CDS at all. Replace with `source.preflight(cfg, season_years, log)`. The
   RDA implementation asserts the archive root exists and is readable, and that the **first day of
   the first requested season** (2018 under `--smoke`, the range's first year under `--years`)
   opens and carries level 250 at `hPa` — the same "fail in seconds with a labelled message, before
   the expensive part" guarantee plan §5.0 wanted from the network preflight. It raises
   `download.PreflightError`, so `cli.run`'s `except` clause and `EXIT_PREFLIGHT` are unchanged.
   `--preflight-network` stays a CDS-only flag with its current behaviour.
2. **The stage body.** `download_mod.run_download(...)` → `source.materialize_seasons(...)`, and
   `--skip-download`'s `download_mod.ensure_downloaded(...)` → `source.validate_seasons(...)`.
   **Two calls, two names** (§A7.1) — the flag must never materialize anything.
3. **`--smoke`, and where the check runs.** `--smoke` currently calls `check_r1_equivalence`
   **inside the download block** (`cli.py:191`–`204`), which needs the CDS 6-hourly operand.
   **That operand does not and cannot exist on Derecho** (§A9.1), so on the RDA path `--smoke` runs
   the §A9 regression instead — the faithful analogue: R1 asked "is this the contract's daily
   mean?"; the regression asks the same question against the artifact that answered it. On the CDS
   path the R1 gate stays exactly where and what it is.

   **The RDA check cannot occupy the R1 check's position.** R1 compares two *raw* season files, so
   it can run inside the download block. The regression compares the **profile, the CSV and the
   summary** — none of which exist until `profile` and `classify` have run. Placed where R1 sits,
   a clean smoke run would fail on missing operands and a dirty one would silently compare **stale**
   files from a previous invocation. It therefore runs **after the `figure` stage, immediately
   before `run`'s final return**, where all three operands are on disk.

   Running it last also matches **O5**'s shape: the run finishes, the smoke figure is written, the
   regression result is reported, and only then does a failure set the exit code. A mismatch hands
   the operator a figure and a diff, not a bare traceback. A regression failure returns
   `EXIT_SANITY` (1), the same code a hard gate uses; if both the fraction gate and the regression
   fail, both are reported and the run exits 1 once.

   **It is gated on the stages that produce its operands, exactly as the R1 gate is.** R1 runs only
   when `"download" in args.stage`, because that is where *its* operands come from. `--stage`
   accepts arbitrary subsets (`cli.py:105`, pinned by `test_cli.py:72`), so an unconditional
   placement would make `--smoke --stage download` compare three files that do not exist, and
   `--smoke --stage figure` compare **stale** ones from an earlier invocation — the identical defect
   this item exists to fix, merely moved. The regression therefore runs only when **both `profile`
   and `classify` are in `args.stage`**, since those are the two stages that write its operands.
   When it is skipped, the run **logs that it was skipped and which stages were missing** — a
   silently absent gate is the failure mode that matters here, so it is never silent.
4. **`OutputNames` keeps exactly one evidence slot; it is renamed, not duplicated.**
   `r1_validation: Path | None` becomes `evidence: Path | None`, and for a smoke run it resolves
   **source-dependently**: `data/smoke_2018_r1_validation.json` on the CDS path (the legacy name,
   unchanged) and `data/smoke_2018_regression.json` on the RDA path. It stays `None` for the
   campaign and for every `--years` subset.

   **Adding a second field was the wrong answer and is withdrawn.** `test_config.py:167` asserts
   `len(campaign) == len(smoke) == len(subset) == 5`, so a smoke run carrying *both* an
   `r1_validation` and a `regression` path would make it six and break a test this addendum is not
   willing to weaken. That assertion is not incidental — it is how plan §8 R12 ("a smoke or
   `--years` rerun overwrites campaign outputs") is enforced, and it should stay exactly as strict
   as it is.

   One slot is also the truer model: a smoke run produces **one** source-equivalence evidence file,
   and which check wrote it is a property of the source, not an extra artifact. `all_paths()` keeps
   its existing `is not None` guard (`cli.py:41`), all three length assertions still hold, and
   `campaign.evidence is None` still holds.

   **This costs two enumerated lines in `tests/test_config.py`** — the second and last existing-test
   edit this addendum authorizes (§A8): `campaign.r1_validation is None` → `campaign.evidence is
   None`, and the pinned smoke filename becomes the source-aware one. Both are the test following
   its subject through an intended rename, not the test being bent around the loader.

   `--smoke`'s help text still promises "both CDS products, the R1 equivalence gate" (`cli.py:123`).
   Update it to state what the configured source actually does.

Nothing else in `cli.py` moves. `STAGES`, `parse_stages`, `output_names`, `parse_years` and the exit
codes are untouched, so `test_cli.py` stays green unedited.

---

## A8. Tests

`tests/test_rda.py`, a **new file**, carries everything in §A4–§A7.

**Exactly two existing-test edits are authorized. They are enumerated here and nowhere else.**

**(1) `tests/test_profile.py:54`, one line.** `make_cfg` builds every fixture in that file by
copying the shipped `configs/double_jet.yaml` (§A4.3). Those fixtures are **CDS-path tests** — they
construct CDS-shaped season files and assert a CDS-shaped request template — so once the shipped
YAML says `source: rda_hourly` they would silently follow the wrong dispatch and stat real archive
files. The edit is precisely:

```python
overrides.setdefault("source", "cds_derived")   # <-- the one added line
raw.update(overrides)                           # existing
```

`overrides`, **not** `raw`: `raw` already carries `source: rda_hourly` from the shipped file, so
`raw.setdefault` would do nothing at all. Setting the default on `overrides` pins the CDS path while
still letting an individual test ask for the RDA one.

**No assertion changes from this edit.** With the CDS path pinned, `source_dataset == cfg.dataset`
still holds (`active_dataset` *is* `dataset` there) and `request_template["pressure_level"] ==
["250"]` still holds.

**(2) `tests/test_config.py`, two lines.** The `r1_validation` → `evidence` rename of §A7.3 item 4:
`campaign.r1_validation is None` → `campaign.evidence is None`, and the pinned smoke filename
becomes the source-aware one. **No assertion is weakened** — in particular
`len(campaign) == len(smoke) == len(subset) == 5` and the pairwise-disjointness checks stay exactly
as they are, because they are how plan §8 R12 is enforced.

Both are tests following their subject through an intended, enumerated change — HANDOFF §5.3's
"genuinely wrong" exception — not tests bent around the loader.

**`test_classify.py` and `test_cli.py` are not touched, and here is the checked reason.**
`test_classify.py:68` *does* call `load_config(CONFIG_PATH)` on the shipped YAML, so it will read
`source: rda_hourly` — but it never reaches a source-dependent path: it calls no
`build_intermediate`, no `season_paths`, and no request builder, using `cfg` only for thresholds and
the sector axis (verified by grep over the file). It therefore stays green **provided `load_config`
does not stat the archive**, which §A4.2 requires. `test_cli.py` constructs no `Config` at all and
touches neither `output_names` nor the preflight (verified). `make_cfg` is the only fixture that
*copies and rewrites* the real YAML; `test_classify.py` and `test_config.py` load it directly, which
is why the two edits above are scoped the way they are.

Synthetic archive files are built in `tmp_path` on a **reduced global grid** driven by a test config
with a coarser resolution and a smaller sector, exactly so that the loader is proven to read its
grid from `cfg` and never to hardcode 721/1440/37. One integration test reads two *real* archive
days, `skipif` the archive is absent, so the suite stays runnable off-machine.

| # | Test | Pins |
|---|---|---|
| 1 | four fields selected by timestamp on a file whose hours are shuffled | **J1** — the isel trap |
| 2 | a day carrying 23 hours is rejected, naming the date | J1 |
| 3 | a day absent from the archive is rejected, naming the date and expected filename | A5.2 step 1 |
| 4 | level selected by value; a Pa-tagged level rejected | J6, J7 |
| 5 | a level set without 250 rejected | J6 |
| 6 | longitude wrap lands on `cfg.sector.longitudes()`, 361 points, meridian straddled | J4 |
| 7 | latitude written ascending and equal to `cfg.sector.latitudes()` | J4, J5 |
| 8 | units copied from source; a source in `K` or `Pa` rejected | J7 |
| 9 | a non-finite cell inside the sector rejected, naming the date | A5.2 step 2 |
| 10 | **the written season survives `profile.open_normalized` unmodified** | **the seam contract** |
| 11 | sidecar round-trip marks the season complete | A6 |
| 12 | a detection-threshold change leaves the season complete | A6.3 — the free re-run |
| 13 | a sector change refuses the cache | A6.3 |
| 14 | a `source` change (CDS ↔ RDA) refuses the cache | A6.3, O1 |
| 15 | a changed archive `mtime`/`bytes` refuses the cache, naming the file | A6.2 |
| 16 | an interrupted write leaves a `.part` and no complete-looking season | A6.3 |
| 17 | `validate_local` reports every missing season together, not just the first | mirrors `download.ensure_downloaded` |
| 18 | `profile_sha256` differs between a CDS and an RDA config, and between two RDA roots | **O1** |
| 19 | `build_intermediate` records the **RDA** request template and `source_dataset` | A7.2 |
| 20 | `validate_local` never writes: pointed at an empty cache it raises and creates nothing | A7.1 — the `--skip-download` guarantee |
| 21 | a season whose `.part` fails the seam (bad unit string) is **not published**: no `.nc`, no sidecar, and the next run rebuilds | **A5.2 step 5** — the failure `_check_shape` cannot see |
| 22 | `check_regression_2018` passes on identical operands and fails on each of the three comparisons independently (a flipped state; an altered summary line; a profile offset by 0.06 m/s) | **A9.2**, all three arms |
| 23 | `check_regression_2018` refuses **misaligned** operands rather than comparing an intersection | **A9.2** — the `join="exact"` trap |
| 24 | `output_names(..., smoke=True).evidence` resolves source-dependently, stays disjoint from `CONTRACT_NAMES`, and keeps all three `all_paths()` lengths at 5; the campaign's is `None` | A7.3 item 4, plan §8 R12 |
| 25 | `--smoke --stage download` and `--smoke --stage figure` do **not** run the regression, and say so in the log | **A7.3 item 3** — the stale/missing-operand trap |

**Acceptance: `pytest tests/ -q` green — the 63 pre-existing tests plus `tests/test_rda.py`, with
exactly the two edits enumerated above (one line in `test_profile.py`, two in `test_config.py`),
no assertion weakened, and no test deleted or skipped.**

---

## A9. The 2018 regression check — the gate between the loader and the campaign

**Nothing runs at 47-season scale until this passes.** This is HANDOFF §5.4's cross-check, re-aimed
at the only baseline reachable from this machine.

### A9.1 The operand, and why it is not §5.4's

HANDOFF §5.4 names `/work2/11114/zhixingliu/double-jet-natl/era5_r1_evidence/`. **`/work2` does not
exist on Derecho** — it is Stampede3's filesystem, and this session had no route to that machine.
So §5.4's stated fallback applies.

The fallback is **stronger than §5.4 anticipated**, and the executor should know why. §5.4 expected
to fall back to comparing classifications only. But `results/smoke_2018/smoke_2018_profile.nc` is
committed and is a **full numeric operand**: `U(time=153, latitude=221)` float32, the CDS-built
intermediate itself. So the check is numeric *and* categorical, not categorical alone.

### A9.2 The three comparisons, and the stop rule

Build MJJAS 2018 from RDA through the real pipeline
(`python -m double_jet --config configs/double_jet.yaml --smoke`), then compare:

| # | Comparison | Requirement (**O3**) |
|---|---|---|
| **1** | `data/smoke_2018_jet_states.csv` vs `results/smoke_2018/smoke_2018_jet_states.csv` | **State labels and core latitudes match exactly**, all 153 rows |
| **2** | `data/smoke_2018_summary.txt` vs `results/smoke_2018/smoke_2018_summary.txt` | **Exact match** of the summary block |
| **3** | `data/smoke_2018_profile.nc` `U` vs `results/smoke_2018/smoke_2018_profile.nc` `U` | **max-abs diff ≤ 0.05 m/s**, and **the actual value is reported** |

**Comparison 3 aligns exactly, and counts.** Both operands are opened with
`profile.open_intermediate` and aligned with `xr.align(..., join="exact")` before anything is
subtracted, then the compared-point count is asserted to be **33 813** (= 153 days × 221 latitudes).
This is not ceremony: `check_r1_equivalence` (`download.py:462`) documents exactly why a bare
`a - b` is unsafe — xarray defaults `arithmetic_join` to `"inner"`, so mismatched coordinates would
silently compare only the overlap and **pass a gate they never tested**. A regression check that can
pass on 200 of 33 813 points is worse than none. Comparisons 1 and 2 likewise align on the `date`
column and on line count before comparing, so a short CSV fails rather than matching on its prefix.

Written to the smoke run's single evidence path — `data/smoke_2018_regression.json` on the RDA
path (§A7.3 item 4) — in `check_r1_equivalence`'s style (achieved value,
count compared, expected count, tolerance, both operand paths, per-comparison pass flags) so the
evidence is a file, not a log line.

**Expected outcome, from §A1.7:** comparison 3 lands near **1.9e-4 m/s**. Report the number
achieved, not the number expected.

**On any failure: STOP and show the operator the diff.** Do not change the loader, the seam, or a
threshold to make it match — **O3**, and plan §11's escalation boundary. For comparison 1 that means
the offending dates with both state labels and both core latitudes; for 3, the max-abs value, its
day and latitude, and the distribution.

### A9.3 The one honest risk, named in advance

Comparison 3's tolerance is 0.05 m/s but comparisons 1 and 2 demand **exact** agreement, and the
profile difference is not zero (§A1.7 — CDS's int16 packing makes zero unreachable). A ~2e-4 m/s
perturbation could in principle flip a day whose decision sits within 2e-4 of `u_core_min`
(15 m/s), of the 5 m/s prominence, or of the 10° separation, or move a `find_peaks` core by one
0.25° grid row on a near-flat maximum. The probability is low — the smoke season's core winds sit at
23–35 m/s, far from 15 — but it is **not zero, and it is not a bug if it happens.**

If it happens, it is a finding for the operator with a precise diagnosis, not a tolerance to be
loosened by the executor. Report: which day, which rule was marginal, the two values either side of
it, and the margin. **O3's stop rule applies unchanged.**

---

## A10. The campaign on Derecho

### A10.1 One job, not a chain — and why

§A1.3 measures the loader stage at **0.86 h** for all 47 seasons at 8-way parallelism. Adding
`profile` (47 reads of ~30 MB), `classify` (7 191 days of 1-D peak finding) and `figure` (47 panels)
against the Stampede3 smoke's whole-pipeline 1 min 15 s for one season puts the **end-to-end
campaign near 1.5 h, against a 12 h ceiling — ~8× margin.**

**Therefore: a single submission of the pre-authorized shape, running all stages.** A chain would
add resume machinery and inter-job latency to a job that finishes in an eighth of its own walltime.

The serial fallback is recorded because it is the number that decides this: at 4.69 s/day the same
work is **9.37 h**, which does *not* fit 12 h with defensible margin on a shared filesystem. **If
the parallel path is ever disabled, the campaign no longer fits in one job.** That is the tripwire.

### A10.2 `jobs/derecho/campaign.pbs`

Per repo `CLAUDE.md`, Derecho/PBS scripts live in `jobs/derecho/`; the top-level `*.slurm` files are
Stampede3's and stay.

```bash
#PBS -N djet_campaign
#PBS -A UCHI0014
#PBS -q main
#PBS -l select=1:ncpus=8:mem=64gb
#PBS -l walltime=12:00:00
#PBS -j oe
#PBS -o logs/campaign.out
```

Exactly HANDOFF §7's pre-authorized shape and **not one unit larger**. Measured headroom:
2.49 GB of 64 GB, ~1.5 h of 12 h.

Prologue, mirroring plan §5.0's contract:

- `set -euo pipefail`
- **assert `$PBS_JOBID` is set** — never the driver bare on a login node
- `cd` to the checkout, `module purge` as appropriate, activate
  `/glade/work/zhil/conda_envs/aires`
- `python -c 'import xarray, netCDF4, scipy, matplotlib, yaml'` — the env is what we think it is
- `python -m double_jet --help` — M9, the entry point runs from a clean shell (§A1.5 note: `cdsapi`
  is **not** imported on this path and must not be required)
- **No worker-count export.** `$PBS_NCPUS` is set by PBS itself and the loader reads it directly
  (§A5.2 step 2); a shell variable of our own would be a second, divergent source of truth

Body:

```bash
python -m double_jet --config configs/double_jet.yaml
```

**`logs/` must exist at submit time** — PBS opens `-o` before the job body runs, so a prologue
`mkdir` is too late. This is the same lesson `jobs/smoke_2018.slurm` records for Slurm; it is not a
new one and it must not be re-learned.

### A10.3 Surviving a 12 h wall mid-season

Required by the brief even though §A10.1 makes it unlikely to be exercised:

- Per-season outputs, written atomically, sidecar-checked on resume (§A5.2 step 5, §A6.3).
- `ensure_local` skips complete seasons and reports the count skipped, so a resubmission of the same
  shape completes only the gaps. **This is what the pre-authorization's "resubmit until complete"
  clause rests on.**
- The worst case is one season's ≈ 66 s of work lost, plus a `.part` orphan that the next run
  ignores and overwrites.
- A season killed **between** the `.nc` and its sidecar reads as incomplete and rebuilds — correct,
  and merely wasteful (§A5.2 step 5).

### A10.4 Budget

One campaign submission of the pre-authorized shape. Up to **five** smoke-scale submissions
(2018 only) remain available for getting the loader green, per HANDOFF §7 — the Gate-1 timing probe
(job `7317125`, 2 min, read-only characterization, no pipeline code) is **not** one of them. If all
five smoke submissions are spent without a clean end-to-end pass, **stop and report**.

**Anything larger than §A10.2's shape — more nodes, longer walltime, a different queue, a GPU
queue — is an escalation, however small the increase.**

---

## A11. Where every byte lands on Derecho

Plan §6's table is Stampede3's. HANDOFF §11 leaves Derecho storage to this addendum. The rule is
unchanged: **raw ERA5 never under `$HOME` or `$WORK`.**

| Path | FS | Size | Written by |
|---|---|---|---|
| `$SCRATCH/double-jet-natl/era5_raw/u250_natl_mjjas_<year>.nc` × 47 | `/glade/derecho/scratch/zhil` | ≈ 30 MB ea (**≈ 1.4 GB total**) | §A5 |
| `$SCRATCH/double-jet-natl/era5_raw/u250_natl_mjjas_<year>.request.json` × 47 | scratch | ≈ 14 KB ea | §A6 |
| `data/`, `figs/`, `logs/` | `/glade/u/home/zhil` | < 30 MB total | plan §4.2–§4.5 |

`$SCRATCH` resolves to `/glade/derecho/scratch/zhil` (set in the environment; `Paths._expand` errors
on an unset variable, so a missing `$SCRATCH` fails loudly at config load rather than writing to a
literal `$SCRATCH` directory). Measured headroom: scratch **9.95 of 30 TiB** used, `$HOME` **62.1 of
100 GiB**. Both are ample; the campaign adds ≈ 1.4 GB and ≈ 30 MB respectively.

**No ZIPs on this path** — plan §6's ZIP row does not apply. The `$SCRATCH` tree remains a
purgeable cache: after a purge every deliverable still regenerates from `data/`, and the raw cache
itself regenerates in ≈ 52 min from an archive that has no queue. **Nothing is copied to `/glade/campaign`
for durability** — unlike Stampede3's R1 evidence pair, this cache is cheaply reproducible from a
permanent local archive, which is the whole point of D3.

---

## A12. Deliverables

HANDOFF §8's five, unchanged in content. Recorded here only where this machine changes a path or
this addendum adds a requirement.

| # | Deliverable | Note |
|---|---|---|
| 1 | `data/u250_natl_mjjas_1979-2025.nc` | provenance now carries `source: rda_hourly`, the RDA root, and the RDA request template (§A4.3, §A7.2) |
| 2 | `data/jet_states_mjjas_1979-2025.csv` | 7 191 rows |
| 3 | `data/jet_states_summary.txt` | double-jet fraction (hard gate, 5–90 %) **and** the core-latitude diagnostic over all 47 seasons (**reported, never gated** — O2) |
| 4 | `figs/double_jet_natl_panels.{pdf,png}` | `rasterized=True` retained — 1.79 MB vs ~24 MB |
| 5 | `docs/results/2026-09-XX_wave1_results.md` | see below |
| 6 | `data/smoke_2018_regression.json` | §A9 — the smoke run's single evidence file on the RDA path (§A7.3 item 4); the CDS path still writes `smoke_2018_r1_validation.json` to the same slot |
| 7 | `docs/rda_archive_notes.md` **or** a D4 entry in `docs/deviations.md` | **required by HANDOFF §4**: §A1.1–§A1.3's findings, so the next person does not rediscover the chunk layout |

The write-up (5) covers, per HANDOFF §8: the double-jet fraction over 1979–2025 and how it varies by
season and across the record; **the core-latitude diagnostic over all 47 seasons set against the
smoke season's 81.4 %** (O2 — reported for the operator's ruling, with no threshold moved and no
recommendation to move one); the regression result from §A9; the last complete MJJAS found in the
archive (§A1.2); and anything the data did that the plan did not predict. **Interpretation, not just
artifacts.**

Exit codes are preserved: `0` OK, `1` a hard sanity gate failed, `2` preflight failed, `3` crash.
Gate timing is **O5** — unchanged.

**Out of scope, explicitly:** no trend analysis, no persistence analysis, no heatwave linkage. The
write-up reports what the contract defines.

---

## A13. Risks

Plan §8's R1–R13 stand where they still apply (R3, R5, R10 are CDS-path-only and are now moot for
the campaign). New and changed:

| # | Risk | Response |
|---|---|---|
| **DR1** | A marginal 2018 day flips state or core latitude on a ~2e-4 m/s profile difference, failing O3's exact-match requirement | §A9.3. Named in advance with a precise diagnosis required. **Report, do not retune.** Low probability: smoke cores sit at 23–35 m/s against a 15 m/s threshold |
| **DR2** | `cli.run`'s unconditional `preflight_network` aborts the campaign at `EXIT_PREFLIGHT` before reading a file | §A7.3 item 1. **Found at Gate 1, fixed by dispatch.** Would have been a guaranteed campaign failure |
| **DR3** | `--smoke` calls `check_r1_equivalence`, whose CDS operand cannot exist on Derecho | §A7.3 item 3, §A9.1 |
| **DR4** | Hour selection by index silently becomes a different statistic | **J1** — forbidden, and test 1 pins it |
| **DR5** | A raw archive file is handed to `open_normalized` and rejected for having two data variables (`U`, `utc_date`) | §A1.1. The loader emits one variable named `u`; test 10 pins the seam contract |
| **DR6** | The archive is repointed or re-published; stale seasons silently reused | §A4.3 puts `rda_root` in `profile_sha256`; §A6 puts size+mtime in the sidecar |
| **DR7** | `/glade/campaign` unavailable from a compute node | **Retired.** Verified in-job at Gate 1 (§A1.3) |
| **DR8** | The campaign does not fit 12 h | **Retired for the parallel path** (0.86 h measured). **Live if parallelism is disabled** (9.37 h serial) — §A10.1's tripwire |
| **DR9** | Env drift between Stampede3 and `aires` changes a result | §A1.5: 63/63 green here; `package_versions` recorded in the intermediate (plan §8 R9) |
| **DR10** | A filesystem migration changes mtimes without changing content, forcing a needless rebuild | §A6.3. Accepted: ≈ 52 min, and it fails in the safe direction |
| **DR11** | The expired `URIC0009` is copied from `butterfly` into a job script | §A1.4, **O4**. The campaign script names `UCHI0014` |
| **DR12** | The regression check compares operands that do not yet exist — or, worse, **stale ones from a previous run** | §A7.3 item 3. It runs after `figure`, **and only when `profile` and `classify` both ran**; §A9.2 asserts the compared-point count; a skip is logged, never silent |
| **DR17** | A second evidence field pushes a smoke run to six output paths and breaks the R12 disjointness test | §A7.3 item 4. One renamed, source-aware slot; all three `all_paths()` lengths stay 5 |
| **DR13** | A season that fails the seam is published anyway, because `_check_shape` validates dimension sizes only, and the next run skips it as complete | §A5.2 step 5. The seam check runs on the `.part`, before `os.replace` and before the sidecar |
| **DR14** | `--skip-download` materializes seasons, because one dispatcher name covered both meanings | §A7.1. `materialize_seasons` and `validate_seasons` are separate functions with separate `rda.py` implementations |
| **DR15** | A future authorized change to `hourly_times` alters every value of `U(φ, t)` without changing `profile_sha256`, and a `--stage classify` re-run accepts a stale intermediate | §A4.3. `hourly_times` is in `profile_fields()` |
| **DR16** | The headline 47-season figure is captioned with the CDS dataset it was not built from | §A7.2. `figure.py:252` uses `cfg.active_dataset` |

---

## A14. Execution order

The brief's order, with this addendum's acceptance criteria attached. **Each step gates the next.**

1. **Config + loader + dispatcher + the three named edits** (§A4, §A5, §A6, §A7).
   `pytest tests/ -q` green: the 63 pre-existing tests plus `tests/test_rda.py`, with exactly the
   two enumerated existing-test edits of §A8 and no assertion weakened (§A8).
   Behaviour commit.
2. **2018 rebuild from the archive → the §A9 regression check.**
   `python -m double_jet --config configs/double_jet.yaml --smoke`.
   **All three comparisons must pass. On any failure: STOP and show the operator the diff** (O3).
   Do not proceed to step 3 on a partial pass.
3. **The campaign** (§A10): `qsub jobs/derecho/campaign.pbs`, 1979 → **2025** (§A1.2 — and report
   the last complete MJJAS found, which is that same 2025).
4. **Figure and write-up** per `wave1-plan.md` §4.5 and HANDOFF §8. The full-period sanity
   statistics are **reported, not gated** (O2).
5. **Commit and push.** Behaviour-changing and structure-only commits kept separate, as always.
   The archive notes of §A12 item 7 are part of this.

---

## A15. Decision boundary on this machine

Reproduced here because `~/projects/CLAUDE.md` does not exist on Derecho (§A1.6).

**Escalate — operator only:** every threshold in `configs/double_jet.yaml`; the year range; the
sector; the level; the daily-mean definition; which sanity checks gate versus report; the source of
the data; any environment, dependency or module change; any submission larger than §A10.2's shape;
**and any failure of §A9**.

**Decide in-session:** file layout, function decomposition, naming, logging, error handling,
parallelization mechanics, test structure, PBS script details within the authorized shape, figure
styling that does not change what is plotted.

**Carried escalations from plan §10:** E2 (the double-jet fraction gate fires), **E3 (the
core-latitude fraction over the full archive — O2 rules that the operator judges it once the
47-season number exists, and the executor neither moves a band nor recommends moving one)**, E6
(mirroring `data/` for durability — not planned; §A11 explains why it is unnecessary here).
