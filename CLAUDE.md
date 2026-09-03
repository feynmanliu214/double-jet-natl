# CLAUDE.md — double-jet-natl

Repo invariants. The parent `~/projects/CLAUDE.md` and `wave1-plan.md` govern everything else;
this file records only what is specific to this repo and must not drift.

## The plan is the contract

`wave1-plan.md` (identical to `docs/plans/2026-09-03_wave1_plan.md`) is post-Gate-4 and reviewed.
Do not reopen its rulings (§0 R1–R3, §2 I1–I7). If the code contradicts it, stop and say so.

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

## Compute

Never on a login node. `jobs/smoke_2018.slurm` (skx-dev, 2 CDS requests) is pre-authorized.
`jobs/download_all.slurm` (skx, 47 CDS requests) needs the operator's explicit go, every time.
