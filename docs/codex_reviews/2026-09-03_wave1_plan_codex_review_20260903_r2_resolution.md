# Round 2 resolution

## Applied
- P1-1: deleted "or resubmit the same job script" from the threshold-rerun path (§5.3). Added an explicit
  refusal: `download_all.slurm` is pinned to `--stage all`, would re-issue 47 requests after a purge, and is a
  production submission needing fresh approval (§10 E1). It is now stated as the only script that issues a request.
- P2-1 (self-audit, class sweep): the round-1 fix was applied to the cited lines only. Swept every output path in
  the document; replaced the prose rule with **one authoritative table in §4.2** covering full campaign / smoke /
  `--years` subset, and made §4.3, §4.4, §4.5 refer to it instead of restating literals. Only the full-campaign row
  may use the wave prompt's contract names; subsets are year-qualified, including summary and panels.
- P2-2: ZIP demoted from artifact to incidental transport container (§4.1, §6, M1). Not promised, not validated,
  not required; still not deleted, per the wave prompt's "the pipeline deletes nothing".
- P2-3 (self-audit, class sweep): round 1 changed I3 but left "strict interior maxima" at §4.3 step 2. Swept the
  phrase; §4.3 now states the `find_peaks` default behaviour including the flat-top midpoint. Added a flat-top test
  to `test_classify.py` so a later `plateau_size` "tightening" fails the suite instead of silently dropping cores.
- Tests: `test_config.py` now compares full / smoke / subset namespaces **pairwise**, asserting only the
  full-campaign case yields the contract names. Risk R12 restated against the table.

## Rejected
(none)

## Contested
(none)
