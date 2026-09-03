# Round 1 resolution

## Applied
- P1-1 R1 gate: both operands via the §4.2 reader, `xr.align(join="exact")`, `n_compared` asserted and logged (§4.1).
- P1-2 ingestion: exact lat/lon arrays via `np.arange`, units checks (deg/hPa/m s-1), `np.isfinite` not non-NaN (§4.2).
- P1-4 entry point: added `double_jet/__main__.py` + `cli.py`; `python -m double_jet` canonical; script kept as shim (§3).
- P1-4 jobs: new §5.0 job-script contract — `set -euo pipefail`, SLURM guard, `cd`, conda activate, import check.
- P1-5 I3: reworded to `find_peaks` defaults (plateau midpoint). Codex's `plateau_size=(None,1)` verified to DROP a
  flat-topped core (`find_peaks([0,1,2,3,3,3,2,1,0], plateau_size=(None,1))` -> `[]`), so the wording moved, not the code.
- P2-1 cache: request-sidecar identity required on skip; `.part` + atomic rename; same rule for the 6-hourly file (§4.1).
- P2-2 namespaces: all filenames derived from the run's year range by `cli.output_names`; smoke prefixed (§4.2, §4.3, §6).
- P2-2 config hash: classify fails if the intermediate's profile-determining hash differs; thresholds excluded (§4.3).
- P2-3 `wave1.md`: materialized verbatim at the repo root by the planning session; §9 step 1 updated.
- P2-4 network: "settled" -> "proven on skx, unverified on skx-dev"; connectivity preflight added to both jobs (§1.8, §5.0).
- P2-5 tests: added `test_profile.py` (9 ingestion gates), `test_cli.py`, output-naming and config-hash cases (§4.6).
- Bookkeeping: M1 reframed as a purgeable cache; M9 added; risks R10-R13 added; §10 E6 added; §0 provenance note.

## Rejected
- P1-3 / suggested-edit-3 (move `data/`, `figs/` to `$WORK`) — the wave prompt is the governing document for this wave
  and specifies it directly: "The cached intermediate profile (a few MB) goes to the repo's `data/`", and "This is under
  `$HOME`, which has a small quota — code and the few-MB intermediate only". The quota was called out by the operator,
  not overlooked. Parent `CLAUDE.md` itself defers to repo-specific rules. The deliverable paths `data/…` and `figs/…`
  are contract text; moving them breaks the spec being implemented. Substance partly adopted: §6 now calls `$SCRATCH` a
  cache, states nothing downstream needs it after a purge, and notes `$HOME` is unbacked; the mirror option is §10 E6.
- P2-2 tail ("refuse overwriting outputs from a different config hash unless explicitly requested") — the naming fix
  removes the collision at its root; an overwrite-refusal dialog is extra mechanism for a case that can no longer arise.
  Single-operator, recoverable-by-rerun; residual risk accepted.

## Contested
(none)
