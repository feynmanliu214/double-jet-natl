## Strengths

- The proposed season file satisfies all eight `profile.open_normalized` gates: recognized names, scalar 250 hPa level, one `u` data variable, canonical coordinates, copied units, exact seasonal dates, finite values, and canonical dimension order ([profile.py](/glade/u/home/zhil/project/double-jet-natl/double_jet/profile.py:156)). The scalar-level design also works with `_check_shape`, which deliberately checks only time/latitude/longitude dimensions ([download.py](/glade/u/home/zhil/project/double-jet-natl/double_jet/download.py:147)).
- Separating inventory comparison from `_canonical_request` is correct; the latter cannot meaningfully canonicalize nested file dictionaries ([download.py](/glade/u/home/zhil/project/double-jet-natl/double_jet/download.py:182)).
- The three baseline operands exist with the claimed schemas: 153-row CSV, exact summary block, and `U(time=153, latitude=221)` profile. `results/` is distinct from generated `data/`, so the planned run does not clobber the committed baseline.
- `test_config.py` does not pin a literal profile hash, and its threshold/sector relational assertions remain valid ([test_config.py](/glade/u/home/zhil/project/double-jet-natl/tests/test_config.py:221)).
- Size+mtime inventory validation is proportionate to a recoverable 52-minute loader; content-hashing 11+ TB per validation would be over-engineered.

## Issues

### P0

None.

### P1

1. **The RDA smoke regression cannot replace the current smoke check in place.** The current check executes inside the download block, before profile and classification create any of the three comparison operands ([cli.py](/glade/u/home/zhil/project/double-jet-natl/double_jet/cli.py:191), [cli.py](/glade/u/home/zhil/project/double-jet-natl/double_jet/cli.py:204)). Yet §A7 says nothing else moves, while §A9 requires generated profile, CSV, and summary files ([addendum](/glade/u/home/zhil/project/double-jet-natl/docs/plans/2026-09-04_wave1_derecho_addendum_plan.md:420)). A clean smoke run will fail on missing operands; a dirty run could compare stale ones.

   There is also no path for the promised `data/smoke_2018_regression.json`: unchanged `output_names` provides only `smoke_2018_r1_validation.json` ([cli.py](/glade/u/home/zhil/project/double-jet-natl/double_jet/cli.py:58)), which an existing test pins ([test_config.py](/glade/u/home/zhil/project/double-jet-natl/tests/test_config.py:187)).

2. **The validate-only dispatch is unspecified and conflicts with the proposed API.** `source.ensure_seasons` maps to materializing functions, while §A7.3 also assigns it a `--skip-download` validate-only responsibility ([addendum](/glade/u/home/zhil/project/double-jet-natl/docs/plans/2026-09-04_wave1_derecho_addendum_plan.md:381)). Today those are deliberately separate operations: `run_download` mutates the cache, whereas `ensure_downloaded` only validates ([download.py](/glade/u/home/zhil/project/double-jet-natl/double_jet/download.py:348), [download.py](/glade/u/home/zhil/project/double-jet-natl/double_jet/download.py:394)). A literal implementation could make `--skip-download` materialize RDA seasons.

3. **The seam self-check happens too late for the claimed resume safety.** §A5 lands the `.nc`, writes its matching sidecar, and only then calls `open_normalized` ([addendum](/glade/u/home/zhil/project/double-jet-natl/docs/plans/2026-09-04_wave1_derecho_addendum_plan.md:290)). If that check rejects units, grid, time, variable, or finite values, both artifacts remain complete-looking. `_check_shape` cannot detect those failures, so the next run may skip the bad cache.

4. **`profile_sha256` still omits an RDA profile-determining field.** The loader directly uses `cfg.hourly_times`, but current `profile_fields()` contains `frequency` and not `hourly_times` ([config.py](/glade/u/home/zhil/project/double-jet-natl/double_jet/config.py:180)). An authorized future hour-set change could therefore alter the daily field without changing the hash, allowing classify-only execution to accept a stale intermediate ([classify.py](/glade/u/home/zhil/project/double-jet-natl/double_jet/classify.py:341)).

5. **The claim that all 63 existing tests remain green unedited is false.** With the shipped YAML switched to RDA, the planned provenance changes conflict with assertions that require `source_dataset == cfg.dataset` and a CDS-shaped `pressure_level == ["250"]` request ([test_profile.py](/glade/u/home/zhil/project/double-jet-natl/tests/test_profile.py:338)). Because that fixture copies the production YAML, dispatching `request_for` would also make this synthetic unit test inspect the real RDA archive off-machine ([test_profile.py](/glade/u/home/zhil/project/double-jet-natl/tests/test_profile.py:54)).

6. **The final figure remains falsely labeled as CDS-derived.** `figure.py` prints `cfg.dataset`, which remains `derived-era5-pressure-levels-daily-statistics`, not `cfg.active_dataset` ([figure.py](/glade/u/home/zhil/project/double-jet-natl/double_jet/figure.py:246), [double_jet.yaml](/glade/u/home/zhil/project/double-jet-natl/configs/double_jet.yaml:6)). This is another CDS assumption outside the three authorized edits and produces incorrect scientific provenance.

### P2

1. **The numeric regression needs explicit coordinate semantics and tests.** Require exact time/latitude alignment and exactly 33,813 compared points. The existing R1 implementation documents why bare xarray subtraction can silently compare only an intersection ([download.py](/glade/u/home/zhil/project/double-jet-natl/double_jet/download.py:462)). None of the twenty proposed RDA tests exercises `check_regression_2018`.

2. **The PBS snippet contains two inconsistencies.** Its `-o` directive contains an array placeholder plus an inline comment despite stating no array is used ([addendum](/glade/u/home/zhil/project/double-jet-natl/docs/plans/2026-09-04_wave1_derecho_addendum_plan.md:551)). It also exports `DJET_WORKERS`, but the loader is specified to read only `cfg.rda.workers`; no code path consumes that environment variable ([addendum](/glade/u/home/zhil/project/double-jet-natl/docs/plans/2026-09-04_wave1_derecho_addendum_plan.md:272)).

3. **The RDA preflight contract lacks the requested years and exception mapping.** `preflight(cfg, log)` cannot check “the first requested season” for `--smoke` or `--years`; current CLI also catches only `download.PreflightError` to produce exit 2 ([cli.py](/glade/u/home/zhil/project/double-jet-natl/double_jet/cli.py:191)). The plan should specify the year argument and common/translated exception. The CLI’s `--smoke` help also still promises “both CDS products” ([cli.py](/glade/u/home/zhil/project/double-jet-natl/double_jet/cli.py:123)).

## Suggested edits

1. Move the RDA regression after profile/classify outputs are written; retain the CDS R1 check after download. Add a source-specific regression output to `OutputNames`.
2. Define separate materialize and validate-only dispatcher functions.
3. Run `open_normalized` against `.part` before `os.replace` and before writing the sidecar; add a failure-path test.
4. Add `hourly_times` to `profile_fields()` and test that it changes the hash.
5. Permit the minimal existing test edits needed to keep CDS tests isolated, while testing RDA provenance in `test_rda.py`.
6. Authorize the one-line `figure.py` source-label correction.
7. Require exact regression coordinate alignment and pass/failure tests for all three comparisons.
8. Change the PBS output to plain `logs/campaign.out`; either specify how `DJET_WORKERS` is consumed or remove the dead export.

verdict: CHANGES_REQUESTED