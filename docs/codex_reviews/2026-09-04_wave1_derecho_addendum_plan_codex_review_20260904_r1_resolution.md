# Round 1 resolution

## Applied
- P1.1 smoke-check placement — RDA regression moved after the `figure` stage; §A7.3 item 3 rewritten.
- P1.1 output path — `OutputNames.regression` added as an optional field; `r1_validation` slot NOT reused.
- P1.2 dispatcher — split into `materialize_seasons` / `validate_seasons`; `rda.validate_local` added.
- P1.3 seam self-check — moved onto the `.part`, before `os.replace` and before the sidecar; §A6.3 row added.
- P1.4 `hourly_times` added to `profile_fields()`, with the reason it is definitional on the RDA path.
- P1.5 "63 unedited" claim corrected — one line in `test_profile.make_cfg` authorized and scoped; `_variant` anchor constraint recorded.
- P1.6 `figure.py:252` source label → `cfg.active_dataset`; edit count in §A0 raised to four.
- P2.1 regression alignment — `join="exact"` + 33 813-point assertion; tests 22-24 added.
- P2.2 PBS `-o` → plain `logs/campaign.out`; dead `DJET_WORKERS` export removed, `$PBS_NCPUS` read in code (§A5.2).
- P2.3 `preflight(cfg, years, log)` raising `download.PreflightError`; `--smoke` help text flagged.
- (self-audit) class-sweep for CDS assumptions across all modules recorded in §A7.2 — no fourth site exists.
- (self-audit) risks DR12-DR16 added for the five defects this round surfaced.

## Rejected
(none)

## Contested
(none)
