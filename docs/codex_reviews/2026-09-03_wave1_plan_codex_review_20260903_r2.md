## Strengths

- The R1 gate now normalizes both operands, uses exact coordinate alignment, and verifies all `153 × 221 × 361` values ([plan:339](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:339)).
- Grid sequences, physical units, and finite values are now hard-gated ([plan:358](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:358)). These checks match the inspected sibling ERA5 file.
- The canonical module entry point and Slurm prologue correctly establish the repo and conda environment ([plan:281](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:281), [plan:478](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:478)).
- `wave1.md` now exists, and the `skx`/`skx-dev` network distinction is accurately carried into the jobs.
- The current CDS request design remains consistent with the official [daily-statistics documentation](https://confluence.ecmwf.int/pages/viewpage.action?pageId=505382220).

## Issues

### P0

None.

### P1

1. **The advertised batch alternative for a threshold-only rerun still executes the complete download stage.** The plan says such a rerun touches neither raw data nor `$SCRATCH`, then offers “resubmit the same job script” ([plan:537](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:537)). That script is specified to run `--stage all` over 47 seasons ([plan:526](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:526)). If Scratch was purged, this silently launches all 47 requests again; even if intact, it unnecessarily validates the raw cache. It is also a production-queue submission requiring fresh approval under [CLAUDE.md:42](/home1/11114/zhixingliu/projects/CLAUDE.md:42). This leaves the round-1 “postprocessing after Scratch purge” fix only partially applied.

### P2

1. **The output-namespace fix is not applied to the summary and campaign figures.** Section 4.2 claims every output name derives from the actual year range ([plan:385](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:385)), but §4.4 and §4.5 retain fixed `jet_states_summary.txt` and `double_jet_natl_panels.{pdf,png}` names ([plan:424](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:424), [plan:437](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:437)). A non-smoke `--years` subset can therefore overwrite campaign outputs. The proposed test checks only smoke versus campaign, not subset versus campaign ([plan:467](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:467)).

2. **Cache acceptance still ignores the retained ZIP deliverable.** A season is skipped based only on the `.nc` and request sidecar ([plan:320](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:320)), while the ZIP is promised as retained output and part of M1 ([plan:317](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:317), [plan:585](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:585)). A missing ZIP is thus silently accepted and cannot be restored by rerunning the documented command.

3. **The revised plateau decision remains internally inconsistent.** I3 explicitly includes the midpoint of a flat peak ([plan:234](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:234)), but the implementation step still calls the peaks “strict interior maxima” ([plan:403](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:403)), and no plateau test locks in the chosen behavior ([plan:453](/home1/11114/zhixingliu/projects/double-jet-natl/docs/plans/2026-09-03_wave1_plan.md:453)). This does not challenge the chosen `find_peaks` behavior; it flags contradictory executor guidance.

## Suggested edits

1. Delete “or resubmit the same job script” from the threshold-rerun instructions. The existing `idev` classify/figure command is sufficient and avoids another mechanism.
2. Preserve the contract’s fixed names for the full campaign, but give every non-smoke subset year-qualified summary and figure names. Test full, smoke, and subset namespaces pairwise.
3. Either require the ZIP to exist and validate before skipping, or simplify by treating it only as a temporary extraction file and removing it from M1/storage promises.
4. Replace “strict interior maxima” with wording that explicitly includes I3’s plateau midpoint, and add one above-threshold flat-top test.

verdict: CHANGES_REQUESTED