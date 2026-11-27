"""Value-DAG post-pass: rebuild values from any other values of the program, then recompile.

The peephole (ADR 0012) already rewrites the value DAG, but it only accepts a rewrite whose
result still fits the register file without recomputation. This pass lifts that limit: it runs
the same DAG rewrites with unlimited virtual registers, so a value may be rebuilt from a pair of
values produced anywhere in the program (not only nearby ones), and then compiles the smaller DAG
to the real register file with recomputation (ADR 0016). Compiled length is the score of record:
a smaller DAG that needs more recomputation is discarded. The verifier is the oracle (ADR 0002).
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from multiprocessing import Pool
from pathlib import Path

from elf_abacus.io import (
    load_puzzles,
    load_submission,
    score_submission,
    write_submission,
)
from elf_abacus.peephole import (
    _depth_first_order,
    _Node,
    _reachable,
    _rederive,
    _rederive_multi,
    _rederive_with_helpers,
    _topological_order,
    build_dag,
    rematerialize,
)
from elf_abacus.verifier import InvalidProgram, Puzzle, verify

Program = list[list]


def _virtual_program(
    puzzle: Puzzle, nodes: list[_Node], keep: set[int], order: list[int]
) -> tuple[Program, int]:
    """`order` written with one register per value (never reused) and the register count."""
    reg_of: dict[int, int] = {}
    for reg, value in enumerate(puzzle.starting_values):
        start = next(
            i for i, nd in enumerate(nodes) if nd.op is None and nd.value == value
        )
        reg_of.setdefault(start, reg)
    next_reg = len(puzzle.starting_values)
    program: Program = []
    for n in order:
        reg_of[n] = next_reg
        program.append([nodes[n].op, reg_of[nodes[n].a], reg_of[nodes[n].b], next_reg])
        next_reg += 1
    return program, next_reg


def _shrunk_dag(puzzle: Puzzle, program: Program) -> tuple[list[_Node], set[int]]:
    nodes = build_dag(puzzle, program)
    by_value = {node.value: n for n, node in enumerate(nodes)}
    roots = {by_value[t] for t in puzzle.targets}

    def anywhere(_keep: set[int]) -> bool:
        return True

    live = _rederive(nodes, roots, _reachable(nodes, roots), anywhere)
    while True:
        more = None
        for new_values in (0, 1, 2):
            more = _rederive_with_helpers(
                nodes, roots, live, puzzle.value_limit, anywhere, new_values
            )
            if more is not None:
                break
        if more is None:
            more = _rederive_multi(nodes, roots, live, puzzle.value_limit, anywhere)
        if more is None:
            return nodes, live
        live = _rederive(nodes, roots, more, anywhere)


def dag_shrink(puzzle: Puzzle, program: Program) -> Program:
    """Equivalent program that is never longer; the input itself if it is invalid."""
    try:
        verify(puzzle, program)
    except InvalidProgram:
        return program
    nodes, keep = _shrunk_dag(puzzle, program)
    best = program
    for order in (_topological_order(nodes, keep), _depth_first_order(nodes, keep)):
        virtual, registers = _virtual_program(puzzle, nodes, keep, order)
        candidate = rematerialize(puzzle, virtual, registers)
        if candidate is not None and len(candidate) < len(best):
            best = candidate
    return best


def _shrink(job: tuple[Puzzle, Program]) -> Program:
    return dag_shrink(*job)


def main(argv: Sequence[str] | None = None) -> None:
    """Shrink every program of a submission file with the DAG rebuild pass."""
    parser = argparse.ArgumentParser(prog="elf_abacus.dagopt")
    parser.add_argument("--puzzles", type=Path, default=Path("data/puzzles.csv"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("submission", type=Path)
    args = parser.parse_args(argv)
    puzzles = load_puzzles(args.puzzles)
    programs = load_submission(args.submission)
    jobs = [(p, programs[p.id]) for p in puzzles]
    with Pool(args.workers) as pool:
        shrunk = pool.map(_shrink, jobs, chunksize=1)
    result = {p.id: program for p, program in zip(puzzles, shrunk, strict=True)}
    write_submission(args.out, result)
    before = sum(len(programs[p.id]) for p in puzzles)
    print(f"dagopt: {before} -> {score_submission(puzzles, result)}")


if __name__ == "__main__":
    main()
