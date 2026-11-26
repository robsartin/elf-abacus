"""Crossover of candidate programs: each value may come from a different candidate's derivation.

Best-of keeps one whole program per puzzle. Here every verified candidate contributes the
derivations it used (value -> (op, left, right)); a local search over the shared pool picks one
derivation per needed value so the set of computed values is as small as possible, and the result
is compiled to the real register file with recomputation and the peephole post-pass.
"""

from __future__ import annotations

import argparse
import dataclasses
import heapq
import multiprocessing
import random
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path

from elf_abacus.io import (
    load_puzzles,
    load_submission,
    score_submission,
    write_submission,
)
from elf_abacus.peephole import build_dag, optimize, rematerialize
from elf_abacus.verifier import InvalidProgram, Puzzle, verify

Program = list[list]
Derivation = tuple[str, int, int]  # op, left value, right value
VIRTUAL_REGISTERS = 256
BASES = 6  # starting candidates merged, shortest first
REFINED = 2  # best merged plans refined by compiled length
REFINE_BUDGET = 10  # compiled-length evaluations per refined plan
ORDER_TRIES = 40  # perturbed emission orders compiled per refined plan
UNFIT = 10**9  # cost of a plan that does not fit the register file


def _virtual(puzzle: Puzzle) -> Puzzle:
    return dataclasses.replace(puzzle, registers=VIRTUAL_REGISTERS)


def derivations(
    puzzle: Puzzle, programs: Iterable[Program]
) -> dict[int, set[Derivation]]:
    """Every way each value was made by any of the programs (value-level, register names erased)."""
    pool: dict[int, set[Derivation]] = {}
    for program in programs:
        nodes = build_dag(_virtual(puzzle), program)
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


def merge_plan(
    puzzle: Puzzle, base: Program, pool: Mapping[int, set[Derivation]]
) -> dict[int, Derivation] | None:
    """Fewest-values plan reached from `base` by swapping in pooled derivations."""
    starts = set(puzzle.starting_values)
    roots = [t for t in puzzle.targets if t not in starts]
    nodes = build_dag(_virtual(puzzle), base)
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
    return current


def merge_derivations(
    puzzle: Puzzle, base: Program, pool: Mapping[int, set[Derivation]]
) -> Program | None:
    """`merge_plan` compiled to a program with a register per value (virtual registers)."""
    plan = merge_plan(puzzle, base, pool)
    return None if plan is None else _compile(puzzle, plan)


def refine_by_cost(
    puzzle: Puzzle,
    plan: Mapping[int, Derivation],
    pool: Mapping[int, set[Derivation]],
    cost: Callable[[Mapping[int, Derivation]], int],
    budget: int,
) -> dict[int, Derivation]:
    """First-improvement search over single-derivation swaps, scored by `cost` (at most `budget` calls).

    The value count is only a proxy for the compiled length (registers force recomputation), so the
    swaps are judged by the real objective instead; the result never costs more than `plan`.
    """
    starts = set(puzzle.starting_values)
    roots = [t for t in puzzle.targets if t not in starts]
    current = dict(plan)
    current_cost = cost(current)
    spent = 1
    improved = True
    while improved and spent < budget:
        improved = False
        for value in list(current):
            for option in sorted(pool.get(value, ())):
                if option == current[value]:
                    continue
                trial = _closure(pool, current, roots, starts, {value: option})
                if trial is None or trial == current:
                    continue
                spent += 1
                trial_cost = cost(trial)
                if trial_cost < current_cost:
                    current, current_cost, improved = trial, trial_cost, True
                    break
                if spent >= budget:
                    return current
            if improved:
                break
    return current


def _depth_first_values(puzzle: Puzzle, plan: Mapping[int, Derivation]) -> list[int]:
    """Values in the order `_compile` emits them."""
    seen = set(puzzle.starting_values)
    order: list[int] = []

    def visit(x: int) -> None:
        if x in seen:
            return
        seen.add(x)
        visit(plan[x][1])
        visit(plan[x][2])
        order.append(x)

    for target in puzzle.targets:
        visit(target)
    return order


