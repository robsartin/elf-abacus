# 0017. Value-limit-tight puzzles are the 60-bit puzzles; no route change

Status: Accepted (2026-11-24)

A negative result: no route change. Extends ADR 0010 (round-five huge-target route); it does not change it.

## Context
About 126 puzzles have `value_limit` within 5% of their largest target and average ~300
instructions against ~165 elsewhere. Controlling for bit length removes most of the effect: among
puzzles with 40-59 bit targets the tight ones cost the same per target as the loose ones
(`final4.csv`: 6.9 against 7.5 at 50 bits). The tight group is mostly the 60 puzzles whose every
target is at least 2^54 (all have a 60-bit limit): they cost ~12 instructions per target
(~21,300 of the 179,209 total) against ~9 for other tight 60-bit puzzles.

Measured on that group (seed 0, pool 20):
- No pool pair is pruned by the limit: the pool tops out near sqrt(largest target), so every
  pool sum and product fits. The limit only prunes at forward level 2-3 and there the pruning is
  harmless, since only 0.6% (level 2) and 4.5% (level 3) of forward values reach the target band.
- Cost per target is flat (~11) from the second target to the last; growing the pool with solved
  targets does not help because 60-bit targets sit ~2^55 apart and are useless as stepping stones.
- Direct chains almost never exist (|forward| x |sums| is ~1e10 against a 2^60 range); the cost is
  the nested forward-plus-gap peeling, ~15 bits per level.

## Decision
No router change. `HUGE_POOL` stays at 20. A pool of 28 beat 20 on seed 0 alone (8 of the
costliest puzzles: 29 of 3,251 instructions saved, -0.9%, 6 of 8 better, ~15% less CPU), but the
route's second seed (virtual registers, ADR 0016) with pool 20 beat pool 28 on both puzzles
measured (388 against 401, 381 against 386), and the best-of-two per puzzle was equal or worse
with pool 28. The seed-0 gain does not survive the best-of.

## Alternatives rejected
- **Pool 28 on both seeds:** see Decision; best-of-two equal or worse on the two puzzles measured
  (two more were still running at the time box, so this is thin).
- **Pool 36:** 1,658 against 1,636 for pool 28 on four puzzles; one puzzle +19.
- **Pool 14:** failed outright on 3 of 4 puzzles.
- **`relate=False`:** -45% CPU but +3-5% instructions on 3 of 3; at equal CPU a second seed does not make that up.
- **`max_terms=5`:** 419 against 419 on one puzzle at 5x the CPU.
- **Larger pool constants (cap sqrt -> top^0.67) and a higher smallest constant:** the first target
  becomes unreachable (no plan), so the pool needs small scales.

## Consequences
Sample sizes are 2-8 puzzles and seed noise is about +-8 instructions a puzzle. A mixed route
(pool 28 on seed 0, pool 20 on the virtual seed) is untested beyond those two puzzles.
