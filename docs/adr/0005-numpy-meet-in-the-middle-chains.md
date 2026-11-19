# 0005. Vectorised meet-in-the-middle chains over a constant pool (NumPy)

Status: Accepted (2026-11-19)

## Context
Independent and mixed puzzles ask for about 27 near-random targets of 10^9 to 10^18 each. Probing
the practice data showed no hidden structure to recover: no target lies within three operation
levels of the starting values, none is a short chain over them, and none is one operation from
earlier targets. Each instruction can carry at most log2(6 ops x 48 x 48) ~ 13.8 bits, and the
scored targets total ~995k bits, so the floor is ~72k instructions. A fixed pool of ~40 registers
gives ~7 bits per chain step, and the Horner solver (`src/elf_abacus/solvers/horner.py`) managed only ~3. The gap is the search method, not missing structure.

## Decision
`src/elf_abacus/solvers/chain.py` builds, per puzzle, a pool of constants (log-uniform magnitudes,
each one instruction from earlier values) and enumerates once: forward values `pool op pool (op
pool)...` to depth 3, and every signed sum of up to four pool values. A target is found by a
sorted-array lookup of `target - forward` in the sums (iterating the smaller side). When no direct
chain exists, the nearest forward value is used and the gap is solved by a nested plan. NumPy
provides the vectorised build and lookups, so NumPy is a runtime dependency of the solvers (the
verifier stays standard-library only, ADR 0002).

## Alternatives rejected
- **Pure-Python search:** each target needs ~10^6 to 10^7 lookups; interpreted loops would take
  days across the 27k targets.
- **Numba:** would work, but ties the algorithms to JIT-compilable shapes and adds a heavy
  dependency before NumPy has been shown insufficient.
- **Rust or C++ extension:** fastest, but no toolchain is installed and the vectorised version
  already runs the whole set in minutes on 28 cores; revisit (new ADR) if search size must grow.
- **Hash sets instead of sorted arrays:** Python sets cost ~10x the memory of int64 arrays at the
  tens-of-millions scale and cannot be searched vectorised.
- **Keep improving Horner:** capped near 3 bits per instruction by construction.