def emit_in_priority_order(
    puzzle: Puzzle,
    plan: Mapping[int, Derivation],
    priority: Callable[[int], float],
) -> Program:
    """Program with a register per value, emitting the ready value of lowest priority next.

    Order decides how long values stay live, so it decides how much the 48-register compile has to
    recompute; any priority still gives a valid program because operands always come first.
    """
    starts = len(puzzle.starting_values)
    reg: dict[int, int] = {}
    for i, value in enumerate(puzzle.starting_values):
        reg.setdefault(value, i)
    needed: set[int] = set()
    stack = list(puzzle.targets)
    while stack:
        x = stack.pop()
        if x in reg or x in needed:
            continue
        needed.add(x)
        stack += [plan[x][1], plan[x][2]]
    waiting = {x: len({plan[x][1], plan[x][2]} & needed) for x in needed}
    users: dict[int, list[int]] = {}
    for x in needed:
        for operand in {plan[x][1], plan[x][2]} & needed:
            users.setdefault(operand, []).append(x)
    ready = [(priority(x), x) for x in needed if waiting[x] == 0]
    heapq.heapify(ready)
    program: Program = []
    while ready:
        _, x = heapq.heappop(ready)
        op, a, b = plan[x]
        reg[x] = starts + len(program)
        program.append([op, reg[a], reg[b], reg[x]])
        for user in users.get(x, ()):
            waiting[user] -= 1
            if waiting[user] == 0:
                heapq.heappush(ready, (priority(user), user))
    return program


def search_orders(
    puzzle: Puzzle,
    plan: Mapping[int, Derivation],
    cost: Callable[[Program], int],
    tries: int,
    seed: int,
) -> Program:
    """Lowest-cost emission of `plan` among the depth-first default and `tries` perturbed orders.

    Each try keeps the default order's rank with noise of growing size (the last ones are fully
    random), so the search ranges from small reshuffles to unrelated schedules.
    """
    best = _compile(puzzle, plan)
    best_cost = cost(best)
    value_rank = {x: i for i, x in enumerate(_depth_first_values(puzzle, plan))}
    rng = random.Random(seed)
    sigmas = (2.0, 8.0, 32.0, 1e9)
    for i in range(tries):
        sigma = sigmas[i % len(sigmas)]
        noise = {x: value_rank.get(x, 0) + rng.gauss(0, sigma) for x in plan}
        program = emit_in_priority_order(puzzle, plan, noise.__getitem__)
        program_cost = cost(program)
        if program_cost < best_cost:
            best, best_cost = program, program_cost
    return best


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

    def rematerialized(program: Program) -> Program | None:
        return rematerialize(
            puzzle, program, len(puzzle.starting_values) + len(program) + 1
        )

    def program_length(program: Program) -> int:
        out = rematerialized(program)
        return UNFIT if out is None else len(out)

    def plan_length(plan: Mapping[int, Derivation]) -> int:
        return program_length(_compile(puzzle, plan))

    plans: list[dict[int, Derivation]] = []
    for base in sorted(valid, key=len)[:BASES]:
        plan = merge_plan(puzzle, base, pool)
        if plan is not None and plan not in plans:
            plans.append(plan)
    scored = sorted((plan_length(plan), i) for i, plan in enumerate(plans))
    for _, i in scored[:REFINED]:
        plan = refine_by_cost(puzzle, plans[i], pool, plan_length, REFINE_BUDGET)
        merged = search_orders(puzzle, plan, program_length, ORDER_TRIES, seed=i)
        compiled = rematerialized(merged)
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
    if uncovered := [p.id for p, candidates in jobs if not candidates]:
        raise SystemExit(f"no candidate program in any file for {uncovered[:5]}")
    with multiprocessing.Pool(args.workers) as pool:
        results = pool.map(_cross_one, jobs, chunksize=1)
    merged = {p.id: program for p, program in zip(puzzles, results, strict=True)}
    write_submission(args.out, merged)
    print(f"crossover of {len(files)} files: {score_submission(puzzles, merged)}")


if __name__ == "__main__":
    main()
