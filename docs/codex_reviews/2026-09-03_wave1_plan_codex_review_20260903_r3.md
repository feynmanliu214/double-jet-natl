## Strengths

- The round-2 threshold-rerun fix is substantively applied: the documented rerun is now compute-only and the production job requires fresh approval.
- ZIP files are consistently treated as incidental, while `.nc` plus request JSON remain the validated cache artifacts.
- Full, smoke, and ordinary subset outputs now have separate namespaces.
- Plateau handling and its regression test now agree.
- CDS keys remain consistent with the live [daily](https://cds.climate.copernicus.eu/api/retrieve/v1/processes/derived-era5-pressure-levels-daily-statistics) and [hourly](https://cds.climate.copernicus.eu/api/retrieve/v1/processes/reanalysis-era5-pressure-levels) schemas. The environment and Slurm prologue also match the inspected installation and sibling convention ([submit_lead30_smoke.sh:25](/home1/11114/zhixingliu/projects/butterfly/jobs/stampede3/submit_lead30_smoke.sh:25)).

## Issues

### P0

None.

### P1

None.

### P2

1. **A newly added safety statement incorrectly says only the campaign script issues CDS requests.** `smoke_2018.slurm` invokes `--smoke`, which explicitly performs two requests ([plan:528](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:528)), while §5.3 calls `download_all.slurm` the only requesting script ([plan:563](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:563)). The wave prompt likewise requires the smoke request ([wave1.md:97](/home1/11114/zhixingliu/projects/double-jet-natl/wave1.md:97)). This is new contradictory operator guidance introduced while applying P1-1.

2. **Endpoint-only subset names do not establish the claimed collision guarantee.** Nothing defines `--years` as necessarily contiguous. A subset containing 1979 and 2025 but omitting interior years would enter the subset row yet receive the same `<first>-<last>` names as production ([plan:389](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:389)). Testing only “a subset” does not cover that case ([plan:483](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:483)). Thus the round-2 namespace fix remains implementation-dependent despite R12 claiming all subsets are safe ([plan:639](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:639)).

3. **The new “one function owns every output path” contract is broader than its table.** The table covers derived artifacts only ([plan:389](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:389)); raw ZIP/NC/JSON names are assigned under `download.py` ([plan:318](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:318)), and Slurm log paths are separate outputs ([plan:588](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:588)). Requiring the CLI helper to own those paths would be unnecessary coupling; leaving them elsewhere would violate the literal plan.

## Suggested edits

1. Change “the only script … that issues a CDS request” to “the only full-campaign script,” or delete that sentence.
2. Define `--years` as a validated inclusive contiguous range, with full-campaign detection based on exact equality to `1979…2025`. If arbitrary year lists are intended, encode the complete set or a hash in subset names. Add a same-endpoints/missing-interior test.
3. Narrow the ownership claim to “all derived `data/` and `figs/` output paths”; let `download.py` own raw-cache names and the job headers own log names.

verdict: CHANGES_REQUESTED