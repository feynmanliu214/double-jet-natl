# Deviations from `wave1-plan.md`

The plan is post-Gate-4 and reviewed. Anything execution found to be untrue of it is recorded here
with the evidence, rather than silently absorbed into the code.

---

## D1 — The derived daily-statistics product does not always return a ZIP

**Date:** 2026-09-03 · **Evidence:** smoke job `3466587` (skx-dev), `logs/smoke_2018_3466587.out`
**Plan text contradicted:** §1.4, second numbered property —

> It **always returns a ZIP** — *"provided in netCDF format only (in a zip file) … one netCDF file
> per variable, and all files will be archived in a zip file."* This is why the process exposes no
> `data_format` / `download_format` input.

**What actually happened.** The MJJAS 2018 request to
`derived-era5-pressure-levels-daily-statistics` completed successfully on the CDS side
(request `af43a673-8fc9-4f25-94a4-a226e535171b`, status `successful`) and delivered a **bare
netCDF of 29.5 MB** from
`https://object-store.os-api.cci2.ecmwf.int:443/cci2-prod-cache-3/2026-09-03/867bd2421be6a7e7a7e8a4e4b9f3e945.nc`
— note the `.nc` suffix on the object-store URL. `download.extract_zip` then failed with
`File is not a zip file`, and the season was reported as failed. The 6-hourly R1 operand from
`reanalysis-era5-pressure-levels` downloaded normally (91.8 MB) in the same job.

The §1.4 quotation is accurate as ECMWF *documentation*; it is the documentation that is stale, not
the plan's reading of it. Gate 1 could not have caught this: it is only observable by retrieving
from this dataset, which §1.3 records as never having been done from this account.

**What changed.** `download._download_season` now **detects** the container instead of assuming it:
`zipfile.is_zipfile()` decides between extracting a member and using the delivered file directly.
A ZIP is still kept when one arrives.

**Why this is not a science change.** §4.1 already designates the ZIP "an incidental transport file,
not an artifact … a season whose ZIP is gone is complete", and `season_is_complete` never referenced
it. The season's artifacts — the `.nc` and its `.request.json` sidecar — are bit-for-bit what the
plan specifies either way. No threshold, sector, level, year range, metric or gate is touched. This
sits on the "decide yourself" side of `CLAUDE.md`'s boundary (error handling / file layout).

**Locked in by:** `tests/test_profile.py::test_derived_product_is_accepted_whether_or_not_it_arrives_zipped`,
parametrized over both containers. Reverting the fix reproduces the production error exactly
(`BadZipFile: File is not a zip file`) on the bare-netCDF case.

---

## Resolved at execution — plan uncertainties that the smoke job answered

| Plan item | Status after job 3466587 |
|---|---|
| **R10 / §1.8** — `skx-dev` outbound network unproven | **Proven.** Preflight on the compute node: DNS `cds.climate.copernicus.eu -> 136.156.139.54`, `https://cds.climate.copernicus.eu/api -> 202`, `https://object-store.os-api.cci2.ecmwf.int/ -> 200`. Identical to the `skx` values §1.8 measured. |
| **R3 / E5** — derived dataset licence never retrieved from this account | **Cleared.** No 403; the request was accepted and completed. The licence covers it. |
| **§1.5** — queue wait and processing time | Queue wait 20 min (skx-dev fully allocated at submission, not a CDS delay). CDS processing: derived daily 2 min 55 s, 6-hourly 1 min 28 s — both inside §1.5's estimate. |

---

## Note — smoke season outcome (job `3466678`, 2026-09-03)

