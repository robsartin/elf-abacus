# 0016. Plan on virtual registers, recompute into the real file

Status: Accepted (2026-11-21)

The plan is chosen under a larger register file than the puzzle has, and then compiled down by
recomputing values that do not fit. The mechanism is `rematerialize` in `src/elf_abacus/peephole.py`;
the route constants are in `src/elf_abacus/router.py`. The code, not this ADR, is the authority.

## Context
`chain.solve` plans under the real 48 registers: once they are full, `retain` (ADR 0014) overwrites
a kept value the remaining targets are least near. That couples two questions that the leading
public solvers keep apart: which values to build, and where to keep them. A register is also
occupied by a value that is dead for the rest of the program, so the real file can look full while
the live set is much smaller. The peephole allocator (ADR 0012) already shows this: it fits plans
into 48 registers at a peak well under what the planner thought it had.

## Decision
- Seeds after the first of a many-target puzzle run the planner on a puzzle copy with 300
  registers, so nothing is ever evicted for lack of a register.
- `rematerialize` rebuilds the value DAG, prunes it to what the targets need and allocates
  registers with recomputation: when none is free, the computed value with the furthest next use is
  overwritten and, if needed again, recomputed (operands recursively). Starting values are never
  overwritten while needed. Production order and depth-first order are both tried and the shorter
  verified result kept. The verifier stays the oracle (ADR 0002).
- The first seed stays on the real register file, so a puzzle whose virtual plans overflow badly
  keeps the old result.

## Evidence
Scratch harness, pool 10, seed 0, `grow` + `relate` + `keep_inner` + `retain`, each result put
through `optimize`; 21 many-target puzzles of the 1,000 (every 36th starting at 0, minus the first,
which had no real baseline): real 3,484 instructions, virtual 3,401 (-2.4%). Virtual won 16
puzzles, tied 4 and lost 1. The plan's peak live set exceeded 48 on 9 of the 21; those paid 3 to 15
recomputations each and gained least. Pool 24 planned virtually was worse than pool 10 on
4 of the 5 puzzles tried (e.g. 307 vs 292 and 259 vs 248 before the peephole), so larger
pools were not the lever.

## Alternatives rejected
- **Larger pools once registers are not a limit:** pool 24 on 300 registers lost to pool 10 on 4 of
  the 5 puzzles tried; the small pool preference is not an artifact of register pressure.
- **Reordering instructions to lower the peak:** random depth-first orders (300 per puzzle, on two
  puzzles) never beat the plain depth-first order, and a greedy list scheduler was worse; the overflow comes
  from long-lived shared values, not from the order.
- **Running the peephole on the virtual program before compiling:** it merges values into helpers
  that live longer, so recomputations rose (302 vs 292 instructions on one puzzle); it only helped
  on puzzles that already fit.
- **Planning on all virtual seeds:** puzzles whose plan overflows (peak 55 to 57) lost up to 3.6%
  against the real-file plan, so seed 0 stays real as the safe candidate.
