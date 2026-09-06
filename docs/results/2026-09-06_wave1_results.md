# DJET-NATL Wave 1 — results: the double-jet fraction over MJJAS 1979–2025

**Date:** 2026-09-06 · **Machine:** NCAR Derecho · **Campaign job:** `7321579`, exit 0
**Contract:** `wave1-plan.md` (post-Gate-4) as extended by `wave1-plan-derecho-addendum.md` (D3)
**Deliverable:** addendum §A12 item 5 / HANDOFF §8 item 5

This is the write-up the campaign owed. It reports what the 47 seasons produced, sets the
core-latitude diagnostic against the smoke season for the operator's ruling (**O2**, plan §10 **E3**),
records the §A9 regression evidence, and names what the data did that the plan did not predict.

Every number below is either read from a committed artifact — `data/jet_states_summary.txt`,
`data/smoke_2018_regression.json`, `logs/campaign.out`, the intermediate's attributes — or computed
here from `data/jet_states_mjjas_1979-2025.csv`. The source is named on each. Nothing is estimated.

**Scope, per §A12:** no trend analysis, no persistence analysis, no heatwave linkage. Variation is
reported as distribution and spread; the ordering of seasons across the record is out of scope and
no direction over time is fitted, tested or claimed anywhere in this document.

---

## 1. What ran, and where

| | |
|---|---|
| Job | `7321579`, queue `main`, account `UCHI0014`, `select=1:ncpus=8:mem=64gb` |
| Started | 2026-09-05T00:00:47-06:00, node `dec0313`, git `f88ac98` |
| Walltime | **00:57:23** of a 12 h ceiling |
| Peak memory | **3.94 GB** of 64 GB requested |
| Interpreter | `/glade/work/zhil/conda_envs/aires/bin/python`, Python 3.11.11 |
| Stages | `download → profile → classify → figure`, one submission, no resubmission |

Stage 1 read the RDA hourly archive on `/glade` rather than the CDS derived product — deviation
**D3**, implemented per addendum §A4–§A7. 46 of the 47 seasons were built in the job; MJJAS 2018 was
already on `$SCRATCH` from the smoke run and was correctly skipped as complete by the sidecar check
(`logs/campaign.out`). The 46 builds took **3 369 s ≈ 56.2 min** in total (mean **73.2 s** per season,
computed from the per-season lines in `logs/campaign.out`); `profile`, `classify` and `figure`
together took about **31 s**. The campaign is loader-bound, as §A1.3 predicted.

Deliverables produced (paths per §A12):

| Deliverable | Size |
|---|---|
| `data/u250_natl_mjjas_1979-2025.nc` | 4.7 MB — 7 191 days × 221 latitudes |
| `data/jet_states_mjjas_1979-2025.csv` | 7 191 rows + header |
| `data/jet_states_summary.txt` | the §4.4 sanity block |
| `figs/double_jet_natl_explorer.html` | 202.1 KB — 47 seasons embedded as JSON, no network, no external scripts (**D4**) |
| `results/season_summary.csv` | 47 rows + header — one row per season (**D4**) |
| `figs/double_jet_natl_annual.png` | 98.2 KB — 2200 × 500, the explorer's annual chart (**D4**) |
| `data/smoke_2018_regression.json` | §A9 evidence, all three comparisons passed |

The three **D4** rows are the deliverable set as it now stands, not what this job wrote: the
2026-09-05 run produced `figs/double_jet_natl_panels.pdf` / `.png` (1.92 MB / 1.70 MB, 47 panels
in an 8 × 6 grid), which D4 retired afterwards and which are retained in `results/campaign/`.

The intermediate carries the full provenance the addendum required: `source_dataset: ds633.0`, the
RDA request template with the archive root and file template, `profile_sha256`
`a375a91a…`, `config_sha256` `9a6116ad…`, the `aires` package-version table, and a per-season
`source_files` inventory with SHA-256 for all 47 season files.

---

## 2. The headline result and the gate

From `data/jet_states_summary.txt`:

| State | Days | Share |
|---|---|---|
| **double** | **3 246** | **45.1 %** |
| single | 3 932 | 54.7 % |
| none | 13 | 0.2 % |
| **total** | **7 191** | 100 % |

**Double-jet fraction 0.4514, against the hard gate band 0.05–0.90 → PASS.** The fraction sits near
the middle of the band, not near either edge; the gate was never in question at 47-season scale.

