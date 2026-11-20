"""Per-puzzle worker: every solver's best program (importable so process pools can pickle it)."""

from __future__ import annotations

from elf_abacus.solvers import chain, horner
from elf_abacus.verifier import InvalidProgram, Puzzle, verify

CHAIN_POOL_SIZES = (24, 32, 40)


def _shortest(puzzle: Puzzle, programs: list[list[list] | None]) -> list[list] | None:
    best = None
    for program in programs:
        if program is None or (best is not None and len(program) >= len(best)):
            continue
        try:
            verify(puzzle, program)
        except InvalidProgram:
            continue
        best = program
    return best


def solve_one(puzzle: Puzzle) -> dict[str, list[list] | None]:
    """Every solver's best program for one puzzle (module-level so it can run in a worker)."""
    chain_programs = [chain.solve(puzzle, pool_size=n) for n in CHAIN_POOL_SIZES]
    return {
        "horner": horner.solve(puzzle),
        "chain": _shortest(puzzle, chain_programs),
    }