The rerun after D1 completed in 1 min 15 s, exit 0, issuing one CDS request (the 6-hourly operand
was already complete on `$SCRATCH` and was skipped, which is R11's identity check doing its job).

**M2 settled decisively.** The R1 equivalence gate returned `max_abs_diff = 0.0` over all
12 206 493 points (= 153 × 221 × 361, the full expected count). The derived daily-statistics product
is not merely within 1e-3 of the mean of 00/06/12/18 UTC — it is *bit-identical* to it. §4.1's R4
risk is closed.

**One diagnostic misses its target, and it is E3's to judge.** Core latitudes within 25–70 °N:
**81.4 %** of 247 recorded cores, against the ≥ 95 % target — a wider miss than the 89.9 % §1.7
measured on the 1.5° probe. Under ruling R2 the run finished and reported; no band was moved.

§1.7's supporting argument is *weakened but not overturned* on real 0.25° data:

| §1.7 claim (1.5° probe, MJJAS 2020) | Measured (0.25° ERA5, MJJAS 2018) |
|---|---|
| zero out-of-band cores within one half-window (1.25°) of 20 N / 75 N | **6 of 46** (13 %) |
| out-of-band cores are physically real, not edge artifacts | still true of **87 %** of them |
| 23–72 N holds 97.4 % | 23–72 N holds 91.1 % |
| 22–74 N holds 100 % | 22–74 N holds 97.2 % |

Zero cores sit on the outermost grid row, as I3/R7 guarantees by construction. The out-of-band
population is 29 subtropical cores at 20.50–24.75 N (median 23.5 m s⁻¹) and 17 high-latitude cores
at 71.00–74.75 N (median 21.2 m s⁻¹). The figure shows the subtropical jet still strong at the 20 °N
boundary in May–June, so some southern cores plausibly belong to a jet whose true maximum lies
*south of the domain* — a domain-truncation question, not an algorithm fault.

This is **one season**; E3 concerns the full archive. Recorded here so the campaign's number can be
compared against it rather than judged fresh.

---

## D2 — The derived product's throughput is ~1 season/hour, not "minutes per season"

**Date:** 2026-09-04 · **Evidence:** campaign job `3466925` (skx), TIMEOUT at 04:00:03,
`logs/download_all_3466925.{out,err}`
**Plan text contradicted:** §1.5, last bullet —

> **Queue wait**, from this account's 2026-08-25 history: **8–95 s to start** (median ≈ 15 s). …
> A season is minutes, not hours.

**What actually happened.** In 4 h the job submitted 8 requests and completed **5 seasons**
(1979–1983). It hit the walltime with 3 requests still in `accepted`. Season completions landed at
02:19, 02:55, 03:33, 04:24, 05:20 — inter-completion gaps of **36, 38, 51, 56 min**.

Two facts from the request lifecycle, both load-bearing:

1. **CDS serializes this account's derived-product requests.** Three were in flight at all times
   (the `max_in_flight: 3` pool worked as designed), but every `running` transition is immediately
   preceded by the previous `successful` — never two at once. Concurrency buys nothing here.
2. **Compute is fast; the queue wait is the cost, and it grows.** `running -> successful` was dead
   steady at **2m00s–2m39s** every time. `accepted -> running` grew monotonically:
   **14 s → 34 min → 36 min → 49 min → 54 min**. Per-request latency grew 3 → 39 → 77 → 125 →
   145 min. This is per-user throttling that tightens under sustained use.

**Why Gate 1 could not have caught it, and why §1.5 was nonetheless too optimistic.** §1.5's
8–95 s figure is taken from this account's 2026-08-25 history, which §1.3 records as *ordinary*
`reanalysis-era5-pressure-levels` retrievals. §1.3 also records that the derived dataset had **never
been retrieved from this account**, so no derived-product timing existed to measure. §1.4 item 1
already noted the mechanism — *"the daily aggregation is calculated during the retrieval process and
is not part of a permanently archived dataset"* — but the plan did not connect that property to
throughput: each season is a compute job in a throttled per-user queue, not an archive read.

**The smoke run's 51 s was a cache hit, not a measurement.** Job `3466678` retrieved the identical
object-store URL (`867bd2421be6a7e7a7e8a4e4b9f3e945.nc`) that the D1 attempt had already caused CDS
to compute. The only cold single-request timing is D1's **2m55s**, which is consistent with the
2-minute compute above and is fine in isolation — it simply does not survive 46 sequential requests.

**Projection.** 41 seasons remain (1984–2025; 1979–1983 and 2018 are cached and will be skipped).
At the observed 56 min/season that is **≈ 38 h**; if the throttle keeps tightening it exceeds the
48 h queue ceiling. A 4 h walltime was never going to be enough, and this is not a Stampede3
constraint — the compute node was idle almost the whole time.

**Nothing was lost.** All 6 cached seasons carry matching request sidecars, no `.part` orphans
survived the SIGKILL, and `season_is_complete` will skip exactly those 6 on the next run. The
idempotence design (§4.1, R11) did its job: a resumed run completes only the gaps.

**Not resolved here.** Fixing this needs either a larger shape (a longer walltime) or reopening
ruling **R1** (which product supplies the daily mean). Both are operator decisions under §11 and
`CLAUDE.md`'s compute rules; the executor stopped and reported rather than choosing.

Relevant asset for that decision: **R1's gate returned `max_abs_diff = 0.0`** over all 12 206 493
points of MJJAS 2018 (see the smoke note above). The derived daily product and the local mean of
00/06/12/18 from the archived hourly dataset are *bit-identical*, which is a stronger equivalence
than the documentation R1 was originally decided on.

---

## D3 — Ruling R1 reopened: the campaign moves to Derecho and to the archived hourly product

**Date:** 2026-09-04 · **Authority:** operator, explicit, this date
**Plan text superseded:** §0 **R1** — the derived daily-statistics product supplies the daily mean
for all 47 seasons.

**The decision.** The CDS retrieval campaign is abandoned. The daily means are computed locally
from the ERA5 hourly archive already resident on NCAR Derecho's `/glade` filesystem (NCAR RDA
`d633000`, `e5.oper.an.pl`), by a Derecho agent picking up this repository. The definition of the
daily mean is unchanged: the unweighted mean of the 00, 06, 12 and 18 UTC analyses, per
`hourly_times` in the config.

