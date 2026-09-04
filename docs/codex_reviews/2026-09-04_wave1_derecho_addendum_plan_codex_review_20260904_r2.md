## Strengths

- The proposed season file satisfies all eight `open_normalized` gates: recognized names, scalar 250 hPa level, one `u` variable, canonical grids, copied accepted units, exact assembled dates, finite values, and canonical dimension order ([profile.py](/glade/u/home/zhil/project/double-jet-natl/double_jet/profile.py:156), [addendum](/glade/u/home/zhil/project/double-jet-natl/docs/plans/2026-09-04_wave1_derecho_addendum_plan.md:299)).
- Reusing `_check_shape` with a scalar level is valid because it examines only time/latitude/longitude dimensions. Separating inventory comparison from `_canonical_request` also avoids its unsuitable nested-dictionary handling ([download.py](/glade/u/home/zhil/project/double-jet-natl/double_jet/download.py:147), [download.py](/glade/u/home/zhil/project/double-jet-natl/double_jet/download.py:182)).
- The CDS-assumption sweep is substantially correct: outside `download.py`/`config.py`, the necessary provenance fixes are the two `profile.py` values and the figure label; `classify.py` only consumes `profile_sha256` ([profile.py](/glade/u/home/zhil/project/double-jet-natl/double_jet/profile.py:334), [profile.py](/glade/u/home/zhil/project/double-jet-natl/double_jet/profile.py:391), [figure.py](/glade/u/home/zhil/project/double-jet-natl/double_jet/figure.py:252), [classify.py](/glade/u/home/zhil/project/double-jet-natl/double_jet/classify.py:341)).
- The committed regression operands exist with the claimed schemas, and generated outputs remain under ignored `data/`/`figs/`, separate from tracked `results/` ([cli.py](/glade/u/home/zhil/project/double-jet-natl/double_jet/cli.py:58), [.gitignore](/glade/u/home/zhil/project/double-jet-natl/.gitignore:1)).
- The round-1 fixes for exact profile alignment, 33,813-point counting, split validate/materialize dispatch, and pre-publication seam checking are correctly incorporated.

## Issues

### P0

None.

### P1

1. **The new `OutputNames.regression` still breaks an existing test that the plan forbids editing.** The addendum keeps the existing smoke `r1_validation`, sets `regression` for smoke, and adds both non-`None` fields to `all_paths()` ([addendum](/glade/u/home/zhil/project/double-jet-natl/docs/plans/2026-09-04_wave1_derecho_addendum_plan.md:504)). That produces six smoke paths, while the untouched test asserts exactly five ([test_config.py](/glade/u/home/zhil/project/double-jet-natl/tests/test_config.py:162)). This contradicts the claim that `test_config.py` remains untouched and the suite stays green.

2. **Round-1’s regression-placement fix remains unsafe for supported stage subsets.** `--stage` accepts arbitrary subsets ([cli.py](/glade/u/home/zhil/project/double-jet-natl/double_jet/cli.py:105), [test_cli.py](/glade/u/home/zhil/project/double-jet-natl/tests/test_cli.py:72)), but the addendum only says to run the RDA regression after the figure block, before the final return ([addendum](/glade/u/home/zhil/project/double-jet-natl/docs/plans/2026-09-04_wave1_derecho_addendum_plan.md:492)). An unconditional `--smoke --stage download` then lacks all three operands; `--smoke --stage figure` can compare stale profile/CSV/summary files. Thus the clean all-stage path is fixed, but the stale-operand defect remains for partial-stage invocations.

3. **The figure-label fix is simultaneously authorized and prohibited.** §A0 authorizes one `figure.py` provenance edit, then states that no change to `figure.py` is authorized ([addendum](/glade/u/home/zhil/project/double-jet-natl/docs/plans/2026-09-04_wave1_derecho_addendum_plan.md:27), [addendum](/glade/u/home/zhil/project/double-jet-natl/docs/plans/2026-09-04_wave1_derecho_addendum_plan.md:33)). Obeying the prohibition leaves the known false CDS label in place ([figure.py](/glade/u/home/zhil/project/double-jet-natl/double_jet/figure.py:252)).

### P2

1. **The fixture edit is ambiguously described.** Calling `raw.setdefault("source", "cds_derived")` would do nothing once the shipped YAML already contains `source: rda_hourly`. The helper currently loads the YAML and then applies `overrides` ([test_profile.py](/glade/u/home/zhil/project/double-jet-natl/tests/test_profile.py:54)); the plan should name the effective one-line operation explicitly.

2. **Several round-1 edits were not propagated through the document.** §A8 allows one existing-test change, while §A14 still says all 63 pre-existing tests remain unedited ([addendum](/glade/u/home/zhil/project/double-jet-natl/docs/plans/2026-09-04_wave1_derecho_addendum_plan.md:576), [addendum](/glade/u/home/zhil/project/double-jet-natl/docs/plans/2026-09-04_wave1_derecho_addendum_plan.md:809)). §A5 still describes dispatch “on one name” despite the new split API ([addendum](/glade/u/home/zhil/project/double-jet-natl/docs/plans/2026-09-04_wave1_derecho_addendum_plan.md:273)), and the synthetic-archive paragraph is duplicated ([addendum](/glade/u/home/zhil/project/double-jet-natl/docs/plans/2026-09-04_wave1_derecho_addendum_plan.md:539)).

## Suggested edits

1. Make smoke evidence paths source-specific: RDA smoke should activate `regression`; CDS smoke should activate `r1_validation`. Ensure `all_paths()` contains only the active evidence path, and add source-aware assertions while preserving the legacy CDS filename.
2. Define the regression dispatch condition explicitly—at minimum require a fresh `classify` stage, or restrict automatic regression to the canonical all-stage RDA smoke invocation. Add tests proving download-only/figure-only smoke runs do not compare missing or stale operands.
3. Change §A0’s prohibition to “any other change to `figure.py`.”
4. Specify `overrides.setdefault("source", "cds_derived")` immediately before `raw.update(overrides)` in `make_cfg`.
5. Correct §A14, remove the duplicated paragraph, and update §A5’s stale single-dispatch wording.

verdict: CHANGES_REQUESTED