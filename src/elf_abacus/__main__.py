"""`python -m elf_abacus`: run solvers in parallel, keep the best verified program per puzzle."""

from __future__ import annotations

import argparse
import os
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from pathlib import Path

from elf_abacus.io import (
    load_puzzles,
    load_submission,
    score_submission,
    write_submission,
)
from elf_abacus.portfolio import best_programs
from elf_abacus.run import solve_one


def main() -> None:
    parser = argparse.ArgumentParser(prog="elf_abacus")
    parser.add_argument("--puzzles", type=Path, default=Path("data/puzzles.csv"))
    parser.add_argument(
        "--baseline", type=Path, default=Path("data/sample_submission.csv")
    )
    parser.add_argument("--out", type=Path, default=Path("submissions/latest.csv"))
    parser.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    parser.add_argument(
        "--limit", type=int, default=0, help="only the first N puzzles (testing)"
    )
    parser.add_argument(
        "--seeds",
        type=int,
        default=3,
        help="chain runs (distinct constant pools) per many-target puzzle",
    )
    parser.add_argument(
        "--seed-offset",
        type=int,
        default=0,
        help="first chain seed (a different offset gives different constant pools)",
    )
    args = parser.parse_args()

    puzzles = load_puzzles(args.puzzles)
    if args.limit:
        puzzles = puzzles[: args.limit]
    baseline = load_submission(args.baseline)
    with ProcessPoolExecutor(args.workers) as pool:
        results = list(
            pool.map(
                partial(solve_one, seeds=args.seeds, seed_offset=args.seed_offset),
                puzzles,
                chunksize=4,
            )
        )
    candidates: dict[str, dict[str, list[list]]] = {}
    for puzzle, programs in zip(puzzles, results, strict=True):
        for name, program in programs.items():
            if program is not None:
                candidates.setdefault(name, {})[puzzle.id] = program
    for name, found in candidates.items():
        print(
            f"{name}: {len(found)}/{len(puzzles)} puzzles, total {sum(map(len, found.values()))}"
        )
    best = best_programs(puzzles, [baseline, *candidates.values()])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_submission(args.out, best)
    # Re-read the written file and score it independently of the in-memory result.
    total = score_submission(puzzles, load_submission(args.out))
    print(f"best {total} over {len(puzzles)} puzzles -> {args.out}")


if __name__ == "__main__":
    main()
