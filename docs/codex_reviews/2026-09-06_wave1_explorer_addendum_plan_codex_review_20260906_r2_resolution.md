# Round 2 resolution

## Applied
- P1.1 stale dispatch — §B10 item 5 changed to `if "explorer" in stages:`; the site list is now the
  exact six executable `args.stage` lines (cli.py:208/211/233/237/242/258) plus the new explorer
  block = seven, the :255 comment included, with a grep/re-grep instruction.
- P2.1 mock count — the run-level test now names seven callables including explorer.run_explorer.
- P2.2 grep + import — grep re-described as a candidate list to triage (== 5 also matches
  test_rda.py:440 and :594, which are not sites); site 4 now adds `explorer` to the import at
  tests/test_rda.py:53.
- P2.3 false exhaustive count — §B14 now says "no other line changes" with 283/367/396 kept as
  representative reasons and an explicit "do not sweep the document for the word".
- P2.4 orphaned G10 — gate removed entirely (it compared a payload against the values it was built
  from); replaced by a B12.1 assertion on the parsed payload, with G3 named as the real proof.
- P2.5 module usage string — §B4 now covers both cli.py:4 and cli.py:149-150.
- (self-audit) `--stage all` now means five stages, so a campaign `--stage all` builds panels AND
  explorer; stated in §B10, and jobs/download_all.slurm:52 noted as the superseded Stampede3 job
  that is deliberately not fixed.
- (self-audit) jobs/derecho/campaign.pbs:5's "All four stages ... -> figure" comment becomes false;
  added to the enumeration as a comment-only edit, with the job body and #PBS shape untouched so
  HANDOFF §7's compute authorization is unaffected.

## Rejected
(none)

## Contested
(none)
