# DJET-NATL — Wave 1 of 1: ERA5 double-jet vs single-jet time series, North Atlantic–Europe

**Status**: ready

## Objective

Produce a figure showing, day by day over extended summer (MJJAS) 1979–present, when the upper-level
jet over the North Atlantic–Europe sector is split into two cores and when those cores merge into one.
Descriptive, not hypothesis-testing: the deliverable is a trustworthy daily classification and a
plot on which the merges are visible.

## Scientific contract

All quantities come from ERA5 zonal wind at 250 hPa on the native 0.25° grid. Daily mean = average of
the 00, 06, 12, 18 UTC analyses (6-hourly is sufficient for a jet-core classification and is 4× cheaper
to download than hourly; if CDS offers a pre-computed daily-mean product for this variable and level,
use that instead — confirm at Gate 1).

| Quantity | Definition | Parameter |
|---|---|---|
| Sector profile U(φ, t) | Daily-mean u at 250 hPa, zonally averaged over 60°W–30°E (equal weight per longitude), for φ in 20–75°N | lon bounds, lat bounds |
| Smoothed profile | U(φ, t) boxcar-smoothed in latitude with a 2.5° window before any peak detection | window = 2.5° |
| Jet core | Local maximum of the smoothed profile with U ≥ 15 m/s | U_core_min = 15 m/s |
| Double-jet day | ≥ 2 cores whose latitudes differ by ≥ 10°, and the smoothed-profile minimum between them is ≤ (weaker core − 5 m/s). If more than two cores qualify, keep the two strongest that satisfy the separation rule | sep_min = 10°, prominence = 5 m/s |
| Single-jet day | Exactly one core, or several cores that fail the double-jet test (report only the strongest) | — |
| No-jet day | No core ≥ U_core_min | — |

Every parameter above lives in one config block; changing a threshold and re-running must not touch
the raw ERA5 files again (see cached intermediate under Deliverables).

Sanity checks — the classification is usable only if all hold; a failure means the thresholds or the
data pipeline are wrong, not a result:

- Double-jet fraction over all MJJAS days 1979–2025 lies in 5–90%.
- ≥ 95% of core latitudes fall within 25–70°N.
- The smoothed profile on the smoke season (MJJAS 2018) shows a plausible mid-latitude jet (peak
  20–40 m/s) — inspect it before trusting anything downstream.
- The sector covers 60°W–30°E at 0.25°: assert 361 longitude points and read min/max longitude from
  the file rather than assuming the sign convention CDS used.
- The level is selected by reading the pressure coordinate and asserting 250 hPa, never by index.

## Context

- **Machine**: Stampede3 (Derecho is down for maintenance; the NCAR RDA mirror is not an option).
- **Repo / branch**: `/home1/11114/zhixingliu/projects/double-jet-natl/` (new; `main`). This is under
  `$HOME`, which has a small quota — code and the few-MB intermediate only.
- **Data source**: Copernicus CDS API, dataset `reanalysis-era5-pressure-levels` (or the derived
  daily-statistics product if it exists for u at 250 hPa), variable u-component of wind, level 250,
  subset server-side to area N75 / W-60 / S20 / E30, months May–Sep. Confirm at Gate 1: the current
  CDS API request keys and output format (the CDS was re-platformed in 2024 and old request syntax is
  invalid), the size of one season's subset, and that `~/.cdsapirc` with a valid token exists.
- **Storage contract**: raw downloads go to `$SCRATCH/<project>/era5_raw/`, one file per season-year,
  written idempotently (skip files that exist and pass a size/open check). The cached intermediate
  profile (a few MB) goes to the repo's `data/`. No raw ERA5 under `$HOME` or `$WORK`, ever. Raw files are not deleted by the pipeline; `$SCRATCH` purge handles them once the intermediate
  is validated and copied out.
- **Entry points to read first**: any existing ERA5 / CDS download or subsetting utility in the repo
  (reuse rather than reimplement); check whether a u250 or MJJAS ERA5 subset already exists anywhere
  under the group's `$WORK` or `$SCRATCH` before downloading a single byte.
- **Prior runs this must stay consistent with**: none.

## Non-goals

