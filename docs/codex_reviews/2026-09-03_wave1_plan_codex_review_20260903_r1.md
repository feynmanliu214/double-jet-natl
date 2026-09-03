## Strengths

- The plan clearly records and consistently applies operator rulings R1–R3 and interpretations I1–I7.
- The ERA5 dataset, 6-hourly aggregation, ZIP output, 0.25° resolution, and current CDS request conventions agree with the official [CDS product documentation](https://cds.climate.copernicus.eu/datasets/derived-era5-pressure-levels-daily-statistics?tab=overview).
- The stated environment versions and the cited ERA5 sample’s coordinates, encoding, and units match the files inspected.
- Resource requests respect allocation, queue, walltime, smoke-budget, dependency, and approval constraints.
- Separating retrieval, unsmoothed profiles, classification, and plotting supports inexpensive threshold reruns.

## Issues

### P0

None.

### P1

1. **The R1 equivalence gate can silently compare only a coordinate intersection.** The plan acknowledges that longitude convention is unverified ([plan:127](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:127)), but the comparison is specified before either product is normalized or exact coordinate identity is required ([plan:302](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:302)). Installed xarray defaults binary arithmetic to an inner coordinate join ([options.py:80](/work2/11114/zhixingliu/stampede3/conda-envs/graphcast/lib/python3.11/site-packages/xarray/core/options.py:80)); therefore 300…30 versus −60…30 could compare only the overlapping longitudes and falsely satisfy the “all 361 points” gate. This behavior is also documented by [xarray](https://docs.xarray.dev/en/stable/generated/xarray.set_options.html).

2. **The ingestion gates do not establish the physical grid or units on which the metric depends.** Validation checks only coordinate counts/bounds, pressure value 250, and NaNs ([plan:323](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:323)). It never asserts exact 0.25° coordinate sequences, coordinate units, pressure units, or wind units, despite interpreting 11 samples as 2.5° and applying thresholds in m s⁻¹ ([plan:220](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:220), [plan:349](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:349)). A nonuniform 221-point grid or incorrectly unit-tagged field can pass and silently change the science.

3. **The storage layout violates the parent project invariant.** This challenges §6 based on concrete machine policy. The plan calls the Scratch files a deliverable, says the intermediate “survives,” and puts persistent data and figures under `$HOME` ([plan:455](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:455), [plan:482](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:482)). The parent instructions require surviving artifacts in `$WORK`, identify Scratch as purgeable, and state that `$HOME` is not a data filesystem ([CLAUDE.md:50](/home1/11114/zhixingliu/projects/CLAUDE.md:50)). This is a policy contradiction, not a capacity concern.

4. **The documented entry point and jobs are not executable deterministically as specified.** The three-line `scripts/double_jet.py` has no planned CLI/orchestration module and is invoked directly ([plan:242](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:242), [plan:262](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:262)). Direct execution puts `scripts/`, not the repository root, on `sys.path`; no package installation or root injection is planned. The jobs also use bare `python` without specifying environment activation ([plan:418](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:418)); currently bare `python` lacks `cdsapi`. The sibling’s proven convention explicitly changes directory and activates the environment ([submit_lead30_smoke.sh:38](/home1/11114/zhixingliu/projects/butterfly/jobs/stampede3/submit_lead30_smoke.sh:38), [submit_lead30_smoke.sh:46](/home1/11114/zhixingliu/projects/butterfly/jobs/stampede3/submit_lead30_smoke.sh:46)).

5. **Challenges user-approved I3: `find_peaks` alone is not a strict-maximum implementation.** I3 specifies strict interior maxima through `find_peaks` ([plan:222](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:222)), but SciPy returns the midpoint of a flat-topped peak ([installed source:837](/work2/11114/zhixingliu/stampede3/conda-envs/graphcast/lib/python3.11/site-packages/scipy/signal/_peak_finding.py:837); [SciPy documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.find_peaks.html)). Thus the selected implementation contradicts the approved strictness definition.

### P2

1. **Cache acceptance is too weak and does not verify its claimed deliverables.** A valid-shaped `.nc` causes a skip even if its request differs or the ZIP/request JSON is missing ([plan:291](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:291)), contradicting M1’s artifact claim. The 6-hourly cache has no stated resume validation. Because these are recoverable downloads, this is P2, but request identity is needed to prevent silent stale reuse.

2. **Smoke and campaign output namespaces are incomplete.** Only the profile and figure receive smoke-specific names; classification and summary have fixed campaign names ([plan:359](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:359), [plan:423](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:423)). A later smoke or threshold rerun can overwrite production CSV/summary/figures. The achieved one-time R1 result also lacks an unambiguously durable, smoke-specific record.

3. **The promised verbatim `wave1.md` cannot be created by the executor.** The prompt was never written to disk and the executor receives only the plan and `CLAUDE.md` ([plan:4](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:4), [plan:10](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:10)), yet execution requires creating a verbatim copy ([plan:512](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:512)).

4. **Network access was proven on `skx`, not the smoke partition.** The successful probe used `skx`, while the `skx-dev` probe was cancelled ([plan:159](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:159), [plan:175](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:175)); smoke runs on `skx-dev` ([plan:415](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:415)). This is recoverable within the smoke budget, but “settled” is overstated.

5. **Tests omit the riskiest new interfaces.** Only classification and config tests are planned ([plan:387](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:387)). There are no synthetic tests for ZIP extraction, cache identity, exact coordinate normalization/alignment, unit rejection, CLI imports, or smoke/campaign output separation.

## Suggested edits

1. Normalize both R1 operands through one reader, assert exact timestamps and exact coordinates, then use `xr.align(..., join="exact")` before calculating the maximum difference.
2. Require exact expected latitude/longitude arrays, `hPa` pressure units, m s⁻¹ wind units, and finite—not merely non-NaN—values.
3. Keep disposable raw downloads on Scratch, but place the intermediate, CSV, summaries, validation record, and figures in an explicit `$WORK` output root. If M1 must survive, store it in `$WORK`; otherwise describe it as a cache, not a durable deliverable.
4. Add `double_jet/cli.py` or `double_jet/__main__.py` and invoke it with the absolute environment interpreter using `python -m double_jet`. Specify the job prologue: `set -euo pipefail`, SLURM guard, repository `cd`, environment activation, and pre-submission creation of `logs/`.
5. Enforce I3 with `plateau_size=(None, 1)` or explicit strict-neighbor comparisons, plus an above-threshold plateau test.
6. Validate cache request sidecars and all promised artifacts; use partial files plus atomic rename. Make classify/figure-only stages depend solely on the persistent intermediate even after Scratch purge.
7. Give smoke outputs their own CSV, summary, and validation JSON. Refuse overwriting outputs produced by a different config hash unless explicitly requested.
8. Have the planning session materialize `wave1.md` before handoff, and describe `skx-dev` network access as first-smoke validation rather than already proven.

verdict: CHANGES_REQUESTED