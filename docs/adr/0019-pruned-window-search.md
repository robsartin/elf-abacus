# 0019. Pruned window search and a fixpoint driver

Status: Accepted (2026-11-26)

Amends the cost figures of ADR 0018 (which is not edited); builds on ADR 0012 and ADR 0002.

## Context
ADR 0018 left windows of 5 and more as an option because of the cost: about 5 s a puzzle at window 5
and no finished run at 6. On the current best file (`best-12s.csv`, already a window-4 fixpoint) the
profile showed the time in `_one_step` (the scan over every register for one operand pair), called
about ten times per search node, and the node count itself.

## Decision
Four changes in `src/elf_abacus/superopt.py`, none of which changes what a found rewrite looks like
(every candidate is still re-verified):

1. Failed search nodes are memoised on (register contents, values produced, budget).
2. The value-to-register index is built once per node and shared by all `_one_step` calls.
3. `_one_step` stops at the first instruction: the state after building a value does not depend on
   which operation built it, so alternatives only repeat the same subtree.
4. A helper value (a stepping stone built before the wanted values) is only offered for a wanted value
   with no one-step route from the current state. When every wanted value is directly buildable the
   helper cannot shorten the search.

`superoptimize_fixpoint` alternates `superoptimize` and `peephole.optimize` until neither shortens.

## Alternatives rejected
- **Meet-in-the-middle over the set of values one step from the state:** the reachable set is built from every register pair (about 9,000 operations) per node, and the search asks about ten values per node, so it costs more than the targeted scans it would replace. Not built.
- **Skipping windows by their lower bound (live-out registers plus needed targets):** the root already returns at once when that bound exceeds the budget, and those windows cost almost nothing (windows at the bound cost 0.0 to 0.1 s of 14 s in the profile), so a selection heuristic has nothing left to save. The time is in windows with slack 2 and every win seen sat there too.
- **Fixpoint with the peephole as the default:** see Evidence; the peephole adds CPU and no length on the measured samples, so it is a separate function and not the default of the command line.

## Evidence
Sample = puzzles at index 0 mod 25 (and 12 mod 25 where stated), 40 puzzles, 3 workers, CPU measured
with `process_time` (the machine was loaded, wall time is not comparable).
`final5.csv` (the ADR 0018 file), window 5: ADR 0018 code 145.5 s (gain 7) to 33.8 s (gain 7); the
12 mod 25 sample 168.8 s (gain 8) to 37.9 s (gain 8). Equal gains, 4.3x and 4.5x less CPU. The
intermediate steps 1 to 3 alone gave 78 s (1.9x).
`best-12s.csv` (the current best), 0 mod 25: window 4 gains 0 in 20 s; window 5 gains 1 in 34 s;
window 6 gains 2 in 81 s; window 7 gains 4 in 223 s (slowest puzzle 34 s); window 8 did not finish in about 25 minutes on 3 workers
(one puzzle ran for most of it) and was stopped. 12 mod 25: window 4 gains 0, window 5 gains 1,
window 6 gains 1 in 92 s. The fixpoint with window 4 gains 0 on 0 mod 25 for 200 s (180 s of it the
peephole), so the alternation did not unlock anything there.
The pruning is a heuristic (helpers are no longer tried for directly buildable needs); the equal
gains on 2 samples with 15 wins are the only completeness evidence, not a proof.

## Consequences
Window 6 costs about 2 s a puzzle and window 7 about 5.6 s (worst case 34 s), so a whole-set run of
either fits a few hours on 3 workers; window 8 is not feasible without a per-puzzle time cap. Gains per window size on the best file are small (1 to 4 per 40 puzzles) and are
samples, not whole-set measurements. Not tried: helper pairs where neither helper is one step from the
state, windows that change the destination of a live-out value.
