## Strengths

- The intermediate and CSV claims are accurate: dimensions, missing longitude, attributes, hashes, counts, dates, and null patterns all match.
- `OutputNames`, `CONTRACT_NAMES`, `len == 5`, and `STAGES` assertions are correctly located.
- The `classify.py` references for `profile_sha256`, core threshold, separation, and prominence are exact.
- The mockup is 260 lines, has the stated checksum, and contains the described offline design and renderer behavior.
- Test collection confirms 90 existing tests. No tracked files were modified during review.

## Issues

### P0

None.

### P1

1. **The enumerated test edits cannot keep the suite green.**  
   [tests/test_rda.py:974](/glade/u/home/zhil/project/double-jet-natl/tests/test_rda.py:974) directly constructs `OutputNames`; three new required fields will cause `TypeError`. In addition, [tests/test_rda.py:1185](/glade/u/home/zhil/project/double-jet-natl/tests/test_rda.py:1185) runs `cli.STAGES`, which will now include `explorer`, but the test only mocks existing stages at [tests/test_rda.py:1156](/glade/u/home/zhil/project/double-jet-natl/tests/test_rda.py:1156) and expects no explorer call. §B12.4 only authorizes the literal/length changes.

2. **The new default-stage behavior is not pinned at the execution boundary.**  
   The plan changes the parser default to `None`, while current `run()` joins and tests membership on `args.stage` at [double_jet/cli.py:208](/glade/u/home/zhil/project/double-jet-natl/double_jet/cli.py:208) and [double_jet/cli.py:211](/glade/u/home/zhil/project/double-jet-natl/double_jet/cli.py:211). The prose says `run()` resolves it, but neither an exact assignment nor a test that calls `run()` with the parser-produced `None` is specified. The proposed helper-only assertions could pass while the one-command build crashes.

3. **The “complete enumeration” omits three required tracked artifacts.**  
   §B4’s file list at [the addendum:195](/glade/u/home/zhil/project/double-jet-natl/docs/plans/2026-09-06_wave1_explorer_addendum_plan.md:195) excludes `results/season_summary.csv` and the two new `results/campaign/` copies required at [the addendum:632](/glade/u/home/zhil/project/double-jet-natl/docs/plans/2026-09-06_wave1_explorer_addendum_plan.md:632). That conflicts with §B0’s “nothing outside the enumeration” authorization.

4. **The results-document edit targets would corrupt historical provenance.**  
   [docs/results/2026-09-06_wave1_results.md:367](/glade/u/home/zhil/project/double-jet-natl/docs/results/2026-09-06_wave1_results.md:367) explains the measured memory of the actual 2026-09-05 panel-producing job and must remain historical. At [line 396](/glade/u/home/zhil/project/double-jet-natl/docs/results/2026-09-06_wave1_results.md:396), “figure” means a numerical result, not a visualization. §B14 incorrectly instructs replacing both references.

### P2

1. **The positional data contract lacks exact date and latitude-grid validation.**  
   Counting 153 rows and comparing year sets does not reject duplicated, missing, or reordered dates; those would silently change derived tooltips and run lengths. Existing code shows the stronger patterns at [double_jet/figure.py:91](/glade/u/home/zhil/project/double-jet-natl/double_jet/figure.py:91) and [double_jet/rda.py:532](/glade/u/home/zhil/project/double-jet-natl/double_jet/rda.py:532). Likewise, `lat_range` has no explicit source, and checking only spacing would accept a shifted coordinate; `open_intermediate` currently verifies only dimensions at [double_jet/profile.py:426](/glade/u/home/zhil/project/double-jet-natl/double_jet/profile.py:426).

2. **Several advertised hard gates lack negative tests.**  
   §B12 tests only the `u_core_min` arm of G6, although the other arms correspond to [double_jet/classify.py:147](/glade/u/home/zhil/project/double-jet-natl/double_jet/classify.py:147) and [double_jet/classify.py:153](/glade/u/home/zhil/project/double-jet-natl/double_jet/classify.py:153). G7/G8 also lack malformed-input tests, and G8 should explicitly require `u_1` as well as `lat_1` on `single` rows.

3. **BR1 omits smoothing provenance.**  
   `profile_sha256` excludes the entire detection block at [double_jet/config.py:216](/glade/u/home/zhil/project/double-jet-natl/double_jet/config.py:216), including `smooth_window_deg`. Unlike threshold tightening/loosening, a smoothing change is non-monotonic and cannot be checked from the CSV inequalities. This does not require overturning the approved no-`config_sha256` gate decision, but BR1 and D4’s blanket provenance claim should acknowledge it.

4. **Some documentation statements become false.**  
   CLI help still says `all` is the default at [double_jet/cli.py:150](/glade/u/home/zhil/project/double-jet-natl/double_jet/cli.py:150). Also, M6 is specifically the smoke panel at [wave1-plan.md:634](/glade/u/home/zhil/project/double-jet-natl/wave1-plan.md:634), so the campaign command cannot truthfully claim to reproduce M1–M6. Finally, §B14 says README/HANDOFF do not name the panels, but [HANDOFF.md:307](/glade/u/home/zhil/project/double-jet-natl/HANDOFF.md:307) does. Respecting the approved scope, record that as known-stale rather than asserting otherwise.

5. **The JSON round-trip does not test JavaScript hydration.**  
   `json.loads` verifies payload nulls, not the generated JS conversion before the mockup’s global `isFinite` guard at [docs/mockup/double_jet_explorer_v2.html:210](/glade/u/home/zhil/project/double-jet-natl/docs/mockup/double_jet_explorer_v2.html:210). A browser dependency would be disproportionate; a focused assertion on the emitted hydration code, or removal of the claim that the round-trip tests that seam, is sufficient.

## Suggested edits

1. Expand §B12.4 to update both missed `test_rda.py` sites.
2. Specify `stages = args.stage or default_stages(smoke)` before logging/dispatch and add one mocked run-level test for campaign and smoke defaults.
3. Add all three tracked outputs to §B4.
4. Rewrite §B14 to preserve historical job statements and remove line 396 from its targets.
5. Add one exact expected-date-vector gate, full latitude-axis validation, and compact parameterized negative tests for G6–G8.
6. Amend BR1/D4 for the uncheckable smoothing case; no stronger hash gate is necessary.
7. Update CLI help/M8 wording and accurately record the intentionally stale README/HANDOFF references.
8. Test the emitted hydration statement without introducing browser tooling.

verdict: CHANGES_REQUESTED