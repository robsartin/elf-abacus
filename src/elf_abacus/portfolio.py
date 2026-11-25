"""Combine solvers: keep the shortest verified program per puzzle."""

from __future__ import annotations

import argparse
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from elf_abacus.io import (
    load_puzzles,
    load_submission,
    score_submission,
    write_submission,
)
from elf_abacus.peephole import optimize
from elf_abacus.verifier import InvalidProgram, Puzzle, verify

Program = list[list]


def best_programs(
    puzzles: Iterable[Puzzle],
    candidates: list[Mapping[str, Program]],
    polish: bool = True,
) -> dict[str, Program]:
    """Shortest valid candidate per puzzle, peephole-optimized unless `polish` is off; raises if some puzzle has none."""
    best: dict[str, Program] = {}
    for puzzle in puzzles:
        for solver in candidates:
            program = solver.get(puzzle.id)
            if program is None or (
                puzzle.id in best and len(program) >= len(best[puzzle.id])
            ):
                continue
            try:
                verify(puzzle, program)
            except InvalidProgram:
                continue
            best[puzzle.id] = program
        if puzzle.id not in best:
            raise InvalidProgram(f"{puzzle.id}: no valid candidate program")
        if polish:
            best[puzzle.id] = optimize(puzzle, best[puzzle.id])
    return best


def main(argv: Sequence[str] | None = None) -> None:
    """Merge submission files: keep the shortest verified program per puzzle and print the total."""
    parser = argparse.ArgumentParser(prog="elf_abacus.portfolio")
    parser.add_argument("--puzzles", type=Path, default=Path("data/puzzles.csv"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--polish",
        action="store_true",
        help="also run the peephole pass over every winner (slow: about 3 s per program)",
    )
    parser.add_argument("submissions", type=Path, nargs="+")
    args = parser.parse_args(argv)
    puzzles = load_puzzles(args.puzzles)
    merged = best_programs(
        puzzles, [load_submission(p) for p in args.submissions], polish=args.polish
    )
    write_submission(args.out, merged)
    print(f"best of {len(args.submissions)} files: {score_submission(puzzles, merged)}")


if __name__ == "__main__":
    main()
