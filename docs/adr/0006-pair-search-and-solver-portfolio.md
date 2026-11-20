# 0006. Pair search over two forward sets, inside a per-puzzle solver portfolio

Status: Accepted (2026-11-20)

Extends ADR 0005; it does not change it.

## Context
After ADR 0005 no target had a direct chain: the forward set times the signed sums covered about
0.3% of the value range, so every target paid for a nested residual plan (about 9.6 instructions).
The additive tail carries only ~5 bits per instruction (its terms are order-redundant) while the
forward part carries ~7.6.

## Decision
`find_pair` in `src/elf_abacus/solvers/chain.py` builds a target as `a +/- b + tail`, with `a` and
`b` from two forward sets and a tail of at most `PAIR_TERMS` pool terms. For each value of the
smaller set it expands only the window of the larger set that can land within the tail's reach of
the target, then looks each gap up in the sums. `MAX_PAIRS` bounds the candidates per search by
narrowing the window in dense regions. `plan_target` tries it only at the outermost call.
`src/elf_abacus/run.py` keeps every solver's result per puzzle (Horner, and chains at three pool
sizes with and without pairs) and the portfolio takes the shortest verified program.

## Alternatives rejected
- **Parameter tuning of the old search** (pool 44, row cap 400k, 16 residual candidates, other
  seeds, 4 nesting levels): each moved a 28-puzzle sample by under 1%, which is the seed noise.
- **Product-of-sums forward level `(p +/- q) * (r +/- s)`:** -0.7% on the same sample; not worth a
  temporary register and a new code path.
- **Five-term sums:** 3% worse and several times slower.
- **Pair search alone, without the portfolio:** 3-7% shorter on large-target puzzles but 2-27%
  longer on small-target ones, so it is a candidate, never a replacement.
- **No pair cap:** on small-target puzzles a search expanded 6e9 to 6e11 pairs and the worker
  processes were killed.

## Consequences
Whole-set score 229,033 -> 222,529 (Kaggle agreed with the local verifier). The gain was smaller
than the ~10% projected from a prototype; the code, not this ADR, is the authority for the
constants.
