"""Per-puzzle worker: every routed solver's best program (importable so process pools can pickle it)."""

from __future__ import annotations

import dataclasses

from elf_abacus.peephole import rematerialize
from elf_abacus.router import ChainRun, route
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


def _run_chain(puzzle: Puzzle, c: ChainRun) -> list[list] | None:
    planned = dataclasses.replace(puzzle, registers=c.virtual) if c.virtual else puzzle
    program = chain.solve(
        planned,
        pool_size=c.pool_size,
        pairs=c.pairs,
        seed=c.seed,
        grow=c.grow,
        relate=c.relate,
        keep_inner=c.keep_inner,
        retain=c.retain,
    )
    if program is None or not c.virtual:
        return program
    return rematerialize(puzzle, program, c.virtual)


def solve_one(puzzle: Puzzle, seeds: int = 3) -> dict[str, list[list] | None]:
    """Each routed solver's best program for one puzzle (module-level so it can run in a worker)."""
    plan = route(puzzle, seeds)
    best = _shortest(puzzle, [_run_chain(puzzle, c) for c in plan.chains])
    for c in plan.fallback:
        if best is not None:
            break
        best = _shortest(puzzle, [_run_chain(puzzle, c)])
    return {
        "horner": horner.solve(puzzle) if plan.horner else None,
        "chain": best,
    }