- No trend, persistence, or duration statistics on the jet states.
- No linkage to heatwaves, blocking, or any other field.
- No other pressure levels, sectors, or seasons; the Eurasian sector of Rousi et al. is explicitly out.
- No global or full-year downloads — every CDS request carries the area, level, and month subset.
- No temporal smoothing of the daily state.

## Workflow — follow these gates in order

**Gate 1 — Inspect.** Read the entry points above. Report what you actually found: existing local
ERA5 subsets, the CDS dataset and request syntax that actually works today, the size and queue wait of
one season's request, whether Stampede3 compute nodes have outbound access for the download job,
grid and coordinate conventions of the returned file (longitude sign, latitude ordering, level
coordinate name, packing), and the last date available. Write no code in this phase.

**Gate 2 — Interview.** Ask me about ambiguities that inspection actually surfaced — things the
design could not have anticipated without seeing the data or the CDS. The design questions are
settled in the Scientific contract above; if a question you want to ask doesn't trace back to
something you found, check there first, because it is probably answered. Batch what remains,
multiple choice with a recommended default. Ask only about choices that affect what gets classified;
decide engineering details yourself. Having no questions is a valid outcome — say so and move to
Gate 3.

**Gate 3 — Plan.** Produce an implementation plan: files touched, new modules, execution sequence,
how each deliverable gets produced and verified, and where each byte lands. Stop there and wait for
my approval. No code at any point in this session.

**Gate 4 — Review.** Run `/codex-review-plan` on the approved plan. Address each finding, or state
why it does not apply, then write the revised plan to `wave1-plan.md` next to this file, following
`references/plan-template.md`.

**This session ends there.** A different session executes, and it will not have this file or this
conversation — only `wave1-plan.md` and `CLAUDE.md`. Everything you and I settled here that the
executor needs has to be in that plan file. Do not begin implementing.

## Smoke jobs

The plan must carry this shape forward: one CDS request for MJJAS 2018 (sector, 250 hPa, 6-hourly),
then extraction, classification, and a single-panel figure — run as one short batch job or `idev`
session, not on a login node; expected wall time is dominated by the CDS queue, minutes to an hour.
The full 1979–present download is ~47 such requests and is the only step large enough to be a
standalone batch job.

The submission budget at that shape, and the approval rules for anything larger, are in `CLAUDE.md`.

## Deliverables and output contract

- `$SCRATCH/<project>/era5_raw/u250_natl_mjjas_<year>.nc` — one raw subset per season-year, the
  request dictionary that produced it saved alongside as JSON.
- `data/u250_natl_mjjas_1979-<last>.nc` — the daily sector-mean profile U(φ, t), unsmoothed, with
  attributes recording sector bounds, level, source dataset and the list of source files. This is the
  cached intermediate; every downstream step reads it, never the raw files.
- `data/jet_states_mjjas_1979-<last>.csv` — one row per day: date, state (double | single | none),
  lat_1, u_1, lat_2, u_2, interjet_min. Cores ordered south to north.
- `figs/double_jet_natl_panels.pdf` and `.png` — one panel per season (grid of ~8 × 6), each with
  x = date from 1 May to 30 Sep, y = latitude 20–75°N, the smoothed profile as a grey pcolormesh
  background, and jet cores as points colored by state (single vs double; none-days left blank).
  Shared axes, one legend, the config thresholds printed in the figure title or margin.
- `figs/smoke_2018.png` — the same panel for the smoke season alone, produced first.
- One documented command (`python scripts/double_jet.py --config <yaml>` or equivalent) that
  reproduces all of the above end to end, with `--skip-download` reusing whatever is already on
  `$SCRATCH`.

Every deliverable must be reproducible from a single documented command.

## Wave-specific constraints

- The download step runs on a compute node (batch or `idev`), never on a login node, and at most
  3 CDS requests in flight at once — the CDS throttles per user anyway, and this keeps the filesystem
  write load negligible.
- Nothing raw is written under `$HOME` or `$WORK`; the plan must state the target path of every
  output before approval.
- CDS access is a prerequisite I handle before execution: `~/.cdsapirc` with a current personal
  access token, and the ERA5 licence accepted on the CDS profile. If either is missing at Gate 1,
  report it and continue planning; do not work around it.
