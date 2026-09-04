# double-jet-natl

Classification of **double-jet vs single-jet** days from ERA5 250 hPa zonal wind over the
North Atlantic–Europe sector (60°W–30°E, 20–75°N), MJJAS 1979–2025.

## Start here

| File | What it is |
|---|---|
| **`HANDOFF.md`** | **Current brief.** State of the work, the seam to plug into, compute authorization, deliverables. Read first. |
| `CLAUDE.md` | Repo invariants — frozen numbers, entry point, storage and compute rules. |
| `wave1-plan.md` | The reviewed contract (= `docs/plans/2026-09-03_wave1_plan.md`). Its rulings are not reopened without the operator. |
| `docs/deviations.md` | D1, D2, D3 — every departure from the plan, with evidence. |
| `wave1.md` | The original wave prompt and the scientific question. |
| `results/smoke_2018/` | Committed regression baseline: the MJJAS 2018 smoke season's actual outputs. |

## Status (2026-09-04)

Pipeline complete and tested (63 tests). Smoke season 2018 passed end to end. The 47-season
campaign is **not** done: the CDS retrieval route ran at ~1 season/hour and timed out (deviation
D2), so the campaign was moved to NCAR Derecho reading the ERA5 hourly archive already on `/glade`
(deviation D3, operator-authorized).

The key measurement so far: the CDS derived daily-mean product and a local mean of the archived
hourly product at 00/06/12/18 UTC are **bit-identical** — `max_abs_diff = 0.0` over 12 206 493
points of MJJAS 2018. That is what makes the source change safe.

## Running it

```bash
python -m double_jet --config configs/double_jet.yaml [--smoke | --stage ... | --skip-download]
python -m pytest tests/ -q
```

Every number that defines the science lives in `configs/double_jet.yaml` and nowhere else.
Changing one is an escalation to the operator, not a code edit.
