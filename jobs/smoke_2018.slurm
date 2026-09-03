#!/bin/bash
# =============================================================================
# wave1-plan.md §5.2 -- the smoke job. PRE-AUTHORIZED as submission 1 of 5.
#
# Cost: 1 skx-dev node for <= 30 min (~2 SUs) and exactly TWO CDS requests --
# the derived-daily product for MJJAS 2018 (153 fields) and the 6-hourly
# product for the same season (612 fields, the R1 equivalence cross-check).
# No other season is touched. Then: profile -> classify -> figs/smoke_2018.png.
#
# The wave stops here and reports (plan §5.2). A green smoke run is NOT
# approval to submit jobs/download_all.slurm.
# =============================================================================
#SBATCH -J djet_smoke2018
#SBATCH -A TG-ATM170020
#SBATCH -p skx-dev
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -t 00:30:00
#SBATCH -o logs/smoke_2018_%j.out
#SBATCH -e logs/smoke_2018_%j.err
# logs/ must already exist at submit time: Slurm opens -o/-e before the job
# body runs, so the prologue's `cd` is too late to create it (plan §3, §5.0).

set -euo pipefail
[[ -n "${SLURM_JOB_ID:-}" ]] || { echo "ALARM: run via sbatch, not on a login node." >&2; exit 2; }
cd /home1/11114/zhixingliu/projects/double-jet-natl
module purge
source /work2/11114/zhixingliu/stampede3/miniforge3/etc/profile.d/conda.sh
conda activate /work2/11114/zhixingliu/stampede3/conda-envs/graphcast
python -c 'import cdsapi, xarray, scipy, matplotlib'                      # env is what we think it is
python -m double_jet --config configs/double_jet.yaml --preflight-network  # §1.8; exits 2 on failure

# --- the run: plan §5.2 ------------------------------------------------------
python -m double_jet --config configs/double_jet.yaml --smoke