The 13 `none` days (no smoothed core anywhere in 20–75 °N reaching `U_core_min` = 15 m/s) are
overwhelmingly midsummer: 9 in July, 3 in August, 1 in June (computed from the CSV). They are the
days on which the sector's zonal-mean 250 hPa flow is simply too weak to register a core at all.

**The classification is not perched on a threshold.** Computed from the CSV and the intermediate:
on double days the achieved prominence — `min(u_1, u_2) − interjet_min` — has median **13.67 m/s**
against the 5 m/s floor, and only 179 double days (5.5 %) sit within 1 m/s of it; core separation
has median **26.0°** against the 10° floor, and only 27 days sit within 2° of it. On the other side,
2 518 of the 3 932 single days (64.0 %) carry exactly **one** candidate core above 15 m/s, so they
are single by absence of a second jet rather than by a rule rejecting a pair; the remaining 1 414
(36.0 %) had two or more candidate cores and failed the separation or prominence rule. A
plausibility check on the field itself (plan §2 I5, printed for the smoke run only): the median over
all 7 191 days of the daily maximum of the smoothed profile is **26.67 m/s**, inside the 20–40 m/s
band, and every one of the 47 season medians falls in **24.27–29.10 m/s**.

---

## 3. How it varies by month

Computed from the CSV. Each month is pooled over all 47 seasons.

| Month | Days | Double | Single | None | **Double fraction** |
|---|---|---|---|---|---|
| May | 1 457 | 989 | 468 | 0 | **67.9 %** |
| June | 1 410 | 760 | 649 | 1 | **53.9 %** |
| July | 1 457 | 425 | 1 023 | 9 | **29.2 %** |
| August | 1 457 | 408 | 1 046 | 3 | **28.0 %** |
| September | 1 410 | 664 | 746 | 0 | **47.1 %** |
| **all** | **7 191** | **3 246** | **3 932** | **13** | **45.14 %** |

**Check:** the five month rows pool to 3 246 / 7 191 = 0.451398 — the summary's 0.4514 exactly.

This is the largest source of structure in the whole result, and it is much larger than the
season-to-season spread of §4. The double-jet state is the *majority* state in May (67.9 %) and a
clear minority in July and August (29.2 %, 28.0 %) — a factor of 2.4 between the extremes of the
season. September recovers to 47.1 %, near the all-record mean, so the shape across MJJAS is a
midsummer minimum bracketed by double-jet-dominated shoulders rather than a monotone progression
through the season.

The month effect is not an artifact of a few seasons: the per-season monthly fractions are wide but
consistently ordered. Their per-month min / median / max across the 47 seasons are May
35.5 / 67.7 / 96.8 %, June 10.0 / 50.0 / 93.3 %, July 3.2 / 29.0 / 74.2 %, August 0.0 / 25.8 / 87.1 %,
September 16.7 / 50.0 / 76.7 %. Note that individual months in individual seasons reach both 0 % and
96.8 % — the 5–90 % gate band is a statement about the *pooled* record, and it would not survive
being applied per month per season. It is not applied that way, and nothing here proposes that it
should be.

The plan did not predict this month structure and did not ask for it; it is reported because it is
the dominant term in "how it varies by season" (HANDOFF §8), and because it conditions §5: the
out-of-band cores are concentrated in exactly the months where double-jet days are common.

---

## 4. How it varies across the 47 seasons

Each season is exactly 153 MJJAS days (verified: all 47 groups have 153 rows), so the count and the
fraction carry the same information.

| Season | n | % | Season | n | % | Season | n | % | Season | n | % |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1979 | 87 | 56.9 | 1991 | 76 | 49.7 | 2003 | 61 | 39.9 | 2015 | 68 | 44.4 |
| 1980 | 45 | 29.4 | 1992 | 71 | 46.4 | 2004 | 60 | 39.2 | 2016 | 60 | 39.2 |
| 1981 | 90 | 58.8 | 1993 | 54 | 35.3 | 2005 | 67 | 43.8 | 2017 | 44 | **28.8** |
| 1982 | 63 | 41.2 | 1994 | 74 | 48.4 | 2006 | 65 | 42.5 | 2018 | 96 | **62.7** |
| 1983 | 83 | 54.2 | 1995 | 84 | 54.9 | 2007 | 84 | 54.9 | 2019 | 57 | 37.3 |
| 1984 | 70 | 45.8 | 1996 | 81 | 52.9 | 2008 | 64 | 41.8 | 2020 | 76 | 49.7 |
| 1985 | 58 | 37.9 | 1997 | 71 | 46.4 | 2009 | 68 | 44.4 | 2021 | 82 | 53.6 |
| 1986 | 73 | 47.7 | 1998 | 76 | 49.7 | 2010 | 63 | 41.2 | 2022 | 74 | 48.4 |
| 1987 | 49 | 32.0 | 1999 | 70 | 45.8 | 2011 | 58 | 37.9 | 2023 | 68 | 44.4 |
| 1988 | 72 | 47.1 | 2000 | 77 | 50.3 | 2012 | 52 | 34.0 | 2024 | 78 | 51.0 |
| 1989 | 84 | 54.9 | 2001 | 76 | 49.7 | 2013 | 58 | 37.9 | 2025 | 52 | 34.0 |
| 1990 | 52 | 34.0 | 2002 | 84 | 54.9 | 2014 | 71 | 46.4 | | | |

