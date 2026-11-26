"""Window superoptimiser: exhaustively shorten small stretches of a finished program.

Where the peephole (ADR 0012) rebuilds the value DAG, this works on the instruction list itself.
A window is a few consecutive instructions. Everything after it only observes (a) the registers it
reads before overwriting them (live-out) and (b) the target values nothing else produces, so any
shorter sequence that leaves the live-out registers holding the same values and still produces
those targets can replace the window, with the rest of the program untouched and no register
re-allocation. The replacement may read any register's current value and write the window's own
destinations or registers that are dead there. The verifier stays the oracle (ADR 0002).
"""

from __future__ import annotations

import argparse
import time
from collections.abc import Iterator, Sequence
from multiprocessing import Pool
from pathlib import Path

from elf_abacus.io import (
    load_puzzles,
    load_submission,
    score_submission,
    write_submission,
)
from elf_abacus.verifier import InvalidProgram, Puzzle, verify

Program = list[list]
State = dict[int, int]
Step = tuple[str, int, int, int]

MAX_WINDOW = 4  # instructions per window searched by default
MAX_SPAN = 8  # how far apart two instructions of a gapped window may be
DEAD_SCRATCH = 2  # dead registers offered as scratch space per window
STEP_CAP = 6  # alternative operand pairs tried per wanted value


def _apply(op: str, a: int, b: int, limit: int) -> int | None:
    """The calculator's rules: value of `a op b`, or None when the verifier would reject it."""
    if op == "+":
        value = a + b
    elif op == "-":
        if a <= b:
            return None
        value = a - b
    elif op == "*":
        value = a * b
    else:
        if b == 0 or a % b:
            return None
        value = a // b
    return value if 0 < value <= limit else None


def _holders(state: State) -> dict[int, list[int]]:
    """Registers holding each value."""
    holders: dict[int, list[int]] = {}
    for reg, value in state.items():
        holders.setdefault(value, []).append(reg)
    return holders


