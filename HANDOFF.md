# HANDOFF — double-jet-natl, Stampede3 → Derecho

**Written:** 2026-09-04 · **By:** the Stampede3 executor session · **For:** the Derecho Claude agent
**Operator:** Zhixing Liu (`feynmanliu214`), who authorized every ruling marked *(operator, 2026-09-04)* below.

---

## 0. Read this first — which role you are in

Per `~/projects/CLAUDE.md`: *"Given a plan file (`*-plan.md`) → you are executing."*

**You are executing.** `wave1-plan.md` is post-Gate-4 and reviewed. The four gates are done, the
rulings stand, and you do **not** re-plan. One ruling — **R1** — has been reopened by the operator
and is superseded by §3 of this document; everything else in the plan is still the contract.

Your job, in one sentence: **replace the CDS download stage with a reader over the ERA5 archive
already on `/glade`, run the 47-season campaign, and write up the result.**

If the plan contradicts what you find in the code, **stop and say so**. Do not silently adapt it.

Read, in this order:

1. this file,
2. `CLAUDE.md` (repo invariants) and `~/projects/CLAUDE.md` (machine rules),
3. `wave1-plan.md` — the contract. §0 (rulings), §2 (I1–I7), §4 (stages), §6 (paths), §10–11.
4. `docs/deviations.md` — D1, D2, D3. D3 is the one that authorizes your data source.
5. `wave1.md` — the original wave prompt, for the scientific question behind all of it.

---

## 1. What this experiment is

Classify each MJJAS day, 1979–2025, over the North Atlantic–Europe sector as **double-jet**,
**single-jet**, or **neither**, from ERA5 250 hPa zonal wind, and report how the double-jet
fraction behaves across 47 seasons.

Every number that defines the science lives in `configs/double_jet.yaml` **and nowhere else**:

| | |
|---|---|
| Sector | 60°W–30°E × 20–75°N at 0.25° → **361 × 221** points |
| Level | **250 hPa** |
| Season | **MJJAS**, 1979–2025 → 47 seasons, **7 191** days |
| Smoothing | boxcar **2.5°** = **11** grid points (truncated + renormalized at the edges, I2) |
| Core threshold | `U_core_min` **15 m/s** |
| Pair separation | **10°** minimum latitude separation |
| Prominence | **5 m/s** below the weaker core |
| Hard gate | double-jet fraction must land in **5–90 %** |
| Diagnostic | ≥95 % of cores in 25–70 °N — **reported, never enforced** (ruling R2) |

**Changing any of these is an escalation to the operator (plan §11), not a code edit.** That
includes "just for a test". Ask.

---

## 2. State of the work — what is done, what is not

### Done and verified on Stampede3

- **The full pipeline is written, tested, and has run end to end.** 63 tests pass. Five modules:
  `config.py` (frozen dataclasses + two hashes), `download.py`, `profile.py`, `classify.py`,
  `figure.py`, behind one CLI (`double_jet/cli.py`).
- **The smoke season (MJJAS 2018) completed cleanly** — job `3466678`, exit 0, 1 min 15 s.
  Its outputs are committed under `results/smoke_2018/` as your regression baseline (§6).
- **Ruling R1's gate passed, and passed hard.** The CDS *derived* daily-mean product and a local
  mean of the archived hourly product at 00/06/12/18 UTC are **bit-identical**:
  `max_abs_diff = 0.0` over all **12 206 493** points (= 153 × 221 × 361) of MJJAS 2018.
  See `results/smoke_2018/smoke_2018_r1_validation.json`. This is the single most important
  measurement in the handoff — it is what makes §3 safe.
- **Smoke science numbers** (one season, for comparison only — not a target):
  double 96 / single 55 / none 2 → fraction **0.6275**, gate PASS.
  Core-latitude diagnostic **81.4 %** of 247 cores inside 25–70 °N, against a ≥95 % target.
  Season median of the daily maximum smoothed wind **26.87 m/s** (band 20–40).

### Not done — this is your work