`n` is double-jet days out of 153.

| Statistic | Value |
|---|---|
| Minimum | **28.8 %** (2017, 44 days) |
| Maximum | **62.7 %** (2018, 96 days) |
| Median | **45.8 %** (70 days; 1984 and 1999 sit on it) |
| Mean | 45.1 % |
| Standard deviation | **8.0 percentage points** |
| Interquartile range | 39.2 % – 50.0 %, width **10.8 pp** |
| Full range | width **34.0 pp** |

**Check:** the 47 season counts sum to 3 246 over 7 191 days = 0.451398, the summary's value again.

Three things are worth saying about this distribution, none of them about direction over time.

1. **Every one of the 47 seasons lands inside the 5–90 % gate band on its own**, by a wide margin at
   both ends. The gate is a statement about the pooled record, but it would also have passed had it
   been applied season by season — which is a useful robustness fact about the classifier, not a
   proposal to change where the gate is applied.
2. **The bulk of the distribution is tight and the tails are short.** 22 of 47 seasons fall inside
   the interquartile range of 39.2–50.0 %; only six seasons fall below 35 % (1980, 1987, 1990, 2012,
   2017, 2025) and only three above 55 % (1979, 1981, 2018). The season-to-season spread
   (8.0 pp standard deviation) is small next to the 39.9 pp spread between the May and August
   monthly fractions of §3.
3. **The smoke season was the extreme, not the typical case — and this matters for how the smoke
   baseline should be read.** MJJAS 2018 at 62.7 % is the **single highest of the 47 seasons**, and
   2017 at 28.8 % is the lowest; they are adjacent seasons spanning almost the entire range of the
   record. HANDOFF §2 was explicit that the smoke numbers were "for comparison only — not a target",
   and this is the vindication of that caution: the 0.6275 smoke fraction was 17.6 pp above the
   47-season value, and anyone who had taken it as an expectation would have been badly calibrated.
   The campaign's 45.1 % is the answer; 2018's 62.7 % is one draw from the top of the distribution.

---

## 5. The core-latitude diagnostic (R2 / O2 / E3) — reported, not gated

**This section reports. It moves no threshold, and it recommends moving none.** Under plan §0 **R2**
and addendum **O2** the operator rules on this once the full-period number exists. It now exists.

### 5.1 The number

From `data/jet_states_summary.txt`:

```
[REPORT]   core latitudes within 25-70 N :  88.2 % of 10424 recorded cores (target >= 95 %)
           out-of-band cores : 1227
```

**88.2 % of 10 424 recorded cores fall in 25–70 °N, against the ≥ 95 % target — a shortfall of
6.8 percentage points.** The smoke season alone gave **81.4 %**. The full record is therefore
**6.8 pp better than the smoke season**, and still **6.8 pp short of the target**.

The 10 424 cores are 3 932 single-day cores plus 2 × 3 246 double-day cores, exactly as the
classifier records them (verified against the CSV: `lat_1` non-null on every classified day, `lat_2`
additionally on double days).

### 5.2 Where the out-of-band cores sit

Computed from the CSV. The 1 227 out-of-band cores split almost evenly between the two edges:

| Edge | Cores | Latitude range | Median latitude | Median core wind |
|---|---|---|---|---|
| **Low (< 25 °N)** | **653** (53.2 %) | 20.25 – 24.75 °N | 23.00 °N | 23.50 m/s |
| **High (> 70 °N)** | **574** (46.8 %) | 70.25 – 74.75 °N | 72.00 °N | 20.41 m/s |

