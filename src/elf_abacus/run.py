"""Per-puzzle worker: every routed solver's best program (importable so process pools can pickle it)."""

from __future__ import annotations

from elf_abacus.router import route
from elf_abacus.solvers import chain, horner
from elf_abacus.verifier import InvalidProgram, Puzzle, verify


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


def solve_one(puzzle: Puzzle, seeds: int = 3) -> dict[str, list[list] | None]:
    """Each routed solver's best program for one puzzle (module-level so it can run in a worker)."""
    plan = route(puzzle, seeds)
    chain_programs = [
        chain.solve(puzzle, pool_size=c.pool_size, pairs=c.pairs, seed=c.seed)
        for c in plan.chains
    ]
    return {
        "horner": horner.solve(puzzle) if plan.horner else None,
        "chain": _shortest(puzzle, chain_programs),
    }