- **The 47-season campaign never completed.** Job `3466925` timed out at 4 h having produced
  **5 seasons** (1979–1983). Cause is deviation **D2**: the CDS derived product is computed
  per-request, CDS serializes this account's requests, and the per-user queue wait grew
  monotonically 14 s → 34 → 36 → 49 → 54 min. Observed throughput **≈ 1 season/hour**;
  41 remaining seasons projected to **≈ 38 h** and still tightening.
- Therefore: **no `data/u250_natl_mjjas_1979-2025.nc`, no classification over the full record, no
  final figure, no write-up.** Those four are your deliverables.

### The 81.4 % question (plan §10 E3) — open, and it is a science question, not a bug

The smoke season put only 81.4 % of cores inside 25–70 °N. The out-of-band cores are **29
subtropical** at 20.50–24.75 °N (median 23.5 m/s) and **17 high-latitude** at 71.00–74.75 °N
(median 21.2 m/s) — i.e. they pile up at *both* domain edges, which is what a domain-truncation
effect looks like, not a detector fault. Only 6 of 46 sit within one half-window of the boundary,
so it is not a smoothing artifact either. Widening to 22–74 °N would hold 97.2 %.

Per ruling **R2** this is **reported, never gated** — it must not abort your run, and you must not
move the band to make it look better. Report the full-archive number and let the operator judge.

---

## 3. Ruling R1 is superseded — read this before touching the download stage

> **D3 (operator, 2026-09-04).** The campaign's daily means are no longer retrieved from the CDS
> derived product. They are computed locally from the ERA5 hourly archive already on Derecho's
> `/glade` filesystem. Plan ruling **R1** is reopened and replaced to this extent only.

**Why this is safe and not a change to the science:** R1's own verification gate measured the two
products **bit-identical** (`max_abs_diff = 0.0`, 12.2 M points). The equivalence R1 was originally
decided on was documentary; the equivalence you are relying on was measured. The daily mean is
defined exactly as before — the unweighted mean of the 00, 06, 12 and 18 UTC analyses
(`hourly_times` in the config). Nothing else about the metric moves.

**What this does not authorize.** It does not change the sector, level, season, year range, any
detection threshold, or any gate. If your reader would require changing one of those to work, that
is a discrepancy — **stop and report it**, per §0.

**Keep the CDS code.** `double_jet/download.py` and its tests stay in the tree, working. It is the
provenance record for the 2018 R1 evidence and the only thing that can re-derive it. Do not delete
it, and do not gut it to make room for the new reader — add alongside.

---

## 4. Your data source on Derecho

The NCAR RDA ERA5 archive, on disk, no network retrieval, no queue:

```
/glade/campaign/collections/rda/data/d633000/e5.oper.an.pl/{YYYYMM}/
```

Files are named like `e5.oper.an.pl.128_131_u.ll025uv.<start>_<end>.nc`. The `128_131_u` code is
the **u component of wind**; `128_130_t` is temperature and `128_129_z` geopotential, for
orientation. This path and the variable code are **verified in use** by the sibling repo
`butterfly` (`workflows/wave6_target_realism.py:79`, `workflows/wave5_year_select.py:252`) — but
that code reads *surface* and a different variable, so treat the details below as things to check,
not facts to assume.

**Characterize before you code.** In your first session, actually look:

- How is a month split? RDA pressure-level files are commonly **two half-month files per month**
  (days 1–15 and 16–end), unlike the single-file-per-month surface data `butterfly` reads. Confirm.
- What are the dims, the level coordinate and its **units** (`hPa` vs `Pa` — a Pa-tagged level
  makes "= 250" wrong by 100×; the pipeline checks this and will refuse), the variable name, the
  time coordinate, and the chunking.
- Is the grid **global 0.25°** with latitude **descending** (90 → −90) and longitude **0…359.75**?
  The pipeline handles both orientations, but you must land on exactly the config's grid.
- How large is one file, and how expensive is reading a single level out of it? This drives your
  walltime estimate more than anything else.

Write what you find into `docs/deviations.md` or a short `docs/rda_archive_notes.md`. The next
person should not have to rediscover it.

---

## 5. The seam — where your code plugs in

