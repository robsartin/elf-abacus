# 0012. Shrink finished programs with a verified peephole post-pass

Status: Accepted (2026-11-20)

Extends ADR 0006 (portfolio); relies on ADR 0002 (the verifier is the oracle).

## Context
A program only has to produce every target value somewhere; all values are exact integers, so a
program is a DAG over distinct values and register names are bookkeeping. Solvers emit programs
that still contain recomputed values, results nothing reads, and helper values whose consumers
can be built from other values. Measured on the best-per-puzzle merge of the early whole-set
files (222,529 instructions, 1,000 puzzles; the 218,127 file was no longer on disk): value
numbering removed 1,585, dead code 236, re-derivation about 2,800, for 217,903 in total
(-2.1%) in about 30 s on six workers.

## Decision
`src/elf_abacus/peephole.py` provides `optimize(puzzle, program) -> program`, applied by
`portfolio.best_programs` to each puzzle's winner. It (1) rebuilds the value DAG, dropping
recomputations, (2) keeps only what the targets reach, (3) re-derives a non-target value's
consumers from other live values (any operator, any acyclic pair) when that shrinks the live set,
and (4) re-allocates registers, giving up on a step when the result no longer fits the register
file. The result is re-verified and the input is returned unless the result is strictly shorter,
so the function never lengthens a program and never emits one the verifier rejects.

## Alternatives rejected
- **Dest-preserving deletion on the original instructions:** sound only for dead code, which is
  15% of the gain; removing a recomputation would leave a register stale for later readers.
- **Re-derivation restricted to earlier values:** a first version only used operands produced
  before the consumer; allowing any acyclic pair raised the gain from about 3,500 to 4,626.
- **Trying several alternatives per consumer and keeping the smallest live set:** 217,908 against
  217,903 for the first acceptable one, at the same cost; not worth the code.
- **Optimizing every candidate before the portfolio pick:** three times the cost for a gain
  unmeasured here; the pick is optimized once. Revisit if a longer candidate often optimizes
  below the winner.

## Consequences
Cheap enough to run on every submission. Pool constants used once, accumulator steps into a
target register and register copies need no rewrite of their own: there are no copies (every
instruction is an operation) and the target register is irrelevant, so those cases reduce to
the three rewrites above. Gains shrink as solvers improve and stop emitting waste.

## Amendment 2026-11-21: pair-helper rewrite

The original post-pass was already at a fixpoint on the trial4 output (13 instructions saved over
6 programs). A fourth rewrite, `_rederive_with_helper` in `src/elf_abacus/peephole.py`, rebuilds a
single-consumer helper's consumer as `x op n` where `n` is one new value made from two live values.
It is accepted only when the live set shrinks, the programs still fit in the registers and the
verifier passes. On the whole-set output it saved 1,843 of 196,977 instructions (0.94%); the full
pass costs about 2.6 s per program. Not tried: multi-consumer helpers and chains replaced by two or
more new helpers.

## Amendment 2026-11-22: multi-helper rebuilds

`_rederive_with_helpers` (with `_rebuilds` and `_private_chain`) in `src/elf_abacus/peephole.py`
generalises the pair-helper rewrite: any live node can be rebuilt from live values plus zero, one
or two new values, accepted when its private helper chain is longer than the new values it needs,
the registers still fit and the verifier passes. Whole-set effect: 188,783 to 186,213 (about
1.1%) on top of the earlier rounds. Still not tried: multi-consumer helpers.
