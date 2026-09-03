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