The pipeline is four stages: `download → profile → classify → figure`. **Only the first one
changes.** Everything downstream is already correct, tested, and must be left alone.

The contract between stage 1 and stage 2 is a **per-season netCDF file on disk plus a sidecar**.
Match it and the rest of the pipeline cannot tell the difference.

### 5.1 What you must produce, per season

One file at the path `download.season_paths(cfg, year)["nc"]` gives you —
`$SCRATCH/double-jet-natl/era5_raw/u250_natl_mjjas_{year}.nc` on Stampede3; on Derecho point
`paths.scratch_raw` at Derecho scratch (see §7). It must survive `profile.open_normalized`, which
is deliberately strict (plan §4.2, steps 1–8) and will refuse anything else:

| Requirement | Detail |
|---|---|
| **Dims** | time × latitude × longitude. Names must be one of `valid_time`/`time`, `latitude`/`lat`, `longitude`/`lon`. |
| **Shape** | **153 × 221 × 361** exactly. |
| **Level** | exactly one pressure level, value **250**, coordinate named `pressure_level`/`level`/`isobaricInhPa`, **`units: hPa`**. A size-1 level dim is fine; 37 levels is a hard error. |
| **Variable** | one data variable, or one named `u`. **`units` must be one of `m s**-1`, `m s-1`, `m/s`** — a missing `units` attribute is itself a failure ("units are read, not assumed"). |
| **Latitude** | must match `cfg.sector.latitudes()` to 1e-6 after sorting ascending; **`units: degrees_north`**. |
| **Longitude** | must match `cfg.sector.longitudes()` to 1e-6 after wrapping to [−180, 180) and sorting; **`units: degrees_east`**. Note the sector straddles the meridian, so a 0…360 source needs the wrap. |
| **Time** | 153 timestamps, one per day, all in one year, all in months 5–9. `datetime64`, no NaT. |
| **Values** | everywhere **finite** — `NaN` *and* `±inf` are both caught. |
| **Scalar coords** | `number`, `expver` are dropped for you; you need not add or remove them. |

The daily mean itself: **unweighted mean of the four analyses at 00, 06, 12, 18 UTC**, per
`cfg.hourly_times`. Not the mean of 24 hours. Not a weighted mean. This is the definition the R1
gate certified as bit-identical, and it is the metric definition — changing it is an escalation.

### 5.2 The sidecar and idempotence — do not skip this

`download.season_is_complete(cfg, year)` returns `(True, "")` only when the `.nc` opens with the
expected shape **and** a `.request.json` sidecar exists **and** that sidecar equals the request
that would be issued now. This is what makes the whole design work: a threshold change re-runs
classification **without touching a single raw file**, while a *sector* change correctly refuses to
reuse the cache. That behavior was verified on Stampede3 and it is a property worth preserving.

So your reader needs the same three-part contract, with an RDA-flavoured sidecar: record the source
file list, the subset spec (level, sector, hours), and enough identity (size + mtime, or a hash) to
detect that the archive moved under you. Compare against what would be built *now*, exactly as
`_canonical_request` does. Write to a `.part` file and `os.replace` it into place so a killed job
leaves no half-written season — the Stampede3 run was SIGKILLed mid-flight and left zero orphans
because of this.

### 5.3 Suggested shape (yours to change — file layout is your call)

- New module `double_jet/rda.py` with `ensure_local(cfg, years, smoke, log)`, mirroring
  `download.ensure_downloaded`'s signature.
- A config key `source: cds_derived | rda_hourly` that `cli.run` dispatches on, defaulting to
  `rda_hourly` on Derecho. Add a Derecho block to `configs/` rather than editing the frozen numbers.
- Tests in `tests/test_rda.py` (a new file — the four existing test files are owned by existing
  modules; do not edit them to accommodate you unless they are genuinely wrong).

Per `~/projects/CLAUDE.md` you **decide yourself**: file layout, function decomposition, naming,
logging, error handling, parallelization, test structure. You **escalate**: metric definitions,
thresholds, sampling, which years are included, dropping seasons, changing the target.

