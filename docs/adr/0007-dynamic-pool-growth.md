# 0007. Dynamic pool growth from solved targets

Status: Proposed (2026-11-20)

Extends ADR 0005; it does not change it.

## Context
The fixed constant pool costs one instruction per constant (about 13-15% of a puzzle's total) and
fills almost all 48 registers, so nothing else can be kept. Targets solved earlier already sit in
registers, so they can serve as free pool terms for later targets.

## Decision
`solve(..., grow=True)` in `src/elf_abacus/solvers/chain.py` writes each solved target to its own
register (the plan's last instruction is redirected), appends it to the pool, and rebuilds the
forward and sum sets every `rebuild_every` solved targets. Accumulators move to the top of the
register file so the pool can grow beneath them. Growth needs a smaller starting pool.

Measured on the 28-puzzle sample (`puzzles[::len//28]`), totals in instructions:
pairs off: pool 40 plain 6,884; pool 24 plain 7,628; pool 24 grow/4 6,679; pool 30 grow/4 6,610;
pool 24 grow/8 6,845; pool 16 grow/4 7,189; pool 12 grow/3 unsolved on 2 puzzles.
Pairs on: pool 40 plain 6,654; pool 24 grow/4 6,415 (-3.6%).

## Alternatives rejected
- **Rebuilding less often (every 8):** 2.3x cheaper than every 4 but gave back about a quarter
  of the gain (6,845 vs 6,679).
- **Starting pools of 16 or 12:** the constants saved are outweighed by a weaker early search;
  pool 12 failed outright on two puzzles.
- **Plain larger pools:** pool 40 is the plain optimum already; it cannot also grow.

## Consequences
CPU cost is high: about 8x plain pool 24 without pairs, 2.4x the pairs-on baseline with them.
`run.py` is not changed here; adding growth as a further portfolio variant is the follow-up.
Plan intermediates and cheap accumulators as pool members were not tried. The code, not this
ADR, is the authority for constants.