def _one_step(
    state: State,
    want: int,
    limit: int,
    cap: int = STEP_CAP,
    holders: dict[int, list[int]] | None = None,
) -> list[Step]:
    """Up to `cap` instructions (op, left reg, right reg) over `state` that yield `want`.

    `holders` is `_holders(state)` when the caller already has it (the search asks many wants
    of one state).
    """
    if holders is None:
        holders = _holders(state)
    seen: set[tuple[str, int, int]] = set()
    found: list[Step] = []
    for ra, a in state.items():
        partners: list[tuple[str, int]] = []
        if want > a:
            partners.append(("+", want - a))
        if a > want:
            partners.append(("-", a - want))
        if a and want % a == 0:
            partners.append(("*", want // a))
        if a % want == 0:
            partners.append(("/", a // want))
        for op, b in partners:
            for rb in holders.get(b, ()):
                key = (op, min(ra, rb), max(ra, rb)) if op in "+*" else (op, ra, rb)
                if key in seen or _apply(op, a, b, limit) != want:
                    continue
                seen.add(key)
                found.append((op, ra, rb, -1))
                if len(found) >= cap:
                    return found
    return found[:cap]


def _helper_values(state: State, needs: set[int], limit: int) -> Iterator[int]:
    """Values worth building as a stepping stone: one operand of a one-step route to a need."""
    values = set(state.values())
    seen: set[int] = set()
    for need in sorted(needs):
        for x in sorted(values):
            guesses = [need - x, x - need, need * x]
            if x and need % x == 0:
                guesses.append(need // x)
            if need and x % need == 0:
                guesses.append(x // need)
            for h in guesses:
                if 0 < h <= limit and h not in values and h not in seen:
                    seen.add(h)
                    yield h


def _search(
    state: State,
    held: dict[int, int],
    targets: set[int],
    scratch: list[int],
    limit: int,
    budget: int,
) -> list[Step] | None:
    """At most `budget` instructions after which `held` registers hold their values and every
    value in `targets` has been produced (or is in `state` already), or None.

    Productive moves build a wanted value straight into the register that wants it (or a scratch
    register for a target nobody holds); with slack left, a helper value that opens a one-step
    route to a wanted value is built into a scratch register first.
    """

    dead: set[tuple[tuple[tuple[int, int], ...], frozenset[int], int]] = set()

    def dfs(st: State, produced: frozenset[int], budget: int) -> list[Step] | None:
        key = (tuple(sorted(st.items())), produced, budget)
        if key in dead:
            return None
        found = expand(st, produced, budget)
        if found is None:
            dead.add(key)
        return found

    def expand(st: State, produced: frozenset[int], budget: int) -> list[Step] | None:
        held_by = _holders(st)
        wrong = {r: v for r, v in held.items() if st.get(r) != v}
        loose = {v for v in targets if v not in produced} - set(wrong.values())
        if not wrong and not loose:
            return []
        floor = len(wrong) + len(loose)
        if floor > budget:
            return None
        for reg, value in sorted(wrong.items()):
            for op, ra, rb, _ in _one_step(st, value, limit, cap=1, holders=held_by):
                rest = dfs({**st, reg: value}, produced | {value}, budget - 1)
                if rest is not None:
                    return [(op, ra, rb, reg), *rest]
        for value in sorted(loose):
            for op, ra, rb, _ in _one_step(st, value, limit, cap=1, holders=held_by):
                for reg in scratch:
                    rest = dfs({**st, reg: value}, produced | {value}, budget - 1)
                    if rest is not None:
                        return [(op, ra, rb, reg), *rest]
        if budget > floor:
            needs = set(wrong.values()) | loose
            blocked = {
                n for n in needs if not _one_step(st, n, limit, cap=1, holders=held_by)
            }
            for h in _helper_values(st, blocked, limit):
                for op, ra, rb, _ in _one_step(st, h, limit, cap=1, holders=held_by):
                    for reg in scratch:
                        made = produced | ({h} if h in targets else set())
                        rest = dfs({**st, reg: h}, made, budget - 1)
                        if rest is not None:
                            return [(op, ra, rb, reg), *rest]
        return None

    return dfs(state, frozenset(), budget)


def _states(puzzle: Puzzle, program: Program) -> list[State] | None:
    """Register contents before each instruction (and after the last); None if it does not run."""
    regs: State = dict(enumerate(puzzle.starting_values))
    out = [dict(regs)]
    for op, i, j, d in program:
        if i not in regs or j not in regs:
            return None
        value = _apply(op, regs[i], regs[j], puzzle.value_limit)
        if value is None:
            return None
        regs[d] = value
        out.append(dict(regs))
    return out


def _live_in(program: Program) -> list[set[int]]:
    """For each position, the registers read at or after it before being overwritten."""
    live: list[set[int]] = [set() for _ in range(len(program) + 1)]
    for i in range(len(program) - 1, -1, -1):
        _, a, b, d = program[i]
        live[i] = (live[i + 1] - {d}) | {a, b}
    return live


def _try_window(
    puzzle: Puzzle,
    program: Program,
    states: list[State],
    live: list[set[int]],
    start: int,
    length: int,
) -> Program | None:
    end = start + length
    after = states[end]
    reads = live[end]
    held = {r: after[r] for r in reads if r in after}
    first_made: dict[int, list[int]] = {}
    for pos, (_, _, _, d) in enumerate(program):
        first_made.setdefault(states[pos + 1][d], []).append(pos)
    needed = {
        t
        for t in puzzle.targets
        if t not in puzzle.starting_values
        and all(start <= p < end for p in first_made.get(t, [-1]))
    }
    dests = {program[p][3] for p in range(start, end)}
    scratch = sorted(dests - reads)
    scratch += [
        r for r in range(puzzle.registers) if r not in reads and r not in dests
    ][:DEAD_SCRATCH]
    steps = _search(
        states[start], held, needed, scratch, puzzle.value_limit, length - 1
    )
    if steps is None:
        return None
    candidate = [*program[:start], *(list(s) for s in steps), *program[end:]]
    try:
        verify(puzzle, candidate)
    except InvalidProgram:
        return None
    return candidate


def shrink_window(
    puzzle: Puzzle, program: Program, start: int, length: int
) -> Program | None:
    """A strictly shorter equivalent of `program` with `length` instructions from `start`
    replaced, or None when no shorter replacement of that window exists."""
    states = _states(puzzle, program)
    if states is None or start < 0 or start + length > len(program):
        return None
    return _try_window(puzzle, program, states, _live_in(program), start, length)


def _independent(x: list, y: list) -> bool:
    """Adjacent instructions x then y can trade places."""
    return x[3] not in (y[1], y[2], y[3]) and y[3] not in (x[1], x[2])


def _hoist(program: Program, j: int, i: int) -> Program | None:
    """Instruction j moved earlier to position i, or None if a hazard blocks it."""
    out = list(program)
    for p in range(j, i, -1):
        if not _independent(out[p - 1], out[p]):
            return None
        out[p - 1], out[p] = out[p], out[p - 1]
    return out


def _sink(program: Program, i: int, j: int) -> Program | None:
    """Instruction i moved later to position j, or None if a hazard blocks it."""
    out = list(program)
    for p in range(i, j):
        if not _independent(out[p], out[p + 1]):
            return None
        out[p], out[p + 1] = out[p + 1], out[p]
    return out


def _improve(
    puzzle: Puzzle,
    program: Program,
    max_window: int,
    span: int,
    start: int,
    deadline: float,
) -> tuple[Program, int] | None:
    """The first shortening found at or after position `start`, with where it began."""
    n = len(program)
    states = _states(puzzle, program)
    if states is None:
        return None
    live = _live_in(program)
    for s in range(start, n):
        for k in range(2, max_window + 1):
            if s + k <= n:
                found = _try_window(puzzle, program, states, live, s, k)
                if found is not None:
                    return found, s
        for j in range(s + 2, min(n, s + span + 1)):
            for variant in (_hoist(program, j, s + 1), _sink(program, s, j - 1)):
                if variant is None:
                    continue
                v_states = _states(puzzle, variant)
                if v_states is None:
                    continue
                v_live = _live_in(variant)
                for k in range(2, max_window + 1):
                    if s + k > n:
                        break
                    found = _try_window(puzzle, variant, v_states, v_live, s, k)
                    if found is not None:
                        return found, s
        if time.monotonic() > deadline:
            return None
    return None


def superoptimize(
    puzzle: Puzzle,
    program: Program,
    max_window: int = MAX_WINDOW,
    span: int = MAX_SPAN,
    seconds: float = 120.0,
) -> Program:
    """Equivalent program that is never longer; the input itself if it is invalid.

    Repeatedly replaces a window of up to `max_window` instructions (consecutive, or an
    instruction with one that is up to `span` positions away moved next to it) by a shorter
    sequence, until none shrinks or `seconds` run out.
    """
    try:
        verify(puzzle, program)
    except InvalidProgram:
        return program
    deadline = time.monotonic() + seconds
    current = [list(ins) for ins in program]
    start = 0
    while (
        step := _improve(puzzle, current, max_window, span, start, deadline)
    ) is not None:
        current, found_at = step
        start = max(0, found_at - max_window)
    return current if len(current) < len(program) else program


def superoptimize_fixpoint(
    puzzle: Puzzle,
    program: Program,
    max_window: int = MAX_WINDOW,
    span: int = MAX_SPAN,
    seconds: float = 120.0,
) -> Program:
    """Alternate the window search and the DAG peephole until neither shortens the program.

    A rewrite by one pass can leave a shape only the other sees (the peephole re-allocates
    registers, which changes which windows are redundant). Never longer than the input.
    """
    from elf_abacus.peephole import optimize

    deadline = time.monotonic() + seconds
    current = program
    while True:
        before = len(current)
        current = superoptimize(
            puzzle, current, max_window, span, max(0.0, deadline - time.monotonic())
        )
        current = optimize(puzzle, current)
        if len(current) >= before or time.monotonic() > deadline:
            return current


def _shrink(job: tuple[Puzzle, Program, int, int, float]) -> Program:
    puzzle, program, max_window, span, seconds = job
    return superoptimize(puzzle, program, max_window, span, seconds)


def main(argv: Sequence[str] | None = None) -> None:
    """Shrink every program of a submission file with the window superoptimiser."""
    parser = argparse.ArgumentParser(prog="elf_abacus.superopt")
    parser.add_argument("--puzzles", type=Path, default=Path("data/puzzles.csv"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--window", type=int, default=MAX_WINDOW)
    parser.add_argument("--span", type=int, default=MAX_SPAN)
    parser.add_argument("--seconds", type=float, default=120.0, help="per puzzle")
    parser.add_argument("submission", type=Path)
    args = parser.parse_args(argv)
    puzzles = load_puzzles(args.puzzles)
    programs = load_submission(args.submission)
    jobs = [(p, programs[p.id], args.window, args.span, args.seconds) for p in puzzles]
    if args.workers > 1:
        with Pool(args.workers) as pool:
            shrunk = pool.map(_shrink, jobs, chunksize=1)
    else:
        shrunk = [_shrink(job) for job in jobs]
    result = {p.id: program for p, program in zip(puzzles, shrunk, strict=True)}
    write_submission(args.out, result)
    before = sum(len(programs[p.id]) for p in puzzles)
    print(f"superoptimized: {before} -> {score_submission(puzzles, result)}")


if __name__ == "__main__":
    main()
