# 0018. Window superoptimiser over the finished programs

Status: Accepted (2026-11-25)

Extends ADR 0012 (verified peephole); relies on ADR 0002 (the verifier is the oracle).

## Context
The peephole works on the value DAG and re-allocates registers, so it only fires when the rebuilt
program still fits the register file, and it only rebuilds a node from live values plus a few new
ones. On `final5.csv` (178,625) the programs are a fixpoint of it. The instruction list itself still
holds small redundancies the DAG view cannot see: recompute steps forced by the 48-register limit
(1,284 instructions more than distinct live values, in 217 puzzles) and short detours.

## Decision
`src/elf_abacus/superopt.py` provides `superoptimize(puzzle, program)`. For a window of 2 to
`max_window` instructions it replays the program to get every register's value at the window's
start and end, finds the registers read afterwards before being overwritten (live-out) and the
targets only this window produces, and runs an exhaustive depth-limited search for a sequence one
instruction shorter or more. The replacement may read any register and may write only the window's
own destinations or dead registers, so the rest of the program is untouched and no allocation is
redone. A window can also be an instruction plus one up to `span` positions away that is moved next
to it when no register hazard blocks the move. Every rewrite is re-verified; the input is returned
if invalid, and the result is never longer. `python -m elf_abacus.superopt` runs it over a file.

## Alternatives rejected
- **A DAG-space window search (choose a node set, rebuild its live-outs):** `peephole.py` already
  rebuilds groups of nodes with up to one new value each, and the 2026-11-24 amendment to ADR 0012
  measured that at a near-fixpoint (52 instructions); the register-space window reaches the
  recompute overhead it cannot, because it needs no re-allocation.
- **Windows larger than 4 by default:** on a 40-puzzle sample 5 saved 7 instructions against 6 for
  4, at about 6 times the time per puzzle (mean 5 s, worst 39 s against 0.8 s and 4 s); kept as the
  `--window` option, not the default. Window 6 was not finished within the time box.
- **Gapped windows as a default-on gain:** hoisting or sinking one instruction found nothing the
  consecutive windows did not on the samples measured; it stays because it is cheap and tested, but
  the measured gain does not depend on it.

## Evidence
Two disjoint 40-puzzle samples of `final5.csv` (puzzles at indices 0 mod 25, and 12 mod 25),
`max_window=4`, `span=8`: 6,265 to 6,259 (-6, 4 puzzles) and 7,044 to 7,037 (-7, 4 puzzles), about
0.1% each, 0.8 s a puzzle. Extrapolated, a whole-set run saves about 170 of 178,625; this is a
sample estimate, not a whole-set measurement. The saved puzzles were already peephole fixpoints
(`optimize` on the old and the new program gave the same lengths), so the gain stacks on ADR 0012.
Control: a planted dead instruction and a planted three-step detour are removed (see
`tests/test_superopt.py`).

## Consequences
Cheap enough to run on every final file as the last step. Gains are small and shrink as solvers stop
emitting recomputations; it is not a substitute for another seed run. Not tried: windows whose
replacement also changes the destinations of live-out values, two instructions moved at once, and
larger windows with a smarter (meet-in-the-middle) search.
