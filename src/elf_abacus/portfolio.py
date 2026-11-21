"""Combine solvers: keep the shortest verified program per puzzle."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from elf_abacus.peephole import optimize
from elf_abacus.verifier import InvalidProgram, Puzzle, verify

Program = list[list]


def best_programs(
    puzzles: Iterable[Puzzle], candidates: list[Mapping[str, Program]]
) -> dict[str, Program]:
    """Shortest valid candidate per puzzle, peephole-optimized; raises if some puzzle has none."""
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
        best[puzzle.id] = optimize(puzzle, best[puzzle.id])
    return best
