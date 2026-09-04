# CLAUDE.md — double-jet-natl

Repo invariants. The parent `~/projects/CLAUDE.md` and `wave1-plan.md` govern everything else;
this file records only what is specific to this repo and must not drift.

**This repo is now dual-site.** The pipeline was built and smoke-tested on TACC Stampede3; the
47-season campaign moved to NCAR Derecho on 2026-09-04 (deviation D3). **Read `HANDOFF.md` first**
— it carries the current brief, the stage-1 seam, and the compute authorization. Top-level
`jobs/*.slurm` are Stampede3/SLURM; Derecho/PBS scripts belong in `jobs/derecho/`.

## The plan is the contract

`wave1-plan.md` (identical to `docs/plans/2026-09-03_wave1_plan.md`) is post-Gate-4 and reviewed.
Do not reopen its rulings (§0 R1–R3, §2 I1–I7). If the code contradicts it, stop and say so.

One exception, on the operator's explicit authority: **R1 is superseded by deviation D3** — the
daily mean is now computed locally from the archived hourly product rather than retrieved from the
CDS derived product. The definition of the daily mean is unchanged, and R1's own gate measured the
two bit-identical (`max_abs_diff = 0.0`, 12 206 493 points). R2, R3 and I1–I7 all still stand.

## Frozen numbers — all live in `configs/double_jet.yaml`, nowhere else

Sector 60°W–30°E × 20–75°N at 0.25° (361 × 221 points) · level 250 hPa · MJJAS · 1979–2025
(47 seasons, 7 191 days) · boxcar 2.5° = 11 grid points · `U_core_min` 15 m/s · separation 10° ·
prominence 5 m/s · double-jet fraction gate 5–90 % · core-latitude diagnostic ≥ 95 % in 25–70 °N
(reported, not a gate — plan §0 R2).

Changing any of these is an escalation (plan §11), not a code edit.

## Entry point

    python -m double_jet --config configs/double_jet.yaml [--smoke | --stage ... | --skip-download]

`scripts/double_jet.py` is a documented shim only. Nothing is pip-installed; the interpreter is
`/work2/11114/zhixingliu/stampede3/conda-envs/graphcast/bin/python` (butterfly's shared env, used
read-only — plan §1.9). Do not install into it or build a new env without asking.

## Storage

Raw ERA5 → `$SCRATCH/double-jet-natl/era5_raw/` only. Never under `$HOME` or `$WORK`.
The intermediate `data/u250_natl_mjjas_1979-2025.nc` is the only thing downstream stages read.

One deliberate exception: the 2018 R1 evidence pair is preserved at
`/work2/11114/zhixingliu/double-jet-natl/era5_r1_evidence/` (123 MB, with `SHA256SUMS`) because
`$SCRATCH` purges on inactivity and it is the provenance for the only R1 measurement that exists.

`data/`, `figs/` and `logs/` are gitignored. `results/` is tracked and holds the smoke-2018
baseline and the job logs — the regression evidence a fresh clone would otherwise not have.

## Compute

Never on a login node. `jobs/smoke_2018.slurm` (skx-dev, 2 CDS requests) is pre-authorized.
`jobs/download_all.slurm` (skx, 47 CDS requests) needs the operator's explicit go, every time —
and is superseded in practice by D3: it timed out at ~1 season/hour and is not to be resubmitted.

On Derecho the campaign is pre-authorized at one stated shape only; `HANDOFF.md` §7 has the exact
terms and the conditions attached to them. Anything larger is an escalation.
