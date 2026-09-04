# The NCAR RDA ERA5 archive on Derecho — measured notes

**Date:** 2026-09-04 · **Machine:** NCAR Derecho · **Author:** the Derecho executor session

Every number in this file was **measured on Derecho at Gate 1** on the date above. Nothing here is
quoted from documentation, inferred from a sibling repository, or carried over from Stampede3.

This file exists because HANDOFF §4 asks for it ("Write what you find into `docs/deviations.md` or a
short `docs/rda_archive_notes.md`. The next person should not have to rediscover it.") and because
`wave1-plan-derecho-addendum.md` §A12 item 7 makes it a deliverable. It is a **reference note about
the archive**, not a plan: it records what the files are, how they are laid out, what reading them
costs, and the two traps around them. The pipeline design that consumes the archive is the
addendum's (§A4–§A10) and is not restated here.

Each claim is cross-referenced to the addendum section that carries it, so a reader can trace it:
§A1.1 the archive, §A1.2 coverage, §A1.3 timing, §A1.4 the account, §A1.5 the environment,
§A1.6 missing documents, §A1.7 the float32/int16 finding.

---

## 1. Path, granularity, and the file-naming template (§A1.1)

```
/glade/campaign/collections/rda/data/d633000/e5.oper.an.pl/{YYYYMM}/
```

The month directory holds **one file per day**, named

```
e5.oper.an.pl.128_131_u.ll025uv.{YYYYMMDD}00_{YYYYMMDD}23.nc
```

at **≈ 1.6 GB each**. The `128_131_u` code is the u component of wind; the `00`/`23` suffixes are
the first and last hour the file covers, both on the same day.

**HANDOFF §4's guess is wrong and should not be repeated.** §4 anticipated "two half-month files per
month (days 1–15 and 16–end)". It is neither that nor one file per month: **it is one file per
day.** A season of MJJAS is therefore **153 files**, not 10 and not 5, and the campaign's 47 seasons
touch **7 191 files** on the read side.

The layout is uniform across the record: headers for 1979-05-01, 2018-05-01 and 2025 are identical.
There is **no era split and no format change** anywhere in 1979–2025, so code may assume one shape.

---

## 2. What is inside one file (§A1.1)

| Property | Measured value |
|---|---|
| Dims | `time = 24` (UNLIMITED; hours 00…23 all present), `level = 37`, `latitude = 721`, `longitude = 1440` |
| Wind variable | **`U`** — *uppercase* — `float32`, `units = "m s**-1"`, `_FillValue = missing_value = 9.999e+20`, `number_of_significant_digits = 7` |
| Second data variable | **`utc_date(time)`** shares the file |
| Level coordinate | `level`, `float64`, **`units = "hPa"`** (not Pa), 37 values, `250.0` present **exactly**, at **index 16** |
| Latitude | `latitude`, `float64`, **descending 90 → −90**, `units = "degrees_north"` |
| Longitude | `longitude`, `float64`, **0 … 359.75 ascending**, `units = "degrees_east"` |
| Time | `time`, `int`, `hours since 1900-01-01 00:00:00`, `calendar = gregorian`; decodes to `datetime64[ns]` |

Four consequences worth stating plainly, because each one is a thing a reader could get wrong:

- **A raw archive file cannot be handed to `profile.open_normalized`.** The file carries **two data
  variables** (`U` and `utc_date`) and no lowercase `u`, so `_resolve_wind` would reject it. Whatever
  reads the archive must emit its own file carrying a **single** variable named `u`. This is not a
  quirk of the wind field's capitalization alone; even after case is handled, `utc_date` is still a
  second data variable in the file.
- **The level units are `hPa`, and 250.0 is exact.** No unit conversion, no nearest-neighbour
  selection, no floating-point tolerance is needed to land on 250 hPa. A future file tagged in `Pa`
  would make "= 250" wrong by 100×, which is why the units string is worth asserting rather than
  assuming — but on every file inspected it is `hPa`.
- **Longitude is 0…359.75, so the wrap HANDOFF §4 anticipated is required.** The study sector
  (60°W–30°E) straddles the prime meridian, and the archive's convention does not.
- **Latitude is descending**, opposite to the ascending order the sector config and the intermediate
  use.

Every coordinate name, every unit string and the level value are already exactly what
`profile.open_normalized` accepts. **No frozen number in `configs/double_jet.yaml` has to move to
read this archive** (§A1.1).

---

## 3. Chunking, and the cost model it dictates (§A1.1)

This is the single most consequential measurement for anyone estimating walltime.

| | |
|---|---|
| Chunk shape | **`(1, 37, 721, 1440)`** — time × level × lat × lon |
| Filters | `shuffle`, `deflate` level **1** |
| One chunk | **one timestep × all 37 levels** = **154 MB uncompressed**, **≈ 67 MB on disk** |

**The level axis is inside the chunk.** There is no way to read the 250 hPa slice of one timestep
without decompressing the full 37-level chunk for that timestep. Selecting one level saves memory
and post-decompression work; it saves **no** I/O and **no** decompression.

**This, and nothing else, is the cost model.** Not the file size, not the sector size, not the
number of levels asked for: the cost of a day is four full-chunk decompresses (one per analysis
hour used), and everything else is noise against that. An estimate built on "we only want one level
of one sector, so it should be cheap" is wrong by construction, and §4's timings are what the real
model produces.

---

## 4. Coverage, and the last complete season (§A1.2)

A full inventory of MJJAS 1979–2026 was walked by name.

| Question | Measured answer |
|---|---|
| MJJAS 1979–2025 `128_131_u` daily files | **All 7 191 present. Zero gaps, zero short months.** |
| How far the archive extends | `202606` |
| MJJAS 2026 | **May and June only** — an incomplete season |
| Last complete MJJAS in the archive | **2025** |

47 seasons × 153 days = **7 191**, which is exactly the contract's `year_last: 2025` and exactly the
count in `CLAUDE.md`'s frozen numbers. Ruling R3 needs no revision.

The zero-gap result is a measurement of the archive as it stood on 2026-09-04, not a guarantee about
the future. Code that enumerates the 153 daily paths should still fail loudly, naming the date and
the expected filename, if one is absent.

---

## 5. Timing (§A1.3)

Measured by a read-only characterization job, **`7317125`**, on queue `main`, node `dec1933`, at
`select=1:ncpus=8:mem=64gb`, exit 0. This was a probe of the archive, not a pipeline run.

| Measurement | Value |
|---|---|
| Serial, per day (on a compute node) | **4.69 s** |
| Serial, per season (153 days) | **12.0 min** |
| Serial × 47 seasons | **9.37 h** |
| 8-way process-parallel, one full season (MJJAS 2018, 153 days) | **65.8 s** |
| 8-way × 47 seasons | **0.86 h ≈ 52 min** |
| Speed-up, 8 workers | **10.9×** |
| Peak memory | **2.49 GB** of the 64 GB requested |
| `/glade/campaign` visible from a `main` compute node | **Yes — verified in-job, not assumed** |

The 10.9× speed-up on 8 workers is measured, and it is super-linear. No mechanism for that is
claimed here; it is recorded as the observation it is.

Two things a future reader should take from this table. First, the compute-node visibility of
`/glade/campaign` is **verified**, so it is not a risk to re-litigate. Second, **9.37 h serial is
the number that matters for job sizing**: the parallel path is what makes the whole campaign fit
comfortably inside a 12 h walltime, and if parallelism is ever disabled the serial path does *not*
fit with defensible margin on a shared filesystem.

Peak memory of 2.49 GB against 64 GB requested means memory is not a constraint at this shape, and a
larger memory request would buy nothing.

---

## 6. The compute account trap (§A1.4)

`groups` returns `ncar uric0009 uchi0014 uchi0018`. That listing is misleading:

- **`URIC0009` is EXPIRED.** It is the account the sibling repo `butterfly` uses, so it is the
  obvious one to copy — and `qsub` refuses it **at submit time** with

  ```
  qsub: Account is in state: Expired
  ```

  A campaign script that copied `butterfly`'s account would have failed at submission.

- **`UCHI0014` is the account to use.** Normal/Active, it is the account behind the operator's other
  NCAR PBS work, and the Gate-1 probe ran clean under it. This is an operator ruling of 2026-09-04
  (§A1.4, decision O4).

---

## 7. Environment, and drift against Stampede3 (§A1.5)

Interpreter: `/glade/work/zhil/conda_envs/aires/bin/python`, **Python 3.11.11**.

| Package | Derecho (`aires`) | Stampede3 |
|---|---|---|
| xarray | 2025.1.2 | 2026.7.0 |
| numpy | 2.2.4 | 2.4.3 |
| scipy | 1.15.2 | 1.17.1 |
| netCDF4 | 1.7.2 | — |
| matplotlib | 3.10.0 | — |
| pandas | 2.2.3 | — |
| pyyaml | 6.0.2 | — |
| pytest | 9.0.2 | — |

`cdsapi` is importable in this environment. **All 63 pre-existing tests pass on Derecho under this
interpreter.**

The version drift against Stampede3 is real but **detectable rather than silent**: the version table
is recorded in the intermediate's **`package_versions`** attribute (plan §8 R9), so any result built
here carries the environment that built it. `scipy.signal.find_peaks`' documented default behaviour
(plan §2 I3) is stable across 1.15 and 1.17, and the 63 green tests include the I3 cases.

Nothing is pip-installed and no environment is rebuilt.

---

## 8. float32 versus int16 — a bit-exact match against the CDS baseline is impossible (§A1.7)

**This is the most important item in this file for a future reader not to get wrong.**

The RDA archive stores `U` as **unpacked `float32`**. The CDS products that produced the committed
2018 baseline are **`int16`-packed**. The two therefore cannot agree bit-for-bit, no matter how
correct the loader is.

The arithmetic, so the magnitude is *explained* rather than merely observed to be small:

- The 2018 R1 evidence pair is 91.8 MB for 612 × 221 × 361 = 48.8 M points — **1.88 bytes/point** —
  and 29.5 MB for 12.2 M points. That is packed storage, not float32.
- A ±100 m/s `int16` range quantizes at **≈ 0.003 m/s**, i.e. **±0.0015 m/s per point**.
- Averaging 4 hours and then 361 longitudes reduces that to **≈ 4e-5 m/s**.

Measured, comparing the Gate-1 RDA-built MJJAS-2018 daily-mean field (reduced to the zonal-mean
profile) against the committed CDS-built `results/smoke_2018/smoke_2018_profile.nc`:

```
max |diff| = 1.907e-04 m/s     mean |diff| = 2.92e-05 m/s     over 33 813 points (153 x 221)
```

The observed mean difference **is** the predicted quantization floor. The result is 250× inside the
operator's 0.05 m/s allowance.

**Therefore: a bit-exact profile match against the CDS baseline is impossible and must not be
pursued.** The discrepancy is CDS's packing, not the loader's arithmetic. The 0.05 m/s max-abs
allowance is the correct instrument, and the correct reading of it is "the difference is the packing
floor", not "the difference is an error we should drive to zero". Do not re-pack the RDA path to
`int16` to make the numbers match — that would reintroduce exactly the error identified here.

Two caveats on the figures above. They come from a Gate-1 probe that accumulated in `float64`
**outside** the pipeline, so they are a *characterization of the archive*, not the executor's
regression measurement; the real number is measured through the real code path (§A9). And a
difference of order 2e-4 m/s is small but not zero, so a day whose classification sits within 2e-4
of a threshold could in principle differ — that is a finding to report with a precise diagnosis, not
a tolerance to loosen (§A9.3).

---

## 9. Two documents HANDOFF cites that do not exist on this machine (§A1.6)

Recorded so nobody hunts for them:

- **`~/projects/CLAUDE.md`** — the "machine rules" file HANDOFF §0, §5.3 and §7 defer to repeatedly.
  **It does not exist on Derecho.** There is no `~/projects` directory at all; the checkout root is
  `~/project`. Its decide-yourself / escalate boundary is reproduced in the addendum's §A15, so
  nothing depends on the missing file.
- **`references/plan-template.md`** — cited by the brief as the template the addendum should follow.
  It does not exist in this repository or anywhere on this machine (searched). The addendum mirrors
  the section structure of `wave1-plan.md` instead, that being the reviewed exemplar in the tree.

Neither is a blocker.
