"""`python -m elf_abacus solve`: run solvers, keep the best verified program per puzzle."""

from __future__ import annotations

import argparse
from pathlib import Path

from elf_abacus.io import (
    load_puzzles,
    load_submission,
    score_submission,
    write_submission,
)
from elf_abacus.portfolio import best_programs
from elf_abacus.solvers import horner


def main() -> None:
    parser = argparse.ArgumentParser(prog="elf_abacus")
    parser.add_argument("--puzzles", type=Path, default=Path("data/puzzles.csv"))
    parser.add_argument(
        "--baseline", type=Path, default=Path("data/sample_submission.csv")
    )
    parser.add_argument("--out", type=Path, default=Path("submissions/latest.csv"))
    args = parser.parse_args()

    puzzles = load_puzzles(args.puzzles)
    baseline = load_submission(args.baseline)
    solved = {p.id: prog for p in puzzles if (prog := horner.solve(p)) is not None}
    print(f"horner solved {len(solved)}/{len(puzzles)} puzzles")
    best = best_programs(puzzles, [baseline, solved])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_submission(args.out, best)
    # Re-read the written file and score it independently of the in-memory result.
    total = score_submission(puzzles, load_submission(args.out))
    print(
        f"baseline {score_submission(puzzles, baseline)} -> best {total} -> {args.out}"
    )


if __name__ == "__main__":
    main()