**Why this is not a change to the science.** R1's own verification gate measured the two products
**bit-identical** — `max_abs_diff = 0.0` over all 12 206 493 points of MJJAS 2018
(`results/smoke_2018/smoke_2018_r1_validation.json`). R1 was originally decided on ECMWF's
documentation of the two products; it is now being reopened on a direct measurement of them, which
is the stronger evidence. No sector, level, season, year range, detection threshold or gate moves.

**Why it was necessary.** D2: the derived product is computed per request, CDS serializes this
account's requests, and the per-user queue wait grows monotonically under sustained use — measured
throughput ≈ 1 season/hour, projecting ≈ 38 h for the 41 remaining seasons against a 48 h ceiling
that was still tightening. The archived hourly data on `/glade` has no retrieval queue at all.

**Scope.** This authorizes the change of data source and nothing else. `double_jet/download.py` and
its tests stay in the tree, working: they are the provenance record for the 2018 R1 evidence and the
only code that can re-derive it. A reader that would require changing a frozen number to work is a
discrepancy to report, not to accommodate.

**Evidence preserved.** The 2018 pair — CDS derived daily and the 6-hourly cross-check file — was
copied off `$SCRATCH` (which purges on inactivity) to
`/work2/11114/zhixingliu/double-jet-natl/era5_r1_evidence/`, 123 MB, with `SHA256SUMS`. The five
seasons 1979–1983 downloaded before the timeout were left to purge: they are reproducible from RDA
and the operator chose not to preserve them.

**Handoff.** `HANDOFF.md` carries the full brief for the Derecho agent: the stage-1 seam and the
exact contract `profile.open_normalized` enforces, the archive path to characterize before coding,
the compute authorization, and the deliverables. `results/` now carries the smoke-season outputs and
the job logs as a committed regression baseline, since `data/`, `figs/` and `logs/` are gitignored
and a fresh clone would otherwise arrive with no evidence at all.
