# 0001. Python 3.12, with a native seam deferred

Status: Accepted (2026-11-18)

## Context
Competition is combinatorial optimisation over 1,000 independent puzzles, values up to 1e18,
2 months to run. We need an exact verifier, a solver search, and CSV/JSON I/O. The dev machine
has Python 3.12 (default `python3` is older: use `python3.12` for the venv) and no Rust toolchain.

## Decision
Python 3.12, standard library only to start. The verifier is the first module and the oracle
for every solver. If profiling shows search is the bottleneck, add a native hot loop behind a
narrow function seam (e.g. Rust via PyO3) in a new ADR.

## Alternatives rejected
- **Rust from day one:** fastest search, but no toolchain installed and the early work (rules,
  verifier, baseline, puzzle analysis) is I/O and exploration where speed is irrelevant. Premature.
- **Java/Kotlin:** fits the author's other projects, but weak for fast exploratory analysis;
  Kaggle tooling and shared notebooks are Python.
- **C++:** same speed as Rust with a worse safety/tooling story and no existing toolchain use here.
- **Python + numba:** int64 covers 1e18, but JIT constraints would shape the algorithms early.
