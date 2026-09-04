# Round 2 resolution

## Applied
- P1.1 — SIMPLIFIED rather than elaborated (anti-ratchet): the second `OutputNames` field added in round 1 is withdrawn. `r1_validation` is renamed to a single source-aware `evidence` slot, so `len(campaign)==len(smoke)==len(subset)==5` and the R12 disjointness test stay exactly as strict.
- P1.2 — regression gated on `{"profile","classify"} ⊆ args.stage`, mirroring how the R1 gate is gated on `"download"`; a skip is logged, never silent. Test 25 added for `--stage download` / `--stage figure`.
- P1.3 — §A0's blanket `figure.py` prohibition changed to "any *other* change to `figure.py`".
- P2.1 — fixture edit made exact: `overrides.setdefault("source","cds_derived")` before `raw.update(overrides)`; the reason `raw.setdefault` would be a no-op is stated.
- P2.2 — §A14 test claim corrected, §A5 "one name" wording fixed, duplicated synthetic-archive paragraph removed, §A0 edit inventory updated to two enumerated test edits.
- (self-audit) `load_config` must not stat the filesystem when parsing the `rda` block — `test_classify.py:68` and `test_config.py:51` load the shipped YAML, so an existence check at load time would break the suite off-machine. Not raised by either round.
- (self-audit) "test_classify/test_cli not touched" replaced with the verified reason: test_classify loads the real YAML but reaches no source-dependent path; test_cli constructs no Config.
- (self-audit) risk DR17 added for the six-path/R12 defect.

## Rejected
(none)

## Contested
(none)