### 5.4 The one cross-check you owe

Before the campaign, re-run the R1 equivalence **against your own reader**: build MJJAS 2018 from
RDA, and compare it to the CDS-derived 2018 season preserved at

```
/work2/11114/zhixingliu/double-jet-natl/era5_r1_evidence/u250_natl_mjjas_2018.nc
```

(with `SHA256SUMS`, and the 6-hourly file beside it). If you can reach Stampede3, copy it over; if
not, say so and fall back to comparing your 2018 classification against
`results/smoke_2018/smoke_2018_jet_states.csv`. Expect **max_abs_diff = 0.0**, or an explanation.
A non-zero difference here is a finding, not a nuisance — report it before running 47 seasons on it.

---

## 6. Regression baseline — committed, use it

`results/smoke_2018/` holds the Stampede3 smoke season's actual outputs:

| File | What it pins |
|---|---|
| `smoke_2018_r1_validation.json` | `max_abs_diff = 0.0` over 12 206 493 points |
| `smoke_2018_jet_states.csv` | the per-day classification, 153 rows |
| `smoke_2018_summary.txt` | the sanity block: 96/55/2, fraction 0.6275, 81.4 % core latitudes |
| `smoke_2018_profile.nc` | the intermediate profile |
| `smoke_2018.png` | the figure |

`results/logs/` holds the four job logs behind D1, D2 and the smoke result.

**Your RDA-built 2018 should reproduce the CSV and the summary block exactly.** If it does not,
that is the finding to chase before anything else.

---

## 7. Compute on Derecho

### Verify these before you use them

