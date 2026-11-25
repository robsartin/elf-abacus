"""Crossover of candidate programs: each value may come from a different candidate's derivation.

Best-of keeps one whole program per puzzle. Here every verified candidate contributes the
derivations it used (value -> (op, left, right)); a local search over the shared pool picks one
derivation per needed value so the set of computed values is as small as possible, and the result
is compiled to the real register file with recomputation and the peephole post-pass.
"""

from __future__ import annotations

import argparse
import dataclasses
import multiprocessing
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from elf_abacus.io import (
    load_puzzles,
    load_submission,
    score_submission,
    write_submission,
)
from elf_abacus.peephole import _build_dag, optimize, rematerialize
from elf_abacus.verifier import InvalidProgram, Puzzle, verify

Program = list[list]
Derivation = tuple[str, int, int]  # op, left value, right value
VIRTUAL_REGISTERS = 256


def _virtual(puzzle: Puzzle) -> Puzzle:
    return dataclasses.replace(puzzle, registers=VIRTUAL_REGISTERS)


def derivations(
    puzzle: Puzzle, programs: Iterable[Program]
) -> dict[int, set[Derivation]]:
    """Every way each value was made by any of the programs (value-level, register names erased)."""
    pool: dict[int, set[Derivation]] = {}
    for program in programs:
        nodes = _build_dag(_virtual(puzzle), program)
        for node in nodes:
            if node.op is not None:
                pool.setdefault(node.value, set()).add(
                    (node.op, nodes[node.a].value, nodes[node.b].value)
                )
    return pool


def _closure(
    pool: Mapping[int, set[Derivation]],
    chosen: Mapping[int, Derivation],
    roots: Sequence[int],
    starts: set[int],
    override: Mapping[int, Derivation] | None = None,
) -> dict[int, Derivation] | None:
    """One derivation per value reachable from `roots`; unchosen values pick the cheapest in the pool."""
    out: dict[int, Derivation] = {}
    busy: set[int] = set()

    def have(x: int) -> bool:
        return x in starts or x in out

    def need(x: int) -> bool:
        if have(x):
            return True
        if x in busy:
            return False
        busy.add(x)
        if override and x in override:
            options = [override[x]]
        elif x in chosen:
            options = [chosen[x]]
        else:
            options = sorted(
                pool.get(x, ()), key=lambda t: (not have(t[1])) + (not have(t[2]))
            )
        for option in options:
            snapshot = dict(out)
            if need(option[1]) and need(option[2]):
                out[x] = option
                busy.discard(x)
                return True
            out.clear()
            out.update(snapshot)
        busy.discard(x)
        return False

    for root in roots:
        if not need(root):
            return None
    return out


def _compile(puzzle: Puzzle, chosen: Mapping[int, Derivation]) -> Program:
    """Operands-first program giving every chosen value a register of its own."""
    reg: dict[int, int] = {}
    for i, value in enumerate(puzzle.starting_values):
        reg.setdefault(value, i)
    program: Program = []
    done: set[int] = set()

    def visit(x: int) -> None:
        if x in reg or x in done:
            return
        done.add(x)
        _, a, b = chosen[x]
        visit(a)
        visit(b)
        reg[x] = len(puzzle.starting_values) + len(program)
        op, a, b = chosen[x]
        program.append([op, reg[a], reg[b], reg[x]])

    for target in puzzle.targets:
        visit(target)
    return program


def merge_derivations(
    puzzle: Puzzle, base: Program, pool: Mapping[int, set[Derivation]]
) -> Program | None:
    """Fewest-values program (virtual registers) reached from `base` by swapping in pooled derivations."""
    starts = set(puzzle.starting_values)
    roots = [t for t in puzzle.targets if t not in starts]
    nodes = _build_dag(_virtual(puzzle), base)
    chosen = {
        n.value: (n.op, nodes[n.a].value, nodes[n.b].value) for n in nodes if n.op
    }
    current = _closure(pool, chosen, roots, starts)
    if current is None:
        return None
    improved = True
    while improved:
        improved = False
        for value in list(current):
            for option in sorted(pool.get(value, ())):
                if option == current[value]:
                    continue
                trial = _closure(pool, current, roots, starts, {value: option})
                if trial is not None and len(trial) < len(current):
                    current, improved = trial, True
                    break
            if improved:
                break
    return _compile(puzzle, current)


def crossover(puzzle: Puzzle, candidates: Iterable[Program]) -> Program:
    """Shortest verified program built from the candidates' derivations; never longer than the best input."""
    valid: list[Program] = []
    for program in candidates:
        try:
            verify(_virtual(puzzle), program)
        except InvalidProgram:
            continue
        valid.append(program)
    best: Program | None = None
    for program in valid:
        try:
            verify(puzzle, program)
        except InvalidProgram:
            continue
        if best is None or len(program) < len(best):
            best = program
    if not valid:
        raise InvalidProgram(f"{puzzle.id}: no valid candidate program")
    pool = derivations(puzzle, valid)
    for base in sorted(valid, key=len)[:2]:
        merged = merge_derivations(puzzle, base, pool)
        if merged is None:
            continue
        compiled = rematerialize(
            puzzle, merged, len(puzzle.starting_values) + len(merged) + 1
        )
        if compiled is None:
            continue
        compiled = optimize(puzzle, compiled)
        try:
            verify(puzzle, compiled)
        except InvalidProgram:
            continue
        if best is None or len(compiled) < len(best):
            best = compiled
    if best is None:
        raise InvalidProgram(
            f"{puzzle.id}: no candidate fits {puzzle.registers} registers"
        )
    return best


def _cross_one(job: tuple[Puzzle, list[Program]]) -> Program:
    puzzle, candidates = job
    return crossover(puzzle, candidates)


def main(argv: Sequence[str] | None = None) -> None:
    """Cross the candidate files over every puzzle and print the total."""
    parser = argparse.ArgumentParser(prog="elf_abacus.crossover")
    parser.add_argument("--puzzles", type=Path, default=Path("data/puzzles.csv"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("submissions", type=Path, nargs="+")
    args = parser.parse_args(argv)
    puzzles = load_puzzles(args.puzzles)
    files = [load_submission(p) for p in args.submissions]
    jobs = [(p, [f[p.id] for f in files if p.id in f]) for p in puzzles]
    with multiprocessing.Pool(args.workers) as pool:
        results = pool.map(_cross_one, jobs, chunksize=1)
    merged = {p.id: program for p, program in zip(puzzles, results, strict=True)}
    write_submission(args.out, merged)
    print(f"crossover of {len(files)} files: {score_submission(puzzles, merged)}")


if __name__ == "__main__":
    main()