Both edges, not one. This is the same picture HANDOFF §2 reported for the smoke season, at 47-season
scale and with a fuller decomposition:

- **No core in the entire record sits on the domain boundary row** — 0 of 10 424 at 20.00 °N and 0
  at 75.00 °N. `find_peaks` at its defaults (plan §2 I3) requires a strict interior local maximum,
  so the extreme reachable rows are 20.25 and 74.75 °N. Those two rows carry **28** and **29** cores
  respectively.
- **The out-of-band cores are not clustered against the wall.** Only 91 of the 653 low-edge cores
  and 90 of the 574 high-edge cores lie within one half smoothing window (1.25° = 5 grid rows) of the
  domain edge — **181 of 1 227, or 14.8 %**. The rest are interior features that simply sit poleward
  of 70 °N or equatorward of 25 °N. This rules out the truncated-boxcar edge treatment (plan §2 I2)
  as the explanation, and it matches the smoke season's ratio (6 of 46) closely.
- **They are a property of double days.** 1 152 of the 1 227 out-of-band cores (93.9 %) come from
  double days; only **75 of the 3 932 single-day cores (1.9 %) are out of band**. Read the other
  way: on the 3 246 double days, the equatorward core is below 25 °N on 593 days (18.3 %), the
  poleward core is above 70 °N on 559 days (17.2 %), both on 29 days, and neither on 2 123 days
  (65.4 %).
- **The low edge is strongly seasonal; the high edge is not.** In-band percentages by month are May
  78.3, June 87.5, July **94.9**, August **93.7**, September 89.8. Of the 653 low-edge cores, 408 are
  in May, 174 in June and 70 in September — **1 in July and 0 in August**. The 574 high-edge cores
  are spread across all five months (123 / 98 / 95 / 117 / 141). July and August, the two months that
  very nearly meet the 95 % target, are exactly the months in which the subtropical member of the
  pair is absent from the sector.
- **Per season**, the in-band fraction runs from **81.4 % (2018) to 94.5 % (2005)**, median 88.3 %.
  **No single season reaches 95 %**, and 2018 — the smoke season — is the **worst of the 47**. So the
  smoke season was the extreme case on this diagnostic too, in the same direction as it was extreme
  on the double-jet fraction, and consistently so: it had the most double days, and double days are
  what produce out-of-band cores.
- The summary's eight "worst offenders" all fall in 1979–1985, which is an artifact of the printing
  rule, not a property of the record. The sanity block sorts by excess descending and breaks ties by
  date ascending; there are **57** cores tied at the maximum excess (the 20.25 and 74.75 °N rows),
  spread over **34 distinct years spanning 1979–2025**, so the eight printed are simply the earliest
  eight of a tie. They should not be read as evidence about any part of the record.

### 5.3 What this does and does not mean

**What it means.** The diagnostic counts *cores*, not days, and a double-jet day contributes two
cores by construction. The pair rule requires ≥ 10° of separation inside a domain only 55° tall, so
whenever the sector holds a genuine double structure, one member is pushed toward a domain edge.
That is why 93.9 % of the shortfall comes from double days, why the shortfall is worst in the months
with the most double days, and why the season with the most double days (2018) has the worst in-band
fraction. The 25–70 °N band covers 45° of the 55° domain; the out-of-band strip is 18.2 % of the
domain by latitude and holds 11.8 % of the cores, so cores are in fact *less* concentrated at the
edges than a latitude-uniform distribution would put them. A ≥ 95 % in-band target on a
two-core-per-double-day statistic is therefore a demanding target in this domain, and the 88.2 %
result is consistent with the geometry of the sector rather than with a detector fault. The
out-of-band cores are also real jets, not noise: their median wind is 23.50 m/s at the low edge and
20.41 m/s at the high edge, against 24.42 m/s for the in-band cores — weaker, but far above the
15 m/s core threshold.

**What it does not mean.** It is not a gate and it did not affect the exit code; job `7321579`
exited 0 on the strength of the double-jet fraction alone. It is not evidence that the 25–70 °N band
or the 95 % target is wrong, and **this write-up neither moves them nor recommends moving them**
(plan §0 R2, §10 **E3**, addendum **O2**). It is not evidence that the classifier is misbehaving: the
out-of-band cores are interior local maxima above threshold, not edge artifacts, not smoothing
artifacts, and not boundary-row pile-ups.

**The decision is the operator's.** The 47-season number O2 asked for is 88.2 %; the smoke season it
is to be set against is 81.4 %; the shortfall against the target is 6.8 pp; the decomposition above
is the evidence. Plan §10 E3 governs what happens next.