`butterfly` (the operator's other repo, dual-site) uses account **`URIC0009`**, queue **`main`**,
checkout `/glade/u/home/zhil/project/<repo>`, env `/glade/work/zhil/conda_envs/aires`.

> **The operator has flagged that the account code may differ for this project — check it, do not
> assume it.** `groups` lists your project codes; confirm against a past job (`qstat -f <jobid>`)
> or the NCAR SAM portal, and if it is ambiguous, ask. A campaign that dies on a bad `-A` after
> six hours is a bad way to find out.

### Environment

The pipeline needs `xarray`, `netCDF4`, `numpy`, `scipy`, `matplotlib`, `pandas`, `pyyaml`,
`pytest` — `cdsapi` **only** if you exercise the legacy CDS path. On Stampede3 it ran under
Python 3.11.15 with xarray 2026.7.0, netCDF4 1.7.4, numpy 2.4.3, scipy 1.17.1, matplotlib 3.10.9.
Nothing is pip-installed; the package is run as `python -m double_jet` from the checkout.

Check whether `aires` already has these. Per `~/projects/CLAUDE.md`, **"No new dependencies, module
changes, or env rebuilds without asking"** — if `aires` is short something, report the gap and what
needs it, and ask. Do not `pip install` into a shared pinned env to unblock yourself.

### Job authority — read this precisely

**Smoke budget:** up to **five** smoke-scale PBS submissions (one season, 2018) to get the reader
working. A smoke job that fails is yours to diagnose, fix and resubmit without asking — that loop
is what the budget is for. If all five are spent without a clean end-to-end pass, **stop and
report**; five failures at smoke scale is evidence about the approach, not a budget problem.

**Campaign — pre-authorized (operator, 2026-09-04), at this shape and no larger:**

```
#PBS -A <verified account>
#PBS -q main
#PBS -l select=1:ncpus=8:mem=64gb
#PBS -l walltime=12:00:00
```

Conditions, all of which must hold:

1. The 2018 smoke season passes end to end first, including the §5.4 cross-check.
2. The run is idempotent, so **resubmitting this same shape until all 47 seasons are complete is
   covered by this authorization.** Partial progress must always survive.
3. **Anything larger is not covered** — more nodes, longer walltime, a different queue, a GPU
   queue. Scaling up is never a smoke job, however small the increase. Ask.

`main`'s 12 h ceiling is the binding constraint. If your archive characterization (§4) suggests one
pass cannot finish in 12 h, say so up front with the numbers — do not discover it at hour 11.

**Never run the driver bare on a login node.** Submit, or use an interactive session. Reading a few
files to characterize the archive (§4) is fine on a login node; running the pipeline is not.

---

## 8. Deliverables

1. `data/u250_natl_mjjas_1979-2025.nc` — the intermediate profile, all 47 seasons.
2. `data/jet_states_mjjas_1979-2025.csv` — 7 191 rows, one per day.
3. `data/jet_states_summary.txt` — the sanity block, including the full-archive double-jet fraction
   (hard gate, 5–90 %) and the core-latitude diagnostic (reported, not gated).
4. `figs/double_jet_natl_panels.{pdf,png}` — the figure. Keep `rasterized=True`; it was measured
   as the difference between 1.79 MB and ~24 MB.
5. **A write-up** (`docs/results/2026-XX-XX_wave1_results.md` or similar) covering: the double-jet
   fraction over 1979–2025 and how it varies by season and across the record; the core-latitude
   diagnostic and your reading of the 81.4 % question from §2; anything the data did that the plan
   did not predict. The operator asked for interpretation, not just artifacts.

Exit codes are meaningful and worth preserving: `0` OK, `1` a hard sanity gate failed, `2` preflight
failed, `3` crash.

Note the gate behavior, flagged by the Stampede3 executor and left as-is: the double-jet fraction
gate lets the run finish (figure included) and *then* exits 1, so a gate failure still hands you a
figure to look at. The R1, grid and level gates abort immediately. If the operator prefers a hard
stop at classify, that is a one-line change — but it is their call.

---

## 9. Three judgment calls from Stampede3 you are inheriting

Flagged to the operator, unchanged unless they say otherwise:

1. **Gate timing**, as just described — report-then-exit rather than abort-at-classify.
2. **`profile_sha256` was widened** past the plan's four fields to also cover
   `dataset`/`variable`/`daily_statistic`/`frequency`, so a frequency change cannot silently reuse
   a stale intermediate. Detection thresholds stay *excluded* per plan §4.3 — that exclusion is
   exactly what makes a threshold-only re-run free. **Your new source key belongs in this hash**:
   an intermediate built from CDS and one built from RDA must not be silently interchangeable.
3. **`build_intermediate` records the request template by rebuilding it from config**, not by
   reading the on-disk sidecar. Identical whenever the download stage ran in the same invocation;
   differs only for a bare `--stage profile` over stale files. One-line change if wanted.

---

## 10. Entry point

```bash
python -m double_jet --config configs/double_jet.yaml [--smoke | --stage ... | --skip-download]
```

`scripts/double_jet.py` is a documented shim only. `--stage` takes any of
`download,profile,classify,figure` (or `all`); `--smoke` runs the 2018 season and the R1 check;
`--years A-B` runs a subset **inside** the configured range and refuses anything outside it —
changing the year range is an escalation, not a flag.

```bash
python -m pytest tests/ -q      # 63 tests, all green as of commit d68d703
```

---

## 11. What is deliberately *not* in this repo

- `data/`, `figs/`, `logs/` are gitignored. A fresh clone has no outputs — that is why the smoke
  baseline was copied into the tracked `results/` instead.
- Raw ERA5 is never committed and never lives under `$HOME` or `$WORK` on Stampede3
  (repo `CLAUDE.md`). The one exception is the 2018 R1 evidence pair deliberately preserved at
  `/work2/11114/zhixingliu/double-jet-natl/era5_r1_evidence/` — 123 MB, with checksums, because
  `$SCRATCH` purges on inactivity and that pair is the provenance for the only R1 measurement that
  exists. **Derecho storage rules are yours to establish**; do not blindly apply Stampede3's paths.
- The five 1979–1983 seasons downloaded on Stampede3 were **left to purge**. They are reproducible
  from RDA and the operator chose not to preserve them.

---

## 12. If something here is wrong

Say so. This document was written by the session that wrote the code, which is exactly the session
most likely to have blind spots about it. The plan, the deviations log and the committed evidence
are the record; this file is a reading of them. Where they disagree, **they win**.
