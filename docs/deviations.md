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
