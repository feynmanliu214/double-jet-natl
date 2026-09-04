## Strengths

- All round-2 P1 fixes are correctly applied: one source-aware evidence slot preserves the five-path invariant, and regression requires freshly produced profile/classification operands ([addendum](/glade/u/home/zhil/project/double-jet-natl/docs/plans/2026-09-04_wave1_derecho_addendum_plan.md:516), [test_config.py](/glade/u/home/zhil/project/double-jet-natl/tests/test_config.py:162)).
- The proposed season output survives all eight `open_normalized` gates, including the scalar-level design and canonical coordinate adoption ([profile.py](/glade/u/home/zhil/project/double-jet-natl/double_jet/profile.py:156)). Reusing `_check_shape` and separating nested inventory comparison from `_canonical_request` remain valid ([download.py](/glade/u/home/zhil/project/double-jet-natl/double_jet/download.py:147)).
- The fixture correction is now exact and preserves existing CDS-path assertions ([addendum](/glade/u/home/zhil/project/double-jet-natl/docs/plans/2026-09-04_wave1_derecho_addendum_plan.md:562), [test_profile.py](/glade/u/home/zhil/project/double-jet-natl/tests/test_profile.py:54)).
- The three regression operands exist with the claimed dimensions and schemas, while generated `data/` outputs cannot clobber tracked `results/`.
- No additional CDS-dependent runtime site was missed in `cli.py`, `profile.py`, or `classify.py`; the planned provenance substitutions and dispatcher calls are sufficient.

## Issues

### P0

None.

### P1

None.

### P2

1. **Test 17 names the wrong half of the split API.** It says `ensure_local` reports every missing season, but the plan defines `ensure_local` as materializing and `validate_local` as the validate-only analogue of `download.ensure_downloaded` ([addendum](/glade/u/home/zhil/project/double-jet-natl/docs/plans/2026-09-04_wave1_derecho_addendum_plan.md:294), [addendum](/glade/u/home/zhil/project/double-jet-natl/docs/plans/2026-09-04_wave1_derecho_addendum_plan.md:623), [download.py](/glade/u/home/zhil/project/double-jet-natl/double_jet/download.py:394)). The surrounding contract is unambiguous, so this is non-blocking test-matrix wording.

## Suggested edits

1. In test 17, replace `ensure_local` with `validate_local`. No additional mechanism or test is needed.

verdict: APPROVED