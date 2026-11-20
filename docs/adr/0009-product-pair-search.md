# 0009. Product pair search: a second value one level deeper than the stored sets

Status: Accepted (2026-11-20)

Extends ADR 0006; it does not change it.

## Context
ADR 0006's pair search stops at the stored forward levels. Measured per target on a 28-puzzle
sample (first 12 targets, only those with no direct chain), the best pair cost was 6 for 6 targets,
7 for 58, 8 for 16, 9 for 31 and none for 25. Whether a pair exists is a counting question: the
expected number of exact hits is (values at the target's scale) x (values in the partner set) x
(tail gaps) / (value range). Each extra tail term multiplies the gaps ~30x; each forward level
multiplies a set ~55x but cannot be stored.

## Decision
`find_product_pair` in `src/elf_abacus/solvers/chain.py` adds the family
`a +/- c + tail` where `c = y * p` or `y // p`, `y` a top-level stored value and `p` a pool value.
`c` is never enumerated: every candidate `c = target -/+ a -/+ tail` is derived from the other side
and tested backwards (`p` divides `c` and `c / p` is stored, or `c * p` is stored). Divisibility
prunes nearly everything, so a pass costs about a second. Spans larger than `MAX_PRODUCT_GRID`
are skipped. `plan_target` tries it after `find_pair`, with the same bound.

## Alternatives rejected
- **Raise `MAX_PAIRS` / uncap the pair windows:** an uncapped, chunked probe returned the same
  cost distribution (7:58, 8:17, 9:30, none:25 vs 7:58, 8:16, 9:31, none:25). The cap is not the
  limit; the pair space is.
- **More additive families as extra pair sets** (`(p+-q)*(r+-s)`, `(p op q) +- (r op s)`, each
  paired with level 3): no target moved from "no pair <= 8" to a hit, and one moved 7 -> 6.
- **Every span of the product family** (also first values at level 2 with one tail term):
  6,573 vs 6,578 on the sample but 30x the time (444 s vs 38 s per puzzle).
- **Tuning `PAIR_TERMS`:** each extra tail term multiplies the scan ~30x for one cost step; the
  cost-9 hits it adds are the ones the nested plan already reaches.

## Consequences
Sample total (plain chain, pool 40, pairs on) 6,654 -> 6,578 (-1.1%) at 2.6x the time (14.5 s ->
38 s per puzzle). Of 31 targets whose best pair cost 9, 7 now cost 8; 5 of 16 cost-8 now cost 7 and
4 of 58 cost-7 now cost 6. The 25 targets with no pair at all are unchanged. The code is the
authority for the constants.

## Amendment 2026-11-20 (integration)
Merged in PR 9 and active whenever pairs are on. PR 9 merged this with ADRs 0007-0010 together. The whole-set score of the combined solver was 218,259 (218,127 as best-of with the earlier file, Kaggle-confirmed) against 222,529 before: -2.0%, well under the sum of the sample gains, so the four overlap.
