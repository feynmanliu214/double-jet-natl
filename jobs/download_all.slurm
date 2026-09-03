#!/bin/bash
# #############################################################################
# ##                                                                         ##
# ##   S T O P  --  T H I S  I S  N O T  P R E - A U T H O R I Z E D         ##
# ##                                                                         ##
# ##   This script requires the operator's EXPLICIT approval EVERY TIME it   ##
# ##   is submitted (wave1-plan.md §10 E1, §5.3; CLAUDE.md "production and   ##
# ##   full-campaign submission requires my explicit approval, every time"). ##
# ##   A green smoke run is not approval. A previous approval is not         ##
# ##   approval. Ask, every time.                                            ##
# ##                                                                         ##
# ##   It issues 47 CDS requests (one per MJJAS season, 1979-2025) at <= 3    ##
# ##   in flight. It is a production-queue submission and is NOT a smoke      ##
# ##   job at any size.                                                      ##
# ##                                                                         ##
# ##   DO NOT USE THIS SCRIPT FOR A THRESHOLD-ONLY RE-RUN.                   ##
# ##   It is pinned to `--stage all`, so after a $SCRATCH purge it would     ##
# ##   silently re-issue all 47 requests. A threshold change touches no raw  ##
# ##   file: run this in `idev` instead, it takes about a second --          ##
# ##                                                                         ##
# ##     python -m double_jet --config configs/double_jet.yaml \             ##
# ##            --skip-download --stage classify,figure                      ##
# ##                                                                         ##
# #############################################################################
#
# wave1-plan.md §5.3 -- the 47-season campaign.
# Cost: 1 skx node for <= 4 h (~4 SUs/node-hour against 107023 available) and
# 47 CDS requests. Produces M1, M3, M4, M5, M7: the raw cache on $SCRATCH, the
# intermediate data/u250_natl_mjjas_1979-2025.nc, the states CSV, the sanity
# block, and figs/double_jet_natl_panels.{pdf,png}.
#SBATCH -J djet_download_all
#SBATCH -A TG-ATM170020
#SBATCH -p skx
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -t 04:00:00
#SBATCH -o logs/download_all_%j.out
#SBATCH -e logs/download_all_%j.err
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

# --- the run: plan §5.3 -- 47 CDS requests, then profile, classify, figure ---
python -m double_jet --config configs/double_jet.yaml --stage all