---

## 6. Provenance: D3, the RDA archive, and the 2018 regression

### 6.1 The source

Stage 1 read `/glade/campaign/collections/rda/data/d633000/e5.oper.an.pl` — one file per day,
≈ 1.6 GB each, 7 191 files touched on the read side — and computed the daily mean locally as the
unweighted mean of the 00, 06, 12 and 18 UTC analyses, selected by timestamp (§A3 **J1**). The
metric definition is unchanged from `wave1-plan.md`; only its supplier changed, which is exactly
what D3 authorizes. `docs/rda_archive_notes.md` carries the Gate-1 archive findings behind this.

The intermediate records `source_dataset: ds633.0` and an RDA-shaped `request_template`, so the
figure and every downstream artifact are captioned with the archive they were actually built from
(§A7.2). The `profile_sha256` covers `source`, `hourly_times` and the archive root (§A4.3 / **O1**),
so a CDS-built and an RDA-built intermediate can never be silently interchanged.

### 6.2 The §A9 regression against the Stampede3 CDS baseline

From `data/smoke_2018_regression.json` — all three comparisons **passed**:

| # | Comparison | Requirement (**O3**) | Achieved |
|---|---|---|---|
| 1 | `smoke_2018_jet_states.csv`: `state`, `lat_1`, `lat_2` | exact, all 153 rows | **0 mismatched rows of 153** |
| 2 | `smoke_2018_summary.txt` | exact | **28 of 28 lines identical** |
| 3 | `smoke_2018_profile.nc` `U` | max-abs ≤ 0.05 m/s | **0.000e+00 m/s over 33 813 compared points** (= 153 × 221, the expected count) |

The RDA-built 2018 season reproduces the CDS-built Stampede3 baseline **bit-exactly**, not merely
within tolerance: mean, median, p99 and maximum absolute difference are all 0.0, with 0 points
exceeding the tolerance. The two operands are a verified-distinct pair — different machine,
different interpreter, different library versions, and the baseline unmodified since commit
`519f99c`.

This is the strongest possible form of the cross-check HANDOFF §5.4 asked for, and it is the
evidence that the 47-season campaign rests on a supplier change and not on a science change.

---

## 7. The last complete season

Reporting §A1.2 as §A12 requires. A full name-by-name inventory of MJJAS 1979–2026 was walked at
Gate 1:

- **1979–2025: all 7 191 daily `128_131_u` files present — zero gaps, zero short months.**
- The archive extends to `202606`; **MJJAS 2026 has May and June only.**
- **The last complete MJJAS in the archive is 2025.**

That is exactly `year_last: 2025`, and 47 × 153 = 7 191 is exactly the day count the classification
produced. **Ruling R3 needs no revision.** The campaign covers every complete MJJAS season the
archive holds, with nothing dropped and nothing padded.

---

## 8. What the data did that the plan did not predict

Five items, in descending order of how much they matter.

1. **The 2018 profile matched the CDS baseline bit-exactly, which §A1.7 asserted was impossible.**
   The addendum predicted comparison 3 would land near **1.9e-4 m/s** and stated flatly that "a
   bit-exact profile match is therefore impossible and must not be pursued", reasoning from the
   evidence files' bytes-per-point (1.88) that the CDS operands were `int16`-packed and that a
   ±100 m/s int16 range would leave a ≈ 4e-5 m/s quantization floor after averaging. The measured
   answer through the real code path is **0.000e+00 m/s at every one of 33 813 points**. The
   file-size arithmetic was a plausible inference that did not survive contact with the real
   pipeline; the Gate-1 probe's 1.907e-4 m/s came from a float64 accumulation outside the pipeline,
   which §A1.7 itself flagged as "not the executor's measurement". The prediction was wrong in the
   safe direction — the tolerance was never approached — but it was wrong, and `docs/rda_archive_notes.md`
   §8 still states the impossibility claim. Recorded here as a factual discrepancy between the
   addendum's expectation and the measurement; no artifact is edited to resolve it.
   Consequence worth noting: risk **DR1** (a marginal 2018 day flipping on a ~2e-4 perturbation)
   could not fire, because there was no perturbation at all.
2. **The month structure is the dominant source of variation, and the plan never mentioned it.**
   67.9 % in May against 28.0 % in August is a 39.9 pp span — five times the 8.0 pp season-to-season
   standard deviation. Any reading of the double-jet fraction that does not condition on calendar
   month is averaging over the largest effect in the dataset. The plan framed the deliverable as a
   fraction plus a per-season figure; the per-month decomposition is where the signal is.
