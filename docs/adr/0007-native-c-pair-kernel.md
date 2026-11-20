# 0007. A C kernel for the pair search, loaded with ctypes, NumPy kept as the fallback

Status: Accepted (2026-11-20)

Extends ADR 0005 and ADR 0006; it supersedes the "Rust or C++ extension" rejection in ADR 0005,
which said to revisit if the search had to grow.

## Context
A 50-bit target needs about 1e15 combinations on the two sides of the meet-in-the-middle; the
stored depth-3 forward set (7.5M values) times the 372k sums is about 3e12. The pair search of
ADR 0006 closes part of the gap, but NumPy must materialise every candidate pair (and does one
`searchsorted` per window edge over a 7.5M array), so it is capped at `MAX_PAIRS` candidates and
cannot probe a forward set one operation deeper than it stores (depth 4 would be ~1.8e9 values).
`cc` (Apple clang) was present on the development machine; `rustc`, `cargo` and `numba` were not.

## Decision
- `src/elf_abacus/csrc/pairs.c` holds the window expansion and gap lookup. It is compiled on first
  use with the system `cc` (`-O3 -shared -fPIC`) into `~/.cache/elf_abacus/` (override with
  `ELF_ABACUS_CACHE`), named by a hash of the source, and loaded with `ctypes`. A racing build in
  another worker writes a temporary file and renames it. `CC` selects the compiler.
- `src/elf_abacus/solvers/pairkernel.py` is the only Python that touches it. `hits_numpy` is the
  reference implementation and the automatic fallback: if there is no compiler, the build fails,
  or `ELF_ABACUS_NATIVE=0`, `find_pair` runs the NumPy path and gives the same answer.
  `tests/test_pairkernel.py` is the parity test (random inputs, every pair kind, same hits in the
  same order) and tests the fallbacks.
- Both sides of a window are found by galloping from the previous position, because the sorted
  first set makes consecutive windows move monotonically; the NumPy version needs the same
  asymptotics only for its binary searches, which is the main reason it is slower.
- `find_pair_lazy` in `src/elf_abacus/solvers/chain.py` uses a second kernel, `lazy_pair_hits`, to
  probe values `top op pool` (one operation deeper than any stored set) against the stored sets of
  at most 300k values, never storing them: for each value of the small set the window of
  admissible first values is mapped back to a window of the stored depth-3 set. It is native-only,
  bounded by a per-probe work budget, and opt-in (`solve(..., lazy=True)`).
- No new Python dependency; the compiler is optional.

## Alternatives rejected
- **Numba:** low friction to write, but a heavy install (LLVM) that is absent here, a cold JIT
  compile in every worker process, and the kernel would still need ctypes-style parity checks; a
  50-line C file is smaller, faster to start and easier to audit.
- **Rust (PyO3 or a cdylib) or Cython:** no toolchain installed, and a build backend such as
  maturin or setuptools-rust would make installation harder for this one hot loop.
- **A pre-built binary wheel or checked-in shared library:** platform-specific, unreviewable, and
  it would hide the source of truth. Only the source is checked in.
- **Making the compiler mandatory:** the repo must still run, and be tested, on a machine with no
  compiler, so the NumPy path stays complete rather than becoming dead code.
- **Larger `MAX_PAIRS` instead of a native kernel:** it did not help on the sample (a cap of 2e8
  scored 6,653 against 6,654), so the cap is not what limits the search.
- **Lazy probing against the full depth-3 set (7.5M):** about 12 s per target and no extra hit
  seen on the four targets tried; the default is therefore stored sets of at most 300k values.

## Consequences
Measured on the 28-puzzle sample (`puzzles[::len//28]`, pool 40, six workers; other sessions share
the machine, so CPU seconds are indicative):

| run | total instructions | CPU seconds |
|---|---|---|
| NumPy pair search (ADR 0006) | 6,654 | 900 |
| native pair kernel, same search | 6,654 (identical lengths) | 268 |
| native + lazy depth-4 probe | 6,556 (-1.5%) | 444 |

Per target the pair search took 1.0 s -> 0.08 s on a large-target puzzle and 0.43 s -> 0.09 s on
a dense one (the NumPy time is dominated by window binary searches, which galloping removes).
Resident memory per worker is unchanged (~1.2-1.5 GB), because the stored forward sets dominate; the
native path removes only the NumPy candidate-pair temporaries. The gain from the extra headroom is
small: most of the speed-up is better spent on more pool sizes and seeds in the portfolio than on
the lazy probe, which should be added to `src/elf_abacus/run.py` only after a whole-set run shows it
pays. Open risk: a compiler difference could change hit order on overflow of the hit cap
(`DEFAULT_HIT_CAP`); below the cap the parity test shows identical results. The code is the
authority for constants (`LAZY_BUDGET`, `PAIR_TERMS`, the flags in `pairkernel.py`).

## Amendment 2026-11-20 (integration)
PR 9 merged this with ADRs 0007-0010 together. The whole-set score of the combined solver was 218,259 (218,127 as best-of with the earlier file, Kaggle-confirmed) against 222,529 before: -2.0%, well under the sum of the sample gains, so the four overlap. `run.solve_one` now passes `lazy=True` for every chain run (it falls back to NumPy when the native kernel is unavailable). That whole-set run enabled lazy together with the other three, so the lazy probe's own contribution was not isolated; the sentence above about adding it only after a whole-set run that shows it pays was not met in isolation.
