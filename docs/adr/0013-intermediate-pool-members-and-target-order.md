# 0013. Plan intermediates as pool members; target order left alone

Status: Proposed (2026-11-20)

Extends ADR 0008; it does not change it. Written as 0011 because the sequence gate in
`tests/test_adrs.py` needs consecutive numbers on this branch; renumber it (the coordinator asked
for 0013) when the other branches' 0011 and 0012 land.

## Context
ADR 0008 listed plan intermediates as untried, and the order targets are solved in decides which of
them win a register (about 16 are free of 48 once the pool, starting values and accumulators are
placed, against ~30 targets).

## Decision
`solve(..., grow=True, keep_inner=True)` saves every new in-range value a plan computes before its
last instruction (accumulator and second-chain values) into its own free register, via
`save_intermediates` in `src/elf_abacus/solvers/chain.py`, and adds it to the pool. It is
opt-in and not yet wired into `router.py`/`run.py`. Targets stay in file order.

Measured on the `puzzles[::len//28]` sample (29 puzzles here), grow pool 24, pairs on,
`rebuild_every` 4, totals in instructions:

| Variant | seed 0 | seed 1 |
|---|---|---|
| grow baseline | 6,393 | 6,369 |
| `keep_inner` | 6,050 (-5.4%) | 6,047 (-5.1%) |

Target order alone, seed 0 (scratch spike, not in the code): descending 7,025; cheapest-first by
chain cost 6,375; hardest-first 6,523; nearest-gap 6,587; greedy re-rank at each rebuild 6,365;
greedy hardest-first 6,555. With intermediates, greedy re-ranking gave 6,246 against 6,050 for file order.

## Alternatives rejected
- **Reordering targets:** the files are already ascending, which is the best of those tried; the
  cheapest-first and greedy variants moved the total by under 0.5%, the noise level, at more CPU.
- **Intermediates with a register reserve for later targets:** 6,387, no gain; reserving starves
  the intermediates, which are the part that helps. Keeping only the last two: 6,205 (-2.9%).

## Consequences
Intermediates also took CPU down (about 740 vs 1,160 cpu-s, spike run) since the pool grows
faster. Gains on the whole set are expected to stack to less than the sample (ADR 0008 amendment:
-3.6% sample became -2.0%); a whole-set run is not done. Not yet tried: other pool sizes with
`keep_inner`, wiring into the router. The code, not this ADR, is the authority for the rules.
