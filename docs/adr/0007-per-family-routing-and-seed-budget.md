# 0007. Route solvers by puzzle features and spend the saved time on seeds

Status: Proposed (2026-11-20)

Extends ADR 0006; it does not change it.

## Context
ADR 0006 ran Horner and six chain variants (pool 24/32/40, pairs on/off) on every puzzle, about
65 CPU-seconds a puzzle. The per-puzzle win table on a 28-puzzle sample (every 36th puzzle of
`puzzles.csv`; solver outputs are reproducible) shows:

- About 96% of the score is in the ~850 puzzles with 28-32 targets (8.3-8.6 instructions/target).
  Puzzles with 1-18 targets are 4% of the score.
- With at least 15 targets the pool-40 chain with pair search was the shortest (or tied) on 20 of
  22 puzzles; Horner and the pool-24 chains won only at 1-10 targets or tiny value limits.
- Totals are monotone in pool size (24: 6,251; 32: 5,845; 40: 5,687 with pairs) and pairs beat
  plain chains at every pool size.
- Horner + pool-40 pairs alone scores 5,615 on the sample against 5,613 for the full portfolio,
  in 38% of the CPU time (559 s against 1,462 s).
- The chain's constant pool is random, so a different seed is an independent draw: best of three
  seeds on the 22 large puzzles scored 5,263 against 5,347 for seed 0 (-1.6%).
- Cost per target tracks bit length and the number of starting values (one starting value is the
  worst, 11.9/target), not how close the targets sit to `value_limit`.

## Decision
`src/elf_abacus/router.py` computes puzzle features and returns a route. With at least
`BIG_TARGETS` targets: Horner plus the pool-40 pair chain at `seeds` different seeds
(`--seeds`, default 3). With fewer: Horner and the full six-variant chain portfolio, which is cheap
there. `run.solve_one` executes the route; the shortest verified program still wins.

## Alternatives rejected
- **Keep running every variant everywhere:** 2.6x the time of the route for 0.04% of score.
- **Route by `value_limit` tightness:** the table shows no cost effect of a tight limit once bit
  length and starting-value count are accounted for, so a rule on it would be noise.
- **Choose seeds by predicted gain per puzzle:** no feature separated puzzles where extra seeds
  paid; seed gains were spread evenly (best-of-3 improved 16 of 22 puzzles). A uniform seed count
  is the simplest budget.
- **Pool above 40 to use the saved time:** ADR 0006 measured under 1% for pool 44.

## Consequences
On the sample, route plus 3 seeds scores 5,531 (-1.5% against 5,613) in about the same CPU time
as the full portfolio (1,425 s against 1,462 s); route plus 1 seed scores 5,558 in 40% of it. The
threshold and pool sizes are in code; this ADR records why, not the values.
