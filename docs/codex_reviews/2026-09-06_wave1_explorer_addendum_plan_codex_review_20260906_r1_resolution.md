# Round 1 resolution

## Applied
- P1.1 test-edit enumeration — added test_rda.py:974 (OutputNames fixture) and :1156-1186 (stage
  mocks + expected calls) as sites 3 and 4; §B12.4 retitled "three files, five sites"; added a
  grep/re-grep instruction; §B0 and §B4 wording follow.
- P1.2 stage resolution — §B10 item 4 now specifies `stages = args.stage or default_stages(smoke)`
  before cli.py:205 and names every downstream `args.stage` site; §B12.3 gains
  `test_stage_defaults_are_shape_dependent` with a mocked run-level dispatch assertion.
- P1.3 enumeration gap — §B4 gains a "New tracked artifacts" table: results/season_summary.csv and
  the two results/campaign/ copies.
- P1.4 write-up targets — §B14 item 2 narrowed to line 46 only; lines 283, 367 and 396 named as
  explicit non-targets with the reason each must stay (captioning statement, measured job memory,
  "figure" meaning a numeric value).
- P2.1 data contract — G1 upgraded from a row count to an exact expected-date-vector check modelled
  on rda._assert_season_dates; G3 upgraded to full latitude-axis equality (endpoints + spacing);
  new G10 pins lat_range to the sector attribute.
- P2.2 negative tests — G6 parametrized over all three arms; new tests for reordered/duplicated
  dates, shifted latitude axis, and malformed G7/G8 shapes; G8 now requires u_1 on single rows.
- P2.3 smoothing provenance — BR1 rewritten to state that smooth_window_deg is neither hashed nor
  CSV-checkable (non-monotonic); D4's blanket provenance sentence replaced with the scoped claim.
- P2.4 stale statements — §B4 adds the cli.py:149-150 help string; §B14 M8 corrected to M1/M3/M4/M5
  (M2 and M6 are --smoke deliverables, M7 retired); the "not updated" paragraph now records
  HANDOFF.md:307 as knowingly stale rather than claiming nothing names the panels.
- P2.5 hydration seam — §B12.1 gains a scoped note plus a string assertion on the emitted
  hydration statement; the round-trip's claim narrowed to the payload half.

## Rejected
(none)

## Contested
(none)
