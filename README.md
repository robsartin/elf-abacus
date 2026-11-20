# elf-abacus

Entry for Kaggle's [Santa 2026 – The Elf Calculator](https://www.kaggle.com/competitions/santa-2026).

Build each of 1,000 target lists from a few starting values using `+ - * /` on at most 48
registers (positive integers, exact division, bounded by `value_limit`). Score = total
instruction count across all puzzles; lower is better.

## Setup

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
```

Put `puzzles.csv` / `practice_puzzles.csv` in `data/` (git-ignored; competition data is not
redistributable). Rules, format and limits live on the competition's Data and Evaluation pages.

### Optional native kernel

The pair search has a C kernel (`src/elf_abacus/csrc/pairs.c`, ADR 0007). It is compiled
automatically on first use with the system `cc` into `~/.cache/elf_abacus/` and loaded with
`ctypes`; nothing to install. Without a compiler the pure-NumPy path runs instead, with the same
results but about 3x slower. `ELF_ABACUS_NATIVE=0` forces NumPy; `CC=...` picks the compiler;
`ELF_ABACUS_CACHE=...` moves the build cache. The opt-in lazy depth-4 probe
(`chain.solve(..., lazy=True)`) needs the native kernel.

## Run

```bash
.venv/bin/python -m elf_abacus   # writes submissions/latest.csv, prints score
```

## Layout

- `src/elf_abacus/` library (verifier first, then solvers)
- `tests/` pytest
- `docs/adr/` architecture decision records

License: Apache-2.0.