3. **The smoke season was the extreme of the record on both reported statistics simultaneously.**
   MJJAS 2018 has the highest double-jet fraction of the 47 seasons (62.7 % against a 45.1 % record
   value) *and* the lowest core-latitude in-band fraction (81.4 % against 88.2 %). Those are not two
   coincidences: double days generate the out-of-band cores, so the season with the most double days
   is the season with the worst diagnostic. The plan chose 2018 as the smoke season for reasons of
   convenience and warned that its numbers were not a target; it turns out to have picked the single
   least representative season available, which makes the warning load-bearing rather than
   boilerplate.
4. **`$PBS_NCPUS` was not set inside the job.** §A5.2 step 2 assumed PBS would export it and treated
   it as the authoritative worker count, with `cfg.rda.workers` as the fallback. `logs/campaign.out`
   records `PBS_NCPUS : <unset>` and every season line reads "8 worker process(es) (from
   `cfg.rda.workers`)". The fallback did its job and the two sources agreed at 8, so the run used
   exactly the requested shape — but the mechanism the addendum expected to be primary never
   engaged, and a future job whose `ncpus` differs from `cfg.rda.workers` would silently use the
   config value. Worth knowing before anyone changes the requested shape.
5. **The campaign finished faster than §A10.1's estimate and used more memory than §A1.3's.**
   End-to-end was **57 min 23 s** against the addendum's "near 1.5 h", because the downstream stages
   cost 31 s rather than the minutes extrapolated from Stampede3. Per-season loader time was
   **73.2 s** against the Gate-1 probe's 65.8 s — about 11 % slower per season on a shared
   filesystem, which is well inside the noise the estimate allowed for. Peak memory was **3.94 GB**
   against the probe's 2.49 GB, still 6 % of the 64 GB requested; the difference is the concatenated
   intermediate and the 47-panel figure, neither of which the read-only probe built. None of this
   threatens anything — the job used a twelfth of its walltime and a sixteenth of its memory — but
   the §A10.1 tripwire is unchanged: at the 4.69 s/day serial rate the same work is 9.37 h, and if
   parallelism is ever disabled the campaign no longer fits one job.

---

## 9. What remains for the operator

1. **Rule on the core-latitude diagnostic (plan §10 E3, addendum O2).** The 47-season number
   requested by O2 is **88.2 %** against a ≥ 95 % target, set against the smoke season's **81.4 %**;
   §5 is the decomposition. No band has been moved and no move is recommended. This is the one open
   escalation the campaign produced.
2. **Nothing else is blocked.** The double-jet gate passed (0.4514 in 5–90 %), the §A9 regression
   passed on all three arms, ruling R3 is confirmed by the archive inventory, and all seven §A12
   deliverables exist. Job `7321579` exited 0.
3. **Two housekeeping observations, neither requiring a decision now:** the `$PBS_NCPUS` fallback of
   §8 item 4 is a latent inconsistency if the job shape is ever changed, and
   `docs/rda_archive_notes.md` §8 and addendum §A1.7 still carry the "bit-exact match is impossible"
   claim that §6.2 measured to be false. Both are recorded rather than edited, because both live in
   reviewed documents.

---

## Provenance of the numbers in this document

| Source | What was taken from it |
|---|---|
| `data/jet_states_summary.txt` | 7 191 / 3 246 / 3 932 / 13, fraction 0.4514, gate PASS, 88.2 % of 10 424 cores, 1 227 out-of-band, the worst-offenders list |
| `data/jet_states_mjjas_1979-2025.csv` | every per-month, per-season and per-core figure in §2–§5, computed with pandas |
| `data/u250_natl_mjjas_1979-2025.nc` | provenance attributes; the I5 plausibility statistic, recomputed with `double_jet.classify.smooth` at 11 points |
| `data/smoke_2018_regression.json` | §6.2's three comparisons and their achieved values |
| `logs/campaign.out` | job identity, per-season loader timings, worker source, stage boundaries, figure sizes |
| Established for this write-up | job `7321579`, exit 0, walltime 00:57:23, peak memory 3.94 GB, 1 node / 8 cpus |
| `wave1-plan-derecho-addendum.md` §A1.2, §A1.3, §A1.7 | the archive inventory, the Gate-1 timings, the superseded 1.9e-4 prediction |
